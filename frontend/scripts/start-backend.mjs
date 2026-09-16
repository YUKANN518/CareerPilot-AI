import { existsSync, mkdirSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { spawn, spawnSync } from "node:child_process"

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const frontendDirectory = resolve(scriptDirectory, "..")
const backendDirectory = resolve(frontendDirectory, "..", "backend")
const candidatePython = process.env.BACKEND_PYTHON
  ? resolve(process.env.BACKEND_PYTHON)
  : process.platform === "win32"
    ? join(backendDirectory, ".venv", "Scripts", "python.exe")
    : join(backendDirectory, ".venv", "bin", "python")
const python = existsSync(candidatePython) ? candidatePython : "python"

const runtimeDirectory = join(tmpdir(), "careerpilot-e2e-runtime")
const databasePath = join(runtimeDirectory, "careerpilot.db")
const uploadDirectory = join(runtimeDirectory, "uploads")
mkdirSync(runtimeDirectory, { recursive: true })
rmSync(databasePath, { force: true })
rmSync(uploadDirectory, { recursive: true, force: true })

const databaseUrl = `sqlite:///${databasePath.replaceAll("\\", "/")}`
const environment = {
  ...process.env,
  APP_ENV: "test",
  AUTO_CREATE_TABLES: "true",
  DATABASE_URL: databaseUrl,
  UPLOAD_DIRECTORY: uploadDirectory,
  AI_PROVIDER: "mock",
  JWT_SECRET_KEY: "e2e-only-secret-key-with-at-least-32-characters",
}
const seed = spawnSync(python, ["-m", "scripts.seed_e2e"], {
  cwd: backendDirectory,
  env: environment,
  stdio: "inherit",
})
if (seed.status !== 0) {
  process.exit(seed.status ?? 1)
}

const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
  {
    cwd: backendDirectory,
    env: environment,
    stdio: "inherit",
  },
)

function stop(signal) {
  if (!child.killed) {
    child.kill(signal)
  }
}

process.on("SIGINT", () => stop("SIGINT"))
process.on("SIGTERM", () => stop("SIGTERM"))
child.on("exit", (code) => {
  process.exit(code ?? 0)
})
