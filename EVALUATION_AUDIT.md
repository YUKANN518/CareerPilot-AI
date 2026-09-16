# CareerPilot AI Evaluation Audit

Audited on 2026-09-16 before Phase 3 evaluation changes. No matching algorithm, skill alias,
blocking threshold or semantic weight was changed during this audit.

## 1. Existing evaluation assets

The repository already contains a substantial deterministic evaluation implementation under
`backend/evaluation/matching/`:

- `fixtures/resumes.json`: 28 anonymous structured resume fixtures;
- `fixtures/jobs.json`: 52 structured job fixtures;
- `labels/labels.json`: 52 labelled resume-job cases;
- `schemas.py`: strict Pydantic fixture, label, result and metric schemas;
- `executor.py`: builds in-memory ORM objects and invokes the released requirement extractor and
  deterministic matching engine directly;
- `metrics.py`: score intervals, recommendations, four-state skill confusion matrix, risk
  precision/recall, evidence trace coverage, repeatability and ranking metrics;
- `runner.py`: repeatable CLI runner for `deterministic-v1` and filtered cases/categories;
- `hybrid_runner.py`: offline FAISS/fake-embedding semantic comparison over 10 semantic cases;
- `report.py` and `charts.py`: JSON, CSV, Markdown and chart outputs;
- `tests/test_matching_evaluation.py`: dataset validation, metric, stability, monotonicity,
  policy and output-generation tests;
- checked-in outputs under `backend/evaluation/matching/outputs/`.

This is more than ordinary unit testing: the executor evaluates labelled case outcomes through the
real matching components. It is nevertheless an engineering fixture benchmark, not a real-world
recruiting dataset or an academic benchmark.

## 2. What is unit testing versus evaluation

The normal `backend/tests/test_matching.py` and `test_semantic_matching.py` suites mostly test
isolated rules, API/service behavior, and invariants. They include valuable adversarial checks but
do not provide a labelled population-level metric.

The existing `backend/evaluation/matching` runner is evaluation-oriented because every case has a
labelled expected skill state, risk expectation, score interval or ranking role. The 52-case
deterministic set includes high match, medium match, skill gap, blocking, incomplete posting and
insufficient evidence categories. The semantic runner adds 10 fixed, synthetic relevance cases.

## 3. Human-labelled data status

There is no real applicant or employer data. The current labels are manually authored synthetic
fixtures. They are useful for regression and portfolio-level validation, but they must be reported
as synthetic/manually annotated and must not be presented as hiring accuracy.

The current label schema covers expected matched, partial, missing and unknown skill states,
expected blocking/high risks, recommendation alternatives and score intervals. It does not yet
have the requested explicit `expected_eligibility`, `expected_match_band`, or an independent
per-skill evidence-validity label.

## 4. Existing benchmark behavior

The current command is:

```powershell
cd backend
.venv\\Scripts\\python.exe -m evaluation.matching.runner
```

It loads all fixtures, repeats each case, computes metrics and writes outputs. It also compares
the legacy `deterministic-v1` result with `deterministic-v1.1`; that comparison is useful for
historical policy work but is not the same as a clean Phase 3 baseline of the current production
contract.

The existing semantic command is:

```powershell
.venv\\Scripts\\python.exe -m evaluation.matching.hybrid_runner
```

It uses a deterministic fake embedding provider and controlled two-dimensional vectors. This is
appropriate for offline stability and boundary tests, but its expected relevance is constructed
inside the fixture and is not a human relevance judgement. It must be described as a semantic
regression/ablation diagnostic, not a general semantic-quality score.

## 5. Current measurable outputs

The checked-in deterministic output reports 52 cases, perfect four-state skill confusion on its
labelled fields, complete evidence trace coverage and repeatability, but only 11.8% blocking
recall for the legacy `deterministic-v1` policy. The report explicitly attributes this to the
older policy's narrow blocking definition. The v1.1 comparison and hybrid output separately show
policy-cap and semantic-preservation behavior.

These are useful findings, but the current metrics do not directly report:

- required-skill precision/recall/F1 as a binary matched-required task;
- missing-skill precision/recall;
- blocking-risk F1 in the requested shape;
- evidence-backed match rate and unsupported skill claim rate;
- structured result schema validity;
- typed failure categories per case.

## 6. Dataset and output separation gap

The existing assets live under `backend/evaluation/matching`, next to implementation code and
checked-in generated outputs. Product demo data lives under `sample_data`, so the two are not
currently mixed in content, but there is no root-level `evaluation/` contract with a README,
annotation guide, alias policy, frozen baseline directories and stable result filenames requested
for Phase 3.

Phase 3 will preserve the existing fixtures and results, then add a thin independent file-based
evaluation package at root-level `evaluation/`. It will not write to the product database or demo
runtime. Existing backend evaluation tests remain compatibility coverage.

## 7. Evaluation suitability and limitations

- Deterministic matching is highly suitable for offline benchmark runs because the extractor,
  normalizer and scorer are pure/in-memory components and the fake fixtures are stable.
- The fake semantic provider is suitable for reproducibility and blocking-preservation checks, not
  for claiming real embedding quality.
- Current synthetic resumes encode skills directly, so parsing quality is not evaluated. Parsing
  evaluation must remain a separate future track.
- Score interval labels are secondary and intentionally broad; exact numeric agreement would be
  subjective and should not be the primary metric.
- Blocking labels must follow the released `blocking-policy-v1` semantics. They cannot be changed
  after seeing baseline results without a changelog.

## 8. Phase 3 implementation boundary

Before the first new baseline run, do not change:

- matching weights;
- deterministic or semantic thresholds;
- skill alias dictionary;
- blocking rules;
- semantic blend weights.

The Phase 3 additions will provide a 52-case `eval-v1` baseline, explicit annotation and alias
policies, requested metrics, case-level failure categories, JSON/Markdown/CSV outputs and tests
for the evaluator itself. Deterministic, semantic and hybrid results will only be compared where
the metric is meaningful; Semantic Only blocking metrics will be `N/A` because semantic retrieval
has no blocking policy of its own.

