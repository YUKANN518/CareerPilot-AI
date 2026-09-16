from pathlib import Path

from evaluation.matching.hybrid_runner import run


def test_hybrid_evaluation_preserves_policy_and_is_reproducible(tmp_path: Path) -> None:
    first = run(tmp_path / "first")
    second = run(tmp_path / "second")
    first_metrics = first["metrics"]
    second_metrics = second["metrics"]

    assert first_metrics["frozen_baseline_cases"] == 52
    assert first_metrics["semantic_cases"] == 10
    assert first_metrics["total_reviewed_cases"] == 62
    assert first_metrics["blocking_preserved"] is True
    assert first_metrics["incomplete_cap_preserved"] is True
    assert first_metrics["new_misjudgments"] == 0
    assert first_metrics["ranking_accuracy"] >= 0.8
    assert first_metrics["usable_experimental"] is True
    for key in (
        "recommendation_consistency_rate",
        "ranking_accuracy",
        "semantic_case_improvements",
        "new_misjudgments",
        "blocking_preserved",
        "incomplete_cap_preserved",
        "index_count",
        "index_size_bytes",
    ):
        assert first_metrics[key] == second_metrics[key]
