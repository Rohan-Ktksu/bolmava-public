"""Refuse to run destructive test fixtures against anything but a disposable local test database."""
import os

from sqlalchemy.engine import make_url

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Query parameters that cannot change which server or database the driver connects to.
SAFE_PARAMS = {"sslmode", "connect_timeout", "application_name"}
# libpq environment variables that can redirect a connection even when the URL names a host.
ROUTING_ENV = ("PGHOSTADDR", "PGSERVICE")


def effective_target(url: str) -> tuple:
    """(host, port, database) exactly as the PostgreSQL driver will receive them, including query overrides."""
    u = make_url(url)
    _, kwargs = u.get_dialect()().create_connect_args(u)
    host, port = kwargs.get("host"), kwargs.get("port")
    # Query values arrive as strings ("5432", "LOCALHOST"); the driver treats them like 5432 and localhost.
    return host.lower() if host else host, int(port) if port is not None else None, kwargs.get("dbname")


def check_test_database(test_url: str, app_url: str, allowed_host: str | None = None, env=os.environ) -> None:
    unsafe = sorted(set(make_url(test_url).query) - SAFE_PARAMS)
    if unsafe:
        raise ValueError(f"TEST_DATABASE_URL may not set connection parameters {unsafe}")
    if routing := [name for name in ROUTING_ENV if env.get(name)]:
        raise ValueError(f"unset {', '.join(routing)}; they can redirect the test connection")
    host, port, db = effective_target(test_url)
    if not (host and port and db):
        raise ValueError("TEST_DATABASE_URL must state host, port and database explicitly")
    if not db.endswith("_test"):
        raise ValueError(f"database name {db!r} does not end with _test")
    if host not in LOCAL_HOSTS and host != allowed_host:
        raise ValueError(f"host {host!r} is not local; set TEST_DATABASE_ALLOWED_HOST={host} if it is disposable")
    a_host, a_port, a_db = effective_target(app_url)
    same_host = host == a_host or {host, a_host or "localhost"} <= LOCAL_HOSTS
    if same_host and port == (a_port or 5432) and db == a_db:
        raise ValueError("TEST_DATABASE_URL points at the application database (DATABASE_URL)")
