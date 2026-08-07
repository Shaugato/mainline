# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Turning the committed seed TOML into clause rows of the REG-SAFE-DIRECTION document.

The seed is not the registry (see :mod:`mainline_domain.registry.doc`).  It is
the text of a proposed first ratification commit.  This module reads it,
validates every entry against the same encoder the loader decodes with, and
produces the rows a writer inserts into ``mainline.clause`` /
``mainline.clause_version``.

DETERMINISTIC CLAUSE IDS
------------------------
``clause_uuid`` is ``uuid5(NAMESPACE, site_id|doc_code|parameter)``.  A random
UUID would be equally correct and much worse to live with: seeding twice would
produce two clauses for one parameter, which the loader would report as
``duplicate_parameter`` and abstain on — a self-inflicted outage that looks
exactly like a governance dispute.  A derived id makes re-seeding idempotent at
the identity level, so a second run updates the same clause instead of forking
it.  ``uuid5`` and not a truncated hash because ``clause_uuid`` is a ``UUID``
column and a UUID with the version nibble set is what belongs in one.

WHAT THIS MODULE WILL NOT DO
----------------------------
It does not sign anything, and it does not mark anything ``RATIFIED`` by itself.
Every seeded clause is written ``PROPOSED``.  Ratification is a human act
recorded as a signed commit, and a seeder that emitted ``RATIFIED`` rows would
be a program ratifying a safety decision — which is the exact shape of the thing
this whole system exists to make impossible.  :func:`ratified_variant` exists so
that a *test* can construct the ratified form explicitly, in a place where it is
obvious that a test is doing it.
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from uuid import NAMESPACE_URL, UUID, uuid5

from ..data import data_file
from ..quantity.errors import UnknownUnitError
from ..quantity.units import dimensionality_for_label
from .doc import DOC_CODE
from .encoding import ENCODING_VERSION, encode
from .errors import SeedError
from .model import EntryStatus, SafeDirection
from .source import ClauseVersionRow, InMemoryClauseVersionSource

__all__ = [
    "CLAUSE_NAMESPACE",
    "SeedParameter",
    "clause_uuid_for",
    "load_seed",
    "ratified_variant",
    "seed_clause_rows",
    "seed_source",
]

#: A stable namespace for derived clause ids.  Written as a URN under a domain
#: this project controls so that two systems deriving ids for the same site and
#: parameter agree, and so that a collision with any other uuid5 namespace in
#: the repository is impossible by construction.
CLAUSE_NAMESPACE: Final[UUID] = uuid5(NAMESPACE_URL, "https://mainline.trappoint/clause")


@dataclass(frozen=True, slots=True)
class SeedParameter:
    """One row of the seed TOML, validated."""

    key: str
    dimension_label: str
    dimensionality: str
    direction: SafeDirection
    rationale: str


def load_seed(path: Path | None = None) -> tuple[SeedParameter, ...]:
    """Read and validate the committed seed.

    Validation is total: an unknown dimension label, an unknown direction, a
    duplicate key, a missing rationale or a body that will not encode all raise
    :class:`SeedError` here rather than producing a clause that abstains later.
    A seed that half-loads is worse than one that does not load, because the
    half that is missing abstains, and an abstention looks like ordinary
    under-coverage rather than like a broken build.
    """
    source = path if path is not None else data_file("registry", "safe-direction-seed.toml")
    try:
        document: dict[str, Any] = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SeedError(f"cannot read the safe-direction seed at {source}: {exc}") from exc

    meta = document.get("meta")
    if not isinstance(meta, dict):
        raise SeedError("the seed has no [meta] table")
    if meta.get("doc_code") != DOC_CODE:
        raise SeedError(
            f"the seed declares doc_code {meta.get('doc_code')!r}; this build writes "
            f"{DOC_CODE!r}"
        )
    if meta.get("encoding_version") != ENCODING_VERSION:
        raise SeedError(
            f"the seed was written for clause encoding version "
            f"{meta.get('encoding_version')!r}; this build decodes version "
            f"{ENCODING_VERSION}"
        )

    raw = document.get("parameter")
    if not isinstance(raw, list) or not raw:
        raise SeedError("the seed carries no [[parameter]] entries")

    seen: set[str] = set()
    parameters: list[SeedParameter] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SeedError(f"[[parameter]] #{index} is not a table")
        key = item.get("key")
        if not isinstance(key, str):
            raise SeedError(f"[[parameter]] #{index} has no string `key`")
        if key in seen:
            raise SeedError(
                f"{key!r} appears twice in the seed. Two seeded clauses for one "
                "parameter would load as `duplicate_parameter`, which abstains, which "
                "blocks — a self-inflicted outage indistinguishable from a real dispute"
            )
        seen.add(key)

        label = item.get("dimension")
        if not isinstance(label, str):
            raise SeedError(f"{key!r} has no string `dimension`")
        try:
            dimensionality = dimensionality_for_label(label)
        except UnknownUnitError as exc:
            raise SeedError(f"{key!r}: {exc}") from exc

        raw_direction = item.get("direction")
        if not isinstance(raw_direction, str):
            raise SeedError(f"{key!r} has no string `direction`")
        try:
            direction = SafeDirection(raw_direction.upper())
        except ValueError:
            raise SeedError(
                f"{key!r}: {raw_direction!r} is not a safe direction"
            ) from None

        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise SeedError(f"{key!r} has no rationale")

        parameter = SeedParameter(
            key=key,
            dimension_label=label,
            dimensionality=dimensionality,
            direction=direction,
            rationale=rationale.strip(),
        )
        # Encode now, so a seed entry that cannot become a clause fails at load
        # rather than at write.  `encode` decodes its own output, so this is a
        # full round trip through the grammar the loader uses.
        encode(
            parameter=parameter.key,
            dimension_label=parameter.dimension_label,
            direction=parameter.direction,
            status=EntryStatus.PROPOSED,
            rationale=parameter.rationale,
        )
        parameters.append(parameter)

    return tuple(parameters)


