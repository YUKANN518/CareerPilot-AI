from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.common import ApiResponse
from app.schemas.matching import (
    MatchCreate,
    MatchCreateResult,
    MatchDetailRead,
    MatchListRead,
    MatchReportRead,
    MatchStatusRead,
)
from app.services.matching import MatchService

router = APIRouter(prefix="/matches", tags=["matches"])


@router.post(
    "",
    response_model=ApiResponse[MatchCreateResult],
    status_code=status.HTTP_201_CREATED,
    summary="Run versioned rule or hybrid matching",
    description=(
        "Matches one confirmed resume version with one accessible normalized job. "
        "The default is deterministic-v1.1; deterministic-v1 and experimental hybrid-v1 "
        "may be selected explicitly. Identical successful report inputs are reused."
    ),
)
def create_match(
    payload: MatchCreate,
    response: Response,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchCreateResult]:
    result = MatchService(session).create(current_user, payload)
    if result.reused:
        response.status_code = status.HTTP_200_OK
    return ApiResponse(
        data=result,
        message="Existing match report reused" if result.reused else "Match completed",
    )


@router.get(
    "",
    response_model=ApiResponse[MatchListRead],
    summary="List the current user's match reports",
)
def list_matches(
    current_user: CurrentUser,
    session: DbSession,
    resume_version_id: int | None = Query(default=None, ge=1),
    job_id: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[MatchListRead]:
    return ApiResponse(
        data=MatchService(session).list_reports(
            current_user,
            resume_version_id=resume_version_id,
            job_id=job_id,
            offset=offset,
            limit=limit,
        )
    )


@router.get(
    "/{match_id}/details",
    response_model=ApiResponse[list[MatchDetailRead]],
    summary="Get dimension, skill, risk, and evidence details",
)
def get_match_details(
    match_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[list[MatchDetailRead]]:
    return ApiResponse(data=MatchService(session).details(current_user, match_id))


@router.get(
    "/{match_id}/status",
    response_model=ApiResponse[MatchStatusRead],
    summary="Get the persisted match task status and phase timings",
)
def get_match_status(
    match_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchStatusRead]:
    return ApiResponse(data=MatchService(session).status(current_user, match_id))


@router.post(
    "/{match_id}/recalculate",
    response_model=ApiResponse[MatchCreateResult],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new report with the historical report's scoring version",
    description="The historical report is retained and never overwritten.",
)
def recalculate_match(
    match_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchCreateResult]:
    return ApiResponse(
        data=MatchService(session).recalculate(current_user, match_id),
        message="Match recalculated as a new report",
    )


@router.get(
    "/{match_id}",
    response_model=ApiResponse[MatchReportRead],
    summary="Get one explainable match report",
)
def get_match(
    match_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchReportRead]:
    return ApiResponse(data=MatchService(session).get(current_user, match_id))
