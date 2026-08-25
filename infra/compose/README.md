# Phase 1 Compose topology

This topology starts one cloud foundation service and three independent edge foundation services. It validates packaging, configuration isolation, health checks, and reproducible local orchestration only. It contains no authority issuer, proof verifier, policy engine, patient data, fault injector, or experimental result.

Published ports bind to `127.0.0.1`:

| Node | Port |
|---|---:|
| cloud | 18080 |
| edge-a | 18081 |
| edge-b | 18082 |
| edge-c | 18083 |

