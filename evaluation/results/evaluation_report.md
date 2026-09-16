# CareerPilot AI Matching Evaluation

- Dataset: `eval-v1`
- Dataset type: manually annotated synthetic resume-job pairs
- Scoring version: `deterministic-v1.1`
- Repeats per case: `3`
- Generated: `2026-09-16T07:01:28.195461+00:00`

## Primary Metrics

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
| Match Band Agreement (secondary) | N/A |

## Deterministic vs Semantic vs Hybrid

The primary baseline evaluates the released deterministic matcher. The semantic
runner uses the fixed fake embedding provider only as an offline relevance and
blocking-preservation diagnostic. Semantic-only blocking metrics are `N/A` because
semantic retrieval has no blocking policy of its own.

| Mode | Required Skill F1 | Blocking Risk Recall / Preservation | Evidence Validity |
| --- | ---: | ---: | ---: |
| Deterministic `deterministic-v1.1` | 100.00% | 100.00% | 100.00% |
| Semantic Only | N/A | N/A | N/A |
| Hybrid diagnostic | N/A | 100.00% | N/A |

## Failure Analysis

- Failed cases: `1`
- Categories: `{"RULE_FAILURE": 1}`
- Details: `FAILURE_ANALYSIS.md`

## Algorithm Changes

No matching algorithm was changed before this baseline. The evaluation layer invokes
the existing requirement extractor, deterministic scorer and offline hybrid runner.

## Limitations

- The dataset is synthetic and manually annotated; it is not a hiring-success benchmark.
- Structured fixtures begin after parsing, so parser quality is not measured here.
- Semantic relevance is evaluated with controlled fake vectors, not a real provider.
- Match Band Agreement is `N/A` until independent band labels are added.
- Metrics describe this fixture set and should not be generalized to a population.
