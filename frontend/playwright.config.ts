import { defineConfig, devices } from "@playwright/test"
import { join } from "node:path"
import { tmpdir } from "node:os"
import { resolve } from "node:path"

const playwrightRuntime = join(tmpdir(), "careerpilot-playwright-runtime")
const backendDirectory = resolve(import.meta.dirname, "..", "backend")
const backendPython =
  process.platform === "win32"
    ? join(backendDirectory, ".venv", "Scripts", "python.exe")
    : join(backendDirectory, ".venv", "bin", "python")

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: join(playwrightRuntime, "test-results"),
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: join(playwrightRuntime, "report") }],
  ],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.PW_EXTERNAL_SERVERS ? undefined : [
    {
      command: `"${backendPython}" -m scripts.run_e2e`,
      cwd: backendDirectory,
      url: "http://127.0.0.1:8000/api/health",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      gracefulShutdown: { signal: "SIGINT", timeout: 5_000 },
      stdout: "ignore",
      stderr: "ignore",
    },
    {
      command:
        "node node_modules/vite/bin/vite.js --configLoader runner --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      gracefulShutdown: { signal: "SIGINT", timeout: 5_000 },
      stdout: "ignore",
      stderr: "ignore",
      env: {
        VITE_CACHE_DIR: join(playwrightRuntime, "vite-cache"),
      },
    },
  ],
})
