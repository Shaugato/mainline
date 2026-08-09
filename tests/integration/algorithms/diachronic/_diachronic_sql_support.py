# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Support code for the ORIGINDIFF SQL suite.  Asserts nothing itself.

The module name is deliberately not ``_support``.  pytest's prepend import mode
puts every collected test directory on ``sys.path``, so two modules sharing a name
resolve to whichever collection reached first — a silent failure that produces a
suite exercising somebody else's helpers.
``tests/integration/algorithms/lattice/_lattice_sql_support.py`` and
``tests/integration/algorithms/candidates/_support.py`` both already exist.

THE TWO MIGRATIONS THIS SUITE OWNS
----------------------------------
====================================  =======================================
``0049b_commutation_edge.sql``        the derived-dependency table
``0152_v_blame_origin.sql``           the bounded blame-origin candidate query
====================================  =======================================

Both were drafted under the revoked ``0200-0219`` annexe (``0206`` and ``0212``).
``0200`` and above is ``UNALLOCATED`` in
``verticals/mainline/db/migrations.allocation.toml`` and ``trappoint migrate lint``
rule B refuses any file that claims it, so they live in the algorithms domain's
granted bands instead.  This module resolves them **by name**, because their
numbers are granted rather than chosen, and resolves everything else **by
content**, so a renumber inside another lead's band does not silently reduce this
suite to a skip.

THE STAND-IN, WHAT IT COVERS, AND WHAT IT MUST NEVER COVER
-----------------------------------------------------------
``mainline.blame_edge``, ``mainline.clause_blame_closure`` and
``mainline.clause_blame_current`` belong to ``datamodel/dm-blame`` (band
``0032``-``0039z``).  When this suite was written only ``0032``-``0036`` were on
disk, so ``0152_v_blame_origin.sql`` could not be applied against the real tree at
all.

:func:`origin_stack` therefore applies a **stand-in** for exactly those three
objects, transcribed from ``ARCHITECTURE.md`` §5.4, and :func:`stood_in_for`
reports which ones it had to invent.  Every cluster-backed test in this directory
prints that list, so a green run never hides the substitution.

Two hard rules keep the stand-in from becoming a lie:

1. **It covers only objects that no migration creates.**  The moment ``dm-blame``
   lands, :func:`spine_migrations` finds the real files and the stand-in shrinks to
   nothing without a line of this module changing.
2. **It may never cover an object that exists.**  :func:`origin_stack` raises if a
   stand-in would shadow a real migration.  The DELTALATTICE suite's argument
   applies unchanged: a hand-written twin of a table that exists proves the test
   file is self-consistent and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

HERE = Path(__file__).resolve().parent

__all__ = [
    "BLAME_STANDIN_SQL",
    "MIGRATIONS_DIR",
    "OWNED_MIGRATIONS",
    "SPINE_OBJECTS",
    "STANDIN_OBJECTS",
    "Commit",
    "commit_id",
    "insert_blame_edge",
    "insert_clause",
    "insert_clause_version",
    "insert_closure",
    "insert_commit",
    "insert_commit_edge",
    "insert_doc",
    "insert_event",
    "migration",
    "origin_stack",
    "plan_scans",
    "repo_root",
    "rows",
    "spine_migrations",
    "split_statements",
    "stood_in_for",
]


def repo_root() -> Path:
    for parent in [HERE, *HERE.parents]:
        if (parent / "verticals" / "mainline" / "db" / "migrations").is_dir():
            return parent
    raise RuntimeError(f"cannot locate verticals/mainline/db/migrations above {HERE}")


MIGRATIONS_DIR: Final[Path] = repo_root() / "verticals" / "mainline" / "db" / "migrations"

OWNED_MIGRATIONS: Final[tuple[str, str]] = (
    "0049b_commutation_edge.sql",
    "0152_v_blame_origin.sql",
)

