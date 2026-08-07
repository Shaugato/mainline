# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""LSH banding, and ``mainline.clause_band`` as a **pure equality join**.

The banding trade-off, stated once: a signature of 128 minima is cut into 16
bands of 8 rows; two clauses are candidates iff at least one band hashes
identically.  The probability of that is ``1 - (1 - J**8)**16``, an S-curve
whose knee sits at ``(1/16)**(1/8) = 0.7071``.  More bands buys recall, more
rows per band buys precision, and there is no third option.

**Why the table shape matters.**  ``mainline.clause_band``'s primary key is
``(site_id, band_no, band_hash, clause_uuid, commit_id)``.  Every probe binds
the first three columns to specific values, so candidate generation is sixteen
point lookups on a primary-key prefix — no inverted index, no trigram operator,
no vector search, nothing whose plan could quietly become a scan.  That is the
entire reason the design puts an LSH stage in front of the ANN stage: the cheap
stage has to be *provably* cheap, and a primary-key prefix lookup is the only
access path in CockroachDB about which that is unarguable.

**Why ``UNION ALL`` and not ``(band_no, band_hash) IN ((..),(..))``.**  The
tuple-``IN`` form is shorter and probably plans identically.  "Probably" is the
problem: sixteen separate fully-constrained selects have exactly one possible
plan shape, and this package's whole claim about S3 is that its cost does not
depend on corpus size.  :data:`BAND_PROBE_TUPLE_IN_SQL_NOTE` records the
alternative and the integration suite characterises both, so if the optimiser
is ever measured to handle the tuple form identically the change is one line
and it is a measured change rather than an assumed one.

Bands are written **once per clause version**, at ingest, and never updated:
a clause version is immutable, so its signature is immutable, so its sixteen
rows are immutable.  Writes are therefore idempotent by construction and the
insert carries ``ON CONFLICT DO NOTHING`` to say so.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from .minhash import MinHashParams, default_params
from .records import ClauseRef

__all__ = [
    "BAND_HASH_PERSON",
    "BAND_PROBE_TUPLE_IN_SQL_NOTE",
    "INSERT_BAND_SQL",
    "BandRow",
    "InMemoryBandIndex",
    "band_hashes",
    "band_probe_params",
    "band_probe_sql",
    "band_rows",
]

BAND_HASH_PERSON: Final[bytes] = b"mainline-band1"
"""``blake2b`` personalisation for the band hash.

Distinct from :data:`~.minhash.BASE_HASH_PERSON` so that a signature minimum
and a band hash can never be the same 8 bytes for the same input.  Costs
nothing; removes a whole class of "the value came from the other table"
argument.
"""

INSERT_BAND_SQL: Final[str] = """
INSERT INTO mainline.clause_band (site_id, band_no, band_hash, clause_uuid, commit_id)
VALUES (%(site_id)s, %(band_no)s, %(band_hash)s, %(clause_uuid)s, %(commit_id)s)
ON CONFLICT DO NOTHING
""".strip()
"""Idempotent by construction: a clause version's bands are a function of its text."""

BAND_PROBE_TUPLE_IN_SQL_NOTE: Final[str] = (
    "The alternative probe is a single "
    "`WHERE site_id = %(site_id)s AND (band_no, band_hash) IN ((0,%(h0)s), ...)`. "
    "It is not the default because sixteen fully-constrained selects have exactly one "
    "possible plan shape and the tuple form's is an optimiser outcome. "
    "tests/integration/algorithms/candidates/test_band_probe_sql.py runs both against a "
    "live cluster and asserts they return the same rows; if that ever also shows the same "
    "plan, switching is a one-line change and a measured one."
)


@dataclass(frozen=True, slots=True)
class BandRow:
    """One row of ``mainline.clause_band``."""

    site_id: UUID
    band_no: int
    band_hash: int
    clause_uuid: UUID
    commit_id: bytes

    def as_params(self) -> dict[str, object]:
        """Named parameters for :data:`INSERT_BAND_SQL`."""
        return {
            "site_id": str(self.site_id),
            "band_no": self.band_no,
            "band_hash": self.band_hash,
            "clause_uuid": str(self.clause_uuid),
            "commit_id": self.commit_id,
        }


def band_hashes(signature: tuple[int, ...], params: MinHashParams | None = None) -> tuple[int, ...]:
    """Fold a signature into ``bands`` signed 64-bit band hashes.

    Each band's preimage is the concatenation of its ``rows_per_band`` minima,
    **8 bytes big-endian each, in row order**.  Every minimum is less than
    ``2**61``, so 8 bytes is exact and no value is truncated.  The digest is
    read back with ``signed=True`` because CockroachDB's ``INT8`` is signed and
    a band hash that overflowed into a range the column cannot hold would fail
    at insert time on some rows and not others.
    """
    p = params if params is not None else default_params()
    if len(signature) != p.n_perms:
        raise ValueError(
            f"signature has {len(signature)} elements, permutation table declares {p.n_perms}"
        )
    rows = p.rows_per_band
    out: list[int] = []
    for band_no in range(p.bands):
        chunk = signature[band_no * rows : (band_no + 1) * rows]
        preimage = b"".join(value.to_bytes(8, "big") for value in chunk)
        digest = hashlib.blake2b(preimage, digest_size=8, person=BAND_HASH_PERSON).digest()
        out.append(int.from_bytes(digest, "big", signed=True))
    return tuple(out)


