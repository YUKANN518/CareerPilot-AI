from __future__ import annotations

from collections import Counter
from collections.abc import Hashable
from typing import Any, TypeVar

MetricKey = TypeVar("MetricKey", bound=Hashable)


def safe_ratio(numerator: float, denominator: float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0


def canonical(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _expected_statuses(label: dict[str, Any]) -> dict[str, str]:
    return {
        canonical(skill): status
        for field, status in (
            ("expected_matched_skills", "MATCHED"),
            ("expected_partial_skills", "PARTIAL"),
            ("expected_missing_skills", "MISSING"),
            ("expected_unknown_skills", "UNKNOWN"),
        )
        for skill in label.get(field, [])
    }


def _actual_statuses(result: dict[str, Any]) -> dict[str, str]:
    return {canonical(name): str(status) for name, status in result.get("skill_statuses", {}).items()}


def _skill_sets(
    label: dict[str, Any],
    result: dict[str, Any],
    jobs_by_id: dict[str, dict[str, Any]],
) -> tuple[set[str], set[str], set[str], set[str]]:
    expected = _expected_statuses(label)
    actual = _actual_statuses(result)
    job = jobs_by_id[label["job_fixture"]]
    required = {
        canonical(item["name"])
        for item in job.get("skills", [])
        if item.get("required", True)
    }
    expected_required_matched = {
        skill for skill, status in expected.items() if status == "MATCHED" and skill in required
    }
    actual_required_matched = {
        skill for skill, status in actual.items() if status == "MATCHED" and skill in required
    }
    expected_missing = {skill for skill, status in expected.items() if status == "MISSING"}
    actual_missing = {skill for skill, status in actual.items() if status == "MISSING"}
    return (
        expected_required_matched,
        actual_required_matched,
        expected_missing,
        actual_missing,
    )


def _precision_recall(
    expected: set[MetricKey],
    actual: set[MetricKey],
) -> dict[str, float]:
    true_positive = len(expected & actual)
    precision = safe_ratio(true_positive, len(actual))
    recall = safe_ratio(true_positive, len(expected))
    return {"precision": precision, "recall": recall, "f1": f1(precision, recall)}


def _evidence_backed_claims(result: dict[str, Any]) -> tuple[int, int]:
    matched = {
        canonical(name)
        for name, status in result.get("skill_statuses", {}).items()
        if status == "MATCHED"
    }
    backed: set[str] = set()
    for signature in result.get("evidence_signature", []):
        parts = str(signature).split("|", 4)
        if len(parts) >= 3 and parts[1] and parts[2]:
            backed.add(canonical(parts[0]))
    return len(matched & backed), len(matched)


def _structured_result_valid(result: Any) -> bool:
    required = {
        "case_id",
        "category",
        "scoring_version",
        "rule_score",
        "skill_statuses",
        "risks",
        "evidence_signature",
        "config_snapshot",
    }
    return isinstance(result, dict) and required <= result.keys()


def calculate_metrics(
    labels: list[dict[str, Any]],
    results: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    results_by_id = {result.get("case_id"): result for result in results}
    jobs_by_id = {job["fixture_id"]: job for job in jobs}
    required_expected: set[str] = set()
    required_actual: set[str] = set()
    missing_expected: set[str] = set()
    missing_actual: set[str] = set()
    blocking_expected: set[tuple[str, str]] = set()
    blocking_actual: set[tuple[str, str]] = set()
    evidence_backed = 0
    evidence_claims = 0
    valid_results = 0
    recommendation_hits = 0
    band_labels = 0
    band_hits = 0
    failures: list[dict[str, Any]] = []

    for label in labels:
        case_id = label["case_id"]
        result = results_by_id.get(case_id)
        if result is None:
            failures.append(
                {
                    "case_id": case_id,
                    "category": "STRUCTURED_RESULT_FAILURE",
                    "expected": label,
                    "actual": None,
                    "difference": "missing prediction",
                }
            )
            continue
        valid_results += _structured_result_valid(result)
        expected_req, actual_req, expected_missing_case, actual_missing_case = _skill_sets(
            label,
            result,
            jobs_by_id,
        )
        required_expected.update(f"{case_id}:{skill}" for skill in expected_req)
        required_actual.update(f"{case_id}:{skill}" for skill in actual_req)
        missing_expected.update(f"{case_id}:{skill}" for skill in expected_missing_case)
        missing_actual.update(f"{case_id}:{skill}" for skill in actual_missing_case)
        expected_risks = {
            (case_id, code) for code in label.get("expected_blocking_risks", [])
        }
        actual_risks = {
            (case_id, code)
            for code, severity in result.get("risks", {}).items()
            if severity == "BLOCKING"
        }
        blocking_expected.update(expected_risks)
        blocking_actual.update(actual_risks)
        backed, claims = _evidence_backed_claims(result)
        evidence_backed += backed
        evidence_claims += claims
        expected_recommendations = set(label.get("expected_recommendations", []))
        recommendation_hits += result.get("recommendation") in expected_recommendations
        expected_band = label.get("expected_match_band")
        if expected_band:
            band_labels += 1
            band_hits += _score_band(float(result.get("rule_score", 0))) == expected_band

        expected_status = _expected_statuses(label)
        actual_status = _actual_statuses(result)
        differences: list[str] = []
        for skill, status in expected_status.items():
            if actual_status.get(skill, "UNKNOWN") != status:
                differences.append(
                    f"skill {skill}: expected {status}, actual {actual_status.get(skill, 'UNKNOWN')}"
                )
        missing_blocking = sorted(expected_risks - actual_risks)
        extra_blocking = sorted(actual_risks - expected_risks)
        if missing_blocking:
            differences.append(f"missing blocking risks: {missing_blocking}")
        if extra_blocking:
            differences.append(f"unexpected blocking risks: {extra_blocking}")
        if result.get("recommendation") not in expected_recommendations:
            differences.append(
                f"recommendation: expected {sorted(expected_recommendations)}, "
                f"actual {result.get('recommendation')}"
            )
        if differences:
            failures.append(
                {
                    "case_id": case_id,
                    "category": _failure_category(label, result, differences),
                    "expected": {
                        "skills": expected_status,
                        "blocking_risks": sorted(expected_risks),
                        "recommendations": sorted(expected_recommendations),
                    },
                    "actual": {
                        "skills": actual_status,
                        "blocking_risks": sorted(actual_risks),
                        "recommendation": result.get("recommendation"),
                    },
                    "difference": differences,
                }
            )

    required = _precision_recall(required_expected, required_actual)
    missing = _precision_recall(missing_expected, missing_actual)
    blocking = _precision_recall(blocking_expected, blocking_actual)
    unsupported_claims = evidence_claims - evidence_backed
    return {
        "case_count": len(labels),
        "required_skill_precision": required["precision"],
        "required_skill_recall": required["recall"],
        "required_skill_f1": required["f1"],
        "missing_skill_precision": missing["precision"],
        "missing_skill_recall": missing["recall"],
        "missing_skill_f1": missing["f1"],
        "blocking_risk_precision": blocking["precision"],
        "blocking_risk_recall": blocking["recall"],
        "blocking_risk_f1": blocking["f1"],
        "evidence_validity": safe_ratio(evidence_backed, evidence_claims),
        "evidence_backed_match_rate": safe_ratio(evidence_backed, evidence_claims),
        "unsupported_skill_claim_rate": safe_ratio(unsupported_claims, evidence_claims),
        "structured_result_validity": safe_ratio(valid_results, len(labels)),
        "recommendation_agreement": safe_ratio(recommendation_hits, len(labels)),
        "match_band_agreement": safe_ratio(band_hits, band_labels) if band_labels else None,
        "evidence_backed_claims": evidence_backed,
        "matched_skill_claims": evidence_claims,
        "blocking_expected": len(blocking_expected),
        "blocking_predicted": len(blocking_actual),
        "failure_count": len(failures),
        "failure_categories": dict(Counter(item["category"] for item in failures)),
        "failures": failures,
    }


def _score_band(score: float) -> str:
    if score >= 85:
        return "HIGH"
    if score >= 55:
        return "MODERATE"
    return "LOW"


def _failure_category(
    label: dict[str, Any],
    result: dict[str, Any],
    differences: list[str],
) -> str:
    joined = " ".join(differences).casefold()
    if "structured" in joined or not _structured_result_valid(result):
        return "STRUCTURED_RESULT_FAILURE"
    if "skill" in joined:
        if label.get("category") == "INSUFFICIENT_EVIDENCE":
            return "EVIDENCE_FAILURE"
        return "SKILL_OR_ALIAS_FAILURE"
    if "blocking" in joined:
        return "RULE_FAILURE"
    return "RULE_FAILURE"
