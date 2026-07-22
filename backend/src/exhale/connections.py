"""Per-member OAuth connection records inside the family profile.

Connections used to be one record per provider per family
(``connections[provider] = tokens``) — so when a second member connected the
same provider, their tokens silently replaced the first member's and that
inbox/calendar stopped feeding the brain. Now each provider holds a map of
accounts keyed by the member who connected it::

    connections["google"]["user_ab12"] = {access_token, refresh_token, ...}

Legacy flat records (a token dict directly under the provider) are read as a
single account under :data:`LEGACY_KEY` — stored profiles keep working and
keep their original sync watermark. Sync paths iterate *all* usable accounts;
nothing is displaced, both inboxes feed the same family graph (downstream
dedupe already handles resends/repeats).
"""

from __future__ import annotations

# The account key for records stored before per-member keying (and for
# connections made in anonymous dev mode, where there is no user).
LEGACY_KEY = "primary"


def _usable(record: dict) -> bool:
    return bool(record.get("refresh_token") or record.get("access_token"))


def accounts_for(connections: dict | None, provider: str) -> dict[str, dict]:
    """All usable accounts for ``provider``, keyed by member (normalized).

    Accepts both shapes: the legacy flat token record (→ one account under
    :data:`LEGACY_KEY`) and the per-member map.
    """

    raw = (connections or {}).get(provider)
    if not raw or not isinstance(raw, dict):
        return {}
    if "access_token" in raw or "refresh_token" in raw:  # legacy flat record
        return {LEGACY_KEY: raw} if _usable(raw) else {}
    return {key: rec for key, rec in raw.items()
            if isinstance(rec, dict) and _usable(rec)}


def first_account(connections: dict | None, provider: str) -> dict | None:
    """One usable account (legacy first, then deterministic order) or None.

    For paths that need *a* grant rather than every grant — e.g. writing a
    calendar event. Reading paths should iterate :func:`accounts_for`.
    """

    accounts = accounts_for(connections, provider)
    if not accounts:
        return None
    if LEGACY_KEY in accounts:
        return accounts[LEGACY_KEY]
    return accounts[sorted(accounts)[0]]


def merge_account(connections: dict | None, provider: str, user_key: str,
                  record: dict) -> dict:
    """A new connections dict with ``record`` stored for one member.

    Normalizes a legacy flat record into the per-member shape first, so an
    upgrade-in-place never drops the original member's tokens.
    """

    conns = dict(connections or {})
    existing = conns.get(provider)
    if existing and ("access_token" in existing or "refresh_token" in existing):
        existing = {LEGACY_KEY: existing}  # promote legacy record, keep it
    accounts = dict(existing or {})
    accounts[user_key] = record
    conns[provider] = accounts
    return conns


def watermark_key(provider: str, user_key: str) -> str:
    """The per-account incremental-sync watermark key.

    The legacy/primary Google account keeps the historical ``last_sync_at``
    key so pre-upgrade families don't re-scan 180 days after deploy; every
    other account gets its own scoped key (two inboxes must never share a
    watermark — the second would silently skip everything older than the
    first's last sync).
    """

    if provider == "google" and user_key == LEGACY_KEY:
        return "last_sync_at"
    return f"last_sync_at:{provider}:{user_key}"
