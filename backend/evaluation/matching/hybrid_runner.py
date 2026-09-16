from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.matching.config import DETERMINISTIC_V11_CONFIG, HYBRID_SCORING_CONFIG
from app.matching.normalization import SkillNormalizationService
from app.matching.policy import JobInformationAssessor
from app.matching.requirements import JobRequirementExtractor
from app.matching.scoring import DeterministicMatchEngine, recommendation_for_score
from app.models.jobs import Job, JobSkill
from app.models.resumes import ResumeSkill, ResumeVersion, Skill
from app.models.users import UserProfile
from app.schemas.matching import RecommendationLevel
from app.semantic.documents import SemanticDocumentFactory
from app.semantic.embeddings import FakeEmbeddingProvider
from app.semantic.index import SemanticIndexService
from app.semantic.matching import SemanticMatchingService

ROOT = Path(__file__).resolve().parent
ANCHOR = datetime(2026, 7, 18, tzinfo=UTC)


class SemanticCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: str
    resume_skills: list[str]
    job_skills: list[str]
    resume_text: str
    job_text: str
    expected_relevance: float = Field(ge=0, le=1)
    blocking: bool = False
    incomplete: bool = False
    duplicate_text: bool = False


def _field(value: str) -> dict[str, object]:
    return {
        "value": value,
        "confidence": 1,
        "evidence_text": value,
        "source_location": {"source_type": "page", "page_number": 1},
        "needs_confirmation": False,
    }


def _inputs(case: SemanticCase, number: int) -> tuple[ResumeVersion, Job, UserProfile]:
    version = ResumeVersion(
        id=1_000 + number,
        resume_id=1_000 + number,
        version_number=1,
        raw_text=case.resume_text,
        structured_data={
            "basic_info": {"location": _field("Shanghai")},
            "education": [
                {
                    "degree": _field("Bachelor"),
                    "description": _field(case.resume_text),
                }
            ],
            "work_experience": [
                {
                    "company": _field("Synthetic Labs"),
                    "title": _field("Engineer"),
                    "description": _field(case.resume_text),
                }
            ],
            "project_experience": [
                {
                    "name": _field("Anonymous Project"),
                    "description": _field(case.resume_text),
                }
            ],
            "certificates": [{"name": _field(case.resume_text)}],
            "languages": [_field("English")],
        },
        is_current=True,
        is_confirmed=True,
        created_at=ANCHOR,
        updated_at=ANCHOR,
    )
    for offset, name in enumerate(case.resume_skills, start=1):
        skill_id = number * 100 + offset
        version.skills.append(
            ResumeSkill(
                id=skill_id,
                resume_version_id=version.id,
                skill_id=skill_id,
                raw_name=name,
                confidence=0.95,
                evidence_text=case.resume_text,
                evidence_section="project_experience",
                evidence_source_id=f"page-1-{offset}",
                source_location=json.dumps({"page_number": 1, "block_index": offset}),
                is_user_confirmed=True,
                skill=Skill(id=skill_id, name=name, category="TECHNICAL"),
            )
        )
    requirements = None if case.incomplete else case.job_text
    job = Job(
        id=2_000 + number,
        title="Synthetic Role",
        company="Synthetic Evaluation Company",
        location=None if case.incomplete else "Shanghai",
        description=case.job_text,
        responsibilities=case.job_text,
        requirements=requirements,
        experience_level=None if case.incomplete else "2 years",
        education_requirement=None if case.incomplete else "Bachelor preferred",
        language_requirements=[] if case.incomplete else ["English"],
        employment_type=None if case.incomplete else "FULL_TIME",
        content_hash=f"{number:064x}"[-64:],
        raw_data={"industry": "Software"},
        status="ACTIVE",
    )
    for offset, name in enumerate(case.job_skills, start=1):
        skill_id = number * 1_000 + offset
        job.skills.append(
            JobSkill(
                id=skill_id,
                job_id=job.id,
                skill_id=skill_id,
                is_required=True,
                weight=2,
                evidence_text=f"Required skill: {name}",
                skill=Skill(id=skill_id, name=name, category="TECHNICAL"),
            )
        )
    profile = UserProfile(
        user_id=500,
        display_name="Anonymous Evaluation Candidate",
        location="Shanghai",
        target_roles=[],
        preferences={"work_eligibility": not case.blocking},
    )
    return version, job, profile


