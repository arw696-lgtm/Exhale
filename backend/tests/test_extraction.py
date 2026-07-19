"""Tests for the Layer 2 extraction engine (§3)."""

from datetime import date, datetime, timezone

import pytest

from exhale.connectors.base import Attachment, RawMessage
from exhale.extraction import ExtractionContext, extract_payload
from exhale.routing import ConfidenceBand, classify_confidence

REF = date(2026, 7, 19)  # a Sunday


def _msg(subject, body, *, domain=None, attachments=()):
    return RawMessage(
        source_id="msg_1",
        channel="fixture",
        subject=subject,
        body=body,
        received_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        sender=f"noreply@{domain}" if domain else None,
        sender_domain=domain,
        attachments=attachments,
    )


def _ctx(children=("Olivia", "Leo")):
    return ExtractionContext(known_children=list(children), reference_date=REF)


def test_full_signal_school_email_is_high_confidence():
    raw = _msg(
        "West High Field Trip Permission Slip",
        "Please sign and return the permission slip for Olivia's field trip. "
        "The trip is on August 25, 2026. Forms are due by July 24, 2026.",
        domain="powerschool.com",
    )
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.event_date == date(2026, 8, 25)
    assert payload.deadline_date == date(2026, 7, 24)
    assert payload.target_person_name == "Olivia"
    assert payload.action_required is True
    assert classify_confidence(payload.confidence_score) is ConfidenceBand.HIGH
    assert payload.source_document_name == "West High Field Trip Permission Slip"
    assert payload.source_reference == "msg_1"


def test_medium_confidence_when_untrusted_and_no_deadline():
    raw = _msg(
        "Volunteer Signup",
        "Please register for the fall festival happening on October 3, 2026.",
        domain="gmail.com",
    )
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.event_date == date(2026, 10, 3)
    assert payload.deadline_date is None
    assert classify_confidence(payload.confidence_score) is ConfidenceBand.MEDIUM


def test_low_confidence_for_vague_relative_date():
    raw = _msg("Reminder", "See you on Monday.")
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.event_date == date(2026, 7, 20)  # next Monday
    assert classify_confidence(payload.confidence_score) is ConfidenceBand.LOW


def test_no_date_returns_none():
    assert extract_payload(_msg("Hello", "Just checking in, nothing scheduled."), _ctx()) is None


def test_deadline_only_email_uses_deadline_as_event_date():
    raw = _msg("Tuition", "Tuition payment is due by 9/1/2026.")
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.event_date == date(2026, 9, 1)
    assert payload.deadline_date == date(2026, 9, 1)
    assert payload.action_required is True  # deadline implies action


def test_tomorrow_resolves_relative_to_reference():
    raw = _msg("Form", "The field form is due tomorrow.")
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.deadline_date == date(2026, 7, 20)


def test_person_defaults_to_none_when_no_known_child_present():
    raw = _msg("Notice", "The assembly is on September 9, 2026.")
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.target_person_name is None


def test_attachment_text_is_part_of_corpus():
    raw = _msg(
        "See attached",
        "Details attached.",
        attachments=(Attachment(filename="slip.pdf", mime_type="application/pdf",
                                 text="Sign and return by August 1, 2026 for Leo."),),
    )
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.deadline_date == date(2026, 8, 1)
    assert payload.target_person_name == "Leo"


def test_footer_noise_does_not_break_extraction():
    raw = _msg(
        "Picture Day",
        "Picture day is on September 4, 2026.\nUnsubscribe here to opt out.\n"
        "© 2026 School District. All rights reserved.",
    )
    payload = extract_payload(raw, _ctx())
    assert payload is not None
    assert payload.event_date == date(2026, 9, 4)
