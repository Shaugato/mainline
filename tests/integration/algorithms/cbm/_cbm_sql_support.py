# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Support code for the CONSERVATION OF BLAME MASS SQL suite.  Asserts nothing itself.

The module name is deliberately not ``_support``.  pytest's prepend import mode
puts every collected test directory on ``sys.path``, so two modules sharing a
name resolve to whichever collection reached first — a silent failure that
produces a suite exercising somebody else's helpers.  ``_lattice_sql_support``
and ``_directrix_support`` are the same defence in the neighbouring suites.

THE ELEVEN MIGRATIONS THIS SUITE OWNS
-------------------------------------
==========================================  ==========================================
``0049c_cbm_account.sql``                   the table, ``balanced``, ``cbm_balances``
``0140a_fn_cbm_account_guard.sql``          re-derives the six counters
``0140b_fn_residue_project.sql``            projects ``max_ancestral_severity``
``0140c_fn_cbm_gate_permit.sql``            the merge refusals, permit side
``0140d_fn_cbm_gate_cr.sql``                the merge refusals, change-request side
``0145a_trg_cbm_account_guard.sql``         attaches the guard
``0145b_trg_residue_project.sql``           attaches the projector
``0145c_trg_cbm_gate_permit.sql``           attaches ``z_cbm_gate``
``0145d_trg_cbm_gate_cr.sql``               attaches ``z_cbm_gate_cr``
``0145e_trg_cbm_account_append_only.sql``   refuses UPDATE and DELETE on the account
``0151_v_cbm_ledger.sql``                   ``mainline_audit.v_cbm_ledger``
==========================================  ==========================================

They were briefed as ``0201``-``0210`` under the ``0200-0219`` annexe that
``docs/leads/algorithms.md`` D9/section 9 reserved.  That annexe is **revoked**:
``ARCHITECTURE.md`` section 18 never defined a ``0200+`` space, ``0200`` and above
is ``UNALLOCATED`` in ``verticals/mainline/db/migrations.allocation.toml``, and
``trappoint migrate lint`` rule B refuses any file that claims it.  The
replacement numbers come from this domain's own grants — the ``0049a``-``0049z``
table annexe, the ``0150``-``0154`` view band, and MR-5 band overflow of this
domain's own ``0140`` and ``0145``.

WHY THE SPINE IS REAL AND THREE OBJECTS ARE NOT (YET)
-----------------------------------------------------
Everything the CBM derivation reads is resolved against the REAL migration tree
by content.  Three objects had no migration in the tree when this suite was
written — ``clause_blame_closure``, ``clause_blame_current`` and
``identity_assignment``, owned by ``datamodel/dm-blame`` and by worker W8 — and
for those, and only those, ``_pending_dependency.sql`` supplies a transcribed
stand-in.  :func:`stood_in_objects` names them, every fixture prints them, and
``test_cbm_pending_dependency.py`` fails the moment a real migration lands and this
file still shadows it.  Nothing else is stubbed: a hand-written twin of
``clause_version`` would prove that this test file is self-consistent and
nothing else.
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
    "ABSENT_ACCOUNT_MESSAGE",
    "BALANCES_CONSTRAINT",
    "CLOSURE_ABSENT_MESSAGE",
    "GENERATION_MESSAGE",
    "MIGRATIONS_DIR",
    "NO_FIRST_PARENT_MESSAGE",
    "OWNED_MIGRATIONS",
    "PENDING_DDL",
    "PENDING_OBJECTS",
    "RESIDUE_CLOSURE_MESSAGE",
    "SCENE_DISPOSITIONS",
    "SPINE_OBJECTS",
    "STALE_ACCOUNT_MESSAGE",
    "UNKNOWN_COMMIT_MESSAGE",
    "Commit",
    "CommitScene",
    "build_scene",
    "code_of",
    "commit_id_for",
    "full_stack",
    "insert_assignment",
    "insert_clause",
    "insert_clause_version",
    "insert_closure",
    "insert_commit",
    "insert_cr",
    "insert_cr_clause",
    "insert_doc",
    "insert_permit",
    "insert_permit_clause",
    "insert_residue",
    "migration",
    "repo_root",
    "rows",
    "spine_files",
    "split_statements",
    "stack_without",
    "stood_in_objects",
]


