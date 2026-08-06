# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``mainline_domain.contracts`` — the frozen vocabulary ten workers share.

Two things are checked here that nothing else can check later:

* the ``ControlDelta`` members and ``force()`` codomain, because the ABSTENTION
  RATCHET's guarantee ("a model can raise a verdict, never lower it") is stated
  as arithmetic over this function;
* that ``contracts`` imports **nothing but the standard library**, because the
  migration runner and the offline verifier depend on it and a model SDK
  arriving here by accident would breach P7 for the whole domain.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

import pytest

CONTRACTS = (
    Path(__file__).resolve().parents[4]
    / "verticals"
    / "mainline"
    / "packages"
    / "mainline-domain"
    / "src"
    / "mainline_domain"
    / "contracts.py"
)

STDLIB_ROOTS = {
    "__future__",
    "collections",
    "dataclasses",
    "decimal",
    "enum",
    "typing",
    "uuid",
}


def test_control_delta_mirrors_the_sql_enum() -> None:
    from mainline_domain.contracts import ControlDelta

    assert [member.value for member in ControlDelta] == [
        "introduce",
        "strengthen",
        "restate",
        "weaken",
        "remove",
    ]


def test_force_codomain() -> None:
    from mainline_domain.contracts import ControlDelta, force

    assert force(ControlDelta.INTRODUCE) == 0
    assert force(ControlDelta.STRENGTHEN) == 0
    assert force(ControlDelta.RESTATE) == 0
    assert force(ControlDelta.WEAKEN) == 2
    assert force(ControlDelta.REMOVE) == 3


def test_force_is_total_over_the_enum() -> None:
    """A member with no force is a member the ratchet cannot reason about."""
    from mainline_domain.contracts import ControlDelta, force

    assert {force(member) for member in ControlDelta} == {0, 2, 3}


def test_contracts_imports_only_the_standard_library() -> None:
    tree = ast.parse(CONTRACTS.read_text(encoding="utf-8"), filename=str(CONTRACTS))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import is not a third-party dependency
                continue
            roots.add((node.module or "").split(".")[0])
    assert roots <= STDLIB_ROOTS, f"contracts.py grew a dependency: {roots - STDLIB_ROOTS}"


def test_no_model_sdk_reachable_from_contracts() -> None:
    forbidden = {"boto3", "botocore", "anthropic", "strands", "openai", "langchain"}
    source = CONTRACTS.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CONTRACTS))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden


IDENTITY_TYPES = [
    "Anchor",
    "AnchorSet",
    "AssignmentEdge",
    "CAT",
    "CATResult",
    "CBMAccount",
    "Candidate",
    "CanonResult",
    "DeltaVerdict",
    "DeltaWitness",
    "OcrRepair",
    "OracleRequest",
    "OracleVerdict",
    "Quantity",
    "ResidueRow",
    "Segment",
]


@pytest.mark.parametrize("name", IDENTITY_TYPES)
def test_every_shared_type_is_a_frozen_slotted_dataclass(name: str) -> None:
    import mainline_domain.contracts as contracts

    cls = getattr(contracts, name)
    assert is_dataclass(cls), f"{name} must be a dataclass"
    assert getattr(cls, "__slots__", None) is not None, f"{name} must use slots"
    assert fields(cls), f"{name} has no fields"
    assert cls.__dataclass_params__.frozen, f"{name} must be frozen"


def test_identity_bearing_fields_carry_no_defaults() -> None:
    """A default on an identity field is a decision nobody signed for."""
    import dataclasses

    import mainline_domain.contracts as contracts

    for name in IDENTITY_TYPES:
        cls = getattr(contracts, name)
        for field in dataclasses.fields(cls):
            assert field.default is dataclasses.MISSING, f"{name}.{field.name} has a default"
            assert field.default_factory is dataclasses.MISSING, (
                f"{name}.{field.name} has a default factory"
            )


def test_frozen_means_frozen() -> None:
    from mainline_domain.contracts import Anchor, AnchorClass

    anchor = Anchor(cls=AnchorClass.EQUIPMENT_TAG, raw="P-101A", norm="P-101A", span=(0, 6))
    with pytest.raises(FrozenInstanceError):
        anchor.norm = "P-101B"  # type: ignore[misc]


def test_residue_reasons_are_exactly_the_five_in_the_ddl() -> None:
    import typing

    from mainline_domain.contracts import ResidueReason

    assert set(typing.get_args(ResidueReason)) == {
        "unmatched",
        "ambiguous",
        "anchor_drop",
        "opaque_control",
        "citation_unresolved",
    }


def test_rule_ids_are_the_nine_lattice_rules() -> None:
    import typing

    from mainline_domain.contracts import RULE_IDS, RuleId

    assert set(typing.get_args(RuleId)) == set(RULE_IDS)
    assert len(RULE_IDS) == 9
    assert RULE_IDS[0] == "R1_DEONTIC"
    assert RULE_IDS[-1] == "R9_COVERAGE"


def test_cbm_balance_identity() -> None:
    from uuid import uuid4

    from mainline_domain.contracts import CBMAccount

    balanced = CBMAccount(
        site_id=uuid4(),
        commit_id=b"\x01" * 32,
        inherited=5,
        carried=2,
        split_carried=1,
        merge_carried=1,
        residue_open=1,
        residue_disposed=0,
    )
    assert balanced.balanced()

    # five obligations went in and four came out
    under_emitted = CBMAccount(
        site_id=balanced.site_id,
        commit_id=balanced.commit_id,
        inherited=5,
        carried=2,
        split_carried=1,
        merge_carried=1,
        residue_open=0,
        residue_disposed=0,
    )
    assert not under_emitted.balanced()
