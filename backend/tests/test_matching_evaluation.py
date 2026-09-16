from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.matching import (
    RecommendationLevel,
    ReportConfidence,
    RequirementInformationStatus,
    SkillMatchStatus,
)
from evaluation.matching.charts import generate_charts
from evaluation.matching.dataset import load_dataset
from evaluation.matching.executor import EvaluationExecutor
from evaluation.matching.metrics import calculate_metrics, confusion_matrix, ranking_metrics
from evaluation.matching.report import write_outputs
from evaluation.matching.runner import stability_rate
from evaluation.matching.schemas import CaseCategory, EvaluationLabel


@pytest.fixture(scope="module")
def evaluation_context() -> tuple[list[EvaluationLabel], EvaluationExecutor]:
    dataset = load_dataset()
    return dataset.labels, EvaluationExecutor(dataset.resumes, dataset.jobs)


def test_dataset_has_required_categories_and_strict_labels() -> None:
    dataset = load_dataset()
    counts = {
        category: sum(label.category is category for label in dataset.labels)
        for category in CaseCategory
    }

    assert len(dataset.labels) == 52
    assert counts[CaseCategory.HIGH_MATCH] >= 8
    assert counts[CaseCategory.MEDIUM_MATCH] >= 8
    assert counts[CaseCategory.SKILL_GAP] >= 6
    assert counts[CaseCategory.BLOCKING] >= 3
    assert counts[CaseCategory.INCOMPLETE_JOB] >= 3
    assert counts[CaseCategory.INSUFFICIENT_EVIDENCE] >= 2
    with pytest.raises(ValidationError):
        EvaluationLabel.model_validate(
            {
                **dataset.labels[0].model_dump(mode="json"),
                "unexpected": True,
            }
        )


