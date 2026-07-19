/** @type {import('tailwindcss').Config} */
// Brand tokens mirror src/brand/tokens.js (Blueprint §8).
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        "sanctuary-navy": "#1A2B4C",
        "sage-release": "#7C9D96",
        "looming-amber": "#E29578",
        "pure-breath": "#F8F9FA",
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
