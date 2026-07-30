"""The Cost Meter — the Milo lesson instrumented.

Holds the per-family spend meter to the honesty bar: real usage only (the
deterministic pipeline is free and reads as free), estimates labeled as
estimates, and no monthly projection until a full week has been observed.
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from exhale.api import app
from exhale.costs import (
    MAX_USAGE_ENTRIES,
    build_cost_meter,
    estimate_cost_usd,
    metering,
    note_usage,
    record_llm_use,
)
from exhale.store import HouseholdStore

client = TestClient(app)

NOW = datetime(2026, 7, 26, 12, 0)


# --- pricing ---------------------------------------------------------------------
def test_estimate_uses_model_family_rates():
    # Opus family: $5/MTok in, $25/MTok out.
    assert estimate_cost_usd("claude-opus-4-8", 1_000_000, 0) == 5.0
    assert estimate_cost_usd("claude-opus-4-8", 0, 1_000_000) == 25.0
    # Haiku: $1/$5. Fable: $10/$50.
    assert estimate_cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0
    assert estimate_cost_usd("claude-fable-5", 1_000_000, 0) == 10.0


def test_unknown_model_prices_like_opus_never_zero():
    assert estimate_cost_usd("some-future-model", 1_000_000, 0) == 5.0


def test_cache_tokens_priced_at_their_factors():
    # 1M cache-read on opus: 5.00 * 0.1 = 0.50; 1M cache-write: 5.00 * 1.25 = 6.25.
    assert estimate_cost_usd("claude-opus-4-8", 0, 0, cache_read_tokens=1_000_000) == 0.5
    assert estimate_cost_usd("claude-opus-4-8", 0, 0, cache_write_tokens=1_000_000) == 6.25


# --- the metering bridge ---------------------------------------------------------
def test_note_usage_outside_metering_is_a_silent_noop():
    note_usage("claude-opus-4-8", {"input_tokens": 100, "output_tokens": 50},
               purpose="email_extraction")  # must not raise, must not record


def test_metering_attributes_usage_to_the_family():
    store = HouseholdStore()
    with metering(store, "fam_meter"):
        note_usage("claude-opus-4-8",
                   {"input_tokens": 2000, "output_tokens": 300,
                    "cache_read_input_tokens": 500},
                   purpose="email_extraction")
    (entry,) = store.profile("fam_meter")["llm_usage"]
    assert entry["purpose"] == "email_extraction"
    assert entry["input_tokens"] == 2000
    assert entry["cache_read_tokens"] == 500
    assert entry["estimated_cost_usd"] > 0


def test_metering_scope_ends_with_the_block():
    store = HouseholdStore()
    with metering(store, "fam_scope"):
        pass
    note_usage("claude-opus-4-8", {"input_tokens": 10, "output_tokens": 10},
               purpose="photo")
    assert store.profile("fam_scope").get("llm_usage") is None or \
        store.profile("fam_scope").get("llm_usage") == []


def test_usage_log_is_capped():
    store = HouseholdStore()
    for i in range(MAX_USAGE_ENTRIES + 20):
        record_llm_use(store, "fam_cap", model="claude-opus-4-8", purpose="photo",
                       input_tokens=1, output_tokens=1)
    assert len(store.profile("fam_cap")["llm_usage"]) == MAX_USAGE_ENTRIES


# --- the meter -------------------------------------------------------------------
def _use(store, fam, *, days_ago, cost_tokens=(1000, 100), purpose="email_extraction"):
    record_llm_use(store, fam, model="claude-opus-4-8", purpose=purpose,
                   input_tokens=cost_tokens[0], output_tokens=cost_tokens[1],
                   at=NOW - timedelta(days=days_ago))


def test_meter_windows_the_week_and_keeps_all_time():
    store = HouseholdStore()
    _use(store, "fam", days_ago=1)
    _use(store, "fam", days_ago=2, purpose="photo")
    _use(store, "fam", days_ago=30)  # old — all-time only
    meter = build_cost_meter(store.profile("fam"), now=NOW)
    assert meter["week"]["calls"] == 2
    assert meter["all_time"]["calls"] == 3
    assert set(meter["week"]["by_purpose"]) == {"email_extraction", "photo"}
    assert "estimate" in meter["pricing_basis"]


def test_no_projection_until_a_full_week_observed():
    store = HouseholdStore()
    _use(store, "fam_young", days_ago=2)  # only 2 days of history
    meter = build_cost_meter(store.profile("fam_young"), now=NOW)
    assert meter["projected_monthly_usd"] is None
    assert meter["observed_days"] == 2


def test_projection_appears_after_a_week():
    store = HouseholdStore()
    _use(store, "fam_old", days_ago=10)   # history begins >7 days ago
    _use(store, "fam_old", days_ago=1)
    meter = build_cost_meter(store.profile("fam_old"), now=NOW)
    assert meter["projected_monthly_usd"] is not None
    # ~4.35 weeks/month over this week's spend.
    assert meter["projected_monthly_usd"] >= meter["week"]["estimated_cost_usd"]


def test_zero_usage_reads_as_zero():
    meter = build_cost_meter({}, now=NOW)
    assert meter["week"]["calls"] == 0
    assert meter["all_time"]["estimated_cost_usd"] == 0
    assert meter["projected_monthly_usd"] is None


# --- API -------------------------------------------------------------------------
def test_costs_endpoint_cold_family():
    meter = client.get("/v1/families/fam_costs_cold/costs").json()
    assert meter["view"] == "cost_meter"
    assert meter["week"]["calls"] == 0
