"""Cold-start 6-Month Retro Scan (Blueprint §6).

Orchestrates a connector over the household's recent history: fetch → extract →
route → ingest, then distill an immediate **Household Assessment Snapshot** that
surfaces active entities and a few already-forgotten obligations — proving value
in the first session before the user enters anything manually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from exhale.briefing import build_weekly_briefing
from exhale.connectors.base import Connector
from exhale.extraction import ExtractionContext, extract_payload
from exhale.graph import NodeType
from exhale.routing import RecordStatus
from exhale.store import HouseholdStore

RETRO_SCAN_DAYS = 180


@dataclass
class RetroScanResult:
    family_id: str
    scanned: int = 0
    extracted: int = 0
    committed: int = 0
    pending: int = 0
    rejected: int = 0
    snapshot: dict = field(default_factory=dict)


def run_retro_scan(
    connector: Connector,
    store: HouseholdStore,
    family_id: str,
    ctx: ExtractionContext | None = None,
    *,
    days: float = RETRO_SCAN_DAYS,
    now: datetime | None = None,
    extractor=extract_payload,
) -> RetroScanResult:
    """Run the retro scan and return counts + a Household Assessment Snapshot.

    ``extractor`` is any callable with the ``extract_payload`` interface —
    the deterministic default, or the LLM-backed hybrid from
    :mod:`exhale.extraction_llm`.
    """

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    ctx = ctx or ExtractionContext(reference_date=now.date())

    result = RetroScanResult(family_id=family_id)
    for raw in connector.fetch(since=since):
        result.scanned += 1
        payload = extractor(raw, ctx)
        if payload is None:
            continue
        result.extracted += 1
        entry = store.ingest(family_id, payload)
        status = entry.decision.status
        if status is RecordStatus.COMMITTED:
            result.committed += 1
        elif status is RecordStatus.PENDING_VERIFICATION:
            result.pending += 1
        else:
            result.rejected += 1

    result.snapshot = _build_snapshot(store, family_id, result, now=now)
    return result


def run_incremental_sync(
    connector: Connector,
    store: HouseholdStore,
    family_id: str,
    ctx: ExtractionContext | None = None,
    *,
    now: datetime | None = None,
    extractor=extract_payload,
) -> RetroScanResult:
    """Sync only what's new since the last run (Blueprint §2 Layer 1).

    The last-sync watermark lives in the family profile, so under the
    persistent store it survives restarts. First run falls back to the full
    6-month retro scan window.
    """

    now = now or datetime.now(timezone.utc)
    last = store.profile(family_id).get("last_sync_at")
    if last:
        since = datetime.fromisoformat(last)
        days = max((now - since).total_seconds() / 86400.0, 0.0)
    else:
        days = RETRO_SCAN_DAYS

    result = run_retro_scan(
        connector, store, family_id, ctx, days=days, now=now, extractor=extractor
    )
    store.set_profile(family_id, last_sync_at=now.isoformat())
    return result


def _build_snapshot(
    store: HouseholdStore, family_id: str, result: RetroScanResult, *, now: datetime
) -> dict:
    """Distill the "Household Assessment Snapshot" (§6.3)."""

    graph = store.graph(family_id)
    node_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        node_counts[node.type.value] = node_counts.get(node.type.value, 0) + 1

    briefing = build_weekly_briefing(graph, now=now)
    forgotten = (briefing["critical_threats"] + briefing["dependency_watch"])[:3]

    return {
        "headline": (
            f"Exhale scanned {result.scanned} recent items and already found "
            f"{len(forgotten)} obligation(s) worth your attention."
        ),
        "active_nodes": node_counts,
        "obligation_count": node_counts.get(NodeType.OBLIGATION.value, 0),
        "forgotten_obligations": [
            {
                "title": item["title"],
                "person": item.get("person"),
                "deadline": item["deadline"],
                "threat_level": item["threat_level"],
            }
            for item in forgotten
        ],
        "briefing_summary": briefing["summary"],
    }
