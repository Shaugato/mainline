#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Prove that ``reconcile_demo_checkpoints.sql`` turns custody checks 2 and 3 green — and
that it changes nothing else.

WHAT THIS PROGRAM IS FOR
========================
``scripts/deploy/reconcile_demo_checkpoints.sql`` deletes one checkpoint row and one
cosignature row from the demo's custody ledger. A ``DELETE`` in a deployment script is the
kind of statement that has to be *proved*, not reviewed, because the failure it can produce
— the wrong row, or one extra row — is invisible on every screen that would have shown it.

So this program runs the reconciliation between two full measurements of the same database
and refuses unless all seven of these hold:

  A. **Before**, checks 2 and 3 both FAIL, and they fail for the stated reason. A proof that
     starts from green proves nothing; this is the discriminating half.
  B. **After**, checks 2 and 3 both PASS.
  C. Every SURVIVING checkpoint is byte-identical to what it was — its root, its note, its
     cosignature — and so is every leaf and every interior node the payload carries. A
     reconciliation that fixed two checks by moving a third row is a regression with good
     manners.
  D. Of every base table in the six schemas this deployment uses — 89 of them in the
     database this was proved on — exactly TWO change:
     ``mainline.ledger_checkpoint`` and ``mainline.cosignature``, each losing exactly one
     row. Every surviving row is byte-identical to a row that was there before — nothing was
     updated, nothing was inserted, and no other table moved at all.
  E. The row that left is the one the predicate describes: a checkpoint whose ``root_hash``
     is the SHA-256 of a string naming itself and appears nowhere in ``mainline.ledger_node``.
  F. Every recall policy at the site is still anchored: some admissible, cosigned checkpoint
     with ``tree_size >= anchored_tree_size`` survives. That is
     ``mainline.fn_recall_policy_anchored``'s own predicate (migration 0112), re-asked here.
  G. A SECOND application changes nothing at all. Idempotence is asserted by running it, not
     by reading the ``WHERE`` clause.

THIS PROGRAM NEVER TOUCHES AWS
==============================
It refuses any DSN whose host is not ``localhost`` / ``127.0.0.1`` / ``::1``, and there is no
flag that overrides that. The reconciliation is applied to the DEPLOYED database by the
orchestrator, never by this script and never by the worker that wrote it. A verifier that
could be pointed at production is a deployment tool wearing a verifier's name.

WHAT THE CHECK NUMBERS MEAN, AND WHOSE ARITHMETIC THIS IS
=========================================================
The numbers are ``spec/custody/checks.yaml``'s. The payload is the demo API's OWN reader —
``mainline_demo_api.reads.read_ledger``, the exact function behind ``GET /v1/ledger`` — so
what is verified here is the bytes a browser would receive, not a convenient re-query.

The RFC 6962 arithmetic is ``trappoint_ledger.merkle``: the repository's own tree, the one
the sequencer appends with. It is NOT the console's TypeScript verifier — that one runs in
the reader's browser and its verdicts are the ones the custody screen prints. This program
asks the SAME two questions of the SAME bytes with the repository's Python implementation,
which is the useful kind of redundancy: two implementations of one RFC, and a disagreement
between them would itself be a finding.

Checks 4 and 10 are reported here as **facts about the note text**, never as verdicts. This
program does not implement them and does not pretend to: it prints whether each note has a
signature section, whether its root line decodes to 32 bytes, and whether it carries a
``canon:`` extension line, and it asserts only that those facts are UNCHANGED by the
reconciliation. Their verdicts belong to the console's verifier and to ``trappoint-verify``.

Usage::

    # the full proof, on a scratch database of your own
    .venv/Scripts/python.exe scripts/deploy/verify_demo_checkpoints.py \\
        --dsn 'postgresql://root@localhost:26257/w_w6?sslmode=disable' \\
        --reproduce --apply

    # measure a database somebody else reconciled, and change nothing
    .venv/Scripts/python.exe scripts/deploy/verify_demo_checkpoints.py --dsn '...'

