"""Run the released deterministic matcher against the independent holdout JSON.

The command intentionally reuses :class:`EvaluationExecutor`; it only adapts the
label-first holdout representation into the existing fixture schema.  It does not
change matching rules, weights, aliases, thresholds, or policy configuration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from app.schemas.matching import RecommendationLevel
from evaluation.matching.executor import EvaluationExecutor
from evaluation.matching.schemas import (
    CaseCategory,
    EvaluationLabel,
    JobFixture,
    JobSkillFixture,
    ResumeFixture,
)


def _score_interval(band: str) -> tuple[float, float]:
    return {
        "HIGH": (75.0, 100.0),
        "MODERATE": (45.0, 84.99),
        "LOW": (0.0, 54.99),
    }.get(band, (0.0, 100.0))


def load_holdout(path: Path) -> tuple[str, list[dict[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("dataset_version") != "holdout-v1":
        raise ValueError("holdout input must declare dataset_version=holdout-v1")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("holdout input must contain a non-empty cases list")
    return str(payload["dataset_version"]), cases


def run(path: Path, scoring_version: str = "deterministic-v1.1") -> dict[str, object]:
    dataset_version, cases = load_holdout(path)
    resumes: list[ResumeFixture] = []
    jobs: list[JobFixture] = []
    labels: list[EvaluationLabel] = []
    for raw in cases:
        case = cast(dict[str, Any], raw)
        case_id = str(case["case_id"])
        resume_payload = {"fixture_id": f"{case_id}-resume", **case["resume"]}
        job_payload = dict(case["job"])
        job_payload["fixture_id"] = f"{case_id}-job"
        job_payload["skills"] = [
            JobSkillFixture.model_validate(item) for item in job_payload["skills"]
        ]
        resumes.append(ResumeFixture.model_validate(resume_payload))
        jobs.append(JobFixture.model_validate(job_payload))
        expected = dict(case["expected"])
        score_min, score_max = _score_interval(str(expected.get("match_band", "")))
        labels.append(
            EvaluationLabel(
                case_id=case_id,
                category=CaseCategory(str(case["category"])),
                resume_fixture=f"{case_id}-resume",
                job_fixture=f"{case_id}-job",
                expected_score_min=score_min,
                expected_score_max=score_max,
                expected_recommendations=[
                    RecommendationLevel(item) for item in expected.get("recommendations", [])
                ],
                expected_matched_skills=list(expected.get("matched_skills", [])),
                expected_partial_skills=list(expected.get("partial_skills", [])),
                expected_missing_skills=list(expected.get("missing_skills", [])),
                expected_unknown_skills=list(expected.get("unknown_skills", [])),
                expected_blocking_risks=list(expected.get("blocking_risks", [])),
                notes=str(case.get("rationale", "")),
            )
        )

    executor = EvaluationExecutor(resumes, jobs)
    results = [executor.run_case(label, scoring_version=scoring_version) for label in labels]
    return {
        "dataset_version": dataset_version,
        "scoring_version": scoring_version,
        "case_count": len(results),
        "cases": cases,
        "results": [item.model_dump(mode="json") for item in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run holdout-v1 through deterministic matching")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scoring-version", default="deterministic-v1.1")
    args = parser.parse_args()
    payload = run(args.input, args.scoring_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"dataset_version": payload["dataset_version"], "case_count": payload["case_count"]}
        )
    )


if __name__ == "__main__":
    main()
