# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Static checks on the guard: ``0140`` (the function) and ``0145`` (the trigger).

No cluster, no driver, runs everywhere — which is the point.  ``test_witness_or_refuse``
proves the refusal *happens*; if no cluster is reachable it skips, and a skip
verifies nothing.  These checks are what still holds on a machine with no Docker
daemon, and they are chosen to be the ones a cluster run would not notice:

* **The split held.**  ``0211`` was one file declaring ``statements: 2``, carrying
  a ``CREATE FUNCTION`` in a range §18 never defined.  It is now one statement in
  the function band and one in the trigger band, ordered ``0049a < 0140 < 0145``
  so every dependency points backwards.  A cluster run passes just as happily
  with both statements crammed back into one file — right up to the day one half
  applies and the operator cannot tell which.

* **The exact refusal strings.**  Pinned as literals in three independent places:
  ``_lattice_sql_support``, the SQL, and (in the cluster suite) the ``psycopg``
  error.  Two would be a tautology — a test that reads a string out of a file and
  compares it to itself passes for any string, including the empty one.

* **Decision D10, checked rather than asserted.**  CockroachDB v26.2 does not
  document the firing order of multiple row-level triggers on one table, so the
  guard is written to read **only** columns the INSERT itself supplies.  A
  cluster run cannot see the difference — with one trigger on the table there is
  no order to get wrong.  Reading the function body can.

* **The scoping of the exemptions.**  ``abstain_to_weaken`` and ``human`` are
  exempt; ``lattice+model`` is not.  Those three facts are the whole of P7 at this
  gate, and each is one deleted line away from being untrue.
