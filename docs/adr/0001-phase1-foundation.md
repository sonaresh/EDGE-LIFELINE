# ADR 0001: Phase 1 local-first foundation

## Status

Accepted for Phase 1.

## Decision

Use Python 3.12, FastAPI, `uv`, Docker Compose, Pytest, Ruff, Mypy, CycloneDX, and GitHub Actions. One image is configured as one cloud node and three edge nodes. Ports bind to loopback and containers run with a reduced privilege profile.

## Rationale

This is the smallest useful foundation that validates packaging, service identity, reproducible dependency resolution, CI, evidence generation, and cleanup without prematurely implementing Phase 2 or later mechanisms.

## Consequences

- Docker Desktop with WSL2 is required for the complete local gate.
- Kubernetes, PostgreSQL, OPA, cryptography, formal tools, observability, and fault injection remain deferred to their approved phases.
- The Python base-image tag is exact and the Docker build installs runtime packages from `uv.lock`. The immutable pulled digest is environment/architecture dependent and is captured by the Compose gate.
- A local gate cannot self-certify final completion. CI and Compose evidence require independent review before Phase 1 receives a final pass.