#: Everything the view and the table need, as ``(regex, human name)``, matched
#: against file *content*, ANCHORED AT COLUMN 0 with ``re.M``.  Anchoring is not
#: tidiness: every one of these files carries a `-- requires: 0001a CREATE SCHEMA
#: mainline` line in its header, and an unanchored probe matches the comment,
#: which silently drags a dozen unrelated migrations into the stack.  Measured:
#: it pulled in 0019, 0020, 0020a, 0032, 0040, 0043-0045 and 0072-0088 before the
#: anchor was added.  Order is the apply order and it is also the dependency
#: order; the files are re-sorted by name before use, which is what the deployed
#: runner does (MR-5: lexicographic on the whole version stem).
SPINE_OBJECTS: Final[tuple[tuple[str, str], ...]] = (
    (r"^CREATE\s+SCHEMA\s+(IF\s+NOT\s+EXISTS\s+)?mainline\b", "SCHEMA mainline"),
    (r"^CREATE\s+TYPE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.control_delta\b", "TYPE control_delta"),
    (
        r"^CREATE\s+TYPE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.virulence_class\b",
        "TYPE virulence_class",
    ),
    (r"^CREATE\s+TYPE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.blame_basis\b", "TYPE blame_basis"),
    (r"^CREATE\s+TYPE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.blame_state\b", "TYPE blame_state"),
    (r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.commit_obj\b", "TABLE commit_obj"),
    (r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.commit_edge\b", "TABLE commit_edge"),
    (r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.doc\b", "TABLE doc"),
    (r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause\b", "TABLE clause"),
    (
        r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause_version\b",
        "TABLE clause_version",
    ),
    (r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.event\b", "TABLE event"),
)

#: The three objects the stand-in may cover, and nothing else.  Each is
#: ``(regex, human name, ddl)``.
STANDIN_OBJECTS: Final[tuple[tuple[str, str, str], ...]] = (
    (
        r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.blame_edge\b",
        "TABLE blame_edge",
        """
CREATE TABLE mainline.blame_edge (
  event_id     UUID  NOT NULL REFERENCES mainline.event (event_id),
  clause_uuid  UUID  NOT NULL REFERENCES mainline.clause (clause_uuid),
  basis        mainline.blame_basis NOT NULL,
  state        mainline.blame_state NOT NULL DEFAULT 'provisional',
  site_id      UUID  NOT NULL,
  commit_id    BYTES NOT NULL REFERENCES mainline.commit_obj (commit_id),
  p_link       FLOAT8 NULL,
  features     JSONB  NOT NULL,
  attribution  STRING NULL,
  evidence_doc_id UUID NULL,
  evidence_span INT8[] NULL,
  evidence_quote_sha256 BYTES NULL,
  provisional_until TIMESTAMPTZ NULL,
  reviewed_by  STRING NULL,
  review_sig   BYTES NULL,
  reviewed_at  TIMESTAMPTZ NULL,
  model_id     STRING NULL,
  prompt_version STRING NULL,
  PRIMARY KEY (clause_uuid, event_id, basis),
  INDEX by_event (site_id, event_id) STORING (basis, state, p_link),
  CONSTRAINT asserted_needs_quote
    CHECK (basis <> 'asserted_document' OR evidence_quote_sha256 IS NOT NULL),
  CONSTRAINT human_needs_signature
    CHECK (basis <> 'asserted_human' OR review_sig IS NOT NULL),
  CONSTRAINT scored_needs_features
    CHECK (basis IN ('asserted_document', 'asserted_human') OR p_link IS NOT NULL),
  CONSTRAINT inference_never_blocks
    CHECK (basis <> 'inferred_semantic' OR state <> 'active')
)
""",
    ),
    (
        r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause_blame_closure\b",
        "TABLE clause_blame_closure",
        """
CREATE TABLE mainline.clause_blame_closure (
  clause_uuid     UUID   NOT NULL,
  as_of_commit    BYTES  NOT NULL,
  closure_gen     INT8   NOT NULL,
  site_id         UUID   NOT NULL,
  ancestor_events UUID[] NOT NULL,
  ancestor_count  INT4   NOT NULL,
  max_severity    INT2   NOT NULL,
  virulence       mainline.virulence_class NOT NULL,
  depth           INT4   NOT NULL,
  truncated       BOOL   NOT NULL DEFAULT false,
  computed_by     STRING NOT NULL,
  projector_ver   STRING NOT NULL,
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (clause_uuid, as_of_commit, closure_gen),
  CONSTRAINT fk_version FOREIGN KEY (clause_uuid, as_of_commit)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  CONSTRAINT closure_sev_range CHECK (max_severity BETWEEN 0 AND 5),
  CONSTRAINT closure_gen_positive CHECK (closure_gen >= 0)
)
""",
    ),
    (
        r"^CREATE\s+VIEW\s+mainline\.clause_blame_current\b",
        "VIEW clause_blame_current",
        """
CREATE VIEW mainline.clause_blame_current AS
SELECT DISTINCT ON (clause_uuid, as_of_commit)
       clause_uuid, as_of_commit, closure_gen, site_id, ancestor_events, ancestor_count,
       max_severity, virulence, depth, truncated, computed_by, projector_ver, computed_at
  FROM mainline.clause_blame_closure
 ORDER BY clause_uuid, as_of_commit, closure_gen DESC
""",
    ),
)

BLAME_STANDIN_SQL: Final[tuple[str, ...]] = tuple(ddl for _, _, ddl in STANDIN_OBJECTS)


def migration(name: str) -> Path:
    path = MIGRATIONS_DIR / name
    if not path.is_file():
        raise RuntimeError(
            f"{name} is missing from {MIGRATIONS_DIR}. The ORIGINDIFF migrations are "
            "0049b (mainline.commutation_edge) and 0152 (mainline.v_blame_origin); the "
            "0206/0212 numbers they were drafted under are revoked with the 0200-0219 annexe."
        )
    return path


def _texts() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in sorted(MIGRATIONS_DIR.glob("*.sql"))}


def spine_migrations() -> list[Path]:
    """Return the real migrations that create everything the view reads, in apply order.

    :raises RuntimeError: naming every spine object no file creates.  A skip would
        be worse here than for the stand-in objects: these are the spine, they are
        on disk, and a failure to find them means this module's content probes have
        drifted rather than that a band is late.
    """
    texts = _texts()
    ordered: list[Path] = []
    missing: list[str] = []
    for pattern, human in SPINE_OBJECTS:
        found = [path for path, text in texts.items() if re.search(pattern, text, re.M)]
        if not found:
            missing.append(human)
            continue
        for path in found:
            if path not in ordered:
                ordered.append(path)
    if missing:
        raise RuntimeError(
            f"no migration in {MIGRATIONS_DIR} creates: {', '.join(missing)}. "
            "The ORIGINDIFF SQL suite runs against the real spine wherever one exists."
        )
    return sorted(ordered, key=lambda p: p.name)


def stood_in_for() -> tuple[str, ...]:
    """Return the names of the blame objects no migration creates.

    Empty once ``datamodel/dm-blame`` lands, at which point this suite runs against
    the real tables with no change to this module.
    """
    texts = _texts()
    return tuple(
        human
        for pattern, human, _ in STANDIN_OBJECTS
        if not any(re.search(pattern, text, re.M) for text in texts.values())
    )


def origin_stack() -> tuple[list[Path], tuple[str, ...]]:
    """Return ``(migration paths, stand-in DDL)`` for a schema this suite can run against.

    :raises RuntimeError: if a stand-in would shadow an object a real migration
        creates.  Applying both would either fail with "relation already exists" or,
        worse, succeed against whichever ran first — and a suite that silently
        tests a hand-written twin of a real table asserts nothing about the real one.
    """
    texts = _texts()
    standins: list[str] = []
    shadowed: list[str] = []
    for pattern, human, ddl in STANDIN_OBJECTS:
        real = [path.name for path, text in texts.items() if re.search(pattern, text, re.M)]
        if real:
            shadowed.append(f"{human} (created by {', '.join(sorted(real))})")
            continue
        standins.append(ddl)
    if shadowed and len(shadowed) != len(STANDIN_OBJECTS):
        # Partial arrival: some of dm-blame has landed and some has not.  Refuse
        # rather than mixing, because the half that landed may not have the shape
        # the half that did not was written against.
        raise RuntimeError(
            "datamodel/dm-blame has landed PARTIALLY: "
            f"{'; '.join(shadowed)} exist while the rest do not. This suite will not mix a "
            "real table with a stand-in for its neighbour — the two were written against the "
            "same section of ARCHITECTURE.md but only one of them has been reviewed. Re-run "
            "once the band is complete."
        )
    stack = [*spine_migrations(), *(migration(name) for name in OWNED_MIGRATIONS)]
    return stack, tuple(standins)


# ── statement splitting ──────────────────────────────────────────────────────
#
# One statement at a time, because that is what the deployed migration runner does
# (§18) and a suite must not be more permissive than the thing it tests.
# Dollar-quote aware: nothing in these two files uses a `$$` body, but the spine
# files this suite applies alongside them do.

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def split_statements(sql: str) -> list[str]:
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
    stripped = re.sub(r"/\*.*?\*/", " ", fragment, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    return bool(stripped.strip())


def code_of(statement: str) -> str:
    """Return a statement with its leading ``--`` comment lines removed."""
    lines = [line for line in statement.splitlines() if not line.lstrip().startswith("--")]
    return "\n".join(lines).strip()


# ── EXPLAIN ──────────────────────────────────────────────────────────────────

_TABLE_LINE = re.compile(r"table:\s*(?P<table>[\w.]+)@(?P<index>[\w.]+)")
_SPANS_LINE = re.compile(r"spans:\s*(?P<spans>.+)")


@dataclass(frozen=True)
class PlanScan:
    """One ``table@index`` a plan reads, with the spans it reads over."""

    table: str
    index: str
    spans: str

    @property
    def full_scan(self) -> bool:
        return "FULL SCAN" in self.spans.upper()


def plan_scans(plan_text: str) -> tuple[PlanScan, ...]:
    """Parse ``EXPLAIN`` output into the set of ``table@index`` reads and their spans.

    Deliberately small and local.  ``packages/trappoint-recall`` has a richer plan
    parser; it belongs to the recall lead, it is Apache substrate, and the event-cue
    arms are its subject.  Twenty lines here beats coupling two domains' release
    cadences.

    A scan node whose ``spans:`` line is absent is reported with ``spans=''``, which
    is **not** a full scan — CockroachDB omits the line for a lookup join — and the
    caller decides what to make of it rather than this parser guessing.
    """
    scans: list[PlanScan] = []
    pending: tuple[str, str] | None = None
    for raw in plan_text.splitlines():
        line = raw.strip()
        table = _TABLE_LINE.search(line)
        if table is not None:
            if pending is not None:
                scans.append(PlanScan(table=pending[0], index=pending[1], spans=""))
            pending = (table.group("table"), table.group("index"))
            continue
        spans = _SPANS_LINE.search(line)
        if spans is not None and pending is not None:
            scans.append(PlanScan(table=pending[0], index=pending[1], spans=spans.group("spans")))
            pending = None
    if pending is not None:
        scans.append(PlanScan(table=pending[0], index=pending[1], spans=""))
    return tuple(scans)


# ── legal rows ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Commit:
    commit_id: bytes
    gen: int
    label: str


def commit_id(label: str) -> bytes:
    """Return a deterministic 32-byte id.  ``commit_obj.id_is_sha256`` wants exactly 32."""
    return hashlib.sha256(f"mainline-origindiff/{label}".encode()).digest()


def insert_commit(
    conn: Any,
    *,
    site_id: uuid.UUID,
    label: str,
    gen: int,
    ref_name: str = "site/marrindal/main",
) -> Commit:
    cid = commit_id(label)
    conn.execute(
        """
        INSERT INTO mainline.commit_obj
          (commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes, sig)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            cid,
            site_id,
            gen,
            ref_name,
            "sub-principal-engineer",
            f"origindiff test commit {label}",
            json.dumps({"label": label, "gen": gen}),
            label.encode("utf-8"),
            hashlib.sha256(f"sig/{label}".encode()).digest(),
        ),
    )
    return Commit(commit_id=cid, gen=gen, label=label)


def insert_commit_edge(conn: Any, *, child: Commit, parent: Commit, parent_ord: int) -> None:
    conn.execute(
        """
        INSERT INTO mainline.commit_edge (child_id, parent_ord, parent_id, parent_gen)
        VALUES (%s, %s, %s, %s)
        """,
        (child.commit_id, parent_ord, parent.commit_id, parent.gen),
    )


def insert_doc(conn: Any, *, site_id: uuid.UUID, doc_code: str = "PROC-ISOLATION-001") -> uuid.UUID:
    doc_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.doc (doc_id, site_id, doc_code, title) VALUES (%s, %s, %s, %s)",
        (doc_id, site_id, doc_code, "Isolation and permit-to-work procedure"),
    )
    return doc_id


def insert_clause(
    conn: Any,
    *,
    site_id: uuid.UUID,
    birth: Commit,
    activity_root: str = "ISOLATION-OF-STORED-ENERGY",
) -> uuid.UUID:
    clause_uuid = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO mainline.clause
          (clause_uuid, site_id, birth_commit, activity_root, head_commit)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (clause_uuid, site_id, birth.commit_id, activity_root, birth.commit_id),
    )
    return clause_uuid


def insert_clause_version(
    conn: Any,
    *,
    site_id: uuid.UUID,
    doc_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    commit: Commit,
    parent_version: bytes | None = None,
    control_delta: str = "restate",
    delta_basis: str = "lattice",
    sev_max: int = 0,
    canon_text: str = "The vessel shall be operated at or below 350 kPa.",
    activity_root: str = "ISOLATION-OF-STORED-ENERGY",
    ordinal: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.clause_version
          (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, parent_version,
           ordinal, raw_text, canon_text, canon_version, canon_sha256, anchor_set,
           cat_confidence, control_delta, delta_basis,
           blood_root, blood_peaks, blood_size, sev_max)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                'ok', %s, %s,
                %s, ARRAY[]::BYTES[], 0, %s)
        """,
        (
            clause_uuid,
            commit.gen,
            commit.commit_id,
            site_id,
            doc_id,
            activity_root,
            parent_version,
            ordinal,
            canon_text,
            canon_text,
            1,
            hashlib.sha256(f"{canon_text}/{commit.label}".encode()).digest(),
            [],
            control_delta,
            delta_basis,
            hashlib.sha256(b"mainline-origindiff/empty-mmr").digest(),
            sev_max,
        ),
    )


def insert_event(
    conn: Any,
    *,
    site_id: uuid.UUID,
    label: str,
    severity_gate: int,
    severity_basis: str = "regulator_class",
) -> uuid.UUID:
    event_id = uuid.uuid4()
    occurred = datetime(1998, 6, 14, tzinfo=UTC)
    conn.execute(
        """
        INSERT INTO mainline.event
          (event_id, site_id, external_ref, occurred_at, kind, title, narrative,
           source_object_key, source_sha256, severity_actual, severity_potential,
           severity_gate, severity_basis, canon_version)
        VALUES (%s, %s, %s, %s, 'incident', %s, %s, %s, %s, %s, %s, %s, %s, 1)
        """,
        (
            event_id,
            site_id,
            f"INC-{label}",
            occurred,
            f"origindiff fixture event {label}",
            "A fixture narrative long enough to be a narrative.",
            f"s3://fixture/{label}",
            hashlib.sha256(f"source/{label}".encode()).digest(),
            severity_gate,
            severity_gate,
            severity_gate,
            severity_basis,
        ),
    )
    return event_id


def insert_blame_edge(
    conn: Any,
    *,
    site_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    event_id: uuid.UUID,
    commit: Commit,
    basis: str = "asserted_document",
    state: str = "active",
) -> None:
    """Insert one blame edge, filling the columns each ``basis`` requires.

    ``scored_needs_features`` refuses a non-asserted basis with a NULL ``p_link``
    and ``human_needs_signature`` refuses ``asserted_human`` without a signature, so
    the fixture derives both from the basis rather than making every call site
    remember them.  A helper that produced an illegal row would fail the test for a
    reason that has nothing to do with the view under test.
    """
    asserted = basis in ("asserted_document", "asserted_human")
    conn.execute(
        """
        INSERT INTO mainline.blame_edge
          (event_id, clause_uuid, basis, state, site_id, commit_id, p_link, features,
           evidence_quote_sha256, reviewed_by, review_sig, reviewed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event_id,
            clause_uuid,
            basis,
            state,
            site_id,
            commit.commit_id,
            None if asserted else 0.91,
            json.dumps({"fixture": True}),
            hashlib.sha256(b"quote").digest(),
            "sub-reviewer" if basis == "asserted_human" else None,
            hashlib.sha256(b"review-sig").digest() if basis == "asserted_human" else None,
            datetime.now(tz=UTC) if basis == "asserted_human" else None,
        ),
    )


def insert_closure(
    conn: Any,
    *,
    site_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    as_of: Commit,
    max_severity: int,
    ancestor_events: Sequence[uuid.UUID] = (),
    closure_gen: int = 0,
    virulence: str = "blood_fatal",
    truncated: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.clause_blame_closure
          (clause_uuid, as_of_commit, closure_gen, site_id, ancestor_events, ancestor_count,
           max_severity, virulence, depth, truncated, computed_by, projector_ver)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            clause_uuid,
            as_of.commit_id,
            closure_gen,
            site_id,
            list(ancestor_events),
            len(ancestor_events),
            max_severity,
            virulence,
            1,
            truncated,
            "origindiff-fixture",
            "fixture-1",
        ),
    )


def rows(conn: Any, sql: str, params: Iterable[Any] = ()) -> Sequence[tuple[Any, ...]]:
    return conn.execute(sql, tuple(params)).fetchall()
