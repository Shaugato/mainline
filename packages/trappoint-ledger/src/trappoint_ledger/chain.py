# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The ``link_hash`` chain — the jury-legible half of the ledger, and the CAS the append turns on.

Why a log that already has a Merkle tree also keeps a hash chain, verbatim from
``research/05-architecture/custody-tamper-evidence.md`` §4:

    **Why not a monolithic chain only?** We keep ``link_hash`` too (cheap, one extra SHA
    per leaf). It gives a plain-English courtroom artifact — "entry 41 209 names entry
    41 208" — that survives a jury better than a Merkle path. The Merkle tree is what
    *proves* things; the chain is what *explains* them.

Read that in both directions. The chain explains, and **the chain alone does not
prove**: a rogue DBA who deletes leaf *k*, renumbers ``k+1..n`` and recomputes every
``link_hash`` in one ``UPDATE … FROM generate_series`` leaves a chain that recomputes
perfectly. That is attack **A1**, and only a root that was signed, timestamped and put
beyond our reach before the rewrite catches it. This module is therefore honest about
its own weight: it is the legibility layer and the append-time compare-and-swap, and
:func:`verify_chain` returning no findings is *not* an integrity result on its own.
``packages/trappoint-ledger/tests/test_chain.py`` contains that demonstration as an
executable test rather than as a caveat in prose.

The definitions
---------------
::

    prev_link_hash[0] = 32 zero bytes                          (genesis)
    link_hash[i]      = SHA-256(prev_link_hash[i] || leaf_hash[i])
    prev_link_hash[i] = link_hash[i - 1]                       for i > 0

Note there is no domain separation prefix here, unlike RFC 6962's ``0x00``/``0x01``: the
inputs are two fixed-width 32-byte digests, so the concatenation is unambiguous and a
prefix would buy nothing. The leaf hashes being chained are themselves already
RFC 6962 leaf hashes, ``SHA-256(0x00 || canon_bytes)``, so the leaf/interior confusion
the prefixes exist to prevent cannot arise.

Why ``prev_link_hash`` is a stored column and not merely derivable — decision **CU-1**:
``ledger_leaf`` carries ``prev_link_hash BYTES NOT NULL`` with
``CONSTRAINT ledger_linear UNIQUE (site_code, prev_link_hash)``. Two rows claiming the
same predecessor is a fork, and the constraint makes a fork *physically impossible*
rather than merely detectable. That is the ``UNIQUE (permit_id, prev_seq)``
compare-and-swap idiom of the gate, transplanted: the ledger append is held to the same
refusal depth (primary key, and linearity) as the thing it records. Genesis being 32
explicit zero bytes rather than ``NULL`` is what lets the constraint cover ``seq = 0``
at all, since ``NULL`` values do not collide.

This module imports ``hashlib`` and nothing else.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

#: Width of every digest handled here.
HASH_BYTES: Final = 32

#: ``prev_link_hash`` of ``seq = 0``. Explicit, not ``NULL``, so that
#: ``UNIQUE (site_code, prev_link_hash)`` is load-bearing for the genesis row too.
GENESIS_LINK_HASH: Final = bytes(HASH_BYTES)


class ChainError(Exception):
    """Base class for refusals raised while building or checking a link chain."""


class MalformedHash(ChainError):
    """A value offered as a SHA-256 digest was not 32 bytes."""


class SequenceNotDense(ChainError):
    """``seq`` was not dense ``0..n-1``, which in this ledger means tampering.

    ``CREATE SEQUENCE``, ``SERIAL``, ``nextval()`` and ``unique_rowid()`` are banned
    repository-wide, and the sequencer derives ``seq`` as ``COALESCE(max(seq), -1) + 1``
    inside the transaction that inserts it (decision **CU-2**). No mechanism in the
    system can produce a gap by accident — sequence caching, the classic innocent
    explanation for one, does not exist here. So a gap is not a data-quality problem to
    be tolerated: it is a missing entry, and this is the exception that says so.
    """


def _require_digest(value: bytes, what: str) -> bytes:
    """Return ``value`` if it is a 32-byte digest; raise :class:`MalformedHash` otherwise."""
    if not isinstance(value, bytes | bytearray | memoryview):
        raise MalformedHash(f"{what} must be bytes, got {type(value).__name__}")
    raw = bytes(value)
    if len(raw) != HASH_BYTES:
        raise MalformedHash(f"{what} must be {HASH_BYTES} bytes, got {len(raw)}")
    return raw


def link_hash(prev_link_hash: bytes, leaf_hash: bytes) -> bytes:
    """Return ``SHA-256(prev_link_hash || leaf_hash)`` — one link of the chain."""
    return hashlib.sha256(
        _require_digest(prev_link_hash, "prev_link_hash") + _require_digest(leaf_hash, "leaf_hash")
    ).digest()


def recompute_chain(
    leaf_hashes: Iterable[bytes], *, head: bytes = GENESIS_LINK_HASH
) -> list[bytes]:
    """Return the ``link_hash`` for each leaf, in order, starting from ``head``.

    ``head`` is the chain head the leaves are being appended to — :data:`GENESIS_LINK_HASH`
    when recomputing a whole log from scratch, and the current head when the sequencer
    is deriving the links for one batch. A verifier recomputing a bundle passes neither
    and gets the genesis default, which is the only value it can check.
    """
    current = _require_digest(head, "head")
    links: list[bytes] = []
    for leaf in leaf_hashes:
        current = link_hash(current, leaf)
        links.append(current)
    return links


