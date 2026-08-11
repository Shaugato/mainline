# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixture provenance, and the one rule that must never be broken by convenience.

**Real corpora are for the harness. The demo tenant is synthetic. A real fatality is
never presented as a fictional site's record.**

That sentence is a promise made to the families of the people in those reports, and a
promise a build system can keep only if it is mechanised. So every corpus artefact this
package reads or writes carries a :class:`FixtureProvenance` block, and the combination
``corpus_class='real_regulator'`` with ``tenant_use='demo_tenant'`` is refused at
construction time — not warned about, not linted, refused.

Why a field rather than a directory convention
-----------------------------------------------
A directory convention is a habit, and habits are what get broken at 2 a.m. before a
demo. A field travels with the data through every copy, every merge and every rebuild,
and :func:`assert_harness_only` can be called from anywhere that is about to put a
record in front of an audience.

The three axes
--------------
``corpus_class``  what the bytes actually are.
``tenant_use``    the only audience they may reach.
``licence``       what a redistributor is allowed to do with them, since the MSHA and
                  CSB material is US federal work product and the AU regulator material
                  is not, and the difference matters before anything is committed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "CorpusClass",
    "DemoTenantContamination",
    "FixtureProvenance",
    "FixtureRef",
    "ProvenanceError",
    "ProvenanceManifest",
    "TenantUse",
    "assert_harness_only",
    "file_sha256",
    "load_provenance_manifest",
]

CorpusClass = Literal["real_regulator", "synthetic_replica", "synthetic_permit"]
"""``real_regulator``: bytes that came from MSHA / CSB / a state regulator.
``synthetic_replica``: invented records shaped like a real corpus, for hermetic CI.
``synthetic_permit``: invented permits — no real permit corpus exists to draw from."""

TenantUse = Literal["harness_only", "demo_tenant", "either"]
"""``harness_only`` is the only value a ``real_regulator`` corpus may carry."""

_REAL: Final = "real_regulator"
_DEMO: Final = "demo_tenant"


class ProvenanceError(ValueError):
    """Raised when a provenance manifest is missing, malformed or inconsistent."""


class DemoTenantContamination(RuntimeError):
    """Raised when real regulator data is about to be shown as a fictional site's record.

    This is deliberately a ``RuntimeError`` and not a ``ValueError``: it is not a bad
    argument, it is a category of thing that must not happen.
    """


class FixtureProvenance(BaseModel):
    """Where a corpus artefact came from and who may be shown it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_class: Annotated[
        CorpusClass, Field(description="What the bytes are: real regulator data, or invented.")
    ]
    tenant_use: Annotated[
        TenantUse,
        Field(
            description=(
                "The only audience these bytes may reach. Real regulator data is "
                "harness_only, always, with no exception and no override flag."
            )
        ),
    ]
    source_name: Annotated[
        str, Field(min_length=1, description="Human name of the corpus, e.g. 'MSHA Part 50'.")
    ]
    source_url: Annotated[
        str | None, Field(description="Canonical URL, when the corpus has one.")
    ] = None
    licence: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "SPDX identifier or a plain-language statement. US federal work product "
                "is public domain; AU regulator material is not, and is referenced rather "
                "than redistributed."
            ),
        ),
    ]
    retrieved_at: Annotated[
        datetime | None,
        Field(description="When the bytes were fetched. None for anything never fetched."),
    ] = None
    generator: Annotated[
        str | None,
        Field(description="For synthetic artefacts: the module and seed that produced them."),
    ] = None
    notes: Annotated[str, Field(description="Anything a reader needs before believing it.")] = ""

    @model_validator(mode="after")
    def _real_data_is_harness_only(self) -> FixtureProvenance:
        if self.corpus_class == _REAL and self.tenant_use != "harness_only":
            raise ValueError(
                f"{self.source_name}: corpus_class='real_regulator' with "
                f"tenant_use={self.tenant_use!r} is refused. Real regulator data — every "
                "record of which is somebody's death or injury — is for the evaluation "
                "harness only. The demo tenant is synthetic, and presenting a real "
                "fatality as a fictional site's record is the one thing this build must "
                "never do."
            )
        if self.corpus_class != _REAL and self.retrieved_at is not None:
            raise ValueError(
                f"{self.source_name}: a synthetic artefact carries retrieved_at, which "
                "would let it be mistaken for something that was downloaded. Use "
                "'generator' instead."
            )
        if self.corpus_class != _REAL and not self.generator:
            raise ValueError(
                f"{self.source_name}: a synthetic artefact must name its generator and "
                "seed, otherwise it cannot be regenerated and diffed"
            )
        return self

    @property
    def is_real(self) -> bool:
        return self.corpus_class == _REAL

    @property
    def demo_safe(self) -> bool:
        """True only when these bytes may be shown as a fictional site's record."""
        return not self.is_real and self.tenant_use in ("demo_tenant", "either")


