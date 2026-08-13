# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Tier-1 schema suite for migrations 0032-0036 — the activity taxonomy, the event, and the
severity record (worker ``dm-blame``, band 0032-0039 in
``verticals/mainline/db/migrations.allocation.toml``).

What this band owns, and therefore what this file may honestly assert:

* ``mainline.activity_node`` — the functional archival taxonomy, three levels, level 1 frozen
  because its code is a physical vector-index prefix;
* ``mainline.event`` — the bitemporal event with three severities and ``model_cannot_arm``
  (**MI14**: an LLM's rating may never arm a blocking gate);
* ``mainline.event_edge`` — the event DAG the blame closure's recursive walk traverses;
* ``mainline.control_failure`` — ICAM and bowtie normalised to one shape, with the closed
  ``control_class`` join key the ``derived_documentary`` blame basis depends on;
* ``mainline.event_severity_revision`` — ``downgrade_needs_new_rater`` and ``substantive``,
  the two constraints that price the cheapest attack on the whole design.

What this band does NOT own, and what this file therefore does not pretend to prove:

* **MI13** (``inference_never_blocks``) is a CHECK on ``blame_edge``, migration 0037;
* **MI15** / **MI26** (blame ancestry never shrinks; the closure is monotone) are triggers on
  ``clause_blame_closure``, migrations 0038 and 0130-0199;
* **MI16** (every bonded severity-5 event is blocking) is ``fn_bonded_sev5``, already shipped by
  the recall band against tables this one supplies.

This band ships the *rated event* — the ultimate source of the one scalar everything
ancestry-conditioned in MAINLINE reads. It asserts that the rating cannot be armed by a machine
and cannot be quietly lowered by one person. It does not assert that lowering it propagates,
because that propagation does not exist yet, and there is one deliberately RED test below saying
so in the sharpest available terms.

Running it
----------
The static tier needs nothing but the repository and runs anywhere. The cluster tier is marked
``requires_cluster`` and finds a CockroachDB v26.2 in this order, **skipping with a reason**
rather than faking anything: ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL``, then a
``cockroach`` binary on ``PATH``, then a running Docker daemon. Nothing in this band is done on
the basis of a skipped run.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from trappoint_testkit import pinned_image

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Paths and band constants
# ══════════════════════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"
CORPUS_GAZETTEER = (
    REPO_ROOT
    / "verticals"
    / "mainline"
    / "packages"
    / "mainline-corpus"
    / "src"
    / "mainline_corpus"
    / "gazetteer"
)

#: The band this worker owns, exclusively.
BAND_FIRST, BAND_LAST = 32, 36

#: Everything numbered at or below this must exist before the band applies. 0024 (commit_obj) is
#: `dm-spine`'s; when it is absent the cluster fixture substitutes a clearly-labelled stand-in.
PREREQ_LAST = 31

BAND_TABLES = (
    "mainline.activity_node",
    "mainline.event",
    "mainline.event_edge",
    "mainline.control_failure",
    "mainline.event_severity_revision",
)

#: The four mandatory header keys the runner's linter enforces on every migration.
REQUIRED_HEADER_KEYS = ("-- MI:", "-- I:", "-- COUNSEL-GATED:", "-- RATIONALE:")

#: MR-5, the one filename convention: ``NNNN[a-z]_lower_snake_slug.sql``. Four digits, an optional
#: SINGLE lowercase letter, a snake slug with **no second dot**, and ``.sql``. ``.up.sql`` is banned
#: — not as a style preference, but because it names a ``.down.sql`` counterpart that is illegal at
#: or below the protected floor (DM-14), and because ``_version_of()`` strips both suffixes alike,
#: so a ``.up.sql`` twin of a ``.sql`` file claims the same version and ``discover()`` refuses the
#: whole tree.
MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

VALID_MI = frozenset(f"MI{n:02d}" for n in range(1, 31))
VALID_I = frozenset(f"I{n:02d}" for n in range(1, 17))

#: Constraint names that are quoted in ARCHITECTURE §5.4 / §16 and asserted by name in the
#: conformance corpus. Renaming one is a breaking change to an exhibit, not a refactor.
LOAD_BEARING_NAMES = {
    "0032_activity_node.sql": ("l1_frozen",),
    "0033_event.sql": ("model_cannot_arm",),
    "0034_event_edge.sql": ("no_self_edge",),
    "0035_control_failure.sql": ("evidence_span_is_a_pair",),
    "0036_event_severity_revision.sql": ("downgrade_needs_new_rater", "substantive"),
}

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-event-severity-schema-test"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 600.0

#: `mainline.commit_obj` is migration 0024, owned by `dm-spine`. `event_severity_revision`
#: composite-FKs nothing but takes a plain FK onto it, so the band cannot apply without it. When
#: 0024 has not landed, this stand-in is created INSTEAD — shape-faithful to ARCHITECTURE §5.2 so
#: the FK means what it will mean, and labelled so that no reader mistakes it for the real file.
COMMIT_OBJ_STANDIN = """
CREATE TABLE mainline.commit_obj (
  commit_id      BYTES  NOT NULL,
  site_id        UUID   NOT NULL,
  gen            INT8   NOT NULL,
  ref_name       STRING NOT NULL,
  committed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  author_sub     STRING NOT NULL,
  message        STRING NOT NULL,
  envelope       JSONB  NOT NULL,
  envelope_bytes BYTES  NOT NULL,
  sig            BYTES  NULL,
  CONSTRAINT commit_obj_pk PRIMARY KEY (commit_id),
  CONSTRAINT id_is_sha256 CHECK (length(commit_id) = 32),
  CONSTRAINT gen_positive CHECK (gen >= 0)
)
"""


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A comment- and string-aware SQL reader.
#
# Every file in this band is mostly prose, and the prose is full of apostrophes ("the operator's
# permit"). A scanner that looks for quotes before comment markers reads `operator's permit` as
# the start of a string literal and swallows the rest of the file, which would let a
# two-statement file through the one-statement lint. The state machine is the fix and
# `test_the_scanner_survives_apostrophes_in_prose` is its self-test, run before it is trusted.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def strip_sql_comments(text: str) -> str:
    """Remove ``--`` and ``/* */`` comments, preserving string and identifier literals."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
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


def table_body(create_table_sql: str) -> str:
    """Return the text between the outermost parentheses of a ``CREATE TABLE``."""
    start = create_table_sql.index("(")
    depth = 0
    for index in range(start, len(create_table_sql)):
        if create_table_sql[index] == "(":
            depth += 1
        elif create_table_sql[index] == ")":
            depth -= 1
            if depth == 0:
                return create_table_sql[start + 1 : index]
    raise AssertionError("unbalanced parentheses in CREATE TABLE")


def top_level_items(body: str) -> list[str]:
    """Split a ``CREATE TABLE`` body into its comma-separated top-level items."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return [item for item in items if item]


def band_files() -> list[Path]:
    """The 0032-0036 migrations, ordered by version.

    Read by SHAPE (``MR5_FILENAME``) rather than by a hardcoded list, so that a stray file landing
    inside this band is caught by ``test_band_is_dense_and_exclusive`` instead of being silently
    skipped. The shape filter is also what excludes a ``.up.sql`` twin: ``_version_of()`` strips
    ``.sql`` and ``.up.sql`` alike, so a twin claims the same version and would be linted twice
    while the runner refuses the tree outright.
    """
    found: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or MR5_FILENAME.match(path.name) is None:
            continue
        if BAND_FIRST <= int(path.name[:4]) <= BAND_LAST:
            found.append((int(path.name[:4]), path))
    return [p for _, p in sorted(found)]


def prerequisite_files() -> list[Path]:
    """Every migration numbered at or below ``PREREQ_LAST`` that currently exists.

    ``NNNNa_`` suffixed files are included and ordered after their base number: other bands use
    that spelling for an addendum to a numbered file (``0029a_clause_version_trgm``), and a
    prerequisite reader that silently skipped them would apply an incomplete spine and then blame
    this band for the consequences.

    Selected by shape and never by name. Bands 0001-0031 belong to other domains — most of
    0001-0023 is RENDERED from ``packages/trappoint-sql/templates/`` under MR-1 — so this file
    asserts nothing whatever about them; it applies what is there, best-effort, and says so in
    ``prerequisite_notes`` when one fails.
    """
    found: list[tuple[int, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or MR5_FILENAME.match(path.name) is None:
            continue
        match = re.match(r"^(\d{4})([a-z]?)_", path.name)
        if match and int(match.group(1)) <= PREREQ_LAST:
            found.append((int(match.group(1)), match.group(2), path))
    return [p for _, _, p in sorted(found)]


def header_value(text: str, key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key):
            return stripped[len(key) :].strip()
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — no cluster, no driver, no network. These run everywhere.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_scanner_survives_apostrophes_in_prose() -> None:
    """Self-test of this file's own scanner, before it is trusted to lint anything."""
    sample = (
        "-- the operator's permit, not ours; and it isn't the contractor's either\n"
        "/* a block comment with a ; and an apostrophe: don't */\n"
        "SELECT 'a;b', 'it''s fine';\n"
    )
    statements = split_statements(sample)
    assert len(statements) == 1, statements
    assert statements[0].startswith("SELECT")
    assert "a;b" in statements[0]


def test_band_is_dense_and_exclusive() -> None:
    """0032-0036, no gaps, no duplicates, no strays."""
    files = band_files()
    numbers = [int(p.name[:4]) for p in files]
    assert numbers == list(range(BAND_FIRST, BAND_LAST + 1)), (
        f"the event-severity band must be dense over {BAND_FIRST:04d}-{BAND_LAST:04d}; "
        f"got {numbers}"
    )
    for path in files:
        assert MR5_FILENAME.match(path.name), (
            f"{path.name} does not match NNNN[a-z]_lower_snake_slug.sql (MR-5, the one filename "
            "convention). Ordering is lexicographic on the whole stem, so a name outside that "
            "shape has no defined position; `.up.sql` is banned because it names a `.down.sql` "
            "counterpart that is illegal by construction, and because two suffix chains coexisting "
            "invisibly is what let two domains implement this band's neighbours twice."
        )
    strays = sorted(
        p.name
        for p in MIGRATIONS_DIR.iterdir()
        if p.is_file()
        and re.match(r"^\d{4}", p.name)
        and BAND_FIRST <= int(p.name[:4]) <= BAND_LAST
        and MR5_FILENAME.match(p.name) is None
    )
    assert not strays, (
        f"files inside {BAND_FIRST:04d}-{BAND_LAST:04d} that MR-5 refuses: {strays}. A `.up.sql` "
        "twin claims the same version as its `.sql` sibling and `discover()` refuses the whole "
        "tree; a second dot in the slug does the same for a different reason."
    )


def test_no_down_migration_in_the_band() -> None:
    """DM-14. Down-migrating an evidentiary table is destruction of evidence, not a rollback."""
    strays = [
        p.name
        for p in MIGRATIONS_DIR.glob("*.down.sql")
        if re.match(r"^\d{4}_", p.name) and BAND_FIRST <= int(p.name[:4]) <= BAND_LAST
    ]
    assert not strays, f".down.sql is illegal at or below the protected floor: {strays}"


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_every_file_carries_the_mandatory_header_block(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for key in REQUIRED_HEADER_KEYS:
        assert header_value(text, key) is not None, f"{path.name} is missing `{key}`"

    cited = re.findall(r"MI\d{2}", header_value(text, "-- MI:") or "")
    assert cited, f"{path.name} cites no MI id (ARCHITECTURE §18: every migration cites one)"
    assert not set(cited) - VALID_MI, f"{path.name} cites MI ids outside MI01-MI30: {cited}"

    i_cited = re.findall(r"\bI\d{2}\b", header_value(text, "-- I:") or "")
    assert i_cited, f"{path.name} cites no TRAPPOINT invariant in `-- I:`"
    assert not set(i_cited) - VALID_I, f"{path.name} cites ids outside I01-I16: {i_cited}"

    gated = (header_value(text, "-- COUNSEL-GATED:") or "").lower()
    assert gated.startswith("no"), (
        f"{path.name} claims to be counsel-gated. The counsel-gated five are 0066-0069 and 0086 "
        f"(DM-17); 0001-0065 are counsel-independent by construction."
    )
    assert len(header_value(text, "-- RATIONALE:") or "") >= 40, (
        f"{path.name}'s RATIONALE is too short to be one"
    )


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_exactly_one_statement_per_file(path: Path) -> None:
    """The runner does not wrap a body in a transaction, so a two-statement file is not atomic."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    assert len(statements) == 1, (
        f"{path.name} parses to {len(statements)} statements, not 1:\n"
        + "\n---\n".join(s[:200] for s in statements)
    )


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_no_banned_constructs(path: Path) -> None:
    """§4.1 law 9. The ledger is gap-free by CAS, so a gap must MEAN tampering.

    F4 of the platform ground truth measured ``CREATE SEQUENCE`` as *succeeding* on the target
    cluster, which is exactly why this lint is load-bearing rather than decorative: nothing about
    the platform stops a future migration from reintroducing one.
    """
    body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
    for banned in ("create sequence", "nextval", "unique_rowid", " serial", "\tserial"):
        assert banned not in body, f"{path.name} uses the banned construct {banned!r}"


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_no_check_reads_another_row_or_the_clock(path: Path) -> None:
    """DM-4 / constraint 5. A CHECK sees only the row being written.

    ``now()`` appears in this band exactly once per file that needs it — as a column DEFAULT —
    and a CHECK that reached for it would be a constraint whose truth value changes while the row
    sits still. A subquery in a CHECK is worse: it is a cross-row read that the optimiser is under
    no obligation to re-evaluate, which is how a projection gets *trusted* instead of enforced.
    """
    statement = split_statements(path.read_text(encoding="utf-8"))[0]
    for item in top_level_items(table_body(statement)):
        if not re.match(r"^CONSTRAINT\s+\w+\s+CHECK\b", item, re.IGNORECASE):
            continue
        lowered = item.lower()
        for forbidden in ("now(", "current_timestamp", "select ", "::jsonb", " ? "):
            assert forbidden not in lowered, (
                f"{path.name}: CHECK {item.split()[1]} contains {forbidden!r}. A CHECK may read "
                f"only the row being written (DM-4)."
            )


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_every_constraint_is_explicitly_named(path: Path) -> None:
    """DM-10, asserted against the FILE and not only against the cluster.

    The cluster test proves the database ended up with named constraints; this one proves nobody
    wrote an anonymous one and relied on CockroachDB's generator to be stable. The constraint name
    is the courtroom exhibit — ``check_event_3`` is not an exhibit, and it renumbers the moment a
    column is added above it.
    """
    statement = split_statements(path.read_text(encoding="utf-8"))[0]
    anonymous: list[str] = []
    for item in top_level_items(table_body(statement)):
        if re.match(r"^CONSTRAINT\s+\w+\b", item, re.IGNORECASE):
            continue
        if re.match(r"^(INDEX|UNIQUE\s+INDEX|INVERTED\s+INDEX|FAMILY)\b", item, re.IGNORECASE):
            continue
        lowered = item.lower()
        for keyword in ("primary key", "unique", "check", "references", "foreign key"):
            if keyword in lowered:
                anonymous.append(f"{item[:120]}  ← anonymous {keyword.upper()}")
                break
    assert not anonymous, (
        f"{path.name} declares constraints CockroachDB will have to name for us (DM-10):\n  "
        + "\n  ".join(anonymous)
    )


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_the_load_bearing_constraint_names_are_verbatim(path: Path) -> None:
    """These names are quoted in ARCHITECTURE and asserted by name in the conformance corpus."""
    body = strip_sql_comments(path.read_text(encoding="utf-8"))
    for name in LOAD_BEARING_NAMES[path.name]:
        assert re.search(rf"CONSTRAINT\s+{name}\b", body), (
            f"{path.name} no longer declares CONSTRAINT {name}. That name appears in "
            f"ARCHITECTURE §5.4/§16 and in trappoint-conform's expected diagnoses; renaming it is "
            f"a breaking change to an exhibit, not a refactor."
        )


def test_model_cannot_arm_is_spelled_exactly_as_mi14_states_it() -> None:
    """MI14, read off the file rather than off the docstring.

    A CHECK that said ``severity_gate <= 4`` or ``severity_basis != 'model_rated'`` alone would
    pass every other test in this file and would not be MI14. So the predicate itself is asserted,
    not merely the presence of a constraint with the right name.
    """
    body = strip_sql_comments((MIGRATIONS_DIR / "0033_event.sql").read_text(encoding="utf-8"))
    normalised = " ".join(body.split()).lower()
    assert (
        "constraint model_cannot_arm check (severity_gate < 4 or severity_basis <> 'model_rated')"
        in normalised
    ), (
        "0033's model_cannot_arm is not the MI14 predicate. It must be exactly\n"
        "  CHECK (severity_gate < 4 OR severity_basis <> 'model_rated')\n"
        "— a model may rate an event at 5 and say so; it may not thereby arm a gate."
    )


def test_the_gate_severity_is_not_chained_to_the_potential_severity() -> None:
    """A recorded ABSENCE, because the obvious constraint would break the case MI14 exists for.

    ``severity_gate >= severity_potential`` looks like an oversight waiting to be fixed. It is
    not: the reference corpus carries an event whose ``severity_potential`` is 5, whose
    ``severity_basis`` is ``model_rated`` and whose ``severity_gate`` is 3 — a model said "this
    could have killed someone" and the gate did not arm. Adding that constraint would make that
    row unrepresentable, and the schema would quietly stop being able to record the exact
    situation the product was built to handle. This test fails if someone adds it later without
    reading this comment.
    """
    body = strip_sql_comments((MIGRATIONS_DIR / "0033_event.sql").read_text(encoding="utf-8"))
    normalised = " ".join(body.split()).lower()
    for forbidden in (
        "severity_gate >= severity_potential",
        "severity_potential <= severity_gate",
    ):
        assert forbidden not in normalised, (
            "0033 now chains severity_gate to severity_potential. Together with model_cannot_arm "
            "that makes a model-rated potential-5 near miss unrepresentable — see the anchor "
            "event in the reference corpus, and ARCHITECTURE §5.4."
        )


def test_closed_vocabularies_agree_with_the_reference_corpus() -> None:
    """The schema and the corpus must share one alphabet or the demo cannot load.

    ``control_failure``'s four closed vocabularies are the join surface between an event and a
    clause's Control Assertion Tuple. If the corpus emits ``task_or_environmental_condition`` and
    the CHECK spells it ``task_environment_condition``, every insert is a 23514 and the failure
    surfaces as "the demo corpus will not load" hours before it is needed. Cheap to assert here,
    expensive to discover there.
    """
    yaml = pytest.importorskip("yaml", reason="pyyaml is required to read the corpus gazetteer")
    classes_path = CORPUS_GAZETTEER / "control_classes.yaml"
    if not classes_path.is_file():
        pytest.skip(f"the reference corpus gazetteer is not present at {classes_path}")

    gazetteer = yaml.safe_load(classes_path.read_text(encoding="utf-8"))
    body = strip_sql_comments(
        (MIGRATIONS_DIR / "0035_control_failure.sql").read_text(encoding="utf-8")
    )

    def vocabulary(constraint: str) -> set[str]:
        match = re.search(
            rf"CONSTRAINT\s+{constraint}\s+CHECK\s*\((.*?)\)\s*(?:,|$)",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None, f"0035 no longer declares CONSTRAINT {constraint}"
        return set(re.findall(r"'([a-z_]+)'", match.group(1)))

    icam = vocabulary("icam_tier_closed")
    assert set(gazetteer["icam_tiers"]) <= icam, (
        f"the corpus uses ICAM tiers the schema refuses: "
        f"{sorted(set(gazetteer['icam_tiers']) - icam)}"
    )

    modes = vocabulary("failure_mode_closed")
    roles = vocabulary("barrier_role_closed")
    energies = vocabulary("hazard_energy_closed")
    corpus_modes: set[str] = set()
    corpus_roles: set[str] = set()
    corpus_energies: set[str] = set()
    for entry in gazetteer["classes"]:
        corpus_modes |= set(entry["failure_modes"])
        corpus_roles.add(entry["barrier_role"])
        corpus_energies |= set(entry["hazard_energies"])
    assert corpus_modes <= modes, f"corpus failure modes the schema refuses: {corpus_modes - modes}"
    assert corpus_roles <= roles, f"corpus barrier roles the schema refuses: {corpus_roles - roles}"
    assert corpus_energies <= energies, (
        f"corpus hazard energies the schema refuses: {sorted(corpus_energies - energies)}"
    )


def test_the_taxonomy_gazetteer_satisfies_l1_frozen() -> None:
    """Level 1 is anchored to the ICMM register and frozen, in the corpus as in the CHECK."""
    yaml = pytest.importorskip("yaml", reason="pyyaml is required to read the corpus gazetteer")
    taxonomy_path = CORPUS_GAZETTEER / "taxonomy.yaml"
    if not taxonomy_path.is_file():
        pytest.skip(f"the reference corpus gazetteer is not present at {taxonomy_path}")

    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    level1 = taxonomy["level1"]
    assert level1, "the corpus taxonomy has no level-1 fonds"
    assert 12 <= len(level1) <= 25, (
        f"the level-1 register has {len(level1)} fonds; the design specifies 12-25, and the count "
        f"is the number of C-SPANN trees the coarse prefix will partition into"
    )
    for fonds in level1:
        code = str(fonds["code"])
        assert code, "a level-1 code is empty; it is a physical vector-index prefix value"
        assert code == code.strip(), f"the level-1 code {code!r} is padded; a prefix value is not"
        assert fonds["series"], f"{code} has no level-2 series, so level 3 is unreachable"

    body = strip_sql_comments(
        (MIGRATIONS_DIR / "0032_activity_node.sql").read_text(encoding="utf-8")
    )
    normalised = " ".join(body.split()).lower()
    assert "constraint l1_frozen check (level <> 1 or frozen = true)" in normalised, (
        "0032's l1_frozen is not the ARCHITECTURE predicate. A level-1 code is baked into the "
        "physical vector index; re-inducting one is a re-partition, not an edit."
    )


# ── PL-2: the deliberately RED case ───────────────────────────────────────────────────────────


@pytest.mark.pl2_red
def test_pl2_red_severity_revision_provenance_is_not_yet_projected() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: ``dm-functions-triggers``, band 0130-0199.

    ``downgrade_needs_new_rater`` compares ``to_gate`` against ``from_gate`` and ``rater_sub``
    against ``prior_rater_sub``. Two of those four columns are supplied by the writer today, and a
    constraint is only as strong as the provenance of the columns it reads — that sentence is the
    whole of P2, and getting it wrong is precisely adversarial finding S1.

    The attack, in one INSERT: the event's real ``severity_gate`` is 5. Declare ``from_gate = 0``
    and ``to_gate = 3``. The CHECK reads that as an UPGRADE, ``rater_sub <> prior_rater_sub`` is
    never consulted, one person downgrades a fatality to a 3 with their own name in both rater
    columns, and no constraint anywhere fires.

    Until a ``CREATE FUNCTION`` in the migration set reads ``mainline.event`` and writes
    ``from_gate`` — RAISEing ``P0001`` when the event row is absent — this band ships a
    two-person rule that one person can satisfy alone. This test fails today for that reason and
    goes green the moment the projection lands. It is not ``xfail``: the ``mi-red`` job needs to
    see the failure, and an xfail that passes when it fails is exactly the accounting PL-2 exists
    to prevent.
    """
    projecting: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        lowered = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
        if not re.search(r"\bcreate\s+(or\s+replace\s+)?function\b", lowered):
            continue
        if "mainline.event" not in lowered:
            continue
        if re.search(r"\b(from_gate|prior_rater_sub)\b", lowered):
            projecting.append(path.name)

    assert projecting, (
        "PL-2 RED, as intended. No migration defines a function that reads mainline.event and "
        "writes event_severity_revision.from_gate / .prior_rater_sub, so:\n"
        "  * from_gate is client-supplied — declare 0 -> 3 on an event whose real severity_gate "
        "is 5 and downgrade_needs_new_rater reads the row as an upgrade;\n"
        "  * prior_rater_sub is client-supplied — name anyone and the two-person rule is met.\n"
        "Both columns must appear in TRIGGER-MAP.yaml with fn_severity_revision_project and "
        "SQLSTATE P0001. Owner of the fix: dm-functions-triggers, band 0130-0199. Promote the MI "
        "entry in mi_catalogue.yaml from `pending` to `enforced` when this goes green."
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


def _wait_until_ready(psycopg: Any, dsn: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
        except Exception:  # noqa: BLE001 — any failure here means "not yet"
            time.sleep(1.0)
        else:
            return True
    return False


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """A dead Docker daemon does not refuse ``docker info``; it BLOCKS.

    An uncaught ``TimeoutExpired`` in a fixture turns a run that should have SKIPPED into a suite
    of ERRORs, which is a different and much worse message to a reader.
    """
    try:
        return subprocess.run(
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


def _from_local_binary(psycopg: Any, tmp: Path) -> Cluster | None:
    binary = shutil.which("cockroach")
    if binary is None:
        return None
    port, http_port = _free_port(), _free_port()
    proc = subprocess.Popen(
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
    if _wait_until_ready(psycopg, dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on {port}", proc=proc)
    proc.terminate()
    return None


def _from_docker(psycopg: Any) -> Cluster | None:
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
    if _wait_until_ready(psycopg, dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on {port}", owns_docker=True)
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


@pytest.fixture(scope="session")
def driver() -> Any:
    return pytest.importorskip(
        "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
    )


@pytest.fixture(scope="session")
def cluster(driver: Any, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    found = (
        _from_env()
        or _from_local_binary(driver, tmp_path_factory.mktemp("crdb"))
        or _from_docker(driver)
    )
    if found is None:
        pytest.skip(
            "no CockroachDB v26.2 reachable. Provide $MAINLINE_TEST_DSN, a `cockroach` binary on "
            f"PATH, or a running Docker daemon for `docker run {CRDB_IMAGE}`. Migrations "
            "0032-0036 are NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


@dataclass
class Applied:
    dsn: str
    database: str
    commit_obj_is_a_standin: bool
    prerequisite_notes: list[str]


def _apply_file(driver: Any, conn: Any, path: Path, *, strict: bool) -> str | None:
    """Apply one migration. Return a note when it failed and ``strict`` is false.

    Prerequisites are applied best-effort ON PURPOSE. Bands 0001-0031 belong to other workers and
    are landing concurrently; a half-written sibling that raises here would report as "the
    event-severity band is broken", which is both false and the kind of message that gets a
    working band reverted. This band's OWN files are applied strictly — a failure there is this
    worker's failure and must read like one.
    """
    for statement in split_statements(path.read_text(encoding="utf-8")):
        try:
            conn.execute(statement)
        except driver.Error as exc:
            detail = (
                f"{path.name} failed to apply.\n"
                f"  sqlstate: {exc.sqlstate}\n"
                f"  error:    {exc}\n"
                f"  statement:\n{statement.strip()[:1500]}"
            )
            if strict:
                raise AssertionError(detail) from exc
            return f"{path.name}: {exc.sqlstate} {str(exc).splitlines()[0][:160]}"
    return None


@pytest.fixture(scope="session")
def applied(driver: Any, cluster: Cluster) -> Iterator[Applied]:
    """Apply every prerequisite that exists, then the band, into a fresh database."""
    from psycopg.conninfo import make_conninfo

    database = f"mainline_event_severity_{uuid.uuid4().hex[:10]}"
    with driver.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    dsn = make_conninfo(cluster.dsn, dbname=database)
    standin = False
    notes: list[str] = []
    with driver.connect(dsn, autocommit=True) as conn:
        for path in prerequisite_files():
            note = _apply_file(driver, conn, path, strict=False)
            if note is not None:
                notes.append(note)
        exists = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'mainline' AND table_name = 'commit_obj'"
        ).fetchone()
        if exists is None:
            conn.execute(COMMIT_OBJ_STANDIN)
            standin = True
        for path in band_files():
            _apply_file(driver, conn, path, strict=True)

    print(
        f"\n[event-severity] cluster:  {cluster.provenance}\n"
        f"[event-severity] database: {database}\n"
        f"[event-severity] applied {len(prerequisite_files())} prerequisites "
        f"({len(notes)} of them failed and were skipped) + {len(band_files())} band migrations"
        + ("; mainline.commit_obj is a STAND-IN (0024 has not landed)" if standin else "")
        + ("".join(f"\n[event-severity] prerequisite skipped — {n}" for n in notes))
    )
    try:
        yield Applied(
            dsn=dsn,
            database=database,
            commit_obj_is_a_standin=standin,
            prerequisite_notes=notes,
        )
    finally:
        with driver.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(driver: Any, applied: Applied) -> Iterator[Any]:
    """One autocommit connection per test.

    Autocommit and not a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it.
    """
    connection = driver.connect(applied.dsn, autocommit=True)
    try:
        yield connection
    finally:
        connection.close()


# ── helpers that mint legal rows, so that every refusal below is about ONE column ─────────────

_LONG_RATIONALE = (
    "The original rating relied on the potential-consequence field of the contractor's report, "
    "which the investigation has since shown described a different task on the same permit; the "
    "corrected classification is recorded here with the source paragraph cited in the commit."
)


def _digest(label: str) -> bytes:
    return hashlib.sha256(label.encode("utf-8")).digest()


def _new_site() -> uuid.UUID:
    """A fresh site per test is this suite's isolation primitive (xdist-safe)."""
    return uuid.uuid4()


def _insert_event(conn: Any, site: uuid.UUID, **overrides: Any) -> uuid.UUID:
    row = {
        "site_id": site,
        "external_ref": f"INC-{uuid.uuid4().hex[:8]}",
        "occurred_at": "2019-03-14T06:20:00+00:00",
        "kind": "incident",
        "title": "loss of isolation during pump seal replacement",
        "narrative": "the pump was returned to service before the trapped energy was proved dead",
        "source_object_key": "s3://mainline-raw/INC-0001.pdf#v1",
        "source_sha256": _digest("INC-0001"),
        "severity_actual": 4,
        "severity_potential": 5,
        "severity_gate": 4,
        "severity_basis": "coded_field",
        "canon_version": 1,
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    # S608 is suppressed and the suppression is narrow: the only text interpolated is the KEY SET
    # of a dict literal defined three lines above, and every VALUE travels as a bound parameter.
    # A test helper that built the value list by interpolation would be the defect S608 is for.
    result = conn.execute(
        f"INSERT INTO mainline.event ({columns}) VALUES ({placeholders}) RETURNING event_id",  # noqa: S608
        tuple(row.values()),
    ).fetchone()
    assert result is not None
    return uuid.UUID(str(result[0]))


def _insert_commit(conn: Any, site: uuid.UUID, label: str) -> bytes:
    commit_id = _digest(label)
    conn.execute(
        "INSERT INTO mainline.commit_obj "
        "(commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (commit_id, site, 1, "site/test/main", "sub-a", label, "{}", b"{}"),
    )
    return commit_id


def _refusal(driver: Any, conn: Any, statement: str, params: tuple[Any, ...]) -> Any:
    """Execute expecting a refusal, and return the exception. Fail loudly if it succeeded."""
    try:
        conn.execute(statement, params)
    except driver.Error as exc:
        return exc
    raise AssertionError(f"the database ACCEPTED a write it must refuse:\n  {statement}")


def _names_constraint(exc: Any, expected: str) -> None:
    """Assert the refusal identifies the constraint BY NAME, from either place it can appear.

    The conformance corpus asserts an exact SQLSTATE *and* an exact constraint name, because the
    diagnosis is the deliverable. If CockroachDB v26.2 carries the name in neither the structured
    error field nor the message, that is a PLATFORM FINDING affecting every such assertion in the
    repository — so the failure prints what the server actually said.
    """
    diag_name = getattr(getattr(exc, "diag", None), "constraint_name", None)
    message = str(exc)
    if diag_name == expected or expected in message:
        return
    raise AssertionError(
        f"the refusal did not name the constraint {expected!r}.\n"
        f"  diag.constraint_name: {diag_name!r}\n"
        f"  message:              {message}"
    )


# ── MI14 — a model-rated severity never arms the gate ─────────────────────────────────────────


@pytest.mark.requires_cluster
def test_mi14_a_model_rated_severity_cannot_arm_the_gate(driver: Any, conn: Any) -> None:
    """The single line this band exists for.

    Three assertions, and the two positive controls matter as much as the refusal: a test that
    only ever sees 23514 passes just as happily when the INSERT is failing for an unrelated
    reason, and MI14 that refused *everything* would be indistinguishable from MI14 working right
    up until the first legitimate severity-5 incident could not be recorded.
    """
    site = _new_site()

    # 1. A model may rate an event at 5 and say so — while the gate stays below the arming line.
    below = _insert_event(
        conn,
        site,
        severity_actual=1,
        severity_potential=5,
        severity_gate=3,
        severity_basis="model_rated",
    )
    assert below is not None

    # 2. A human or a coded field may arm the gate at 5.
    armed = _insert_event(
        conn,
        site,
        severity_actual=5,
        severity_potential=5,
        severity_gate=5,
        severity_basis="human_rated",
    )
    assert armed is not None

    # 3. A model may not.
    exc = _refusal(
        driver,
        conn,
        "INSERT INTO mainline.event (site_id, occurred_at, kind, title, narrative, "
        "source_object_key, source_sha256, severity_actual, severity_potential, severity_gate, "
        "severity_basis, canon_version) "
        "VALUES (%s, %s, 'incident', 't', 'n', 'k', %s, 3, 5, 4, 'model_rated', 1)",
        (site, "2019-03-14T06:20:00+00:00", _digest("mi14")),
    )
    assert exc.sqlstate == "23514", f"MI14 must be a CHECK refusal, got {exc.sqlstate}"
    _names_constraint(exc, "model_cannot_arm")


@pytest.mark.requires_cluster
def test_an_event_cannot_be_ingested_before_it_occurred(driver: Any, conn: Any) -> None:
    """The bitemporal pair, in the one direction that is nonsense."""
    site = _new_site()
    exc = _refusal(
        driver,
        conn,
        "INSERT INTO mainline.event (site_id, occurred_at, ingested_at, kind, title, narrative, "
        "source_object_key, source_sha256, severity_actual, severity_potential, severity_gate, "
        "severity_basis, canon_version) "
        "VALUES (%s, '2026-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00', 'incident', "
        "'t', 'n', 'k', %s, 1, 1, 1, 'coded_field', 1)",
        (site, _digest("bitemporal")),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "ingested_before_occurrence")


# ── the archival taxonomy ─────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_level_one_must_be_frozen_and_rootless(driver: Any, conn: Any) -> None:
    """``l1_frozen`` and ``l1_has_no_parent``: a fonds is a root and its code is an index prefix."""
    site = _new_site()
    conn.execute(
        "INSERT INTO mainline.activity_node "
        "(site_id, level, label, activity_root, taxonomy_ver, induced_by, frozen) "
        "VALUES (%s, 1, 'isolating stored energy before intrusive work', "
        "'ISOLATION-OF-STORED-ENERGY', 1, 'icmm_mue', true)",
        (site,),
    )

    exc = _refusal(
        driver,
        conn,
        "INSERT INTO mainline.activity_node "
        "(site_id, level, label, activity_root, taxonomy_ver, induced_by, frozen) "
        "VALUES (%s, 1, 'thawed fonds', 'ISOLATION-OF-STORED-ENERGY', 1, 'icmm_mue', false)",
        (site,),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "l1_frozen")


@pytest.mark.requires_cluster
def test_a_series_without_a_parent_is_refused(driver: Any, conn: Any) -> None:
    """An orphan scope is invisible to the ancestor walk MI16 depends on, and errors nowhere."""
    site = _new_site()
    exc = _refusal(
        driver,
        conn,
        "INSERT INTO mainline.activity_node "
        "(site_id, level, label, activity_root, taxonomy_ver, induced_by, frozen) "
        "VALUES (%s, 2, 'planning and permitting an isolation', 'ISOLATION-OF-STORED-ENERGY', "
        "1, 'human', false)",
        (site,),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "below_l1_has_a_parent")


@pytest.mark.requires_cluster
def test_two_events_cannot_share_one_external_reference(driver: Any, conn: Any) -> None:
    """``one_event_per_external_ref``. A re-ingest that forked the buyer's incident number would
    split one incident's blame across two rows, and each half would look complete.
    """
    site = _new_site()
    ref = f"INC-{uuid.uuid4().hex[:8]}"
    _insert_event(conn, site, external_ref=ref)
    exc = _refusal(
        driver,
        conn,
        "INSERT INTO mainline.event (site_id, external_ref, occurred_at, kind, title, narrative, "
        "source_object_key, source_sha256, severity_actual, severity_potential, severity_gate, "
        "severity_basis, canon_version) "
        "VALUES (%s, %s, '2019-03-14T06:20:00+00:00', 'incident', 't', 'n', 'k', %s, 1, 1, 1, "
        "'coded_field', 1)",
        (site, ref, _digest("dupe")),
    )
    assert exc.sqlstate == "23505"
    _names_constraint(exc, "one_event_per_external_ref")


# ── the control failure — the join key and the quote discipline ───────────────────────────────


def _control_failure_sql() -> str:
    return (
        "INSERT INTO mainline.control_failure "
        "(event_id, control_class, barrier_role, failure_mode, icam_tier, hazard_energy, "
        "evidence_span, quote_sha256) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )


@pytest.mark.requires_cluster
def test_a_control_failure_carries_a_real_quote_and_a_known_tier(driver: Any, conn: Any) -> None:
    """``evidence_span_is_a_pair``, ``quote_sha256_is_a_digest`` and ``icam_tier_closed``.

    ``INT8[2]`` is declaration, not enforcement — neither PostgreSQL nor CockroachDB checks an
    array dimension — so the pair-ness is asserted here against a live cluster rather than assumed
    from the type. Nullable evidence is how a control failure becomes an allegation; a span of
    three integers is a span nobody can render.
    """
    site = _new_site()
    event = _insert_event(conn, site)

    # The legal row, first, so every refusal below differs from it in exactly one place.
    conn.execute(
        _control_failure_sql(),
        (
            event,
            "POSITIVE_ISOLATION_APPLICATION",
            "preventive",
            "bypassed",
            "absent_or_failed_defence",
            "electrical",
            [1204, 1391],
            _digest("quote"),
        ),
    )

    exc = _refusal(
        driver,
        conn,
        _control_failure_sql(),
        (
            event,
            "POSITIVE_ISOLATION_APPLICATION",
            "preventive",
            "bypassed",
            "absent_or_failed_defence",
            "electrical",
            [1204, 1391, 1500],
            _digest("quote"),
        ),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "evidence_span_is_a_pair")

    exc = _refusal(
        driver,
        conn,
        _control_failure_sql(),
        (
            event,
            "POSITIVE_ISOLATION_APPLICATION",
            "preventive",
            "bypassed",
            "absent_or_failed_defence",
            "electrical",
            [1204, 1391],
            b"short",
        ),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "quote_sha256_is_a_digest")

    exc = _refusal(
        driver,
        conn,
        _control_failure_sql(),
        (
            event,
            "POSITIVE_ISOLATION_APPLICATION",
            "preventive",
            "bypassed",
            "task_environment_condition",
            "electrical",
            [1204, 1391],
            _digest("quote"),
        ),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "icam_tier_closed")


# ── the event DAG ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_an_event_cannot_be_its_own_precursor(driver: Any, conn: Any) -> None:
    """``no_self_edge``. The closure's only cycle guard is a depth cap; a 1-cycle burns it."""
    site = _new_site()
    event = _insert_event(conn, site)
    exc = _refusal(
        driver,
        conn,
        "INSERT INTO mainline.event_edge (child_event_id, parent_event_id, relation) "
        "VALUES (%s, %s, 'precursor_of')",
        (event, event),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "no_self_edge")


# ── the severity revision — the cheapest attack, priced ───────────────────────────────────────


def _revision_sql() -> str:
    return (
        "INSERT INTO mainline.event_severity_revision "
        "(event_id, commit_id, from_gate, to_gate, rationale, rater_sub, prior_rater_sub, sig) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )


@pytest.mark.requires_cluster
def test_an_upgrade_is_free_and_a_downgrade_costs_a_second_person(driver: Any, conn: Any) -> None:
    """``downgrade_needs_new_rater``, with both halves asserted.

    Raising a severity adds obligations, so it must be cheap — a system that makes it expensive to
    admit something was worse than recorded teaches people not to. Lowering one subtracts
    obligations other people are relying on, so it costs a second named person.
    """
    site = _new_site()
    event = _insert_event(conn, site)

    # An upgrade by the same rater: free.
    conn.execute(
        _revision_sql(),
        (event, _insert_commit(conn, site, "up"), 3, 5, _LONG_RATIONALE, "sub-a", "sub-a", b"sig"),
    )

    # A downgrade by a different rater: allowed, and loud.
    conn.execute(
        _revision_sql(),
        (
            event,
            _insert_commit(conn, site, "down-ok"),
            5,
            3,
            _LONG_RATIONALE,
            "sub-b",
            "sub-a",
            b"sig",
        ),
    )

    # A downgrade by the SAME rater: refused.
    exc = _refusal(
        driver,
        conn,
        _revision_sql(),
        (
            event,
            _insert_commit(conn, site, "down-bad"),
            5,
            3,
            _LONG_RATIONALE,
            "sub-a",
            "sub-a",
            b"sig",
        ),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "downgrade_needs_new_rater")


@pytest.mark.requires_cluster
def test_a_re_rating_without_reasons_is_refused(driver: Any, conn: Any) -> None:
    """``substantive``. Crude on purpose: 120 characters is longer than "reviewed" and "n/a"."""
    site = _new_site()
    event = _insert_event(conn, site)
    exc = _refusal(
        driver,
        conn,
        _revision_sql(),
        (event, _insert_commit(conn, site, "terse"), 5, 3, "reviewed", "sub-b", "sub-a", b"sig"),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "substantive")


@pytest.mark.requires_cluster
def test_a_no_op_revision_is_refused(driver: Any, conn: Any) -> None:
    """``a_revision_changes_something``.

    Without it, one person accumulates no-op revisions whose ``prior_rater_sub`` they also choose,
    building a chain of their own until the two-person rule is satisfied by nobody.
    """
    site = _new_site()
    event = _insert_event(conn, site)
    exc = _refusal(
        driver,
        conn,
        _revision_sql(),
        (
            event,
            _insert_commit(conn, site, "noop"),
            4,
            4,
            _LONG_RATIONALE,
            "sub-b",
            "sub-a",
            b"sig",
        ),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "a_revision_changes_something")


@pytest.mark.requires_cluster
def test_pl2_red_one_person_can_still_downgrade_a_fatality(driver: Any, conn: Any) -> None:
    """RED BY DESIGN (PL-2), executed against a real cluster. Fix: ``dm-functions-triggers``.

    The static PL-2 case above proves no projection function exists. This one performs the attack
    it enables, so the red is a transcript rather than an inference:

        the event's real severity_gate is 5
        one person inserts (from_gate = 0, to_gate = 3, rater_sub = prior_rater_sub = 'sub-a')
        downgrade_needs_new_rater reads 3 >= 0 and passes it as an UPGRADE
        the row now says the event was re-rated to 3, by one person, with nobody's countersignature

    Every constraint in 0036 is correct and every one of them is satisfied. The defect is
    entirely in the PROVENANCE of ``from_gate``, which is what P2 is about and what adversarial
    finding S1 was. When ``fn_severity_revision_project`` overwrites ``from_gate`` from
    ``mainline.event``, this INSERT becomes a 23514 on ``downgrade_needs_new_rater`` and the
    assertion below goes green.
    """
    site = _new_site()
    event = _insert_event(
        conn,
        site,
        severity_actual=5,
        severity_potential=5,
        severity_gate=5,
        severity_basis="coded_field",
    )
    commit_id = _insert_commit(conn, site, "s1-attack")

    accepted = True
    try:
        conn.execute(
            _revision_sql(),
            (event, commit_id, 0, 3, _LONG_RATIONALE, "sub-a", "sub-a", b"sig"),
        )
    except driver.Error:
        accepted = False

    stored = conn.execute(
        "SELECT from_gate, to_gate FROM mainline.event_severity_revision WHERE event_id = %s",
        (event,),
    ).fetchall()

    assert not accepted, (
        "PL-2 RED, as intended, and this is the attack transcript.\n"
        f"  mainline.event.severity_gate = 5\n"
        f"  the accepted revision row(s)  = {stored}\n"
        "  rater_sub == prior_rater_sub == 'sub-a'\n"
        "One person just re-rated a fatality-severity event to 3 by declaring from_gate = 0, and "
        "downgrade_needs_new_rater read it as an upgrade. The CHECK is right; the provenance of "
        "the column it reads is not. Fix: fn_severity_revision_project (band 0130-0199) must "
        "overwrite from_gate from mainline.event inside the same transaction and RAISE P0001 "
        "when the event row is absent, and prior_rater_sub must come from the latest prior "
        "revision. Then this INSERT is a 23514 on downgrade_needs_new_rater."
    )


# ── shape assertions over the applied band ────────────────────────────────────────────────────


def _rows_by_column(conn: Any, statement: str) -> list[dict[str, Any]]:
    """Run a ``SHOW …`` and return dicts, by name and never by position."""
    with conn.cursor() as cur:
        cur.execute(statement)
        names = [d.name for d in (cur.description or [])]
        return [dict(zip(names, row, strict=False)) for row in cur.fetchall()]


#: Shapes CockroachDB synthesises when nobody named the constraint. `^fk_.*_ref_` is ANCHORED
#: rather than a bare `_ref_` substring, and the difference is not pedantry: a bare substring
#: also matches names a human deliberately wrote — `event_external_ref_unique` was one, and it
#: was flagged as system-generated on the first live run of this suite. A DM-10 probe that
#: reports false positives is a probe somebody will eventually relax the wrong way.
_AUTO_CONSTRAINT_PATTERNS = (
    re.compile(r"_pkey$"),
    re.compile(r"^primary$"),
    re.compile(r"^check_"),
    re.compile(r"^unique_"),
    re.compile(r"^fk_.*_ref_"),
    re.compile(r"_key$"),
    re.compile(r"^\d"),
)
_NOT_NULL_NAME = re.compile(r"_not_null$")


@pytest.mark.requires_cluster
def test_every_constraint_on_the_band_tables_is_named(conn: Any) -> None:
    """DM-10, as the cluster sees it. Complements the file-level test with what actually landed."""
    offenders: list[str] = []
    for qualified in BAND_TABLES:
        _, _, table = qualified.partition(".")
        rows = conn.execute(
            "SELECT constraint_name, constraint_type FROM information_schema.table_constraints "
            "WHERE table_schema = 'mainline' AND table_name = %s "
            "AND constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'CHECK', 'FOREIGN KEY')",
            (table,),
        ).fetchall()
        assert rows, f"{qualified} reports no constraints — the band did not apply"
        for name, kind in rows:
            if _NOT_NULL_NAME.search(str(name)):
                continue
            if any(p.search(str(name)) for p in _AUTO_CONSTRAINT_PATTERNS):
                offenders.append(f"{qualified}.{name} ({kind})")
    assert not offenders, "system-generated constraint names (DM-10):\n  " + "\n  ".join(offenders)


@pytest.mark.requires_cluster
def test_every_index_on_the_band_tables_is_named(conn: Any) -> None:
    """DM-10 for indexes. A ``…_auto_index_fk_…`` name is one CockroachDB chose, not one we did."""
    offenders: list[str] = []
    for qualified in BAND_TABLES:
        for row in _rows_by_column(conn, f"SHOW INDEXES FROM {qualified}"):
            name = str(row["index_name"])
            if name.endswith("_pkey") or name == "primary":
                continue
            if "_auto_index_" in name or name.endswith("_key"):
                offenders.append(f"{qualified}.{name}")
    assert not offenders, f"system-generated index names (DM-10): {offenders}"


#: Markers CockroachDB emits in `SHOW CREATE TABLE` for a row-level-TTL table. NOT the bare
#: substring "ttl": a column named `max_ttl_hours` exists elsewhere in this schema and would make
#: a substring test report a TTL that is not there.
_TTL_MARKERS = ("ttl_expire", "ttl_expiration_expression", "ttl_job_cron", "ttl = ", "ttl='on'")


@pytest.mark.requires_cluster
def test_no_row_level_ttl_on_any_band_table(conn: Any) -> None:
    """§4.1 law 13. Zero TTL in schema ``mainline``, forever — expired rows are not filtered from
    query results, including from UPDATE and DELETE, which alone disqualifies TTL for evidence.
    """
    for qualified in BAND_TABLES:
        row = conn.execute(f"SHOW CREATE TABLE {qualified}").fetchone()
        assert row is not None
        create = " ".join(str(c) for c in row).lower()
        hits = [m for m in _TTL_MARKERS if m in create]
        assert not hits, f"{qualified} carries a row-level TTL ({hits})"
