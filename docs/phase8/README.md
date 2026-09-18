# Phase 8: preregistered synthetic evaluation

Phase 8 executes the final synthetic research experiment for EDGE-LIFELINE. The frozen protocol
crosses eight methods (B0-B6 and EL), twenty failure scenarios (E1-E20), and ten independent
seeds. Every method in a scenario/seed block receives the exact same 64-event trace.

The final run therefore contains 1,600 cells and 200 unique paired traces. The executable
analysis registry must exactly match `experiments/phase8/protocol.json`. The independent oracle
classifies ground-truth safe and authorized actions without calling the treatment implementation.

Primary estimates use deterministic paired bootstrap intervals, paired sign-flip permutation
tests, and Holm multiplicity correction. H4 is a separate host-specific engineering benchmark.
The gate checks completeness, preregistration integrity, exact reproduction, tests, provenance,
SBOM, and dependency audit. It never requires a favorable hypothesis result.

Run:

```powershell
.\scripts\run_phase8_gate.ps1
```

Successful automated evidence remains `CONDITIONAL_PASS` by design. Independent local-versus-CI
review recorded Phase 8 `PASS` at source commit
`c376cb5bd6fee1c63805c416b9b17f22cfa48066` and authorized Phase 9 packaging.
