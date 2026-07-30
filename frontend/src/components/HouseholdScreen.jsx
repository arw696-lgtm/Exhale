import React from "react";
import ConnectionsPanel from "./ConnectionsPanel.jsx";
import CostMeterPanel from "./CostMeterPanel.jsx";
import HelperInvitePanel from "./HelperInvitePanel.jsx";
import LearningScoreboard from "./LearningScoreboard.jsx";
import PhotoDrop from "./PhotoDrop.jsx";
import SetupPanel from "./SetupPanel.jsx";

/**
 * Household — the setup surface. Who's connected, who helps, and how the
 * household's coverage is configured. The operational panels live here so the
 * Today screen stays about the week, not the plumbing.
 */
export default function HouseholdScreen({ briefing, familyId, live, onRefresh }) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6">
        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.16em] text-sage-release">
          Household
        </p>
        <h1 className="mt-2 font-display text-[2rem] italic text-sanctuary-navy">
          Who's here, what's connected
        </h1>
      </header>

      {!live && (
        <div className="mb-8 rounded-[22px] border border-sanctuary-navy/10 bg-surface p-8 text-center shadow-card">
          <p className="font-display text-xl italic text-sanctuary-navy">Connect to set up.</p>
          <p className="mx-auto mt-2 max-w-xs font-micro text-sm text-sanctuary-navy/55">
            Sign in to configure your household, connect calendars, and invite
            helpers.
          </p>
        </div>
      )}

      {/* Is Exhale learning? — the instrument for the product's core promise. */}
      {live && <LearningScoreboard familyId={familyId} />}

      {/* Running costs — the unit-economics instrument (the Milo lesson). */}
      {live && <CostMeterPanel familyId={familyId} />}

      {/* Coverage model — the setup form shows until a household is configured. */}
      {live && briefing?.care_watch == null && (
        <SetupPanel familyId={familyId} onSaved={onRefresh} />
      )}
      {live && <PhotoDrop familyId={familyId} onChanged={onRefresh} />}
      {live && <ConnectionsPanel familyId={familyId} />}
      {live && <HelperInvitePanel familyId={familyId} />}
    </main>
  );
}
