# Phase 6 — Portfolio Release Report

Date: 2026-09-17

## Final status

```text
FEATURE_SCOPE_FROZEN = true
PORTFOLIO_RELEASE_READY = true
READY_FOR_PUBLIC_GITHUB = true
```

Phase 6 packaged the already-validated CareerPilot AI implementation for GitHub, resume, and
technical-interview presentation. No product feature, matching policy, prompt, evaluation label,
or blocking rule was changed.

## README

`README.md` was rewritten around a recruiter-first first screen:

- one-sentence product definition and the evidence-grounding differentiator;
- Why CareerPilot problem/solution framing;
- a core workflow Mermaid diagram;
- Core, Optional, and Hidden scope boundaries;
- Docker Demo first-run instructions and synthetic credentials;
- honest regression, holdout, parsing, and real-provider metrics;
- technology stack, limitations, privacy, and links to portfolio material.

The README intentionally does not include a CI badge because no public remote has run the workflow
yet.

## Screenshots

Seven anonymous Demo/Fake screenshots were generated under `docs/images/`:

| File | Purpose |
| --- | --- |
| `01_dashboard.png` | Demo dashboard |
| `02_resume_evidence.png` | Resume status, verification, and evidence |
| `03_job_input.png` | Structured job details |
| `04_matching_progress.png` | LangGraph match-run progress and human checkpoint |
| `05_match_report.png` | Hero screenshot: scores, evidence, dimensions, skill gaps, and Blocking Risk |
| `06_blocking_risk.png` | Blocking Risk detail |
| `07_application_board.png` | Application tracking board |

All screenshots use fictional Demo data. No API key, private resume, real contact detail, or debug
information is visible.

## Architecture and workflow

- Updated [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) to show human verification and the frozen
  70/30 hybrid boundary.
- Added the simpler recruiter-facing workflow diagram to `README.md`.
- The diagram contains only Vue, FastAPI, the resume/provider boundary, deterministic matching,
  FAISS supporting retrieval, SQLite/private storage, applications, and optional Dify.

## Portfolio material

Added:

- [DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — a two-minute walkthrough;
- [PORTFOLIO_SUMMARY.md](docs/PORTFOLIO_SUMMARY.md) — one-line, short, and detailed descriptions;
- [RESUME_BULLETS.md](docs/RESUME_BULLETS.md) — Chinese and English quantified bullets;
- [INTERVIEW_PITCH.md](docs/INTERVIEW_PITCH.md) — 30-second, one-minute, and three-minute pitches;
- [TECHNICAL_INTERVIEW_QA.md](docs/TECHNICAL_INTERVIEW_QA.md) — 18 evidence-based questions;
- [TECH_STACK.md](docs/TECH_STACK.md) — final technology inventory and explicit exclusions;
- [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — frozen scope and release gates;
- [GITHUB_METADATA.md](docs/GITHUB_METADATA.md) — suggested description and topics;
- [development notes index](docs/development/README.md) — historical-report navigation.

Historical phase reports remain at the root to avoid breaking their existing relative links. The
development index groups them without making the public README read like a development diary.

## Quality and CI

The trusted baseline remains:

- Backend Pytest: 222 passed;
- Evaluation tests: 8 passed;
- Frontend Vitest: 91 passed;
- Playwright: 16 passed;
- Ruff, mypy, TypeScript, ESLint, Alembic, clean clone, and Docker Demo smoke: PASS.

`.github/workflows/ci.yml` contains separate secret-free backend and frontend jobs. Remote GitHub
Actions execution is pending because this workspace has no configured remote.

## Security and publication hygiene

- `.env` is ignored and `.env.example` contains placeholders only.
- Tracked-file inventory contains no `.env`, database, upload, FAISS runtime, `node_modules`, or
  virtual-environment artifacts.
- Secret scan found no API-key-shaped or long Bearer-token values in release Markdown and source
  artifacts.
- Screenshots use only synthetic Demo/Fake data.
- Real-provider reports record key status as `configured`; no key or Authorization header is
  included.

See [PUBLICATION_SECURITY_CHECKLIST.md](PUBLICATION_SECURITY_CHECKLIST.md) before publishing.

## Git and public GitHub status

- Local branch: `main`.
- No remote was configured or pushed by this phase.
- Repository metadata is prepared in [GITHUB_METADATA.md](docs/GITHUB_METADATA.md).
- A public repository URL must be supplied by the user before `git remote add` or `git push`.

## Scope freeze

```text
No new feature development is planned before internship applications.
No matching algorithm, weights, thresholds, blocking rules, prompts or evaluation labels changed.
```

## Final report result

`PORTFOLIO_RELEASE_READY = true`.

Phase 6 is complete. No Phase 7 work, remote repository creation, or public push was started.
