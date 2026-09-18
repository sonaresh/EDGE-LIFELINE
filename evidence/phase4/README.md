# Phase 4 evidence

Generated evidence is written under `generated/<UTC timestamp>/` and excluded from the source
manifest. A successful automated gate remains conditional until matching Windows and GitHub
Actions archives are independently reviewed.

The accepted review is recorded in `phase4-external-acceptance.json`. Generated reruns do not
replace that decision.

Expected files include full/security/timeout JUnit reports, coverage, oracle conformance, frozen
and regenerated MVSG vectors, raw optimizer/validator benchmark samples, the accepted Phase 3
record, provenance, source manifest, SBOM, dependency audit, gate decision, and evidence manifest.
