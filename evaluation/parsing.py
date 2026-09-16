"""Parsing validation for text extraction and deterministic evidence extraction.

This intentionally excludes real-provider semantic structuring.  It measures what can be
reproduced offline: PDF/DOCX text extraction, section headings, dictionary skill mentions,
evidence attachment, and required/preferred job requirement detection.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from evaluation.dataset import ROOT
from evaluation.report import write_json


def _project_root() -> Path:
    return ROOT.parent


def _backend_python() -> Path:
    candidate = _project_root() / "backend" / ".venv" / "Scripts" / "python.exe"
    return candidate if candidate.exists() else Path(sys.executable)


def _canonical(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _prf(expected: set[str], actual: set[str]) -> dict[str, float]:
    true_positive = len(expected & actual)
    precision = true_positive / len(actual) if actual else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _run_backend(input_path: Path, output_path: Path) -> dict[str, Any]:
    command = [
        str(_backend_python()),
        "-m",
        "evaluation.matching.parsing_runner",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=_project_root() / "backend",
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "parsing evaluation failed:\n"
            + completed.stdout[-4000:]
            + completed.stderr[-4000:]
        )
    return json.loads(output_path.read_text(encoding="utf-8"))


def _metrics(payload: dict[str, Any]) -> dict[str, Any]:
    resume_results = payload["resume_results"]
    job_results = payload["job_results"]
    successful_resumes = sum(bool(item["extraction_success"]) for item in resume_results)
    successful_jobs = sum(bool(item["extraction_success"]) for item in job_results)
    resume_expected = {
        _canonical(skill)
        for item in resume_results
        for skill in item["expected_skills"]
    }
    resume_actual = {
        _canonical(skill)
        for item in resume_results
        for skill in item["found_skills"]
    }
    attached = {
        _canonical(skill)
        for item in resume_results
        for skill in item["evidence_attached_skills"]
    }
    expected_sections = sum(len(item["expected_sections"]) for item in resume_results)
    found_sections = sum(len(item["found_sections"]) for item in resume_results)

    job_expected_required = {
        _canonical(skill)
        for item in job_results
        for skill in item["expected_required"]
    }
    job_actual_required = {
        _canonical(skill)
        for item in job_results
        for skill in item["detected_required"]
    }
    job_expected_preferred = {
        _canonical(skill)
        for item in job_results
        for skill in item["expected_preferred"]
    }
    job_actual_preferred = {
        _canonical(skill)
        for item in job_results
        for skill in item["detected_preferred"]
    }
    expected_job_all = job_expected_required | job_expected_preferred
    actual_job_all = job_actual_required | job_actual_preferred
    classification_total = 0
    classification_hits = 0
    for item in job_results:
        expected = {
            **{_canonical(skill): "required" for skill in item["expected_required"]},
            **{_canonical(skill): "preferred" for skill in item["expected_preferred"]},
        }
        actual = {
            **{_canonical(skill): "required" for skill in item["detected_required"]},
            **{_canonical(skill): "preferred" for skill in item["detected_preferred"]},
        }
        classification_total += len(expected)
        classification_hits += sum(actual.get(name, "missing") == status for name, status in expected.items())

    return {
        "resume_sample_count": len(resume_results),
        "job_sample_count": len(job_results),
        "resume_text_extraction_success": round(successful_resumes / len(resume_results), 4),
        "job_text_extraction_success": round(successful_jobs / len(job_results), 4),
        "resume_section_extraction_success": round(found_sections / expected_sections, 4) if expected_sections else 0.0,
        "resume_skill_precision_recall_f1": _prf(resume_expected, resume_actual),
        "resume_evidence_attachment_rate": round(len(attached & resume_expected) / len(resume_expected), 4) if resume_expected else 0.0,
        "job_requirement_detection_precision_recall_f1": _prf(expected_job_all, actual_job_all),
        "job_required_detection_precision_recall_f1": _prf(job_expected_required, job_actual_required),
        "job_preferred_detection_precision_recall_f1": _prf(job_expected_preferred, job_actual_preferred),
        "job_required_vs_preferred_accuracy": round(classification_hits / classification_total, 4) if classification_total else 0.0,
    }


def _render_report(summary: dict[str, Any]) -> str:
    metrics = summary["metrics"]
    resume_prf = metrics["resume_skill_precision_recall_f1"]
    job_prf = metrics["job_requirement_detection_precision_recall_f1"]
    return f"""# Parsing Validation — parsing-v1

This validation uses ten new synthetic resume documents (five PDF and five DOCX) and ten
natural-language job description text files. It evaluates the existing deterministic text
extractor and skill/requirement evidence path only; it is not an LLM resume-structuring
benchmark.

## Metrics

| Metric | Result |
| --- | ---: |
| Resume samples | {metrics['resume_sample_count']} |
| Job description samples | {metrics['job_sample_count']} |
| Resume text extraction success | {metrics['resume_text_extraction_success']:.2%} |
| Job text extraction success | {metrics['job_text_extraction_success']:.2%} |
| Resume section extraction success | {metrics['resume_section_extraction_success']:.2%} |
| Resume skill precision / recall / F1 | {resume_prf['precision']:.2%} / {resume_prf['recall']:.2%} / {resume_prf['f1']:.2%} |
| Resume evidence attachment rate | {metrics['resume_evidence_attachment_rate']:.2%} |
| Job requirement precision / recall / F1 | {job_prf['precision']:.2%} / {job_prf['recall']:.2%} / {job_prf['f1']:.2%} |
| Required-vs-preferred accuracy | {metrics['job_required_vs_preferred_accuracy']:.2%} |

The sample is deliberately small and synthetic. The numbers describe extraction behavior on
these fixtures, not general parsing quality or hiring outcomes.
"""


def run(*, output_dir: Path | None = None) -> dict[str, Any]:
    input_path = ROOT / "dataset" / "parsing" / "cases.json"
    target = (output_dir or ROOT / "results" / "parsing-v1").resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"parsing output already exists at {target}; use a new directory")
    target.mkdir(parents=True, exist_ok=True)
    payload = _run_backend(input_path, target / "parsing-evaluation.json")
    summary = {
        "evaluation_version": "careerpilot-parsing-v1",
        "dataset_version": payload["dataset_version"],
        "scope": "deterministic_text_extraction_and_evidence_only",
        "metrics": _metrics(payload),
    }
    write_json(target / "evaluation_summary.json", summary)
    write_json(target / "evaluation_details.json", {"summary": summary, **payload})
    (target / "evaluation_report.md").write_text(_render_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parsing validation")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "parsing-v1")
    args = parser.parse_args()
    print(json.dumps(run(output_dir=args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
