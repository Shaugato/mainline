# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Support code for the DIRECTRIX integration suite.  Asserts nothing itself.

The module name is deliberately not ``_support``: worker W1 of the recall domain
already ships ``tests/integration/recall_schema/_support.py``, and pytest's
prepend import mode puts both directories on ``sys.path``, so two modules named
``_support`` would resolve to whichever collection reached first.  That failure
is silent and produces a suite testing somebody else's helpers.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PREREQ_DIR = HERE / "prereq"


def repo_root() -> Path:
    for parent in [HERE, *HERE.parents]:
        candidate = parent / "verticals" / "mainline" / "db" / "migrations"
        if candidate.is_dir():
            return parent
    raise RuntimeError(f"cannot locate verticals/mainline/db/migrations above {HERE}")


MIGRATIONS_DIR = repo_root() / "verticals" / "mainline" / "db" / "migrations"

#: Worker W2 owns exactly one migration.  Band 0200-0219 belongs to the
#: algorithms domain; 0207 is this worker's and nothing else in the band is.
OWNED_MIGRATION = 207

#: Objects the view reads.  If the schema lead's migrations that create these
#: have landed, the suite applies those instead of the stand-in.
SPINE_TABLES = ("commit_obj", "commit_edge", "doc", "clause", "clause_version")


def owned_migration_file() -> Path:
    matches = sorted(MIGRATIONS_DIR.glob(f"{OWNED_MIGRATION:04d}_*.sql"))
    if not matches:
        raise RuntimeError(f"migration {OWNED_MIGRATION:04d} is missing from {MIGRATIONS_DIR}")
    if len(matches) > 1:
        raise RuntimeError(
            f"two files claim migration {OWNED_MIGRATION:04d}: "
            + ", ".join(p.name for p in matches)
        )
    return matches[0]


def spine_migrations() -> list[Path]:
    """Real migrations that create the spine tables, if any have landed yet.

    Matched by content rather than by number, because the numbering inside the
    schema lead's band is that lead's to choose and this suite must not encode a
    guess about it.  An empty list means the stand-in is needed, and the suite
    says so in its header.
    """
    found: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        head = path.name.split("_", 1)[0]
        if not head.isdigit():
            continue
        number = int(head)
        if number >= 200:  # the algorithms band; never a spine table
            continue
        text = path.read_text(encoding="utf-8")
        if any(
            re.search(rf"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.{table}\b", text)
            for table in SPINE_TABLES
        ):
            found.append((number, path))
    return [path for _, path in sorted(found)]


# ── statement splitting ──────────────────────────────────────────────────────
#
# One statement at a time, because that is what the deployed migration runner
# does (§18) and a suite must not be more permissive than the thing it tests.
# Dollar-quote aware so a `$$` body is never cut in half.

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


# ── legal rows ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Commit:
    commit_id: bytes
    gen: int
    author_sub: str
    signed: bool


def commit_id(label: str) -> bytes:
    return hashlib.sha256(f"mainline-directrix/{label}".encode()).digest()


def insert_commit(
    conn: Any,
    *,
    site_id: uuid.UUID,
    label: str,
    gen: int,
    parents: Iterable[bytes] = (),
    author_sub: str = "sub-principal-engineer",
    signed: bool = True,
    ref_name: str = "site/marrindal/main",
) -> Commit:
    cid = commit_id(label)
    conn.execute(
        """
        INSERT INTO mainline.commit_obj
          (commit_id, site_id, gen, ref_name, author_sub, message, envelope,
           envelope_bytes, sig)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            cid,
            site_id,
            gen,
            ref_name,
            author_sub,
            f"directrix test commit {label}",
            json.dumps({"label": label}),
            label.encode("utf-8"),
            hashlib.sha256(f"sig/{label}".encode()).digest() if signed else None,
        ),
    )
    for ordinal, parent in enumerate(parents):
        conn.execute(
            """
            INSERT INTO mainline.commit_edge (child_id, parent_ord, parent_id, parent_gen)
            VALUES (%s, %s, %s, %s)
            """,
            (cid, ordinal, parent, gen - 1),
        )
    return Commit(commit_id=cid, gen=gen, author_sub=author_sub, signed=signed)


def insert_registry_doc(conn: Any, *, site_id: uuid.UUID, doc_code: str) -> uuid.UUID:
    doc_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO mainline.doc (doc_id, site_id, doc_code, title)
        VALUES (%s, %s, %s, %s)
        """,
        (doc_id, site_id, doc_code, "Safe-direction registry (DIRECTRIX)"),
    )
    return doc_id


def insert_clause_version(
    conn: Any,
    *,
    site_id: uuid.UUID,
    doc_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    commit: Commit,
    canon_text: str,
    canon_sha256: bytes,
    ordinal: int,
    is_head: bool = True,
    retired_commit: bytes | None = None,
    activity_root: str = "GOVERNANCE-OF-CONTROL-PARAMETERS",
) -> None:
    """Insert the clause (once) and one of its versions, wiring ``head_commit``.

    ``ON CONFLICT DO NOTHING`` on the clause row so a second version of the same
    clause does not need the caller to remember whether it exists yet.
    """
    conn.execute(
        """
        INSERT INTO mainline.clause
          (clause_uuid, site_id, birth_commit, activity_root, head_commit, retired_commit)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (clause_uuid) DO NOTHING
        """,
        (clause_uuid, site_id, commit.commit_id, activity_root, commit.commit_id, retired_commit),
    )
    conn.execute(
        """
        INSERT INTO mainline.clause_version
          (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, ordinal,
           raw_text, canon_text, canon_version, canon_sha256, anchor_set,
           cat_confidence, control_delta, delta_basis,
           blood_root, blood_peaks, blood_size, sev_max)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'ok', 'introduce', 'lattice', %s, ARRAY[]::BYTES[], 0, 0)
        """,
        (
            clause_uuid,
            commit.gen,
            commit.commit_id,
            site_id,
            doc_id,
            activity_root,
            ordinal,
            canon_text,
            canon_text,
            1,
            canon_sha256,
            [],
            hashlib.sha256(b"empty-mmr").digest(),
        ),
    )
    if is_head:
        conn.execute(
            "UPDATE mainline.clause SET head_commit = %s WHERE clause_uuid = %s",
            (commit.commit_id, clause_uuid),
        )
    if retired_commit is not None:
        conn.execute(
            "UPDATE mainline.clause SET retired_commit = %s WHERE clause_uuid = %s",
            (retired_commit, clause_uuid),
        )


def rows(conn: Any, sql: str, params: Iterable[Any] = ()) -> list[tuple[Any, ...]]:
    return conn.execute(sql, tuple(params)).fetchall()