def _case_result(
    case: SemanticCase,
    number: int,
    settings: Settings,
) -> dict[str, Any]:
    version, job, profile = _inputs(case, number)
    factory = SemanticDocumentFactory()
    similarity = max(0, min(0.98, case.expected_relevance))
    resume_vector = [1.0, 0.0]
    job_vector = [similarity, math.sqrt(max(0, 1 - similarity**2))]
    vectors = {
        document.page_content: resume_vector
        for document in factory.resume_documents(version, profile.user_id)
    }
    vectors.update({document.page_content: job_vector for document in factory.job_documents(job)})
    provider = FakeEmbeddingProvider(vectors=vectors, dimensions=2)
    index = SemanticIndexService(settings, provider, factory)
    normalizer = SkillNormalizationService()
    requirements = JobRequirementExtractor(
        normalizer,
        DETERMINISTIC_V11_CONFIG.blocking_policy,
    ).extract(job)
    assessment = JobInformationAssessor.assess(job, requirements)
    started = perf_counter()
    deterministic = DeterministicMatchEngine(
        normalizer,
        DETERMINISTIC_V11_CONFIG,
    ).calculate(version, requirements, profile, assessment)
    semantic_config = HYBRID_SCORING_CONFIG.semantic
    weights = HYBRID_SCORING_CONFIG.hybrid_weights
    assert semantic_config is not None and weights is not None
    semantic = SemanticMatchingService(index, semantic_config).calculate(
        version,
        job,
        profile.user_id,
    )
    hybrid_score = round(
        deterministic.rule_score * weights.deterministic + semantic.score * weights.semantic,
        2,
    )
    hybrid_recommendation = recommendation_for_score(
        hybrid_score,
        deterministic.risks,
        deterministic.recommendation_cap,
    )
    duration_ms = round((perf_counter() - started) * 1000, 4)
    return {
        "case_id": case.case_id,
        "category": case.category,
        "expected_relevance": case.expected_relevance,
        "rule_score": deterministic.rule_score,
        "semantic_score": semantic.score,
        "hybrid_score": hybrid_score,
        "deterministic_recommendation": deterministic.recommendation.value,
        "hybrid_recommendation": hybrid_recommendation.value,
        "blocking": case.blocking,
        "blocking_preserved": (
            not case.blocking
            or (
                deterministic.recommendation is RecommendationLevel.NOT_RECOMMENDED
                and hybrid_recommendation is RecommendationLevel.NOT_RECOMMENDED
            )
        ),
        "incomplete": case.incomplete,
        "recommendation_cap": (
            deterministic.recommendation_cap.value
            if deterministic.recommendation_cap is not None
            else None
        ),
        "cap_preserved": (
            not case.incomplete
            or hybrid_recommendation
            in {
                RecommendationLevel.CONSIDER,
                RecommendationLevel.HIGH_RISK,
                RecommendationLevel.NOT_RECOMMENDED,
            }
        ),
        "semantic_evidence_count": len(semantic.evidence),
        "unique_semantic_pairs": len(
            {
                (
                    item.resume_metadata["content_hash"],
                    item.job_metadata["content_hash"],
                )
                for item in semantic.evidence
            }
        ),
        "improved": (
            case.expected_relevance >= 0.8
            and semantic.score >= 70
            and hybrid_score > deterministic.rule_score
        ),
        "new_misjudgment": (
            case.expected_relevance <= 0.2 and hybrid_score > deterministic.rule_score + 5
        ),
        "duration_ms": duration_ms,
    }


