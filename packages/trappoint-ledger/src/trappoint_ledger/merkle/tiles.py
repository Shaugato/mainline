# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""C2SP ``tlog-tiles`` addressing — the static surface a verifier reads instead of us.

`tlog-tiles <https://c2sp.org/tlog-tiles>`_ serves a transparency log as immutable
static files. Quoting the specification:

    the *n*-th tile at level *l*, with *n* and *l* starting at 0, is the sequence of the
    following Merkle Tree Hashes, with *i* from 0 to 255:
    ``MTH(D[(n * 256 + i) * 256**l : (n * 256 + i + 1) * 256**l])``

    a tile represents the entire subtree of height 8 with its hashes as the leaves. The
    Merkle Tree levels between those expressed by the tile hashes are reconstructed by
    hashing the leaves.

    all Merkle tree cryptographic operations are as specified by RFC 6962, so these APIs
    can be thought of as an alternative encoding format for the same data.

So tile ``(l, n)`` holds the hashes of :class:`~trappoint_ledger.merkle.tree.NodeCoord`
``(8 * l, n * 256 + i)`` for ``i`` in ``[0, width)`` — 256 hashes, 8192 bytes, when
full. Levels of the RFC 6962 tree that are not multiples of eight are never served:
a verifier rebuilds them from the tile it already fetched.

Why this exists at all, in one sentence
---------------------------------------
Serving proofs from static objects in S3 + CloudFront means **the public verification
surface is not our database and not our application code**, so a verifier cannot be
handed a targeted view — the split-view attack needs our code in the request path, and
here there is none. (That is a necessary condition, not a sufficient one: split-view
resistance is only claimed once an adverse witness cosigns, which today it does not.
See ``spec/custody/checks.yaml`` check 7, marked ``implemented_but_not_adverse``.)

Paths
-----
Hash tiles are served at ``<prefix>/tile/<L>/<N>[.p/<W>]``; entry bundles at
``<prefix>/tile/entries/<N>[.p/<W>]``. ``<L>`` is a decimal integer from 0 to 63 with
no leading zeroes; ``<W>`` runs from 1 to 255 and appears only for a partial tile; ``<N>`` is
encoded as three-digit groups where every group but the last carries an ``x`` prefix,
so index 1234067 is ``x001/x234/067``. That encoding exists so a log with billions of
entries does not put millions of objects in one directory.

This module is index arithmetic and string formatting. It performs no IO, fetches
nothing, and imports nothing outside this package.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from trappoint_ledger.merkle.proof import (
    LeafRange,
    consistency_proof_ranges,
    inclusion_proof_ranges,
)
from trappoint_ledger.merkle.tree import HASH_BYTES, NodeCoord

#: Tile height: each tile spans 8 levels of the RFC 6962 tree. Fixed by tlog-tiles.
TILE_HEIGHT: Final = 8

#: Hashes in a full tile: ``2 ** TILE_HEIGHT``.
TILE_WIDTH: Final = 1 << TILE_HEIGHT

#: Bytes in a full hash tile: 256 * 32 = 8192.
FULL_TILE_BYTES: Final = TILE_WIDTH * HASH_BYTES

#: Highest tile level the path grammar admits (``<L>`` runs from 0 to 63).
MAX_TILE_LEVEL: Final = 63

_INDEX_GROUP = re.compile(r"\A[0-9]{3}\Z")
_PREFIXED_GROUP = re.compile(r"\Ax[0-9]{3}\Z")
_PATH = re.compile(
    r"\Atile/(?P<level>entries|0|[1-9][0-9]?)/"
    r"(?P<index>[0-9x/]+?)(?:\.p/(?P<width>[1-9][0-9]{0,2}))?\Z"
)


class TileError(Exception):
    """Base class for tile addressing refusals."""


class MalformedTilePath(TileError):
    """A string was offered as a tile path and is not one."""


