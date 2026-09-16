"""Independent holdout-v1 execution and reporting.

This module is intentionally separate from ``evaluation.run`` so the frozen
52-case regression baseline cannot be overwritten accidentally.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.dataset import ROOT
from evaluation.metrics import calculate_metrics
from evaluation.report import write_json


def _project_root() -> Path:
    return ROOT.parent


def _backend_python() -> Path:
    candidate = _project_root() / "backend" / ".venv" / "Scripts" / "python.exe"
    return candidate if candidate.exists() else Path(sys.executable)


def _run_backend(input_path: Path, output_path: Path, scoring_version: str) -> dict[str, Any]:
    command = [
        str(_backend_python()),
        "-m",
        "evaluation.matching.holdout_runner",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--scoring-version",
        scoring_version,
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
            "holdout matcher failed:\n"
            + completed.stdout[-4000:]
            + completed.stderr[-4000:]
        )
    return json.loads(output_path.read_text(encoding="utf-8"))


def _labels_and_jobs(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    for case in cases:
        expected = case["expected"]
        band = expected.get("match_band")
        score_min, score_max = {
            "HIGH": (75.0, 100.0),
            "MODERATE": (45.0, 84.99),
            "LOW": (0.0, 54.99),
        }.get(band, (0.0, 100.0))
        labels.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "job_fixture": f"{case['case_id']}-job",
                "expected_score_min": score_min,
                "expected_score_max": score_max,
                "expected_recommendations": expected.get("recommendations", []),
                "expected_matched_skills": expected.get("matched_skills", []),
                "expected_partial_skills": expected.get("partial_skills", []),
                "expected_missing_skills": expected.get("missing_skills", []),
                "expected_unknown_skills": expected.get("unknown_skills", []),
                "expected_blocking_risks": expected.get("blocking_risks", []),
                "expected_match_band": band,
            }
        )
        jobs.append(
            {
                "fixture_id": f"{case['case_id']}-job",
                "skills": case["job"].get("skills", []),
            }
        )
    return labels, jobs


def _preferred_metrics(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, float]:
    by_id = {item["case_id"]: item for item in predictions}
    expected: set[str] = set()
    actual: set[str] = set()
    for case in cases:
        case_id = case["case_id"]
        required = {
            str(item["name"]).casefold()
            for item in case["job"].get("skills", [])
            if item.get("required", True)
        }
        expected_status = {
            str(item).casefold(): "MATCHED" for item in case["expected"].get("matched_skills", [])
        }
        for name, status in expected_status.items():
            if status == "MATCHED" and name not in required:
                expected.add(f"{case_id}:{name}")
        for name, status in by_id[case_id].get("skill_statuses", {}).items():
            if str(status) == "MATCHED" and str(name).casefold() not in required:
                actual.add(f"{case_id}:{str(name).casefold()}")
    true_positive = len(expected & actual)
    precision = true_positive / len(actual) if actual else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def _eligibility_metrics(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["case_id"]: item for item in predictions}
    hits = 0
    expected_counts: Counter[str] = Counter()
    actual_counts: Counter[str] = Counter()
    for case in cases:
        expected = str(case["expected"].get("eligibility", "UNVERIFIED"))
        result = by_id[case["case_id"]]
        risks = result.get("risks", {})
        if any(value == "BLOCKING" for value in risks.values()):
            actual = "BLOCKED"
        elif result.get("unknown_count", 0) or "WORK_ELIGIBILITY_UNKNOWN" in risks:
            actual = "UNVERIFIED"
        else:
            actual = "ELIGIBLE"
        expected_counts[expected] += 1
        actual_counts[actual] += 1
        hits += actual == expected
    return {
        "agreement": round(hits / len(cases), 4) if cases else 0.0,
        "expected_distribution": dict(expected_counts),
        "actual_distribution": dict(actual_counts),
    }


def _render_report(summary: dict[str, Any]) -> str:
    metrics = summary["metrics"]
    failures = metrics.get("failures", [])
    lines = [
        "# Independent Holdout Evaluation — holdout-v1",
        "",
        "This is a label-first synthetic holdout authored independently of the regression fixtures.",
        "It is evaluated with the frozen deterministic-v1.1 matcher; no matching rule, weight,",
        "threshold or alias was changed for this run.",
        "",
        f"- Cases: `{summary['case_count']}`",
        f"- Generated: `{summary['generated_at']}`",
        "- Annotation log: `evaluation/dataset/holdout/ANNOTATION_LOG.md`",
        "",
        "## Metrics",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
    ]
    for label, key in (
        ("Required skill precision", "required_skill_precision"),
        ("Required skill recall", "required_skill_recall"),
        ("Required skill F1", "required_skill_f1"),
        ("Missing skill precision", "missing_skill_precision"),
        ("Missing skill recall", "missing_skill_recall"),
        ("Missing skill F1", "missing_skill_f1"),
        ("Blocking risk precision", "blocking_risk_precision"),
        ("Blocking risk recall", "blocking_risk_recall"),
        ("Evidence validity", "evidence_validity"),
        ("Evidence-backed match rate", "evidence_backed_match_rate"),
        ("Unsupported skill claim rate", "unsupported_skill_claim_rate"),
        ("Structured result validity", "structured_result_validity"),
        ("Recommendation agreement", "recommendation_agreement"),
        ("Match band agreement", "match_band_agreement"),
    ):
        value = metrics.get(key)
        rendered = "N/A" if value is None else f"{float(value):.2%}"
        lines.append(f"| {label} | {rendered} |")
    preferred = summary["preferred_skill_metrics"]
    lines.extend(
        [
            f"| Preferred skill precision / recall / F1 | {preferred['precision']:.2%} / {preferred['recall']:.2%} / {preferred['f1']:.2%} |",
            f"| Eligibility agreement | {summary['eligibility']['agreement']:.2%} |",
            "",
            "## Failure analysis",
            "",
            f"- Failed cases: `{metrics.get('failure_count', 0)}`",
            f"- Categories: `{json.dumps(metrics.get('failure_categories', {}), ensure_ascii=False, sort_keys=True)}`",
        ]
    )
    if failures:
        lines.extend(["", "| Case | Category | Difference |", "| --- | --- | --- |"])
        for failure in failures:
            lines.append(
                f"| {failure['case_id']} | {failure['category']} | {'; '.join(failure['difference'])} |"
            )
    else:
        lines.extend(["", "No labelled failures."])
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This holdout is evidence about deterministic extraction and matching behavior on these",
            "synthetic scenarios only.  It is not a hiring-success benchmark, and no aggregate score",
            "across regression and holdout sets is reported.",
            "",
        ]
    )
    return "\n".join(lines)


def run(*, output_dir: Path | None = None, scoring_version: str = "deterministic-v1.1") -> dict[str, Any]:
    input_path = ROOT / "dataset" / "holdout" / "cases.json"
    target = (output_dir or ROOT / "results" / "holdout-v1").resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"holdout output already exists at {target}; use a new directory")
    target.mkdir(parents=True, exist_ok=True)
    raw_path = target / "holdout-evaluation.json"
    payload = _run_backend(input_path, raw_path, scoring_version)
    cases = payload["cases"]
    predictions = payload["results"]
    labels, jobs = _labels_and_jobs(cases)
    metrics = calculate_metrics(labels, predictions, jobs)
    summary = {
        "evaluation_version": "careerpilot-holdout-v1",
        "dataset_version": "holdout-v1",
        "dataset_type": "independent_label_first_synthetic_holdout",
        "case_count": len(cases),
        "scoring_version": scoring_version,
        "generated_at": "2026-09-16",
        "metrics": metrics,
        "preferred_skill_metrics": _preferred_metrics(cases, predictions),
        "eligibility": _eligibility_metrics(cases, predictions),
    }
    write_json(target / "evaluation_summary.json", summary)
    write_json(target / "evaluation_details.json", {"summary": summary, "cases": cases, "predictions": predictions})
    (target / "evaluation_report.md").write_text(_render_report(summary), encoding="utf-8")
    (target / "FAILURE_ANALYSIS.md").write_text(
        "# Holdout Failure Analysis\n\n"
        + "\n".join(
            f"## {item['case_id']}\n\n- Category: `{item['category']}`\n- Difference: "
            + "; ".join(item["difference"])
            + "\n"
            for item in metrics.get("failures", [])
        )
        if metrics.get("failures")
        else "# Holdout Failure Analysis\n\nNo labelled failures.\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent holdout-v1 evaluation")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "holdout-v1")
    parser.add_argument("--scoring-version", default="deterministic-v1.1")
    args = parser.parse_args()
    print(json.dumps(run(output_dir=args.output_dir, scoring_version=args.scoring_version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
