"""Starting over without losing the household.

A scan that ran before a filter existed cannot be repaired item by item, and
re-running it changes nothing: the scan dedupes on message id, so it skips
every message it has already read. Clearing the derived data is the only way
to get a better extractor applied to mail already seen.

The whole risk of that operation is over-reach. A person who has just spent an
evening connecting Google, entering a coverage model and inviting a helper
must not lose any of it because the mail scan was junk. These tests pin the
boundary in both directions: the derived data goes, the household stays.
"""

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.schemas import ArtifactTier, ExtractionPayload, FactOrigin
from exhale.store import DERIVED_PROFILE_KEYS, HouseholdStore

client = TestClient(app)


def _payload(name, ref):
    return ExtractionPayload(
        extracted_event=name,
        event_date="2026-10-02",
        action_required=True,
        confidence_score=0.97,
        artifact_tier=ArtifactTier.CONFIRMATION,
        event_date_origin=FactOrigin.OBSERVED,
        source_reference=ref,
    )


def _loaded_store(fam="fam_reset"):
    store = HouseholdStore()
    store.ingest(fam, _payload("Return the camp form", "gmail_1"))
    store.ingest(fam, _payload("Soccer practice", "gmail_2"))
    return store, fam


def test_reset_clears_the_ledger_and_the_graph():
    store, fam = _loaded_store()
    assert store.ledger(fam) and store.graph(fam).nodes

    removed = store.reset_ingested(fam)

    assert store.ledger(fam) == []
    assert store.graph(fam).nodes == {}
    assert store.graph(fam).edges == {}
    assert removed["ledger_entries"] == 2
    assert removed["graph_nodes"] > 0


def test_reset_keeps_everything_a_person_set_up_by_hand():
    """The failure that would actually hurt: losing the evening's setup."""

    store, fam = _loaded_store()
    setup = {
        "coverage_model": {"children": ["Stevie"]},
        "connections": {"google": {"refresh_token": "xyz"}},
        "sync_configs": [{"provider": "google"}],
        "helpers": [{"name": "Grandma"}],
        "away_periods": [{"label": "Duluth", "start": "2026-11-01"}],
        "tasks": [{"title": "call the dentist"}],
        "feed_token": "tok_abc",
        "autonomy": "prepare",
        "parent_first_name": "Andy",
        "notify_email": "andy@example.com",
        "llm_usage": {"total_usd": 1.23},
        "intentions": [{"what": "read more"}],
    }
    store.set_profile(fam, **setup)

    store.reset_ingested(fam)

    assert store.profile(fam) == setup, "a reset took something a person entered"


def test_reset_clears_the_keys_that_point_at_vanished_extractions():
    store, fam = _loaded_store()
    store.set_profile(
        fam,
        dismissed_extractions=["ext_1"],
        retriage_seen=["ext_2"],
        unattributed_ok=["ext_3"],
        resolved_log=[{"obligation_id": "ob_1"}],
        learning_acks=["rule_1"],
    )

    removed = store.reset_ingested(fam)

    for key in ("dismissed_extractions", "retriage_seen", "unattributed_ok",
                "resolved_log", "learning_acks"):
        assert key not in store.profile(fam), key
        assert key in removed["profile_keys_cleared"]


def test_a_stale_dismissal_list_cannot_silently_hide_a_fresh_scan():
    """The concrete harm of keeping those keys, not just the untidiness."""

    store, fam = _loaded_store()
    ext_id = store.ledger(fam)[0].extraction_id
    store.set_profile(fam, dismissed_extractions=[ext_id])

    store.reset_ingested(fam)
    store.ingest(fam, _payload("Return the camp form", "gmail_1"))

    dismissed = set(store.profile(fam).get("dismissed_extractions") or [])
    assert not dismissed


def test_derived_keys_are_an_allowlist_not_a_denylist():
    """An unknown key must survive: for a destructive op, keep is the safe default."""

    store, fam = _loaded_store()
    store.set_profile(fam, some_future_setting={"kept": True})

    store.reset_ingested(fam)

    assert store.profile(fam)["some_future_setting"] == {"kept": True}
    assert "some_future_setting" not in DERIVED_PROFILE_KEYS


def test_reset_is_idempotent():
    store, fam = _loaded_store()
    store.reset_ingested(fam)
    again = store.reset_ingested(fam)

    assert again["ledger_entries"] == 0
    assert store.ledger(fam) == []


def test_endpoint_refuses_without_a_matching_confirmation():
    fam = "fam_reset_api"
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Return the camp form", "event_date": "2026-10-02",
        "action_required": True, "confidence_score": 0.97,
        "artifact_tier": "CONFIRMATION",
    })

    r = client.post(f"/v1/families/{fam}/reset",
                    json={"confirm_family_id": "some_other_family"})

    assert r.status_code == 400
    assert client.get(f"/v1/families/{fam}/ledger").json()["entries"], (
        "a refused reset must not have deleted anything"
    )


def test_endpoint_resets_when_confirmed():
    fam = "fam_reset_api_2"
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Return the camp form", "event_date": "2026-10-02",
        "action_required": True, "confidence_score": 0.97,
        "artifact_tier": "CONFIRMATION",
    })

    r = client.post(f"/v1/families/{fam}/reset", json={"confirm_family_id": fam})

    assert r.status_code == 200
    assert r.json()["reset"] is True
    assert client.get(f"/v1/families/{fam}/ledger").json()["entries"] == []
