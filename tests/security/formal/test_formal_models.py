from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.security
def test_positive_model_covers_phase2_invariants() -> None:
    config = Path("formal/tla/configs/positive.cfg").read_text(encoding="utf-8")
    for invariant in (
        "I1_MonotonicContraction",
        "I2_ParentBounded",
        "I4_ConservativeTime",
        "I5_AntiReplay",
        "I6_ProofBeforeEffect",
        "I9_NoReconnectGrant",
        "I10_NoAutomaticEffectReplay",
        "I11_OverrideBounded",
        "I12_OverrideOneShot",
        "I13_EffectStateSafe",
        "I15_AggregateChildBudget",
        "I16_IssuerCeiling",
    ):
        assert invariant in config


@pytest.mark.security
@pytest.mark.parametrize(
    ("filename", "weakened", "invariant"),
    [
        ("negative_parent.cfg", "CheckParent = FALSE", "I2_ParentBounded"),
        ("negative_time.cfg", "UseConservativeTime = FALSE", "I4_ConservativeTime"),
        ("negative_replay.cfg", "RememberNonces = FALSE", "I5_AntiReplay"),
        (
            "negative_reconnect.cfg",
            "ReconnectGrantsAuthority = TRUE",
            "I9_NoReconnectGrant",
        ),
        ("negative_proof.cfg", "RequireProof = FALSE", "I6_ProofBeforeEffect"),
        (
            "negative_auto_replay.cfg",
            "AutoReplayEffects = TRUE",
            "I10_NoAutomaticEffectReplay",
        ),
    ],
)
def test_each_negative_model_weakens_one_guard(
    filename: str, weakened: str, invariant: str
) -> None:
    config = Path("formal/tla/configs", filename).read_text(encoding="utf-8")
    assert weakened in config
    assert f"INVARIANT {invariant}" in config


@pytest.mark.security
def test_formal_model_keeps_emergency_authority_separate() -> None:
    specification = Path("formal/tla/EdgeLifeline.tla").read_text(encoding="utf-8")
    activation = specification.split("ActivateOverride(e, a) ==", maxsplit=1)[1].split(
        "ConsumeOverride(e) ==", maxsplit=1
    )[0]
    assert "overrideAuthority'" in activation
    assert "UNCHANGED <<mode, epoch, authority" in activation
    assert "~overrideConsumed[e]" in activation


@pytest.mark.security
def test_reconnection_requires_explicit_fresh_authority() -> None:
    specification = Path("formal/tla/EdgeLifeline.tla").read_text(encoding="utf-8")
    reconnect = specification.split("Reconnect(e) ==", maxsplit=1)[1].split(
        "ReceiveFreshAuthority(e) ==", maxsplit=1
    )[0]
    reconcile = specification.split("ReconcileNewEpoch(e) ==", maxsplit=1)[1].split(
        "Quarantine(e) ==", maxsplit=1
    )[0]
    assert "freshAuthorityReceived'" in reconnect
    assert "FALSE" in reconnect
    assert "freshAuthorityReceived[e]" in reconcile


@pytest.mark.security
def test_phase3_cryptography_is_not_implemented_early() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("src").rglob("*.py")
    ).lower()
    assert "ed25519privatekey" not in source
    assert "cose_sign1" not in source
    assert "signing_key" not in source
