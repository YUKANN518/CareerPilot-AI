# CareerPilot AI — Portfolio summary

## One-line

Built an evidence-grounded AI job-matching platform that combines verified resume evidence,
deterministic six-dimension scoring, semantic supporting signals, blocking-risk detection, and
explainable reports.

## Short

CareerPilot AI is a Vue/FastAPI portfolio project for explainable job decisions. Resumes are parsed
into structured fields with source evidence and must be human-verified before matching. Jobs enter
through deterministic structured input, then a six-dimension rules engine optionally combines a
70/30 semantic supporting signal. Reports expose scores, evidence coverage, skill gaps, and
blocking risks instead of returning an opaque LLM score. The project includes real DeepSeek resume
provider validation, synthetic regression and holdout evaluation, Docker Compose, CI, and a
secret-free Demo/Fake mode.

## Detailed

CareerPilot AI addresses a common weakness in LLM-assisted recruiting tools: a fluent answer does
not necessarily provide a defensible decision. The platform parses PDF/DOCX resumes into a strict
schema, attaches each field and skill to source text, and requires human verification before a
version becomes eligible for matching. Production job matching intentionally consumes structured
manual or CSV input, keeping requirement extraction reproducible and avoiding an unnecessary AI
Job Parser dependency.

The matching workflow uses deterministic rules across six dimensions—hard skills, evidence
strength, experience and education, language/location, user preferences, and other conditions.
Hybrid mode adds a local FAISS semantic supporting signal under a frozen 70/30 policy; semantic
similarity cannot prove a skill or override a blocking eligibility conflict. The explainable report
stores input snapshots, scoring configuration, dimension explanations, evidence coverage, matched
skills, skill gaps, and blocking risks. Applications provide a lightweight follow-up workflow.

Engineering evidence includes 222 backend tests, 91 frontend unit tests, 16 E2E tests, separate
evaluation and holdout datasets, opt-in DeepSeek validation (6 resumes and 10 job descriptions), a
CPU-only locked Docker build, and a complete Demo/Fake browser smoke. The limitations are explicit:
the datasets are synthetic, holdout blocking-risk recall is limited, real Dify is optional, and
SQLite is suitable for portfolio scale rather than large production traffic.
