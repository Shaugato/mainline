# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The conservation laws, as SQL that runs after every generated step.

``ARCHITECTURE.md`` §16.1 states three of them and every one is a counting assertion —
which is why they are cheap enough to evaluate after *each* step of a hundred-step
history rather than once at the end. An invariant that broke at step 7 and was repaired
by step 40 is a gate that was open for thirty-three steps, and a check that only runs at
the end cannot tell you that.

======  =============================================================  ==============
Law     Statement                                                      Here
======  =============================================================  ==============
**L1**  a completion record exists ⟹ it is pinned to the subject's     ``L1-pin`` ·
        current epoch and no obligation of that subject is open        ``L1-gate``
**L2**  every ancestor clause at severity ≥ 4 is matched or carries    ``L2-blame``
        an ``identity_residue`` row — never neither
**L3**  ``generated = blocking + advisory + silenced + deduped``,      ``L3-silence``
        exactly partitioned
======  =============================================================  ==============

**L2 and L3 are NOT ASSERTED against the reference vertical, and this module says so out
loud.** Their relations (``identity_residue``, ``silence_ledger``) belong to the ancestry
and recall domains and the reference vertical does not carry them, so :func:`check_all`
returns them in its ``not_applicable`` list. A green tick for a law nobody evaluated is
the single worst thing an assurance pack can contain.

Four structural invariants ride alongside, and they are the detectors for a mechanism
that silently stopped firing:

``no-fork``
    the ``permit_event`` chain is a chain, not a tree.
``counter-fidelity``
    the projected counter equals the derivation it claims to summarise, on the
    *retraction* predicate. It deliberately does **not** compare against the
    time-conditioned anti-join: an expired verdict decrements the counter and stops
    covering the obligation, so the two disagree BY DESIGN and that disagreement is
    exactly what ``fn_permit_merge_gate`` refuses on.
``drift-direction``
    the one-sided bound that makes the above safe — the live derivation is never
    *smaller* than the counter. Smaller would mean an obligation was cleared without the
    counter learning, which is the direction that lets a merge through.
``ledger-density`` / ``ledger-link``
    ``seq`` is gap-free from 1 and every ``prev_seq`` is its own predecessor. Gap-free by
    compare-and-swap is the whole reason ``CREATE SEQUENCE`` is banned repository-wide: a
    gap MEANS tampering, so a gap nobody looks for means nothing.

**One round trip.** :func:`check_all` fuses every applicable law into a single
``UNION ALL`` so that checking after every step costs one statement rather than seven.
The laws are declared once, in :data:`LAWS`, and both the fused query and the individual
accessors are built from that one declaration — so a law cannot be in the fused query and
absent from the accessor, or the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import psycopg

from .refschema import SCHEMA

__all__ = [
    "LAWS",
    "NOT_APPLICABLE",
    "Violation",
    "check_all",
    "l1_gate",
    "run_law",
]

#: Returned by a law whose relations this binding does not carry. Never a pass.
NOT_APPLICABLE: Final = "not-applicable"


@dataclass(frozen=True, slots=True)
class Violation:
    """One conservation-law failure, with enough of the row to start an investigation."""

    law: str
    detail: str

    def __str__(self) -> str:
        """Return the one line a failing property test prints."""
        return f"{self.law}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Law:
    """A named predicate that returns one ``detail`` string per violating row.

    Attributes:
        name: the label a violation carries.
        sql: a ``SELECT`` of exactly one STRING column. Empty result means the law holds.
        needs: relations this law requires, as ``(schema, table)``. A law whose relations
            are absent is NOT APPLICABLE — never passed.
    """

    name: str
    sql: str
    needs: tuple[tuple[str, str], ...] = ()