Exit status is ``0`` only on ``VERDICT RECONCILED`` (with ``--apply``) or ``VERDICT CLEAN``
(without it). Every other outcome exits ``1`` and says which of A to G failed.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import sys
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_API_SRC = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"
LEDGER_SRC = REPO_ROOT / "packages" / "trappoint-ledger" / "src"
RECONCILE_SQL = REPO_ROOT / "scripts" / "deploy" / "reconcile_demo_checkpoints.sql"

for _source_root in (DEMO_API_SRC, LEDGER_SRC):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

import psycopg  # noqa: E402
from mainline_demo_api import reads  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from trappoint_ledger.merkle import (  # noqa: E402
    merkle_tree_hash,
    verify_consistency,
    verify_inclusion,
)

DEFAULT_DSN = "postgresql://root@localhost:26257/w_w6?sslmode=disable"
DEMO_SITE_CODE = "dec0de00-0001-4000-8000-000000000001"
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "[::1]"})

# The name the deployment and its local mirror both use. `--reproduce` is refused on it: a
# database other lanes read is not a place to insert a row known to be false, even locally.
PROTECTED_DATABASES = frozenset({"mainline_demo", "defaultdb", "postgres", "system"})

# Every schema the deployment writes into, plus the migrator's own bookkeeping. `trappoint`
# is in the list precisely BECAUSE the reconciliation has no business there: a census that
# only watched the tables one expects to move is a census that cannot be surprised.
CENSUS_SCHEMAS = (
    "mainline",
    "mainline_audit",
    "mainline_meas",
    "mainline_ops",
    "mainline_qa",
    "trappoint",
)

# The two tables the reconciliation is allowed to change, and by how much.
EXPECTED_DELTA = {"mainline.ledger_checkpoint": -1, "mainline.cosignature": -1}

# The pre-2026-08-14 §8 statements, verbatim, so the defect is REPRODUCED rather than
# imagined. `git show 8e6a195:verticals/mainline/db/seeds/demo/demo_world.sql` is where these
# two came from; not one character of arithmetic is typed here, `digest()` computes it all.
REPRODUCE_SQL = """
INSERT INTO mainline.ledger_checkpoint (
  site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, admissible, issued_at
) VALUES (
  'dec0de00-0001-4000-8000-000000000001',
  1,
  digest('mainline-demo/ledger/root/1', 'sha256'),
  'mainline/dec0de00-0001-4000-8000-000000000001' || chr(10) || '1' || chr(10)
    || encode(digest('mainline-demo/ledger/root/1', 'sha256'), 'hex') || chr(10),
  '{"synthetic": true, "drand_round": 1, "nist_pulse": 1,
    "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
  digest('mainline-demo/ledger/logsig/1', 'sha256'),
  digest('mainline-demo/ledger/canon-src', 'sha256'),
  true,
  TIMESTAMPTZ '2026-08-01 01:00:00+00'
)
ON CONFLICT DO NOTHING;

INSERT INTO mainline.cosignature (
  site_code, tree_size, witness_id, trust_domain, adverse, sig, received_at
) VALUES (
  'dec0de00-0001-4000-8000-000000000001',
  1,
  'witness.demo/hsr-1', 'union_hsr', true,
  digest('mainline-demo/ledger/cosig/1', 'sha256'),
  TIMESTAMPTZ '2026-08-01 01:05:00+00'
)
ON CONFLICT DO NOTHING;
"""


# ── Refusals ───────────────────────────────────────────────────────────────


class Refused(RuntimeError):
    """A precondition this program will not proceed without."""


def require_local(dsn: str) -> None:
    """Refuse a DSN that is not on this machine. There is no override flag, on purpose."""
    host = urlsplit(dsn).hostname or ""
    if host not in LOCAL_HOSTS:
        raise Refused(
            f"refusing to connect to host {host!r}. This program reproduces a defect and "
            "applies a DELETE; it runs against a local cluster and nothing else. The "
            "reconciliation is applied to the deployed database by the orchestrator."
        )


def database_of(dsn: str) -> str:
    return urlsplit(dsn).path.lstrip("/")


