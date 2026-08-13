# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Tier-1 schema suite for the foundation band, migrations 0001-0023.

The band has TWO owners since the migration reconciliation, and the split is the point:

* **RENDERED (44 files)** — emitted by templates in ``packages/trappoint-sql/templates/`` and
  never hand-edited. These are SUBSTRATE objects (MR-2): the schemas, the nine roles and the
  privilege floor, the seven types, both lattices, ``person`` and ``signing_credential``. A
  second TRAPPOINT vertical needs every one of them to pass ``trappoint-conform``, which is
  exactly the test that decides whether an object is substrate.
* **AUTHORED (3 files)** — ``0019_retention_class``, ``0020_adm_decision_class``, ``0020a_site``.
  These are VERTICAL: MAINLINE's retention schedule, its APP 1.7 disclosure register and its
  tenancy scope. No other vertical needs them, so no template emits them.

That distinction is why this file no longer asserts a dense ``0001-0023``. Two domains once
implemented this same band under two conventions — ``NNNN_name.up.sql`` and ``NNNN[a-z]_name.sql``
— and a density check over the leading four digits was satisfied by BOTH of them at once. The
band is enumerated now (``EXPECTED_BAND_FILES``) and the filename convention is MR-5, checked
against the directory rather than against whatever discovery happened to select.

What this band owns, and therefore what this file may honestly assert:

* the five schema zones, their ownership, and the default-deny posture over them;
* the seven ENUM types;
* the clearance lattice, **including its three deliberately absent cells** — the single most
  load-bearing piece of *data* in the product;
* the legal state-transition edge set, identical for both gated subjects (S16);
* ``mainline.site``, the authoritative source DM-3 adds for every projected ``site_role``,
  ``site_code`` and ``tenant_id`` in the schema;
* ``person`` and ``signing_credential``;
* ``GRANTS.yaml``, and the privilege probe that turns it from a claim into evidence.

What this band does NOT own, and what this file therefore does not pretend to prove: the refusals.
``MI10`` is a ``23503`` against ``subject_transition`` raised by ``permit``/``change_request``
(band 0050-0065); ``MI11`` is a ``23503`` against ``clearance_legal`` raised by ``disposition``
(band 0066-0071). This band ships the *referenced vocabulary*, which is the precondition for those
refusals being correct, and asserts that the vocabulary is exactly right — no more. Claiming
otherwise here would be the kind of green-that-asserts-nothing PL-2 exists to prevent.

Running it
----------
The static tier (``@pytest.mark.shape``) needs no cluster and runs anywhere. The cluster tier
finds a CockroachDB v26.2 in this order and **skips with a reason** rather than faking anything:

1. the session ``dsn`` fixture, if ``tests/integration/schema/conftest.py`` (owned by
   ``dm-runner``) is present — so the two suites share one cluster;
2. ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL``;
3. a ``cockroach`` binary on ``PATH`` (in-memory single node, session-scoped);
4. a running Docker daemon (the image ``compose.yaml`` pins).

Nothing in this band is done on the basis of a skipped run, and the skip message says which of the
four is missing.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from trappoint_testkit import pinned_image

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)
yaml = pytest.importorskip("yaml", reason="pyyaml is required to read GRANTS.yaml")

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Paths and band constants
# ══════════════════════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"
SEEDS_DIR = DB_DIR / "seeds" / "00-lattice"
GRANTS_PATH = DB_DIR / "GRANTS.yaml"

#: The band this worker owns, exclusively.
BAND_FIRST, BAND_LAST = 1, 23

#: Seeds the fixture still applies from `db/seeds/00-lattice/`, in order. Order is fixed so the
#: schema+seed fingerprint is stable (DM-12).
#:
#: `subject_transition.sql` and `clearance_legal.sql` are NO LONGER APPLIED HERE. Under MR-1 both
#: lattices are SUBSTRATE, so they ship as rendered migrations that carry their own seed —
#: `0017b_subject_transition_seed.sql` and `0018b_clearance_legal_seed.sql`. Applying the band and
#: then re-applying those two seed files would insert the same rows twice and fail on 23505, and
#: the seed a second TRAPPOINT vertical gets must be the one in the template, not one that lives
#: in MAINLINE's seed directory where no other vertical can see it.
SEED_ORDER = (
    "retention_class.sql",
    "adm_decision_class.sql",
)

#: The two lattices, now seeded by migration rather than by the seed runner. The files under
#: `db/seeds/00-lattice/` still exist for the seed tooling; `test_lattice_seed_files_have_not_
#: drifted_from_the_migrations` is what stops the two copies diverging.
MIGRATED_LATTICE_SEEDS = (
    "0017b_subject_transition_seed.sql",
    "0018b_clearance_legal_seed.sql",
)

#: Seed files that still exist on disk and must stay deterministic, whether or not the fixture
#: applies them.
DETERMINISTIC_SEED_FILES = (
    "subject_transition.sql",
    "clearance_legal.sql",
    "retention_class.sql",
    "adm_decision_class.sql",
)

SCHEMAS = ("mainline", "mainline_meas", "mainline_audit", "mainline_qa", "mainline_ops")

#: The four mandatory header keys the runner's linter enforces on every migration.
REQUIRED_HEADER_KEYS = ("-- MI:", "-- I:", "-- COUNSEL-GATED:", "-- RATIONALE:")

#: MR-5, the one filename convention: `NNNN[a-z]_lower_snake_slug.sql`.
#:
#: Four digits, an OPTIONAL SINGLE lowercase letter, a lower-snake slug, `.sql`, and **no second
#: dot ever**. The second-dot prohibition is not tidiness: the runner's `_VERSION_RE` does not
#: admit `.`, so one `0031_clause_embedding.fallback.sql` makes the WHOLE directory
#: undiscoverable — every migration, not just that one. `.up.sql` is banned by the same rule and
#: for a second reason: it names a `.down.sql` counterpart that is illegal by construction at or
#: below the protected floor (DM-14), and a suffix chain is precisely what let two conventions
#: coexist invisibly until the chain would not apply.
MR5_FILENAME_RE = re.compile(r"^(\d{4})([a-z]?)_([a-z0-9_]+)\.sql$")

#: Exactly the files the foundation band must contain after the migration reconciliation, in
#: runner order. This list is literal on purpose: the band is no longer dense over 0001-0023, so
#: "no gaps, no duplicates" cannot be expressed as a range any more, and a range test would have
#: been satisfied by both halves of the collision that caused the reconciliation.
#:
#: RENDERED (44) — emitted by a template in `packages/trappoint-sql/templates/`, never hand-edited.
#: AUTHORED (3)  — `retention_class`, `adm_decision_class`, `site`; VERTICAL objects (MR-2), which
#:                 a second TRAPPOINT vertical does not need in order to pass `trappoint-conform`.
EXPECTED_BAND_FILES = (
    # 0001-0005 · the five schema zones
    "0001a_schema_mainline.sql",
    "0002_schema_meas.sql",
    "0003_schema_audit.sql",
    "0004_schema_qa.sql",
    "0005_schema_ops.sql",
    # 0006a-0006i · the nine roles
    "0006a_role_migrator.sql",
    "0006b_role_owner.sql",
    "0006c_role_gate.sql",
    "0006d_role_projector.sql",
    "0006e_role_recaller.sql",
    "0006f_role_disposer.sql",
    "0006g_role_auditor.sql",
    "0006h_role_reader.sql",
    "0006i_role_qa.sql",
    # 0007a-0007e · one REVOKE per zone (one statement per file)
    "0007a_revoke_public_business.sql",
    "0007b_revoke_public_meas.sql",
    "0007c_revoke_public_audit.sql",
    "0007d_revoke_public_qa.sql",
    "0007e_revoke_public_ops.sql",
    # 0008a-0008e · one ownership transfer per zone
    "0008a_owner_business.sql",
    "0008b_owner_meas.sql",
    "0008c_owner_audit.sql",
    "0008d_owner_qa.sql",
    "0008e_owner_ops.sql",
    # 0009a-0009f · the privilege floor, and 0009x · the covenant comment
    "0009a_grant_create_migrator.sql",
    "0009b_grant_usage_agents.sql",
    "0009c_grant_usage_auditor.sql",
    "0009d_grant_usage_qa.sql",
    "0009e_default_privileges_floor.sql",
    "0009f_revoke_create_public_schema.sql",
    "0009x_covenant_comment.sql",
    # 0010-0016 · the seven ENUM types
    "0010_type_control_delta.sql",
    "0011_type_subject_state.sql",
    "0012_type_disposition_kind.sql",
    "0013_type_virulence_class.sql",
    "0014_type_blame_basis.sql",
    "0015_type_blame_state.sql",
    "0016_type_prop_state.sql",
    # 0017-0018 · the two lattices, each as table + seed
    "0017a_subject_transition.sql",
    "0017b_subject_transition_seed.sql",
    "0018a_clearance_legal.sql",
    "0018b_clearance_legal_seed.sql",
    # 0019-0020a · AUTHORED, dm-foundation's surviving three
    "0019_retention_class.sql",
    "0020_adm_decision_class.sql",
    "0020a_site.sql",
    # 0021-0023 · identity
    "0021_person.sql",
    "0022_signing_credential.sql",
    "0023_signing_credential_index.sql",
)

