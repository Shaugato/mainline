# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""RFC 6962 known-answer vectors, and the dependency floor of the proof algorithms.

The vectors are the Certificate Transparency reference implementation's eight-leaf test
set — the same inputs and outputs that Google's C++ reference implementation,
`certificate-transparency-go` and every other CT log agree on. They are hard-coded here
as hex so that a change in our code cannot change what "correct" means.

They are ALSO recomputed in this file by `_reference_mth`, `_reference_path` and
`_reference_subproof`: literal, deliberately naive transcriptions of the recursive
definitions in RFC 6962 §2.1, §2.1.1 and §2.1.2, written to look like the RFC rather
than like production code. Two independent statements of the same thing, one of them
copied from outside this repository, means a failure tells you *which* side is wrong:

* hard-coded vectors pass, transcription fails  → the transcription is wrong
* transcription passes, vectors fail            → the vectors were transcribed wrong
* both fail identically                         → `trappoint_ledger.merkle` is wrong

That third row is the one this file exists for.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from trappoint_ledger.merkle import (
    EMPTY_ROOT,
    MerkleTree,
    NodeCoord,
    consistency_proof,
    hash_children,
    hash_leaf,
    inclusion_proof,
    is_power_of_two,
    largest_power_of_two_below,
    merkle_tree_hash,
    verify_consistency,
    verify_inclusion,
)

# ── The CT reference implementation's eight test leaves (entry bytes, not hashes) ─────
CT_LEAF_DATA: list[bytes] = [
    bytes.fromhex(""),
    bytes.fromhex("00"),
    bytes.fromhex("10"),
    bytes.fromhex("2021"),
    bytes.fromhex("3031"),
    bytes.fromhex("40414243"),
    bytes.fromhex("5051525354555657"),
    bytes.fromhex("606162636465666768696a6b6c6d6e6f"),
]

#: `MTH(D[n])` for n = 0..8. Index 0 is the empty tree: SHA-256 of the empty string.
CT_ROOTS_HEX: list[str] = [
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
    "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
    "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
    "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
    "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
    "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
    "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
]

#: `(leaf_index, tree_size, PATH)` — RFC 6962 §2.1.1.
CT_INCLUSION_VECTORS: list[tuple[int, int, list[str]]] = [
    (0, 1, []),
    (
        0,
        8,
        [
            "96a296d224f285c67bee93c30f8a309157f0daa35dc5b87e410b78630a09cfc7",
            "5f083f0a1a33ca076a95279832580db3e0ef4584bdff1f54c8a360f50de3031e",
            "6b47aaf29ee3c2af9af889bc1fb9254dabd31177f16232dd6aab035ca39bf6e4",
        ],
    ),
    (
        5,
        8,
        [
            "bc1a0643b12e4d2d7c77918f44e0f4f79a838b6cf9ec5b5c283e1f4d88599e6b",
            "ca854ea128ed050b41b35ffc1b87b8eb2bde461e9e3b5596ece6b9d5975a0ae0",
            "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
        ],
    ),
    (2, 3, ["fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125"]),
    (
        1,
        5,
        [
            "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
            "5f083f0a1a33ca076a95279832580db3e0ef4584bdff1f54c8a360f50de3031e",
            "bc1a0643b12e4d2d7c77918f44e0f4f79a838b6cf9ec5b5c283e1f4d88599e6b",
        ],
    ),
]

#: `(first_size, tree_size, PROOF)` — RFC 6962 §2.1.2.
CT_CONSISTENCY_VECTORS: list[tuple[int, int, list[str]]] = [
    (1, 1, []),
    (
        1,
        8,
        [
            "96a296d224f285c67bee93c30f8a309157f0daa35dc5b87e410b78630a09cfc7",
            "5f083f0a1a33ca076a95279832580db3e0ef4584bdff1f54c8a360f50de3031e",
            "6b47aaf29ee3c2af9af889bc1fb9254dabd31177f16232dd6aab035ca39bf6e4",
        ],
    ),
    (
        6,
        8,
        [
            "0ebc5d3437fbe2db158b9f126a1d118e308181031d0a949f8dededebc558ef6a",
            "ca854ea128ed050b41b35ffc1b87b8eb2bde461e9e3b5596ece6b9d5975a0ae0",
            "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
        ],
    ),
    (
        2,
        5,
        [
            "5f083f0a1a33ca076a95279832580db3e0ef4584bdff1f54c8a360f50de3031e",
            "bc1a0643b12e4d2d7c77918f44e0f4f79a838b6cf9ec5b5c283e1f4d88599e6b",
        ],
    ),
]


