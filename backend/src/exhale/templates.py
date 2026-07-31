"""Copywriting Engine — system message templates (Blueprint §10).

Pure, deterministic render functions for the three template families in §10.
Each returns the fully-interpolated copy string; the Action engine (§6) decides
*which* template fires for a given obligation and supplies the values.

Keeping these as plain functions (no I/O, no state) makes the exact wording
testable and keeps the brand voice in one place.
"""

from __future__ import annotations

from datetime import date


def _fmt_date(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def critical_deadline_alarm(
    *,
    parent_first_name: str,
    extracted_event: str,
    target_person_name: str | None,
    deadline_date: date | str,
    source_document_name: str | None = None,
    source_document_date: date | str | None = None,
    is_tomorrow: bool = False,
    has_reply_draft: bool = False,
) -> str:
    """§10.1 — Critical Deadline Alarm (PUSH / immediate app-tray launch view).

    ``has_reply_draft`` gates every send-shaped claim: the copy may only
    promise a ready reply when the action engine actually rendered one.
    """

    who = target_person_name or "your household"
    deadline = _fmt_date(deadline_date) + (" (Tomorrow)" if is_tomorrow else "")
    lines = [
        "[🚨 CRITICAL THREAT]",
        f"Hey {parent_first_name}, the Forgetting Engine™ caught an upcoming deadline.",
        f"• What: {extracted_event}",
        f"• Who: {who}",
        f"• Deadline: {deadline}",
    ]
    if source_document_name:
        provenance = f"We parsed this directly from the {source_document_name}"
        if source_document_date:
            provenance += f" sent on {_fmt_date(source_document_date)}"
        if has_reply_draft:
            provenance += ". Your reply is drafted below — review it, then send it from your own mail app."
        else:
            provenance += "."
        lines.append(provenance)
    lines.append("[👉 Review & Send Reply]" if has_reply_draft else "[👉 Review & Mark Handled]")
    return "\n".join(lines)


def dependency_gap_alarm(
    *,
    anchor_event_name: str,
    days_until_event: int,
    target_person_name: str | None,
    missing_item_name: str,
    confirmed_prerequisites: list[tuple[str, str]] | None = None,
    total_items_count: int | None = None,
) -> str:
    """§10.2 — Dependency System Alarm (mid-page element in the Sunday briefing).

    ``confirmed_prerequisites`` is a list of ``(name, verified_detail)`` pairs
    rendered as satisfied [✓] rows above the missing [!] item.
    """

    who = f" for {target_person_name}" if target_person_name else ""
    lines = [
        "[➔ DEPENDENCY GAP DETECTED]",
        f"{anchor_event_name} starts in {days_until_event} days{who}.",
        "While verifying your household status, Exhale found a missing dependency gap:",
    ]
    for name, detail in confirmed_prerequisites or []:
        lines.append(f"• [✓] {name}: Confirmed ({detail})")
    lines.append(f"• [!] {missing_item_name}: MISSING")
    if total_items_count is not None:
        lines.append(
            f"We located the correct list on the school portal. "
            f"There are {total_items_count} required tracking items."
        )
        lines.append(f"[🛒 Add all {total_items_count} items to Household Shopping Cart]")
    return "\n".join(lines)


def sign_form_reply(
    *,
    parent_name: str,
    target_person_name: str | None,
    obligation_name: str,
    deadline_date: date | str | None = None,
) -> str:
    """§10.4 — the actual outbound reply for a signature-type obligation.

    This is the text that leaves the household, so it is written in the
    parent's voice, states only what the parent is affirming, and asks —
    never assumes — whether a paper form is still required. Exhale writes
    it; the human reads, edits, and presses send from their own mail app.
    """

    who = target_person_name or "our child"
    lines = [
        "Hi,",
        "",
        f"{who} has my permission for the {obligation_name.rstrip('.')}."
        " Please accept this email as my sign-off.",
    ]
    if deadline_date:
        lines.append(
            f"I understand the deadline is {_fmt_date(deadline_date)} — "
            "if a printed or signed paper copy is still required, let me know "
            "and I'll send it in."
        )
    else:
        lines.append(
            "If a printed or signed paper copy is still required, let me know "
            "and I'll send it in."
        )
    lines += ["", "Thank you,", parent_name]
    return "\n".join(lines)


def value_realization_summary(
    *,
    total_active_nodes: int,
    saved_surprises_count: int,
    saved_events: list[tuple[str, str]],
    horizon_day_increase: int,
) -> str:
    """§10.3 — Value Realization Summary (monthly retention email report card).

    ``saved_events`` is a list of ``(deadline_date, description)`` pairs.
    """

    lines = [
        "[🛡️ MONTHLY HOUSEHOLD PROTECTION REPORT]",
        f"This month, Exhale actively managed {total_active_nodes} nodes in your "
        "Household Graph.",
        f"The Forgetting Engine™ successfully intercepted {saved_surprises_count} "
        "logistics oversights before they caused a disruption:",
    ]
    for when, description in saved_events:
        lines.append(f"• Intercepted {_fmt_date(when)}: {description}")
    lines.append(
        f"Your Household Planning Horizon has successfully expanded by "
        f"{horizon_day_increase} days compared to last month. "
        "Take a deep breath—your memory systems are secure."
    )
    return "\n".join(lines)
