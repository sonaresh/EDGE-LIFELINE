from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.mark.security
def test_compose_services_use_local_ports_and_restricted_containers() -> None:
    document = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    services = document["services"]
    assert set(services) == {"cloud", "edge-a", "edge-b", "edge-c"}
    for service in services.values():
        assert service["user"] == "10001:10001"
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        for binding in service["ports"]:
            assert binding.startswith("127.0.0.1:")


@pytest.mark.security
def test_only_cloud_service_builds_the_shared_image() -> None:
    document = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    assert "build" in document["services"]["cloud"]
    assert all("build" not in document["services"][edge] for edge in ("edge-a", "edge-b", "edge-c"))


@pytest.mark.security
def test_container_install_uses_frozen_lock() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --no-editable" in dockerfile


@pytest.mark.security
def test_phase1_configuration_cannot_claim_authority_or_aws() -> None:
    document = yaml.safe_load(Path("config/phase1.yaml").read_text(encoding="utf-8"))
    assert document["scope"]["phase"] == 1
    assert document["scope"]["authority_logic_enabled"] is False
    assert document["scope"]["aws_enabled"] is False
