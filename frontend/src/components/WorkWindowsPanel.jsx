import React, { useState } from "react";
import { fetchWorkWindows } from "../data/api.js";

/**
 * Work Windows — "when can I work this week?"
 *
 * The intent side of the coverage math: a caregiver's open windows are the
 * times they're free AND the child is covered by someone else. Renders each
 * suggested block with what makes it workable ("Stevie at ISLA").
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

export default function WorkWindowsPanel({ familyId }) {
  const [caregiver, setCaregiver] = useState("");
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
          ⏳ When Can I Work?
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
          {busy ? "Looking…" : "Find my windows"}
        </button>
      </form>

      {plan && (
        <div className="mt-4">
          {plan.windows.length === 0 ? (
            <p className="font-micro text-sm text-sanctuary-navy/60">
              No open windows found in the next week — every free stretch has the
              kids uncovered.
            </p>
          ) : (
            <ul className="space-y-2">
              {plan.windows.map((w) => (
                <li key={w.start} className="flex items-baseline justify-between border-l-2 border-sage-release/60 pl-3 font-micro text-sm">
                  <span>
                    <span className="font-semibold text-sanctuary-navy">
                      {fmtDay(w.start)} · {fmt(w.start)}–{fmt(w.end)}
                    </span>
                    <span className="ml-2 text-xs text-sanctuary-navy/50">
                      {w.child_covered_by.join(", ")}
                    </span>
                  </span>
                  <span className="text-xs text-sanctuary-navy/50">{w.duration_hours}h</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 font-micro text-xs text-sanctuary-navy/40">
            {plan.summary.total_hours}h suggested across the next week — times
            you're free and the kids are covered.
          </p>
        </div>
      )}
      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
