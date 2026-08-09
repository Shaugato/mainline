# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""``index_fingerprint`` — the only structural tripwire this platform gives us.

The problem, stated exactly
---------------------------
``INSPECT`` skips vector indexes. Nothing in CockroachDB will tell us that a C-SPANN tree was
re-partitioned, rebuilt or silently degraded between the run that scored a corpus and the
exhibit that quotes that run's silence. A certificate that said "coverage was complete" while
the tree underneath it had changed would be worse than no certificate: it would be an
assurance with nothing behind it.

So the certificate carries a digest over everything observable about the index's *structure*
at run time, and a later mismatch turns the certificate from evidence into a question. That
is the correct failure direction, and it is why ``recall_certificate.coverage_basis`` has a
``'fingerprint_mismatch'`` value at all.

What goes into it, and why each one
-----------------------------------
=======================  ====================================================================
``index_generation``     The generation string carried on every cue row. A rebuild changes it.
``embed_model``          A different encoder is a different geometry; the same tree searched
                         with vectors from another model is not the same search.
``taxonomy_ver``         The prefix values *are* the taxonomy. Re-inducting level 1 is a
                         re-partition, not a relabelling (ARCHITECTURE 5.4).
``arm_set_digest``       Which trees were searched at all, at what ``k`` and what weight.
``prefix tree counts``   Row count per searched prefix. A tree that lost or gained rows
                         between the run and the exhibit did not hold the corpus the receipt
                         describes.
=======================  ====================================================================

Serialisation is a frozen, line-oriented, field-tagged text format rather than JSON — the
same convention ``trappoint_recall.arms.digest`` uses for the plan skeleton — so that the
preimage is legible in a diff and reproducible by a stranger without a canonicalisation
library. Every field is length-prefixed against separator injection: a prefix *value* that
contained ``\\x1e`` could otherwise be crafted to collide with a different tree list.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from trappoint_recall.horizon.errors import UncountableCorpus

__all__ = [
    "FINGERPRINT_DOMAIN",
    "IndexFingerprintInput",
    "PrefixTree",
    "fingerprint_preimage",
    "index_fingerprint",
    "trees_from_counts",
]

#: Domain separation. Present so this digest can never be confused with the plan-skeleton
#: digest, the arm-policy digest or a Merkle node, all of which are also SHA-256 over text.
FINGERPRINT_DOMAIN: Final = b"trappoint-recall/index-fingerprint/v1\n"

#: ASCII record separator, matching ``trappoint_recall.arms.digest``.
_RECORD: Final = "\x1e"

#: ASCII unit separator, for fields within a record.
_UNIT: Final = "\x1f"


def _field(name: str, value: str) -> str:
    """One length-prefixed ``name=value`` field. The length is what defeats injection."""
    return f"{name}{_UNIT}{len(value)}{_UNIT}{value}"


@dataclass(frozen=True, slots=True)
class PrefixTree:
    """One searched C-SPANN tree: the table, the bound prefix, and how many rows it held."""

    table: str
    prefix: tuple[tuple[str, str], ...]
    row_count: int | None

    def __post_init__(self) -> None:
        """Refuse a shape that could not have come from an executed arm."""
        if not self.table:
            raise UncountableCorpus("a prefix tree must name its table")
        if self.row_count is not None and self.row_count < 0:
            raise UncountableCorpus(
                f"{self.table}: row_count {self.row_count} is negative; an unknown count is "
                "None, which is a different fact and hashes differently"
            )

    @property
    def counted(self) -> bool:
        """Whether the row count is known. An unknown count forces ``UNDETERMINED``."""
        return self.row_count is not None

    def key(self) -> str:
        """Return a stable ordering key: table, then the bound prefix in column order."""
        return self.table + _UNIT + _UNIT.join(f"{column}={value}" for column, value in self.prefix)

    def record(self) -> str:
        """Render the line this tree contributes to the preimage."""
        if self.row_count is None:
            raise UncountableCorpus(
                f"{self.key()} has no row count; a fingerprint over an unknown is a "
                "fingerprint of nothing"
            )
        parts = [_field("table", self.table)]
        parts.extend(_field(f"prefix:{column}", value) for column, value in self.prefix)
        parts.append(_field("rows", str(self.row_count)))
        return _UNIT.join(parts)


@dataclass(frozen=True, slots=True)
class IndexFingerprintInput:
    """Everything the fingerprint is taken over."""

    index_generation: str
    embed_model: str
    taxonomy_ver: int
    arm_set_digest: str
    prefix_trees: tuple[PrefixTree, ...]

    def __post_init__(self) -> None:
        """Refuse an input missing a component the fingerprint claims to cover."""
        for name in ("index_generation", "embed_model", "arm_set_digest"):
            if not getattr(self, name):
                raise UncountableCorpus(
                    f"{name} is empty; the fingerprint would not distinguish two runs that "
                    "differed in exactly that respect"
                )

    @property
    def fully_counted(self) -> bool:
        """Whether every searched tree reported a row count."""
        return all(tree.counted for tree in self.prefix_trees)

    def uncounted(self) -> tuple[str, ...]:
        """Return the keys of the trees whose row counts are unknown."""
        return tuple(tree.key() for tree in self.prefix_trees if not tree.counted)


def fingerprint_preimage(document: IndexFingerprintInput) -> bytes:
    """Return the exact bytes hashed, so a stranger can inspect them and not just the digest.

    Raises:
        UncountableCorpus: if any searched tree has no row count.
    """
    if not document.fully_counted:
        raise UncountableCorpus(
            "cannot fingerprint an index whose prefix trees were not counted: "
            + ", ".join(document.uncounted())
        )
    header = _RECORD.join(
        (
            _field("index_generation", document.index_generation),
            _field("embed_model", document.embed_model),
            _field("taxonomy_ver", str(document.taxonomy_ver)),
            _field("arm_set_digest", document.arm_set_digest),
            _field("n_trees", str(len(document.prefix_trees))),
        )
    )
    trees = sorted(document.prefix_trees, key=PrefixTree.key)
    body = _RECORD.join(tree.record() for tree in trees)
    text = header if not trees else header + _RECORD + body
    return FINGERPRINT_DOMAIN + text.encode("utf-8") + b"\n"


def index_fingerprint(document: IndexFingerprintInput) -> bytes:
    """SHA-256 over :func:`fingerprint_preimage`. 32 bytes, straight into ``BYTES``.

    Raises:
        UncountableCorpus: if any searched tree has no row count.
    """
    return hashlib.sha256(fingerprint_preimage(document)).digest()


def trees_from_counts(
    table: str,
    prefixes: Sequence[tuple[tuple[tuple[str, str], ...], int | None]],
) -> tuple[PrefixTree, ...]:
    """Build a tree tuple for one table from ``(prefix, count)`` pairs."""
    return tuple(
        PrefixTree(table=table, prefix=prefix, row_count=count) for prefix, count in prefixes
    )