def repo_root() -> Path:
    for parent in [HERE, *HERE.parents]:
        if (parent / "verticals" / "mainline" / "db" / "migrations").is_dir():
            return parent
    raise RuntimeError(f"cannot locate verticals/mainline/db/migrations above {HERE}")


MIGRATIONS_DIR: Final[Path] = repo_root() / "verticals" / "mainline" / "db" / "migrations"

#: This worker's files, in apply order.  Named literally, because their numbers
#: are *granted* by ``migrations.allocation.toml``: resolving them by content
#: would make a file that quietly drifted out of its band invisible here, and the
#: band is half of what ``test_cbm_migration_shape.py`` checks.
OWNED_MIGRATIONS: Final[tuple[str, ...]] = (
    "0049c_cbm_account.sql",
    "0140a_fn_cbm_account_guard.sql",
    "0140b_fn_residue_project.sql",
    "0140c_fn_cbm_gate_permit.sql",
    "0140d_fn_cbm_gate_cr.sql",
    "0145a_trg_cbm_account_guard.sql",
    "0145b_trg_residue_project.sql",
    "0145c_trg_cbm_gate_permit.sql",
    "0145d_trg_cbm_gate_cr.sql",
    "0145e_trg_cbm_account_append_only.sql",
    "0151_v_cbm_ledger.sql",
)

#: Everything the eleven statements above read, as ``(regex, human name)``.
#: Matched against file CONTENT: the numbering inside another lead's bands is
#: that lead's to choose and this suite must not encode a guess about it.
SPINE_OBJECTS: Final[tuple[tuple[str, str], ...]] = (
    (r"CREATE\s+SCHEMA\s+(IF\s+NOT\s+EXISTS\s+)?mainline\s*;", "SCHEMA mainline"),
    (r"CREATE\s+SCHEMA\s+(IF\s+NOT\s+EXISTS\s+)?mainline_audit\b", "SCHEMA mainline_audit"),
    (r"CREATE\s+TYPE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.control_delta\b", "TYPE control_delta"),
    (r"CREATE\s+TYPE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.subject_state\b", "TYPE subject_state"),
    (
        r"CREATE\s+TYPE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.virulence_class\b",
        "TYPE virulence_class",
    ),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.commit_obj\b", "TABLE commit_obj"),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.commit_edge\b", "TABLE commit_edge"),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.doc\b", "TABLE doc"),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause\b", "TABLE clause"),
    (
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause_version\b",
        "TABLE clause_version",
    ),
    (
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.identity_residue\b",
        "TABLE identity_residue",
    ),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.permit\b", "TABLE permit"),
    (
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.change_request\b",
        "TABLE change_request",
    ),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.permit_clause\b", "TABLE permit_clause"),
    (r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.cr_clause\b", "TABLE cr_clause"),
    # 0145e attaches the KERNEL's append-only function to this domain's table rather than
    # writing a second, near-identical one, so the substrate function must be in the stack.
    (r"CREATE\s+FUNCTION\s+mainline\.fn_refuse_mutation\b", "FUNCTION fn_refuse_mutation"),
)

#: The three objects that may legitimately not exist yet, with the stand-in that
#: covers each.  Order matters: the table before the view over it.
PENDING_OBJECTS: Final[tuple[tuple[str, str], ...]] = (
    (
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.clause_blame_closure\b",
        "TABLE clause_blame_closure",
    ),
    (r"CREATE\s+VIEW\s+mainline\.clause_blame_current\b", "VIEW clause_blame_current"),
    (
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?mainline\.identity_assignment\b",
        "TABLE identity_assignment",
    ),
)

PENDING_DDL: Final[Path] = HERE / "_pending_dependency.sql"

# ── the refusals, pinned as literals ─────────────────────────────────────────
#
# Pinned in THREE places on purpose: here, in the SQL, and in the psycopg error a
# live cluster raises.  A test that read the string out of the migration and
# compared it with itself would pass for any string at all, including an empty
# one.

UNKNOWN_COMMIT_MESSAGE: Final[str] = (
    "MAINLINE: cbm account refused — the commit it accounts for does not exist"
)
CLOSURE_ABSENT_MESSAGE: Final[str] = (
    "MAINLINE: cbm account refused — blame closure not materialised for the first-parent commit"
)
GENERATION_MESSAGE: Final[str] = "MAINLINE: cbm account generations must be dense and monotone"
NO_FIRST_PARENT_MESSAGE: Final[str] = (
    "MAINLINE: residue refused — the commit has no first parent, so no ancestor can be missing"
)
RESIDUE_CLOSURE_MESSAGE: Final[str] = (
    "MAINLINE: residue refused — no blame closure for the ancestor clause in the "
    "first-parent commit"
)
ABSENT_ACCOUNT_MESSAGE: Final[str] = (
    "MAINLINE: merge refused — blame accounting absent for a cited commit"
)
STALE_ACCOUNT_MESSAGE: Final[str] = (
    "MAINLINE: merge refused — blame accounting is stale for a cited commit"
)

