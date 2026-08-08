# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The frozen wire contract between the recall agent and the kernel.

**The recall agent never writes ``blocking_check``.** It hands the kernel a candidate set and
the kernel's ``POST /v1/permits/{id}/checks:materialise`` decides what becomes an obligation
(ARCHITECTURE 8.3, 8.4; adversarial finding S1). The kernel lead owns the endpoint; this
module owns the payload shape, and that division is the whole reason the shape is frozen:
two teams cannot negotiate a serialisation at run time.

Three models, and the reason each field is present
--------------------------------------------------
:class:`ExposureCueRef`
    What the *permit side* emitted, per facet, and under which template and model. Query and
    document must share a genre or the design silently degrades to narrative search
    (recall lead D3), so the template digest travels with the request and the receipt.

:class:`Candidate`
    One retrieved precursor with the arithmetic that produced its outcome. It carries
    ``clause_uuid`` and ``commit_id`` because ``blocking_check`` foreign-keys
    ``(clause_uuid, commit_id)`` — which is what makes a disposition uninheritable across a
    clause revision — and it carries ``channels`` because *which* channel found something is
    evidence about how much weight it deserves.

:class:`CandidateSet`
    The envelope, and the place the conservation law is enforced before anything is written.

What the validators refuse, and why here rather than only in the database
-------------------------------------------------------------------------
MI17 (``candidates_conserved``) is a database ``CHECK``, and it will refuse a lying run row.
But a ``23514`` arriving at the end of a transaction that has already POSTed nothing is a
diagnosis nobody can act on, and — decisively — *the conservation law must never be the first
thing that notices*. A candidate that was retrieved and then vanished from the accounting is
a defect in the retrieval, not in the arithmetic, and the error message has to say which
candidate. So the same law is enforced here, at the shape, where the offending event id is
still in hand.

The cap and the uncapped channels are likewise enforced twice on purpose: at most three
blocking checks of probabilistic origin (recall lead D2), and **no cap at all** on channels A
and B, because a cap that could suppress a bonded fatality would contradict
``bonded_fatalities_all_blocking`` (MI16) and make the gate unsatisfiable on a fonds with
four fatalities.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "BLOCKING_CAP_PROBABILISTIC",
    "CHANNELS",
    "CONTRACT_SCHEMA_VERSION",
    "DETERMINISTIC_ORIGINS",
    "FACETS",
    "KERNEL_ORIGIN",
    "OUTCOMES",
    "ORIGINS",
    "Candidate",
    "CandidateSet",
    "Counts",
    "ExposureCueRef",
]

#: Bumped on any change that is not additive-and-optional. The kernel dispatches on it.
CONTRACT_SCHEMA_VERSION: Final = 1

#: The four Recurrence-Condition Cue facets plus the raw narrative safety net
#: (ARCHITECTURE 6.2). Identical on the event side and the permit side, by design.
FACETS: Final[tuple[str, ...]] = (
    "mechanism",
    "precondition",
    "control_failure",
    "recurrence_test",
    "narrative",
)

#: The retrieval channels of ARCHITECTURE 6.4. ``C_sweep`` is the 256-d unpartitioned coarse
#: sweep, kept distinct from ``C`` because its hits are never blocking below severity 5.
CHANNELS: Final[tuple[str, ...]] = ("A", "B", "C", "C_sweep", "D")

#: The origin vocabulary of ``trappoint_recall.fusion.sga``. These are *retrieval* origins.
ORIGINS: Final[tuple[str, ...]] = (
    "deterministic_ancestry",
    "bonded",
    "recall_probabilistic",
    "lexical",
)

#: Channels A and B. Graph truth and fatality bonds: admitted unconditionally, never capped,
#: never thresholded, and never silenced.
DETERMINISTIC_ORIGINS: Final[frozenset[str]] = frozenset({"deterministic_ancestry", "bonded"})

#: Retrieval origin -> the value the kernel writes to ``blocking_check.origin``, whose CHECK
#: vocabulary belongs to the gate domain (ARCHITECTURE 5.5) and is deliberately not extended
#: from here. The retrieval-side distinction survives in ``Candidate.channels`` and in
#: ``recall_candidate.features``, which is where an auditor looks for it.
KERNEL_ORIGIN: Final[Mapping[str, str]] = {
    "deterministic_ancestry": "blame_ancestry",
    "bonded": "blame_ancestry",
    "recall_probabilistic": "recall_probabilistic",
    "lexical": "recall_probabilistic",
}

