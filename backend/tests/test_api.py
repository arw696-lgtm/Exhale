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


# --- Care-coverage model + care-gaps (end-to-end) ---------------------------------
def _coverage_model_payload():
    """Stevie + Ali (work pattern) + Andy (with the two real concerts) + ISLA."""
    concerts = [
        {"title": "Gary Clark Jr.", "start": "2026-09-19T19:30:00",
         "end": "2026-09-19T21:00:00", "attendees": ["Ali", "Andy"],
         "source_reference": "shared_cal_gcj"},
        {"title": "Monrovia Concert", "start": "2026-10-02T19:00:00",
         "end": "2026-10-02T20:00:00", "attendees": ["Ali", "Andy"]},
    ]
    return {
        "recipient": {"name": "Stevie"},
        "caregivers": [
            {"name": "Ali", "role": "PARENT",
             "work_pattern": {"weekdays": [0, 1, 2, 3, 4],
                              "start": "07:30:00", "end": "16:30:00",
                              "basis": "INFERRED"},
             "events": concerts},
            {"name": "Andy", "role": "PARENT", "events": concerts},
        ],
        "school": {"name": "ISLA", "first_day": "2026-09-01", "last_day": "2027-06-03",
                   "no_school_days": {"2026-10-15": "MEA break"}},
    }


def test_coverage_model_saves_then_care_gaps_surfaces_concert_sitter_gaps():
    fam = "family_coverage_model"
    r = client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    assert r.status_code == 200
    assert r.json()["recipient"] == "Stevie"
    assert r.json()["school"] == "ISLA"

    r2 = client.get(f"/v1/families/{fam}/care-gaps",
                    params={"from": "2026-09-01", "to": "2026-10-31"})
    assert r2.status_code == 200
    watch = r2.json()
    assert watch["view"] == "care_watch"
    reasons = " ".join(g["reason"] for g in watch["gaps"])
    assert "Gary Clark Jr." in reasons
    assert "Monrovia Concert" in reasons
    # The concert gaps are built from observed calendar events.
    concert_gaps = [g for g in watch["gaps"] if "Concert" in g["reason"] or "Clark" in g["reason"]]
    assert concert_gaps and all(not g["depends_on_inference"] for g in concert_gaps)


def test_care_gaps_404_without_a_model():
    r = client.get("/v1/families/family_no_model/care-gaps")
    assert r.status_code == 404


def test_briefing_includes_care_watch_once_model_is_set():
    fam = "family_briefing_care"
    # Before configuring: care_watch is null, not an error.
    assert client.get(f"/v1/families/{fam}/briefing").json()["care_watch"] is None

    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    briefing = client.get(f"/v1/families/{fam}/briefing").json()
    assert briefing["care_watch"] is not None
    assert briefing["care_watch"]["recipient"] == "Stevie"
