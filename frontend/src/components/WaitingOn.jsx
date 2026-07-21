import React, { useCallback, useEffect, useState } from "react";
import { addWaiting, fetchWaiting, resolveWaiting } from "../data/api.js";

/**
 * Waiting On — threads where the ball is in someone else's court.
 *
 * Each open wait shows how long it's been quiet; a week of silence flips it to
 * "time to nudge". Resolve when they finally answer.
 */
export default function WaitingOn({ familyId }) {
  const [watch, setWatch] = useState(null);
  const [who, setWho] = useState("");
  const [about, setAbout] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    fetchWaiting(familyId).then(setWatch);
  }, [familyId]);

  useEffect(load, [load]);

  if (watch === null) return null; // backend unavailable

  const add = async (e) => {
    e.preventDefault();
    if (!who.trim() || !about.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addWaiting({ who: who.trim(), about: about.trim() }, familyId);
      setWho("");
      setAbout("");
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const resolve = async (id) => {
    setBusy(true);
    try {
      await resolveWaiting(id, familyId);
      load();
    } finally {
      setBusy(false);
    }
  };

  const input =
    "rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-1.5 " +
    "font-micro text-sm text-sanctuary-navy outline-none focus:border-sage-release";

  return (
    <section className="mb-8 rounded-card bg-white p-5 shadow-card">
      <header className="mb-4 flex items-baseline justify-between">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          ⏱ Waiting On
        </h2>
        {watch.summary.need_nudge > 0 && (
          <span className="font-micro text-xs text-looming-amber">
            {watch.summary.need_nudge} need a nudge
          </span>
        )}
      </header>

      {watch.items.length > 0 && (
        <ul className="mb-4 space-y-3">
          {watch.items.map((item) => (
            <li key={item.id} className="flex items-center justify-between font-micro text-sm">
              <div>
                <p className="font-semibold text-sanctuary-navy">
                  {item.indicator} {item.who} — {item.about}
                </p>
                <p className="text-xs text-sanctuary-navy/50">
                  quiet for {item.days_waiting} day{item.days_waiting === 1 ? "" : "s"} ·{" "}
                  {item.suggested_action}
                </p>
              </div>
              <button
                onClick={() => resolve(item.id)}
                disabled={busy}
                className="whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-3 py-1 font-micro text-xs font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
              >
                They answered
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={add} className="flex flex-wrap gap-2">
        <input className={`${input} flex-1`} value={who} placeholder="Who owes you a reply?"
               onChange={(e) => setWho(e.target.value)} />
        <input className={`${input} flex-[2]`} value={about} placeholder="About what?"
               onChange={(e) => setAbout(e.target.value)} />
        <button type="submit" disabled={busy || !who.trim() || !about.trim()}
                className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50">
          Track it
        </button>
      </form>
      {error && <p className="mt-2 font-micro text-xs text-looming-amber">{error}</p>}
    </section>
  );
}
