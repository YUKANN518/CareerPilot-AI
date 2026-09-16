from __future__ import annotations

from collections import defaultdict
from statistics import mean, median

from app.schemas.matching import SkillMatchStatus
from evaluation.matching.schemas import (
    CaseResult,
    EvaluationLabel,
    EvaluationMetrics,
)

STATUSES = [item.value for item in SkillMatchStatus]


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def confusion_matrix(
    labels: list[EvaluationLabel],
    results: list[CaseResult],
) -> dict[str, dict[str, int]]:
    by_case = {item.case_id: item for item in results}
    matrix = {expected: {actual: 0 for actual in STATUSES} for expected in STATUSES}
    for label in labels:
        expected = {
            **{name: "MATCHED" for name in label.expected_matched_skills},
            **{name: "PARTIAL" for name in label.expected_partial_skills},
            **{name: "MISSING" for name in label.expected_missing_skills},
            **{name: "UNKNOWN" for name in label.expected_unknown_skills},
        }
        actual = {
            name.casefold(): status.value
            for name, status in by_case[label.case_id].skill_statuses.items()
        }
        for name, expected_status in expected.items():
            actual_status = actual.get(name.casefold(), "UNKNOWN")
            matrix[expected_status][actual_status] += 1
    return matrix


def ranking_metrics(results: list[CaseResult]) -> tuple[float, float, float]:
    groups: dict[str, list[CaseResult]] = defaultdict(list)
    for result in results:
        if result.expected_order_group:
            groups[result.expected_order_group].append(result)
    if not groups:
        return 0.0, 0.0, 0.0
    exact = 0
    correct_pairs = 0
    total_pairs = 0
    correlations: list[float] = []
    for items in groups.values():
        expected = sorted(items, key=lambda item: item.expected_order_rank or 0)
        actual = sorted(items, key=lambda item: (-item.rule_score, item.case_id))
        exact += [item.case_id for item in expected] == [item.case_id for item in actual]
        expected_position = {item.case_id: index + 1 for index, item in enumerate(expected)}
        actual_position = {item.case_id: index + 1 for index, item in enumerate(actual)}
        for left_index, left in enumerate(expected):
            for right in expected[left_index + 1 :]:
                total_pairs += 1
                correct_pairs += left.rule_score >= right.rule_score
        count = len(items)
        squared = sum(
            (expected_position[item.case_id] - actual_position[item.case_id]) ** 2 for item in items
        )
        correlations.append(1 - 6 * squared / (count * (count**2 - 1)) if count > 1 else 1)
    return (
        _ratio(exact, len(groups)),
        _ratio(correct_pairs, total_pairs),
        round(mean(correlations), 4),
    )


def calculate_metrics(
    labels: list[EvaluationLabel],
    results: list[CaseResult],
    *,
    repeat_consistency_rate: float = 1.0,
) -> EvaluationMetrics:
    by_case = {item.case_id: item for item in results}
    matrix = confusion_matrix(labels, results)
    score_hits = 0
    score_errors: list[float] = []
    recommendation_hits = 0
    expected_blocking: set[tuple[str, str]] = set()
    actual_blocking: set[tuple[str, str]] = set()
    expected_high: set[tuple[str, str]] = set()
    actual_high: set[tuple[str, str]] = set()
    for label in labels:
        result = by_case[label.case_id]
        recommendation_hits += result.recommendation in label.expected_recommendations
        if label.expected_score_min <= result.rule_score <= label.expected_score_max:
            score_hits += 1
            score_errors.append(0.0)
        else:
            score_errors.append(
                min(
                    abs(result.rule_score - label.expected_score_min),
                    abs(result.rule_score - label.expected_score_max),
                )
            )
        expected_blocking.update((label.case_id, code) for code in label.expected_blocking_risks)
        expected_high.update((label.case_id, code) for code in label.expected_high_risks)
        actual_blocking.update(
            (label.case_id, code)
            for code, severity in result.risks.items()
            if severity == "BLOCKING"
        )
        actual_high.update(
            (label.case_id, code) for code, severity in result.risks.items() if severity == "HIGH"
        )
    skill_accuracy: dict[str, float] = {}
    f1_values: list[float] = []
    for status in STATUSES:
        true_positive = matrix[status][status]
        actual_total = sum(matrix[expected][status] for expected in STATUSES)
        expected_total = sum(matrix[status].values())
        precision = _ratio(true_positive, actual_total)
        recall = _ratio(true_positive, expected_total)
        f1_values.append(
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        skill_accuracy[status] = precision
    exact_ranking, pairwise_ranking, spearman = ranking_metrics(results)
    durations = [item.duration_ms for item in results]
    evidence_complete = sum(item.evidence_complete for item in results)
    evidence_total = sum(item.evidence_total for item in results)
    required_complete = sum(item.required_skill_evidence_complete for item in results)
    required_total = sum(item.required_skill_evidence_total for item in results)
    blocking_complete = sum(item.blocking_evidence_complete for item in results)
    blocking_total = sum(item.blocking_evidence_total for item in results)
    skill_total = sum(len(item.skill_statuses) for item in results)
    criterion_total = len(results) * 7
    return EvaluationMetrics(
        case_count=len(results),
        recommendation_accuracy=_ratio(recommendation_hits, len(labels)),
        score_interval_hit_rate=_ratio(score_hits, len(labels)),
        score_mean_absolute_error=round(mean(score_errors), 4),
        blocking_recall=_ratio(len(expected_blocking & actual_blocking), len(expected_blocking)),
        blocking_precision=_ratio(len(expected_blocking & actual_blocking), len(actual_blocking)),
        high_risk_recall=_ratio(len(expected_high & actual_high), len(expected_high)),
        skill_accuracy=skill_accuracy,
        skill_macro_f1=round(mean(f1_values), 4),
        confusion_matrix=matrix,
        evidence_trace_coverage=_ratio(evidence_complete, evidence_total),
        required_skill_evidence_coverage=_ratio(required_complete, required_total),
        blocking_evidence_coverage=_ratio(blocking_complete, blocking_total),
        no_evidence_conclusion_count=evidence_total - evidence_complete,
        repeat_consistency_rate=repeat_consistency_rate,
        exact_ranking_accuracy=exact_ranking,
        pairwise_ranking_accuracy=pairwise_ranking,
        spearman_correlation=spearman,
        unknown_ratio=_ratio(
            sum(
                status is SkillMatchStatus.UNKNOWN
                for result in results
                for status in result.skill_statuses.values()
            ),
            skill_total,
        ),
        not_provided_ratio=_ratio(
            sum(item.not_provided_count for item in results),
            criterion_total,
        ),
        mean_duration_ms=round(mean(durations), 4),
        p50_duration_ms=round(median(durations), 4),
        p95_duration_ms=round(_percentile(durations, 0.95), 4),
    )
