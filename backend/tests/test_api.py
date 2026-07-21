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
    # Nothing committed -> empty graph -> a valid all-clear briefing.
    r2 = client.get(f"/v1/families/{fam}/briefing")
    assert r2.status_code == 200
    assert r2.json()["summary"]["total_gaps"] == 0


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


def test_demo_drafts_are_generated():
    r = client.get(f"/v1/families/{DEMO_FAMILY_ID}/drafts")
    assert r.status_code == 200
    drafts = r.json()["drafts"]
    assert len(drafts) >= 2
    critical = [d for d in drafts if d["threat_level"] == "CRITICAL"]
    assert critical, "demo household should surface at least one critical draft"
    assert critical[0]["requires_approval"] is True
    assert "CRITICAL THREAT" in critical[0]["body"]
    # Personalized with the demo family's parent name.
    assert "Hey Andrew" in critical[0]["body"]


def test_approve_action_resolves_gap_and_updates_briefing():
    fam = "family_approve_api"
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Field Trip Permission Slip",
        "target_person_name": "Olivia",
        "event_date": "2026-08-25",
        "deadline_date": "2026-08-01",
        "action_required": True,
        "confidence_score": 0.97,
    })
    drafts = client.get(f"/v1/families/{fam}/drafts").json()["drafts"]
    assert len(drafts) == 1
    obligation_id = drafts[0]["obligation_node_id"]

    r = client.post(f"/v1/families/{fam}/actions/approve",
                    json={"obligation_node_id": obligation_id})
    assert r.status_code == 200
    assert r.json()["stage"] == "EXECUTED"

    # After execution the gap is gone.
    assert client.get(f"/v1/families/{fam}/drafts").json()["drafts"] == []


def test_approve_unknown_obligation_is_404():
    r = client.post(f"/v1/families/{DEMO_FAMILY_ID}/actions/approve",
                    json={"obligation_node_id": "ob_does_not_exist"})
    assert r.status_code == 404


def test_scan_endpoint_ingests_raw_and_returns_snapshot():
    fam = "family_scan_api"
    body = {
        "known_children": ["Olivia", "Leo"],
        "messages": [
            {
                "source_id": "raw1",
                "channel": "gmail",
                "subject": "Field Trip Permission Slip",
                "body": "Please sign and return the slip for Olivia. Trip on "
                        "August 25, 2026. Forms due by July 20, 2026.",
                "sender_domain": "powerschool.com",
            },
            {
                "source_id": "raw2",
                "channel": "gmail",
                "subject": "Just hi",
                "body": "Nothing scheduled here.",
            },
        ],
    }
    r = client.post(f"/v1/families/{fam}/scan", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["scanned"] == 2
    assert data["extracted"] == 1  # second message has no date
    assert data["snapshot"]["obligation_count"] == 1
    titles = [o["title"] for o in data["snapshot"]["forgotten_obligations"]]
    assert "Field Trip Permission Slip" in titles

    # The scanned obligation now shows up as a real briefing gap + draft.
    assert client.get(f"/v1/families/{fam}/briefing").status_code == 200
    assert len(client.get(f"/v1/families/{fam}/drafts").json()["drafts"]) == 1


def test_invalid_confidence_rejected_by_validation():
    r = client.post("/v1/families/x/extractions", json={
        "extracted_event": "x",
        "event_date": "2026-09-15",
        "action_required": True,
        "confidence_score": 1.5,
    })
    assert r.status_code == 422


def test_correct_extraction_endpoint_supersedes_and_commits():
    fam = "family_correct_api"
    payload = {
        "extracted_event": "Junior Robotics Camp",
        "event_date": "2026-07-20",
        "action_required": True,
        "confidence_score": 0.95,
        "artifact_tier": "REMINDER",  # held pending: reminders never auto-commit
    }
    r = client.post(f"/v1/families/{fam}/extractions", json=payload)
    assert r.json()["routing"]["status"] == "PENDING_VERIFICATION"
    ledger = client.get(f"/v1/families/{fam}/ledger").json()["entries"]
    original_id = ledger[0]["extraction_id"]

    r2 = client.post(
        f"/v1/families/{fam}/extractions/{original_id}/correct",
        json={"event_start_time": "13:00:00", "event_end_time": "16:00:00"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["record_status"] == "COMMITTED"
    assert body["event_date_origin"] == "USER_CONFIRMED"
    assert body["event_start_time"] == "13:00:00"
    assert body["corrects"] == original_id

    entries = client.get(f"/v1/families/{fam}/ledger").json()["entries"]
    by_id = {e["extraction_id"]: e for e in entries}
    assert by_id[original_id]["superseded_by"] == body["extraction_id"]


def test_correct_unknown_extraction_is_404():
    r = client.post(
        "/v1/families/family_correct_api/extractions/ext_missing/correct",
        json={"event_date": "2026-08-01"},
    )
    assert r.status_code == 404


def test_coverage_declaration_flows_into_briefing():
    fam = "family_coverage_api"
    r = client.put(
        f"/v1/families/{fam}/coverage",
        json={
            "connected_sources": ["gmail:arw696@gmail.com"],
            "known_missing_sources": [
                {"source": "parentsquare", "owns": ["school communications"]},
            ],
        },
    )
    assert r.status_code == 200
    assert "parentsquare" in r.json()["statement"]

    briefing = client.get(f"/v1/families/{fam}/briefing").json()
    assert briefing["coverage"]["connected_sources"] == ["gmail:arw696@gmail.com"]
    assert "incomplete by construction" in briefing["coverage"]["statement"]


def test_briefing_without_declaration_says_coverage_undeclared():
    briefing = client.get("/v1/families/family_no_coverage/briefing").json()
    assert "undeclared" in briefing["coverage"]["statement"].lower()