# ── An independent, literal transcription of RFC 6962 §2.1 / §2.1.1 / §2.1.2 ──────────
def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _reference_k(n: int) -> int:
    """The largest power of two smaller than n, found by counting rather than by bit tricks."""
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
    k = _reference_k(n)
    return _sha(b"\x01" + _reference_mth(d[:k]) + _reference_mth(d[k:]))


def _reference_path(m: int, d: list[bytes]) -> list[bytes]:
    if len(d) == 1:
        return []
    k = _reference_k(len(d))
    if m < k:
        return [*_reference_path(m, d[:k]), _reference_mth(d[k:])]
    return [*_reference_path(m - k, d[k:]), _reference_mth(d[:k])]


def _reference_subproof(m: int, d: list[bytes], complete: bool) -> list[bytes]:
    n = len(d)
    if m == n:
        return [] if complete else [_reference_mth(d)]
    k = _reference_k(n)
    if m <= k:
        return [*_reference_subproof(m, d[:k], complete), _reference_mth(d[k:])]
    return [*_reference_subproof(m - k, d[k:], False), _reference_mth(d[:k])]


CT_LEAF_HASHES: list[bytes] = [_sha(b"\x00" + d) for d in CT_LEAF_DATA]


# ── The vectors ───────────────────────────────────────────────────────────────────────
def test_empty_tree_root_is_sha256_of_the_empty_string():
    # MTH({}) = SHA-256(). Not 32 zero bytes, not the hash of any leaf. The distinction
    # only becomes visible in a consistency proof against an empty prefix, by which
    # point the wrong value has been signed.
    assert hashlib.sha256(b"").digest() == EMPTY_ROOT
    assert EMPTY_ROOT.hex() == CT_ROOTS_HEX[0]
    assert MerkleTree().root == EMPTY_ROOT
    assert merkle_tree_hash([]) == EMPTY_ROOT


def test_leaf_and_node_hashing_are_domain_separated():
    assert hash_leaf(b"") == hashlib.sha256(b"\x00").digest()
    assert hash_leaf(b"abc") == hashlib.sha256(b"\x00abc").digest()
    left, right = hash_leaf(b"a"), hash_leaf(b"b")
    assert hash_children(left, right) == hashlib.sha256(b"\x01" + left + right).digest()
    # A leaf hash and an interior hash of the same bytes must differ, which is the whole
    # point of the prefixes: without them a second-preimage attack swaps a subtree for a
    # leaf and the root does not move.
    assert hash_leaf(left + right) != hash_children(left, right)


@pytest.mark.parametrize("n", range(9))
def test_merkle_tree_hash_matches_ct_vectors(n):
    tree = MerkleTree(CT_LEAF_HASHES[:n])
    assert tree.root.hex() == CT_ROOTS_HEX[n]
    assert merkle_tree_hash(CT_LEAF_HASHES[:n]).hex() == CT_ROOTS_HEX[n]
    assert _reference_mth(CT_LEAF_DATA[:n]).hex() == CT_ROOTS_HEX[n]


@pytest.mark.parametrize("n", range(9))
def test_root_at_recovers_every_earlier_root(n):
    tree = MerkleTree(CT_LEAF_HASHES)
    assert tree.root_at(n).hex() == CT_ROOTS_HEX[n]


def test_largest_power_of_two_below_matches_brute_force():
    # The classic wrong answer, `1 << (n.bit_length() - 1)`, differs from the right one
    # for every power of two — where it returns n itself. Name the disagreement so the
    # test documents the bug it exists to catch.
    for n in range(2, 2048):
        expected = max(k for k in (1 << b for b in range(12)) if k < n)
        assert largest_power_of_two_below(n) == expected
        naive = 1 << (n.bit_length() - 1)
        if is_power_of_two(n):
            assert naive == n
            assert largest_power_of_two_below(n) == n // 2
        else:
            assert naive == expected


def test_largest_power_of_two_below_refuses_a_list_it_cannot_split():
    for n in (-1, 0, 1):
        with pytest.raises(ValueError, match="n >= 2"):
            largest_power_of_two_below(n)


