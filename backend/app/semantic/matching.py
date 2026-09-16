from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pydantic import JsonValue

from app.models.jobs import Job
from app.models.resumes import ResumeVersion
from app.schemas.matching import (
    SemanticEvidence,
    SemanticScoringConfig,
    SemanticSummary,
)
from app.semantic.documents import SemanticDocumentFactory
from app.semantic.index import SemanticIndexService

RELATIONS = {
    "project_experience": {
        "description",
        "responsibilities",
        "requirements",
        "required_skills",
        "preferred_skills",
    },
    "work_experience": {
        "description",
        "responsibilities",
        "requirements",
        "required_skills",
        "preferred_skills",
    },
    "skill_evidence": {"required_skills", "preferred_skills", "requirements"},
    "education": {"education_requirement", "requirements"},
    "certificate": {"requirements", "education_requirement"},
}


@dataclass(frozen=True)
class SemanticMatchResult:
    score: float
    evidence: list[SemanticEvidence]
    summary: SemanticSummary


class SemanticMatchingService:
    def __init__(
        self,
        index: SemanticIndexService,
        config: SemanticScoringConfig,
        documents: SemanticDocumentFactory | None = None,
    ) -> None:
        self.index = index
        self.config = config
        self.documents = documents or index.documents

    def calculate(
        self,
        resume_version: ResumeVersion,
        job: Job,
        user_id: int,
    ) -> SemanticMatchResult:
        self.index.ensure_resume_index(resume_version, user_id)
        store = self.index.load_job_index(job, user_id)
        resume_documents = self.documents.resume_documents(resume_version, user_id)
        candidates: list[SemanticEvidence] = []
        seen_pairs: set[tuple[str, str]] = set()
        fetch_k = max(self.config.top_k * 3, self.config.top_k)
        for resume_document in resume_documents:
            resume_section = str(resume_document.metadata["section"])
            allowed = RELATIONS.get(resume_section, set())
            if not allowed:
                continue
            for job_document, distance in store.similarity_search_with_score(
                resume_document.page_content,
                k=fetch_k,
            ):
                job_field = str(job_document.metadata["section"])
                if job_field not in allowed:
                    continue
                pair = (
                    str(resume_document.metadata["content_hash"]),
                    str(job_document.metadata["content_hash"]),
                )
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                similarity = self._cosine_from_l2(float(distance))
                if similarity < self.config.similarity_threshold:
                    continue
                candidates.append(
                    SemanticEvidence(
                        rank=1,
                        relation=f"{resume_section}_to_{job_field}",
                        similarity=similarity,
                        score=self._similarity_score(similarity),
                        resume_text=resume_document.page_content,
                        job_text=job_document.page_content,
                        resume_section=resume_section,
                        job_field=job_field,
                        page_number=self._optional_int(resume_document.metadata.get("page_number")),
                        paragraph_index=self._optional_int(
                            resume_document.metadata.get("paragraph_index"),
                            minimum=0,
                        ),
                        resume_metadata=self._json_metadata(resume_document.metadata),
                        job_metadata=self._json_metadata(job_document.metadata),
                    )
                )
        selected = sorted(
            candidates,
            key=lambda item: (-item.similarity, item.relation, item.resume_text, item.job_text),
        )[: self.config.top_k]
        evidence = [item.model_copy(update={"rank": rank}) for rank, item in enumerate(selected, 1)]
        score = (
            round(sum(item.score for item in evidence) / len(evidence), 2)
            if evidence
            else self.config.empty_score
        )
        relation_counts = Counter(item.relation for item in evidence)
        return SemanticMatchResult(
            score=max(0, min(100, score)),
            evidence=evidence,
            summary=SemanticSummary(
                evidence_count=len(evidence),
                evaluated_resume_chunks=len(resume_documents),
                top_similarity=evidence[0].similarity if evidence else None,
                relation_counts=dict(relation_counts),
            ),
        )

    def _similarity_score(self, similarity: float) -> float:
        floor = self.config.similarity_threshold
        ceiling = self.config.similarity_ceiling
        if similarity <= floor or ceiling <= floor:
            return 0
        return round(max(0, min(100, (similarity - floor) / (ceiling - floor) * 100)), 2)

    @staticmethod
    def _cosine_from_l2(distance: float) -> float:
        return round(max(-1, min(1, 1 - max(distance, 0) / 2)), 6)

    @staticmethod
    def _optional_int(value: object, *, minimum: int = 1) -> int | None:
        return int(value) if isinstance(value, int) and value >= minimum else None

    @staticmethod
    def _json_metadata(metadata: dict[str, object]) -> dict[str, JsonValue]:
        return {
            key: value
            for key, value in metadata.items()
            if value is None or isinstance(value, str | int | float | bool)
        }
