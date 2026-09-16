from __future__ import annotations

import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "careerpilot-matplotlib"),
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from evaluation.matching.schemas import CaseResult, EvaluationLabel, EvaluationMetrics

BLUE = "#3954A5"
GOLD = "#C6922F"
ORANGE = "#D97735"
OLIVE = "#748C45"
PINK = "#B85C7A"
INK = "#172033"
GRID = "#D9DFEA"


def _finish(path: Path, title: str, subtitle: str) -> None:
    figure = plt.gcf()
    figure.suptitle(
        title,
        x=0.08,
        y=0.97,
        ha="left",
        fontsize=14,
        color=INK,
        weight="bold",
    )
    figure.text(0.08, 0.89, subtitle, ha="left", fontsize=9, color="#5E6B82")
    plt.tight_layout(rect=(0.05, 0.04, 0.98, 0.83))
    figure.savefig(path, dpi=160, facecolor="white")
    plt.close(figure)


def generate_charts(
    output_dir: Path,
    labels: list[EvaluationLabel],
    results: list[CaseResult],
    metrics: EvaluationMetrics,
) -> list[Path]:
    chart_dir = output_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    categories: dict[str, list[float]] = defaultdict(list)
    for result in results:
        categories[result.category.value].append(result.rule_score)
    plt.figure(figsize=(9, 5))
    plt.boxplot(
        list(categories.values()),
        tick_labels=list(categories),
        patch_artist=True,
    )
    for patch in plt.gca().patches:
        patch.set_facecolor(BLUE)
        patch.set_alpha(0.7)
    plt.xticks(rotation=25, ha="right")
    plt.ylabel("Rule score (0-100)")
    plt.grid(axis="y", color=GRID, linewidth=0.7)
    paths.append(chart_dir / "01-score-distribution.png")
    _finish(
        paths[-1],
        "Score distribution by case category",
        f"{len(labels)} synthetic labelled cases",
    )

    plt.figure(figsize=(7, 4))
    recommendation_values = [
        metrics.recommendation_accuracy * 100,
        (1 - metrics.recommendation_accuracy) * 100,
    ]
    plt.bar(
        ["Consistent", "Inconsistent"],
        recommendation_values,
        color=[BLUE, GOLD],
    )
    plt.ylim(0, 100)
    plt.ylabel("Share of cases (%)")
    paths.append(chart_dir / "02-recommendation-consistency.png")
    _finish(paths[-1], "Recommendation label consistency", "Allowed-label match rate")

    plt.figure(figsize=(6, 5))
    statuses = list(metrics.confusion_matrix)
    matrix = [[metrics.confusion_matrix[row][column] for column in statuses] for row in statuses]
    image = plt.imshow(matrix, cmap="Blues")
    plt.colorbar(image, label="Case-skill count")
    plt.xticks(range(len(statuses)), statuses, rotation=30, ha="right")
    plt.yticks(range(len(statuses)), statuses)
    plt.xlabel("Actual")
    plt.ylabel("Expected")
    for row, row_values in enumerate(matrix):
        for column, value in enumerate(row_values):
            plt.text(column, row, str(value), ha="center", va="center", color=INK)
    paths.append(chart_dir / "03-skill-confusion-matrix.png")
    _finish(paths[-1], "Skill-status confusion matrix", "Expected status by actual status")

    risk_counts = Counter(severity for result in results for severity in result.risks.values())
    plt.figure(figsize=(7, 4))
    risk_order = ["INFO", "LOW", "MEDIUM", "HIGH", "BLOCKING"]
    plt.bar(risk_order, [risk_counts[item] for item in risk_order], color=ORANGE)
    plt.ylabel("Risk conclusions")
    paths.append(chart_dir / "04-risk-severity-counts.png")
    _finish(paths[-1], "Risk conclusions by severity", "All deterministic-v1 risk outputs")

    plt.figure(figsize=(7, 4))
    plt.bar(
        ["Precision", "Recall"],
        [metrics.blocking_precision * 100, metrics.blocking_recall * 100],
        color=[BLUE, GOLD],
    )
    plt.ylim(0, 100)
    plt.ylabel("Percent")
    paths.append(chart_dir / "05-blocking-precision-recall.png")
    blocking_case_count = sum(bool(item.expected_blocking_risks) for item in labels)
    _finish(
        paths[-1],
        "Blocking risk precision and recall",
        f"{blocking_case_count} manually labelled blocking cases",
    )

    plt.figure(figsize=(8, 4))
    coverage = [
        metrics.evidence_trace_coverage,
        metrics.required_skill_evidence_coverage,
        metrics.blocking_evidence_coverage,
    ]
    plt.bar(
        ["All conclusions", "Required skills", "Blocking risks"],
        [item * 100 for item in coverage],
        color=[BLUE, OLIVE, GOLD],
    )
    plt.ylim(0, 100)
    plt.ylabel("Coverage (%)")
    paths.append(chart_dir / "06-evidence-coverage.png")
    _finish(paths[-1], "Evidence coverage", "Completeness rules differ by conclusion type")

    plt.figure(figsize=(8, 4))
    plt.hist([item.duration_ms for item in results], bins=10, color=BLUE, edgecolor=INK)
    plt.xlabel("Execution time (ms)")
    plt.ylabel("Cases")
    paths.append(chart_dir / "07-execution-time.png")
    _finish(paths[-1], "Execution-time distribution", "Direct service execution, one run per case")

    ranking = sorted(
        [item for item in results if item.expected_order_group == "python_backend"],
        key=lambda item: item.expected_order_rank or 0,
    )
    plt.figure(figsize=(8, 4))
    plt.bar([item.case_id for item in ranking], [item.rule_score for item in ranking], color=BLUE)
    plt.ylim(0, 100)
    plt.ylabel("Rule score")
    paths.append(chart_dir / "08-python-ranking.png")
    _finish(paths[-1], "Python resume multi-job ranking", "Expected order H01, M01, M02, G01")

    plt.figure(figsize=(7, 5))
    colors = [PINK if item.category.value == "INCOMPLETE_JOB" else BLUE for item in results]
    plt.scatter(
        [item.job_information_completeness * 100 for item in results],
        [item.rule_score for item in results],
        c=colors,
        edgecolors=INK,
    )
    plt.xlabel("Job information completeness (%)")
    plt.ylabel("Rule score")
    plt.xlim(-2, 102)
    plt.ylim(0, 102)
    plt.grid(color=GRID, linewidth=0.7)
    paths.append(chart_dir / "09-completeness-vs-score.png")
    _finish(paths[-1], "Job completeness and rule score", "Pink points are incomplete-job cases")
    return paths
