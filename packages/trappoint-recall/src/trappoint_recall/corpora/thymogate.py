# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""M5 THYMOGATE — running a configuration against the panel, and refusing to certify.

A retrieval configuration is presented with the panel — the fleet's known killers, one
per hazard-energy class, at mixed archival levels — and the certificate records, per item,
whether the configuration recalled it. **A configuration that misses any panel item
cannot be certified.** Not "is certified with a warning", not "is certified at 7/8".
Cannot be certified: :class:`ThymogateCertificate` refuses to construct a ``pass`` verdict
alongside a non-zero miss count, so the object that would carry the false claim does not
exist.

That refusal is the same shape as the CHECK constraint on the vertical's certificate
table (``(verdict = 'pass') = (n_missed = 0)``). Two enforcement points, deliberately: the
database refuses the row, and the Python refuses the object, so a certificate cannot be
constructed in memory, rendered into a slide, and never written.

The certificate binds two digests
----------------------------------
``config_digest`` pins the exact configuration measured; ``panel_digest`` pins the exact
panel it was measured against. Change either and the certificate is stale by
construction rather than by policy. This is why the panel refuses to load with a drifted
digest.

What a certificate does not say
--------------------------------
It says this configuration recalled these eight events. It does not say the configuration
recalls every precursor in the corpus — C-SPANN is approximate, its trees mutate on every
insert, and no bit-identical replay of an ANN search exists. The statement is carried on
the panel itself and rendered wherever a certificate is shown, because a proof that
overclaims is worse than none.

Float handling
--------------
:mod:`trappoint_recall.corpora.canonical` refuses floats under a digest. Configurations
carry thresholds, so :func:`config_digest` quantises every float to
``round(x * 10**6)`` — the same integer quantisation the recall lead pinned for PER leaves
(D10) — and records the rule inside the digested payload so the quantisation is part of
what was committed to.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trappoint_recall.corpora.canonical import deterministic_uuid, digest_hex
from trappoint_recall.corpora.panel import Panel, PanelItem
from trappoint_recall.eval.backend import ScoredCandidate
from trappoint_recall.eval.corpus import EvalQuery

__all__ = [
    "FLOAT_QUANTISATION",
    "PanelOutcome",
    "RecallCriterion",
    "ThymogateCertificate",
    "ThymogateRefusal",
    "certify",
    "certify_sync",
    "config_digest",
]

FLOAT_QUANTISATION: Final = "round(x * 10**6)"
"""How a float becomes an integer before it is digested. Recorded in the digested payload."""

RecallCriterion = Literal["blocking", "top_k"]
"""``blocking``: the item must come back as a blocking check — the product's own claim.
``top_k``: the item must appear in the ranked candidates. Weaker, and named as such."""

_DEFAULT_K: Final = 10


class ThymogateRefusal(RuntimeError):
    """Raised when certification is attempted on a configuration that missed a panel item."""


@runtime_checkable
class _Retriever(Protocol):
    """The slice of the harness's backend contract THYMOGATE needs."""

    name: str

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]: ...


