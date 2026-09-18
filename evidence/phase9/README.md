# Phase 9 evidence

Generated evidence is ignored under `generated/`. The Phase 9 gate preserves two independently
generated publication packages, tests, coverage, source provenance, SBOM, dependency audit, and
a conditional decision. Public release requires external local-versus-CI review.

The review is complete. `phase9-external-acceptance.json` records `PASS`, authorizes public release
v0.9.0, and binds the validated source and both evidence archive hashes. Automated reruns remain
conditional and cannot overwrite the external decision.
