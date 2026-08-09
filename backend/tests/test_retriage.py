"""Tests for the review-queue second-opinion sweep.

The load-bearing rule is the autonomy posture: the machine may only take junk
OFF the pile — every uncertain path (LLM down, unfetchable source, no LLM at
all) must leave items held for the human yes.
"""

from datetime import date, datetime, timedelta, timezone

from exhale.connectors.base import RawMessage
from exhale.retriage import STALE_DAYS, second_opinion_sweep
from exhale.routing import RecordStatus
from exhale.schemas import ExtractionPayload
from exhale.store import HouseholdStore

NOW = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)
FAM = "fam_retriage"


def _held(store, family_id, *, title, event_date, deadline=None, ref="msg_x"):
    """Ingest a payload that routes to PENDING_VERIFICATION; return its id."""

    entry = store.ingest(family_id, ExtractionPayload(
        extracted_event=title,
        event_date=event_date,
        deadline_date=deadline,
        action_required=False,
        confidence_score=0.75,  # MEDIUM band → held
        source_reference=ref,
        source_document_name=title,
    ))
    assert entry.decision.status is RecordStatus.PENDING_VERIFICATION
    return entry.extraction_id


def _raw(ref="msg_x", subject="x"):
    return RawMessage(source_id=ref, channel="fixture", subject=subject,
                      body="body", received_at=NOW)


class _LLM:
    """Scripted second reader: judgments[ref] = payload | None."""

    def __init__(self, judgments):
        self.judgments = judgments
        self.reads = []

    def extract(self, raw, ctx=None):
        self.reads.append(raw.source_id)
        return self.judgments.get(raw.source_id)


def _queue_ids(store, family_id):
    dismissed = set(store.profile(family_id).get("dismissed_extractions") or [])
    return {e.extraction_id for e in store.ledger(family_id)
            if e.decision.status is RecordStatus.PENDING_VERIFICATION
            and e.extraction_id not in dismissed}


def test_stale_items_dismissed_without_llm():
    """1974: Nixon announces he will resign — the moment has passed."""

    store = HouseholdStore()
    nixon = _held(store, FAM, title="Nixon resigns", event_date=date(1974, 8, 8))
    fresh = _held(store, FAM, title="Health forms", event_date=NOW.date(), ref="msg_f")

    report = second_opinion_sweep(store, FAM, now=NOW)
    assert report["stale"] == 1
    assert nixon not in _queue_ids(store, FAM)
    assert fresh in _queue_ids(store, FAM)  # no LLM → stays held
    reasons = store.profile(FAM).get("retriage_reasons")
    assert reasons[nixon] == "moment passed"


def test_stale_uses_the_latest_of_event_and_deadline():
    """A past event date with a future deadline is still actionable."""

    store = HouseholdStore()
    live = _held(store, FAM, title="Forms", event_date=NOW.date() - timedelta(days=40),
                 deadline=NOW.date() + timedelta(days=3))
    second_opinion_sweep(store, FAM, now=NOW)
    assert live in _queue_ids(store, FAM)


def test_llm_noise_verdict_dismisses_with_reason():
    store = HouseholdStore()
    junk = _held(store, FAM, title="Free garlic bread!", event_date=NOW.date(),
                 ref="msg_junk")
    llm = _LLM({"msg_junk": None})  # not a household obligation

    report = second_opinion_sweep(
        store, FAM, llm=llm, now=NOW,
        fetch_message=lambda ref: _raw(subject="Free garlic bread!"),
    )
    assert report["noise"] == 1
    assert junk not in _queue_ids(store, FAM)
    reasons = store.profile(FAM).get("retriage_reasons")
    assert "second opinion" in reasons[junk]


def test_llm_real_verdict_keeps_item_held_never_promotes():
    """The machine never confirms — a real item still waits for the human."""

    store = HouseholdStore()
    real = _held(store, FAM, title="Health forms return", event_date=NOW.date(),
                 ref="msg_real")
    payload = ExtractionPayload(
        extracted_event="Health forms return", event_date=NOW.date(),
        action_required=True, confidence_score=0.95,
    )
    llm = _LLM({"msg_real": payload})

    report = second_opinion_sweep(store, FAM, llm=llm, now=NOW,
                                  fetch_message=lambda ref: _raw(ref))
    assert report["kept_held"] == 1
    assert real in _queue_ids(store, FAM)
    # And nothing new committed: confirming stayed a person's job.
    committed = [e for e in store.ledger(FAM)
                 if e.decision.status is RecordStatus.COMMITTED]
    assert committed == []


def test_each_item_gets_one_second_read_not_one_per_cycle():
    store = HouseholdStore()
    _held(store, FAM, title="Ambiguous", event_date=NOW.date(), ref="msg_a")
    payload = ExtractionPayload(extracted_event="Ambiguous", event_date=NOW.date(),
                                action_required=False, confidence_score=0.9)
    llm = _LLM({"msg_a": payload})

    second_opinion_sweep(store, FAM, llm=llm, now=NOW, fetch_message=lambda r: _raw(r))
    second_opinion_sweep(store, FAM, llm=llm, now=NOW, fetch_message=lambda r: _raw(r))
    assert len(llm.reads) == 1  # hourly cycles must not re-bill the same item


def test_llm_failure_keeps_item_held_and_retries_later():
    store = HouseholdStore()
    item = _held(store, FAM, title="Camp email", event_date=NOW.date(), ref="msg_c")

    class _DownLLM:
        def extract(self, raw, ctx=None):
            raise RuntimeError("api down")

    second_opinion_sweep(store, FAM, llm=_DownLLM(), now=NOW,
                         fetch_message=lambda r: _raw(r))
    assert item in _queue_ids(store, FAM)
    # Not marked seen — the next sweep may try again.
    assert item not in set(store.profile(FAM).get("retriage_seen") or [])


def test_unfetchable_source_stays_held_but_is_not_retried():
    store = HouseholdStore()
    item = _held(store, FAM, title="Photo item", event_date=NOW.date(), ref="photo_1")
    llm = _LLM({})

    second_opinion_sweep(store, FAM, llm=llm, now=NOW, fetch_message=lambda r: None)
    assert item in _queue_ids(store, FAM)
    assert item in set(store.profile(FAM).get("retriage_seen") or [])
    assert llm.reads == []


def test_dismissal_is_signal_not_erasure():
    """The ledger row survives; only the queue membership changes."""

    store = HouseholdStore()
    junk = _held(store, FAM, title="Lottery credits", event_date=NOW.date(),
                 ref="msg_l")
    llm = _LLM({"msg_l": None})
    second_opinion_sweep(store, FAM, llm=llm, now=NOW, fetch_message=lambda r: _raw(r))
    assert any(e.extraction_id == junk for e in store.ledger(FAM))
