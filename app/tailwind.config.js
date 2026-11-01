/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", '"SF Pro Text"', '"Segoe UI"', "Roboto", "sans-serif"],
        serif: ['"Iowan Old Style"', '"Charter"', '"Source Serif Pro"', "Georgia", "serif"],
        mono: ['"SF Mono"', "ui-monospace", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        fg: { DEFAULT: "#0d0d0d", 2: "#5d5d5d", 3: "#8f8f8f", 4: "#b4b4b4" },
        line: { DEFAULT: "#e5e5e5", soft: "#efefef" },
        surface: { DEFAULT: "#f9f9f9", 2: "#f4f4f4", 3: "#ececec" },
        ok: "#15803d",
        bad: "#b91c1c",
        warn: "#b45309",
        cache: "#c2410c",
        focus: "#2563eb",
      },
      boxShadow: {
        composer: "0 0 0 1px rgba(0,0,0,.04), 0 2px 6px rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.06)",
        pop: "0 0 0 1px rgba(0,0,0,.06), 0 8px 28px rgba(0,0,0,.12)",
      },
      keyframes: {
        shimmer: { "0%": { backgroundPosition: "100% 0" }, "100%": { backgroundPosition: "-100% 0" } },
        rec: { "50%": { opacity: ".35" } },
      },
      animation: {
        shimmer: "shimmer 1.8s linear infinite",
        rec: "rec 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
