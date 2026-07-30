"""The Cost Meter — what does running Exhale for this family actually cost?

The Milo lesson (strategy brief, mid-2026): the AI-copilot that shut down died
in part because the cost of serving one user quietly exceeded what that user
would pay — and they found out too late. This module is the instrument that
makes sure Exhale always knows which side of that line it's on: every LLM call
is recorded per family, priced with rough planning rates, and rolled up into a
weekly meter with a monthly projection.

Design constraints:

* **Zero plumbing through the pipeline.** Extractors don't know families; the
  API layer does. A context-variable meter bridges them: the API wraps LLM-using
  work in :func:`metering`, and the extractors call :func:`note_usage` after
  each call. Outside a metering block, ``note_usage`` is a silent no-op — the
  pipeline never breaks because accounting isn't set up (tests, scripts).
* **Estimates say so.** Prices are planning numbers (per-MTok, as of mid-2026),
  not an invoice; the payload is labeled ``estimated``. The token counts are
  exact — they come from the API's own usage block.
* **Deterministic-first stays visible.** Most extractions never touch the API
  (the hybrid engine's HIGH band is free); the meter only ever records real
  calls, so a cheap week honestly reads as cheap.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta

# Rough planning rates in USD per million tokens (input, output), mid-2026.
# Prefix-matched so dated variants of a model price like their family.
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus": (5.00, 25.00),      # opus-5 / 4.8 / 4.7 / 4.6
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (1.00, 5.00),
}
_FALLBACK_RATE = (5.00, 25.00)  # unknown model → price like Opus, never $0

# Cache reads bill ~0.1x input; cache writes ~1.25x. Kept as coefficients so
# the estimate tracks the real bill shape without a second price table.
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25

MAX_USAGE_ENTRIES = 500
METER_DAYS = 7
# Weeks per month for the projection (365.25 / 12 / 7).
WEEKS_PER_MONTH = 4.348

_active_meter: ContextVar = ContextVar("exhale_cost_meter", default=None)


def _rate_for(model: str) -> tuple[float, float]:
    for prefix, rate in PRICING.items():
        if model.startswith(prefix):
            return rate
    return _FALLBACK_RATE


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """A planning estimate for one call, in dollars."""

    in_rate, out_rate = _rate_for(model)
    cost = (
        input_tokens * in_rate
        + output_tokens * out_rate
        + cache_read_tokens * in_rate * CACHE_READ_FACTOR
        + cache_write_tokens * in_rate * CACHE_WRITE_FACTOR
    ) / 1_000_000
    return round(cost, 6)


# -- the bridge: extractors report, the API layer attributes ----------------------
def note_usage(model: str, usage, *, purpose: str) -> None:
    """Report one LLM call's usage (called from extraction engines).

    ``usage`` is the SDK response's usage object (or any object/dict carrying
    ``input_tokens`` / ``output_tokens``). No-op unless a meter is active.
    """

    meter = _active_meter.get()
    if meter is None:
        return

    def _field(name: str) -> int:
        if isinstance(usage, dict):
            return int(usage.get(name) or 0)
        return int(getattr(usage, name, 0) or 0)

    meter(
        model=model,
        purpose=purpose,
        input_tokens=_field("input_tokens"),
        output_tokens=_field("output_tokens"),
        cache_read_tokens=_field("cache_read_input_tokens"),
        cache_write_tokens=_field("cache_creation_input_tokens"),
    )


@contextmanager
def metering(store, family_id: str):
    """Attribute every :func:`note_usage` inside the block to this family."""

    def _record(**kw) -> None:
        record_llm_use(store, family_id, **kw)

    token = _active_meter.set(_record)
    try:
        yield
    finally:
        _active_meter.reset(token)


def record_llm_use(
    store,
    family_id: str,
    *,
    model: str,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    at: datetime | None = None,
) -> dict:
    """Append one call to the family's usage log (capped)."""

    entry = {
        "at": (at or datetime.now()).isoformat(),
        "model": model,
        "purpose": purpose,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "estimated_cost_usd": estimate_cost_usd(
            model, input_tokens, output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        ),
    }
    with store.family_lock(family_id):  # RMW must not race a concurrent writer
        entries = list(store.profile(family_id).get("llm_usage") or [])
        entries.append(entry)
        store.set_profile(family_id, llm_usage=entries[-MAX_USAGE_ENTRIES:])
    return entry


# -- the meter --------------------------------------------------------------------
def build_cost_meter(profile: dict, *, now: datetime | None = None) -> dict:
    """The per-family cost meter: this week, all time, and a monthly projection.

    ``projected_monthly_usd`` is the Milo question made a number: at this week's
    pace, what does this household cost per month? ``None`` until a full week of
    observation exists — a two-day-old family extrapolated to a month would be a
    guess, and guesses are banned here too.
    """

    now = now or datetime.now()
    cutoff = now - timedelta(days=METER_DAYS)
    entries = list(profile.get("llm_usage") or [])

    week: list[dict] = []
    first_seen: datetime | None = None
    for e in entries:
        try:
            at = datetime.fromisoformat(e["at"])
        except (KeyError, ValueError):
            continue
        if at.tzinfo is not None:
            at = at.replace(tzinfo=None)
        if first_seen is None or at < first_seen:
            first_seen = at
        if at >= cutoff:
            week.append(e)

    week_summary = _summarize(week)
    observed_days = (now - first_seen).days if first_seen else 0
    projected = (
        round(week_summary["estimated_cost_usd"] * WEEKS_PER_MONTH, 2)
        if observed_days >= METER_DAYS
        else None
    )

    return {
        "view": "cost_meter",
        "pricing_basis": "planning estimates, mid-2026 per-MTok rates",
        "week": week_summary,
        "all_time": _summarize(entries),
        "projected_monthly_usd": projected,
        "observed_days": observed_days,
    }


def _summarize(entries: list[dict]) -> dict:
    by_purpose: dict[str, dict] = {}
    total_in = total_out = 0
    total_cost = 0.0
    for e in entries:
        total_in += int(e.get("input_tokens") or 0)
        total_out += int(e.get("output_tokens") or 0)
        total_cost += float(e.get("estimated_cost_usd") or 0.0)
        p = by_purpose.setdefault(
            e.get("purpose", "unknown"), {"calls": 0, "estimated_cost_usd": 0.0})
        p["calls"] += 1
        p["estimated_cost_usd"] = round(p["estimated_cost_usd"] + float(e.get("estimated_cost_usd") or 0.0), 6)
    return {
        "calls": len(entries),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "estimated_cost_usd": round(total_cost, 6),
        "by_purpose": by_purpose,
    }
