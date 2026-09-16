from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectedMatchOutcome:
    minimum_score: float
    maximum_score: float
    required_risks: frozenset[str]
    forbidden_risks: frozenset[str] = frozenset()
    recommendation: str | None = None


MATCH_FIXTURES = {
    "high_match": ExpectedMatchOutcome(
        85,
        100,
        frozenset(),
        frozenset({"REQUIRED_SKILL_MISSING", "MINIMUM_EXPERIENCE_NOT_MET"}),
    ),
    "medium_match": ExpectedMatchOutcome(
        55,
        85,
        frozenset({"REQUIRED_SKILL_MISSING"}),
    ),
    "skill_gap": ExpectedMatchOutcome(
        0,
        60,
        frozenset({"REQUIRED_SKILL_MISSING"}),
    ),
    "eligibility_blocked": ExpectedMatchOutcome(
        0,
        100,
        frozenset({"WORK_ELIGIBILITY_BLOCKED"}),
        recommendation="NOT_RECOMMENDED",
    ),
    "incomplete_job": ExpectedMatchOutcome(
        90,
        100,
        frozenset({"JOB_REQUIREMENTS_INCOMPLETE"}),
    ),
    "insufficient_evidence": ExpectedMatchOutcome(
        55,
        85,
        frozenset({"REQUIRED_SKILL_PARTIAL"}),
    ),
    "graduate_role": ExpectedMatchOutcome(
        85,
        100,
        frozenset(),
        frozenset({"MINIMUM_EXPERIENCE_NOT_MET", "EXPERIENCE_UNKNOWN"}),
    ),
}
