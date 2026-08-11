# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Static checks on the DIRECTRIX view's producer.  No cluster, no driver, runs everywhere.

WHY THIS FILE IS STILL CALLED ``test_0207_shape.py``
----------------------------------------------------
Because ``0207`` is a **revoked address**, and this module is now the thing that
keeps it revoked.

The algorithms lead originally allocated itself the migration band ``0200-0219``
and wrote the DIRECTRIX view into it as ``0207_v_safe_direction_current.sql``.
`verticals/mainline/db/migrations.allocation.toml` revoked that annexe (MR-7):
``0200`` and above is ``UNALLOCATED``, no file may use it in either mode, and
``trappoint migrate lint`` rule B refuses a file that claims a number no band
grants.  The three algorithms files moved — ``0205 -> 0049a``, ``0207 -> 0150``,
``0211 -> 0140 + 0145`` — recorded in ``docs/leads/migration-reconciliation.md``
§5.4 and in the relocated file's own header.

So there is **no missing producer here**.  The producer exists, at
``verticals/mainline/db/migrations/0150_v_safe_direction_current.sql``, and it
has been applied against a real cluster: ``evidence/chain/chain-20260810T062542Z.json``
records ``0150_v_safe_direction_current`` in ``applied_versions``, 271 of 271
applied, 0 failed, against CockroachDB CCL v26.2.5.  What was missing was a
suite that had been told.  Until this rewrite, eight tests in this file each
raised ``RuntimeError: migration 0207 is missing`` — eight restatements of one
stale number — and one of them printed ``more than one file claims 0207: []``,
a sentence that reports the opposite of what happened.

This module therefore does two jobs before it does anything else:

* **ONE declaration** —
  :func:`test_the_producer_of_the_directrix_view_exists_at_its_allocated_address`
  resolves the producer by the object it creates rather than by a number.  If it
  is ever absent, exactly one test fails, and its message names the path, the
  band, the invariants the file satisfies and the domain that owes it.  The other
  seven are guarded behind it so an absence is reported once.
* **The revocation is enforced** —
  :func:`test_the_revoked_0207_address_is_still_empty_and_unallocated`
  fails if anybody re-creates a ``0207`` file, or if the allocation TOML stops
  saying that ``0200+`` has no owner.  A number space with no owner is what
  produced two conventions in the first place (MRR-7).

WHAT THE REMAINING SEVEN ARE FOR
--------------------------------
Band discipline: one statement, a header that cites its band, its invariants and
its sources, forward-only.  Cheap, and it is the check that would catch a
migration quietly acquiring a second statement.

And the one that earns the file.  The view extracts every field from the clause
text with ``split_part`` on literal labels — ``'Parameter: '``, ``'Direction: '``
— and those labels are defined in :mod:`mainline_domain.registry.encoding`.
Nothing in SQL knows that.  If the grammar is ever changed on the Python side,
the view keeps applying, keeps returning rows, and silently reports every
``parameter_key`` as the empty string with ``answers`` false — which reads
exactly like a site that has ratified nothing.  So the labels are cross-checked
here, against the encoder, by encoding a real entry and confirming that the
literals the SQL searches for occur in it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _directrix_support import MIGRATIONS_DIR, split_statements
from mainline_domain.registry import (
    RATIFIABLE_DIRECTIONS,
    EntryStatus,
    SafeDirection,
    encode,
)
from mainline_domain.registry.doc import DOC_CODE
from mainline_domain.registry.encoding import PREAMBLE

# ── the producer, named by object rather than by number ──────────────────────
#
# Resolved by the object it creates.  A number is an address and addresses get
# reallocated; `mainline.v_safe_direction_current` is the thing the algorithm
# actually depends on, and it is what the manifest, the console and the operator
# name.

VIEW_OBJECT = "mainline.v_safe_direction_current"
PRODUCER_STEM = "v_safe_direction_current"

