# CareerPilot AI — Phase 4.7 Portfolio Scope Freeze

Completed: 2026-09-16

## Decision

CareerPilot AI is now frozen as an evidence-grounded resume-to-match portfolio product. The
portfolio does not require every module to be backed by a real external LLM. Job requirements
used by the matching engine come from structured job input. Real LLM Job Parsing was independently
validated as a provider capability in Phase 4.5, but it is not required by the production matching
path and is not a product blocker.

## Final Core Features

- PDF/DOCX resume upload and safe local storage.
- Real DeepSeek structured resume parsing, field-level evidence attachment and human verification.
- Immutable confirmed resume versions.
- Manual structured Job input, supported CSV/deterministic import and requirement representation.
- Six-dimension deterministic scoring with semantic supporting signal and frozen 70/30 hybrid logic.
- Blocking Risk, Skill Gap and Evidence Coverage.
- Explainable Match Report with dimension explanations, evidence traceability, input snapshot and
  matching version.
- Lightweight application tracking with status history.

## Optional Features

### Optional Dify Integration

Career Assistant remains available through its formal API and local retrieval/citation pipeline.
It is classified as an optional Dify integration: Demo/Fake mode is supported, while real Dify
credentials and production groundedness have not been validated. This does not block the core
portfolio engineering decision.

## Hidden Features

- Resume Optimization — retained implementation/tests, hidden from the core portfolio narrative.
- Chat Interview — retained implementation/tests, hidden from the core portfolio narrative.

Learning Plan, Cover Letter, additional RAG/agents, new recruitment sources, extra matching
dimensions, recommendation tuning and new AI workflows are explicitly out of scope.

## Real AI Status

| Area | Status |
| --- | --- |
| Resume parsing | Core real product path validated; one end-to-end product smoke plus 6/6 direct cases |
| Job input | Core deterministic structured input; no product AI parser by design |
| Matching and explainable report | Core product flow and frozen evaluation validated |
| Applications | Core product flow retained and regression-tested |
| Career Assistant | Optional; formal API/Fake mode validated, real Dify not validated |
| Resume Optimization / Chat Interview | Hidden; not validated as portfolio core |

## Test Status

The existing regression suite was rerun without any new DeepSeek calls:

- Backend Pytest: 222 passed (2 existing warnings)
- Evaluation tests: 8 passed
- Ruff: all checks passed
- mypy: no issues in 111 source files
- TypeScript type-check: passed
- ESLint: passed
- Vitest: 25 files / 91 tests passed
- Playwright: 16 passed

## Remaining Limitations

- The product Job path intentionally accepts structured input rather than parsing natural-language
  JDs with an LLM.
- Real Dify Career Assistant connectivity and real-model groundedness/citation correctness remain
  unvalidated and are optional follow-up work.
- Real-provider latency/token numbers are small synthetic validation measurements, not production
  SLOs or hiring-quality benchmarks.

## Scope Freeze

`FEATURE_SCOPE_FROZEN = true`

No new AI capability, agent, workflow, recruitment source, matching dimension, recommendation
tuning or external-service integration is to be added under this portfolio scope.

## Portfolio Engineering

`READY_FOR_PORTFOLIO_ENGINEERING = true`

The readiness decision is based on the frozen Core Features only. Optional Dify validation and the
absence of a product LLM Job parser are not feature-level blockers.

**No matching algorithm, weights, thresholds, blocking rules or holdout labels were changed.**

