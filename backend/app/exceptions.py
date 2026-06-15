from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class FXPGError(Exception):
    def __init__(self, message: str, code: str = "FXPG_ERROR", status: int = 400):
        self.message = message
        self.code = code
        self.status = status
        super().__init__(message)


async def fxpg_exception_handler(_request: Request, exc: FXPGError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "服务器内部错误，请稍后重试"}},
    )
