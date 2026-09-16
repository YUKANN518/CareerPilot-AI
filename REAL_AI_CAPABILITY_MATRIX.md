# CareerPilot AI — Real AI Capability Matrix

Updated: 2026-09-16 (Phase 4.6 Product Path Closure)

| Feature | Portfolio role | Real validated | Product status / evidence |
| --- | --- | --- | --- |
| Resume parsing | CORE | YES | Real DeepSeek product smoke; 6/6 direct cases; evidence and `ModelUsageLog` verified |
| Job input | CORE | Deterministic | Structured manual input and CSV import; no product LLM parser by design |
| Matching | CORE | YES | Deterministic/hybrid match-run, blocking and human review flow passed |
| Explainable match report | CORE | YES | Dimension explanations, evidence traceability, blocking risk and input snapshot passed |
| Applications | CORE | YES | Lightweight application tracking remains in the main product path and regression suite |
| Career Assistant | OPTIONAL | Real Dify not validated | Formal API and Fake mode pass; Dify is an optional integration |
| Resume Optimization | HIDDEN | NO | Retained implementation/tests, excluded from the portfolio path |
| Chat Interview | HIDDEN | NO | Retained implementation/tests, excluded from the portfolio path |

## Verified Phase 4.5 direct-provider numbers

- Resume: 6 cases (3 PDF, 3 DOCX), 6 structured-valid successes, 18 skills, 100% average
  evidence attachment, 0 unsupported skills, average latency 14,142.33 ms, tokens
  13,728 / 23,385 / 37,113 (input/output/total).
- Job contract: 10 cases, 10 structured-valid successes, 26 required entries and 9 preferred
  entries, average latency 7,036.80 ms, tokens 6,940 / 15,572 / 22,512.
- Direct QA contract: 10 questions, 7 provider calls, 3 deterministic unsupported prechecks,
  average latency 2,923.86 ms, tokens 5,734 / 3,097 / 8,831. Citation correctness and
  groundedness remain manual-review fields.

## Release decision

`READY_FOR_PORTFOLIO_ENGINEERING = true` for the frozen Core Features scope. The absence of a
product LLM Job parser is intentional, and the formal Career Assistant Dify path is optional;
neither blocks portfolio engineering.

No matching algorithm, weights, thresholds, blocking rules or holdout labels were changed.
