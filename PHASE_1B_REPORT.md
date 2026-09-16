# CareerPilot AI Phase 1B Report

Completed on 2026-09-16. Phase 1B narrows CareerPilot AI into an **Evidence-Grounded AI
Job Matching & Career Decision Platform（基于证据约束的人岗匹配与 AI 求职决策平台）**.
This phase changed product scope, navigation and compatibility data only; it did not redesign
matching weights, blocking rules, resume evidence, RAG retrieval or LangGraph orchestration.

## 1. Scope Decision

| Decision | Product capability | Result |
| --- | --- | --- |
| KEEP — CORE | Resume | Upload, parse, review, confirm, immutable version and field evidence remain. |
| KEEP — CORE | Jobs | Manual/JD paste, preview, private job CRUD and CSV import remain. |
| KEEP — PRIMARY | Matching | Deterministic and hybrid execution, SSE progress, blocking policy and explainable report remain. |
| KEEP — CORE | AI Assistant / RAG | Knowledge and personal-context retrieval, citations and no-evidence behavior remain. |
| KEEP | Applications | Simplified to `SAVED`, `APPLIED`, `INTERVIEW`, `OFFER`, `REJECTED`. |
| KEEP — ADMIN | Knowledge Base | The only retained admin product surface. |
| HIDE | Resume Optimization | API, direct routes, provider and tests remain; navigation and Match Report CTA were removed. |
| HIDE | Chat Interview | API, direct routes, state machine, chat/final providers and tests remain; navigation and Match Report CTA were removed. |
| REMOVE | Learning Plan | Removed end to end, including personal-context coupling and Dify configuration. |
| REMOVE | Cover Letter | Removed end to end; shared fact validation and `GeneratedMaterial` remain for Resume Optimization. |
| REMOVE | Legacy Interview | Removed one-shot answer submission, scoring, report, `InterviewAnswer` and answer-evaluation provider. |
| REMOVE | External job acquisition/admin | Removed source CRUD/sync, credentials, adapters, URL import and admin UI; minimal source provenance remains for existing jobs. |
| REMOVE | Fake shell UI | Removed global search, notification placeholder, settings entry, environment badge and development-stage labels. |

The pre-change dependency analysis and rationale are recorded in
[`SCOPE_CLEANUP_PLAN.md`](SCOPE_CLEANUP_PLAN.md).

## 2. Removed

- Learning Plan business module, routes, persistence access, UI, tests, scripts and AI provider.
- Cover Letter business module, routes, UI, tests, scripts and AI provider.
- Legacy one-question-at-a-time interview answer evaluation and legacy report screens.
- External job-source configuration, encrypted credentials, sync tasks/logs, website/API adapters,
  URL import, public discovery tabs and their admin screens.
- Obsolete application states: `PREPARING`, `ASSESSMENT`, `ACCEPTED`, `WITHDRAWN`.
- Header global search, fake notification indicator, settings placeholder and Demo/Mixed/Real
  development badge.
- CTAs from Match Report to Resume Optimization, Learning Plan, Cover Letter and Interview.

## 3. Hidden

Resume Optimization and Chat Interview are still implemented and covered, but cannot be
reached from the ordinary navigation or Match Report. Their authenticated APIs and direct
routes remain so the code can be demonstrated separately without widening the default story.
Playwright exercises both through authenticated API setup followed by direct navigation.

## 4. Kept

- Confirmed resume versions and source-level evidence.
- Manual/JD and CSV target-job input.
- Deterministic scoring, hybrid semantic retrieval, hard blocking and report evidence.
- Grounded AI Assistant with Knowledge Base plus user context.
- Five-state application tracking.
- Admin Knowledge Base management.
- Minimal `JobSource` provenance mapping required to read older job rows.
- Shared `GeneratedMaterial`, fact validation, interview session/question planning and chat
  messages required by the two hidden optional modules.

## 5. AI Config Before / After

The active Dify feature keys were reduced from **8 to 5**.

| Before | After |
| --- | --- |
| Learning Plan | Removed |
| Resume Optimization | Retained — hidden |
| Knowledge QA | Retained — core |
| Cover Letter | Removed |
| Interview Plan | Retained — shared by Chat Interview |
| Interview Answer Evaluation | Removed |
| Interview Chat | Retained — hidden |
| Interview Final Evaluation | Retained — hidden |

The corresponding removed environment variables and workflow settings were deleted from the
application settings and `.env.example`. The complete effective configuration and rationale are
in [`AI_CONFIG_AFTER_CLEANUP.md`](AI_CONFIG_AFTER_CLEANUP.md).

## 6. Tests: Phase 1A → Phase 1B

