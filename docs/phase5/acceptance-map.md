# Phase 5 acceptance and test map

| Acceptance ID | Requirement | Principal tests/evidence |
|---|---|---|
| P5-ID-01 | Cached identity is bounded by age, assurance, role, expiry, and issuer/snapshot binding. | `tests/unit/identity/test_cache.py`, `identity-fixtures-v1.json` |
| P5-ID-02 | Offline revocation claims stop at the last authenticated snapshot and exposure is freshness-bounded. | `tests/security/phase5/test_offline_boundaries.py`, `identity-fixtures-v1.json` |
| P5-TIME-01 | Authenticated UTC anchor plus boot-aware elapsed time and drift produce a conservative interval. | `tests/unit/time/test_estimator.py`, `time-traces-v1.json` |
| P5-TIME-02 | Rollback, discontinuity, or unretained reboot causes protective read-only; wall clock cannot reactivate. | `tests/security/phase5/test_offline_boundaries.py`, `time-traces-v1.json` |
| P5-POL-01 | Semantic policy hash covers normalized Rego/data, entrypoints, schema, policy version, and exact OPA version. | `tests/unit/policy/test_bundle.py`, `policy-manifest-v1.json` |
| P5-POL-02 | OPA is local-only and outage, malformed response, deny, hash mismatch, or version mismatch fails safe. | `tests/security/policy/test_policy_client.py` |
| P5-POL-03 | Rego requires identity, time, action, resource, policy hash, and policy version simultaneously. | `policy/rego/edge_lifeline_test.rego`, `opa-tests.json` |
| P5-INT-01 | Admission composes time, identity, and policy without bypass; earlier failure short-circuits later evaluation. | `tests/integration/test_phase5_admission.py` |
| P5-REP-01 | Frozen fixtures regenerate byte-for-byte and local/CI evidence is manifest-bound to one commit. | `tests/security/phase5/test_frozen_fixtures.py`, source/evidence manifests, provenance |

Automated results remain conditional. Only external comparison of local Windows and GitHub
Actions evidence from the same commit can set `phase5_complete` and authorize Phase 6.