def encode_tile_index(index: int) -> str:
    """Return the tlog-tiles path encoding of ``index``.

    Three-digit zero-padded groups, most significant first, every group but the last
    prefixed with ``x``. ``1234067`` becomes ``x001/x234/067``; ``0`` becomes ``000``.
    """
    if index < 0:
        raise ValueError(f"tile index is non-negative, got {index}")
    groups = [f"{index % 1000:03d}"]
    index //= 1000
    while index > 0:
        groups.append(f"x{index % 1000:03d}")
        index //= 1000
    groups.reverse()
    return "/".join(groups)


def decode_tile_index(encoded: str) -> int:
    """Return the integer index for a tlog-tiles encoded index, refusing sloppy forms.

    Every group is exactly three digits, only the last group is unprefixed, and a
    multi-group encoding may not have a zero leading group — ``x000/001`` is not the
    encoding of 1, and accepting it would give one tile two addresses.
    """
    groups = encoded.split("/")
    if not groups:
        raise MalformedTilePath(f"empty tile index: {encoded!r}")
    if not _INDEX_GROUP.match(groups[-1]):
        raise MalformedTilePath(f"final tile index group must be three digits: {encoded!r}")
    for group in groups[:-1]:
        if not _PREFIXED_GROUP.match(group):
            raise MalformedTilePath(
                f"leading tile index groups are 'x' + three digits: {encoded!r}"
            )
    if len(groups) > 1 and groups[0] == "x000":
        raise MalformedTilePath(f"tile index has a redundant leading group: {encoded!r}")
    value = 0
    for group in groups:
        value = value * 1000 + int(group.lstrip("x"))
    return value


@dataclass(frozen=True, slots=True)
class Tile:
    """One tlog-tiles hash tile: up to 256 consecutive node hashes at tree level ``8 * level``."""

    level: int
    index: int
    width: int

    def __post_init__(self) -> None:
        """Refuse a tile the path grammar could not express."""
        if not 0 <= self.level <= MAX_TILE_LEVEL:
            raise ValueError(f"tile level must be 0..{MAX_TILE_LEVEL}, got {self.level}")
        if self.index < 0:
            raise ValueError(f"tile index is non-negative, got {self.index}")
        if not 1 <= self.width <= TILE_WIDTH:
            raise ValueError(f"tile width must be 1..{TILE_WIDTH}, got {self.width}")

    @property
    def is_full(self) -> bool:
        """Return whether the tile carries all 256 hashes (so has no ``.p/<W>`` suffix)."""
        return self.width == TILE_WIDTH

    @property
    def tree_level(self) -> int:
        """Return the RFC 6962 level whose nodes this tile carries: ``8 * level``."""
        return self.level * TILE_HEIGHT

    @property
    def first_node_index(self) -> int:
        """Return the index, within :attr:`tree_level`, of this tile's first hash."""
        return self.index * TILE_WIDTH

    @property
    def size_bytes(self) -> int:
        """Return the exact byte length of the served object."""
        return self.width * HASH_BYTES

    def node_coords(self) -> tuple[NodeCoord, ...]:
        """Return the node coordinates of this tile's hashes, in served order."""
        base = self.first_node_index
        return tuple(NodeCoord(self.tree_level, base + i) for i in range(self.width))

    def leaf_span(self) -> tuple[int, int]:
        """Return the half-open leaf range ``[start, end)`` this tile's hashes cover."""
        leaves_per_hash = 1 << self.tree_level
        start = self.first_node_index * leaves_per_hash
        return start, start + self.width * leaves_per_hash

    def contains(self, coord: NodeCoord) -> bool:
        """Return whether ``coord`` is one of this tile's hashes."""
        return (
            coord.level == self.tree_level
            and self.first_node_index <= coord.index < self.first_node_index + self.width
        )

    def path(self, prefix: str = "") -> str:
        """Return the tlog-tiles path for this tile, optionally under ``prefix``."""
        suffix = "" if self.is_full else f".p/{self.width}"
        path = f"tile/{self.level}/{encode_tile_index(self.index)}{suffix}"
        return f"{prefix.rstrip('/')}/{path}" if prefix else path


