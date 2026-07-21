"""Tests for the provider-generic OAuth flow — no real accounts required."""

import httpx
import pytest

from exhale.oauth import (
    GOOGLE,
    MICROSOFT,
    OAuthAppConfig,
    OAuthStateError,
    authorization_url,
    config_from_env,
    exchange_code,
    sign_state,
    verify_state,
)

GOOGLE_CFG = OAuthAppConfig(GOOGLE, "gcid.apps.googleusercontent.com", "gsecret",
                            "https://app.exhale.example/v1/oauth/google/callback")
MSFT_CFG = OAuthAppConfig(MICROSOFT, "mcid", "msecret",
                          "https://app.exhale.example/v1/oauth/microsoft/callback")
SECRET = "server-state-secret"


# --- signed state -----------------------------------------------------------------
def test_state_roundtrips_family_id():
    assert verify_state(sign_state("fam_42", SECRET, now=1000), SECRET, now=1000) == "fam_42"


def test_tampered_state_is_rejected():
    state = sign_state("fam_42", SECRET, now=1000)
    with pytest.raises(OAuthStateError, match="signature"):
        verify_state(state.replace("fam_42", "fam_99"), SECRET, now=1000)


def test_expired_state_is_rejected():
    with pytest.raises(OAuthStateError, match="expired"):
        verify_state(sign_state("fam_42", SECRET, now=1000), SECRET, now=1000 + 601)


def test_malformed_state_is_rejected():
    with pytest.raises(OAuthStateError, match="malformed"):
        verify_state("nonsense", SECRET)


# --- authorization url (both providers) -------------------------------------------
def test_google_authorization_url():
    url = authorization_url(GOOGLE_CFG, "fam_42", SECRET, now=1000)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "access_type=offline" in url and "prompt=consent" in url
    assert "calendar.readonly" in url and "gmail.readonly" in url
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    assert verify_state(state, SECRET, now=1000) == "fam_42"


def test_microsoft_authorization_url():
    url = authorization_url(MSFT_CFG, "fam_7", SECRET, now=1000)
    assert url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?")
    assert "offline_access" in url            # refresh token on MS identity platform
    assert "Calendars.Read" in url
    assert "prompt=select_account" in url


# --- code exchange ----------------------------------------------------------------
def test_google_exchange_omits_scope_in_body():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"})

    exchange_code(GOOGLE_CFG, "code-1", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert "oauth2.googleapis.com/token" in seen["url"]
    assert "grant_type=authorization_code" in seen["body"]
    assert "scope=" not in seen["body"]  # Google: no scope on the exchange


def test_microsoft_exchange_includes_scope_in_body():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"})

    exchange_code(MSFT_CFG, "code-1", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert "login.microsoftonline.com" in seen["url"]
    assert "scope=" in seen["body"]  # Microsoft requires scope on the exchange


# --- config from env --------------------------------------------------------------
def test_config_from_env_none_when_unset(monkeypatch):
    for v in ("EXHALE_GOOGLE_CLIENT_ID", "EXHALE_GOOGLE_CLIENT_SECRET", "EXHALE_GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(v, raising=False)
    assert config_from_env("google") is None


def test_config_from_env_google(monkeypatch):
    monkeypatch.setenv("EXHALE_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("EXHALE_GOOGLE_CLIENT_SECRET", "sec")
    monkeypatch.setenv("EXHALE_GOOGLE_REDIRECT_URI", "https://x/cb")
    cfg = config_from_env("google")
    assert cfg is not None and cfg.provider is GOOGLE and cfg.client_id == "cid"


def test_config_from_env_microsoft(monkeypatch):
    monkeypatch.setenv("EXHALE_MSFT_CLIENT_ID", "mid")
    monkeypatch.setenv("EXHALE_MSFT_CLIENT_SECRET", "msec")
    monkeypatch.setenv("EXHALE_MSFT_REDIRECT_URI", "https://x/mcb")
    cfg = config_from_env("microsoft")
    assert cfg is not None and cfg.provider is MICROSOFT and cfg.client_id == "mid"
