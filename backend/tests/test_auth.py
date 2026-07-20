"""Tests for accounts, sessions, and family-scoped access control (Part 3)."""

import pytest
from fastapi.testclient import TestClient

from exhale.api import app
from exhale.auth import (
    AuthError,
    InMemoryAuthStore,
    hash_password,
    new_invite_code,
    verify_password,
)

client = TestClient(app)


# --- primitives ---------------------------------------------------------------
def test_password_hash_roundtrip():
    h, s = hash_password("correct horse battery")
    assert verify_password("correct horse battery", h, s)
    assert not verify_password("wrong password!", h, s)


def test_short_password_rejected():
    with pytest.raises(ValueError):
        hash_password("short")


def test_invite_code_shape():
    code = new_invite_code()
    assert len(code) == 8
    assert not set(code) & {"0", "O", "1", "I"}  # no ambiguous characters


# --- store behavior -----------------------------------------------------------
def test_signup_login_and_token_lifecycle():
    store = InMemoryAuthStore()
    user, token = store.signup("a@b.com", "password123", "Andrew")
    assert store.user_for_token(token).user_id == user.user_id

    _, token2 = store.login("A@B.COM", "password123")  # email normalized
    assert store.user_for_token(token2).user_id == user.user_id

    store.revoke_token(token)
    assert store.user_for_token(token) is None
    assert store.user_for_token("bogus") is None


def test_duplicate_email_and_bad_login():
    store = InMemoryAuthStore()
    store.signup("a@b.com", "password123", "Andrew")
    with pytest.raises(AuthError):
        store.signup("a@b.com", "password456", "Other")
    with pytest.raises(AuthError):
        store.login("a@b.com", "wrong-password")


def test_invite_code_joins_same_family():
    store = InMemoryAuthStore()
    parent, _ = store.signup("a@b.com", "password123", "Andrew")
    code = store.invite_code_for(parent.family_id)
    spouse, _ = store.signup("c@d.com", "password123", "Alicia", invite_code=code)
    assert spouse.family_id == parent.family_id
    with pytest.raises(AuthError):
        store.signup("e@f.com", "password123", "X", invite_code="WRONGCOD")


# --- API flow -----------------------------------------------------------------
def _signup(email="parent@example.com", name="Andrew", invite_code=None):
    r = client.post("/v1/auth/signup", json={
        "email": email, "password": "password123",
        "display_name": name, "invite_code": invite_code,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_api_signup_me_and_family_access():
    session = _signup(email="me@example.com")
    token, family_id = session["token"], session["user"]["family_id"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/v1/me", headers=headers).json()
    assert me["email"] == "me@example.com"
    assert me["invite_code"] == session["invite_code"]

    # Token grants access to own family...
    assert client.get(f"/v1/families/{family_id}/briefing", headers=headers).status_code in (200, 404)
    # ...and is refused for someone else's.
    r = client.get("/v1/families/family_demo_001/briefing", headers=headers)
    assert r.status_code == 403


def test_api_enforcement_blocks_anonymous(monkeypatch):
    monkeypatch.setenv("EXHALE_REQUIRE_AUTH", "1")
    assert client.get("/v1/families/family_demo_001/briefing").status_code == 401
    assert client.get("/v1/me").status_code == 401


def test_api_dev_mode_allows_anonymous(monkeypatch):
    monkeypatch.setenv("EXHALE_REQUIRE_AUTH", "0")
    assert client.get("/v1/families/family_demo_001/briefing").status_code == 200


def test_api_caregiver_invite_flow():
    parent = _signup(email="p1@example.com")
    spouse = _signup(email="p2@example.com", name="Alicia",
                     invite_code=parent["invite_code"])
    assert spouse["user"]["family_id"] == parent["user"]["family_id"]

    # Both see the same family data; profile keeps the founder's name.
    fam = parent["user"]["family_id"]
    for sess in (parent, spouse):
        r = client.get(f"/v1/families/{fam}/drafts",
                       headers={"Authorization": f"Bearer {sess['token']}"})
        assert r.status_code == 200


def test_api_logout_revokes():
    session = _signup(email="bye@example.com")
    headers = {"Authorization": f"Bearer {session['token']}"}
    assert client.get("/v1/me", headers=headers).status_code == 200
    client.post("/v1/auth/logout", headers=headers)
    assert client.get("/v1/me", headers=headers).status_code == 401


def test_api_signup_validation_errors():
    r = client.post("/v1/auth/signup", json={
        "email": "x@y.com", "password": "short", "display_name": "X"})
    assert r.status_code == 400
    _signup(email="dup@example.com")
    r = client.post("/v1/auth/signup", json={
        "email": "dup@example.com", "password": "password123", "display_name": "X"})
    assert r.status_code == 400