# The anti-join the substrate itself uses, verbatim, in both its forms. `_LIVE` carries
# the time condition the merge gate re-derives with; `_UNRETRACTED` is what the counter
# is maintained against.
_LIVE = (
    f"NOT EXISTS (SELECT 1 FROM {SCHEMA}.disposition d "  # noqa: S608
    f" WHERE d.check_id = bc.check_id AND d.retracted_by IS NULL "
    f"   AND (d.expires_at IS NULL OR d.expires_at > now()))"
)
_UNRETRACTED = (
    f"NOT EXISTS (SELECT 1 FROM {SCHEMA}.disposition d "  # noqa: S608
    f" WHERE d.check_id = bc.check_id AND d.retracted_by IS NULL)"
)

LAWS: Final[tuple[Law, ...]] = (
    Law(
        "L1-pin",
        f"SELECT 'subject ' || mr.subject_id::STRING || ' merged at epoch ' "  # noqa: S608
        f"    || mr.gate_epoch::STRING || ' but the subject now reads ' "
        f"    || p.gate_epoch::STRING || ': the epoch moved under a completion record' "
        f"  FROM {SCHEMA}.merge_record mr "
        f"  JOIN {SCHEMA}.permit p ON p.permit_id = mr.permit_id "
        f" WHERE p.gate_epoch <> mr.gate_epoch",
    ),
    Law(
        "L1-gate",
        f"SELECT 'subject ' || mr.subject_id::STRING || ' carries a completion record and ' "  # noqa: S608
        f"    || (SELECT count(*) FROM {SCHEMA}.blocking_check bc "
        f"         WHERE bc.permit_id = mr.permit_id AND {_LIVE})::STRING "
        f"    || ' open obligation(s): the gate admitted a write it exists to refuse' "
        f"  FROM {SCHEMA}.merge_record mr "
        f" WHERE mr.permit_id IS NOT NULL "
        f"   AND EXISTS (SELECT 1 FROM {SCHEMA}.blocking_check bc "
        f"                WHERE bc.permit_id = mr.permit_id AND {_LIVE})",
    ),
    Law(
        "L2-blame",
        f"SELECT 'clause ' || c.clause_uuid::STRING || ' at severity ' "  # noqa: S608
        f"    || c.max_severity::STRING || ' is neither matched nor residued' "
        f"  FROM {SCHEMA}.clause_blame_current c "
        f" WHERE c.max_severity >= 4 "
        f"   AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.blocking_check bc "
        f"        WHERE bc.clause_uuid = c.clause_uuid AND bc.commit_id = c.as_of_commit) "
        f"   AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.identity_residue ir "
        f"        WHERE ir.clause_uuid = c.clause_uuid)",
        needs=((SCHEMA, "identity_residue"),),
    ),
    Law(
        "L3-silence",
        f"SELECT 'run ' || run_id::STRING || ': generated ' "  # noqa: S608
        f"    || candidates_generated::STRING || ' but the partition sums to ' "
        f"    || (blocking_count + advisory_count + silenced_count + deduped_count)::STRING "
        f"  FROM {SCHEMA}.silence_ledger "
        f" WHERE candidates_generated <> "
        f"       blocking_count + advisory_count + silenced_count + deduped_count",
        needs=((SCHEMA, "silence_ledger"),),
    ),
    Law(
        "no-fork",
        f"SELECT 'subject ' || permit_id::STRING || ' has ' || count(*)::STRING "  # noqa: S608
        f"    || ' events claiming prev_seq=' || prev_seq::STRING || ': the chain forked' "
        f"  FROM {SCHEMA}.permit_event "
        f" GROUP BY permit_id, prev_seq HAVING count(*) > 1",
    ),
    Law(
        "counter-fidelity",
        f"SELECT 'subject ' || p.permit_id::STRING || ': open_blocking reads ' "  # noqa: S608
        f"    || p.open_blocking::STRING || ', the derivation is ' || x.n::STRING "
        f"  FROM {SCHEMA}.permit p, LATERAL ("
        f"    SELECT count(*) AS n FROM {SCHEMA}.blocking_check bc "
        f"     WHERE bc.permit_id = p.permit_id AND {_UNRETRACTED}) AS x "
        f" WHERE x.n <> p.open_blocking",
    ),
    Law(
        "drift-direction",
        f"SELECT 'subject ' || p.permit_id::STRING || ': the live derivation is ' "  # noqa: S608
        f"    || x.n::STRING || ' but the counter reads ' || p.open_blocking::STRING "
        f"    || ' — an obligation was cleared without the counter moving' "
        f"  FROM {SCHEMA}.permit p, LATERAL ("
        f"    SELECT count(*) AS n FROM {SCHEMA}.blocking_check bc "
        f"     WHERE bc.permit_id = p.permit_id AND {_LIVE}) AS x "
        f" WHERE x.n < p.open_blocking",
    ),
    Law(
        "ledger-density",
        f"SELECT 'subject ' || permit_id::STRING || ': ' || count(*)::STRING "  # noqa: S608
        f"    || ' events but seq runs to ' || max(seq)::STRING || ' — the chain has a gap' "
        f"  FROM {SCHEMA}.permit_event "
        f" GROUP BY permit_id HAVING count(*) <> max(seq)",
    ),
    Law(
        "ledger-link",
        f"SELECT 'subject ' || permit_id::STRING || ': event ' || seq::STRING "  # noqa: S608
        f"    || ' declares prev_seq=' || prev_seq::STRING "
        f"  FROM {SCHEMA}.permit_event WHERE prev_seq <> seq - 1",
    ),
)

