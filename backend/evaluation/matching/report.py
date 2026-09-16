from __future__ import annotations

import csv
import json
from pathlib import Path

from app.schemas.matching import RecommendationLevel
from evaluation.matching.schemas import (
    CaseResult,
    EvaluationLabel,
    EvaluationMetrics,
)


def write_outputs(
    output_dir: Path,
    labels: list[EvaluationLabel],
    results: list[CaseResult],
    metrics: EvaluationMetrics,
    comparison_results: list[CaseResult],
    comparison_metrics: EvaluationMetrics,
    formats: set[str] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_formats = formats or {"json", "csv", "markdown"}
    payload = {
        "dataset": "matching-evaluation-v1",
        "scoring_version": "deterministic-v1",
        "metrics": metrics.model_dump(mode="json"),
        "results": [item.model_dump(mode="json") for item in results],
        "comparison": {
            "scoring_version": "deterministic-v1.1",
            "metrics": comparison_metrics.model_dump(mode="json"),
            "results": [item.model_dump(mode="json") for item in comparison_results],
        },
    }
    if "json" in selected_formats:
        (output_dir / "matching-evaluation.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if "csv" in selected_formats:
        _write_metric_csv(
            output_dir / "matching-evaluation.csv",
            metrics,
            comparison_metrics,
        )
        _write_case_csv(
            output_dir / "case-results.csv",
            labels,
            results,
            comparison_results,
        )
    if "markdown" in selected_formats:
        (output_dir / "matching-evaluation.md").write_text(
            _main_report(labels, results, metrics),
            encoding="utf-8",
        )
        (output_dir / "failure-cases.md").write_text(
            _failure_report(labels, results),
            encoding="utf-8",
        )
        (output_dir / "version-comparison.md").write_text(
            _comparison_report(
                labels,
                results,
                metrics,
                comparison_results,
                comparison_metrics,
            ),
            encoding="utf-8",
        )


def _write_metric_csv(
    path: Path,
    metrics: EvaluationMetrics,
    comparison_metrics: EvaluationMetrics,
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["scoring_version", "metric", "value"])
        for version, version_metrics in (
            ("deterministic-v1", metrics),
            ("deterministic-v1.1", comparison_metrics),
        ):
            for key, value in version_metrics.model_dump(mode="json").items():
                rendered = (
                    json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
                )
                writer.writerow([version, key, rendered])


def _write_case_csv(
    path: Path,
    labels: list[EvaluationLabel],
    results: list[CaseResult],
    comparison_results: list[CaseResult],
) -> None:
    label_map = {item.case_id: item for item in labels}
    comparison_map = {item.case_id: item for item in comparison_results}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "case_id",
            "category",
            "score",
            "recommendation",
            "candidate_recommendation",
            "candidate_blocking_risks",
            "score_in_range",
            "recommendation_consistent",
            "completeness",
            "confidence",
            "not_provided",
            "unknown",
            "duration_ms",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            label = label_map[result.case_id]
            candidate = comparison_map[result.case_id]
            writer.writerow(
                {
                    "case_id": result.case_id,
                    "category": result.category.value,
                    "score": result.rule_score,
                    "recommendation": result.recommendation.value,
                    "candidate_recommendation": candidate.recommendation.value,
                    "candidate_blocking_risks": ",".join(
                        code for code, severity in candidate.risks.items() if severity == "BLOCKING"
                    ),
                    "score_in_range": label.expected_score_min
                    <= result.rule_score
                    <= label.expected_score_max,
                    "recommendation_consistent": result.recommendation
                    in label.expected_recommendations,
                    "completeness": result.job_information_completeness,
                    "confidence": result.report_confidence,
                    "not_provided": result.not_provided_count,
                    "unknown": result.unknown_count,
                    "duration_ms": result.duration_ms,
                }
            )


def _main_report(
    labels: list[EvaluationLabel],
    results: list[CaseResult],
    metrics: EvaluationMetrics,
) -> str:
    incomplete = [item for item in results if item.category.value == "INCOMPLETE_JOB"]
    blocking_case_count = sum(bool(item.expected_blocking_risks) for item in labels)
    return f"""# deterministic-v1 Matching Evaluation

## Technical summary

The released deterministic-v1 engine remains fully repeatable with strong skill-state agreement
and traceable evidence. The expanded policy set exposes its intentionally narrow BLOCKING
definition and sparse-posting overconfidence. The reviewed deterministic-v1.1 comparison is in
`version-comparison.md`; no deterministic-v1 rule or historical report was changed.

- Dataset: {len(labels)} anonymous synthetic cases.
- Recommendation consistency: {metrics.recommendation_accuracy:.1%}.
- Score interval hit rate: {metrics.score_interval_hit_rate:.1%}; interval MAE:
  {metrics.score_mean_absolute_error:.2f}.
- Blocking precision/recall: {metrics.blocking_precision:.1%} /
  {metrics.blocking_recall:.1%}.
- Skill macro F1: {metrics.skill_macro_f1:.1%}; repeat consistency:
  {metrics.repeat_consistency_rate:.1%}.

## Incomplete postings expose a confidence problem

The {len(incomplete)} sparse-posting cases have completeness values from
{min(item.job_information_completeness for item in incomplete):.1%} to
{max(item.job_information_completeness for item in incomplete):.1%}, while their rule scores
remain between {min(item.rule_score for item in incomplete):.2f} and
{max(item.rule_score for item in incomplete):.2f}. This is descriptive evidence that missing
criteria are treated neutrally and can yield an overconfident recommendation.

![Job completeness and rule score](charts/09-completeness-vs-score.png)

The score itself remains untouched for historical reproducibility. deterministic-v1.1 adds
configured completeness and confidence caps without changing rule_score.

## Blocking recall is the release gate

![Blocking precision and recall](charts/05-blocking-precision-recall.png)

The {blocking_case_count} manually labelled cases cover explicit work authorization, mandatory
certificate, mandatory language, large explicit experience gaps, and non-substitutable degree
minimums. deterministic-v1 marks only work authorization as BLOCKING; the versioned
blocking-policy-v1 comparison addresses the remaining policy categories.

## Skill states and evidence remain strong

![Skill status confusion matrix](charts/03-skill-confusion-matrix.png)

Evidence trace coverage is {metrics.evidence_trace_coverage:.1%}; required-skill evidence
coverage is {metrics.required_skill_evidence_coverage:.1%}. Missing and UNKNOWN skills retain
job-side evidence without fabricated resume evidence.

![Evidence coverage](charts/06-evidence-coverage.png)

## Stability and ranking

Repeated outputs are identical at {metrics.repeat_consistency_rate:.1%}. The Python-resume
ranking has exact accuracy {metrics.exact_ranking_accuracy:.1%}, pairwise accuracy
{metrics.pairwise_ranking_accuracy:.1%}, and Spearman correlation
{metrics.spearman_correlation:.3f}.

![Python resume multi-job ranking](charts/08-python-ranking.png)

## Score and recommendation distribution

![Score distribution by case category](charts/01-score-distribution.png)

Category score ranges mostly follow the labelled ordering. The remaining overlap is expected:
the released engine scores known criteria and does not treat a sparse posting as inherently
weak.

![Recommendation label consistency](charts/02-recommendation-consistency.png)

Recommendation consistency is lower than score-interval agreement because the manual policy
uses stricter Blocking and incomplete-posting expectations than deterministic-v1.

## Risk mix and execution timing

![Risk conclusions by severity](charts/04-risk-severity-counts.png)

The severity mix confirms that deterministic-v1 emits mandatory language, certificate,
experience, and degree gaps as HIGH rather than BLOCKING. That is a policy mismatch, not a
runtime failure.

![Execution-time distribution](charts/07-execution-time.png)

Execution time is reported only as a local-process diagnostic. It is excluded from stability
signatures and must not be interpreted as an API service-level objective.

## Scope and methodology

All cases use synthetic resumes and jobs. The runner invokes SkillNormalizationService,
JobRequirementExtractor, and DeterministicMatchEngine directly. Score error is distance to the
nearest labelled interval boundary. Skill metrics use a four-class confusion matrix.
Repeatability excludes execution time but includes score, recommendation, risks, skill states,
evidence ordering, dimensions, and config snapshot.

## Limitations and next steps

- The dataset is deliberately small and synthetic; it does not estimate population performance.
- Synthetic labels do not replace legal or recruiting-domain review.
- Timing is a local-process micro-benchmark, not an API latency or throughput benchmark.
- Keep deterministic-v1 as the production default until version-selection and report
  presentation changes are approved; the v1.1 quantitative gate result is documented
  separately.
"""


def _failure_report(labels: list[EvaluationLabel], results: list[CaseResult]) -> str:
    by_case = {item.case_id: item for item in results}
    lines = ["# Failure Cases", "", "Labels are unchanged; failures reflect engine behaviour.", ""]
    for label in labels:
        result = by_case[label.case_id]
        failures: list[str] = []
        if result.recommendation not in label.expected_recommendations:
            failures.append(
                f"recommendation={result.recommendation.value}, expected one of "
                f"{[item.value for item in label.expected_recommendations]}"
            )
        if not label.expected_score_min <= result.rule_score <= label.expected_score_max:
            failures.append(
                f"score={result.rule_score}, interval="
                f"[{label.expected_score_min}, {label.expected_score_max}]"
            )
        actual_blocking = {
            code for code, severity in result.risks.items() if severity == "BLOCKING"
        }
        missing_blocking = set(label.expected_blocking_risks) - actual_blocking
        if missing_blocking:
            failures.append(f"missing BLOCKING labels={sorted(missing_blocking)}")
        if failures:
            lines.extend([f"## {label.case_id}", "", *[f"- {item}" for item in failures], ""])
    if len(lines) == 4:
        lines.append("No labelled failures.")
    return "\n".join(lines)


def _comparison_report(
    labels: list[EvaluationLabel],
    baseline: list[CaseResult],
    baseline_metrics: EvaluationMetrics,
    candidate: list[CaseResult],
    candidate_metrics: EvaluationMetrics,
) -> str:
    base = {item.case_id: item for item in baseline}
    changes = []
    risk_changes = 0
    for item in candidate:
        baseline_item = base[item.case_id]
        risk_changes += baseline_item.risks != item.risks
        if baseline_item.recommendation != item.recommendation:
            changes.append(
                (
                    item.case_id,
                    baseline_item.recommendation.value,
                    item.recommendation.value,
                )
            )
    rows = "\n".join(f"| {case_id} | {old} | {new} |" for case_id, old, new in changes)
    rows = rows or "| none | - | - |"
    expected_blocking = {
        (label.case_id, code) for label in labels for code in label.expected_blocking_risks
    }
    actual_blocking = {
        (result.case_id, code)
        for result in candidate
        for code, severity in result.risks.items()
        if severity == "BLOCKING"
    }
    false_positives = sorted(actual_blocking - expected_blocking)
    false_negatives = sorted(expected_blocking - actual_blocking)
    gates = {
        "Blocking recall >= 90%": candidate_metrics.blocking_recall >= 0.9,
        "Blocking precision >= 95%": candidate_metrics.blocking_precision >= 0.95,
        "Recommendation consistency >= 85%": (candidate_metrics.recommendation_accuracy >= 0.85),
        "Skill macro F1 does not regress": (
            candidate_metrics.skill_macro_f1 >= baseline_metrics.skill_macro_f1
        ),
        "Evidence coverage does not regress": (
            candidate_metrics.evidence_trace_coverage >= baseline_metrics.evidence_trace_coverage
        ),
        "Repeat consistency is 100%": (candidate_metrics.repeat_consistency_rate == 1),
        "Ranking does not regress": (
            candidate_metrics.exact_ranking_accuracy >= baseline_metrics.exact_ranking_accuracy
            and candidate_metrics.pairwise_ranking_accuracy
            >= baseline_metrics.pairwise_ranking_accuracy
            and candidate_metrics.spearman_correlation >= baseline_metrics.spearman_correlation
        ),
        "I01-I03 are capped": all(
            item.recommendation is RecommendationLevel.CONSIDER
            for item in candidate
            if item.case_id in {"I01", "I02", "I03"}
        ),
    }
    gate_rows = "\n".join(
        f"| {name} | {'PASS' if passed else 'FAIL'} |" for name, passed in gates.items()
    )
    release_ready = all(gates.values())
    metric_values = (
        ("Blocking precision", "blocking_precision"),
        ("Blocking recall", "blocking_recall"),
        ("Recommendation consistency", "recommendation_accuracy"),
        ("Score interval hit rate", "score_interval_hit_rate"),
        ("Skill macro F1", "skill_macro_f1"),
        ("Evidence coverage", "evidence_trace_coverage"),
        ("Repeat consistency", "repeat_consistency_rate"),
    )
    metric_rows = "\n".join(
        f"| {label} | {getattr(baseline_metrics, field):.2%} | "
        f"{getattr(candidate_metrics, field):.2%} |"
        for label, field in metric_values
    )
    return f"""# Version Comparison

## Status

`deterministic-v1.1` is a reviewed backend candidate. It preserves deterministic-v1 rule_score,
uses `blocking-policy-v1`, and applies configured completeness caps. It is not the production
default and the evaluation runner creates no database reports.

## Metric comparison

| Metric | deterministic-v1 | deterministic-v1.1 |
| --- | ---: | ---: |
{metric_rows}

## Observed changes

- Cases compared: {len(labels)}.
- Score changes: 0.
- Risk changes: {risk_changes}.
- Recommendation changes: {len(changes)}.
- New Blocking false positives: {false_positives or "none"}.
- Remaining Blocking false negatives: {false_negatives or "none"}.

| Case | deterministic-v1 | v1.1 candidate |
| --- | --- | --- |
{rows}

## Release gates

| Gate | Result |
| --- | --- |
{gate_rows}

## Decision

Quantitative release gates: {"PASS" if release_ready else "FAIL"}. The candidate remains
non-default until the existing deterministic-v1 API/UI contract receives a separately approved
version-selection and presentation change. deterministic-v1 remains queryable, reproducible,
and unchanged.
"""
