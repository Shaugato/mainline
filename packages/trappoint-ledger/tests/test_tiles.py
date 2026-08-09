# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""C2SP tlog-tiles addressing: the path grammar, the geometry, and proof coverage.

The path grammar is frozen here as vectors because it is a *wire* format in the same
sense as the checkpoint: it is what a third-party verifier — or an off-the-shelf CT
tooling stack — will construct URLs with. A tile served at a path our implementation
invented is a tile nobody else can fetch.
"""

from __future__ import annotations

import pytest
from trappoint_ledger.merkle import (
    FULL_TILE_BYTES,
    TILE_HEIGHT,
    TILE_WIDTH,
    LeafRange,
    MalformedTilePath,
    MerkleTree,
    NodeCoord,
    Tile,
    TileError,
    consistency_proof_ranges,
    decode_tile_index,
    encode_tile_index,
    entry_bundle_path,
    entry_bundles_for_tree,
    hash_leaf,
    inclusion_proof_ranges,
    parse_entry_bundle_path,
    parse_tile_path,
    tile_for_node,
    tile_width_for,
    tiles_for_consistency_proof,
    tiles_for_inclusion_proof,
    tiles_for_tree,
)


def test_tile_geometry_is_the_c2sp_geometry():
    # "Each tile contains exactly 256 hashes, totaling 8,192 bytes when full."
    assert TILE_HEIGHT == 8
    assert TILE_WIDTH == 256
    assert FULL_TILE_BYTES == 8192
    assert Tile(0, 0, TILE_WIDTH).size_bytes == 8192
    assert Tile(0, 0, 3).size_bytes == 96


@pytest.mark.parametrize(
    ("index", "encoded"),
    [
        (0, "000"),
        (1, "001"),
        (255, "255"),
        (999, "999"),
        (1000, "x001/000"),
        (1001, "x001/001"),
        (999999, "x999/999"),
        (1000000, "x001/x000/000"),
        # The example given verbatim in the specification.
        (1234067, "x001/x234/067"),
    ],
)
def test_tile_index_encoding_vectors(index, encoded):
    assert encode_tile_index(index) == encoded
    assert decode_tile_index(encoded) == index


@pytest.mark.parametrize(
    "bad",
    [
        "x001/x234/67",  # final group not three digits
        "001/234",  # leading group missing its x
        "x000/001",  # redundant leading group: one tile must not have two addresses
        "xx01/000",
        "",
    ],
)
def test_tile_index_decoding_refuses_non_canonical_forms(bad):
    with pytest.raises(MalformedTilePath):
        decode_tile_index(bad)


@pytest.mark.parametrize(
    ("tile", "path"),
    [
        (Tile(0, 0, TILE_WIDTH), "tile/0/000"),
        (Tile(0, 0, 1), "tile/0/000.p/1"),
        (Tile(0, 0, 255), "tile/0/000.p/255"),
        (Tile(1, 0, TILE_WIDTH), "tile/1/000"),
        (Tile(3, 1234067, TILE_WIDTH), "tile/3/x001/x234/067"),
        (Tile(3, 1234067, 17), "tile/3/x001/x234/067.p/17"),
        (Tile(63, 0, TILE_WIDTH), "tile/63/000"),
    ],
)
def test_tile_path_vectors_round_trip(tile, path):
    assert tile.path() == path
    assert parse_tile_path(path) == tile
    assert tile.path(prefix="https://tiles.example/log/") == f"https://tiles.example/log/{path}"


def test_full_tiles_have_no_partial_suffix():
    # Accepting `.p/256` as well as the bare path would give one tile two addresses; a
    # verifier that fetched one would never see the other, which is a split view served
    # by accident rather than by malice.
    with pytest.raises(MalformedTilePath, match=r"must not carry a \.p suffix"):
        parse_tile_path("tile/0/000.p/256")


def test_entry_bundle_paths():
    assert entry_bundle_path(0) == "tile/entries/000"
    assert entry_bundle_path(1234067, 5) == "tile/entries/x001/x234/067.p/5"
    assert parse_entry_bundle_path("tile/entries/000") == (0, TILE_WIDTH)
    assert parse_entry_bundle_path("tile/entries/x001/x234/067.p/5") == (1234067, 5)
    # An entry bundle is not a hash tile, and the two carry different content types.
    with pytest.raises(MalformedTilePath, match="entry bundle"):
        parse_tile_path("tile/entries/000")
    with pytest.raises(MalformedTilePath, match="entry bundle"):
        parse_entry_bundle_path("tile/0/000")


def test_entry_bundles_for_tree():
    assert entry_bundles_for_tree(0) == []
    assert entry_bundles_for_tree(1) == [(0, 1)]
    assert entry_bundles_for_tree(256) == [(0, 256)]
    assert entry_bundles_for_tree(257) == [(0, 256), (1, 1)]
    assert entry_bundles_for_tree(600) == [(0, 256), (1, 256), (2, 88)]


def test_tile_refuses_a_shape_the_path_grammar_cannot_express():
    with pytest.raises(ValueError, match="tile level"):
        Tile(64, 0, TILE_WIDTH)
    with pytest.raises(ValueError, match="tile width"):
        Tile(0, 0, 0)
    with pytest.raises(ValueError, match="tile width"):
        Tile(0, 0, 257)
    with pytest.raises(ValueError, match="non-negative"):
        Tile(0, -1, TILE_WIDTH)


def test_tile_width_tracks_the_number_of_complete_nodes():
    # A level-8 node exists only once all 256 of its leaves are sequenced, so the tile
    # above the leaf tiles stays empty for a long time.
    assert tile_width_for(0, 0, 0) == 0
    assert tile_width_for(0, 0, 1) == 1
    assert tile_width_for(0, 0, 255) == 255
    assert tile_width_for(0, 0, 256) == TILE_WIDTH
    assert tile_width_for(0, 1, 256) == 0
    assert tile_width_for(0, 1, 300) == 44
    assert tile_width_for(1, 0, 255) == 0
    assert tile_width_for(1, 0, 256) == 1
    assert tile_width_for(1, 0, 65535) == 255
    assert tile_width_for(1, 0, 65536) == TILE_WIDTH
    assert tile_width_for(2, 0, 65536) == 1


def test_tile_for_node_maps_levels_that_are_not_multiples_of_eight_inward():
    # Level 0..7 nodes live inside a level-0 tile; the verifier rehashes the tile's own
    # hashes to rebuild them, which is why they are never served separately.
    assert tile_for_node(NodeCoord(0, 0), 1024) == Tile(0, 0, TILE_WIDTH)
    assert tile_for_node(NodeCoord(0, 300), 1024) == Tile(0, 1, TILE_WIDTH)
    assert tile_for_node(NodeCoord(7, 0), 1024) == Tile(0, 0, TILE_WIDTH)
    assert tile_for_node(NodeCoord(7, 1), 1024) == Tile(0, 0, TILE_WIDTH)
    assert tile_for_node(NodeCoord(7, 2), 1024) == Tile(0, 1, TILE_WIDTH)
    # A level-8 node is the root of a whole level-0 tile, and is served as one hash of
    # the level-1 tile.
    assert tile_for_node(NodeCoord(8, 0), 1024) == Tile(1, 0, 4)
    assert tile_for_node(NodeCoord(8, 3), 1024) == Tile(1, 0, 4)


def test_tile_for_node_refuses_a_node_the_tree_does_not_have_yet():
    with pytest.raises(TileError, match="does not exist yet"):
        tile_for_node(NodeCoord(8, 0), 255)
    with pytest.raises(TileError, match="not complete"):
        # Leaves 0..299 exist, so the level-4 node covering leaves 304..319 does not.
        tile_for_node(NodeCoord(4, 19), 300)


def _leaf_hashes(n: int) -> list[bytes]:
    return [hash_leaf(f"entry-{i}".encode()) for i in range(n)]


def _assert_tiles_cover(tiles, ranges, tree_size):
    """Every stored node the proof needs must be obtainable from one returned tile.

    "Obtainable" is not "served". A tile serves the 256 hashes at tree level ``8 * L``;
    a node at a level in between is *inside* the tile and the verifier rebuilds it by
    rehashing the tile's own hashes. So the assertion is that the tile responsible for
    each node was returned — and, for the nodes that a tile does serve directly, that
    the node really is one of its hashes.
    """
    returned = {(t.level, t.index): t for t in tiles}
    for leaf_range in ranges:
        for block in leaf_range.perfect_blocks():
            coord = block.node_coord()
            assert coord is not None
            tile = tile_for_node(coord, tree_size)
            assert (tile.level, tile.index) in returned, f"{coord!r} is in no returned tile"
            assert returned[(tile.level, tile.index)] == tile
            if coord.level % TILE_HEIGHT == 0:
                assert coord in set(tile.node_coords())
            else:
                start, end = tile.leaf_span()
                assert start <= coord.leaf_start
                assert coord.leaf_end <= end


@pytest.mark.parametrize("tree_size", [1, 2, 255, 256, 257, 512, 700, 1024, 1025])
@pytest.mark.parametrize("leaf_fraction", [0.0, 0.37, 0.99])
def test_every_inclusion_proof_node_is_inside_a_returned_tile(tree_size, leaf_fraction):
    leaf_index = min(tree_size - 1, int(tree_size * leaf_fraction))
    tiles = tiles_for_inclusion_proof(leaf_index, tree_size)

    # The leaf itself, plus every stored node each proof node decomposes into.
    ranges = [
        LeafRange(leaf_index, leaf_index + 1),
        *inclusion_proof_ranges(leaf_index, tree_size),
    ]
    _assert_tiles_cover(tiles, ranges, tree_size)

    # Tiles are deduplicated and every one of them actually exists at this tree size.
    assert len({(t.level, t.index) for t in tiles}) == len(tiles)
    for tile in tiles:
        assert tile.width == tile_width_for(tile.level, tile.index, tree_size)
        assert parse_tile_path(tile.path()) == tile


@pytest.mark.parametrize(("first_size", "tree_size"), [(1, 2), (255, 700), (256, 512), (511, 1024)])
def test_every_consistency_proof_node_is_inside_a_returned_tile(first_size, tree_size):
    tiles = tiles_for_consistency_proof(first_size, tree_size)
    _assert_tiles_cover(tiles, consistency_proof_ranges(first_size, tree_size), tree_size)


def test_tile_hashes_are_the_nodes_the_tree_actually_holds():
    # The C2SP definition, checked against our tree rather than paraphrased:
    # the i-th hash of tile (l, n) is MTH(D[(n*256+i) * 256**l : (n*256+i+1) * 256**l]).
    tree = MerkleTree(_leaf_hashes(600))
    for tile in tiles_for_tree(600):
        span = 1 << tile.tree_level
        for i, coord in enumerate(tile.node_coords()):
            start = (tile.index * TILE_WIDTH + i) * span
            assert coord == NodeCoord(tile.tree_level, tile.index * TILE_WIDTH + i)
            assert tree.node(coord.level, coord.index) == tree.subtree_hash(start, start + span)


def test_tiles_for_tree_enumerates_exactly_the_published_objects():
    assert tiles_for_tree(0) == []
    assert tiles_for_tree(1) == [Tile(0, 0, 1)]
    assert tiles_for_tree(256) == [Tile(0, 0, TILE_WIDTH), Tile(1, 0, 1)]
    assert tiles_for_tree(600) == [
        Tile(0, 0, TILE_WIDTH),
        Tile(0, 1, TILE_WIDTH),
        Tile(0, 2, 88),
        Tile(1, 0, 2),
    ]
    for tile in tiles_for_tree(70000):
        assert tile.leaf_span()[0] < 70000
        assert parse_tile_path(tile.path()) == tile