def _quantise(value: object, *, path: str = "$") -> object:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return round(value * 1_000_000)
    if isinstance(value, Mapping):
        return {str(k): _quantise(v, path=f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_quantise(v, path=f"{path}[{i}]") for i, v in enumerate(value)]
    raise TypeError(
        f"{path}: {type(value).__name__} cannot be placed under a config digest. Convert "
        "it at the point where the conversion is reviewable."
    )


def config_digest(config: Mapping[str, object]) -> str:
    """Hex sha256 over the canonical, float-quantised configuration.

    The quantisation rule is *inside* the digested payload, so two certificates quoting
    the same digest agree on how their thresholds were rounded as well as on what they
    were.
    """
    return digest_hex({"float_quantisation": FLOAT_QUANTISATION, "config": _quantise(dict(config))})


class PanelOutcome(BaseModel):
    """What the configuration did with one panel item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: Annotated[str, Field(min_length=1)]
    hazard_energy: Annotated[str, Field(min_length=1)]
    scope_level: Annotated[int, Field(ge=1, le=3)]
    must_recall_doc_id: Annotated[str, Field(min_length=1)]
    recalled: bool
    rank: Annotated[int | None, Field(ge=1, description="1-based rank, when returned.")] = None
    outcome: Annotated[
        str | None, Field(description="The candidate's outcome, when it was returned at all.")
    ] = None
    score_q: Annotated[
        int | None,
        Field(
            ge=0,
            le=1_000_000,
            description="round(p_relevant * 10**6). An integer, so sortedness and "
            "reproducibility cannot be broken by float formatting (lead D10).",
        ),
    ] = None
    miss_reason: Annotated[
        str | None,
        Field(description="Why it was not recalled. Required when recalled is false."),
    ] = None

    @model_validator(mode="after")
    def _a_miss_has_a_reason(self) -> PanelOutcome:
        if not self.recalled and not self.miss_reason:
            raise ValueError(
                f"{self.item_id}: a missed panel item must name why it was missed. "
                "'not recalled' with no reason is the sentence that gets rounded off in "
                "the retelling."
            )
        if self.recalled and self.miss_reason:
            raise ValueError(f"{self.item_id}: recalled item carries a miss reason")
        return self


class ThymogateCertificate(BaseModel):
    """A configuration, a panel, and the arithmetic that decides the verdict.

    The verdict is not an opinion about the count — it **is** the count. The validator
    below mirrors the vertical's ``verdict_matches_arithmetic`` CHECK exactly, so a
    certificate claiming ``pass`` while recording misses cannot be constructed in Python
    any more than it can be inserted into the database.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    certificate_id: Annotated[str, Field(min_length=1, description="Deterministic UUIDv5.")]
    config_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    panel_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    panel_id: Annotated[str, Field(min_length=1)]
    configuration_name: Annotated[str, Field(min_length=1)]
    criterion: RecallCriterion
    k: Annotated[int, Field(ge=1)]
    panel_size: Annotated[int, Field(ge=1, description="An empty panel certifies nothing.")]
    n_missed: Annotated[int, Field(ge=0)]
    verdict: Literal["pass", "fail"]
    issued_at: datetime
    outcomes: Annotated[Sequence[PanelOutcome], Field(min_length=1)]
    statement: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def _verdict_is_the_arithmetic(self) -> ThymogateCertificate:
        if len(self.outcomes) != self.panel_size:
            raise ValueError(
                f"certificate records {len(self.outcomes)} outcomes for a panel of "
                f"{self.panel_size}; a certificate that does not report on every panel "
                "member is silent about the ones it omitted"
            )
        counted = sum(1 for o in self.outcomes if not o.recalled)
        if counted != self.n_missed:
            raise ValueError(
                f"n_missed={self.n_missed} but {counted} outcomes are misses. The count is "
                "derived from the outcomes; it is not a separate assertion about them."
            )
        if (self.verdict == "pass") != (self.n_missed == 0):
            raise ValueError(
                f"verdict={self.verdict!r} with n_missed={self.n_missed} is refused. A "
                "configuration that misses any panel member cannot be certified: the "
                "panel is one known killer per hazard-energy class, and 'seven of eight' "
                "names the class nobody will be protected from."
            )
        return self

    @property
    def certified(self) -> bool:
        return self.verdict == "pass"

    @property
    def missed_items(self) -> tuple[PanelOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.recalled)

    def render(self) -> str:
        head = (
            f"THYMOGATE {self.verdict.upper()} — {self.configuration_name} against "
            f"{self.panel_id} ({self.panel_size - self.n_missed}/{self.panel_size} recalled)"
        )
        if self.certified:
            return head
        misses = "\n".join(
            f"    MISS {o.item_id} [{o.hazard_energy}, level {o.scope_level}] "
            f"{o.must_recall_doc_id}: {o.miss_reason}"
            for o in self.missed_items
        )
        return f"{head}\n{misses}"

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")

    def to_certificate_row(self) -> dict[str, object]:
        """The row shape the vertical's certificate table takes.

        ``config_digest`` and ``panel_digest`` are hex here and ``BYTES`` there; the
        caller converts with ``decode('hex')`` at the driver boundary. This package holds
        no database driver and does not pretend to.
        """
        return {
            "certificate_id": self.certificate_id,
            "config_digest_hex": self.config_digest,
            "panel_digest_hex": self.panel_digest,
            "panel_size": self.panel_size,
            "n_missed": self.n_missed,
            "verdict": self.verdict,
            "issued_at": self.issued_at.astimezone(UTC).isoformat(),
        }


def _outcome_for(
    item: PanelItem, candidates: Sequence[ScoredCandidate], *, criterion: RecallCriterion, k: int
) -> PanelOutcome:
    ranked = sorted(candidates, key=lambda c: c.rank)
    match: ScoredCandidate | None = None
    for candidate in ranked:
        if candidate.doc_id == item.must_recall_doc_id:
            match = candidate
            break
    if match is None:
        return PanelOutcome(
            item_id=item.item_id,
            hazard_energy=item.hazard_energy,
            scope_level=item.scope_level,
            must_recall_doc_id=item.must_recall_doc_id,
            recalled=False,
            miss_reason=(
                f"not returned at all among {len(ranked)} candidates at k={k}"
                if ranked
                else "the configuration returned no candidates for this permit"
            ),
        )
    score_q = round(match.p_relevant * 1_000_000)
    if criterion == "blocking" and match.outcome != "blocking":
        return PanelOutcome(
            item_id=item.item_id,
            hazard_energy=item.hazard_energy,
            scope_level=item.scope_level,
            must_recall_doc_id=item.must_recall_doc_id,
            recalled=False,
            rank=match.rank,
            outcome=match.outcome,
            score_q=score_q,
            miss_reason=(
                f"returned at rank {match.rank} but outcome was {match.outcome!r}, not "
                "'blocking'. A known killer that is advisory does not stop the permit."
            ),
        )
    if criterion == "top_k" and match.rank > k:
        return PanelOutcome(
            item_id=item.item_id,
            hazard_energy=item.hazard_energy,
            scope_level=item.scope_level,
            must_recall_doc_id=item.must_recall_doc_id,
            recalled=False,
            rank=match.rank,
            outcome=match.outcome,
            score_q=score_q,
            miss_reason=f"returned at rank {match.rank}, beyond k={k}",
        )
    return PanelOutcome(
        item_id=item.item_id,
        hazard_energy=item.hazard_energy,
        scope_level=item.scope_level,
        must_recall_doc_id=item.must_recall_doc_id,
        recalled=True,
        rank=match.rank,
        outcome=match.outcome,
        score_q=score_q,
    )


async def certify(
    backend: _Retriever,
    panel: Panel,
    *,
    configuration: Mapping[str, object],
    configuration_name: str | None = None,
    criterion: RecallCriterion = "blocking",
    k: int = _DEFAULT_K,
    issued_at: datetime | None = None,
    raise_on_fail: bool = False,
) -> ThymogateCertificate:
    """Run ``backend`` against every panel item and emit the certificate.

    Args:
        backend: Anything satisfying the harness's retrieval contract.
        panel: The panel. Its digest is bound into the certificate.
        configuration: The configuration under test, as a plain mapping — model ids,
            thresholds, beam size, arm set. Digested, so the certificate names exactly
            what was measured.
        configuration_name: Human label. Defaults to the backend's ``name``.
        criterion: ``blocking`` (the product's own claim) or ``top_k``.
        k: Candidates requested per item.
        issued_at: Timestamp. Defaults to now, in UTC.
        raise_on_fail: Raise :class:`ThymogateRefusal` instead of returning a ``fail``
            certificate. A failing certificate is a real artefact worth keeping — it is
            the evidence of what was missed — so the default returns it.

    Returns:
        A :class:`ThymogateCertificate`, ``pass`` only when every item was recalled.

    Raises:
        ThymogateRefusal: when ``raise_on_fail`` and any item was missed.
    """
    name = configuration_name or str(getattr(backend, "name", "") or "unnamed-configuration")
    outcomes: list[PanelOutcome] = []
    for item in panel.ordered_items:
        candidates = await backend.retrieve(item.to_eval_query(), k)
        outcomes.append(_outcome_for(item, candidates, criterion=criterion, k=k))

    n_missed = sum(1 for o in outcomes if not o.recalled)
    digest = config_digest({"configuration": dict(configuration), "criterion": criterion, "k": k})
    certificate = ThymogateCertificate(
        certificate_id=str(deterministic_uuid("thymogate", digest, panel.digest)),
        config_digest=digest,
        panel_digest=panel.digest,
        panel_id=panel.panel_id,
        configuration_name=name,
        criterion=criterion,
        k=k,
        panel_size=len(panel.ordered_items),
        n_missed=n_missed,
        verdict="pass" if n_missed == 0 else "fail",
        issued_at=issued_at or datetime.now(UTC),
        outcomes=tuple(outcomes),
        statement=panel.statement,
    )
    if raise_on_fail and not certificate.certified:
        raise ThymogateRefusal(certificate.render())
    return certificate


def certify_sync(backend: Any, panel: Panel, **kwargs: Any) -> ThymogateCertificate:
    """Synchronous wrapper around :func:`certify`, for scripts and tests.

    Raises:
        RuntimeError: if called from inside a running event loop, where it would deadlock.
            Await :func:`certify` there instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(certify(backend, panel, **kwargs))
    raise RuntimeError(
        "certify_sync() called from inside a running event loop; await certify() instead"
    )
