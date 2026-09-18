# Phase 7 acceptance map

| Requirement | Evidence |
|---|---|
| One cloud plus three edge clusters | `cluster-inventory.json` |
| Pinned k3d and K3s | `k3d-version.txt`, `topology-validation.json` |
| Restricted workloads and default-deny networking | manifests and security tests |
| All workloads observable and Ready | per-cluster inventory YAML |
| Deterministic pod replacement | `fault-results.json`, `F7-POD-RESTART` |
| Deterministic edge stop/restart | `fault-results.json`, `F7-EDGE-RESTART` |
| Reconnect does not grant authority | frozen runtime vector and negative tests |
| Cleanup removes all created clusters | `cleanup.json` |
| Reproducible source and evidence | manifests, provenance, CI artifact |

The required Windows/CI comparison was completed and recorded in
`evidence/phase7/phase7-external-acceptance.json`, authorizing the now-completed Phase 8 work.
