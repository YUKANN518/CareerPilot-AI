"""API routes for the optional chat-based mock interview feature.

Endpoints
---------

* ``POST /api/interviews`` — create a new interview session (generates
  plan + questions)
* ``GET  /api/interviews`` — list owned interview sessions (failed
  records are hidden by default)
* ``GET  /api/interviews/{id}`` — fetch one session with questions and
* ``POST /api/interviews/{id}/chat/start`` — start the chat interview
  by presenting the first question via the Dify Chatflow
* ``POST /api/interviews/{id}/messages`` — submit one user answer in
  the chat flow; the response includes the next assistant message and
  hidden progress metadata
* ``GET  /api/interviews/{id}/messages`` — list all chat messages
* ``POST /api/interviews/{id}/chat/complete`` — user-initiated early
  completion; triggers the final evaluation Workflow
* ``POST /api/interviews/{id}/chat/cancel`` — cancel the interview
* ``GET  /api/interviews/{id}/chat/status`` — current chat status
* ``GET  /api/interviews/{id}/chat/report`` — final chat report

All routes require an authenticated user. The service layer enforces
ownership checks so user A cannot read or mutate user B's interviews.
"""

from fastapi import APIRouter, Query, status

from app.api.dependencies import AppSettings, CurrentUser, DbSession
from app.integrations.dify.interview_providers import (
    FakeInterviewChatProvider,
    FakeInterviewFinalEvaluationProvider,
    FakeInterviewPlanProvider,
    create_interview_chat_provider,
    create_interview_final_evaluation_provider,
    create_interview_plan_provider,
)
from app.schemas.common import ApiResponse
from app.schemas.interviews import (
    InterviewChatReportRead,
    InterviewChatStatusRead,
    InterviewChatTurnResponse,
    InterviewCreate,
    InterviewListRead,
    InterviewMessageRead,
    InterviewMessageSubmit,
    InterviewRead,
)
from app.services.interviews import InterviewService

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _full_service(session: DbSession, settings: AppSettings) -> InterviewService:
    """Build a service with configured plan/chat/final providers."""
    return InterviewService(
        session,
        create_interview_plan_provider(settings),
        create_interview_chat_provider(settings),
        create_interview_final_evaluation_provider(settings),
    )


def _readonly_service(session: DbSession) -> InterviewService:
    """Build a service for read-only list/get operations (no provider calls)."""
    return InterviewService(
        session,
        FakeInterviewPlanProvider(),
        FakeInterviewChatProvider(),
        FakeInterviewFinalEvaluationProvider(),
    )


@router.post(
    "",
    response_model=ApiResponse[InterviewRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a mock interview session",
)
def create_interview(
    payload: InterviewCreate,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[InterviewRead]:
    service = _full_service(session, settings)
    return ApiResponse(
        data=service.create(current_user.id, payload),
        message="Interview session created",
    )


@router.get(
    "",
    response_model=ApiResponse[InterviewListRead],
    summary="List the current user's interview sessions",
)
def list_interviews(
    current_user: CurrentUser,
    session: DbSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_failed: bool = Query(default=False),
) -> ApiResponse[InterviewListRead]:
    return ApiResponse(
        data=_readonly_service(session).list_interviews(
            current_user.id,
            offset=offset,
            limit=limit,
            include_failed=include_failed,
        )
    )


@router.get(
    "/{interview_id}",
    response_model=ApiResponse[InterviewRead],
    summary="Get one owned interview session",
)
def get_interview(
    interview_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[InterviewRead]:
    return ApiResponse(data=_readonly_service(session).get(current_user.id, interview_id))


@router.post(
    "/{interview_id}/chat/start",
    response_model=ApiResponse[InterviewChatStatusRead],
    summary="Start the chat-based interview by presenting the first question",
)
def start_chat(
    interview_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[InterviewChatStatusRead]:
    service = _full_service(session, settings)
    return ApiResponse(
        data=service.start_interview(current_user.id, interview_id),
        message="Interview chat started",
    )


@router.post(
    "/{interview_id}/messages",
    response_model=ApiResponse[InterviewChatTurnResponse],
    summary="Submit one user answer in the chat flow",
)
def send_message(
    interview_id: int,
    payload: InterviewMessageSubmit,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[InterviewChatTurnResponse]:
    service = _full_service(session, settings)
    return ApiResponse(
        data=service.send_message(
            current_user.id,
            interview_id,
            payload,
        ),
        message="Message processed",
    )


@router.get(
    "/{interview_id}/messages",
    response_model=ApiResponse[list[InterviewMessageRead]],
    summary="List all chat messages in the interview session",
)
def list_messages(
    interview_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[list[InterviewMessageRead]]:
    return ApiResponse(data=_readonly_service(session).get_messages(current_user.id, interview_id))


@router.post(
    "/{interview_id}/chat/complete",
    response_model=ApiResponse[InterviewChatStatusRead],
    summary="User-initiated early completion; triggers the final evaluation",
)
def complete_chat(
    interview_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[InterviewChatStatusRead]:
    service = _full_service(session, settings)
    return ApiResponse(
        data=service.complete_interview(current_user.id, interview_id),
        message="Interview completed",
    )


@router.post(
    "/{interview_id}/chat/cancel",
    response_model=ApiResponse[InterviewChatStatusRead],
    summary="Cancel the chat-based interview",
)
def cancel_chat(
    interview_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[InterviewChatStatusRead]:
    return ApiResponse(
        data=_readonly_service(session).cancel_interview(current_user.id, interview_id),
        message="Interview cancelled",
    )


@router.get(
    "/{interview_id}/chat/status",
    response_model=ApiResponse[InterviewChatStatusRead],
    summary="Get the current chat-based interview status",
)
def get_chat_status(
    interview_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[InterviewChatStatusRead]:
    return ApiResponse(
        data=_readonly_service(session).get_chat_status(current_user.id, interview_id)
    )


@router.get(
    "/{interview_id}/chat/report",
    response_model=ApiResponse[InterviewChatReportRead],
    summary="Get the final chat-based interview report",
)
def get_chat_report(
    interview_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[InterviewChatReportRead]:
    # Uses the full service so an unfinished session can finalize on demand.
    service = _full_service(session, settings)
    return ApiResponse(data=service.get_chat_report(current_user.id, interview_id))
