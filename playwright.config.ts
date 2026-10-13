import { defineConfig } from "@playwright/test";

// Use dedicated ports and fail if occupied; never reuse an unrelated service.
export default defineConfig({
  testDir: "./tests/e2e",
  workers: 1,
  retries: 0,
  timeout: 15_000,
  use: { baseURL: "http://127.0.0.1:5174", headless: true },
  webServer: {
    command: "bash scripts/codex/start.sh",
    url: "http://127.0.0.1:5174/api/v1/health",
    env: {
      FEA_API_PORT: "8001",
      FEA_WEB_PORT: "5174",
      FEA_ENV: "test",
      FEA_AUTH_MODE: "local",
      FEA_BIND_HOST: "127.0.0.1",
    },
    reuseExistingServer: false,
    timeout: 60_000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
  },
});
