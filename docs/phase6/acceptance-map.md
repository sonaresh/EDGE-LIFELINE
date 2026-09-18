# Phase 6 acceptance map

| Requirement | Evidence |
|---|---|
| Canonical signed event schema | Unit tests and `event-archive-v1.json` |
| Gap, fork, parent, cycle, epoch and false-class rejection | Phase 6 security-negative JUnit |
| S0–S4 class-specific behavior | Reconciliation unit and integration tests |
| Invalid subtree quarantine | DAG and end-to-end tests plus negative vector |
| No irreversible-effect replay | Store, engine, and security tests |
| No reconnect authority grant | Plan/receipt invariants and recovery vector |
| Signed receipt and witnessed checkpoint | Recovery round-trip tests and frozen vector |
| Deterministic outputs | Byte-for-byte vector regeneration |

The automated gate reports `CONDITIONAL_PASS`. Independent review of matching local and CI
evidence is required before Phase 6 completes or Phase 7 is authorized.
