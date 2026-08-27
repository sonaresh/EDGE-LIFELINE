from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from edge_lifeline.policy import PolicyBundle


def bundle() -> PolicyBundle:
    return PolicyBundle(
        sources={"policy/edge.rego": b"package edge\r\nallow := true\r\n"},
        data_documents={"data/roles.json": {"roles": ["operator"]}},
        entrypoints=("edge/result",),
        policy_version="phase5-policy-v1",
        opa_version="1.19.1",
    )


def test_semantic_hash_normalizes_line_endings_and_mapping_order() -> None:
    first = bundle()
    second = PolicyBundle(
        sources={"policy/edge.rego": b"package edge\nallow := true\n"},
        data_documents={"data/roles.json": {"roles": ["operator"]}},
        entrypoints=("edge/result",),
        policy_version="phase5-policy-v1",
        opa_version="1.19.1",
    )
    assert first.policy_hash() == second.policy_hash()
    assert first.sources["policy/edge.rego"].count(b"\r") == 0


@pytest.mark.parametrize(
    "changed",
    [
        lambda value: replace(
            value, sources={"policy/edge.rego": b"package edge\nallow := false\n"}
        ),
        lambda value: replace(value, data_documents={"data/roles.json": {"roles": ["admin"]}}),
        lambda value: replace(value, entrypoints=("edge/other",)),
        lambda value: replace(value, policy_version="phase5-policy-v2"),
        lambda value: replace(value, opa_version="1.20.0"),
    ],
)
def test_every_semantic_dimension_changes_hash(
    changed: Callable[[PolicyBundle], PolicyBundle],
) -> None:
    original = bundle()
    assert changed(original).policy_hash() != original.policy_hash()


def test_bundle_copies_and_freezes_nested_data() -> None:
    document = {"roles": ["operator"]}
    value = replace(bundle(), data_documents={"data/roles.json": document})
    document["roles"].append("admin")
    assert value.semantic_obj()["data_documents"] == {"data/roles.json": {"roles": ["operator"]}}
    with pytest.raises(TypeError):
        value.data_documents["data/roles.json"]["roles"] = ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sources": {"../edge.rego": b"package edge"}},
        {"sources": {"policy//edge.rego": b"package edge"}},
        {"sources": {"edge.rego": b"\xff"}},
        {"data_documents": {"data.json": {"bad": {1, 2}}}},
        {"entrypoints": ("../edge/result",)},
        {"entrypoints": ("edge//result",)},
        {"entrypoints": ("edge/result", "edge/result")},
    ],
)
def test_invalid_or_ambiguous_bundle_inputs_are_rejected(kwargs: dict[str, object]) -> None:
    values: dict[str, Any] = {
        "sources": {"policy/edge.rego": b"package edge\n"},
        "data_documents": {},
        "entrypoints": ("edge/result",),
        "policy_version": "phase5-policy-v1",
        "opa_version": "1.19.1",
    }
    values.update(kwargs)
    with pytest.raises((UnicodeDecodeError, ValueError)):
        PolicyBundle(**values)
