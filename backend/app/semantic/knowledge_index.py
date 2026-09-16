"""Knowledge base indexing service for Stage 4A Career Assistant.

Builds per-document FAISS indexes for ``KnowledgeDocument`` rows so the
Career Assistant can retrieve cited evidence snippets. The service reuses
the existing ``EmbeddingProvider`` contract and ``PrivateFileStorage``
patterns; it does not cross ownership boundaries and does not share
indexes with resume/job semantic indexes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.files.extraction import ResumeTextExtractor
from app.files.storage import PrivateFileStorage
from app.models.operations import KnowledgeDocument
from app.models.resumes import FileAsset
from app.semantic.embeddings import EmbeddingProvider, LangChainEmbeddingAdapter
from app.semantic.faiss_io import load_faiss_local, save_faiss_local

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeChunk:
    """A retrieved knowledge chunk with provenance for citation."""

    document_id: int
    title: str
    category: str
    chunk_text: str
    chunk_index: int
    page_number: int | None
    paragraph_index: int | None
    score: float


@dataclass(frozen=True)
class KnowledgeIndexResult:
    document_id: int
    chunk_count: int
    content_hash: str
    index_path: str
    reused: bool
    timings_ms: dict[str, int]


class KnowledgeIndexService:
    """Build, load and query per-document FAISS indexes for knowledge QA.

    Each ``KnowledgeDocument`` gets its own FAISS index directory under
    ``<faiss_index_dir>/knowledge/doc-<id>``. This keeps knowledge base
    indexes fully isolated from resume/job semantic indexes and makes
    per-document re-indexing and deletion cheap.
    """

    def __init__(
        self,
        settings: Settings,
        provider: EmbeddingProvider,
        session: Session,
    ) -> None:
        self.root = Path(settings.faiss_index_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self.embeddings = LangChainEmbeddingAdapter(provider)
        self.session = session
        self.storage = PrivateFileStorage(settings.upload_directory)
        self.extractor = ResumeTextExtractor()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,
            chunk_overlap=80,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_document(self, document: KnowledgeDocument) -> KnowledgeIndexResult:
        """Extract text, chunk, embed and persist a FAISS index for one doc.

        Updates ``KnowledgeDocument`` columns ``content_hash``, ``index_path``,
        ``chunk_count``, ``indexed_at``, ``status`` and clears any prior
        ``error_code`` / ``error_message`` on success. On failure the document
        is marked ``FAILED`` with structured error info and the exception is
        re-raised.
        """
        file_asset = self.session.get(FileAsset, document.file_asset_id)
        if file_asset is None:
            self._mark_failed(
                document,
                "KNOWLEDGE_DOCUMENT_FILE_MISSING",
                "The underlying file asset no longer exists",
            )
            raise AppError(
                "KNOWLEDGE_DOCUMENT_FILE_MISSING",
                "The underlying file asset no longer exists",
                404,
            )

        try:
            file_path = self.storage.resolve_existing(file_asset.storage_key)
        except AppError as exc:
            self._mark_failed(document, exc.code, exc.message)
            raise

        document.status = "PROCESSING"
        self.session.flush()
        timings_ms: dict[str, int] = {}

        try:
            with self._timed(timings_ms, "document_parse"):
                extraction = self.extractor.extract(file_path, file_asset.file_format)
            with self._timed(timings_ms, "text_chunking"):
                chunks = self._build_chunks(document, extraction.raw_text)
            if not chunks:
                self._mark_failed(
                    document,
                    "KNOWLEDGE_DOCUMENT_EMPTY",
                    "The document has no indexable text",
                )
                raise AppError(
                    "KNOWLEDGE_DOCUMENT_EMPTY",
                    "The document has no indexable text",
                    422,
                )

            with self._timed(timings_ms, "content_hash"):
                content_hash = self._combined_hash(chunks)
            index_path = self._doc_path(document.id)
            with self._timed(timings_ms, "faiss_index_read"):
                manifest = self._read_manifest(index_path)
            if (
                manifest.get("content_hash") == content_hash
                and manifest.get("embedding_model") == self.provider.config_snapshot.model
                and (index_path / "index.faiss").is_file()
                and (index_path / "index.pkl").is_file()
            ):
                try:
                    self._load(index_path)
                    reused = True
                except AppError:
                    self._remove(index_path)
                    reused = False
            else:
                reused = False

            if not reused:
                self._replace_with_new_index(
                    document,
                    chunks,
                    content_hash,
                    index_path,
                    timings_ms,
                )

            document.content_hash = content_hash
            document.index_path = str(index_path.relative_to(self.root)).replace("\\", "/")
            document.chunk_count = len(chunks)
            document.indexed_at = datetime.now(UTC)
            document.status = "READY"
            document.error_code = None
            document.error_message = None
            metadata = dict(document.metadata_json or {})
            metadata["indexing"] = {
                "timings_ms": timings_ms,
                "last_completed_at": datetime.now(UTC).isoformat(),
            }
            document.metadata_json = metadata
            self.session.flush()
            logger.info(
                "Knowledge document indexed document_id=%s chunks=%s reused=%s timings_ms=%s",
                document.id,
                len(chunks),
                reused,
                timings_ms,
            )
            return KnowledgeIndexResult(
                document_id=document.id,
                chunk_count=len(chunks),
                content_hash=content_hash,
                index_path=document.index_path,
                reused=reused,
                timings_ms=timings_ms,
            )
        except AppError as exc:
            self._mark_failed(document, exc.code, exc.message)
            raise
        except Exception as exc:
            self._mark_failed(
                document,
                "KNOWLEDGE_INDEX_BUILD_FAILED",
                "The knowledge document index could not be built",
            )
            raise AppError(
                "KNOWLEDGE_INDEX_BUILD_FAILED",
                "The knowledge document index could not be built",
                503,
            ) from exc

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        similarity_threshold: float = 0.25,
        document_ids: list[int] | None = None,
    ) -> list[KnowledgeChunk]:
        """Search across READY knowledge documents and return ranked chunks.

        ``document_ids`` optionally restricts the search to a subset of
        documents; ``None`` searches all READY documents. Results below
        ``similarity_threshold`` are filtered out.
        """
        query = query.strip()
        if not query:
            return []

        stmt = select(KnowledgeDocument).where(KnowledgeDocument.status == "READY")
        if document_ids is not None:
            if not document_ids:
                return []
            stmt = stmt.where(KnowledgeDocument.id.in_(document_ids))
        documents = list(self.session.execute(stmt).scalars())
        if not documents:
            return []

        results: list[KnowledgeChunk] = []
        for doc in documents:
            if not doc.index_path:
                continue
            index_path = self.root / doc.index_path
            try:
                store = self._load(index_path)
            except AppError:
                continue
            docs_with_scores = store.similarity_search_with_relevance_scores(
                query,
                k=top_k,
            )
            for hit, score in docs_with_scores:
                if score < similarity_threshold:
                    continue
                results.append(
                    KnowledgeChunk(
                        document_id=doc.id,
                        title=doc.title,
                        category=doc.category,
                        chunk_text=hit.page_content,
                        chunk_index=int(hit.metadata.get("chunk_index", 0)),
                        page_number=hit.metadata.get("page_number"),
                        paragraph_index=hit.metadata.get("paragraph_index"),
                        score=float(score),
                    )
                )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    def delete_index(self, document_id: int) -> None:
        """Remove the FAISS index directory for one document."""
        self._remove(self._doc_path(document_id))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_chunks(
        self,
        document: KnowledgeDocument,
        raw_text: str,
    ) -> list[Document]:
        cleaned = " ".join(raw_text.split())
        if not cleaned:
            return []
        texts = self.splitter.split_text(cleaned)
        chunks: list[Document] = []
        for index, text in enumerate(texts):
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                Document(
                    page_content=text,
                    metadata={
                        "document_id": document.id,
                        "title": document.title,
                        "category": document.category,
                        "chunk_index": index,
                        "content_hash": content_hash,
                    },
                )
            )
        return chunks

    def _replace_with_new_index(
        self,
        document: KnowledgeDocument,
        chunks: list[Document],
        content_hash: str,
        index_path: Path,
        timings_ms: dict[str, int],
    ) -> None:
        """Build in a temporary sibling directory, then atomically replace.

        A failed embedding or FAISS write must not leave a partially-written
        directory behind or incorrectly mark the document as READY.
        """
        parent = index_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary_path = Path(tempfile.mkdtemp(prefix=f".doc-{document.id}-", dir=parent))
        try:
            loader = getattr(self.provider, "ensure_model_loaded", None)
            if callable(loader):
                with self._timed(timings_ms, "embedding_model_load"):
                    loader()
            with self._timed(timings_ms, "embedding_calculation"):
                vectors = self.provider.embed_documents([chunk.page_content for chunk in chunks])
            if len(vectors) != len(chunks):
                raise AppError(
                    "EMBEDDING_FAILED",
                    "The configured document embedding provider returned invalid vectors",
                    503,
                )
            with self._timed(timings_ms, "faiss_write"):
                store = FAISS.from_embeddings(
                    [
                        (chunk.page_content, vector)
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ],
                    self.embeddings,
                    metadatas=[chunk.metadata for chunk in chunks],
                    normalize_L2=True,
                )
                save_faiss_local(store, temporary_path)
                (temporary_path / "manifest.json").write_text(
                    json.dumps(
                        {
                            "resource_type": "knowledge",
                            "document_id": document.id,
                            "content_hash": content_hash,
                            "document_count": len(chunks),
                            "embedding_model": self.provider.config_snapshot.model,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            self._replace_index_directory(temporary_path, index_path)
        finally:
            if temporary_path.exists():
                self._remove(temporary_path)

    def _replace_index_directory(self, temporary_path: Path, index_path: Path) -> None:
        self._assert_under_root(temporary_path)
        self._assert_under_root(index_path)
        backup_path = index_path.parent / f".backup-{index_path.name}-{uuid.uuid4().hex}"
        moved_existing = False
        try:
            if index_path.exists():
                index_path.replace(backup_path)
                moved_existing = True
            temporary_path.replace(index_path)
        except Exception:
            if moved_existing and backup_path.exists() and not index_path.exists():
                backup_path.replace(index_path)
            raise
        finally:
            if backup_path.exists():
                self._remove(backup_path)

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
                "KNOWLEDGE_INDEX_CORRUPTED",
                "The knowledge index is unavailable and must be rebuilt",
                503,
            ) from exc

    def _doc_path(self, document_id: int) -> Path:
        return self.root / "knowledge" / f"doc-{document_id}"

    def _remove(self, path: Path) -> None:
        self._assert_under_root(path)
        if path.exists():
            shutil.rmtree(path)

    def _assert_under_root(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise AppError("INVALID_INDEX_PATH", "The knowledge index path is invalid", 500)

    def _mark_failed(
        self,
        document: KnowledgeDocument,
        code: str,
        message: str,
    ) -> None:
        document.status = "FAILED"
        document.error_code = code
        document.error_message = message
        metadata = dict(document.metadata_json or {})
        metadata["indexing"] = {
            **dict(metadata.get("indexing") or {}),
            "last_failed_at": datetime.now(UTC).isoformat(),
        }
        document.metadata_json = metadata
        self.session.flush()

    @staticmethod
    @contextmanager
    def _timed(timings_ms: dict[str, int], phase: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            timings_ms[phase] = round((time.perf_counter() - started) * 1000)

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