#: The address `migrations.allocation.toml` grants this file, verbatim from the
#: band whose `contents` names it: `mainline.* business views;
#: v_safe_direction_current = 0150`.
ALLOCATED_ADDRESS = "0150"
ALLOCATED_BAND = "0150-0154z"
ALLOCATED_PATH = f"verticals/mainline/db/migrations/{ALLOCATED_ADDRESS}_{PRODUCER_STEM}.sql"

#: The address the algorithms lead used before MR-7 revoked the whole 0200+ space.
REVOKED_ADDRESS = "0207"

#: The domain that owes this artefact if it is ever absent.  R3 of
#: `docs/leads/ci-finish-final.md`: an intentional red must name its missing
#: artefact AND the desk it is on.
OWNING_DOMAIN = "algorithms — docs/leads/algorithms.md §2 (DIRECTRIX) and §9"

ALLOCATION_TOML = MIGRATIONS_DIR.parent / "migrations.allocation.toml"

#: The single sentence a reader gets when the producer is gone.  Written once,
#: used by the declaration and quoted by the guard, so the two can never drift.
MISSING_PRODUCER_DECLARATION = f"""
MISSING PRODUCER: {ALLOCATED_PATH}
  object:      CREATE VIEW {VIEW_OBJECT}
  band:        {ALLOCATED_BAND} · algorithms · AUTHORED, allocated by
               verticals/mainline/db/migrations.allocation.toml, whose `contents` line for
               that band reads "mainline.* business views; v_safe_direction_current = 0150"
  invariants:  MI22 — the gate fails closed on a stale or absent projection.
               I06  — a dependency a gate consumes is COMPUTED, never declared.
  owner:       {OWNING_DOMAIN}
  NOT at {REVOKED_ADDRESS}: the algorithms 0200-0219 annexe is revoked (MR-7). 0200 and above is
               UNALLOCATED and `trappoint migrate lint` rule B refuses a file that claims a
               number no band grants. See docs/leads/migration-reconciliation.md §5.4.
  what it would do: project the REG-SAFE-DIRECTION clauses at clause.head_commit into a
               readable per-parameter row for the console and the operator. It refuses
               nothing; it is a view, and it is NOT what the gate reads.
""".strip()

_GUARD_REASON = (
    "SKIP(declared-once): the DIRECTRIX view has no producer, which is declared exactly once "
    "by test_the_producer_of_the_directrix_view_exists_at_its_allocated_address in this module. "
    "Read that failure. Eight shape assertions restating one absence tell a reader the same "
    "thing eight times and the owning domain zero times."
)

#: The two tests that must run even when the producer is absent — they are the
#: ones whose whole job is to say so.
_DECLARATIONS = frozenset(
    {
        "test_the_producer_of_the_directrix_view_exists_at_its_allocated_address",
        "test_the_revoked_0207_address_is_still_empty_and_unallocated",
    }
)


def producers() -> list[Path]:
    """Every migration that claims to create the DIRECTRIX view, by filename."""
    return sorted(MIGRATIONS_DIR.glob(f"*_{PRODUCER_STEM}.sql"))


def producer() -> Path:
    found = producers()
    assert len(found) == 1, MISSING_PRODUCER_DECLARATION
    return found[0]


def migration_text() -> str:
    return producer().read_text(encoding="utf-8")


def code_of(statement: str) -> str:
    """A statement with its leading ``--`` comment lines removed.

    The splitter keeps comments attached to the statement that follows them, so
    a file whose header is longer than its SQL — which this one is, deliberately —
    has one statement that begins with a hundred lines of prose.
    """
    lines = [line for line in statement.splitlines() if not line.lstrip().startswith("--")]
    return "\n".join(lines).strip()


@pytest.fixture(autouse=True)
def _one_declaration_not_eight(request: pytest.FixtureRequest) -> None:
    """Guard the shape suite behind the declaration.

    This is not a skip taken to obtain a green: when the producer is absent the
    declaration above is RED and names the artefact and its owner. The guard
    exists so that one missing file produces one sentence a reader can act on
    instead of eight copies of the same stack trace.
    """
    if request.node.name in _DECLARATIONS:
        return
    if not producers():
        pytest.skip(_GUARD_REASON)


