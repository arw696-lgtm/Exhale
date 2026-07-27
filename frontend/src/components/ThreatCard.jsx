import React from "react";
import { threatPresentation } from "../brand/tokens.js";
import WhyTrace from "./WhyTrace.jsx";

/**
 * A single "needs you" card (Blueprint §8.3, §9.1).
 *
 * Calm vocabulary: a quiet dot-with-halo carries severity (not a shouting
 * emoji or a hard stripe), and the eyebrow says what's being asked in plain
 * words — attention without alarm.
 */
const DOT = { CRITICAL: "severity-dot--amber", IMPORTANT: "severity-dot--sage", ADVISORY: "severity-dot--navy" };
const EYEBROW = { CRITICAL: "Needs you soon", IMPORTANT: "Worth a look", ADVISORY: "On the horizon" };

export default function ThreatCard({ item, draft, onOpenDraft }) {
  const preset = threatPresentation[item.threat_level] ?? threatPresentation.CRITICAL;
  const tier = preset.label; // CRITICAL | IMPORTANT | ADVISORY
  const tomorrow = item.hours_until_deadline <= 36;
  const primaryLabel = draft?.primary_action_label ?? item.primary_action ?? "Review draft";
  const obligationId = item.obligation_id ?? item.obligation_node_id;

  return (
    <article className="rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
      <div className="flex items-center gap-2">
        <span className={`severity-dot ${DOT[tier] ?? DOT.CRITICAL}`} aria-hidden="true" />
        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
          {tomorrow && tier === "CRITICAL" ? "Needs you by tomorrow" : EYEBROW[tier] ?? EYEBROW.CRITICAL}
        </p>
      </div>
      <h3 className="mt-2 font-interface text-lg font-semibold leading-snug tracking-interface text-sanctuary-navy">
        {item.title}
      </h3>

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
            {tomorrow && <span className="ml-1 font-semibold text-looming-amber">(tomorrow)</span>}
          </dd>
        </div>
        {item.source_document_name && (
          <div className="col-span-2 flex gap-2 text-xs text-sanctuary-navy/55">
            <dt>Read from:</dt>
            <dd>“{item.source_document_name}”</dd>
          </div>
        )}
      </dl>

      <WhyTrace why={item.why} />

      <div className="mt-4 flex flex-wrap gap-2">
        {item.secondary_action && (
          <button className="rounded-full border border-sanctuary-navy/15 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath">
            {item.secondary_action}
          </button>
        )}
        <button
          onClick={() => onOpenDraft?.(obligationId)}
          disabled={!draft && !onOpenDraft}
          className="rounded-full bg-ink-solid px-4 py-1.5 font-micro text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {primaryLabel} →
        </button>
      </div>
    </article>
  );
}
