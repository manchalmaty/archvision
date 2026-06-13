/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Single accent — "blueprint blue" (matches the brand logo).
        // Reuses the `brand` token name so existing bg-brand-*/text-brand-*
        // utilities follow the accent with no per-component edits.
        brand: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
          900: "#0c4a6e",
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
