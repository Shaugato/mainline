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
from typing import Any, Iterable

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

#: The migration numbers this worker owns, in application order. Files outside this list are
#: deliberately NOT applied: the suite proves that the recall band applies forward from clean on
#: its own, which is what its ``done_when`` asks for.
RECALL_MIGRATION_NUMBERS: tuple[int, ...] = (
    40, 41, 42, 43, 44, 45, 46,
    80, 81, 82, 83, 84, 85, 86, 87, 88,
    112, 113, 114,
    136, 137, 138, 139,
)


def recall_migration_files() -> list[Path]:
    """Every reserved recall migration, in numeric order. Missing files are an error."""
    found: dict[int, Path] = {}
    for path in MIGRATIONS_DIR.glob("*.sql"):
        head = path.name.split("_", 1)[0]
        if head.isdigit():
            number = int(head)
            if number in RECALL_MIGRATION_NUMBERS:
                if number in found:
                    raise RuntimeError(
                        f"two files claim migration {number:04d}: "
                        f"{found[number].name} and {path.name}"
                    )
                found[number] = path
    missing = [n for n in RECALL_MIGRATION_NUMBERS if n not in found]
    if missing:
        raise RuntimeError(
            "missing reserved recall migrations: "
            + ", ".join(f"{n:04d}" for n in missing)
        )
    return [found[n] for n in RECALL_MIGRATION_NUMBERS]


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
    """
    try:
        catalogue = conn.execute(f"SHOW CONSTRAINTS FROM {schema}.{table}").fetchall()
    except psycopg.Error:
        return None
    for row in catalogue:
        record = [str(value) for value in row]
        if constraint in record:
            for text in record:
                if "CHECK" in text.upper():
                    return _expression_only(text)
    return None


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
        assert state in GATE_REFUSALS, (
            f"the database refused with {state}, which is not a modelled gate refusal "
            f"({sorted(GATE_REFUSALS)}). Message: {exc}"
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
