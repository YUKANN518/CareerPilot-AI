$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$runtime = Join-Path $root "data\runtime\demo"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend virtual environment is missing: $python"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
  throw "Frontend dependencies are missing. Run npm install in frontend first."
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null

# Demo mode is deliberately isolated from the developer's normal database and
# never needs external AI credentials.
$env:APP_ENV = "demo"
$env:DATABASE_URL = "sqlite:///../data/runtime/demo/careerpilot-demo.db"
$env:UPLOAD_DIRECTORY = "../data/runtime/demo/uploads"
$env:FAISS_INDEX_DIR = "../data/runtime/demo/vector_store"
$env:AI_PROVIDER = "mock"
$env:DIFY_PROVIDER_MODE = "fake"
$env:EMBEDDING_PROVIDER = "fake"
$env:DEMO_ADMIN_ENABLED = "true"
$env:DEMO_ADMIN_EMAIL = "admin@careerpilot.local"
$env:DEMO_ADMIN_PASSWORD = "Admin123456!"
$env:JWT_SECRET_KEY = "careerpilot-demo-only-secret-key-32-characters"

Push-Location $backend
try {
  & $python -m scripts.check_demo_config
  & $python -m alembic upgrade head
  & $python -m scripts.seed_demo
} finally {
  Pop-Location
}

$backendProcess = Start-Process `
  -FilePath $python `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory $backend `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $runtime "backend.log") `
  -RedirectStandardError (Join-Path $runtime "backend-error.log") `
  -PassThru

$frontendProcess = Start-Process `
  -FilePath "npm.cmd" `
  -ArgumentList "run", "dev" `
  -WorkingDirectory $frontend `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $runtime "frontend.log") `
  -RedirectStandardError (Join-Path $runtime "frontend-error.log") `
  -PassThru

Write-Host ""
Write-Host "CareerPilot demo started."
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "API docs: http://127.0.0.1:8000/docs"
Write-Host "Admin: admin@careerpilot.local / Admin123456!"
Write-Host "Processes: backend=$($backendProcess.Id), frontend=$($frontendProcess.Id)"
Write-Host "Logs: $runtime"
