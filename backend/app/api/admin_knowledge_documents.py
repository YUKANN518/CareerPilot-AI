"""Admin knowledge document API for Stage 4A.

Admin-only endpoints to upload, list, inspect, re-index and delete
knowledge base documents that back the Career Assistant QA feature.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import AppSettings, DbSession, require_roles
from app.models.enums import UserRole
from app.models.users import User
from app.schemas.career_assistant import (
    KnowledgeDocumentListRead,
    KnowledgeDocumentRead,
    KnowledgeDocumentReindexResult,
)
from app.schemas.common import ApiResponse
from app.services.knowledge_documents import KnowledgeDocumentService
from app.services.knowledge_index_jobs import knowledge_index_job_runner

router = APIRouter(prefix="/admin/knowledge-documents", tags=["admin knowledge documents"])

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.post(
    "",
    response_model=ApiResponse[KnowledgeDocumentRead],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a knowledge document and queue background indexing (PDF/DOCX)",
)
async def upload_knowledge_document(
    file: Annotated[UploadFile, File(description="PDF 或 DOCX 知识文档")],
    title: Annotated[str, Form(description="文档标题", min_length=1, max_length=240)],
    category: Annotated[str, Form(description="文档分类", min_length=1, max_length=80)],
    current_user: AdminUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[KnowledgeDocumentRead]:
    result = await KnowledgeDocumentService(session, settings).upload(
        current_user,
        file,
        title=title,
        category=category,
    )
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    knowledge_index_job_runner.submit(result.id, settings=settings, session_factory=factory)
    return ApiResponse(data=result, message="知识文档已上传，正在后台解析和建立索引")


@router.get(
    "",
    response_model=ApiResponse[KnowledgeDocumentListRead],
    summary="List knowledge documents",
)
def list_knowledge_documents(
    _current_user: AdminUser,
    session: DbSession,
    settings: AppSettings,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[KnowledgeDocumentListRead]:
    return ApiResponse(
        data=KnowledgeDocumentService(session, settings).list(offset=offset, limit=limit)
    )


@router.get(
    "/{document_id}",
    response_model=ApiResponse[KnowledgeDocumentRead],
    summary="Read one knowledge document",
)
def get_knowledge_document(
    document_id: int,
    _current_user: AdminUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[KnowledgeDocumentRead]:
    return ApiResponse(data=KnowledgeDocumentService(session, settings).get(document_id))


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge document and its index",
)
def delete_knowledge_document(
    document_id: int,
    _current_user: AdminUser,
    session: DbSession,
    settings: AppSettings,
) -> None:
    with knowledge_index_job_runner.document_lock(document_id):
        KnowledgeDocumentService(session, settings).delete(document_id)


@router.post(
    "/{document_id}/reindex",
    response_model=ApiResponse[KnowledgeDocumentReindexResult],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-index a knowledge document",
)
def reindex_knowledge_document(
    document_id: int,
    _current_user: AdminUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[KnowledgeDocumentReindexResult]:
    result = KnowledgeDocumentService(session, settings).queue_reindex(document_id)
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    knowledge_index_job_runner.submit(document_id, settings=settings, session_factory=factory)
    return ApiResponse(data=result, message="知识文档正在重新索引")
