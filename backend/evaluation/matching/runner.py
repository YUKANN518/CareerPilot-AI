from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.matching.charts import generate_charts
from evaluation.matching.dataset import ROOT, load_dataset
from evaluation.matching.executor import EvaluationExecutor
from evaluation.matching.metrics import calculate_metrics
from evaluation.matching.report import write_outputs
from evaluation.matching.schemas import CaseResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deterministic matching")
    parser.add_argument("--scoring-version", default="deterministic-v1")
    parser.add_argument("--case")
    parser.add_argument("--category")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--format", choices=["json", "csv", "markdown"], action="append")
    return parser.parse_args()


def stability_rate(repeats: dict[str, list[CaseResult]]) -> float:
    consistent = 0
    total = 0
    for runs in repeats.values():
        if not runs:
            continue
        total += 1
        baseline = _stable_signature(runs[0])
        consistent += all(_stable_signature(item) == baseline for item in runs[1:])
    return round(consistent / total, 4) if total else 0.0


def _stable_signature(result: CaseResult) -> str:
    payload = result.model_dump(mode="json", exclude={"duration_ms"})
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def main() -> None:
    args = parse_args()
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1")
    dataset = load_dataset()
    labels = [
        item
        for item in dataset.labels
        if (args.case is None or item.case_id == args.case)
        and (args.category is None or item.category.value == args.category)
    ]
    if not labels:
        raise SystemExit("no evaluation cases matched the filters")
    executor = EvaluationExecutor(dataset.resumes, dataset.jobs)
    repeats = {
        label.case_id: [
            executor.run_case(label, scoring_version=args.scoring_version)
            for _ in range(args.repeat)
        ]
        for label in labels
    }
    results = [runs[0] for runs in repeats.values()]
    metrics = calculate_metrics(
        labels,
        results,
        repeat_consistency_rate=stability_rate(repeats),
    )
    candidate_repeats = {
        label.case_id: [
            executor.run_case(label, scoring_version="deterministic-v1.1")
            for _ in range(args.repeat)
        ]
        for label in labels
    }
    candidate = [runs[0] for runs in candidate_repeats.values()]
    candidate_metrics = calculate_metrics(
        labels,
        candidate,
        repeat_consistency_rate=stability_rate(candidate_repeats),
    )
    write_outputs(
        args.output_dir,
        labels,
        results,
        metrics,
        candidate,
        candidate_metrics,
        set(args.format) if args.format else None,
    )
    generate_charts(args.output_dir, labels, results, metrics)
    print(json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
