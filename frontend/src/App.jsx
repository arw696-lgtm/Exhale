import React, { useCallback, useEffect, useState } from "react";
import WeeklyBriefing from "./components/WeeklyBriefing.jsx";
import DraftModal from "./components/DraftModal.jsx";
import { approveAction, fetchBriefing, fetchDrafts } from "./data/api.js";

export default function App() {
  const [briefing, setBriefing] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [source, setSource] = useState(null);
  const [openObligationId, setOpenObligationId] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [{ briefing, source }, draftMap] = await Promise.all([
      fetchBriefing(),
      fetchDrafts(),
    ]);
    setBriefing(briefing);
    setSource(source);
    setDrafts(draftMap);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleApprove = async () => {
    if (!openObligationId) return;
    setBusy(true);
    try {
      await approveAction(openObligationId);
      setOpenObligationId(null);
      await load(); // refresh: the resolved gap drops out of the briefing
    } catch (err) {
      console.error("Approval failed:", err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!briefing) {
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
