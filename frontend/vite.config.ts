import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev server: same-origin /api, /static and /health calls are forwarded
// to the FastAPI backend.
// Pinned to :4200 so the backend's default FRONTEND_ORIGIN CORS list works.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 4200,
    // Fail fast instead of silently moving to :4201.
    strictPort: true,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/static": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    // Keep the dist layout so scripts/build_ui keeps working:
    // output lands in frontend/dist/frontend/browser.
    outDir: "dist/frontend/browser",
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
  },
});
