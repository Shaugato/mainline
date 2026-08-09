# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Content addressing for the two directory trees a run is pinned to.

``skill_sha256`` and ``prompt_version`` are both "the sha256 of a directory of text
files". They are computed here, once, by :func:`tree_sha256`, because two directory
hashes that disagree about ordering or about line endings are two different claims about
what ran.

Three properties, each of which is a decision rather than a default:

* **Length-prefixed framing.** Every path and every body is preceded by its length, so
  no rename can produce the same byte stream as a different tree. Concatenating
  ``path ‖ content`` without lengths lets ``a/bc`` + ``d`` collide with ``a/b`` + ``cd``.

* **CRLF is normalised to LF before hashing.** The same reason
  ``trappoint_jcs.canon_src_sha256`` normalises: a Windows checkout with
  ``core.autocrlf=true`` and a Linux CI runner must produce the same pin, or the pin is
  a platform fingerprint rather than a content fingerprint. The cost is named: the digest
  is over the *normalised* bytes, not over the bytes on disk, so it identifies the text
  and not the file. For prompts and Markdown skills that is the right identity.

* **The exclusion list is short and explicit.** ``.git`` and ``__pycache__`` only.
  A hash that skipped "uninteresting" files would be a hash of somebody's taste.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Final

__all__ = [
    "EXCLUDED_DIRECTORY_NAMES",
    "sha256_hex",
    "tree_file_count",
    "tree_sha256",
]

#: Directory names never descended into. Deliberately two entries, not a policy.
EXCLUDED_DIRECTORY_NAMES: Final = frozenset({".git", "__pycache__"})

_FILE_TAG: Final = b"F"
_PATH_LENGTH_BYTES: Final = 4
_BODY_LENGTH_BYTES: Final = 8


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _iter_tree(root: Path, suffixes: Sequence[str] | None) -> Iterator[Path]:
    """Yield every included file under ``root``, in sorted POSIX-relative-path order."""
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in path.relative_to(root).parts):
            continue
        if suffixes is not None and path.suffix.lower() not in suffixes:
            continue
        candidates.append(path)
    yield from sorted(candidates, key=lambda p: p.relative_to(root).as_posix())


def tree_sha256(root: Path, *, suffixes: Sequence[str] | None = None) -> str:
    """Return the content digest of the directory ``root``, as lowercase hex.

    Args:
        root: the directory to hash. Must exist and be a directory.
        suffixes: when given, only files with one of these (lowercase, dot-prefixed)
            suffixes are hashed. Used by the prompt digest, where the prompt assets are
            the ``.md`` files and a stray editor artefact must not change
            ``prompt_version``.

    Returns:
        Lowercase hex SHA-256 over the length-framed, LF-normalised tree.

    Raises:
        FileNotFoundError: ``root`` does not exist or is not a directory. Deliberately
            not a silent empty digest: an empty tree and an absent tree must not hash
            the same, because "the skill was not there" and "the skill was empty" are
            different failures.
    """
    if not root.is_dir():
        raise FileNotFoundError(
            f"{root} is not a directory; an absent tree has no digest, and returning the "
            "digest of nothing would make a missing skill look like an empty one"
        )
    hasher = hashlib.sha256()
    for path in _iter_tree(root, suffixes):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        body = path.read_bytes().replace(b"\r\n", b"\n")
        hasher.update(_FILE_TAG)
        hasher.update(len(relative).to_bytes(_PATH_LENGTH_BYTES, "big"))
        hasher.update(relative)
        hasher.update(len(body).to_bytes(_BODY_LENGTH_BYTES, "big"))
        hasher.update(body)
    return hasher.hexdigest()


def tree_file_count(root: Path, *, suffixes: Sequence[str] | None = None) -> int:
    """Return how many files :func:`tree_sha256` would hash under ``root``.

    Recorded beside every digest in the attestation. A digest alone cannot tell a reader
    that the tree it covered had one file in it when it should have had nine, and a
    skill checkout that silently produced an almost-empty directory is exactly the
    failure a pinned commit is supposed to prevent.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"{root} is not a directory")
    return sum(1 for _ in _iter_tree(root, suffixes))
