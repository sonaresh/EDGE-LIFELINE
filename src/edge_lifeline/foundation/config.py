from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


class NodeRole(StrEnum):
    CLOUD = "cloud"
    EDGE = "edge"


class Settings(BaseSettings):
    """Non-secret Phase 1 process configuration."""

    model_config = SettingsConfigDict(
        env_prefix="EDGE_LIFELINE_",
        case_sensitive=False,
        extra="forbid",
    )

    node_id: str = Field(default="edge-a")
    node_role: NodeRole = Field(default=NodeRole.EDGE)
    environment: str = Field(default="development", pattern=r"^(development|test|research)$")
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    build_revision: str = Field(default="unversioned", max_length=80)
    build_timestamp: str = Field(default="unknown", max_length=64)

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, value: str) -> str:
        if not NODE_ID_PATTERN.fullmatch(value):
            raise ValueError("node_id must be a lowercase DNS-style identifier up to 32 characters")
        return value

    @field_validator("build_revision", "build_timestamp")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("build metadata cannot contain control characters")
        return value


def get_settings() -> Settings:
    return Settings()
