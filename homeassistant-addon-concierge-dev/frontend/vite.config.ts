/// <reference types="vitest/config" />
import { defineConfig } from "vite";

export default defineConfig({
  // Relative asset URLs: the app is served under Supervisor ingress's
  // dynamic path prefix, so absolute paths would 404.
  base: "",
  server: {
    // Dev-mode proxy to the backend (uv run python -m concierge).
    proxy: {
      "/agui": "http://127.0.0.1:8098",
      "/threads": "http://127.0.0.1:8098",
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    include: ["tests/**/*.test.ts"],
  },
});
