# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# ruff: noqa: S101, PLR2004
# ruff.toml's per-file-ignores exempt `**/tests/**` from the assert, magic-value,
# annotation and private-access rules, for the reason every test suite needs them.
# This IS a test suite; it lives in `unweld/` rather than `tests/` because the
# schema-mutating suite is invoked as its own serial job (`-m schema -p no:xdist`)
# and the matrix it drives is library code its tests import. The exemption is
# declared here rather than by widening a glob in a file this worker does not own.
"""Invariant mutation testing: unweld one mechanism, and see whether the gate holds.

Four assertions, and they are deliberately separate because they fail for different reasons
and a reader needs to know which one happened.

``test_no_single_mechanism_unwelds_the_gate``
    the headline. Take one mechanism away and the illegal history is **still refused**. A
    failure here means the gate had exactly one weld at that point, which is not a test
    failure so much as a design finding.

``test_the_surviving_refusal_is_a_different_mechanism``
    the assertion that makes the first one mean something. *Still refused* is worthless if
    it is the same mechanism answering under a different name, so the survivor is compared
    against the mechanism that was removed, by identity rather than by SQLSTATE. Two
    constraints can share a code; sharing a code is not sharing a mechanism.

``test_merge_gate_histories_are_at_least_double_welded``
    the CI floor. Below two, the job fails, and the pre-committed response is the kernel
    lead's: *cut the mechanism, do not ship it.*

``test_restoration_matches_the_migration``
    a hermetic guard with no cluster in it. Every restoration clause in the matrix must
    appear in the migration tree that owns the object, so a constraint whose definition
    changes cannot leave ``mutations.py`` quietly re-adding the old one — which would make
    every row measured after it a measurement of a schema nobody ships.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from .container import MAINLINE_TREE, REF_TREE
from .harness import MatrixRow, _mechanism_matches, render_report
from .mutations import MECHANISMS

pytestmark = pytest.mark.schema

REPORT = Path(__file__).resolve().parents[1] / "REFUSAL_DEPTH.md"


def _row(matrix: list[MatrixRow], case_id: str) -> MatrixRow | None:
    return next((r for r in matrix if r.case_id == case_id), None)


@pytest.mark.anomaly("A9")
def test_no_single_mechanism_unwelds_the_gate(matrix: list[MatrixRow]) -> None:
    """No single removal opens a gate that was closed."""
    opened: list[str] = []
    for row in matrix:
        for mutation, observation in row.probes:
            if not observation.refused:
                opened.append(
                    f"{row.case_id}: removing {mutation.name} ALONE admitted the write "
                    f"({observation.detail or 'the history completed'})"
                )
    assert not opened, (
        "UNWELDED. Each line names one mechanism whose removal alone opened a gate:\n  "
        + "\n  ".join(opened)
        + "\n\nThat is not a broken test. It is the measurement the suite exists to make, "
        "and the pre-committed response is to cut the mechanism rather than ship a "
        "single-welded gate."
    )


@pytest.mark.anomaly("A9")
def test_the_surviving_refusal_is_a_different_mechanism(matrix: list[MatrixRow]) -> None:
    """The refusal that survives a removal did not come from the thing removed."""
    impostors: list[str] = []
    for row in matrix:
        for mutation, observation in row.probes:
            if observation.refused and _mechanism_matches(observation.exhibit, mutation):
                impostors.append(
                    f"{row.case_id}: {mutation.name} was removed and the surviving refusal "
                    f"still names it ({observation.sqlstate} on {observation.exhibit})"
                )
    assert not impostors, (
        "A mechanism that was removed is still producing the refusal, so either the "
        "removal did not take effect or the matrix names the wrong mechanism. Either way "
        "the depth reported for these histories is not a measurement:\n  " + "\n  ".join(impostors)
    )


@pytest.mark.anomaly("A2")
def test_merge_gate_histories_are_at_least_double_welded(
    matrix: list[MatrixRow], gated: frozenset[str]
) -> None:
    """Every merge-gate history is refused by at least two independent mechanisms."""
    thin = [
        f"{row.case_id}: depth {row.depth} "
        f"({', '.join(row.observed_mechanisms) or 'nothing observed'})"
        for row in matrix
        if row.case_id in gated and row.depth < 2
    ]
    assert not thin, (
        "Merge-gate histories below the refusal-depth floor of two:\n  "
        + "\n  ".join(thin)
        + "\n\nA single-welded gate is a claim that cannot be made under oath. The "
        "pre-committed response is to cut the mechanism, not to lower the floor."
    )


def test_restoration_matches_the_migration(repo_root: Path) -> None:
    """Every restoration in the matrix is grounded in the migration that owns the object.

    Hermetic: no cluster, no container, no network. It runs in the ordinary unit job as
    well as the schema job, because a matrix that has drifted from the schema is worth
    catching before a container is started rather than after.
    """
    trees = [repo_root / REF_TREE, repo_root / MAINLINE_TREE]
    corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for tree in trees
        if tree.is_dir()
        for path in sorted(tree.glob("*.sql"))
    )
    if not corpus:
        pytest.skip("SKIP WITH REASON: no migration tree in this checkout to ground against")

    ungrounded: list[str] = []
    for mutation in MECHANISMS:
        if not mutation.removable:
            assert mutation.unremovable_reason, (
                f"{mutation.name} is declared unremovable with no reason. An untested "
                f"mechanism silently omitted from the matrix is exactly the gap this suite "
                f"exists to make visible."
            )
            continue
        local = mutation.name.split("@")[-1].split(".")[-1]
        if local not in corpus:
            ungrounded.append(f"{mutation.name}: no migration in either tree mentions {local!r}")
            continue
        # The distinguishing part of the restoration — the predicate of a CHECK, the
        # referenced columns of a foreign key — has to be findable in the tree too, or the
        # restoration is putting back something the migrations never created.
        payload = _restoration_payload(mutation.restore)
        if payload and payload not in _normalise(corpus):
            ungrounded.append(
                f"{mutation.name}: the restoration clause {payload!r} does not appear in "
                f"either migration tree, so putting this mechanism back would install a "
                f"definition nobody ships"
            )
    assert not ungrounded, "\n  ".join(["Ungrounded restorations:", *ungrounded])


_SCHEMA_PREFIX = re.compile(r"\b(?:trappoint_ref|trappoint|mainline)(?:_meas|_audit|_qa|_ops)?\.")


def _normalise(text: str) -> str:
    """Collapse whitespace and drop schema qualifiers.

    The matrix writes ``{s}.permit`` and the migrations write ``trappoint_ref.permit`` or
    ``mainline.permit`` for the same object, because one is a template and the others are
    two renderings of it. Comparing them with the qualifier attached would ground nothing
    and would say so five times, which is a guard that trains its reader to ignore it.
    """
    return _SCHEMA_PREFIX.sub("", re.sub(r"\s+", " ", text))


def _restoration_payload(restore: str) -> str:
    """Return the distinguishing tail of a restoration, normalised for comparison."""
    normalised = _normalise(restore.replace("{s}.", ""))
    for keyword in ("CHECK (", "FOREIGN KEY (", "UNIQUE (", "WHERE "):
        index = normalised.find(keyword)
        if index >= 0:
            return normalised[index:].rstrip()
    return ""


@pytest.fixture(scope="session", autouse=True)
def _emit_report(request: pytest.FixtureRequest) -> None:
    """Write ``REFUSAL_DEPTH.md`` from the matrix, once, at the end of the session.

    Autouse and session-scoped so the report is written even when an assertion above
    fails — the run that found a single-welded gate is precisely the run whose matrix
    somebody needs to read.
    """
    yield  # type: ignore[misc]
    try:
        matrix = request.getfixturevalue("matrix")
        manifest = request.getfixturevalue("manifest")
        gated = request.getfixturevalue("gated")
        conn = request.getfixturevalue("mutable_conn")
    except pytest.skip.Exception:
        return
    except Exception:  # noqa: BLE001 — a missing fixture means the suite skipped
        return
    version = ""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = str(cur.fetchone()[0]).split(" (")[0]
    except Exception:  # noqa: BLE001
        version = ""
    from trappoint_conformance.runner import resolve_schema

    from .conftest import PROFILE

    REPORT.write_text(
        render_report(
            matrix,
            manifest=manifest,
            profile=PROFILE,
            schema=resolve_schema(PROFILE),
            gated=gated,
            server_version=version,
        ),
        encoding="utf-8",
    )
