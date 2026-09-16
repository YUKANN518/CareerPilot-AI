# Holdout Failure Analysis

## H002

- Category: `RULE_FAILURE`
- Difference: recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK

## H003

- Category: `SKILL_OR_ALIAS_FAILURE`
- Difference: skill tableau: expected MISSING, actual UNKNOWN

## H005

- Category: `RULE_FAILURE`
- Difference: recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK

## H006

- Category: `SKILL_OR_ALIAS_FAILURE`
- Difference: skill pytorch: expected MISSING, actual UNKNOWN; recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK

## H007

- Category: `SKILL_OR_ALIAS_FAILURE`
- Difference: skill aws: expected MISSING, actual UNKNOWN; recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual HIGH_RISK

## H009

- Category: `RULE_FAILURE`
- Difference: recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual STRONGLY_RECOMMENDED

## H012

- Category: `RULE_FAILURE`
- Difference: missing blocking risks: [('H012', 'EDUCATION_REQUIREMENT_NOT_MET')]; recommendation: expected ['HIGH_RISK', 'NOT_RECOMMENDED'], actual RECOMMENDED

## H013

- Category: `RULE_FAILURE`
- Difference: missing blocking risks: [('H013', 'LANGUAGE_REQUIREMENT_NOT_MET'), ('H013', 'WORK_ELIGIBILITY_UNKNOWN')]; unexpected blocking risks: [('H013', 'WORK_ELIGIBILITY_BLOCKED')]; recommendation: expected ['CONSIDER', 'HIGH_RISK'], actual NOT_RECOMMENDED
