"""Runtime-verifiable counterparts to the Phase 0 safety invariants."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from edge_lifeline.formal.authority import AuthorityEnvelope, Budgets


@dataclass(frozen=True, slots=True)
class DecisionTransaction:
    nonce_consumed: bool
    budget_reserved: bool
    certificate_committed: bool
    effect_registered: bool
    effect_dispatched: bool


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    content_present: bool
    hash_matches: bool
    provenance_valid: bool
    freshness_valid: bool
    chain_link_valid: bool


def assert_monotonic_trace(trace: Iterable[AuthorityEnvelope]) -> None:
    iterator = iter(trace)
    try:
        previous = next(iterator)
    except StopIteration as error:
        raise ValueError("authority trace cannot be empty") from error
    for current in iterator:
        if current.isolation_epoch != previous.isolation_epoch:
            raise ValueError("same-epoch monotonic check cannot cross epoch boundaries")
        if not current.is_no_more_authoritative_than(previous):
            raise AssertionError("I1 monotonic contraction violated")
        previous = current


def assert_parent_chain_bounded(
    child: AuthorityEnvelope,
    ancestors: Iterable[AuthorityEnvelope],
) -> None:
    for ancestor in ancestors:
        if not child.is_no_more_authoritative_than(ancestor):
            raise AssertionError("I2/I16 ancestor or issuer ceiling violated")


def assert_aggregate_budget(
    parent: Budgets,
    consumed: Budgets,
    active_child_reservations: Iterable[Budgets],
) -> None:
    total = consumed
    for reservation in active_child_reservations:
        total = total.add(reservation)
    if not total.is_no_more_than(parent):
        raise AssertionError("I15 aggregate child budget exceeded")


def assert_proof_before_effect(transaction: DecisionTransaction) -> None:
    atomic_prerequisites = (
        transaction.nonce_consumed
        and transaction.budget_reserved
        and transaction.certificate_committed
        and transaction.effect_registered
    )
    if transaction.effect_dispatched and not atomic_prerequisites:
        raise AssertionError("I6/I14 proof-before-effect atomicity violated")


def evidence_complete(references: Iterable[EvidenceReference]) -> bool:
    references_tuple = tuple(references)
    return bool(references_tuple) and all(
        reference.content_present
        and reference.hash_matches
        and reference.provenance_valid
        and reference.freshness_valid
        and reference.chain_link_valid
        for reference in references_tuple
    )


def consume_nonce(used: frozenset[str], nonce: str) -> frozenset[str]:
    if not nonce:
        raise ValueError("nonce cannot be empty")
    if nonce in used:
        raise ValueError("I5 replay detected")
    return used | {nonce}
