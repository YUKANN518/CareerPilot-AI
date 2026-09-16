# holdout-v1 annotation log

Annotation date: 2026-09-16  
Annotation order: Resume + Job + Expected outcome were authored and frozen before the first
holdout system execution.  The file `cases.json` is therefore a label-first artifact, not a
post-hoc transcription of matcher output.

This set contains 20 new synthetic Resume–Job pairs.  None reuses the backend evaluation
fixtures, `sample_data`, demo jobs, or the 52-case `eval-v1` labels.  Expected skills are
canonical names where the current dictionary has one; an unfamiliar product name remains an
explicit missing/unknown expectation.  A blocking risk is listed only when the frozen
blocking-policy-v1 should classify an explicit conflict as BLOCKING.

| Case | Expected outcome | Annotation rationale |
| --- | --- | --- |
| H001 | High; Python/FastAPI/PostgreSQL/Docker matched; no blocker | Confirmed backend stack and 3+ years meet the posting. |
| H002 | Moderate; Docker missing | Required container packaging is absent while core API skills match. |
| H003 | Moderate; SQL/Python matched; analytics/Tableau missing | Required skills are present; optional analytics signals are absent. |
| H004 | High; Docker/Kubernetes/CI-CD matched | Containerized workload wording is backed by explicit canonical skills. |
| H005 | Moderate; PostgreSQL missing; SQL/Python matched | Relational database knowledge is not assumed to equal PostgreSQL administration. |
| H006 | Moderate; PyTorch missing; Python/ML matched | Generic AI/ML evidence is not silently promoted to PyTorch. |
| H007 | Moderate; AWS and Docker missing; Python matched | Cloud is not assumed to mean AWS. |
| H008 | High; fresh graduate exception; Python/Git matched | Zero years is acceptable for an explicitly graduate-friendly role. |
| H009 | Moderate; internship context; JavaScript/React matched | Internship/student wording does not create a senior experience gap. |
| H010 | Low/high risk; 4-year minimum vs 1 year | Large explicit experience gap is a blocking-policy case. |
| H011 | High; preferred experience non-blocking | “Preferred, not required” must not become a hard failure. |
| H012 | Low/high risk; non-related mandatory degree | Communications degree is not a CS/related technical degree. |
| H013 | Unverified; Cantonese and HK eligibility unresolved | Written English is required; Cantonese is preferred; work eligibility is unknown. |
| H014 | High; Cantonese and HK eligibility confirmed | Both language context and explicit eligibility are satisfied. |
| H015 | Low/high risk; known HK ineligibility | Explicit authorization conflict is a true blocker. |
| H016 | High; hybrid arrangement compatible | Hybrid is contextual and does not alter technical skill status. |
| H017 | High; on-site arrangement compatible | Matching city satisfies the explicit on-site context. |
| H018 | Moderate/unverified; sparse posting | Missing job criteria lower confidence; no requirements are invented. |
| H019 | Moderate/unverified; Docker partial | Resume names Docker but confirmation/evidence is intentionally absent. |
| H020 | High; graduate programme; all skills matched | Final-year/recent-graduate wording avoids a seniority penalty. |

No row was changed after the first frozen matcher run.  Any mismatch is retained as an honest
holdout failure and is discussed in the Phase 3.5 report rather than repaired by changing the
labels or matching rules.
