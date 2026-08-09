"""Ask Exhale — the household concierge.

A natural-language front door onto engines that already exist. "Do I have any
free time today?" is a work-windows query. "Can you find me a time for the
dentist?" is the same query plus a proposed hold. The value here is not new
intelligence; it is removing the requirement to know which screen holds the
answer.

Two rules shape the design:

**It answers from real state, never from memory of a conversation.** Every
reply is grounded in a snapshot assembled at question time — the week's open
items, coverage gaps, found windows, waiting threads, trips. The model is
told, explicitly, that anything not in the snapshot is something it does not
know. A household assistant that confabulates a pickup time is worse than one
that says "I don't know."

**It proposes; it never enacts.** A suggested time comes back as a
confirmable card carrying real start/end times — the same approval gate as
every other action in Exhale. The assistant cannot write to a calendar, mark
anything handled, or change the household. The tap is the approval, and the
tap belongs to a person.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from exhale.costs import note_usage

log = logging.getLogger("exhale.concierge")

DEFAULT_MODEL = "claude-opus-4-8"
MAX_QUESTION_CHARS = 500
MAX_HISTORY_TURNS = 6

_SYSTEM_PROMPT = """\
You are Exhale, a household assistant. You are speaking with an adult in the \
household about their family's real logistics.

You will be given a SNAPSHOT of the household's current state as JSON. That \
snapshot is the ONLY thing you know. Rules:

1. NEVER invent an event, deadline, person, time, or commitment that is not in \
the snapshot. If asked about something absent, say plainly that you don't see \
it — never guess or fill in a plausible answer.
2. When the snapshot has open windows and the person asks about free time, \
answer with the actual windows and their real times.
3. When they ask you to find time for something ("schedule my dentist", "when \
could I do X"), pick the best-fitting open window and PROPOSE it. Do not \
claim to have booked, scheduled, or added anything — you cannot. Say you can \
hold it if they confirm.
4. Speak plainly and warmly, like a capable person who knows the household. \
Two or three sentences is usually right. No bullet lists unless asked, no \
corporate cheer, no exclamation marks.
5. Never scold, never imply anyone is behind, never rank family members \
against each other, and never celebrate on a hard week.

Return JSON matching the given schema. Put your reply in `reply`. If (and \
only if) you are proposing a specific time block from an open window, fill \
`proposal` with its exact ISO start/end from the snapshot and a short title; \
otherwise leave `proposal` null."""


def _iso(value) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if value else None


def build_snapshot(
    *,
    briefing: dict | None,
    tasks: list[dict] | None = None,
    work_windows: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Assemble what the assistant is allowed to know.

    Deliberately compact and derived: names and times the household already
    sees on its own screens, nothing raw and nothing private beyond it.
    """

    now = now or datetime.now(timezone.utc)
    briefing = briefing or {}
    care = briefing.get("care_watch") or {}
    waiting = briefing.get("waiting_on") or {}

    def _item(i: dict) -> dict:
        return {k: i.get(k) for k in ("title", "person", "deadline") if i.get(k)}

    snapshot = {
        "today": now.date().isoformat(),
        "now": now.isoformat(),
        "needs_you": [_item(i) for i in (briefing.get("critical_threats") or [])],
        "watching": [_item(i) for i in (briefing.get("dependency_watch") or [])],
        "coverage_gaps": [
            {"who": g.get("recipient"), "start": g.get("start"), "end": g.get("end"),
             "why": g.get("reason")}
            for g in (care.get("gaps") or [])
        ],
        "waiting_on": [
            {"what": w.get("description") or w.get("title"), "with": w.get("with_whom")}
            for w in (waiting.get("items") or [])
        ],
        "open_tasks": [t.get("description") for t in (tasks or []) if t.get("description")],
        "away": briefing.get("away"),
    }
    if work_windows:
        snapshot["open_windows"] = [
            {"start": w.get("start"), "end": w.get("end"),
             "hours": w.get("duration_hours"), "for": w.get("caregiver")}
            for w in (work_windows.get("windows") or [])
        ]
    return snapshot


class _Reply:
    """Duck-typed container so callers get attribute access either way."""

    def __init__(self, reply: str, proposal: dict | None = None):
        self.reply = reply
        self.proposal = proposal


def _schema():
    from pydantic import BaseModel, Field

    class Proposal(BaseModel):
        title: str = Field(description="Short title for the time block.")
        start: str = Field(description="Exact ISO start copied from an open window.")
        end: str = Field(description="Exact ISO end for the block.")

    class ConciergeReply(BaseModel):
        reply: str = Field(description="What to say to the person, 2-3 sentences.")
        proposal: Proposal | None = Field(
            default=None,
            description="A time block to hold, ONLY when proposing a specific "
                        "time from an open window. Otherwise null.",
        )

    return ConciergeReply


def ask(
    question: str,
    snapshot: dict,
    *,
    history: list[dict] | None = None,
    client=None,
    model: str | None = None,
) -> _Reply:
    """Answer one question against the snapshot. Raises RuntimeError if the
    model is unreachable — the caller degrades, never fabricates."""

    question = (question or "").strip()[:MAX_QUESTION_CHARS]
    if not question:
        return _Reply("Ask me anything about the week — what needs you, when "
                      "you're free, who's covering what.")

    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    model = (model or os.environ.get("EXHALE_LLM_MODEL", "").strip()
             or DEFAULT_MODEL)

    messages = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        text = str(turn.get("text") or "")[:MAX_QUESTION_CHARS]
        if text:
            messages.append({"role": role, "content": text})
    messages.append({
        "role": "user",
        "content": f"HOUSEHOLD SNAPSHOT:\n{json.dumps(snapshot, default=str)}\n\n"
                   f"QUESTION: {question}",
    })

    try:
        response = client.messages.parse(
            model=model,
            max_tokens=2000,
            system=_SYSTEM_PROMPT,
            messages=messages,
            output_format=_schema(),
        )
    except Exception as exc:  # noqa: BLE001 — caller degrades gracefully
        raise RuntimeError(str(exc)) from exc

    note_usage(model, getattr(response, "usage", None) or {}, purpose="concierge")

    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError("no parsed output from the assistant")

    proposal = None
    if parsed.proposal is not None:
        proposal = {
            "title": parsed.proposal.title,
            "start": parsed.proposal.start,
            "end": parsed.proposal.end,
        }
        # A proposal must correspond to a real open window — the model is not
        # permitted to invent free time, only to select it.
        starts = {w.get("start") for w in (snapshot.get("open_windows") or [])}
        if proposal["start"] not in starts:
            log.warning("concierge proposed a time outside the open windows; dropping")
            proposal = None
    return _Reply(parsed.reply, proposal)
