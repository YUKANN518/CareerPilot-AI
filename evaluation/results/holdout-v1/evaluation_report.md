# Independent Holdout Evaluation — holdout-v1

This is a label-first synthetic holdout authored independently of the regression fixtures.
It is evaluated with the frozen deterministic-v1.1 matcher; no matching rule, weight,
threshold or alias was changed for this run.

- Cases: `20`
- Generated: `2026-09-16`
- Annotation log: `evaluation/dataset/holdout/ANNOTATION_LOG.md`

## Metrics

| Metric | Result |
| --- | ---: |
| Required skill precision | 100.00% |
| Required skill recall | 100.00% |
| Required skill F1 | 100.00% |
| Missing skill precision | 80.00% |
| Missing skill recall | 57.14% |
| Missing skill F1 | 66.66% |
| Blocking risk precision | 66.67% |
| Blocking risk recall | 40.00% |
| Evidence validity | 100.00% |
| Evidence-backed match rate | 100.00% |
| Unsupported skill claim rate | 0.00% |
| Structured result validity | 100.00% |
| Recommendation agreement | 65.00% |
| Match band agreement | 65.00% |
| Preferred skill precision / recall / F1 | 100.00% / 100.00% / 100.00% |
| Eligibility agreement | 60.00% |

## Failure analysis

- Failed cases: `8`
- Categories: `{"RULE_FAILURE": 5, "SKILL_OR_ALIAS_FAILURE": 3}`

| Case | Category | Difference |
| --- | --- | --- |
| H002 | RULE_FAILURE | recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK |
| H003 | SKILL_OR_ALIAS_FAILURE | skill tableau: expected MISSING, actual UNKNOWN |
| H005 | RULE_FAILURE | recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK |
| H006 | SKILL_OR_ALIAS_FAILURE | skill pytorch: expected MISSING, actual UNKNOWN; recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK |
| H007 | SKILL_OR_ALIAS_FAILURE | skill aws: expected MISSING, actual UNKNOWN; recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK |
| H009 | RULE_FAILURE | recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual STRONGLY_RECOMMENDED |
| H012 | RULE_FAILURE | missing blocking risks: [('H012', 'EDUCATION_REQUIREMENT_NOT_MET')]; recommendation: expected ['HIGH_RISK', 'NOT_RECOMMENDED'], actual RECOMMENDED |
| H013 | RULE_FAILURE | missing blocking risks: [('H013', 'LANGUAGE_REQUIREMENT_NOT_MET'), ('H013', 'WORK_ELIGIBILITY_UNKNOWN')]; unexpected blocking risks: [('H013', 'WORK_ELIGIBILITY_BLOCKED')]; recommendation: expected ['CONSIDER', 'HIGH_RISK'], actual NOT_RECOMMENDED |

## Interpretation

This holdout is evidence about deterministic extraction and matching behavior on these
synthetic scenarios only.  It is not a hiring-success benchmark, and no aggregate score
across regression and holdout sets is reported.