def chain_links(
    leaf_hashes: Iterable[bytes], *, head: bytes = GENESIS_LINK_HASH
) -> list[tuple[bytes, bytes]]:
    """Return ``(prev_link_hash, link_hash)`` per leaf — the two columns of a ledger row."""
    current = _require_digest(head, "head")
    pairs: list[tuple[bytes, bytes]] = []
    for leaf in leaf_hashes:
        nxt = link_hash(current, leaf)
        pairs.append((current, nxt))
        current = nxt
    return pairs


def chain_head(leaf_hashes: Iterable[bytes], *, head: bytes = GENESIS_LINK_HASH) -> bytes:
    """Return the chain head after appending ``leaf_hashes`` to ``head``."""
    current = _require_digest(head, "head")
    for leaf in leaf_hashes:
        current = link_hash(current, leaf)
    return current


def assert_dense(sequence_numbers: Sequence[int], *, start: int = 0) -> None:
    """Raise :class:`SequenceNotDense` unless ``sequence_numbers`` is exactly ``start..start+n-1``.

    Order matters as well as membership: a set that happens to contain every value but
    arrives out of order is a renumbering (attack **A2**), not a shuffle, because the
    ledger is read in ``seq`` order and written in ``seq`` order.
    """
    for offset, value in enumerate(sequence_numbers):
        expected = start + offset
        if value != expected:
            raise SequenceNotDense(
                f"seq is not dense: position {offset} holds {value}, expected {expected}"
            )


class ChainFault(StrEnum):
    """The distinct ways a link chain can be wrong. Each is a separate finding."""

    NOT_DENSE = "seq_not_dense"
    GENESIS_WRONG = "genesis_prev_link_hash_wrong"
    PREV_MISMATCH = "prev_link_hash_does_not_name_predecessor"
    LINK_MISMATCH = "link_hash_is_not_sha256_of_prev_and_leaf"
    MALFORMED = "malformed_digest"


@dataclass(frozen=True, slots=True)
class LinkedLeaf:
    """One ``ledger_leaf`` row, as far as the chain is concerned."""

    seq: int
    leaf_hash: bytes
    link_hash: bytes
    prev_link_hash: bytes


@dataclass(frozen=True, slots=True)
class ChainFinding:
    """A single, individually reportable defect in a link chain."""

    seq: int
    fault: ChainFault
    detail: str


def verify_chain(leaves: Sequence[LinkedLeaf], *, start: int = 0) -> list[ChainFinding]:
    """Return every defect in ``leaves``; an empty list means the chain recomputes.

    Total by construction: this is verifier code, every byte of its input may have been
    chosen by an adversary, and it reports rather than raises. It also reports **all**
    findings rather than the first, because "entry 41 209 does not name entry 41 208"
    and "entry 41 300's link hash is not the hash of its own contents" are different
    accusations and an operator needs both.

    What a clean result does and does not mean is in this module's docstring: it means
    the chain is internally consistent, which a wholesale rewrite also achieves. Check
    3 (consistency against a previously published root) is what makes it evidence.
    """
    findings: list[ChainFinding] = []
    expected_prev = GENESIS_LINK_HASH

    for offset, leaf in enumerate(leaves):
        expected_seq = start + offset
        if leaf.seq != expected_seq:
            findings.append(
                ChainFinding(
                    seq=leaf.seq,
                    fault=ChainFault.NOT_DENSE,
                    detail=f"position {offset} holds seq {leaf.seq}, expected {expected_seq}",
                )
            )

        try:
            leaf_digest = _require_digest(leaf.leaf_hash, "leaf_hash")
            link_digest = _require_digest(leaf.link_hash, "link_hash")
            prev_digest = _require_digest(leaf.prev_link_hash, "prev_link_hash")
        except MalformedHash as exc:
            findings.append(ChainFinding(seq=leaf.seq, fault=ChainFault.MALFORMED, detail=str(exc)))
            # The chain cannot be continued through a row whose digests are not digests;
            # every later row would be reported against a head we never established.
            return findings

        if offset == 0 and start == 0 and prev_digest != GENESIS_LINK_HASH:
            findings.append(
                ChainFinding(
                    seq=leaf.seq,
                    fault=ChainFault.GENESIS_WRONG,
                    detail=(
                        f"seq 0 must carry 32 zero bytes as prev_link_hash, got {prev_digest.hex()}"
                    ),
                )
            )
        elif offset > 0 and prev_digest != expected_prev:
            findings.append(
                ChainFinding(
                    seq=leaf.seq,
                    fault=ChainFault.PREV_MISMATCH,
                    detail=(
                        f"prev_link_hash {prev_digest.hex()} does not name the preceding "
                        f"link_hash {expected_prev.hex()}"
                    ),
                )
            )

        recomputed = link_hash(prev_digest, leaf_digest)
        if recomputed != link_digest:
            findings.append(
                ChainFinding(
                    seq=leaf.seq,
                    fault=ChainFault.LINK_MISMATCH,
                    detail=(
                        f"stored link_hash {link_digest.hex()} is not "
                        f"SHA-256(prev_link_hash || leaf_hash) = {recomputed.hex()}"
                    ),
                )
            )

        # Continue from what the row *claims*, so one bad link produces one finding
        # rather than cascading into every row after it.
        expected_prev = link_digest

    return findings
