import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "var(--brand-50)",
          500: "var(--brand)",
          600: "var(--brand-600)",
        },
        ink: {
          DEFAULT: "var(--ink)",
          900: "var(--ink)",
          700: "var(--ink-2)",
          500: "var(--ink-3)",
          300: "var(--ink-3)",
        },
        paper: "var(--paper)",
        midnight: "var(--midnight)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
