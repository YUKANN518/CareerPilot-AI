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

Initial Phase 5 validation was blocked while the Docker Desktop Linux backend was unavailable.
The follow-up verification below was run after the host/WSL2 repair.

## Docker verification follow-up (2026-09-16)

### Engine versions

- Docker Desktop: **4.91.0 (239619)**
- Docker Engine: **29.8.0** (API 1.56)
- Docker Compose: **v5.5.1**
- Context: `desktop-linux`, WSL2 kernel `6.18.33.2-microsoft-standard-WSL2`

### Verification results

- `docker version`: **PASS**.
- `docker info`: **PASS**; Linux engine reachable.
- `docker compose config`: **PASS**.
- `docker compose build --no-cache`: **BLOCKED_ENVIRONMENT**. Docker Hub/GHCR metadata and
  blob downloads were intermittently unavailable. After same-version mirror pre-pulls, the
  build reached the backend's locked uv install, but the Linux resolution downloaded a very
  large PyTorch/CUDA dependency set and made no further progress for an extended period. The
  build was safely interrupted. The frontend image stage completed successfully, but the
  complete Compose build did not finish.
- `docker compose ps`: **PASS** for the requested status check; no CareerPilot containers were
  running because the complete build did not finish.
- `docker compose up -d`: **BLOCKED**; Compose attempted to build the missing backend image and
  was stopped at the same external dependency-download stage before any service started.
- Backend health/API: **NOT RUN** because no backend container started.
- Frontend load: **NOT RUN** as a running Compose service; the frontend image build stage itself
  completed successfully.
- Demo Login → Resume → Job → Matching → Explainable Match Report: **NOT RUN** in Docker because
  the stack never reached a runnable state.
- `docker compose down`: **PASS**; cleanup completed with no CareerPilot stack left running.

### Runtime independence review

Static Docker context review confirms that the intended runtime does not depend on the host
`.venv`, `frontend/node_modules`, local API keys, an existing SQLite database, an existing FAISS
cache, or private uploaded files. The Dockerfiles install from repository lockfiles and the
`.dockerignore` excludes those host artifacts. This independence was not promoted to a runtime
smoke claim because the backend image did not complete.

### Docker-specific changes

No repository Dockerfile, Compose, application, dependency lock, or configuration change was made
during this follow-up. Same-version mirror tags and a temporary local uv bootstrap image were used
only in the Docker host for troubleshooting and were not committed.

Previous static validation:

- Compose syntax/config: **PASS** (`docker compose config --quiet`).
- `docker compose build --no-cache`: **BLOCKED** as detailed in the follow-up section above.
- Container startup and smoke: **BLOCKED**, because the complete build did not finish.

This is an external registry/dependency-download limitation, not a claimed application success.
Re-run the build and runtime smoke after Docker Hub/GHCR/PyPI downloads are reliable.

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
commit is `0e0a13a` (`feat: prepare CareerPilot AI portfolio release`). Documentation follow-ups
are `5a93bc6` (`docs: finalize publication guidance`), `25043d0` (`docs: record portfolio
engineering validation`), and `3181710` (`docs: clarify release commit history`). The working
tree is clean and no remote was added or pushed.

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

`READY_FOR_PUBLIC_GITHUB` remains false because the requested complete Docker build, startup,
health checks, frontend load, and portfolio smoke flow were not completed. The Docker engine is now
reachable; the remaining blocker is external registry/dependency download completion, not a
matching or application-functionality issue.
