"""Controlled autonomy — per-household permission dials + earned trust (§6).

The blueprint's autonomy path is *Observe → Recommend → Draft → Execute with
Approval → Autonomous*. This module makes that a per-household, per-action
**setting** rather than a fixed policy: some families want Exhale writing to
their calendar freely, some want a tap-to-approve, some want it off entirely.

The promotion rule is the important part: **autonomy is earned with evidence,
never self-granted.** Every review-queue decision is a scored test of Exhale's
judgment — a confirmation means it was right to surface the item, a dismissal
means it was wrong. When the track record clears the bar, Exhale *proposes* the
upgrade, showing its record; the human flips the dial. The system never
promotes itself.
"""

from __future__ import annotations

from enum import Enum


class AutonomyLevel(str, Enum):
    OFF = "OFF"    # Exhale may not perform this action at all
    ASK = "ASK"    # Exhale drafts; a human tap executes (the default)
    AUTO = "AUTO"  # Exhale executes and reports


# Action categories with an autonomy dial. calendar_write is the first; the
# same machinery serves future categories (send_email, purchase, …).
DEFAULT_AUTONOMY: dict[str, str] = {
    "calendar_write": AutonomyLevel.ASK.value,
}

# Promotion bar: enough decisions to mean something, almost all of them right.
PROMOTION_MIN_DECISIONS = 10
PROMOTION_MIN_ACCURACY = 0.9


def autonomy_settings(profile: dict) -> dict[str, str]:
    """The household's dials, defaults filled in for unset categories."""

    stored = profile.get("autonomy") or {}
    return {**DEFAULT_AUTONOMY, **{k: v for k, v in stored.items() if k in DEFAULT_AUTONOMY}}


def level_for(profile: dict, category: str) -> AutonomyLevel:
    return AutonomyLevel(autonomy_settings(profile).get(category, AutonomyLevel.ASK.value))


def trust_record(ledger_entries, dismissed_ids: set[str]) -> dict:
    """Exhale's scored track record, computed from review decisions.

    * **agreed** — items the user confirmed (a USER_CONFIRMED entry that
      corrects a prior one with no changes is "yes, you were right").
    * **overruled** — items the user dismissed ("that wasn't real").

    Accuracy over those decisions is the evidence a promotion proposal cites.
    Corrections with actual field changes are counted as agreed-with-fixes —
    the item was real, details needed help — and tracked separately.
    """

    agreed = overruled = agreed_with_fixes = 0
    by_id = {e.extraction_id: e for e in ledger_entries}
    for entry in ledger_entries:
        corrects = entry.payload.corrects
        if corrects and corrects in by_id:
            original = by_id[corrects]
            same = entry.payload.model_dump(exclude={"corrects", "confidence_score",
                                                     "event_date_origin"}) == \
                original.payload.model_dump(exclude={"corrects", "confidence_score",
                                                     "event_date_origin"})
            if same:
                agreed += 1
            else:
                agreed_with_fixes += 1
    overruled = len(dismissed_ids)

    decisions = agreed + agreed_with_fixes + overruled
    accuracy = (agreed + agreed_with_fixes) / decisions if decisions else None
    return {
        "agreed": agreed,
        "agreed_with_fixes": agreed_with_fixes,
        "overruled": overruled,
        "decisions": decisions,
        "accuracy": round(accuracy, 3) if accuracy is not None else None,
        "eligible_for_auto": (
            decisions >= PROMOTION_MIN_DECISIONS
            and accuracy is not None
            and accuracy >= PROMOTION_MIN_ACCURACY
        ),
        "promotion_bar": {
            "min_decisions": PROMOTION_MIN_DECISIONS,
            "min_accuracy": PROMOTION_MIN_ACCURACY,
        },
    }
