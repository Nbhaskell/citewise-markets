import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API is reached through this proxy, so the browser sees one origin.
const API = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true, // the API only allows requests from localhost:5173 and :3000
    proxy: { "/api": API, "/health": API },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
