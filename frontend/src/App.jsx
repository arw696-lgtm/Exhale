import React, { useCallback, useEffect, useState } from "react";
import WeeklyBriefing from "./components/WeeklyBriefing.jsx";
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

  return (
    <>
      <WeeklyBriefing
        briefing={briefing}
        drafts={drafts}
        onOpenDraft={setOpenObligationId}
        user={me}
        inviteCode={me?.invite_code}
        onLogout={me ? handleLogout : undefined}
        familyId={familyId}
        live={source === "api"}
        onRefresh={() => loadData(familyId)}
      />
      <DraftModal
        draft={openObligationId ? drafts[openObligationId] : null}
        busy={busy}
        onApprove={handleApprove}
        onClose={() => setOpenObligationId(null)}
      />
      {source === "fixture" && (
        <p className="pb-6 text-center font-micro text-xs text-sanctuary-navy/30">
          offline preview · backend not connected
        </p>
      )}
    </>
  );
}
