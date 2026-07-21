"""Scoped-caregiver (helper) API: invites, default-deny enforcement, scoped view.

The trust-critical boundary from FAMILY_STRUCTURES §3.2 — a helper must see only
their care days and explicitly shared items, and nothing else.
"""

from fastapi.testclient import TestClient

from exhale.api import app

client = TestClient(app)


def _member():
    """A fresh household with a full member and a coverage model that yields a
    care gap every day (single caregiver working 08–18, child supervised 08–18)."""

    r = client.post("/v1/auth/signup", json={
        "email": f"parent-{_member.n}@example.com", "password": "password123",
        "display_name": "Parent"})
    _member.n += 1
    session = r.json()
    fam = session["user"]["family_id"]
    headers = {"Authorization": f"Bearer {session['token']}"}
    client.put(f"/v1/families/{fam}/coverage-model", headers=headers, json={
        "recipient": {"name": "Stevie", "supervised_start": "08:00:00",
                      "supervised_end": "18:00:00"},
        "caregivers": [{"name": "Parent", "role": "PARENT",
                        "work_pattern": {"weekdays": [0, 1, 2, 3, 4, 5, 6],
                                         "start": "08:00:00", "end": "18:00:00",
                                         "basis": "OBSERVED"}}],
    })
    return session, fam, headers


_member.n = 0


def _helper(fam, headers, weekdays):
    code = client.post(f"/v1/families/{fam}/helper-invites", headers=headers,
                       json={"weekdays": weekdays}).json()["code"]
    r = client.post("/v1/auth/signup", json={
        "email": f"helper-{_helper.n}@example.com", "password": "password123",
        "display_name": "Grandma", "invite_code": code})
    _helper.n += 1
    session = r.json()
    return session, {"Authorization": f"Bearer {session['token']}"}


_helper.n = 0


# --- invite + role ------------------------------------------------------------
def test_helper_signup_is_scoped_role_without_family_code():
    session, fam, headers = _member()
    assert session["invite_code"]  # member gets the family join code
    hsession, _ = _helper(fam, headers, [1, 3])
    assert hsession["user"]["role"] == "HELPER"
    assert hsession["user"]["family_id"] == fam
    # The family join code must NEVER be handed to a helper.
    assert hsession["invite_code"] is None


def test_only_members_can_invite_helpers():
    _s, fam, headers = _member()
    _hs, hheaders = _helper(fam, headers, [1, 3])
    r = client.post(f"/v1/families/{fam}/helper-invites", headers=hheaders,
                    json={"weekdays": [0]})
    assert r.status_code == 403


# --- default-deny enforcement -------------------------------------------------
def test_helper_is_denied_every_household_view():
    _s, fam, headers = _member()
    _hs, hheaders = _helper(fam, headers, [1, 3])
    for path in ("briefing", "ledger", "connections", "care-gaps", "autonomy",
                 "waiting", "notifications", "review", "feed-url"):
        r = client.get(f"/v1/families/{fam}/{path}", headers=hheaders)
        assert r.status_code == 403, f"helper reached /{path}: {r.status_code}"
    # Write paths too.
    assert client.post(f"/v1/families/{fam}/schedule", headers=hheaders, json={
        "title": "x", "start": "2026-09-01T09:00:00", "end": "2026-09-01T10:00:00",
    }).status_code == 403


def test_helper_cannot_reach_another_familys_data():
    _s1, fam1, headers1 = _member()
    _hs, hheaders = _helper(fam1, headers1, [1, 3])
    _s2, fam2, _headers2 = _member()
    # Wrong family entirely → 403 (membership check fires first).
    assert client.get(f"/v1/families/{fam2}/helper-view", headers=hheaders).status_code == 403


# --- the scoped view ----------------------------------------------------------
def test_helper_view_is_filtered_to_covered_days():
    _s, fam, headers = _member()
    _hs, hheaders = _helper(fam, headers, [1, 3])  # Tue + Thu
    view = client.get(f"/v1/families/{fam}/helper-view", headers=hheaders).json()
    assert view["view"] == "helper_home"
    assert view["scope"]["covered_weekdays"] == ["Tuesday", "Thursday"]
    for gap in view["care_watch"]["gaps"]:
        wd = __import__("datetime").date.fromisoformat(gap["date"]).weekday()
        assert wd in (1, 3), f"helper saw a gap on weekday {wd}"


def test_member_shares_obligation_then_helper_sees_summary_only():
    _s, fam, headers = _member()
    _hs, hheaders = _helper(fam, headers, [1, 3])

    # Member commits an obligation with private provenance.
    client.post(f"/v1/families/{fam}/extractions", headers=headers, json={
        "extracted_event": "Permission slip due", "target_person_name": "Stevie",
        "event_date": "2026-09-10", "deadline_date": "2026-09-01",
        "action_required": True, "confidence_score": 0.98,
        "source_document_name": "Subject: forms (mom's inbox)",
        "source_reference": "gmail_msg_private"})
    ledger = client.get(f"/v1/families/{fam}/ledger", headers=headers).json()["entries"]
    ob_id = next(e["obligation_node_id"] for e in ledger if e["obligation_node_id"])

    # Before sharing: helper sees no obligations.
    hid = _hs["user"]["user_id"]
    assert client.get(f"/v1/families/{fam}/helper-view", headers=hheaders).json()[
        "shared_obligations"] == []

    # Member shares it.
    client.put(f"/v1/families/{fam}/helpers/{hid}", headers=headers,
               json={"shared_obligation_ids": [ob_id]})
    shared = client.get(f"/v1/families/{fam}/helper-view", headers=hheaders).json()[
        "shared_obligations"]
    assert len(shared) == 1
    assert shared[0]["title"] == "Permission slip due"
    # Provenance never crosses to the helper.
    assert "source_document_name" not in shared[0]
    assert "source_reference" not in shared[0]


def test_member_roster_preview_and_revoke():
    _s, fam, headers = _member()
    hs, hheaders = _helper(fam, headers, [1, 3])
    hid = hs["user"]["user_id"]

    roster = client.get(f"/v1/families/{fam}/helpers", headers=headers).json()["helpers"]
    assert roster[0]["user_id"] == hid
    assert roster[0]["display_name"] == "Grandma"
    assert roster[0]["weekday_labels"] == ["Tuesday", "Thursday"]

    # Member preview requires ?as=; bare call guides them to the briefing.
    assert client.get(f"/v1/families/{fam}/helper-view", headers=headers).status_code == 400
    preview = client.get(f"/v1/families/{fam}/helper-view?as={hid}", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["scope"]["covered_weekdays"] == ["Tuesday", "Thursday"]

    # Revoke clears scope → helper's own view goes empty.
    assert client.delete(f"/v1/families/{fam}/helpers/{hid}", headers=headers).status_code == 200
    after = client.get(f"/v1/families/{fam}/helper-view", headers=hheaders).json()
    assert after["care_watch"]["gaps"] == []
    assert after["scope"]["covered_weekdays"] == []