All reductions are intentional deletions of retired feature tests, not skipped tests.

| Gate | Phase 1A | Phase 1B | Result |
| --- | ---: | ---: | --- |
| Pytest | 285 passed, 84% | **213 passed, 84%** | PASS |
| Ruff | PASS | **PASS** | PASS |
| mypy `app` | 133 source files | **109 source files** | PASS |
| TypeScript | PASS | **PASS** | PASS |
| ESLint | PASS | **PASS** | PASS |
| Vitest | 30 files / 144 tests | **25 files / 89 tests** | PASS |
| Playwright | 27 tests | **16 tests** | PASS |

Additional database verification upgraded a new SQLite database through all 11 Alembic
revisions. The final schema contained 32 tables; `learning_plans`, `learning_tasks`,
`cover_letters`, `interview_answers`, `job_source_configs`, `job_source_credentials`,
`job_sync_tasks` and `job_sync_logs` were absent.

Two non-blocking backend warnings remain: the LangGraph `allowed_objects` pending deprecation
and Starlette's HTTP 422 constant deprecation.

## 7. Main E2E

`frontend/tests/e2e/portfolio-main-flow.spec.ts` is the portfolio-oriented smoke journey:

1. Log in as the isolated demo user.
2. Open the seeded confirmed resume and verify its confirmed status.
3. Open the seeded target job.
4. Start a hybrid match with the confirmed resume version.
5. Verify input loading, deterministic matching, semantic retrieval and report persistence.
6. Confirm the human-review checkpoint and open the report.
7. Verify the score, matched Python evidence, semantic-evidence section and hard-risk/blocking
   section.

The separate Resume Center E2E still proves upload → extraction → parsing → manual correction →
confirmation → evidence inspection.

## 8. Removed Files

The deletion set is grouped below because several features previously spanned every layer.

| Area | Removed file families |
| --- | --- |
| Learning Plan | `backend/app/{api,schemas,services,repositories}/learning_plans.py`, its Dify provider, backend tests/diagnostic scripts, and `frontend/src/{api,types,pages}` plus unit/E2E coverage for learning plans. |
| Cover Letter | `backend/app/{api,schemas,services,repositories}/cover_letters.py`, its Dify provider, backend tests/diagnostic scripts, and `frontend/src/{api,types,pages}` plus unit/E2E coverage for cover letters. |
| Legacy Interview | Legacy answer provider/factory branches and answer schemas, `frontend/src/pages/InterviewDetailPage.vue`, `InterviewReportPage.vue`, their client/types/tests, and the obsolete backend legacy-interview test. |
| Job-source administration | `backend/app/api/job_sources.py`, `backend/app/api/admin.py`, `backend/app/core/credentials.py`, source service/repository code and the external adapters under `backend/app/job_sources/`; corresponding scripts, admin pages, frontend API/types, unit tests and E2E specs. |
| Retired UI/tests | `frontend/tests/e2e/interviews.spec.ts` and scope-specific discovery/import tests that no longer describe the product. |

Historical Alembic revision files were not deleted. A new migration
`backend/alembic/versions/e7c4a9d12b30_simplify_application_statuses.py` maps legacy application
statuses and drops retired tables. Its downgrade is intentionally non-restorative because
deleted business data and old status distinctions cannot be reconstructed safely.

## 9. Remaining Issues

- Real OpenAI-compatible and Dify connectivity, cost, latency and output quality were not
  tested; the acceptance matrix uses deterministic Mock/Fake providers.
- The Phase 1A npm audit baseline (10 findings: 6 moderate, 4 high) was intentionally not changed
  or re-audited in this scope phase.
- Python dependency locking, Docker and CI remain out of scope.
- The supplied workspace is not a Git repository, so history-level secret scanning and a true
  Git deletion diff are unavailable.
- Existing private runtime data under `data/` must still be excluded before publishing.
- Resume Optimization and Chat Interview remain maintenance surface even though they are hidden;
  a later product decision should either promote or remove each one.
- Minimal legacy job-source provenance remains by design; it is not a source-management or
  scraping capability.

## 10. Product Navigation

Ordinary users now see exactly six product destinations:

1. 工作台 / Dashboard
2. 我的简历 / Resume
3. 目标岗位 / Jobs
4. 匹配任务 / Matching
5. AI 职业助手 / AI Assistant
6. 投递管理 / Applications

Administrators receive one additional destination: **知识库管理 / Knowledge Base**. `/admin`
redirects there. No Learning Plan, Cover Letter, Resume Optimization, Interview, job-source
administration, settings, global search or notification entry appears in the default shell.

Phase 1B is complete. Phase 2 has not been started.
