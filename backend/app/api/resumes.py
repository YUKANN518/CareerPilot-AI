from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.dependencies import (
    AppSettings,
    CurrentUser,
    DbSession,
    ResumeProvider,
)
from app.schemas.common import ApiResponse
from app.schemas.matching import MatchListRead
from app.schemas.resume import (
    ExtractionResult,
    ParseResultRead,
    ResumeProfile,
    ResumeRead,
    ResumeSkillRead,
    ResumeUploadResult,
    ResumeVersionRead,
)
from app.services.matching import MatchService
from app.services.resumes import ResumeService

router = APIRouter(prefix="/resumes", tags=["resumes"])
version_router = APIRouter(prefix="/resume-versions", tags=["resume versions"])


@router.post(
    "/upload",
    response_model=ApiResponse[ResumeUploadResult],
    status_code=status.HTTP_201_CREATED,
    summary="上传 PDF 或 DOCX 简历",
    description=(
        "验证扩展名、MIME、文件签名与文件结构，按当前用户和 SHA-256 去重，"
        "并将原文件保存到非公开目录。"
    ),
)
async def upload_resume(
    response: Response,
    file: Annotated[UploadFile, File(description="不超过 10MB 的 PDF 或 DOCX 文件")],
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ResumeUploadResult]:
    result = await ResumeService(session, settings).upload(current_user, file)
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return ApiResponse(
        data=result,
        message="文件已存在，已返回原简历" if result.duplicate else "简历上传成功",
    )


@router.get(
    "",
    response_model=ApiResponse[list[ResumeRead]],
    summary="列出当前用户的简历",
)
def list_resumes(
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[list[ResumeRead]]:
    return ApiResponse(data=ResumeService(session, settings).list(current_user))


@router.get(
    "/{resume_id}",
    response_model=ApiResponse[ResumeRead],
    summary="获取简历状态与元数据",
)
def get_resume(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ResumeRead]:
    return ApiResponse(data=ResumeService(session, settings).get(resume_id, current_user))


@router.delete(
    "/{resume_id}",
    response_model=ApiResponse[dict[str, bool]],
    summary="删除简历及其版本",
)
def delete_resume(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[dict[str, bool]]:
    ResumeService(session, settings).delete(resume_id, current_user)
    return ApiResponse(data={"deleted": True}, message="简历已删除")


@router.get(
    "/{resume_id}/file",
    response_class=FileResponse,
    summary="下载或预览原始简历文件",
    description="仅文件所有者可访问，响应不会暴露服务器文件路径。",
)
def get_resume_file(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> FileResponse:
    path, asset = ResumeService(session, settings).get_file(resume_id, current_user)
    return FileResponse(
        path=path,
        media_type=asset.mime_type,
        filename=asset.original_name,
        content_disposition_type="inline",
    )


@router.post(
    "/{resume_id}/extract",
    response_model=ApiResponse[ExtractionResult],
    summary="提取简历文本及来源位置",
)
def extract_resume(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ExtractionResult]:
    result = ResumeService(session, settings).extract(resume_id, current_user)
    return ApiResponse(data=result, message="文本提取完成")


@router.post(
    "/{resume_id}/parse",
    response_model=ApiResponse[ParseResultRead],
    summary="执行 AI 结构化解析",
    description=(
        "通过配置的 AI Provider 生成严格 Schema，失败最多自动重试两次，"
        "最终失败时进入人工填写状态，不写入正式简历版本。"
    ),
)
async def parse_resume(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
    provider: ResumeProvider,
) -> ApiResponse[ParseResultRead]:
    result = await ResumeService(session, settings, provider).parse(
        resume_id,
        current_user,
    )
    return ApiResponse(data=result, message="结构化解析完成，请人工确认")


@router.get(
    "/{resume_id}/parse-result",
    response_model=ApiResponse[ParseResultRead],
    summary="查看待确认的结构化解析结果",
)
def get_parse_result(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ParseResultRead]:
    result = ResumeService(session, settings).get_parse_result(resume_id, current_user)
    return ApiResponse(data=result)


@router.patch(
    "/{resume_id}/parse-result",
    response_model=ApiResponse[ParseResultRead],
    summary="人工修改待确认的解析结果",
)
def update_parse_result(
    resume_id: int,
    payload: ResumeProfile,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ParseResultRead]:
    result = ResumeService(session, settings).update_parse_result(
        resume_id,
        current_user,
        payload,
    )
    return ApiResponse(data=result, message="解析结果已更新，尚未生成正式版本")


@router.post(
    "/{resume_id}/confirm",
    response_model=ApiResponse[ResumeVersionRead],
    status_code=status.HTTP_201_CREATED,
    summary="确认解析结果并创建不可覆盖版本",
)
def confirm_resume(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ResumeVersionRead]:
    version = ResumeService(session, settings).confirm(resume_id, current_user)
    return ApiResponse(data=version, message="简历版本已确认")


@router.get(
    "/{resume_id}/versions",
    response_model=ApiResponse[list[ResumeVersionRead]],
    summary="列出简历的历史版本",
)
def list_resume_versions(
    resume_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[list[ResumeVersionRead]]:
    versions = ResumeService(session, settings).list_versions(resume_id, current_user)
    return ApiResponse(data=versions)


@version_router.get(
    "/{version_id}",
    response_model=ApiResponse[ResumeVersionRead],
    summary="查看已确认的简历版本",
)
def get_resume_version(
    version_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ResumeVersionRead]:
    version = ResumeService(session, settings).get_version(version_id, current_user)
    return ApiResponse(data=version)


@version_router.get(
    "/{version_id}/skills",
    response_model=ApiResponse[list[ResumeSkillRead]],
    summary="查看版本中的技能及原文证据",
)
def list_resume_version_skills(
    version_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[list[ResumeSkillRead]]:
    skills = ResumeService(session, settings).list_version_skills(
        version_id,
        current_user,
    )
    return ApiResponse(data=skills)


@version_router.get(
    "/{version_id}/match-history",
    response_model=ApiResponse[MatchListRead],
    summary="List the current user's reports for a confirmed resume version",
)
def get_resume_version_match_history(
    version_id: int,
    current_user: CurrentUser,
    session: DbSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[MatchListRead]:
    return ApiResponse(
        data=MatchService(session).resume_history(
            current_user,
            version_id,
            offset=offset,
            limit=limit,
        )
    )
