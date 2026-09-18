# Phase 8 acceptance map

| Claim | Evidence |
|---|---|
| Frozen final protocol | `protocol.json`, protocol/executable-registry security test |
| Complete paired factorial | `raw-results.csv`, `run-manifest.json` |
| Identical traces across methods | 200 trace hashes and pairing tests |
| Independent safety oracle | `oracle.json` and oracle byte-equivalence test |
| H1-H3, H5-H9 estimates | `analysis.json` |
| H4 host measurement | `performance.json` |
| No outcome exclusion | `exclusions.json` |
| Exact reproduction | independent first/second run hashes and frozen digest |
| Source and environment binding | source manifest and provenance |
| Supply-chain inventory | CycloneDX SBOM and dependency audit |
| Scientific boundary | `limitations.md` |

The gate result is conditional. External review must match local and CI manifests, source hashes,
raw results, analysis, protocol, oracle, benchmark interpretation, and acceptance linkage.
