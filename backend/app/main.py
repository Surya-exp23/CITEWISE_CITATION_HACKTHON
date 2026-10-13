"""CiteWise FastAPI app. All routers are mounted under /api (PRD 12)."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.routers import (
    citations,
    ingest,
    institutions,
    integrity,
    policies,
    reports,
    researchers,
    review,
    verify,
    waterfall,
)


def _error_payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def create_app() -> FastAPI:
    app = FastAPI(title="CiteWise", version="0.1.0",
                  description="Medical citation & research impact intelligence — auditable citation verification.")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Standard error shape: {"error": {"code", "message"}} (PRD 12).
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        code = {400: "bad_request", 404: "not_found", 422: "unprocessable"}.get(exc.status_code, "error")
        return JSONResponse(status_code=exc.status_code,
                            content=_error_payload(code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=_error_payload("validation_error", str(exc)))

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content=_error_payload("internal_error", str(exc)))

    @app.get("/health")
    def health():
        return {"status": "ok", "offline_mode": settings.OFFLINE_MODE,
                "llm_assist": settings.ENABLE_LLM_ASSIST}

    for router in (ingest, researchers, institutions, citations, waterfall,
                   policies, review, integrity, reports, verify):
        app.include_router(router.router, prefix="/api")

    return app


app = create_app()
