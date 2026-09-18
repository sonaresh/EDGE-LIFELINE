# Changelog

## 0.8.0 - 2026-09-18

- Add a frozen paired-factorial experiment across eight methods, E1-E20, and ten seeds.
- Add an independent declarative action oracle and exact trace pairing across methods.
- Add preregistered H1-H3 and H5-H9 comparisons with deterministic bootstrap intervals,
  paired sign-flip tests, Holm correction, and explicit non-increasing-invariant guards.
- Add host-specific H4 proof-verification and consequential-admission proxy measurements.
- Preserve all outcomes with no outcome-based exclusions and make hypothesis favorability
  independent of gate success.
- Add deterministic double execution, frozen digests, scientific-integrity tests, and a Phase 8
  evidence gate while keeping Phase 9 packaging locked.

## 0.7.0 - 2026-09-18

- Add a pinned four-cluster k3d/K3s research topology with one cloud and three edge clusters.
- Add restricted non-root workloads, disabled service-account token mounting, resource limits,
  read-only filesystems, dropped capabilities, and default-deny network policy.
- Add conservative orchestration-state decisions that cannot grant authority on reconnection.
- Add deterministic pod-replacement and edge-cluster restart faults with mandatory cleanup.
- Add frozen runtime vectors, static topology validation, security-negative tests, and the Phase 7 gate.
- Preserve the no-AWS and synthetic mechanism-only boundary; keep Phase 8 experiments locked.

## 0.6.0 - 2026-08-27

- Add canonical COSE/Ed25519 causal events with proof, lease, epoch, parent, vector-clock,
  idempotency, pre/postcondition, payload, and safety-class bindings.
- Add deterministic DAG validation for missing parents, gaps, forks, causal cycles, epoch
  mismatches, invalid proofs, false safety classes, and quarantined descendants.
- Add append-only SQLite event, irreversible-effect, quarantine, checkpoint, and receipt storage.
- Implement S0–S4 class-specific reconciliation; S5 inputs are quarantined before state mutation.
- Require compensation as a new event, human review for concurrent authoritative conflicts, and
  exactly-once preservation without re-dispatch for irreversible effects.
- Add signed reconciliation receipts and witnessed checkpoints that cannot restore authority and
  always require a fresh connected-epoch lease.
- Add deterministic event/recovery vectors, security-negative tests, and the Phase 6 evidence gate.

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
