# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Two fingerprints, and the reason there are two rather than one.

:mod:`trappoint_migrate.attest` fingerprints the **live schema** — what the cluster
actually holds, including trigger and routine source — and appends it to a chained
ledger. That is the drift alarm and the self-attesting-gate claim, and it needs a
cluster.

This module adds the other half, which needs none:

**The tree fingerprint** hashes the *inputs* — the migration files and the seed data
that will produce a schema. `docs/leads/datamodel.md` DM-12 calls the schema+seed
fingerprint "the dev/demo/prod parity gate", and it is only a gate if it can be computed
before anything is applied. Two consequences follow immediately:

* A pull request can prove that dev, demo and prod are being asked to build the same
  thing, on a runner with no database.
* ``apply`` can record the tree fingerprint alongside the schema fingerprint, so a
  divergence is attributable to *inputs* or to *the cluster* rather than being one
  undifferentiated alarm.

**Determinism is the whole product here, so it is engineered rather than hoped for.**

* Line endings are normalised. This repository is developed on Windows and built on
  Linux; a CRLF checkout that hashed differently would make the parity gate report drift
  on every clone, and an alarm that fires for the checkout is an alarm nobody reads.
* Trailing whitespace is stripped per line and a single trailing newline is implied, so
  an editor's "trim on save" is not a schema change.
* Comments are **kept**. They carry the ``MI:`` citation and the ``RATIONALE:``; a
  fingerprint that ignored them would report parity between two trees that make
  different claims about why they exist.
* Each file's *relative POSIX path* is hashed with its content, so moving a statement
  between two files cannot leave the digest unchanged.
* Files are sorted by that relative path, so directory iteration order — which differs
  between filesystems — cannot move the digest.
* And, as with the live fingerprint, :func:`stable_tree_fingerprint` computes it twice
  and refuses when the two disagree. A fingerprint that flickers is worse than no
  fingerprint: it trains everybody to ignore the alarm.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from .attest import Attestation
from .attest import stable_fingerprint as _stable_live_fingerprint
from .errors import AttestationDrift, UsageError

__all__ = [
    "FINGERPRINT_SUFFIXES",
    "FileDigest",
    "TreeFingerprint",
    "live_fingerprint",
    "normalise",
    "stable_tree_fingerprint",
    "tree_fingerprint",
]

#: What counts as an input to the schema. ``.sql`` is the migration and seed corpus;
#: ``.j2`` is a template, whose text is an input to the rendered files a second binding
#: will produce. ``.toml`` picks up ``migrations.allocation.toml`` when a caller points
#: at it explicitly — it is never picked up by a directory walk, because the allocation
#: sits *beside* the tree rather than inside it.
FINGERPRINT_SUFFIXES: tuple[str, ...] = (".sql", ".j2", ".sql.j2")

# Domain separation, identical in intent to `attest`'s: the path and the body are joined
# by a byte that cannot occur in either, so a file named like another file's first line
# cannot produce a colliding pre-image.
_FIELD_SEPARATOR = b"\x1f"
_RECORD_SEPARATOR = b"\x1e"


@dataclass(frozen=True, slots=True)
class FileDigest:
    """One input file, addressed the way the fingerprint addresses it."""

    relpath: str
    """POSIX-relative to the root it was found under. The hashed identity of the file."""
    digest: bytes
    """SHA-256 of the file's normalised text."""
    bytes_read: int


@dataclass(frozen=True, slots=True)
class TreeFingerprint:
    """The digest of a set of schema inputs, plus what went into it."""

    digest: bytes
    files: tuple[FileDigest, ...]
    roots: tuple[str, ...]

    @property
    def hex(self) -> str:
        """The digest as lowercase hex — the form that appears in CI output."""
        return self.digest.hex()

    def by_relpath(self) -> dict[str, bytes]:
        """Relative path → per-file digest, for reporting *which* file diverged."""
        return {entry.relpath: entry.digest for entry in self.files}


