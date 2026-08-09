# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``explain(refusal) -> RefusalPayload`` — declarative first, QuickXplain second, honest third.

The order is not a preference and it is not an optimisation. It is the order in which the
three answers are trustworthy:

1. **DECLARATIVE DECOMPOSITION.** Deterministic, sub-millisecond, no probe, no locks. It
   covers every single-counter refusal, which is every refusal the six named CHECKs
   produce, plus the clearance lattice and the epoch pin. When it answers, the answer is
   minimal by construction — the witness rows behind a counter ARE the reason set, and
   there is no smaller one because removing any of them leaves the counter non-zero.
2. **QUICKXPLAIN OVER SAVEPOINT PROBES.** For a composite refusal the decomposition does
   not cover. Bounded budget, separate transaction, never on the completion path. When it
   answers, the answer is minimal because the DATABASE said so, one subset at a time.
3. **HONEST INCOMPLETENESS.** ``diagnosis="none"``, ``naa=null``, and a reason from a
   closed set. This is a first-class outcome, not a failure path. Shipping a superset
   labelled ``declarative`` would be the one failure mode invariant I14 exists to prevent,
   and it is worse than shipping nothing because it looks like an answer.

**What this module will not do.** It will not retry — a refusal is attempted exactly once,
ever. It will not probe on the completion path — ``oracle.py`` refuses a connection that
is inside a transaction. It will not emit a payload that does not validate — ``wire.py``
validates before returning. And it will not synthesise a diagnosis for an outcome the
database did not produce: ``RefusalContext`` refuses any SQLSTATE outside the REFUSE class,
so a retry that ran out of budget and a permission denial cannot be dressed up as refusals.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .binding import GateBinding
from .decompose import Decomposition, Witnesses, decompose
from .errors import OracleUnavailable, ProbeBudgetExhausted
from .model import CapabilityGap, EvidenceItem, MusAtom, Naa, RefusalContext, RefusalPayload
from .quickxplain import Oracle, quickxplain
from .udf import UdfSource
from .wire import build_payload

__all__ = ["Diagnoser", "ProbeRequest", "context_from_exception"]

_P0001 = "P0001"
_PREFIX_SEPARATOR = ": "


def context_from_exception(
    exc: object,
    *,
    subject_kind: str,
    subject_id: str,
    gate_epoch: int,
    attempt: Mapping[str, Any] | None = None,
) -> RefusalContext:
    """Build a ``RefusalContext`` from a ``GateRefused``, a driver error, or a replayed row.

    Structural, not nominal. ``trappoint_core.GateRefused`` is the intended input and this
    distribution deliberately does not import it: the diagnoser must also work for a
    conformance runner holding a raw ``psycopg`` error and for a replay harness holding a
    recorded ledger row, and a hard dependency on one of the three would exclude the other
    two.

    The exhibit is taken from ``constraint`` or ``constraint_name`` when the object carries
    one, and from ``diag.constraint_name`` otherwise. For ``P0001`` the driver supplies
    nothing, so the exhibit is recovered from the message prefix and
    ``constraint_source`` is set to ``parsed`` — which a consumer MUST render as a
    weakened diagnosis. A payload claiming ``reported`` for a ``P0001`` exhibit would be
    claiming a diagnostic the driver did not supply.

    Raises:
        ValueError: the object carries no SQLSTATE, or one outside the REFUSE class.
    """
    sqlstate = _first_str(exc, ("sqlstate", "pgcode", "code"))
    if sqlstate is None:
        raise ValueError(
            f"{type(exc).__name__} carries no SQLSTATE. A refusal that did not come from "
            "the database has no diagnosis, and a fabricated one is the worst artefact "
            "this system could emit."
        )
    message = _first_str(exc, ("message",)) or str(exc).strip()
    constraint = _first_str(exc, ("constraint", "constraint_name"))
    source: Literal["reported", "parsed"] = "reported"
    if not constraint:
        diag = getattr(exc, "diag", None)
        constraint = _first_str(diag, ("constraint_name",)) if diag is not None else None
    if not constraint or sqlstate == _P0001:
        constraint = _parse_exhibit(message) or constraint
        source = "parsed"
    if not constraint:
        raise ValueError("a refusal with no exhibit is not evidence")
    return RefusalContext(
        sqlstate=sqlstate,
        constraint=constraint,
        message=message,
        subject_kind=subject_kind,
        subject_id=subject_id,
        gate_epoch=gate_epoch,
        constraint_source=source,
        attempt=dict(attempt or {}),
    )


def _first_str(obj: object, names: Sequence[str]) -> str | None:
    for name in names:
        value = getattr(obj, name, None)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_exhibit(message: str) -> str | None:
    """Recover a P0001 exhibit from the message prefix, per spec/errors.md section 3.2.

    Returns the raising object's name when the caller embedded one, and the prefix
    otherwise. A prefix alone is a WEAK exhibit and the caller marks it ``parsed`` so that
    a run whose exhibits were inferred is never indistinguishable from one whose exhibits
    were reported.
    """
    head, separator, _ = message.partition(_PREFIX_SEPARATOR)
    if not separator or not head:
        return None
    token = head.strip()
    return token if token.replace(".", "").replace("_", "").isalnum() else None


@dataclass(frozen=True, slots=True)
class ProbeRequest:
    """The general algorithm's inputs, supplied by the deployment for one refusal.

    ``candidates`` are the facts that might explain the refusal; ``oracle`` answers
    ``admissible?`` for a subset of them; ``atom_of`` turns a fact into the wire atom that
    names it. All three are the deployment's, because what a "fact" is here is a statement
    about a particular vertical's rows, and a substrate that guessed would be guessing
    about the one thing it must not.

    ``alternative_of`` is optional and defaults to "there isn't one". QuickXplain proves a
    reason set minimal; it says nothing about what would restore admissibility, and the
    substrate will not invent a minimum-cardinality claim it cannot support. A deployment
    that CAN compute one for its own facts supplies this and gets a non-null ``naa``;
    every other deployment gets ``null`` with ``not_computable``, which is the truth.
    """

    candidates: Sequence[Hashable]
    oracle: Oracle
    atom_of: Callable[[Hashable], MusAtom]
    background: Sequence[Hashable] = ()
    alternative_of: Callable[[Sequence[Hashable]], Naa | None] | None = None


