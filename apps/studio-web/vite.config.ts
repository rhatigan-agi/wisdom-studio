import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_PORT = process.env.WISDOM_STUDIO_API_PORT ?? "8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
      "/agents": {
        // Per-agent SDK dashboard routes mounted by Studio's SessionManager.
        // Without the bypass, the SPA route /agents/<id> can't be hard-
        // reloaded in dev — Vite proxies *every* /agents/* request to the
        // backend, which 404s (the backend only mounts /agents/<id>/api/...
        // sub-apps lazily on first use). Bypass returns the SPA shell for
        // top-level navigations (Accept: text/html), letting SDK XHR/fetch
        // calls (Accept: application/json) still flow through the proxy.
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
        bypass: (req) => {
          const accept = req.headers.accept ?? "";
          if (req.method === "GET" && accept.includes("text/html")) {
            return "/index.html";
          }
          return undefined;
        },
      },
      "/ws": {
        target: `ws://localhost:${API_PORT}`,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 3000,
  },
});