# --------------------------------------------------------------------------- #
# The declaration, and the revocation it rests on                              #
# --------------------------------------------------------------------------- #


def test_the_producer_of_the_directrix_view_exists_at_its_allocated_address() -> None:
    """Exactly one file creates the DIRECTRIX view, and it sits where the TOML says."""
    found = producers()
    assert found, MISSING_PRODUCER_DECLARATION
    assert len(found) == 1, (
        f"{len(found)} files claim to create {VIEW_OBJECT}: {[p.name for p in found]}. "
        f"The allocation grants {PRODUCER_STEM} exactly one address, {ALLOCATED_ADDRESS}; a "
        "second producer means two definitions of the same view and a deploy whose result "
        f"depends on apply order. Owner: {OWNING_DOMAIN}."
    )

    only = found[0]
    assert only.name == f"{ALLOCATED_ADDRESS}_{PRODUCER_STEM}.sql", (
        f"{VIEW_OBJECT} is produced by {only.name}, but "
        "verticals/mainline/db/migrations.allocation.toml grants it "
        f"{ALLOCATED_ADDRESS} in band {ALLOCATED_BAND} and names it in that band's `contents`. "
        f"Owner: {OWNING_DOMAIN}."
    )

    # Forward-only below the protected floor: no reverse migration, ever.
    assert not list(MIGRATIONS_DIR.glob(f"{ALLOCATED_ADDRESS}_*.down.sql")), (
        f"a .down.sql exists at {ALLOCATED_ADDRESS}; the band is forward-only below the "
        "protected floor (DM-14)"
    )


def test_the_revoked_0207_address_is_still_empty_and_unallocated() -> None:
    """0207 was this view's address until MR-7 revoked the entire 0200+ space.

    Two ways this can rot, and both are silent. Somebody re-creates a 0207 file
    because a plan document still says 0207 — `trappoint migrate lint` rule B
    would refuse it, but a test that says why is cheaper than a lint failure a
    reader has to go and interpret. Or the allocation TOML quietly grows an owner
    for 0200+, at which point the number space that produced two conventions is
    open again.
    """
    squatters = sorted(MIGRATIONS_DIR.glob(f"{REVOKED_ADDRESS}*"))
    assert not squatters, (
        f"{[p.name for p in squatters]} claim migration number {REVOKED_ADDRESS}, which no band "
        "grants. verticals/mainline/db/migrations.allocation.toml records 0200-9999z as "
        'owner = "UNALLOCATED", mode = "unallocated", and the algorithms 0200-0219 annexe as '
        f"revoked (MR-7). {VIEW_OBJECT} lives at {ALLOCATED_PATH}. "
        f"Owner: {OWNING_DOMAIN}."
    )

    assert ALLOCATION_TOML.is_file(), (
        f"{ALLOCATION_TOML} does not exist, so no band grants any number and every migration "
        "in this tree is unaddressed. Owner: the migration-reconciliation lead — "
        "docs/leads/migration-reconciliation.md."
    )
    allocation = ALLOCATION_TOML.read_text(encoding="utf-8")
    assert 'owner = "UNALLOCATED"' in allocation, (
        "verticals/mainline/db/migrations.allocation.toml no longer declares an UNALLOCATED "
        "terminal band. A number space with no owner is exactly what produced two conventions "
        "(MRR-7), and reopening 0200+ is how this view came to be written at 0207."
    )
    assert f"{PRODUCER_STEM} = {ALLOCATED_ADDRESS}" in allocation, (
        f"the allocation TOML no longer names `{PRODUCER_STEM} = {ALLOCATED_ADDRESS}` in any "
        "band's `contents`. The address is then a convention rather than a grant, and the next "
        f"worker has nothing to read. Owner: {OWNING_DOMAIN}."
    )


# --------------------------------------------------------------------------- #
# Band discipline                                                              #
# --------------------------------------------------------------------------- #


def test_the_migration_is_exactly_one_statement() -> None:
    """The deployed runner applies one statement per file (§18)."""
    statements = split_statements(migration_text())
    assert len(statements) == 1, (
        f"{producer().name} carries {len(statements)} statements; the header declares 1"
    )
    assert code_of(statements[0]).upper().startswith("CREATE VIEW")


