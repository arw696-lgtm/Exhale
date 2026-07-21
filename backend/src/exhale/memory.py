"""Layer 4 — Memory: learned recurring rules (blueprint §4 Memory).

The graph remembers *facts*; this module learns *patterns* — the implicit
rhythms a household runs on that no single email states. The founding example
(from live testing): ISLA closes camp registration on the Wednesday *before*
each session, a rule the family discovered by missing it. After a few
occurrences, that rhythm is sitting in the extraction ledger — this engine
reads it back out.

Two deterministic detectors, both requiring multiple witnesses (a pattern
asserted from one sample would be a guess, and guesses are banned here):

* **Weekly cadence** — the same event stem recurring on the same weekday at a
  regular weekly interval ("Every Monday: ISLA Camp").
* **Deadline lead** — deadlines consistently landing a fixed number of days
  before the event across occurrences ("Registration closes 5 days before —
  always a Wednesday").

Each rule carries its sample count and the source references that witnessed it
(the credibility discipline: a learned rule cites its evidence like any other
fact). Rules are recomputed from the ledger on demand — no hidden state to
drift out of sync.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Strip dates/numbers/week-references so recurring instances share one stem:
# "ISLA Camp this Week 7/13" and "ISLA Camp this Week 7/20" → "isla camp".
_NOISE = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b|\bweek of\b|"
    r"\bthis week\b|\bnext week\b|\bweek\b|\b\d+\b",
    re.I,
)
_PUNCT = re.compile(r"[^\w\s]")


def _stem(title: str) -> str:
    text = _NOISE.sub(" ", title.lower())
    text = _PUNCT.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class LearnedRule:
    """A recurring household pattern, with the evidence that taught it."""

    kind: str          # WEEKLY_CADENCE | DEADLINE_LEAD
    subject: str       # the event stem the rule is about
    detail: str        # human-readable statement of the rule
    samples: int       # how many occurrences witnessed it
    evidence: tuple[str, ...]  # source references of the witnessing entries

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "detail": self.detail,
            "samples": self.samples,
            "evidence": list(self.evidence),
        }


def learn_rules(entries, *, min_samples: int = 3) -> list[LearnedRule]:
    """Mine the extraction ledger for recurring rules.

    ``entries`` are :class:`~exhale.store.LedgerEntry` items (rejected ones are
    ignored — noise doesn't get to teach). Deterministic and order-stable.
    """

    groups: dict[str, list] = defaultdict(list)
    for entry in entries:
        if entry.decision.status.value == "REJECTED":
            continue
        stem = _stem(entry.payload.extracted_event)
        if stem:
            groups[stem].append(entry)

    rules: list[LearnedRule] = []
    for stem in sorted(groups):
        group = groups[stem]
        # Dedupe by event_date so a resend doesn't double-witness one occurrence.
        by_date = {}
        for e in group:
            by_date.setdefault(e.payload.event_date, e)
        occurrences = [by_date[d] for d in sorted(by_date)]

        rules.extend(_weekly_cadence(stem, occurrences, min_samples))
        rules.extend(_deadline_lead(stem, occurrences, min_samples))
    return rules


def _weekly_cadence(stem: str, occurrences, min_samples: int) -> list[LearnedRule]:
    if len(occurrences) < min_samples:
        return []
    dates = [e.payload.event_date for e in occurrences]
    weekday = dates[0].weekday()
    if any(d.weekday() != weekday for d in dates):
        return []
    deltas = {(b - a).days for a, b in zip(dates, dates[1:])}
    # Regular weekly rhythm: every gap a multiple of 7 (skipped weeks allowed).
    if not deltas or any(delta <= 0 or delta % 7 != 0 for delta in deltas):
        return []
    return [LearnedRule(
        kind="WEEKLY_CADENCE",
        subject=stem,
        detail=f"“{stem}” recurs on {_WEEKDAYS[weekday]}s ({len(dates)} occurrences seen)",
        samples=len(dates),
        evidence=tuple(e.payload.source_reference or "" for e in occurrences),
    )]


def _deadline_lead(stem: str, occurrences, min_samples: int) -> list[LearnedRule]:
    with_deadline = [
        e for e in occurrences
        if e.payload.deadline_date is not None
        and e.payload.deadline_date <= e.payload.event_date
    ]
    if len(with_deadline) < min_samples:
        return []
    leads = {(e.payload.event_date - e.payload.deadline_date).days for e in with_deadline}
    if len(leads) != 1:
        return []  # inconsistent lead → no rule; we don't average guesses
    lead = leads.pop()
    if lead == 0:
        return []  # deadline == event date teaches nothing
    deadline_weekdays = {e.payload.deadline_date.weekday() for e in with_deadline}
    weekday_note = (
        f" — always a {_WEEKDAYS[deadline_weekdays.pop()]}"
        if len(deadline_weekdays) == 1
        else ""
    )
    return [LearnedRule(
        kind="DEADLINE_LEAD",
        subject=stem,
        detail=(
            f"“{stem}” deadlines run {lead} day{'s' if lead != 1 else ''} before "
            f"the event{weekday_note} ({len(with_deadline)} occurrences seen)"
        ),
        samples=len(with_deadline),
        evidence=tuple(e.payload.source_reference or "" for e in with_deadline),
    )]
