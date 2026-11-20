import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the production build of the frontend and a real
 * FastAPI backend (see e2e/start-backend.sh). Nothing is mocked.
 */
const PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3100);
const BACKEND_URL = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8100";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "ru-RU",
    timezoneId: "Asia/Almaty",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `pnpm start -p ${PORT}`,
    url: `http://localhost:${PORT}/login`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { BACKEND_URL, NODE_ENV: "production" },
  },
});
