# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The schema fingerprint, and the chain it is appended to.

This is the eighty lines that make the migration runner worth owning
(research/06-build/schema-migrations.md §6). After every applied statement the runner
computes a fingerprint of the *whole* schema and appends it to a chained ledger. Three
things fall out, and the second one is the interesting one:

**(a) Schema drift is caught by the same patrol that catches procedure drift.** One
mechanism, two surfaces; "as-documented versus as-operated" now covers the database.

**(b) The gate attests to itself.** ``pg_get_triggerdef()`` puts the merge gate's own
source text inside the hash. Nobody can quietly weaken the trigger that prevents
quietly weakening controls, because weakening it changes the fingerprint and the
fingerprint is in a ledger that cannot be rewritten without leaving a gap.

**(c) Environment parity is one equality check.**

Two platform facts shape the implementation and both are honoured rather than hoped
past:

* ``SHOW CREATE ALL TABLES`` guarantees CREATE-before-ALTER ordering but **not**
  intra-category ordering, so the statements are normalised — whitespace collapsed,
  then sorted — *before* hashing, and the fingerprint is computed twice in one run to
  assert it is stable. A fingerprint that flickers is worse than no fingerprint: it
  trains everybody to ignore the alarm.
* ``SHOW CREATE ALL TABLES`` **omits triggers and routines**, which is why the
  ``pg_catalog`` queries are mandatory. ``pg_get_triggerdef()`` is ground-truth check
  **GT-05**; both it and ``pg_get_functiondef()`` were confirmed present on CockroachDB
  CCL **v26.2.5** on 2026-08-07 by running ``trappoint migrate attest`` against a local
  single-node cluster, which reported ``grade strong``. Behaviour on CockroachDB Cloud
  Standard, whose SQL identity differs, is NOT yet verified — so the probe stays, and
  where either routine is absent the runner falls back to the table-granular view and
  records ``attestation_grade = 'weak'`` in the row. The claim softens **in the data**,
  not only in the prose: a run whose attestation was weak is never indistinguishable
  from one whose attestation was strong.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import psycopg

from .bootstrap import GENESIS_FINGERPRINT
from .db import fetch_all, in_txn
from .errors import AttestationDrift
from .sqltext import collapse_whitespace

__all__ = [
    "Attestation",
    "ChainHead",
    "append",
    "chain_head",
    "fingerprint",
    "stable_fingerprint",
    "verify_chain",
]

# Domain separation between the parts, so that moving a statement from one part to
# another cannot leave the digest unchanged.
_PART_SEPARATOR = b"\x1e"
_LABEL_SEPARATOR = b"\x1f"


@dataclass(frozen=True, slots=True)
class Attestation:
    """A computed fingerprint and how much it is worth."""

    digest: bytes
    grade: str
    """``strong`` when triggers and routines are in the hash; ``weak`` when GT-05's
    fallback was taken and the hash covers tables only."""
    parts: tuple[str, ...]
    """The labels that contributed, in order — printed by ``status`` so the grade is
    never the only evidence of what was covered."""


@dataclass(frozen=True, slots=True)
class ChainHead:
    """The newest attestation row."""

    ordinal: int
    fingerprint: bytes
    grade: str
    kind: str
    version: str


def _routine_support(conn: psycopg.Connection[Any]) -> tuple[bool, bool]:
    """Probe for ``pg_get_triggerdef`` and ``pg_get_functiondef`` (GT-05).

    Probed by catalogue lookup rather than by calling the function with a dummy oid: a
    call that errors for the *wrong* reason would be read as absence, and "the feature
    is missing" is a claim the runner writes into a ledger.
    """
    rows = fetch_all(
        conn,
        """
        SELECT proname FROM pg_catalog.pg_proc
        WHERE proname IN ('pg_get_triggerdef', 'pg_get_functiondef')
        """,
    )
    names = {str(r["proname"]) for r in rows}
    return "pg_get_triggerdef" in names, "pg_get_functiondef" in names