# ── Measurement ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckReading:
    """One check's status and the sentence that earns it. Never a bare boolean."""

    check_id: int
    name: str
    status: str
    detail: str

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Measurement:
    """Everything this program knows about the database at one instant."""

    label: str
    census: dict[str, dict[str, Any]]
    row_digests: dict[str, list[str]]
    checkpoints: list[dict[str, Any]]
    checks: list[CheckReading]
    note_facts: list[dict[str, Any]]
    anchors: list[dict[str, Any]]
    """SHA-256 over the payload's leaves and nodes, in payload order. Claim C's subject."""
    leaves_digest: str
    nodes_digest: str

    def facts_by_size(self) -> dict[int, dict[str, Any]]:
        return {int(fact["tree_size"]): fact for fact in self.note_facts}

    def checkpoints_by_size(self) -> dict[int, dict[str, Any]]:
        return {int(row["tree_size"]): row for row in self.checkpoints}

    def status_of(self, check_id: int) -> str:
        for check in self.checks:
            if check.check_id == check_id:
                return check.status
        raise Refused(f"no check {check_id} in measurement {self.label!r}")

    def as_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "census": self.census,
            "checkpoints": self.checkpoints,
            "checks": [check.as_json() for check in self.checks],
            "note_facts": self.note_facts,
            "anchors": self.anchors,
            "leaves_digest": self.leaves_digest,
            "nodes_digest": self.nodes_digest,
        }


def census(conn: psycopg.Connection[Any]) -> dict[str, dict[str, Any]]:
    """Row count and an order-independent content digest for every table in the database.

    The digest is ``md5`` over the sorted per-row ``md5(row::STRING)`` values, so it is
    invariant to storage order and sensitive to any change in any column of any row. That is
    what makes claim D checkable rather than assertable: "nothing else changed" is a statement
    about every table in the six schemas, and counting rows alone would miss an UPDATE.
    """
    tables = conn.execute(
        """
        SELECT table_schema, table_name
          FROM information_schema.tables
         WHERE table_type = 'BASE TABLE' AND table_schema = ANY(%s)
         ORDER BY table_schema, table_name
        """,
        (list(CENSUS_SCHEMAS),),
    ).fetchall()

    out: dict[str, dict[str, Any]] = {}
    for row in tables:
        qualified = f"{row['table_schema']}.{row['table_name']}"
        # S608: the only interpolation is `qualified`, and it comes from
        # `information_schema.tables` on this same connection — a name the server just told
        # us it has. There is no parameter form for a table name, and no caller-supplied
        # string reaches this statement.
        measured = conn.execute(
            f"SELECT count(*) AS n, md5(string_agg(h, '' ORDER BY h)) AS d "  # noqa: S608
            f"FROM (SELECT md5(t::STRING) AS h FROM {qualified} t)"
        ).fetchone()
        out[qualified] = {"rows": int(measured["n"]), "digest": measured["d"]}
    return out


def row_digests(conn: psycopg.Connection[Any], qualified: str) -> list[str]:
    """The per-row digests of one table, sorted. Set arithmetic over these is claim D's proof."""
    # S608: `qualified` is a key of EXPECTED_DELTA, a module constant. No caller-supplied
    # string reaches this statement either.
    rows = conn.execute(
        f"SELECT md5(t::STRING) AS h FROM {qualified} t ORDER BY h"  # noqa: S608
    ).fetchall()
    return [row["h"] for row in rows]


def checkpoint_rows(conn: psycopg.Connection[Any], site_code: str) -> list[dict[str, Any]]:
    """The checkpoints as the database holds them, plus whether each root is a real node.

    ``root_is_a_node`` is the conjunct the reconciliation's predicate turns on, read back from
    the database rather than restated: a checkpoint whose root is a node the appender built is
    a checkpoint over leaves that exist.
    """
    rows = conn.execute(
        """
        SELECT cp.tree_size,
               encode(cp.root_hash, 'hex')                        AS root_hex,
               cp.admissible,
               EXISTS (SELECT 1 FROM mainline.ledger_node n
                        WHERE n.site_code = cp.site_code AND n.hash = cp.root_hash)
                                                                  AS root_is_a_node,
               cp.root_hash = digest('mainline-demo/ledger/root/' || cp.tree_size::STRING,
                                     'sha256')                    AS root_is_its_own_name,
               EXISTS (SELECT 1 FROM mainline.cosignature cs
                        WHERE cs.site_code = cp.site_code AND cs.tree_size = cp.tree_size)
                                                                  AS cosigned
          FROM mainline.ledger_checkpoint cp
         WHERE cp.site_code = %s
         ORDER BY cp.tree_size
        """,
        (site_code,),
    ).fetchall()
    return [dict(row) for row in rows]


