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
      },
      fontFamily: {
        display: ["'Instrument Serif'", "ui-serif", "Georgia", "serif"],
        interface: ["'Inter Tight'", "system-ui", "-apple-system", "sans-serif"],
        micro: ["'Plus Jakarta Sans'", "system-ui", "sans-serif"],
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
