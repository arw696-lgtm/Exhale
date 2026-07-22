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
    assert r.json()["children"] == ["Stevie"]
    assert r.json()["schools"] == {"Stevie": "ISLA"}

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
    # Anonymous dev-mode connect files under the legacy/primary account slot.
    assert r.json() == {"status": "connected", "provider": "google",
                        "family_id": fam, "account": "primary"}

    conns = client.get(f"/v1/families/{fam}/connections").json()
    assert conns["google"]["connected"] is True
    assert conns["google"]["accounts"] == 1
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


# --- Review queue (the human side of "asks when unsure") --------------------------
def _pending_payload(event="Zoo Camp Reminder"):
    return {
        "extracted_event": event, "event_date": "2026-08-10",
        "action_required": True, "confidence_score": 0.95,
        "artifact_tier": "REMINDER",  # reminder tier → held PENDING_VERIFICATION
    }


def test_pending_item_appears_in_review_queue():
    fam = "fam_review_1"
    client.post(f"/v1/families/{fam}/extractions", json=_pending_payload())
    review = client.get(f"/v1/families/{fam}/review").json()
    assert review["count"] == 1
    assert review["pending"][0]["extracted_event"] == "Zoo Camp Reminder"
    assert review["pending"][0]["record_status"] == "PENDING_VERIFICATION"


def test_confirm_commits_and_clears_from_queue():
    fam = "fam_review_2"
    client.post(f"/v1/families/{fam}/extractions", json=_pending_payload())
    ext_id = client.get(f"/v1/families/{fam}/review").json()["pending"][0]["extraction_id"]

    r = client.post(f"/v1/families/{fam}/extractions/{ext_id}/confirm")
    assert r.status_code == 200
    assert r.json()["record_status"] == "COMMITTED"
    assert r.json()["event_date_origin"] == "USER_CONFIRMED"
    assert client.get(f"/v1/families/{fam}/review").json()["count"] == 0

    # Confirmed item now shows in the briefing as a real obligation.
    briefing = client.get(f"/v1/families/{fam}/briefing").json()
    titles = [i["title"] for sec in ("critical_threats", "dependency_watch", "advisories")
              for i in briefing[sec]]
    assert "Zoo Camp Reminder" in titles


def test_dismiss_clears_from_queue_but_keeps_ledger():
    fam = "fam_review_3"
    client.post(f"/v1/families/{fam}/extractions", json=_pending_payload())
    ext_id = client.get(f"/v1/families/{fam}/review").json()["pending"][0]["extraction_id"]

    r = client.post(f"/v1/families/{fam}/extractions/{ext_id}/dismiss")
    assert r.status_code == 200
    assert client.get(f"/v1/families/{fam}/review").json()["count"] == 0
    # Dismissals are signal, not erasure: the ledger keeps the entry.
    ledger = client.get(f"/v1/families/{fam}/ledger").json()["entries"]
    assert any(e["extraction_id"] == ext_id for e in ledger)


def test_confirm_and_dismiss_unknown_are_404():
    assert client.post("/v1/families/f/extractions/ext_x/confirm").status_code == 404
    assert client.post("/v1/families/f/extractions/ext_x/dismiss").status_code == 404


def test_successful_ics_sync_is_remembered_for_auto_sync(monkeypatch):
    import exhale.api as api_mod

    class _FakeICS:
        def __init__(self, url, *, attendees, tz="America/Chicago"):
            self.attendees = attendees

        def fetch_busy(self):
            return []

    monkeypatch.setattr("exhale.connectors.ics.ICSCalendarConnector", _FakeICS)
    fam = "fam_remember_sync"
    client.put(f"/v1/families/{fam}/coverage-model", json=_coverage_model_payload())
    r = client.post(f"/v1/families/{fam}/sync/ics",
                    json={"url": "https://x/shared.ics", "attendees": ["Ali", "Andy"]})
    assert r.status_code == 200
    configs = api_mod.store.profile(fam).get("sync_configs")
    assert configs["ics"][0]["url"] == "https://x/shared.ics"


# --- Waiting-On ledger + learned rules in the briefing ----------------------------
def test_waiting_flow_add_watch_resolve():
    fam = "fam_waiting_1"
    r = client.post(f"/v1/families/{fam}/waiting",
                    json={"who": "Hennepin County", "about": "arborist follow-up",
                          "since": "2026-07-01", "channel": "email"})
    assert r.status_code == 200
    item_id = r.json()["id"]

    watch = client.get(f"/v1/families/{fam}/waiting").json()
    assert watch["summary"]["open"] == 1
    assert watch["items"][0]["who"] == "Hennepin County"
    assert watch["items"][0]["threat_level"] in ("IMPORTANT", "CRITICAL")  # weeks old

    # The wait rides on the briefing too.
    briefing = client.get(f"/v1/families/{fam}/briefing").json()
    assert briefing["waiting_on"]["summary"]["open"] == 1

    r2 = client.post(f"/v1/families/{fam}/waiting/{item_id}/resolve")
    assert r2.status_code == 200
    assert client.get(f"/v1/families/{fam}/waiting").json()["summary"]["open"] == 0