#: ``mainline_meas.recall_candidate.outcome``'s closed vocabulary.
OUTCOMES: Final[tuple[str, ...]] = ("blocking", "advisory", "silenced", "deduped")

#: Recall lead D2. Scoped to probabilistic origins, and to those only.
BLOCKING_CAP_PROBABILISTIC: Final = 3

_HEX32: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

Facet = Literal["mechanism", "precondition", "control_failure", "recurrence_test", "narrative"]
Channel = Literal["A", "B", "C", "C_sweep", "D"]
Origin = Literal["deterministic_ancestry", "bonded", "recall_probabilistic", "lexical"]
Outcome = Literal["blocking", "advisory", "silenced", "deduped"]
Verdict = Literal["complete", "partial", "UNDETERMINED"]

#: A 32-byte digest in lowercase hex. The wire carries text; the database carries ``BYTES``.
Digest32 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_FROZEN = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)


class ExposureCueRef(BaseModel):
    """One facet of the permit's exposure cue, and the provenance of the vector it produced."""

    model_config = _FROZEN

    facet: Facet
    cue_sha256: Digest32 = Field(
        description="sha256 of the cue text as emitted, before templating."
    )
    template_sha256: Digest32 = Field(
        description=(
            "sha256 of the embedding template (recall lead D3). Identical on the event side "
            "and the permit side, or the design degrades to narrative search."
        )
    )
    gen_model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=100)
    embed_model: str = Field(min_length=1, max_length=200)
    insufficient_evidence: bool = Field(
        default=False,
        description=(
            "The per-facet escape hatch. A facet the source could not support is declared, "
            "never invented — and a declared gap is retrievable evidence about the permit."
        ),
    )


class Candidate(BaseModel):
    """One retrieved precursor, with the arithmetic that decided its outcome."""

    model_config = _FROZEN

    event_id: UUID
    clause_uuid: UUID = Field(
        description="The cited clause this candidate would raise an obligation against."
    )
    commit_id: Digest32 = Field(
        description=(
            "The clause version. blocking_check FKs (clause_uuid, commit_id), which is what "
            "makes a disposition uninheritable across a clause revision."
        )
    )
    origin: Origin
    channels: tuple[Channel, ...] = Field(min_length=1)
    outcome: Outcome
    rank: int = Field(ge=1)
    severity: int = Field(ge=0, le=5)
    p_relevant: float = Field(ge=0.0, le=1.0)
    tau_applied: float = Field(ge=0.0, le=1.0)
    features: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: str = Field(default="", max_length=4000)
    also_matched: tuple[UUID, ...] = Field(
        default=(),
        description=(
            "MMR-suppressed siblings, attached to their representative rather than dropped. "
            "Visible, not hidden."
        ),
    )
    bonded_severity_5: bool = Field(
        default=False,
        description=(
            "Observed from event_bond join event, never asserted by the retriever. The "
            "database re-derives it in fn_bonded_sev5; this flag exists so the wire can be "
            "refused before the round trip."
        ),
    )

    @property
    def kernel_origin(self) -> str:
        """The value the kernel writes to ``blocking_check.origin``."""
        return KERNEL_ORIGIN[self.origin]

    @property
    def is_probabilistic(self) -> bool:
        """Whether the probabilistic blocking cap applies to this candidate."""
        return self.origin not in DETERMINISTIC_ORIGINS

    @model_validator(mode="after")
    def _check_candidate(self) -> Candidate:
        """Refuse a candidate whose fields could not describe a real admission decision."""
        if self.origin in DETERMINISTIC_ORIGINS and self.outcome != "blocking":
            raise ValueError(
                f"{self.event_id}: origin {self.origin!r} is channel A or B, which is "
                f"admitted unconditionally as blocking; outcome {self.outcome!r} would "
                "silence graph truth"
            )
        if self.bonded_severity_5 and self.outcome != "blocking":
            raise ValueError(
                f"{self.event_id}: a bonded severity-5 event is blocking, always. MI16 "
                "(bonded_fatalities_all_blocking) would refuse the run row that counted it "
                f"as {self.outcome!r}, and a fatality never decays."
            )
        if self.outcome in {"blocking", "advisory"} and not self.evidence_summary.strip():
            raise ValueError(
                f"{self.event_id}: a candidate shown to a human carries the justification "
                "that will become blocking_check.evidence_summary, which is NOT NULL"
            )
        if self.origin in DETERMINISTIC_ORIGINS and self.tau_applied != 0.0:
            raise ValueError(
                f"{self.event_id}: no threshold is consulted for channel A or B, so "
                f"tau_applied must be 0.0, not {self.tau_applied}"
            )
        return self