def _rows_as_text(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        joined = " | ".join(
            collapse_whitespace(str(value)) for _, value in sorted(row.items()) if value is not None
        )
        if joined:
            out.append(joined)
    return out


def _part(label: str, rows: list[str]) -> bytes:
    # Sorted, because intra-category ordering is not guaranteed by SHOW CREATE.
    body = "\n".join(sorted(rows))
    return label.encode("utf-8") + _LABEL_SEPARATOR + body.encode("utf-8")


def fingerprint(conn: psycopg.Connection[Any], *, schema_prefixes: tuple[str, ...]) -> Attestation:
    r"""Compute the schema fingerprint once.

    *schema_prefixes* are ``LIKE`` patterns naming the schemas whose routines are
    covered, e.g. ``("mainline%", "trappoint%", "trappoint\\_ref%")``. Tables, types and
    schemas are taken from the ``SHOW CREATE ALL …`` statements, which are
    cluster-database scoped and need no filter.
    """
    parts: list[bytes] = []
    labels: list[str] = []

    for label, statement in (
        ("schemas", "SHOW CREATE ALL SCHEMAS"),
        ("types", "SHOW CREATE ALL TYPES"),
        ("tables", "SHOW CREATE ALL TABLES"),
    ):
        parts.append(_part(label, _rows_as_text(fetch_all(conn, statement))))
        labels.append(label)

    has_triggerdef, has_functiondef = _routine_support(conn)

    if has_triggerdef:
        rows = fetch_all(
            conn,
            """
            SELECT t.tgname AS name, pg_get_triggerdef(t.oid) AS def
            FROM pg_catalog.pg_trigger t
            WHERE NOT t.tgisinternal
            ORDER BY 1
            """,
        )
        parts.append(_part("triggers", _rows_as_text(rows)))
        labels.append("triggers")

    if has_functiondef:
        like = " OR ".join(["n.nspname LIKE %s"] * len(schema_prefixes))
        rows = fetch_all(
            conn,
            f"""
            SELECT p.proname AS name, pg_get_functiondef(p.oid) AS def
            FROM pg_catalog.pg_proc p
            JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
            WHERE {like}
            ORDER BY 1
            """,  # noqa: S608 - `like` is a fixed number of placeholders, never data
            list(schema_prefixes),
        )
        parts.append(_part("routines", _rows_as_text(rows)))
        labels.append("routines")

    grade = "strong" if (has_triggerdef and has_functiondef) else "weak"
    digest = hashlib.sha256(_PART_SEPARATOR.join(parts)).digest()
    return Attestation(digest=digest, grade=grade, parts=tuple(labels))


def stable_fingerprint(
    conn: psycopg.Connection[Any], *, schema_prefixes: tuple[str, ...]
) -> Attestation:
    """Compute the fingerprint twice and refuse if the two disagree.

    Day-1 verification item 4 in research/06-build/schema-migrations.md §11: the docs
    guarantee CREATE-before-ALTER ordering and nothing else, so stability is asserted
    rather than assumed. This is cheap and it runs on every attestation, not only in CI.
    """
    first = fingerprint(conn, schema_prefixes=schema_prefixes)
    second = fingerprint(conn, schema_prefixes=schema_prefixes)
    if first.digest != second.digest:
        raise AttestationDrift(
            "the schema fingerprint is not stable across two consecutive computations "
            f"({first.digest.hex()[:16]}… then {second.digest.hex()[:16]}…). The "
            "normalisation is insufficient for this CockroachDB version; a fingerprint "
            "that flickers cannot be used as a drift alarm."
        )
    return first


def chain_head(conn: psycopg.Connection[Any]) -> ChainHead:
    """Return the newest attestation row.

    Raises:
        AttestationDrift: if the chain is empty. Bootstrap writes the genesis row, so an
            empty chain means the row was deleted.
    """
    rows = fetch_all(
        conn,
        """
        SELECT ordinal, fingerprint, attestation_grade, kind, version
        FROM trappoint.schema_attestation
        ORDER BY ordinal DESC
        LIMIT 1
        """,
    )
    if not rows:
        raise AttestationDrift(
            "trappoint.schema_attestation is empty. Bootstrap writes an immutable "
            "genesis row, so an empty chain means it was deleted."
        )
    row = rows[0]
    return ChainHead(
        ordinal=int(row["ordinal"]),
        fingerprint=bytes(row["fingerprint"]),
        grade=str(row["attestation_grade"]),
        kind=str(row["kind"]),
        version=str(row["version"]),
    )


def append(
    conn: psycopg.Connection[Any],
    *,
    kind: str,
    tree: str,
    version: str,
    attestation: Attestation,
    applied_by: str,
    file_sha256: bytes | None = None,
    job_ids: tuple[str, ...] = (),
    incident_id: str | None = None,
) -> int:
    """Append one attestation row, citing the current head.

    The append is a compare-and-swap and it is meant to be seen as one. The new row
    carries ``prev_ordinal = head.ordinal``; ``attestation_chain_linear`` is
    ``UNIQUE (prev_ordinal)``, so two migrators that both read head ``N`` and both try
    to write ``N+1`` produce one commit and one ``23505``. The loser is not retried:
    it read a stale head, and re-reading it silently would hide the fact that two
    migration streams were running.

    Returns:
        The ordinal written.
    """
    head = chain_head(conn)

    def body(c: psycopg.Connection[Any]) -> int:
        c.execute(
            """
            INSERT INTO trappoint.schema_attestation
                (ordinal, prev_ordinal, kind, tree, version, file_sha256,
                 fingerprint, prev_fingerprint, attestation_grade, job_ids,
                 applied_by, incident_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                head.ordinal + 1,
                head.ordinal,
                kind,
                tree,
                version,
                file_sha256,
                attestation.digest,
                head.fingerprint,
                attestation.grade,
                list(job_ids),
                applied_by,
                incident_id,
            ),
        )
        return head.ordinal + 1

    return in_txn(conn, body)


def verify_chain(conn: psycopg.Connection[Any]) -> list[str]:
    """Walk the attestation chain and report every inconsistency found.

    Three checks, and each corresponds to a way the ledger could have been edited:

    * ``ordinal`` starts at 0 and is dense — a gap means a row was **deleted**, which is
      the whole reason the chain is CAS-sequenced rather than sequence-numbered;
    * each row's ``prev_fingerprint`` equals its predecessor's ``fingerprint`` — a
      mismatch means a row was **rewritten**;
    * the genesis row is the genesis value.

    Returns an empty list when the chain is intact. Findings are returned rather than
    raised so ``status`` can print all of them instead of the first.
    """
    rows = fetch_all(
        conn,
        """
        SELECT ordinal, prev_ordinal, fingerprint, prev_fingerprint, kind, version
        FROM trappoint.schema_attestation
        ORDER BY ordinal ASC
        """,
    )
    findings: list[str] = []
    if not rows:
        return ["the attestation chain is empty; the genesis row was deleted"]

    first = rows[0]
    if int(first["ordinal"]) != 0:
        findings.append(f"the chain starts at ordinal {first['ordinal']}, not 0")
    elif bytes(first["prev_fingerprint"]) != GENESIS_FINGERPRINT:
        findings.append("the genesis row does not carry the genesis fingerprint")

    for previous, current in pairwise(rows):
        expected = int(previous["ordinal"]) + 1
        if int(current["ordinal"]) != expected:
            # One finding per accusation. A gap ENTAILS a fingerprint mismatch across the
            # hole, so reporting both would be reporting one fact twice and would make
            # "a row was rewritten" — a different and more serious claim — appear in a
            # report where nothing was rewritten.
            findings.append(
                f"gap: ordinal {previous['ordinal']} is followed by {current['ordinal']}; "
                "the chain is dense by CHECK, so a gap means a row was deleted"
            )
            continue
        if bytes(current["prev_fingerprint"]) != bytes(previous["fingerprint"]):
            findings.append(
                f"ordinal {current['ordinal']} cites a predecessor fingerprint that is not "
                f"ordinal {previous['ordinal']}'s; a row was rewritten"
            )
    return findings
