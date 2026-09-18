# Phase 6: causal ledger and safe reconciliation

Phase 6 implements signed causal events, deterministic DAG validation, append-only persistence,
safety-class reconciliation, subtree quarantine, witnessed checkpoints, and signed receipts.

Authenticated reconnection enters reconciliation pending. It never restores authority. Every
accepted receipt requires a fresh connected-epoch lease before connected authority can be granted.

See `causal-recovery.md`, `limitations.md`, and `acceptance-map.md` for the normative boundary.

Independent review recorded Phase 6 `PASS` at source commit
`4abad6c4f4886e023d05f91d30e6d2b71c62ac64`.
