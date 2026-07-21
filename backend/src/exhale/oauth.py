"""OAuth 2.0 authorization flow — provider-generic ("Connect Google/Outlook").

The one-time developer registration (one OAuth app per provider) is shared by
*every* user; each family that signs up connects their own account with a single
click. The authorization-code flow is identical across providers — only the
endpoints, scopes, and a couple of auth params differ — so this module is
parameterized by :class:`OAuthProvider` and serves Google and Microsoft (and any
future provider) through the same functions:

* :func:`authorization_url` — where the "Connect …" button sends the user
  (the provider's own consent screen), carrying a signed ``state`` so the
  callback can trust which family is returning.
* :func:`exchange_code` — turn the one-time code into an access + refresh token.

Refresh tokens are the durable grant; connectors mint fresh access tokens from
them. Tokens are stored per-family, encrypted at rest. Nothing here needs a real
provider account to build or test: the exchange takes an injectable HTTP client,
and state signing is pure.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

STATE_MAX_AGE_SECONDS = 600  # a consent round-trip is well under 10 min


class OAuthStateError(Exception):
    """The callback's ``state`` is malformed, tampered, or expired."""


@dataclass(frozen=True)
class OAuthProvider:
    """Everything provider-specific about an OAuth 2.0 authorization-code flow."""

    name: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    extra_auth_params: dict[str, str] = field(default_factory=dict)
    token_request_includes_scope: bool = False  # Microsoft wants it; Google ignores


GOOGLE = OAuthProvider(
    name="google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=(
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
        "openid",
        "email",
    ),
    extra_auth_params={
        "access_type": "offline",   # get a refresh token
        "prompt": "consent",        # force it even on re-consent
        "include_granted_scopes": "true",
    },
)

MICROSOFT = OAuthProvider(
    name="microsoft",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    scopes=(
        "offline_access",  # required for a refresh token on the MS identity platform
        "https://graph.microsoft.com/Calendars.Read",
        "https://graph.microsoft.com/Mail.Read",
        "openid",
        "email",
    ),
    extra_auth_params={"prompt": "select_account"},
    token_request_includes_scope=True,
)

PROVIDERS: dict[str, OAuthProvider] = {"google": GOOGLE, "microsoft": MICROSOFT}
_ENV_PREFIX = {"google": "EXHALE_GOOGLE", "microsoft": "EXHALE_MSFT"}


@dataclass(frozen=True)
class OAuthAppConfig:
    """The developer's single registered app for one provider — all users share it."""

    provider: OAuthProvider
    client_id: str
    client_secret: str
    redirect_uri: str


def config_from_env(provider_name: str) -> OAuthAppConfig | None:
    """Build the app config for a provider from env, or ``None`` if unset."""

    provider = PROVIDERS[provider_name]
    prefix = _ENV_PREFIX[provider_name]
    cid = os.environ.get(f"{prefix}_CLIENT_ID")
    secret = os.environ.get(f"{prefix}_CLIENT_SECRET")
    redirect = os.environ.get(f"{prefix}_REDIRECT_URI")
    if not (cid and secret and redirect):
        return None
    return OAuthAppConfig(provider, cid, secret, redirect)


# --- signed state (CSRF protection + identity carry-through) -----------------------
def sign_state(family_id: str, secret: str, *, now: float | None = None) -> str:
    """A tamper-evident ``state`` binding the flow to ``family_id``."""

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
    config: OAuthAppConfig, family_id: str, state_secret: str, *, now: float | None = None
) -> str:
    """The URL a "Connect …" button sends the user to (the provider's consent)."""

    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.provider.scopes),
        "state": sign_state(family_id, state_secret, now=now),
        **config.provider.extra_auth_params,
    }
    return f"{config.provider.authorize_url}?{urllib.parse.urlencode(params)}"


def exchange_code(config: OAuthAppConfig, code: str, *, http: httpx.Client | None = None) -> dict:
    """Exchange the one-time authorization code for tokens."""

    client = http or httpx.Client(timeout=30)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri,
    }
    if config.provider.token_request_includes_scope:
        data["scope"] = " ".join(config.provider.scopes)
    resp = client.post(config.provider.token_url, data=data)
    resp.raise_for_status()
    return resp.json()