def anchor_readings(conn: psycopg.Connection[Any], site_code: str) -> list[dict[str, Any]]:
    """``fn_recall_policy_anchored``'s predicate (migration 0112), asked of every policy.

    Claim F. The trigger fires on INSERT into ``recall_run``; nothing re-asks it when a
    checkpoint is deleted, so this program asks it directly rather than trusting that the row
    it removed was not the one holding an anchor up.
    """
    rows = conn.execute(
        """
        SELECT rp.policy_version,
               rp.anchored_tree_size,
               (SELECT count(*)
                  FROM mainline.ledger_checkpoint cp
                  JOIN mainline.cosignature cs
                    ON cs.site_code = cp.site_code AND cs.tree_size = cp.tree_size
                 WHERE cp.site_code = %s
                   AND cp.tree_size >= rp.anchored_tree_size
                   AND cp.admissible) AS cosigned_at_or_above
          FROM mainline_meas.recall_policy rp
         ORDER BY rp.policy_version
        """,
        (site_code,),
    ).fetchall()
    return [dict(row) for row in rows]


def ledger_payload(conn: psycopg.Connection[Any], site_code: str) -> dict[str, Any]:
    """``GET /v1/ledger``'s own bytes, through the demo API's own reader.

    The reader's refusals are re-raised as this program's, because they are findings. A
    reconciliation that removed every checkpoint would leave `read_ledger` answering *"no
    mainline.ledger_checkpoint rows"* — the 404 the founder met on the custody screen — and
    that has to arrive as a stated refusal with a verdict attached, not as a traceback.
    """
    try:
        return reads.read_ledger(conn, {}, {"site_code": site_code})["data"]
    except reads.NotFound as absent:
        raise Refused(
            f"the demo API's own reader cannot serve this site any more: {absent}. Whatever "
            "was just applied took the ledger with it."
        ) from absent


# ── Checks 2 and 3, with the repository's own RFC 6962 ──────────────────────


def leaf_hashes(payload: dict[str, Any]) -> list[bytes]:
    return [bytes.fromhex(leaf["leaf_hash_hex"]) for leaf in payload["leaves"]]


def check_inclusion(payload: dict[str, Any]) -> CheckReading:
    """Check 2 — every inclusion proof in the payload, against the root its checkpoint records."""
    proofs = payload.get("inclusion_proofs") or []
    if not proofs:
        return CheckReading(
            2,
            "inclusion_proof",
            "SKIP",
            "the payload carries no inclusion proofs, so no leaf has been shown to be in the "
            "tree a checkpoint committed to.",
        )
    roots = {int(cp["tree_size"]): cp["root_hex"] for cp in payload["checkpoints"]}
    leaves = {int(leaf["seq"]): bytes.fromhex(leaf["leaf_hash_hex"]) for leaf in payload["leaves"]}
    failures: list[str] = []
    for proof in proofs:
        size, seq = int(proof["tree_size"]), int(proof["seq"])
        root_hex = roots.get(size)
        if root_hex is None:
            failures.append(f"seq {seq} → size {size}: no checkpoint at that size.")
            continue
        leaf = leaves.get(seq)
        if leaf is None:
            failures.append(f"seq {seq} → size {size}: the payload carries no such leaf.")
            continue
        ok = verify_inclusion(
            leaf, seq, size, [bytes.fromhex(h) for h in proof["path_hex"]], bytes.fromhex(root_hex)
        )
        if not ok:
            recomputed = merkle_tree_hash(leaf_hashes(payload)[:size]).hex()
            failures.append(
                f"seq {seq} → size {size}: the proof does not reconstruct the recorded root "
                f"{root_hex}. The RFC 6962 Merkle Tree Hash of the first {size} leaf/leaves is "
                f"{recomputed}."
            )
    if failures:
        return CheckReading(2, "inclusion_proof", "FAIL", "\n".join(failures))
    return CheckReading(
        2,
        "inclusion_proof",
        "PASS",
        f"{len(proofs)} inclusion proof(s) reconstruct the checkpoint root they are against.",
    )


