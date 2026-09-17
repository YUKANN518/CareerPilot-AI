# Phase 5 — Portfolio Engineering Report

Date: 2026-09-17

## Executive result

CareerPilot AI now has the release engineering baseline for a public portfolio repository:
locked dependencies, reproducible Demo/Fake configuration, Docker assets, CI configuration,
privacy rules, a license, an architecture document, and a first Git commit.

The Docker runtime blocker from the initial Phase 5 attempt has been resolved. The CPU-only locked
backend image starts with the frontend, passes health checks, and completes the Demo/Fake portfolio
smoke flow. `READY_FOR_PUBLIC_GITHUB` is now true.

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

## Docker runtime completion (2026-09-17)

The Docker host recovered and the previously blocked verification was completed without another
full `--no-cache` build. The CPU-only dependency graph was retained; the only image rebuild was a
cached backend rebuild after a Demo fixture-data correction.

### Engine and build

- Docker Desktop: **4.91.0 (239619)**
- Docker Engine: **29.8.0** (API 1.56)
- Docker Compose: **v5.5.1**
- `docker version`: **PASS**
- `docker info`: **PASS**
- `docker compose config`: **PASS**
- Previously completed clean build: **PASS** (backend and frontend; approximately 1,191 seconds).
- Follow-up backend rebuild: **PASS** with Docker layer cache; no `--no-cache` and no CUDA
  dependency download.

The backend image resolves `torch==2.14.0+cpu` from the explicit PyTorch CPU index. The lockfile
contains no CUDA/NVIDIA/Triton runtime packages. `UV_SYSTEM_CERTS=1`, bounded uv retries, and
`--no-install-project` keep the locked install reproducible while avoiding transient registry/TLS
failures and unnecessary editable-build network access.

### Runtime and smoke results

- `docker compose up -d`: **PASS**.
- `docker compose ps -a`: backend and frontend **healthy**.
- Backend `/api/health`: **PASS** (HTTP 200).
- Frontend `http://localhost:5173/`: **PASS** (HTTP 200 and CareerPilot shell loaded).
- Browser smoke (Playwright, Demo/Fake mode): **PASS** — Demo Login → Resume list and detail →
  Job list and detail → start matching → human confirmation → Explainable Match Report.
- The backend log shows the same flow succeeding through `/api/resumes/1/versions`,
  `/api/match-runs`, `/api/match-runs/{id}/confirm`, and `/api/matches/{id}`.

The isolated Demo database was reset and reseeded after correcting schema-required empty evidence
fields in the anonymous fixture. This is Demo fixture data only; no matching or product behavior
was changed. The synthetic DOCX source asset is created inside the isolated runtime directory so
the normal Resume page can render without private uploaded files.

### Runtime independence

The running containers were checked directly:

- `torch==2.14.0+cpu`; `torch.cuda.is_available() == False`.
- `sentence_transformers` and `faiss` import successfully.
- `AI_PROVIDER=mock`, `EMBEDDING_PROVIDER=fake`, `DIFY_PROVIDER_MODE=fake`; no external API key
  was required or used.
- The only backend mount is `data/runtime/docker-demo` → `/workspace/data/runtime/demo`.
- The runtime SQLite database, uploads directory, and FAISS directory are created in that isolated
  path. Host `.venv`, `frontend/node_modules`, existing host SQLite/FAISS data, and private
  uploaded files are not mounted into the containers.
- Frontend has no `node_modules` directory in its Nginx runtime image; backend uses its
  image-managed virtual environment.

### Docker-specific fixes

1. Pinned CPU-only PyTorch in `pyproject.toml`/`uv.lock` to remove the unnecessary CUDA graph.
2. Added bounded locked-sync retries and system certificate use in `backend/Dockerfile`.
3. Kept the Compose bind mount at the isolated `/workspace/data/runtime/demo` path and ensured
   image/runtime ownership is writable by the non-root user.
4. Completed the anonymous Demo resume fixture with schema-required empty evidence fields and a
   synthetic private DOCX asset, allowing the Resume and Job pages to render in Docker.

`docker compose down`: **PASS**. Final `docker compose ps -a` returned no CareerPilot containers.

No new DeepSeek calls were made during this runtime verification.

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
engineering validation`), and `3181710` (`docs: clarify release commit history`). The current
Phase 5 changes are local and uncommitted; no remote was added or pushed.

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

1. `npm audit` advisories remain documented and intentionally unfixed with force; upgrades need a
   dedicated compatibility change.
2. Real Dify connectivity remains an Optional Integration, not a Core Portfolio requirement.
3. The real Job parser remains validation-only; production matching intentionally consumes manual
   or structured deterministic job input.

## Scope integrity

**No matching algorithm, weights, thresholds, blocking rules, prompts or product features were
changed.** No new AI feature, Job Parser API, agent, RAG workflow, matching dimension, or
recommendation threshold was added in Phase 5. `FEATURE_SCOPE_FROZEN = true` remains in effect.

## Portfolio readiness

```text
FEATURE_SCOPE_FROZEN = true
READY_FOR_PUBLIC_GITHUB = true
```

`READY_FOR_PUBLIC_GITHUB = true` because the CPU-only locked build, container startup, health
checks, frontend load, runtime-independence checks, and complete Demo/Fake portfolio smoke flow
all passed. No Docker-specific blocker remains. Docker was brought down after verification and no
GitHub push or Phase 6 work was started.
