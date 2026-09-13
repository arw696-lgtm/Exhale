"""An empty system must never report a calm week.

Andy cleared his household and the app said "A quiet week. Nothing needs you."
It had read nothing at all. Every count a briefing carries is zero in both
cases — the week is genuinely clear, or nobody has looked — and nothing in the
payload told them apart.

That is the failure the tenor rails exist to prevent, arrived at from a new
direction. The old "brand new household" test was `no care_watch and no
learned rules and no needs`, which works for a household that has never been
set up and fails for one that has *just started over*: its coverage model and
its people survive the reset, so care_watch is present, brandNew is false, and
the quiet-week copy runs against mail nobody has opened.

So the briefing now states how many artifacts it has ever read, which is the
only signal that separates silence from calm.
"""

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.briefing import build_weekly_briefing
from exhale.graph import KnowledgeGraph

client = TestClient(app)


def test_briefing_reports_how_much_it_has_read():
    briefing = build_weekly_briefing(KnowledgeGraph(), artifacts_read=0)

    assert briefing["summary"]["artifacts_read"] == 0


def test_unknown_when_the_caller_has_no_ledger_to_count():
    """None reads as "unknown", which must not be confused with zero."""

    briefing = build_weekly_briefing(KnowledgeGraph())

    assert briefing["summary"]["artifacts_read"] is None


def test_the_api_counts_the_real_ledger():
    fam = "fam_unread_api"
    assert client.get(f"/v1/families/{fam}/briefing").json()["summary"][
        "artifacts_read"
    ] == 0

    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Return the camp form",
        "event_date": "2026-10-02",
        "action_required": True,
        "confidence_score": 0.97,
        "artifact_tier": "CONFIRMATION",
    })

    assert client.get(f"/v1/families/{fam}/briefing").json()["summary"][
        "artifacts_read"
    ] == 1


def test_a_reset_household_reports_nothing_read():
    """The exact sequence Andy hit: set up, scanned, cleared."""

    fam = "fam_unread_reset"
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Return the camp form",
        "event_date": "2026-10-02",
        "action_required": True,
        "confidence_score": 0.97,
        "artifact_tier": "CONFIRMATION",
    })
    client.post(f"/v1/families/{fam}/reset", json={"confirm_family_id": fam})

    summary = client.get(f"/v1/families/{fam}/briefing").json()["summary"]

    assert summary["artifacts_read"] == 0
    assert summary["critical_count"] == 0, (
        "both are zero — which is the whole reason artifacts_read has to exist"
    )
