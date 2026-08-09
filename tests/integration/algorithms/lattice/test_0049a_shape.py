# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Static checks on ``0049a_delta_witness.sql``.  No cluster, no driver, runs everywhere.

Three jobs, in increasing order of how much they earn their place.

**Band discipline.**  One top-level statement, the four linted header keys, a
filename that matches the one convention, no ``.down.sql`` and no ``.up.sql``
twin, and — the rule that would have caught the 2026-08-08 incident — the file's
``(NNNN, letter)`` key resolved against ``migrations.allocation.toml`` and its
band's ``mode`` compared with the file's own authoring banner.  That is rule B:
a file compared against a *declaration*, not two declarations compared with each
other.

**The cross-language join.**  ``rule_id_closed`` is a ``CHECK`` over nine string
literals, and those nine strings are also
:data:`mainline_domain.contracts.RULE_IDS` — the vocabulary every
:class:`~mainline_domain.contracts.DeltaWitness` this domain emits is drawn from.
Nothing in SQL knows that and nothing in Python knows the ``CHECK``.  Add a tenth
rule on the Python side and the migration keeps applying, the table keeps
accepting rows, and every witness from the new rule is rejected at ``23514`` — at
which point the version row is refused by ``0140`` for having no witnesses, which
reads in the console exactly like a lattice that found nothing.  So the two sets
are held equal here, by parsing this file, which is the only place both are
visible at once.  ``0049a``'s own header says this test does it.