@pytest.mark.parametrize(("leaf_index", "tree_size", "expected"), CT_INCLUSION_VECTORS)
def test_inclusion_proof_matches_ct_vectors(leaf_index, tree_size, expected):
    tree = MerkleTree(CT_LEAF_HASHES[:tree_size])
    proof = inclusion_proof(tree, leaf_index, tree_size)
    assert [h.hex() for h in proof] == expected
    assert [h.hex() for h in _reference_path(leaf_index, CT_LEAF_DATA[:tree_size])] == expected
    assert verify_inclusion(CT_LEAF_HASHES[leaf_index], leaf_index, tree_size, proof, tree.root)


@pytest.mark.parametrize(("first_size", "tree_size", "expected"), CT_CONSISTENCY_VECTORS)
def test_consistency_proof_matches_ct_vectors(first_size, tree_size, expected):
    tree = MerkleTree(CT_LEAF_HASHES[:tree_size])
    proof = consistency_proof(tree, first_size, tree_size)
    assert [h.hex() for h in proof] == expected
    assert [
        h.hex() for h in _reference_subproof(first_size, CT_LEAF_DATA[:tree_size], True)
    ] == expected
    assert verify_consistency(
        first_size,
        bytes.fromhex(CT_ROOTS_HEX[first_size]),
        tree_size,
        tree.root,
        proof,
    )


def test_proofs_accept_a_bare_sequence_of_leaf_hashes():
    # A verifier holding a bundle has leaf hashes, not a tree object. Making it build
    # one first would be an API that only the writer finds convenient.
    assert inclusion_proof(CT_LEAF_HASHES[:8], 5, 8) == inclusion_proof(
        MerkleTree(CT_LEAF_HASHES[:8]), 5, 8
    )
    assert consistency_proof(CT_LEAF_HASHES[:8], 6, 8) == consistency_proof(
        MerkleTree(CT_LEAF_HASHES[:8]), 6, 8
    )


# ── Negative vectors ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(("leaf_index", "tree_size", "expected"), CT_INCLUSION_VECTORS)
def test_single_byte_mutation_of_an_inclusion_proof_fails(leaf_index, tree_size, expected):
    tree = MerkleTree(CT_LEAF_HASHES[:tree_size])
    proof = inclusion_proof(tree, leaf_index, tree_size)
    for node in range(len(proof)):
        for byte in range(0, 32, 7):
            mutated = list(proof)
            corrupted = bytearray(mutated[node])
            corrupted[byte] ^= 0x01
            mutated[node] = bytes(corrupted)
            assert not verify_inclusion(
                CT_LEAF_HASHES[leaf_index], leaf_index, tree_size, mutated, tree.root
            )
    assert len(proof) == len(expected)


def test_inclusion_verification_refuses_structural_lies():
    tree = MerkleTree(CT_LEAF_HASHES[:8])
    proof = inclusion_proof(tree, 5, 8)
    # Right leaf, wrong index.
    assert not verify_inclusion(CT_LEAF_HASHES[5], 4, 8, proof, tree.root)
    # Right proof, wrong leaf.
    assert not verify_inclusion(CT_LEAF_HASHES[4], 5, 8, proof, tree.root)
    # Right everything, wrong root.
    assert not verify_inclusion(CT_LEAF_HASHES[5], 5, 8, proof, EMPTY_ROOT)
    # Index outside the tree it claims to be in.
    assert not verify_inclusion(CT_LEAF_HASHES[5], 8, 8, proof, tree.root)
    # A truncated and an over-long proof are both refusals, not "close enough".
    assert not verify_inclusion(CT_LEAF_HASHES[5], 5, 8, proof[:-1], tree.root)
    assert not verify_inclusion(CT_LEAF_HASHES[5], 5, 8, [*proof, EMPTY_ROOT], tree.root)
    # Malformed input is a False, never an exception: every byte here is adversarial.
    assert not verify_inclusion(b"\x00" * 31, 5, 8, proof, tree.root)
    assert not verify_inclusion(CT_LEAF_HASHES[5], 5, 8, [b"short"], tree.root)


