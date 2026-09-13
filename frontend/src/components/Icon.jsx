import React from "react";

/**
 * The app's line-icon set — one visual language, drawn once.
 *
 * Every panel header used to open with an emoji: 🔗 Connections, 💛 Time For
 * What Matters, 🧑‍🍼 Helpers, 📆 Bring In a Calendar. Emoji are a different
 * design language from the rest of this app — multicolour, cartoon, and
 * rendered by the operating system, so the same screen looks different on an
 * iPhone, an Android and a Mac, and none of those versions were designed.
 * Against Instrument Serif and a palette tuned to two decimal places they
 * read as placeholders that never got replaced, which is most of why the app
 * looked unfinished.
 *
 * The tab bar already had the answer: 1.8px strokes, round caps and joins, on
 * a 24px grid, inheriting currentColor so an icon is always exactly as loud as
 * the text beside it. That language is now shared instead of living in one
 * component.
 */
const PATHS = {
  // household & people
  home: <><path d="M3 11.5 12 4l9 7.5" /><path d="M5 10v9h14v-9" /></>,
  users: <><path d="M4 20v-1a5 5 0 0 1 5-5h1" /><circle cx="9.5" cy="8" r="3.2" /><path d="M15 13a4 4 0 0 1 5 4v3" /><circle cx="16.5" cy="7.5" r="2.6" /></>,
  person: <><circle cx="12" cy="8" r="4" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
  // time & place
  calendar: <><rect x="3" y="4.5" width="18" height="16" rx="2.5" /><path d="M3 9h18M8 3v3M16 3v3" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  plane: <path d="M10.5 13.5 3 11l1-2 7 1 4-5.5a2 2 0 0 1 3 2.5L15 12l1 7-2 1-2.5-6.5" />,
  // things & actions
  link: <><path d="M10 13.5a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7l-1.4 1.4" /><path d="M14 10.5a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 0 0 5.7 5.7l1.4-1.4" /></>,
  camera: <><path d="M3 8.5A2 2 0 0 1 5 6.5h2l1.4-2h7.2L17 6.5h2a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><circle cx="12" cy="12.5" r="3.4" /></>,
  bell: <><path d="M18 15V10a6 6 0 1 0-12 0v5l-1.5 2.5h15z" /><path d="M10 20.5a2.2 2.2 0 0 0 4 0" /></>,
  heart: <path d="M12 20s-7-4.4-7-9.2A4 4 0 0 1 12 8a4 4 0 0 1 7-2.8c0 4.8-7 14.8-7 14.8z" />,
  // states
  breath: <><path d="M3 9h11a3 3 0 1 0-3-3" /><path d="M3 14h14a3 3 0 1 1-3 3" /></>,
  sparkle: <><path d="M12 3.5 13.6 9 19 10.5 13.6 12 12 17.5 10.4 12 5 10.5 10.4 9z" /><path d="M18.5 16.5l.7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7z" /></>,
  pin: <><path d="M12 21s6-5.4 6-10a6 6 0 1 0-12 0c0 4.6 6 10 6 10z" /><circle cx="12" cy="11" r="2.4" /></>,
};

export default function Icon({ name, className = "h-4 w-4" }) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      className={`${className} shrink-0`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {d}
    </svg>
  );
}
