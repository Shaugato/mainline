# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The table is data, so it is checked against prose written independently of it.

``table.ROWS`` is 100 literal rows.  Its docstring states six rules in English.
This file implements those six rules a second time, from the prose, and asserts
the two agree cell for cell — the same discipline CATSEAL uses for its preimage
encoder.  A transcription error in the data or a drift between the data and the
documentation can then only present as a failing build.
"""

from __future__ import annotations

import hashlib

import pytest
from mainline_domain.contracts import ControlDelta, force
from mainline_domain.resolution import table as table_module
from mainline_domain.resolution.table import (
    RESOLUTION,
    ROWS,
    TABLE_SHA256,
    TABLE_VERSION,
    cell_for,
)

_DELTAS = tuple(ControlDelta)


def _independent_rule(
    a: ControlDelta,
    b: ControlDelta,
    *,
    confident: bool,
    abstained: bool,
) -> tuple[ControlDelta, str, str]:
    """The six rules, transcribed from the module docstring and nothing else."""
    if abstained:
        resolved = a if force(a) >= force(ControlDelta.WEAKEN) else ControlDelta.WEAKEN
        return resolved, "abstain_to_weaken", "ABSTENTION_FLOOR"
    if a is b:
        return a, "lattice", "CONCUR"
    if force(b) > force(a):
        return b, "lattice+model", "MODEL_RAISES"
    if force(b) < force(a):
        return a, "lattice", "MODEL_LOWER_IGNORED"
    if confident:
        return a, "lattice", "NEUTRAL_ACCEPTED"
    return ControlDelta.WEAKEN, "abstain_to_weaken", "NEUTRAL_UNCONFIRMED"


def test_the_table_is_total() -> None:
    assert len(ROWS) == 100
    assert len(RESOLUTION) == len(_DELTAS) * len(_DELTAS) * 2 * 2


@pytest.mark.parametrize("a", _DELTAS, ids=lambda d: f"A={d.value}")
@pytest.mark.parametrize("b", _DELTAS, ids=lambda d: f"B={d.value}")
@pytest.mark.parametrize("confident", [True, False], ids=["confident", "unconfident"])
@pytest.mark.parametrize("abstained", [True, False], ids=["abstained", "answered"])
def test_every_cell_matches_the_prose(
    a: ControlDelta, b: ControlDelta, confident: bool, abstained: bool
) -> None:
    """The data and the documentation, compared."""
    expected_delta, expected_basis, expected_rule = _independent_rule(
        a, b, confident=confident, abstained=abstained
    )
    cell = cell_for(a, b, confident=confident, abstained=abstained)
    assert (cell.delta, cell.basis, cell.rule) == (expected_delta, expected_basis, expected_rule)


def test_no_cell_lowers_force() -> None:
    """The invariant the module refuses to load without, asserted from outside."""
    for (a, _b, _c, _s), cell in RESOLUTION.items():
        assert force(cell.delta) >= force(a)


def test_lattice_plus_model_appears_only_where_the_model_raised() -> None:
    """``delta_basis`` must mean what a reader thinks it means.

    ``'lattice+model'`` is read as *a model was load-bearing for this verdict*.
    If it were also written where the model merely agreed, the column would stop
    answering the question people ask of it.
    """
    for cell in RESOLUTION.values():
        if cell.basis == "lattice+model":
            assert cell.rule == "MODEL_RAISES"
        if cell.rule == "MODEL_RAISES":
            assert cell.basis == "lattice+model"


def test_no_cell_claims_a_human_basis() -> None:
    assert all(cell.basis != "human" for cell in RESOLUTION.values())


def test_every_abstention_cell_is_at_least_a_weakening() -> None:
    for (a, _b, _c, abstained), cell in RESOLUTION.items():
        if abstained:
            assert force(cell.delta) >= force(ControlDelta.WEAKEN)
            assert cell.rule == "ABSTENTION_FLOOR"
            # remove is force 3 and must not be flattened down to weaken
            if a is ControlDelta.REMOVE:
                assert cell.delta is ControlDelta.REMOVE


def test_the_digest_covers_the_rows_and_the_version() -> None:
    """The content address is recomputable by anyone holding the file."""
    digest = hashlib.sha256()
    digest.update(TABLE_VERSION.encode("utf-8"))
    for row in ROWS:
        for field in row:
            token = str(field).encode("utf-8")
            digest.update(len(token).to_bytes(4, "big"))
            digest.update(token)
    assert digest.hexdigest() == TABLE_SHA256
    assert len(TABLE_SHA256) == 64


def test_the_loader_refuses_a_row_that_lowers_the_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """PL-2 for the import-time guard: it has to have rejected something.

    A row saying "Path A found a weakening, the model disagreed, so restate" is
    the exact defect the ratchet exists to make impossible. The loader must
    refuse to build a table containing one.
    """
    target = ("weaken", "restate", True, False)
    poisoned = tuple(
        (*target, "restate", "lattice", "MODEL_LOWER_IGNORED") if row[:4] == target else row
        for row in ROWS
    )
    assert poisoned != ROWS, "the poisoned row must actually replace a real one"
    monkeypatch.setattr(table_module, "ROWS", poisoned)
    with pytest.raises(ValueError, match="lowers the Path-A verdict"):
        table_module._freeze()


def test_the_loader_refuses_an_incomplete_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(table_module, "ROWS", ROWS[:-1])
    with pytest.raises(ValueError, match="not total"):
        table_module._freeze()
