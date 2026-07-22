/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev-time proxy to the local backend (docs/frontend-architecture.md §7):
// the browser only ever talks same-origin, so no CORS configuration exists
// anywhere. Production serving is proposed as an additive FastAPI
// StaticFiles mount (PR3).
const BACKEND = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": BACKEND,
      "/health": BACKEND,
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
});
