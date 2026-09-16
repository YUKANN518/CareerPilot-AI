"""Career Assistant knowledge QA API for Stage 4A.

Exposes endpoints to start a QA run (background LangGraph execution),
read/list runs, and stream persisted events over SSE. SSE access is
gated by a short-lived, run-scoped ticket to avoid long-lived bearer
tokens on the EventSource connection.
"""

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
from app.core.security import create_career_qa_sse_ticket, decode_career_qa_sse_ticket
from app.models.enums import TaskStatus
from app.repositories.users import UserRepository
from app.schemas.career_assistant import (
    CareerAssistantQACreate,
    CareerAssistantQAEventTicket,
    CareerAssistantQAListRead,
    CareerAssistantQARead,
)
from app.schemas.common import ApiResponse
from app.services.career_assistant import CareerAssistantQAService

router = APIRouter(prefix="/career-assistant", tags=["career-assistant"])


@router.post(
    "/qa",
    response_model=ApiResponse[CareerAssistantQARead],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a knowledge QA run",
)
def create_qa_run(
    payload: CareerAssistantQACreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[CareerAssistantQARead]:
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    service = CareerAssistantQAService(session, settings, session_factory=factory)
    run = service.create(current_user, payload)
    background_tasks.add_task(service.execute_in_background, run.id)
    return ApiResponse(data=run, message="Career assistant QA run started")


@router.get(
    "/qa",
    response_model=ApiResponse[CareerAssistantQAListRead],
    summary="List the current user's QA runs",
)
def list_qa_runs(
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[CareerAssistantQAListRead]:
    return ApiResponse(
        data=CareerAssistantQAService(session, settings).list_user(
            current_user,
            offset=offset,
            limit=limit,
        )
    )


@router.get(
    "/qa/{run_id}",
    response_model=ApiResponse[CareerAssistantQARead],
    summary="Read a persisted QA run",
)
def get_qa_run(
    run_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[CareerAssistantQARead]:
    return ApiResponse(data=CareerAssistantQAService(session, settings).get(current_user, run_id))


@router.post(
    "/qa/{run_id}/event-ticket",
    response_model=ApiResponse[CareerAssistantQAEventTicket],
    summary="Issue a short-lived, run-scoped EventSource ticket",
)
def create_qa_event_ticket(
    run_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[CareerAssistantQAEventTicket]:
    CareerAssistantQAService(session, settings).get(current_user, run_id)
    ticket = create_career_qa_sse_ticket(current_user.id, run_id, settings)
    return ApiResponse(
        data=CareerAssistantQAEventTicket(ticket=ticket.value, expires_at=ticket.expires_at)
    )


@router.get(
    "/qa/{run_id}/events",
    summary="Stream persisted QA events with Server-Sent Events",
)
async def stream_qa_events(
    run_id: int,
    session: DbSession,
    settings: AppSettings,
    ticket: str = Query(min_length=20),
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    payload = decode_career_qa_sse_ticket(ticket, run_id, settings)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("INVALID_SSE_TICKET", "The event stream ticket is invalid", 401) from exc
    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "The event stream user was not found", 401)
    CareerAssistantQAService(session, settings).get(user, run_id)
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
                service = CareerAssistantQAService(
                    stream_session, settings, session_factory=factory
                )
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
