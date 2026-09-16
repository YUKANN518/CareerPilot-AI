from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.matching.config import HYBRID_SCORING_CONFIG
from app.schemas.matching import MatchCreate, SemanticScoringConfig
from app.semantic.embeddings import (
    FakeEmbeddingProvider,
    SentenceTransformersEmbeddingProvider,
)
from app.semantic.index import SemanticIndexService
from app.semantic.matching import SemanticMatchingService
from app.services.jobs import JobService
from app.services.matching import MatchService
from app.services.resumes import ResumeService
from tests.test_matching import _create_case


def _semantic_settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={
            "embedding_provider": "fake",
            "faiss_index_dir": str(tmp_path / "faiss"),
        }
    )


def test_fake_embedding_provider_is_deterministic_and_handles_empty_text() -> None:
    provider = FakeEmbeddingProvider(dimensions=24)

    first = provider.embed_query("Python FastAPI")
    second = provider.embed_query("Python FastAPI")

    assert first == second
    assert len(first) == 24
    assert provider.embed_query("") == [0.0] * 24
    assert provider.config_snapshot.model == "fake-deterministic-v1"


def test_sentence_transformers_provider_is_lazy_and_normalizes_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class Model:
        def encode(
            self,
            texts: list[str],
            *,
            normalize_embeddings: bool,
            show_progress_bar: bool,
        ) -> list[list[float]]:
            assert normalize_embeddings is True
            assert show_progress_bar is False
            calls.append(texts)
            return [[0.6, 0.8] for _ in texts]

    monkeypatch.setattr(
        SentenceTransformersEmbeddingProvider,
        "_model",
        staticmethod(lambda _name, _device: Model()),
    )
    provider = SentenceTransformersEmbeddingProvider("local-test-model")

    assert provider.embed_documents(["中文项目", "Python API"]) == [
        [0.6, 0.8],
        [0.6, 0.8],
    ]
    assert provider.embed_query("") == []
    assert calls == [["中文项目", "Python API"]]