def test_consistency_verification_refuses_structural_lies():
    tree = MerkleTree(CT_LEAF_HASHES[:8])
    proof = consistency_proof(tree, 6, 8)
    root6 = bytes.fromhex(CT_ROOTS_HEX[6])
    assert verify_consistency(6, root6, 8, tree.root, proof)
    assert not verify_consistency(6, tree.root, 8, tree.root, proof)
    assert not verify_consistency(5, root6, 8, tree.root, proof)
    assert not verify_consistency(6, root6, 8, root6, proof)
    assert not verify_consistency(6, root6, 8, tree.root, proof[:-1])
    # first > second is not a proof of anything; a shrinking log is the finding.
    assert not verify_consistency(8, tree.root, 6, root6, [])
    # Equal sizes: the proof is empty and the roots must match.
    assert verify_consistency(8, tree.root, 8, tree.root, [])
    assert not verify_consistency(8, tree.root, 8, tree.root, [tree.root])
    assert not verify_consistency(8, root6, 8, tree.root, [])
    # The empty prefix is trivially included, but only if it really was empty.
    assert verify_consistency(0, EMPTY_ROOT, 8, tree.root, [])
    assert not verify_consistency(0, root6, 8, tree.root, [])


def test_a_proof_does_not_authenticate_the_tree_size_only_the_checkpoint_does():
    """A measured limit of the RFC 6962-bis algorithms, recorded so nobody relies on it.

    Both verification algorithms consume ``tree_size`` only as ``tree_size - 1``, and
    the first thing they do is shift it right. So sizes that differ only in bits the
    shifts discard are indistinguishable: a proof generated at tree size 8 verifies
    unchanged when the caller *claims* tree size 7, provided the root it is checked
    against is the real one.

    This is not a defect in the algorithms and it is not something to patch locally —
    a "stricter" verifier that disagreed with every other RFC 6962 implementation
    would be worse. It is a statement about where the tree size is authenticated:
    **in the signed checkpoint body**, which carries ``tree_size`` and ``root_hash``
    together under one signature.

    Consequence for ``trappoint-verify``, checks 2 and 3: take ``tree_size`` and the
    root from the *verified checkpoint*, never from the surrounding bundle's own claim
    about which size a proof belongs to. The bundle is unsigned; the checkpoint is not.
    """
    tree = MerkleTree(CT_LEAF_HASHES[:8])
    root6 = bytes.fromhex(CT_ROOTS_HEX[6])
    proof = consistency_proof(tree, 6, 8)
    assert verify_consistency(6, root6, 8, tree.root, proof)
    assert verify_consistency(6, root6, 7, tree.root, proof)  # the measured limit

    inclusion = inclusion_proof(tree, 5, 8)
    assert verify_inclusion(CT_LEAF_HASHES[5], 5, 8, inclusion, tree.root)
    assert verify_inclusion(CT_LEAF_HASHES[5], 5, 7, inclusion, tree.root)  # same limit

    # What is NOT possible is verifying against a root that was never published. The
    # size may be fuzzy; the root never is.
    assert not verify_consistency(6, root6, 7, bytes.fromhex(CT_ROOTS_HEX[7]), proof)
    assert not verify_inclusion(CT_LEAF_HASHES[5], 5, 7, inclusion, bytes.fromhex(CT_ROOTS_HEX[7]))


def test_consistency_generation_refuses_an_empty_or_impossible_prefix():
    tree = MerkleTree(CT_LEAF_HASHES[:8])
    with pytest.raises(ValueError, match="first_size must be positive"):
        consistency_proof(tree, 0, 8)
    with pytest.raises(ValueError, match="exceeds tree_size"):
        consistency_proof(tree, 9, 8)
    with pytest.raises(ValueError, match="outside a tree"):
        inclusion_proof(tree, 8, 8)


# ── Incremental append: what the sequencer persists ───────────────────────────────────
def test_append_returns_exactly_the_nodes_that_came_into_existence():
    tree = MerkleTree()
    created: dict[NodeCoord, bytes] = {}
    for i, leaf in enumerate(CT_LEAF_HASHES):
        result = tree.append(leaf)
        assert result.leaf_index == i
        assert result.tree_size == i + 1
        assert result.root.hex() == CT_ROOTS_HEX[i + 1]
        for node in result.created_nodes:
            # A perfect node is write-once. If an append ever re-emitted one, the
            # sequencer's INSERT would collide and `ledger_node`'s append-only trigger
            # would refuse it — so this assertion is the one that keeps the ledger's
            # INSERT-only discipline achievable.
            assert node.coord not in created
            created[node.coord] = node.digest
            assert node.digest == tree.node(node.coord.level, node.coord.index)

    # Eight leaves ⇒ 4 + 2 + 1 = 7 interior nodes, and no others.
    assert len(created) == 7
    assert {c.level for c in created} == {1, 2, 3}
    assert created[NodeCoord(3, 0)].hex() == CT_ROOTS_HEX[8]


