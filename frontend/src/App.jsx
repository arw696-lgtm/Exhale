import React, { useEffect, useState } from "react";
import WeeklyBriefing from "./components/WeeklyBriefing.jsx";
import { fetchBriefing } from "./data/api.js";

export default function App() {
  const [briefing, setBriefing] = useState(null);
  const [source, setSource] = useState(null);

  useEffect(() => {
    let active = true;
    fetchBriefing().then(({ briefing, source }) => {
      if (!active) return;
      setBriefing(briefing);
      setSource(source);
    });
    return () => {
      active = false;
    };
  }, []);

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
      <WeeklyBriefing briefing={briefing} />
      {source === "fixture" && (
        <p className="pb-6 text-center font-micro text-xs text-sanctuary-navy/30">
          offline preview · backend not connected
        </p>
      )}
    </>
  );
}
