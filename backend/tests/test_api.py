"""Tests for the FastAPI service layer."""

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.seed import DEMO_FAMILY_ID

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["product"] == "Exhale"


def test_demo_briefing_has_seeded_gaps():
    r = client.get(f"/v1/families/{DEMO_FAMILY_ID}/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["view"] == "weekly_coo_briefing"
    # Seeded household has two imminent high-impact obligations.
    assert body["summary"]["critical_count"] >= 1
    assert body["summary"]["total_gaps"] >= 2


def test_ingest_high_confidence_then_appears_in_briefing():
    fam = "family_test_api"
    payload = {
        "extracted_event": "Book Fair Volunteer Signup",
        "target_person_name": "Olivia",
        "event_date": "2026-09-10",
        "deadline_date": "2026-09-01",
        "action_required": True,
        "confidence_score": 0.98,
    }
    r = client.post(f"/v1/families/{fam}/extractions", json=payload)
    assert r.status_code == 200
    assert r.json()["routing"]["status"] == "COMMITTED"

    r2 = client.get(f"/v1/families/{fam}/briefing")
    assert r2.status_code == 200
    titles = [
        item["title"]
        for section in ("critical_threats", "dependency_watch", "advisories")
        for item in r2.json()[section]
    ]
    assert "Book Fair Volunteer Signup" in titles


def test_ingest_low_confidence_rejected_and_no_briefing():
    fam = "family_reject_api"
    payload = {
        "extracted_event": "Blurry flyer",
        "event_date": "2026-09-10",
        "action_required": True,
        "confidence_score": 0.3,
    }
    r = client.post(f"/v1/families/{fam}/extractions", json=payload)
    assert r.json()["routing"]["status"] == "REJECTED"
    # Nothing committed -> no graph -> 404 briefing.
    assert client.get(f"/v1/families/{fam}/briefing").status_code == 404


def test_ledger_endpoint():
    fam = "family_ledger_api"
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Picture Day",
        "event_date": "2026-09-15",
        "action_required": False,
        "confidence_score": 0.95,
    })
    r = client.get(f"/v1/families/{fam}/ledger")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 1


def test_invalid_confidence_rejected_by_validation():
    r = client.post("/v1/families/x/extractions", json={
        "extracted_event": "x",
        "event_date": "2026-09-15",
        "action_required": True,
        "confidence_score": 1.5,
    })
    assert r.status_code == 422
