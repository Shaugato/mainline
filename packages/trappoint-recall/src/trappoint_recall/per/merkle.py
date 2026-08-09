# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""RFC 6962 Merkle tree hashing, audit paths, and path verification.

This is the Certificate Transparency tree, not "a Merkle tree": the split point is the
largest power of two strictly below ``n``, interior nodes are ``sha256(0x01 || L || R)`` and
leaves are ``sha256(0x00 || preimage)``. Two consequences matter here.

**Domain separation is the same as the custody ledger's**, so a leaf hash and an interior
hash can never collide and a PER leaf can never be presented as a ledger leaf. The custody
domain writes ``leaf_hash = SHA-256(0x00 || canon_bytes)`` (``spec/custody/ledger-schema.md``
6); this module writes the identical shape over the identical canonicalisation, which is what
lets a PER commitment be dropped into a ledger intake payload later without a second
convention to keep straight.

**The audit path is index-dependent by construction.** Verification consumes the leaf index
and the tree size to decide, at each level, whether the sibling goes on the left or the
right — so a path issued for leaf ``s+1`` does not verify at ``s+2``. That is not an accident
of this implementation; it is the property the boundary proof rests on, and
``tests/integration/recall_run/test_boundary_proof.py`` asserts it directly.

Stdlib only, on purpose. See :mod:`trappoint_recall.per.canon`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Final

from trappoint_recall.per.errors import InvalidProof

__all__ = [
    "EMPTY_ROOT",
    "LEAF_PREFIX",
    "NODE_PREFIX",
    "SHA256_BYTES",
    "audit_path",
    "merkle_root",
    "node_hash",
    "verify_audit_path",
]

#: RFC 6962 §2.1 leaf tag.
LEAF_PREFIX: Final = b"\x00"

#: RFC 6962 §2.1 interior-node tag.
NODE_PREFIX: Final = b"\x01"

#: The width of every hash in this tree. A node, a leaf or a root of any other length did not
#: come out of SHA-256, whatever the bundle claims about it.
SHA256_BYTES: Final = 32

#: The smallest tree that has a split point at all. ``MTH`` bottoms out at one leaf.
_SMALLEST_SPLITTABLE_TREE: Final = 2

#: ``MTH({}) = SHA-256()``. RFC 6962 §2.1, the hash of the empty string.
EMPTY_ROOT: Final[bytes] = hashlib.sha256(b"").digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """Return ``sha256(0x01 || left || right)``."""
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def _largest_power_of_two_below(n: int) -> int:
    """Return the ``k`` of RFC 6962 §2.1: the largest power of two strictly less than ``n``."""
    if n < _SMALLEST_SPLITTABLE_TREE:
        raise InvalidProof(f"a split point is undefined for n={n}")
    return 1 << (n - 1).bit_length() - 1


def merkle_root(leaf_hashes: Sequence[bytes]) -> bytes:
    """Return the RFC 6962 Merkle Tree Hash over ``leaf_hashes``.

    Args:
        leaf_hashes: already-tagged leaf hashes, in commitment order.

    Returns:
        The 32-byte root. For an empty sequence, :data:`EMPTY_ROOT`.
    """
    count = len(leaf_hashes)
    if count == 0:
        return EMPTY_ROOT
    if count == 1:
        return leaf_hashes[0]
    split = _largest_power_of_two_below(count)
    return node_hash(merkle_root(leaf_hashes[:split]), merkle_root(leaf_hashes[split:]))


def audit_path(index: int, leaf_hashes: Sequence[bytes]) -> tuple[bytes, ...]:
    """Return the RFC 6962 §2.1.1 audit path for ``index`` within ``leaf_hashes``.

    Args:
        index: 0-based position of the leaf being proved.
        leaf_hashes: the full, ordered leaf-hash sequence.

    Returns:
        Sibling hashes, leaf-most first.

    Raises:
        InvalidProof: if ``index`` is outside the tree.
    """
    count = len(leaf_hashes)
    if not 0 <= index < count:
        raise InvalidProof(f"leaf index {index} is outside a tree of {count} leaves")
    if count == 1:
        return ()
    split = _largest_power_of_two_below(count)
    if index < split:
        return (
            *audit_path(index, leaf_hashes[:split]),
            merkle_root(leaf_hashes[split:]),
        )
    return (
        *audit_path(index - split, leaf_hashes[split:]),
        merkle_root(leaf_hashes[:split]),
    )


def verify_audit_path(
    leaf: bytes,
    index: int,
    tree_size: int,
    path: Sequence[bytes],
    root: bytes,
) -> bool:
    """Return whether ``path`` proves ``leaf`` sits at ``index`` in a tree of ``tree_size``.

    This is RFC 6962 §2.1.1's verification algorithm written out, and it is deliberately
    total: a malformed path returns ``False`` rather than raising, because a verifier handed
    a hostile bundle should report a failed check, not crash inside it. The one exception is
    an index outside the tree, which is a caller error rather than a proof failure.

    Raises:
        InvalidProof: if ``index`` is not inside ``tree_size``.
    """
    if tree_size < 1:
        raise InvalidProof(f"tree_size must be at least 1, got {tree_size}")
    if not 0 <= index < tree_size:
        raise InvalidProof(f"leaf index {index} is outside a tree of {tree_size} leaves")
    if (
        len(leaf) != SHA256_BYTES
        or len(root) != SHA256_BYTES
        or any(len(node) != SHA256_BYTES for node in path)
    ):
        return False

    node = leaf
    fn, sn = index, tree_size - 1
    for sibling in path:
        if sn == 0:
            # The path is longer than the tree is deep: it cannot be an audit path for this
            # (index, tree_size), whatever it hashes to.
            return False
        if fn & 1 or fn == sn:
            node = node_hash(sibling, node)
            while fn != 0 and not fn & 1:
                fn >>= 1
                sn >>= 1
        else:
            node = node_hash(node, sibling)
        fn >>= 1
        sn >>= 1
    return sn == 0 and node == root
