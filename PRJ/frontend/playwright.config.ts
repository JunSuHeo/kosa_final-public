import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  timeout: 45000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  outputDir: process.env.LIVE_PREVIEW_PROJECT_ID
    ? "test-results-live"
    : "test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5175",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
