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
        // Warm drawing-paper surfaces — the brand palette (#F7F4EE paper), not
        // Tailwind's cool slate: the UI inherits the sheet, not a SaaS shell.
        surface: {
          dark: "#f2efe7", // app canvas (paper under the sheet)
          panel: "#f7f4ee", // side panels (brand paper)
          card: "#fffdf8", // cards / drawing sheet
          border: "#e3ddcf", // hairline borders
        },
        // Warm ink ramp REPLACING Tailwind slate (anchored on brand gray
        // #8C8A85): every existing text-slate-*/border-slate-* utility
        // de-blues from this one table — same single-source trick as `brand`.
        slate: {
          50: "#f7f5f0",
          100: "#edeae1",
          200: "#dcd7c9",
          300: "#c4beaf",
          400: "#a39e90",
          500: "#7c7768",
          600: "#615c4f",
          700: "#4a463c",
          800: "#33302a",
          900: "#201e19",
        },
      },
      fontFamily: {
        sans: ["Golos Text", "system-ui", "sans-serif"],
        display: ["Unbounded", "Golos Text", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
