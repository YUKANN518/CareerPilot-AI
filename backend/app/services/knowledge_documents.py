"""Admin knowledge document service for Stage 4A.

Handles upload, asynchronous indexing, listing, re-indexing and deletion of
``KnowledgeDocument`` rows. Uploads reuse the existing PDF/DOCX file
validation and ``PrivateFileStorage`` patterns; indexing is delegated to
``KnowledgeIndexService``.
"""

from __future__ import annotations

import contextlib

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.files.storage import PrivateFileStorage
from app.files.validation import read_upload_limited, validate_resume_upload
from app.models.operations import KnowledgeDocument
from app.models.resumes import FileAsset
from app.models.users import User
from app.schemas.career_assistant import (
    KnowledgeDocumentListRead,
    KnowledgeDocumentRead,
    KnowledgeDocumentReindexResult,
)
from app.semantic.embeddings import embedding_provider_from_settings
from app.semantic.knowledge_index import KnowledgeIndexService


class KnowledgeDocumentService:
    """CRUD + indexing operations for admin knowledge documents."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.storage = PrivateFileStorage(settings.upload_directory)

    async def upload(
        self,
        admin: User,
        upload: UploadFile,
        *,
        title: str,
        category: str,
    ) -> KnowledgeDocumentRead:
        title = title.strip()
        category = category.strip()
        if not title or len(title) > 240:
            raise AppError(
                "KNOWLEDGE_DOCUMENT_TITLE_INVALID",
                "Title must be 1-240 characters",
                422,
            )
        if not category or len(category) > 80:
            raise AppError(
                "KNOWLEDGE_DOCUMENT_CATEGORY_INVALID",
                "Category must be 1-80 characters",
                422,
            )

        content = await read_upload_limited(
            upload,
            self.settings.resume_max_upload_bytes,
        )
        await upload.close()
        validated = validate_resume_upload(
            upload.filename,
            upload.content_type,
            content,
            self.settings.resume_max_upload_bytes,
        )

        storage_key = self.storage.save(
            admin.id,
            validated.file_format,
            validated.content,
        )
        asset = FileAsset(
            owner_id=admin.id,
            storage_key=storage_key,
            original_name=validated.original_name,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
            file_format=validated.file_format,
        )
        self.session.add(asset)
        self.session.flush()

        document = KnowledgeDocument(
            uploaded_by_id=admin.id,
            file_asset_id=asset.id,
            title=title,
            category=category,
            status="PENDING",
            chunk_count=0,
            metadata_json={},
        )
        self.session.add(document)
        self.session.flush()

        self.session.commit()
        self.session.refresh(document)
        return self._read(document)

    def list(self, *, offset: int, limit: int) -> KnowledgeDocumentListRead:
        statement = select(KnowledgeDocument)
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        documents = self.session.scalars(
            statement.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return KnowledgeDocumentListRead(
            items=[self._read(doc) for doc in documents],
            total=total,
            offset=offset,
            limit=limit,
        )

    def get(self, document_id: int) -> KnowledgeDocumentRead:
        return self._read(self._require(document_id))

    def delete(self, document_id: int) -> None:
        document = self._require(document_id)
        index_service = self._index_service()
        with contextlib.suppress(AppError):
            index_service.delete_index(document_id)
        file_asset_id = document.file_asset_id
        self.session.delete(document)
        self.session.flush()
        asset = self.session.get(FileAsset, file_asset_id)
        if asset is not None:
            with contextlib.suppress(AppError):
                self.storage.delete(asset.storage_key)
            self.session.delete(asset)
        self.session.commit()

    def queue_reindex(self, document_id: int) -> KnowledgeDocumentReindexResult:
        document = self._require(document_id)
        if document.status in {"PENDING", "PROCESSING"}:
            raise AppError(
                "KNOWLEDGE_DOCUMENT_ALREADY_PROCESSING",
                "The knowledge document is already being indexed",
                409,
            )
        document.status = "PENDING"
        document.error_code = None
        document.error_message = None
        self.session.commit()
        self.session.refresh(document)
        return KnowledgeDocumentReindexResult(
            document_id=document.id,
            status=document.status,
            chunk_count=document.chunk_count,
            reused=False,
        )

    def process_index_job(self, document_id: int) -> KnowledgeDocumentRead | None:
        """Run one index task with its own session, outside an HTTP request."""
        document = self.session.get(KnowledgeDocument, document_id)
        if document is None or document.status != "PENDING":
            return None
        document.status = "PROCESSING"
        document.error_code = None
        document.error_message = None
        self.session.commit()

        try:
            self._index_service().index_document(document)
            self.session.commit()
        except AppError as exc:
            document = self.session.get(KnowledgeDocument, document_id)
            if document is not None and document.status != "FAILED":
                document.status = "FAILED"
                document.error_code = exc.code
                document.error_message = "The knowledge document index could not be built"
            self.session.commit()
        except Exception:
            self.session.rollback()
            document = self.session.get(KnowledgeDocument, document_id)
            if document is not None:
                document.status = "FAILED"
                document.error_code = "KNOWLEDGE_INDEX_BUILD_FAILED"
                document.error_message = "The knowledge document index could not be built"
                self.session.commit()
        document = self._require(document_id)
        return self._read(document)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_service(self) -> KnowledgeIndexService:
        return KnowledgeIndexService(
            self.settings,
            embedding_provider_from_settings(self.settings),
            self.session,
        )

    def _require(self, document_id: int) -> KnowledgeDocument:
        document = self.session.get(KnowledgeDocument, document_id)
        if document is None:
            raise AppError(
                "KNOWLEDGE_DOCUMENT_NOT_FOUND",
                "The knowledge document was not found",
                404,
            )
        return document

    @staticmethod
    def _read(document: KnowledgeDocument) -> KnowledgeDocumentRead:
        return KnowledgeDocumentRead(
            id=document.id,
            title=document.title,
            category=document.category,
            status=document.status,
            chunk_count=document.chunk_count,
            content_hash=document.content_hash,
            error_code=document.error_code,
            error_message=document.error_message,
            indexed_at=document.indexed_at,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )
