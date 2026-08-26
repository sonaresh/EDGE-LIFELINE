from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from edge_lifeline.formal.authority import AuthorityEnvelope, Budgets
from edge_lifeline.formal.invariants import (
    DecisionTransaction,
    EvidenceReference,
    assert_aggregate_budget,
    assert_monotonic_trace,
    assert_parent_chain_bounded,
    assert_proof_before_effect,
    consume_nonce,
    evidence_complete,
)


def test_runtime_invariants_accept_bounded_trace(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    root = envelope_factory()
    child = replace(root, actions=frozenset({"monitor", "record"}))
    leaf = replace(child, actions=frozenset({"monitor"}))
    assert_monotonic_trace([root, child, leaf])
    assert_parent_chain_bounded(leaf, [child, root])


def test_runtime_invariants_reject_widening_and_cross_epoch(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    root = envelope_factory()
    child = replace(root, actions=frozenset({"monitor"}))
    with pytest.raises(AssertionError, match="I1"):
        assert_monotonic_trace([child, root])
    with pytest.raises(ValueError, match="epoch"):
        assert_monotonic_trace([root, replace(root, isolation_epoch="epoch-2")])
    with pytest.raises(ValueError, match="empty"):
        assert_monotonic_trace([])


def test_aggregate_sibling_budget_is_atomic() -> None:
    parent = Budgets(10, 10, 10, 10, 10, 10)
    assert_aggregate_budget(
        parent,
        Budgets(1, 1, 1, 1, 1, 1),
        [Budgets(4, 4, 4, 4, 4, 4), Budgets(5, 5, 5, 5, 5, 5)],
    )
    with pytest.raises(AssertionError, match="I15"):
        assert_aggregate_budget(
            parent,
            Budgets(1, 1, 1, 1, 1, 1),
            [Budgets(5, 5, 5, 5, 5, 5), Budgets(5, 5, 5, 5, 5, 5)],
        )


def test_effect_dispatch_requires_atomic_prerequisites() -> None:
    valid = DecisionTransaction(True, True, True, True, True)
    assert_proof_before_effect(valid)
    with pytest.raises(AssertionError, match="I6/I14"):
        assert_proof_before_effect(DecisionTransaction(True, True, False, True, True))
    assert_proof_before_effect(DecisionTransaction(False, False, False, False, False))


def test_evidence_completeness_is_nonempty_and_fail_safe() -> None:
    complete = EvidenceReference(True, True, True, True, True)
    invalid = EvidenceReference(True, False, True, True, True)
    assert evidence_complete([complete])
    assert not evidence_complete([])
    assert not evidence_complete([complete, invalid])


def test_nonce_is_consumed_once() -> None:
    used = consume_nonce(frozenset(), "nonce-1")
    assert used == {"nonce-1"}
    with pytest.raises(ValueError, match="replay"):
        consume_nonce(used, "nonce-1")
    with pytest.raises(ValueError, match="empty"):
        consume_nonce(used, "")
