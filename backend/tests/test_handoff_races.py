"""R03a: a handoff summary is authorized and built under the same locks release takes (adapted from reviews/r03_regressions.py)."""
import threading

import pytest
from fastapi.testclient import TestClient

from app import handoff
from app.main import app
from tests.conftest import login
from tests.test_trade import DISTRIBUTOR


@pytest.mark.parametrize("read_path", ["get", "take", "repeat_take"])
def test_summary_read_cannot_cross_release_into_a_new_assignment(client, monkeypatch, read_path):
    buyer = login(client, "suresh.buyer@example.test")
    sanjay = login(client, "sanjay.support@example.test")
    vani = login(client, "vani.support@example.test")
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    first = client.post(f"{base}/{conv}/handoff", headers=buyer, json={}).json()["id"]
    if read_path != "take":
        assert client.post(f"/api/v1/staff/handoffs/{first}/take", headers=sanjay).status_code == 200

    checked, new_message_saved = threading.Event(), threading.Event()
    original_summary = handoff.summary
    secret = "Private message after the prior assignment was released"

    def pause_after_authorization(db, assignment):
        if str(assignment.id) == first:
            checked.set()
            # A correct locking implementation prevents release until the read
            # completes. Do not demand that a blocked release win this race.
            new_message_saved.wait(timeout=2)
        return original_summary(db, assignment)

    monkeypatch.setattr(handoff, "summary", pause_after_authorization)
    results, errors = {}, []

    def read_old():
        try:
            with TestClient(app, raise_server_exceptions=False) as other:
                if read_path == "get":
                    results["old"] = other.get(f"/api/v1/staff/handoffs/{first}", headers=sanjay)
                else:
                    results["old"] = other.post(f"/api/v1/staff/handoffs/{first}/take", headers=sanjay)
        except Exception as exc:
            errors.append(exc)

    def release_and_continue():
        try:
            with TestClient(app, raise_server_exceptions=False) as other:
                r = other.post(f"/api/v1/staff/handoffs/{first}/release", headers=sanjay)
                assert r.status_code == 200, r.text
                r = other.post(f"{base}/{conv}/handoff", headers=buyer, json={})
                assert r.status_code == 201, r.text
                second = r.json()["id"]
                r = other.post(f"/api/v1/staff/handoffs/{second}/take", headers=vani)
                assert r.status_code == 200, r.text
                r = other.post(f"{base}/{conv}/messages", headers=buyer, json={"text": secret})
                assert r.status_code == 200, r.text
                new_message_saved.set()
        except Exception as exc:
            errors.append(exc)

    reader = threading.Thread(target=read_old)
    writer = threading.Thread(target=release_and_continue)
    reader.start()
    assert checked.wait(5), "Reader never reached the protected summary path"
    writer.start()
    reader.join(timeout=10)
    writer.join(timeout=10)
    assert not reader.is_alive() and not writer.is_alive()
    assert not errors, errors
    assert new_message_saved.is_set()
    response = results["old"]
    assert response.status_code in (200, 403, 404), response.text
    assert secret not in response.text, "Old assignee received a message committed after release and reassignment"
    # The release still went through, and the new assignee sees the message.
    assert client.get(f"/api/v1/staff/handoffs/{first}", headers=sanjay).status_code == 404
    (current,) = [h for h in client.get("/api/v1/staff/handoffs?scope=mine", headers=vani).json() if h["status"] == "assigned"]
    assert client.get(f"/api/v1/staff/handoffs/{current['id']}", headers=vani).json()["recent_messages"][-2]["text"] == secret  # then the stored paused reply
