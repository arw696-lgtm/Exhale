/**
 * Exhale API client.
 *
 * Fetches a live Weekly COO Briefing from the backend service
 * (`exhale.api`). The base URL is configurable via the `VITE_EXHALE_API`
 * env var and defaults to the local uvicorn dev server.
 */
import { briefingFixture } from "./briefingFixture.js";

const API_BASE = import.meta.env.VITE_EXHALE_API ?? "http://localhost:8000";
const DEMO_FAMILY = "family_demo_001";

/**
 * Fetch the demo household's briefing from the API. Falls back to the bundled
 * fixture if the backend is unreachable, so the UI always renders.
 *
 * @returns {Promise<{briefing: object, source: "api" | "fixture"}>}
 */
export async function fetchBriefing(familyId = DEMO_FAMILY) {
  try {
    const res = await fetch(`${API_BASE}/v1/families/${familyId}/briefing`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return { briefing: await res.json(), source: "api" };
  } catch (err) {
    console.warn("Exhale API unreachable, using bundled fixture:", err.message);
    return { briefing: briefingFixture, source: "fixture" };
  }
}
