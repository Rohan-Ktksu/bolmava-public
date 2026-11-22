"""Live conversation change signals (SPEC.md 6.7 events stream).

One background thread per API process LISTENs on PostgreSQL and wakes the open streams of the changed
conversation. Streams never hold a database connection or a worker thread of their own.
"""
import asyncio
import threading
import time
from collections.abc import AsyncIterator

import psycopg

from app.db import engine

CHANNEL = "conversation_events"
STREAM_SECONDS = 300  # then the client reconnects and is authorized again
KEEPALIVE_SECONDS = 15

# shortcut: in-process fan-out from one LISTEN connection; behind several API hosts each process listens on its own,
# and production notifications that reach a closed browser need the outbox/SQS worker (SPEC.md 9.8).
_subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
_lock = threading.Lock()
_listener: threading.Thread | None = None


def _wake(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    # A full queue already has a wake-up pending; the client re-reads everything new, so one is enough.
    loop.call_soon_threadsafe(lambda: queue.full() or queue.put_nowait(None))


def _listen() -> None:
    url = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    while True:
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(f"LISTEN {CHANNEL}")
                with _lock:  # anything committed while reconnecting is unknown: tell every stream to re-read
                    for subs in _subscribers.values():
                        for loop, queue in subs:
                            _wake(loop, queue)
                for note in conn.notifies():
                    with _lock:
                        for loop, queue in _subscribers.get(note.payload, ()):
                            _wake(loop, queue)
        except (psycopg.Error, OSError):
            time.sleep(1)  # database restart or network blip: reconnect; clients also keep a slow safety poll


def _subscribe(conversation_id: str) -> asyncio.Queue:
    global _listener
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    with _lock:
        _subscribers.setdefault(conversation_id, set()).add((asyncio.get_running_loop(), queue))
        if _listener is None:
            _listener = threading.Thread(target=_listen, name="conversation-events", daemon=True)
            _listener.start()
    return queue


def _unsubscribe(conversation_id: str, queue: asyncio.Queue) -> None:
    with _lock:
        subs = _subscribers.get(conversation_id, set())
        subs.discard((asyncio.get_running_loop(), queue))
        if not subs:
            _subscribers.pop(conversation_id, None)


async def stream(conversation_id: str) -> AsyncIterator[str]:
    """Server-sent events: `ready` once subscribed, `changed` on each wake-up, keepalive comments between."""
    queue = _subscribe(conversation_id)
    try:
        yield "event: ready\ndata: {}\n\n"
        deadline = time.monotonic() + STREAM_SECONDS
        while (left := deadline - time.monotonic()) > 0:
            try:
                await asyncio.wait_for(queue.get(), timeout=min(KEEPALIVE_SECONDS, left))
                yield "event: changed\ndata: {}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    finally:
        _unsubscribe(conversation_id, queue)
