import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Consulting palette: deep navy, slate, teal accent.
        navy: {
          50: "#eef2f7",
          700: "#1e3a5f",
          800: "#162c49",
          900: "#0f2238",
        },
        accent: {
          DEFAULT: "#0f9b8e",
          dark: "#0b7e73",
        },
        priority: {
          p0: "#b91c1c",
          p1: "#ea580c",
          p2: "#ca8a04",
          p3: "#0f766e",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
