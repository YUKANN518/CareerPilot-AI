# CareerPilot AI Matching Methodology

This document describes the implemented matching contract. It is a product and engineering
disclosure, not a claim that the score predicts hiring outcomes.

## Decision contract

CareerPilot AI uses the following boundary:

```text
LLM-compatible parser structures resume fields
→ verbatim evidence validation rejects unsupported skill quotes
→ the user reviews and confirms an immutable resume version
→ deterministic code extracts job requirements and decides skill/risk outcomes
→ optional semantic retrieval contributes only a relevance signal
→ the report renders stored results and evidence
```

Only a user-confirmed resume version can enter matching. A resume skill receives full matched
credit only when a normalized equivalent exists and the version contains non-empty,
user-confirmed evidence. Free text, semantic similarity and generated explanations cannot create
a skill conclusion.

## Inputs and snapshots

The calculation consumes:

- one immutable confirmed `ResumeVersion`, including structured fields and evidence-backed
  `ResumeSkill` records;
- one Job, including description, requirements, responsibilities and structured `JobSkill`
  records;
- optional user-profile preferences and work-eligibility state;
- one versioned scoring configuration.

Each successful report stores the resume version identity, job identity and content hash, a job
text snapshot, extracted requirement snapshot, scoring configuration, policy version, evidence
traces and final result arrays. Historical reports therefore remain readable if the live Job is
later edited. Deleting a resume intentionally cascades its reports, so this is not a permanent
audit archive.

## Job requirement extraction

`job-requirements-v1` performs deterministic extraction. Skills come from stored JobSkill rows,
structured raw-data lists and dictionary-backed mentions in the requirement text. Required and
preferred skill types remain distinct. Experience, education, language, certificates and work
eligibility retain both availability and explicit required/preferred markers when the source text
supports them.

An absent job criterion is `NOT_PROVIDED`, not satisfied. Ambiguous candidate evidence becomes
`UNKNOWN` or `UNVERIFIED`, not a confirmed conflict.

## Deterministic score

`deterministic-v1.1` has six dimensions. The weights total 100 and were not changed in Phase 2.

| Dimension | Weight | Implemented rule |
| --- | ---: | --- |
| Hard skills | 35% | Canonical skill equality; required skills have weight 2 and preferred skills weight 1. |
| Evidence strength | 20% | Confirmed evidence count, locator/source quality, work/project source and evidence specificity. |
| Experience and education | 15% | Average of non-overlapping dated work experience and ordered education-level comparisons. |
| Language, location and eligibility | 10% | Explicit language/location/work-eligibility comparison; unknown candidate facts are neutral, not passes. |
| User preferences | 10% | Optional location, employment type, role, salary and industry preference comparison. |
| Other conditions | 10% | Explicit certificate and other deterministic condition checks. |

For each dimension:

```text
weighted contribution = dimension score × dimension weight / 100
rule score = sum of all six weighted contributions
```

The report stores the score, weight, contribution, explanation, evidence keys and gap codes for
each dimension. Display statuses (`GOOD`, `PARTIAL`, `WEAK`) summarize score bands; they do not
change the calculation.

## Skill conclusions and evidence coverage

Skill conclusions are:

- `MATCHED`: normalized equivalent plus confirmed, non-empty resume evidence;
- `PARTIAL`: a skill record exists but evidence or confirmation is incomplete;
- `MISSING`: no normalized equivalent exists in the confirmed skill set;
- `UNKNOWN`: the job term cannot be safely resolved by the skill dictionary.

The Evidence Coverage panel counts these states for skill requirements. Its percentage is
`MATCHED / all skill requirements`. It is a disclosure metric only and is not an extra scoring
dimension.

Every displayed matched skill can link to the resume quote, human-readable source category and
source locator. Each gap states the job requirement, candidate evidence state and deterministic
reason.

## Semantic relevance and hybrid score

`hybrid-v1` retrieves compatible resume/job text chunks through local embeddings and FAISS. It
retains top-K pairs above the configured similarity threshold and computes a normalized relevance
score. The formula is:

```text
hybrid score = deterministic rule score × 70%
             + semantic relevance score × 30%
```

Semantic relevance can reflect transferable or conceptually similar experience. It cannot mark a
skill as matched, fabricate resume evidence, remove a risk, or override a recommendation cap. The
report labels it as a supporting signal and shows both sides of each retained evidence pair.

## Skill Gaps versus Blocking Risks

A required skill that is not matched is a `SKILL_GAP`. It remains separate from qualification
blocking and does not become a `BLOCKING_RISK` merely because it is required.

`blocking-policy-v1` recognizes a confirmed conflict only from explicit rules such as:

- work-eligibility conflict;
- mandatory language mismatch;
- mandatory certificate absence or mismatch;
- explicit non-substitutable education shortfall;
- an explicit experience minimum missed by at least three years.

A known contradiction is `CONFLICT`; a mandatory fact that cannot yet be verified is
`UNVERIFIED`. Only a true `BLOCKING` severity forces `NOT_RECOMMENDED`. A high semantic score
cannot cancel that decision. Low job-information completeness can also cap the recommendation and
lower report confidence.

## Explanation safety

Current report explanations are produced by deterministic application code from stored
calculation artifacts. There is no LLM report-explanation path. If a generated narrative is added
later, it must receive the calculation only after scoring and must remain read-only: it may
paraphrase but must not modify scores, statuses, risks, recommendation or evidence.

## Failure behavior

The system fails explicitly when:

- the resume version is not confirmed;
- no confirmed skill evidence exists;
- the resume or Job is missing or inaccessible;
- a semantic/index stage requested by hybrid mode fails.

It does not substitute fabricated evidence or silently fall back to a fake production result.

## Limitations

- Dictionary equality and explicit text rules can miss uncommon aliases or nuanced requirements.
- Resume parsing quality depends on extraction quality and still requires human review.
- Neutral handling of unknown candidate facts avoids false negatives but may inflate a numeric
  dimension compared with a fully observed profile; the report therefore exposes unknowns and
  confidence separately.
- Semantic similarity measures textual relevance, not verified proficiency or hiring success.
- Scores are decision support for one resume/Job pair, not a probability of interview or offer.