def check_consistency(payload: dict[str, Any]) -> CheckReading:
    """Check 3 — every consecutive checkpoint pair, RFC 6962 §2.1.2."""
    checkpoints = sorted(payload["checkpoints"], key=lambda cp: int(cp["tree_size"]))
    if len(checkpoints) < 2:
        return CheckReading(
            3,
            "consistency_proof_every_pair",
            "SKIP",
            f"this payload carries {len(checkpoints)} checkpoint(s), so there is no consecutive "
            "pair to prove consistency between.",
        )
    carried = payload.get("consistency_proofs") or []
    proofs = {(int(p["from_size"]), int(p["to_size"])): p for p in carried}
    failures: list[str] = []
    for earlier, later in pairwise(checkpoints):
        first, second = int(earlier["tree_size"]), int(later["tree_size"])
        proof = proofs.get((first, second))
        if proof is None:
            failures.append(
                f"{first}→{second}: no consistency proof. The registry requires one for EVERY "
                "consecutive pair; a missing pair is exactly where a deletion would be placed."
            )
            continue
        ok = verify_consistency(
            first,
            bytes.fromhex(earlier["root_hex"]),
            second,
            bytes.fromhex(later["root_hex"]),
            [bytes.fromhex(h) for h in proof["path_hex"]],
        )
        if not ok:
            failures.append(
                f"{first}→{second}: the proof does not carry the recorded root "
                f"{earlier['root_hex']} forward to {later['root_hex']}. The Merkle Tree Hash of "
                f"the first {first} leaf/leaves is "
                f"{merkle_tree_hash(leaf_hashes(payload)[:first]).hex()}."
            )
    if failures:
        return CheckReading(3, "consistency_proof_every_pair", "FAIL", "\n".join(failures))
    return CheckReading(
        3,
        "consistency_proof_every_pair",
        "PASS",
        f"every consecutive checkpoint pair ({len(checkpoints) - 1} of them) is proved consistent.",
    )


def check_root_recomputation(payload: dict[str, Any]) -> CheckReading:
    """Not a registry check — the arithmetic under 2 and 3, stated once so it can be quoted.

    For every checkpoint, the RFC 6962 Merkle Tree Hash of the first ``tree_size`` leaves the
    payload carries, against the root the row records. This is the shortest possible statement
    of what is wrong with a self-naming checkpoint, and it needs no proof array at all.
    """
    hashes = leaf_hashes(payload)
    lines: list[str] = []
    disagree = 0
    for checkpoint in sorted(payload["checkpoints"], key=lambda cp: int(cp["tree_size"])):
        size = int(checkpoint["tree_size"])
        if size > len(hashes):
            lines.append(f"tree_size {size}: the payload carries only {len(hashes)} leaves.")
            disagree += 1
            continue
        recomputed = merkle_tree_hash(hashes[:size]).hex()
        agrees = recomputed == checkpoint["root_hex"]
        disagree += 0 if agrees else 1
        lines.append(
            f"tree_size {size}: MTH {recomputed} "
            f"{'==' if agrees else '!='} recorded {checkpoint['root_hex']}"
        )
    status = "PASS" if disagree == 0 else "FAIL"
    return CheckReading(0, "root_recomputation", status, "\n".join(lines))


