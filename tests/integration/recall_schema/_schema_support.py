# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Support code for the recall-schema illegal-history suite.

Nothing here asserts anything. It builds legal rows so that the test modules can be short
enough to read as what they are: a list of things the database must refuse, each naming the
exact SQLSTATE and the exact constraint or trigger that must do the refusing.

The refusal contract (ARCHITECTURE §16): ``40001`` is the only retryable code. ``23514`` /
``23503`` / ``23505`` / ``P0001`` are gate refusals. Any other SQLSTATE fails the suite,
because it means the database refused for a reason nobody modelled.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterable
from typing import Any

import psycopg

# ── repository layout ────────────────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
PREREQ_DIR = HERE / "prereq"


def repo_root() -> Path:
    """Walk up until the migrations directory is found; fail loudly rather than guess."""
    for parent in [HERE, *HERE.parents]:
        candidate = parent / "verticals" / "mainline" / "db" / "migrations"
        if candidate.is_dir():
            return parent
    raise RuntimeError(
        "cannot locate verticals/mainline/db/migrations above " + str(HERE)
    )


MIGRATIONS_DIR = repo_root() / "verticals" / "mainline" / "db" / "migrations"


# ── migration IDs, suffixes included ─────────────────────────────────────────────────────────
#
# A migration ID is a number and, under MR-5, an OPTIONAL lowercase band-overflow suffix:
# `0138`, then `0138a`, then `0139`. The suffix is not a variant of the file before it and it is
# not decoration — `0114a` and `0138a` carry the coarse cue projector and the weld that fastens
# it, an entire mechanism `0114`/`0138` do not contain.
#
# The selector used to read that head with ``head.isdigit()``. `"0138a".isdigit()` is False, so
# every MR-5 suffixed file in the tree — `0049b`, `0049c`, `0049d`, `0049y`, `0049z`, `0114a`,
# `0138a`, `0155a`, `0180a`… — was dropped WITHOUT A WORD, and the duplicate-number guard below
# was disabled for precisely the files most likely to collide. Both defects are one parser.

_MIGRATION_ID = re.compile(r"(\d{1,4})([a-z]*)")


def migration_id(text: str) -> tuple[int, str]:
    """``"0138a"`` → ``(138, "a")`` — the sort key that orders ``0138 < 0138a < 0139``.

    Raises ``ValueError`` rather than returning a sentinel: a name this band cannot order is a
    thing to report, never a thing to skip.
    """
    match = _MIGRATION_ID.fullmatch(text)
    if match is None:
        raise ValueError(
            f"{text!r} is not a migration ID: expected digits and an optional lowercase "
            "MR-5 band-overflow suffix, e.g. `0138` or `0138a`"
        )
    return int(match.group(1)), match.group(2)


def migration_id_of(path: Path) -> tuple[int, str]:
    """The sort key of a migration FILE: ``0138a_trg_….sql`` → ``(138, "a")``."""
    return migration_id(path.name.split("_", 1)[0])


def format_migration_id(key: tuple[int, str]) -> str:
    """``(138, "a")`` → ``"0138a"`` — the spelling used in every message and in the band below."""
    number, suffix = key
    return f"{number:04d}{suffix}"


