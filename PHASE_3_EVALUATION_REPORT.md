# CareerPilot AI Phase 3 Evaluation Report

Completed on 2026-09-16. This phase adds project-level Matching Evaluation and Validation. It
does not add product UI or a new business module, and it does not modify the released matching
algorithm.

## Evaluation Dataset

- Dataset version: `eval-v1`
- Cases: 52 deterministic resume-job cases
- Semantic diagnostics: 10 controlled cases
- Data type: manually annotated synthetic fixtures
- Storage: file-based under `evaluation/`; no production or demo database writes
- Categories: HIGH_MATCH, MEDIUM_MATCH, SKILL_GAP, BLOCKING, INCOMPLETE_JOB,
  INSUFFICIENT_EVIDENCE

The fixtures begin with structured resume/job inputs. Resume parsing and Job parsing quality are
separate future evaluations and are not mixed into these metrics.

The audit is recorded in [EVALUATION_AUDIT.md](EVALUATION_AUDIT.md). Annotation and alias rules
are in [evaluation/ANNOTATION_GUIDELINES.md](evaluation/ANNOTATION_GUIDELINES.md) and
[evaluation/SKILL_ALIAS_POLICY.md](evaluation/SKILL_ALIAS_POLICY.md).

## Metrics

The first frozen baseline ran the actual `deterministic-v1.1` matcher three times per case.

| Metric | Result |
| --- | ---: |
| Required Skill Precision | 100.00% |
| Required Skill Recall | 100.00% |
| Required Skill F1 | 100.00% |
| Missing Skill Precision | 100.00% |
| Missing Skill Recall | 100.00% |
| Missing Skill F1 | 100.00% |
| Blocking Risk Precision | 100.00% |
| Blocking Risk Recall | 100.00% |
| Blocking Risk F1 | 100.00% |
| Evidence Validity | 100.00% |
| Evidence-backed Match Rate | 100.00% |
| Unsupported Skill Claim Rate | 0.00% |
| Structured Result Validity | 100.00% |
| Recommendation Agreement | 98.08% |
| Match Band Agreement | N/A |

The result is intentionally not summarized as “CareerPilot accuracy”. These metrics only describe
this small synthetic fixture set. The single labelled failure is `M03`: skill states matched, but
the current score crossed the deterministic recommendation threshold (`STRONGLY_RECOMMENDED`
versus the label's `RECOMMENDED`/`CONSIDER` set). It is retained in
`evaluation/results/FAILURE_ANALYSIS.md` as `RULE_FAILURE`.

## Deterministic vs Semantic vs Hybrid

The deterministic baseline is the primary evaluation. The existing fixed fake-embedding runner is
used only as an offline semantic diagnostic:

- 10 semantic cases;
- recommendation consistency: 90.00%;
- ranking accuracy: 85.71%;
- 7 semantic-case improvements;
- 0 new misjudgments;
- blocking preserved: true;
- incomplete-job recommendation cap preserved: true;
- embedding model: `fake-deterministic-v1`.

Semantic-only Blocking metrics are `N/A`: semantic retrieval has no blocking policy. The semantic
diagnostic does not claim real embedding quality.

## Failure Analysis

The evaluator saves, per failure:

```text
Expected
Actual
Difference
Category
```

Current failure category counts:

```json
{"RULE_FAILURE": 1}
```

Future categories include alias/normalization failure, parsing failure, evidence failure, unknown
handling, semantic false positive/negative and annotation ambiguity. They are kept distinct from
the product matcher and do not silently change labels.

## Evaluation Runner

Run from the project root:

```powershell
backend\.venv\Scripts\python.exe -m evaluation.run
```

The runner loads the manifest, validates duplicate IDs and expected schema, invokes the existing
backend evaluator, computes the requested metrics, writes JSON/Markdown outputs and refuses to
overwrite an existing `evaluation/results/baseline/` directory.

Outputs:

- [evaluation_summary.json](evaluation/results/evaluation_summary.json)
- [evaluation_details.json](evaluation/results/evaluation_details.json)
- [evaluation_report.md](evaluation/results/evaluation_report.md)
- [FAILURE_ANALYSIS.md](evaluation/results/FAILURE_ANALYSIS.md)
- [baseline metadata](evaluation/results/baseline/metadata.json)

Evaluator tests cover metric edge cases, empty datasets, duplicate case IDs, invalid expected
schema, prediction serialization and failure categorization.

## Algorithm Changes

**No matching algorithm was changed before the first baseline.** Specifically, no matching weight,
blocking rule, alias dictionary, threshold or semantic blend weight was changed.

No post-baseline algorithm fix was made in this phase, so no `EVALUATION_CHANGELOG.md` entry is
needed.

## Tests

| Gate | Result |
| --- | --- |
| Product Pytest | 217 passed |
| Product Coverage | 84% |
| Evaluation tests | 6 passed |
| Ruff | PASS (`app tests scripts evaluation`) |
| mypy | 109 source files PASS |
| TypeScript | PASS |
| ESLint | PASS |
| Vitest | 25 files / 91 tests passed |
| Playwright | 16 passed |
| Alembic | 11 migrations on fresh SQLite database PASS |

Two pre-existing non-blocking warnings remain: LangGraph's pending `allowed_objects` default
change and Starlette's deprecated HTTP 422 constant.

## README

README now includes an Evaluation section that states the dataset is synthetic/manually annotated,
reports the real baseline metrics and explains the semantic diagnostic limitations.

## Remaining Limitations

- `eval-v1` is small and synthetic; it is not representative of a hiring population.
- Structured inputs bypass parser evaluation.
- Match Band Agreement is `N/A` because independent band labels do not exist yet.
- Semantic results use controlled fake vectors and are not real-provider quality evidence.
- The current one-case recommendation failure shows that broad score intervals and recommendation
  labels are not identical objectives.
- A future dataset revision must be versioned and must not overwrite this baseline.

## Do Not Proceed

Phase 3 is complete. Do not proceed automatically to Docker / Engineering Phase.

