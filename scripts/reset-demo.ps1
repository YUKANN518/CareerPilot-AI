$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend virtual environment is missing: $python"
}

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
  & $python -m scripts.seed_demo --reset-and-seed
} finally {
  Pop-Location
}

Write-Host "Anonymous demo data has been reset and re-seeded."
