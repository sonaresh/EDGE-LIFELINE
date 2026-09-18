from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXCLUDED_SOURCE_PARTS = {
    ".coverage",
    ".DS_Store",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    ".uv-cache",
    ".venv",
    ".hypothesis",
    "__pycache__",
    "build",
    "dist",
}
EXCLUDED_SOURCE_PREFIXES = (
    "evidence/phase1/generated/",
    "evidence/phase2/generated/",
    "evidence/phase3/generated/",
    "evidence/phase4/generated/",
    "evidence/phase5/generated/",
    "evidence/phase6/generated/",
    "evidence/phase7/generated/",
    "evidence/phase8/generated/",
    "results/raw/",
    "results/processed/",
)
EXCLUDED_SOURCE_SUFFIXES = {".zip"}


def _command(args: list[str], cwd: Path) -> dict[str, Any]:
    try:
        # Callers provide fixed executable/argument lists; no shell is invoked.
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)  # noqa: S603
    except FileNotFoundError:
        return {"available": False, "command": args, "returncode": None, "output": None}
    output = (result.stdout or result.stderr).strip()
    return {
        "available": True,
        "command": args,
        "returncode": result.returncode,
        "output": output,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, relative_paths: list[str]) -> dict[str, str]:
    resolved_root = root.resolve()
    manifest: dict[str, str] = {}
    for relative in sorted(relative_paths):
        candidate = resolved_root / relative
        if candidate.is_symlink():
            raise ValueError(f"manifest inputs cannot be symbolic links: {relative}")
        target = candidate.resolve()
        try:
            normalized = target.relative_to(resolved_root).as_posix()
        except ValueError as error:
            raise ValueError(f"manifest input escapes the declared root: {relative}") from error
        if not target.is_file():
            raise FileNotFoundError(f"required manifest input is missing: {relative}")
        manifest[normalized] = sha256_file(target)
    return manifest


def discover_source_files(root: Path) -> list[str]:
    resolved_root = root.resolve()
    discovered: list[str] = []
    for target in sorted(resolved_root.rglob("*")):
        relative = target.relative_to(resolved_root).as_posix()
        if any(part in EXCLUDED_SOURCE_PARTS for part in target.relative_to(resolved_root).parts):
            continue
        if any(relative.startswith(prefix) for prefix in EXCLUDED_SOURCE_PREFIXES):
            continue
        if target.suffix.lower() in EXCLUDED_SOURCE_SUFFIXES:
            continue
        if target.is_symlink():
            raise ValueError(f"source tree cannot contain symbolic links: {relative}")
        if target.is_file():
            discovered.append(relative)
    if not discovered:
        raise ValueError("source tree contains no manifestable files")
    return discovered


def capture_environment(root: Path) -> dict[str, Any]:
    return {
        "schema_version": "edge-lifeline-provenance-v1",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "platform": platform.platform(),
        "machine": platform.machine(),
        "git": _command(["git", "rev-parse", "HEAD"], root),
        "git_status": _command(["git", "status", "--short"], root),
        "uv": _command(["uv", "--version"], root),
        "docker": _command(["docker", "version", "--format", "{{json .}}"], root),
        "compose": _command(["docker", "compose", "version"], root),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
