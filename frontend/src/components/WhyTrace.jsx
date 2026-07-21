import React from "react";

/**
 * Why? — the expandable reasoning trace behind a surfaced item.
 *
 * Turns "trust the system" into "verify the system": every briefing item can
 * show where its facts came from (source artifact + tier), whether each was
 * observed or inferred, what's still unknown, and — for care gaps — the
 * per-caregiver basis lines. Pure display; the data is the provenance the
 * pipeline already records.
 */
const TIER_LABEL = {
  CONFIRMATION: "a confirmation (establishes facts)",
  LOGISTICS: "an organizer's logistics notice",
  REMINDER: "a reminder (references facts, doesn't establish them)",
  NEWSLETTER: "a newsletter",
  MARKETING: "marketing",
  UNKNOWN: "an unclassified source",
};

export default function WhyTrace({ why, basis }) {
  const lines = [];

  if (why?.source_document_name) {
    lines.push(
      `Read from “${why.source_document_name}”` +
        (why.artifact_tier ? ` — ${TIER_LABEL[why.artifact_tier] ?? why.artifact_tier}` : "")
    );
  } else if (why?.artifact_tier) {
    lines.push(`Source: ${TIER_LABEL[why.artifact_tier] ?? why.artifact_tier}`);
  }
  if (why?.event_date_origin === "OBSERVED") {
    lines.push("Date was read directly from the source (observed).");
  } else if (why?.event_date_origin === "INFERRED") {
    lines.push("Date was inferred, not read — that's why this waited for review.");
  } else if (why?.event_date_origin === "USER_CONFIRMED") {
    lines.push("Confirmed by you — ground truth.");
  }
  if (why?.corroborated === true) {
    lines.push("Corroborated by more than one source.");
  } else if (why?.corroborated === false) {
    lines.push("Attested by a single source so far (uncorroborated).");
  }
  if (why?.missing_fields?.length) {
    lines.push(
      `Still unknown: ${why.missing_fields.join(", ").replaceAll("_", " ")} — ` +
        "left blank rather than guessed."
    );
  }
  for (const b of basis ?? []) lines.push(b);

  if (lines.length === 0) return null;

  return (
    <details className="mt-2 font-micro text-xs text-sanctuary-navy/60">
      <summary className="cursor-pointer select-none font-medium text-sanctuary-navy/50 hover:text-sanctuary-navy/80">
        Why does Exhale think this?
      </summary>
      <ul className="mt-1.5 space-y-1 border-l border-sanctuary-navy/10 pl-3">
        {lines.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </details>
  );
}
