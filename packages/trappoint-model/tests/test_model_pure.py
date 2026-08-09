# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The oracle on its own: it is small, it is pure, and it refuses what it must.

These tests need no cluster and always run. They are not the differential — an oracle
that agrees with itself has proved nothing about the gate — but they hold the two
properties that make the oracle usable as one:

* **it is readable in five minutes.** ``model.py`` is asserted at ≤ 200 lines. If the
  model needs four hundred, the model is wrong, not the gate: an oracle nobody can hold
  in their head cannot be used to accuse an implementation.
* **it is independent.** It imports nothing from the substrate, so an error shared with
  ``trappoint-core`` cannot cancel out in the comparison.
"""

from __future__ import annotations

import ast
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st
from trappoint_model.model import Accept, Model, Refuse

MODEL_PY = Path(__file__).resolve().parents[1] / "src" / "trappoint_model" / "model.py"
SUBSTRATE_PACKAGES = (
    "trappoint_core",
    "trappoint_sql",
    "trappoint_conformance",
    "trappoint_diagnose",
    "trappoint_migrate",
    "trappoint_ledger",
    "trappoint_recall",
    "mainline_boundary",
    "mainline_agentkit",
    "mainline_mcp",
)


def test_model_is_small_enough_to_read() -> None:
    """≤ 200 lines. The bound is the point, not a style preference."""
    lines = MODEL_PY.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 200, (
        f"model.py is {len(lines)} lines. The oracle must be readable in five minutes; "
        "a model that needs four hundred lines is a second implementation of the gate, "
        "and two implementations of the same misunderstanding agree perfectly."
    )


def test_model_imports_nothing_from_the_substrate() -> None:
    """The oracle is independent, or the differential compares a thing with itself."""
    tree = ast.parse(MODEL_PY.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    offending = [
        name
        for name in imported
        if any(name == pkg or name.startswith(f"{pkg}.") for pkg in SUBSTRATE_PACKAGES)
    ]
    assert not offending, (
        f"model.py imports {offending} from the substrate. An oracle that shares code with "
        "the implementation it judges cannot disagree with it."
    )
    assert imported == ["__future__", "dataclasses"], (
        f"model.py imports {imported}; it must depend on the standard library alone"
    )


def test_the_gate_refuses_an_open_obligation() -> None:
    """The headline refusal, in the oracle: 23514 on ``gate_closed_when_issued``."""
    m = Model()
    m.create_subject("s")
    m.materialise_check("s", "c1")
    m.sign_disposition("c1", "d1")
    m.materialise_check("s", "c2")  # arrives after clearance; the state does not re-open
    assert m.attempt_merge("s") == Refuse("23514", "gate_closed_when_issued")


def test_an_expired_verdict_is_seen_by_the_derivation_and_not_by_the_counter() -> None:
    """The case no CHECK over a scalar can see, and the reason the trigger exists."""
    m = Model()
    m.create_subject("s")
    m.materialise_check("s", "c")
    m.sign_disposition("c", "d", expired=True)
    assert m.subjects["s"].open_blocking == 0, "the counter decremented"
    assert m.derived_open("s") == 1, "the anti-join did not"
    assert m.attempt_merge("s") == Refuse("P0001", "trappoint_ref.fn_permit_merge_gate")


def test_a_precursor_cannot_reach_an_issued_subject() -> None:
    """MI07. The epoch moved; the pin holds it."""
    m = Model()
    m.create_subject("s")
    m.materialise_check("s", "c")
    m.sign_disposition("c", "d")
    assert m.attempt_merge("s") == Accept()
    assert m.materialise_check("s", "c2") == Refuse("P0001", "trappoint_ref.fn_check_materialised")
    assert m.l1_holds()


def test_a_second_merge_is_refused_by_the_transition_table() -> None:
    """A merged subject has no edge to 'merged'. Refusal by data, not by a branch."""
    m = Model()
    m.create_subject("s")
    m.materialise_check("s", "c")
    m.sign_disposition("c", "d")
    m.attempt_merge("s")
    assert m.attempt_merge("s") == Refuse("23503", "legal_edge")


def test_expiry_does_not_free_the_one_live_disposition_slot() -> None:
    """A partial unique index over ``retracted_by IS NULL`` does not care about expiry."""
    m = Model()
    m.create_subject("s")
    m.materialise_check("s", "c")
    m.sign_disposition("c", "d1", expired=True)
    assert m.sign_disposition("c", "d2") == Refuse("23505", "one_live_disposition")


@given(
    ops=st.lists(
        st.sampled_from(["check", "sign", "expire", "retract", "merge", "suspend"]),
        min_size=1,
        max_size=40,
    )
)
def test_l1_survives_every_pure_history(ops: list[str]) -> None:
    """L1 holds in the oracle over arbitrary op sequences — no cluster involved.

    This is the cheap half of the conservation argument and it catches exactly one class
    of defect: a branch added to the model that mutates state on a path that should have
    refused. It says nothing about the gate, which is the differential's job.
    """
    m = Model()
    m.create_subject("s")
    checks: list[str] = []
    dispositions: list[str] = []
    for i, op in enumerate(ops):
        if op == "check":
            cid = f"c{i}"
            if isinstance(m.materialise_check("s", cid), Accept):
                checks.append(cid)
        elif op in {"sign", "expire"} and checks:
            did = f"d{i}"
            if isinstance(
                m.sign_disposition(checks[i % len(checks)], did, expired=op == "expire"), Accept
            ):
                dispositions.append(did)
        elif op == "retract" and len(dispositions) >= 2:
            m.retract(
                dispositions[i % len(dispositions)],
                dispositions[(i + 1) % len(dispositions)],
            )
        elif op == "merge":
            m.attempt_merge("s")
        elif op == "suspend":
            m.suspend("s")
        assert m.l1_holds(), f"L1 broke in the oracle after {ops[: i + 1]}"
