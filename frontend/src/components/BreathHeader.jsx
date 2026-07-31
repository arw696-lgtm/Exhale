import React from "react";
import ThemeToggle from "./ThemeToggle.jsx";
import { weekTenor } from "../data/tenor.js";

/**
 * Breath Header — the Today screen opens with a breath, not a dashboard.
 *
 * Reads the week's emotional temperature from the briefing and says it plainly:
 * a clear week gets relief, a full one gets steadiness — never alarm. The glow
 * behind it literally inhales and exhales (stilled under reduced-motion). This
 * is the thesis made into the first thing you see.
 */
function timeGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function BreathHeader({ user, briefing, inviteCode, onLogout }) {
  const first = user?.display_name?.trim().split(/\s+/)[0];
  // One source of truth with the Breath Glance — the two can never disagree.
  const { headline, sub } = weekTenor(briefing);

  return (
    <header className="relative mb-8 overflow-hidden">
      {/* the breath */}
      <div
        aria-hidden="true"
        className="breath-orb pointer-events-none absolute -left-16 -top-24 h-64 w-64 rounded-full"
        style={{
          background:
            "radial-gradient(circle at 40% 40%, rgba(124,157,150,0.28), transparent 66%)",
          filter: "blur(8px)",
        }}
      />

      <div className="relative">
        {/* top bar — household on the left, theme + logout on the right */}
        <div className="mb-6 flex items-center justify-between font-micro text-xs text-sanctuary-navy/50">
          <span>
            {user ? (
              <>
                {user.display_name}'s household
                {inviteCode && (
                  <span className="ml-2 rounded-full bg-sage-release/15 px-2 py-0.5 font-semibold text-sanctuary-navy/60">
                    invite code: {inviteCode}
                  </span>
                )}
              </>
            ) : (
              <span aria-hidden="true">&nbsp;</span>
            )}
          </span>
          <div className="flex items-center gap-1">
            <ThemeToggle />
            {user && onLogout && (
              <button onClick={onLogout} className="ml-1 underline-offset-2 hover:underline">
                Log out
              </button>
            )}
          </div>
        </div>

        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.16em] text-sage-release">
          {briefing.week_of
            ? /^week of/i.test(briefing.week_of)
              ? briefing.week_of
              : `Week of ${briefing.week_of}`
            : "This week"}
        </p>
        {first && (
          <h1 className="mt-2 font-interface text-2xl font-semibold tracking-interface text-sanctuary-navy">
            {timeGreeting()}, {first}
          </h1>
        )}
        <p className="mt-3 font-display text-[2.1rem] italic leading-[1.06] text-sanctuary-navy">
          {headline[0]}
          <br />
          {headline[1]}
        </p>
        <p className="mt-3 max-w-md font-micro text-sm leading-relaxed text-sanctuary-navy/60">
          {sub}
        </p>
      </div>
    </header>
  );
}
