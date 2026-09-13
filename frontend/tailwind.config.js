/** @type {import('tailwindcss').Config} */
// Brand tokens mirror src/brand/tokens.js (Blueprint §8).
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Backed by CSS variables (RGB channels) so the whole brand palette
        // flips between light and dark from one place — see index.css. Alpha
        // modifiers (text-sanctuary-navy/70, border-…/10) keep working via
        // the <alpha-value> slot.
        "sanctuary-navy": "rgb(var(--ink) / <alpha-value>)",
        "sage-release": "rgb(var(--sage) / <alpha-value>)",
        "looming-amber": "rgb(var(--amber) / <alpha-value>)",
        "pure-breath": "rgb(var(--canvas) / <alpha-value>)",
        // Card/panel surface (was literal white).
        surface: "rgb(var(--surface) / <alpha-value>)",
        // Filled primary buttons — a solid navy that stays legible under white
        // text in BOTH themes (doesn't invert with the ink token).
        "ink-solid": "rgb(var(--ink-solid) / <alpha-value>)",
        // Text-safe accents. sage-release/looming-amber are decorative values
        // tuned for fills and halos; used as TEXT on a light ground they sit
        // at 2.95:1 and 2.39:1 — unreadable. Anything a person reads uses
        // these instead. See index.css.
        "sage-text": "rgb(var(--sage-text) / <alpha-value>)",
        "amber-text": "rgb(var(--amber-text) / <alpha-value>)",
      },
      fontFamily: {
        display: ["'Instrument Serif'", "ui-serif", "Georgia", "serif"],
        interface: ["'Inter Tight'", "system-ui", "-apple-system", "sans-serif"],
        micro: ["'Plus Jakarta Sans'", "system-ui", "sans-serif"],
      },
      // Type scale lifted for legibility: the old xs/sm (12/14px) carried
      // most of the app's body copy, which is too small to read comfortably
      // on a phone. Every step gains 1-2px and a roomier line-height.
      fontSize: {
        xs: ["0.8125rem", { lineHeight: "1.15rem" }],   // 13px (was 12)
        sm: ["0.9375rem", { lineHeight: "1.4rem" }],    // 15px (was 14)
        base: ["1.0625rem", { lineHeight: "1.6rem" }],  // 17px (was 16)
        lg: ["1.1875rem", { lineHeight: "1.75rem" }],   // 19px (was 18)
      },
      borderRadius: {
        card: "16px",
      },
      boxShadow: {
        // Low-impact soft drop elevation (§8.3).
        card: "0 12px 24px rgba(26, 43, 76, 0.04)",
      },
      letterSpacing: {
        interface: "-0.02em",
      },
    },
  },
  plugins: [],
};
