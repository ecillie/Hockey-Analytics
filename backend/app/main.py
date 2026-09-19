"""ASGI entry point for the TradeValue backend."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.api.service import ApiProblem
from app.config import get_api_settings


logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


def create_app() -> FastAPI:
    settings = get_api_settings()
    application = FastAPI(title="TradeValue API", version="1.0.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )

    @application.exception_handler(ApiProblem)
    async def api_problem_handler(_request: Request, exc: ApiProblem):
        return _error(exc.status, exc.code, exc.message, exc.details)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        details: dict[str, list[str]] = {}
        for issue in exc.errors():
            field = str(issue["loc"][-1])
            details.setdefault(field, []).append(issue["msg"])
        return _error(400, "INVALID_REQUEST", "The request parameters are invalid.", details)

    @application.exception_handler(SQLAlchemyError)
    async def database_handler(_request: Request, exc: SQLAlchemyError):
        logger.exception("Database request failed", exc_info=exc)
        return _error(503, "DATABASE_UNAVAILABLE", "The data service is temporarily unavailable.")

    @application.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled API error", exc_info=exc)
        return _error(500, "INTERNAL_ERROR", "The API could not complete this request.")

    application.include_router(router)

    def contract_schema():
        if application.openapi_schema is None:
            schema = get_openapi(
                title=application.title,
                version=application.version,
                routes=application.routes,
            )
            # RequestValidationError is translated to the shared 400 envelope,
            # so FastAPI's default 422 documentation would be incorrect.
            for path in schema["paths"].values():
                for operation in path.values():
                    if isinstance(operation, dict):
                        operation.get("responses", {}).pop("422", None)
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = contract_schema
    return application


app = create_app()
