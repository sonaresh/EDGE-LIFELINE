from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient, Response

from edge_lifeline.foundation.app import create_app
from edge_lifeline.foundation.config import NodeRole, Settings


@pytest.mark.integration
def test_foundation_endpoints() -> None:
    app = create_app(Settings(node_id="edge-c", node_role=NodeRole.EDGE, build_revision="abc123"))

    async def requests() -> tuple[Response, Response, Response]:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return (
                    await client.get("/healthz"),
                    await client.get("/readyz"),
                    await client.get("/version"),
                )

    health, ready, version = asyncio.run(requests())
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "node_id": "edge-c", "node_role": "edge"}
    assert ready.json()["status"] == "ready"
    assert version.json()["revision"] == "abc123"


@pytest.mark.integration
def test_api_surface_is_intentionally_minimal() -> None:
    app = create_app(Settings())

    async def requests() -> tuple[Response, Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return (
                await client.get("/docs"),
                await client.get("/openapi.json"),
                await client.post("/healthz"),
            )

    docs, schema, method = asyncio.run(requests())
    assert docs.status_code == 404
    assert schema.status_code == 404
    assert method.status_code == 405


@pytest.mark.integration
def test_readiness_fails_before_lifespan_initialization() -> None:
    app = create_app(Settings())

    async def request() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/readyz")

    response = asyncio.run(request())
    assert response.status_code == 503
