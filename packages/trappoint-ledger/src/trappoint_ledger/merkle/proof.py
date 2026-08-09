# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""RFC 6962 inclusion and consistency proofs — generation, and stateless verification.

Generation follows `RFC 6962 §2.1.1 (PATH) <https://www.rfc-editor.org/rfc/rfc6962#section-2.1.1>`_
and `§2.1.2 (PROOF/SUBPROOF) <https://www.rfc-editor.org/rfc/rfc6962#section-2.1.2>`_.
Verification follows the algorithms in `RFC 6962-bis §2.1.3.2 and §2.1.4.2
<https://datatracker.ietf.org/doc/html/draft-ietf-trans-rfc6962-bis-42>`_, which are the
same relations expressed so that a verifier needs no tree.

Two layers, deliberately separated
----------------------------------
1. **Index arithmetic** — :func:`inclusion_proof_ranges` and
   :func:`consistency_proof_ranges` answer *which leaf ranges* a proof is made of,
   using no hashes at all. That is what ``merkle.tiles`` consumes to decide which
   static tiles a verifier must fetch, and it is checkable by hand on a whiteboard.
2. **Hashes** — :func:`inclusion_proof` and :func:`consistency_proof` ask a
   :class:`HashSource` (anything with a ``subtree_hash`` method;
   :class:`~trappoint_ledger.merkle.tree.MerkleTree` is one) for the hash of each range.

Why the ranges, and not ``(level, index)`` coordinates
------------------------------------------------------
In a tree whose size is not a power of two, some proof nodes are **ephemeral**: they
are ``MTH`` over a leaf range that is not a perfect aligned subtree, so they exist in
no ``ledger_node`` row and in no tile. A ``(level, index)`` API would have to lie about
them. :class:`LeafRange` does not: :meth:`LeafRange.node_coord` returns ``None`` for an
ephemeral node, and :meth:`LeafRange.perfect_blocks` decomposes it into the stored
nodes a verifier must fetch and fold for itself.

The ``verify_*`` functions are pure, side-effect free, allocate nothing beyond a few
digests, and depend on ``hashlib`` alone — they are written to be *lifted* verbatim into
``trappoint-verify``, whose entire dependency floor is ``cryptography``. They return
``bool`` and never raise on malformed input, because every byte they are given may have
been chosen by an adversary and an exception escaping a verifier is a crash report
where a finding belongs.

A measured limit, stated here because a caller who does not know it will build a check
that does not check what they think
-----------------------------------------------------------------------------------
**A proof does not authenticate the tree size.** Both verification algorithms consume
the sizes only as ``size - 1`` and immediately shift right, so sizes differing in bits
those shifts discard are indistinguishable: a proof generated at tree size 8 verifies
unchanged against a claimed tree size of 7, as long as the root it is checked against is
the real one. ``tests/test_merkle_vectors.py::
test_a_proof_does_not_authenticate_the_tree_size_only_the_checkpoint_does`` demonstrates
it rather than describing it.

That is a property of RFC 6962, not a defect to patch locally — a "stricter" verifier
that disagreed with every other implementation would be worse than this. It says where
the size *is* authenticated: in the signed checkpoint body, which binds ``tree_size``
and ``root_hash`` under one signature. So a verifier must take both from a checkpoint
whose signature it has already verified, and never from the surrounding bundle's own
unsigned claim about which size a proof belongs to. The root is never fuzzy; only the
number beside it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from trappoint_ledger.merkle.tree import (
    EMPTY_ROOT,
    HASH_BYTES,
    MerkleTree,
    NodeCoord,
    hash_children,
    is_power_of_two,
    largest_power_of_two_below,
)


@runtime_checkable
class HashSource(Protocol):
    """Anything that can answer ``MTH(D[start:end])`` for a contiguous leaf range."""

    def subtree_hash(self, start: int, end: int) -> bytes:
        """Return ``MTH(D[start:end])``."""
        ...