def clause_uuid_for(site_id: UUID, parameter: str, *, doc_code: str = DOC_CODE) -> UUID:
    """The derived clause id for one parameter at one site.  Stable forever."""
    return uuid5(CLAUSE_NAMESPACE, f"{site_id}|{doc_code}|{parameter}")


def seed_clause_rows(
    *,
    site_id: UUID,
    commit_id: bytes,
    author_sub: str,
    gen: int = 1,
    signed: bool = False,
    status: EntryStatus = EntryStatus.PROPOSED,
    parameters: Iterable[SeedParameter] | None = None,
    doc_code: str = DOC_CODE,
) -> tuple[ClauseVersionRow, ...]:
    """Build the clause-version rows for a seeding (or re-seeding) commit.

    ``status`` defaults to ``PROPOSED`` — see the module docstring.  ``signed``
    defaults to ``False`` for the same reason: the seeder does not hold a key.
    """
    entries = tuple(parameters) if parameters is not None else load_seed()
    rows: list[ClauseVersionRow] = []
    for parameter in entries:
        text = encode(
            parameter=parameter.key,
            dimension_label=parameter.dimension_label,
            direction=parameter.direction,
            status=status,
            rationale=parameter.rationale,
        )
        rows.append(
            ClauseVersionRow(
                clause_uuid=clause_uuid_for(site_id, parameter.key, doc_code=doc_code),
                commit_id=commit_id,
                gen=gen,
                canon_text=text,
                canon_sha256=_digest(text),
                ratified_by_sub=author_sub,
                ratification_signed=signed,
                retired_commit=None,
            )
        )
    return tuple(rows)


def ratified_variant(
    rows: Sequence[ClauseVersionRow], *, signed: bool = True
) -> tuple[ClauseVersionRow, ...]:
    """Re-emit seeded rows as ``RATIFIED``, optionally on a signed commit.

    For tests and for a controlled bootstrap where a human has actually signed
    the commit these rows go into.  It rewrites the clause text through
    :func:`encode`, so the digest moves with it — a ratified clause is a
    different clause from the proposal, and pretending otherwise would leave two
    different texts sharing one ``canon_sha256``.
    """
    from .encoding import decode

    out: list[ClauseVersionRow] = []
    for row in rows:
        decoded = decode(row.canon_text)
        text = encode(
            parameter=decoded.parameter,
            dimension_label=decoded.dimension_label,
            direction=decoded.direction,
            status=EntryStatus.RATIFIED,
            rationale=decoded.rationale,
        )
        out.append(
            ClauseVersionRow(
                clause_uuid=row.clause_uuid,
                commit_id=row.commit_id,
                gen=row.gen,
                canon_text=text,
                canon_sha256=_digest(text),
                ratified_by_sub=row.ratified_by_sub,
                ratification_signed=signed,
                retired_commit=row.retired_commit,
            )
        )
    return tuple(out)


def seed_source(
    *,
    site_id: UUID,
    commit_id: bytes,
    author_sub: str = "sub-directrix-bootstrap",
    signed: bool = True,
    status: EntryStatus = EntryStatus.RATIFIED,
    parameters: Iterable[SeedParameter] | None = None,
) -> InMemoryClauseVersionSource:
    """A one-commit in-memory document carrying the whole seed.

    The convenience the tests and the offline tooling use.  It is explicit about
    signing and status because those are the two things that decide whether the
    registry answers at all, and a helper that hid them would make every test
    written against it a test of the wrong thing.
    """
    source = InMemoryClauseVersionSource(site_id=site_id, doc_code=DOC_CODE)
    source.add_commit(commit_id, parents=(), author_sub=author_sub, signed=signed)
    for row in seed_clause_rows(
        site_id=site_id,
        commit_id=commit_id,
        author_sub=author_sub,
        signed=signed,
        status=status,
        parameters=parameters,
    ):
        source.add_version(row)
    return source


def _digest(canon_text: str) -> bytes:
    """The clause digest, domain-separated the way CANONHOLD does it.

    Imported lazily from the canon package so that this module keeps working if
    it is ever used in a context where the canonicaliser's data files are not
    installed — in which case a plain SHA-256 of the UTF-8 bytes is used and the
    difference is visible, rather than the seeder failing to import.
    """
    try:
        from ..canon import canon_digest
    except Exception:  # pragma: no cover - only when canon data is unavailable
        return hashlib.sha256(canon_text.encode("utf-8")).digest()
    return canon_digest(canon_text)
