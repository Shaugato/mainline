# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""RFC 6962 Merkle Tree Hash — in memory, with an append that names exactly what changed.

The definitions, verbatim from `RFC 6962 §2.1
<https://www.rfc-editor.org/rfc/rfc6962#section-2.1>`_::

    MTH({})      = SHA-256()
    MTH({d(0)})  = SHA-256(0x00 || d(0))
    MTH(D[n])    = SHA-256(0x01 || MTH(D[0:k]) || MTH(D[k:n]))   for n > 1

where **k is the largest power of two strictly less than n**.

That last clause is the single most common implementation error in this algorithm, and
it is silent: a tree split at ``2 ** (n.bit_length() - 1)`` agrees with RFC 6962 for
every ``n`` that is not a power of two and disagrees for every ``n`` that is, which
means the mistake survives casual testing and then produces a tree that no other
Certificate-Transparency implementation will ever agree with. Once a checkpoint over
such a tree has been signed, timestamped and written to S3 under Object Lock
COMPLIANCE, the error is not fixable — it is baked into evidence that cannot be
deleted. :func:`largest_power_of_two_below` is therefore written once, tested against
brute force, and used everywhere.

Storage model, and why ``ledger_node`` can be append-only
---------------------------------------------------------
A node is **perfect** when the leaf range it covers has a power-of-two length and
starts at a multiple of that length. Perfect nodes are the ones this tree stores, and
they are addressed by ``(level, index)`` — exactly the primary key of
``mainline.ledger_node (site_code, level, idx)``.

A perfect node's value depends only on leaves ``[index * 2**level, (index+1) * 2**level)``,
all of which are already sequenced when it first becomes computable. **A perfect node
is therefore write-once: it can never change.** That is what makes it sound for the
datamodel lead's ``fn_refuse_mutation()`` trigger to be applied to ``ledger_node`` —
an append-only interior-node table is not a restriction the tree has to work around,
it is a property the tree already has.

The nodes that *do* change as the tree grows are the **ephemeral** ones on the right
spine (``MTH(D[k:n])`` for a non-power-of-two ``n``). They are never persisted. The
only ephemeral value the ledger stores is the root itself, and it is stored in
``ledger_checkpoint`` — a new row per checkpoint, never an update.

:meth:`MerkleTree.append` returns precisely the perfect nodes that came into existence,
so the sequencer writes its ``ledger_node`` rows without ever recomputing the tree and
without ever issuing an ``UPDATE``.

This module imports ``hashlib`` and nothing else. See ``merkle/__init__.py``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Final

#: Width of every hash in this module. SHA-256, per RFC 6962 §2.
HASH_BYTES: Final = 32

#: RFC 6962 §2.1 domain separation for leaves.
LEAF_PREFIX: Final = b"\x00"

#: RFC 6962 §2.1 domain separation for interior nodes.
NODE_PREFIX: Final = b"\x01"

#: ``MTH({}) = SHA-256()``. The empty tree hashes the empty string, *not* 32 zero bytes,
#: and not the hash of any leaf. Getting this wrong is invisible until the first
#: consistency proof against an empty prefix.
EMPTY_ROOT: Final = hashlib.sha256(b"").digest()


class MerkleError(Exception):
    """Base class for every refusal raised by this module."""


class MalformedHash(MerkleError):
    """A value offered as a SHA-256 digest was not 32 bytes."""


class NodeNotStored(MerkleError):
    """A ``(level, index)`` node was requested that this tree has not yet computed."""


def _require_digest(value: bytes, what: str) -> bytes:
    """Return ``value`` if it is a 32-byte digest; raise :class:`MalformedHash` otherwise."""
    if not isinstance(value, bytes | bytearray | memoryview):
        raise MalformedHash(f"{what} must be bytes, got {type(value).__name__}")
    raw = bytes(value)
    if len(raw) != HASH_BYTES:
        raise MalformedHash(f"{what} must be {HASH_BYTES} bytes, got {len(raw)}")
    return raw


def hash_leaf(data: bytes) -> bytes:
    """Return ``SHA-256(0x00 || data)`` — the RFC 6962 leaf hash of ``data``.

    ``data`` is the *canonical bytes* of the entry (RFC 8785 JCS, produced by
    ``trappoint_jcs``), never a re-serialised object and never the database's rendering
    of the payload. ``ledger_leaf.leaf_hash`` is this value.
    """
    return hashlib.sha256(LEAF_PREFIX + data).digest()


def hash_children(left: bytes, right: bytes) -> bytes:
    """Return ``SHA-256(0x01 || left || right)`` — the RFC 6962 interior node hash."""
    return hashlib.sha256(
        NODE_PREFIX + _require_digest(left, "left child") + _require_digest(right, "right child")
    ).digest()


