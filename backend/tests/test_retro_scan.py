"""Tests for the 6-Month Retro Scan (§6)."""

from datetime import datetime, timedelta, timezone

from exhale.connectors.base import RawMessage
from exhale.connectors.memory import FixtureConnector
from exhale.extraction import ExtractionContext
from exhale.retro_scan import run_retro_scan
from exhale.store import HouseholdStore

NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)


def _email(source_id, subject, body, *, days_ago, domain=None):
    return RawMessage(
        source_id=source_id,
        channel="fixture",
        subject=subject,
        body=body,
        received_at=NOW - timedelta(days=days_ago),
        sender=f"noreply@{domain}" if domain else None,
        sender_domain=domain,
    )


def _corpus():
    return [
        _email("m1", "Field Trip Permission Slip",
               "Please sign and return the slip for Olivia. Trip on August 25, 2026. "
               "Forms due by July 20, 2026.", days_ago=3, domain="powerschool.com"),
        _email("m2", "Soccer Immunization",
               "Submit Leo's immunization record. Season starts July 24, 2026. "
               "Records due by July 21, 2026.", days_ago=10, domain="teamsnap.com"),
        _email("m3", "Newsletter", "Nothing scheduled, just saying hi.", days_ago=20),
        _email("m4", "Old flyer", "Bake sale was on January 5, 2026.", days_ago=400),  # out of window
    ]


def test_retro_scan_ingests_and_builds_snapshot():
    store = HouseholdStore()
    ctx = ExtractionContext(known_children=["Olivia", "Leo"], reference_date=NOW.date())
    result = run_retro_scan(
        FixtureConnector(_corpus()), store, "fam1", ctx, now=NOW
    )

    # m4 is outside the 180-day window; m3 has no date and is not extracted.
    assert result.scanned == 3
    assert result.extracted == 2
    assert result.committed == 2

    snap = result.snapshot
    assert snap["obligation_count"] == 2
    assert len(snap["forgotten_obligations"]) >= 1
    titles = [o["title"] for o in snap["forgotten_obligations"]]
    assert "Field Trip Permission Slip" in titles


def test_retro_scan_snapshot_headline_reports_counts():
    store = HouseholdStore()
    result = run_retro_scan(
        FixtureConnector(_corpus()),
        store,
        "fam1",
        ExtractionContext(known_children=["Olivia", "Leo"], reference_date=NOW.date()),
        now=NOW,
    )
    assert "scanned 3 recent items" in result.snapshot["headline"]


def test_rerunning_the_scan_does_not_duplicate_obligations():
    # A repeated /scan batch (or a crashed-and-retried sync) must not mint the
    # same obligations twice.
    store = HouseholdStore()
    ctx = ExtractionContext(known_children=["Olivia", "Leo"], reference_date=NOW.date())
    first = run_retro_scan(FixtureConnector(_corpus()), store, "fam1", ctx, now=NOW)
    second = run_retro_scan(FixtureConnector(_corpus()), store, "fam1", ctx, now=NOW)

    assert first.committed == 2
    assert second.committed == 0
    assert second.duplicates >= 2  # the previously-ingested messages were skipped
    obligations = [n for n in store.graph("fam1").nodes.values()
                   if n.type.value == "OBLIGATION"]
    assert len(obligations) == 2  # still two, not four
