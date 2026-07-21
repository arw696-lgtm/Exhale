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


# --- Google Calendar sync endpoint ------------------------------------------------
def test_calendar_sync_404_without_a_coverage_model():
    r = client.post("/v1/families/family_no_cov_model/sync/calendar",
                    json={"caregiver_name": "Andy"})
    assert r.status_code == 404


def test_calendar_sync_503_when_credentials_absent(monkeypatch):
    for var in ("EXHALE_GCAL_ACCESS_TOKEN", "EXHALE_GCAL_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    fam = "family_cal_sync"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.post(f"/v1/families/{fam}/sync/calendar",
                    json={"caregiver_name": "Andy"})
    assert r.status_code == 503
    assert "Google Calendar is not configured" in r.json()["detail"]


# --- ICS (iCloud/Outlook) sync endpoint -------------------------------------------
def test_ics_sync_404_without_a_coverage_model():
    r = client.post("/v1/families/family_no_ics_model/sync/ics",
                    json={"url": "https://x/cal.ics", "attendees": ["Ali", "Andy"]})
    assert r.status_code == 404


def test_ics_sync_validates_attendees():
    fam = "family_ics_validate"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.post(f"/v1/families/{fam}/sync/ics",
                    json={"url": "https://x/cal.ics", "attendees": []})
    assert r.status_code == 400


# --- photo / screenshot extraction ------------------------------------------------
def test_photo_extraction_503_without_credentials(monkeypatch):
    monkeypatch.setattr("exhale.api._vision_extractor", lambda: None)
    r = client.post("/v1/families/fam_photo_none/extractions/photo",
                    json={"image_base64": "abc", "media_type": "image/png"})
    assert r.status_code == 503


def test_photo_extraction_ingests_items_and_appears_in_briefing(monkeypatch):
    from datetime import date
    from exhale.schemas import ArtifactTier, ExtractionPayload

    class _FakeVision:
        def extract(self, *a, **k):
            return [ExtractionPayload(
                extracted_event="Picture Day (from flyer)",
                event_date=date(2026, 9, 4), action_required=True,
                confidence_score=0.95, artifact_tier=ArtifactTier.CONFIRMATION,
                source_document_name="flyer.png", source_reference="photo_x")]

    monkeypatch.setattr("exhale.api._vision_extractor", lambda: _FakeVision())
    fam = "fam_photo_ok"
    r = client.post(f"/v1/families/{fam}/extractions/photo",
                    json={"image_base64": "abc", "media_type": "image/png",
                          "source_name": "flyer.png"})
    assert r.status_code == 200
    body = r.json()
    assert body["extracted"] == 1
    assert body["items"][0]["status"] == "COMMITTED"

    briefing = client.get(f"/v1/families/{fam}/briefing").json()
    titles = [i["title"] for sec in ("critical_threats", "dependency_watch", "advisories")
              for i in briefing[sec]]
    assert "Picture Day (from flyer)" in titles


# --- school-calendar photo → coverage model ---------------------------------------
def test_school_photo_populates_no_school_days_and_care_gaps(monkeypatch):
    from datetime import date
    from exhale.extraction_vision import _SchoolCalendarExtraction, _SchoolClosure

    class _FakeVision:
        def extract_school_calendar(self, *a, **k):
            return _SchoolCalendarExtraction(
                school_name="ISLA", first_day=date(2026, 9, 1), last_day=date(2027, 6, 3),
                no_school_days=[_SchoolClosure(day=date(2026, 10, 15), reason="MEA break")])

    monkeypatch.setattr("exhale.api._vision_extractor", lambda: _FakeVision())
    fam = "fam_school_photo"
    # Need a coverage model first (Andy tied up on the MEA day so a gap appears).
    payload = _coverage_model_payload()
    payload["caregivers"][1]["events"].append({
        "title": "Client review", "start": "2026-10-15T09:00:00",
        "end": "2026-10-15T12:00:00", "attendees": ["Andy"]})
    payload["school"] = None  # start with no school calendar
    client.put(f"/v1/families/{fam}/coverage-model", json=payload)

    r = client.post(f"/v1/families/{fam}/coverage-model/school/photo",
                    json={"image_base64": "abc", "media_type": "image/png", "grade": "1"})
    assert r.status_code == 200
    assert r.json()["school"] == "ISLA"
    assert r.json()["no_school_days"] == 1

    watch = client.get(f"/v1/families/{fam}/care-gaps",
                       params={"from": "2026-10-01", "to": "2026-10-31"}).json()
    reasons = " ".join(g["reason"] for g in watch["gaps"])
    assert "MEA break" in reasons  # the uploaded calendar now drives a care gap