def largest_power_of_two_below(n: int) -> int:
    """Return the largest power of two **strictly less than** ``n`` (RFC 6962's ``k``).

    Defined for ``n >= 2``. For a power of two the answer is ``n // 2``, which is the
    case the naive ``1 << (n.bit_length() - 1)`` gets wrong — that expression returns
    ``n`` itself, producing an empty right subtree and a tree shape no other RFC 6962
    implementation shares.
    """
    if n < 2:  # noqa: PLR2004 — RFC 6962 only splits lists of length > 1.
        raise ValueError(f"k is defined only for n >= 2, got {n}")
    return 1 << ((n - 1).bit_length() - 1)


def is_power_of_two(n: int) -> bool:
    """Return whether ``n`` is a positive power of two."""
    return n > 0 and n & (n - 1) == 0


@dataclass(frozen=True, slots=True)
class NodeCoord:
    """A perfect node's address: ``level`` above the leaves, ``index`` within that level.

    Level 0 is the leaf level, so ``NodeCoord(0, i)`` is leaf ``i``'s hash. This is the
    coordinate system of ``mainline.ledger_node (site_code, level, idx)`` and of C2SP
    ``tlog-tiles``, where the ``n``-th hash of tile ``(l, t)`` is
    ``NodeCoord(8 * l, t * 256 + n)``.
    """

    level: int
    index: int

    def __post_init__(self) -> None:
        """Refuse a negative coordinate; there is no such node."""
        if self.level < 0 or self.index < 0:
            raise ValueError(f"node coordinates are non-negative, got {self!r}")

    @property
    def leaf_start(self) -> int:
        """Return the index of the first leaf this node covers."""
        return self.index << self.level

    @property
    def leaf_end(self) -> int:
        """Return the index one past the last leaf this node covers."""
        return (self.index + 1) << self.level

    @property
    def leaf_count(self) -> int:
        """Return how many leaves this node covers (always a power of two)."""
        return 1 << self.level


@dataclass(frozen=True, slots=True)
class Node:
    """A perfect node and its hash — one row of ``ledger_node``."""

    coord: NodeCoord
    digest: bytes


@dataclass(frozen=True, slots=True)
class AppendResult:
    """What one :meth:`MerkleTree.append` changed.

    ``created_nodes`` is exactly the set of ``ledger_node`` rows the sequencer must
    insert for this leaf — never more, never fewer, and never an update. ``root`` is
    the new tree head, which belongs in ``ledger_checkpoint.root_hash`` and in the
    checkpoint body.
    """

    leaf_index: int
    tree_size: int
    root: bytes
    created_nodes: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class BatchAppendResult:
    """What one batch of appends changed — the shape the sequencer's transaction writes."""

    first_leaf_index: int
    leaf_count: int
    tree_size: int
    root: bytes
    created_nodes: tuple[Node, ...]