class FixtureRef(BaseModel):
    """One committed file, its digest, and the provenance of its contents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: Annotated[str, Field(min_length=1, description="Path relative to the manifest.")]
    sha256: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{64}$", description="Digest of the bytes as committed."),
    ]
    bytes: Annotated[int, Field(ge=0, description="Size, so a truncated checkout is visible.")]
    records: Annotated[
        int | None, Field(ge=0, description="Record count, when the file has records.")
    ] = None
    role: Annotated[str, Field(min_length=1, description="What the build uses this file for.")]
    provenance: FixtureProvenance


class ProvenanceManifest(BaseModel):
    """Every committed corpus fixture in one reviewable object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: Annotated[Literal[1], Field(description="Bumped on a shape change.")] = 1
    generated_by: Annotated[str, Field(min_length=1)]
    seed: Annotated[str, Field(min_length=1, description="Seed of the deterministic generator.")]
    statement: Annotated[
        str,
        Field(
            min_length=1,
            description="The rule, in prose, so a reader meets it before the data.",
        ),
    ]
    files: Annotated[Sequence[FixtureRef], Field(min_length=1)]

    def by_path(self, path: str) -> FixtureRef:
        for ref in self.files:
            if ref.path == path:
                return ref
        raise ProvenanceError(f"no provenance entry for {path!r}")

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(ref.path for ref in self.files)


def assert_harness_only(
    provenance: FixtureProvenance | Mapping[str, object], *, context: str
) -> None:
    """Refuse to let real regulator data reach a demo audience.

    Call this at every boundary where records are about to be written into a tenant, a
    fixture the demo loads, or a rendered exhibit.

    Args:
        provenance: The block travelling with the records.
        context: What was about to happen, quoted back in the refusal.

    Raises:
        DemoTenantContamination: when the corpus is real and the destination is not the
            harness.
    """
    block = (
        provenance
        if isinstance(provenance, FixtureProvenance)
        else FixtureProvenance.model_validate(provenance)
    )
    if block.is_real:
        raise DemoTenantContamination(
            f"{context}: refused. {block.source_name} is real regulator data "
            "(corpus_class='real_regulator'); every record in it is a real injury or a "
            "real death. It may be measured by the evaluation harness and it may never "
            "be presented as a fictional site's record. Use the synthetic corpus for "
            "anything a demo audience will see."
        )


def file_sha256(path: Path | str) -> str:
    """Hex sha256 of a file, read in chunks so a large corpus does not need to fit in RAM."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def load_provenance_manifest(path: Path | str) -> ProvenanceManifest:
    """Load and validate ``provenance.json``.

    Raises:
        ProvenanceError: if the file is missing or does not validate.
    """
    source = Path(path)
    if not source.is_file():
        raise ProvenanceError(
            f"{source}: no provenance manifest. A corpus fixture without provenance is "
            "indistinguishable from real data that escaped, so it is refused rather than "
            "assumed synthetic."
        )
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"{source}: not valid JSON: {exc}") from exc
    try:
        return ProvenanceManifest.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError, re-raised with the path
        raise ProvenanceError(f"{source}: invalid provenance manifest: {exc}") from exc