#: v26.2.5 puts the CHECK EXPRESSION in the 23514 message and the constraint NAME
#: in the error's diagnostics.  Tests read the name from ``exc.diag.constraint_name``.
BALANCES_CONSTRAINT: Final[str] = "cbm_balances"


def migration(name: str) -> Path:
    path = MIGRATIONS_DIR / name
    if not path.is_file():
        raise RuntimeError(
            f"{name} is missing from {MIGRATIONS_DIR}. The CBM migrations take their numbers "
            "from the algorithms table annexe (0049a-0049z), the vertical function/trigger "
            "bands by MR-5 band overflow of 0140/0145, and the 0150-0154 view band; the "
            "0201-0210 numbers the brief used are revoked with the 0200-0219 annexe."
        )
    return path


def _resolve(
    objects: Iterable[tuple[str, str]], texts: dict[Path, str]
) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    missing: list[str] = []
    for pattern, human in objects:
        hits = [path for path, text in texts.items() if re.search(pattern, text)]
        if not hits:
            missing.append(human)
            continue
        for path in hits:
            if path not in found:
                found.append(path)
    return found, missing


def _texts() -> dict[Path, str]:
    owned = set(OWNED_MIGRATIONS)
    return {
        path: path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
        if path.name not in owned
    }


def spine_files() -> list[Path]:
    """Every real migration the nine owned statements need, in apply order.

    Sorted lexicographically on the whole filename stem, which is the order the
    deployed runner uses (MR-5: ``0006a < 0006b < 0007`` and ``0119a < 0120``).

    :raises RuntimeError: naming every spine object no file creates.  A skip
        would be worse: this suite exists to execute real triggers against real
        tables.
    """
    texts = _texts()
    required, missing = _resolve(SPINE_OBJECTS, texts)
    if missing:
        raise RuntimeError(
            f"no migration in {MIGRATIONS_DIR} creates: {', '.join(missing)}. The CBM SQL "
            "suite runs against the real spine and never against a stand-in for it."
        )
    pending, _ = _resolve(PENDING_OBJECTS, texts)
    for path in pending:
        if path not in required:
            required.append(path)
    return sorted(required, key=lambda p: p.name)


def stood_in_objects() -> list[str]:
    """The pending objects for which ``_pending_dependency.sql`` is in play.

    Empty once ``dm-blame`` and W8 have landed.  Never empty silently: the
    fixtures print this list on every run.
    """
    _, missing = _resolve(PENDING_OBJECTS, _texts())
    return missing


def full_stack() -> list[Path]:
    """Spine (+ stand-in when needed) + the nine owned files, in apply order."""
    stack = spine_files()
    if stood_in_objects():
        stack.append(PENDING_DDL)
    stack.extend(migration(name) for name in OWNED_MIGRATIONS)
    return stack


def stack_without(*names: str) -> list[Path]:
    """:func:`full_stack` with the named owned migrations withheld.

    This is the permanent red half of PL-2.  ``test_balance_refusal`` runs the
    identical INSERT against a schema built WITHOUT ``0145a`` — where the guard
    function exists and nothing calls it — and the client's fabricated counters
    survive.  Without that pair, "the account was corrected" is equally
    consistent with the test having computed the right numbers by accident.
    """
    withheld = set(names)
    unknown = withheld - set(OWNED_MIGRATIONS)
    if unknown:
        raise RuntimeError(f"not files this worker owns: {sorted(unknown)}")
    return [p for p in full_stack() if p.name not in withheld]