def note_facts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Facts about each checkpoint note. NOT checks 4 and 10 — their inputs.

    Every field is a property of the bytes, decidable without a key and without a pin. This
    program asserts only that they are UNCHANGED across the reconciliation; what they add up
    to is the console verifier's verdict and ``trappoint-verify``'s, not this script's.
    """
    out: list[dict[str, Any]] = []
    for checkpoint in sorted(payload["checkpoints"], key=lambda cp: int(cp["tree_size"])):
        note: str = checkpoint["note"]
        lines = note.split("\n")
        root_line = lines[2] if len(lines) > 2 else ""
        try:
            decoded_bytes = len(base64.b64decode(root_line, validate=True))
        except (ValueError, TypeError):
            decoded_bytes = -1
        # A C2SP note ends with a newline, so `split` always yields a trailing empty string.
        # The signature section is what follows the LAST EMPTY LINE, so the terminator is
        # excluded before looking for one: `…root\n` has no signature section, `…root\n\nsig\n`
        # has. Counting the terminator as an empty line would report every note as signed.
        out.append(
            {
                "tree_size": int(checkpoint["tree_size"]),
                "has_signature_section": "" in lines[1:-1],
                "root_line_decodes_to_bytes": decoded_bytes,
                "root_line_is_hex_of_root": root_line == checkpoint["root_hex"],
                "carries_canon_extension": any(line.startswith("canon:") for line in lines),
            }
        )
    return out


def digest_of(value: Any) -> str:
    """SHA-256 over a JSON rendering with sorted keys. Stable, and sensitive to one byte."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def measure(conn: psycopg.Connection[Any], site_code: str, label: str) -> Measurement:
    payload = ledger_payload(conn, site_code)
    return Measurement(
        label=label,
        census=census(conn),
        row_digests={table: row_digests(conn, table) for table in EXPECTED_DELTA},
        checkpoints=checkpoint_rows(conn, site_code),
        checks=[
            check_root_recomputation(payload),
            check_inclusion(payload),
            check_consistency(payload),
        ],
        note_facts=note_facts(payload),
        anchors=anchor_readings(conn, site_code),
        leaves_digest=digest_of(payload["leaves"]),
        nodes_digest=digest_of(payload.get("nodes")),
    )


# ── The verdict ────────────────────────────────────────────────────────────


@dataclass
class Verdict:
    """Claims A to G, each recorded with the sentence that earned it."""

    claims: list[dict[str, Any]] = field(default_factory=list)

    def record(self, claim: str, held: bool, detail: str) -> None:
        self.claims.append({"claim": claim, "held": held, "detail": detail})

    @property
    def ok(self) -> bool:
        return all(entry["held"] for entry in self.claims)


