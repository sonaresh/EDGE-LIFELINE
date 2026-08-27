# Changelog

## 0.5.0 - 2026-08-27

- Add fail-safe cached pseudonymous identity evaluation with explicit assurance, role,
  cache-age, expiry, and last-authenticated revocation-snapshot bounds.
- Add authenticated UTC-anchor plus boot-aware elapsed-time intervals with drift, restart,
  suspend penalty, rollback/discontinuity detection, and protective read-only behavior.
- Add canonical semantic Rego/data/entrypoint/schema/OPA-version policy hashing.
- Pin OPA 1.19.1, verify the official binary SHA-256 before use, and restrict policy calls to
  loopback or absolute Unix-domain sockets.
- Add strict OPA response/hash/version checks, deterministic identity/time/policy fixtures,
  Rego tests, security-negative tests, and a reproducible Phase 5 evidence gate.
- Preserve the synthetic nonclinical boundary and keep causal reconciliation locked to Phase 6.

## 0.4.0 - 2026-08-27

- Implement deterministic OR-Tools CP-SAT Mission-Viable Service Graph selection.
- Enforce mandatory capability coverage, AND/OR dependencies, exclusions, locality,
  distinct-site redundancy, startup order, deadlines, freshness, and authority/resource budgets.
- Add a solver-independent validator that recomputes every hard constraint and objective.
- Add safe timeout behavior: validated incumbent, revalidated prior graph, or safe shutdown.
- Add a brute-force reference oracle, frozen graph/plan vector, property tests, and engineering
  benchmark with raw samples.
- Preserve the synthetic, nonclinical boundary and defer mission-outcome experiments to Phase 8.

## 0.3.0 - 2026-08-26

- Implement canonical CBOR and COSE_Sign1 Ed25519 authority artifacts.
- Add cloud issuance and strict edge verification for root, child, and decision certificates.
- Enforce parent-chain subsumption, bounded trusted time, evidence binding, and context binding.
- Add durable SQLite anti-replay, budget accounting, certificate commit, and effect registration.
- Add byte-level golden, mutation, replay, widening, stale-context, and atomicity tests.
- Require cryptography 50.0.1+ after the Phase 3 dependency audit identified advisories
  affecting the initial 46.0.7 candidate.

## 0.2.0 - 2026-08-26

- Implement the typed multidimensional authority lattice and structural meet/subsumption.
- Implement deterministic per-mille hazard contraction and explicit DAE bands.
- Implement bounded trusted-time intervals, rollback detection, and conservative lease checks.
- Implement isolation/reconnection transitions and a separate bounded emergency branch.
- Add runtime checks for monotonicity, parent/issuer ceilings, replay, proof-before-effect,
  evidence completeness, atomic accounting, and aggregate sibling budgets.
- Add a three-edge, two-epoch TLA+ model and six seeded weakened configurations that must
  produce counterexamples.
- Keep COSE, Ed25519, authority issuance, and proof-verifier services deferred to Phase 3.

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
