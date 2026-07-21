import React from "react";
import { threatPresentation } from "../brand/tokens.js";

/**
 * Care Watch section — child-supervision gaps from the Care-Coverage Engine.
 *
 * Renders the `care_watch` block the briefing carries when a coverage model is
 * configured. Each gap shows who's unavailable and why, its threat band, and the
 * suggested action — and, per the credibility discipline, flags the gaps that
 * rest on an *assumed* schedule rather than an observed calendar.
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

export default function CareWatch({ careWatch }) {
  if (!careWatch || (careWatch.gaps?.length ?? 0) === 0) return null;

  const { recipient, summary, gaps } = careWatch;
  const assumptionCount = summary?.assumption_dependent ?? 0;

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
              key={`${gap.start}-${gap.end}`}
              className="border-l-2 pl-3 font-micro text-sm"
              style={{ borderColor: band.accent }}
            >
              <div className="flex items-baseline justify-between gap-2">
                <p className="font-semibold text-sanctuary-navy">
                  {band.indicator} {formatWindow(gap)}
                </p>
                <span className="whitespace-nowrap text-xs text-sanctuary-navy/50">
                  {gap.duration_hours}h
                </span>
              </div>
              <p className="mt-1 text-sanctuary-navy/70">{gap.reason}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
                  → {gap.suggested_action}
                </button>
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
    </section>
  );
}