# ── the reserved band ────────────────────────────────────────────────────────────────────────
#
# THIS BAND IS NOT SELF-CONTAINED, AND SAYING SO OUT LOUD IS THE POINT.
#
# The comment that used to sit here claimed "the suite proves that the recall band applies
# forward from clean on its own". That claim was FALSE, and its falseness is the whole finding
# behind the 2026-08-10 db-schema failure. `0139_trg_candidate_project.sql` welds a trigger to
# `mainline.fn_candidate_project()`, which is created twenty-nine files earlier by `0110` — and
# `0110` was not in this list. A full-chain `trappoint migrate up` can NEVER expose that, because
# the full chain always applies `0110` before `0139`; only this declared cut can. So the local
# tree applied 271/271 while CI failed on `unknown function: mainline.fn_candidate_project()`,
# and the divergence was never an environment difference: the two runs apply different sets.
#
# What this list therefore is: a DECLARED CUT through the chain, in which every producer the cut
# consumes is named next to the consumer that needs it. `_assert_band_is_self_contained` below
# makes that a machine check, so the next cut that forgets a producer is refused by name before a
# single statement reaches a cluster.
RECALL_MIGRATION_NUMBERS: tuple[str, ...] = (
    # the cue, its two vector sidecars, the lexical tables and the bond
    "0040", "0041", "0042", "0043", "0044", "0045", "0046",
    # policy, run, candidate, silence, calibration, thymogate, certificate, stage
    "0080", "0081", "0082", "0083", "0084", "0085", "0086", "0087", "0088",
    # PRODUCER, not a recall table. `mainline.fn_candidate_project()` lives here and `0139`
    # welds a trigger to it. Omitting it is the defect this file was repaired for: the band
    # welded to a producer it did not carry, and the full chain hid that forever.
    "0110",
    # the recall function stratum. `0114a` is `0114`'s MR-5 overflow — a SECOND function
    # (`fn_cue_coarse_project`), not a revision of the first — and `0138a` welds it.
    "0112", "0113", "0114", "0114a",
    # the recall trigger stratum. `0138a` is the coarse sidecar's weld and is what
    # test_rc01b / test_rc02b address by name; `0139` is `0110`'s consumer.
    "0136", "0137", "0138", "0138a", "0139",
)


# ── what the band creates, and what it consumes ──────────────────────────────────────────────

_CREATE_FUNCTION_NAMED = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_][\w.]*)\s*\(", re.IGNORECASE
)
_CREATE_TABLE_NAMED = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)", re.IGNORECASE
)
_CREATE_TRIGGER_WELD = re.compile(
    r"CREATE\s+TRIGGER\s+(\w+)\s+.*?\bON\s+([A-Za-z_][\w.]*)\s+.*?"
    r"\bEXECUTE\s+FUNCTION\s+([A-Za-z_][\w.]*)\s*\(",
    re.IGNORECASE | re.DOTALL,
)
_REFERENCES_TABLE = re.compile(r"\bREFERENCES\s+([A-Za-z_][\w.]*)", re.IGNORECASE)


