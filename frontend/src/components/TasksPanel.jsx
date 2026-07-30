import React, { useCallback, useEffect, useState } from "react";
import {
  addTask,
  claimTask,
  completeTask,
  dropTask,
  fetchTasks,
} from "../data/api.js";

/**
 * Around the House — the household's own task pile. Either member drops one in
 * ("mow the lawn", "call the plumber"); anyone can claim it ("I've got this")
 * or just do it. Completing flows into the resolved record, so the win shows
 * up in the Handled recap and the Sunday reflection's "what you carried."
 *
 * When Exhale has found the household a window this week, the panel lays the
 * pile next to it — a gentle "got a little time?" — but never schedules a
 * chore into anyone's time on its own, and nothing here nags.
 */
function windowPhrase(w) {
  if (!w) return null;
  const d = new Date(w.start);
  const day = d.toLocaleDateString(undefined, { weekday: "long" });
  const h = d.getHours();
  const part = h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
  return `${day} ${part}`;
}

export default function TasksPanel({ familyId, window: suggestedWindow, onChanged }) {
  const [tasks, setTasks] = useState(null);
  const [covered, setCovered] = useState([]);
  const [draft, setDraft] = useState("");
  const [weekly, setWeekly] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const data = await fetchTasks(familyId);
    setTasks(data?.open ?? null);
    setCovered(data?.covered_this_week ?? []);
  }, [familyId]);

  useEffect(() => {
    load();
  }, [load]);

  if (tasks === null) return null; // unavailable (offline/anon) — no empty shell

  const act = async (fn) => {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch {
      await load(); // state moved under us (someone else acted) — resync
    } finally {
      setBusy(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    if (!draft.trim()) return;
    const text = draft.trim();
    const cadence = weekly ? "weekly" : "once";
    setDraft("");
    setWeekly(false);
    act(() => addTask(text, familyId, cadence));
  };

  const complete = (id) =>
    act(async () => {
      await completeTask(id, familyId);
      onChanged?.(); // the win lands in the Handled recap — refresh it
    });

  const when = windowPhrase(suggestedWindow);

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-3">
        <h2 className="font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          Contributions
        </h2>
        {tasks.length > 0 && when && (
          <p className="mt-1 font-micro text-xs text-sage-release">
            {when} looks open — got a little time?
          </p>
        )}
      </header>

      {tasks.length === 0 ? (
        <p className="font-micro text-sm text-sanctuary-navy/50">
          {covered.length > 0
            ? "Everything's covered this week. Nicely done."
            : "Nothing on the pile. Add anything the house needs — mow the lawn, call the plumber — and whoever has a moment can grab it."}
        </p>
      ) : (
        <ul className="space-y-2.5">
          {tasks.map((t) => (
            <li key={t.id} className="flex items-start gap-2">
              <button
                onClick={() => complete(t.id)}
                disabled={busy}
                className="mt-0.5 h-5 w-5 shrink-0 rounded-full border-2 border-sage-release/50 transition hover:bg-sage-release/20"
                title="Done"
                aria-label={`Mark "${t.description}" done`}
              />
              <span className="min-w-0 flex-1 font-micro text-sm leading-relaxed text-sanctuary-navy/85">
                {t.description}
                {t.cadence === "weekly" && (
                  <span className="ml-2 whitespace-nowrap rounded-full bg-sanctuary-navy/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sanctuary-navy/45">
                    weekly
                  </span>
                )}
                {t.claimed_by && (
                  <span className="ml-2 whitespace-nowrap rounded-full bg-sage-release/12 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sage-release">
                    {t.claimed_by}'s got it
                  </span>
                )}
              </span>
              <span className="flex shrink-0 items-center gap-1.5">
                {!t.claimed_by && (
                  <button
                    onClick={() => act(() => claimTask(t.id, familyId))}
                    disabled={busy}
                    className="rounded-full border border-sanctuary-navy/15 px-2.5 py-0.5 font-micro text-[11px] text-sanctuary-navy/60 transition hover:bg-pure-breath"
                  >
                    I've got this
                  </button>
                )}
                <button
                  onClick={() => act(() => dropTask(t.id, familyId))}
                  disabled={busy}
                  className="px-1 font-micro text-xs text-sanctuary-navy/30 transition hover:text-sanctuary-navy/60"
                  title="Let it go"
                  aria-label={`Let "${t.description}" go`}
                >
                  ✕
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* Weeklies already covered — quiet credit, back on the pile next week. */}
      {covered.length > 0 && (
        <div className="mt-4 border-t border-sanctuary-navy/10 pt-3">
          <p className="mb-1.5 font-interface text-[10px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/40">
            Covered this week
          </p>
          <ul className="space-y-1">
            {covered.map((t) => (
              <li key={t.id} className="font-micro text-xs text-sanctuary-navy/50">
                <span className="mr-1.5 text-sage-release">✓</span>
                {t.description}
                {t.last_completed_by && ` — ${t.last_completed_by}'s contribution`}
              </li>
            ))}
          </ul>
        </div>
      )}

      <form onSubmit={submit} className="mt-4">
        <div className="flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="The house needs…"
            className="flex-1 rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-1.5 font-micro text-sm text-sanctuary-navy outline-none focus:border-sage-release"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="whitespace-nowrap rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
          >
            Add
          </button>
        </div>
        <label className="mt-2 flex cursor-pointer items-center gap-2 font-micro text-xs text-sanctuary-navy/55">
          <input
            type="checkbox"
            checked={weekly}
            onChange={(e) => setWeekly(e.target.checked)}
            className="h-3.5 w-3.5 accent-[rgb(var(--sage))]"
          />
          Every week — a standing contribution (comes back each week)
        </label>
      </form>
    </section>
  );
}