class MerkleTree:
    """An RFC 6962 Merkle tree over an append-only list of leaf hashes.

    The tree stores leaf hashes (level 0) and every **perfect** interior node. Roots and
    other ephemeral values are computed on demand by :meth:`subtree_hash`, which is
    ``O(log n)`` hashes and touches no ephemeral state.

    Construct empty and :meth:`append`, or hand the constructor an iterable of leaf
    hashes. Nothing here does IO, holds a lock, or reads a clock.
    """

    __slots__ = ("_levels",)

    def __init__(self, leaf_hashes: Iterable[bytes] = ()) -> None:
        """Build a tree over ``leaf_hashes`` in the order given."""
        self._levels: list[list[bytes]] = [[]]
        for leaf in leaf_hashes:
            self.append(leaf)

    def __len__(self) -> int:
        """Return the number of leaves."""
        return len(self._levels[0])

    def __repr__(self) -> str:
        """Return a debugger-friendly rendering naming the size and the root."""
        return f"MerkleTree(size={self.size}, root={self.root.hex()})"

    @property
    def size(self) -> int:
        """Return the number of leaves — the ``tree_size`` of a checkpoint."""
        return len(self._levels[0])

    @property
    def root(self) -> bytes:
        """Return ``MTH(D[size])``; for an empty tree, :data:`EMPTY_ROOT`."""
        return self.subtree_hash(0, self.size)

    @property
    def levels(self) -> int:
        """Return the number of stored levels, leaves included."""
        return len(self._levels)

    def leaf(self, index: int) -> bytes:
        """Return the hash of leaf ``index``."""
        return self.node(0, index)

    def has_node(self, level: int, index: int) -> bool:
        """Return whether the perfect node ``(level, index)`` has been computed."""
        return 0 <= level < len(self._levels) and 0 <= index < len(self._levels[level])

    def node(self, level: int, index: int) -> bytes:
        """Return the stored hash of the perfect node ``(level, index)``.

        Raises :class:`NodeNotStored` when the node does not exist yet — which is the
        honest answer, because an incomplete subtree has no RFC 6962 hash at all.
        """
        if not self.has_node(level, index):
            raise NodeNotStored(
                f"node (level={level}, index={index}) is not complete in a tree of size {self.size}"
            )
        return self._levels[level][index]

    def nodes(self) -> Iterator[Node]:
        """Yield every stored perfect node in ``(level, index)`` order, leaves first."""
        for level, row in enumerate(self._levels):
            for index, digest in enumerate(row):
                yield Node(NodeCoord(level, index), digest)

    def subtree_hash(self, start: int, end: int) -> bytes:
        """Return ``MTH(D[start:end])``, the RFC 6962 hash of a contiguous leaf range.

        Perfect, aligned ranges are answered from storage in ``O(1)``. Any other range
        is the RFC's own recursion — split at ``k``, hash the two halves — which costs
        ``O(log n)`` hashes and is what produces an ephemeral right-spine value such as
        the root of a tree whose size is not a power of two.
        """
        if start < 0 or end < start or end > self.size:
            raise ValueError(f"leaf range [{start}, {end}) is outside a tree of size {self.size}")
        span = end - start
        if span == 0:
            return EMPTY_ROOT
        if is_power_of_two(span) and start % span == 0:
            return self.node(span.bit_length() - 1, start // span)
        k = largest_power_of_two_below(span)
        return hash_children(self.subtree_hash(start, start + k), self.subtree_hash(start + k, end))

    def root_at(self, tree_size: int) -> bytes:
        """Return the root the log had at ``tree_size`` leaves.

        The log is append-only, so a past root is not history a verifier has to be
        trusted about: it is recomputable from the leaves that are still there. A
        checkpoint whose ``root_hash`` disagrees with this value over the same prefix is
        the finding, not the recomputation.
        """
        return self.subtree_hash(0, tree_size)

    def append(self, leaf_hash: bytes) -> AppendResult:
        """Append one leaf hash and return the new root plus the nodes it created."""
        self._levels[0].append(_require_digest(leaf_hash, "leaf hash"))
        size = self.size
        created: list[Node] = []

        # A leaf at index `size - 1` completes the level-`L` node ending at that leaf
        # exactly when `size` is divisible by `2 ** L`. Walk up while that holds: at
        # most `size.bit_length()` iterations, and for most appends exactly zero.
        level = 1
        while size % (1 << level) == 0:
            index = (size >> level) - 1
            digest = hash_children(
                self._levels[level - 1][2 * index], self._levels[level - 1][2 * index + 1]
            )
            if level == len(self._levels):
                self._levels.append([])
            self._levels[level].append(digest)
            created.append(Node(NodeCoord(level, index), digest))
            level += 1

        return AppendResult(
            leaf_index=size - 1,
            tree_size=size,
            root=self.root,
            created_nodes=tuple(created),
        )

    def extend(self, leaf_hashes: Sequence[bytes]) -> BatchAppendResult:
        """Append a batch of leaf hashes and return one aggregate result.

        This is the sequencer's shape: one batch, one checkpoint, one set of
        ``ledger_node`` inserts. The root is computed once at the end rather than once
        per leaf, because only the final root is signed.
        """
        first = self.size
        created: list[Node] = []
        for leaf in leaf_hashes:
            self._levels[0].append(_require_digest(leaf, "leaf hash"))
            size = self.size
            level = 1
            while size % (1 << level) == 0:
                index = (size >> level) - 1
                digest = hash_children(
                    self._levels[level - 1][2 * index], self._levels[level - 1][2 * index + 1]
                )
                if level == len(self._levels):
                    self._levels.append([])
                self._levels[level].append(digest)
                created.append(Node(NodeCoord(level, index), digest))
                level += 1

        return BatchAppendResult(
            first_leaf_index=first,
            leaf_count=self.size - first,
            tree_size=self.size,
            root=self.root,
            created_nodes=tuple(created),
        )


def merkle_tree_hash(leaf_hashes: Sequence[bytes]) -> bytes:
    """Return ``MTH`` over ``leaf_hashes`` — the one-shot form of :class:`MerkleTree`.

    Provided because the definition should be callable without constructing anything:
    a verifier that has the leaves and wants the root should not have to know about
    node storage.
    """
    return MerkleTree(leaf_hashes).root
