"""Tests for the credibility layer.

Fixtures mirror the two real-world extraction failures that motivated it:
camp hours answered from typical-hours pattern-matching instead of the
logistics email that stated "1pm-4pm", and a multi-leg trip reported as one
leg because the other booking lived in an unconnected inbox.
"""

from datetime import date, datetime, time, timezone

import pytest

from exhale.briefing import build_weekly_briefing
from exhale.connectors.base import RawMessage
from exhale.credibility import build_coverage, classify_artifact
from exhale.extraction import ExtractionContext, extract_payload
from exhale.graph import KnowledgeGraph, NodeType
from exhale.routing import ConfidenceBand, RecordStatus, route_extraction
from exhale.schemas import ArtifactTier, ExtractionPayload, FactOrigin
from exhale.store import HouseholdStore


def _msg(subject, body="", *, domain=None, received=None, source_id="m1"):
    return RawMessage(
        source_id=source_id,
        channel="gmail",
        subject=subject,
        body=body,
        received_at=received or datetime(2026, 7, 13, tzinfo=timezone.utc),
        sender=f"noreply@{domain}" if domain else None,
        sender_domain=domain,
    )


def _payload(**over):
    base = dict(
        extracted_event="Junior Robotics Camp",
        event_date=date(2026, 7, 20),
        action_required=True,
        confidence_score=0.95,
        source_reference="m1",
    )
    base.update(over)
    return ExtractionPayload(**base)


CTX = ExtractionContext(known_children=["Stevie"])


# --- Artifact tier classification -------------------------------------------------
def test_reservation_email_is_confirmation_tier():
    raw = _msg("RE: Reservation for Luxe & Tranquil Forest Oasis, Aug 23 - 26")
    assert classify_artifact(raw) is ArtifactTier.CONFIRMATION


def test_camp_logistics_email_is_logistics_tier():
    raw = _msg(
        "Camp is next week!",
        "Here's what you need to know about the week ahead. "
        "Camp check-in is between 12:30 and 1 p.m.",
    )
    assert classify_artifact(raw) is ArtifactTier.LOGISTICS


def test_retail_blast_is_marketing_tier():
    assert classify_artifact(_msg("The Back to School sale is on")) is ArtifactTier.MARKETING
    assert classify_artifact(_msg("Up to 50% Off is Calling")) is ArtifactTier.MARKETING
    assert classify_artifact(_msg("Member-Only Savings Await")) is ArtifactTier.MARKETING


def test_bake_sale_in_body_is_not_marketing():
    # "sale" is a subject-only cue: legitimate school mail says "bake sale".
    raw = _msg("PTA fundraiser", "The bake sale is on September 5, 2026.")
    assert classify_artifact(raw) is not ArtifactTier.MARKETING


def test_reminder_and_newsletter_tiers():
    assert classify_artifact(_msg("Reminder: forms due Friday")) is ArtifactTier.REMINDER
    assert classify_artifact(_msg("What's happening in camp this week?")) is ArtifactTier.NEWSLETTER


def test_unclassified_defaults_to_unknown():
    raw = _msg("Field Trip Permission Slip", "Please sign and return the slip.")
    assert classify_artifact(raw) is ArtifactTier.UNKNOWN


# --- Time-window extraction (the "1pm-4pm" fix) ------------------------------------
def test_extracts_observed_time_window_from_logistics_email():
    # Shaped like the real Works Museum email: the answer was one search away.
    raw = _msg(
        "Camp is next week!",
        "Camper Information: Jul 20 1pm-4pm: Junior Robotics - Stevie. "
        "Camp check-in is between 12:30 and 1 p.m. for afternoon camps.",
    )
    payload = extract_payload(raw, CTX)
    assert payload is not None
    assert payload.event_start_time == time(13, 0)
    assert payload.event_end_time == time(16, 0)
    assert payload.artifact_tier is ArtifactTier.LOGISTICS
    assert "event_time_window" not in payload.missing_fields()


def test_no_stated_hours_stays_unknown_not_a_guess():
    raw = _msg("Zoo Camp", "Stevie's zoo camp runs the week of July 27, 2026.")
    payload = extract_payload(raw, CTX)
    assert payload is not None
    assert payload.event_start_time is None
    assert payload.event_end_time is None
    assert "event_time_window" in payload.missing_fields()


def test_date_fragments_never_parse_as_time_windows():
    # "Jul 20-23" and ISO dates must not produce a bogus window.
    raw = _msg("Session dates", "Camp runs Jul 20-23. Confirmed on 2026-07-13.")
    payload = extract_payload(raw, CTX)
    assert payload is not None
    assert payload.event_start_time is None