def _uncommented(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", text)


def _objects_created_by(path: Path) -> set[str]:
    code = _uncommented(path)
    created = {m.group(1).lower() for m in _CREATE_FUNCTION_NAMED.finditer(code)}
    created |= {m.group(1).lower() for m in _CREATE_TABLE_NAMED.finditer(code)}
    return created


_PRODUCERS: dict[str, Path] = {}


def producer_of(object_name: str) -> Path | None:
    """The migration ANYWHERE in the chain that creates ``object_name``, or ``None``.

    The chain, not the band, deliberately: the question this answers is always "which file does
    the cut not carry", and answering it from inside the cut would answer "none of them".
    """
    if not _PRODUCERS:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            for created in _objects_created_by(path):
                _PRODUCERS.setdefault(created, path)
    return _PRODUCERS.get(object_name.lower())


def _add_it(object_name: str) -> str:
    """The one sentence a person hitting a missing producer needs, with the file named."""
    path = producer_of(object_name)
    if path is None:
        return (
            f"  nothing in {MIGRATIONS_DIR.name}/ creates {object_name}: it is neither in the "
            f"band nor in the chain, so this is a missing MIGRATION, not a missing declaration"
        )
    return (
        f"  producer: {path.name}\n"
        f"  fix:      add \"{format_migration_id(migration_id_of(path))}\" to "
        f"RECALL_MIGRATION_NUMBERS in {Path(__file__).name}, in numeric position"
    )


def _assert_band_is_self_contained(files: list[Path]) -> None:
    """Every function a band trigger executes, and every table it names, is produced IN the cut.

    This is the check whose absence turned a one-line declaration defect into an
    ``UndefinedFunction`` raised at DDL time inside a session fixture, measured 2026-08-10 as 24
    test ERRORS and 1 failure with nothing in any of them naming `0110`. It needs no cluster, it
    runs before anything is applied, and it names the FILE rather than only the SQLSTATE.
    """
    available: set[str] = set(_objects_created_by(PREREQ_DIR / "00_consumed_tables.sql"))
    problems: list[str] = []
    for path in files:
        code = _uncommented(path)
        # A file's own objects count as available TO ITSELF — a table with a self-referencing
        # foreign key is one statement, not an ordering violation. Everything else is still
        # judged against what the cut has applied BEFORE this file, which is the property that
        # catches a consumer placed ahead of its producer.
        available |= _objects_created_by(path)
        for weld in _CREATE_TRIGGER_WELD.finditer(code):
            trigger, table, function = weld.group(1), weld.group(2), weld.group(3)
            if function.lower() not in available:
                problems.append(
                    f"{path.name} welds trigger `{trigger}` to {function}(), which the band "
                    f"does not create.\n{_add_it(function)}"
                )
            if table.lower() not in available:
                problems.append(
                    f"{path.name} welds trigger `{trigger}` onto {table}, which the band does "
                    f"not create.\n{_add_it(table)}"
                )
        for reference in _REFERENCES_TABLE.finditer(code):
            table = reference.group(1)
            if table.lower() not in available:
                problems.append(
                    f"{path.name} carries a foreign key to {table}, which the band does not "
                    f"create.\n{_add_it(table)}"
                )
    if problems:
        raise RuntimeError(
            "the recall band is not self-contained — it consumes objects its declared cut "
            "through the chain does not produce, so it cannot apply forward from clean:\n\n"
            + "\n\n".join(problems)
            + "\n\nA full-chain `trappoint migrate up` cannot reproduce this: the chain always "
            "applies the producer first. Only this band can, which is why the check is here."
        )


def recall_migration_files() -> list[Path]:
    """Every reserved recall migration, in application order.

    Missing files, duplicate IDs, an out-of-order declaration, a filename this parser cannot
    order, and a consumed object the cut does not produce are all errors, and each of them says
    which file to look at.
    """
    wanted: dict[tuple[int, str], str] = {}
    for declared in RECALL_MIGRATION_NUMBERS:
        key = migration_id(declared)
        if key in wanted:
            raise RuntimeError(
                f"RECALL_MIGRATION_NUMBERS declares {format_migration_id(key)} twice "
                f"({wanted[key]!r} and {declared!r})"
            )
        wanted[key] = declared
    if list(wanted) != sorted(wanted):
        raise RuntimeError(
            "RECALL_MIGRATION_NUMBERS is not in application order; the band is applied in the "
            "order it is written, so a misplaced entry applies a consumer before its producer. "
            f"Declared: {list(RECALL_MIGRATION_NUMBERS)}"
        )

    found: dict[tuple[int, str], Path] = {}
    unorderable: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            key = migration_id_of(path)
        except ValueError as exc:
            unorderable.append(f"{path.name} — {exc}")
            continue
        if key not in wanted:
            continue
        if key in found:
            raise RuntimeError(
                f"two files claim migration {format_migration_id(key)}: "
                f"{found[key].name} and {path.name}"
            )
        found[key] = path
    if unorderable:
        raise RuntimeError(
            "these files are in the migrations directory and this selector cannot order them, "
            "so it will not silently pretend they are absent:\n  " + "\n  ".join(unorderable)
        )

    missing = [format_migration_id(k) for k in wanted if k not in found]
    if missing:
        raise RuntimeError("missing reserved recall migrations: " + ", ".join(missing))

    files = [found[key] for key in wanted]
    _assert_band_is_self_contained(files)
    return files


# ── refusal diagnosis ────────────────────────────────────────────────────────────────────────

#: CockroachDB v26.2 spells these two `42883` / `42P01` refusals exactly this way. Both mean the
#: same thing inside this suite — the declared cut is missing a producer — and neither says so.
_UNKNOWN_FUNCTION = re.compile(r"unknown function:\s*([A-Za-z_][\w.]*)\s*\(", re.IGNORECASE)
_UNDEFINED_RELATION = re.compile(r'relation "([^"]+)" does not exist', re.IGNORECASE)


def producer_hint(message: str) -> str | None:
    """Turn an `UndefinedFunction`/`UndefinedTable` message into the file that would fix it.

    A SQLSTATE tells you the object was absent. It does not tell you that the band is a cut
    through a longer chain, nor which file of that chain produces the object — and the person
    reading the failure should not have to diff two migration sets to find out.
    """
    for pattern in (_UNKNOWN_FUNCTION, _UNDEFINED_RELATION):
        match = pattern.search(message)
        if match is None:
            continue
        name = match.group(1)
        return (
            f"{name} does not exist in this database because the recall band applies a DECLARED "
            f"CUT through the migration chain, not the whole chain.\n{_add_it(name)}"
        )
    return None


# ── statement splitting ──────────────────────────────────────────────────────────────────────
#
# Three of the reserved files carry two statements (0086, 0114/0138 and 0139 say why in their own
# headers), and they must be applied ONE AT A TIME. Sending a whole file makes it a single
# implicit transaction, and a multi-statement DDL transaction on CockroachDB is a different
# animal from a sequence of schema changes: `CREATE TRIGGER` referring to a function created in
# the same transaction, and `ALTER TABLE … ADD CONSTRAINT` against a table created in it, are
# exactly the shapes that behave differently there. The deployed migration runner applies one
# statement per file (§18); the suite must not be more permissive than the thing it is testing.
#
# So there is a splitter, and it is dollar-quote aware — the objection to writing one was that
# it would have to parse `$$` bodies, which is true, and is thirty lines.

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def split_statements(sql: str) -> list[str]:
    """Split a migration file into statements on top-level semicolons.

    Aware of: ``--`` line comments, ``/* */`` block comments, single-quoted strings with ``''``
    escaping, and dollar-quoted bodies with or without a tag. Anything that is only whitespace
    or comments is dropped.
    """
    statements: list[str] = []
    start = 0
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "-" and sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end + 1
        elif ch == "/" and sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif ch == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    if sql.startswith("''", i):
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
        elif ch == "$":
            match = _DOLLAR_TAG.match(sql, i)
            if match is None:
                i += 1
                continue
            tag = match.group(0)
            end = sql.find(tag, match.end())
            i = n if end == -1 else end + len(tag)
        elif ch == ";":
            statements.append(sql[start:i])
            i += 1
            start = i
        else:
            i += 1
    statements.append(sql[start:])
    return [s for s in statements if _has_code(s)]


def _has_code(fragment: str) -> bool:
    """True when a fragment contains something other than whitespace and comments."""
    stripped = re.sub(r"/\*.*?\*/", " ", fragment, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    return bool(stripped.strip())


# ── vectors ──────────────────────────────────────────────────────────────────────────────────


def vector_literal(dimensions: int, seed: int = 0) -> str:
    """A deterministic unit-ish vector in pgvector text form.

    Deterministic on purpose: an ANN result that changes between runs because the fixture
    changed is indistinguishable from one that changes because the index changed.
    """
    digest = hashlib.sha256(f"mainline-recall-{seed}".encode()).digest()
    values = []
    for i in range(dimensions):
        byte = digest[i % len(digest)]
        values.append(round(((byte + i) % 251) / 251.0 - 0.5, 6))
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


# ── legal rows ───────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Event:
    event_id: uuid.UUID
    site_id: uuid.UUID
    severity_gate: int


@dataclass(frozen=True)
class Cue:
    cue_id: uuid.UUID
    event_id: uuid.UUID
    site_id: uuid.UUID
    scope_id: uuid.UUID
    facet: str


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def insert_activity_node(
    conn: psycopg.Connection,
    *,
    site_id: uuid.UUID,
    level: int = 2,
    taxonomy_ver: int = 1,
) -> uuid.UUID:
    scope_id = new_uuid()
    conn.execute(
        """
        INSERT INTO mainline.activity_node
          (scope_id, site_id, level, parent_scope, label, activity_root,
           taxonomy_ver, induced_by, frozen)
        VALUES (%s, %s, %s, NULL, %s, 'ISOLATION-OF-STORED-ENERGY', %s, 'human', %s)
        """,
        (
            scope_id,
            site_id,
            level,
            f"isolating stored energy before intrusive work {scope_id}",
            taxonomy_ver,
            level == 1,
        ),
    )
    return scope_id


def insert_event(
    conn: psycopg.Connection,
    *,
    site_id: uuid.UUID | None = None,
    severity_gate: int = 5,
    occurred_at: datetime | None = None,
) -> Event:
    event_id = new_uuid()
    site_id = site_id or new_uuid()
    occurred_at = occurred_at or (datetime.now(timezone.utc) - timedelta(days=4000))
    conn.execute(
        """
        INSERT INTO mainline.event
          (event_id, site_id, external_ref, occurred_at, kind, title, narrative,
           source_object_key, source_sha256, severity_actual, severity_potential,
           severity_gate, severity_basis, canon_version)
        VALUES (%s, %s, %s, %s, 'incident',
                'seal fire during compressor intervention',
                'Two contractors were burned when a seal failed during an intrusive task on a '
                'compressor that had not been positively isolated.',
                %s, %s, %s, %s, %s, 'coded_field', 1)
        """,
        (
            event_id,
            site_id,
            f"INC-{event_id.hex[:8]}",
            occurred_at,
            f"s3://mainline-raw/{event_id}",
            hashlib.sha256(event_id.bytes).digest(),
            severity_gate,
            severity_gate,
            severity_gate,
        ),
    )
    return Event(event_id=event_id, site_id=site_id, severity_gate=severity_gate)


def insert_cue(
    conn: psycopg.Connection,
    *,
    event: Event,
    scope_id: uuid.UUID,
    facet: str = "recurrence_test",
    scope_level: int = 2,
    prompt_version: str = "cue-v1",
) -> Cue:
    cue_id = new_uuid()
    conn.execute(
        """
        INSERT INTO mainline.event_cue
          (cue_id, event_id, site_id, scope_id, scope_level, facet, taxonomy_ver,
           cue_text, is_derived, gen_model, prompt_version)
        VALUES (%s, %s, %s, %s, %s, %s, 1,
                'recurs where an intrusive task begins before stored energy is positively '
                'isolated and proved dead', true, 'claude-opus-5', %s)
        """,
        (cue_id, event.event_id, event.site_id, scope_id, scope_level, facet, prompt_version),
    )
    return Cue(
        cue_id=cue_id,
        event_id=event.event_id,
        site_id=event.site_id,
        scope_id=scope_id,
        facet=facet,
    )


def insert_embedding(
    conn: psycopg.Connection,
    *,
    cue_id: uuid.UUID,
    site_id: uuid.UUID,
    scope_id: uuid.UUID,
    facet: str,
    seed: int = 1,
) -> None:
    """Insert into the prefixed sidecar with WHATEVER prefix the caller supplies.

    That is the whole point: the caller is the adversary here.
    """
    conn.execute(
        """
        INSERT INTO mainline.event_cue_embedding
          (cue_id, site_id, scope_id, facet, embed_model, index_gen, emb)
        VALUES (%s, %s, %s, %s, 'bge-large-en-v1.5@pinned', 'gen-0', %s::VECTOR(1024))
        """,
        (cue_id, site_id, scope_id, facet, vector_literal(1024, seed)),
    )


def insert_coarse(
    conn: psycopg.Connection,
    *,
    cue_id: uuid.UUID,
    tenant_id: uuid.UUID,
    severity_gate: int,
    seed: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.event_cue_coarse
          (cue_id, tenant_id, severity_gate, embed_model, index_gen, emb_coarse)
        VALUES (%s, %s, %s, 'bge-large-en-v1.5@pinned+pca256', 'gen-0', %s::VECTOR(256))
        """,
        (cue_id, tenant_id, severity_gate, vector_literal(256, seed)),
    )


def insert_bond(
    conn: psycopg.Connection,
    *,
    event_id: uuid.UUID,
    scope_id: uuid.UUID,
    taxonomy_ver: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.event_bond (event_id, scope_id, taxonomy_ver, bond_basis)
        VALUES (%s, %s, %s, 'coded')
        """,
        (event_id, scope_id, taxonomy_ver),
    )


def cosign_checkpoint(
    conn: psycopg.Connection, *, site_id: uuid.UUID, tree_size: int = 4096
) -> None:
    """A checkpoint that has left the trust boundary, with a witness signature on it."""
    site_code = str(site_id)
    conn.execute(
        """
        INSERT INTO mainline.ledger_checkpoint
          (site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, admissible)
        VALUES (%s, %s, %s, %s, %s, %s, %s, true)
        """,
        (
            site_code,
            tree_size,
            hashlib.sha256(b"root").digest(),
            f"mainline/{site_code}\n{tree_size}\n",
            json.dumps({"drand_round": 5_000_000}),
            hashlib.sha256(b"log-sig").digest(),
            hashlib.sha256(b"canon").digest(),
        ),
    )
    conn.execute(
        """
        INSERT INTO mainline.cosignature
          (site_code, tree_size, witness_id, trust_domain, adverse, sig)
        VALUES (%s, %s, 'witness-0', 'external_auditor', true, %s)
        """,
        (site_code, tree_size, hashlib.sha256(b"witness-sig").digest()),
    )


def insert_policy(
    conn: psycopg.Connection,
    *,
    anchored_tree_size: int | None,
    policy_version: str | None = None,
) -> str:
    policy_version = policy_version or f"rp-{new_uuid().hex[:8]}"
    conn.execute(
        """
        INSERT INTO mainline_meas.recall_policy
          (policy_version, taxonomy_ver, embed_model, gen_model, prompt_version, beam_size,
           tau, arms, calibration_set_sha256, author_sub, signature,
           anchored_tree_size, anchored_at, calibrator)
        VALUES (%s, 1, 'bge-large-en-v1.5@pinned', 'claude-opus-5', 'cue-v1', 64,
                %s, %s, %s, 'sub-calibration-author', %s, %s, %s, %s)
        """,
        (
            policy_version,
            json.dumps({"5": 0.35, "4": 0.45, "3": 0.60, "2": 0.75, "1": 0.85}),
            json.dumps({"levels": [1, 2, 3], "k": 12, "max_arms": 16}),
            hashlib.sha256(b"calibration-set").digest(),
            hashlib.sha256(b"policy-signature").digest(),
            anchored_tree_size,
            None if anchored_tree_size is None else datetime.now(timezone.utc),
            json.dumps(
                {
                    "kind": "isotonic_knots",
                    "version": 1,
                    "knots": [[0.0, 0.01], [0.31, 0.22], [0.52, 0.61], [1.0, 0.98]],
                }
            ),
        ),
    )
    return policy_version


RUN_COLUMNS = (
    "run_id, permit_id, site_id, corpus_commit, policy_version, index_plan_digest, "
    "index_generation, n_candidates, n_blocking, n_advisory, n_silenced, n_deduped, "
    "n_bonded_sev5, n_bonded_sev5_blocking"
)


def run_values(
    *,
    run_id: uuid.UUID,
    permit_id: uuid.UUID,
    site_id: uuid.UUID,
    policy_version: str,
    n_candidates: int = 0,
    n_blocking: int = 0,
    n_advisory: int = 0,
    n_silenced: int = 0,
    n_deduped: int = 0,
    n_bonded_sev5: int = 0,
    n_bonded_sev5_blocking: int = 0,
) -> tuple[Any, ...]:
    return (
        run_id,
        permit_id,
        site_id,
        hashlib.sha256(b"corpus-commit").digest(),
        policy_version,
        hashlib.sha256(b"explain-plan").digest(),
        "gen-0",
        n_candidates,
        n_blocking,
        n_advisory,
        n_silenced,
        n_deduped,
        n_bonded_sev5,
        n_bonded_sev5_blocking,
    )


INSERT_RUN_SQL = (
    f"INSERT INTO mainline_meas.recall_run ({RUN_COLUMNS}) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)


def insert_blocking_check(
    conn: psycopg.Connection,
    *,
    permit_id: uuid.UUID,
    site_id: uuid.UUID,
    precursor_event_id: uuid.UUID | None,
    origin: str = "bonded_sev5",
    severity: int = 5,
) -> uuid.UUID:
    check_id = new_uuid()
    conn.execute(
        """
        INSERT INTO mainline.blocking_check
          (check_id, subject_kind, permit_id, cr_id, site_id, precursor_event_id,
           origin, severity)
        VALUES (%s, 'permit', %s, NULL, %s, %s, %s, %s)
        """,
        (check_id, permit_id, site_id, precursor_event_id, origin, severity),
    )
    return check_id


# ── catalogue introspection ──────────────────────────────────────────────────────────────────


def trigger_names(conn: psycopg.Connection, schema: str, table: str) -> set[str]:
    """Every trigger name on a table, from whichever catalogue answers.

    ``pg_catalog.pg_trigger`` is tried first because it is the one CockroachDB populates for
    real triggers; ``information_schema.triggers`` is the fallback. If neither answers, that is
    reported as an empty set and the caller decides whether that is fatal.
    """
    names: set[str] = set()
    try:
        rows = conn.execute(
            """
            SELECT t.tgname
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = %s AND c.relname = %s
            """,
            (schema, table),
        ).fetchall()
        names.update(str(r[0]) for r in rows)
    except psycopg.Error:
        pass
    if not names:
        try:
            rows = conn.execute(
                """
                SELECT trigger_name FROM information_schema.triggers
                 WHERE event_object_schema = %s AND event_object_table = %s
                """,
                (schema, table),
            ).fetchall()
            names.update(str(r[0]) for r in rows)
        except psycopg.Error:
            pass
    return names


def check_constraint_expression(
    conn: psycopg.Connection, schema: str, table: str, constraint: str
) -> str | None:
    """The stored expression of a named CHECK, for error-message attribution.

    CockroachDB's ``23514`` message quotes the constraint EXPRESSION, not always its name
    (a documented-by-observation difference from PostgreSQL). Asserting "the exact constraint"
    therefore means: the message identifies the constraint either by name or by the expression
    that the catalogue says belongs to that name — and no other constraint on the table shares
    it. Both are exact; only one of them is a string the server happens to print.

    MEASURED 2026-08-10 on CockroachDB v26.2.5, the pin ``compose.yaml`` names — the row shape
    this must not be naive about::

        ['table_name', 'constraint_name', 'constraint_type', 'details', 'validated']
        ('t', 'sev_range', 'CHECK', 'CHECK ((severity BETWEEN 0 AND 5))', True)

    TWO columns satisfy ``"CHECK" in text.upper()`` and the useless one comes FIRST. Selecting on
    that substring returned ``_expression_only("CHECK")`` — the empty string — for every CHECK
    constraint in this suite, which `identifies()` then discarded as falsy. The attribution
    silently degraded to "the message must contain the constraint NAME", which CockroachDB's
    ``23514`` does not print, so every `assert_check_refusal` in the band failed with an empty
    ``catalogue expr:`` line. The discriminator is a parenthesised BODY, not the word.
    """
    try:
        catalogue = conn.execute(f"SHOW CONSTRAINTS FROM {schema}.{table}").fetchall()
    except psycopg.Error:
        return None
    for row in catalogue:
        record = [str(value) for value in row]
        if constraint in record:
            for text in record:
                if _CHECK_WITH_A_BODY.search(text):
                    return _expression_only(text)
    return None


#: `CHECK ((a = b))` — the `details` column. NOT the bare `CHECK` of `constraint_type`.
_CHECK_WITH_A_BODY = re.compile(r"CHECK\s*\(", re.IGNORECASE)


def _expression_only(details: str) -> str:
    """`CHECK ((a = b)) ENABLE` → `a = b`, so it can be matched inside an error message."""
    match = re.search(r"CHECK\s*(.*)", details, re.IGNORECASE | re.DOTALL)
    body = match.group(1) if match else details
    return re.sub(r"\b(ENABLE|NOT\s+VALID)\b", "", body, flags=re.IGNORECASE)


#: whitespace, parentheses, and CockroachDB's type annotations (`:::INT8`) — none of which are
#: printed identically by `SHOW CONSTRAINTS` and by the `23514` message.
_CASTS = re.compile(r":{2,3}[A-Za-z_][A-Za-z0-9_]*(\[\])?")
_NOISE = re.compile(r"[\s()]+")


def _normalise(text: str) -> str:
    return _NOISE.sub("", _CASTS.sub("", text)).lower()


def identifies(message: str, *candidates: str | None) -> bool:
    haystack = _normalise(message)
    return any(c and _normalise(c) in haystack for c in candidates)


# ── the refusal assertion ────────────────────────────────────────────────────────────────────

GATE_REFUSALS = frozenset({"23514", "23503", "23505", "P0001"})


@dataclass
class Refusal:
    sqlstate: str
    message: str
    constraint_name: str | None


def capture_refusal(fn, *args: Any, **kwargs: Any) -> Refusal:
    """Run something that must be refused and return the refusal, or fail loudly."""
    try:
        fn(*args, **kwargs)
    except psycopg.Error as exc:  # noqa: PERF203 - the exception IS the deliverable
        state = exc.sqlstate or ""
        constraint = None
        diag = getattr(exc, "diag", None)
        if diag is not None:
            constraint = getattr(diag, "constraint_name", None)
        # A `42883`/`42P01` here is never a gate refusal — it is the band missing a producer,
        # and `producer_hint` names the file rather than leaving a bare SQLSTATE behind.
        hint = producer_hint(str(exc))
        assert state in GATE_REFUSALS, (
            f"the database refused with {state}, which is not a modelled gate refusal "
            f"({sorted(GATE_REFUSALS)}). Message: {exc}"
            + (f"\n\n{hint}" if hint else "")
        )
        return Refusal(sqlstate=state, message=str(exc), constraint_name=constraint)
    raise AssertionError("the write was ACCEPTED; this history must be refused")


def assert_check_refusal(
    conn: psycopg.Connection,
    refusal: Refusal,
    *,
    schema: str,
    table: str,
    constraint: str,
) -> None:
    assert refusal.sqlstate == "23514", (
        f"expected 23514 on {constraint}, got {refusal.sqlstate}: {refusal.message}"
    )
    expression = check_constraint_expression(conn, schema, table, constraint)
    assert identifies(refusal.message, constraint, expression, refusal.constraint_name), (
        f"the refusal does not identify {schema}.{table} CONSTRAINT {constraint}.\n"
        f"  message:          {refusal.message}\n"
        f"  diag.constraint:  {refusal.constraint_name}\n"
        f"  catalogue expr:   {expression}"
    )


def assert_trigger_refusal(
    conn: psycopg.Connection,
    refusal: Refusal,
    *,
    message: str,
    schema: str,
    table: str,
    trigger: str,
) -> None:
    """P0001 with the exact diagnosis, raised on a table carrying the exact named trigger.

    A RAISE carries no trigger name, so attribution is made in two independent moves: the
    message text is exact, and the named trigger is proved present on the exact table. The
    unwelding suite closes the loop by dropping that trigger and showing the refusal goes away.
    """
    assert refusal.sqlstate == "P0001", (
        f"expected P0001 from {trigger}, got {refusal.sqlstate}: {refusal.message}"
    )
    assert message in refusal.message, (
        f"expected the exact diagnosis {message!r}, got: {refusal.message}"
    )
    present = trigger_names(conn, schema, table)
    assert trigger in present, (
        f"trigger {trigger} is not on {schema}.{table}; found {sorted(present)}"
    )


def rows(conn: psycopg.Connection, sql: str, params: Iterable[Any] = ()) -> list[tuple]:
    return conn.execute(sql, tuple(params)).fetchall()
