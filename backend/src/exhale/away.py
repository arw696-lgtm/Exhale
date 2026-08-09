"""Away periods — vacation mode (the family is together, elsewhere).

A trip changes what every other signal means. The coverage engine reasons
from the household's normal rhythm, so without this it would sit computing
"Leo needs someone Thursday 3:15" while Leo is on a beach with both parents
— and the wall feed would publish it. An instrument that is wrong at the
family's expense is worse than no instrument.

An away period is deliberately simple: a label and an inclusive date range.
While one is active:

* care-coverage gaps inside the range are suppressed — but VISIBLY (the
  payload carries the suppressed count; honesty rails: nothing vanishes
  silently),
* weekly contributions step out of the open pile (nobody mows the lawn from
  Portland; the week simply doesn't count against anyone),
* the glance and the wall feed say the family is away instead of inventing
  needs.

Deadlines and obligations are NOT suppressed: a form due mid-trip is still
due — being away is exactly when it's easiest to forget.
"""

from __future__ import annotations

import uuid
from datetime import date

MAX_AWAY_PERIODS = 50


def _parse_day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def new_away(label: str, start, end) -> dict:
    """Validate and shape one away period (range inclusive on both ends)."""

    label = (label or "").strip() or "Away"
    start_d, end_d = _parse_day(start), _parse_day(end)
    if end_d < start_d:
        raise ValueError("Away period ends before it starts")
    return {
        "away_id": f"away_{uuid.uuid4().hex[:10]}",
        "label": label[:80],
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
    }


def add_away(store, family_id: str, *, label: str, start, end) -> dict:
    period = new_away(label, start, end)
    with store.family_lock(family_id):
        profile = store.profile(family_id)
        periods = list(profile.get("away_periods") or [])
        if len(periods) >= MAX_AWAY_PERIODS:
            raise ValueError("Too many away periods")
        periods.append(period)
        periods.sort(key=lambda p: p["start"])
        store.set_profile(family_id, away_periods=periods)
    return period


def remove_away(store, family_id: str, away_id: str) -> bool:
    with store.family_lock(family_id):
        profile = store.profile(family_id)
        periods = list(profile.get("away_periods") or [])
        kept = [p for p in periods if p.get("away_id") != away_id]
        if len(kept) == len(periods):
            return False
        store.set_profile(family_id, away_periods=kept)
    return True


def away_on(profile: dict, day: date) -> dict | None:
    """The away period covering ``day``, or None. Ranges are inclusive."""

    for period in profile.get("away_periods") or []:
        try:
            if _parse_day(period["start"]) <= day <= _parse_day(period["end"]):
                return period
        except (KeyError, ValueError):
            continue
    return None


def suppress_care_gaps(watch: dict, periods: list[dict]) -> dict:
    """Drop gaps that fall inside an away period; count what was dropped.

    Returns a new watch dict with recomputed summary bands and an
    ``away_suppressed`` count — the suppression is stated, never silent.
    """

    if not watch or not periods:
        return watch

    def covered(gap: dict) -> bool:
        try:
            day = _parse_day(gap.get("date") or gap.get("start"))
        except ValueError:
            return False
        return any(
            _parse_day(p["start"]) <= day <= _parse_day(p["end"])
            for p in periods
            if p.get("start") and p.get("end")
        )

    gaps = watch.get("gaps") or []
    kept = [g for g in gaps if not covered(g)]
    suppressed = len(gaps) - len(kept)
    if suppressed == 0:
        return watch

    bands = {"CRITICAL": 0, "IMPORTANT": 0, "ADVISORY": 0}
    for g in kept:
        level = str(g.get("threat_level", "")).upper()
        if level in bands:
            bands[level] += 1
    summary = dict(watch.get("summary") or {})
    summary.update(
        total_gaps=len(kept),
        critical=bands["CRITICAL"],
        important=bands["IMPORTANT"],
        advisory=bands["ADVISORY"],
        assumption_dependent=sum(1 for g in kept if g.get("depends_on_inference")),
    )
    return {**watch, "gaps": kept, "summary": summary, "away_suppressed": suppressed}