def judge_reconciliation(before: Measurement, after: Measurement, again: Measurement) -> Verdict:
    verdict = Verdict()

    verdict.record(
        "A · before, checks 2 and 3 both FAIL",
        before.status_of(2) == "FAIL" and before.status_of(3) == "FAIL",
        f"check 2 {before.status_of(2)}, check 3 {before.status_of(3)}. A proof that starts "
        "from green proves nothing.",
    )
    verdict.record(
        "B · after, checks 2 and 3 both PASS",
        after.status_of(2) == "PASS" and after.status_of(3) == "PASS",
        f"check 2 {after.status_of(2)}, check 3 {after.status_of(3)}.",
    )

    # Checks 0, 2 and 3 are the arithmetic under proof — 0 IS the recomputation that 2 and 3
    # rest on, and it moves with them or the proof is incoherent. Everything a surviving
    # checkpoint carries, and every leaf and node, must be identical.
    survivors = set(after.checkpoints_by_size()) & set(before.checkpoints_by_size())
    rows_same = all(
        before.checkpoints_by_size()[size] == after.checkpoints_by_size()[size]
        for size in survivors
    )
    facts_same = all(
        before.facts_by_size()[size] == after.facts_by_size()[size] for size in survivors
    )
    trees_same = (
        before.leaves_digest == after.leaves_digest and before.nodes_digest == after.nodes_digest
    )
    coherent = after.status_of(0) == "PASS" and before.status_of(0) == "FAIL"
    verdict.record(
        "C · every surviving checkpoint, leaf and node is unchanged",
        rows_same and facts_same and trees_same and coherent,
        f"{len(survivors)} surviving checkpoint(s) {sorted(survivors)}: rows identical "
        f"{rows_same}, note facts identical {facts_same}; leaves digest "
        f"{'unchanged' if before.leaves_digest == after.leaves_digest else 'CHANGED'}, nodes "
        f"digest {'unchanged' if before.nodes_digest == after.nodes_digest else 'CHANGED'}. The "
        f"recomputation under checks 2 and 3 moved {before.status_of(0)} → {after.status_of(0)}, "
        "which is the same defect leaving and not a second one.",
    )

    moved = {
        table: (after.census[table]["rows"] - reading["rows"])
        for table, reading in before.census.items()
        if after.census.get(table, {}).get("digest") != reading["digest"]
    }
    subset = all(
        set(after.row_digests[table]).issubset(set(before.row_digests[table]))
        for table in EXPECTED_DELTA
    )
    verdict.record(
        "D · exactly two tables changed, each losing exactly one row, none modified",
        moved == EXPECTED_DELTA and subset and set(before.census) == set(after.census),
        f"tables whose content digest changed: {moved or 'none'}; every surviving row of both "
        f"is byte-identical to one that was there before: {subset}.",
    )

    gone = [
        row
        for row in before.checkpoints
        if row["tree_size"] not in {r["tree_size"] for r in after.checkpoints}
    ]
    verdict.record(
        "E · the row that left is the one the predicate describes",
        len(gone) == 1 and bool(gone[0]["root_is_its_own_name"]) and not gone[0]["root_is_a_node"],
        "removed "
        + ", ".join(
            f"tree_size {row['tree_size']} root {row['root_hex']} "
            f"(root_is_its_own_name={row['root_is_its_own_name']}, "
            f"root_is_a_node={row['root_is_a_node']})"
            for row in gone
        )
        + f"; kept {[row['tree_size'] for row in after.checkpoints]}.",
    )

    anchored = all(int(row["cosigned_at_or_above"]) > 0 for row in after.anchors)
    verdict.record(
        "F · every recall policy is still anchored inside a cosigned checkpoint",
        anchored,
        "; ".join(
            f"{row['policy_version']} anchored at {row['anchored_tree_size']} → "
            f"{row['cosigned_at_or_above']} admissible cosigned checkpoint(s) at or above"
            for row in after.anchors
        )
        or "no recall policy rows",
    )

    verdict.record(
        "G · a second application changes nothing at all",
        again.census == after.census,
        "the full census is byte-identical across the second apply."
        if again.census == after.census
        else "the second apply moved "
        + str(
            {
                table: (again.census[table]["rows"] - reading["rows"])
                for table, reading in after.census.items()
                if again.census.get(table, {}).get("digest") != reading["digest"]
            }
        ),
    )
    return verdict


# ── Driving ────────────────────────────────────────────────────────────────


def apply_sql(conn: psycopg.Connection[Any], path: Path, label: str) -> None:
    """Apply one SQL file as ONE statement batch, and report a refusal by its SQLSTATE.

    The database's own refusal is the interesting output, not a traceback. A reconciliation
    whose statements are in the wrong order answers `23503` — the cosignature's foreign key
    onto the checkpoint — and a reader needs to see that code rather than 40 lines of Python.
    """
    if not path.is_file():
        raise Refused(f"no SQL file at {path}")
    print(f"  apply        {label:<28} {path.name}", flush=True)
    try:
        conn.execute(path.read_text(encoding="utf-8"))
    except psycopg.Error as refusal:
        sqlstate = refusal.diag.sqlstate or "unknown"
        raise Refused(
            f"the database refused {path.name} with SQLSTATE {sqlstate}: "
            f"{' '.join(str(refusal).split())}"
        ) from refusal


