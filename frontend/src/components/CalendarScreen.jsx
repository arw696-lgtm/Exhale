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

  const days = [...byDay.keys()].sort();

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6">
        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.16em] text-sage-release">
          The week ahead
        </p>
        <h1 className="mt-2 font-display text-[2rem] italic text-sanctuary-navy">
          What's coming
        </h1>
      </header>

      {days.length === 0 ? (
        <div className="rounded-[22px] border border-sanctuary-navy/10 bg-surface p-8 text-center shadow-card">
          <p className="font-display text-xl italic text-sanctuary-navy">Nothing on the horizon.</p>
          <p className="mx-auto mt-2 max-w-xs font-micro text-sm text-sanctuary-navy/55">
            No deadlines, gaps, or open windows in view. Connect a calendar and
            Exhale fills this in.
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          {days.map((key) => {
            const d = parseDay(key);
            const entries = byDay.get(key).sort((a, b) => a.sort - b.sort);
            return (
              <section key={key} className="rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
                <h2 className="mb-3 flex items-baseline gap-2 font-interface tracking-interface text-sanctuary-navy">
                  <span className="text-base font-semibold">
                    {d.toLocaleDateString(undefined, { weekday: "long" })}
                  </span>
                  <span className="font-micro text-xs text-sanctuary-navy/45">
                    {d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </span>
                </h2>
                <ul className="space-y-3">
                  {entries.map((e, i) => (
                    <li key={i} className="flex items-start gap-3 font-micro text-sm">
                      <span className={`severity-dot ${e.dot} mt-[6px]`} aria-hidden="true" />
                      <div>
                        <p className="font-semibold text-sanctuary-navy">{e.title}</p>
                        <p className="mt-0.5 text-sanctuary-navy/60">{e.sub}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </main>
  );
}
