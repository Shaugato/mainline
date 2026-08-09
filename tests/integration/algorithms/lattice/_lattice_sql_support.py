# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Support code for the DELTALATTICE SQL suite.  Asserts nothing itself.

The module name is deliberately not ``_support``.  pytest's prepend import mode
puts every collected test directory on ``sys.path``, so two modules sharing a
name resolve to whichever collection reached first — a silent failure that
produces a suite exercising somebody else's helpers.
``tests/integration/recall_schema/_support.py`` and
``tests/integration/algorithms/candidates/_support.py`` both already exist, and
``_directrix_support`` and ``_lattice_fixtures`` are the same defence in the two
neighbouring suites.

THE THREE MIGRATIONS THIS SUITE OWNS
------------------------------------
=========================================  ============================================
``0049a_delta_witness.sql``                the table.  Algorithms table annexe.
``0140_fn_delta_witness_guard.sql``        the function.  Vertical function band.
``0145_trg_delta_witness_guard.sql``       the trigger.  Vertical trigger band.
=========================================  ============================================

They were authored as ``0205`` and ``0211`` under the ``0200-0219`` annexe that
``docs/leads/algorithms.md`` D9/§9 reserved.  That annexe is **revoked**:
``ARCHITECTURE.md`` §18 never defined a ``0200+`` space, ``0200`` and above is
``UNALLOCATED`` in ``verticals/mainline/db/migrations.allocation.toml``, and
``trappoint migrate lint`` rule B refuses any file that claims it.  This module
resolves the three files **by name against the allocation**, and
:func:`spine_migrations` resolves everything else **by content**, so a renumber
inside the schema lead's bands does not silently reduce this suite to a skip.

WHY THE SPINE IS NOT STUBBED
----------------------------
The neighbouring DIRECTRIX suite ships a stand-in spine because the schema lead's
migrations had not landed when it was written.  They have landed.  A stand-in
here would be strictly worse than nothing: the whole claim of this suite is that
a **real** ``mainline.clause_version`` insert is refused by a **real** trigger, and
a hand-written table that happens to have the same column names proves that the
test file is self-consistent and nothing else.  If a spine object cannot be
found, :func:`spine_migrations` raises and names what is missing.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

HERE = Path(__file__).resolve().parent

__all__ = [
    "MIGRATIONS_DIR",
    "NO_MINIMAL_WITNESS_MESSAGE",
    "OWNED_MIGRATIONS",
    "SPINE_OBJECTS",
    "WITNESSLESS_WEAKEN_MESSAGE",
    "Commit",
    "code_of",
    "commit_id",
    "guarded_stack",
    "insert_clause",
    "insert_clause_version",
    "insert_commit",
    "insert_doc",
    "insert_witness",
    "migration",
    "repo_root",
    "rows",
    "spine_migrations",
    "split_statements",
    "unguarded_stack",
]


def repo_root() -> Path:
    for parent in [HERE, *HERE.parents]:
        if (parent / "verticals" / "mainline" / "db" / "migrations").is_dir():
            return parent
    raise RuntimeError(f"cannot locate verticals/mainline/db/migrations above {HERE}")


MIGRATIONS_DIR: Final[Path] = repo_root() / "verticals" / "mainline" / "db" / "migrations"

#: The three files this worker owns, in apply order.  Named literally, because
#: their numbers are *granted* by ``migrations.allocation.toml`` — resolving them
#: by content would make a file that quietly drifted out of its band invisible
#: here, and the band is half of what the shape tests check.
OWNED_MIGRATIONS: Final[tuple[str, str, str]] = (
    "0049a_delta_witness.sql",
    "0140_fn_delta_witness_guard.sql",
    "0145_trg_delta_witness_guard.sql",
)

#: Everything ``mainline.delta_witness`` and ``mainline.clause_version`` need,
#: as ``(regex, human name)``.  Matched against file *content*: the numbering
#: inside the schema lead's bands is that lead's to choose, and this suite must
#: not encode a guess about it.
SPINE_OBJECTS: Final[tuple[tuple[str, str], ...]] = (
    (r"CREATE\s+SCHEMA\s+(IF\s+NOT\s+EXISTS\s+)?mainline\b", "SCHEMA mainline"),
    (r"CREATE\s+TYPE\s+mainline\.control_delta\b", "TYPE mainline.control_delta"),
    (
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.commit_obj\b",
        "TABLE mainline.commit_obj",
    ),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.doc\b", "TABLE mainline.doc"),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause\b", "TABLE mainline.clause"),
    (
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause_version\b",
        "TABLE mainline.clause_version",
    ),
)

#: The two refusals, pinned as literals.  They are pinned in **three** places on
#: purpose: here, in the SQL, and in the ``psycopg`` error a live cluster raises.
#: A test that read the string out of the migration and compared it to itself
#: would pass for any string at all, including an empty one.
WITNESSLESS_WEAKEN_MESSAGE: Final[str] = (
    "MAINLINE: a lattice weakening must carry its minimal witness set"
)
NO_MINIMAL_WITNESS_MESSAGE: Final[str] = (
    "MAINLINE: a lattice weakening carries witnesses but none is minimal — "
    "I14 asks for an irreducible reason set, not a repair list"
)


def migration(name: str) -> Path:
    path = MIGRATIONS_DIR / name
    if not path.is_file():
        raise RuntimeError(
            f"{name} is missing from {MIGRATIONS_DIR}. The DELTALATTICE migrations are "
            "0049a (table), 0140 (function) and 0145 (trigger); the 0205/0211 numbers "
            "they were authored under are revoked with the 0200-0219 annexe."
        )
    return path