def test_resolve_unknown_waiting_is_404():
    assert client.post("/v1/families/f/waiting/wait_x/resolve").status_code == 404


def test_briefing_learns_rules_from_the_ledger():
    fam = "fam_memory_1"
    # Three weekly Monday sessions, each with a Wednesday-before deadline.
    for monday, wednesday in (("2026-06-22", "2026-06-17"),
                              ("2026-06-29", "2026-06-24"),
                              ("2026-07-06", "2026-07-01")):
        client.post(f"/v1/families/{fam}/extractions", json={
            "extracted_event": f"ISLA Camp this Week {monday[5:7]}/{monday[8:]}",
            "event_date": monday, "deadline_date": wednesday,
            "action_required": True, "confidence_score": 0.95,
            "artifact_tier": "CONFIRMATION"})

    rules = client.get(f"/v1/families/{fam}/briefing").json()["learned_rules"]
    kinds = {r["kind"] for r in rules}
    assert "WEEKLY_CADENCE" in kinds
    assert "DEADLINE_LEAD" in kinds
    lead = next(r for r in rules if r["kind"] == "DEADLINE_LEAD")
    assert "Wednesday" in lead["detail"]


# --- Controlled autonomy: dials, schedule, and the Exhale feed --------------------
def test_autonomy_defaults_and_update():
    fam = "fam_auto_1"
    r = client.get(f"/v1/families/{fam}/autonomy").json()
    assert r["settings"] == {"calendar_write": "ASK"}
    assert r["trust"]["decisions"] == 0

    r2 = client.put(f"/v1/families/{fam}/autonomy", json={"calendar_write": "AUTO"})
    assert r2.json()["settings"]["calendar_write"] == "AUTO"
    assert client.put(f"/v1/families/{fam}/autonomy",
                      json={"calendar_write": "SOMETIMES"}).status_code == 400


def test_schedule_off_is_refused():
    fam = "fam_auto_off"
    client.put(f"/v1/families/{fam}/autonomy", json={"calendar_write": "OFF"})
    r = client.post(f"/v1/families/{fam}/schedule", json={
        "title": "Gym", "start": "2026-07-23T09:00:00", "end": "2026-07-23T10:00:00"})
    assert r.status_code == 403


def test_schedule_falls_back_to_feed_and_feed_serves_it():
    fam = "fam_auto_feed"
    r = client.post(f"/v1/families/{fam}/schedule", json={
        "title": "Gym", "start": "2026-07-23T09:00:00", "end": "2026-07-23T10:00:00"})
    assert r.status_code == 200
    assert r.json()["provider"] == "feed"  # nothing connected → published feed

    path = client.get(f"/v1/families/{fam}/feed-url").json()["path"]
    feed = client.get(path)
    assert feed.status_code == 200
    assert "text/calendar" in feed.headers["content-type"]
    assert "SUMMARY:Gym" in feed.text
    assert "DTSTART:20260723T090000" in feed.text


def test_feed_rejects_bad_token():
    fam = "fam_auto_feed2"
    client.get(f"/v1/families/{fam}/feed-url")  # mint the real token
    assert client.get(f"/v1/feeds/{fam}.ics", params={"token": "wrong"}).status_code == 403


def test_schedule_writes_to_google_when_connected(monkeypatch):
    _google_env(monkeypatch)
    fam = "fam_auto_google"
    # Connect Google via the OAuth flow (stubbed exchange).
    url = client.get(f"/v1/families/{fam}/connect/google").json()["authorization_url"]
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    monkeypatch.setattr("exhale.oauth.exchange_code", lambda cfg, code, **k: {
        "access_token": "at", "refresh_token": "rt", "scope": ""})
    client.get("/v1/oauth/google/callback", params={"code": "c", "state": state})

    created = {}

    class _FakeGcal:
        def __init__(self, **kw):
            pass

        def create_event(self, title, start, end, **kw):
            created["title"] = title
            return {"id": "evt_google_1"}

    monkeypatch.setattr("exhale.connectors.gcal.GoogleCalendarConnector", _FakeGcal)
    r = client.post(f"/v1/families/{fam}/schedule", json={
        "title": "Gym", "start": "2026-07-23T09:00:00", "end": "2026-07-23T10:00:00"})
    assert r.status_code == 200
    assert r.json()["provider"] == "google"
    assert r.json()["reference"] == "evt_google_1"
    assert created["title"] == "Gym"


