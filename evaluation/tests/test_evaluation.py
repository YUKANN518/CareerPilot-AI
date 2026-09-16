from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.dataset import DatasetValidationError, load_dataset, validate_records
from evaluation.metrics import calculate_metrics, f1, safe_ratio
from evaluation.report import render_failure_analysis, write_json


def test_dataset_is_file_based_and_has_unique_case_ids() -> None:
    dataset = load_dataset()

    assert dataset.version == "eval-v1"
    assert dataset.case_count == 52
    assert len({item["case_id"] for item in dataset.labels}) == dataset.case_count
    assert len(dataset.semantic_cases) == 10


def test_duplicate_case_id_is_rejected() -> None:
    dataset = load_dataset()
    with pytest.raises(DatasetValidationError, match="duplicate case_id"):
        validate_records(
            [dataset.labels[0], dataset.labels[0]],
            dataset.resumes,
            dataset.jobs,
        )


def test_invalid_expected_schema_is_rejected() -> None:
    dataset = load_dataset()
    invalid = {
        key: value
        for key, value in dataset.labels[0].items()
        if key != "expected_missing_skills"
    }
    with pytest.raises(DatasetValidationError, match="misses expected fields"):
        validate_records([invalid], dataset.resumes, dataset.jobs)


def test_precision_recall_f1_zero_denominator_edges() -> None:
    assert safe_ratio(0, 0) == 0
    assert f1(0, 0) == 0
    metrics = calculate_metrics(
        [
            {
                "case_id": "T01",
                "resume_fixture": "r",
                "job_fixture": "j",
                "expected_matched_skills": [],
                "expected_partial_skills": [],
                "expected_missing_skills": [],
                "expected_unknown_skills": [],
                "expected_blocking_risks": [],
                "expected_recommendations": ["CONSIDER"],
            }
        ],
        [
            {
                "case_id": "T01",
                "category": "INCOMPLETE_JOB",
                "recommendation": "CONSIDER",
                "skill_statuses": {},
                "risks": {},
                "evidence_signature": [],
                "rule_score": 50,
                "config_snapshot": {},
            }
        ],
        [{"fixture_id": "j", "skills": []}],
    )
    assert metrics["required_skill_f1"] == 0
    assert metrics["missing_skill_f1"] == 0
    assert metrics["blocking_risk_f1"] == 0


def test_empty_dataset_returns_zero_metrics_without_division_error() -> None:
    metrics = calculate_metrics([], [], [])

    assert metrics["case_count"] == 0
    assert metrics["required_skill_f1"] == 0
    assert metrics["structured_result_validity"] == 0
    assert metrics["failure_count"] == 0


def test_prediction_serialization_and_failure_category(tmp_path) -> None:
    dataset = load_dataset()
    prediction = {
        "case_id": "H01",
        "category": "HIGH_MATCH",
        "scoring_version": "deterministic-v1.1",
        "recommendation": "CONSIDER",
        "skill_statuses": {},
        "risks": {},
        "evidence_signature": [],
        "rule_score": 50,
        "config_snapshot": {},
    }
    metrics = calculate_metrics(
        [
            {
                **dataset.labels[0],
                "expected_matched_skills": [],
                "expected_partial_skills": [],
                "expected_missing_skills": [],
                "expected_unknown_skills": [],
                "expected_blocking_risks": [],
                "expected_recommendations": ["STRONGLY_RECOMMENDED"],
            }
        ],
        [prediction],
        [{**dataset.jobs[0], "fixture_id": dataset.labels[0]["job_fixture"]}],
    )
    report = render_failure_analysis(metrics)
    assert "H01" in report
    assert "RULE_FAILURE" in report

    output = tmp_path / "prediction.json"
    write_json(output, {"metrics": metrics})
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metrics"]["failure_count"] == 1


def test_independent_holdout_is_label_first_and_disjoint() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "dataset" / "holdout" / "cases.json").read_text(encoding="utf-8")
    )
    regression_ids = {item["case_id"] for item in load_dataset().labels}
    holdout_ids = {item["case_id"] for item in payload["cases"]}
    assert payload["dataset_version"] == "holdout-v1"
    assert payload["annotation_status"] == "label_first_frozen_before_execution"
    assert len(holdout_ids) == 20
    assert regression_ids.isdisjoint(holdout_ids)
    assert "holdout-v1" in (root / "dataset" / "holdout" / "ANNOTATION_LOG.md").read_text(
        encoding="utf-8"
    )


def test_parsing_fixture_manifest_covers_pdf_and_docx() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "dataset" / "parsing" / "cases.json").read_text(encoding="utf-8")
    )
    formats = {item["format"] for item in payload["resumes"]}
    assert len(payload["resumes"]) == 10
    assert len(payload["jobs"]) == 10
    assert {"pdf", "docx"} <= formats
    assert {"education", "skills", "projects", "experience"} <= set(
        payload["resumes"][0]["expected_structured"]
    )
