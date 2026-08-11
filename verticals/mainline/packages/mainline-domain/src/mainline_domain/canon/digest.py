# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The clause digest: ``canon_sha256``.

One function, and it is deliberately boring.  The only judgement in it is that
``canon_version`` is part of the preimage: two rows normalised under different
canonicalisers must not compare equal at the S1 exact stage, because "equal"
there means "the same clause, no adjudication required".
"""

from __future__ import annotations

import hashlib

from .version import CANON_DIGEST_DOMAIN, CANON_VERSION

__all__ = ["canon_digest", "segment_digest"]


def canon_digest(canon_text: str, canon_version: int = CANON_VERSION) -> bytes:
    """SHA-256 over ``domain || ascii(version) || 0x1F || utf8(canon_text)``.

    ``canon_version`` is an explicit parameter only so that a future
    re-normalisation migration can compute a digest under the version it is
    migrating *from*.  Production callers pass nothing.
    """
    if canon_version < 0:
        raise ValueError(f"canon_version must be non-negative, got {canon_version}")
    preimage = (
        CANON_DIGEST_DOMAIN
        + str(canon_version).encode("ascii")
        + b"\x1f"
        + canon_text.encode("utf-8")
    )
    return hashlib.sha256(preimage).digest()


def segment_digest(segment_text: str) -> bytes:
    """SHA-256 over the segment's UTF-8 bytes, with no domain prefix.

    Segments are an internal boundary artefact, not a clause identity; the
    unprefixed digest keeps them trivially reproducible by an opposing expert
    with ``sha256sum``.
    """
    return hashlib.sha256(segment_text.encode("utf-8")).digest()
