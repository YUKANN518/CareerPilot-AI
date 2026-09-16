# Phase 5 — Portfolio Engineering Report

Date: 2026-09-16

## Executive result

CareerPilot AI now has the release engineering baseline for a public portfolio repository:
locked dependencies, reproducible Demo/Fake configuration, Docker assets, CI configuration,
privacy rules, a license, an architecture document, and a first Git commit.

The only unresolved validation item is the local Docker runtime. Docker Compose configuration
parses successfully, but Docker Desktop's Linux backend/VM did not become available, so a real
image build and container smoke run could not be honestly marked as passed.

## Dependency lock

| Area | Implementation | Result |
| --- | --- | --- |
| Python | `backend/uv.lock`, uv `0.12.15`, Python 3.12 | `uv lock --check` and `uv sync --locked --extra dev` passed |
| Node | Existing `frontend/package-lock.json` | `npm ci` passed in the source tree and clean clone |
| Audit | `npm audit --json` | 0 critical, 4 high, 6 moderate, 0 low/info |

No `npm audit fix --force` was run. The production ECharts advisory and development-tool
advisories are documented in [DEPENDENCY_SECURITY_REPORT.md](DEPENDENCY_SECURITY_REPORT.md) and
require a separate compatibility review before major upgrades.

## Docker

Added:

- `backend/Dockerfile` — Python 3.12, locked uv install, non-root runtime user.
- `frontend/Dockerfile` — Node 20 build stage and Nginx runtime stage.
- `frontend/nginx.conf` — SPA fallback for Vue Router.
- `compose.yaml` — isolated Demo/Fake backend and frontend, health checks, migration and demo
  seed commands, and a runtime-only bind mount under `data/runtime/docker-demo`.
- `.dockerignore` — excludes `.env`, local data, caches, virtual environments, node modules,
  and build output from image contexts.

Validation:

- Compose syntax/config: **PASS** (`docker compose config --quiet`).
- `docker compose build --no-cache`: **BLOCKED_ENVIRONMENT**. Docker Desktop's Linux engine
  returned API 500/unavailable and its own logs reported `backend is not running`.
- `docker compose up` and container smoke: **NOT RUN**, because build could not start.

This is an environment limitation, not a claimed application success. Re-run the two Docker
commands after Docker Desktop's Linux backend is healthy.

## CI

Added `.github/workflows/ci.yml` with two secret-free jobs:

- Backend: uv locked install, product Pytest, evaluation tests, Ruff, and mypy.
- Frontend: npm ci, type-check, ESLint, Vitest, and production build.

Both jobs use Demo/Fake behavior and do not need DeepSeek or Dify credentials. The YAML was
locally parsed successfully; it has not run on a remote GitHub repository because no remote was
configured.

## Privacy and publication hygiene

- `.env` remains local and ignored; `.env.example` contains placeholders only.
- The live provider key was checked only as `configured`; its value was never printed or written
  to a report.
- Exact-key scan: 0 publishable-file matches.
- Generic `sk-*`/long `Bearer` scan: 0 publishable-file matches.
- Local DBs, uploads, FAISS indexes, runtime data, logs, caches, `node_modules`, and virtual
  environments are ignored.
- DOCX fixture scan found only the synthetic `example.test` email domain; no real-looking phone
  number or government ID was found.
- See [PUBLICATION_SECURITY_CHECKLIST.md](PUBLICATION_SECURITY_CHECKLIST.md) and
  [DATA_PRIVACY_CHECKLIST.md](DATA_PRIVACY_CHECKLIST.md).

## Git

The repository was initialized on branch `main` after the privacy cleanup. The first release
commit is `0e0a13a` (`feat: prepare CareerPilot AI portfolio release`); the final documentation
follow-up is `5a93bc6` (`docs: finalize publication guidance`). The working tree is clean and no
remote was added or pushed.

## Clean clone test

An isolated clone was created outside the workspace. It confirmed that the clone contains no
`.env` or local database and then passed:

- Python 3.12 `uv sync --locked --extra dev`.
- Full Alembic migration to head in an isolated SQLite runtime directory.
- `scripts.check_demo_config` in Demo/Fake mode.
- `npm ci` and the frontend production build.

## Native regression status

| Check | Result |
| --- | --- |
| Backend product Pytest | **PASS** — 222 passed |
| Evaluation tests | **PASS** — 8 passed |
| Ruff | **PASS** |
| mypy | **PASS** — 111 source files |
| TypeScript | **PASS** |
| ESLint | **PASS** |
| Vitest | **PASS** — 25 files / 91 tests |
| Frontend build | **PASS** |
| Playwright | **PASS** — existing Phase 4.7 run, 16 tests |
| Alembic | **PASS** — isolated database reached `f4b7c8d9e012 (head)` |

## Repository structure

The public tree now has a clear boundary:

- `backend/` — FastAPI application, Alembic migrations, tests, evaluation helpers, and uv lock.
- `frontend/` — Vue 3/TypeScript application, unit/e2e tests, npm lock, and production image.
- `evaluation/` — deterministic datasets, metrics, expected outputs, and evaluation tests.
- `sample_data/` — fictional Demo/Fake fixtures.
- `docs/ARCHITECTURE.md` — frozen core/optional architecture diagram.
- Root reports — audit, privacy, evaluation, dependency, and phase evidence.

## Remaining limitations

1. Docker image build/up/smoke still needs to be run on a healthy Docker Desktop Linux backend.
2. `npm audit` advisories remain documented and intentionally unfixed with force; upgrades need a
   dedicated compatibility change.
3. Real Dify connectivity remains an Optional Integration, not a Core Portfolio requirement.
4. The real Job parser remains validation-only; production matching intentionally consumes manual
   or structured deterministic job input.

## Scope integrity

**No matching algorithm, weights, thresholds, blocking rules or holdout labels were changed.**
No new AI feature, Job Parser API, agent, RAG workflow, matching dimension, or recommendation
threshold was added in Phase 5. `FEATURE_SCOPE_FROZEN = true` remains in effect.

## Portfolio readiness

```text
FEATURE_SCOPE_FROZEN = true
READY_FOR_PUBLIC_GITHUB = false
```

`READY_FOR_PUBLIC_GITHUB` is false only because the requested real Docker build/up validation was
blocked by the local Docker Desktop engine. All source, lock, privacy, CI, Git, clean-clone, and
native regression work is complete.
