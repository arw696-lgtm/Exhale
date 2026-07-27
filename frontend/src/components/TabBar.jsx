import React from "react";

/**
 * The bottom tab bar — a frosted, floating bar that turns one long scroll into
 * a real multi-screen app. Today carries a small count when something needs
 * attention. Fixed to the viewport bottom; screens pad their content past it.
 */
const ICONS = {
  today: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11.5 12 4l9 7.5" /><path d="M5 10v9h14v-9" />
    </svg>
  ),
  calendar: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4.5" width="18" height="16" rx="2.5" /><path d="M3 9h18M8 3v3M16 3v3" />
    </svg>
  ),
  household: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 20v-1a5 5 0 0 1 5-5h1" /><circle cx="9.5" cy="8" r="3.2" /><path d="M15 13a4 4 0 0 1 5 4v3" /><circle cx="16.5" cy="7.5" r="2.6" />
    </svg>
  ),
  you: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" /><path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  ),
};

const TABS = [
  { key: "today", label: "Today" },
  { key: "calendar", label: "Calendar" },
  { key: "household", label: "Household" },
  { key: "you", label: "You" },
];

export default function TabBar({ active, onChange, todayCount = 0 }) {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-2"
      aria-label="Sections"
    >
      <div className="flex w-full max-w-md justify-around rounded-[26px] border border-sanctuary-navy/10 bg-surface/85 px-2 py-2.5 shadow-card backdrop-blur-xl">
        {TABS.map((t) => {
          const on = active === t.key;
          return (
            <button
              key={t.key}
              onClick={() => onChange(t.key)}
              aria-current={on ? "page" : undefined}
              className={
                "relative flex flex-1 flex-col items-center gap-1 font-interface text-[10px] font-semibold transition " +
                (on ? "text-sage-release" : "text-sanctuary-navy/40 hover:text-sanctuary-navy/70")
              }
            >
              <span className="relative">
                {ICONS[t.key]}
                {t.key === "today" && todayCount > 0 && (
                  <span className="absolute -right-1.5 -top-1 grid h-3.5 min-w-3.5 place-items-center rounded-full bg-looming-amber px-1 text-[8px] font-bold text-white">
                    {todayCount}
                  </span>
                )}
              </span>
              {t.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
