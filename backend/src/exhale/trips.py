"""Trip detection — travel bookings clustered into a suggested away period.

The evidence is already in the ledger: an Airbnb confirmation, a rental car,
two flight emails, all landing within the same week. Individually each is
just "a thing with a date"; together they obviously mean *the family is going
somewhere*. This module connects those dots.

The autonomy posture is suggestion-never-enactment: being wrong about
vacation mode means suppressing real childcare gaps, so Exhale proposes
("Looks like a trip: Aug 19–24 — 3 travel bookings") and a human's tap turns
it into an away period. Dismissing a suggestion is remembered; it never
re-nags.

Detection is deliberately conservative:

* an artifact counts as travel only on strong signal — a known travel-brand
  sender domain, or unambiguous travel wording (flight/airline/boarding/
  Airbnb/rental car/hotel/itinerary),
* restaurant-style reservations are explicitly excluded (a dinner booking is
  a night out, not a trip),
* one artifact alone never makes a trip — it takes at least two, clustered
  within a few days, in the future.

Dismissed-as-noise ledger entries still count as evidence: the second-opinion
sweep judging "your Airbnb receipt is not a household obligation" is correct
for the review queue and irrelevant here — a receipt is exactly how trips
announce themselves.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone

# Merge artifacts whose dates are at most this far apart into one trip.
CLUSTER_GAP_DAYS = 3
# Suggest only trips starting within this horizon (a flight booked for next
# spring is real, but the suggestion is noise until it's close).
SUGGEST_HORIZON_DAYS = 90
MIN_ARTIFACTS = 2

_TRAVEL_DOMAINS = re.compile(
    r"(airbnb|vrbo|booking\.com|expedia|kayak|hopper|hotels?\.com|marriott|"
    r"hilton|hyatt|ihg|delta|united|southwest|alaskaair|aa\.com|jetblue|"
    r"frontier|spirit|allegiant|hertz|avis|budget|enterprise|alamo|national|"
    r"thrifty|turo|amtrak)",
    re.IGNORECASE,
)
_TRAVEL_WORDS = re.compile(
    r"\b(flight|airline|boarding|itinerary|airbnb|vrbo|hotel|resort|lodge|"
    r"rental car|car rental|rent a car|check-?in\b.*\bcheck-?out|round.?trip|"
    r"departure|amtrak|cruise)\b",
    re.IGNORECASE,
)
_NOT_TRAVEL = re.compile(
    r"\b(restaurant|dinner|table|dining|brunch|lunch)\b", re.IGNORECASE
)


def is_travel_artifact(entry: dict) -> bool:
    """Strong-signal travel test over a ledger entry dict."""

    text = f"{entry.get('extracted_event') or ''} {entry.get('source_document_name') or ''}"
    if _NOT_TRAVEL.search(text):
        return False
    sender = entry.get("source_sender") or ""
    if _TRAVEL_DOMAINS.search(sender.split("@")[-1]):
        return True
    return bool(_TRAVEL_WORDS.search(text))


def _entry_date(entry: dict) -> date | None:
    try:
        return date.fromisoformat(str(entry.get("event_date"))[:10])
    except (TypeError, ValueError):
        return None


def _covered(day_a: date, day_b: date, periods: list[dict]) -> bool:
    """True when [day_a, day_b] lies inside one existing away period."""

    for p in periods:
        try:
            if (date.fromisoformat(p["start"]) <= day_a
                    and day_b <= date.fromisoformat(p["end"])):
                return True
        except (KeyError, ValueError):
            continue
    return False


def suggest_trips(
    entries: list[dict],
    *,
    existing_away: list[dict] | None = None,
    dismissed: set[str] | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Cluster travel artifacts into suggested away periods.

    ``entries`` are ledger-entry dicts (superseded ones already excluded by
    the caller). Returns suggestions newest-first-by-start, each carrying a
    stable ``trip_id`` (hash of its artifact ids) so a dismissal sticks even
    as unrelated ledger entries accumulate.
    """

    now = now or datetime.now(timezone.utc)
    today = now.date()
    existing_away = existing_away or []
    dismissed = dismissed or set()

    dated = sorted(
        ((d, e) for e in entries if is_travel_artifact(e)
         if (d := _entry_date(e)) is not None),
        key=lambda pair: pair[0],
    )

    clusters: list[list[tuple[date, dict]]] = []
    for day, entry in dated:
        if clusters and (day - clusters[-1][-1][0]).days <= CLUSTER_GAP_DAYS:
            clusters[-1].append((day, entry))
        else:
            clusters.append([(day, entry)])

    suggestions = []
    for cluster in clusters:
        if len(cluster) < MIN_ARTIFACTS:
            continue
        start, end = cluster[0][0], cluster[-1][0]
        if end < today:  # the trip already happened
            continue
        if (start - today).days > SUGGEST_HORIZON_DAYS:
            continue
        if _covered(start, end, existing_away):  # already declared
            continue
        ids = sorted(e.get("extraction_id") or "" for _, e in cluster)
        trip_id = "trip_" + hashlib.sha1("|".join(ids).encode()).hexdigest()[:12]
        if trip_id in dismissed:
            continue
        suggestions.append({
            "trip_id": trip_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "artifact_count": len(cluster),
            "artifacts": [str(e.get("extracted_event") or "")[:90]
                          for _, e in cluster],
        })
    suggestions.sort(key=lambda s: s["start"])
    return suggestions