class Counts(BaseModel):
    """The conserved partition. These are the integers ``recall_run`` stores."""

    model_config = _FROZEN

    n_candidates: int = Field(ge=0)
    n_blocking: int = Field(ge=0)
    n_advisory: int = Field(ge=0)
    n_silenced: int = Field(ge=0)
    n_deduped: int = Field(ge=0)

    @model_validator(mode="after")
    def _conserved(self) -> Counts:
        """L3, the silence conservation law, as arithmetic rather than as a promise."""
        total = self.n_blocking + self.n_advisory + self.n_silenced + self.n_deduped
        if total != self.n_candidates:
            raise ValueError(
                "candidates_conserved (MI17): n_candidates="
                f"{self.n_candidates} but blocking+advisory+silenced+deduped={total}. A "
                "candidate that was retrieved and then vanished from the accounting has "
                "nowhere to go."
            )
        return self

    @classmethod
    def of(cls, candidates: tuple[Candidate, ...]) -> Counts:
        """Tally a candidate tuple. The only supported way to construct honest counts."""
        tally = dict.fromkeys(OUTCOMES, 0)
        for candidate in candidates:
            tally[candidate.outcome] += 1
        return cls(
            n_candidates=len(candidates),
            n_blocking=tally["blocking"],
            n_advisory=tally["advisory"],
            n_silenced=tally["silenced"],
            n_deduped=tally["deduped"],
        )


class CandidateSet(BaseModel):
    """The payload of ``POST /v1/permits/{id}/checks:materialise``."""

    model_config = _FROZEN

    schema_version: Literal[1] = CONTRACT_SCHEMA_VERSION
    run_id: UUID
    permit_id: UUID
    site_id: UUID
    policy_version: str = Field(min_length=1, max_length=200)
    taxonomy_ver: int = Field(ge=0)
    corpus_commit: Digest32
    index_generation: str = Field(min_length=1, max_length=200)
    index_plan_digest: Digest32
    arms_degraded: bool
    silence_receipt_id: UUID
    candidate_root: Digest32
    certificate_verdict: Verdict
    not_exhaustive: bool = False
    exposure_cues: tuple[ExposureCueRef, ...] = Field(min_length=1)
    candidates: tuple[Candidate, ...] = ()
    counts: Counts

    @model_validator(mode="after")
    def _check_set(self) -> CandidateSet:
        """Enforce, at the shape, every law the database would otherwise discover late."""
        seen: set[UUID] = set()
        for candidate in self.candidates:
            if candidate.event_id in seen:
                raise ValueError(
                    f"{candidate.event_id} appears twice. mainline_meas.recall_candidate is "
                    "keyed (run_id, event_id): a cross-channel rediscovery is a union, not a "
                    "second candidate, and counting it twice would break MI17."
                )
            seen.add(candidate.event_id)

        tallied = Counts.of(self.candidates)
        if tallied != self.counts:
            raise ValueError(
                f"the declared counts {self.counts.model_dump()} do not match the candidate "
                f"list {tallied.model_dump()}. The conservation law must never be the first "
                "thing that notices."
            )

        blocking_probabilistic = sum(
            1
            for candidate in self.candidates
            if candidate.outcome == "blocking" and candidate.is_probabilistic
        )
        if blocking_probabilistic > BLOCKING_CAP_PROBABILISTIC:
            raise ValueError(
                f"{blocking_probabilistic} blocking checks of probabilistic origin exceed the "
                f"cap of {BLOCKING_CAP_PROBABILISTIC} (recall lead D2). Overflow becomes "
                "advisory and a silence_ledger(reason='cap_exceeded') row carrying its score "
                "and its tau."
            )

        facets = [cue.facet for cue in self.exposure_cues]
        if len(set(facets)) != len(facets):
            raise ValueError(f"exposure cue facets are not distinct: {facets}")

        if self.certificate_verdict == "UNDETERMINED" and not self.not_exhaustive:
            raise ValueError(
                "the coverage certificate is UNDETERMINED, so this set may not be presented "
                "as an exhausted retrieval. Set not_exhaustive=True — which travels to the "
                "kernel and onto the exhibit — or certify coverage first."
            )
        return self

    @property
    def open_blocking(self) -> int:
        """How many obligations this set asks the kernel to materialise."""
        return self.counts.n_blocking

    def blocking(self) -> tuple[Candidate, ...]:
        """The candidates that will become ``blocking_check`` rows."""
        return tuple(
            candidate for candidate in self.candidates if candidate.outcome == "blocking"
        )
