# CareerPilot AI Phase 3.5 — Evaluation Hardening Report

Completed on 2026-09-16.  This phase adds an independent holdout and a small parsing
validation surface for resume/job evidence.  It keeps the existing regression baseline intact
and does not add a new product module.

## 1. Evaluation split

The project now reports four separate layers:

1. **Regression Validation (`eval-v1`)** — the existing 52-case synthetic, manually annotated
   set.  It remains regression-oriented and frozen; its original outputs and M03 failure were
   not overwritten.
2. **Independent Synthetic Holdout (`holdout-v1`)** — 20 newly authored label-first cases in
   `evaluation/dataset/holdout/`, with natural-language job descriptions and an annotation log.
3. **Semantic Diagnostic** — the existing 10-case fake-deterministic embedding diagnostic for
   integration/ranking and blocking preservation only.
4. **Parsing Validation (`parsing-v1`)** — ten new synthetic resumes (five PDF, five DOCX) and
   ten job descriptions evaluated through deterministic text/evidence extraction only.

No overall accuracy combines these layers.

## 2. Frozen regression baseline

The baseline is `deterministic-v1.1` over 52 cases, repeated three times per case:

| Metric | Result |
| --- | ---: |
| Required Skill Precision / Recall / F1 | 100.00% / 100.00% / 100.00% |
| Missing Skill Precision / Recall / F1 | 100.00% / 100.00% / 100.00% |
| Blocking Risk Precision / Recall / F1 | 100.00% / 100.00% / 100.00% |
| Evidence validity | 100.00% |
| Evidence-backed match rate | 100.00% |
| Unsupported skill claim rate | 0.00% |
| Structured result validity | 100.00% |
| Recommendation agreement | 98.08% |
| Match Band Agreement | N/A |

The one retained failure is **M03**: skill states agree, but the score crosses the current
recommendation threshold (`STRONGLY_RECOMMENDED` versus the label's `RECOMMENDED`/`CONSIDER`
set).  It remains in `evaluation/results/FAILURE_ANALYSIS.md` as `RULE_FAILURE`.

## 3. Independent holdout

The 20 cases cover containerized vs Docker, relational database vs PostgreSQL, AI vs PyTorch,
cloud vs AWS, required/preferred wording, fresh graduate and final-year contexts, internship,
preferred versus required experience, CS/related degree, Cantonese, written English, Hong Kong
work eligibility, hybrid/on-site arrangements and sparse postings.  The label-first record is
`evaluation/dataset/holdout/ANNOTATION_LOG.md`; cases are not copied from backend tests,
`eval-v1`, `sample_data` or demo jobs.

Frozen `deterministic-v1.1` results:

| Metric | Result |
| --- | ---: |
| Required Skill Precision / Recall / F1 | 100.00% / 100.00% / 100.00% |
| Missing Skill Precision / Recall / F1 | 80.00% / 57.14% / 66.66% |
| Preferred Skill Precision / Recall / F1 | 100.00% / 100.00% / 100.00% |
| Blocking Risk Precision / Recall / F1 | 66.67% / 40.00% / 50.00% |
| Evidence validity | 100.00% |
| Evidence-backed match rate | 100.00% |
| Unsupported skill claim rate | 0.00% |
| Structured result validity | 100.00% |
| Recommendation agreement | 65.00% |
| Match Band Agreement | 65.00% |
| Eligibility agreement | 60.00% |

There are 8 labelled failures: 5 `RULE_FAILURE` and 3 `SKILL_OR_ALIAS_FAILURE`.  They are
retained rather than removed or used to tune the matcher.  The most useful signal is that
unknown dictionary terms such as AWS, PyTorch and Tableau are distinguished from known missing
skills, while broad recommendation expectations remain sensitive to the current score policy.
Full per-case Expected / Actual / Difference records are in
`evaluation/results/holdout-v1/FAILURE_ANALYSIS.md`.

## 4. Parsing validation

`parsing-v1` uses ten synthetic resumes (R01–R05 PDF, R06–R10 DOCX) and ten natural-language job
descriptions.  Every resume expected contract includes Education, Skills, Projects and
Experience sections.  It evaluates the existing `ResumeTextExtractor`, skill dictionary evidence
path and `JobRequirementExtractor`; no real AI provider was used.

| Metric | Result |
| --- | ---: |
| Resume text extraction success | 100.00% |
| Job text extraction success | 100.00% |
| Resume section extraction success | 100.00% |
| Resume skill Precision / Recall / F1 | 100.00% / 94.74% / 97.30% |
| Resume evidence attachment rate | 100.00% |
| Job requirement Precision / Recall / F1 | 100.00% / 100.00% / 100.00% |
| Required-vs-preferred accuracy | 100.00% |

The resume skill recall is below 100% because one synthetic skill (`Java`) is outside the
current local dictionary; this is an honest parser/evidence limitation, not an LLM benchmark.

## 5. Semantic diagnostic

The existing controlled diagnostic reviewed 10 semantic cases using `fake-deterministic-v1`:
recommendation consistency 90.00%, ranking accuracy 85.71%, 7 semantic-case improvements, 0 new
misjudgments, blocking preserved, and incomplete-job recommendation cap preserved.  These values
are integration/ranking diagnostics only.  They do not measure real embedding quality and no
semantic-only blocking score is reported.

## 6. Algorithm changes

**No matching algorithm, weights, thresholds or alias rules were changed.**

The only matching execution is the frozen deterministic-v1.1 configuration.  New code adapts
the independent case format into the existing evaluator and records outputs; it does not alter
production matching behavior.

## 7. Portfolio metrics and claim boundaries

See [evaluation/PORTFOLIO_METRICS.md](evaluation/PORTFOLIO_METRICS.md).  Safe resume wording is
that CareerPilot has versioned synthetic regression/holdout evaluation, evidence-backed
deterministic matching, and deterministic PDF/DOCX text/evidence validation.  Do not claim
“CareerPilot accuracy”, hiring-success prediction, fairness, OCR/LLM quality, real-provider
semantic quality, or a combined overall score.

## 8. Quality gates

| Gate | Result |
| --- | --- |
| Product Pytest | 217 passed; 84% coverage |
| Evaluation tests | 8 passed |
| Ruff | PASS for app/tests/scripts/evaluation and new backend evaluators |
| mypy | PASS for evaluation and new backend evaluators; previous app baseline 109 sources PASS |
| TypeScript / ESLint | PASS |
| Vitest | 25 files / 91 tests passed |
| Playwright | 16 passed |
| Alembic | 11 migrations on fresh SQLite database PASS |
| Holdout run | 20 cases, deterministic-v1.1, repeatable subprocess output |
| Parsing run | 10 resumes + 10 job descriptions, deterministic offline path |

Two pre-existing non-blocking warnings remain: LangGraph's pending `allowed_objects` default
change and Starlette's deprecated HTTP 422 constant.

## 9. Limitations and stopping point

- Both matching datasets are synthetic and small; neither represents a hiring population.
- Holdout labels intentionally expose unknown-skill and policy disagreements; they were not
  retuned after execution.
- Parsing fixtures are text-layer PDFs/DOCX and do not cover scans/OCR, layout-heavy resumes or
  real-provider structured extraction.
- Semantic behavior is a fake-vector integration diagnostic.
- Broad recommendation and match-band labels are secondary to skill/evidence/risk metrics.

**Do not proceed automatically to Docker / Real Provider Phase.**
