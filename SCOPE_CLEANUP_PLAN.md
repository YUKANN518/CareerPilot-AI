# CareerPilot AI Phase 1B Scope Cleanup Plan

> Written before Phase 1B code changes. Decisions are based on reference and persistence
> dependencies, not module names alone.

## Product focus

CareerPilot AI is an **Evidence-Grounded AI Job Matching & Career Decision Platform** —
基于证据约束的人岗匹配与 AI 求职决策平台。

The default portfolio journey is:

`Resume → parsing → evidence verification → target job → structured requirements → hybrid
matching → blocking risks → explainable report → grounded career assistant → application`

## Scope decisions

| Feature | Decision | Dependency finding | Planned final state |
| --- | --- | --- | --- |
| Resume | KEEP — CORE | Owns confirmed immutable versions and evidence consumed by matching/RAG. | Full PDF/DOCX upload, parse, manual confirm and evidence UI remain. |
| Jobs | KEEP — CORE | `Job`, `JobSkill` and job reads are consumed by matching and applications. | Keep manual/JD paste and CSV import. Remove URL/site acquisition entry points. |
| Matching | KEEP — PRIMARY CORE | Central deterministic/hybrid flow and SSE report workflow. | No weight, policy, formula, blocking-rule or LangGraph changes. |
| AI Assistant / RAG | KEEP — CORE | Uses knowledge FAISS plus resume, match and application context. Learning-plan context is separable. | Keep retrieval, citations, user context and no-evidence refusal; remove learning-plan context only. |
| Applications | KEEP | Closes the match-to-action loop. Current nine-state workflow is wider than the portfolio need. | Reduce to Saved, Applied, Interview, Offer and Rejected with a compatibility migration for legacy statuses. |
| Learning Plan | REMOVE | Isolated API/schema/service/repository/model pair and Dify provider; only RAG personal context also reads it. | Remove product code, routes, tests, UI and provider config. Historical migration tables remain for existing-DB compatibility. |
| Cover Letter | REMOVE | Uses shared `GeneratedMaterial`, match/job/resume models and common fact validation; its own API/service/schema/provider are separable. | Remove the business module, routes, UI, tests and Dify config; keep shared material model/fact validation for Resume Optimization. |
| Resume Optimization | HIDE | Already job-specific: requires a confirmed resume, selected job and successful match report; validates evidence keys, missing skills and edited claims. | Keep code/API/tests/provider, remove normal navigation and Match Report CTA. Document as optional/experimental. |
| Legacy Interview | REMOVE | Old answer submission/report paths use `InterviewAnswer` and answer-evaluation provider. Session creation/question planning are also used by Chat Interview. | Remove one-shot pages/routes/client calls/API endpoints/tests and legacy answer evaluation. Preserve shared session/question/plan code needed by chat. |
| Chat Interview | HIDE | Uses `InterviewSession`, `InterviewQuestion`, `InterviewMessage`, session creation/listing and plan generation. | Keep code/API/models/tests and Dify chat/final support; remove navigation and default Match Report CTA. |
| External Job Sources | REMOVE | Admin source CRUD/sync, adapters, credentials and task models are separable from user-owned manual/CSV jobs. Existing jobs may still carry `source_id`. | Remove active API/admin/pages/adapters/config/credentials/schedulers/public discovery. Keep minimal read-only source provenance mapping and historical DB tables so old jobs remain readable. |
| Admin | KEEP — KB ONLY | Knowledge management API/page is independent of recruitment-source admin. | `/admin` redirects to Knowledge Base; only Knowledge Base appears in admin navigation. |
| Global Search | REMOVE | Header input has no search action or results. | Remove control and icon. |
| Notifications | REMOVE | Bell and red dot are fixed and have no backing data. | Remove control and icon. |
| Account Settings | REMOVE | Sidebar item is unavailable placeholder only. | Remove item and placeholder rendering path. Profile remains represented by the authenticated user menu; logout remains. |
| Development labels | REMOVE FROM UI | Stage/phase strings occur in sidebar and resume process copy. | Replace with user-facing product language; technical history/docs may retain phase terminology. |

## Shared-code constraints

- `GeneratedMaterial` cannot be removed because Resume Optimization uses it.
- `InterviewSession` and `InterviewQuestion` cannot be removed because Chat Interview creates a
  planned question set before chat turns. `InterviewMessage` is chat-only and remains.
- The interview plan provider is shared by Chat Interview session creation. The answer-evaluation
  provider is legacy-only and will be removed.
- `Job.source_id` cannot be dropped in this phase without breaking existing databases and public
  provenance rows. The complex source-management surface will be removed while a minimal legacy
  source mapping remains read-only.
- Alembic history is immutable. Removed business tables may continue to exist in upgraded
  databases; application code will stop exposing them. A new migration is justified only for the
  five-state Application compatibility mapping.

## Planned verification checkpoints

1. Remove Learning Plan and its context/config, then run focused backend and frontend checks.
2. Remove Cover Letter and its config, then run focused checks.
3. Remove only Legacy Interview surfaces and answer evaluation; run all retained Chat Interview
   tests.
4. Remove external acquisition/admin surfaces while retaining manual/JD/CSV; run job, matching,
   resume and application tests.
5. Simplify navigation, Dashboard, Applications and fake UI; add/retain a portfolio main-flow E2E.
6. Run the complete Phase 1B matrix and compare counts with Phase 1A.

## Explicitly out of scope

No npm forced audit fix, dependency lock, Docker work, real-provider verification, matching/RAG
redesign or broad UI redesign is included in Phase 1B.

