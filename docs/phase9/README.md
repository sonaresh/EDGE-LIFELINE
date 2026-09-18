# Phase 9: research-release closure

Phase 9 converts the externally accepted Phase 8 record into deterministic publication and
reproducibility artifacts. It does not rerun the experiment or change its analysis.

The package contains accepted results, a manuscript table, an SVG comparison figure,
reproducibility instructions, a claim-evidence matrix, release metadata, checksums, and an
artifact manifest. Every result remains bound to the accepted source, protocol, oracle, raw-data,
and analysis hashes.

Run `scripts/run_phase9_gate.ps1` after committing. Automated success remains conditional until
the Windows and GitHub evidence archives are independently compared.

That comparison is complete. Phase 9 received `PASS` at implementation commit
`d17ba0956d73cc301a4ded939293966843ea8af9`; external acceptance was recorded at commit
`0ca92e3a7d2bc870033d7eaeaff80ac3b13de354`, and the public release is tagged `v0.9.0`.

The accepted review verified 392 complete tests, 159 security tests, 238 matching source entries,
33 evidence entries per environment, byte-identical publication artifacts, 94.77% line coverage,
85.61% branch coverage, and zero known dependency vulnerabilities.