"""

from __future__ import annotations

import re
import tomllib

from _lattice_sql_support import (
    MIGRATIONS_DIR,
    NO_MINIMAL_WITNESS_MESSAGE,
    OWNED_MIGRATIONS,
    WITNESSLESS_WEAKEN_MESSAGE,
    code_of,
    migration,
    split_statements,
)

FUNCTION_MIGRATION = OWNED_MIGRATIONS[1]
TRIGGER_MIGRATION = OWNED_MIGRATIONS[2]

FUNCTION_NAME = "mainline.fn_delta_witness_guard"
TRIGGER_NAME = "z_delta_witness_required"

FILENAME_RE = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")


def text_of(name: str) -> str:
    return migration(name).read_text(encoding="utf-8")


def body_of(name: str) -> str:
    statements = split_statements(text_of(name))
    assert len(statements) == 1, f"{name} carries {len(statements)} statements; 1 is the rule"
    return code_of(statements[0])


def band_of(stem: str) -> dict[str, str] | None:
    path = MIGRATIONS_DIR.parent / "migrations.allocation.toml"
    for band in tomllib.loads(path.read_bytes().decode("utf-8"))["band"]:
        if band["first"] <= stem <= band["last"]:
            return band
    return None


# ── the split ────────────────────────────────────────────────────────────────


def test_each_file_is_exactly_one_statement_of_the_right_kind() -> None:
    assert body_of(FUNCTION_MIGRATION).upper().startswith("CREATE FUNCTION")
    assert body_of(TRIGGER_MIGRATION).upper().startswith("CREATE TRIGGER")


def test_the_function_is_in_the_function_band_and_the_trigger_in_the_trigger_band() -> None:
    """§18 stratifies tables, then functions, then triggers.  ``0211`` was in no stratum."""
    function_band = band_of(FUNCTION_MIGRATION[: -len(".sql")])
    trigger_band = band_of(TRIGGER_MIGRATION[: -len(".sql")])
    assert function_band is not None, f"{FUNCTION_MIGRATION} falls in no allocated band"
    assert trigger_band is not None, f"{TRIGGER_MIGRATION} falls in no allocated band"
    assert "algorithms" in function_band["owner"], function_band
    assert "algorithms" in trigger_band["owner"], trigger_band
    assert function_band["mode"] == "authored"
    assert trigger_band["mode"] == "authored"
    assert "function" in function_band["contents"]
    assert "trigger" in trigger_band["contents"]


def test_the_apply_order_puts_every_dependency_backwards() -> None:
    """``0049a`` (table) < ``0140`` (function) < ``0145`` (trigger), lexicographically.

    The runner orders on the whole filename stem, so this is the comparison that
    decides the real apply order and not an approximation of it.
    """
    table, function, trigger = OWNED_MIGRATIONS
    assert table < function < trigger, (table, function, trigger)
    for name in OWNED_MIGRATIONS:
        assert FILENAME_RE.match(name), name
    assert not list(MIGRATIONS_DIR.glob("014[05]_*.down.sql"))
    assert not list(MIGRATIONS_DIR.glob("014[05]_*.up.sql"))


def test_the_two_halves_name_each_other() -> None:
    """A function nothing calls refuses nothing, and a trigger with no function will not create.

    The two files are useless apart and each must say so, because the failure of
    applying only one of them is silent in exactly one direction: the function
    alone leaves ``clause_version`` unguarded and every test that does not check
    for the refusal still passes.
    """
    assert "0145" in text_of(FUNCTION_MIGRATION)
    assert "0140" in text_of(TRIGGER_MIGRATION)
    assert FUNCTION_NAME in body_of(TRIGGER_MIGRATION)


def test_both_headers_carry_the_four_linted_keys() -> None:
    for name in (FUNCTION_MIGRATION, TRIGGER_MIGRATION):
        text = text_of(name)
        for key in ("MI:", "I:", "COUNSEL-GATED:", "RATIONALE:"):
            assert key in text, f"{name}'s header has no `{key}` line"
        assert "I14" in text, f"{name} does not cite I14"
        assert "MI22" in text, f"{name} does not cite MI22"
        assert "forward-only" in text
        assert "@rendered-by" not in text, f"{name} is authored, not rendered"


# ── the exact refusals ───────────────────────────────────────────────────────


def test_the_function_raises_the_two_pinned_messages_and_nothing_else() -> None:
    body = body_of(FUNCTION_MIGRATION)
    assert WITNESSLESS_WEAKEN_MESSAGE in body, (
        "the first refusal's wording has changed. It is pinned in three places on "
        "purpose; change the SQL and this test, and expect the change to be argued for"
    )
    assert NO_MINIMAL_WITNESS_MESSAGE in body
    raises = re.findall(r"RAISE\s+EXCEPTION", body, re.IGNORECASE)
    assert len(raises) == 2, f"the guard raises {len(raises)} times; the header declares 2"
    errcodes = set(re.findall(r"ERRCODE\s*=\s*'([^']+)'", body))
    assert errcodes == {"P0001"}, errcodes


def test_the_two_messages_are_distinct_because_the_two_defects_are() -> None:
    """No witnesses at all, and witnesses with no minimal member, are different bugs.

    Folding them into one message costs the writer an hour: a refusal that tells
    somebody the wrong thing is worse than one that tells them nothing.
    """
    assert WITNESSLESS_WEAKEN_MESSAGE != NO_MINIMAL_WITNESS_MESSAGE
    assert not NO_MINIMAL_WITNESS_MESSAGE.startswith(WITNESSLESS_WEAKEN_MESSAGE)


def test_the_trigger_file_reproduces_both_messages_for_its_reader() -> None:
    """The file that decides whether a refusal is ever reached should state it."""
    text = text_of(TRIGGER_MIGRATION)
    assert WITNESSLESS_WEAKEN_MESSAGE in text
    assert NO_MINIMAL_WITNESS_MESSAGE in text


# ── decision D10: nothing here depends on firing order ───────────────────────


def test_the_guard_reads_only_columns_the_insert_supplies() -> None:
    """D10.  A cluster with one trigger on the table cannot see this; the body can.

    Every ``(NEW).x`` the function reads must be a column the writer supplies on
    the INSERT.  If it ever read a column another trigger *projects* — ``sev_max``,
    ``blood_root``, ``gen`` — its answer would depend on an ordering CockroachDB
    v26.2 does not document, and PL-3 forbids a dated path resting on that.
    """
    body = body_of(FUNCTION_MIGRATION)
    read = set(re.findall(r"\(NEW\)\.([a-z_]+)", body))
    supplied = {"control_delta", "delta_basis", "clause_uuid", "commit_id"}
    assert read <= supplied, (
        f"the guard reads {sorted(read - supplied)}, which no writer supplies on the "
        "INSERT. A projected column makes this trigger's answer depend on firing order, "
        "which v26.2 does not document (decision D10)"
    )
    assert "(OLD)" not in body, "an INSERT trigger has no OLD"


def test_the_guard_reads_no_table_but_its_own_witnesses() -> None:
    """A gate that joins to a third table acquires that table's write ordering too."""
    body = body_of(FUNCTION_MIGRATION)
    referenced = set(re.findall(r"FROM\s+(mainline\.[a-z_]+)", body, re.IGNORECASE))
    assert referenced == {"mainline.delta_witness"}, referenced


