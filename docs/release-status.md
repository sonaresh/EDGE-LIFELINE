# Release and phase status

EDGE-LIFELINE v0.9.0 is the independently accepted final research release. All planned phases
are complete. Each automated gate remains conditional by design; completion was recorded only
after independent comparison of local Windows and GitHub Actions evidence.

| Phase | Scope | Final status | Accepted source commit |
|---:|---|---|---|
| 0 | Design and scientific boundary | Approved | Design specification v1.1 |
| 1 | Reproducible local foundation | PASS | `d3d065f5e2dfafa8a319a9ed319fbe5e4626d5e8` |
| 2 | Executable and TLA+ safety model | PASS | `53b3065ac6a32ff09d9e286652661f8f4ee6986a` |
| 3 | Proof-carrying authorization | PASS | `965e5aa7dd47ba293b3e25ac6ad388c8e2c51275` |
| 4 | Mission-Viable Service Graph | PASS | `6fb314effdc5e45145593bbdd582e19f60914d5f` |
| 5 | Identity, bounded time, and policy | PASS | `150bf42abd864cb793a2c1de5eb8110b36034162` |
| 6 | Causal ledger and safe reconciliation | PASS | `4abad6c4f4886e023d05f91d30e6d2b71c62ac64` |
| 7 | Local multi-cluster orchestration | PASS | `e04bbf5098463927228f6bb9920f776e6bee85b1` |
| 8 | Preregistered synthetic evaluation | PASS | `c376cb5bd6fee1c63805c416b9b17f22cfa48066` |
| 9 | Deterministic research-release packaging | PASS | `d17ba0956d73cc301a4ded939293966843ea8af9` |

The final external acceptance is recorded at
`evidence/phase9/phase9-external-acceptance.json` and commit
`0ca92e3a7d2bc870033d7eaeaff80ac3b13de354`. The public release tag is `v0.9.0`.

## Final validation summary

- 392 complete tests and 159 security tests passed in both environments.
- Local and CI source manifests matched across all 238 entries.
- All 33 evidence-manifest entries verified per environment.
- Publication outputs reproduced byte-for-byte across two runs and both operating systems.
- Line coverage was 94.77%; branch coverage was 85.61%.
- Both CycloneDX 1.6 SBOMs contained 93 components and the audits found no known vulnerabilities.
- Windows included `colorama==0.4.6`; Linux included `uvloop==0.22.1`, an expected platform-marker difference.
- No experiment was rerun in Phase 9 and no outcome-based exclusion was introduced.

## Scientific boundary

The release validates reproducible synthetic cloud-edge resilience experiments, formal and
executable safety controls, deterministic recovery, and publication packaging. It does not
establish clinical efficacy, patient safety, production reliability, hardware-root assurance,
sensor truth, or prevention under full-TCB compromise.
