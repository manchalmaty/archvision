/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Single accent — ArchVision red (the "AV" brand mark). Reuses the
        // `brand` token name so every bg-brand-*/text-brand-*/border-brand-*
        // utility follows the accent with no per-component edits.
        brand: {
          50: "#fef2f1",
          100: "#fcdcd9",
          400: "#f15a4f",
          500: "#e0261c", // ArchVision red
          600: "#c81f15", // primary button / hover-from
          700: "#a51810",
          900: "#5e0d09",
        },
        // Cool "drafting paper" surfaces
        surface: {
          dark: "#f8fafc", // app canvas (cool paper)
          panel: "#f1f5f9", // side panels
          card: "#ffffff", // cards / drawing sheet
          border: "#e2e8f0", // hairline borders
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
