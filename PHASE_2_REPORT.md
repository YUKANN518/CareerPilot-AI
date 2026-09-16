# CareerPilot AI Phase 2 Report

Completed on 2026-09-16. Phase 2 strengthened the existing
`Resume → Job → Match → Explainable Report` path. It did not add a business module, change the
matching dimensions, change weights, or expand the AI Assistant.

## Core Flow

```text
Resume upload and extraction
→ AI-compatible structured parsing
→ verbatim skill-evidence validation
→ human review and immutable confirmed ResumeVersion
→ deterministic Job requirement extraction
→ deterministic-v1.1 scoring
→ optional FAISS semantic relevance for hybrid-v1
→ deterministic blocking policy
→ stored report, input snapshot and evidence traces
→ explainable Match Report
```

Unconfirmed resume versions remain ineligible for matching. Confirmed versions without any
confirmed skill evidence fail explicitly. Semantic-stage failures do not create a fake score.

## Explainability Improvements

- Added dimension status, evidence keys and gap codes to the existing six-dimension contract.
- Classified report risks as `SKILL_GAP`, `BLOCKING_RISK` or `GENERAL_RISK` and exposed
  `CONFIRMED`, `UNVERIFIED` and `CONFLICT` verification states.
- Added a non-scoring Evidence Coverage summary with verified, partial, missing and unknown counts.
- Added lightweight immutable resume/job input snapshots to existing report metadata; no schema
  migration was required.
- Added readable evidence source categories: Education, Project Experience, Work Experience,
  Skill Section and Other Resume Text.
- Added stored-input, scoring-version and policy disclosure to historical reports.

## Match Report UI

The primary report now presents:

- Overall Match with deterministic score bands and Human Verified Resume status;
- the stored matching version and input snapshot;
- a collapsible “How this score was calculated” section with the real weights;
- Evidence Coverage as a disclosure metric, not an added score;
- Semantic Relevance explicitly labeled as a supporting signal;
- structured Required Skills, Preferred Skills and qualification requirements;
- expandable six-dimension explanations with evidence/gap counts;
- inline verified skill quotes and human-readable source categories;
- gap reason, Job requirement and “No verified evidence found” states;
- a separate Blocking Risk section, distinct from Skill Gaps and general risks;
- explicit empty, loading, authorization and failure states through the existing page-state system.

The match-start page now uses “Evidence-grounded match”, makes Human Verified status visible and
states that semantic similarity cannot prove a skill or cancel a qualification conflict.

## Algorithm and Safety Boundaries

The deterministic weights remain:

| Dimension | Weight |
| --- | ---: |
| Hard skills | 35% |
| Evidence strength | 20% |
| Experience and education | 15% |
| Language, location and eligibility | 10% |
| User preferences | 10% |
| Other conditions | 10% |

`hybrid-v1` remains 70% `deterministic-v1.1` plus 30% Semantic Relevance. Semantic text cannot
create a skill match. Blocking severity and recommendation caps survive the hybrid combination.
Required skill gaps remain distinct from eligibility blocking.

**No matching weights were changed.**

The current report explanation is deterministic application text; no LLM report-explanation path
exists. A contract test additionally proves that replacing narrative text cannot mutate the stored
score, skill arrays or risks.

## Tests

| Gate | Phase 1B | Phase 2 | Result |
| --- | ---: | ---: | --- |
| Pytest | 213 passed | **217 passed** | PASS |
| Coverage | 84% | **84%** | PASS |
| Ruff | PASS | **PASS** | PASS |
| mypy `app` | 109 source files | **109 source files** | PASS |
| TypeScript | PASS | **PASS** | PASS |
| ESLint | PASS | **PASS** | PASS |
| Vitest | 25 files / 89 tests | **25 files / 91 tests** | PASS |
| Playwright | 16 tests | **16 tests** | PASS |
| Alembic | 11 migrations | **11 migrations on a fresh SQLite DB** | PASS |

New backend coverage proves that:

- untrusted/semantic-like resume text cannot fabricate Docker evidence;
- a missing required skill is reported as a Skill Gap;
- an unverified mandatory qualification is a separate Blocking Risk;
- existing hybrid tests preserve blocking regardless of semantic score;
- narrative explanation text cannot alter deterministic results;
- historical input snapshots remain stable after a live Job edit;
- existing unverified-resume rejection remains enforced.

Frontend tests cover evidence rendering, gap reasons, blocking states, dimension explanation and
empty/error states. The portfolio E2E now uses a seeded Job with a verified Python match and a
missing Docker requirement, and asserts score, evidence, matched skills, missing skills,
Semantic Relevance and Blocking Risk sections.

Two pre-existing non-blocking warnings remain: LangGraph's pending `allowed_objects` default
change and Starlette's deprecated HTTP 422 constant.

## Added Files

- `CORE_FLOW_AUDIT.md`
- `MATCHING_METHODOLOGY.md`
- `PHASE_2_REPORT.md`

## Modified Files

- `README.md`
- `backend/app/schemas/matching.py`
- `backend/app/matching/scoring.py`
- `backend/app/services/matching.py`
- `backend/app/services/resumes.py`
- `backend/tests/test_matching.py`
- `frontend/src/types/matching.ts`
- `frontend/src/pages/MatchNewPage.vue`
- `frontend/src/pages/MatchReportPage.vue`
- `frontend/src/components/domain/MatchEvidenceDrawer.vue`
- `frontend/tests/unit/match-fixture.ts`
- `frontend/tests/unit/match-new.spec.ts`
- `frontend/tests/unit/match-report.spec.ts`
- `frontend/tests/e2e/matching.spec.ts`
- `frontend/tests/e2e/portfolio-main-flow.spec.ts`

## Remaining Limitations

- The rule dictionary can miss unusual skill aliases and nuanced prose.
- Resume parsing remains dependent on document extraction quality and human confirmation.
- Unknown candidate facts receive neutral scoring treatment, so confidence/unknown disclosures
  must be considered alongside the numeric score.
- Semantic relevance measures text similarity, not verified proficiency or hiring probability.
- Historical reports are removed when their source resume is intentionally deleted.
- Real provider connectivity, latency, cost and wording quality remain outside the offline suite.

## Do Not Proceed

Phase 2 is complete. Do not enter the Evaluation Phase automatically.

