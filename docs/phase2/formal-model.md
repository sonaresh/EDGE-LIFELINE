# Phase 2 formal model and acceptance specification

## Status and scope

This candidate implements the Phase 0 authority and transition semantics in two
separate forms:

1. a typed executable Python model used for runtime/property tests; and
2. a finite TLA+ abstraction checked exhaustively by TLC.

The two forms share safety claims but are not asserted to be mechanically equivalent.
The mapping is explicit in `formal/runtime-invariant-map.json`. Phase 2 does not
implement COSE, CBOR, Ed25519, an issuer, a verifier service, or an effect adapter.

## Authority order and contraction

For envelopes `x` and `y`, `x <= y` means every permissive dimension of `x` is a
subset of or no greater than `y`, every required assurance of `x` is no weaker than
`y`, and equality-bound context fields match. This is a product partial order, not a
scalar score.

Within isolation epoch `e`, the executable recurrence is:

`A_e(t) = A_e(t-) meet parent meet lease meet C(h(t))`

`C` uses all twelve mandatory hazard dimensions, represented as integer per-mille
values. Missing mandatory evidence is mapped to hazard 1000 by the fail-safe builder.
Per-action risk uses the maximum weighted hazard, preventing a favorable dimension
from compensating for a hard adverse dimension. The structural meet with `A_e(t-)`
prevents re-expansion when evidence later improves.

## Invariant coverage

| ID | Safety claim | TLC | Runtime |
|---|---|---:|---:|
| I1 | Same-epoch authority never expands | Yes | Yes |
| I2 | Child authority never exceeds parent/ancestors | Yes | Yes |
| I3 | Enforcement-integrity failure fails safe | Abstracted by terminal transition | Yes |
| I4 | Expiration uses the conservative upper time bound | Yes | Yes |
| I5 | A nonce cannot cause a second consequential effect | Yes | Yes |
| I6 | Evidence/proof commit precedes effect dispatch | Yes | Yes |
| I7 | Cumulative impact and resource counters remain bounded | Budget portion | Yes |
| I8 | Evidence references are complete and valid | Boolean abstraction | Yes |
| I9 | Reconnection alone grants no authority | Yes | Yes |
| I10 | Reconnection does not automatically replay effects | Yes | Yes |
| I11 | Emergency authority is bounded by a separate ceiling | Yes | Yes |
| I12 | Invalid/compromised edge evidence is quarantined | Transition-level | State tests |
| I13 | Identical normalized inputs produce deterministic decisions | Action relation | Yes |
| I14 | Nonce, budget, evidence, and effect registration are atomic prerequisites | Abstracted | Yes |
| I15 | Consumed plus sibling reservations stay within the parent budget | Yes | Yes |
| I16 | Every descendant remains under the issuer/root ceiling | Yes | Yes |

“Abstracted” means the TLA+ model represents a Boolean protocol fact rather than the
underlying content or transaction implementation. It is not evidence that a future
cryptographic implementation is correct.

## Model bounds

The declared TLC configuration fixes three edges, two nonces, two isolation epochs,
authority and budget domains 0..2, nested delegation depth two, two sibling budget
reservations, bounded uncertain time, and one separate emergency capability branch.
These bounds are deliberately small enough for reproducible exhaustive search. They
do not prove an unbounded system.

## Seeded negative models

The positive configuration must complete without an invariant violation. Each
negative configuration weakens exactly one protection and must produce the named
counterexample:

| Configuration | Weakened protection | Expected invariant |
|---|---|---|
| `negative_parent.cfg` | parent check | `I2_ParentBounded` |
| `negative_time.cfg` | conservative upper time | `I4_ConservativeTime` |
| `negative_replay.cfg` | nonce memory | `I5_AntiReplay` |
| `negative_proof.cfg` | proof-before-effect guard | `I6_ProofBeforeEffect` |
| `negative_reconnect.cfg` | no reconnect grant | `I9_NoReconnectGrant` |
| `negative_auto_replay.cfg` | no automatic replay | `I10_NoAutomaticEffectReplay` |

A negative model is successful only when TLC exits nonzero and names the expected
invariant. An arbitrary model failure is not accepted as a counterexample.

## Phase 2 acceptance gate

Phase 2 passes independent review only if all of the following hold:

- runtime lint, formatting, strict typing, tests, branch coverage threshold, SBOM, and
  dependency audit pass;
- the positive TLC model completes without a counterexample;
- all six weakened models produce their expected counterexamples;
- local Windows and CI evidence manifests are internally valid;
- source manifests and Git commit identity agree across local and CI runs;
- raw TLC logs, structured summary, coverage, provenance, and dependency evidence are
  present; and
- an external review records the acceptance decision.

The automated gate must remain conditional. It cannot self-authorize Phase 3.

## Expected outputs

`evidence/phase2/generated/<timestamp>/` contains:

- `phase2-gate.log`
- `pytest-junit.xml` and `coverage.xml`
- `tlc/positive.log` and six negative logs
- `tlc-summary.json`
- `runtime-invariant-map.json`
- `provenance.json`
- `source-manifest.json`
- `sbom.cdx.json`
- `dependency-audit.json`
- `gate-decision.json`
- `evidence-manifest.json`

No experimental performance or safety outcome is pre-filled by this phase.

## Known limitations and mitigations

| Limitation | Consequence | Mitigation or later phase |
|---|---|---|
| Finite abstraction | Does not prove unbounded deployments | Publish bounds and add targeted larger configurations |
| Ideal cryptography | Does not validate proof-carrying artifacts | Phase 3 byte-level COSE/Ed25519 tests |
| Python/TLA semantic gap | Model and implementation may diverge | Maintain mapping plus shared invariant/property tests |
| Synthetic policy thresholds | No clinical validity | Label nonclinical and run sensitivity analysis later |
| In-memory nonce model | Restart persistence is not proven | Phase 3 durable atomic verifier state |
| Simplified energy/resource units | Not hardware-calibrated | Calibrate in Phases 7–8 |
| No MVSG optimizer yet | Mission graph feasibility is not evaluated | Phase 4 |
| No causal reconciliation engine yet | Recovery safety is only state-level | Phase 6 |

## Rollback

Generated evidence and the downloaded TLA+ JAR are disposable. The accepted Phase 1
source commit is `d3d065f5e2dfafa8a319a9ed319fbe5e4626d5e8`. Preserve Phase 2 on its own branch;
return to Phase 1 by switching branches rather than deleting or resetting user work.