def test_extend_is_indistinguishable_from_repeated_append():
    one_at_a_time = MerkleTree()
    per_leaf_nodes = []
    for leaf in CT_LEAF_HASHES:
        per_leaf_nodes.extend(one_at_a_time.append(leaf).created_nodes)

    batched = MerkleTree()
    batch = batched.extend(CT_LEAF_HASHES)

    assert batch.first_leaf_index == 0
    assert batch.leaf_count == 8
    assert batch.tree_size == 8
    assert batch.root == one_at_a_time.root
    assert list(batch.created_nodes) == per_leaf_nodes
    assert list(batched.nodes()) == list(one_at_a_time.nodes())


def test_perfect_nodes_never_change_as_the_tree_grows():
    tree = MerkleTree(CT_LEAF_HASHES[:4])
    frozen = {(n.coord.level, n.coord.index): n.digest for n in tree.nodes()}
    tree.extend(CT_LEAF_HASHES[4:])
    for (level, index), digest in frozen.items():
        assert tree.node(level, index) == digest


def test_subtree_hash_agrees_with_the_rfc_recursion_on_every_range():
    tree = MerkleTree(CT_LEAF_HASHES)
    for start in range(9):
        for end in range(start, 9):
            expected = _reference_mth(CT_LEAF_DATA[start:end])
            assert tree.subtree_hash(start, end) == expected


def test_a_node_that_is_not_complete_is_not_available():
    from trappoint_ledger.merkle import NodeNotStored

    tree = MerkleTree(CT_LEAF_HASHES[:3])
    assert tree.node(1, 0)  # leaves 0..1 are complete
    with pytest.raises(NodeNotStored):
        tree.node(1, 1)  # leaf 3 has not arrived, so MTH(D[2:4]) does not exist
    with pytest.raises(NodeNotStored):
        tree.node(2, 0)
    with pytest.raises(ValueError, match="outside a tree"):
        tree.subtree_hash(0, 4)


def test_a_leaf_hash_must_be_a_hash():
    from trappoint_ledger.merkle import MalformedHash

    tree = MerkleTree()
    with pytest.raises(MalformedHash):
        tree.append(b"not a digest")
    with pytest.raises(MalformedHash):
        tree.append("0" * 64)  # a hex string is the classic wrong type here
    with pytest.raises(MalformedHash):
        hash_children(b"\x00" * 31, b"\x00" * 32)


# ── The dependency floor ──────────────────────────────────────────────────────────────
_IMPORT_FLOOR_PROBE = """
import sys

BLOCKED = {
    "cryptography", "boto3", "botocore", "trappoint_jcs", "pydantic",
    "numpy", "psycopg", "psycopg2", "hypothesis", "pytest",
}


class Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError("blocked by the dependency-floor probe: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())

import trappoint_ledger.chain as chain
import trappoint_ledger.merkle as merkle

assert merkle.merkle_tree_hash([]) == merkle.EMPTY_ROOT
assert merkle.Tile(0, 1234067, 256).path() == "tile/0/x001/x234/067"
assert chain.GENESIS_LINK_HASH == bytes(32)

leaked = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
assert not leaked, leaked
print("FLOOR-OK")
"""


def test_merkle_imports_with_every_third_party_module_blocked(tmp_path):
    """`trappoint_ledger.merkle` and `.chain` must import with nothing but the stdlib.

    `trappoint-verify` claims a dependency floor of `cryptography` alone to a stranger
    who is checking our log without our cooperation. It lifts these algorithms. A
    quietly added import here becomes an import there, and a claim made to a stranger
    that nobody re-tests is a claim that has already stopped being true once.
    """
    import os

    import trappoint_ledger

    src_root = Path(trappoint_ledger.__file__).resolve().parent.parent
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_FLOOR_PROBE],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(src_root)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "FLOOR-OK" in completed.stdout