def _ranking_accuracy(results: list[dict[str, Any]]) -> float:
    correct = 0
    total = 0
    for left_index, left in enumerate(results):
        for right in results[left_index + 1 :]:
            expected_delta = float(left["expected_relevance"]) - float(right["expected_relevance"])
            if expected_delta == 0:
                continue
            total += 1
            actual_delta = float(left["hybrid_score"]) - float(right["hybrid_score"])
            correct += (expected_delta > 0 and actual_delta > 0) or (
                expected_delta < 0 and actual_delta < 0
            )
    return round(correct / total, 4) if total else 0


def run(output_dir: Path) -> dict[str, Any]:
    raw_cases = json.loads((ROOT / "semantic-cases.json").read_text(encoding="utf-8"))
    cases = [SemanticCase.model_validate(item) for item in raw_cases]
    baseline_labels = json.loads((ROOT / "labels" / "labels.json").read_text(encoding="utf-8"))
    if len(baseline_labels) != 52:
        raise RuntimeError("The frozen deterministic evaluation baseline must contain 52 cases")
    index_dir = output_dir / ".hybrid-evaluation-faiss"
    shutil.rmtree(index_dir, ignore_errors=True)
    settings = Settings(
        app_env="test",
        jwt_secret_key="evaluation-only-secret-key-with-at-least-32-characters",
        embedding_provider="fake",
        faiss_index_dir=str(index_dir),
    )
    results = [_case_result(case, number, settings) for number, case in enumerate(cases, start=1)]
    status = SemanticIndexService(
        settings,
        FakeEmbeddingProvider(dimensions=2),
    ).index_status()
    metrics = {
        "frozen_baseline_cases": len(baseline_labels),
        "semantic_cases": len(cases),
        "total_reviewed_cases": len(baseline_labels) + len(cases),
        "recommendation_consistency_rate": round(
            sum(
                item["deterministic_recommendation"] == item["hybrid_recommendation"]
                for item in results
            )
            / len(results),
            4,
        ),
        "ranking_accuracy": _ranking_accuracy(results),
        "semantic_case_improvements": sum(item["improved"] for item in results),
        "new_misjudgments": sum(item["new_misjudgment"] for item in results),
        "blocking_preserved": all(item["blocking_preserved"] for item in results),
        "incomplete_cap_preserved": all(item["cap_preserved"] for item in results),
        "average_duration_ms": round(
            sum(float(item["duration_ms"]) for item in results) / len(results),
            4,
        ),
        "index_count": status["index_count"],
        "index_size_bytes": status["size_bytes"],
        "embedding_model": "fake-deterministic-v1",
        "usable_experimental": False,
    }
    metrics["usable_experimental"] = bool(
        metrics["blocking_preserved"]
        and metrics["incomplete_cap_preserved"]
        and metrics["new_misjudgments"] == 0
        and float(metrics["ranking_accuracy"]) >= 0.8
    )
    payload = {
        "evaluation_version": "hybrid-v1-evaluation-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "cases": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "hybrid-v1-evaluation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# hybrid-v1 离线评估",
        "",
        f"- 冻结确定性基线: {metrics['frozen_baseline_cases']} 组",
        f"- 新增语义案例: {metrics['semantic_cases']} 组",
        f"- 推荐一致率: {float(metrics['recommendation_consistency_rate']):.1%}",
        f"- 排序准确率: {float(metrics['ranking_accuracy']):.1%}",
        f"- 语义案例改善数: {metrics['semantic_case_improvements']}",
        f"- 新增误判数: {metrics['new_misjudgments']}",
        f"- Blocking 保持: {metrics['blocking_preserved']}",
        f"- 信息不完整上限保持: {metrics['incomplete_cap_preserved']}",
        f"- 平均执行耗时: {metrics['average_duration_ms']} ms",
        f"- 临时索引大小: {metrics['index_size_bytes']} bytes",
        f"- 可用实验版本: {metrics['usable_experimental']}",
        "",
        "详细逐例数据见 `hybrid-v1-evaluation.json`。",
    ]
    (output_dir / "hybrid-v1-evaluation.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(index_dir, ignore_errors=True)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate hybrid-v1 offline")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir)["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
