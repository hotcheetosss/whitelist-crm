"""Application factory: error handlers, routers, migrations on startup."""

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import PORT, database_path
from app.db import apply_migrations
from app.errors import DomainError
from app.routers import calls, companies, managers, meetings

logger = logging.getLogger("crm")


def error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    """The single error body format used by every endpoint."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # pydantic's own error objects may contain non-JSON values (exceptions in ctx),
        # so only the field path and the text are passed on.
        errors = [
            {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return error_response(422, "validation_error", "Некорректные данные запроса", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Unknown route (404), wrong method (405) and similar framework-level errors.
        if exc.status_code == 404:
            return error_response(404, "not_found", "Ресурс не найден")
        if exc.status_code == 405:
            return error_response(405, "method_not_allowed", "Метод не поддерживается для этого пути")
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(sqlite3.IntegrityError)
    async def handle_integrity_error(request: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
        # Second line of defence: every rule is checked in the services first.
        # Reaching this means a constraint caught something the services missed.
        logger.warning("Integrity error on %s %s: %s", request.method, request.url.path, exc)
        return error_response(409, "constraint_violation", "Операция нарушает ограничения данных")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # The stack trace goes to the log, never to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "Внутренняя ошибка сервера")


def create_app(db_path: str | None = None) -> FastAPI:
    path = db_path or database_path()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        apply_migrations(path)
        yield

    app = FastAPI(title="WhiteList CRM", lifespan=lifespan)
    app.state.db_path = path
    register_error_handlers(app)
    app.include_router(companies.router)
    app.include_router(managers.router)
    app.include_router(meetings.router)
    app.include_router(calls.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
