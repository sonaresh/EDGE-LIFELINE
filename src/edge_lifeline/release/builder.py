"""Build a deterministic publication package from externally accepted results."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def validate_release_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    acceptance = _load(root / "evidence/phase8/phase8-external-acceptance.json")
    results = _load(root / "publication/phase9/accepted-results.json")
    if acceptance.get("decision") != "PASS" or not acceptance.get("phase9_authorized"):
        raise ValueError("Phase 8 external acceptance does not authorize Phase 9")
    if results.get("accepted_source_commit") != acceptance.get("accepted_source_commit"):
        raise ValueError("accepted result commit does not match Phase 8 acceptance")
    for field in (
        "protocol_sha256",
        "oracle_sha256",
        "raw_results_sha256",
        "analysis_sha256",
    ):
        if results.get(field) != acceptance.get(field):
            raise ValueError(f"accepted result linkage differs: {field}")
    comparisons = results.get("primary_comparisons")
    if not isinstance(comparisons, list) or len(comparisons) != 8:
        raise ValueError("exactly eight preregistered comparisons are required")
    if [item.get("hypothesis") for item in comparisons] != [
        "H1",
        "H2",
        "H3",
        "H5",
        "H6",
        "H7",
        "H8",
        "H9",
    ]:
        raise ValueError("preregistered hypothesis registry differs")
    if results.get("e9_full_tcb_profile", {}).get("prevention_claimed") is not False:
        raise ValueError("E9 full-TCB prevention must not be claimed")
    return acceptance, results


def _results_csv(results: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    fields = (
        "hypothesis",
        "baseline",
        "metric",
        "paired_blocks",
        "mean_favorable_difference",
        "ci_low",
        "ci_high",
        "holm_adjusted_p_value",
        "safety_guard_non_increasing",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in results["primary_comparisons"]:
        writer.writerow(
            {
                **{field: item[field] for field in fields[:5]},
                "ci_low": item["bootstrap_95_ci"][0],
                "ci_high": item["bootstrap_95_ci"][1],
                "holm_adjusted_p_value": item["holm_adjusted_p_value"],
                "safety_guard_non_increasing": item["safety_guard_non_increasing"],
            }
        )
    return output.getvalue().encode()


def _results_markdown(results: dict[str, Any]) -> bytes:
    rows = [
        "# Accepted Phase 8 results",
        "",
        "All values below are derived from the externally accepted frozen experiment.",
        "Favorable outcomes were not required for gate success.",
        "",
        "| Hypothesis | Baseline | Metric | Blocks | Mean favorable difference | "
        "95% CI | Holm p | Guard |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for item in results["primary_comparisons"]:
        ci = item["bootstrap_95_ci"]
        rows.append(
            f"| {item['hypothesis']} | {item['baseline']} | {item['metric']} | "
            f"{item['paired_blocks']} | {item['mean_favorable_difference']:.6f} | "
            f"[{ci[0]:.6f}, {ci[1]:.6f}] | {item['holm_adjusted_p_value']:.6f} | "
            f"{str(item['safety_guard_non_increasing']).lower()} |"
        )
    rows.extend(
        (
            "",
            "## Interpretation boundary",
            "",
            results["scientific_boundary"],
            "",
            "E9 is a detection-only full-TCB-compromise profile. Its 38 unsafe executions are "
            "retained and no prevention claim is made.",
        )
    )
    return ("\n".join(rows) + "\n").encode()


def _effect_svg(results: dict[str, Any]) -> bytes:
    comparisons = results["primary_comparisons"]
    width, height = 900, 80 + len(comparisons) * 54
    maximum = max(float(item["mean_favorable_difference"]) for item in comparisons)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="24" y="34" font-family="sans-serif" font-size="20" '
        'font-weight="bold">Phase 8 accepted favorable differences</text>',
        '<text x="24" y="56" font-family="sans-serif" font-size="12">'
        "Metrics retain their preregistered native scales; bars are normalized only for display."
        "</text>",
    ]
    for index, item in enumerate(comparisons):
        y = 82 + index * 54
        value = float(item["mean_favorable_difference"])
        bar = 590 * value / maximum
        parts.extend(
            (
                f'<text x="24" y="{y + 18}" font-family="sans-serif" font-size="14">'
                f"{escape(str(item['hypothesis']))} vs "
                f"{escape(str(item['baseline']))}</text>",
                f'<rect x="180" y="{y}" width="{bar:.3f}" height="24" fill="#1769aa"/>',
                f'<text x="{190 + bar:.3f}" y="{y + 18}" font-family="sans-serif" '
                f'font-size="13">{value:.6f}</text>',
            )
        )
    parts.append("</svg>")
    return ("\n".join(parts) + "\n").encode()


def _static_documents(acceptance: dict[str, Any]) -> dict[str, bytes]:
    reproducibility = f"""# Reproducibility

