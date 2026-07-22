import React, { useState } from "react";
import {
  addIntention,
  answerIntentionFollowUp,
  reconfirmIntention,
  setIntentionStatus,
} from "../data/api.js";

/**
 * Time For What Matters — open windows laid next to what they could be for.
 *
 * The thesis as a section: Exhale finds the time; the family says what it's
 * for — seeing a friend, the dermatology appointment, the gym. No
 * auto-assignment: the windows and the intentions sit side by side and the
 * human connects them. Adding an intention is one sentence and a toggle.
 *
 * Anti-guilt: an intention that's been surfaced ~4 weeks unanswered appears
 * once as a gentle check-in (keep it or let it go) instead of quietly
 * nagging; ignoring the check-in retires it. A matched intention gets one
 * "did that happen?" a week later — the only place the system asks whether
 * found time actually landed — then never asks again.
 */
function fmtWindow(w) {
  const d = new Date(w.start);
  const day = d.toLocaleDateString(undefined, { weekday: "long" });
  const time = (iso) =>
    new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} ${time(w.start)}–${time(w.end)}`;
}

export default function TimeForWhatMatters({ block, familyId, live = false, onRefresh }) {
  const [text, setText] = useState("");
  const [kind, setKind] = useState("standing");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!block) return null;

  const windows = block.windows ?? [];
  const intentions = block.open_intentions ?? [];
  const checkIns = block.check_ins ?? [];
  const followUps = block.follow_ups ?? [];

  // Nothing to show, nudge already spent, and no live add-form → no section.
  if (!live && windows.length === 0 && intentions.length === 0 &&
      checkIns.length === 0 && followUps.length === 0 && !block.show_add_nudge)
    return null;

  const submit = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addIntention({ description: text.trim(), type: kind }, familyId);
      setText("");
      onRefresh?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const mark = async (intention, status) => {
    setError(null);
    try {
      // "Scheduled it" remembers which window it went to — that's what the
      // one-week "did that happen?" follow-up refers back to.
      const window = status === "matched" && windows.length > 0
        ? { start: windows[0].start, end: windows[0].end }
        : null;
      await setIntentionStatus(intention.intention_id, status, familyId, window);
      onRefresh?.();
    } catch (err) {
      setError(err.message);
    }
  };

  const keep = async (intention) => {
    setError(null);
    try {
      await reconfirmIntention(intention.intention_id, familyId);
      onRefresh?.();
    } catch (err) {
      setError(err.message);
    }
  };

  const answer = async (fu, outcome) => {
    setError(null);
    try {
      await answerIntentionFollowUp(fu.intention_id, outcome, familyId);
      onRefresh?.();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <h2 className="mb-3 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
        💛 Time For What Matters
      </h2>

      {windows.length > 0 && (
        <div className="mb-4">
          <p className="font-micro text-sm text-sanctuary-navy/70">
            {windows.length === 1 ? "There's an open window" : "Open windows"} this
            week —{" "}
            {windows.map((w, i) => (
              <span key={w.start} className="font-semibold text-sanctuary-navy">
                {i > 0 && ", "}
                {fmtWindow(w)}
              </span>
            ))}
            .
          </p>
          {intentions.length > 0 && (
            <p className="mt-1 font-micro text-sm text-sanctuary-navy/70">
              This could be time for:
            </p>
          )}
        </div>
      )}

      {intentions.length > 0 ? (
        <ul className="space-y-2">
          {intentions.map((it) => (
            <li key={it.intention_id}
                className="flex flex-wrap items-center justify-between gap-2 border-l-2 border-sage-release/50 pl-3 font-micro text-sm">
              <span className="text-sanctuary-navy/80">
                {it.description}
                {it.type === "standing" && (
                  <span className="ml-2 rounded-full bg-sanctuary-navy/5 px-2 py-0.5 text-xs text-sanctuary-navy/50">
                    ongoing
                  </span>
                )}
              </span>
              {live && (
                <span className="flex gap-2">
                  <button onClick={() => mark(it, "matched")}
                          className="rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 text-xs font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
                    ✓ Scheduled it
                  </button>
                  <button onClick={() => mark(it, "dismissed")}
                          className="rounded-full border border-sanctuary-navy/15 px-3 py-1 text-xs font-medium text-sanctuary-navy/60 transition hover:bg-sanctuary-navy/5">
                    Not anymore
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        checkIns.length === 0 && followUps.length === 0 && block.show_add_nudge && (
          <p className="font-micro text-sm text-sanctuary-navy/50">
            No personal intentions logged — add one anytime.
          </p>
        )
      )}

      {windows.length === 0 && intentions.length > 0 && (
        <p className="mt-3 font-micro text-xs text-sanctuary-navy/50">
          No clear windows this week — Exhale keeps looking.
        </p>
      )}

      {/* One "did that happen?" per matched intention — then done, whatever the answer */}
      {followUps.length > 0 && (
        <div className="mt-4 border-t border-sanctuary-navy/10 pt-3">
          {followUps.map((fu) => (
            <div key={fu.intention_id}
                 className="mb-2 flex flex-wrap items-center justify-between gap-2 font-micro text-sm">
              <span className="text-sanctuary-navy/70">
                Last week you set aside time for “{fu.description}” — did that happen?
              </span>
              {live && (
                <span className="flex gap-2">
                  <button onClick={() => answer(fu, "happened")}
                          className="rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 text-xs font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
                    Yes 🎉
                  </button>
                  <button onClick={() => answer(fu, "didnt_happen")}
                          className="rounded-full border border-sanctuary-navy/15 px-3 py-1 text-xs font-medium text-sanctuary-navy/60 transition hover:bg-sanctuary-navy/5">
                    Didn't get to it
                  </button>
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Gentle check-in for long-standing intentions — keep or let go, no guilt */}
      {checkIns.length > 0 && (
        <div className="mt-4 border-t border-sanctuary-navy/10 pt-3">
          {checkIns.map((it) => (
            <div key={it.intention_id}
                 className="mb-2 flex flex-wrap items-center justify-between gap-2 font-micro text-sm">
              <span className="text-sanctuary-navy/70">
                You've had “{it.description}” on your list a while — still want
                it here, or should we let it go?
              </span>
              {live && (
                <span className="flex gap-2">
                  <button onClick={() => keep(it)}
                          className="rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 text-xs font-medium text-sanctuary-navy transition hover:bg-sage-release/20">
                    Keep it
                  </button>
                  <button onClick={() => mark(it, "dismissed")}
                          className="rounded-full border border-sanctuary-navy/15 px-3 py-1 text-xs font-medium text-sanctuary-navy/60 transition hover:bg-sanctuary-navy/5">
                    Let it go
                  </button>
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {live && (
        <form onSubmit={submit} className="mt-4 flex flex-wrap items-center gap-2 border-t border-sanctuary-navy/10 pt-3">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder='e.g. "See Mark", "Ali’s dermatology appointment"'
            className="min-w-48 flex-1 rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-1.5 font-micro text-sm text-sanctuary-navy outline-none focus:border-sage-release"
          />
          <button type="button" aria-pressed={kind === "standing"}
                  onClick={() => setKind(kind === "standing" ? "one_off" : "standing")}
                  className="rounded-full border border-sanctuary-navy/15 px-3 py-1.5 font-micro text-xs font-medium text-sanctuary-navy/70 transition hover:bg-sanctuary-navy/5"
                  title="Standing = keeps coming back (gym, a friend). One-off = done once (an appointment).">
            {kind === "standing" ? "ongoing" : "one-time"}
          </button>
          <button type="submit" disabled={busy || !text.trim()}
                  className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50">
            {busy ? "Adding…" : "Add"}
          </button>
        </form>
      )}
      {error && <p className="mt-3 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
