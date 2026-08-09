"""Tests for the household concierge.

The load-bearing rules: it answers from the snapshot only, and it proposes
without ever enacting. A household assistant that confabulates a pickup time
is worse than one that says "I don't know."
"""

from datetime import datetime, timedelta, timezone

import pytest

from exhale.concierge import ask, build_snapshot

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)


def _briefing(**over):
    body = {
        "critical_threats": [
            {"title": "Health forms return", "person": "Steve",
             "deadline": "2026-08-14", "risk_score": 0.91,
             "threat_level": "CRITICAL"},
        ],
        "dependency_watch": [],
        "care_watch": {"gaps": [
            {"recipient": "Steve", "start": "2026-08-13T15:15:00",
             "end": "2026-08-13T17:00:00", "reason": "no school that day",
             "threat_level": "CRITICAL"},
        ]},
        "waiting_on": {"items": []},
        "away": None,
    }
    body.update(over)
    return body


def _windows():
    start = NOW + timedelta(days=1, hours=4)
    return {"windows": [
        {"caregiver": "Andy", "start": start.isoformat(),
         "end": (start + timedelta(hours=3)).isoformat(), "duration_hours": 3.0},
    ]}


class _Model:
    """Scripted structured-output client."""

    def __init__(self, reply="ok", proposal=None, boom=False):
        self._reply, self._proposal, self._boom = reply, proposal, boom
        self.seen = {}
        self.messages = self

    def parse(self, **kwargs):
        if self._boom:
            raise RuntimeError("api down")
        self.seen = kwargs
        reply, proposal = self._reply, self._proposal

        class _Out:
            parsed_output = type("P", (), {
                "reply": reply,
                "proposal": (type("Q", (), proposal)() if proposal else None),
            })()
            usage = {}

        return _Out()


# --- the snapshot ------------------------------------------------------------
def test_snapshot_carries_real_state_only():
    snap = build_snapshot(briefing=_briefing(), tasks=[{"description": "Mow"}],
                          work_windows=_windows(), now=NOW)
    assert snap["needs_you"][0]["title"] == "Health forms return"
    assert snap["coverage_gaps"][0]["who"] == "Steve"
    assert snap["open_tasks"] == ["Mow"]
    assert snap["open_windows"][0]["hours"] == 3.0
    # Internal scoring never leaks into the assistant's context.
    assert "risk_score" not in snap["needs_you"][0]
    assert "threat_level" not in snap["needs_you"][0]


def test_snapshot_of_empty_household_is_still_valid():
    snap = build_snapshot(briefing=None, now=NOW)
    assert snap["needs_you"] == [] and snap["coverage_gaps"] == []
    assert snap["today"] == NOW.date().isoformat()


def test_snapshot_includes_away():
    snap = build_snapshot(briefing=_briefing(away={"label": "Portland"}), now=NOW)
    assert snap["away"]["label"] == "Portland"


# --- answering ---------------------------------------------------------------
def test_question_and_snapshot_reach_the_model():
    client = _Model(reply="You've got Tuesday afternoon free.")
    out = ask("when am I free?", build_snapshot(briefing=_briefing(),
                                                work_windows=_windows(), now=NOW),
              client=client)
    assert out.reply == "You've got Tuesday afternoon free."
    sent = client.seen["messages"][-1]["content"]
    assert "when am I free?" in sent
    assert "Health forms return" in sent  # grounded in real state


def test_empty_question_answers_without_calling_the_model():
    client = _Model(boom=True)  # would raise if called
    out = ask("   ", {}, client=client)
    assert "Ask me anything" in out.reply


def test_model_failure_raises_for_the_caller_to_degrade():
    with pytest.raises(RuntimeError):
        ask("anything", {}, client=_Model(boom=True))


# --- proposals: select, never invent ----------------------------------------
def test_proposal_matching_an_open_window_is_kept():
    windows = _windows()
    start = windows["windows"][0]["start"]
    client = _Model(
        reply="Thursday at 1 works — want me to hold it?",
        proposal={"title": "Dentist", "start": start, "end": windows["windows"][0]["end"]},
    )
    out = ask("find me a dentist slot",
              build_snapshot(briefing=_briefing(), work_windows=windows, now=NOW),
              client=client)
    assert out.proposal["title"] == "Dentist"
    assert out.proposal["start"] == start


def test_invented_time_outside_the_open_windows_is_dropped():
    """The model may select free time; it may not manufacture it."""

    client = _Model(
        reply="How about 3am Sunday?",
        proposal={"title": "Dentist", "start": "2026-08-16T03:00:00",
                  "end": "2026-08-16T04:00:00"},
    )
    out = ask("find me a time",
              build_snapshot(briefing=_briefing(), work_windows=_windows(), now=NOW),
              client=client)
    assert out.reply  # the words still come through
    assert out.proposal is None  # the fabricated hold does not


def test_no_proposal_when_the_model_offers_none():
    out = ask("what needs me?", build_snapshot(briefing=_briefing(), now=NOW),
              client=_Model(reply="Steve's health forms are due Friday."))
    assert out.proposal is None
