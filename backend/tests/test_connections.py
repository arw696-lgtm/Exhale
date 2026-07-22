"""Per-member OAuth connections: no more silent displacement.

The bug this guards against: connections were one record per provider per
family, so the second parent connecting Gmail silently overwrote the first
parent's tokens and that inbox stopped feeding the brain — no error, nothing.
"""

from fastapi.testclient import TestClient

from exhale.api import app, store
from exhale.connections import (
    LEGACY_KEY,
    accounts_for,
    first_account,
    merge_account,
    watermark_key,
)

client = TestClient(app)


# --- the module ---------------------------------------------------------------
def test_legacy_flat_record_reads_as_one_account():
    conns = {"google": {"access_token": "tokA", "connected_at": "2026-01-01"}}
    assert accounts_for(conns, "google") == {LEGACY_KEY: conns["google"]}
    assert first_account(conns, "google")["access_token"] == "tokA"
    assert accounts_for(conns, "microsoft") == {}
    assert accounts_for(None, "google") == {}


def test_merge_preserves_the_legacy_account():
    conns = {"google": {"access_token": "andys", "connected_at": "2026-01-01"}}
    merged = merge_account(conns, "google", "user_ali", {"access_token": "alis"})
    accounts = accounts_for(merged, "google")
    # Both survive — the original was promoted, not displaced.
    assert accounts[LEGACY_KEY]["access_token"] == "andys"
    assert accounts["user_ali"]["access_token"] == "alis"


def test_merge_updates_own_slot_only():
    conns = merge_account(None, "google", "user_a", {"access_token": "a1"})
    conns = merge_account(conns, "google", "user_b", {"access_token": "b1"})
    conns = merge_account(conns, "google", "user_a", {"access_token": "a2"})  # re-consent
    accounts = accounts_for(conns, "google")
    assert accounts["user_a"]["access_token"] == "a2"
    assert accounts["user_b"]["access_token"] == "b1"


def test_watermark_keys_are_per_account_with_legacy_continuity():
    # The pre-upgrade Google account keeps its historical key (no 180-day
    # rescan after deploy); every other account gets its own clock.
    assert watermark_key("google", LEGACY_KEY) == "last_sync_at"
    assert watermark_key("google", "user_ali") == "last_sync_at:google:user_ali"
    assert watermark_key("microsoft", LEGACY_KEY) == "last_sync_at:microsoft:primary"


# --- the OAuth callback files tokens per member ---------------------------------
class _FakeOAuthConfig:
    client_id = "cid"
    client_secret = "secret"


def _connect_as(monkeypatch, fam: str, user_id: str, token: str) -> None:
    """Drive the real callback with a signed state for (family, member)."""

    from exhale.api import _oauth_state_secret
    from exhale.oauth import sign_state

    monkeypatch.setattr("exhale.oauth.config_from_env",
                        lambda provider: _FakeOAuthConfig())
    monkeypatch.setattr("exhale.oauth.exchange_code",
                        lambda config, code: {"access_token": token,
                                              "refresh_token": f"r_{token}",
                                              "scope": "gmail.readonly"})
    state = sign_state(f"{fam}|{user_id}", _oauth_state_secret())
    r = client.get("/v1/oauth/google/callback",
                   params={"code": "authcode", "state": state})
    assert r.status_code == 200, r.text
    assert r.json()["account"] == user_id


def test_two_members_connecting_gmail_both_persist(monkeypatch):
    fam = "fam_two_gmails"
    _connect_as(monkeypatch, fam, "user_andy", "tok_andy")
    _connect_as(monkeypatch, fam, "user_ali", "tok_ali")

    accounts = accounts_for(store.profile(fam).get("connections"), "google")
    assert accounts["user_andy"]["access_token"] == "tok_andy"
    assert accounts["user_ali"]["access_token"] == "tok_ali"

    status = client.get(f"/v1/families/{fam}/connections").json()["google"]
    assert status["connected"] is True
    assert status["accounts"] == 2


# --- both accounts feed a sync run ------------------------------------------------
class _FakeResult:
    scanned = 3
    extracted = 1
    committed = 1
    pending = 0
    rejected = 0
    snapshot = {"headline": "ok"}


def test_manual_gmail_sync_pulls_every_connected_account(monkeypatch):
    fam = "fam_sync_both"
    _connect_as(monkeypatch, fam, "user_andy", "tok_andy")
    _connect_as(monkeypatch, fam, "user_ali", "tok_ali")

    runs: list[tuple[str, str]] = []  # (access_token, watermark_key)

    def fake_sync(connector, store_, family_id, ctx, *, extractor, watermark_key):
        runs.append((connector._access_token, watermark_key))
        return _FakeResult()

    monkeypatch.setattr("exhale.api.run_incremental_sync", fake_sync)
    r = client.post(f"/v1/families/{fam}/sync/gmail", json={})
    assert r.status_code == 200
    body = r.json()

    # Both inboxes pulled, independently, each on its own watermark.
    assert {t for t, _ in runs} == {"tok_andy", "tok_ali"}
    assert {w for _, w in runs} == {"last_sync_at:google:user_andy",
                                    "last_sync_at:google:user_ali"}
    assert set(body["accounts"]) == {"user_andy", "user_ali"}
    assert body["scanned"] == 6  # totals aggregate across accounts


def test_auto_sync_iterates_all_gmail_accounts(monkeypatch):
    from exhale.auto_sync import run_cycle
    from exhale.store import HouseholdStore

    local = HouseholdStore()
    fam = "fam_auto_both"
    local.set_profile(fam, connections={"google": {
        "user_andy": {"access_token": "tok_andy"},
        "user_ali": {"access_token": "tok_ali"},
    }})

    runs: list[tuple[str, str]] = []

    def fake_sync(connector, store_, family_id, ctx, *, extractor, watermark_key):
        runs.append((connector._access_token, watermark_key))
        return _FakeResult()

    monkeypatch.setattr("exhale.auto_sync.run_incremental_sync", fake_sync)
    report = run_cycle(local, extractor=None)
    gmail = report["families"][fam]["gmail"]
    assert set(gmail) == {"user_andy", "user_ali"}
    assert all(entry == {"scanned": 3, "committed": 1} for entry in gmail.values())
    assert {t for t, _ in runs} == {"tok_andy", "tok_ali"}
    assert len({w for _, w in runs}) == 2  # distinct watermarks


def test_auto_sync_still_reads_legacy_flat_connection(monkeypatch):
    from exhale.auto_sync import run_cycle
    from exhale.store import HouseholdStore

    local = HouseholdStore()
    fam = "fam_auto_legacy"
    local.set_profile(fam, connections={"google": {"access_token": "old_tok"}})

    runs: list[tuple[str, str]] = []

    def fake_sync(connector, store_, family_id, ctx, *, extractor, watermark_key):
        runs.append((connector._access_token, watermark_key))
        return _FakeResult()

    monkeypatch.setattr("exhale.auto_sync.run_incremental_sync", fake_sync)
    run_cycle(local, extractor=None)
    # The pre-upgrade account still syncs — on its original watermark key.
    assert runs == [("old_tok", "last_sync_at")]


def test_replay_uses_the_remembered_members_account():
    from exhale.auto_sync import _tokens

    profile = {"connections": {"google": {
        "user_andy": {"access_token": "tok_andy"},
        "user_ali": {"access_token": "tok_ali"},
    }}}
    assert _tokens(profile, "google", account="user_ali")["access_token"] == "tok_ali"
    # A revoked member's replay degrades to another grant, never breaks.
    assert _tokens(profile, "google", account="user_gone") is not None