def print_measurement(measurement: Measurement) -> None:
    print(f"\n── {measurement.label} " + "─" * (58 - len(measurement.label)), flush=True)
    for row in measurement.checkpoints:
        print(
            f"  checkpoint   tree_size {row['tree_size']:<3} root {row['root_hex']}"
            f"  node={row['root_is_a_node']!s:<5} self_named={row['root_is_its_own_name']!s:<5}"
            f" cosigned={row['cosigned']}",
            flush=True,
        )
    for check in measurement.checks:
        print(f"  check {check.check_id:<2} {check.name:<28} {check.status}", flush=True)
        for line in check.detail.split("\n"):
            print(f"               {line}", flush=True)
    for fact in measurement.note_facts:
        print(
            f"  note         tree_size {fact['tree_size']}: signature_section="
            f"{fact['has_signature_section']} root_line_decodes_to="
            f"{fact['root_line_decodes_to_bytes']}B canon_extension="
            f"{fact['carries_canon_extension']}",
            flush=True,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_demo_checkpoints.py",
        description=(
            "Prove reconcile_demo_checkpoints.sql turns custody checks 2 and 3 green and "
            "changes nothing else. Local clusters only; never AWS."
        ),
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="a LOCAL CockroachDB DSN")
    parser.add_argument("--site-code", default=DEMO_SITE_CODE)
    parser.add_argument(
        "--reproduce",
        action="store_true",
        help="insert the superseded tree_size=1 checkpoint first, exactly as the pre-2026-08-14 "
        "seed wrote it, so the proof starts from the defect",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply scripts/deploy/reconcile_demo_checkpoints.sql between the two measurements",
    )
    parser.add_argument("--sql", type=Path, default=RECONCILE_SQL)
    parser.add_argument("--json", type=Path, default=None, help="write the evidence here")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, and this program prints hashes, rule characters and
    # the reader's own sentences. Re-encoding the stream is the fix; stripping characters out
    # of a measurement to suit a terminal is editing evidence.
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    args = build_parser().parse_args(argv)
    try:
        require_local(args.dsn)
    except Refused as refusal:
        print(f"REFUSED  {refusal}", flush=True)
        return 1

    database = database_of(args.dsn)
    if args.reproduce and database in PROTECTED_DATABASES:
        print(
            f"REFUSED  --reproduce inserts a checkpoint that commits to nothing, and {database!r} "
            "is a database other lanes read. Create one of your own: CREATE DATABASE w_yours.",
            flush=True,
        )
        return 1

    print(f"verify_demo_checkpoints · database {database} · site {args.site_code}", flush=True)

    evidence: dict[str, Any] = {"database": database, "site_code": args.site_code}
    try:
        return _run(args, evidence)
    except Refused as refusal:
        print(f"\nREFUSED  {refusal}", flush=True)
        print("VERDICT REFUSED — nothing below this line was measured.", flush=True)
        return 1


def _run(args: argparse.Namespace, evidence: dict[str, Any]) -> int:
    with psycopg.connect(
        args.dsn, autocommit=True, connect_timeout=10, row_factory=dict_row
    ) as conn:
        if args.reproduce:
            print("  reproduce    the superseded tree_size=1 checkpoint and its cosignature")
            conn.execute(REPRODUCE_SQL)

        before = measure(conn, args.site_code, "BEFORE")
        print_measurement(before)
        evidence["before"] = before.as_json()

        if not args.apply:
            clean = before.status_of(2) == "PASS" and before.status_of(3) == "PASS"
            print(
                f"\nVERDICT {'CLEAN' if clean else 'RED'} — measured only; nothing was applied.",
                flush=True,
            )
            if args.json is not None:
                args.json.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
            return 0 if clean else 1

        apply_sql(conn, args.sql, "reconcile (first)")
        after = measure(conn, args.site_code, "AFTER")
        print_measurement(after)
        evidence["after"] = after.as_json()

        apply_sql(conn, args.sql, "reconcile (second, idempotence)")
        again = measure(conn, args.site_code, "AFTER SECOND APPLY")
        evidence["after_second_apply"] = again.as_json()

    verdict = judge_reconciliation(before, after, again)
    evidence["claims"] = verdict.claims
    print("\n── the verdict " + "─" * 50, flush=True)
    for claim in verdict.claims:
        print(f"  [{'HELD' if claim['held'] else 'FAILED'}] {claim['claim']}", flush=True)
        print(f"           {claim['detail']}", flush=True)

    if args.json is not None:
        args.json.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json}", flush=True)

    print(
        f"\nVERDICT {'RECONCILED' if verdict.ok else 'REFUSED'} — "
        f"{sum(1 for c in verdict.claims if c['held'])}/{len(verdict.claims)} claims held.",
        flush=True,
    )
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
