# Causal recovery specification

Every event binds its edge and isolation epoch, local sequence, previous event, causal parents,
vector clock, verified lease and decision-certificate hashes, registered safety class, schema,
idempotency key, precondition, postcondition, payload, and optional effect or compensation type.
The canonical payload is signed as COSE_Sign1 with Ed25519.

Import proceeds fail-safely: verify bytes and signer, bind proof and lease references, enforce the
epoch and registered class, then validate parents, sequence, vector clocks, gaps, forks, and cycles.
An invalid parent quarantines its imported descendant subtree. Quarantined events never mutate the
authoritative ledger.

Rules are class-specific:

- S0 observations preserve provenance through a registered reducer.
- S1 commutative events may auto-merge through their registered reducer.
- S2 conflicts produce a new compensation proposal; accepted history is never rewritten.
- S3 concurrent authoritative conflicts require human review.
- S4 effects are recorded exactly once and never dispatched by reconciliation.
- S5 invalid or malicious inputs and descendants are quarantined.

The result is a deterministic plan, signed receipt, and witnessed checkpoint. None of these grants
authority. A fresh connected-epoch lease is mandatory after reconciliation.
