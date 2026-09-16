from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import uvicorn


def configure_runtime() -> None:
    temp_root = Path(tempfile.gettempdir()).resolve()
    runtime = (temp_root / "careerpilot-e2e-runtime").resolve()
    if runtime.parent != temp_root:
        raise RuntimeError("Refusing to prepare an E2E runtime outside the system temp directory")
    runtime.mkdir(parents=True, exist_ok=True)
    database = runtime / "careerpilot.db"
    uploads = runtime / "uploads"
    faiss_index = runtime / "faiss"
    database.unlink(missing_ok=True)
    if uploads.exists():
        shutil.rmtree(uploads)
    if faiss_index.exists():
        shutil.rmtree(faiss_index)

    os.environ.update(
        {
            "APP_ENV": "test",
            "AUTO_CREATE_TABLES": "true",
            "DATABASE_URL": f"sqlite:///{database.as_posix()}",
            "UPLOAD_DIRECTORY": str(uploads),
            "AI_PROVIDER": "mock",
            "DIFY_PROVIDER_MODE": "fake",
            "EMBEDDING_PROVIDER": "fake",
            "FAISS_INDEX_DIR": str(faiss_index),
            "JWT_SECRET_KEY": "e2e-only-secret-key-with-at-least-32-characters",
        }
    )


def main() -> None:
    configure_runtime()
    from scripts.seed_e2e import seed

    seed()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
