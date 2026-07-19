import React from "react";
import WeeklyBriefing from "./components/WeeklyBriefing.jsx";
import { briefingFixture } from "./data/briefingFixture.js";

export default function App() {
  return <WeeklyBriefing briefing={briefingFixture} />;
}
