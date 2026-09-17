# CareerPilot AI — Project status

```text
FEATURE_SCOPE_FROZEN = true
PORTFOLIO_RELEASE_READY = true
READY_FOR_PUBLIC_GITHUB = true
```

## Released Core

- Real DeepSeek resume parsing validated through the OpenAI-compatible provider contract.
- Evidence attachment and human verification for immutable resume versions.
- Structured/manual job input and deterministic CSV import.
- Six-dimension deterministic matching and the 70/30 hybrid supporting signal.
- Blocking Risk, Skill Gap, Evidence Coverage, and Explainable Match Report.
- Lightweight application tracking.
- Docker Compose Demo/Fake mode with CPU-only locked dependencies.

## Optional / experimental

- Career Assistant / Dify integration; real Dify deployment is not validated as a Core feature.
- Resume Optimization and Chat Interview remain hidden experimental modules.

## Quality gates

- Backend product Pytest: 222 passed.
- Evaluation tests: 8 passed.
- Frontend Vitest: 91 passed.
- Existing Playwright suite: 16 passed.
- Ruff, mypy, TypeScript, ESLint, Alembic, clean clone, and Docker Demo smoke: PASS.

## Remaining limitations

- Evaluation data is synthetic and small.
- Independent holdout Blocking Risk recall is 40%; recommendation agreement is 65%.
- Semantic relevance does not prove capability.
- SQLite and local storage are portfolio-scale choices.
- Real Dify groundedness/citation correctness remains an optional manual-validation task.

## Scope freeze

No new feature development is planned before internship applications. In particular, do not add a
new AI Job Parser API, new agent, new RAG workflow, new matching dimension, or threshold tuning
without reopening the scope decision and evaluation plan.