#: MI01-MI30 (ARCHITECTURE §16). The catalogue file itself is `dm-runner`'s deliverable; this is
#: the identity check only — "the id you cited is a real id" — not a copy of the catalogue.
VALID_MI = frozenset(f"MI{n:02d}" for n in range(1, 31))
VALID_I = frozenset(f"I{n:02d}" for n in range(1, 17))

#: The three cells the clearance lattice must NOT contain. This tuple is the product.
ABSENT_CELLS = (
    ("blood_fatal", "mechanism_absent"),
    ("blood_fatal", "accept_residual"),
    ("blood_major", "accept_residual"),
)

VIRULENCES = ("routine", "serious", "blood_major", "blood_fatal")
DISPOSITION_KINDS = (
    "applied",
    "mitigated",
    "mechanism_absent",
    "escalated",
    "accept_residual",
    "emergency_override",
)

SUBJECT_KINDS = ("permit", "change_request")
EXPECTED_EDGES = frozenset(
    {
        ("draft", "checks_materialised"),
        ("draft", "abandoned"),
        ("checks_materialised", "checks_materialised"),
        ("checks_materialised", "dispositioned"),
        ("dispositioned", "checks_materialised"),
        ("dispositioned", "merged"),
        ("merged", "suspended"),
        ("merged", "closed"),
        ("suspended", "closed"),
    }
)

#: Tables this band creates, in creation order.
BAND_TABLES = (
    "mainline.subject_transition",
    "mainline.clearance_legal",
    "mainline.retention_class",
    "mainline.adm_decision_class",
    "mainline.site",
    "mainline.person",
    "mainline.signing_credential",
)

_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-foundation-schema-test"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 600.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A comment- and string-aware SQL splitter.
#
# Naive `text.split(';')` is wrong twice over in this band: every file is mostly prose comments,
# and those comments are full of apostrophes ("the customer's officer"). A scanner that looks for
# quotes before it looks for comment markers reads `customer's officer` as the start of a string
# literal and then swallows the rest of the file. The state machine below is the fix, and
# `test_splitter_handles_apostrophes_in_comments` is its self-test — because a linter that
# miscounts statements would silently bless a two-statement file, which is the exact defect the
# one-statement rule exists to prevent.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def strip_sql_comments(text: str) -> str:
    """Remove ``--`` line comments and ``/* */`` block comments, preserving string literals."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":  # doubled '' escape
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append(text[i])
                i += 1
            continue
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n and text[i] != '"':
                out.append(text[i])
                i += 1
            if i < n:
                out.append('"')
                i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def split_statements(text: str) -> list[str]:
    """Split into statements on ``;``, ignoring semicolons inside literals and comments."""
    body = strip_sql_comments(text)
    statements: list[str] = []
    current: list[str] = []
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "'":
            current.append(ch)
            i += 1
            while i < n:
                if body[i] == "'":
                    if i + 1 < n and body[i + 1] == "'":
                        current.append("''")
                        i += 2
                        continue
                    current.append("'")
                    i += 1
                    break
                current.append(body[i])
                i += 1
            continue
        if ch == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def band_files() -> list[Path]:
    """The 0001-0023 migrations, in the order the runner applies them.

    Ordering is **lexicographic on the whole stem**, not numeric on the leading four digits,
    because that is what ``trappoint_migrate.discovery`` does. It is the difference that makes
    ``0006a < 0006b < 0007`` and ``0020 < 0020a < 0021`` true, and sorting numerically here would
    let this suite apply the band in an order the runner never would — a test harness that
    disagrees with the thing it is testing about *sequence* is worse than no test, because the
    band is a sequence.

    Only MR-5 names are returned. A file with a second dot in its name (``.up.sql``,
    ``.fallback.sql``) does not match ``_VERSION_RE`` and is not a migration; it is excluded here
    rather than tolerated, and ``test_band_carries_only_mr5_filenames`` is what reports it.
    """
    found: list[tuple[str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = MR5_FILENAME_RE.match(path.name)
        if match and BAND_FIRST <= int(match.group(1)) <= BAND_LAST:
            found.append((path.name[: -len(".sql")], path))
    return [p for _, p in sorted(found)]


def header_values(text: str, key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key):
            return stripped[len(key) :].strip()
    return None


def quote_ident(name: str) -> str:
    """Refuse anything that is not a plain lower-case identifier.

    GRANTS.yaml is data that becomes SQL. It is ours and it is reviewed, but a matrix that is
    interpolated into DDL without a shape check is a matrix that becomes an injection surface the
    first time someone generates it from somewhere else.
    """
    if not _IDENT_RE.match(name):
        raise AssertionError(f"GRANTS.yaml contains a non-identifier name: {name!r}")
    return name


def assert_names_constraint(exc: Any, expected: str) -> None:
    """Assert the refusal identifies the constraint BY NAME, from either place it can appear.

    DM-10 exists because the constraint name is the courtroom exhibit, and the conformance suite
    asserts an exact SQLSTATE *and* an exact constraint name — "an exception was raised" is
    worthless when the diagnosis is the deliverable. Two sources are checked because
    PostgreSQL-family servers may report the name in the structured error field
    (``diag.constraint_name``), in the message text, or in both, and CockroachDB's behaviour here
    is not something this band could execute to confirm.

    If neither source carries it, that is a PLATFORM FINDING and not a test to relax: it would mean
    every constraint-name assertion in trappoint-conform has to be re-expressed. So the failure
    prints exactly what the server did say.
    """
    diag_name = getattr(getattr(exc, "diag", None), "constraint_name", None)
    message = str(exc)
    if diag_name == expected or expected in message:
        return
    raise AssertionError(
        f"the refusal did not name the constraint {expected!r}.\n"
        f"  diag.constraint_name: {diag_name!r}\n"
        f"  message:              {message}\n"
        "If CockroachDB v26.2 reports neither, this is a platform finding: every constraint-name "
        "assertion in the conformance suite depends on one of these two carrying it."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — no cluster required. These run everywhere, including the machine this band was
# written on, which had neither a `cockroach` binary nor a live Docker daemon.
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.shape
def test_splitter_handles_apostrophes_in_comments() -> None:
    """Self-test of the linter's own scanner, before it is trusted to lint anything."""
    sample = (
        "-- the customer's officer, not ours; and it isn't ours either\n"
        "/* a block comment with a ; and an apostrophe: don't */\n"
        "SELECT 'a;b', 'it''s fine';\n"
    )
    statements = split_statements(sample)
    assert len(statements) == 1, statements
    assert statements[0].startswith("SELECT")
    assert "a;b" in statements[0]


@pytest.mark.shape
def test_band_is_exactly_the_expected_file_set() -> None:
    """The band is an explicit list now, not a dense range.

    Before the migration reconciliation this test asserted ``numbers == range(1, 24)``. That
    assertion is what made the incident invisible for a whole dispatch wave: it grouped on the
    leading four digits, so a hand-authored ``0006_schema_mainline_ops.up.sql`` and nine rendered
    ``0006a..0006i_role_*.sql`` both satisfied "0006 is present exactly once" — two competing
    implementations of the same band, and a green test over the top of them.

    So the set is enumerated, and the diff is printed both ways. An unexpected file is as much a
    failure as a missing one: an extra file in this band is either a resurrected twin or a worker
    writing outside its allocation, and both are the defect this suite now exists to catch.
    """
    actual = tuple(p.name for p in band_files())
    missing = [n for n in EXPECTED_BAND_FILES if n not in actual]
    unexpected = [n for n in actual if n not in EXPECTED_BAND_FILES]
    assert not missing and not unexpected, (
        "the foundation band is not the expected file set.\n"
        f"  missing ({len(missing)}):    {missing}\n"
        f"  unexpected ({len(unexpected)}): {unexpected}\n"
        "Rendered files come from packages/trappoint-sql/templates/ — if one is missing, run "
        "`trappoint render`, do not hand-write it."
    )
    assert actual == EXPECTED_BAND_FILES, (
        "the band contains the right files in the wrong order. Order is lexicographic on the "
        f"whole stem, which is what the runner applies:\n  {list(actual)}"
    )


@pytest.mark.shape
def test_band_carries_only_mr5_filenames() -> None:
    """MR-5, enforced against the directory rather than against what ``band_files()`` selected.

    ``band_files()`` filters to MR-5 names, so on its own it can never see a violation — it would
    simply return fewer files and every downstream test would pass over a band with a hole in it.
    This test does the opposite: it globs everything numbered in the band and asserts that each
    one is a legal name, so a surviving ``.up.sql`` or a ``.fallback.sql`` fails loudly here
    instead of silently shrinking the band.
    """
    offenders: list[str] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or ".sql" not in path.name:
            continue
        leading = re.match(r"^(\d{4})", path.name)
        if not leading or not (BAND_FIRST <= int(leading.group(1)) <= BAND_LAST):
            continue
        if not MR5_FILENAME_RE.match(path.name):
            offenders.append(path.name)
    assert not offenders, (
        "filenames in the foundation band that are not `NNNN[a-z]_lower_snake_slug.sql` (MR-5):\n  "
        + "\n  ".join(offenders)
        + "\nA second dot defeats the runner's `_VERSION_RE` and makes the WHOLE migrations "
        "directory undiscoverable, not just the offending file."
    )


