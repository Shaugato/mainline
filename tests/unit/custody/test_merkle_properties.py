# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Property tests for the RFC 6962 tree: every proof, at every size, up to 512 leaves.

Known-answer vectors prove we agree with Certificate Transparency on eight specific
leaves. They cannot prove we agree on the shapes that only appear at other sizes — and
the tree's structure changes at every power of two, so "it worked on eight leaves" is a
statement about one of the easiest cases there is.

Three independent oracles run here:

1. **Self-consistency** — every proof this package generates verifies with the
   ``verify_*`` functions, which share no code with generation: generation walks leaf
   ranges top-down, verification folds hashes bottom-up over bit arithmetic and never
   sees a tree at all.
2. **An external definition** — ``_reference_*`` is a literal transcription of the
   recursive definitions in RFC 6962 §2.1/§2.1.1/§2.1.2, written to look like the RFC.
   It is slow, and it is meant to be: it is the specification, not an implementation.
3. **Falsification** — a proof with one bit changed, one node dropped or two nodes
   swapped must never verify. A verifier that accepts a mutated proof is worse than no
   verifier, because it produces a PASS an operator will rely on.

Sizing. The exhaustive lane sweeps every ``(leaf_index, tree_size)`` and every
``(first_size, tree_size)`` for tree sizes up to :data:`EXHAUSTIVE_SIZE`, which is
several thousand proofs and runs in the fast lane. The full sweep to 512 — 131 328
inclusion proofs and as many consistency proofs — is the same code with a larger bound,
marked ``slow``. Hypothesis covers the interval between them on every run, drawing
sizes up to 512 and indices within them, so nothing in that range is checked only by
the slow lane.
"""

from __future__ import annotations

import hashlib
import itertools

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from trappoint_ledger.chain import (
    GENESIS_LINK_HASH,
    LinkedLeaf,
    chain_links,
    recompute_chain,
    verify_chain,
)
from trappoint_ledger.merkle import (
    EMPTY_ROOT,
    LeafRange,
    MerkleTree,
    consistency_proof,
    consistency_proof_ranges,
    hash_children,
    hash_leaf,
    inclusion_proof,
    inclusion_proof_ranges,
    verify_consistency,
    verify_inclusion,
)

#: The largest tree these properties build. Named in the K2 exit criteria.
MAX_SIZE = 512

#: Tree sizes swept exhaustively in the fast lane.
EXHAUSTIVE_SIZE = 96

#: Tree sizes cross-checked against the literal RFC transcription, which memoises
#: nothing on purpose and so is O(n log n) per call.
REFERENCE_SIZE = 64

_SETTINGS = settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

ENTRIES: list[bytes] = [f'{{"seq":{i},"site":"BLK-07"}}'.encode() for i in range(MAX_SIZE)]
LEAVES: list[bytes] = [hash_leaf(e) for e in ENTRIES]

#: One tree of MAX_SIZE leaves answers `subtree_hash` for every prefix, because a proof
#: at tree size n only ever asks about leaf ranges inside [0, n).
TREE = MerkleTree(LEAVES)
ROOTS: list[bytes] = [TREE.root_at(n) for n in range(MAX_SIZE + 1)]

_SIZES = st.integers(min_value=1, max_value=MAX_SIZE)


# ── Oracle 2: a literal transcription of RFC 6962 §2.1, §2.1.1, §2.1.2 ────────────────
def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _k(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _reference_mth(d: list[bytes]) -> bytes:
    n = len(d)
    if n == 0:
        return _sha(b"")
    if n == 1:
        return _sha(b"\x00" + d[0])
    k = _k(n)
    return _sha(b"\x01" + _reference_mth(d[:k]) + _reference_mth(d[k:]))


def _reference_path(m: int, d: list[bytes]) -> list[bytes]:
    if len(d) == 1:
        return []
    k = _k(len(d))
    if m < k:
        return [*_reference_path(m, d[:k]), _reference_mth(d[k:])]
    return [*_reference_path(m - k, d[k:]), _reference_mth(d[:k])]


def _reference_subproof(m: int, d: list[bytes], complete: bool) -> list[bytes]:
    n = len(d)
    if m == n:
        return [] if complete else [_reference_mth(d)]
    k = _k(n)
    if m <= k:
        return [*_reference_subproof(m, d[:k], complete), _reference_mth(d[k:])]
    return [*_reference_subproof(m - k, d[k:], False), _reference_mth(d[:k])]


def _mutate(proof, node, position, bit):
    mutated = list(proof)
    corrupted = bytearray(mutated[node])
    corrupted[position] ^= 1 << bit
    mutated[node] = bytes(corrupted)
    return mutated


# ── Fixed facts ───────────────────────────────────────────────────────────────────────
def test_empty_tree_root_is_sha256_of_the_empty_string():
    assert MerkleTree().root == hashlib.sha256(b"").digest()
    assert hashlib.sha256(b"").digest() == EMPTY_ROOT
    assert ROOTS[0] == EMPTY_ROOT


def test_roots_match_the_literal_rfc_transcription():
    for n in range(REFERENCE_SIZE + 1):
        assert ROOTS[n] == _reference_mth(ENTRIES[:n]), f"root disagrees at n={n}"


def test_proof_shapes_match_the_literal_rfc_transcription():
    for n in range(1, REFERENCE_SIZE + 1):
        for i in range(n):
            assert inclusion_proof(TREE, i, n) == _reference_path(i, ENTRIES[:n])
        for m in range(1, n + 1):
            assert consistency_proof(TREE, m, n) == _reference_subproof(m, ENTRIES[:n], True)


def test_proof_length_is_logarithmic():
    # A proof longer than ceil(log2(n)) means the tree is not shaped the way RFC 6962
    # says — which is how a wrong `k` first shows up as a performance defect, long
    # before anyone notices it is also an interoperability defect.
    for n in range(1, EXHAUSTIVE_SIZE + 1):
        limit = max(1, (n - 1).bit_length())
        for i in range(n):
            assert len(inclusion_proof_ranges(i, n)) <= limit
        for m in range(1, n + 1):
            assert len(consistency_proof_ranges(m, n)) <= limit + 1


# ── Oracle 1: self-consistency, exhaustively ──────────────────────────────────────────
def _sweep_inclusion(max_size: int) -> int:
    checked = 0
    for n in range(1, max_size + 1):
        root = ROOTS[n]
        for i in range(n):
            proof = inclusion_proof(TREE, i, n)
            assert verify_inclusion(LEAVES[i], i, n, proof, root), f"i={i} n={n}"
            checked += 1
    return checked


def _sweep_consistency(max_size: int) -> int:
    checked = 0
    for n in range(1, max_size + 1):
        root = ROOTS[n]
        for m in range(1, n + 1):
            proof = consistency_proof(TREE, m, n)
            assert verify_consistency(m, ROOTS[m], n, root, proof), f"m={m} n={n}"
            checked += 1
    return checked


def test_every_inclusion_proof_verifies_up_to_the_exhaustive_bound():
    assert _sweep_inclusion(EXHAUSTIVE_SIZE) == EXHAUSTIVE_SIZE * (EXHAUSTIVE_SIZE + 1) // 2


def test_every_consistency_proof_verifies_up_to_the_exhaustive_bound():
    assert _sweep_consistency(EXHAUSTIVE_SIZE) == EXHAUSTIVE_SIZE * (EXHAUSTIVE_SIZE + 1) // 2


@pytest.mark.slow
def test_every_inclusion_proof_verifies_up_to_512():
    assert _sweep_inclusion(MAX_SIZE) == MAX_SIZE * (MAX_SIZE + 1) // 2


@pytest.mark.slow
def test_every_consistency_proof_verifies_up_to_512():
    assert _sweep_consistency(MAX_SIZE) == MAX_SIZE * (MAX_SIZE + 1) // 2


# ── Hypothesis over the whole range ───────────────────────────────────────────────────
@given(_SIZES, st.data())
@_SETTINGS
def test_inclusion_proof_verifies_at_every_tree_size(tree_size, data):
    leaf_index = data.draw(st.integers(min_value=0, max_value=tree_size - 1))
    proof = inclusion_proof(TREE, leaf_index, tree_size)
    assert verify_inclusion(LEAVES[leaf_index], leaf_index, tree_size, proof, ROOTS[tree_size])

    # A proof is a statement about one root. Against any other root it must fail, and
    # "any other root" includes the log's own root one entry later — which is exactly
    # what a log operator would offer if they wanted the check to look like it passed.
    other = data.draw(st.integers(min_value=1, max_value=MAX_SIZE))
    assume(ROOTS[other] != ROOTS[tree_size])
    assert not verify_inclusion(LEAVES[leaf_index], leaf_index, tree_size, proof, ROOTS[other])


@given(_SIZES, st.data())
@_SETTINGS
def test_consistency_proof_verifies_for_every_pair(tree_size, data):
    first_size = data.draw(st.integers(min_value=1, max_value=tree_size))
    proof = consistency_proof(TREE, first_size, tree_size)
    assert verify_consistency(first_size, ROOTS[first_size], tree_size, ROOTS[tree_size], proof)


@given(_SIZES, st.data())
@_SETTINGS
def test_mutating_one_byte_of_an_inclusion_proof_always_fails(tree_size, data):
    leaf_index = data.draw(st.integers(min_value=0, max_value=tree_size - 1))
    proof = inclusion_proof(TREE, leaf_index, tree_size)
    assume(proof)
    mutated = _mutate(
        proof,
        data.draw(st.integers(min_value=0, max_value=len(proof) - 1)),
        data.draw(st.integers(min_value=0, max_value=31)),
        data.draw(st.integers(min_value=0, max_value=7)),
    )
    assert not verify_inclusion(
        LEAVES[leaf_index], leaf_index, tree_size, mutated, ROOTS[tree_size]
    )


@given(_SIZES, st.data())
@_SETTINGS
def test_mutating_one_byte_of_a_consistency_proof_always_fails(tree_size, data):
    first_size = data.draw(st.integers(min_value=1, max_value=tree_size))
    proof = consistency_proof(TREE, first_size, tree_size)
    assume(proof)
    mutated = _mutate(
        proof,
        data.draw(st.integers(min_value=0, max_value=len(proof) - 1)),
        data.draw(st.integers(min_value=0, max_value=31)),
        data.draw(st.integers(min_value=0, max_value=7)),
    )
    assert not verify_consistency(
        first_size, ROOTS[first_size], tree_size, ROOTS[tree_size], mutated
    )


@given(_SIZES, st.data())
@_SETTINGS
def test_dropping_or_reordering_proof_nodes_always_fails(tree_size, data):
    leaf_index = data.draw(st.integers(min_value=0, max_value=tree_size - 1))
    proof = inclusion_proof(TREE, leaf_index, tree_size)
    assume(len(proof) >= 2)
    root = ROOTS[tree_size]
    assert not verify_inclusion(LEAVES[leaf_index], leaf_index, tree_size, proof[1:], root)
    assert not verify_inclusion(LEAVES[leaf_index], leaf_index, tree_size, proof[:-1], root)
    swapped = list(proof)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assume(swapped != list(proof))
    assert not verify_inclusion(LEAVES[leaf_index], leaf_index, tree_size, swapped, root)


@given(_SIZES)
@_SETTINGS
def test_a_record_that_was_never_sequenced_has_no_inclusion_proof(tree_size):
    # The proposition an inclusion proof answers is "this was never in your log", so
    # test it from the attacker's side: a record that was never sequenced must have no
    # proof against a real root, whatever index is claimed for it.
    stranger = hash_leaf(b'{"seq":9999,"site":"BLK-07","forged":true}')
    for leaf_index in {0, tree_size // 2, tree_size - 1}:
        proof = inclusion_proof(TREE, leaf_index, tree_size)
        assert not verify_inclusion(stranger, leaf_index, tree_size, proof, ROOTS[tree_size])


# ── Proof ranges, stored nodes, and what a tile-fetching verifier rebuilds ────────────
@given(_SIZES, st.data())
@_SETTINGS
def test_proof_nodes_rebuild_from_the_stored_nodes_a_verifier_can_fetch(tree_size, data):
    leaf_index = data.draw(st.integers(min_value=0, max_value=tree_size - 1))
    ranges = inclusion_proof_ranges(leaf_index, tree_size)
    proof = inclusion_proof(TREE, leaf_index, tree_size)

    for leaf_range, digest in zip(ranges, proof, strict=True):
        blocks = leaf_range.perfect_blocks()
        # The blocks tile the range exactly: no overlap, no hole, in leaf order.
        assert blocks[0].start == leaf_range.start
        assert blocks[-1].end == leaf_range.end
        for left, right in itertools.pairwise(blocks):
            assert left.end == right.start

        # Every block is a node the ledger really stores, and folding them right to
        # left rebuilds the (possibly ephemeral) proof node. That fold is precisely
        # what a verifier reading static tiles does, so if this ever fails, the tiles
        # we publish are not sufficient to check the proofs we publish.
        folded: bytes | None = None
        for block in reversed(blocks):
            coord = block.node_coord()
            assert coord is not None
            stored = TREE.node(coord.level, coord.index)
            assert stored == TREE.subtree_hash(block.start, block.end)
            folded = stored if folded is None else hash_children(stored, folded)
        assert folded == digest


@given(_SIZES)
@_SETTINGS
def test_a_perfect_range_is_its_own_only_block(tree_size):
    for level in range(tree_size.bit_length()):
        span = 1 << level
        if span > tree_size:
            break
        leaf_range = LeafRange(0, span)
        assert leaf_range.is_perfect
        assert leaf_range.perfect_blocks() == (leaf_range,)
        coord = leaf_range.node_coord()
        assert coord is not None
        assert coord.level == level
        assert coord.index == 0


# ── The chain, alongside the tree ─────────────────────────────────────────────────────
@given(st.integers(min_value=0, max_value=MAX_SIZE))
@_SETTINGS
def test_link_chain_recomputes_for_every_prefix(tree_size):
    links = recompute_chain(LEAVES[:tree_size])
    pairs = chain_links(LEAVES[:tree_size])
    assert len(links) == tree_size
    assert [link for _, link in pairs] == links
    if tree_size:
        assert pairs[0][0] == GENESIS_LINK_HASH
    rows = [
        LinkedLeaf(seq=i, leaf_hash=LEAVES[i], link_hash=link, prev_link_hash=prev)
        for i, (prev, link) in enumerate(pairs)
    ]
    assert verify_chain(rows) == []
