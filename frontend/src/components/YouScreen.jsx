import React from "react";
import ThemeToggle from "./ThemeToggle.jsx";
import WorkWindowsPanel from "./WorkWindowsPanel.jsx";

/**
 * You — the member's own corner. Their account, their personal time-finding
 * ("Find Your Time"), and the app's own settings (theme, sign out). Small by
 * design; this is where the household stuff gets out of the way.
 */
export default function YouScreen({ user, inviteCode, familyId, live, onLogout }) {
  const first = user?.display_name?.trim().split(/\s+/)[0];

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6">
        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.16em] text-sage-release">
          You
        </p>
        <h1 className="mt-2 font-display text-[2rem] italic text-sanctuary-navy">
          {first ? first : "Your corner"}
        </h1>
      </header>

      {user && (
        <section className="mb-8 rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
          <dl className="space-y-2 font-micro text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-sanctuary-navy/50">Name</dt>
              <dd className="font-semibold text-sanctuary-navy">{user.display_name}</dd>
            </div>
            {user.email && (
              <div className="flex justify-between gap-4">
                <dt className="text-sanctuary-navy/50">Email</dt>
                <dd className="text-sanctuary-navy/80">{user.email}</dd>
              </div>
            )}
            {inviteCode && (
              <div className="flex items-center justify-between gap-4 border-t border-sanctuary-navy/10 pt-2">
                <dt className="text-sanctuary-navy/50">Family invite code</dt>
                <dd className="rounded-full bg-sage-release/15 px-2.5 py-0.5 font-semibold tracking-widest text-sanctuary-navy">
                  {inviteCode}
                </dd>
              </div>
            )}
          </dl>
        </section>
      )}

      {/* Personal time-finding — "when can I actually work / take time?" */}
      {live && <WorkWindowsPanel familyId={familyId} />}

      <section className="mb-8 rounded-[22px] border border-sanctuary-navy/10 bg-surface p-5 shadow-card">
        <h2 className="mb-3 font-interface text-[11px] font-semibold uppercase tracking-[0.13em] text-sanctuary-navy/45">
          Settings
        </h2>
        <div className="flex items-center justify-between font-micro text-sm">
          <span className="text-sanctuary-navy/70">Appearance</span>
          <ThemeToggle />
        </div>
        {onLogout && (
          <button
            onClick={onLogout}
            className="mt-4 w-full rounded-full border border-sanctuary-navy/15 py-2.5 font-micro text-sm font-medium text-sanctuary-navy transition hover:bg-pure-breath"
          >
            Sign out
          </button>
        )}
      </section>
    </main>
  );
}
