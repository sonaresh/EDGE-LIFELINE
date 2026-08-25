from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from edge_lifeline.foundation.app import create_app
from edge_lifeline.foundation.config import Settings


@pytest.mark.security
def test_version_endpoint_does_not_expose_environment_or_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDGE_LIFELINE_TEST_SECRET", "must-not-leak")
    app = create_app(Settings())

    async def request() -> dict[str, str]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/version")
            return response.json()  # type: ignore[no-any-return]

    payload = asyncio.run(request())
    serialized = str(payload)
    assert "must-not-leak" not in serialized
    assert set(payload) == {"service", "version", "revision", "built_at", "python"}