def test_resume_and_job_indexes_are_isolated_persistent_and_hash_aware(
    db_session: Session,
    admin_user,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    settings = _semantic_settings(test_settings, tmp_path)
    provider = FakeEmbeddingProvider()
    service = SemanticIndexService(settings, provider)

    resume_build = service.ensure_resume_index(case.version, admin_user.id)
    job_build = service.ensure_job_index(case.job, admin_user.id)
    repeated = service.ensure_job_index(case.job, admin_user.id)
    reloaded = SemanticIndexService(settings, provider).ensure_job_index(
        case.job,
        admin_user.id,
    )

    assert f"user-{admin_user.id}" in resume_build.path.as_posix()
    assert "/jobs/public/" in job_build.path.as_posix()
    assert resume_build.document_count > 0
    assert job_build.document_count > 0
    assert repeated.reused is True
    assert reloaded.reused is True
    assert service.index_status()["index_count"] == 2

    old_hash = job_build.content_hash
    case.job.requirements = f"{case.job.requirements} Kubernetes platform operations."
    db_session.commit()
    changed = service.ensure_job_index(case.job, admin_user.id)
    assert changed.reused is False
    assert changed.content_hash != old_hash


def test_private_job_index_rejects_other_users(
    db_session: Session,
    admin_user,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    case.job.owner_id = admin_user.id
    db_session.commit()
    service = SemanticIndexService(
        _semantic_settings(test_settings, tmp_path),
        FakeEmbeddingProvider(),
    )

    with pytest.raises(Exception) as error:
        service.ensure_job_index(case.job, admin_user.id + 1)

    assert getattr(error.value, "code", None) == "JOB_NOT_FOUND"


def test_resume_and_private_job_deletion_remove_owned_indexes(
    db_session: Session,
    admin_user,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    settings = _semantic_settings(test_settings, tmp_path)
    index = SemanticIndexService(settings, FakeEmbeddingProvider())
    resume_case = _create_case(db_session, admin_user, "high_match")
    resume_path = index.ensure_resume_index(resume_case.version, admin_user.id).path
    resume_id = resume_case.version.resume_id

    ResumeService(
        db_session,
        settings,
        semantic_index=index,
    ).delete(resume_id, admin_user)
    assert not resume_path.exists()

    job_case = _create_case(db_session, admin_user, "medium_match")
    job_case.job.owner_id = admin_user.id
    db_session.commit()
    job_path = index.ensure_job_index(job_case.job, admin_user.id).path
    JobService(
        db_session,
        settings,
        semantic_index=index,
    ).delete_private_job(admin_user, job_case.job.id)
    assert not job_path.exists()


def test_semantic_top_k_bounds_and_duplicate_evidence(
    db_session: Session,
    admin_user,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    index = SemanticIndexService(
        _semantic_settings(test_settings, tmp_path),
        FakeEmbeddingProvider(dimensions=64),
    )
    result = SemanticMatchingService(
        index,
        SemanticScoringConfig(top_k=2, similarity_threshold=-1),
    ).calculate(case.version, case.job, admin_user.id)
    pairs = {
        (
            item.resume_metadata["content_hash"],
            item.job_metadata["content_hash"],
        )
        for item in result.evidence
    }

    assert 0 <= result.score <= 100
    assert len(result.evidence) <= 2
    assert len(pairs) == len(result.evidence)
    assert [item.rank for item in result.evidence] == list(range(1, len(result.evidence) + 1))


def test_empty_job_requirements_cannot_receive_a_semantic_score(
    db_session: Session,
    admin_user,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    case = _create_case(db_session, admin_user, "incomplete_job")
    case.job.description = ""
    case.job.responsibilities = None
    case.job.requirements = None
    case.job.skills.clear()
    case.job.experience_level = None
    case.job.education_requirement = None
    case.job.language_requirements = []
    db_session.commit()
    index = SemanticIndexService(
        _semantic_settings(test_settings, tmp_path),
        FakeEmbeddingProvider(),
    )

    result = SemanticMatchingService(
        index,
        SemanticScoringConfig(top_k=5),
    ).calculate(case.version, case.job, admin_user.id)

    assert result.score == 0
    assert result.evidence == []


@pytest.mark.parametrize(
    ("fixture_name", "expected_recommendation"),
    [
        ("eligibility_blocked", "NOT_RECOMMENDED"),
        ("incomplete_job", "CONSIDER"),
    ],
)
def test_hybrid_score_preserves_blocking_and_recommendation_cap(
    db_session: Session,
    admin_user,
    test_settings: Settings,
    tmp_path: Path,
    fixture_name: str,
    expected_recommendation: str,
) -> None:
    case = _create_case(db_session, admin_user, fixture_name)
    provider = FakeEmbeddingProvider()
    settings = _semantic_settings(test_settings, tmp_path).model_copy(
        update={
            "semantic_top_k": 2,
            "semantic_similarity_threshold": -1.0,
        }
    )
    report = (
        MatchService(
            db_session,
            HYBRID_SCORING_CONFIG,
            settings=settings,
            embedding_provider=provider,
            semantic_index=SemanticIndexService(settings, provider),
        )
        .create(
            admin_user,
            MatchCreate(
                resume_version_id=case.version.id,
                job_id=case.job.id,
                scoring_version="hybrid-v1",
            ),
        )
        .report
    )

    assert report.semantic_score is not None
    assert report.hybrid_score == pytest.approx(
        report.rule_score * 0.7 + report.semantic_score * 0.3,
        abs=0.01,
    )
    assert report.final_score == report.hybrid_score
    assert report.recommendation == expected_recommendation
    assert report.policy_version == "blocking-policy-v1"
    assert report.embedding_model == "fake-deterministic-v1"
    assert report.semantic_summary is not None
    assert report.semantic_config_snapshot is not None
    assert report.semantic_config_snapshot.top_k == 2
    assert len(report.semantic_evidence) <= 2


def test_scoring_versions_and_embedding_snapshots_do_not_reuse_reports(
    db_session: Session,
    admin_user,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    settings = _semantic_settings(test_settings, tmp_path)
    first_provider = FakeEmbeddingProvider(dimensions=32)
    first_service = MatchService(
        db_session,
        settings=settings,
        embedding_provider=first_provider,
        semantic_index=SemanticIndexService(settings, first_provider),
    )
    rule = first_service.create(
        admin_user,
        MatchCreate(resume_version_id=case.version.id, job_id=case.job.id),
    )
    hybrid = first_service.create(
        admin_user,
        MatchCreate(
            resume_version_id=case.version.id,
            job_id=case.job.id,
            scoring_version="hybrid-v1",
        ),
    )
    reused = first_service.create(
        admin_user,
        MatchCreate(
            resume_version_id=case.version.id,
            job_id=case.job.id,
            scoring_version="hybrid-v1",
        ),
    )

    assert rule.report.scoring_version == "deterministic-v1.1"
    assert hybrid.report.id != rule.report.id
    assert reused.reused is True
    assert reused.report.id == hybrid.report.id
