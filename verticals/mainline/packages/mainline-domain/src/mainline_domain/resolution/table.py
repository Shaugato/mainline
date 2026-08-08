# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ABSTENTION RATCHET, written out as data.

This module is the resolution of Path A (the deterministic lattice, worker W4)
and Path B (the model, ``mainline-delta-oracle``).  It is a **table**, not an
if-chain, for one reason: the claim being made is *"there exists no input under
which the model lowers the verdict"*, and a claim quantified over all inputs is
answerable by inspection only if all inputs are written down.  A reviewer can
read :data:`ROWS` and check the claim by eye; nobody can check it by eye against
a nest of conditionals, and neither can a diff.

**The domain of the table.**  ``5 x 5 x 2 x 2 = 100`` cells, exhaustive and
total, keyed by

``(path_a_delta, oracle_label, confident, abstained)``

where ``confident`` is ``oracle.confidence >= theta`` — theta itself lives in
``identity_policy``, never in this file (see :mod:`mainline_domain.resolution.policy`) —
and ``abstained`` is the oracle's own flag.

**The six rules the rows encode**, in the order clause-identity research §6.3 and
the worker brief state them.  The rows are the artefact; this list is the reading
key, and ``tests/unit/domain/resolution/test_table_totality.py`` re-derives all
100 cells from it in an independently written function, so the two can disagree
only by failing the build.

===================== ==========================================================
``ABSTENTION_FLOOR``  ``abstained`` — the label is meaningless, so the floor
                      applies: the resolution is ``weaken``, or the Path-A
                      verdict when that is already **more** forceful than
                      ``weaken`` (``remove``).  Basis ``abstain_to_weaken``.
``CONCUR``            ``A == B`` — accept.  Exactly the brief's first rule, and
                      it fires **before** the confidence gate, which is what
                      stops a low-confidence model from manufacturing a refusal
                      out of two paths that already agree.
``MODEL_RAISES``      ``force(B) > force(A)`` — the model found something the
                      lattice did not.  Take the model's label.  This is the one
                      cell family where the basis is ``lattice+model``, and it is
                      therefore the only place a model is *load-bearing* for a
                      refusal.
``MODEL_LOWER_IGNORED`` ``force(B) < force(A)`` — the model disagrees downward.
                      Path A stands, on its witnesses.  **This is the ratchet.**
``NEUTRAL_ACCEPTED``  both sides in the zero-force class, different members,
                      ``confidence >= theta`` — the lattice's member is the
                      verdict of record because it is the one carrying witnesses.
``NEUTRAL_UNCONFIRMED`` both sides in the zero-force class, different members,
                      ``confidence < theta`` — not an agreement, so it resolves
                      the way every unresolved thing resolves here: ``weaken``.
===================== ==========================================================

**Why the table is stated over five members and not three.**  The research text
writes the resolution over ``{weaken, strengthen, neutral}``.  The SQL enum
``mainline.control_delta`` has five members, and two of the extra ones matter:
``remove`` has force 3, so the brief's rule *"A == weaken or B == weaken =>
weaken"* would **lower** a Path-A ``remove`` to ``weaken`` if applied literally.
The table therefore takes the join in force order rather than the literal label,
which is the same rule on the three-label projection and the only extension of it
that keeps the ratchet true.  Where the letter and the invariant disagreed, the
invariant won, and the disagreement is written here rather than being quietly
resolved in code.

**What is deliberately absent.**  There is no cell whose resolution depends on
the model's rationale, its cited spans, its model id, or anything else it
returned.  Path B contributes exactly two bits of decision-relevant information —
a label and an abstention flag — plus one number that is compared against a
policy threshold.  Everything else it produces is evidence for a human, recorded
and never dispositive.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from ..contracts import ControlDelta, DeltaBasis, force

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "RESOLUTION",
    "ROWS",
    "TABLE_SHA256",
    "TABLE_VERSION",
    "ResolutionCell",
    "ResolutionKey",
    "ResolutionRule",
    "cell_for",
]

#: Bumped when any row changes.  A resolution table edit is a versioned change to
#: the meaning of every stored ``delta_basis``, not a tweak.
TABLE_VERSION: Final[str] = "ratchet.v1"

ResolutionRule = Literal[
    "ABSTENTION_FLOOR",
    "CONCUR",
    "MODEL_RAISES",
    "MODEL_LOWER_IGNORED",
    "NEUTRAL_ACCEPTED",
    "NEUTRAL_UNCONFIRMED",
]

#: ``(path_a_delta, oracle_label, confident, abstained)``.
ResolutionKey = tuple[ControlDelta, ControlDelta, bool, bool]


@dataclass(frozen=True, slots=True)
class ResolutionCell:
    """One decided cell: the delta of record, its basis, and the rule that chose it."""

    delta: ControlDelta
    basis: DeltaBasis
    rule: ResolutionRule


