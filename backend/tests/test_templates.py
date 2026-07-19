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
    )
    assert body.startswith("[🚨 CRITICAL THREAT]")
    assert "Hey Andrew" in body
    assert "• What: Field Trip Permission Slip" in body
    assert "• Who: Olivia" in body
    assert "2026-07-20 (Tomorrow)" in body
    assert "West High Weekly Newsletter" in body
    assert "sent on 2026-07-15" in body
    assert body.endswith("[👉 Review, Sign, and Send Now]")


def test_critical_alarm_without_person_or_source():
    body = templates.critical_deadline_alarm(
        parent_first_name="Andrew",
        extracted_event="Tuition Payment",
        target_person_name=None,
        deadline_date="2026-09-01",
    )
    assert "• Who: your household" in body
    assert "We parsed this" not in body


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