# ── statement splitting ──────────────────────────────────────────────────────
#
# One statement at a time, because that is what the deployed migration runner
# does (ARCHITECTURE.md section 18) and a suite must not be more permissive than
# the thing it tests.  Dollar-quote aware, which is load-bearing and not merely
# careful: four of the owned files are ``$$ ... $$`` PL/pgSQL bodies full of
# semicolons, and a naive split would hand the cluster fragments of a function.

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
    file whose header is longer than its SQL — which all eleven of these are,
    deliberately — has one statement beginning with a hundred lines of prose.
    """
    lines = [line for line in statement.splitlines() if not line.lstrip().startswith("--")]
    return "\n".join(lines).strip()


# ── legal rows ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Commit:
    commit_id: bytes
    gen: int


def commit_id_for(label: str) -> bytes:
    """A deterministic 32-byte id.  ``commit_obj.id_is_sha256`` wants exactly 32."""
    return hashlib.sha256(f"mainline-cbm/{label}".encode()).digest()


def insert_commit(
    conn: Any,
    *,
    site_id: uuid.UUID,
    label: str,
    gen: int,
    parent: Commit | None = None,
    ref_name: str = "site/marrindal/main",
) -> Commit:
    cid = commit_id_for(label)
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
            f"cbm test commit {label}",
            json.dumps({"label": label, "gen": gen}),
            label.encode("utf-8"),
            hashlib.sha256(f"sig/{label}".encode()).digest(),
        ),
    )
    if parent is not None:
        conn.execute(
            """
            INSERT INTO mainline.commit_edge (child_id, parent_ord, parent_id, parent_gen)
            VALUES (%s, 0, %s, %s)
            """,
            (cid, parent.commit_id, parent.gen),
        )
    return Commit(commit_id=cid, gen=gen)


def insert_doc(conn: Any, *, site_id: uuid.UUID, doc_code: str) -> uuid.UUID:
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
    ordinal: int = 0,
    canon_text: str = "The isolation shall be verified by a second person before work begins.",
    activity_root: str = "ISOLATION-OF-STORED-ENERGY",
) -> None:
    """One ``mainline.clause_version`` row.

    ``control_delta='restate'`` / ``delta_basis='human'`` throughout, and that is
    not laziness: were this suite to declare a lattice ``weaken`` it would be
    exercising worker W4's ``z_delta_witness_required`` guard, which is a
    different refusal in a different file.  A test that trips two gates cannot
    say which one refused it.
    """
    conn.execute(
        """
        INSERT INTO mainline.clause_version
          (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, parent_version,
           ordinal, raw_text, canon_text, canon_version, canon_sha256, anchor_set,
           cat_confidence, control_delta, delta_basis, delta_model,
           blood_root, blood_peaks, blood_size, sev_max)
        VALUES (%s, %s, %s, %s, %s, %s, NULL,
                %s, %s, %s, 1, %s, ARRAY[]::STRING[],
                'ok', 'restate', 'human', NULL,
                %s, ARRAY[]::BYTES[], 0, 0)
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
            hashlib.sha256(canon_text.encode("utf-8")).digest(),
            hashlib.sha256(b"mainline-cbm/empty-mmr").digest(),
        ),
    )


#: The banding ARCHITECTURE.md section 5.4 puts on the closure, reproduced only so the
#: fixture can satisfy `virulence NOT NULL`.  Nothing in the CBM derivation reads it: the
#: law quantifies over `max_severity >= 4`, and a second, softer copy of that threshold in
#: a banding table is exactly the kind of drift the differential test cannot see.
_VIRULENCE = {
    0: "routine",
    1: "routine",
    2: "routine",
    3: "serious",
    4: "blood_major",
    5: "blood_fatal",
}


def insert_closure(
    conn: Any,
    *,
    site_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    as_of: Commit,
    max_severity: int,
    closure_gen: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.clause_blame_closure
          (clause_uuid, as_of_commit, closure_gen, site_id, ancestor_events, ancestor_count,
           max_severity, virulence, depth, truncated, computed_by, projector_ver)
        VALUES (%s, %s, %s, %s, ARRAY[]::UUID[], 0, %s, %s, 0, false, %s, %s)
        """,
        (
            clause_uuid,
            as_of.commit_id,
            closure_gen,
            site_id,
            max_severity,
            _VIRULENCE[max_severity],
            "agent_projector",
            "cbm-test-fixture",
        ),
    )


def insert_assignment(
    conn: Any,
    *,
    site_id: uuid.UUID,
    commit: Commit,
    ancestor: uuid.UUID,
    relation: str,
    descendant: uuid.UUID | None = None,
    stage: str = "S1",
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.identity_assignment
          (site_id, commit_id, ancestor_clause_uuid, descendant_clause_uuid, relation,
           stage, score, margin, policy_sha256, computed_by)
        VALUES (%s, %s, %s, %s, %s, %s, 1.0, 1.0, %s, %s)
        """,
        (
            site_id,
            commit.commit_id,
            ancestor,
            descendant,
            relation,
            stage,
            hashlib.sha256(b"identity-policy-v1").digest(),
            "agent_cartographer",
        ),
    )


