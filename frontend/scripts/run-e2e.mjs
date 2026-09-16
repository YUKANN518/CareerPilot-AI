import { existsSync } from "node:fs"
import { join, resolve } from "node:path"
import { spawn, spawnSync } from "node:child_process"
import { tmpdir } from "node:os"

const frontendDirectory = resolve(import.meta.dirname, "..")
const backendDirectory = resolve(frontendDirectory, "..", "backend")
const backendPythonCandidate =
  process.platform === "win32"
    ? join(backendDirectory, ".venv", "Scripts", "python.exe")
    : join(backendDirectory, ".venv", "bin", "python")
const backendPython = existsSync(backendPythonCandidate)
  ? backendPythonCandidate
  : "python"
const playwrightCli = join(
  frontendDirectory,
  "node_modules",
  "@playwright",
  "test",
  "cli.js",
)
const viteCli = join(frontendDirectory, "node_modules", "vite", "bin", "vite.js")
const childEnvironment = {
  ...process.env,
  VITE_CACHE_DIR: join(tmpdir(), "careerpilot-playwright-runtime", "vite-cache"),
}

const backend = spawn(backendPython, ["-m", "scripts.run_e2e"], {
  cwd: backendDirectory,
  env: childEnvironment,
  stdio: "inherit",
  windowsHide: true,
})
const vite = spawn(
  process.execPath,
  [viteCli, "--configLoader", "runner", "--host", "127.0.0.1", "--port", "4173"],
  {
    cwd: frontendDirectory,
    env: childEnvironment,
    stdio: "inherit",
    windowsHide: true,
  },
)

function stopTree(child) {
  if (!child.pid) return
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    })
  } else {
    child.kill("SIGTERM")
  }
}

async function waitFor(url, child, label) {
  const deadline = Date.now() + 120_000
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`${label} exited before becoming ready`)
    }
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // The service is still starting.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250))
  }
  throw new Error(`${label} did not become ready within 120 seconds`)
}

let exitCode = 1
try {
  await Promise.all([
    waitFor("http://127.0.0.1:8000/api/health", backend, "FastAPI"),
    waitFor("http://127.0.0.1:4173", vite, "Vite"),
  ])
  const result = spawnSync(
    process.execPath,
    [playwrightCli, "test", ...process.argv.slice(2)],
    {
      cwd: frontendDirectory,
      env: { ...childEnvironment, PW_EXTERNAL_SERVERS: "1" },
      stdio: "inherit",
      windowsHide: true,
    },
  )
  exitCode = result.status ?? 1
} finally {
  stopTree(vite)
  stopTree(backend)
}

process.exit(exitCode)
