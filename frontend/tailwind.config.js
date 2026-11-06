/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: { DEFAULT: "#0a0b0e", 800: "#121318", 700: "#1a1c23", 600: "#23262f" },
        edge: "#2a2d37",
        accent: { DEFAULT: "#4f9dff", dim: "#2f6fc0" },
        good: "#36d399",
        warn: "#fbbd23",
        bad: "#f87272",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