class Diagnoser:
    """Turns a refusal into a payload. One instance per binding; safe to reuse."""

    def __init__(
        self,
        binding: GateBinding,
        *,
        spec_version: str | None = None,
        profile: str | None = None,
        schema: Mapping[str, Any] | None = None,
    ) -> None:
        """Bind the diagnoser to a vertical.

        *spec_version* and *profile* default to the binding's own, which is what makes a
        payload's ``spec_version`` a claim the vertical made rather than one this package
        invented.
        """
        self._binding = binding
        self._spec_version = spec_version or binding.spec_version
        self._profile = profile if profile is not None else binding.profile
        self._schema = schema

    @property
    def binding(self) -> GateBinding:
        """The vertical this diagnoser answers for."""
        return self._binding

    def explain(
        self,
        context: RefusalContext,
        *,
        witnesses: Witnesses | None = None,
        source: UdfSource | None = None,
        probe: ProbeRequest | None = None,
        evidence: Sequence[EvidenceItem] = (),
        ext: Mapping[str, Any] | None = None,
        refusal_id: str | None = None,
        observed_at: str | None = None,
    ) -> RefusalPayload:
        """Explain *context*, and return a payload that validates against the wire schema.

        Exactly one of *witnesses* and *source* supplies the declarative pass: witnesses
        for the offline and replay paths, a ``UdfSource`` for the live path. When neither
        covers the refusal and *probe* is supplied, QuickXplain runs. When nothing covers
        it, the payload says so.

        Raises:
            PayloadInvalid: the assembled payload does not validate.
            NotDiagnosable: the database refused to diagnose and there is no probe to fall
                back to. Propagated rather than swallowed: drift between a projection and
                its source is a finding, not a formatting problem.
        """
        declarative, extra = self._declarative(context, witnesses, source)
        if declarative is not None and declarative.covered:
            return self._emit(
                context,
                diagnosis="declarative",
                probe_calls=0,
                mus=declarative.mus,
                naa=declarative.naa,
                naa_reason=declarative.naa_reason,
                evidence=evidence,
                ext=ext,
                refusal_id=refusal_id,
                observed_at=observed_at,
                spec_version=extra.get("spec_version"),
                profile=extra.get("profile"),
            )

        fallback = declarative or self._uncovered(context)
        if probe is None:
            return self._emit(
                context,
                diagnosis="none",
                probe_calls=0,
                mus=fallback.mus,
                naa=None,
                naa_reason=fallback.naa_reason or "not_computable",
                evidence=evidence,
                ext=ext,
                refusal_id=refusal_id,
                observed_at=observed_at,
                spec_version=extra.get("spec_version"),
                profile=extra.get("profile"),
            )
        return self._quickxplain(
            context,
            probe,
            fallback,
            evidence=evidence,
            ext=ext,
            refusal_id=refusal_id,
            observed_at=observed_at,
            spec_version=extra.get("spec_version"),
            profile=extra.get("profile"),
        )

    def _declarative(
        self,
        context: RefusalContext,
        witnesses: Witnesses | None,
        source: UdfSource | None,
    ) -> tuple[Decomposition | None, dict[str, Any]]:
        if source is not None:
            decomposition, answer = source.decomposition(context)
            return decomposition, answer
        if witnesses is None:
            return None, {}
        return (
            decompose(
                self._binding,
                subject_kind=context.subject_kind,
                subject_id=context.subject_id,
                gate_epoch=context.gate_epoch,
                constraint=context.constraint,
                witnesses=witnesses,
                attempt=context.attempt,
            ),
            {},
        )

    def _uncovered(self, context: RefusalContext) -> Decomposition:
        return Decomposition(
            diagnosis="none",
            mus=(
                CapabilityGap(
                    capability=context.constraint[:128],
                    detail=(
                        "no declarative decomposition and no probe were available for this "
                        "constraint; the candidate set is not proven irreducible"
                    ),
                ),
            ),
            naa=None,
            naa_reason="not_computable",
        )

    def _quickxplain(
        self,
        context: RefusalContext,
        probe: ProbeRequest,
        fallback: Decomposition,
        *,
        evidence: Sequence[EvidenceItem],
        ext: Mapping[str, Any] | None,
        refusal_id: str | None,
        observed_at: str | None,
        spec_version: str | None,
        profile: str | None,
    ) -> RefusalPayload:
        calls = 0
        try:
            conflict = quickxplain(probe.candidates, probe.oracle, background=probe.background)
        except (ProbeBudgetExhausted, OracleUnavailable) as exc:
            calls = _calls_of(probe.oracle)
            reason = (
                "probe_budget_exhausted"
                if isinstance(exc, ProbeBudgetExhausted)
                else "not_computable"
            )
            return self._emit(
                context,
                diagnosis="none",
                probe_calls=calls,
                mus=fallback.mus,
                naa=None,
                naa_reason=reason,
                evidence=evidence,
                ext=ext,
                refusal_id=refusal_id,
                observed_at=observed_at,
                spec_version=spec_version,
                profile=profile,
            )
        calls = _calls_of(probe.oracle)
        if not conflict:
            # `None` is the full candidate set being admissible; `()` is the background
            # alone refusing. Neither is a reason set drawn from the candidates, and
            # emitting one anyway would be a fabrication — so the payload keeps the
            # declarative fallback and says the minimality was not established.
            return self._emit(
                context,
                diagnosis="none",
                probe_calls=calls,
                mus=fallback.mus,
                naa=None,
                naa_reason="not_computable",
                evidence=evidence,
                ext=ext,
                refusal_id=refusal_id,
                observed_at=observed_at,
                spec_version=spec_version,
                profile=profile,
            )
        alternative = None if probe.alternative_of is None else probe.alternative_of(conflict)
        return self._emit(
            context,
            diagnosis="quickxplain",
            probe_calls=max(calls, 1),
            mus=tuple(probe.atom_of(fact) for fact in conflict),
            naa=alternative,
            naa_reason=None if alternative is not None else "not_computable",
            evidence=evidence,
            ext=ext,
            refusal_id=refusal_id,
            observed_at=observed_at,
            spec_version=spec_version,
            profile=profile,
        )

    def _emit(
        self,
        context: RefusalContext,
        *,
        diagnosis: Literal["declarative", "quickxplain", "none"],
        probe_calls: int,
        mus: Sequence[MusAtom],
        naa: Naa | None,
        naa_reason: str | None,
        evidence: Sequence[EvidenceItem],
        ext: Mapping[str, Any] | None,
        refusal_id: str | None,
        observed_at: str | None,
        spec_version: str | None = None,
        profile: str | None = None,
    ) -> RefusalPayload:
        return build_payload(
            context,
            spec_version=spec_version or self._spec_version,
            diagnosis=diagnosis,
            mus=mus,
            naa=naa,
            naa_reason=naa_reason,
            probe_calls=probe_calls,
            profile=profile if profile is not None else self._profile,
            evidence=evidence,
            ext=ext,
            refusal_id=refusal_id,
            observed_at=observed_at,
            schema=self._schema,
        )


def _calls_of(oracle: Oracle) -> int:
    """Read an oracle's call count, defaulting to zero when it does not keep one.

    ``probe_calls`` is a claim about what was spent, so an oracle that does not count is
    reported as zero rather than as a guess. The QuickXplain path floors it at one,
    because an answer that came from probing consumed at least one probe and a payload
    saying otherwise would contradict its own ``diagnosis``.
    """
    calls = getattr(oracle, "calls", 0)
    return calls if isinstance(calls, int) and calls >= 0 else 0
