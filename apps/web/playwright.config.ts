// Playwright end-to-end tests: a real browser clicks through the real app.
// The config builds the web app and starts a throwaway server (scripts/e2e_server.py)
// with a fake LLM and fresh databases, then runs tests/e2e/*.spec.ts against it.
import { defineConfig, devices } from "@playwright/test";

const python = process.env.PYTHON ?? (process.platform === "win32" ? "..\\..\\.venv\\Scripts\\python" : "python");

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:8010", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: `npm run build && ${python} ../../scripts/e2e_server.py 8010`,
    url: "http://127.0.0.1:8010/api/ping",
    timeout: 180_000,
    reuseExistingServer: false,
  },
});
