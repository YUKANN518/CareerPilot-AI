from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.dependencies import AppSettings, CurrentUser, DbSession
from app.models.enums import JobSourceType
from app.schemas.common import ApiResponse
from app.schemas.jobs import (
    FavoriteState,
    JobImportResult,
    JobListRead,
    JobRead,
    ManualJobPreview,
    UserJobCsvImport,
    UserJobInput,
    UserJobUpdate,
)
from app.schemas.matching import MatchListRead
from app.services.jobs import JobService
from app.services.matching import MatchService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/favorites",
    response_model=ApiResponse[JobListRead],
    summary="List the current user's favorite jobs",
)
def list_favorites(
    current_user: CurrentUser,
    session: DbSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[JobListRead]:
    return ApiResponse(data=JobService(session).list_favorites(current_user, offset, limit))


@router.post(
    "/manual/preview",
    response_model=ApiResponse[ManualJobPreview],
    summary="Normalize a private job before saving it",
)
def preview_manual_job(
    payload: UserJobInput,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ManualJobPreview]:
    return ApiResponse(data=JobService(session).preview_manual(current_user, payload))


@router.post(
    "/manual",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[JobImportResult],
    summary="Add a private job manually",
)
def import_manual_job(
    payload: UserJobInput,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[JobImportResult]:
    return ApiResponse(
        data=JobService(session).import_manual(current_user, payload),
        message="Job imported",
    )


@router.post(
    "/import-csv",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[JobImportResult],
    summary="Import private jobs from validated CSV content",
)
def import_job_csv(
    payload: UserJobCsvImport,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[JobImportResult]:
    return ApiResponse(
        data=JobService(session).import_csv(current_user, payload),
        message="CSV import completed",
    )


@router.get("", response_model=ApiResponse[JobListRead], summary="List normalized jobs")
def list_jobs(
    current_user: CurrentUser,
    session: DbSession,
    search: str | None = Query(default=None, max_length=120),
    location: str | None = Query(default=None, max_length=120),
    company: str | None = Query(default=None, max_length=160),
    employment_type: str | None = Query(default=None, max_length=80),
    experience_level: str | None = Query(default=None, max_length=80),
    source_id: int | None = Query(default=None, ge=1),
    source_name: str | None = Query(default=None, max_length=160),
    source_type: JobSourceType | None = Query(default=None),  # noqa: B008
    published_after: datetime | None = Query(default=None),  # noqa: B008
    information_type: Literal["SUMMARY"] | None = Query(default=None),
    visibility: Literal["ALL", "PUBLIC", "PRIVATE"] = Query(default="ALL"),
    status_filter: str = Query(default="ACTIVE", alias="status", max_length=24),
    sort: Literal[
        "published_desc",
        "published_asc",
        "salary_desc",
        "title_asc",
        "created_desc",
    ] = Query(default="published_desc"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[JobListRead]:
    data = JobService(session).list_jobs(
        user=current_user,
        search=search,
        location=location,
        company=company,
        employment_type=employment_type,
        experience_level=experience_level,
        source_id=source_id,
        source_name=source_name,
        source_type=source_type,
        published_after=published_after,
        status=status_filter,
        sort=sort,
        offset=offset,
        limit=limit,
        information_type=information_type,
        visibility=visibility,
    )
    return ApiResponse(data=data)


@router.post(
    "/{job_id}/favorite",
    response_model=ApiResponse[FavoriteState],
    summary="Favorite a visible job",
)
def favorite_job(
    job_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[FavoriteState]:
    JobService(session).favorite(current_user, job_id)
    return ApiResponse(
        data=FavoriteState(job_id=job_id, is_favorite=True),
        message="Job favorited",
    )


@router.delete(
    "/{job_id}/favorite",
    response_model=ApiResponse[FavoriteState],
    summary="Remove a job from favorites",
)
def unfavorite_job(
    job_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[FavoriteState]:
    JobService(session).unfavorite(current_user, job_id)
    return ApiResponse(
        data=FavoriteState(job_id=job_id, is_favorite=False),
        message="Favorite removed",
    )


@router.delete(
    "/{job_id}",
    response_model=ApiResponse[dict[str, bool]],
    summary="Delete a job privately imported by the current user",
)
def delete_private_job(
    job_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[dict[str, bool]]:
    JobService(session, settings).delete_private_job(current_user, job_id)
    return ApiResponse(data={"deleted": True}, message="Private job deleted")


@router.patch(
    "/{job_id}",
    response_model=ApiResponse[JobRead],
    summary="Update a privately imported job owned by the current user",
)
def update_private_job(
    job_id: int,
    payload: UserJobUpdate,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[JobRead]:
    return ApiResponse(
        data=JobService(session).update_private_job(current_user, job_id, payload),
        message="Private job updated",
    )


@router.get("/{job_id}", response_model=ApiResponse[JobRead], summary="Get one job")
def get_job(
    job_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[JobRead]:
    return ApiResponse(data=JobService(session).get_job(current_user, job_id))


@router.get(
    "/{job_id}/match-history",
    response_model=ApiResponse[MatchListRead],
    summary="List the current user's reports for an accessible job",
)
def get_job_match_history(
    job_id: int,
    current_user: CurrentUser,
    session: DbSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[MatchListRead]:
    return ApiResponse(
        data=MatchService(session).job_history(
            current_user,
            job_id,
            offset=offset,
            limit=limit,
        )
    )
