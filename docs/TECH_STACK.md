# CareerPilot AI — Final tech stack

| Boundary | Technologies actually used | Portfolio role |
| --- | --- | --- |
| Frontend | Vue 3, TypeScript, Vite, Pinia, Vue Router, Tailwind CSS, Axios | Demo UI, workflow state, report visualization |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | API, validation, persistence, migrations |
| AI provider | OpenAI-compatible API / DeepSeek | Real resume parsing validation |
| Optional AI integration | Dify workflow/chatflow | Optional Career Assistant only |
| Workflow | LangGraph | Match-run orchestration, events, human checkpoint |
| Matching | Deterministic six-dimension rules, blocking policy, 70/30 hybrid | Explainable core decision path |
| Retrieval | Sentence Transformers, FAISS | Local semantic supporting evidence |
| Storage | SQLite, private local file storage | Portfolio/demo persistence |
| Testing | Pytest, Vitest, Playwright, Ruff, mypy, ESLint | Product, evaluation, static, and E2E gates |
| Delivery | Docker Compose, uv.lock, package-lock.json, GitHub Actions | Reproducible Demo and CI |

## Explicitly out of scope

Redis, Kafka, Kubernetes, microservices, managed vector databases, production-scale PostgreSQL,
and multi-agent orchestration are not part of the released portfolio architecture.
