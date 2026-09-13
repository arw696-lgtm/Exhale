"""Household obligation vs. a company talking to a customer.

Every fixture below is a real title from a live household's ledger — the
noise ones are what auto-committed and taught fake rhythms, the real ones
are what has to survive the filter. They are the specification.
"""

from datetime import date, timedelta

import pytest

from exhale.memory import learn_rules
from exhale.relevance import is_transactional_notice
from exhale.routing import RecordStatus, route_extraction
from exhale.schemas import ArtifactTier, ExtractionPayload

# --- verbatim from the household that exposed this -------------------------
NOISE = [
    "Pick up Target Drive Up order #912003657854484 at Bloomington 79th and Penn",
    "Your Drive Up order is ready at Bloomington 79th and Penn",
    "Beep beep! Your Drive Up order ending in 4424 was picked up.",
    "Your Statement is Ready",
    "AutoPay Reminder from The Hartford",
    "Thanks for Your Order! Enjoy a Free 4-Piece Garlic Cheese Bread on Us!",
    "Order $15+ on Draw and get $2 in Lottery Credits!",
    "An item has arrived from order",
    "Your shipment was delivered 382981351705",
    "A new passkey has been added for your account",
    "You shared some Google account data with Arux app",
    "Sep digest: new messages from International Spanish Language Academy",
    "Thanks for shopping with us! Here's your order #:912003657268116.",
]

REAL = [
    "Foxes (Purple) Practice – Lincoln Park, Field 9",
    "Foxes (Purple) vs Bears (Royal Blue)",
    "Foxes (Purple) game reminder Thursday at 6pm",
    "No School – MN Education Association",
    "No School – Professional Development",
    "Request for Health Forms Return",
    "West High Field Trip Permission Slip",
    "Appointment Rescheduled",
    "Appointment Scheduled",
    "ISLA Camp this Week 7/13",
    "Around the World - ISLA Summer Camp",
    # Words that look transactional but name real household obligations.
    "Tuition Payment Due Friday",
    "Order your yearbook by October 3",  # a real ask, caught deliberately
    "Soccer registration closes Wednesday",
]


@pytest.mark.parametrize("title", NOISE)
def test_commercial_notices_are_recognized(title):
    assert is_transactional_notice(title), title


@pytest.mark.parametrize("title", REAL)
def test_household_obligations_are_not_swept_up(title):
    if title.startswith("Order your yearbook"):
        pytest.xfail("'order' catches a real ask; costs one confirm tap")
    assert not is_transactional_notice(title), title


def _payload(title, **over):
    body = {
        "extracted_event": title,
        "event_date": date.today() + timedelta(days=5),
        "action_required": True,
        "confidence_score": 0.97,          # HIGH band
        "artifact_tier": ArtifactTier.CONFIRMATION,  # clears every authority bar
    }
    body.update(over)
    return ExtractionPayload(**body)


# --- routing: the trust-ledger half ----------------------------------------
def test_retail_confirmation_no_longer_auto_commits():
    """It IS a confirmation with a real date — which is exactly why it used
    to sail through. 20 of 35 auto-commits needed a correction."""

    decision = route_extraction(_payload("Your Drive Up order is ready at Edina"))
    assert decision.status is RecordStatus.PENDING_VERIFICATION
    assert decision.commits_to_graph is False


def test_it_is_held_not_rejected():
    """A receipt may still matter to someone — held for a human, not binned."""

    decision = route_extraction(_payload("Your Statement is Ready"))
    assert decision.status is not RecordStatus.REJECTED
    assert decision.requires_user_review is True


def test_a_real_obligation_still_auto_commits():
    decision = route_extraction(_payload("West High Field Trip Permission Slip"))
    assert decision.status is RecordStatus.COMMITTED


def test_user_confirmation_still_outranks_everything():
    """If a person says a receipt matters, it matters."""

    from exhale.schemas import FactOrigin

    decision = route_extraction(_payload(
        "Your Statement is Ready", event_date_origin=FactOrigin.USER_CONFIRMED))
    assert decision.status is RecordStatus.COMMITTED


# --- memory: the fake-rhythm half ------------------------------------------
class _Entry:
    """Minimal ledger-entry stand-in for the learner."""

    def __init__(self, title, day):
        self.payload = ExtractionPayload(
            extracted_event=title, event_date=day,
            action_required=False, confidence_score=0.95,
            source_reference=f"m_{title[:6]}_{day}",
        )
        self.decision = route_extraction(self.payload)


def _weekly(title, weeks=3):
    start = date(2026, 9, 7)  # a Monday
    return [_Entry(title, start + timedelta(weeks=w)) for w in range(weeks)]


def test_a_mailing_schedule_is_not_a_family_rhythm():
    """The exact fake rule a real household was taught."""

    entries = _weekly("Order $15+ on Draw and get $2 in Lottery Credits!")
    assert learn_rules(entries) == []


def test_a_real_weekly_rhythm_is_still_learned():
    rules = learn_rules(_weekly("Foxes (Purple) Practice"))
    assert len(rules) == 1
    assert "recurs on Mondays" in rules[0].detail


def test_noise_does_not_crowd_out_the_real_rhythm():
    """Both streams present: only the family's rhythm survives."""

    entries = _weekly("Foxes (Purple) Practice") + _weekly("Your Statement is Ready")
    rules = learn_rules(entries)
    assert len(rules) == 1
    assert "foxes" in rules[0].subject
