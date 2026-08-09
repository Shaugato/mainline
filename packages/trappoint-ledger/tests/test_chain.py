# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The link chain: recomputation, density, and the demonstration of its own limits.

The last test in this file is the important one. It performs attack **A1** — delete
leaf *k*, renumber the rest, recompute every ``link_hash`` — and asserts that the chain
verifies afterwards. That is not a bug being documented; it is the reason the Merkle
tree exists, stated as an executable fact rather than as a paragraph nobody rereads.
"""

from __future__ import annotations

import hashlib

import pytest
from trappoint_ledger.chain import (
    GENESIS_LINK_HASH,
    ChainFault,
    LinkedLeaf,
    MalformedHash,
    SequenceNotDense,
    assert_dense,
    chain_head,
    chain_links,
    link_hash,
    recompute_chain,
    verify_chain,
)
from trappoint_ledger.merkle import (
    MerkleTree,
    consistency_proof,
    hash_leaf,
    verify_consistency,
)

ENTRIES = [f'{{"entry":{i},"kind":"disposition"}}'.encode() for i in range(12)]
LEAVES = [hash_leaf(e) for e in ENTRIES]


def _linked(leaf_hashes, *, start=0):
    return [
        LinkedLeaf(seq=start + i, leaf_hash=leaf, link_hash=link, prev_link_hash=prev)
        for i, (leaf, (prev, link)) in enumerate(
            zip(leaf_hashes, chain_links(leaf_hashes), strict=True)
        )
    ]


def test_genesis_is_thirty_two_zero_bytes_and_is_not_null():
    # Explicit zeroes rather than NULL, because CU-1's UNIQUE (site_code,
    # prev_link_hash) must cover seq 0 too — and NULL values do not collide, so a
    # nullable genesis would leave exactly one row forkable.
    assert bytes(32) == GENESIS_LINK_HASH
    assert len(GENESIS_LINK_HASH) == 32
    assert hashlib.sha256(b"").digest() != GENESIS_LINK_HASH


def test_link_hash_is_sha256_of_the_two_digests_concatenated():
    first = link_hash(GENESIS_LINK_HASH, LEAVES[0])
    assert first == hashlib.sha256(GENESIS_LINK_HASH + LEAVES[0]).digest()
    second = link_hash(first, LEAVES[1])
    assert second == hashlib.sha256(first + LEAVES[1]).digest()
    assert recompute_chain(LEAVES[:2]) == [first, second]
    assert chain_head(LEAVES[:2]) == second


def test_recompute_chain_from_a_running_head_matches_recomputing_the_whole_log():
    whole = recompute_chain(LEAVES)
    head_after_five = chain_head(LEAVES[:5])
    tail = recompute_chain(LEAVES[5:], head=head_after_five)
    assert whole[5:] == tail
    # The sequencer appends a batch onto the head it read inside the transaction; a
    # verifier recomputes from genesis. They must agree, or the verifier's finding is
    # about our sequencer rather than about an attacker.
    assert chain_links(LEAVES)[5][0] == whole[4]


def test_chain_links_pairs_each_row_with_its_predecessor():
    pairs = chain_links(LEAVES)
    assert pairs[0][0] == GENESIS_LINK_HASH
    for i in range(1, len(pairs)):
        assert pairs[i][0] == pairs[i - 1][1]


def test_a_digest_must_be_a_digest():
    with pytest.raises(MalformedHash):
        link_hash(b"\x00" * 31, LEAVES[0])
    with pytest.raises(MalformedHash):
        link_hash(GENESIS_LINK_HASH, "not bytes")
    with pytest.raises(MalformedHash):
        recompute_chain([b"short"])


def test_assert_dense_accepts_only_dense_ascending_sequences():
    assert_dense([0, 1, 2, 3])
    assert_dense([])
    assert_dense([7, 8, 9], start=7)
    with pytest.raises(SequenceNotDense, match="expected 2"):
        assert_dense([0, 1, 3])
    with pytest.raises(SequenceNotDense):
        assert_dense([1, 0, 2])
    with pytest.raises(SequenceNotDense):
        assert_dense([0, 0, 1])


def test_verify_chain_is_clean_on_an_honest_chain():
    assert verify_chain(_linked(LEAVES)) == []
    assert verify_chain([]) == []
    assert verify_chain(_linked(LEAVES[5:], start=5), start=5) == []


def test_verify_chain_reports_a_forged_genesis():
    leaves = _linked(LEAVES)
    leaves[0] = LinkedLeaf(
        seq=0,
        leaf_hash=leaves[0].leaf_hash,
        link_hash=leaves[0].link_hash,
        prev_link_hash=b"\xff" * 32,
    )
    faults = [f.fault for f in verify_chain(leaves)]
    assert ChainFault.GENESIS_WRONG in faults
    assert ChainFault.LINK_MISMATCH in faults


def test_verify_chain_reports_a_row_that_does_not_name_its_predecessor():
    leaves = _linked(LEAVES)
    forged_prev = hashlib.sha256(b"a head that was never the head").digest()
    leaves[4] = LinkedLeaf(
        seq=4,
        leaf_hash=leaves[4].leaf_hash,
        link_hash=link_hash(forged_prev, leaves[4].leaf_hash),
        prev_link_hash=forged_prev,
    )
    findings = verify_chain(leaves)
    # Two accusations, and only two. The substituted row is internally consistent — its
    # own link_hash really is SHA-256 of the head it claims — so it is caught from BOTH
    # sides: it does not name its predecessor, and its successor does not name it. That
    # is the whole mechanical value of a chain, and it is why the report names rows 4
    # and 5 rather than every row from 4 to the head.
    assert [(f.seq, f.fault) for f in findings] == [
        (4, ChainFault.PREV_MISMATCH),
        (5, ChainFault.PREV_MISMATCH),
    ]


def test_verify_chain_reports_a_payload_swap_that_left_the_link_alone():
    leaves = _linked(LEAVES)
    leaves[6] = LinkedLeaf(
        seq=6,
        leaf_hash=hash_leaf(b'{"entry":6,"kind":"disposition","amended":true}'),
        link_hash=leaves[6].link_hash,
        prev_link_hash=leaves[6].prev_link_hash,
    )
    assert [(f.seq, f.fault) for f in verify_chain(leaves)] == [(6, ChainFault.LINK_MISMATCH)]


def test_verify_chain_reports_a_gap():
    leaves = [leaf for leaf in _linked(LEAVES) if leaf.seq != 3]
    faults = {(f.seq, f.fault) for f in verify_chain(leaves)}
    assert (4, ChainFault.NOT_DENSE) in faults


def test_verify_chain_reports_rather_than_raises_on_adversarial_bytes():
    leaves = _linked(LEAVES)
    leaves[2] = LinkedLeaf(seq=2, leaf_hash=b"", link_hash=b"", prev_link_hash=b"")
    findings = verify_chain(leaves)
    assert findings[-1].fault is ChainFault.MALFORMED
    assert findings[-1].seq == 2


def test_a1_delete_and_relink_is_invisible_to_the_chain_and_fatal_to_the_tree():
    """Attack A1, executed: the chain recomputes perfectly, the tree refuses.

    A rogue DBA with UPDATE deletes leaf 4, renumbers 5..11 down by one and recomputes
    every ``link_hash`` in a single ``UPDATE … FROM generate_series``. The result is a
    chain with no gap, correct genesis, and every row naming its predecessor: the chain
    alone reports nothing, and it is *right* to report nothing, because internally the
    chain is now perfect.

    What the attacker cannot do is change a root that was signed by a key they cannot
    reach, timestamped by an authority with no relationship to us, and written to an S3
    object version under Object Lock COMPLIANCE before they made up their mind. The
    consistency proof from that root into the rewritten log does not exist.
    """
    honest_tree = MerkleTree(LEAVES)
    published_size = 8
    published_root = honest_tree.root_at(published_size)

    tampered_leaves = [*LEAVES[:4], *LEAVES[5:]]
    tampered_rows = _linked(tampered_leaves)

    # 1. The chain is silent. Every row is dense, genesis is right, every link recomputes.
    assert verify_chain(tampered_rows) == []
    assert_dense([row.seq for row in tampered_rows])

    # 2. The tree is not. Nothing the attacker can compute over the rewritten log
    #    satisfies a verifier holding the earlier root.
    tampered_tree = MerkleTree(tampered_leaves)
    assert tampered_tree.root_at(published_size) != published_root
    forged = consistency_proof(tampered_tree, published_size, tampered_tree.size)
    assert not verify_consistency(
        published_size, published_root, tampered_tree.size, tampered_tree.root, forged
    )
    # Nor does presenting the rewritten log's own earlier root help: it is not the root
    # the witness, the timestamp and the Object Lock version all recorded.
    assert verify_consistency(
        published_size,
        tampered_tree.root_at(published_size),
        tampered_tree.size,
        tampered_tree.root,
        forged,
    )
    assert tampered_tree.root_at(published_size) != published_root
