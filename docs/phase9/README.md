# Phase 9: research-release closure

Phase 9 converts the externally accepted Phase 8 record into deterministic publication and
reproducibility artifacts. It does not rerun the experiment or change its analysis.

The package contains accepted results, a manuscript table, an SVG comparison figure,
reproducibility instructions, a claim-evidence matrix, release metadata, checksums, and an
artifact manifest. Every result remains bound to the accepted source, protocol, oracle, raw-data,
and analysis hashes.

Run `scripts/run_phase9_gate.ps1` after committing. Automated success remains conditional until
the Windows and GitHub evidence archives are independently compared.
