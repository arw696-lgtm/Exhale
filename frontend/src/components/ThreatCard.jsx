import React from "react";
import { threatPresentation, components } from "../brand/tokens.js";

/**
 * A single critical-threat card (Blueprint §8.3, §9.1).
 * Uses a solid vertical Looming Amber indicator bar along the left boundary.
 */
export default function ThreatCard({ item }) {
  const preset = threatPresentation[item.threat_level] ?? threatPresentation.CRITICAL;
  const tomorrow = item.hours_until_deadline <= 36;

  return (
    <article
      className="relative overflow-hidden rounded-card bg-white p-5 shadow-card"
      style={{ borderLeft: `${components.threatBarWidth} solid ${preset.accent}` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-micro text-xs font-semibold uppercase tracking-wide text-looming-amber">
            {preset.indicator} {preset.label} THREAT
          </p>
          <h3 className="mt-1 font-interface text-lg font-semibold leading-snug tracking-interface text-sanctuary-navy">
            {item.title}
          </h3>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 font-micro text-sm text-sanctuary-navy/80">
        {item.person && (
          <div className="col-span-2 flex gap-2">
            <dt className="font-semibold">Who:</dt>
            <dd>{item.person}</dd>
          </div>
        )}
        <div className="col-span-2 flex gap-2">
          <dt className="font-semibold">Deadline:</dt>
          <dd>
            {item.deadline}
            {tomorrow && <span className="ml-1 font-semibold text-looming-amber">(Tomorrow)</span>}
          </dd>
        </div>
        {item.source_document_name && (
          <div className="col-span-2 flex gap-2 text-xs text-sanctuary-navy/60">
            <dt>Parsed from:</dt>
            <dd>{item.source_document_name}</dd>
          </div>
        )}
      </dl>

      <div className="mt-4 flex flex-wrap gap-2">
        {item.secondary_action && (
          <button className="rounded-full border border-sanctuary-navy/15 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath">
            {item.secondary_action}
          </button>
        )}
        {item.primary_action && (
          <button className="rounded-full bg-sanctuary-navy px-4 py-1.5 font-micro text-sm font-semibold text-white transition hover:opacity-90">
            {item.primary_action} →
          </button>
        )}
      </div>
    </article>
  );
}
