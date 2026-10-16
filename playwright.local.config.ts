import { defineConfig } from "@playwright/test";

// Run this with Windows Node/PowerShell against a separately started WSL2
// backend. No Linux/headless/fallback browser can masquerade as Windows proof.
if (process.platform !== "win32")
  throw new Error(
    "Target-laptop evidence requires Windows Node and installed headed Chrome/Edge; use playwright.config.ts for cloud regression.",
  );
const baseURL = process.env.FEA_ACCEPTANCE_BASE_URL ?? "http://127.0.0.1:5173";
const url = new URL(baseURL);
if (
  url.protocol !== "http:" ||
  !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) ||
  url.username ||
  url.password ||
  url.pathname !== "/" ||
  url.search ||
  url.hash
)
  throw new Error(
    "Local acceptance connects only to a loopback HTTP application URL.",
  );
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: [
    "tutorials.spec.ts",
    "archives.spec.ts",
    "reports.spec.ts",
    "workspace.spec.ts",
  ],
  workers: 1,
  retries: 0,
  timeout: 15_000,
  outputDir: ".local/windows-acceptance-artifacts",
  reporter: [
    ["list"],
    ["json", { outputFile: ".local/windows-acceptance-results.json" }],
  ],
  use: { baseURL, headless: false },
  projects: [
    { name: "Windows-Chrome", use: { channel: "chrome" } },
    { name: "Windows-Edge", use: { channel: "msedge" } },
  ],
});
