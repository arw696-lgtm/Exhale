import React, { useCallback, useEffect, useState } from "react";
import { confirmExtraction, dismissExtraction, fetchReview } from "../data/api.js";

/**
 * Review Queue — the human side of "asks when unsure".
 *
 * Everything the pipeline held at PENDING_VERIFICATION waits here for a yes /
 * no. Each card shows *why* it was held (artifact tier, inferred date, the
 * routing rationale) so the user is reviewing the system's reasoning, not just
 * its answer. Confirm commits it as USER_CONFIRMED ground truth; Dismiss drops
 * it from the queue but keeps the ledger record.
 */
const TIER_LABEL = {
  CONFIRMATION: "confirmation",
  LOGISTICS: "logistics notice",
  REMINDER: "reminder",
  NEWSLETTER: "newsletter",
  MARKETING: "marketing",
  UNKNOWN: "unclassified",
};

export default function ReviewQueue({ familyId, onChanged }) {
  const [review, setReview] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    fetchReview(familyId).then(setReview);
  }, [familyId]);

  useEffect(load, [load]);

  if (!review || review.count === 0) return null;

  const act = async (fn, id) => {
    setError(null);
    setBusyId(id);
    try {
      await fn(id, familyId);
      load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-4 flex items-baseline justify-between">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          ？ Needs Your Confirmation
        </h2>
        <span className="font-micro text-xs text-sanctuary-navy/50">
          {review.count} held for review
        </span>
      </header>

      <ul className="space-y-4">
        {review.pending.map((item) => (
          <li key={item.extraction_id} className="border-l-2 border-looming-amber/60 pl-3 font-micro text-sm">
            <div className="flex items-baseline justify-between gap-2">
              <p className="font-semibold text-sanctuary-navy">{item.extracted_event}</p>
              <span className="whitespace-nowrap text-xs text-sanctuary-navy/50">{item.event_date}</span>
            </div>
            <p className="mt-1 text-xs text-sanctuary-navy/60">
              Held because: {TIER_LABEL[item.artifact_tier] ?? item.artifact_tier}
              {item.event_date_origin === "INFERRED" && " · date was inferred, not read"}
              {item.source_document_name && ` · from “${item.source_document_name}”`}
            </p>
            {item.missing_fields?.length > 0 && (
              <p className="mt-0.5 text-xs text-sanctuary-navy/45">
                Unknown: {item.missing_fields.join(", ").replaceAll("_", " ")}
              </p>
            )}
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => act(confirmExtraction, item.extraction_id)}
                disabled={busyId === item.extraction_id}
                className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
              >
                ✓ Yes, that's real
              </button>
              <button
                onClick={() => act(dismissExtraction, item.extraction_id)}
                disabled={busyId === item.extraction_id}
                className="rounded-full border border-sanctuary-navy/15 px-4 py-1.5 font-medium text-sanctuary-navy/60 transition hover:bg-sanctuary-navy/5 disabled:opacity-50"
              >
                ✕ Not a real obligation
              </button>
            </div>
          </li>
        ))}
      </ul>

      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
