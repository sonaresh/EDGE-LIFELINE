from __future__ import annotations

import pytest
from pydantic import ValidationError

from edge_lifeline.foundation.config import NodeRole, Settings


def test_default_settings_are_safe_for_local_development() -> None:
    settings = Settings()
    assert settings.node_id == "edge-a"
    assert settings.node_role is NodeRole.EDGE
    assert settings.environment == "development"


@pytest.mark.parametrize("node_id", ["EDGE-A", "../cloud", "a_b", "", "a" * 33])
def test_invalid_node_ids_are_rejected(node_id: str) -> None:
    with pytest.raises(ValidationError):
        Settings(node_id=node_id)


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(node_role="administrator")  # type: ignore[arg-type]


def test_control_characters_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(build_revision="main\nforged")