**The refusals it claims.**  A header that lists a SQLSTATE it does not implement
is worse than one that lists nothing, because the next reader budgets for a
refusal that will never fire.  Every constraint named in the ``sqlstate:`` line is
checked to exist in the DDL, and the P0001 the header *defers to another file* is
checked to be absent from this one.
"""

from __future__ import annotations

import re
import tomllib

from _lattice_sql_support import (
    MIGRATIONS_DIR,
    OWNED_MIGRATIONS,
    code_of,
    migration,
    split_statements,
)
from mainline_domain.contracts import RULE_IDS

TABLE_MIGRATION = OWNED_MIGRATIONS[0]
FILENAME_RE = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")


def migration_text() -> str:
    return migration(TABLE_MIGRATION).read_text(encoding="utf-8")


def allocation_bands() -> list[dict[str, str]]:
    path = MIGRATIONS_DIR.parent / "migrations.allocation.toml"
    return tomllib.loads(path.read_bytes().decode("utf-8"))["band"]


def band_of(stem: str) -> dict[str, str] | None:
    """The band whose ``[first, last]`` interval contains ``stem``.

    Lexicographic on the whole stem, which is exactly how the runner orders files
    (MR-5: ``0006a < 0006b < 0007``, ``0119a < 0120``) and therefore the only
    comparison that can agree with it.
    """
    for band in allocation_bands():
        if band["first"] <= stem <= band["last"]:
            return band
    return None


# ── band discipline ──────────────────────────────────────────────────────────


def test_the_migration_is_exactly_one_statement() -> None:
    """The deployed runner applies one statement per file (§18, ``statement_count()``).

    CockroachDB DDL is not transactional across statements and the runner does
    not wrap a migration body in a transaction, so a two-statement file that
    half-applies leaves the version marked ``dirty`` with no way to tell which
    half is on the cluster.  ``0211`` was such a file; the split into ``0140`` +
    ``0145`` is what fixed it, and this assertion is what keeps it fixed.
    """
    statements = split_statements(migration_text())
    assert len(statements) == 1, (
        f"{TABLE_MIGRATION} carries {len(statements)} statements; the header declares 1"
    )
    assert code_of(statements[0]).upper().startswith("CREATE TABLE MAINLINE.DELTA_WITNESS")


def test_the_header_carries_the_four_linted_keys_and_its_sources() -> None:
    text = migration_text()
    for key in ("MI:", "I:", "COUNSEL-GATED:", "RATIONALE:"):
        assert key in text, f"{TABLE_MIGRATION}'s header has no `{key}` line"
    for field in ("migration:", "domain:", "band:", "statements:", "invariants:", "source:"):
        assert field in text, f"{TABLE_MIGRATION}'s header has no `{field}` line"
    assert "I14" in text, f"{TABLE_MIGRATION} does not cite I14"
    assert "MI22" in text, f"{TABLE_MIGRATION} does not cite MI22"
    assert "forward-only" in text


def test_the_filename_matches_the_one_convention() -> None:
    """``NNNN[a-z]_lower_snake_slug.sql`` — rule A, and nothing else.

    A second dot makes the whole directory undiscoverable: one such filename was
    measured to make ``trappoint migrate`` refuse all 121 files beside it.
    """
    assert FILENAME_RE.match(TABLE_MIGRATION), TABLE_MIGRATION
    assert not list(MIGRATIONS_DIR.glob("0049a_*.down.sql"))
    assert not list(MIGRATIONS_DIR.glob("0049a_*.up.sql"))
    claims = sorted(MIGRATIONS_DIR.glob("0049a_*"))
    assert [p.name for p in claims] == [TABLE_MIGRATION], (
        f"more than one file claims 0049a: {[p.name for p in claims]}"
    )


def test_the_file_resolves_against_the_allocation_and_agrees_with_its_mode() -> None:
    """Lint rule B, reproduced: the file is compared against the *declaration*.

    The collision check that reported zero collisions on 2026-08-08 compared two
    declarations with each other and found nothing in common.  It was wrong by
    twenty numbers.  This compares a file on disk against
    ``migrations.allocation.toml``, which is the authority.
    """
    stem = TABLE_MIGRATION[: -len(".sql")]
    band = band_of(stem)
    assert band is not None, f"{stem} falls in no band; 0200+ is UNALLOCATED and lint refuses it"
    assert band["owner"] == "algorithms", (
        f"{stem} resolves to a band owned by {band['owner']!r}, not by this domain"
    )
    assert band["mode"] == "authored"
    assert "@rendered-by" not in migration_text(), (
        "an authored-band file carrying the rendered banner is a lint failure, and a "
        "hand-authored twin of a rendered file is permanently red in the worst way: "
        "`render --check` stays green while the runner refuses the tree"
    )


def test_nothing_in_this_domain_claims_0200_or_above() -> None:
    """The revoked annexe, asserted from the other side.

    ``0205``/``0211`` are gone and ``0200+`` is ``UNALLOCATED``.  A number space
    with no owner is what produced two conventions in the first place, so the
    absence is checked rather than assumed.
    """
    trespassers = [
        path.name
        for path in MIGRATIONS_DIR.glob("*.sql")
        if path.name[:4].isdigit() and int(path.name[:4]) >= 200
    ]
    assert trespassers == [], f"files claim the unallocated 0200+ range: {trespassers}"


# ── the cross-language join ──────────────────────────────────────────────────


def rule_ids_in_the_check() -> tuple[str, ...]:
    text = migration_text()
    match = re.search(
        r"CONSTRAINT\s+rule_id_closed\s+CHECK\s*\(\s*rule_id\s+IN\s*\((?P<body>.*?)\)\s*\)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    assert match is not None, f"{TABLE_MIGRATION} has no `rule_id_closed` CHECK"
    return tuple(re.findall(r"'([^']+)'", match.group("body")))


def test_the_sql_vocabulary_is_exactly_the_python_vocabulary() -> None:
    """The join nothing else checks.  See this module's docstring for the failure mode."""
    assert rule_ids_in_the_check() == RULE_IDS, (
        "the rule_id CHECK in "
        f"{TABLE_MIGRATION} and mainline_domain.contracts.RULE_IDS have diverged:\n"
        f"  SQL:    {rule_ids_in_the_check()}\n"
        f"  Python: {RULE_IDS}"
    )


def test_the_vocabulary_is_a_check_and_not_an_enum() -> None:
    """Deliberate, and stated in the header: a ``CREATE TYPE`` would be a second migration.

    The nine ids change only when a rule is added, which is a ``LATTICE_VERSION``
    bump, a re-derivation of every affected verdict and a decision somebody signs.
    A ``CHECK`` also means that widening the vocabulary is an
    ``ALTER TABLE ... DROP CONSTRAINT``, which the custody ledger sees.
    """
    body = code_of(split_statements(migration_text())[0])
    assert "CREATE TYPE" not in body.upper(), (
        "the vocabulary became an enum; the header argues at length for a CHECK and the "
        "two must not disagree"
    )
    assert re.search(r"\brule_id\s+STRING\s+NOT NULL", body), (
        "rule_id is no longer a plain STRING column"
    )