def test_the_header_declares_what_the_band_requires() -> None:
    text = migration_text()
    for field in ("migration:", "domain:", "band:", "statements:", "invariants:", "source:"):
        assert field in text, f"{producer().name}'s header has no `{field}` line"
    assert "MI22" in text and "I06" in text, f"{producer().name} does not cite its invariants"
    assert "forward-only" in text
    assert "migrations.allocation.toml" in text, (
        f"{producer().name}'s `band:` line does not cite "
        "verticals/mainline/db/migrations.allocation.toml. A band nobody granted is the "
        "condition MR-7 exists to end."
    )


def test_the_view_name_and_schema_are_the_reserved_ones() -> None:
    text = migration_text()
    assert f"CREATE VIEW {VIEW_OBJECT}" in text
    assert f"'{DOC_CODE}'" in text, f"{producer().name} does not filter on the registry doc_code"


def test_the_sql_labels_match_the_python_grammar() -> None:
    """The cross-language join that nothing else checks.

    A grammar change on the Python side leaves this view applying cleanly and
    returning empty strings for every field — indistinguishable, in the console,
    from a site that has ratified nothing.
    """
    text = migration_text()
    sample = encode(
        parameter="max_operating_pressure",
        dimension_label="pressure",
        direction=SafeDirection.LOWER_IS_SAFER,
        status=EntryStatus.RATIFIED,
        rationale="a rationale long enough to be worth disagreeing with",
    )

    literals = re.findall(r"split_part\(\s*(?:split_part\(\s*)?cv\.canon_text,\s*'([^']+)'", text)
    assert literals, f"{producer().name} does not extract anything from cv.canon_text"
    for literal in literals:
        assert literal in sample, (
            f"{producer().name} searches the clause text for {literal!r}, which the encoder does "
            "not emit. The view would apply cleanly and return empty fields forever."
        )

    for label in ("Parameter: ", "Dimension: ", "Direction: ", "Status: ", "Rationale: "):
        assert label in literals, f"{producer().name} does not extract the {label.strip()} field"

    assert PREAMBLE in text, (
        f"{producer().name}'s `answers` column does not test the clause preamble, so a clause "
        "that is not a registry entry could report as one"
    )


def test_every_ratifiable_direction_is_named_in_the_answers_predicate() -> None:
    """A direction the Python side can ratify and the view does not know reads as false.

    That is fail-closed and therefore not dangerous, but it is a disagreement
    between the operator's view of the live registry and the algorithm's, and the
    two must not drift apart quietly.
    """
    text = migration_text()
    for direction in RATIFIABLE_DIRECTIONS:
        assert f"'{direction.value}'" in text, (
            f"{producer().name} does not recognise {direction.value}; the view would report a "
            "ratified parameter as not answering"
        )
    assert f"'{SafeDirection.ABSTAIN.value}'" not in text, (
        f"{producer().name} treats ABSTAIN as a direction a clause may carry; it is what the "
        "registry answers when no clause applies and must never be ratifiable"
    )


def test_the_migration_says_out_loud_that_it_is_not_what_the_gate_reads() -> None:
    """A header that omits this invites somebody to wire rule R2 to the view.

    Which would make every historical verdict re-computable under a registry that
    has since moved — the retro-tuning attack, rebuilt in a different column.
    """
    text = migration_text()
    assert "IT IS NOT WHAT THE GATE READS" in text
    assert "AS OF THE COMMIT UNDER TEST" in text
    assert "load_registry" in text


def test_the_migration_claims_no_refusal_it_does_not_implement() -> None:
    """A view has no CHECK, no trigger and no SQLSTATE, and the header must say so."""
    text = migration_text()
    assert "sqlstate:   none" in text
    statement = code_of(split_statements(text)[0]).upper()
    for forbidden in ("CHECK (", "CREATE TRIGGER", "RAISE "):
        assert forbidden not in statement, (
            f"{producer().name}'s statement contains {forbidden!r}; this file creates a view "
            "and claims no refusal"
        )
