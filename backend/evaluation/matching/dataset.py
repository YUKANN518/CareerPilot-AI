from __future__ import annotations

import json
from pathlib import Path

from evaluation.matching.schemas import (
    EvaluationDataset,
    EvaluationLabel,
    JobFixture,
    ResumeFixture,
)

ROOT = Path(__file__).resolve().parent


def load_dataset() -> EvaluationDataset:
    resumes = [
        ResumeFixture.model_validate(item)
        for item in json.loads((ROOT / "fixtures" / "resumes.json").read_text(encoding="utf-8"))
    ]
    jobs = [
        JobFixture.model_validate(item)
        for item in json.loads((ROOT / "fixtures" / "jobs.json").read_text(encoding="utf-8"))
    ]
    labels = [
        EvaluationLabel.model_validate(item)
        for item in json.loads((ROOT / "labels" / "labels.json").read_text(encoding="utf-8"))
    ]
    dataset = EvaluationDataset(
        dataset_version="matching-evaluation-v1",
        resumes=resumes,
        jobs=jobs,
        labels=labels,
    )
    resume_ids = {item.fixture_id for item in resumes}
    job_ids = {item.fixture_id for item in jobs}
    for label in labels:
        if label.resume_fixture not in resume_ids or label.job_fixture not in job_ids:
            raise ValueError(f"{label.case_id} references an unknown fixture")
    return dataset
