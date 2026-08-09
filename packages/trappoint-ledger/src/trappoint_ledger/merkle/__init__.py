# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint_ledger.merkle`` — RFC 6962 tree, proofs, and C2SP tlog-tiles addressing.

The published interface of this subpackage is consumed by the sequencer (which appends
and persists ``ledger_node`` rows), by ``trappoint-verify`` (which verifies proofs it
was handed by a stranger), and by the witness (which verifies a consistency proof from
its own last state before cosigning).

**Dependency floor.** Everything reachable from this import — ``tree``, ``proof``,
``tiles`` — imports ``hashlib``, ``re``, ``dataclasses``, ``typing`` and
``collections.abc``, and nothing else. Not ``cryptography``, not ``trappoint_jcs``, not
this package's own siblings. That is deliberate and it is tested
(``tests/test_merkle_vectors.py::test_merkle_imports_with_every_third_party_module_blocked``):
the verifier's one-dependency claim is only worth something if the algorithms it lifts
carry no dependencies of their own, and an opposing expert reimplementing this in Rust
should have to reproduce a hash function and nothing more.
"""

from __future__ import annotations

from trappoint_ledger.merkle.proof import (
    HashSource,
    LeafRange,
    consistency_proof,
    consistency_proof_ranges,
    inclusion_proof,
    inclusion_proof_ranges,
    verify_consistency,
    verify_inclusion,
)
from trappoint_ledger.merkle.tiles import (
    FULL_TILE_BYTES,
    TILE_HEIGHT,
    TILE_WIDTH,
    MalformedTilePath,
    Tile,
    TileError,
    decode_tile_index,
    encode_tile_index,
    entry_bundle_path,
    entry_bundles_for_tree,
    parse_entry_bundle_path,
    parse_tile_path,
    tile_for_node,
    tile_width_for,
    tiles_for_consistency_proof,
    tiles_for_inclusion_proof,
    tiles_for_ranges,
    tiles_for_tree,
)
from trappoint_ledger.merkle.tree import (
    EMPTY_ROOT,
    HASH_BYTES,
    LEAF_PREFIX,
    NODE_PREFIX,
    AppendResult,
    BatchAppendResult,
    MalformedHash,
    MerkleError,
    MerkleTree,
    Node,
    NodeCoord,
    NodeNotStored,
    hash_children,
    hash_leaf,
    is_power_of_two,
    largest_power_of_two_below,
    merkle_tree_hash,
)

__all__ = [
    "EMPTY_ROOT",
    "FULL_TILE_BYTES",
    "HASH_BYTES",
    "LEAF_PREFIX",
    "NODE_PREFIX",
    "TILE_HEIGHT",
    "TILE_WIDTH",
    "AppendResult",
    "BatchAppendResult",
    "HashSource",
    "LeafRange",
    "MalformedHash",
    "MalformedTilePath",
    "MerkleError",
    "MerkleTree",
    "Node",
    "NodeCoord",
    "NodeNotStored",
    "Tile",
    "TileError",
    "consistency_proof",
    "consistency_proof_ranges",
    "decode_tile_index",
    "encode_tile_index",
    "entry_bundle_path",
    "entry_bundles_for_tree",
    "hash_children",
    "hash_leaf",
    "inclusion_proof",
    "inclusion_proof_ranges",
    "is_power_of_two",
    "largest_power_of_two_below",
    "merkle_tree_hash",
    "parse_entry_bundle_path",
    "parse_tile_path",
    "tile_for_node",
    "tile_width_for",
    "tiles_for_consistency_proof",
    "tiles_for_inclusion_proof",
    "tiles_for_ranges",
    "tiles_for_tree",
    "verify_consistency",
    "verify_inclusion",
]