def test_the_old_and_new_records_are_parenthesised() -> None:
    """CockroachDB requires ``(NEW).col``; the unparenthesised PostgreSQL form is refused.

    §5.11 of the architecture is written in the PostgreSQL style, so every trigger
    in this deployment needs the correction and a copy-paste from the spec would
    fail at ``CREATE FUNCTION`` time — but only on a cluster, and only if one is
    reachable.
    """
    body = body_of(FUNCTION_MIGRATION)
    assert not re.search(r"(?<!\()\bNEW\.[a-z_]", body), (
        "an unparenthesised NEW.column reference; CockroachDB v26.2 requires (NEW).column"
    )


def test_the_trigger_is_before_insert_for_each_row() -> None:
    """BEFORE, so the state never forms (MI22).  FOR EACH ROW, so there is a ``NEW`` to read.

    An AFTER trigger that raises rolls the statement back too — but it has let the
    row exist and be re-read by anything firing in between, and MI22's claim is
    that the state never forms at all.
    """
    body = body_of(TRIGGER_MIGRATION)
    assert re.search(
        rf"CREATE\s+TRIGGER\s+{TRIGGER_NAME}\s+BEFORE\s+INSERT\s+ON\s+mainline\.clause_version",
        body,
        re.IGNORECASE,
    ), body
    assert "FOR EACH ROW" in body.upper()
    assert "FOR EACH STATEMENT" not in body.upper()
    assert "AFTER INSERT" not in body.upper()


def test_the_trigger_object_name_does_not_collide_with_the_schema_lead_s_guard() -> None:
    """``clause_version_guard`` on this same table is the BLOODLINE / MI15 guard, and theirs.

    The file *slug* is ``trg_delta_witness_guard`` because the allocation names it
    so; the *object* is ``z_delta_witness_required``.  The two differ deliberately —
    renaming the object to match the file would silently break
    ``ALTER TABLE mainline.clause_version DISABLE TRIGGER z_delta_witness_required``,
    which the custodian patrol names verbatim.
    """
    body = body_of(TRIGGER_MIGRATION)
    assert TRIGGER_NAME in body
    assert "clause_version_guard" not in body


# ── the exemptions, which are P7 at this gate ────────────────────────────────


def test_the_guard_fires_only_on_the_two_forceful_labels() -> None:
    body = body_of(FUNCTION_MIGRATION)
    assert "'weaken'::mainline.control_delta" in body
    assert "'remove'::mainline.control_delta" in body
    for benign in ("'introduce'", "'strengthen'", "'restate'"):
        assert benign not in body, (
            f"the guard mentions {benign}; a force-0 delta has nothing to witness and "
            "demanding one is a guard somebody disables"
        )


def test_lattice_and_lattice_plus_model_are_in_scope_and_the_other_two_are_not() -> None:
    """A ``lattice+model`` weaken with no lattice witness rests entirely on a model (P7).

    ``abstain_to_weaken`` fires precisely when Path A could *not* decide, so
    demanding a lattice witness for it demands an explanation that does not exist;
    ``human`` carries the commit message and the signature on it.  Both exemptions
    are narrow and neither is a loophole — but they are one edited line from
    becoming one.
    """
    body = body_of(FUNCTION_MIGRATION)
    match = re.search(
        r"delta_basis\s+NOT\s+IN\s*\((?P<body>[^)]*)\)", body, re.IGNORECASE | re.DOTALL
    )
    assert match is not None, "the guard does not scope itself by delta_basis"
    in_scope = set(re.findall(r"'([^']+)'", match.group("body")))
    assert in_scope == {"lattice", "lattice+model"}, in_scope
    assert "'abstain_to_weaken'" not in body
    assert "'human'" not in body


def test_the_style_rules_for_this_band_are_respected() -> None:
    """§5.11: PL/pgSQL, row-level, no dynamic SQL, no loops, no ``CASE``.

    ``EXECUTE`` is the one that matters: a gate assembling its own predicate from
    a string is a gate whose behaviour is not readable from the migration.
    """
    body = body_of(FUNCTION_MIGRATION).upper()
    # String literals are stripped before the keyword scan. The refusal messages are
    # English sentences and one of them contains the word "for"; a scanner that reads
    # a message as code would report a loop that is not there, and a test that cries
    # wolf about its own error text is one somebody deletes.
    code = re.sub(r"'[^']*'", "''", body)
    for forbidden in ("EXECUTE", "PERFORM", "FOREACH", "CASE", "LOOP"):
        assert not re.search(rf"\b{forbidden}\b", code), f"{forbidden} in the guard body"
    assert not re.search(r"\bFOR\b\s+\w+\s+IN\b", code), "a FOR..IN loop in the guard body"
    assert "LANGUAGE PLPGSQL" in code
    assert "RETURNS TRIGGER" in code