Accepted source commit: `{acceptance["accepted_source_commit"]}`

1. Obtain the v0.8.0 source archive and verify `{acceptance["source_archive_sha256"]}`.
2. Obtain the Windows and CI evidence archives and verify their hashes recorded in the acceptance.
3. Verify each archive's evidence manifest before interpreting results.
4. Confirm protocol, oracle, raw-result, and analysis hashes match `release-metadata.json`.
5. Do not rerun or replace the accepted experiment when reproducing this publication package.

This artifact documents a synthetic, nonclinical experiment. It is not a production or
clinical certification.
"""
    claims = """# Claim-to-evidence matrix

| Claim | Evidence | Boundary |
|---|---|---|
| Paired experiment | raw-results and trace hashes | Synthetic workloads |
| H1-H3 and H5-H9 | accepted-results.json and results-table.csv | Frozen scenarios and seeds |
| H4 targets | accepted Windows/Linux performance records | Host-specific proxy latency |
| Cross-platform reproduction | identical result hashes | Reviewed Python 3.12 environments |
| Supply-chain state | two CycloneDX inventories and audits | Capture-time dependencies |
| Full-TCB compromise | E9 retained outcomes | Detection-only; no prevention claim |
"""
    return {
        "REPRODUCIBILITY.md": reproducibility.encode(),
        "CLAIM-EVIDENCE-MATRIX.md": claims.encode(),
    }


def build_publication_package(root: Path, output: Path) -> dict[str, Any]:
    acceptance, results = validate_release_inputs(root)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "accepted-results.json": _json_bytes(results),
        "phase8-external-acceptance.json": _json_bytes(acceptance),
        "RESULTS.md": _results_markdown(results),
        "results-table.csv": _results_csv(results),
        "comparison-effects.svg": _effect_svg(results),
        **_static_documents(acceptance),
    }
    metadata = {
        "schema_version": "edge-lifeline-phase9-release-v1",
        "release_version": "0.9.0",
        "accepted_source_commit": acceptance["accepted_source_commit"],
        "acceptance_commit": "4b28e5a0858c76eeffdd8b855d67fc830a574a88",
        "synthetic_nonclinical": True,
        "experiment_rerun": False,
        "outcome_based_exclusions": 0,
        "phase9_complete": False,
        "public_release_authorized": False,
        "protocol_sha256": acceptance["protocol_sha256"],
        "oracle_sha256": acceptance["oracle_sha256"],
        "raw_results_sha256": acceptance["raw_results_sha256"],
        "analysis_sha256": acceptance["analysis_sha256"],
        "scientific_boundary": acceptance["scientific_boundary"],
    }
    files["release-metadata.json"] = _json_bytes(metadata)
    for name, content in files.items():
        (output / name).write_bytes(content)
    checksums = "".join(f"{_sha256(files[name])}  {name}\n" for name in sorted(files))
    (output / "CHECKSUMS.sha256").write_bytes(checksums.encode())
    manifest_files = {**files, "CHECKSUMS.sha256": checksums.encode()}
    manifest = {
        "schema_version": "edge-lifeline-phase9-artifact-manifest-v1",
        "file_count": len(manifest_files),
        "sha256": {name: _sha256(content) for name, content in sorted(manifest_files.items())},
    }
    (output / "ARTIFACT-MANIFEST.json").write_bytes(_json_bytes(manifest))
    return manifest
