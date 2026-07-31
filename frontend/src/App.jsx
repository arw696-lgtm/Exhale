import React, { useCallback, useEffect, useState } from "react";
import BreathGlance from "./components/BreathGlance.jsx";
import WeeklyBriefing from "./components/WeeklyBriefing.jsx";
import WeeklyReflection from "./components/WeeklyReflection.jsx";
import CalendarScreen from "./components/CalendarScreen.jsx";
import HouseholdScreen from "./components/HouseholdScreen.jsx";
import YouScreen from "./components/YouScreen.jsx";
import TabBar from "./components/TabBar.jsx";
import HelperHome from "./components/HelperHome.jsx";
import DraftModal from "./components/DraftModal.jsx";
import AuthScreen from "./components/AuthScreen.jsx";
import {
  approveAction,
  DEMO_FAMILY,
  fetchBriefing,
  fetchDrafts,
  fetchMe,
  logout,
} from "./data/api.js";

export default function App() {
  // phase: "loading" | "auth" | "ready"
  const [phase, setPhase] = useState("loading");
  const [me, setMe] = useState(null); // {user_id, display_name, family_id, invite_code}
  const [briefing, setBriefing] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [source, setSource] = useState(null);
  const [openObligationId, setOpenObligationId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("today");
  // The Breath Glance is the opening state every day; the reflection is one
  // tap away (a prominent CTA on Sundays, the quiet link otherwise).
  const [reviewOpen, setReviewOpen] = useState(false);
  // "Handled. One thing lighter." — the counting-down confirmation.
  const [lighter, setLighter] = useState(false);

  const familyId = me?.family_id ?? DEMO_FAMILY;

  const loadData = useCallback(async (fid) => {
    const result = await fetchBriefing(fid);
    if (result.authRequired) {
      setPhase("auth");
      return;
    }
    const draftMap = result.source === "api" ? await fetchDrafts(fid) : {};
    setBriefing(result.briefing);
    setSource(result.source);
    setDrafts(draftMap);
    setPhase("ready");
  }, []);

  // Boot: restore session from stored token, else probe whether the backend
  // allows anonymous access (dev/demo mode) or demands login.
  useEffect(() => {
    (async () => {
      const restored = await fetchMe();
      if (restored) {
        setMe(restored);
        // A helper never loads the household briefing (they'd be denied);
        // their scoped home fetches its own data.
        if (restored.role === "HELPER") {
          setPhase("ready");
          return;
        }
        await loadData(restored.family_id);
      } else {
        await loadData(DEMO_FAMILY);
      }
    })();
  }, [loadData]);

  const handleAuthed = async (user) => {
    const restored = await fetchMe(); // pick up invite_code alongside the user
    const u = restored ?? user;
    setMe(u);
    if (u.role === "HELPER") {
      setPhase("ready");
      return;
    }
    setPhase("loading");
    await loadData(u.family_id);
  };

  const handleLogout = async () => {
    await logout();
    setMe(null);
    setBriefing(null);
    setPhase("auth");
  };

  const handleApprove = async () => {
    if (!openObligationId) return;
    setBusy(true);
    try {
      await approveAction(openObligationId, familyId);
      setOpenObligationId(null);
      await loadData(familyId); // resolved gap drops out of the briefing
      setLighter(true);
      setTimeout(() => setLighter(false), 3500);
    } catch (err) {
      console.error("Approval failed:", err.message);
    } finally {
      setBusy(false);
    }
  };

  if (phase === "auth") {
    return <AuthScreen onAuthed={handleAuthed} />;
  }

  // Scoped caregiver: their own home, not the household briefing.
  if (me?.role === "HELPER") {
    return (
      <HelperHome
        familyId={me.family_id}
        displayName={me.display_name}
        onLogout={handleLogout}
      />
    );
  }

  if (phase === "loading" || !briefing) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="font-display text-2xl italic text-sanctuary-navy/50">
          Exhale is preparing your briefing…
        </p>
      </div>
    );
  }

  const live = source === "api";
  const refresh = () => loadData(familyId);
  const needsCount = briefing.summary?.critical_count ?? briefing.critical_threats?.length ?? 0;
  const showReview = live && reviewOpen;
  const closeReview = () => setReviewOpen(false);

  return (
    <>
      {/* pb clears the fixed tab bar */}
      <div className="pb-28">
        {tab === "today" && showReview && (
          <WeeklyReflection
            familyId={familyId}
            live={live}
            user={me}
            onClose={closeReview}
          />
        )}
        {tab === "today" && !showReview && (
          <>
            {/* The opening state — most opens should end here. */}
            <BreathGlance
              briefing={briefing}
              drafts={drafts}
              user={me}
              inviteCode={me?.invite_code}
              onLogout={me ? handleLogout : undefined}
              onOpenDraft={setOpenObligationId}
              onOpenReview={live ? () => setReviewOpen(true) : undefined}
              detailId="week-detail"
            />
            <div id="week-detail">
              <WeeklyBriefing
                briefing={briefing}
                drafts={drafts}
                onOpenDraft={setOpenObligationId}
                user={me}
                inviteCode={me?.invite_code}
                onLogout={me ? handleLogout : undefined}
                familyId={familyId}
                live={live}
                onRefresh={refresh}
                onOpenReview={live ? () => setReviewOpen(true) : undefined}
                hideHero
              />
            </div>
          </>
        )}
        {tab === "calendar" && <CalendarScreen briefing={briefing} />}
        {tab === "household" && (
          <HouseholdScreen
            briefing={briefing}
            familyId={familyId}
            live={live}
            onRefresh={refresh}
          />
        )}
        {tab === "you" && (
          <YouScreen
            user={me}
            inviteCode={me?.invite_code}
            familyId={familyId}
            live={live}
            onLogout={me ? handleLogout : undefined}
          />
        )}

        {source === "fixture" && (
          <p className="pb-2 text-center font-micro text-xs text-sanctuary-navy/30">
            offline preview · backend not connected
          </p>
        )}
      </div>

      <TabBar active={tab} onChange={setTab} todayCount={needsCount} />

      {/* The counting-down confirmation — relief, not celebration. */}
      {lighter && (
        <div
          className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex justify-center"
          role="status"
        >
          <span className="rounded-full border border-sage-release/40 bg-surface px-5 py-2.5 font-display text-lg italic text-sanctuary-navy shadow-card">
            Handled. One thing lighter.
          </span>
        </div>
      )}

      <DraftModal
        draft={openObligationId ? drafts[openObligationId] : null}
        busy={busy}
        onApprove={handleApprove}
        onClose={() => setOpenObligationId(null)}
      />
    </>
  );
}
