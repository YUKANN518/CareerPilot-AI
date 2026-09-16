"""Shared Dify workflow HTTP parsing, retry and redaction helpers."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from pydantic import JsonValue

from app.core.exceptions import AppError

MAX_PROVIDER_RETRIES = 2
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0)
RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 502, 503, 504})


def _is_retryable_error(exc: AppError) -> bool:
    return exc.code in {
        "DIFY_TIMEOUT",
        "DIFY_UNAVAILABLE",
        "DIFY_HTTP_RETRYABLE",
        "DIFY_EMPTY_OUTPUT",
        "DIFY_EMPTY_RESULT",
        "DIFY_INVALID_JSON",
    }


def _build_workflow_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/workflows/run"
    return f"{normalized}/v1/workflows/run"


def _extract_masked_metadata(raw: dict[str, Any], http_status: int) -> dict[str, Any]:
    raw_data = raw.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_outputs = data.get("outputs")
    outputs: dict[str, Any] = raw_outputs if isinstance(raw_outputs, dict) else {}
    workflow_run_id = _string_path(raw, ("workflow_run_id",)) or _string_path(
        raw, ("data", "workflow_run_id")
    )
    return {
        "http_status": http_status,
        "workflow_run_id": _truncate_str(workflow_run_id),
        "workflow_id": _truncate_str(_string_path(data, ("workflow_id",))),
        "status": _truncate_str(_string_path(data, ("status",))),
        "error": _truncate_str(_string_path(data, ("error",))),
        "total_steps": _optional_int(data.get("total_steps")),
        "elapsed_time": _optional_float(data.get("elapsed_time")),
        "outputs_keys": sorted(outputs.keys()),
    }


def _extract_output(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else None
    outputs = data.get("outputs") if isinstance(data, dict) else None
    candidate: Any = outputs if outputs is not None else raw.get("outputs", raw)
    if isinstance(outputs, dict) and not outputs:
        status = _string_path(raw, ("data", "status")) or _string_path(raw, ("status",))
        suffix = f" with status={status}" if status else ""
        raise AppError("DIFY_EMPTY_OUTPUT", f"Dify returned an empty outputs object{suffix}", 502)
    if isinstance(candidate, dict):
        if not candidate:
            raise AppError("DIFY_EMPTY_OUTPUT", "Dify returned an empty output object", 502)
        for key in ("result", "output", "text", "json"):
            value = candidate.get(key)
            if isinstance(value, str):
                if not value.strip():
                    raise AppError(
                        "DIFY_EMPTY_RESULT",
                        f"Dify returned an empty string for output key '{key}'",
                        502,
                    )
                return _parse_json(value)
            if isinstance(value, dict):
                return value
        return candidate
    if isinstance(candidate, str):
        if not candidate.strip():
            raise AppError("DIFY_EMPTY_RESULT", "Dify returned an empty output string", 502)
        return _parse_json(candidate)
    raise AppError("DIFY_OUTPUT_INVALID", "Dify returned an unsupported output shape", 502)


def _parse_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AppError("DIFY_INVALID_JSON", "Dify returned invalid JSON", 502) from exc
    if not isinstance(parsed, dict):
        raise AppError("DIFY_OUTPUT_INVALID", "Dify returned a non-object JSON output", 502)
    return parsed


def _string_path(raw: dict[str, Any], path: tuple[str, ...]) -> str | None:
    current: Any = raw
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _truncate_str(value: str | None, max_length: int = 160) -> str | None:
    if value is None or len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _elapsed_ms(started: float) -> int:
    return max(round((perf_counter() - started) * 1000), 0)


def _json_object(raw: dict[str, Any]) -> dict[str, JsonValue]:
    parsed = json.loads(json.dumps(raw, ensure_ascii=False, default=str))
    if not isinstance(parsed, dict):
        raise AppError("DIFY_OUTPUT_INVALID", "Dify returned a non-object response", 502)
    return parsed

