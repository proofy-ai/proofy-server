"""공통 오류 응답(계약 1.1). 모든 4xx/5xx를 `{ "error": { code, message, details } }`로 내보낸다."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("proofy")


class ApiError(Exception):
    """서비스·라우터에서 직접 던지는 오류. `code`는 계약 1.1 표의 값만 쓴다."""

    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message, exc.details)


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields: dict[str, str] = {}
    for err in exc.errors():
        # loc 예: ("body", "inflow", "amountKrw") → "inflow.amountKrw"
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header")]
        fields[".".join(loc) or "request"] = err.get("msg", "잘못된 값")
    return error_response(400, "VALIDATION_ERROR", "입력값을 확인해 주세요.", {"fields": fields})


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return error_response(404, "NOT_FOUND", "요청한 주소를 찾을 수 없습니다.")
    if exc.status_code < 500:
        # 계약에 없는 4xx(예: 405)는 요청 오류로 묶는다
        return error_response(exc.status_code, "VALIDATION_ERROR", "요청을 처리할 수 없습니다.")
    return error_response(exc.status_code, "INTERNAL", "서버 오류가 발생했습니다.")


async def _unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    # 내부 내용은 응답에 넣지 않고 로그로만 남긴다
    logger.exception("처리하지 못한 예외", exc_info=exc)
    return error_response(500, "INTERNAL", "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
