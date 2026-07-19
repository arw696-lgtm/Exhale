"""Demo: 6-Month Retro Scan over a messy inbox (Blueprint §2, §3, §6).

Feeds raw, unstructured "emails" through the full Layer 1→2 pipeline
(connector → cleanse → extract → route → graph) and prints the resulting
Household Assessment Snapshot.

Usage::

    cd backend && PYTHONPATH=src python examples/demo_retro_scan.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from exhale.connectors.base import RawMessage
from exhale.connectors.memory import FixtureConnector
from exhale.extraction import ExtractionContext
from exhale.retro_scan import run_retro_scan
from exhale.store import HouseholdStore

NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)


def _email(sid, subject, body, days_ago, domain=None):
    return RawMessage(
        source_id=sid, channel="gmail", subject=subject, body=body,
        received_at=NOW - timedelta(days=days_ago),
        sender=f"noreply@{domain}" if domain else None, sender_domain=domain,
    )


INBOX = [
    _email("m1", "West High Field Trip Permission Slip",
           "Please sign and return the permission slip for Olivia's field trip. "
           "The trip is on August 25, 2026. Forms are due by July 20, 2026.\n"
           "Unsubscribe here to stop these emails.", 4, "powerschool.com"),
    _email("m2", "Soccer League — Immunization Records",
           "Reminder: submit Leo's state immunization record before the season. "
           "Season starts July 24, 2026. Records due by July 21, 2026.", 9, "teamsnap.com"),
    _email("m3", "3rd Grade Supply List",
           "The classroom supply list for Olivia is attached. Please bring items by "
           "the first week of school, September 8, 2026.", 12, "schoology.com"),
    _email("m4", "Weekend plans", "No school stuff — just brunch on Sunday.", 15),
    _email("m5", "Bake sale 2025", "Thanks for last year's bake sale on Nov 3, 2025.", 320),
]


def main() -> None:
    store = HouseholdStore()
    ctx = ExtractionContext(known_children=["Olivia", "Leo"], reference_date=NOW.date())
    result = run_retro_scan(FixtureConnector(INBOX), store, "family_demo", ctx, now=NOW)

    print(f"scanned={result.scanned} extracted={result.extracted} "
          f"committed={result.committed} pending={result.pending} rejected={result.rejected}")
    print(json.dumps(result.snapshot, indent=2))


if __name__ == "__main__":
    main()
