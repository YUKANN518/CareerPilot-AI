from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import AppSettings, CurrentUser, DbSession
from app.core.exceptions import AppError
from app.core.security import create_match_sse_ticket, decode_match_sse_ticket
from app.models.enums import TaskStatus
from app.repositories.users import UserRepository
from app.schemas.common import ApiResponse
from app.schemas.match_runs import (
    MatchRunActionResult,
    MatchRunCreate,
    MatchRunEventTicket,
    MatchRunRead,
)
from app.services.match_runs import MatchRunService

router = APIRouter(prefix="/match-runs", tags=["match-runs"])


@router.post(
    "",
    response_model=ApiResponse[MatchRunRead],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a durable LangGraph matching run",
)
def create_match_run(
    payload: MatchRunCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchRunRead]:
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    service = MatchRunService(session, session_factory=factory)
    run = service.create(current_user, payload)
    background_tasks.add_task(service.execute_in_background, run.run_id)
    return ApiResponse(data=run, message="Matching workflow started")


@router.get(
    "/{run_id}",
    response_model=ApiResponse[MatchRunRead],
    summary="Read a persisted matching workflow state",
)
def get_match_run(
    run_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchRunRead]:
    return ApiResponse(data=MatchRunService(session).get(current_user, run_id))


@router.post(
    "/{run_id}/event-ticket",
    response_model=ApiResponse[MatchRunEventTicket],
    summary="Issue a short-lived, run-scoped EventSource ticket",
)
def create_event_ticket(
    run_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[MatchRunEventTicket]:
    MatchRunService(session).get(current_user, run_id)
    ticket = create_match_sse_ticket(current_user.id, run_id, settings)
    return ApiResponse(data=MatchRunEventTicket(ticket=ticket.value, expires_at=ticket.expires_at))


@router.get(
    "/{run_id}/events",
    summary="Stream persisted workflow events with Server-Sent Events",
)
async def stream_match_run_events(
    run_id: int,
    session: DbSession,
    settings: AppSettings,
    ticket: str = Query(min_length=20),
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    payload = decode_match_sse_ticket(ticket, run_id, settings)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("INVALID_SSE_TICKET", "The event stream ticket is invalid", 401) from exc
    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "The event stream user was not found", 401)
    MatchRunService(session).get(user, run_id)
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    try:
        cursor = max(0, int(last_event_id or "0"))
    except ValueError:
        cursor = 0

    async def generate() -> AsyncIterator[str]:
        nonlocal cursor
        idle_cycles = 0
        while True:
            with factory() as stream_session:
                service = MatchRunService(stream_session, session_factory=factory)
                events = service.events(user, run_id, cursor)
                run = service.get(user, run_id)
            if events:
                idle_cycles = 0
                for event in events:
                    cursor = event.id
                    body = event.model_dump(mode="json")
                    yield (
                        f"id: {event.id}\n"
                        f"event: {event.event}\n"
                        f"data: {json.dumps(body, ensure_ascii=False)}\n\n"
                    )
            else:
                idle_cycles += 1
                if idle_cycles % 20 == 0:
                    yield ": keep-alive\n\n"
            if run.status in {
                TaskStatus.SUCCEEDED.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            }:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{run_id}/retry",
    response_model=ApiResponse[MatchRunActionResult],
    summary="Retry the failed node up to two times",
)
def retry_match_run(
    run_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchRunActionResult]:
    run = MatchRunService(session).retry(current_user, run_id)
    return ApiResponse(data=MatchRunActionResult(run=run), message="Failed node retried")


@router.post(
    "/{run_id}/confirm",
    response_model=ApiResponse[MatchRunActionResult],
    summary="Confirm the human review checkpoint",
)
def confirm_match_run(
    run_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchRunActionResult]:
    run = MatchRunService(session).confirm(current_user, run_id)
    return ApiResponse(data=MatchRunActionResult(run=run), message="Review confirmed")


@router.post(
    "/{run_id}/cancel",
    response_model=ApiResponse[MatchRunActionResult],
    summary="Cancel a non-terminal matching run",
)
def cancel_match_run(
    run_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MatchRunActionResult]:
    run = MatchRunService(session).cancel(current_user, run_id)
    return ApiResponse(data=MatchRunActionResult(run=run), message="Matching run cancelled")
