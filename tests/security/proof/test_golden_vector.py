from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from edge_lifeline.proof.artifact import ArtifactType
from edge_lifeline.proof.codec import sha256_hex
from edge_lifeline.proof.verifier import EdgeProofVerifier, TrustedSigner


def test_frozen_vector_is_reproducible_and_authentic(tmp_path: Path) -> None:
    frozen_path = Path("tests/vectors/phase3/proof-chain-v1.json")
    regenerated_path = tmp_path / "regenerated.json"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/generate_phase3_vectors.py",
            "--output",
            str(regenerated_path),
        ],
        check=True,
    )
    frozen_bytes = frozen_path.read_bytes()
    assert regenerated_path.read_bytes() == frozen_bytes
    vector = json.loads(frozen_bytes)
    artifacts = vector["artifacts"]
    root = bytes.fromhex(artifacts["root"]["encoded_hex"])
    child = bytes.fromhex(artifacts["child"]["encoded_hex"])
    decision = bytes.fromhex(artifacts["decision"]["encoded_hex"])
    assert sha256_hex(root) == artifacts["root"]["sha256"]
    assert sha256_hex(child) == artifacts["child"]["sha256"]
    assert sha256_hex(decision) == artifacts["decision"]["sha256"]
    verifier = EdgeProofVerifier(
        {
            bytes.fromhex(vector["key_ids_hex"]["cloud"]): TrustedSigner(
                "cloud-authority",
                Ed25519PublicKey.from_public_bytes(
                    bytes.fromhex(vector["public_keys_hex"]["cloud"])
                ),
                frozenset({ArtifactType.AUTHORITY_LEASE}),
                root_authority=True,
            ),
            bytes.fromhex(vector["key_ids_hex"]["edge"]): TrustedSigner(
                "edge-a",
                Ed25519PublicKey.from_public_bytes(
                    bytes.fromhex(vector["public_keys_hex"]["edge"])
                ),
                frozenset({ArtifactType.AUTHORITY_LEASE, ArtifactType.DECISION_CERTIFICATE}),
            ),
        }
    )
    assert verifier.decode_and_authenticate(root).claims.parent_authority_ref is None
    assert verifier.decode_and_authenticate(child).claims.parent_authority_ref == sha256_hex(root)
    assert verifier.decode_and_authenticate(decision).claims.parent_authority_ref == sha256_hex(
        child
    )