def parse_tile_path(path: str) -> Tile:
    """Return the :class:`Tile` a hash-tile path names, refusing entry-bundle paths.

    Entry bundles live at ``tile/entries/<N>``; they carry log entries rather than
    hashes, so they are not :class:`Tile` values. Use :func:`parse_entry_bundle_path`.
    """
    match = _PATH.match(path.strip("/"))
    if match is None:
        raise MalformedTilePath(f"not a tlog-tiles path: {path!r}")
    if match.group("level") == "entries":
        raise MalformedTilePath(f"{path!r} is an entry bundle, not a hash tile")
    if match.group("width") is None:
        width = TILE_WIDTH
    else:
        width = int(match.group("width"))
        if width == TILE_WIDTH:
            # A full tile has no `.p/<W>`. Accepting both spellings would give one tile
            # two addresses, and a verifier that fetched one would not notice the other.
            raise MalformedTilePath(f"a full tile must not carry a .p suffix: {path!r}")
    return Tile(
        level=int(match.group("level")),
        index=decode_tile_index(match.group("index")),
        width=width,
    )


def entry_bundle_path(index: int, width: int = TILE_WIDTH, prefix: str = "") -> str:
    """Return the tlog-tiles path of the entry bundle holding leaves ``[index*256, …)``."""
    if not 1 <= width <= TILE_WIDTH:
        raise ValueError(f"entry bundle width must be 1..{TILE_WIDTH}, got {width}")
    suffix = "" if width == TILE_WIDTH else f".p/{width}"
    path = f"tile/entries/{encode_tile_index(index)}{suffix}"
    return f"{prefix.rstrip('/')}/{path}" if prefix else path


def parse_entry_bundle_path(path: str) -> tuple[int, int]:
    """Return ``(index, width)`` for an entry-bundle path."""
    match = _PATH.match(path.strip("/"))
    if match is None or match.group("level") != "entries":
        raise MalformedTilePath(f"not a tlog-tiles entry bundle path: {path!r}")
    if match.group("width") is None:
        return decode_tile_index(match.group("index")), TILE_WIDTH
    width = int(match.group("width"))
    if not 1 <= width < TILE_WIDTH:
        raise MalformedTilePath(
            f"a partial entry bundle width must be 1..{TILE_WIDTH - 1}: {path!r}"
        )
    return decode_tile_index(match.group("index")), width


def entry_bundles_for_tree(tree_size: int) -> list[tuple[int, int]]:
    """Return ``(index, width)`` for every entry bundle a log of ``tree_size`` serves."""
    if tree_size < 0:
        raise ValueError(f"tree_size is non-negative, got {tree_size}")
    full, remainder = divmod(tree_size, TILE_WIDTH)
    bundles = [(i, TILE_WIDTH) for i in range(full)]
    if remainder:
        bundles.append((full, remainder))
    return bundles


def tile_width_for(tile_level: int, tile_index: int, tree_size: int) -> int:
    """Return how many hashes tile ``(tile_level, tile_index)`` has at ``tree_size`` leaves.

    Zero means the tile does not exist yet: a node at tree level ``8 * tile_level``
    exists only once all ``2 ** (8 * tile_level)`` of its leaves have been sequenced,
    so the count of complete nodes at that level is ``tree_size >> (8 * tile_level)``.
    """
    if tile_level < 0 or tile_index < 0 or tree_size < 0:
        raise ValueError("tile coordinates and tree_size are non-negative")
    complete_nodes = tree_size >> (tile_level * TILE_HEIGHT)
    available = complete_nodes - tile_index * TILE_WIDTH
    if available <= 0:
        return 0
    return min(TILE_WIDTH, available)