#: THE TABLE.  ``(A, B, confident, abstained, resolved, basis, rule)``.
#:
#: Read down the ``resolved`` column against the ``A`` column: it never moves
#: left in the force order ``{introduce, strengthen, restate} < weaken < remove``.
#: That is the whole of worker W5, and it is checkable here with a finger.
ROWS: Final[tuple[tuple[str, str, bool, bool, str, str, str], ...]] = (
    ("introduce", "introduce", True, False, "introduce", "lattice", "CONCUR"),
    ("introduce", "introduce", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "introduce", False, False, "introduce", "lattice", "CONCUR"),
    ("introduce", "introduce", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "strengthen", True, False, "introduce", "lattice", "NEUTRAL_ACCEPTED"),
    ("introduce", "strengthen", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "strengthen", False, False, "weaken", "abstain_to_weaken", "NEUTRAL_UNCONFIRMED"),
    ("introduce", "strengthen", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "restate", True, False, "introduce", "lattice", "NEUTRAL_ACCEPTED"),
    ("introduce", "restate", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "restate", False, False, "weaken", "abstain_to_weaken", "NEUTRAL_UNCONFIRMED"),
    ("introduce", "restate", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "weaken", True, False, "weaken", "lattice+model", "MODEL_RAISES"),
    ("introduce", "weaken", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "weaken", False, False, "weaken", "lattice+model", "MODEL_RAISES"),
    ("introduce", "weaken", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "remove", True, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("introduce", "remove", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("introduce", "remove", False, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("introduce", "remove", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "introduce", True, False, "strengthen", "lattice", "NEUTRAL_ACCEPTED"),
    ("strengthen", "introduce", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "introduce", False, False, "weaken", "abstain_to_weaken", "NEUTRAL_UNCONFIRMED"),
    ("strengthen", "introduce", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "strengthen", True, False, "strengthen", "lattice", "CONCUR"),
    ("strengthen", "strengthen", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "strengthen", False, False, "strengthen", "lattice", "CONCUR"),
    ("strengthen", "strengthen", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "restate", True, False, "strengthen", "lattice", "NEUTRAL_ACCEPTED"),
    ("strengthen", "restate", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "restate", False, False, "weaken", "abstain_to_weaken", "NEUTRAL_UNCONFIRMED"),
    ("strengthen", "restate", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "weaken", True, False, "weaken", "lattice+model", "MODEL_RAISES"),
    ("strengthen", "weaken", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "weaken", False, False, "weaken", "lattice+model", "MODEL_RAISES"),
    ("strengthen", "weaken", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "remove", True, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("strengthen", "remove", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("strengthen", "remove", False, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("strengthen", "remove", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "introduce", True, False, "restate", "lattice", "NEUTRAL_ACCEPTED"),
    ("restate", "introduce", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "introduce", False, False, "weaken", "abstain_to_weaken", "NEUTRAL_UNCONFIRMED"),
    ("restate", "introduce", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "strengthen", True, False, "restate", "lattice", "NEUTRAL_ACCEPTED"),
    ("restate", "strengthen", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "strengthen", False, False, "weaken", "abstain_to_weaken", "NEUTRAL_UNCONFIRMED"),
    ("restate", "strengthen", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "restate", True, False, "restate", "lattice", "CONCUR"),
    ("restate", "restate", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "restate", False, False, "restate", "lattice", "CONCUR"),
    ("restate", "restate", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "weaken", True, False, "weaken", "lattice+model", "MODEL_RAISES"),
    ("restate", "weaken", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "weaken", False, False, "weaken", "lattice+model", "MODEL_RAISES"),
    ("restate", "weaken", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "remove", True, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("restate", "remove", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("restate", "remove", False, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("restate", "remove", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "introduce", True, False, "weaken", "lattice", "MODEL_LOWER_IGNORED"),
    ("weaken", "introduce", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "introduce", False, False, "weaken", "lattice", "MODEL_LOWER_IGNORED"),
    ("weaken", "introduce", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "strengthen", True, False, "weaken", "lattice", "MODEL_LOWER_IGNORED"),
    ("weaken", "strengthen", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "strengthen", False, False, "weaken", "lattice", "MODEL_LOWER_IGNORED"),
    ("weaken", "strengthen", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "restate", True, False, "weaken", "lattice", "MODEL_LOWER_IGNORED"),
    ("weaken", "restate", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "restate", False, False, "weaken", "lattice", "MODEL_LOWER_IGNORED"),
    ("weaken", "restate", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "weaken", True, False, "weaken", "lattice", "CONCUR"),
    ("weaken", "weaken", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "weaken", False, False, "weaken", "lattice", "CONCUR"),
    ("weaken", "weaken", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "remove", True, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("weaken", "remove", True, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("weaken", "remove", False, False, "remove", "lattice+model", "MODEL_RAISES"),
    ("weaken", "remove", False, True, "weaken", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "introduce", True, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "introduce", True, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "introduce", False, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "introduce", False, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "strengthen", True, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "strengthen", True, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "strengthen", False, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "strengthen", False, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "restate", True, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "restate", True, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "restate", False, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "restate", False, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "weaken", True, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "weaken", True, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "weaken", False, False, "remove", "lattice", "MODEL_LOWER_IGNORED"),
    ("remove", "weaken", False, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "remove", True, False, "remove", "lattice", "CONCUR"),
    ("remove", "remove", True, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
    ("remove", "remove", False, False, "remove", "lattice", "CONCUR"),
    ("remove", "remove", False, True, "remove", "abstain_to_weaken", "ABSTENTION_FLOOR"),
)


def _freeze() -> Mapping[ResolutionKey, ResolutionCell]:
    """Build the frozen mapping, refusing anything the rows cannot justify.

    Three refusals happen at **import time**, so a table that cannot be trusted
    cannot be loaded: a duplicated key, a missing cell, and — the one that
    matters — a row whose resolution has lower force than its Path-A input.
    """
    table: dict[ResolutionKey, ResolutionCell] = {}
    for a_raw, b_raw, confident, abstained, resolved_raw, basis_raw, rule_raw in ROWS:
        a = ControlDelta(a_raw)
        b = ControlDelta(b_raw)
        resolved = ControlDelta(resolved_raw)
        key: ResolutionKey = (a, b, confident, abstained)
        if key in table:
            raise ValueError(f"duplicate resolution key {key}")
        if force(resolved) < force(a):
            raise ValueError(
                f"row {key} lowers the Path-A verdict from {a.value} to {resolved.value}; "
                f"the abstention ratchet forbids it"
            )
        table[key] = ResolutionCell(
            delta=resolved,
            basis=_basis(basis_raw),
            rule=_rule(rule_raw),
        )
    expected = len(ControlDelta) * len(ControlDelta) * 2 * 2
    if len(table) != expected:
        missing = [
            (a, b, c, s)
            for a in ControlDelta
            for b in ControlDelta
            for c in (True, False)
            for s in (True, False)
            if (a, b, c, s) not in table
        ]
        raise ValueError(f"resolution table is not total; {len(missing)} cells missing: {missing}")
    return table


def _basis(raw: str) -> DeltaBasis:
    if raw not in ("lattice", "lattice+model", "abstain_to_weaken", "human"):
        raise ValueError(f"{raw!r} is not a mainline.delta_basis value")
    if raw == "human":
        raise ValueError("no resolution cell may claim a human basis; a human verdict is an input")
    return raw  # type: ignore[return-value]  # narrowed by the membership test above


def _rule(raw: str) -> ResolutionRule:
    if raw not in (
        "ABSTENTION_FLOOR",
        "CONCUR",
        "MODEL_RAISES",
        "MODEL_LOWER_IGNORED",
        "NEUTRAL_ACCEPTED",
        "NEUTRAL_UNCONFIRMED",
    ):
        raise ValueError(f"{raw!r} is not a resolution rule id")
    return raw  # type: ignore[return-value]  # narrowed by the membership test above


#: The frozen table.  Built once, at import, or the module does not load.
RESOLUTION: Final[Mapping[ResolutionKey, ResolutionCell]] = _freeze()


def _digest() -> str:
    """SHA-256 over the rows, in file order, length-prefixed per field.

    Carried onto every silence record so that retro-tuning the resolution is
    visible in the same way decision D11 makes retro-tuning the matcher visible.
    Length prefixes rather than a separator: ``("a","bc")`` and ``("ab","c")``
    must not hash alike, and a delimiter that can appear in a field is not a
    delimiter.
    """
    digest = hashlib.sha256()
    digest.update(TABLE_VERSION.encode("utf-8"))
    for row in ROWS:
        for field in row:
            token = str(field).encode("utf-8")
            digest.update(len(token).to_bytes(4, "big"))
            digest.update(token)
    return digest.hexdigest()


#: Content address of :data:`ROWS`.  Written into every silence record.
TABLE_SHA256: Final[str] = _digest()


def cell_for(
    path_a: ControlDelta,
    oracle_label: ControlDelta,
    *,
    confident: bool,
    abstained: bool,
) -> ResolutionCell:
    """Look one cell up.

    Raises:
        KeyError: never, in practice — :func:`_freeze` proved totality at import.
            The lookup is written without a ``.get`` default on purpose: a
            default here would be a sixth rule that nobody wrote down.
    """
    return RESOLUTION[(path_a, oracle_label, confident, abstained)]