def insert_residue(
    conn: Any,
    *,
    site_id: uuid.UUID,
    commit: Commit,
    ancestor: uuid.UUID,
    reason: str = "unmatched",
    disposition_id: uuid.UUID | None = None,
    max_ancestral_severity: int = 0,
) -> uuid.UUID:
    """One ``identity_residue`` row.

    ``max_ancestral_severity`` defaults to ``0`` on purpose: once ``0145b`` is
    applied the column is overwritten from the closure, so a fixture that
    supplied the right answer would hide a projector that had stopped working.
    """
    residue_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO mainline.identity_residue
          (residue_id, site_id, commit_id, ancestor_clause_uuid, reason,
           max_ancestral_severity, match_score, features, disposition_id)
        VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s)
        """,
        (
            residue_id,
            site_id,
            commit.commit_id,
            ancestor,
            reason,
            max_ancestral_severity,
            json.dumps({"stage": "S4", "shingle_overlap": 0.0}),
            disposition_id,
        ),
    )
    return residue_id


def insert_permit(conn: Any, *, site_id: uuid.UUID, external_ref: str) -> uuid.UUID:
    permit_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO mainline.permit
          (permit_id, site_id, site_role, external_ref, ref_name, state, horizon_at)
        VALUES (%s, %s, %s, %s, %s, 'draft', now() + INTERVAL '7 days')
        """,
        (permit_id, site_id, "site_marrindal", external_ref, f"permit/{external_ref}"),
    )
    return permit_id


def insert_permit_clause(
    conn: Any,
    *,
    permit_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    commit: Commit,
    relation: str = "relies_on",
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.permit_clause (permit_id, clause_uuid, commit_id, relation)
        VALUES (%s, %s, %s, %s)
        """,
        (permit_id, clause_uuid, commit.commit_id, relation),
    )


def insert_cr(conn: Any, *, site_id: uuid.UUID, external_ref: str) -> uuid.UUID:
    cr_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO mainline.change_request
          (cr_id, site_id, site_role, external_ref, ref_name, target_ref, state)
        VALUES (%s, %s, %s, %s, %s, %s, 'draft')
        """,
        (
            cr_id,
            site_id,
            "site_marrindal",
            external_ref,
            f"cr/{external_ref}",
            "site/marrindal/main",
        ),
    )
    return cr_id


