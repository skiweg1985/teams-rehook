from __future__ import annotations

from fastapi import FastAPI, Request, Response

from app.core.config import get_settings
from app.core.settings_overrides import get_effective_settings
from app.routers import admin, auth, bot_messages, monitoring, public, teams_targets, webhook_routes
from app.seed import init_db
from app.services.event_log import log_api_request


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_session_secret()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    )
    if not settings.cors_origin_list:
        raise RuntimeError("CORS_ORIGINS must list at least one origin when using credential cookies")

    @app.middleware("http")
    async def event_log_middleware(request, call_next):
        return await log_api_request(request, call_next)

    @app.middleware("http")
    async def dynamic_cors_middleware(request: Request, call_next):
        effective_settings = get_effective_settings()
        allowed_origins = set(effective_settings.cors_origin_list)
        origin = request.headers.get("origin", "")
        requested_method = request.headers.get("access-control-request-method", "")
        requested_headers = request.headers.get("access-control-request-headers", "")

        if request.method == "OPTIONS" and origin in allowed_origins and requested_method:
            response = Response(status_code=204)
        else:
            response = await call_next(request)

        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = requested_method or "GET,POST,PUT,PATCH,DELETE,OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                requested_headers or "Authorization,Content-Type,X-CSRF-Token"
            )
            response.headers["Vary"] = "Origin"

        return response

    @app.on_event("startup")
    def startup():
        init_db()

    app.include_router(public.router, prefix=settings.api_v1_prefix)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(bot_messages.router, prefix=settings.api_v1_prefix)
    app.include_router(webhook_routes.router, prefix=settings.api_v1_prefix)
    app.include_router(teams_targets.router, prefix=settings.api_v1_prefix)
    app.include_router(admin.router, prefix=settings.api_v1_prefix)
    app.include_router(monitoring.router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
