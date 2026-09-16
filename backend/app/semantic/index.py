from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.jobs import Job
from app.models.resumes import ResumeVersion
from app.semantic.documents import SemanticDocumentFactory
from app.semantic.embeddings import EmbeddingProvider, LangChainEmbeddingAdapter
from app.semantic.faiss_io import load_faiss_local, save_faiss_local


@dataclass(frozen=True)
class IndexBuildResult:
    path: Path
    document_count: int
    content_hash: str
    reused: bool


class SemanticIndexService:
    """Persist resource-scoped FAISS indexes without crossing ownership boundaries."""

    def __init__(
        self,
        settings: Settings,
        provider: EmbeddingProvider,
        documents: SemanticDocumentFactory | None = None,
    ) -> None:
        self.root = Path(settings.faiss_index_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self.embeddings = LangChainEmbeddingAdapter(provider)
        self.documents = documents or SemanticDocumentFactory()

    def ensure_resume_index(self, version: ResumeVersion, user_id: int) -> IndexBuildResult:
        if not version.is_confirmed:
            raise AppError(
                "RESUME_VERSION_NOT_CONFIRMED",
                "Only confirmed resume versions can be indexed",
                409,
            )
        docs = self.documents.resume_documents(version, user_id)
        return self._ensure(self._resume_path(user_id, version.id), docs, "resume")

    def ensure_job_index(self, job: Job, user_id: int) -> IndexBuildResult:
        if job.owner_id is not None and job.owner_id != user_id:
            raise AppError("JOB_NOT_FOUND", "The job was not found", 404)
        docs = self.documents.job_documents(job)
        return self._ensure(self._job_path(job), docs, "job")

    def load_job_index(self, job: Job, user_id: int) -> FAISS:
        self.ensure_job_index(job, user_id)
        return self._load(self._job_path(job))

    def delete_resume_index(self, user_id: int, version_id: int) -> None:
        self._remove(self._resume_path(user_id, version_id))

    def delete_job_index(self, job: Job) -> None:
        self._remove(self._job_path(job))

    def index_status(self) -> dict[str, int]:
        manifests = list(self.root.rglob("manifest.json"))
        return {
            "index_count": len(manifests),
            "size_bytes": sum(
                file.stat().st_size
                for manifest in manifests
                for file in manifest.parent.glob("*")
                if file.is_file()
            ),
        }

    def _ensure(
        self,
        path: Path,
        documents: list[Document],
        resource_type: str,
    ) -> IndexBuildResult:
        if not documents:
            raise AppError(
                "SEMANTIC_INDEX_EMPTY",
                f"The {resource_type} has no indexable confirmed text",
                422,
            )
        content_hash = self._combined_hash(documents)
        manifest = self._read_manifest(path)
        if (
            manifest.get("content_hash") == content_hash
            and manifest.get("embedding_model") == self.provider.config_snapshot.model
            and (path / "index.faiss").is_file()
            and (path / "index.pkl").is_file()
        ):
            try:
                self._load(path)
                return IndexBuildResult(path, len(documents), content_hash, True)
            except AppError:
                self._remove(path)

        self._remove(path)
        path.mkdir(parents=True, exist_ok=True)
        try:
            store = FAISS.from_documents(
                documents,
                self.embeddings,
                normalize_L2=True,
            )
            save_faiss_local(store, path)
            (path / "manifest.json").write_text(
                json.dumps(
                    {
                        "resource_type": resource_type,
                        "content_hash": content_hash,
                        "document_count": len(documents),
                        "embedding_model": self.provider.config_snapshot.model,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            self._remove(path)
            if isinstance(exc, AppError):
                raise
            raise AppError(
                "SEMANTIC_INDEX_BUILD_FAILED",
                f"The {resource_type} semantic index could not be built",
                503,
            ) from exc
        return IndexBuildResult(path, len(documents), content_hash, False)

    def _load(self, path: Path) -> FAISS:
        self._assert_under_root(path)
        try:
            return load_faiss_local(
                path,
                self.embeddings,
                normalize_l2=True,
            )
        except Exception as exc:
            raise AppError(
                "SEMANTIC_INDEX_CORRUPTED",
                "The local semantic index is unavailable and must be rebuilt",
                503,
            ) from exc

    def _resume_path(self, user_id: int, version_id: int) -> Path:
        return self.root / "resumes" / f"user-{user_id}" / f"resume-{version_id}"

    def _job_path(self, job: Job) -> Path:
        namespace = "public" if job.owner_id is None else f"user-{job.owner_id}"
        return self.root / "jobs" / namespace / f"job-{job.id}"

    def _remove(self, path: Path) -> None:
        self._assert_under_root(path)
        if path.exists():
            shutil.rmtree(path)

    def _assert_under_root(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise AppError("INVALID_INDEX_PATH", "The semantic index path is invalid", 500)

    @staticmethod
    def _combined_hash(documents: list[Document]) -> str:
        values = sorted(str(item.metadata["content_hash"]) for item in documents)
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, object]:
        try:
            raw = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}