def insert_cr_clause(
    conn: Any,
    *,
    cr_id: uuid.UUID,
    clause_uuid: uuid.UUID,
    commit: Commit,
    relation: str = "edits",
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.cr_clause (cr_id, clause_uuid, commit_id, relation)
        VALUES (%s, %s, %s, %s)
        """,
        (cr_id, clause_uuid, commit.commit_id, relation),
    )


def rows(conn: Any, sql: str, params: Sequence[Any] = ()) -> Sequence[tuple[Any, ...]]:
    return conn.execute(sql, tuple(params)).fetchall()


# ── one whole scene, for the differential ────────────────────────────────────


@dataclass(frozen=True)
class CommitScene:
    """A parent commit, a child commit, and every fact the ledger reads.

    Built from a seed so the 200-commit differential is reproducible byte for
    byte across processes and machines.
    """

    site_id: uuid.UUID
    parent: Commit
    child: Commit
    doc_id: uuid.UUID
    ancestors: tuple[uuid.UUID, ...]
    severities: tuple[int, ...]
    dispositions: tuple[str, ...]


#: The dispositions a scene can give an ancestor, and what each one exercises.
#: ``"absent_only"`` is the interesting one: an ``identity_assignment`` row
#: declaring the ancestor absent, with NO residue row, which is an assertion with
#: no obligation attached and must leave the account UNBALANCED.
SCENE_DISPOSITIONS: Final[tuple[str, ...]] = (
    "matched",
    "split",
    "merge",
    "residue_open",
    "residue_disposed",
    "residue_open_and_matched",
    "residue_two_reasons_open",
    "absent_only",
    "nothing",
)


def build_scene(
    conn: Any,
    *,
    site_id: uuid.UUID,
    seed: int,
    n_ancestors: int,
    severities: Sequence[int],
    dispositions: Sequence[str],
) -> CommitScene:
    """Materialise one parent/child pair with the given per-ancestor treatment.

    Every clause is versioned in BOTH commits — the parent version is what makes
    it an ancestor, the child version is what makes the document ``touched`` —
    and every parent version gets a closure row, because ``0140a`` refuses when
    one is missing and that refusal has its own test.
    """
    if len(severities) != n_ancestors or len(dispositions) != n_ancestors:
        raise RuntimeError("severities and dispositions must be one per ancestor")

    parent = insert_commit(conn, site_id=site_id, label=f"scene-{seed}-parent", gen=1)
    child = insert_commit(conn, site_id=site_id, label=f"scene-{seed}-child", gen=2, parent=parent)
    doc_id = insert_doc(conn, site_id=site_id, doc_code=f"PROC-{seed:05d}")

    ancestors: list[uuid.UUID] = []
    for index in range(n_ancestors):
        clause_uuid = insert_clause(conn, site_id=site_id, birth=parent)
        ancestors.append(clause_uuid)
        insert_clause_version(
            conn,
            site_id=site_id,
            doc_id=doc_id,
            clause_uuid=clause_uuid,
            commit=parent,
            ordinal=index,
        )
        insert_closure(
            conn,
            site_id=site_id,
            clause_uuid=clause_uuid,
            as_of=parent,
            max_severity=severities[index],
        )
        insert_clause_version(
            conn,
            site_id=site_id,
            doc_id=doc_id,
            clause_uuid=clause_uuid,
            commit=child,
            ordinal=index,
        )

    for clause_uuid, disposition in zip(ancestors, dispositions, strict=True):
        _apply_disposition(
            conn, site_id=site_id, child=child, ancestor=clause_uuid, kind=disposition
        )

    return CommitScene(
        site_id=site_id,
        parent=parent,
        child=child,
        doc_id=doc_id,
        ancestors=tuple(ancestors),
        severities=tuple(severities),
        dispositions=tuple(dispositions),
    )


def _apply_disposition(
    conn: Any, *, site_id: uuid.UUID, child: Commit, ancestor: uuid.UUID, kind: str
) -> None:
    """Write the rows one scene disposition calls for.  An ``if``/``elif`` ladder
    with exactly one exit, because a fixture that returns early in seven places is
    a fixture in which one forgotten branch writes nothing and the test still
    passes."""
    if kind == "nothing":
        pass
    elif kind in {"matched", "merge"}:
        insert_assignment(
            conn,
            site_id=site_id,
            commit=child,
            ancestor=ancestor,
            relation=kind,
            descendant=ancestor,
        )
    elif kind == "split":
        # A split writes one row per child.  Two rows for one ancestor is exactly
        # the shape that makes counting rows instead of ancestors wrong, so the
        # fixture produces it on purpose.
        insert_assignment(
            conn,
            site_id=site_id,
            commit=child,
            ancestor=ancestor,
            relation="split",
            descendant=ancestor,
        )
        insert_assignment(
            conn,
            site_id=site_id,
            commit=child,
            ancestor=ancestor,
            relation="split",
            descendant=uuid.uuid4(),
            stage="S2",
        )
    elif kind == "residue_open":
        insert_residue(conn, site_id=site_id, commit=child, ancestor=ancestor)
    elif kind == "residue_disposed":
        insert_residue(
            conn,
            site_id=site_id,
            commit=child,
            ancestor=ancestor,
            disposition_id=uuid.uuid4(),
        )
    elif kind == "residue_open_and_matched":
        insert_assignment(
            conn,
            site_id=site_id,
            commit=child,
            ancestor=ancestor,
            relation="matched",
            descendant=ancestor,
        )
        insert_residue(conn, site_id=site_id, commit=child, ancestor=ancestor, reason="ambiguous")
    elif kind == "residue_two_reasons_open":
        insert_residue(conn, site_id=site_id, commit=child, ancestor=ancestor, reason="ambiguous")
        insert_residue(conn, site_id=site_id, commit=child, ancestor=ancestor, reason="anchor_drop")
    elif kind == "absent_only":
        insert_assignment(conn, site_id=site_id, commit=child, ancestor=ancestor, relation="absent")
    else:
        raise RuntimeError(f"unknown scene disposition {kind!r}")
