import containerQueries from "@tailwindcss/container-queries";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        surface: {
          base: "#0a0d12",
          card: "#10141b",
          sunken: "#0d1117",
          raised: "#151a22",
          border: "#1b2028",
          divider: "#161b23",
        },
        brand: {
          DEFAULT: "#7c83ff",
          soft: "#8b93ff",
          muted: "#2a2e4a",
        },
        up: "#19c37d",
        down: "#ff5c62",
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.02) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [containerQueries],
};
