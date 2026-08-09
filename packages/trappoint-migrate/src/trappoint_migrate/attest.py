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
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any, Protocol, runtime_checkable

import psycopg

from .bootstrap import GENESIS_FINGERPRINT
from .db import fetch_all, in_txn
from .errors import AttestationDrift
from .sqltext import collapse_whitespace

__all__ = [
    "SINK_FAILURES",
    "Attestation",
    "ChainHead",
    "LedgerSink",
    "NullLedgerSink",
    "append",
    "chain_head",
    "default_sink",
    "fingerprint",
    "set_default_sink",
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


@runtime_checkable
class LedgerSink(Protocol):
    """The seam between the migration runner and the custody ledger.

    A schema change is a custody event. The custody domain wants every one of them —
    every applied migration, every drift alarm, every ``force`` under an incident — in
    the MAINLINE ledger, hashed into the same chain as everything else. But the runner
    must not import the custody package: ``trappoint-migrate`` is Apache-2.0 substrate
    that a second vertical forks, and the ledger is FSL-1.1 vertical code. An import in
    that direction would make the substrate depend on the thing it exists to be
    independent of, and ``.importlinter``'s layering contract refuses it.

    So the direction is inverted. This is a :class:`typing.Protocol` with one method,
    the default implementation does nothing, and the custody lead plugs in a real
    recorder with :func:`set_default_sink` — **without editing this package**.

    Contract, and each clause is load-bearing:

    * ``emit`` is called **after** the attestation row is committed, never before. The
      chain is the record of last resort; a sink that ran first could publish a schema
      change that then failed to commit.
    * ``emit`` **must not raise.** A sink that throws would turn a successful migration
      into a failed one and, worse, into a failed one whose schema had already changed.
      :class:`NullLedgerSink` documents this by doing nothing at all;
      :func:`_emit_safely` enforces it for third-party sinks.
    * ``payload`` is JSON-shaped: str/int/bool/None, lists and dicts thereof. Bytes are
      hex-encoded by the caller, because a ledger entry has to survive a JSON round trip.
    """

    def emit(self, kind: str, subject_id: str, payload: dict[str, Any]) -> None:
        """Record one custody-relevant event. Must not raise; see the class docstring."""
        ...


@dataclass(slots=True)
class NullLedgerSink:
    """The default sink: it records what it was told, in memory, and never raises.

    Not a no-op that discards — a no-op that *remembers*. The difference matters in a
    test: ``assert sink.events == [...]`` proves the runner emitted what it claimed to,
    which is exactly the assertion a custody integration needs before it swaps a real
    sink in. In production nothing reads ``events`` and the list stays bounded by the
    number of migrations in one process's lifetime.
    """

    events: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def emit(self, kind: str, subject_id: str, payload: dict[str, Any]) -> None:
        """Append the event. Never raises, by construction."""
        self.events.append((kind, subject_id, dict(payload)))


_DEFAULT_SINK: LedgerSink = NullLedgerSink()


def default_sink() -> LedgerSink:
    """Return the sink :func:`append` uses when a caller passes none."""
    return _DEFAULT_SINK


def set_default_sink(sink: LedgerSink) -> LedgerSink:
    """Install *sink* as the process-wide default, returning the one it replaced.

    Process-wide because the runner is a command-line tool: there is one migration stream
    per process, and threading a sink through ``cli`` → ``runner`` → ``attest`` as an
    argument would put a custody concern in three signatures that have no other reason to
    mention it. Returning the previous sink is what lets a test restore it.
    """
    global _DEFAULT_SINK  # noqa: PLW0603 - one process, one migration stream; see docstring
    previous = _DEFAULT_SINK
    _DEFAULT_SINK = sink
    return previous


#: Sinks that raised, in order, as ``"<kind> <subject_id>: <error>"``. Read by
#: ``trappoint migrate status``, which prints every entry. A sink failure is NOT allowed
#: to fail the migration (see :func:`_emit_safely`) and it is NOT allowed to be silent
#: either — "custody did not receive this event" is itself something custody has to learn.
SINK_FAILURES: list[str] = []


def _emit_safely(sink: LedgerSink, kind: str, subject_id: str, payload: dict[str, Any]) -> None:
    """Call ``sink.emit`` and refuse to let it fail the migration.

    The blanket catch is deliberate and is the only one in this package. The alternative
    is a third-party sink whose bug turns an applied migration into a *reported* failure
    — leaving a schema that did change and a caller who believes it did not, which is
    strictly the worst available outcome. The exception is recorded in
    :data:`SINK_FAILURES`, which ``status`` prints, so the swallow is bounded: the
    migration proceeds, and the fact that custody was not told is on the record.
    """
    try:
        sink.emit(kind, subject_id, payload)
    except Exception as exc:  # noqa: BLE001 - a sink must never fail a migration; see docstring
        SINK_FAILURES.append(f"{kind} {subject_id}: {type(exc).__name__}: {exc}")


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
    sink: LedgerSink | None = None,
) -> int:
    """Append one attestation row, citing the current head.

    The append is a compare-and-swap and it is meant to be seen as one. The new row
    carries ``prev_ordinal = head.ordinal``; ``attestation_chain_linear`` is
    ``UNIQUE (prev_ordinal)``, so two migrators that both read head ``N`` and both try
    to write ``N+1`` produce one commit and one ``23505``. The loser is not retried:
    it read a stale head, and re-reading it silently would hide the fact that two
    migration streams were running.

    *sink* receives the same fact after the row commits (see :class:`LedgerSink`).
    Defaulting to :func:`default_sink` rather than to ``None`` means a custody
    integration is installed once, process-wide, instead of being threaded through every
    call site that happens to attest something.

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

    ordinal = in_txn(conn, body)

    # AFTER the commit, never before: the chain is the record of last resort, and a sink
    # that ran first could publish a schema change that then failed to commit.
    _emit_safely(
        sink if sink is not None else _DEFAULT_SINK,
        f"schema_attestation.{kind}",
        f"{tree}/{version}",
        {
            "ordinal": ordinal,
            "prev_ordinal": head.ordinal,
            "kind": kind,
            "tree": tree,
            "version": version,
            "fingerprint": attestation.digest.hex(),
            "prev_fingerprint": head.fingerprint.hex(),
            "attestation_grade": attestation.grade,
            "covers": list(attestation.parts),
            "file_sha256": None if file_sha256 is None else file_sha256.hex(),
            "job_ids": list(job_ids),
            "applied_by": applied_by,
            "incident_id": incident_id,
        },
    )
    return ordinal


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