def test_start_inherits_meridiem_without_running_backwards():
    raw = _msg("Practice", "Practice is on July 22, 2026 from 11-1pm.")
    payload = extract_payload(raw, CTX)
    assert payload is not None
    assert payload.event_start_time == time(11, 0)
    assert payload.event_end_time == time(13, 0)


# --- Observed vs. inferred dates ----------------------------------------------------
def test_explicit_date_is_observed():
    raw = _msg("Picture Day", "Picture day is on September 4, 2026.")
    payload = extract_payload(raw, CTX)
    assert payload.event_date_origin is FactOrigin.OBSERVED


def test_relative_date_is_inferred():
    raw = _msg("Camp session", "Your camp session begins next week.")
    payload = extract_payload(raw, CTX)
    assert payload.event_date_origin is FactOrigin.INFERRED


# --- Routing ceilings ----------------------------------------------------------------
def test_marketing_is_rejected_regardless_of_score():
    decision = route_extraction(_payload(artifact_tier=ArtifactTier.MARKETING,
                                         confidence_score=0.99))
    assert decision.status is RecordStatus.REJECTED
    assert not decision.commits_to_graph


def test_reminder_tier_never_auto_commits():
    decision = route_extraction(_payload(artifact_tier=ArtifactTier.REMINDER))
    assert decision.band is ConfidenceBand.MEDIUM
    assert decision.status is RecordStatus.PENDING_VERIFICATION
    assert decision.requires_user_review


def test_newsletter_tier_never_auto_commits():
    decision = route_extraction(_payload(artifact_tier=ArtifactTier.NEWSLETTER))
    assert decision.status is RecordStatus.PENDING_VERIFICATION


def test_inferred_date_never_auto_commits():
    decision = route_extraction(_payload(event_date_origin=FactOrigin.INFERRED))
    assert decision.status is RecordStatus.PENDING_VERIFICATION
    assert "inferred" in decision.rationale.lower()


def test_confirmation_tier_with_observed_date_still_commits():
    decision = route_extraction(_payload(artifact_tier=ArtifactTier.CONFIRMATION))
    assert decision.status is RecordStatus.COMMITTED


def test_user_confirmed_commits_even_from_marketing_tier():
    decision = route_extraction(_payload(
        event_date_origin=FactOrigin.USER_CONFIRMED,
        artifact_tier=ArtifactTier.MARKETING,
        confidence_score=1.0,
    ))
    assert decision.status is RecordStatus.COMMITTED


def test_reminder_below_high_band_routes_normally():
    # The ceiling only demotes HIGH; a mid-score reminder is ordinary MEDIUM.
    decision = route_extraction(_payload(artifact_tier=ArtifactTier.REMINDER,
                                         confidence_score=0.8))
    assert decision.band is ConfidenceBand.MEDIUM


# --- Corroboration (falsification-pass primitive) ------------------------------------
def test_single_witness_is_uncorroborated_second_source_corroborates():
    store = HouseholdStore()
    first = store.ingest("fam1", _payload(source_reference="msg_a"))
    second = store.ingest("fam1", _payload(source_reference="msg_b"))

    graph = store.graph("fam1")
    ob_first = graph.nodes[first.obligation_node_id]
    ob_second = graph.nodes[second.obligation_node_id]
    assert ob_first.properties["corroborated"] is False
    assert ob_second.properties["corroborated"] is True

    anchors = [n for n in graph.nodes.values() if n.type is NodeType.EVENT]
    assert len(anchors) == 1
    assert anchors[0].properties["witness_refs"] == ["msg_a", "msg_b"]


def test_same_source_twice_does_not_self_corroborate():
    store = HouseholdStore()
    store.ingest("fam1", _payload(source_reference="msg_a"))
    entry = store.ingest("fam1", _payload(source_reference="msg_a"))
    ob = store.graph("fam1").nodes[entry.obligation_node_id]
    assert ob.properties["corroborated"] is False


# --- Obligation nodes carry the credibility record ------------------------------------
def test_committed_obligation_records_provenance_and_gaps():
    store = HouseholdStore()
    entry = store.ingest("fam1", _payload(
        artifact_tier=ArtifactTier.LOGISTICS,
        event_start_time=time(13, 0),
        event_end_time=time(16, 0),
        target_person_name="Stevie",
        deadline_date=date(2026, 7, 18),
    ))
    props = store.graph("fam1").nodes[entry.obligation_node_id].properties
    assert props["artifact_tier"] == "LOGISTICS"
    assert props["event_date_origin"] == "OBSERVED"
    assert props["event_start_time"] == "13:00:00"
    assert props["hours_known"] is True
    assert props["missing_fields"] == []