# ── the refusals it claims, and the one it defers ────────────────────────────


def test_every_constraint_the_header_promises_exists_in_the_ddl() -> None:
    text = migration_text()
    promised = (
        "delta_witness_pk",
        "fk_clause",
        "fk_commit",
        "rule_id_closed",
        "witness_ord_nonneg",
        "field_stated",
        "note_stated",
        "commit_id_is_sha256",
    )
    body = code_of(split_statements(text)[0])
    for name in promised:
        assert f"CONSTRAINT {name}" in body, (
            f"{TABLE_MIGRATION}'s header names {name} in its sqlstate line but the DDL "
            "does not declare it"
        )


def test_a_witness_cannot_be_blank() -> None:
    """``note_stated`` is D8 one level down.

    A row that satisfies the guard and explains nothing is exactly the shape the
    guard exists to refuse, so the table refuses it structurally — and that
    ``CHECK`` survives ``DISABLE TRIGGER``, which the trigger's own refusal does
    not.
    """
    body = code_of(split_statements(migration_text())[0])
    assert "CONSTRAINT note_stated CHECK (note <> '')" in body
    assert "CONSTRAINT field_stated CHECK (field <> '')" in body


def test_the_p0001_is_deferred_to_the_guard_and_not_claimed_here() -> None:
    """A table cannot raise P0001.  The header must not imply that this one does."""
    body = code_of(split_statements(migration_text())[0])
    assert "RAISE" not in body.upper(), (
        "the CREATE TABLE statement contains a RAISE; the P0001 belongs to 0140"
    )
    text = migration_text()
    for attaches in ("0140", "0145"):
        assert attaches in text, (
            f"{TABLE_MIGRATION} does not name {attaches}, one of the two files that attach "
            "the refusal making this table load-bearing"
        )


# ── the two things the header states normatively ─────────────────────────────


def test_the_ordering_contract_is_stated_in_the_file() -> None:
    """Witnesses first, version row second, one transaction.

    This is the only place the contract is normative — the guard is a BEFORE
    INSERT trigger, so witnesses written *after* the version row are witnesses it
    never saw.  A projector author who reads only the DDL must still find it.
    """
    text = migration_text()
    assert "ORDERING CONTRACT" in text
    witness_at = text.find("INSERT INTO mainline.delta_witness")
    version_at = text.find("INSERT INTO mainline.clause_version")
    assert 0 < witness_at < version_at, (
        "the ordering contract in the header does not show the witness INSERT before "
        "the clause_version INSERT"
    )


def test_the_absent_composite_fk_is_explained_rather_than_omitted() -> None:
    """The natural constraint is unbuildable here, and the file says so.

    ``FOREIGN KEY (clause_uuid, commit_id) REFERENCES clause_version`` is directly
    incompatible with the ordering contract, because CockroachDB checks foreign
    keys per statement and does not implement ``DEFERRABLE``.  An unstated
    omission reads as an oversight; a stated one is a measured platform limit.
    """
    text = migration_text()
    body = code_of(split_statements(text)[0])
    assert "REFERENCES mainline.clause_version" not in body, (
        "0049a declares a composite FK onto clause_version; the ordering contract makes "
        "the witness INSERT the first statement, so this refuses every legal write at 23503"
    )
    assert "DEFERRABLE" in text.upper() or "deferred" in text, (
        "the file does not record WHY the natural composite FK is absent"
    )


def test_the_table_is_not_silently_missing_site_id() -> None:
    """No ``site_id``, and the reason is P2, not forgetfulness.

    A column a policy reads must be projected from an authoritative row by a
    trigger, and the authoritative row here — the ``clause_version`` — does not
    exist yet when the witness is written.  The header says so and pairs the
    column with the policy that would need it.
    """
    text = migration_text()
    body = code_of(split_statements(text)[0])
    assert "site_id" not in body
    assert "site_id" in text, "0049a omits site_id without saying why"