@dataclass(frozen=True, slots=True)
class LeafRange:
    """A contiguous half-open leaf range ``[start, end)`` whose ``MTH`` is one proof node."""

    start: int
    end: int

    def __post_init__(self) -> None:
        """Refuse an inverted or negative range."""
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"leaf range must be non-empty and non-negative, got {self!r}")

    @property
    def size(self) -> int:
        """Return how many leaves the range covers."""
        return self.end - self.start

    @property
    def is_perfect(self) -> bool:
        """Return whether the range is a perfect, aligned subtree (so a stored node)."""
        span = self.size
        return is_power_of_two(span) and self.start % span == 0

    def node_coord(self) -> NodeCoord | None:
        """Return the ``(level, index)`` of the stored node, or ``None`` if ephemeral."""
        if not self.is_perfect:
            return None
        return NodeCoord(self.size.bit_length() - 1, self.start // self.size)

    def perfect_blocks(self) -> tuple[LeafRange, ...]:
        """Return the stored, perfect ranges this range decomposes into, left to right.

        For a perfect range this is the range itself. For an ephemeral one it is the
        RFC 6962 recursion carried out to its perfect leaves — exactly the ``ledger_node``
        rows (equivalently, the tile hashes) a verifier must fetch in order to
        reconstruct this proof node without our help.
        """
        out: list[LeafRange] = []
        stack = [(self.start, self.end)]
        while stack:
            start, end = stack.pop()
            span = end - start
            if is_power_of_two(span) and start % span == 0:
                out.append(LeafRange(start, end))
                continue
            k = largest_power_of_two_below(span)
            # Pushed right-first so the left block is processed first and `out` stays
            # in left-to-right leaf order.
            stack.append((start + k, end))
            stack.append((start, start + k))
        return tuple(out)


def _as_source(source: HashSource | Sequence[bytes]) -> HashSource:
    """Return ``source`` as a :class:`HashSource`, building a tree from bare leaf hashes."""
    if isinstance(source, HashSource):
        return source
    return MerkleTree(source)


def inclusion_proof_ranges(leaf_index: int, tree_size: int) -> list[LeafRange]:
    """Return the leaf ranges of ``PATH(leaf_index, D[tree_size])``, bottom node first.

    RFC 6962 §2.1.1 defines ``PATH`` bottom-up by recursion (the sibling of the current
    subtree is appended *after* the recursive result, so the deepest sibling ends up
    first). The loop below descends top-down, which is the natural iteration, and
    reverses at the end.
    """
    if tree_size <= 0:
        raise ValueError(f"tree_size must be positive, got {tree_size}")
    if not 0 <= leaf_index < tree_size:
        raise ValueError(f"leaf_index {leaf_index} is outside a tree of size {tree_size}")

    out: list[LeafRange] = []
    start, end, m = 0, tree_size, leaf_index
    while end - start > 1:
        k = largest_power_of_two_below(end - start)
        if m < k:
            out.append(LeafRange(start + k, end))
            end = start + k
        else:
            out.append(LeafRange(start, start + k))
            start += k
            m -= k
    out.reverse()
    return out


def consistency_proof_ranges(first_size: int, tree_size: int) -> list[LeafRange]:
    """Return the leaf ranges of ``PROOF(first_size, D[tree_size])``, bottom node first.

    RFC 6962 §2.1.2 defines ``PROOF(m, D[n]) = SUBPROOF(m, D[n], true)`` for
    ``0 < m <= n``. The boolean records whether the ``m``-leaf prefix is still known to
    be a complete subtree of the range under consideration; once it is not, the
    prefix's own hash must be included so the verifier can rebuild both roots. An
    ``m`` of zero is outside the RFC's domain — the empty tree is trivially a prefix of
    everything and there is nothing to prove — so this refuses it rather than inventing
    a proof.
    """
    if first_size <= 0:
        raise ValueError(f"first_size must be positive, got {first_size}")
    if first_size > tree_size:
        raise ValueError(f"first_size {first_size} exceeds tree_size {tree_size}")

    out: list[LeafRange] = []
    start, end, m, prefix_is_whole_subtree = 0, tree_size, first_size, True
    while True:
        span = end - start
        if m == span:
            if not prefix_is_whole_subtree:
                out.append(LeafRange(start, end))
            break
        k = largest_power_of_two_below(span)
        if m <= k:
            out.append(LeafRange(start + k, end))
            end = start + k
        else:
            out.append(LeafRange(start, start + k))
            start += k
            m -= k
            prefix_is_whole_subtree = False
    out.reverse()
    return out


def inclusion_proof(
    source: HashSource | Sequence[bytes], leaf_index: int, tree_size: int
) -> list[bytes]:
    """Return the RFC 6962 inclusion proof for ``leaf_index`` at ``tree_size``."""
    src = _as_source(source)
    return [src.subtree_hash(r.start, r.end) for r in inclusion_proof_ranges(leaf_index, tree_size)]


def consistency_proof(
    source: HashSource | Sequence[bytes], first_size: int, tree_size: int
) -> list[bytes]:
    """Return the RFC 6962 consistency proof between ``first_size`` and ``tree_size``."""
    src = _as_source(source)
    return [
        src.subtree_hash(r.start, r.end) for r in consistency_proof_ranges(first_size, tree_size)
    ]


def _well_formed(proof: Sequence[bytes]) -> bool:
    """Return whether every element of ``proof`` is a 32-byte digest."""
    return all(isinstance(p, bytes | bytearray) and len(p) == HASH_BYTES for p in proof)


def verify_inclusion(
    leaf_hash: bytes,
    leaf_index: int,
    tree_size: int,
    proof: Sequence[bytes],
    root: bytes,
) -> bool:
    """Return whether ``proof`` shows ``leaf_hash`` is leaf ``leaf_index`` of ``root``.

    RFC 6962-bis §2.1.3.2. Pure: no IO, no state, no exceptions on adversarial input.

    This is the check that answers *"that entry was never in your log"* — the one
    proposition a hash chain cannot rebut, because a chain that has been rewritten
    end-to-end is self-consistent and a tree whose root was published before the
    rewrite is not.
    """
    if tree_size <= 0 or not 0 <= leaf_index < tree_size:
        return False
    if not _well_formed([leaf_hash, root]) or not _well_formed(proof):
        return False

    node_index, last_index = leaf_index, tree_size - 1
    computed = bytes(leaf_hash)
    for sibling in proof:
        if last_index == 0:
            return False
        if node_index & 1 or node_index == last_index:
            computed = hash_children(sibling, computed)
            while node_index != 0 and not node_index & 1:
                node_index >>= 1
                last_index >>= 1
        else:
            computed = hash_children(computed, sibling)
        node_index >>= 1
        last_index >>= 1

    return last_index == 0 and computed == bytes(root)


def verify_consistency(  # noqa: PLR0911 — see the note on early returns below.
    first_size: int,
    first_root: bytes,
    tree_size: int,
    tree_root: bytes,
    proof: Sequence[bytes],
) -> bool:
    """Return whether ``proof`` shows the ``first_size`` tree is a prefix of the ``tree_size`` one.

    RFC 6962-bis §2.1.4.2. Pure, and total: malformed or adversarial input yields
    ``False``, never an exception.

    The early returns are deliberate and are why ``PLR0911`` is suppressed here: each
    one is a distinct reason to refuse — the sizes are impossible, a digest is not a
    digest, the prefix is empty, the sizes are equal, the proof is empty when it must
    not be. Collapsing them into one exit would make the function shorter and would
    make it impossible for a reader to see which refusals exist.

    This is check 3, and it is the one that defeats attack **A1** — delete leaf *k*,
    renumber, recompute every ``link_hash`` in a single ``UPDATE … FROM
    generate_series``. That attack leaves a perfectly self-consistent chain. It cannot
    leave a consistent tree, because the earlier root was signed, timestamped and
    written to Object Lock storage before the attacker changed their mind.
    """
    if first_size < 0 or tree_size < 0 or first_size > tree_size:
        return False
    if not _well_formed([first_root, tree_root]) or not _well_formed(proof):
        return False

    if first_size == 0:
        # The empty tree is a prefix of every tree; there is nothing to prove and
        # nothing to accept beyond the claim that the earlier root really was empty.
        return len(proof) == 0 and bytes(first_root) == EMPTY_ROOT
    if first_size == tree_size:
        return len(proof) == 0 and bytes(first_root) == bytes(tree_root)

    path = [bytes(p) for p in proof]
    if is_power_of_two(first_size):
        # The prefix is itself a complete subtree, so its root is not carried in the
        # proof; RFC 6962-bis prepends it before running the common loop.
        path.insert(0, bytes(first_root))
    if not path:
        return False

    node_index, last_index = first_size - 1, tree_size - 1
    while node_index & 1:
        node_index >>= 1
        last_index >>= 1

    first_computed = path[0]
    tree_computed = path[0]
    for sibling in path[1:]:
        if last_index == 0:
            return False
        if node_index & 1 or node_index == last_index:
            first_computed = hash_children(sibling, first_computed)
            tree_computed = hash_children(sibling, tree_computed)
            while node_index != 0 and not node_index & 1:
                node_index >>= 1
                last_index >>= 1
        else:
            tree_computed = hash_children(tree_computed, sibling)
        node_index >>= 1
        last_index >>= 1

    return (
        last_index == 0
        and first_computed == bytes(first_root)
        and tree_computed == bytes(tree_root)
    )