def test_metric_calculation_confusion_risk_evidence_and_ranking(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    results = [executor.run_case(label) for label in labels]
    metrics = calculate_metrics(labels, results)
    matrix = confusion_matrix(labels, results)
    exact, pairwise, spearman = ranking_metrics(results)

    assert metrics.case_count == 52
    assert metrics.score_interval_hit_rate >= 0.95
    assert metrics.blocking_precision == 1
    assert metrics.blocking_recall < 0.2
    assert metrics.evidence_trace_coverage == 1
    assert matrix["MATCHED"]["MATCHED"] >= 50
    assert matrix["UNKNOWN"]["MISSING"] == 0
    assert exact == pairwise == spearman == 1


def test_candidate_meets_release_metrics_without_changing_rule_scores(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    baseline = [executor.run_case(label) for label in labels]
    candidate = [executor.run_case(label, scoring_version="deterministic-v1.1") for label in labels]
    baseline_metrics = calculate_metrics(labels, baseline)
    candidate_metrics = calculate_metrics(labels, candidate)

    assert all(
        candidate[index].rule_score == item.rule_score for index, item in enumerate(baseline)
    )
    assert candidate_metrics.blocking_recall >= 0.9
    assert candidate_metrics.blocking_precision >= 0.95
    assert candidate_metrics.recommendation_accuracy >= 0.85
    assert candidate_metrics.skill_macro_f1 >= baseline_metrics.skill_macro_f1
    assert candidate_metrics.evidence_trace_coverage >= baseline_metrics.evidence_trace_coverage
    assert candidate_metrics.exact_ranking_accuracy >= baseline_metrics.exact_ranking_accuracy


def test_blocking_policy_matrix_and_unknown_semantics(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    label_map = {item.case_id: item for item in labels}
    results = {
        case_id: executor.run_case(
            label_map[case_id],
            scoring_version="deterministic-v1.1",
        )
        for case_id in {
            "N01",
            "N02",
            "N04",
            "N05",
            "N06",
            "N07",
            "N08",
            "N09",
            "N10",
            "N11",
            "N12",
            "N13",
            "N20",
        }
    }

    assert results["N01"].risks["CERTIFICATE_REQUIREMENT_NOT_MET"] == "BLOCKING"
    assert results["N02"].risks["CERTIFICATE_REQUIREMENT_NOT_MET"] == "MEDIUM"
    assert results["N04"].risks["LANGUAGE_REQUIREMENT_NOT_MET"] == "BLOCKING"
    assert results["N05"].risks["LANGUAGE_REQUIREMENT_NOT_MET"] == "MEDIUM"
    assert results["N06"].risks["MINIMUM_EXPERIENCE_NOT_MET"] == "MEDIUM"
    assert results["N07"].risks["MINIMUM_EXPERIENCE_NOT_MET"] == "HIGH"
    assert results["N08"].risks["MINIMUM_EXPERIENCE_NOT_MET"] == "BLOCKING"
    assert "MINIMUM_EXPERIENCE_NOT_MET" not in results["N09"].risks
    assert results["N10"].risks["EDUCATION_REQUIREMENT_NOT_MET"] == "HIGH"
    assert results["N11"].risks["EDUCATION_REQUIREMENT_NOT_MET"] == "BLOCKING"
    assert results["N12"].risks["WORK_ELIGIBILITY_UNKNOWN"] == "INFO"
    assert "BLOCKING" not in results["N12"].risks.values()
    assert results["N13"].risks["WORK_ELIGIBILITY_BLOCKED"] == "BLOCKING"
    assert results["N20"].risks["LANGUAGE_REQUIREMENT_NOT_MET"] == "BLOCKING"


def test_completeness_confidence_and_information_statuses(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    label_map = {item.case_id: item for item in labels}
    sparse = executor.run_case(
        label_map["N16"],
        scoring_version="deterministic-v1.1",
    )
    explicit_none = executor.run_case(
        label_map["N18"],
        scoring_version="deterministic-v1.1",
    )
    unparseable = executor.run_case(
        label_map["N19"],
        scoring_version="deterministic-v1.1",
    )

    assert sparse.job_information_completeness < 0.5
    assert sparse.report_confidence_level is ReportConfidence.VERY_LOW
    assert sparse.recommendation_cap is RecommendationLevel.CONSIDER
    assert sparse.recommendation is RecommendationLevel.CONSIDER
    assert explicit_none.job_information_completeness == 1
    assert all(
        status is RequirementInformationStatus.NOT_REQUIRED
        for status in explicit_none.information_statuses.values()
    )
    assert (
        unparseable.information_statuses["experience_requirement"]
        is RequirementInformationStatus.UNPARSEABLE
    )
    assert "BLOCKING" not in sparse.risks.values()


def test_ten_repeat_stability_is_exact(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    selected = [label for label in labels if label.case_id in {"H01", "B01", "I01", "E02"}]
    repeats = {label.case_id: [executor.run_case(label) for _ in range(10)] for label in selected}

    assert stability_rate(repeats) == 1
    candidate_selected = [label for label in labels if label.case_id in {"N01", "N12", "N16"}]
    candidate_repeats = {
        label.case_id: [
            executor.run_case(label, scoring_version="deterministic-v1.1") for _ in range(10)
        ]
        for label in candidate_selected
    }
    assert stability_rate(candidate_repeats) == 1


def test_score_bounds_weighted_sum_and_unknown_semantics(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    results = {label.case_id: executor.run_case(label) for label in labels}

    assert all(0 <= result.rule_score <= 100 for result in results.values())
    assert all(result.rule_score == result.weighted_score_sum for result in results.values())
    assert results["G03"].skill_statuses == {
        "Java": SkillMatchStatus.UNKNOWN,
        "Spring Boot": SkillMatchStatus.UNKNOWN,
    }
    assert "EXPERIENCE_UNKNOWN" not in results["I01"].risks


def test_monotonicity_evidence_and_unrelated_skill(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    label_map = {item.case_id: item for item in labels}
    base = executor.run_case(label_map["G02"])
    resume = executor.resumes["communication_only"]
    executor.resumes["communication_only"] = resume.model_copy(
        update={"skills": [*resume.skills, "Python"]}
    )
    improved = executor.run_case(label_map["G02"])
    executor.resumes["communication_only"] = resume
    assert improved.dimension_scores["hard_skills"] >= base.dimension_scores["hard_skills"]

    high = executor.run_case(label_map["H01"])
    ranked_resume = executor.resumes["python_rank"]
    executor.resumes["python_rank"] = ranked_resume.model_copy(
        update={"unconfirmed_skills": ["FastAPI"]}
    )
    reduced_evidence = executor.run_case(label_map["H01"])
    executor.resumes["python_rank"] = ranked_resume
    assert reduced_evidence.dimension_scores["hard_skills"] <= high.dimension_scores["hard_skills"]

    unrelated = ranked_resume.model_copy(
        update={"skills": [*ranked_resume.skills, "Communication"]}
    )
    executor.resumes["python_rank"] = unrelated
    unrelated_result = executor.run_case(label_map["H01"])
    executor.resumes["python_rank"] = ranked_resume
    assert unrelated_result.rule_score - high.rule_score <= 0.01


def test_required_penalty_blocking_and_duplicate_evidence_are_bounded(
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    label_map = {item.case_id: item for item in labels}
    blocking = executor.run_case(label_map["B01"])
    assert blocking.recommendation is RecommendationLevel.NOT_RECOMMENDED
    blocked_job = executor.jobs["b01_eligibility"]
    executor.jobs["b01_eligibility"] = blocked_job.model_copy(
        update={"requirements": "Python and FastAPI required. 3 years experience. Bachelor degree."}
    )
    without_blocker = executor.run_case(label_map["B01"])
    executor.jobs["b01_eligibility"] = blocked_job
    assert without_blocker.rule_score >= blocking.rule_score
    assert without_blocker.recommendation is not RecommendationLevel.NOT_RECOMMENDED

    duplicate = executor.run_case(label_map["E02"])
    resume = executor.resumes["duplicate_python"]
    executor.resumes["duplicate_python"] = resume.model_copy(update={"duplicate_evidence": {}})
    single = executor.run_case(label_map["E02"])
    executor.resumes["duplicate_python"] = resume
    assert duplicate.rule_score - single.rule_score <= 2.1

    job = executor.jobs["m01_backend_rank"]
    preferred = job.model_copy(
        update={
            "skills": [
                item.model_copy(update={"required": False}) if item.name == "JavaScript" else item
                for item in job.skills
            ]
        }
    )
    executor.jobs["m01_backend_rank"] = preferred
    preferred_result = executor.run_case(label_map["M01"])
    executor.jobs["m01_backend_rank"] = job
    required_result = executor.run_case(label_map["M01"])
    assert (
        required_result.dimension_scores["hard_skills"]
        <= preferred_result.dimension_scores["hard_skills"]
    )


def test_incomplete_candidate_version_and_output_generation(
    tmp_path,
    evaluation_context: tuple[list[EvaluationLabel], EvaluationExecutor],
) -> None:
    labels, executor = evaluation_context
    selected = [label for label in labels if label.case_id in {"I01", "I02", "I03"}]
    baseline = [executor.run_case(label) for label in selected]
    candidate = [
        executor.run_case(label, scoring_version="deterministic-v1.1") for label in selected
    ]
    metrics = calculate_metrics(selected, baseline)
    candidate_metrics = calculate_metrics(selected, candidate)

    assert all(
        item.rule_score == baseline[index].rule_score for index, item in enumerate(candidate)
    )
    assert all(item.recommendation is RecommendationLevel.CONSIDER for item in candidate)
    write_outputs(
        tmp_path,
        selected,
        baseline,
        metrics,
        candidate,
        candidate_metrics,
    )
    charts = generate_charts(tmp_path, selected, baseline, metrics)
    required = {
        "matching-evaluation.json",
        "matching-evaluation.csv",
        "matching-evaluation.md",
        "case-results.csv",
        "failure-cases.md",
        "version-comparison.md",
    }
    assert required <= {item.name for item in tmp_path.iterdir()}
    assert len(charts) == 9
    payload = json.loads((tmp_path / "matching-evaluation.json").read_text(encoding="utf-8"))
    assert payload["metrics"]["case_count"] == 3
    assert payload["comparison"]["metrics"]["case_count"] == 3
    comparison = (tmp_path / "version-comparison.md").read_text(encoding="utf-8")
    assert "Quantitative release gates:" in comparison
    json_only = tmp_path / "json-only"
    write_outputs(
        json_only,
        selected,
        baseline,
        metrics,
        candidate,
        candidate_metrics,
        formats={"json"},
    )
    assert {item.name for item in json_only.iterdir()} == {"matching-evaluation.json"}
