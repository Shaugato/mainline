# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The append: one SERIALIZABLE transaction, a dense ``seq``, and the only retryable 23505.

This module is where "a gap MEANS tampering" is either true or false.

**CU-2, stated once and implemented literally.** ``seq`` is derived *inside* the appending
transaction as ``COALESCE(max(seq), -1) + 1``. ``CREATE SEQUENCE``, ``nextval()``,
``SERIAL`` and ``unique_rowid()`` are banned repository-wide, and the ban is load-bearing
rather than stylistic because ``CREATE SEQUENCE`` **succeeds** on the target cluster
(``docs/adr/0002`` F4) — nothing but ``trappoint migrate lint`` stands between this schema
and a ledger whose gaps mean nothing. Sequence increments survive rollback; CAS
derivations do not. That single difference is what lets verifier check 9 treat a gap as
evidence.

**The retry predicate matches on CONSTRAINT NAME, never on SQLSTATE.** Four constraints
on ``mainline.ledger_leaf`` raise ``23505`` and they are four different facts:

===========================  ==============================================  ==========
constraint                   what it means                                   this loop
===========================  ==============================================  ==========
``ledger_leaf_pkey``         somebody else took this position                 retry
``ledger_linear``            somebody else claimed this predecessor (A6)      retry
``ledger_leaf_entry_unique`` this entry was already sequenced ("already       escape
                             done") — a different fact, and one that must
                             reach the caller
``ledger_node_pkey``         a settled interior hash was written twice with   escape
                             different content
===========================  ==============================================  ==========

Retrying the third would turn a detected duplicate into a silent one; retrying anything
outside the first two would make the one legitimate retry in this repository a **laundry
for real refusals**, which is a far worse defect than the contention it absorbs. The loop
is bounded at eight attempts, and
``tests/test_append_unit.py::test_other_unique_violations_escape_the_cas_loop`` is the
assertion that keeps it honest.

**A retry that cannot name the constraint does not happen.** CockroachDB's population of
the pgwire constraint field is version-dependent, so :func:`constraint_name_of` falls back
to parsing the driver's message — and when *neither* yields a name the exception
propagates. An unnamed retry is a blanket retry wearing a specific loop's clothes.

**``40001`` is retried with capped exponential backoff and full jitter**, per the kernel's
taxonomy in ``spec/errors.md``. The loop is hand-written because
``tenacity``/``backoff``/``retrying`` are forbidden repository-wide
(``.importlinter`` contract 4): a decorator that retries "on exception" cannot make the
distinction the table above turns on.

**The signer is called INSIDE the transaction, and the cost is stated rather than hidden.**
The checkpoint body is a function of the tree size and root this transaction read, so it
cannot be built before the head is known. A retry therefore re-signs — correctly, because
the body differs — and that is one reason the attempt bound is eight rather than sixty.

**What this module does not own.** RFC 6962 hashing, the link-chain step and the C2SP
checkpoint body all live in ``packages/trappoint-ledger`` and are consumed through
:class:`LedgerAlgebra`. They are **not** re-implemented here: a second implementation of
an evidentiary hash is a second thing that can drift, and the custody domain already pays
a CI equality check to keep one canonicaliser from drifting from its vendored copy.
:func:`default_algebra` binds the real package lazily and raises
:class:`LedgerAlgebraUnavailable` naming the exact missing symbol.
"""

from __future__ import annotations

import importlib
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .batch import IntakeRow

__all__ = [
    "CAS_RETRYABLE_CONSTRAINTS",
    "GENESIS_LINK_HASH",
    "MAX_CAS_ATTEMPTS",
    "AppendResult",
    "CasExhausted",
    "CheckpointIncomplete",
    "CheckpointInputs",
    "Head",
    "LedgerAlgebra",
    "LedgerAlgebraUnavailable",
    "Signer",
    "TreeDelta",
    "append_batch",
    "constraint_name_of",
    "default_algebra",
    "optional_symbol",
    "read_head",
]

#: CU-1: genesis is 32 zero bytes, not ``NULL``. Under a nullable ``prev_link_hash`` every
#: genesis row would be distinct to ``UNIQUE (site_code, prev_link_hash)`` and the first
#: leaf would be the one position at which a fork was permitted.
GENESIS_LINK_HASH = bytes(32)

#: The ONLY two constraints in the repository on which a ``23505`` is retried (CU-2).
CAS_RETRYABLE_CONSTRAINTS = frozenset({"ledger_leaf_pkey", "ledger_linear"})

#: Named because the test that proves it escapes has to name it too.
IDEMPOTENCE_CONSTRAINT = "ledger_leaf_entry_unique"

#: Eight attempts of capped, fully-jittered backoff is roughly six seconds of contention
#: tolerance. Past that, something is holding a conflicting transaction and the honest
#: answer is to say so — under a lease that is also expiring.
MAX_CAS_ATTEMPTS = 8

_BASE_DELAY_S = 0.02
_CAP_DELAY_S = 1.0

_SHA256_LEN = 32

_DRAND_VALUE = re.compile(r"^[0-9a-f]{64} (?P<round>[0-9]+) [0-9a-f]{64}$")
_NIST_VALUE = re.compile(r"^2\.0 (?P<chain>[0-9]+)\.(?P<pulse>[0-9]+) [0-9a-f]{128}$")
_CONSTRAINT_IN_MESSAGE = re.compile(r'constraint "([^"]+)"')

# ── SQL ────────────────────────────────────────────────────────────────────────────────
# Every statement below is an INSERT or a SELECT. There is no UPDATE and no DELETE
# against any `ledger_*` object anywhere in this package, and
# `tests/test_batch_antijoin.py::test_no_update_against_any_ledger_table` reads these
# module sources and asserts it.

# `ORDER BY seq DESC LIMIT 1` is exactly `COALESCE(max(seq), -1) + 1` with the head's
# link hash fetched by the same read, so the position and the predecessor cannot come
# from two different observations of the table.
READ_HEAD_SQL = """
SELECT seq, link_hash
  FROM mainline.ledger_leaf
 WHERE site_code = %s
 ORDER BY seq DESC
 LIMIT 1
"""

ALREADY_SEQUENCED_SQL = """
SELECT entry_id
  FROM mainline.ledger_leaf
 WHERE site_code = %s
   AND entry_id = ANY(%s)
"""

# THE HONEST COST, STATED. `trappoint_ledger.merkle.tree.MerkleTree` is constructed from
# leaf hashes and has no restore-from-stored-nodes constructor, so extending the tree
# means reading every leaf hash for the site — O(n) bytes and O(n) SHA-256 per checkpoint
# rather than O(log n). At 100k leaves that is a 3.2 MB read and roughly 50 ms of hashing
# every fifteen seconds, which is affordable and is not free.
#
# The narrower read this replaced — the ~log2(n) perfect-subtree "fringe" out of
# `mainline.ledger_node` — is the right long-term shape, and it needs exactly one thing
# from the substrate package: a `MerkleTree.from_nodes(fringe)` constructor. That is
# recorded as a cross-domain note rather than implemented here, because re-deriving RFC
# 6962 in the sequencer to save a read would put a second implementation of an
# evidentiary hash in the repository, which costs far more than the read does.
READ_LEAF_HASHES_SQL = """
SELECT leaf_hash
  FROM mainline.ledger_leaf
 WHERE site_code = %s
 ORDER BY seq
"""

INSERT_LEAF_SQL = """
INSERT INTO mainline.ledger_leaf
    (site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

INSERT_NODE_SQL = """
INSERT INTO mainline.ledger_node (site_code, level, idx, hash)
VALUES (%s, %s, %s, %s)
"""

INSERT_CHECKPOINT_SQL = """
INSERT INTO mainline.ledger_checkpoint
    (site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


# ── Failures ───────────────────────────────────────────────────────────────────────────


class CasExhausted(RuntimeError):
    """Eight CAS attempts all lost. The batch was NOT appended.

    This is a legitimate outcome under sustained contention and it is reported rather
    than absorbed. The next EventBridge tick re-selects the same rows by anti-join, so
    nothing is lost — but a site that reaches this repeatedly has two sequencers running,
    which is a fact an operator needs rather than one a retry should hide.
    """


class LedgerAlgebraUnavailable(RuntimeError):
    """``trappoint_ledger`` is absent or does not expose the symbol this module needs."""


class CheckpointIncomplete(ValueError):
    """The checkpoint inputs are malformed or a beacon is missing.

    A checkpoint without a beacon has no lower time bound, and a checkpoint whose
    extension lines do not parse is a note a third-party verifier will reject. Both are
    refused before the transaction opens rather than after the leaves are written.
    """


# ── The interface this module requires of ``trappoint_ledger`` ─────────────────────────


@runtime_checkable
class Signer(Protocol):
    """Structural mirror of ``trappoint_ledger.signer.Signer``.

    Declared structurally rather than imported so that this module carries no import-time
    dependency on a sibling distribution. ``LocalP256Signer`` and ``KmsSigner`` both
    satisfy it without knowing this file exists.
    """

    def sign(self, body: bytes) -> bytes:
        """Return the ECDSA P-256 / SHA-256 signature over *body*, DER encoded (CU-3)."""
        ...

    def public_key_spki_der(self) -> bytes:
        """Return the DER SPKI public key, from which the C2SP ``0x02`` key ID is taken."""
        ...


@dataclass(frozen=True, slots=True)
class TreeDelta:
    """What an incremental RFC 6962 append produced."""

    root_hash: bytes
    """The Merkle Tree Hash at the NEW tree size. At a non-power-of-two size this is an
    ephemeral value that is not a perfect-subtree node; it is committed to by the
    checkpoint and is deliberately not stored in ``ledger_node``."""

    nodes: tuple[tuple[int, int, bytes], ...]
    """``(level, idx, hash)`` rows to insert — and ONLY nodes that are now COMPLETE.

    A perfect-subtree node never changes once written, so restricting the delta to
    completed subtrees is what lets ``mainline.ledger_node`` be append-only with a
    primary key on ``(site_code, level, idx)``. An implementation that emitted partial
    interior hashes would collide on ``ledger_node_pkey`` the moment the subtree filled,
    and that collision escapes the CAS loop on purpose — a settled hash written twice
    with different content is not contention."""


class LedgerAlgebra(Protocol):
    """The RFC 6962 / C2SP operations the sequencer consumes and does not implement.

    Bound to ``packages/trappoint-ledger`` by :func:`default_algebra`:

    * ``chain.link_hash(prev_link_hash, leaf_hash) -> bytes`` — one step of the link
      chain. The sequencer continues a chain from an existing head, so the
      genesis-anchored ``chain.recompute_chain(leaves)`` cannot stand in for it.
    * ``merkle.tree.MerkleTree(existing_leaf_hashes).extend(new_leaf_hashes)`` →
      ``BatchAppendResult(root, created_nodes, …)``. ``created_nodes`` was verified
      against the shipped implementation to contain each completed interior node exactly
      once and never a repeat across successive extends — which is what makes
      ``mainline.ledger_node`` append-only with a primary key on ``(site_code, level,
      idx)`` rather than a table that would need an ``UPDATE`` grant.
    * ``checkpoint.build_body(origin, tree_size, root_hash, extensions) -> str`` — the
      C2SP ``tlog-checkpoint`` note text.
    """

    def link_hash(self, prev_link_hash: bytes, leaf_hash: bytes) -> bytes:
        """``SHA-256(prev_link_hash ‖ leaf_hash)``."""
        ...

    def extend(
        self, existing_leaf_hashes: Sequence[bytes], new_leaf_hashes: Sequence[bytes]
    ) -> TreeDelta:
        """Append *new_leaf_hashes* to the tree over *existing_leaf_hashes*."""
        ...

    def checkpoint_body(
        self,
        origin: str,
        tree_size: int,
        root_hash: bytes,
        extensions: Sequence[tuple[str, str]],
    ) -> str:
        """Assemble the C2SP ``tlog-checkpoint`` note text (the signed bytes)."""
        ...


@dataclass(frozen=True, slots=True)
class _TrappointLedgerAlgebra:
    """Adapter onto ``trappoint_ledger``. Constructed only by :func:`default_algebra`."""

    _link_hash: Callable[[bytes, bytes], bytes]
    _merkle_tree: Callable[[Sequence[bytes]], Any]
    _build_body: Callable[[str, int, bytes, Sequence[tuple[str, str]]], str]

    def link_hash(self, prev_link_hash: bytes, leaf_hash: bytes) -> bytes:
        return self._link_hash(prev_link_hash, leaf_hash)

    def extend(
        self, existing_leaf_hashes: Sequence[bytes], new_leaf_hashes: Sequence[bytes]
    ) -> TreeDelta:
        batch = self._merkle_tree(list(existing_leaf_hashes)).extend(list(new_leaf_hashes))
        return TreeDelta(
            root_hash=bytes(batch.root),
            nodes=tuple(
                (int(node.coord.level), int(node.coord.index), bytes(node.digest))
                for node in batch.created_nodes
            ),
        )

    def checkpoint_body(
        self,
        origin: str,
        tree_size: int,
        root_hash: bytes,
        extensions: Sequence[tuple[str, str]],
    ) -> str:
        return self._build_body(origin, tree_size, root_hash, extensions)


def default_algebra() -> LedgerAlgebra:
    """Bind the real ``trappoint_ledger`` implementation.

    Imported inside the function so that this module remains importable — and its SQL and
    its CAS classification remain testable — on a checkout where
    ``packages/trappoint-ledger`` has not landed, or has landed only in part. Nothing
    degrades silently: the failure is a named exception saying which symbol is missing.

    Raises:
        LedgerAlgebraUnavailable: if the package or any required symbol is absent.
    """
    try:
        from trappoint_ledger.chain import link_hash
        from trappoint_ledger.merkle.tree import MerkleTree
    except ImportError as exc:
        raise LedgerAlgebraUnavailable(
            "trappoint_ledger.chain.link_hash and trappoint_ledger.merkle.tree.MerkleTree "
            "are required and were not importable, so the sequencer has no link-chain step "
            "and no RFC 6962 tree. They are NOT re-implemented here on purpose: a second "
            f"implementation of an evidentiary hash is a second thing that can drift. {exc}"
        ) from exc
    # `importlib` rather than `from trappoint_ledger.checkpoint import build_body`, and the
    # asymmetry with the two imports above is deliberate. `chain` and `merkle.tree` are in
    # the source tree, so a static import of them is checked. `checkpoint` is not yet: a
    # static import of a module absent from the source tree makes the type checker fall
    # back to the untyped installed distribution and report an error that a `type: ignore`
    # would have to carry — and that ignore would itself become an error the day the module
    # lands, under `warn_unused_ignores`. A dynamic resolution is correct under both states
    # and says plainly that this binding is late.
    build_body = optional_symbol("trappoint_ledger.checkpoint", "build_body")
    if build_body is None:
        raise LedgerAlgebraUnavailable(
            "trappoint_ledger.checkpoint.build_body is required and was not importable, so "
            "no C2SP tlog-checkpoint note text can be assembled. spec/wire/checkpoint.md "
            "v1.0 is frozen and is the interface a third-party verifier implements from; "
            "assembling the note anywhere but in the one place that owns the format is how "
            "two spellings of a signed object come to exist."
        )
    return _TrappointLedgerAlgebra(link_hash, MerkleTree, build_body)


# ── Inputs and outputs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CheckpointInputs:
    """Everything the checkpoint note needs that is not a function of the tree.

    The extension lines are validated here, before any transaction opens, because
    ``spec/wire/checkpoint.md`` §4 makes their shape normative and a malformed one
    produces a note that a third-party verifier rejects — discovered by the stranger
    rather than by us.
    """

    origin: str
    payload_ver: int
    canon_src_sha256: bytes
    drand: str
    """The ``drand:`` extension VALUE: ``<64 hex chain hash> <round> <64 hex randomness>``."""
    nist: str
    """The ``nist:`` extension VALUE: ``2.0 <chainIndex>.<pulseIndex> <128 hex output>``."""

    def __post_init__(self) -> None:
        """Refuse a checkpoint that could not be verified by a stranger."""
        if not self.origin or " " in self.origin or "+" in self.origin:
            raise CheckpointIncomplete(
                f"origin {self.origin!r} is empty or contains a space or '+'; "
                "spec/wire/checkpoint.md §3 forbids both, and §5.2's vkey form parses on "
                "the first two '+' characters"
            )
        if self.payload_ver < 1:
            raise CheckpointIncomplete(f"payload_ver must be >= 1, got {self.payload_ver}")
        if len(self.canon_src_sha256) != _SHA256_LEN:
            raise CheckpointIncomplete(
                f"canon_src_sha256 is {len(self.canon_src_sha256)} bytes, not {_SHA256_LEN}"
            )
        if _DRAND_VALUE.match(self.drand) is None:
            raise CheckpointIncomplete(
                f"the drand: extension value {self.drand!r} does not match "
                "'<64 hex chain hash> <round> <64 hex randomness>' "
                "(spec/wire/checkpoint.md §4.2)"
            )
        if _NIST_VALUE.match(self.nist) is None:
            raise CheckpointIncomplete(
                f"the nist: extension value {self.nist!r} does not match "
                "'2.0 <chainIndex>.<pulseIndex> <128 hex outputValue>' "
                "(spec/wire/checkpoint.md §4.3)"
            )

    def extensions(self) -> tuple[tuple[str, str], ...]:
        """Return the three extension lines, in the order §4 makes normative."""
        return (
            ("canon", f"{self.payload_ver} {self.canon_src_sha256.hex()}"),
            ("drand", self.drand),
            ("nist", self.nist),
        )

    def beacon_json(self) -> dict[str, Any]:
        """Return the parsed beacon, for ``ledger_checkpoint.beacon JSONB``.

        Derived from the same two validated strings that produce the extension lines, so
        the column and the signed note cannot disagree about which round was quoted.
        """
        drand_chain, drand_round, drand_randomness = self.drand.split(" ")
        _version, indices, output = self.nist.split(" ")
        chain_index, pulse_index = indices.split(".")
        return {
            "drand": {
                "chain_hash": drand_chain,
                "round": int(drand_round),
                "randomness": drand_randomness,
            },
            "nist": {
                "version": "2.0",
                "chain_index": int(chain_index),
                "pulse_index": int(pulse_index),
                "output_value": output,
            },
        }


@dataclass(frozen=True, slots=True)
class Head:
    """The log head as read inside the appending transaction."""

    tree_size: int
    """``max(seq) + 1``: both the number of leaves and the ``seq`` of the next one."""
    link_hash: bytes
    """The head leaf's ``link_hash``, or :data:`GENESIS_LINK_HASH` for an empty log."""


@dataclass(frozen=True, slots=True)
class AppendResult:
    """What one invocation of :func:`append_batch` actually did."""

    site_code: str
    batch_id: UUID
    first_seq: int
    appended: int
    already_sequenced: int
    tree_size: int
    root_hash: bytes | None
    checkpoint_body: str | None
    log_sig: bytes | None
    attempts: int
    nodes_written: int

    @property
    def checkpoint_written(self) -> bool:
        """Whether this invocation signed and recorded a checkpoint."""
        return self.checkpoint_body is not None


# ── Pure helpers ───────────────────────────────────────────────────────────────────────


def optional_symbol(module_name: str, attribute: str) -> Any:
    """Resolve ``module_name.attribute`` dynamically, or return ``None`` if it is absent.

    Used for the bindings onto ``packages/trappoint-ledger`` modules that had not landed
    when this package was written. It returns ``None`` rather than raising so that each
    caller can say, in its own words, what the missing symbol was for — a bare
    ``ImportError`` from three different call sites is three chances to guess wrong about
    which capability the deployment is missing.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    return getattr(module, attribute, None)


def constraint_name_of(exc: psycopg.Error) -> str | None:
    """Return the constraint a database error names, or ``None`` when it names none.

    ``exc.diag.constraint_name`` is the pgwire field and is preferred. CockroachDB's
    population of that field is version-dependent and was not verified for every
    constraint class on v26.2.5, so the driver's own message is parsed as a fallback —
    ``duplicate key value violates unique constraint "ledger_leaf_pkey"``.

    A ``None`` return is consequential: :func:`append_batch` does **not** retry an error
    it cannot name. A retry keyed on an absent name is a blanket retry, and blanket
    retries are exactly what CU-2 forbids.
    """
    diag = exc.diag
    name = getattr(diag, "constraint_name", None)
    if name:
        return str(name)
    match = _CONSTRAINT_IN_MESSAGE.search(str(exc))
    return match.group(1) if match is not None else None


def _full_jitter(attempt: int, rng: random.Random) -> float:
    """Capped exponential backoff with FULL jitter: ``U(0, min(cap, base·2^n))``.

    Full rather than equal jitter because the herd being dispersed is N sequencer Lambdas
    invoked by the same EventBridge tick, and only full jitter spreads a synchronised
    herd on the *first* retry.
    """
    ceiling = min(_CAP_DELAY_S, _BASE_DELAY_S * (2**attempt))
    return rng.uniform(0.0, ceiling)


# ── Reads ──────────────────────────────────────────────────────────────────────────────


def read_head(conn: psycopg.Connection[Any], *, site_code: str) -> Head:
    """Read ``(max(seq) + 1, head link_hash)`` for *site_code*.

    MUST be called inside the appending transaction. Under ``SERIALIZABLE`` this read is
    what a racing appender's commit invalidates, which is how a fork becomes a ``40001``
    or a ``23505`` rather than a second branch.
    """
    with conn.cursor() as cur:
        cur.execute(READ_HEAD_SQL, (site_code,))
        row = cur.fetchone()
    if row is None:
        return Head(tree_size=0, link_hash=GENESIS_LINK_HASH)
    seq, link_hash = row
    return Head(tree_size=int(seq) + 1, link_hash=bytes(link_hash))


def _already_sequenced(
    conn: psycopg.Connection[Any], *, site_code: str, entry_ids: Sequence[UUID]
) -> set[UUID]:
    """Which of *entry_ids* already have a leaf.

    Re-run on every CAS attempt, not once before the loop. That is what makes a replay a
    genuine no-op and what keeps ``ledger_leaf_entry_unique`` outside the retry set: by
    the time an attempt inserts, the entries it is inserting were observed unsequenced in
    the same transaction, so a ``23505`` on that constraint means something the loop must
    not paper over.
    """
    if not entry_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(ALREADY_SEQUENCED_SQL, (site_code, list(entry_ids)))
        return {row[0] for row in cur.fetchall()}


def _existing_leaf_hashes(
    conn: psycopg.Connection[Any], *, site_code: str, expected: int
) -> list[bytes]:
    """Read every leaf hash for *site_code*, in ``seq`` order.

    The count is checked against the head this transaction already read. A short read
    would mean the tree is being extended over fewer leaves than the log contains, which
    produces a root that commits to a *different log* — and it would be discovered at
    verification time, years later, by the person least able to do anything about it.
    """
    with conn.cursor() as cur:
        cur.execute(READ_LEAF_HASHES_SQL, (site_code,))
        hashes = [bytes(row[0]) for row in cur.fetchall()]
    if len(hashes) != expected:
        raise LookupError(
            f"site {site_code!r}: the head says the tree has {expected} leaves but "
            f"{len(hashes)} leaf hashes were read. The sequence is not dense, which under "
            "CU-2 means the ledger was tampered with — refusing to extend a tree over a "
            "prefix that is missing rows, because the root that resulted would commit to "
            "a log nobody can reproduce."
        )
    return hashes


# ── The append ─────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _AttemptContext:
    """The arguments one CAS attempt needs, gathered so the attempt body stays readable."""

    site_code: str
    rows: tuple[IntakeRow, ...]
    signer: Signer
    checkpoint: CheckpointInputs
    algebra: LedgerAlgebra
    batch_id: UUID
    attempt: int = field(default=0)


def _attempt(conn: psycopg.Connection[Any], ctx: _AttemptContext) -> AppendResult:
    """One transaction's worth of work. Called inside ``conn.transaction()``."""
    head = read_head(conn, site_code=ctx.site_code)
    done = _already_sequenced(
        conn, site_code=ctx.site_code, entry_ids=[row.entry_id for row in ctx.rows]
    )
    fresh = tuple(row for row in ctx.rows if row.entry_id not in done)

    if not fresh:
        # A replay writes NOTHING, including no checkpoint. `ledger_checkpoint_pkey` is
        # `(site_code, tree_size)`, so a second checkpoint at an unchanged size is either
        # a duplicate or attack A7 (checkpoint_swap) — and this path must not be the code
        # that decides which. Idempotence is thereby a no-op rather than a conflict.
        return AppendResult(
            site_code=ctx.site_code,
            batch_id=ctx.batch_id,
            first_seq=head.tree_size,
            appended=0,
            already_sequenced=len(done),
            tree_size=head.tree_size,
            root_hash=None,
            checkpoint_body=None,
            log_sig=None,
            attempts=ctx.attempt + 1,
            nodes_written=0,
        )

    leaf_hashes = [row.leaf_hash for row in fresh]
    prev = head.link_hash
    leaf_rows: list[tuple[Any, ...]] = []
    for offset, row in enumerate(fresh):
        link = ctx.algebra.link_hash(prev, row.leaf_hash)
        leaf_rows.append(
            (
                ctx.site_code,
                head.tree_size + offset,
                row.entry_id,
                row.leaf_hash,
                prev,
                link,
                ctx.batch_id,
            )
        )
        prev = link

    existing = _existing_leaf_hashes(conn, site_code=ctx.site_code, expected=head.tree_size)
    delta = ctx.algebra.extend(existing, leaf_hashes)
    new_tree_size = head.tree_size + len(fresh)

    body = ctx.algebra.checkpoint_body(
        ctx.checkpoint.origin, new_tree_size, delta.root_hash, ctx.checkpoint.extensions()
    )
    log_sig = ctx.signer.sign(body.encode("utf-8"))

    node_rows = [
        (ctx.site_code, level, idx, node_hash) for level, idx, node_hash in sorted(delta.nodes)
    ]
    with conn.cursor() as cur:
        cur.executemany(INSERT_LEAF_SQL, leaf_rows)
        if node_rows:
            cur.executemany(INSERT_NODE_SQL, node_rows)
        cur.execute(
            INSERT_CHECKPOINT_SQL,
            (
                ctx.site_code,
                new_tree_size,
                delta.root_hash,
                body,
                Jsonb(ctx.checkpoint.beacon_json()),
                log_sig,
                ctx.checkpoint.canon_src_sha256,
            ),
        )

    return AppendResult(
        site_code=ctx.site_code,
        batch_id=ctx.batch_id,
        first_seq=head.tree_size,
        appended=len(fresh),
        already_sequenced=len(done),
        tree_size=new_tree_size,
        root_hash=delta.root_hash,
        checkpoint_body=body,
        log_sig=log_sig,
        attempts=ctx.attempt + 1,
        nodes_written=len(node_rows),
    )


def append_batch(
    conn: psycopg.Connection[Any],
    *,
    site_code: str,
    rows: Sequence[IntakeRow],
    signer: Signer,
    checkpoint: CheckpointInputs,
    algebra: LedgerAlgebra | None = None,
    batch_id: UUID | None = None,
    max_attempts: int = MAX_CAS_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> AppendResult:
    """Append *rows* as leaves, extend the tree, and sign a checkpoint — atomically.

    Args:
        conn: an open connection whose ``isolation_level`` is ``SERIALIZABLE``. The level
            is the caller's to set and ``handler.connect`` sets it explicitly rather than
            inheriting a pool default (``spec/errors.md`` §2.1).
        site_code: the log partition.
        rows: the batch, in the total order :func:`~mainline_sequencer.batch.unsequenced`
            produced. Rows already sequenced are dropped inside the transaction, so
            replaying a batch is a no-op rather than a conflict.
        signer: the log key. Called inside the transaction — see the module docstring.
        checkpoint: origin, canonicaliser pin and the two beacon extension values.
        algebra: the RFC 6962 / C2SP operations. Defaults to :func:`default_algebra`,
            which binds ``trappoint_ledger``; tests inject a double.
        batch_id: forensic tag recorded on every leaf. Commits to nothing and orders
            nothing; it exists so a run can be reconstructed from the ledger.
        max_attempts: the CAS bound. Eight, per CU-2.
        sleep: injected for tests, so the backoff is asserted rather than waited out.
        rng: injected for tests, so the jitter is reproducible.

    Returns:
        What was done, including ``attempts`` and whether a checkpoint was written.

    Raises:
        CasExhausted: every attempt lost. Nothing was appended.
        psycopg.errors.UniqueViolation: on any constraint outside
            :data:`CAS_RETRYABLE_CONSTRAINTS`, and on any unique violation whose
            constraint cannot be named.
        psycopg.Error: every other database refusal, on the first attempt, unretried.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")
    ctx = _AttemptContext(
        site_code=site_code,
        rows=tuple(rows),
        signer=signer,
        checkpoint=checkpoint,
        algebra=algebra if algebra is not None else default_algebra(),
        batch_id=batch_id if batch_id is not None else uuid4(),
    )
    jitter = rng if rng is not None else random.SystemRandom()
    last: psycopg.Error | None = None

    for attempt in range(max_attempts):
        ctx.attempt = attempt
        try:
            with conn.transaction():
                return _attempt(conn, ctx)
        except psycopg.errors.UniqueViolation as exc:
            name = constraint_name_of(exc)
            if name not in CAS_RETRYABLE_CONSTRAINTS:
                # `ledger_leaf_entry_unique` (already done), `ledger_node_pkey` (a
                # settled hash rewritten), an unnameable violation — all escape. CU-2:
                # the one legitimate retry must not become a laundry for real refusals.
                raise
            last = exc
        except psycopg.errors.SerializationFailure as exc:
            # 40001 is the kernel's one retryable code and it is retried here for the
            # same reason: the transaction is UNDECIDED, so re-running it decides it.
            last = exc
        if attempt + 1 < max_attempts:
            sleep(_full_jitter(attempt, jitter))

    raise CasExhausted(
        f"{max_attempts} CAS attempts against site {site_code!r} all lost; the batch of "
        f"{len(ctx.rows)} row(s) was NOT appended. The last refusal was "
        f"{type(last).__name__}"
        + (f" on constraint {constraint_name_of(last)!r}" if last is not None else "")
        + ". The rows remain unsequenced and the next invocation re-selects them by "
        "anti-join, so nothing is lost — but a site that reaches this repeatedly has two "
        "sequencers running, which the lease is meant to prevent and which "
        "ledger_leaf_pkey and ledger_linear are what actually stop."
    )
