# Evaluation Failure Analysis

Failures are reported against manually annotated synthetic labels; they are not silently
removed from the baseline.

## M03

- Category: `RULE_FAILURE`
- Expected: `{"blocking_risks": [], "recommendations": ["CONSIDER", "RECOMMENDED"], "skills": {"javascript": "MATCHED", "typescript": "PARTIAL", "vue": "MATCHED"}}`
- Actual: `{"blocking_risks": [], "recommendation": "STRONGLY_RECOMMENDED", "skills": {"javascript": "MATCHED", "typescript": "PARTIAL", "vue": "MATCHED"}}`
- Difference:
  - recommendation: expected ['CONSIDER', 'RECOMMENDED'], actual STRONGLY_RECOMMENDED
