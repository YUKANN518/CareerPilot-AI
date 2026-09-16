from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def render_failure_analysis(metrics: dict[str, Any]) -> str:
    lines = [
        "# Evaluation Failure Analysis",
        "",
        "Failures are reported against manually annotated synthetic labels; they are not silently",
        "removed from the baseline.",
        "",
    ]
    failures = metrics.get("failures", [])
    if not failures:
        lines.append("No labelled failures.")
        return "\n".join(lines) + "\n"
    for failure in failures:
        lines.extend(
            [
                f"## {failure['case_id']}",
                "",
                f"- Category: `{failure['category']}`",
                f"- Expected: `{json.dumps(failure['expected'], ensure_ascii=False, sort_keys=True)}`",
                f"- Actual: `{json.dumps(failure['actual'], ensure_ascii=False, sort_keys=True)}`",
                "- Difference:",
                *[f"  - {item}" for item in failure["difference"]],
                "",
            ]
        )
    return "\n".join(lines)


def render_report(
    *,
    dataset_version: str,
    scoring_version: str,
    metrics: dict[str, Any],
    hybrid_metrics: dict[str, Any] | None,
    repeat: int,
) -> str:
    lines = [
        "# CareerPilot AI Matching Evaluation",
        "",
        f"- Dataset: `{dataset_version}`",
        "- Dataset type: manually annotated synthetic resume-job pairs",
        f"- Scoring version: `{scoring_version}`",
        f"- Repeats per case: `{repeat}`",
        f"- Generated: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Primary Metrics",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
    ]
    metric_names = [
        ("Required Skill Precision", "required_skill_precision"),
        ("Required Skill Recall", "required_skill_recall"),
        ("Required Skill F1", "required_skill_f1"),
        ("Missing Skill Precision", "missing_skill_precision"),
        ("Missing Skill Recall", "missing_skill_recall"),
        ("Missing Skill F1", "missing_skill_f1"),
        ("Blocking Risk Precision", "blocking_risk_precision"),
        ("Blocking Risk Recall", "blocking_risk_recall"),
        ("Blocking Risk F1", "blocking_risk_f1"),
        ("Evidence Validity", "evidence_validity"),
        ("Evidence-backed Match Rate", "evidence_backed_match_rate"),
        ("Unsupported Skill Claim Rate", "unsupported_skill_claim_rate"),
        ("Structured Result Validity", "structured_result_validity"),
        ("Recommendation Agreement", "recommendation_agreement"),
        ("Match Band Agreement (secondary)", "match_band_agreement"),
    ]
    lines.extend(f"| {label} | {_percent(metrics.get(field))} |" for label, field in metric_names)
    lines.extend(
        [
            "",
            "## Deterministic vs Semantic vs Hybrid",
            "",
            "The primary baseline evaluates the released deterministic matcher. The semantic",
            "runner uses the fixed fake embedding provider only as an offline relevance and",
            "blocking-preservation diagnostic. Semantic-only blocking metrics are `N/A` because",
            "semantic retrieval has no blocking policy of its own.",
            "",
            "| Mode | Required Skill F1 | Blocking Risk Recall / Preservation | Evidence Validity |",
            "| --- | ---: | ---: | ---: |",
            f"| Deterministic `{scoring_version}` | {_percent(metrics.get('required_skill_f1'))} | {_percent(metrics.get('blocking_risk_recall'))} | {_percent(metrics.get('evidence_validity'))} |",
            "| Semantic Only | N/A | N/A | N/A |",
        ]
    )
    if hybrid_metrics is not None:
        lines.append(
            f"| Hybrid diagnostic | N/A | {'100.00%' if hybrid_metrics.get('blocking_preserved') else '0.00%'} | N/A |"
        )
    else:
        lines.append("| Hybrid diagnostic | N/A | N/A | N/A |")
    lines.extend(
        [
            "",
            "## Failure Analysis",
            "",
            f"- Failed cases: `{metrics.get('failure_count', 0)}`",
            f"- Categories: `{json.dumps(metrics.get('failure_categories', {}), ensure_ascii=False, sort_keys=True)}`",
            "- Details: `FAILURE_ANALYSIS.md`",
            "",
            "## Algorithm Changes",
            "",
            "No matching algorithm was changed before this baseline. The evaluation layer invokes",
            "the existing requirement extractor, deterministic scorer and offline hybrid runner.",
            "",
            "## Limitations",
            "",
            "- The dataset is synthetic and manually annotated; it is not a hiring-success benchmark.",
            "- Structured fixtures begin after parsing, so parser quality is not measured here.",
            "- Semantic relevance is evaluated with controlled fake vectors, not a real provider.",
            "- Match Band Agreement is `N/A` until independent band labels are added.",
            "- Metrics describe this fixture set and should not be generalized to a population.",
            "",
        ]
    )
    return "\n".join(lines)
