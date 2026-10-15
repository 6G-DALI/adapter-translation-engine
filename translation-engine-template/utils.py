"""
Helpers. COMMON to all testbeds - do not change.

  success(...)              build a success response
  error(...)                build an error response
  APIException              raise it to return an error from anywhere
  send_status_update(...)   POST a status update to the Framework
  doc(...)                  Swagger documentation entry for one HTTP status
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from models import AdapterStateUpdate, APIResponse, ErrorType, NewAdapterState, ResponseCode

logger = logging.getLogger("translation_engine")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def success(code: ResponseCode, message: str, data: Optional[dict] = None) -> dict:
    """Standard success response."""
    return {
        "result": "success",
        "code": code.value,
        "message": message,
        "data": data,
        "error": None,
        "timestamp": utc_timestamp(),
    }


def error(
    code: ResponseCode,
    message: str,
    err_type: ErrorType,
    details: Any = None,
) -> dict:
    """Standard error response."""
    return {
        "result": "error",
        "code": code.value,
        "message": message,
        "data": None,
        "error": {"type": err_type.value, "details": details},
        "timestamp": utc_timestamp(),
    }


class APIException(Exception):
    """
    Raise this to return an error in the standard format, e.g.:

        raise APIException(
            400, ResponseCode.INVALID_CONFIGURATION,
            "Scenario 'foo' does not exist on this testbed.",
            ErrorType.VALIDATION_ERROR,
            details={"field": "scenario_name"},
        )

    Do NOT use FastAPI's HTTPException: it wraps the body in {"detail": ...}.
    """

    def __init__(self, http_status: int, code: ResponseCode, message: str,
                 err_type: ErrorType, details: Any = None):
        super().__init__(message)
        self.http_status = http_status
        self.body = error(code, message, err_type, details)


async def send_status_update(
    exp_id: str, new_status: NewAdapterState, status_update_url: str
) -> bool:
    """
    POST {"exp_id", "new_status", "timestamp"} to the Framework.
    Returns True on success, False on failure (failure is logged, not raised).
    """
    body = AdapterStateUpdate(
        exp_id=exp_id, new_status=new_status, timestamp=utc_timestamp()
    ).model_dump(mode="json")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(status_update_url, json=body)
            response.raise_for_status()
        logger.info("Status '%s' sent for '%s'.", new_status.value, exp_id)
        return True
    except httpx.HTTPError as exc:
        logger.error("Status update failed for '%s': %s", exp_id, exc)
        return False


def doc(description: str, example: dict) -> dict:
    """Swagger entry for one HTTP status: the APIResponse schema + an example."""
    return {
        "model": APIResponse,
        "description": description,
        "content": {"application/json": {"example": example}},
    }