def tile_for_node(coord: NodeCoord, tree_size: int) -> Tile:
    """Return the tile a verifier fetches in order to obtain ``coord``.

    A node whose level is a multiple of eight is one of the tile's own hashes. A node
    at any other level lies *strictly inside* a tile — the tile's hashes are the leaves
    of the height-8 subtree containing it, and the verifier rehashes them to rebuild
    it. Such a node can never straddle two tiles: it spans ``2 ** (level % 8) <= 128``
    consecutive level-``8l`` nodes starting at a multiple of that span, and 256 is
    divisible by it.
    """
    tile_level = coord.level // TILE_HEIGHT
    within_level_index = coord.index << (coord.level % TILE_HEIGHT)
    tile_index = within_level_index // TILE_WIDTH
    width = tile_width_for(tile_level, tile_index, tree_size)
    if width == 0:
        raise TileError(
            f"node {coord!r} is not in a tree of size {tree_size}: "
            f"tile (level={tile_level}, index={tile_index}) does not exist yet"
        )
    covered = within_level_index - tile_index * TILE_WIDTH + (1 << (coord.level % TILE_HEIGHT))
    if covered > width:
        raise TileError(
            f"node {coord!r} is not complete in a tree of size {tree_size}: "
            f"tile (level={tile_level}, index={tile_index}) has width {width}"
        )
    return Tile(level=tile_level, index=tile_index, width=width)


def tiles_for_ranges(ranges: Sequence[LeafRange], tree_size: int) -> list[Tile]:
    """Return the deduplicated tiles covering every stored node the ranges resolve to."""
    seen: dict[tuple[int, int], Tile] = {}
    for leaf_range in ranges:
        for block in leaf_range.perfect_blocks():
            coord = block.node_coord()
            if coord is None:  # pragma: no cover — perfect_blocks() only yields perfect ranges.
                raise TileError(f"{block!r} did not decompose into stored nodes")
            tile = tile_for_node(coord, tree_size)
            seen[(tile.level, tile.index)] = tile
    return [seen[key] for key in sorted(seen)]


def tiles_for_inclusion_proof(leaf_index: int, tree_size: int) -> list[Tile]:
    """Return every hash tile a verifier needs to check leaf ``leaf_index`` at ``tree_size``.

    The leaf's own hash is included: a tile-based verifier fetches the entry bundle for
    the record's bytes and the level-0 tile for the hash it must reproduce, and a proof
    it cannot anchor to a leaf hash proves nothing about the record.
    """
    ranges = [LeafRange(leaf_index, leaf_index + 1), *inclusion_proof_ranges(leaf_index, tree_size)]
    return tiles_for_ranges(ranges, tree_size)


def tiles_for_consistency_proof(first_size: int, tree_size: int) -> list[Tile]:
    """Return every hash tile a verifier needs for the ``first_size`` → ``tree_size`` proof."""
    return tiles_for_ranges(consistency_proof_ranges(first_size, tree_size), tree_size)


def tiles_for_tree(tree_size: int) -> list[Tile]:
    """Return every hash tile a log of ``tree_size`` leaves publishes, lowest level first.

    This is what the anchor fan-out uploads. A partial tile is republished as it grows
    and is replaced by the full tile once complete; only the full tiles are immutable,
    which is why a verifier must pin the ``tree_size`` it fetched at and why a
    checkpoint — not a tile — is the thing that gets signed.
    """
    if tree_size < 0:
        raise ValueError(f"tree_size is non-negative, got {tree_size}")
    tiles: list[Tile] = []
    tile_level = 0
    while True:
        complete_nodes = tree_size >> (tile_level * TILE_HEIGHT)
        if complete_nodes == 0:
            break
        full, remainder = divmod(complete_nodes, TILE_WIDTH)
        tiles.extend(Tile(tile_level, i, TILE_WIDTH) for i in range(full))
        if remainder:
            tiles.append(Tile(tile_level, full, remainder))
        tile_level += 1
    return tiles