def test_obligation_with_unknown_hours_says_so():
    store = HouseholdStore()
    entry = store.ingest("fam1", _payload(target_person_name="Stevie",
                                          deadline_date=date(2026, 7, 18)))
    props = store.graph("fam1").nodes[entry.obligation_node_id].properties
    assert props["hours_known"] is False
    assert "event_time_window" in props["missing_fields"]


# --- User corrections are ground truth -------------------------------------------------
def test_correction_of_pending_entry_commits_and_supersedes():
    store = HouseholdStore()
    # A reminder-tier extraction: held pending, no obligation committed.
    original = store.ingest("fam1", _payload(artifact_tier=ArtifactTier.REMINDER))
    assert original.obligation_node_id is None

    corrected = store.correct(
        "fam1", original.extraction_id,
        event_start_time=time(13, 0), event_end_time=time(16, 0),
    )
    assert corrected.decision.status is RecordStatus.COMMITTED
    assert corrected.obligation_node_id is not None
    assert corrected.payload.event_date_origin is FactOrigin.USER_CONFIRMED
    assert corrected.payload.corrects == original.extraction_id
    assert original.superseded_by == corrected.extraction_id

    props = store.graph("fam1").nodes[corrected.obligation_node_id].properties
    assert props["event_start_time"] == "13:00:00"


def test_correction_of_committed_entry_updates_node_in_place():
    store = HouseholdStore()
    original = store.ingest("fam1", _payload())
    node_id = original.obligation_node_id
    assert node_id is not None

    corrected = store.correct("fam1", original.extraction_id,
                              event_start_time=time(13, 0),
                              event_end_time=time(16, 0))
    assert corrected.obligation_node_id == node_id  # updated, not duplicated
    props = store.graph("fam1").nodes[node_id].properties
    assert props["event_start_time"] == "13:00:00"
    assert props["event_date_origin"] == "USER_CONFIRMED"


def test_correction_of_unknown_extraction_raises():
    with pytest.raises(KeyError):
        HouseholdStore().correct("fam1", "ext_nope", event_date=date(2026, 8, 1))


def test_supersession_relink_from_payload_corrects():
    store = HouseholdStore()
    original = store.ingest("fam1", _payload())
    corrected = store.correct("fam1", original.extraction_id,
                              event_date=date(2026, 7, 21))
    # Simulate hydration: links rebuilt purely from payload.corrects.
    original.superseded_by = None
    HouseholdStore._link_supersessions(store.ledger("fam1"))
    assert original.superseded_by == corrected.extraction_id


def test_ledger_dict_exposes_credibility_fields():
    store = HouseholdStore()
    entry = store.ingest("fam1", _payload(artifact_tier=ArtifactTier.CONFIRMATION))
    row = entry.to_dict()
    assert row["artifact_tier"] == "CONFIRMATION"
    assert row["event_date_origin"] == "OBSERVED"
    assert row["event_start_time"] is None
    assert "event_time_window" in row["missing_fields"]
    assert row["superseded_by"] is None


# --- Coverage honesty --------------------------------------------------------------------
def test_undeclared_coverage_is_an_explicit_state():
    coverage = build_coverage(None)
    assert coverage["connected_sources"] == []
    assert "undeclared" in coverage["statement"].lower()


def test_coverage_statement_names_blind_spots():
    profile = {"coverage": {
        "connected_sources": ["gmail:arw696@gmail.com"],
        "known_missing_sources": [
            {"source": "gmail:archesney22@gmail.com", "owns": ["travel bookings"]},
            {"source": "parentsquare", "owns": ["school communications"]},
        ],
    }}
    coverage = build_coverage(profile)
    statement = coverage["statement"]
    assert "gmail:archesney22@gmail.com" in statement
    assert "travel bookings" in statement
    assert "parentsquare" in statement
    assert "incomplete by construction" in statement


def test_briefing_always_carries_coverage_block():
    briefing = build_weekly_briefing(KnowledgeGraph())
    assert "coverage" in briefing
    assert "undeclared" in briefing["coverage"]["statement"].lower()

    declared = build_coverage({"coverage": {"connected_sources": ["gmail:a"]}})
    briefing = build_weekly_briefing(KnowledgeGraph(), coverage=declared)
    assert briefing["coverage"]["connected_sources"] == ["gmail:a"]
