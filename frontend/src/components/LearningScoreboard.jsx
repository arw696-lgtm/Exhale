import React, { useEffect, useState } from "react";
import { acknowledgeLearning, fetchLearning } from "../data/api.js";

/**
 * The Learning Scoreboard — the one surface that measures Exhale, not the
 * household. The product's whole promise is "just connect your stuff and I'll
 * learn how your family works," so the honest question isn't "are you clicking
 * around?" — it's "is it actually learning?" This shows the answer, and never
 * pads it: a cold start reads as a cold start, and the surprise count moves
 * only when a real person confirms Exhale told them something new.
 */
function leadPhrase(hours) {
  if (hours == null) return null;
  if (hours >= 48) return `${Math.round(hours / 24)} days ahead`;
  if (hours >= 24) return "a day ahead";
  return `${Math.round(hours)} hours ahead`;
}

function StatLine({ children }) {
  return <p className="font-micro text-sm leading-relaxed text-sanctuary-navy/80">{children}</p>;
}

export default function LearningScoreboard({ familyId }) {
  const [board, setBoard] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [acked, setAcked] = useState({}); // observation_id → true

  useEffect(() => {
    let alive = true;
    fetchLearning(familyId).then((b) => {
      if (alive) {
        setBoard(b);
        setLoaded(true);
      }
    });
    return () => {
      alive = false;
    };
  }, [familyId]);

  if (!loaded) return null; // stay quiet until we know; no skeleton flash
  if (!board) return null; // unavailable (anon/offline) — the panel simply doesn't show

  const { data, patterns_held: held, coverage_foresight: foresight, surprises } = board;
  const ttfp = board.time_to_first_pattern;

  const headline = held.count > 0
    ? "Exhale is learning your family."
    : held.emerging.length > 0
      ? "Exhale is starting to see the rhythm."
      : "Exhale is still listening.";

  const ackRule = async (subject) => {
    const id = `rule:${subject}`;
    setAcked((a) => ({ ...a, [id]: true })); // optimistic; the log is idempotent
    try {
      await acknowledgeLearning(id, "learned_rule", "", familyId);
    } catch {
      /* the count is derived server-side; a failed tap just won't persist */
    }
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-4">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          Is Exhale learning?
        </h2>
        <p className="mt-2 font-display text-xl italic text-sanctuary-navy">{headline}</p>
        {data.signals_seen > 0 && (
          <p className="mt-1 font-micro text-xs text-sanctuary-navy/45">
            {data.signals_seen} signal{data.signals_seen === 1 ? "" : "s"} seen
            {data.days_observed > 0 && ` · listening for ${data.days_observed} day${data.days_observed === 1 ? "" : "s"}`}
          </p>
        )}
      </header>

      {/* Time to first pattern — the headline learning metric. */}
      <div className="mb-4 border-l-2 border-sage-release/60 pl-3">
        {ttfp?.achieved ? (
          <StatLine>
            First pattern held in{" "}
            <span className="font-semibold text-sanctuary-navy">
              {ttfp.days === 0 ? "under a day" : `${ttfp.days} day${ttfp.days === 1 ? "" : "s"}`}
            </span>{" "}
            — after {ttfp.signals_needed} signal{ttfp.signals_needed === 1 ? "" : "s"}.
          </StatLine>
        ) : held.emerging.length > 0 ? (
          <StatLine>
            No pattern held yet — {held.emerging.length} rhythm
            {held.emerging.length === 1 ? " is" : "s are"} still gathering evidence.
          </StatLine>
        ) : (
          <StatLine>
            No pattern yet. Connect email and calendars, and Exhale learns your
            recurring rhythms on its own — no setup.
          </StatLine>
        )}
      </div>

      {/* Patterns held — each cites its evidence; each can be marked "new to me". */}
      {held.count > 0 && (
        <div className="mb-4">
          <p className="mb-2 font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
            What it's learned
          </p>
          <ul className="space-y-2">
            {held.rules.map((r) => {
              const id = `rule:${r.subject}`;
              return (
                <li key={r.kind + r.subject} className="flex items-start justify-between gap-3">
                  <span className="font-micro text-sm text-sanctuary-navy/85">
                    {r.detail}
                  </span>
                  {acked[id] ? (
                    <span className="whitespace-nowrap font-micro text-xs text-sage-release">✓ new to us</span>
                  ) : (
                    <button
                      onClick={() => ackRule(r.subject)}
                      className="whitespace-nowrap rounded-full border border-sanctuary-navy/15 px-2.5 py-0.5 font-micro text-[11px] text-sanctuary-navy/60 transition hover:bg-pure-breath"
                      title="Mark this as something you didn't already know"
                    >
                      I didn't know this
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Emerging — honest "almost", so still-learning reads as motion. */}
      {held.emerging.length > 0 && (
        <p className="mb-4 font-micro text-xs text-sanctuary-navy/45">
          Almost there:{" "}
          {held.emerging
            .map((e) => `“${e.subject}” (${e.samples} of ${e.samples + e.needs} seen)`)
            .join(" · ")}
        </p>
      )}

      {/* Coverage foresight + surprises — the two outcome measures. */}
      <div className="grid grid-cols-2 gap-3 border-t border-sanctuary-navy/10 pt-4">
        <div>
          <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
            Coverage foresight
          </p>
          {foresight ? (
            <StatLine>
              {foresight.gaps_ahead === 0 ? (
                "No gaps on the horizon."
              ) : (
                <>
                  Soonest gap seen{" "}
                  <span className="font-semibold text-sanctuary-navy">
                    {leadPhrase(foresight.earliest_lead_hours) ?? "ahead"}
                  </span>
                  .
                </>
              )}
              {foresight.acted_on_this_week > 0 &&
                ` ${foresight.acted_on_this_week} caught & handled this week.`}
            </StatLine>
          ) : (
            <p className="font-micro text-sm text-sanctuary-navy/45">
              Set up coverage to measure this.
            </p>
          )}
        </div>
        <div>
          <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
            Surprises confirmed
          </p>
          {surprises.confirmed > 0 ? (
            <StatLine>
              <span className="font-semibold text-sanctuary-navy">{surprises.confirmed}</span>{" "}
              thing{surprises.confirmed === 1 ? "" : "s"} you said you didn't know.
            </StatLine>
          ) : (
            <p className="font-micro text-sm text-sanctuary-navy/45">
              None yet — mark a pattern above as new when it surprises you.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
