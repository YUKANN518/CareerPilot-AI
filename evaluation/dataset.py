from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
MANIFEST_PATH = ROOT / "dataset" / "manifest.json"


class DatasetValidationError(ValueError):
    """Raised when the evaluation manifest or labels are not safe to run."""


@dataclass(frozen=True)
class EvaluationDataset:
    version: str
    labels: list[dict[str, Any]]
    resumes: list[dict[str, Any]]
    jobs: list[dict[str, Any]]
    semantic_cases: list[dict[str, Any]]
    manifest: dict[str, Any]

    @property
    def case_count(self) -> int:
        return len(self.labels)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetValidationError(f"evaluation source does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"invalid JSON in evaluation source: {path}") from exc


def _source_path(manifest: dict[str, Any], field: str) -> Path:
    value = manifest.get(field)
    if not isinstance(value, str) or not value:
        raise DatasetValidationError(f"manifest field {field!r} must be a non-empty path")
    return PROJECT_ROOT / value


def _as_records(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise DatasetValidationError(f"{field} must be a JSON array of objects")
    return value


def _canonical(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def validate_records(
    labels: list[dict[str, Any]],
    resumes: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
) -> None:
    raw_label_ids = [item.get("case_id") for item in labels]
    if any(not isinstance(case_id, str) or not case_id for case_id in raw_label_ids):
        raise DatasetValidationError("every evaluation label requires a non-empty case_id")
    label_ids = [case_id for case_id in raw_label_ids if isinstance(case_id, str)]
    if len(label_ids) != len(set(label_ids)):
        duplicates = sorted({case_id for case_id in label_ids if label_ids.count(case_id) > 1})
        raise DatasetValidationError(f"duplicate case_id values: {duplicates}")

    resume_ids = {item.get("fixture_id") for item in resumes}
    job_ids = {item.get("fixture_id") for item in jobs}
    required_expected_fields = {
        "expected_matched_skills",
        "expected_partial_skills",
        "expected_missing_skills",
        "expected_unknown_skills",
        "expected_blocking_risks",
    }
    for label in labels:
        case_id = label["case_id"]
        if label.get("resume_fixture") not in resume_ids:
            raise DatasetValidationError(f"{case_id} references an unknown resume fixture")
        if label.get("job_fixture") not in job_ids:
            raise DatasetValidationError(f"{case_id} references an unknown job fixture")
        missing_fields = sorted(required_expected_fields - label.keys())
        if missing_fields:
            raise DatasetValidationError(f"{case_id} misses expected fields: {missing_fields}")
        skill_groups = [
            label["expected_matched_skills"],
            label["expected_partial_skills"],
            label["expected_missing_skills"],
            label["expected_unknown_skills"],
        ]
        if not all(isinstance(group, list) for group in skill_groups):
            raise DatasetValidationError(f"{case_id} expected skill groups must be arrays")
        normalized = [_canonical(skill) for group in skill_groups for skill in group]
        if len(normalized) != len(set(normalized)):
            raise DatasetValidationError(f"{case_id} assigns one skill to multiple expected states")


def load_dataset() -> EvaluationDataset:
    manifest = _read_json(MANIFEST_PATH)
    if not isinstance(manifest, dict):
        raise DatasetValidationError("evaluation manifest must be a JSON object")
    labels = _as_records(_read_json(_source_path(manifest, "case_source")), "labels")
    resumes = _as_records(_read_json(_source_path(manifest, "resume_source")), "resumes")
    jobs = _as_records(_read_json(_source_path(manifest, "job_source")), "jobs")
    semantic_cases = _as_records(
        _read_json(_source_path(manifest, "semantic_source")),
        "semantic_cases",
    )
    validate_records(labels, resumes, jobs)
    declared_count = manifest.get("case_count")
    if declared_count != len(labels):
        raise DatasetValidationError(
            f"manifest case_count={declared_count} does not match labels={len(labels)}"
        )
    return EvaluationDataset(
        version=str(manifest.get("dataset_version", "unknown")),
        labels=labels,
        resumes=resumes,
        jobs=jobs,
        semantic_cases=semantic_cases,
        manifest=manifest,
    )
