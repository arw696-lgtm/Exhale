import React, { useState } from "react";
import { fetchWorkWindows, scheduleEvent } from "../data/api.js";

/**
 * Find Your Time — "when is my time actually mine this week?"
 *
 * The intent side of the coverage math: a caregiver's open windows are the
 * times they're free AND the children are covered by someone else. The math
 * is unchanged — only the framing: this is time back for work, a workout, or
 * a call you owe someone, not "schedule optimization."
 */
function fmt(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function fmtDay(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function dayPart(iso) {
  const d = new Date(iso);
  const day = d.toLocaleDateString(undefined, { weekday: "long" });
  const h = d.getHours();
  return `${day} ${h < 12 ? "morning" : h < 17 ? "afternoon" : "evening"}`;
}

const PROVIDER_LABEL = { google: "Google", microsoft: "Outlook", feed: "Exhale" };

export default function WorkWindowsPanel({ familyId }) {
  const [caregiver, setCaregiver] = useState("");
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [added, setAdded] = useState({}); // window start iso → provider it landed on

  const addToCalendar = async (w) => {
    setError(null);
    try {
      const result = await scheduleEvent(
        { title: `Protected time (Exhale)`, start: w.start, end: w.end,
          description: `Time that's yours — ${w.child_covered_by.join(", ")}. (Exhale)` },
        familyId
      );
      setAdded((a) => ({ ...a, [w.start]: result.provider }));
    } catch (err) {
      setError(err.message);
    }
  };

  const lookup = async (e) => {
    e.preventDefault();
    if (!caregiver.trim()) return;
    setBusy(true);
    setError(null);
    setPlan(null);
    try {
      setPlan(await fetchWorkWindows(caregiver.trim(), familyId));
    } catch (err) {
      setError(
        err.message.includes("No coverage model")
          ? "Set up the household's coverage model first."
          : err.message
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          ⏳ Find Your Time
        </h2>
      </header>

      <form onSubmit={lookup} className="flex gap-2">
        <input
          value={caregiver}
          onChange={(e) => setCaregiver(e.target.value)}
          placeholder="Your name (as in the household setup)"
          className="flex-1 rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-1.5 font-micro text-sm text-sanctuary-navy outline-none focus:border-sage-release"
        />
        <button
          type="submit"
          disabled={busy || !caregiver.trim()}
          className="whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
        >
          {busy ? "Looking…" : "Find my time"}
        </button>
      </form>

      {plan && (
        <div className="mt-4">
          {plan.windows.length === 0 ? (
            <p className="font-micro text-sm text-sanctuary-navy/60">
              Couldn't find you a clear stretch this week — every free moment,
              the kids need someone. Syncing more calendars sometimes surfaces
              time you can't see from here.
            </p>
          ) : (
            <ul className="space-y-2">
              {plan.windows.map((w) => (
                <li key={w.start} className="flex items-center justify-between gap-2 border-l-2 border-sage-release/60 pl-3 font-micro text-sm">
                  <span>
                    <span className="font-semibold text-sanctuary-navy">
                      {fmtDay(w.start)} · {fmt(w.start)}–{fmt(w.end)}
                    </span>
                    <span className="ml-2 text-xs text-sanctuary-navy/50">
                      {w.child_covered_by.join(", ")} · {w.duration_hours}h
                    </span>
                  </span>
                  {added[w.start] ? (
                    <span className="whitespace-nowrap text-xs font-medium text-sanctuary-navy/60">
                      ✓ {dayPart(w.start)} is yours — on your{" "}
                      {PROVIDER_LABEL[added[w.start]] ?? added[w.start]} calendar
                    </span>
                  ) : (
                    <button
                      onClick={() => addToCalendar(w)}
                      className="whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 text-xs font-medium text-sanctuary-navy transition hover:bg-sage-release/20"
                    >
                      + Keep this time
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 font-micro text-xs text-sanctuary-navy/40">
            {plan.windows.length} window{plan.windows.length === 1 ? "" : "s"} of
            real time this week — {plan.summary.total_hours} hours that are
            genuinely yours: you're free, and the kids are looked after.
          </p>
        </div>
      )}
      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
