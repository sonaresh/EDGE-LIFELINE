# Changelog

## 0.1.1 - 2026-08-25

- Install container runtime dependencies from the frozen `uv.lock`.
- Use a single shared image build for the cloud and three edge services.
- Bind container build metadata to the complete source-manifest hash.
- Make readiness fail closed before application lifespan initialization.
- Guarantee best-effort Compose cleanup when startup or smoke checks fail.
- Correct prerequisite detection for missing commands and failed native tools.
- Hash the complete source tree and reject manifest path escapes and symbolic links.
- Capture rendered Compose configuration, health results, service/image inventories, and base-image metadata.
- Run the full Phase 1 gate in CI and preserve its evidence archive.
- Keep automated decisions conditional pending independent Compose and CI evidence review.

## 0.1.0 - 2026-08-25

- Initial Phase 1 reproducibility foundation.
