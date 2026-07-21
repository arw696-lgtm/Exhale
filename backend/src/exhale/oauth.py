"""Google OAuth 2.0 authorization flow (productization: the "Connect Google" button).

The one-time developer registration (a Google Cloud project → one client id +
secret) is shared by *every* user; each family that signs up just clicks
"Connect Google" and grants access to their own account. This module implements
that flow, provider-agnostic in spirit but Google-shaped in specifics:

* :func:`authorization_url` — where "Connect Google" sends the user (Google's own
  consent screen), carrying a signed ``state`` so the callback can trust which
  family is returning.
* :func:`exchange_code` — turn the one-time code Google hands back into an
  access + refresh token for that family.

The refresh token is the durable grant; connectors mint fresh access tokens from
it. Tokens are stored per-family (encrypted at rest by the existing envelope
pipeline) — never in the code, never shared between families.

Nothing here needs a real Google account to build or test: the token exchange
takes an injectable HTTP client, and the state signing is pure.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.parse
from dataclasses import dataclass

import httpx

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

# Read-only scopes — Exhale observes, it does not write to the user's account.
GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
)

STATE_MAX_AGE_SECONDS = 600  # a consent round-trip should take well under 10 min


class OAuthNotConfigured(Exception):
    """The Google OAuth app credentials are not set (developer-side, one time)."""


class OAuthStateError(Exception):
    """The callback's ``state`` is malformed, tampered, or expired."""


@dataclass(frozen=True)
class GoogleOAuthConfig:
    """The developer's single registered OAuth app — one set, all users."""

    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "GoogleOAuthConfig | None":
        cid = os.environ.get("EXHALE_GOOGLE_CLIENT_ID")
        secret = os.environ.get("EXHALE_GOOGLE_CLIENT_SECRET")
        redirect = os.environ.get("EXHALE_GOOGLE_REDIRECT_URI")
        if not (cid and secret and redirect):
            return None
        return cls(client_id=cid, client_secret=secret, redirect_uri=redirect)


# --- signed state (CSRF protection + identity carry-through) -----------------------
def sign_state(family_id: str, secret: str, *, now: float | None = None) -> str:
    """A tamper-evident ``state`` token binding the flow to ``family_id``.

    Google echoes ``state`` back to the callback verbatim; signing it lets the
    callback trust which family is returning without a session cookie, and
    rejects forged or replayed callbacks.
    """

    ts = str(int(now if now is not None else time.time()))
    payload = f"{family_id}:{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def verify_state(state: str, secret: str, *, now: float | None = None) -> str:
    """Validate a ``state`` token and return the family id it carries."""

    try:
        family_id, ts, sig = state.rsplit(":", 2)
    except ValueError as exc:
        raise OAuthStateError("malformed state") from exc
    payload = f"{family_id}:{ts}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise OAuthStateError("bad state signature")
    age = int(now if now is not None else time.time()) - int(ts)
    if age > STATE_MAX_AGE_SECONDS:
        raise OAuthStateError("state expired")
    return family_id


# --- the flow ----------------------------------------------------------------------
def authorization_url(
    config: GoogleOAuthConfig,
    family_id: str,
    state_secret: str,
    *,
    scopes: tuple[str, ...] = GOOGLE_SCOPES,
    now: float | None = None,
) -> str:
    """The URL the "Connect Google" button sends the user to (Google's consent)."""

    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",   # ask for a refresh token
        "prompt": "consent",        # force the refresh token even on re-consent
        "include_granted_scopes": "true",
        "state": sign_state(family_id, state_secret, now=now),
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code(config: GoogleOAuthConfig, code: str, *, http: httpx.Client | None = None) -> dict:
    """Exchange the one-time authorization code for tokens.

    Returns Google's token response (``access_token``, ``refresh_token``,
    ``expires_in``, ``scope``, …).
    """

    client = http or httpx.Client(timeout=30)
    resp = client.post(
        GOOGLE_TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": config.redirect_uri,
        },
    )
    resp.raise_for_status()
    return resp.json()
