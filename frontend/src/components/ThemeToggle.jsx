import React, { useState } from "react";

/**
 * Light/dark toggle. The whole app flips through CSS tokens (index.css), so
 * this only sets data-theme on <html> and remembers the choice — the viewer's
 * pick wins over the OS preference. Shared by the Today header and the You tab.
 */
function currentTheme() {
  if (typeof document !== "undefined") {
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "light" || attr === "dark") return attr;
  }
  return typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export default function ThemeToggle({ className = "" }) {
  const [theme, setTheme] = useState(currentTheme);
  const flip = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("exhale-theme", next);
    } catch (e) {
      /* storage unavailable — theme still applies for the page life */
    }
  };
  const dark = theme === "dark";
  return (
    <button
      onClick={flip}
      aria-label={dark ? "Switch to light" : "Switch to dark"}
      title={dark ? "Switch to light" : "Switch to dark"}
      className={
        "grid h-7 w-7 place-items-center rounded-full text-sanctuary-navy/55 transition hover:bg-sanctuary-navy/5 hover:text-sanctuary-navy " +
        className
      }
    >
      {dark ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}
