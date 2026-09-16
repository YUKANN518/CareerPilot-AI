# Evaluation Annotation Guidelines

These guidelines define labels for the manually authored `eval-v1` synthetic dataset. They are
decision-support labels, not claims about hiring outcomes.

## Matched Skill

Use `MATCHED` only when the resume evidence explicitly supports the normalized job skill and the
evidence is attributable to the candidate's resume fixture. A bare nearby concept is not enough.

## Partial Evidence

Use `PARTIAL` when a resume skill record exists but confirmation or usable evidence is incomplete.
Do not treat a name-only or unconfirmed record as fully verified.

## Missing Skill

Use `MISSING` when no supported normalized skill record exists in the candidate fixture. The
requirement remains a gap even if semantically related text appears elsewhere.

## Unknown Skill

Use `UNKNOWN` when the job term cannot be safely resolved by the released dictionary. Unknown is
not the same as missing and should not be silently converted into a failure.

## Blocking Risk

Use a blocking label only when the released deterministic policy recognizes an explicit hard
qualification conflict. Examples include an explicit work-authorization conflict, mandatory
language mismatch, mandatory certificate absence, non-substitutable education shortfall, or an
experience gap at the configured threshold.

## General Risk and Unverified

`UNVERIFIED` means the evidence needed to decide is absent or ambiguous. `CONFLICT` means the
available candidate evidence contradicts an explicit requirement. Unknown eligibility is not an
automatic eligibility pass and is not automatically a confirmed conflict.

## Semantic Related ≠ Skill Verified

The following are intentionally not skill aliases unless the skill itself is explicitly present:

```text
deployed containerized services  ≠ Docker
containerization                ≠ Docker
AI                              ≠ PyTorch
machine learning project        ≠ TensorFlow
database                        ≠ MySQL
cloud                           ≠ AWS
```

Semantic retrieval may provide relevant context, but it must not change a skill label or create
resume evidence.

## Match Band

If a future dataset adds independent bands, use the product thresholds: `HIGH` >= 85,
`MODERATE` >= 55, and `LOW` below 55. Band agreement is secondary to skill, evidence and blocking
metrics because human band judgements are subjective.

