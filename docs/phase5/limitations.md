# Phase 5 limitations and deviations

- All fixtures are synthetic and nonclinical. No claim of patient safety, clinical efficacy,
  production readiness, or regulatory compliance is made.
- A disconnected edge knows only the last authenticated revocation snapshot. Revocations
  created after that snapshot are unknowable; the implementation bounds exposure by snapshot
  freshness and cache age instead of claiming current revocation status.
- The authenticated-time model is an executable abstraction. Production hardware-backed
  secure time, suspend accounting, reboot persistence, and re-anchoring protocols remain
  deployment-specific.
- OPA is restricted to loopback HTTP or an absolute Unix-domain socket. A production sidecar
  supervisor, mutual process identity, and operating-system confinement remain outside this
  prototype.
- Policy WASM is deferred. Phase 5 validates the pinned OPA/Rego sidecar profile only.
- Phase 5 does not implement causal ledgers, reconciliation, automatic merge, compensation, or
  causal recovery. Those capabilities belong to Phase 6 and remain locked.
- The official OPA checksum is retrieved over HTTPS from the OPA distribution endpoint and
  verified before execution. A future release process may additionally vendor the checksum in
  a signed, independently witnessed release manifest.
