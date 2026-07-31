import React from "react";
import { threatPresentation } from "../brand/tokens.js";

/**
 * Draft review modal (Blueprint §6 "Execute with Approval", §9.2).
 *
 * Shows the rendered §10 communication for an obligation. When the draft
 * carries a MAILTO handoff, the actual reply is previewed and the primary
 * action opens it in the user's own mail app — Exhale prepares to the
 * threshold, the human crosses it. Approval then only records what the
 * human says happened ("I sent it"). Without a handoff the button says
 * exactly what it does: mark handled.
 */
function mailtoHref(draft) {
  const subject = encodeURIComponent(draft.reply_subject ?? "");
  const body = encodeURIComponent(draft.reply_body ?? "");
  return `mailto:${encodeURIComponent(draft.reply_to)}?subject=${subject}&body=${body}`;
}

export default function DraftModal({ draft, busy, onApprove, onClose }) {
  if (!draft) return null;
  const preset = threatPresentation[draft.threat_level] ?? threatPresentation.CRITICAL;
  const hasHandoff = draft.handoff === "MAILTO" && draft.reply_to;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(8, 14, 24, 0.55)" }}
      onClick={onClose}
    >
      <div
        className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-card bg-surface shadow-card"
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

        {/* The reply itself — the words that will leave the household, shown
            in full before any button. Sent from the user's address, by them. */}
        {hasHandoff && (
          <section className="mx-6 mt-4 rounded-xl border border-sage-release/30 bg-pure-breath p-4">
            <p className="font-micro text-[11px] font-semibold uppercase tracking-wide text-sage-release">
              Your reply, ready to send
            </p>
            <p className="mt-2 font-micro text-xs text-sanctuary-navy/55">
              To: {draft.reply_to}
              <br />
              Subject: {draft.reply_subject}
            </p>
            <pre className="mt-3 whitespace-pre-wrap font-micro text-sm leading-relaxed text-sanctuary-navy">
              {draft.reply_body}
            </pre>
            <p className="mt-3 font-micro text-xs text-sanctuary-navy/45">
              This opens in your own mail app — you can edit anything before it
              goes, and it sends from your address, not Exhale's.
            </p>
          </section>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2 px-6 py-5">
          <button
            onClick={onClose}
            className="rounded-full border border-sanctuary-navy/15 px-4 py-2 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath"
          >
            Not now
          </button>
          {hasHandoff ? (
            <>
              <button
                onClick={onApprove}
                disabled={busy}
                className="rounded-full border border-sanctuary-navy/15 px-4 py-2 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath disabled:opacity-50"
              >
                {busy ? "Marking…" : "I sent it — mark handled"}
              </button>
              <a
                href={mailtoHref(draft)}
                className="rounded-full bg-ink-solid px-5 py-2 font-micro text-sm font-semibold text-white transition hover:opacity-90"
              >
                {draft.primary_action_label} →
              </a>
            </>
          ) : (
            <button
              onClick={onApprove}
              disabled={busy}
              className="rounded-full bg-ink-solid px-5 py-2 font-micro text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "Marking…" : `${draft.primary_action_label} →`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
