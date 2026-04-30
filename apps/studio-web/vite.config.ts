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
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
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
