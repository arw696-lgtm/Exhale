import React, { useCallback, useEffect, useState } from "react";
import {
  addAwayPeriod,
  dismissTripSuggestion,
  fetchAway,
  removeAwayPeriod,
} from "../data/api.js";

/**
 * Away — vacation mode ("we're together, elsewhere").
 *
 * While a period is active: supervision gaps stop being computed from the
 * normal weekly rhythm, weekly contributions pause, and the glance + family
 * feed say the family is away. Deadlines still stand — a form due mid-trip
 * is still due, and being away is when it's easiest to forget.
 */
function prettyRange(p) {
  const opts = { month: "short", day: "numeric" };
  const from = new Date(`${p.start}T00:00:00`).toLocaleDateString(undefined, opts);
  const to = new Date(`${p.end}T00:00:00`).toLocaleDateString(undefined, opts);
  return from === to ? from : `${from} – ${to}`;
}

export default function AwayPanel({ familyId, onChanged }) {
  const [periods, setPeriods] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [label, setLabel] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    const data = await fetchAway(familyId);
    setPeriods(data?.away_periods ?? null);
    setSuggestions(data?.trip_suggestions ?? []);
  }, [familyId]);

  useEffect(() => {
    load();
  }, [load]);

  if (periods === null) return null; // offline/anon — no empty shell

  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    if (!start || !end) return;
    setBusy(true);
    setError(null);
    try {
      await addAwayPeriod(label.trim() || "Away", start, end, familyId);
      setLabel("");
      setStart("");
      setEnd("");
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (awayId) => {
    setBusy(true);
    try {
      await removeAwayPeriod(awayId, familyId);
      await load();
      onChanged?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          ✈️ Away
        </h2>
      </header>

      <p className="mb-3 font-micro text-sm text-sanctuary-navy/60">
        Tell Exhale when the family's away together. Coverage stops asking who's
        watching the kids, weekly contributions pause, and the calendar feed
        shows the trip. Deadlines still stand — that's when they're easiest to
        forget.
      </p>

      {/* Trips Exhale thinks it sees — clustered bookings, one tap to declare.
          Suggestion, never enactment: nothing suppresses until a human says so. */}
      {suggestions.map((s) => (
        <div
          key={s.trip_id}
          className="mb-3 rounded-2xl border border-sage-release/30 bg-sage-release/8 p-4"
        >
          <p className="font-micro text-sm text-sanctuary-navy/85">
            ✈️ Looks like a trip:{" "}
            <span className="font-semibold">{prettyRange(s)}</span>
            <span className="text-sanctuary-navy/55">
              {" "}— {s.artifact_count} travel booking{s.artifact_count === 1 ? "" : "s"}
            </span>
          </p>
          <p className="mt-1 font-micro text-xs text-sanctuary-navy/50">
            {s.artifacts.slice(0, 3).join(" · ")}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() =>
                act(async () => {
                  await addAwayPeriod("Trip", s.start, s.end, familyId);
                })
              }
              disabled={busy}
              className="rounded-full border border-sage-release/40 bg-sage-release/15 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/25 disabled:opacity-50"
            >
              We'll be away — turn it on
            </button>
            <button
              onClick={() =>
                act(async () => {
                  await dismissTripSuggestion(s.trip_id, familyId);
                })
              }
              disabled={busy}
              className="rounded-full border border-sanctuary-navy/15 px-4 py-1.5 font-micro text-sm text-sanctuary-navy transition hover:bg-pure-breath disabled:opacity-50"
            >
              Not a trip
            </button>
          </div>
        </div>
      ))}

      {periods.length > 0 && (
        <ul className="mb-4 space-y-2">
          {periods.map((p) => (
            <li
              key={p.away_id}
              className="flex items-center justify-between gap-3 rounded-2xl bg-sage-release/10 px-4 py-2.5"
            >
              <span className="min-w-0 font-micro text-sm text-sanctuary-navy/85">
                <span className="font-semibold">{p.label}</span>
                <span className="ml-2 text-sanctuary-navy/55">{prettyRange(p)}</span>
              </span>
              <button
                onClick={() => remove(p.away_id)}
                disabled={busy}
                className="shrink-0 font-micro text-xs text-sanctuary-navy/45 underline-offset-2 hover:underline disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Where to? (optional)"
          className="min-w-0 flex-1 rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-2 font-micro text-sm text-sanctuary-navy placeholder:text-sanctuary-navy/35 focus:border-sage-release focus:outline-none"
        />
        <input
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          aria-label="First day away"
          className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-2 font-micro text-sm text-sanctuary-navy focus:border-sage-release focus:outline-none"
        />
        <span className="font-micro text-xs text-sanctuary-navy/45">to</span>
        <input
          type="date"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          aria-label="Last day away"
          className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-2 font-micro text-sm text-sanctuary-navy focus:border-sage-release focus:outline-none"
        />
        <button
          onClick={add}
          disabled={busy || !start || !end}
          className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-2 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
        >
          {busy ? "Saving…" : "Add"}
        </button>
      </div>
      {error && <p className="mt-2 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
