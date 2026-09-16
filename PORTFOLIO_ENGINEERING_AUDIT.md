# CareerPilot AI — Portfolio Engineering Audit

Audit date: 2026-09-16. This is a pre-publication inventory. No private file is deleted by this
audit; local runtime data remains on disk until the publication staging step.

## MUST KEEP — source and reproducible fixtures

- `backend/app/`, `backend/alembic/`, `backend/tests/`, `backend/pyproject.toml` and
  `backend/alembic.ini` — FastAPI source, migrations, tests and Python dependency metadata.
- `frontend/src/`, `frontend/public/`, `frontend/tests/`, `frontend/package.json`,
  `frontend/package-lock.json`, TypeScript/Vite/Tailwind/ESLint/Playwright configuration.
- `evaluation/dataset/`, `evaluation/expected/`, `evaluation/tests/`, `evaluation/*.py` and
  `evaluation/README.md` — deterministic, synthetic evaluation source and tests.
- `sample_data/` — fictional, reviewable demo fixtures only; re-scan before publication.
- `scripts/start-demo.ps1`, `scripts/reset-demo.ps1`, `scripts/start-local.ps1` and the
  corresponding backend seed/E2E scripts.
- `.env.example` (to be added at repository root) as the public configuration contract.
- Curated architecture, methodology, privacy, capability and scope-freeze documentation.

## MUST IGNORE — never commit

- `.env` and any `.env.*` file except `.env.example`.
- `backend/.venv/`, `frontend/node_modules/`, Python/TypeScript caches, `__pycache__/`,
  `*.egg-info/`, `.coverage`, coverage databases and editor metadata.
- `data/runtime/`, `data/uploads/`, `data/faiss/`, `data/backups/`, SQLite files and logs.
- Frontend build/test output (`frontend/dist/`, `frontend/playwright-report/`,
  `frontend/test-results/`, `frontend/output/`) and temporary Vite caches.

## MUST REMOVE BEFORE PUBLICATION — local artifacts identified

The following are present locally and must be excluded from the first public commit (by ignore
rules or staging cleanup):

- Root `data/careerpilot.db` (local SQLite state).
- `data/uploads/` (uploaded PDF/DOCX files), `data/faiss/` (runtime indexes), and
  `data/runtime/` (Demo, E2E and Phase 4.6 databases, uploads and logs).
- `backend/.venv/`, `backend/*-cache/`, `backend/__pycache__/`, `backend/*.egg-info/`,
  `frontend/node_modules/`, and generated coverage/build/test artifacts.
- Root `output/` and `evaluation/results/_raw/` should remain generated/local unless an explicit
  review confirms that every included image and report is synthetic and useful.
- Any unreviewed screenshots, debug dumps, soak outputs or real-provider raw payloads. The
  existing real-provider public artifact is metadata-only and must not be replaced by raw output.

No deletion was performed during this audit. Private data should be moved outside the publication
staging tree or left in ignored runtime directories.

## GENERATED — reproducible outputs

- `evaluation/results/` (baseline, holdout, parsing and real-provider summary artifacts).
- `coverage-data`, `.coverage`, `backend/mypy-cache`, `backend/pytest-cache`, `.ruff_cache` and
  other test/type-check caches.
- `data/runtime/` databases, uploads, FAISS/vector stores and service logs.
- `uv.lock` (if generated), `frontend/package-lock.json` (committed Node lockfile), and Docker
  image/build layers (never source data).

## PRIVATE — do not publish

- Root `.env` contains a real local API key and local configuration.
- `data/careerpilot.db` and all files below `data/uploads/`, `data/faiss/` and
  `data/runtime/` are local state or user-upload-like artifacts, even when generated during
  testing.
- Any future logs or provider payloads containing resume text, Authorization headers, tokens or
  personal contact details.

## SOURCE — publication candidates

- Backend/frontend application source, migrations, tests, deterministic evaluation definitions,
  fictional `sample_data/`, public-safe scripts, `.env.example`, Docker/Compose/CI files to be
  added in Phase 5, `LICENSE`, and concise README/docs.
- Historical Phase reports may remain during engineering, but should be moved under
  `docs/development/` only after link impact is checked. They are not runtime data.

## Immediate engineering findings

1. Python has a valid `pyproject.toml` but no `uv.lock`; the `uv` executable is not currently
   installed, so lock generation must be evaluated before changing dependency management.
2. Node has a committed `frontend/package-lock.json`; clean-install verification must use
   `npm ci` and include type-check, lint, unit tests and build.
3. A root `.env.example` is missing even though README documents root-level setup; it should be
   added without copying any secret value.
4. Dockerfiles, Compose, CI, Git metadata and a public license are not yet present.
5. Existing Demo Mode already isolates SQLite/uploads/vector data and uses Mock/Fake providers;
   it is the correct default for Docker and CI.