_APPLICABILITY: dict[int, dict[str, bool]] = {}


def _applicable(conn: psycopg.Connection[Any], law: Law) -> bool:
    """Whether *law*'s relations exist. Cached per connection: schemas do not move."""
    cache = _APPLICABILITY.setdefault(id(conn), {})
    if law.name not in cache:
        present = True
        for schema, table in law.needs:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s",
                    (schema, table),
                )
                row = cur.fetchone()
            present = present and bool(row and row[0])
        cache[law.name] = present
    return cache[law.name]


def run_law(conn: psycopg.Connection[Any], name: str) -> list[Violation] | str:
    """Run one law by name.

    Returns:
        Its violations, or :data:`NOT_APPLICABLE` when this binding lacks its relations.

    Raises:
        KeyError: no law by that name.
    """
    law = next((entry for entry in LAWS if entry.name == name), None)
    if law is None:
        raise KeyError(f"no such law: {name}. Known: {[entry.name for entry in LAWS]}")
    if not _applicable(conn, law):
        return NOT_APPLICABLE
    with conn.cursor() as cur:
        cur.execute(law.sql)
        return [Violation(law.name, str(row[0])) for row in cur.fetchall()]


def l1_gate(conn: psycopg.Connection[Any]) -> list[Violation]:
    """L1 in both halves: the pin held, and no merged subject carries an open obligation."""
    found: list[Violation] = []
    for name in ("L1-pin", "L1-gate"):
        outcome = run_law(conn, name)
        # S101: a test instrument. L1 declares no optional relations, so a string here
        # would mean `LAWS` was edited to make the product's headline law skippable.
        assert isinstance(outcome, list), (  # noqa: S101
            "L1 has no optional relations and is always applicable"
        )
        found.extend(outcome)
    return found


def check_all(conn: psycopg.Connection[Any]) -> tuple[list[Violation], list[str]]:
    """Every applicable law, in ONE statement.

    Returns:
        ``(violations, not_applicable)`` — the second element names the laws whose
        relations this binding does not carry, so a caller prints them rather than
        reporting a pass nobody earned.
    """
    applicable = [law for law in LAWS if _applicable(conn, law)]
    skipped = [law.name for law in LAWS if law not in applicable]
    fused = " UNION ALL ".join(
        f"SELECT '{law.name}' AS law, x.detail FROM ({law.sql}) AS x(detail)"  # noqa: S608
        for law in applicable
    )
    with conn.cursor() as cur:
        cur.execute(fused)
        violations = [Violation(str(law), str(detail)) for law, detail in cur.fetchall()]
    return violations, skipped
