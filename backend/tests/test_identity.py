import time

import pytest
from pydantic import ValidationError

from app import auth
from app.config import Settings
from app.seed import _id
from tests.conftest import login

SELLER_ORG = _id("org:sri-lakshmi")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_local_users_and_me(client):
    emails = [u["email"] for u in client.get("/api/v1/auth/local/users").json()]
    assert "ravi.seller@example.test" in emails
    me = client.get("/api/v1/me", headers=login(client, "RAVI.seller@example.test")).json()
    assert me["memberships"][0]["role"] == "admin"
    assert me["memberships"][0]["organization"]["id"] == str(SELLER_ORG)


def test_unknown_email_rejected(client):
    r = client.post("/api/v1/auth/local/session", json={"email": "nobody@example.test"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("header", [None, "Bearer junk", "Bearer a.b.c"])
def test_bad_tokens_rejected(client, header):
    r = client.get("/api/v1/me", headers={"Authorization": header} if header else {})
    assert r.status_code == 401


@pytest.mark.parametrize("raw", [b"\xff", "\u0663".encode()])
def test_non_ascii_signature_rejected(client, raw):
    # bytes header so the client does not reject non-ASCII before it reaches the app
    token = f"{_id('user:ravi.seller@example.test')}.{int(time.time()) + 600}.".encode() + raw
    assert client.get("/api/v1/me", headers={"Authorization": b"Bearer " + token}).status_code == 401


@pytest.mark.parametrize("token", ["a.b", "a.b.c.d", "not-a-uuid.123.sig", f"{_id('x')}.soon.sig"])
def test_malformed_tokens_rejected(client, token):
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_tampered_and_expired_tokens_rejected(client, monkeypatch):
    token = login(client, "ravi.seller@example.test")["Authorization"]
    other = str(_id("user:kiran.retail@example.test"))
    user_id, expires, sig = token.removeprefix("Bearer ").split(".")
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {other}.{expires}.{sig}"}).status_code == 401
    monkeypatch.setattr(auth.time, "time", lambda: time.time_ns() / 1e9 + auth.TOKEN_TTL_SECONDS + 1)
    assert client.get("/api/v1/me", headers={"Authorization": token}).status_code == 401


def test_production_refuses_local_auth():
    with pytest.raises(ValidationError):
        Settings(app_env="production", auth_mode="local")
    with pytest.raises(ValidationError):
        Settings(app_env="production", auth_mode="cognito")


def test_create_org_makes_caller_admin(client):
    h = login(client, "kiran.retail@example.test")
    r = client.post("/api/v1/orgs", headers=h, json={"name": "Kiran Wholesale (Fictional)", "city": "Visakhapatnam",
                                                      "state": "Andhra Pradesh", "can_sell": True, "can_buy": False})
    assert r.status_code == 201
    org = r.json()
    assert org["verification_status"] == "simulated_unverified"
    roles = {m["organization"]["id"]: m["role"] for m in client.get("/api/v1/me", headers=h).json()["memberships"]}
    assert roles[org["id"]] == "admin"


def test_retried_registration_returns_the_same_org(client):
    # F05: a lost response and a retry with the same key must not register the business twice.
    h = login(client, "kiran.retail@example.test")
    body = {"name": "Retry Traders (Fictional)", "city": "Tenali", "state": "Andhra Pradesh", "can_sell": True, "can_buy": True}
    first = client.post("/api/v1/orgs", headers={**h, "Idempotency-Key": "reg-1"}, json=body)
    again = client.post("/api/v1/orgs", headers={**h, "Idempotency-Key": "reg-1"}, json=body)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    mine = [m for m in client.get("/api/v1/me", headers=h).json()["memberships"] if m["organization"]["name"] == body["name"]]
    assert len(mine) == 1
    changed = client.post("/api/v1/orgs", headers={**h, "Idempotency-Key": "reg-1"}, json={**body, "city": "Guntur"})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "idempotency_key_reused"
    # Keys belong to the person: someone else using the same key registers their own business.
    other = client.post("/api/v1/orgs", headers={**login(client, "lakshmi.admin@example.test"), "Idempotency-Key": "reg-1"}, json=body)
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]


def test_org_needs_a_capability(client):
    r = client.post("/api/v1/orgs", headers=login(client, "kiran.retail@example.test"),
                    json={"name": "X", "city": "Y", "state": "Z", "can_sell": False, "can_buy": False})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


def test_non_member_cannot_see_org(client):
    h = login(client, "kiran.retail@example.test")
    assert client.get(f"/api/v1/orgs/{SELLER_ORG}", headers=h).status_code == 404
    assert client.get(f"/api/v1/orgs/{SELLER_ORG}", headers=login(client, "anitha.catalog@example.test")).status_code == 200