def band_rows(
    site_id: UUID,
    ref: ClauseRef,
    signature: tuple[int, ...],
    params: MinHashParams | None = None,
) -> tuple[BandRow, ...]:
    """Build the rows one clause version contributes to ``mainline.clause_band``."""
    return tuple(
        BandRow(
            site_id=site_id,
            band_no=band_no,
            band_hash=band_hash,
            clause_uuid=ref.clause_uuid,
            commit_id=ref.commit_id,
        )
        for band_no, band_hash in enumerate(band_hashes(signature, params))
    )


def band_probe_sql(n_bands: int) -> str:
    """One statement: ``n_bands`` fully-constrained selects, ``UNION ALL``'d, aggregated.

    Every arm binds ``site_id``, ``band_no`` and ``band_hash`` to a specific
    value, which is the whole primary-key prefix, so each is a point lookup.
    ``band_hits`` comes back with the rows because "shared 9 of 16 bands" is a
    recorded feature of the candidate and a far better triage signal than the
    bare fact of a collision.

    Named parameters: ``site_id``, and ``h0 … h{n_bands-1}``.  The statement is
    a pure function of ``n_bands``, so a test can assert its text.
    """
    if n_bands < 1:
        raise ValueError(f"n_bands must be >= 1, got {n_bands}")
    arms = "\n    UNION ALL\n".join(
        f"    SELECT clause_uuid, commit_id FROM mainline.clause_band\n"  # noqa: S608
        f"     WHERE site_id = %(site_id)s AND band_no = {i} AND band_hash = %(h{i})s"
        for i in range(n_bands)
    )
    return (
        "WITH hits AS (\n"
        f"{arms}\n"
        ")\n"
        "SELECT clause_uuid, commit_id, count(*)::INT8 AS band_hits\n"
        "  FROM hits\n"
        " GROUP BY clause_uuid, commit_id\n"
        " ORDER BY band_hits DESC, clause_uuid, commit_id"
    )


def band_probe_params(site_id: UUID, hashes: tuple[int, ...]) -> dict[str, object]:
    """Named parameters for :func:`band_probe_sql`, in the same order it expects."""
    params: dict[str, object] = {"site_id": str(site_id)}
    for i, value in enumerate(hashes):
        params[f"h{i}"] = value
    return params


class InMemoryBandIndex:
    """The reference implementation of the band probe.

    This is not a convenience: it is the thing the SQL is checked *against*.
    ``tests/integration/algorithms/candidates/test_band_probe_sql.py`` loads the
    same corpus into both and asserts the candidate sets are identical, so
    "the SQL does what the algorithm says" is a measured claim rather than a
    reading of the statement text.  It is also what lets every unit test in this
    package run with no cluster.
    """

    __slots__ = ("_buckets", "_params", "_site_id")

    def __init__(self, site_id: UUID, params: MinHashParams | None = None) -> None:
        self._site_id = site_id
        self._params = params if params is not None else default_params()
        self._buckets: dict[tuple[int, int], list[ClauseRef]] = {}

    @property
    def site_id(self) -> UUID:
        return self._site_id

    @property
    def bucket_count(self) -> int:
        """How many distinct ``(band_no, band_hash)`` buckets are populated."""
        return len(self._buckets)

    def add(self, ref: ClauseRef, signature: tuple[int, ...]) -> tuple[BandRow, ...]:
        """Index one clause version; returns the rows the SQL path would insert."""
        rows = band_rows(self._site_id, ref, signature, self._params)
        for row in rows:
            bucket = self._buckets.setdefault((row.band_no, row.band_hash), [])
            if ref not in bucket:
                bucket.append(ref)
        return rows

    def extend(self, items: Iterable[tuple[ClauseRef, tuple[int, ...]]]) -> None:
        for ref, sig in items:
            self.add(ref, sig)

    def probe(self, signature: tuple[int, ...]) -> Mapping[ClauseRef, int]:
        """Candidates that share at least one band, mapped to how many they share.

        Deterministically ordered: descending band hits, then
        ``(clause_uuid, commit_id)``.  A dict is returned because Python
        preserves insertion order, so the caller gets the order without having
        to know that it was sorted.
        """
        hits: dict[ClauseRef, int] = {}
        for band_no, band_hash in enumerate(band_hashes(signature, self._params)):
            for ref in self._buckets.get((band_no, band_hash), ()):
                hits[ref] = hits.get(ref, 0) + 1
        return dict(
            sorted(hits.items(), key=lambda kv: (-kv[1], kv[0].clause_uuid.bytes, kv[0].commit_id))
        )
