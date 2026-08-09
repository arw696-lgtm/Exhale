"""Second-opinion sweep over the review queue.

A first real inbox scan without the LLM produces exactly one thing: a wall of
held items. The deterministic engine cannot tell a pizza coupon from a
permission slip — it sees a date, isn't sure, and holds it for a human. Forty
of those at once buries the three that matter, and tapping "not a real
obligation" forty times is the guilt-engine experience this product exists to
end.

This sweep gives every held item the judgment it didn't get at scan time.
Its autonomy posture is deliberately one-sided:

    The machine may only take junk OFF the pile. It never promotes.

* An item whose moment has clearly passed is dismissed outright (free).
* Otherwise the original email is re-fetched and the LLM re-reads it. "Not a
  household obligation" → dismissed, with the reason recorded. Anything the
  LLM thinks is real (or can't rule on, or the fetch fails) STAYS HELD for
  the human yes — confirming is a person's job, and stays one.

Dismissals land in the same ``dismissed_extractions`` set the dismiss button
uses: signal, not erasure — the ledger row remains. Each examined id is
remembered (``retriage_seen``) so an item gets its second read once, not once
per hourly cycle; reasons persist in ``retriage_reasons``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from exhale.routing import RecordStatus

log = logging.getLogger("exhale.retriage")

# An obligation whose event AND deadline are this far gone is moot — the wall
# of "Appointment Scheduled (last month)" rows answers itself.
STALE_DAYS = 14

# LLM re-reads per sweep — bounds one cycle's spend; the next cycle continues.
MAX_LLM_READS = 60


def _latest_date(payload) -> date | None:
    dates = [d for d in (payload.event_date, payload.deadline_date) if d]
    return max(dates) if dates else None


def second_opinion_sweep(
    store,
    family_id: str,
    *,
    llm=None,
    fetch_message=None,
    now: datetime | None = None,
) -> dict:
    """Sweep one family's held items. Returns counts for the cycle report.

    ``llm``            — object with ``.extract(raw) -> payload | None``
                         (an :class:`exhale.extraction_llm.LLMExtractor`).
    ``fetch_message``  — callable ``(source_reference) -> RawMessage | None``;
                         the caller decides how to reach the source (Gmail
                         by id in production, a stub in tests).
    Both optional: with neither, only the free staleness rule runs.
    """

    now = now or datetime.now(timezone.utc)
    today = now.date()

    profile = store.profile(family_id)
    already_dismissed = set(profile.get("dismissed_extractions") or [])
    already_seen = set(profile.get("retriage_seen") or [])

    pending = [
        e for e in store.ledger(family_id)
        if e.decision.status is RecordStatus.PENDING_VERIFICATION
        and e.superseded_by is None
        and e.extraction_id not in already_dismissed
        and e.extraction_id not in already_seen
    ]

    report = {"examined": 0, "stale": 0, "noise": 0, "kept_held": 0}
    newly_dismissed: dict[str, str] = {}  # id -> reason
    mark_seen: set[str] = set()  # got its one second read (or is unfetchable)
    llm_reads = 0

    for entry in pending:
        # Rule 1 (free): the moment has passed. Event and deadline both weeks
        # gone — nothing a human confirms now changes anything.
        latest = _latest_date(entry.payload)
        if latest is not None and (today - latest).days > STALE_DAYS:
            newly_dismissed[entry.extraction_id] = "moment passed"
            mark_seen.add(entry.extraction_id)
            report["examined"] += 1
            report["stale"] += 1
            continue

        # Rule 2 (LLM): re-read the source. Every failure mode keeps the item
        # held — absence of judgment must never empty the queue.
        if llm is None or fetch_message is None or llm_reads >= MAX_LLM_READS:
            continue  # not examined — eligible again next cycle

        raw = None
        try:
            raw = fetch_message(entry.payload.source_reference)
        except Exception as exc:  # noqa: BLE001 — a dead ref must not stall the sweep
            log.warning("retriage refetch %s failed: %s", entry.extraction_id, exc)
        if raw is None:
            # Unfetchable (deleted mail, foreign source) — held forever is the
            # human's call; don't burn a re-fetch on it every hour.
            mark_seen.add(entry.extraction_id)
            report["examined"] += 1
            report["kept_held"] += 1
            continue

        llm_reads += 1
        try:
            second_read = llm.extract(raw)
        except Exception as exc:  # noqa: BLE001 — LLM down = everything stays held
            log.warning("retriage LLM read %s failed: %s", entry.extraction_id, exc)
            continue  # not marked seen — retried when the LLM is back

        report["examined"] += 1
        if second_read is None:
            newly_dismissed[entry.extraction_id] = (
                "second opinion: not a household obligation"
            )
            report["noise"] += 1
        else:
            report["kept_held"] += 1  # real (or plausibly real) → human's yes
        mark_seen.add(entry.extraction_id)

    if not (newly_dismissed or mark_seen):
        return report

    with store.family_lock(family_id):
        profile = store.profile(family_id)
        dismissed = set(profile.get("dismissed_extractions") or [])
        dismissed.update(newly_dismissed)
        reasons = dict(profile.get("retriage_reasons") or {})
        reasons.update(newly_dismissed)
        seen = set(profile.get("retriage_seen") or [])
        seen |= mark_seen
        store.set_profile(
            family_id,
            dismissed_extractions=sorted(dismissed),
            retriage_reasons=reasons,
            retriage_seen=sorted(seen),
        )

    if newly_dismissed:
        log.info("retriage %s: dismissed %d (%d stale, %d noise), %d kept held",
                 family_id, len(newly_dismissed), report["stale"],
                 report["noise"], report["kept_held"])
    return report
