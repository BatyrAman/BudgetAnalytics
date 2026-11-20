import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "."),
      // `server-only` throws outside a React Server environment; tests import server modules directly.
      "server-only": path.resolve(import.meta.dirname, "tests/server-only-stub.ts"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", "e2e/**", ".next/**"],
    restoreMocks: true,
    // UI tests type into jsdom with user-event; under a full parallel run on a
    // loaded machine they can exceed Vitest's 5 s default without being wrong.
    // One project-wide limit instead of per-file overrides.
    testTimeout: 20_000,
  },
});