@pytest.mark.shape
def test_no_down_migration_at_or_below_the_protected_floor() -> None:
    """DM-14. Down-migrating an append-only ledger is destruction of evidence, not a rollback."""
    strays = [
        p.name
        for p in MIGRATIONS_DIR.glob("*.down.sql")
        if re.match(r"^\d{4}_", p.name) and BAND_FIRST <= int(p.name[:4]) <= BAND_LAST
    ]
    assert not strays, f".down.sql is illegal at or below the protected floor: {strays}"


@pytest.mark.shape
@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_every_file_carries_the_mandatory_header_block(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for key in REQUIRED_HEADER_KEYS:
        assert header_values(text, key) is not None, f"{path.name} is missing `{key}`"

    mi_field = header_values(text, "-- MI:") or ""
    cited = re.findall(r"MI\d{2}", mi_field)
    assert cited, f"{path.name} cites no MI id (ARCHITECTURE §18: every migration cites one)"
    unknown = sorted(set(cited) - VALID_MI)
    assert not unknown, f"{path.name} cites MI ids that are not in MI01-MI30: {unknown}"

    i_field = header_values(text, "-- I:") or ""
    i_cited = re.findall(r"\bI\d{2}\b", i_field)
    assert i_cited, f"{path.name} cites no TRAPPOINT invariant in `-- I:`"
    unknown_i = sorted(set(i_cited) - VALID_I)
    assert not unknown_i, f"{path.name} cites TRAPPOINT ids outside I01-I16: {unknown_i}"

    gated = (header_values(text, "-- COUNSEL-GATED:") or "").lower()
    assert gated.startswith("no"), (
        f"{path.name} claims to be counsel-gated. The counsel-gated five are 0066-0069 and 0086 "
        f"(DM-17); 0001-0065 are counsel-independent by construction."
    )
    assert len(header_values(text, "-- RATIONALE:") or "") >= 40, (
        f"{path.name}'s RATIONALE is too short to be one"
    )


@pytest.mark.shape
@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_exactly_one_statement_per_file(path: Path) -> None:
    """The runner does not wrap a body in a transaction, so a two-statement file is not atomic."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    assert len(statements) == 1, (
        f"{path.name} parses to {len(statements)} statements, not 1:\n"
        + "\n---\n".join(s[:200] for s in statements)
    )


@pytest.mark.shape
@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_no_banned_constructs(path: Path) -> None:
    """Sequences are banned (§4.1 law 9): a gap in the ledger must MEAN tampering."""
    body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
    for banned in ("create sequence", "nextval", "unique_rowid", " serial", "\tserial"):
        assert banned not in body, f"{path.name} uses the banned construct {banned!r}"


@pytest.mark.shape
@pytest.mark.parametrize("name", DETERMINISTIC_SEED_FILES)
def test_seeds_are_deterministic(name: str) -> None:
    """DM-12. The schema+seed fingerprint is the dev/demo/prod parity gate.

    A ``now()`` or a ``gen_random_uuid()`` in a seed makes parity unprovable: the same twenty-one
    lattice rows would hash differently in every environment, and the one artefact that proves the
    demo cluster and the production cluster hold the same legal surface would prove nothing.
    """
    path = SEEDS_DIR / name
    assert path.is_file(), f"missing seed {path}"
    body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
    for banned in ("now()", "gen_random_uuid", "current_timestamp", "localtimestamp", "random()"):
        assert banned not in body, f"{name} contains the non-deterministic construct {banned!r}"


@pytest.mark.shape
def test_clearance_seed_holds_twenty_one_rows_and_omits_three() -> None:
    """The absent cells, asserted against the FILE as well as the table.

    Two assertions of the same fact, deliberately. The cluster test proves the database ended up
    without those rows; this one proves nobody wrote them and then relied on a later delete. For
    the one piece of data the company's central claim rests on, "how it got that way" is worth a
    second test.
    """
    body = strip_sql_comments(
        (MIGRATIONS_DIR / "0018b_clearance_legal_seed.sql").read_text(encoding="utf-8")
    )
    for virulence, kind in ABSENT_CELLS:
        pattern = re.compile(rf"'{virulence}'\s*,\s*'{kind}'")
        assert not pattern.search(body), (
            f"({virulence}, {kind}) is present in the seed. That cell is the product: there is no "
            f"disposition constructor that dismisses a control written by a fatality."
        )
    tuples = re.findall(r"\(\s*'(routine|serious|blood_major|blood_fatal)'\s*,\s*'(\w+)'", body)
    assert len(tuples) == 21, f"expected 21 seeded cells, found {len(tuples)}"


@pytest.mark.shape
@pytest.mark.parametrize("name", MIGRATED_LATTICE_SEEDS)
def test_migrated_lattice_seeds_are_deterministic(name: str) -> None:
    """DM-12 again, for the two lattices that moved from the seed runner into the migration set.

    Moving a seed into a migration must not lose the property that made it a seed: the same rows,
    byte-for-byte, in every environment. Otherwise the schema+seed fingerprint that proves the
    demo cluster and the production cluster hold the same legal surface stops proving it.
    """
    body = strip_sql_comments((MIGRATIONS_DIR / name).read_text(encoding="utf-8")).lower()
    for banned in ("now()", "gen_random_uuid", "current_timestamp", "localtimestamp", "random()"):
        assert banned not in body, f"{name} contains the non-deterministic construct {banned!r}"


@pytest.mark.shape
def test_lattice_seed_files_have_not_drifted_from_the_migrations() -> None:
    """Two copies of the lattice now exist. This is the test that stops them diverging.

    The reconciliation moved both lattices into rendered migrations (0017b, 0018b), but the files
    under ``db/seeds/00-lattice/`` remain for the seed tooling. Two copies of the single most
    load-bearing piece of *data* in the product is a drift hazard, and drift here is invisible:
    both files load, both look plausible, and the one that reaches a given cluster depends on
    which tool ran. So the row sets are compared directly, and the migration is the authority —
    it is what a second TRAPPOINT vertical receives.
    """

    def cells(text: str) -> list[tuple[str, str]]:
        body = strip_sql_comments(text)
        return sorted(
            re.findall(r"\(\s*'(routine|serious|blood_major|blood_fatal)'\s*,\s*'(\w+)'", body)
        )

    def edges(text: str) -> list[tuple[str, str, str]]:
        body = strip_sql_comments(text)
        return sorted(
            re.findall(r"\(\s*'(permit|change_request)'\s*,\s*'(\w+)'\s*,\s*'(\w+)'", body)
        )

    seed_cells = cells((SEEDS_DIR / "clearance_legal.sql").read_text(encoding="utf-8"))
    migr_cells = cells(
        (MIGRATIONS_DIR / "0018b_clearance_legal_seed.sql").read_text(encoding="utf-8")
    )
    assert seed_cells == migr_cells, (
        "the clearance lattice in db/seeds/00-lattice/clearance_legal.sql has drifted from "
        "migration 0018b_clearance_legal_seed.sql, which is the authority.\n"
        f"  only in the seed file: {sorted(set(seed_cells) - set(migr_cells))}\n"
        f"  only in the migration: {sorted(set(migr_cells) - set(seed_cells))}"
    )

    seed_edges = edges((SEEDS_DIR / "subject_transition.sql").read_text(encoding="utf-8"))
    migr_edges = edges(
        (MIGRATIONS_DIR / "0017b_subject_transition_seed.sql").read_text(encoding="utf-8")
    )
    assert seed_edges == migr_edges, (
        "the transition lattice in db/seeds/00-lattice/subject_transition.sql has drifted from "
        "migration 0017b_subject_transition_seed.sql, which is the authority.\n"
        f"  only in the seed file: {sorted(set(seed_edges) - set(migr_edges))}\n"
        f"  only in the migration: {sorted(set(migr_edges) - set(seed_edges))}"
    )


@pytest.mark.shape
def test_grants_yaml_is_wellformed_and_covers_the_role_matrix() -> None:
    matrix = yaml.safe_load(GRANTS_PATH.read_text(encoding="utf-8"))
    declared = {r["name"] for r in matrix["roles"]}
    required = {
        "mainline_owner",
        "mainline_migrator",
        "agent_ingestor",
        "agent_cartographer",
        "agent_projector",
        "agent_recaller",
        "agent_gate",
        "svc_disposition",
        "agent_patroller",
        "agent_sequencer",
        "agent_relay",
        "agent_fleet",
        "agent_assay",
        "mainline_auditor",
        "auditor_ro",
        "quality_assurance",
        "subject_access",
        "site_reader",
        "fleet_hse",
        "signer",
    }
    missing = sorted(required - declared)
    assert not missing, f"GRANTS.yaml omits roles from §11.2: {missing}"

    # S2: agent_projector writes exactly one table.
    projector = [r for r in matrix["table_privileges"] if r["role"] == "agent_projector"]
    assert len(projector) == 1 and projector[0]["object"] == "mainline.clause_blame_closure", (
        "agent_projector must hold INSERT on clause_blame_closure and nothing else (S2)"
    )

    # S13: the MCP identity writes exactly one table.
    auditor_writes = [
        r
        for r in matrix["table_privileges"]
        if r["role"] == "mainline_auditor" and "INSERT" in r["privileges"]
    ]
    assert len(auditor_writes) == 1, "mainline_auditor must have exactly one writable object"
    assert auditor_writes[0]["object"] == "mainline_meas.external_attestation"

    # Nobody holds DELETE, anywhere, in the whole matrix.
    for row in matrix["table_privileges"] + matrix["schema_wide"]:
        assert "DELETE" not in row["privileges"], (
            f"{row} grants DELETE. MI01 layer one: no standing role holds DELETE on anything."
        )

    # mainline_owner is granted to nobody. That is what "unassumable" means.
    assert matrix["memberships"] == [], "mainline_owner must remain unassumable"

    # Every identifier that will be interpolated into SQL is a plain identifier.
    for row in matrix["roles"]:
        quote_ident(row["name"])
    for row in matrix["table_privileges"]:
        schema, _, table = row["object"].partition(".")
        quote_ident(schema)
        quote_ident(table)


@pytest.mark.shape
def test_pl2_red_site_projection_is_not_yet_enforced() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: kernel ``projection-triggers``, bands 0100-0109
    (functions, including ``fn_site_role`` at 0109) and 0120-0129 (the nine triggers).

    DM-3 makes ``mainline.site`` the authoritative source for every projected ``site_role``,
    ``site_code`` and ``tenant_id``. This band ships the table. A table nothing projects FROM is
    not yet a control: ``event_cue_coarse.tenant_id`` (migration 0042) still takes its value from
    the client and says so in its own comments, and ``permit.site_role`` — the RLS scope token —
    has no trigger behind it either. Until a trigger function reads ``mainline.site`` and writes
    one of those three columns, P2 is unsatisfied for the columns DM-3 exists to close.

    This test fails today, for that reason, and goes green the moment the projection lands. It is
    not marked xfail: an xfail that passes when it fails is exactly the accounting PL-2's ``mi-red``
    job needs to be able to see through.
    """
    projecting: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        body = strip_sql_comments(path.read_text(encoding="utf-8"))
        lowered = body.lower()
        if "mainline.site" not in lowered:
            continue
        if not re.search(r"\bcreate\s+(or\s+replace\s+)?function\b", lowered):
            continue
        if re.search(r"\b(site_role|site_code|tenant_id)\b", lowered):
            projecting.append(path.name)

    assert projecting, (
        "PL-2 RED, as intended. No migration defines a function that reads mainline.site and "
        "writes site_role / site_code / tenant_id, so DM-3's authoritative table is shipped but "
        "not yet load-bearing:\n"
        "  * mainline.site exists (migration 0020a, this band);\n"
        "  * event_cue_coarse.tenant_id (0042) is still client-supplied, recorded there as an "
        "unclosed loop;\n"
        "  * permit.site_role — the RLS scope token — has no projection trigger.\n"
        "Owner of the fix: kernel `projection-triggers` — `fn_site_role` at 0109 and its trigger "
        "in 0120-0129, both RENDERED from packages/trappoint-sql/templates/. (Before the "
        "migration reconciliation this pointed at dm-functions-triggers/0130-0199; MR-7 moved it, "
        "because projection is SUBSTRATE — every TRAPPOINT vertical projects its own scope token "
        "and none may take it from the writer.) Promote this test's MI entry in mi_catalogue.yaml "
        "from `pending` to `enforced` when it goes green."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER — everything below needs a real CockroachDB v26.2.
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Cluster:
    dsn: str
    provenance: str
    proc: subprocess.Popen[bytes] | None = None
    owns_docker: bool = False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until_ready(dsn: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 — any failure here means "not yet"
            time.sleep(1.0)
    return False


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """A dead Docker daemon does not refuse ``docker info``; it BLOCKS.

    ``subprocess.run(timeout=…)`` then raises ``TimeoutExpired``, which ``check=False`` does not
    cover, and an uncaught exception in a fixture turns a run that should have SKIPPED into a
    suite of ERRORs. That is the machine this band was authored on, so it is not hypothetical.
    """
    try:
        return subprocess.run(  # noqa: S603, S607
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _from_env() -> Cluster | None:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL"):
        value = os.environ.get(name)
        if value:
            return Cluster(dsn=value, provenance=f"${name}")
    return None


def _from_local_binary(tmp: Path) -> Cluster | None:
    binary = shutil.which("cockroach")
    if binary is None:
        return None
    port, http_port = _free_port(), _free_port()
    proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [
            binary,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
            f"--listen-addr=127.0.0.1:{port}",
            f"--http-addr=127.0.0.1:{http_port}",
        ],
        cwd=str(tmp),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on {port}", proc=proc)
    proc.terminate()
    return None


def _from_docker() -> Cluster | None:
    if shutil.which("docker") is None:
        return None
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
    if probe is None or probe.returncode != 0:
        return None
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-p",
            f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        timeout=DOCKER_RUN_TIMEOUT_S,
    )
    if started is None or started.returncode != 0:
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on {port}", owns_docker=True)
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


@pytest.fixture(scope="session")
def foundation_cluster(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Cluster]:
    # Cooperate with dm-runner's conftest if it is present, so the two suites share one cluster.
    # A bare `except Exception` and not `except FixtureLookupError`: pytest does not export that
    # class publicly, and a `Skipped` raised by dm-runner's own fixture derives from
    # BaseException, so it propagates through this handler untouched — which is the behaviour we
    # want (their skip reason is better than ours).
    try:
        shared = request.getfixturevalue("dsn")
    except Exception:  # noqa: BLE001
        shared = None
    if isinstance(shared, str) and shared:
        yield Cluster(dsn=shared, provenance="the `dsn` fixture from tests/integration/schema")
        return

    found = _from_env() or _from_local_binary(tmp_path_factory.mktemp("crdb")) or _from_docker()
    if found is None:
        pytest.skip(
            "no CockroachDB v26.2 reachable. Provide one of: tests/integration/schema/conftest.py "
            "with a session `dsn` fixture (dm-runner), $MAINLINE_TEST_DSN, a `cockroach` binary on "
            f"PATH, or a running Docker daemon for `docker run {CRDB_IMAGE}`. "
            "The foundation band is NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


def _apply(conn: Any, path: Path) -> None:
    for statement in split_statements(path.read_text(encoding="utf-8")):
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            raise AssertionError(
                f"{path.name} failed to apply.\n"
                f"  sqlstate: {exc.sqlstate}\n"
                f"  error:    {exc}\n"
                f"  statement:\n{statement.strip()[:1500]}"
            ) from exc


@dataclass
class Foundation:
    dsn: str
    database: str
    grants_notes: list[str] = field(default_factory=list)

    def connect(self) -> Any:
        return psycopg.connect(self.dsn, autocommit=True)


def _table_exists(conn: Any, schema: str, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    ).fetchone()
    return row is not None


def _schema_has_tables(conn: Any, schema: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s LIMIT 1", (schema,)
    ).fetchone()
    return row is not None


def apply_grants_matrix(conn: Any, matrix: dict[str, Any]) -> list[str]:
    """Apply GRANTS.yaml. Idempotent. Skips rows whose object does not exist yet.

    This is a faithful, self-contained implementation of the contract documented at the head of
    GRANTS.yaml, so that the band is testable before ``trappoint-migrate grants apply`` exists.
    When it does, this function becomes a second implementation of the same contract, and the two
    agreeing is worth more than either alone.
    """
    notes: list[str] = []

    for role in matrix["roles"]:
        name = quote_ident(role["name"])
        option = "LOGIN" if role.get("login") else "NOLOGIN"
        conn.execute(f"CREATE ROLE IF NOT EXISTS {name} WITH {option}")

    for member in matrix.get("memberships", []):
        conn.execute(f"GRANT {quote_ident(member['role'])} TO {quote_ident(member['member'])}")

    for row in matrix.get("schema_privileges", []):
        privileges = ", ".join(row["privileges"])
        for schema in row["schemas"]:
            conn.execute(
                f"GRANT {privileges} ON SCHEMA {quote_ident(schema)} TO {quote_ident(row['role'])}"
            )

    for row in matrix.get("table_privileges", []) + matrix.get("subject_access_views", []):
        schema, _, table = row["object"].partition(".")
        if not _table_exists(conn, schema, table):
            notes.append(f"skipped {row['object']} for {row['role']} (since {row.get('since')})")
            continue
        privileges = ", ".join(row["privileges"])
        conn.execute(
            f"GRANT {privileges} ON TABLE {quote_ident(schema)}.{quote_ident(table)} "
            f"TO {quote_ident(row['role'])}"
        )

    for row in matrix.get("schema_wide", []):
        schema = row["schema"]
        if not _schema_has_tables(conn, schema):
            notes.append(f"skipped schema-wide {row['privileges']} on {schema} (no tables yet)")
            continue
        privileges = ", ".join(row["privileges"])
        conn.execute(
            f"GRANT {privileges} ON ALL TABLES IN SCHEMA {quote_ident(schema)} "
            f"TO {quote_ident(row['role'])}"
        )

    for row in matrix.get("default_privileges", []):
        privileges = ", ".join(row["privileges"])
        statement = (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quote_ident(row['for_role'])} "
            f"IN SCHEMA {quote_ident(row['schema'])} "
            f"GRANT {privileges} ON {row['object_type']} TO {quote_ident(row['to_role'])}"
        )
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            # Best-effort, and recorded rather than swallowed. Default privileges are a
            # convenience for views that do not exist yet; nothing the probe asserts depends on
            # them, and `FOR ROLE <owner>` may require membership in the owner role — which
            # nobody has, by design.
            notes.append(f"default privileges not applied ({exc.sqlstate}): {statement}")

    for row in matrix.get("revocations", []):
        privileges = ", ".join(row["privileges"])
        objects = ", ".join(quote_ident(o) for o in row["objects"])
        conn.execute(
            f"REVOKE {privileges} ON {row['object_type']} {objects} "
            f"FROM {quote_ident(row['grantee'])}"
        )

    return notes


@pytest.fixture(scope="session")
def foundation(foundation_cluster: Cluster) -> Iterator[Foundation]:
    """Apply the whole band forward from clean into a fresh database, then seed, then grant."""
    from psycopg.conninfo import make_conninfo

    database = f"mainline_foundation_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(foundation_cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    # Re-point at the fresh database WITHOUT string surgery on the URL: an env-supplied DSN may
    # carry `options=--cluster=…` (CockroachDB Cloud Serverless), an sslrootcert path, or no path
    # component at all, and every one of those breaks a naive rsplit on "/".
    dsn = make_conninfo(foundation_cluster.dsn, dbname=database)

    state = Foundation(dsn=dsn, database=database)
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in band_files():
            _apply(conn, path)
        for name in SEED_ORDER:
            _apply(conn, SEEDS_DIR / name)
        matrix = yaml.safe_load(GRANTS_PATH.read_text(encoding="utf-8"))
        state.grants_notes = apply_grants_matrix(conn, matrix)

    print(
        f"\n[foundation] cluster:  {foundation_cluster.provenance}\n"
        f"[foundation] database: {database}\n"
        f"[foundation] applied {len(band_files())} migrations + {len(SEED_ORDER)} seeds, "
        f"then GRANTS.yaml ({len(state.grants_notes)} rows deferred to later bands)"
    )
    try:
        yield state
    finally:
        with psycopg.connect(foundation_cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture()
def conn(foundation: Foundation) -> Iterator[Any]:
    """One autocommit connection per test.

    Autocommit and not a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it.
    """
    connection = foundation.connect()
    try:
        yield connection
    finally:
        connection.execute("RESET ROLE")
        connection.close()


# ── the lattice ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.schema
@pytest.mark.mi("MI11")
def test_clearance_lattice_absent_cells_return_no_row(conn: Any) -> None:
    """The three cells that are not there ARE the product.

    ``disposition`` composite-FKs to ``(virulence, kind)``, and ``virulence`` is projected from the
    blame closure by trigger — never supplied by the signer. So a missing row here is not a policy
    a determined operator can be talked out of at 3 a.m.; it is ``23503`` on ``fk_clearance``, for
    every writer, including a DBA and including the Managed-MCP insert path.
    """
    for virulence, kind in ABSENT_CELLS:
        row = conn.execute(
            "SELECT count(*) FROM mainline.clearance_legal WHERE virulence = %s AND kind = %s",
            (virulence, kind),
        ).fetchone()
        assert row is not None and row[0] == 0, (
            f"({virulence}, {kind}) exists in clearance_legal. There is no disposition "
            f"constructor that dismisses a control written by a fatality — and if there is one "
            f"in this cluster, the central claim of the product is false here."
        )


@pytest.mark.schema
@pytest.mark.mi("MI11")
def test_clearance_lattice_is_complete_apart_from_those_three(conn: Any) -> None:
    """4 × 6 = 24 cells, minus the three, is 21. Both halves matter.

    Asserting only the absences would pass on an empty table, which would refuse everything and
    look identical to a working lattice right up until the first legitimate disposition.
    """
    rows = conn.execute(
        "SELECT virulence::STRING, kind::STRING FROM mainline.clearance_legal"
    ).fetchall()
    present = {(v, k) for v, k in rows}
    expected = {(v, k) for v in VIRULENCES for k in DISPOSITION_KINDS} - set(ABSENT_CELLS)
    assert present == expected, (
        f"lattice mismatch.\n  missing: {sorted(expected - present)}\n"
        f"  unexpected: {sorted(present - expected)}"
    )
    assert len(rows) == 21


@pytest.mark.schema
@pytest.mark.mi("MI11")
def test_clearance_lattice_escalates_and_bounds(conn: Any) -> None:
    """Shape assertions that would catch a transposed column in the seed.

    A seed with two boolean columns swapped still loads, still has 21 rows, and still omits the
    three cells — and is wrong in the way that matters. These four properties are the ones a
    transposition breaks.
    """
    rows = conn.execute(
        "SELECT virulence::STRING, kind::STRING, req_second_signer, min_signer_rank, max_ttl_hours "
        "FROM mainline.clearance_legal"
    ).fetchall()
    by_cell = {(v, k): (second, rank, ttl) for v, k, second, rank, ttl in rows}

    # 1. Every emergency_override expires. An emergency that has lasted a week is not one.
    for virulence in VIRULENCES:
        _, _, ttl = by_cell[(virulence, "emergency_override")]
        assert ttl is not None and ttl > 0, f"emergency_override at {virulence} has no TTL"

    # 2. Every emergency_override needs a second signer.
    for virulence in VIRULENCES:
        second, _, _ = by_cell[(virulence, "emergency_override")]
        assert second is True, f"emergency_override at {virulence} needs a countersignature"

    # 3. accept_residual always expires where it exists at all, and exists only below blood.
    for virulence in ("routine", "serious"):
        _, _, ttl = by_cell[(virulence, "accept_residual")]
        assert ttl is not None and ttl > 0

    # 4. min_signer_rank is monotone non-decreasing with virulence for the kinds present at all.
    for kind in DISPOSITION_KINDS:
        ranks = [by_cell[(v, kind)][1] for v in VIRULENCES if (v, kind) in by_cell]
        assert ranks == sorted(ranks), (
            f"min_signer_rank for {kind} is not monotone across virulence: {ranks}"
        )


@pytest.mark.schema
@pytest.mark.mi("MI10")
def test_subject_transition_edges_are_identical_for_both_subjects(conn: Any) -> None:
    """S16. The change_request is a gated subject in exactly the sense the permit is."""
    rows = conn.execute(
        "SELECT subject_kind, from_state::STRING, to_state::STRING FROM mainline.subject_transition"
    ).fetchall()
    assert len(rows) == 18, f"expected 18 edges (9 x 2 subjects), got {len(rows)}"
    by_kind: dict[str, set[tuple[str, str]]] = {k: set() for k in SUBJECT_KINDS}
    for kind, src, dst in rows:
        assert kind in by_kind, f"unknown subject_kind {kind!r}"
        by_kind[kind].add((src, dst))
    assert by_kind["permit"] == EXPECTED_EDGES
    assert by_kind["change_request"] == EXPECTED_EDGES, (
        "MI30 — a change_request merges only with zero open blocking checks — is unsatisfiable "
        "the moment the two subjects stop sharing one alphabet."
    )


@pytest.mark.schema
@pytest.mark.mi("MI10")
def test_merged_is_reachable_only_from_dispositioned_and_is_terminal_forward(conn: Any) -> None:
    """The epoch pin's precondition, asserted as data.

    If any edge reached ``merged`` from a state that is not ``dispositioned``, a subject could be
    merged without ever having passed through the point at which every open obligation carries a
    signature. If any edge left ``merged`` for a pre-merge state, a caller could reopen a completed
    transition and attach an obligation to it — which is exactly what ``ON UPDATE RESTRICT`` on the
    ``(subject_id, gate_epoch)`` composite FK exists to make physically impossible.
    """
    into_merged = conn.execute(
        "SELECT DISTINCT from_state::STRING FROM mainline.subject_transition "
        "WHERE to_state = 'merged'"
    ).fetchall()
    assert {r[0] for r in into_merged} == {"dispositioned"}

    out_of_merged = conn.execute(
        "SELECT DISTINCT to_state::STRING FROM mainline.subject_transition "
        "WHERE from_state = 'merged'"
    ).fetchall()
    assert {r[0] for r in out_of_merged} == {"suspended", "closed"}

    into_draft = conn.execute(
        "SELECT count(*) FROM mainline.subject_transition WHERE to_state = 'draft'"
    ).fetchone()
    assert into_draft is not None and into_draft[0] == 0, "nothing returns to draft"


@pytest.mark.schema
def test_enum_types_carry_exactly_the_declared_labels(conn: Any) -> None:
    """A typo in an ENUM label is permanent: five later CHECKs quote these strings literally."""
    expected = {
        "control_delta": ["introduce", "strengthen", "restate", "weaken", "remove"],
        "subject_state": [
            "draft",
            "checks_materialised",
            "dispositioned",
            "merged",
            "suspended",
            "closed",
            "abandoned",
        ],
        "disposition_kind": list(DISPOSITION_KINDS),
        "virulence_class": list(VIRULENCES),
        "blame_basis": [
            "asserted_document",
            "asserted_human",
            "derived_documentary",
            "inferred_semantic",
        ],
        "blame_state": ["active", "provisional", "dormant", "refuted"],
        "prop_state": [
            "proposed",
            "already_present",
            "conflicted",
            "adopted",
            "declined",
            "revoked",
        ],
    }
    for type_name, labels in expected.items():
        rows = conn.execute(
            "SELECT e.enumlabel FROM pg_catalog.pg_enum e "
            "JOIN pg_catalog.pg_type t ON t.oid = e.enumtypid "
            "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'mainline' AND t.typname = %s "
            "ORDER BY e.enumsortorder",
            (type_name,),
        ).fetchall()
        assert [r[0] for r in rows] == labels, (
            f"mainline.{type_name} labels or ORDER differ from ARCHITECTURE §5.0. "
            f"Order is part of the type: MI23 compares over it."
        )


# ── DM-10: every constraint and index is explicitly named ─────────────────────────────────────


_AUTO_CONSTRAINT_PATTERNS = (
    re.compile(r"_pkey$"),
    re.compile(r"^primary$"),
    re.compile(r"^check_"),
    re.compile(r"^unique_"),
    re.compile(r"_ref_"),
    re.compile(r"_key$"),
    re.compile(r"^\d"),
)

#: CockroachDB surfaces NOT NULL as a table constraint in some releases, with a synthesised name
#: that no human wrote and that DM-10 was never about. Those are skipped, and the skip is narrow.
_NOT_NULL_NAME = re.compile(r"_not_null$")


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_every_constraint_in_the_band_is_explicitly_named(conn: Any) -> None:
    """DM-10. The constraint name is the courtroom exhibit; ``check_permit_1`` is not an exhibit.

    Conformance cases assert an exact SQLSTATE *and an exact constraint name*, because the
    diagnosis is the deliverable. A system-generated name breaks that the moment a column is added
    and the generator renumbers.
    """
    rows = conn.execute(
        "SELECT table_schema, table_name, constraint_name, constraint_type "
        "FROM information_schema.table_constraints "
        "WHERE table_schema = ANY(%s) "
        "AND constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'CHECK', 'FOREIGN KEY')",
        (list(SCHEMAS),),
    ).fetchall()
    assert rows, "no constraints found — the band did not apply"

    offenders: list[str] = []
    for schema, table, name, kind in rows:
        if _NOT_NULL_NAME.search(name):
            continue
        if any(p.search(name) for p in _AUTO_CONSTRAINT_PATTERNS):
            offenders.append(f"{schema}.{table}.{name} ({kind})")
    assert not offenders, (
        "system-generated constraint names in the mainline* schemas (DM-10):\n  "
        + "\n  ".join(offenders)
    )


def _rows_by_column(conn: Any, statement: str) -> list[dict[str, Any]]:
    """Run a ``SHOW …`` and return dicts.

    By name, never by position: a column order change in a ``SHOW`` output must not silently
    turn an assertion into a different assertion that happens to hold.
    """
    with conn.cursor() as cur:
        cur.execute(statement)
        names = [d.name for d in (cur.description or [])]
        return [dict(zip(names, row, strict=False)) for row in cur.fetchall()]


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_every_secondary_index_in_the_band_is_explicitly_named(conn: Any) -> None:
    """DM-10 again, for indexes. ``SHOW INDEXES`` rather than information_schema: certain syntax."""
    offenders: list[str] = []
    for qualified in BAND_TABLES:
        for row in _rows_by_column(conn, f"SHOW INDEXES FROM {qualified}"):
            name = str(row["index_name"])
            if name.endswith("_pkey") or name == "primary":
                continue
            if "_auto_index_" in name or name.endswith("_key"):
                offenders.append(f"{qualified}.{name}")
    assert not offenders, f"system-generated index names (DM-10): {offenders}"


#: Markers CockroachDB emits in `SHOW CREATE TABLE` for a row-level-TTL table.
#:
#: NOT the bare substring "ttl": `mainline.clearance_legal` has a column called `max_ttl_hours`,
#: and a test that matched on "ttl" would have failed on it — reporting a TTL that is not there,
#: on the one table whose contents the product's central claim rests on. Caught by reading the
#: band back rather than by running it, which is exactly why the band gets read back.
_TTL_MARKERS = ("ttl_expire", "ttl_expiration_expression", "ttl_job_cron", "ttl = ", "ttl='on'")


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_no_row_level_ttl_anywhere_in_schema_mainline(conn: Any) -> None:
    """§4.1 law 13. Zero TTL in schema ``mainline``, forever.

    Expired rows are not filtered from query results — including from ``UPDATE`` and ``DELETE``
    (verified limitation F5) — which alone disqualifies TTL for evidentiary data. The
    Crimes (Document Destruction) Act 2006 (Vic) supplies the reason that matters more.
    """
    for qualified in BAND_TABLES:
        row = conn.execute(f"SHOW CREATE TABLE {qualified}").fetchone()
        assert row is not None
        create = " ".join(str(c) for c in row).lower()
        hits = [m for m in _TTL_MARKERS if m in create]
        assert not hits, f"{qualified} carries a row-level TTL ({hits})"


# ── ownership, the deny posture, and the probe ────────────────────────────────────────────────


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_mainline_owner_is_unassumable_and_owns_every_zone(conn: Any) -> None:
    """The claim migration 0006b makes, checked rather than asserted.

    ``CREATE ROLE IF NOT EXISTS`` would silently accept a pre-existing ``mainline_owner`` that
    somebody had given LOGIN to. A migration cannot check that; this can.
    """
    row = conn.execute(
        "SELECT rolcanlogin FROM pg_catalog.pg_roles WHERE rolname = 'mainline_owner'"
    ).fetchone()
    assert row is not None, "mainline_owner does not exist"
    assert row[0] is False, "mainline_owner can log in — it must be NOLOGIN and unassumable"

    members = conn.execute("SHOW GRANTS ON ROLE mainline_owner").fetchall()
    assert members == [], (
        f"mainline_owner has members: {members}. Unassumable means the membership set is empty, "
        f"so the identity that can DROP TRIGGER and bypass non-FORCEd RLS has no way in."
    )

    rows = _rows_by_column(conn, "SHOW SCHEMAS")
    assert rows and "owner" in rows[0], (
        f"SHOW SCHEMAS did not report an owner column on this cluster; columns were "
        f"{sorted(rows[0]) if rows else 'none'}. Ownership is the control migrations "
        f"0008a-0008e assert, so an unreadable owner is a failure, not a reason to skip."
    )
    owners = {str(r["schema_name"]): str(r["owner"]) for r in rows}
    for schema in SCHEMAS:
        assert owners.get(schema) == "mainline_owner", (
            f"schema {schema} is owned by {owners.get(schema)!r}, not mainline_owner"
        )


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_public_holds_nothing_on_the_mainline_zones(conn: Any) -> None:
    """Migrations 0007a-0007e and 0009f, re-asserted by GRANTS.yaml's ``revocations``.

    The two halves are NOT the same assertion. ``0007a``-``0007e`` revoke on the five MAINLINE
    zones, where ``public`` held nothing to begin with — a deny posture asserted rather than
    assumed. ``0009f`` revokes on the built-in ``public`` schema, where CockroachDB really does
    grant ``public`` both CREATE and USAGE out of the box (measured on v26.2.5). Only the second
    one changes anything on a clean cluster, and it is the one that stops any principal who can
    connect from creating an object inside the evidentiary database.
    """
    # By COLUMN NAME, not by "is the word 'public' anywhere in the row". `SHOW GRANTS ON SCHEMA
    # public` returns rows whose schema_name is literally 'public', so a substring test would
    # report the grantee as `public` on every row of that query and pass or fail for the wrong
    # reason in both directions.
    for schema in (*SCHEMAS, "public"):
        rows = _rows_by_column(conn, f"SHOW GRANTS ON SCHEMA {schema}")
        assert rows, f"SHOW GRANTS ON SCHEMA {schema} returned nothing at all"
        assert "grantee" in rows[0] and "privilege_type" in rows[0], (
            f"SHOW GRANTS columns are {sorted(rows[0])} on this cluster, so this test cannot see "
            f"who holds what. A privilege assertion that cannot read the grantee column would "
            f"pass vacuously, which is worse than failing."
        )
        leaked = [r for r in rows if str(r["grantee"]) == "public"]
        if schema == "public":
            offending = [r for r in leaked if str(r["privilege_type"]).upper() in {"CREATE", "ALL"}]
            assert not offending, (
                "`public` still holds CREATE on the built-in public schema. Migration "
                "0009f_revoke_create_public_schema.sql is the one revoke that changes something "
                f"on a clean cluster, and it did not take: {offending}"
            )
        else:
            assert not leaked, f"`public` holds a privilege on schema {schema}: {leaked}"


def _first_required_column(conn: Any, schema: str, table: str) -> str | None:
    """A NOT NULL column with no default and no generation — so the probe INSERT never succeeds."""
    row = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s "
        "AND is_nullable = 'NO' AND column_default IS NULL "
        "AND (is_generated IS NULL OR is_generated = 'NEVER') "
        "ORDER BY ordinal_position LIMIT 1",
        (schema, table),
    ).fetchone()
    return None if row is None else str(row[0])


def _probe_insert(conn: Any, role: str, schema: str, table: str, column: str) -> str | None:
    """Attempt an INSERT as ``role``. Returns the SQLSTATE, or None if it somehow succeeded.

    The inserted value is NULL into a NOT NULL column with no default, so the statement CANNOT
    succeed on its merits. That is what makes the probe safe to run over every table without a
    transaction: nothing is ever written, and the two outcomes are cleanly distinguishable —

        42501  the privilege check refused it   → the role may not write here
        23502  the not-null check refused it    → the role MAY write here, and the row was rejected
                                                  on its content, which is a different sentence
    """
    conn.execute(f"SET ROLE {quote_ident(role)}")
    try:
        conn.execute(f"INSERT INTO {schema}.{table} ({column}) VALUES (NULL)")
        return None
    except psycopg.Error as exc:
        return exc.sqlstate
    finally:
        conn.execute("RESET ROLE")


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_probe_harness_distinguishes_refusal_from_rejection(conn: Any) -> None:
    """The probe's own positive control, before any negative result from it is believed.

    A privilege probe that only ever asserts 42501 passes just as happily when ``SET ROLE`` is
    silently doing nothing, when the schema is unreachable for an unrelated reason, or when the
    table does not exist. So: one throwaway role WITH the grant must get 23502, and one WITHOUT it
    must get 42501, on the same table in the same run. If those two do not differ, every negative
    result in this file is worthless and the suite says so here rather than passing quietly.
    """
    suffix = uuid.uuid4().hex[:8]
    allowed, denied = f"mainline_probe_yes_{suffix}", f"mainline_probe_no_{suffix}"
    try:
        conn.execute(f"CREATE ROLE {allowed} WITH NOLOGIN")
        conn.execute(f"CREATE ROLE {denied} WITH NOLOGIN")
        conn.execute(f"GRANT USAGE ON SCHEMA mainline TO {allowed}")
        conn.execute(f"GRANT USAGE ON SCHEMA mainline TO {denied}")
        conn.execute(f"GRANT INSERT ON TABLE mainline.site TO {allowed}")

        column = _first_required_column(conn, "mainline", "site")
        assert column is not None

        granted_state = _probe_insert(conn, allowed, "mainline", "site", column)
        refused_state = _probe_insert(conn, denied, "mainline", "site", column)

        assert refused_state == "42501", (
            f"a role with no INSERT grant got {refused_state!r}, not 42501 — the probe is not "
            f"measuring privileges"
        )
        assert granted_state == "23502", (
            f"a role WITH the INSERT grant got {granted_state!r}, not 23502. If it is 42501, the "
            f"probe cannot tell a refusal from a rejection and every negative below is vacuous."
        )
    finally:
        # CockroachDB refuses `DROP ROLE` while any grant still references the role
        # (`DependentObjectsStillExist`), so the grants made above must come off first. Without
        # this the teardown raises, and — because it raises from a `finally` — it REPLACES
        # whatever the body was trying to report. A cleanup that can mask the assertion it is
        # cleaning up after is worse than no cleanup, so each statement is also individually
        # tolerant: the throwaway roles are suffixed with a fresh uuid4 and leaking one is
        # harmless, while losing the real diagnosis is not.
        conn.execute("RESET ROLE")
        for statement in (
            f"REVOKE INSERT ON TABLE mainline.site FROM {allowed}",
            f"REVOKE USAGE ON SCHEMA mainline FROM {allowed}",
            f"REVOKE USAGE ON SCHEMA mainline FROM {denied}",
            f"DROP ROLE IF EXISTS {allowed}",
            f"DROP ROLE IF EXISTS {denied}",
        ):
            try:
                conn.execute(statement)
            except psycopg.Error:  # noqa: PERF203 — per-statement tolerance is the point
                pass


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_privilege_probe_refuses_ungranted_writes(conn: Any) -> None:
    """§11.2, table by table, role by role, as ``42501`` rather than as a claim.

    The property, stated generally so that it keeps holding as later bands add tables: **for every
    role in GRANTS.yaml and every table that exists, if the matrix does not grant that role INSERT
    on that table, the INSERT is refused with 42501.**

    Today that covers this band's seven tables. When ``dm-periphery`` lands
    ``mainline_meas.external_attestation``, the brief's specific requirement — the Managed-MCP
    identity is refused everywhere except that one table — becomes a case of this property with no
    edit to this test. That is deliberate: a hand-written list of forbidden pairs rots the moment
    someone adds a table and forgets it, and forgetting is the whole failure mode.

    ``mainline_owner`` is excluded: it owns every table, so it holds every privilege implicitly.
    Its control is that nobody can become it, which ``test_mainline_owner_is_unassumable`` asserts.
    """
    matrix = yaml.safe_load(GRANTS_PATH.read_text(encoding="utf-8"))
    granted: set[tuple[str, str]] = set()
    for row in matrix.get("table_privileges", []) + matrix.get("subject_access_views", []):
        if "INSERT" in row["privileges"]:
            granted.add((row["role"], row["object"]))

    roles = [r["name"] for r in matrix["roles"] if r["name"] != "mainline_owner"]
    tables = conn.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE' "
        "ORDER BY table_schema, table_name",
        (list(SCHEMAS),),
    ).fetchall()
    assert tables, "no tables found — the band did not apply"

    failures: list[str] = []
    checked = 0
    for schema, table in tables:
        column = _first_required_column(conn, schema, table)
        if column is None:
            failures.append(f"{schema}.{table} has no NOT NULL column without a default to probe")
            continue
        for role in roles:
            if (role, f"{schema}.{table}") in granted:
                continue
            state = _probe_insert(conn, role, schema, table, column)
            checked += 1
            if state != "42501":
                failures.append(
                    f"{role} INSERT on {schema}.{table} returned {state!r}, expected 42501"
                )
    assert not failures, "\n".join(failures)
    assert checked >= len(roles), "the probe examined suspiciously few pairs"


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_mainline_auditor_cannot_read_the_business_record(conn: Any) -> None:
    """S13 and S14, stated as the two reads that must fail.

    The Managed-MCP identity reads ``mainline_audit`` views and nothing else. ``mainline_qa`` — the
    per-named-person zone — must never be reachable from an MCP account, ever; a connector
    credential for per-person distributions is the single worst credential this system could issue.
    """
    failures: list[str] = []
    conn.execute("SET ROLE mainline_auditor")
    try:
        for qualified in BAND_TABLES:
            try:
                conn.execute(f"SELECT 1 FROM {qualified} LIMIT 1").fetchall()
                failures.append(f"mainline_auditor could SELECT from {qualified}")
            except psycopg.Error as exc:
                if exc.sqlstate != "42501":
                    failures.append(
                        f"SELECT on {qualified} as mainline_auditor gave {exc.sqlstate}, not 42501"
                    )
        for schema in ("mainline", "mainline_qa", "mainline_ops"):
            try:
                conn.execute(f"CREATE TABLE {schema}.mcp_should_not_be_able_to (x INT)")
                failures.append(f"mainline_auditor created a table in {schema}")
            except psycopg.Error as exc:
                if exc.sqlstate != "42501":
                    failures.append(f"CREATE in {schema} gave {exc.sqlstate}, not 42501")
    finally:
        conn.execute("RESET ROLE")
    assert not failures, "\n".join(failures)


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_no_application_role_holds_ddl(conn: Any) -> None:
    """Without this, a compromised agent could ``DROP TRIGGER permit_merge_gate``.

    The central invariant would evaporate with no schema-change record. This is the denial that
    matters most in GRANTS.yaml and the one a reviewer should check first.
    """
    matrix = yaml.safe_load(GRANTS_PATH.read_text(encoding="utf-8"))
    application_roles = [
        r["name"]
        for r in matrix["roles"]
        if r["name"] not in {"mainline_owner", "mainline_migrator"}
    ]
    failures: list[str] = []
    for role in application_roles:
        conn.execute(f"SET ROLE {quote_ident(role)}")
        try:
            conn.execute(f"CREATE TABLE mainline.ddl_probe_{role} (x INT)")
            failures.append(f"{role} holds CREATE in schema mainline")
        except psycopg.Error as exc:
            if exc.sqlstate != "42501":
                failures.append(f"{role} CREATE gave {exc.sqlstate}, not 42501")
        finally:
            conn.execute("RESET ROLE")
    assert not failures, "\n".join(failures)


def _grant_snapshot(conn: Any) -> list[str]:
    snapshot: list[str] = []
    for schema in SCHEMAS:
        for row in conn.execute(f"SHOW GRANTS ON SCHEMA {schema}").fetchall():
            snapshot.append(f"SCHEMA {schema} :: " + " | ".join(str(c) for c in row))
    for qualified in BAND_TABLES:
        for row in conn.execute(f"SHOW GRANTS ON TABLE {qualified}").fetchall():
            snapshot.append(f"TABLE {qualified} :: " + " | ".join(str(c) for c in row))
    return sorted(snapshot)


@pytest.mark.schema
def test_grants_matrix_is_idempotent(conn: Any) -> None:
    """DM-7's whole premise: the matrix is RE-ASSERTED, on every environment, forever.

    A RESTORE into a fresh cluster does not carry grants, so ``grants apply`` runs again and again
    over a cluster that already has most of them. If a second run were not a no-op, drift-checking
    would be indistinguishable from drift-causing.
    """
    matrix = yaml.safe_load(GRANTS_PATH.read_text(encoding="utf-8"))
    before = _grant_snapshot(conn)
    apply_grants_matrix(conn, matrix)
    after_second = _grant_snapshot(conn)
    apply_grants_matrix(conn, matrix)
    after_third = _grant_snapshot(conn)
    assert before == after_second == after_third, (
        "re-applying GRANTS.yaml changed the privilege set:\n"
        f"  added on 2nd run:   {sorted(set(after_second) - set(before))}\n"
        f"  removed on 2nd run: {sorted(set(before) - set(after_second))}"
    )


# ── the DM-3 authoritative table, and identity ────────────────────────────────────────────────


#: One site INSERT, used by both site tests. `opened_at` is supplied explicitly rather than
#: left to the column default: for a real site it is the operational commissioning date, and a
#: test that leans on `DEFAULT now()` quietly endorses the reading of that column the migration
#: comment warns against.
_SITE_INSERT = (
    "INSERT INTO mainline.site "
    "(site_id, site_code, site_role, tenant_id, taxonomy_ver, opened_at) "
    "VALUES (%s, %s, %s, %s, 1, '2026-08-05T00:00:00Z')"
)


@pytest.mark.schema
def test_site_refuses_a_scope_token_rls_could_never_match(conn: Any) -> None:
    """An RLS policy that matches nothing does not error. It returns zero rows, silently, forever.

    ``USING (site_role = CURRENT_USER)`` compares against a value CockroachDB folded to lower case
    when the role was created unquoted. A ``site_role`` stored as ``SITE_NORTH`` therefore matches
    no session ever, and a tenancy control that fails closed and silent looks exactly like one that
    works — until someone notices a site has never seen its own data.
    """
    good = uuid.uuid4()
    conn.execute(
        _SITE_INSERT,
        (good, f"site-{good.hex[:8]}", f"site_{good.hex[:8]}", uuid.uuid4()),
    )
    bad = uuid.uuid4()
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            _SITE_INSERT,
            (bad, f"site-{bad.hex[:8]}", f"SITE_{bad.hex[:8]}", uuid.uuid4()),
        )
    assert caught.value.sqlstate == "23514"
    assert_names_constraint(caught.value, "site_role_is_lower_case")


@pytest.mark.schema
def test_site_codes_and_roles_are_unique(conn: Any) -> None:
    """Two sites sharing a scope token is two tenancies sharing a boundary."""
    first, second = uuid.uuid4(), uuid.uuid4()
    code, role = f"dup-{first.hex[:8]}", f"dup_{first.hex[:8]}"
    conn.execute(
        _SITE_INSERT,
        (first, code, role, uuid.uuid4()),
    )
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            _SITE_INSERT,
            (second, code, f"other_{second.hex[:8]}", uuid.uuid4()),
        )
    assert caught.value.sqlstate == "23505"


