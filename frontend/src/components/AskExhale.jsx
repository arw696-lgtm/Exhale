import React, { useRef, useState } from "react";
import { askExhale, scheduleEvent } from "../data/api.js";

/**
 * Ask Exhale — the household's front door in plain language.
 *
 * "Do I have free time today?" · "Find me a time for the dentist" · "What
 * needs me this week?" — questions answered from the household's real state,
 * not from a chat model's imagination.
 *
 * When it finds a time, it comes back as a proposal with a confirm button:
 * the same approval gate as everything else in Exhale. The assistant can
 * suggest a hold; only a person's tap places it.
 */
function prettySlot(p) {
  const start = new Date(p.start);
  const end = new Date(p.end);
  const day = start.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
  const t = (d) => d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} · ${t(start)}–${t(end)}`;
}

export default function AskExhale({ familyId, live, onChanged }) {
  const [turns, setTurns] = useState([]); // {role, text, proposal?, held?}
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const inputRef = useRef(null);

  if (!live) return null;

  const send = async (e) => {
    e?.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    setDraft("");
    const history = turns.map((t) => ({ role: t.role, text: t.text }));
    setTurns((prev) => [...prev, { role: "user", text: question }]);
    setBusy(true);
    try {
      const body = await askExhale(question, familyId, history);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: body.reply, proposal: body.proposal },
      ]);
    } catch (err) {
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: err.message, error: true },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const hold = async (index, proposal) => {
    setBusy(true);
    try {
      await scheduleEvent(
        {
          title: proposal.title,
          start: proposal.start,
          end: proposal.end,
          description: "Held from Ask Exhale",
        },
        familyId
      );
      setTurns((prev) =>
        prev.map((t, i) => (i === index ? { ...t, held: true } : t))
      );
      onChanged?.();
    } catch (err) {
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: err.message, error: true },
      ]);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <div className="mx-auto max-w-2xl px-4 pb-4">
        <button
          onClick={() => {
            setOpen(true);
            setTimeout(() => inputRef.current?.focus(), 50);
          }}
          className="w-full rounded-full border border-sanctuary-navy/12 bg-surface px-5 py-3 text-left font-micro text-sm text-sanctuary-navy/45 shadow-card transition hover:border-sage-release/40"
        >
          Ask Exhale — "do I have any free time today?"
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 pb-4">
      <section className="rounded-card bg-surface p-4 shadow-card">
        <header className="mb-3 flex items-baseline justify-between">
          <h2 className="font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
            Ask Exhale
          </h2>
          <button
            onClick={() => setOpen(false)}
            className="font-micro text-xs text-sanctuary-navy/40 hover:text-sanctuary-navy"
          >
            Close
          </button>
        </header>

        {turns.length === 0 && (
          <p className="mb-3 font-micro text-xs leading-relaxed text-sanctuary-navy/50">
            Ask about the week, who's covering what, or when you're free. If
            you ask for a time, Exhale will offer one you can hold — it never
            books anything on its own.
          </p>
        )}

        <div className="space-y-3">
          {turns.map((t, i) => (
            <div key={i}>
              <p
                className={
                  t.role === "user"
                    ? "font-micro text-sm text-sanctuary-navy/85"
                    : t.error
                    ? "font-micro text-sm text-looming-amber"
                    : "font-micro text-sm leading-relaxed text-sanctuary-navy/70"
                }
              >
                {t.role === "user" ? (
                  <span className="text-sanctuary-navy/45">You: </span>
                ) : null}
                {t.text}
              </p>

              {t.proposal && !t.held && (
                <div className="mt-2 rounded-2xl border border-sage-release/30 bg-sage-release/8 p-3">
                  <p className="font-micro text-sm text-sanctuary-navy/85">
                    {t.proposal.title}
                  </p>
                  <p className="mt-0.5 font-micro text-xs text-sanctuary-navy/55">
                    {prettySlot(t.proposal)}
                  </p>
                  <button
                    onClick={() => hold(i, t.proposal)}
                    disabled={busy}
                    className="mt-2 rounded-full border border-sage-release/40 bg-sage-release/15 px-4 py-1.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-sage-release/25 disabled:opacity-50"
                  >
                    Hold this time
                  </button>
                </div>
              )}
              {t.held && (
                <p className="mt-1 font-micro text-xs text-sage-release">
                  Held — it's on the calendar.
                </p>
              )}
            </div>
          ))}
          {busy && (
            <p className="font-micro text-sm text-sanctuary-navy/40">Thinking…</p>
          )}
        </div>

        <form onSubmit={send} className="mt-3 flex items-center gap-2">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Do I have any free time today?"
            className="min-w-0 flex-1 rounded-full border border-sanctuary-navy/15 bg-pure-breath px-4 py-2 font-micro text-sm text-sanctuary-navy placeholder:text-sanctuary-navy/35 focus:border-sage-release focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="shrink-0 rounded-full bg-ink-solid px-4 py-2 font-micro text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
          >
            Ask
          </button>
        </form>
      </section>
    </div>
  );
}
