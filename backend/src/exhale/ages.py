"""Birthdate-derived signals — prompts and inference seeds, never decisions.

A birthdate (stored, not an age — ages go stale, birthdates never change) buys
three things, each kept strictly on the right side of the credibility line:

* **Aging-out prompts** — when a child reaches an age where many households
  loosen supervision, Exhale *asks* the family to revisit the supervised
  window. It never shortens one on its own: a specific 12-year-old being fine
  alone until 5pm is the family's call, not a rule applied from a birthday.
* **Sibling-sitter prompts** — a teenager in the house is one of the biggest
  real coverage sources there is. Exhale may *suggest* adding them as a
  caregiver; the family decides.
* **Grade inference** — prefills the grade for grade-aware school-calendar
  extraction instead of asking every year.

No birthdate → no prompts. A named unknown stays silent rather than guessed.
"""

from __future__ import annotations

from datetime import date

from exhale.coverage import DEFAULT_SUPERVISED_END, DEFAULT_SUPERVISED_START

# The age at which we *ask* the family to revisit full-day supervision. Chosen
# as a conservative prompt threshold, not a legal or safety claim.
SUPERVISION_REVIEW_AGE = 10
# The age at which an older sibling becomes worth *suggesting* as a caregiver.
SIBLING_SITTER_AGE = 13
# US-typical kindergarten cutoff: age 5 by September 1 → grade K.
KINDERGARTEN_AGE = 5


def age_on(birthdate: date, on: date) -> int:
    """Completed years of age on the given day."""

    years = on.year - birthdate.year
    if (on.month, on.day) < (birthdate.month, birthdate.day):
        years -= 1
    return years


def school_year_start(today: date) -> date:
    """September 1 of the current-or-upcoming school year."""

    cutoff = date(today.year, 9, 1)
    return cutoff if today <= cutoff else date(today.year + 1, 9, 1)


def grade_for(birthdate: date, *, today: date | None = None) -> str | None:
    """The US grade label for the school year ``today`` falls in (or starts).

    ``"K"`` for kindergarten, ``"1"``.. upward; ``None`` when the child is
    younger than school age or implausibly old for K-12 (no guessing outside
    the range the school-calendar reader can use).
    """

    today = today or date.today()
    years = age_on(birthdate, school_year_start(today))
    grade = years - KINDERGARTEN_AGE
    if grade < 0 or grade > 12:
        return None
    return "K" if grade == 0 else str(grade)


def age_prompts(model, *, today: date | None = None) -> list[dict]:
    """Age-triggered questions for the family (never actions).

    ``model`` is a parsed :class:`~exhale.coverage_config.CoverageModelIn`.
    Each prompt carries its ``basis`` so the UI can show why it appeared.
    """

    today = today or date.today()
    caregiver_names = {c.name for c in model.caregivers}
    prompts: list[dict] = []

    for child in model.children:
        r = child.recipient
        if r.birthdate is None:
            continue  # named unknown — stay silent, never guess
        age = age_on(r.birthdate, today)
        basis = f"{r.name}'s birthdate — entered by you (USER_CONFIRMED)"

        full_window = (r.supervised_start == DEFAULT_SUPERVISED_START
                       and r.supervised_end == DEFAULT_SUPERVISED_END)
        if age >= SUPERVISION_REVIEW_AGE and full_window:
            prompts.append({
                "kind": "supervised_hours_review",
                "child": r.name,
                "age": age,
                "question": (
                    f"{r.name} is {age} and still set to full-day supervision "
                    "(6:00–22:00). Still right, or shorten the window in "
                    "Household Setup? Your call — Exhale never loosens this "
                    "on its own."
                ),
                "basis": basis,
            })

        if age >= SIBLING_SITTER_AGE and r.name not in caregiver_names:
            prompts.append({
                "kind": "sibling_sitter",
                "child": r.name,
                "age": age,
                "question": (
                    f"{r.name} ({age}) might be able to cover shorter gaps. "
                    "If you're comfortable, add them as a caregiver in "
                    "Household Setup and their availability starts counting."
                ),
                "basis": basis,
            })

    return prompts