#: One person INSERT, used twice. `competency_snapshot` is cast EXPLICITLY to JSONB: psycopg sends
#: a Python `str` as text, and a text-to-JSONB coercion in an INSERT target list is not something
#: to leave to an implicit cast when the point of the test is a different refusal entirely — a
#: 42804 here would look like a passing `pytest.raises(psycopg.Error)` and prove nothing.
_PERSON_INSERT = (
    "INSERT INTO mainline.person (signer_sub, effective_from, org, rank, competency_source_id, "
    "competency_sha256, competency_snapshot, identity_source, enrolment_assurance) "
    "VALUES (%s, %s, 'ACME Mining', %s, %s, %s, '{}'::JSONB, "
    "'https://idp.example/acme', 'hr_system_of_record')"
)


@pytest.mark.schema
@pytest.mark.mi("MI27")
def test_person_is_a_temporal_series_not_a_mutable_row(conn: Any) -> None:
    """``PRIMARY KEY (signer_sub, effective_from DESC)``: a promotion is a new row, never an edit.

    The DESC ordering is not decoration. The projection triggers read "this signer's current row"
    on every disposition, and the descending primary index makes that the first key in the scan.
    """
    sub = f"oidc|{uuid.uuid4().hex[:12]}"
    for moment, rank in (("2027-01-01T00:00:00Z", 2), ("2028-01-01T00:00:00Z", 5)):
        conn.execute(_PERSON_INSERT, (sub, moment, rank, uuid.uuid4(), b"\x00" * 32))
    rows = conn.execute("SELECT rank FROM mainline.person WHERE signer_sub = %s", (sub,)).fetchall()
    assert [r[0] for r in rows] == [5, 2], (
        f"the primary index must yield the most recent row first; got {[r[0] for r in rows]}"
    )

    with pytest.raises(psycopg.Error) as caught:
        conn.execute(_PERSON_INSERT, (sub, "2029-01-01T00:00:00Z", 11, uuid.uuid4(), b"\x00" * 32))
    assert caught.value.sqlstate == "23514"
    # `person_rank_range`, not the authored `rank_in_lattice`. MR-1 makes `person` a SUBSTRATE
    # object emitted from templates/0021_identity.sql.j2, and MRR-2 accepts the rename knowingly:
    # the constraint name is the courtroom exhibit, only one set can be the exhibit, and it must
    # be the set a second TRAPPOINT vertical also produces. The corpus asserts exact names, so a
    # MAINLINE-only name here would be a case that passes for this vertical and no other.
    assert_names_constraint(caught.value, "person_rank_range")


