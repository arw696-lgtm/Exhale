"""Tests for the §10 copywriting templates."""

from datetime import date

from exhale import templates


def test_critical_deadline_alarm_includes_all_fields():
    body = templates.critical_deadline_alarm(
        parent_first_name="Andrew",
        extracted_event="Field Trip Permission Slip",
        target_person_name="Olivia",
        deadline_date=date(2026, 7, 20),
        source_document_name="West High Weekly Newsletter",
        source_document_date=date(2026, 7, 15),
        is_tomorrow=True,
        has_reply_draft=True,
    )
    assert body.startswith("[🚨 CRITICAL THREAT]")
    assert "Hey Andrew" in body
    assert "• What: Field Trip Permission Slip" in body
    assert "• Who: Olivia" in body
    assert "2026-07-20 (Tomorrow)" in body
    assert "West High Weekly Newsletter" in body
    assert "sent on 2026-07-15" in body
    assert "send it from your own mail app" in body
    assert body.endswith("[👉 Review & Send Reply]")


def test_critical_alarm_without_person_or_source():
    body = templates.critical_deadline_alarm(
        parent_first_name="Andrew",
        extracted_event="Tuition Payment",
        target_person_name=None,
        deadline_date="2026-09-01",
    )
    assert "• Who: your household" in body
    assert "We parsed this" not in body


def test_critical_alarm_never_promises_a_send_it_cannot_make():
    """Honest copy: no reply draft → no send-shaped claims anywhere."""

    body = templates.critical_deadline_alarm(
        parent_first_name="Andrew",
        extracted_event="Field Trip Permission Slip",
        target_person_name="Olivia",
        deadline_date=date(2026, 7, 20),
        source_document_name="West High Weekly Newsletter",
    )
    assert "reply" not in body.lower()
    assert "send" not in body.lower()
    assert body.endswith("[👉 Review & Mark Handled]")


def test_sign_form_reply_is_parent_voiced_and_asks_about_paper():
    body = templates.sign_form_reply(
        parent_name="Andrew",
        target_person_name="Olivia",
        obligation_name="West High Field Trip Permission Slip",
        deadline_date=date(2026, 8, 1),
    )
    assert body.startswith("Hi,")
    assert "Olivia has my permission" in body
    assert "Please accept this email as my sign-off." in body
    # It asks whether paper is still required — never assumes email suffices.
    assert "if a printed or signed paper copy is still required" in body.lower()
    assert "2026-08-01" in body
    assert body.endswith("Thank you,\nAndrew")
    # The reply is the parent's words leaving the household: no branding,
    # no robot voice.
    assert "Exhale" not in body
    assert "Forgetting Engine" not in body


def test_sign_form_reply_without_child_or_deadline():
    body = templates.sign_form_reply(
        parent_name="Andrew",
        target_person_name=None,
        obligation_name="Field Day Waiver",
    )
    assert "our child has my permission" in body
    assert "deadline" not in body.lower()


def test_dependency_gap_alarm_lists_confirmed_and_missing():
    body = templates.dependency_gap_alarm(
        anchor_event_name="School Resumes",
        days_until_event=21,
        target_person_name="Olivia",
        missing_item_name="3rd Grade Supply List",
        confirmed_prerequisites=[("Health Clearance", "Verified July 14")],
        total_items_count=12,
    )
    assert "School Resumes starts in 21 days for Olivia." in body
    assert "• [✓] Health Clearance: Confirmed (Verified July 14)" in body
    assert "• [!] 3rd Grade Supply List: MISSING" in body
    assert "[🛒 Add all 12 items to Household Shopping Cart]" in body


def test_dependency_gap_alarm_without_item_count_has_no_cart_cta():
    body = templates.dependency_gap_alarm(
        anchor_event_name="Soccer Camp",
        days_until_event=10,
        target_person_name="Leo",
        missing_item_name="Shin Guards",
    )
    assert "Shopping Cart" not in body
    assert "• [!] Shin Guards: MISSING" in body


def test_value_realization_summary():
    body = templates.value_realization_summary(
        total_active_nodes=42,
        saved_surprises_count=3,
        saved_events=[("2026-07-20", "Permission slip"), ("2026-07-24", "Immunization")],
        horizon_day_increase=9,
    )
    assert "managed 42 nodes" in body
    assert "intercepted 3 logistics oversights" in body
    assert "• Intercepted 2026-07-20: Permission slip" in body
    assert "expanded by 9 days" in body
