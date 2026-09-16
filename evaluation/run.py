from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.dataset import ROOT, DatasetValidationError, load_dataset
from evaluation.metrics import calculate_metrics
from evaluation.report import render_failure_analysis, render_report, write_json


def _project_root() -> Path:
    return ROOT.parent


def _backend_python() -> Path:
    candidate = _project_root() / "backend" / ".venv" / "Scripts" / "python.exe"
    return candidate if candidate.exists() else Path(sys.executable)


def _run_backend_evaluation(output_dir: Path, scoring_version: str, repeat: int) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(_backend_python()),
        "-m",
        "evaluation.matching.runner",
        "--scoring-version",
        scoring_version,
        "--repeat",
        str(repeat),
        "--output-dir",
        str(output_dir),
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
            "backend evaluation failed:\n"
            + completed.stdout[-4000:]
            + completed.stderr[-4000:]
        )
    result_path = output_dir / "matching-evaluation.json"
    if not result_path.exists():
        raise RuntimeError(f"backend evaluation did not write {result_path}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def _run_hybrid_diagnostic(output_dir: Path) -> dict[str, Any] | None:
    command = [
        str(_backend_python()),
        "-m",
        "evaluation.matching.hybrid_runner",
        "--output-dir",
        str(output_dir),
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
            "hybrid evaluation failed:\n"
            + completed.stdout[-4000:]
            + completed.stderr[-4000:]
        )
    result_path = output_dir / "hybrid-v1-evaluation.json"
    return json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CareerPilot AI file-based evaluation")
    parser.add_argument(
        "--scoring-version",
        default="deterministic-v1.1",
        choices=("deterministic-v1", "deterministic-v1.1"),
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--skip-hybrid", action="store_true")
    return parser.parse_args()


def run(
    *,
    scoring_version: str = "deterministic-v1.1",
    repeat: int = 3,
    output_dir: Path | None = None,
    skip_hybrid: bool = False,
) -> dict[str, Any]:
    if repeat < 1:
        raise DatasetValidationError("repeat must be at least 1")
    dataset = load_dataset()
    target = (output_dir or (ROOT / "results")).resolve()
    target.mkdir(parents=True, exist_ok=True)
    baseline_dir = target / "baseline"
    if baseline_dir.exists():
        raise FileExistsError(
            f"baseline already exists at {baseline_dir}; use a new output directory to avoid overwriting it"
        )
    raw_dir = target / "_raw"
    raw_payload = _run_backend_evaluation(raw_dir, scoring_version, repeat)
    predictions = raw_payload.get("results", [])
    metrics = calculate_metrics(dataset.labels, predictions, dataset.jobs)
    hybrid_payload = None if skip_hybrid else _run_hybrid_diagnostic(raw_dir)
    baseline_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(raw_dir / "matching-evaluation.json", baseline_dir / "matching-evaluation.json")
    if hybrid_payload is not None and (raw_dir / "hybrid-v1-evaluation.json").exists():
        shutil.copy2(raw_dir / "hybrid-v1-evaluation.json", baseline_dir / "hybrid-v1-evaluation.json")
    source_hash = hashlib.sha256(
        (ROOT / "dataset" / "manifest.json").read_bytes()
        + json.dumps(dataset.labels, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    write_json(
        baseline_dir / "metadata.json",
        {
            "matching_version": scoring_version,
            "rules_version": "blocking-policy-v1",
            "dataset_version": dataset.version,
            "evaluation_date": datetime.now(UTC).isoformat(),
            "dataset_source_sha256": source_hash,
        },
    )
    summary = {
        "evaluation_version": "careerpilot-eval-v1",
        "dataset_version": dataset.version,
        "dataset_type": dataset.manifest.get("annotation_status"),
        "dataset_size": dataset.case_count,
        "scoring_version": scoring_version,
        "repeat": repeat,
        "algorithm_changed_before_baseline": False,
        "metrics": {key: value for key, value in metrics.items() if key not in {"failures"}},
        "hybrid_diagnostic": (
            hybrid_payload.get("metrics") if hybrid_payload is not None else None
        ),
    }
    write_json(target / "evaluation_summary.json", summary)
    write_json(
        target / "evaluation_details.json",
        {
            "summary": summary,
            "predictions": predictions,
            "labels": dataset.labels,
        },
    )
    (target / "FAILURE_ANALYSIS.md").write_text(
        render_failure_analysis(metrics),
        encoding="utf-8",
    )
    (target / "evaluation_report.md").write_text(
        render_report(
            dataset_version=dataset.version,
            scoring_version=scoring_version,
            metrics=metrics,
            hybrid_metrics=(hybrid_payload or {}).get("metrics"),
            repeat=repeat,
        ),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = _parse_args()
    summary = run(
        scoring_version=args.scoring_version,
        repeat=args.repeat,
        output_dir=args.output_dir,
        skip_hybrid=args.skip_hybrid,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
