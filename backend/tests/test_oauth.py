"""Tests for the Google OAuth flow — no real Google account required."""

import httpx
import pytest

from exhale.oauth import (
    GoogleOAuthConfig,
    OAuthStateError,
    authorization_url,
    exchange_code,
    sign_state,
    verify_state,
)

CFG = GoogleOAuthConfig(
    client_id="client-123.apps.googleusercontent.com",
    client_secret="secret-xyz",
    redirect_uri="https://app.exhale.example/v1/oauth/google/callback",
)
SECRET = "server-state-secret"


# --- signed state -----------------------------------------------------------------
def test_state_roundtrips_family_id():
    state = sign_state("fam_42", SECRET, now=1000)
    assert verify_state(state, SECRET, now=1000) == "fam_42"


def test_tampered_state_is_rejected():
    state = sign_state("fam_42", SECRET, now=1000)
    forged = state.replace("fam_42", "fam_99")  # try to hijack another family
    with pytest.raises(OAuthStateError, match="signature"):
        verify_state(forged, SECRET, now=1000)


def test_expired_state_is_rejected():
    state = sign_state("fam_42", SECRET, now=1000)
    with pytest.raises(OAuthStateError, match="expired"):
        verify_state(state, SECRET, now=1000 + 601)


def test_malformed_state_is_rejected():
    with pytest.raises(OAuthStateError, match="malformed"):
        verify_state("not-a-valid-state", SECRET)


def test_wrong_secret_is_rejected():
    state = sign_state("fam_42", SECRET, now=1000)
    with pytest.raises(OAuthStateError):
        verify_state(state, "different-secret", now=1000)


# --- authorization url ------------------------------------------------------------
def test_authorization_url_has_the_required_params():
    url = authorization_url(CFG, "fam_42", SECRET, now=1000)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=client-123" in url
    assert "response_type=code" in url
    assert "access_type=offline" in url          # so we get a refresh token
    assert "prompt=consent" in url
    assert "calendar.readonly" in url
    assert "gmail.readonly" in url
    # state carries the (verifiable) family id
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    assert verify_state(state, SECRET, now=1000) == "fam_42"


# --- code exchange ----------------------------------------------------------------
def test_exchange_code_posts_and_returns_tokens():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={
            "access_token": "at-1", "refresh_token": "rt-1",
            "expires_in": 3599, "scope": "calendar.readonly gmail.readonly"})

    tokens = exchange_code(CFG, "auth-code-abc",
                           http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert tokens["access_token"] == "at-1"
    assert tokens["refresh_token"] == "rt-1"
    assert "oauth2.googleapis.com/token" in seen["url"]
    assert "grant_type=authorization_code" in seen["body"]
    assert "code=auth-code-abc" in seen["body"]


# --- config from env --------------------------------------------------------------
def test_config_from_env_none_when_unset(monkeypatch):
    for v in ("EXHALE_GOOGLE_CLIENT_ID", "EXHALE_GOOGLE_CLIENT_SECRET",
              "EXHALE_GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(v, raising=False)
    assert GoogleOAuthConfig.from_env() is None


def test_config_from_env_built_when_set(monkeypatch):
    monkeypatch.setenv("EXHALE_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("EXHALE_GOOGLE_CLIENT_SECRET", "sec")
    monkeypatch.setenv("EXHALE_GOOGLE_REDIRECT_URI", "https://x/cb")
    cfg = GoogleOAuthConfig.from_env()
    assert cfg is not None and cfg.client_id == "cid"
