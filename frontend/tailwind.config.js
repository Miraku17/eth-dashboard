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
          base: "#0a0d12",     // body bg
          card: "#10141b",     // panel bg
          sunken: "#0d1117",   // subtle darker blocks (tables)
          raised: "#151a22",   // hover / elevated rows
          border: "#1b2028",   // panel borders
          divider: "#161b23",  // inner dividers
        },
        brand: {
          DEFAULT: "#7c83ff",  // Ethereum-ish violet
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
  plugins: [],
};
