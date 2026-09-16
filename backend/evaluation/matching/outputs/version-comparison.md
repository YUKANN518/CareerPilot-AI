# Version Comparison

## Status

`deterministic-v1.1` is a reviewed backend candidate. It preserves deterministic-v1 rule_score,
uses `blocking-policy-v1`, and applies configured completeness caps. It is not the production
default and the evaluation runner creates no database reports.

## Metric comparison

| Metric | deterministic-v1 | deterministic-v1.1 |
| --- | ---: | ---: |
| Blocking precision | 100.00% | 100.00% |
| Blocking recall | 11.76% | 100.00% |
| Recommendation consistency | 55.77% | 98.08% |
| Score interval hit rate | 100.00% | 100.00% |
| Skill macro F1 | 100.00% | 100.00% |
| Evidence coverage | 100.00% | 100.00% |
| Repeat consistency | 100.00% | 100.00% |

## Observed changes

- Cases compared: 52.
- Score changes: 0.
- Risk changes: 16.
- Recommendation changes: 27.
- New Blocking false positives: none.
- Remaining Blocking false negatives: none.

| Case | deterministic-v1 | v1.1 candidate |
| --- | --- | --- |
| H05 | STRONGLY_RECOMMENDED | RECOMMENDED |
| H06 | STRONGLY_RECOMMENDED | RECOMMENDED |
| H07 | STRONGLY_RECOMMENDED | RECOMMENDED |
| M05 | STRONGLY_RECOMMENDED | RECOMMENDED |
| M08 | STRONGLY_RECOMMENDED | RECOMMENDED |
| B02 | HIGH_RISK | NOT_RECOMMENDED |
| B03 | HIGH_RISK | NOT_RECOMMENDED |
| B04 | HIGH_RISK | NOT_RECOMMENDED |
| B05 | HIGH_RISK | NOT_RECOMMENDED |
| I01 | STRONGLY_RECOMMENDED | CONSIDER |
| I02 | STRONGLY_RECOMMENDED | CONSIDER |
| I03 | STRONGLY_RECOMMENDED | CONSIDER |
| E02 | STRONGLY_RECOMMENDED | RECOMMENDED |
| N01 | STRONGLY_RECOMMENDED | NOT_RECOMMENDED |
| N03 | HIGH_RISK | NOT_RECOMMENDED |
| N04 | HIGH_RISK | NOT_RECOMMENDED |
| N05 | HIGH_RISK | RECOMMENDED |
| N06 | STRONGLY_RECOMMENDED | RECOMMENDED |
| N08 | HIGH_RISK | NOT_RECOMMENDED |
| N09 | STRONGLY_RECOMMENDED | RECOMMENDED |
| N11 | HIGH_RISK | NOT_RECOMMENDED |
| N14 | HIGH_RISK | NOT_RECOMMENDED |
| N15 | HIGH_RISK | NOT_RECOMMENDED |
| N16 | STRONGLY_RECOMMENDED | CONSIDER |
| N17 | HIGH_RISK | NOT_RECOMMENDED |
| N19 | STRONGLY_RECOMMENDED | CONSIDER |
| N20 | HIGH_RISK | NOT_RECOMMENDED |

## Release gates

| Gate | Result |
| --- | --- |
| Blocking recall >= 90% | PASS |
| Blocking precision >= 95% | PASS |
| Recommendation consistency >= 85% | PASS |
| Skill macro F1 does not regress | PASS |
| Evidence coverage does not regress | PASS |
| Repeat consistency is 100% | PASS |
| Ranking does not regress | PASS |
| I01-I03 are capped | PASS |

## Decision

Quantitative release gates: PASS. The candidate remains
non-default until the existing deterministic-v1 API/UI contract receives a separately approved
version-selection and presentation change. deterministic-v1 remains queryable, reproducible,
and unchanged.
