import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Allow the duckdns hostname so Vite doesn't reject requests forwarded
    // through Caddy. localhost stays allowed by default for local dev.
    allowedHosts: ["etherscope.duckdns.org"],
    proxy: {
      "/api": { target: "http://api:8000", changeOrigin: true },
    },
  },
});