def normalise(text: str) -> str:
    r"""Return *text* in the one canonical form the fingerprint hashes.

    ``\r\n`` and bare ``\r`` become ``\n``; every line loses its trailing whitespace; the
    result ends with exactly one newline when it is non-empty. Nothing else is touched —
    in particular comments, blank lines *inside* the text and indentation all survive,
    because they carry the header block and the rationale.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in unified.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _iter_inputs(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise UsageError(
            f"{root} is neither a file nor a directory. The parity gate hashes inputs "
            "that exist; a missing root would hash to the same digest as an empty one, "
            "and 'the tree is absent' must not be indistinguishable from 'the tree is empty'."
        )
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and any(path.name.endswith(s) for s in FINGERPRINT_SUFFIXES)
    )


def tree_fingerprint(roots: Sequence[Path]) -> TreeFingerprint:
    """Fingerprint every schema input under *roots*, once.

    Each root contributes files addressed relative to *itself*, so a caller may pass a
    migration tree and a seed tree together and get one digest whose per-file names stay
    readable. Two roots that resolve to the same directory are refused rather than
    double-counted — a repeated root would change the digest without changing the tree.

    Raises:
        UsageError: on a missing root, or on the same directory passed twice.
    """
    seen_roots: dict[Path, None] = {}
    entries: list[FileDigest] = []
    for root in roots:
        resolved = root.resolve()
        if resolved in seen_roots:
            raise UsageError(
                f"{root} was passed twice. A repeated root would contribute every file "
                "twice and change the digest without changing the tree."
            )
        seen_roots[resolved] = None
        base = resolved if resolved.is_dir() else resolved.parent
        for path in _iter_inputs(root):
            text = normalise(path.read_text(encoding="utf-8"))
            relpath = path.resolve().relative_to(base).as_posix()
            entries.append(
                FileDigest(
                    relpath=relpath,
                    digest=hashlib.sha256(
                        relpath.encode("utf-8") + _FIELD_SEPARATOR + text.encode("utf-8")
                    ).digest(),
                    bytes_read=len(text.encode("utf-8")),
                )
            )

    ordered = sorted(entries, key=lambda e: e.relpath)
    accumulator = hashlib.sha256()
    for entry in ordered:
        accumulator.update(entry.digest)
        accumulator.update(_RECORD_SEPARATOR)
    return TreeFingerprint(
        digest=accumulator.digest(),
        files=tuple(ordered),
        roots=tuple(str(r) for r in roots),
    )


def stable_tree_fingerprint(roots: Sequence[Path]) -> TreeFingerprint:
    """Fingerprint *roots* twice and refuse when the two computations disagree.

    The same discipline :func:`trappoint_migrate.attest.stable_fingerprint` applies to
    the live schema, applied to the inputs. It is cheap, it runs every time rather than
    only in CI, and it is the difference between "the digest is deterministic" as a claim
    and as a measurement.

    Raises:
        AttestationDrift: when the two computations differ, naming the first file whose
            per-file digest moved — because "something is non-deterministic" is not an
            actionable sentence and "this file is" is.
    """
    first = tree_fingerprint(roots)
    second = tree_fingerprint(roots)
    if first.digest == second.digest:
        return first

    left, right = first.by_relpath(), second.by_relpath()
    culprits = sorted(name for name in set(left) | set(right) if left.get(name) != right.get(name))
    named = culprits[0] if culprits else "(the file set itself changed between reads)"
    raise AttestationDrift(
        "the tree fingerprint is not stable across two consecutive computations "
        f"({first.hex[:16]}… then {second.hex[:16]}…); first divergence at {named}. "
        "Something is writing into the tree while it is being read, or normalisation is "
        "insufficient. A parity gate that flickers cannot be used as a gate."
    )


def live_fingerprint(
    conn: psycopg.Connection[Any], *, schema_prefixes: tuple[str, ...]
) -> Attestation:
    """Fingerprint the live schema, stably. One entry point, so callers do not choose.

    A thin re-export of :func:`trappoint_migrate.attest.stable_fingerprint` on purpose:
    ``fingerprint.live_fingerprint`` and ``fingerprint.tree_fingerprint`` are the two
    halves of the parity story and they should be reachable from one module, but the
    unstable single-shot :func:`trappoint_migrate.attest.fingerprint` is deliberately
    **not** re-exported here — a caller that wants the one without the stability check
    should have to say so in the module it lives in.
    """
    return _stable_live_fingerprint(conn, schema_prefixes=schema_prefixes)
