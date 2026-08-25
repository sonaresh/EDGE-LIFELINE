from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from edge_lifeline import __version__
from edge_lifeline.foundation.config import Settings, get_settings


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    node_id: str
    node_role: str


class VersionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    service: str
    version: str
    revision: str
    built_at: str
    python: str


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved
        app.state.ready = True
        yield
        app.state.ready = False

    app = FastAPI(
        title="EDGE-LIFELINE Foundation Service",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get("/healthz", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", node_id=resolved.node_id, node_role=resolved.node_role)

    @app.get("/readyz", response_model=HealthResponse)
    async def readiness(request: Request) -> HealthResponse:
        if not getattr(request.app.state, "ready", False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="service initialization is incomplete",
            )
        return HealthResponse(
            status="ready", node_id=resolved.node_id, node_role=resolved.node_role
        )

    @app.get("/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        import platform

        return VersionResponse(
            service="edge-lifeline-foundation",
            version=__version__,
            revision=resolved.build_revision,
            built_at=resolved.build_timestamp,
            python=platform.python_version(),
        )

    return app


app = create_app()
