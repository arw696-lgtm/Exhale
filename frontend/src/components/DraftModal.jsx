import React from "react";
import { threatPresentation } from "../brand/tokens.js";

/**
 * Draft review modal (Blueprint §6 "Execute with Approval", §9.2).
 *
 * Shows the rendered §10 communication draft for an obligation and lets the user
 * approve it. Approval calls the backend, which resolves the obligation.
 */
export default function DraftModal({ draft, busy, onApprove, onClose }) {
  if (!draft) return null;
  const preset = threatPresentation[draft.threat_level] ?? threatPresentation.CRITICAL;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-sanctuary-navy/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-card bg-white shadow-card"
        onClick={(e) => e.stopPropagation()}
        style={{ borderTop: `4px solid ${preset.accent}` }}
      >
        <header className="flex items-start justify-between gap-4 px-6 pt-5">
          <div>
            <p className="font-micro text-xs font-semibold uppercase tracking-wide text-sanctuary-navy/50">
              {draft.delivery_vector.replace("_", " ")} · Draft
            </p>
            <h3 className="mt-1 font-interface text-lg font-semibold tracking-interface text-sanctuary-navy">
              {draft.title}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="font-micro text-xl leading-none text-sanctuary-navy/40 hover:text-sanctuary-navy"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <pre className="mx-6 mt-4 whitespace-pre-wrap rounded-xl bg-pure-breath p-4 font-micro text-sm leading-relaxed text-sanctuary-navy">
          {draft.body}
        </pre>

        <div className="flex items-center justify-end gap-2 px-6 py-5">
          <button
            onClick={onClose}
            className="rounded-full border border-sanctuary-navy/15 px-4 py-2 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath"
          >
            Not now
          </button>
          <button
            onClick={onApprove}
            disabled={busy}
            className="rounded-full bg-sanctuary-navy px-5 py-2 font-micro text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Sending…" : `${draft.primary_action_label} →`}
          </button>
        </div>
      </div>
    </div>
  );
}