def test_school_photo_404_without_coverage_model(monkeypatch):
    monkeypatch.setattr("exhale.api._vision_extractor", lambda: object())
    r = client.post("/v1/families/fam_no_cov/coverage-model/school/photo",
                    json={"image_base64": "abc"})
    assert r.status_code == 404


def test_school_photo_503_without_credentials(monkeypatch):
    monkeypatch.setattr("exhale.api._vision_extractor", lambda: None)
    fam = "fam_school_503"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.post(f"/v1/families/{fam}/coverage-model/school/photo",
                    json={"image_base64": "abc"})
    assert r.status_code == 503


# --- work-windows endpoint --------------------------------------------------------
def test_work_windows_endpoint_suggests_blocks():
    fam = "family_work_windows"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.get(f"/v1/families/{fam}/work-windows",
                   params={"caregiver": "Andy", "from": "2026-09-14", "to": "2026-09-18",
                           "count": 3, "min_hours": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["view"] == "work_windows"
    assert body["caregiver"] == "Andy"
    assert body["summary"]["suggested"] >= 1
    assert all(w["duration_hours"] >= 2 for w in body["windows"])


def test_work_windows_404_without_model():
    r = client.get("/v1/families/family_no_ww/work-windows", params={"caregiver": "Andy"})
    assert r.status_code == 404


def test_work_windows_400_for_unknown_caregiver():
    fam = "family_ww_badcg"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.get(f"/v1/families/{fam}/work-windows", params={"caregiver": "Nobody"})
    assert r.status_code == 400


# --- Google OAuth "Connect Google" flow -------------------------------------------
def _google_env(monkeypatch):
    monkeypatch.setenv("EXHALE_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("EXHALE_GOOGLE_CLIENT_SECRET", "sec")
    monkeypatch.setenv("EXHALE_GOOGLE_REDIRECT_URI", "https://app/x/oauth/google/callback")


def test_connect_google_503_without_developer_config(monkeypatch):
    for v in ("EXHALE_GOOGLE_CLIENT_ID", "EXHALE_GOOGLE_CLIENT_SECRET",
              "EXHALE_GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(v, raising=False)
    r = client.get("/v1/families/fam_oauth_none/connect/google")
    assert r.status_code == 503


def test_connect_returns_consent_url(monkeypatch):
    _google_env(monkeypatch)
    r = client.get("/v1/families/fam_oauth_1/connect/google")
    assert r.status_code == 200
    assert r.json()["authorization_url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?")


def test_callback_stores_tokens_and_connections_reflects_it(monkeypatch):
    _google_env(monkeypatch)
    fam = "fam_oauth_2"
    # Get a valid signed state from the connect step.
    url = client.get(f"/v1/families/{fam}/connect/google").json()["authorization_url"]
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]

    # Stub the token exchange (no real Google).
    monkeypatch.setattr("exhale.oauth.exchange_code", lambda cfg, code, **k: {
        "access_token": "at-1", "refresh_token": "rt-1",
        "scope": "https://www.googleapis.com/auth/calendar.readonly"})
    r = client.get("/v1/oauth/google/callback", params={"code": "abc", "state": state})
    assert r.status_code == 200
    assert r.json() == {"status": "connected", "provider": "google", "family_id": fam}

    conns = client.get(f"/v1/families/{fam}/connections").json()
    assert conns["google"]["connected"] is True
    assert "calendar.readonly" in conns["google"]["scopes"][0]


def test_callback_rejects_forged_state(monkeypatch):
    _google_env(monkeypatch)
    r = client.get("/v1/oauth/google/callback",
                   params={"code": "abc", "state": "fam_x:9999999999:deadbeef"})
    assert r.status_code == 400


def test_connected_family_tokens_drive_the_connector(monkeypatch):
    _google_env(monkeypatch)
    fam = "fam_oauth_3"
    from exhale.api import _gcal_connector_for_family
    # Not connected → no env fallback → None.
    for v in ("EXHALE_GCAL_ACCESS_TOKEN", "EXHALE_GCAL_REFRESH_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    assert _gcal_connector_for_family(fam, "Andy", "primary") is None

    # Connect, then the connector is built from the family's stored token.
    url = client.get(f"/v1/families/{fam}/connect/google").json()["authorization_url"]
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    monkeypatch.setattr("exhale.oauth.exchange_code", lambda cfg, code, **k: {
        "access_token": "at-1", "refresh_token": "rt-1", "scope": ""})
    client.get("/v1/oauth/google/callback", params={"code": "abc", "state": state})

    conn = _gcal_connector_for_family(fam, "Andy", "primary")
    assert conn is not None
    assert conn._refresh_token == "rt-1"


# --- Connect Outlook (Microsoft) + .ics upload ------------------------------------
def _msft_env(monkeypatch):
    monkeypatch.setenv("EXHALE_MSFT_CLIENT_ID", "mcid")
    monkeypatch.setenv("EXHALE_MSFT_CLIENT_SECRET", "msec")
    monkeypatch.setenv("EXHALE_MSFT_REDIRECT_URI", "https://app/x/oauth/microsoft/callback")


def test_connect_microsoft_503_without_config(monkeypatch):
    for v in ("EXHALE_MSFT_CLIENT_ID", "EXHALE_MSFT_CLIENT_SECRET", "EXHALE_MSFT_REDIRECT_URI"):
        monkeypatch.delenv(v, raising=False)
    r = client.get("/v1/families/fam_ms_none/connect/microsoft")
    assert r.status_code == 503


def test_connect_microsoft_returns_ms_consent_url(monkeypatch):
    _msft_env(monkeypatch)
    r = client.get("/v1/families/fam_ms_1/connect/microsoft")
    assert r.status_code == 200
    assert "login.microsoftonline.com" in r.json()["authorization_url"]


def test_microsoft_callback_stores_tokens_and_connections_shows_both(monkeypatch):
    _msft_env(monkeypatch)
    fam = "fam_ms_2"
    url = client.get(f"/v1/families/{fam}/connect/microsoft").json()["authorization_url"]
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    monkeypatch.setattr("exhale.oauth.exchange_code", lambda cfg, code, **k: {
        "access_token": "at", "refresh_token": "rt", "scope": "Calendars.Read"})
    r = client.get("/v1/oauth/microsoft/callback", params={"code": "abc", "state": state})
    assert r.status_code == 200
    assert r.json()["provider"] == "microsoft"

    conns = client.get(f"/v1/families/{fam}/connections").json()
    assert conns["microsoft"]["connected"] is True
    assert conns["google"]["connected"] is False  # both providers reported


def test_sync_outlook_503_without_connection():
    fam = "fam_outlook_noconn"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.post(f"/v1/families/{fam}/sync/outlook", json={"caregiver_name": "Ali"})
    assert r.status_code == 503


def test_ics_upload_imports_events_into_model():
    fam = "fam_ics_upload"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    ics = (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u1\nSUMMARY:Recital\n"
        "DTSTART;TZID=America/Chicago:20260919T180000\n"
        "DTEND;TZID=America/Chicago:20260919T193000\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    r = client.post(f"/v1/families/{fam}/sync/ics/upload",
                    json={"content": ics, "attendees": ["Ali", "Andy"]})
    assert r.status_code == 200
    assert r.json()["synced_busy_events"] == 1


def test_ics_upload_validates_attendees():
    fam = "fam_ics_upload_bad"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.post(f"/v1/families/{fam}/sync/ics/upload",
                    json={"content": "BEGIN:VCALENDAR\nEND:VCALENDAR\n", "attendees": []})
    assert r.status_code == 400
