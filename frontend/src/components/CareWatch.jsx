import React, { useState } from "react";
import { threatPresentation } from "../brand/tokens.js";
import { scheduleEvent } from "../data/api.js";
import WhyTrace from "./WhyTrace.jsx";

/**
 * Care Watch section — child-supervision gaps from the Care-Coverage Engine.
 *
 * Renders the `care_watch` block the briefing carries when a coverage model is
 * configured. Each gap shows who's unavailable and why, its threat band, and the
 * suggested action — and, per the credibility discipline, flags the gaps that
 * rest on an *assumed* schedule rather than an observed calendar.
 *
 * Against a live backend, each gap also gets "+ Put on my calendar": one tap
 * writes the coverage block ("Sitter needed: Stevie") through /schedule, so it
 * shows up on the family's phone/CarPlay — the same governed write path as
 * work windows (autonomy dial applies; the tap is the approval).
 */
function formatWindow(gap) {
  const day = new Date(gap.start).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
  const time = (iso) =>
    new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} · ${time(gap.start)}–${time(gap.end)}`;
}

const gapKey = (gap) => `${gap.recipient ?? ""}|${gap.start}|${gap.end}`;

const PROVIDER_LABEL = { google: "Google", microsoft: "Outlook", feed: "Exhale" };

// "Saturday" / "Thursday afternoon" — the concrete stretch this covers.
function coveredLabel(gap) {
  const d = new Date(gap.start);
  const day = d.toLocaleDateString(undefined, { weekday: "long" });
  if ((gap.duration_hours ?? 24) >= 8) return day; // most of the day → just the day
  const h = d.getHours();
  return `${day} ${h < 12 ? "morning" : h < 17 ? "afternoon" : "evening"}`;
}

export default function CareWatch({ careWatch, familyId, live = false }) {
  const [added, setAdded] = useState({}); // gap key → provider it landed on
  const [error, setError] = useState(null);

  const agePrompts = careWatch?.age_prompts ?? [];
  if (!careWatch || ((careWatch.gaps?.length ?? 0) === 0 && agePrompts.length === 0))
    return null;

  const { recipient, summary, gaps } = careWatch;
  const assumptionCount = summary?.assumption_dependent ?? 0;
  // Multi-child households: name the child on each gap (the header shows all).
  const multiChild = (careWatch.recipients?.length ?? 1) > 1;

  const putOnCalendar = async (gap) => {
    setError(null);
    try {
      const result = await scheduleEvent(
        {
          title: `Sitter needed: ${gap.recipient ?? recipient}`,
          start: gap.start,
          end: gap.end,
          description: `Care gap — ${gap.reason}. Suggested: ${gap.suggested_action}. (Exhale)`,
        },
        familyId
      );
      setAdded((a) => ({ ...a, [gapKey(gap)]: result.provider }));
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-4 flex items-baseline justify-between">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          🧑‍🍼 Care Watch · {recipient}
        </h2>
        <span className="font-micro text-xs text-sanctuary-navy/50">
          {summary.total_gaps} gap{summary.total_gaps === 1 ? "" : "s"} to cover
        </span>
      </header>

      <ul className="space-y-4">
        {gaps.map((gap) => {
          const band = threatPresentation[gap.threat_level] ?? threatPresentation.ADVISORY;
          return (
            <li
              key={`${gap.recipient ?? ""}-${gap.start}-${gap.end}`}
              className="border-l-2 pl-3 font-micro text-sm"
              style={{ borderColor: band.accent }}
            >
              <div className="flex items-baseline justify-between gap-2">
                <p className="font-semibold text-sanctuary-navy">
                  {band.indicator} {multiChild && gap.recipient ? `${gap.recipient} · ` : ""}
                  {formatWindow(gap)}
                </p>
                <span className="whitespace-nowrap text-xs text-sanctuary-navy/50">
                  {gap.duration_hours}h
                </span>
              </div>
              <p className="mt-1 text-sanctuary-navy/70">{gap.reason}</p>
              <WhyTrace basis={gap.basis} />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
                  → {gap.suggested_action}
                </button>
                {live &&
                  (added[gapKey(gap)] ? (
                    <span className="text-xs font-medium text-sanctuary-navy/60">
                      ✓ {coveredLabel(gap)} is handled — sitter reminder on your{" "}
                      {PROVIDER_LABEL[added[gapKey(gap)]] ?? added[gapKey(gap)]} calendar
                    </span>
                  ) : (
                    <button
                      onClick={() => putOnCalendar(gap)}
                      className="rounded-full border border-sanctuary-navy/15 px-3 py-1 text-xs font-medium text-sanctuary-navy/70 transition hover:bg-sanctuary-navy/5"
                    >
                      + Put on my calendar
                    </button>
                  ))}
                {gap.depends_on_inference && (
                  <span
                    className="rounded-full bg-looming-amber/15 px-2 py-0.5 text-xs font-medium text-sanctuary-navy/70"
                    title="This gap rests on an assumed schedule, not an observed calendar. Sync the calendar to confirm."
                  >
                    assumes a schedule
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {assumptionCount > 0 && (
        <p className="mt-4 border-t border-sanctuary-navy/10 pt-3 font-micro text-xs text-sanctuary-navy/50">
          {assumptionCount} of these rest on an assumed schedule. Sync the calendars
          to turn them into confirmed facts.
        </p>
      )}

      {agePrompts.length > 0 && (
        <div className="mt-4 border-t border-sanctuary-navy/10 pt-3">
          <p className="mb-2 font-micro text-xs font-semibold uppercase text-sanctuary-navy/50">
            Worth a look as they grow
          </p>
          <ul className="space-y-2">
            {agePrompts.map((p) => (
              <li key={`${p.kind}-${p.child}`}
                  className="border-l-2 border-sage-release/50 pl-3 font-micro text-xs text-sanctuary-navy/70">
                {p.question}
                <span className="mt-0.5 block text-sanctuary-navy/40">{p.basis}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
