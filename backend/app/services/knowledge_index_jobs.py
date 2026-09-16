"""Durable, in-process background execution for knowledge document indexing.

The application deliberately keeps this small: each task owns a fresh
SQLAlchemy session and writes only a per-document FAISS directory.  No HTTP
request waits for parsing, embedding, or index persistence.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.operations import KnowledgeDocument
from app.services.knowledge_documents import KnowledgeDocumentService

logger = logging.getLogger(__name__)


class KnowledgeIndexJobRunner:
    """Queue one safe index task per document in a bounded thread pool."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="knowledge-index",
        )
        self._guard = Lock()
        self._document_locks: dict[int, Lock] = {}

    def submit(
        self,
        document_id: int,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
    ) -> Future[None]:
        return self._executor.submit(self._run, document_id, settings, session_factory)

    @contextmanager
    def document_lock(self, document_id: int) -> Iterator[None]:
        with self._guard:
            lock = self._document_locks.setdefault(document_id, Lock())
        with lock:
            yield

    def recover_interrupted(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
    ) -> None:
        """Requeue pending work and fail stale in-progress work at startup."""
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.knowledge_index_stale_after_seconds)
        pending_ids: list[int] = []
        with session_factory() as session:
            pending_ids = list(
                session.scalars(
                    select(KnowledgeDocument.id).where(KnowledgeDocument.status == "PENDING")
                )
            )
            stale = list(
                session.scalars(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.status == "PROCESSING",
                        KnowledgeDocument.updated_at < cutoff,
                    )
                )
            )
            for document in stale:
                document.status = "FAILED"
                document.error_code = "KNOWLEDGE_INDEX_INTERRUPTED"
                document.error_message = "The indexing task was interrupted; please retry indexing."
            if stale:
                session.commit()
                logger.warning(
                    "Marked interrupted knowledge indexing tasks as failed document_ids=%s",
                    [document.id for document in stale],
                )
        for document_id in pending_ids:
            self.submit(document_id, settings=settings, session_factory=session_factory)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(
        self,
        document_id: int,
        settings: Settings,
        session_factory: sessionmaker[Session],
    ) -> None:
        with self.document_lock(document_id), session_factory() as session:
            service = KnowledgeDocumentService(session, settings)
            try:
                service.process_index_job(document_id)
            except Exception as exc:  # The service has persisted a safe FAILED state.
                logger.error(
                    "Knowledge indexing task failed document_id=%s error_type=%s",
                    document_id,
                    type(exc).__name__,
                )


knowledge_index_job_runner = KnowledgeIndexJobRunner()