def test_schedule_rejects_backwards_window():
    r = client.post("/v1/families/fam_auto_bad/schedule", json={
        "title": "Gym", "start": "2026-07-23T10:00:00", "end": "2026-07-23T09:00:00"})
    assert r.status_code == 400


# --- Bug-hunt regressions (found in the full-code review) -------------------------
def test_schedule_mixed_timezone_input_is_400_not_500():
    # Aware start + naive end used to raise TypeError -> 500.
    r = client.post("/v1/families/fam_bug_tz/schedule", json={
        "title": "Gym", "start": "2026-07-23T10:00:00Z", "end": "2026-07-23T09:00:00"})
    assert r.status_code == 400  # backwards after normalization -> clean 400
    r2 = client.post("/v1/families/fam_bug_tz/schedule", json={
        "title": "Gym", "start": "2026-07-23T09:00:00Z", "end": "2026-07-23T10:00:00"})
    assert r2.status_code == 200


def test_feed_escapes_titles_and_descriptions():
    fam = "fam_bug_feed"
    client.post(f"/v1/families/{fam}/schedule", json={
        "title": "Dentist, then errands; maybe gym",
        "start": "2026-07-23T09:00:00", "end": "2026-07-23T10:00:00",
        "description": "line one\nline two"})
    path = client.get(f"/v1/families/{fam}/feed-url").json()["path"]
    text = client.get(path).text
    assert "SUMMARY:Dentist\\, then errands\; maybe gym" in text
    assert "DESCRIPTION:line one\\nline two" in text
    # No raw continuation garbage: every line is a known ICS property.
    assert not any(line == "line two" for line in text.splitlines())


def test_double_confirm_is_409_and_single_obligation():
    fam = "fam_bug_dupconfirm"
    client.post(f"/v1/families/{fam}/extractions", json=_pending_payload("Dup guard"))
    eid = client.get(f"/v1/families/{fam}/review").json()["pending"][0]["extraction_id"]
    assert client.post(f"/v1/families/{fam}/extractions/{eid}/confirm").status_code == 200
    assert client.post(f"/v1/families/{fam}/extractions/{eid}/confirm").status_code == 409
    ledger = client.get(f"/v1/families/{fam}/ledger").json()["entries"]
    assert sum(1 for e in ledger if e["obligation_node_id"]) == 1


def test_photo_reupload_skips_duplicates(monkeypatch):
    from datetime import date
    from exhale.schemas import ArtifactTier, ExtractionPayload

    class _FakeVision:
        def extract(self, image_base64, media_type, *, source_name, source_reference, ctx):
            return [ExtractionPayload(
                extracted_event="Picture Day", event_date=date(2026, 9, 4),
                action_required=True, confidence_score=0.95,
                artifact_tier=ArtifactTier.CONFIRMATION,
                source_document_name=source_name, source_reference=source_reference)]

    monkeypatch.setattr("exhale.api._vision_extractor", lambda: _FakeVision())
    fam = "fam_bug_photodup"
    body = {"image_base64": "same-bytes", "media_type": "image/png"}
    r1 = client.post(f"/v1/families/{fam}/extractions/photo", json=body)
    r2 = client.post(f"/v1/families/{fam}/extractions/photo", json=body)
    assert r1.json()["extracted"] == 1
    assert r2.json()["extracted"] == 0 and r2.json()["duplicates_skipped"] == 1
    ledger = client.get(f"/v1/families/{fam}/ledger").json()["entries"]
    assert len(ledger) == 1


def test_briefing_items_carry_why_trace():
    fam = "fam_why_trace"
    client.post(f"/v1/families/{fam}/extractions", json={
        "extracted_event": "Permission slip due",
        "target_person_name": "Stevie",
        "event_date": "2026-09-10",
        "deadline_date": "2026-09-01",
        "action_required": True,
        "confidence_score": 0.97,
        "artifact_tier": "CONFIRMATION",
        "source_document_name": "Subject: Field trip forms",
        "source_reference": "gmail_msg_777",
    })
    items = [item for section in ("critical_threats", "dependency_watch", "advisories")
             for item in client.get(f"/v1/families/{fam}/briefing").json()[section]]
    (item,) = items
    assert item["why"]["source_document_name"] == "Subject: Field trip forms"
    assert item["why"]["artifact_tier"] == "CONFIRMATION"
    assert item["why"]["event_date_origin"] == "OBSERVED"


