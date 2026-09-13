import React, { useCallback, useEffect, useState } from "react";
import Icon from "./Icon.jsx";
import {
  addOneOffHandover,
  addRecurringHandover,
  fetchHandovers,
  removeHandover,
} from "../data/api.js";
import { childrenPhrase } from "../data/household.js";

/**
 * Who has the child — the one thing Exhale could never work out on its own.
 *
 * Everything else it knows is about when someone is *busy*. Without this the
 * only way to answer "who has Stevie on Saturday?" was to invert busyness, so
 * an empty weekend diary became sixteen hours of "time that's yours" on a day
 * the child was home the whole time.
 *
 * Two shapes, because households run on a rhythm that real life interrupts:
 * a standing arrangement, and a one-off. Nothing here is ever inferred — if
 * it is not stated, Exhale says nothing rather than guessing.
 */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function prettyRecurring(h) {
  const days = h.weekdays.map((d) => DAYS[d]).join(", ");
  return `${days} · ${shortTime(h.start_time)}–${shortTime(h.end_time)}`;
}

function shortTime(hms) {
  const [h, m] = String(hms).split(":").map(Number);
  const period = h < 12 ? "am" : "pm";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return m ? `${hour}:${String(m).padStart(2, "0")}${period}` : `${hour}${period}`;
}

function prettyOnce(h) {
  const start = new Date(h.start);
  const end = new Date(h.end);
  const day = start.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const t = (d) => d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} · ${t(start)}–${t(end)}`;
}

export default function HandoversPanel({ briefing, familyId, caregivers = [], onChanged }) {
  const kids = childrenPhrase(briefing);
  const [handovers, setHandovers] = useState(null);
  const [who, setWho] = useState("");
  const [days, setDays] = useState([]);
  const [from, setFrom] = useState("16:00");
  const [to, setTo] = useState("20:00");
  const [onceDay, setOnceDay] = useState("");
  const [mode, setMode] = useState("recurring");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    const data = await fetchHandovers(familyId);
    setHandovers(data?.handovers ?? null);
  }, [familyId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!who && caregivers.length) setWho(caregivers[0]);
  }, [caregivers, who]);

  // No coverage model yet — there is nobody to hand over to.
  if (handovers === null) return null;

  const toggleDay = (d) =>
    setDays((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d]));

  const add = async () => {
    setError(null);
    setBusy(true);
    try {
      if (mode === "recurring") {
        if (days.length === 0) throw new Error("Pick at least one day.");
        await addRecurringHandover(who, days, `${from}:00`, `${to}:00`, familyId);
        setDays([]);
      } else {
        if (!onceDay) throw new Error("Pick a date.");
        await addOneOffHandover(
          who, `${onceDay}T${from}:00`, `${onceDay}T${to}:00`, familyId
        );
        setOnceDay("");
      }
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const drop = async (id) => {
    setBusy(true);
    setError(null);
    try {
      await removeHandover(id, familyId);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-8 rounded-card bg-surface p-5 shadow-card">
      <header className="mb-3">
        <h2 className="flex items-center gap-2 font-interface text-sm font-semibold uppercase tracking-interface text-sanctuary-navy/70">
          <Icon name="users" className="h-4 w-4 text-sage-text" />
          Who has {kids}
        </h2>
      </header>

      <p className="mb-4 font-micro text-sm text-sanctuary-navy/70">
        Exhale can see when someone's busy, but not who's on duty. Tell it, and
        it can say when your time is genuinely your own — and warn you when
        someone's down to have {kids} and booked elsewhere. Left unsaid, it
        stays quiet rather than guessing.
      </p>

      {handovers.length > 0 && (
        <ul className="mb-4 space-y-2">
          {handovers.map((h) => (
            <li
              key={h.handover_id}
              className="flex items-center justify-between gap-3 rounded-2xl bg-sage-release/10 px-4 py-2.5"
            >
              <span className="min-w-0 font-micro text-sm text-sanctuary-navy/85">
                <span className="font-semibold">{h.caregiver}</span>
                <span className="ml-2 text-sanctuary-navy/70">
                  {h.kind === "recurring" ? prettyRecurring(h) : prettyOnce(h)}
                </span>
              </span>
              <button
                onClick={() => drop(h.handover_id)}
                disabled={busy}
                className="shrink-0 font-micro text-xs text-sanctuary-navy/70 underline-offset-2 hover:underline disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="rounded-2xl border border-sanctuary-navy/10 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2 font-micro text-sm">
          <select
            value={who}
            onChange={(e) => setWho(e.target.value)}
            aria-label="Who has them"
            className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-2 text-sanctuary-navy focus:border-sage-release focus:outline-none"
          >
            {caregivers.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <span className="text-sanctuary-navy/70">has {kids}</span>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            aria-label="How often"
            className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-2 text-sanctuary-navy focus:border-sage-release focus:outline-none"
          >
            <option value="recurring">every week</option>
            <option value="once">just once</option>
          </select>
        </div>

        {mode === "recurring" ? (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {DAYS.map((label, day) => {
              const on = days.includes(day);
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleDay(day)}
                  className={
                    "rounded-full border px-2.5 py-1 font-micro text-xs font-medium transition " +
                    (on
                      ? "border-sage-release/60 bg-sage-release/20 text-sanctuary-navy"
                      : "border-sanctuary-navy/15 text-sanctuary-navy/70 hover:bg-sanctuary-navy/5")
                  }
                >
                  {label}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="mb-3">
            <input
              type="date"
              value={onceDay}
              onChange={(e) => setOnceDay(e.target.value)}
              aria-label="Which day"
              className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-2 font-micro text-sanctuary-navy focus:border-sage-release focus:outline-none"
            />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 font-micro text-sm">
          <span className="text-sanctuary-navy/70">from</span>
          <input
            type="time"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            aria-label="From"
            className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-2 text-sanctuary-navy focus:border-sage-release focus:outline-none"
          />
          <span className="text-sanctuary-navy/70">to</span>
          <input
            type="time"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            aria-label="To"
            className="rounded-full border border-sanctuary-navy/15 bg-pure-breath px-3 py-2 text-sanctuary-navy focus:border-sage-release focus:outline-none"
          />
          <button
            onClick={add}
            disabled={busy || !who}
            className="rounded-full border border-sage-release/40 bg-sage-release/10 px-4 py-2 font-medium text-sanctuary-navy transition hover:bg-sage-release/20 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Add"}
          </button>
        </div>
      </div>

      {error && <p className="mt-3 font-micro text-sm text-amber-text">{error}</p>}
    </section>
  );
}
