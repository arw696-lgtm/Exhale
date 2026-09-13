import React from "react";

/**
 * Calendar — the week ahead as one honest agenda.
 *
 * Not a month grid to fill: Exhale already knows what matters, so this stitches
 * the briefing's own signals into a day-by-day list — deadlines that need you,
 * care gaps to cover, and the open windows that are yours. Assembled from data
 * the briefing already carries; no new fetch.
 */
function dayKey(iso) {
  return String(iso).slice(0, 10);
}
function parseDay(key) {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
const DOT = { CRITICAL: "severity-dot--amber", IMPORTANT: "severity-dot--sage", ADVISORY: "severity-dot--navy" };

export default function CalendarScreen({ briefing }) {
  const byDay = new Map();
  const add = (key, entry) => {
    if (!key) return;
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(entry);
  };

  // Deadlines that need you.
  for (const it of [...(briefing.critical_threats ?? []), ...(briefing.dependency_watch ?? [])]) {
    if (!it.deadline) continue;
    add(dayKey(it.deadline), {
      dot: DOT[it.threat_level] ?? "severity-dot--amber",
      title: it.title,
      sub: `Due${it.person ? ` · ${it.person}` : ""}`,
      sort: 0,
    });
  }

  // Care gaps to cover.
  for (const g of briefing.care_watch?.gaps ?? []) {
    add(dayKey(g.date ?? g.start), {
      dot: DOT[g.threat_level] ?? "severity-dot--navy",
      title: `${g.recipient ?? "Coverage"} needs a sitter`,
      sub: `${fmtTime(g.start)}–${fmtTime(g.end)} · ${g.reason}`,
      sort: new Date(g.start).getHours(),
    });
  }

  // Open windows — time that's yours.
  const tfwm = briefing.time_for_what_matters ?? {};
  const windowGroups = [
    [tfwm.windows, "Open window", "severity-dot--sage"],
    [tfwm.together_windows, "Together time", "severity-dot--sage"],
    [tfwm.on_duty_windows, "With the kids", "severity-dot--navy"],
  ];
  for (const [list, label, dot] of windowGroups) {
    for (const w of list ?? []) {
      add(dayKey(w.start), {
        dot,
        title: label,
        sub: `${fmtTime(w.start)}–${fmtTime(w.end)} · time that's yours`,
        sort: new Date(w.start).getHours(),
      });
    }
  }

  // A screen headed "what's coming" must know what day it is. Every day key
  // present was being rendered, so an obligation still open from July sat
  // under "The week ahead" in September. Overdue is real and stays visible —
  // it just isn't coming, and saying so is the difference between an agenda
  // and a pile.
  const todayKey = dayKey(new Date().toLocaleDateString("sv"));
  const allDays = [...byDay.keys()].sort();
  const overdueDays = allDays.filter((k) => k < todayKey);
  const days = allDays.filter((k) => k >= todayKey);
  const passed = briefing.passed ?? [];

  const daySection = (key) => {
    const d = parseDay(key);
    const entries = byDay.get(key).sort((a, b) => a.sort - b.sort);
    return (
      <section key={key} className="rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
        <h2 className="mb-3 flex items-baseline gap-2 font-interface tracking-interface text-sanctuary-navy">
          <span className="text-base font-semibold">
            {d.toLocaleDateString(undefined, { weekday: "long" })}
          </span>
          <span className="font-micro text-xs text-sanctuary-navy/70">
            {d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          </span>
        </h2>
        <ul className="space-y-3">
          {entries.map((e, i) => (
            <li key={i} className="flex items-start gap-3 font-micro text-sm">
              <span className={`severity-dot ${e.dot} mt-[6px]`} aria-hidden="true" />
              <div>
                <p className="font-semibold text-sanctuary-navy">{e.title}</p>
                <p className="mt-0.5 text-sanctuary-navy/70">{e.sub}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    );
  };

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      {/* Overdue leads, because it is the only thing here that can still be
          acted on and lost. It is deliberately not folded into "what's
          coming": a missed deadline dressed as an upcoming one is the one
          thing an instrument like this must never do. */}
      {overdueDays.length > 0 && (
        <section className="mb-8">
          <header className="mb-4">
            <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-text">
              Already past
            </p>
            <h2 className="mt-2 font-display text-[1.6rem] italic text-sanctuary-navy">
              Still open
            </h2>
          </header>
          <div className="space-y-5">{overdueDays.map(daySection)}</div>
        </section>
      )}

      <header className="mb-6">
        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.16em] text-sage-text">
          The week ahead
        </p>
        <h1 className="mt-2 font-display text-[2rem] italic text-sanctuary-navy">
          What's coming
        </h1>
      </header>

      {days.length === 0 ? (
        <div className="rounded-[22px] border border-sanctuary-navy/10 bg-surface p-8 text-center shadow-card">
          <p className="font-display text-xl italic text-sanctuary-navy">Nothing on the horizon.</p>
          <p className="mx-auto mt-2 max-w-xs font-micro text-sm text-sanctuary-navy/70">
            No deadlines, gaps, or open windows in view. Connect a calendar and
            Exhale fills this in.
          </p>
        </div>
      ) : (
        <div className="space-y-5">{days.map(daySection)}</div>
      )}

      {/* Counted nowhere, hidden nowhere. These are weeks gone — naming them
          is what keeps "nothing needs you" honest. */}
      {passed.length > 0 && (
        <section className="mt-8 rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
          <h2 className="font-interface text-[11px] font-semibold uppercase tracking-[0.16em] text-sanctuary-navy/70">
            The moment has passed · {passed.length}
          </h2>
          <p className="mt-2 font-micro text-sm text-sanctuary-navy/70">
            Open in Exhale, but the date is more than two weeks behind us.
            They're kept on the record and left out of the counts — nothing you
            do today changes them.
          </p>
          <ul className="mt-3 space-y-2">
            {passed.slice(0, 8).map((item) => (
              <li key={item.obligation_id} className="font-micro text-sm text-sanctuary-navy/70">
                <span className="text-sanctuary-navy">{item.title}</span>
                {item.deadline && <span> · {item.deadline}</span>}
              </li>
            ))}
          </ul>
          {passed.length > 8 && (
            <p className="mt-2 font-micro text-xs text-sanctuary-navy/70">
              and {passed.length - 8} more
            </p>
          )}
        </section>
      )}
    </main>
  );
}
