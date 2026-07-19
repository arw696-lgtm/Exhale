/**
 * Exhale Brand System — single source of truth (Blueprint §8).
 *
 * The consumer identity projects sensory relief, emotional de-escalation, and
 * high data reliability. Palette follows the 60/20/10/10 balance in §8.
 */

export const palette = {
  // 60% Dominant — Structure & Texts
  sanctuaryNavy: "#1A2B4C",
  // 20% Medium — Interactions & Success / verified graph states
  sageRelease: "#7C9D96",
  // 10% Call-out — Threat architecture (attention without red-alert anxiety)
  loomingAmber: "#E29578",
  // 10% Canvas — Clutter isolation / breathing room
  pureBreath: "#F8F9FA",
  // Card surface
  pureWhite: "#FFFFFF",
};

export const typography = {
  // Display Header & H1 — editorial, premium lifestyle
  display: "'Instrument Serif', ui-serif, Georgia, serif",
  // Subheadings & core interface — dense, geometric
  interface: "'Inter Tight', system-ui, -apple-system, sans-serif",
  // System labels & ingestion logs — humanist, clean down to 12px
  microData: "'Plus Jakarta Sans', system-ui, sans-serif",
};

/** Threat stratification presentation (Blueprint §7.3). */
export const threatPresentation = {
  CRITICAL: { label: "CRITICAL", indicator: "🔴", accent: palette.loomingAmber },
  IMPORTANT: { label: "IMPORTANT", indicator: "🟡", accent: palette.sageRelease },
  ADVISORY: { label: "ADVISORY", indicator: "🔵", accent: palette.sanctuaryNavy },
};

/** Component tokens (Blueprint §8.3). */
export const components = {
  cardRadius: "16px",
  cardShadow: "0 12px 24px rgba(26, 43, 76, 0.04)",
  threatBarWidth: "4px",
};