def spine_migrations() -> list[Path]:
    """The real migrations that create everything the guard reads, in apply order.

    Sorted lexicographically on the whole filename stem, which is the order the
    deployed runner uses (MR-5: ``0006a < 0006b < 0007`` and ``0119a < 0120``).

    :raises RuntimeError: naming every spine object no file creates.  A skip
        would be worse: this suite exists to execute a real trigger against a
        real table, and quietly substituting a hand-written stand-in would turn a
        broken spine into a green run.
    """
    texts = {
        path: path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
    }
    ordered: list[Path] = []
    missing: list[str] = []
    for pattern, human in SPINE_OBJECTS:
        found = [path for path, text in texts.items() if re.search(pattern, text)]
        if not found:
            missing.append(human)
            continue
        for path in found:
            if path not in ordered:
                ordered.append(path)
    if missing:
        raise RuntimeError(
            "no migration in "
            f"{MIGRATIONS_DIR} creates: {', '.join(missing)}. "
            "The DELTALATTICE SQL suite runs against the real spine and never against a "
            "stand-in — a hand-written twin of clause_version would prove that this test "
            "file is self-consistent and nothing else."
        )
    return sorted(ordered, key=lambda p: p.name)


def guarded_stack() -> list[Path]:
    """Spine + table + function + trigger.  The deployment as it is meant to be."""
    return [*spine_migrations(), *(migration(name) for name in OWNED_MIGRATIONS)]


def unguarded_stack() -> list[Path]:
    """The same stack with **0145 removed** — the function exists, nothing calls it.

    This is the red half of PL-2, kept permanently rather than performed once.
    ``test_witness_or_refuse`` runs the identical INSERT against both schemas: the
    unguarded one accepts it, the guarded one raises ``P0001``.  Without that
    pair, "the insert was refused" is compatible with the row being refused by a
    ``NOT NULL``, by a foreign key, or by a typo in the test's own SQL.
    """
    return [path for path in guarded_stack() if path.name != OWNED_MIGRATIONS[2]]


# ── statement splitting ──────────────────────────────────────────────────────
#
# One statement at a time, because that is what the deployed migration runner
# does (§18) and a suite must not be more permissive than the thing it tests.
# Dollar-quote aware, which is load-bearing here and not merely careful: 0140's
# body is a `$$ ... $$` PL/pgSQL block containing semicolons, and a naive split
# would hand the cluster four fragments of a function.

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
    """A statement with its leading ``--`` comment lines removed.

    The splitter keeps comments attached to the statement that follows them, so a
    file whose header is longer than its SQL — which all three of these are,
    deliberately — has one statement beginning with a hundred lines of prose.
    """
    lines = [line for line in statement.splitlines() if not line.lstrip().startswith("--")]
    return "\n".join(lines).strip()


# ── legal rows ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Commit:
    commit_id: bytes
    gen: int


def commit_id(label: str) -> bytes:
    """A deterministic 32-byte id.  ``commit_obj.id_is_sha256`` wants exactly 32."""
    return hashlib.sha256(f"mainline-deltalattice/{label}".encode()).digest()


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
            f"deltalattice test commit {label}",
            json.dumps({"label": label, "gen": gen}),
            label.encode("utf-8"),
            hashlib.sha256(f"sig/{label}".encode()).digest(),
        ),
    )
    return Commit(commit_id=cid, gen=gen)


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
    cur: Any,
    *,
    site_id: uuid.UUID,
    doc_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    commit: Commit,
    control_delta: str,
    delta_basis: str,
    parent_version: bytes | None = None,
    delta_model: str | None = None,
    canon_text: str = "The isolation shall be verified by a second person before work begins.",
    activity_root: str = "ISOLATION-OF-STORED-ENERGY",
    ordinal: int = 0,
) -> None:
    """One ``mainline.clause_version`` row — the INSERT the guard fires on.

    Takes a *cursor or connection* rather than only a connection, because the
    ordering contract this suite exists to prove is a two-statement transaction
    and the caller has to hold it open across both.
    """
    cur.execute(
        """
        INSERT INTO mainline.clause_version
          (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, parent_version,
           ordinal, raw_text, canon_text, canon_version, canon_sha256, anchor_set,
           cat_confidence, control_delta, delta_basis, delta_model,
           blood_root, blood_peaks, blood_size, sev_max)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                'ok', %s, %s, %s,
                %s, ARRAY[]::BYTES[], 0, 0)
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
            hashlib.sha256(canon_text.encode("utf-8")).digest(),
            [],
            control_delta,
            delta_basis,
            delta_model,
            hashlib.sha256(b"mainline-deltalattice/empty-mmr").digest(),
        ),
    )


def insert_witness(
    cur: Any,
    *,
    clause_uuid: uuid.UUID,
    commit: Commit,
    witness_ord: int,
    rule_id: str,
    field: str,
    from_repr: str,
    to_repr: str,
    note: str,
    minimal: bool = True,
) -> None:
    cur.execute(
        """
        INSERT INTO mainline.delta_witness
          (clause_uuid, commit_id, witness_ord, rule_id, field, from_repr, to_repr, note, minimal)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            clause_uuid,
            commit.commit_id,
            witness_ord,
            rule_id,
            field,
            from_repr,
            to_repr,
            note,
            minimal,
        ),
    )


def rows(conn: Any, sql: str, params: Iterable[Any] = ()) -> Sequence[tuple[Any, ...]]:
    return conn.execute(sql, tuple(params)).fetchall()
