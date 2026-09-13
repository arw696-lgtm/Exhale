"""A reply is not a source.

Two of the four obligations on a real household's Calendar were threads:
"Re: Around the World - ISLA Summer Camp" (a reply about a camp already dealt
with) and "Following Up - Meeting on 6/30 Regarding 8811 Nicollet Ave S" (a
realtor nudging an adult, not household logistics at all). Both had committed,
both carried a deadline, and both were still shouting weeks later.

The rule mirrors :func:`is_transactional_notice`: held for a human, never
rejected. A reply really can carry the only statement of a new date, so the
cost of a false positive is one confirmation tap — against a permanent
fabricated obligation for a false negative.
"""

import pytest

from exhale.relevance import is_conversational_thread
from exhale.routing import RecordStatus, route_extraction
from exhale.schemas import ArtifactTier, ExtractionPayload, FactOrigin


@pytest.mark.parametrize(
    "title",
    [
        "Re: Around the World - ISLA Summer Camp",
        "RE: Picture day",
        "re:picture day",
        "Fwd: Soccer schedule",
        "FW: Field trip",
        "Following Up - Meeting on 6/30 Regarding 8811 Nicollet Ave S",
        "Following up on your inquiry",
        "Follow-up: kitchen quote",
        "Checking in about the deck",
        "Circling back on pricing",
        "Quick question about the listing",
    ],
)
def test_threads_are_recognised(title):
    assert is_conversational_thread(title)


@pytest.mark.parametrize(
    "title",
    [
        # The words are only evidence when they open the title.
        "Registration for the reading program",
        "Renew Stevie's swim membership",
        "Soccer practice - Foxes (Purple)",
        "Dentist appointment for Stevie",
        "Permission slip due Friday",
        # "re" inside a word, and the real word it gets truncated from
        "Pre: K orientation",
        "Regarding the school photo order",
        "Retainer check for the orthodontist",
        # A real obligation that happens to mention following up later on
        "Sign the form, then we are following up with the nurse",
    ],
)
def test_real_obligations_are_not_mistaken_for_threads(title):
    assert not is_conversational_thread(title)


def test_empty_input_is_not_a_thread():
    assert not is_conversational_thread(None)
    assert not is_conversational_thread("")


def _payload(title):
    """A payload that would otherwise sail straight into the graph."""

    return ExtractionPayload(
        extracted_event=title,
        event_date="2026-10-02",
        deadline_date="2026-10-01",
        action_required=True,
        confidence_score=0.97,  # HIGH band
        artifact_tier=ArtifactTier.CONFIRMATION,
        event_date_origin=FactOrigin.OBSERVED,
    )


def test_a_thread_is_held_not_committed():
    decision = route_extraction(_payload("Re: Around the World - ISLA Summer Camp"))

    assert decision.status is RecordStatus.PENDING_VERIFICATION
    assert decision.commits_to_graph is False
    assert decision.requires_user_review is True


def test_a_thread_is_never_rejected_outright():
    """It may hold the only statement of a real new date."""

    decision = route_extraction(_payload("Re: moving Stevie's lesson to Thursday"))

    assert decision.status is not RecordStatus.REJECTED


def test_an_equivalent_primary_artifact_still_commits():
    """Guard the guard: the hold must come from the thread, not the payload."""

    decision = route_extraction(_payload("Return Stevie's camp permission slip"))

    assert decision.status is RecordStatus.COMMITTED
    assert decision.commits_to_graph is True


def test_threads_never_teach_a_rhythm():
    """Replies cluster on one stem and recur on whatever day people answer mail."""

    from exhale.memory import learn_rules
    from exhale.store import HouseholdStore

    store = HouseholdStore()
    fam = "fam_threads"
    for n, day in enumerate(("2026-03-02", "2026-04-06", "2026-05-04", "2026-06-01")):
        store.ingest(
            fam,
            ExtractionPayload(
                extracted_event="Re: Around the World - ISLA Summer Camp",
                event_date=day,
                action_required=True,
                confidence_score=0.95,
                artifact_tier=ArtifactTier.CONFIRMATION,
                event_date_origin=FactOrigin.OBSERVED,
                source_reference=f"gmail_thread_{n}",
            ),
        )

    rules = learn_rules(store.ledger(fam))

    assert rules == [], f"a reply thread taught a rhythm: {rules}"
