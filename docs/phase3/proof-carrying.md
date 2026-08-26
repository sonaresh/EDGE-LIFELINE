# Phase 3 proof-carrying authority and verification specification

## Status and scientific boundary

This candidate implements a machine-verifiable authorization artifact, not a renamed
log record. A proof consists of signed claims plus the complete hash-linked parent
authority chain, locally supplied evidence bytes, current verification context, and
durable admission state. Verification establishes that the configured issuer
authorized the encoded bounded decision under the supplied inputs. It does not prove
that a sensor is truthful, a policy is clinically correct, or an effect adapter
faithfully executes the admitted action.

“Proof-Carrying” would be scientifically misleading if any of these were true:

- a decision could execute using only a log entry or unsigned JSON;
- noncanonical encodings, mutable unprotected headers, unknown keys, or invalid
  signatures were accepted;
- a parent reference were trusted without verifying the complete chain;
- an edge signing key could self-assert root authority;
- a validly signed child could widen any authority dimension;
- replay and accounting state disappeared on process restart;
- proof commit and effect registration were separate transactions;
- the effect adapter could dispatch before the certificate transaction committed; or
- cryptographic tests were presented as proof of the TLA+ model, or vice versa.

The implementation and negative tests directly guard these conditions. Deployment
claims remain pending independent Phase 3 evidence review.

## Normative artifact profile

| Property | Phase 3 rule |
|---|---|
| Serialization | Deterministic/canonical CBOR; decoder re-encodes and requires byte equality |
| Container | Tagged `COSE_Sign1`, CBOR tag 18 |
| Algorithm | EdDSA COSE algorithm `-8`, implemented with Ed25519 |
| Protected headers | Exactly `alg` (1) and `kid` (4) |
| Unprotected headers | Forbidden |
| External AAD | Empty byte string |
| Parent reference | Lowercase SHA-256 of the complete encoded parent artifact |
| Root | Parentless `AUTHORITY_LEASE` signed by an explicitly configured root anchor |
| Replay key | Durable unique `(replay_domain, nonce)` |
| Evidence | Exact identifier set and SHA-256 of each supplied evidence byte string |
| Event linkage | Signed `previous_event_hash`, checked against the local ledger head |

The signed claim includes every Phase 0 field: lease and parent identifiers; issuer
and edge identity; actions, resources, sites and isolation epoch; issue, activation,
expiry and uncertainty bounds; freshness and confidence requirements; energy/resource
budgets; impact and financial ceilings; approval and security requirements; policy
version/hash; MVSG and verifier-profile hashes; evidence hashes; decision and
justification trace; nonce/replay domain; previous-event hash; and a hash of the
complete decision context.

## Verification order

The verifier fails closed in this order:

1. Require unique canonical CBOR and the strict COSE profile.
2. Resolve `kid`, verify Ed25519, and enforce issuer/key and artifact-type permission.
3. Follow every parent hash and terminate only at an explicit root trust anchor.
4. Compare each envelope against every ancestor using the structural authority partial
   order; equality-bound epoch/policy/MVSG/profile fields cannot drift.
5. Require conservative uncertain time (`lower >= activation`, `upper < expiration`)
   and a validity interval no longer than the signed maximum horizon.
6. Validate edge, epoch, action, resource, freshness, identity/revocation age, sensor
   confidence, approval, security posture, requested physical impact, requested
   financial exposure, policy, MVSG, and verifier profile.
7. Match previous-event hash, context hash, evidence set, and every evidence byte hash.
8. Return a `VerifiedProof`, distinct from a merely authenticated artifact.

Reconnection is not a verification shortcut and does not mint or widen a lease.

## Durable proof-before-effect transaction

SQLite runs in WAL mode with foreign keys enabled. Authority activation is one-shot.
For each decision, `BEGIN IMMEDIATE` serializes admission while the store checks the
exact activated parent, context binding, commit-time uncertain time, per-decision
limits, cumulative lease resource budgets, physical-impact class, and cumulative
financial exposure. It then records nonce, accounting update, certificate, and pending
effect in one transaction. A separate dispatch transition is allowed only for that
uniquely committed certificate/effect pair.

This provides crash/restart persistence on the same storage volume and prevents two
concurrent admissions from oversubscribing a lease. It does not provide Byzantine
storage, hardware rollback protection, or multi-node serializability.

## Emergency capability

Emergency authority is an explicit `EMERGENCY_CAPABILITY`, never an implicit increase.
It must be signed by a key configured for that artifact type, name the explicit
emergency authorization decision, remain no more authoritative than every ancestor,
and consume delegation depth. A zero-depth emergency capability may authorize a
bounded decision but cannot issue another lease.

## Test and evidence requirements

Phase 3 can pass independent review only when:

- the accepted Phase 2 record authorizes this phase;
- frozen dependencies, lint, formatting, strict typing, all tests, and branch-aware
  coverage at or above 90% pass locally and in CI;
- deterministic root/child/decision vectors regenerate byte-for-byte;
- modification, forgery, algorithm/header confusion, malformed CBOR, missing chain,
  untrusted root, every-dimensional widening, stale context, replay, budget/exposure
  oversubscription, expiry, atomic rollback, and proof-before-effect tests reject;
- provenance, source manifest, test logs, coverage, SBOM, dependency audit, raw
  benchmark samples, vectors, and evidence manifest are present and internally valid;
- local and CI archives identify the same source commit; and
- an independent reviewer records a pass. The automated gate remains conditional.

Expected files under `evidence/phase3/generated/<timestamp>/` are:

- `phase3-gate.log`
- `pytest-junit.xml`, `security-tests-junit.xml`, and `coverage.xml`
- `proof-chain-v1.json` and `proof-chain-v1.regenerated.json`
- `proof-benchmark.json`
- `phase2-external-acceptance.json`
- `source-manifest.json`, `provenance.json`, `sbom.cdx.json`, and
  `dependency-audit.json`
- `gate-decision.json` and `evidence-manifest.json`

## Known limitations and next phases

| Limitation | Consequence | Mitigation or later phase |
|---|---|---|
| Software-managed keys | Host compromise may expose signing keys | Hardware-backed key experiments in Phase 7/8 |
| SQLite on one volume | No Byzantine or cross-node transaction guarantee | Keep one authoritative admission store per edge; evaluate storage faults |
| SHA-256 evidence references | Hash proves byte identity, not truth or provenance quality | Signed attestations and provenance policies in Phase 5 |
| In-process issuer/verifier core | HTTP/mTLS boundary is not evaluated here | Service deployment and network isolation in Phase 7 |
| Synthetic policy and case study | No clinical safety or efficacy claim | Maintain nonclinical label; expert/clinical validation is outside scope |
| Performance samples are host-specific | No general latency claim | Repeated seeded experiments and confidence intervals in Phase 8 |
| No MVSG optimizer yet | Mission-minimal graph is not selected | Phase 4 |
| No causal reconciliation engine yet | Recovery artifacts are not implemented | Phase 6 |
