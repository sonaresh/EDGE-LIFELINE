# Phase 7: research orchestration

Phase 7 creates four local k3d/K3s clusters: one cloud and three registered edges. It validates
repeatable creation, restricted workload deployment, observation, deterministic pod and cluster
faults, recovery, and cleanup. Kubernetes health is evidence only and never grants authority.

The authoritative entry point is `scripts/run_phase7_gate.ps1`. It requires PowerShell 7.4+,
Docker, kubectl, and enough local resources for four single-server clusters. The checksum-pinned
k3d 5.9.0 binary is installed into the ignored `.tools` directory.

This phase provisions no AWS resource and makes no production, clinical, availability, latency,
or comparative outcome claim.
