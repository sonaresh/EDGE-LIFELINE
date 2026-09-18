# Phase 8 evidence

Generated evidence is intentionally ignored under `generated/`. A successful gate records the
complete experiment, independent reproduction, H4 measurement, tests, source manifest,
provenance, SBOM, dependency audit, limitations, acceptance map, and a conditional gate decision.

Do not commit generated evidence. Commit only a separately reviewed external acceptance record.
The accepted Phase 8 record is `phase8-external-acceptance.json`; it binds the final protocol,
oracle, raw results, analysis, source, and both reviewed evidence archives.
