/**
 * Exhale API client — briefing data + auth sessions.
 *
 * The session token lives in localStorage and rides along as a Bearer header
 * on every call. `fetchBriefing` distinguishes three outcomes: live data,
 * auth required (401), or backend unreachable (bundled fixture fallback so the
 * UI always renders something in pure offline demos).
 */
import { briefingFixture } from "./briefingFixture.js";

const API_BASE = import.meta.env.VITE_EXHALE_API ?? "http://localhost:8000";
const DEMO_FAMILY = "family_demo_001";
const TOKEN_KEY = "exhale_token";

// --- session storage ---------------------------------------------------------
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode) — session lasts for the page life */
  }
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
}

// --- auth --------------------------------------------------------------------
/** Restore the session from a stored token. Returns the user or null. */
export async function fetchMe() {
  if (!getToken()) return null;
  try {
    const res = await apiFetch("/v1/me");
    if (!res.ok) {
      if (res.status === 401) setToken(null); // stale token
      return null;
    }
    return res.json();
  } catch {
    return null;
  }
}

async function sessionRequest(path, payload) {
  const res = await apiFetch(path, { method: "POST", body: JSON.stringify(payload) });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `HTTP ${res.status}`);
  setToken(body.token);
  return body;
}

export function signup({ email, password, displayName, inviteCode }) {
  return sessionRequest("/v1/auth/signup", {
    email,
    password,
    display_name: displayName,
    invite_code: inviteCode || null,
  });
}

export function login({ email, password }) {
  return sessionRequest("/v1/auth/login", { email, password });
}

export async function logout() {
  try {
    await apiFetch("/v1/auth/logout", { method: "POST" });
  } finally {
    setToken(null);
  }
}

// --- briefing data -----------------------------------------------------------
/**
 * @returns {Promise<{briefing: object, source: "api"|"fixture"} | {authRequired: true}>}
 */
export async function fetchBriefing(familyId = DEMO_FAMILY) {
  let res;
  try {
    res = await apiFetch(`/v1/families/${familyId}/briefing`);
  } catch (err) {
    console.warn("Exhale API unreachable, using bundled fixture:", err.message);
    return { briefing: briefingFixture, source: "fixture" };
  }
  if (res.status === 401 || res.status === 403) return { authRequired: true };
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return { briefing: await res.json(), source: "api" };
}

/** Drafts keyed by obligation id; empty map when unavailable. */
export async function fetchDrafts(familyId = DEMO_FAMILY) {
  try {
    const res = await apiFetch(`/v1/families/${familyId}/drafts`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { drafts } = await res.json();
    return Object.fromEntries(drafts.map((d) => [d.obligation_node_id, d]));
  } catch (err) {
    console.warn("Exhale drafts unreachable:", err.message);
    return {};
  }
}

/** Approve a drafted action; resolves the obligation on the backend. */
export async function approveAction(obligationNodeId, familyId = DEMO_FAMILY) {
  const res = await apiFetch(`/v1/families/${familyId}/actions/approve`, {
    method: "POST",
    body: JSON.stringify({ obligation_node_id: obligationNodeId }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export { DEMO_FAMILY };