@pytest.mark.schema
def test_signing_credential_refuses_an_unknown_attachment(conn: Any) -> None:
    """A platform passkey on a shared crew tablet is an identity belonging to the DEVICE.

    The type is closed here; the device policy is enforced at enrolment, because the database
    cannot know what a tablet is. What the database can refuse is a value outside the vocabulary,
    which is what stops a third attachment kind quietly appearing and defeating the rule.
    """
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.signing_credential (credential_id, signer_sub, public_key_cose, "
            "aaguid, transports, attachment, enrolment_assurance) "
            "VALUES (%s, 'oidc|x', %s, %s, ARRAY['usb'], 'shared-tablet', 'in_person_verified')",
            (b"\x01\x02\x03", b"\x04" * 8, b"\x05" * 16),
        )
    assert caught.value.sqlstate == "23514"
    # `credential_attachment_known`, not the authored `attachment_closed` — same MRR-2 reasoning
    # as `person_rank_range` above.
    assert_names_constraint(caught.value, "credential_attachment_known")


@pytest.mark.schema
def test_revoking_a_credential_never_removes_it(conn: Any) -> None:
    """A key revoked in 2031 still verifies the disposition it signed in 2029.

    The partial index ``by_signer … WHERE revoked_at IS NULL`` is what makes the live-credential
    read cheap without the revoked ones ever leaving the table — the verifier comes in by
    ``credential_id`` and uses the primary index.
    """
    cred = uuid.uuid4().bytes
    sub = f"oidc|{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO mainline.signing_credential (credential_id, signer_sub, public_key_cose, "
        "aaguid, transports, attachment, enrolment_assurance) "
        "VALUES (%s, %s, %s, %s, ARRAY['usb','nfc'], 'cross-platform', 'in_person_verified')",
        (cred, sub, b"\x06" * 64, b"\x07" * 16),
    )
    conn.execute(
        "UPDATE mainline.signing_credential SET revoked_at = '2031-01-01T00:00:00Z', "
        "revoke_reason = 'lost at the muster point' WHERE credential_id = %s",
        (cred,),
    )
    row = conn.execute(
        "SELECT public_key_cose, revoked_at FROM mainline.signing_credential "
        "WHERE credential_id = %s",
        (cred,),
    ).fetchone()
    assert row is not None, "the credential row was removed; history no longer verifies"
    assert row[0] == b"\x06" * 64
    assert row[1] is not None

    live = conn.execute(
        "SELECT count(*) FROM mainline.signing_credential "
        "WHERE signer_sub = %s AND revoked_at IS NULL",
        (sub,),
    ).fetchone()
    assert live is not None and live[0] == 0


@pytest.mark.schema
def test_retention_and_adm_registers_are_seeded_and_two_person_by_default(conn: Any) -> None:
    """Both registers exist, are populated, and default to the conservative posture."""
    classes = conn.execute(
        "SELECT class_id, min_years, destruction_requires_two_person FROM mainline.retention_class"
    ).fetchall()
    assert len(classes) >= 6
    assert all(row[2] is True for row in classes), (
        "every retention class must require two-person destruction, including the privacy "
        "rectification class — the exception is exercised visibly or not at all"
    )
    by_id = {row[0]: row[1] for row in classes}
    assert by_id["notifiable_incident"] == 5

    adm = conn.execute(
        "SELECT class_id, personal_info_used FROM mainline.adm_decision_class"
    ).fetchall()
    assert len(adm) >= 5
    empties = {row[0] for row in adm if not row[1]}
    assert {"recall_admission", "blocking_check_materialisation"} <= empties, (
        "the two decisions the product is built on must read no personal information at all — "
        "that is the substantive APP 1.7 disclosure, and it is only true if the register says so"
    )
