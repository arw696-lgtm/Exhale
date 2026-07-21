import React, { useEffect, useState } from "react";
import {
  createHelperInvite,
  fetchHelpers,
  revokeHelper,
} from "../data/api.js";

/**
 * Helper Invite panel (members only) — invite a scoped secondary caregiver
 * (FAMILY_STRUCTURES §3.2). Pick the days a grandparent/sitter covers, get a
 * code; they sign up with it and see only those care days + what you share.
 *
 * Renders nothing when the roster call fails (offline demo / helper account —
 * a helper can't reach these endpoints, and shouldn't see this control).
 */
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function HelperInvitePanel({ familyId }) {
  const [roster, setRoster] = useState(null);
  const [days, setDays] = useState([1, 3]); // a common Tue/Thu default
  const [code, setCode] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  const load = () => fetchHelpers(familyId).then(setRoster);
  useEffect(() => {
    let alive = true;
    fetchHelpers(familyId).then((r) => alive && setRoster(r));
    return () => { alive = false; };
  }, [familyId]);

  if (roster === null) return null; // endpoint unavailable (not a member / offline)

  const toggle = (d) =>
    setDays((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d]));

  const mint = async () => {
    setError(null);
    setCopied(false);
    if (days.length === 0) {
      setError("Pick at least one care day.");
      return;
    }
    try {
      const result = await createHelperInvite(days, familyId);
      setCode(result.code);
    } catch (e) {
      setError(e.message);
    }
  };

  const revoke = async (userId) => {
    setError(null);
    try {
      await revokeHelper(userId, familyId);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const helpers = roster.helpers ?? [];

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          🧑‍🍼 Helpers
        </h2>
      </header>
      <p className="mb-4 font-micro text-sm text-sanctuary-navy/60">
        Invite a grandparent, relative, or regular sitter for specific days. They
        see only those care days and anything you choose to share — never your
        inbox, calendar, or the rest of the household.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        {DAY_LABELS.map((label, day) => {
          const on = days.includes(day);
          return (
            <button key={day} type="button" aria-pressed={on} onClick={() => toggle(day)}
              className={
                "rounded-full border px-2.5 py-1 text-xs font-medium transition " +
                (on
                  ? "border-sage-release/60 bg-sage-release/20 text-sanctuary-navy"
                  : "border-sanctuary-navy/15 text-sanctuary-navy/50 hover:bg-sanctuary-navy/5")
              }>
              {label}
            </button>
          );
        })}
        <button onClick={mint}
          className="ml-2 rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
          Create invite
        </button>
      </div>

      {code && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-sage-release/30 bg-sage-release/5 px-4 py-2 font-micro text-sm">
          <span className="text-sanctuary-navy/70">
            Invite code: <span className="font-semibold tracking-widest text-sanctuary-navy">{code}</span>
          </span>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(code);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            className="rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
      )}

      {helpers.length > 0 && (
        <ul className="space-y-2 border-t border-sanctuary-navy/10 pt-3">
          {helpers.map((h) => (
            <li key={h.user_id} className="flex items-center justify-between font-micro text-sm">
              <div>
                <span className="font-semibold text-sanctuary-navy">
                  {h.display_name || "Helper"}
                </span>
                <span className="ml-2 text-sanctuary-navy/50">
                  {h.weekday_labels?.join(", ") || "no days"}
                  {h.shared_obligation_ids?.length
                    ? ` · ${h.shared_obligation_ids.length} shared`
                    : ""}
                </span>
              </div>
              <button onClick={() => revoke(h.user_id)}
                className="text-xs text-looming-amber/90 underline hover:text-looming-amber">
                Revoke
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