def test_notification_prefs_roundtrip():
    fam = "fam_notify_prefs"
    r = client.get(f"/v1/families/{fam}/notifications")
    assert r.json() == {"family_id": fam, "email": None,
                        "smtp_configured": False, "alerts_sent": 0,
                        "members_opted_in": 0}

    r = client.put(f"/v1/families/{fam}/notifications", json={"email": "andy@test"})
    assert r.json()["email"] == "andy@test"
    assert r.json()["members_opted_in"] == 1
    # Opt back out with null.
    r = client.put(f"/v1/families/{fam}/notifications", json={"email": None})
    assert r.json()["email"] is None
    assert r.json()["members_opted_in"] == 0
    # Garbage is refused, not stored.
    assert client.put(f"/v1/families/{fam}/notifications",
                      json={"email": "not-an-address"}).status_code == 400


def test_notification_prefs_are_per_member():
    """Each member flips their own alerts — never their spouse's."""

    r = client.post("/v1/auth/signup", json={
        "email": "np-a@example.com", "password": "password123",
        "display_name": "Andrew"})
    a = r.json()
    fam = a["user"]["family_id"]
    ha = {"Authorization": f"Bearer {a['token']}"}
    b = client.post("/v1/auth/signup", json={
        "email": "np-b@example.com", "password": "password123",
        "display_name": "Alicia", "invite_code": a["invite_code"]}).json()
    hb = {"Authorization": f"Bearer {b['token']}"}

    client.put(f"/v1/families/{fam}/notifications", headers=ha,
               json={"email": "andy@test"})
    # B sees their own (unset) slot, not A's address.
    assert client.get(f"/v1/families/{fam}/notifications", headers=hb).json()["email"] is None
    client.put(f"/v1/families/{fam}/notifications", headers=hb,
               json={"email": "ali@test"})
    got = client.get(f"/v1/families/{fam}/notifications", headers=hb).json()
    assert got["email"] == "ali@test"
    assert got["members_opted_in"] == 2
    # B opting out leaves A opted in.
    client.put(f"/v1/families/{fam}/notifications", headers=hb, json={"email": None})
    assert client.get(f"/v1/families/{fam}/notifications",
                      headers=ha).json()["members_opted_in"] == 1


def test_draft_greeting_addresses_the_viewer():
    """"Hey Alicia" when Alicia looks — not the founder's name for everyone."""

    from datetime import date, timedelta

    r = client.post("/v1/auth/signup", json={
        "email": "greet-a@example.com", "password": "password123",
        "display_name": "Andrew Ward"})
    a = r.json()
    fam = a["user"]["family_id"]
    ha = {"Authorization": f"Bearer {a['token']}"}
    b = client.post("/v1/auth/signup", json={
        "email": "greet-b@example.com", "password": "password123",
        "display_name": "Alicia Ward", "invite_code": a["invite_code"]}).json()
    hb = {"Authorization": f"Bearer {b['token']}"}

    # Deadline tomorrow → 🔴 critical draft, the template that greets by name.
    tomorrow = date.today() + timedelta(days=1)
    client.post(f"/v1/families/{fam}/extractions", headers=ha, json={
        "extracted_event": "Permission slip", "target_person_name": "Stevie",
        "event_date": (tomorrow + timedelta(days=10)).isoformat(),
        "deadline_date": tomorrow.isoformat(),
        "action_required": True, "confidence_score": 0.97})

    drafts_a = client.get(f"/v1/families/{fam}/drafts", headers=ha).text
    drafts_b = client.get(f"/v1/families/{fam}/drafts", headers=hb).text
    assert "Andrew" in drafts_a and "Alicia" not in drafts_a
    assert "Alicia" in drafts_b and "Andrew" not in drafts_b


def test_notification_test_send_requires_smtp_and_address(monkeypatch):
    monkeypatch.delenv("EXHALE_SMTP_HOST", raising=False)
    fam = "fam_notify_test"
    assert client.post(f"/v1/families/{fam}/notifications/test").status_code == 503

    monkeypatch.setenv("EXHALE_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("EXHALE_SMTP_FROM", "alerts@exhale.test")
    # SMTP configured but no address on file yet -> 400 with guidance.
    assert client.post(f"/v1/families/{fam}/notifications/test").status_code == 400


def test_notification_run_reports_pending_without_smtp(monkeypatch):
    monkeypatch.delenv("EXHALE_SMTP_HOST", raising=False)
    from exhale.seed import DEMO_FAMILY_ID
    r = client.post(f"/v1/families/{DEMO_FAMILY_ID}/notifications/run")
    body = r.json()
    assert body["smtp_configured"] is False
    assert any(line.startswith("🔴") for line in body["pending_alerts"])
