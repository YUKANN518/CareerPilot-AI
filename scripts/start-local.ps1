$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$runtime = Join-Path $root "data\runtime"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend virtual environment is missing: $python"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
  throw "Frontend dependencies are missing. Run npm install in frontend first."
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null

Push-Location $backend
try {
  & $python -m alembic upgrade head
} finally {
  Pop-Location
}

$backendLog = Join-Path $runtime "backend.log"
$backendErrorLog = Join-Path $runtime "backend-error.log"
$frontendLog = Join-Path $runtime "frontend.log"
$frontendErrorLog = Join-Path $runtime "frontend-error.log"

# Some Windows shells inherit both `Path` and `PATH`. PowerShell's Start-Process
# rejects that environment block, so use cmd's detached start command instead.
$backendCommand = "cd /d `"$backend`" && start `"`" /b `"$python`" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > `"$backendLog`" 2> `"$backendErrorLog`""
$frontendCommand = "cd /d `"$frontend`" && start `"`" /b npm.cmd run dev > `"$frontendLog`" 2> `"$frontendErrorLog`""
& cmd.exe /d /c $backendCommand
& cmd.exe /d /c $frontendCommand

Write-Host ""
Write-Host "CareerPilot local environment started without demo seeding."
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "API docs: http://127.0.0.1:8000/docs"
Write-Host "Processes: backend and frontend started in the background"
Write-Host "Logs: $runtime"
