import React, { useEffect, useState } from "react";
import { fetchReflection, reconfirmIntention } from "../data/api.js";

/**
 * The Weekly Reflection — Exhale's exhale. The Sunday face of the home screen:
 * a look back at the week you carried, the hard-won things, and what's still
 * waiting — each with a way to make a call. Weekdays this steps aside for the
 * task briefing; Sunday it leads, because Sunday is when people are already
 * thinking about the week.
 *
 * Honest by construction: it shows only what the backend could actually see, a
 * hard week is named as hard, and a quiet week stays quiet. No confetti.
 */
const KIND_LABEL = {
  dependency_gap: "Handled",
  waiting_on: "Closed a loop",
  pattern_catch: "Caught",
  intention: "Made time",
};

const CONTEXT_LABEL = { alone: "your time", together: "together", on_duty: "on-duty" };

export default function WeeklyReflection({ familyId, live = true, onClose }) {
  const [r, setR] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [scheduled, setScheduled] = useState({}); // intention id → true

  useEffect(() => {
    let alive = true;
    fetchReflection(familyId).then((data) => {
      if (alive) {
        setR(data);
        setLoaded(true);
      }
    });
    return () => {
      alive = false;
    };
  }, [familyId]);

  const makeTime = async (id) => {
    setScheduled((s) => ({ ...s, [id]: true })); // optimistic
    try {
      await reconfirmIntention(id, familyId); // resets staleness → resurfaces with a window
    } catch {
      /* it's already on the list; a failed reconfirm just won't reset the clock */
    }
  };

  if (!loaded) {
    return (
      <main className="flex min-h-[60vh] items-center justify-center">
        <p className="font-display text-2xl italic text-sanctuary-navy/50">
          Looking back on your week…
        </p>
      </main>
    );
  }
  if (!r) {
    // Offline/anonymous — no reflection to show; fall back to tasks quietly.
    return null;
  }

  const { tenor, carried, lingering } = r;
  const hard = tenor.key === "hard" || tenor.key === "mixed";

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 sm:py-12">
      {/* The breath — the honest temperature of the week. */}
      <header className="mb-8 text-center">
        <div className="mx-auto mb-5 h-14 w-14">
          <div className="breath-orb h-full w-full" aria-hidden="true" />
        </div>
        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.18em] text-sage-release">
          Your week · in review
        </p>
        <h1
          className={`mt-3 font-display text-[2.1rem] italic leading-tight ${
            hard ? "text-looming-amber" : "text-sanctuary-navy"
          }`}
        >
          {tenor.headline}
        </h1>
        <p className="mx-auto mt-3 max-w-md font-micro text-sm leading-relaxed text-sanctuary-navy/60">
          {tenor.subhead}
        </p>
      </header>

      {/* What you carried — the invisible labor, made visible. */}
      {carried.count > 0 && (
        <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
          <h2 className="mb-4 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
            What you carried
          </h2>
          <ul className="space-y-3">
            {carried.items.map((it, i) => (
              <li key={i} className="flex items-start gap-3 border-l-2 border-sage-release/60 pl-3">
                <span className="font-micro text-sm text-sanctuary-navy/85">{it.text}</span>
                <span className="ml-auto shrink-0 rounded-full bg-sage-release/12 px-2 py-0.5 font-micro text-[10px] font-medium uppercase tracking-wide text-sage-release">
                  {it.kind === "intention" && it.context
                    ? CONTEXT_LABEL[it.context] ?? KIND_LABEL.intention
                    : KIND_LABEL[it.kind] ?? "Done"}
                </span>
              </li>
            ))}
          </ul>

          {carried.hard_won.length > 0 && (
            <div className="mt-4 rounded-2xl bg-sage-release/8 p-3">
              <p className="font-micro text-xs text-sanctuary-navy/70">
                <span className="font-semibold text-sage-release">And the hard-won one{carried.hard_won.length === 1 ? "" : "s"}:</span>{" "}
                {carried.hard_won.map((h) => h.text).join(" · ")} — things you kept
                meaning to do, and finally did.
              </p>
            </div>
          )}
        </section>
      )}

      {/* What's still waiting — the forward look: make a call, don't just carry it. */}
      {lingering.count > 0 && (
        <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
          <h2 className="mb-1 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
            Still waiting
          </h2>
          <p className="mb-4 font-micro text-xs text-sanctuary-navy/45">
            Long-running things that didn't get their time. No pressure — just a
            chance to decide.
          </p>
          <ul className="space-y-3">
            {lingering.items.map((it) => (
              <li key={it.id} className="flex flex-wrap items-center gap-2">
                <span className="font-micro text-sm text-sanctuary-navy/85">
                  {it.text}
                  {it.kind === "waiting" && (
                    <span className={`ml-2 text-xs ${it.dying ? "text-looming-amber" : "text-sanctuary-navy/45"}`}>
                      · quiet {it.days_waiting} days{it.dying ? " — this thread is dying" : ""}
                    </span>
                  )}
                  {it.kind === "intention" && (
                    <span className="ml-2 text-xs text-sanctuary-navy/45">
                      · come up {it.surfaced_count}×, never scheduled
                    </span>
                  )}
                </span>
                {it.action === "schedule" ? (
                  scheduled[it.id] ? (
                    <span className="ml-auto whitespace-nowrap font-micro text-xs text-sage-release">
                      ✓ back on your list — we'll find you a window
                    </span>
                  ) : (
                    <button
                      onClick={() => makeTime(it.id)}
                      className="ml-auto whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 font-micro text-xs font-medium text-sanctuary-navy transition hover:bg-sage-release/20"
                    >
                      Make time this week
                    </button>
                  )
                ) : (
                  <span className="ml-auto whitespace-nowrap font-micro text-xs text-sanctuary-navy/50">
                    {it.suggestion} →
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {onClose && (
        <div className="mt-2 text-center">
          <button
            onClick={onClose}
            className="rounded-full border border-sanctuary-navy/15 px-5 py-2 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath"
          >
            See this week's tasks →
          </button>
        </div>
      )}

      <footer className="mt-10 text-center font-micro text-xs text-sanctuary-navy/40">
        Breathe out. The week is behind you.
      </footer>
    </main>
  );
}
