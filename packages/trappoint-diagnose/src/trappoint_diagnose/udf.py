# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""One round trip to ``trappoint.explain_refusal()``, and the codec for what comes back.

The declarative decomposition runs IN the database (migration ``0119a``) for three
reasons the client cannot reproduce: it reads the same rows under the same isolation as
the refusal it explains, it is one statement and therefore one plan that CI can assert
with ``EXPLAIN``, and it is the same artefact for every vertical because it is rendered
from the binding.

This module is the client half. It does three things and refuses to do a fourth:

* opens its OWN connection, reads once, and rolls back in a ``finally`` — a diagnosis
  must never be able to mutate the gate, and "we only ran a SELECT" is a promise about
  today's code rather than a property of the path;
* turns the returned JSONB into the same typed objects the pure decomposition produces,
  so the emitter has one shape to assemble from and the two implementations are directly
  comparable;
* turns the UDF's ``P0001`` refusals into ``NotDiagnosable`` with the database's own
  message, verbatim. The UDF raises when the projected counter disagrees with its
  re-derived witness set. That is DRIFT, it is a fact about the world, and it does not
  licence a fabricated reason set — so the client propagates it rather than falling back
  to something plausible.

It does not retry. A refusal is attempted exactly once, ever, and a diagnosis of one is
not more true the second time it is asked for.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .decompose import Decomposition
from .errors import NotDiagnosable, PayloadInvalid
from .model import (
    AuthorityGap,
    CapabilityGap,
    ClauseAtom,
    DisposeObligations,
    EventAtom,
    ForkSubject,
    MaterialiseAuthority,
    MusAtom,
    Naa,
    Obligation,
    RefusalContext,
    SubstituteKind,
    SupplyEvidence,
)
from .oracle import Connection

__all__ = [
    "DEFAULT_FUNCTION",
    "UdfSource",
    "atom_from_wire",
    "atoms_from_wire",
    "naa_from_wire",
]

DEFAULT_FUNCTION = "trappoint.explain_refusal"
_RAISE_EXCEPTION = "P0001"


def atom_from_wire(atom: Mapping[str, Any]) -> MusAtom:
    """Rebuild one typed MUS atom from its wire form.

    Raises:
        PayloadInvalid: the atom names no modelled fact family. The five families are the
            whole vocabulary; a sixth would be a specification change, and accepting one
            here would let it arrive without one.
    """
    kind = atom.get("kind")
    fields = {key: value for key, value in atom.items() if key != "kind"}
    if kind == "obligation":
        return Obligation(**fields)
    if kind == "clause":
        return ClauseAtom(**fields)
    if kind == "event":
        return EventAtom(**fields)
    if kind == "authority_gap":
        return AuthorityGap(**fields)
    if kind == "capability_gap":
        return CapabilityGap(**fields)
    raise PayloadInvalid(f"{kind!r} names no modelled fact family")


def atoms_from_wire(atoms: Sequence[Mapping[str, Any]]) -> tuple[MusAtom, ...]:
    """Rebuild a reason set from its wire form."""
    return tuple(atom_from_wire(atom) for atom in atoms)


def naa_from_wire(naa: Mapping[str, Any] | None) -> Naa | None:
    """Rebuild the nearest admissible alternative from its wire form.

    Raises:
        PayloadInvalid: the alternative names no modelled kind.
    """
    if naa is None:
        return None
    kind = naa.get("kind")
    fields = {key: value for key, value in naa.items() if key != "kind"}
    if kind == "dispose_obligations":
        return DisposeObligations(**fields)
    if kind == "substitute_kind":
        return SubstituteKind(**fields)
    if kind == "supply_evidence":
        return SupplyEvidence(**fields)
    if kind == "materialise_authority":
        return MaterialiseAuthority(**fields)
    if kind == "fork_subject":
        return ForkSubject(**fields)
    raise PayloadInvalid(f"{kind!r} names no modelled alternative kind")


@dataclass(frozen=True, slots=True)
class UdfSource:
    """Calls the in-database decomposition once, on a connection it owns."""

    connect: Callable[[], Connection]
    function: str = DEFAULT_FUNCTION

    def raw(self, context: RefusalContext) -> dict[str, Any]:
        """Return the UDF's JSONB answer, unmodified.

        Raises:
            NotDiagnosable: the UDF raised ``P0001`` — drift, an unknown subject, or a
                refusal that is no longer reproducible against the current row.
        """
        statement = f"SELECT {self.function}(%s, %s::UUID, %s, %s::JSONB)"
        # S608 flags string-built SQL. `self.function` is a schema-qualified object name,
        # which cannot be a bind parameter in any dialect, and the three values that could
        # carry an injection ARE bound. The name comes from this package's own default or
        # from a deployment's configuration file, never from a refusal or a document.
        params = (
            context.subject_kind,
            context.subject_id,
            context.constraint,
            json.dumps(dict(context.attempt)) if context.attempt else None,
        )
        connection = self.connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, params)
                row = cursor.fetchone()
            except Exception as exc:
                translated = self._translate(exc)
                if translated is exc:
                    raise
                raise translated from exc
            finally:
                cursor.close()
        finally:
            # Unconditional, and in this order: a read-only path still opened a
            # transaction, and leaving one open on a pooled connection is how a diagnosis
            # ends up holding a timestamp the gate then contends with.
            try:
                connection.rollback()
            finally:
                connection.close()
        if not row or row[0] is None:
            raise NotDiagnosable(
                f"{self.function} returned no row. A diagnosis that produced nothing is "
                "not a diagnosis, and an empty reason set is the artefact I14 abolishes."
            )
        answer = row[0]
        if isinstance(answer, str):
            answer = json.loads(answer)
        if not isinstance(answer, dict):
            raise NotDiagnosable(f"{self.function} returned {type(answer).__name__}, not an object")
        return answer

    def decomposition(self, context: RefusalContext) -> tuple[Decomposition, dict[str, Any]]:
        """Return the typed decomposition and the raw answer it came from.

        Both, because the raw answer carries the binding's ``spec_version`` and
        ``profile``, which the emitter needs and which are not part of a decomposition.

        Raises:
            NotDiagnosable: the UDF refused to diagnose, and said why.
            PayloadInvalid: the answer names a fact family or alternative kind that is not
                modelled.
        """
        answer = self.raw(context)
        diagnosis = answer.get("diagnosis")
        if diagnosis not in ("declarative", "none"):
            raise PayloadInvalid(
                f"the in-database decomposition reported diagnosis {diagnosis!r}; it can "
                "only ever be 'declarative' or 'none', because it does not probe"
            )
        mus_raw = answer.get("mus") or []
        if not isinstance(mus_raw, list) or not mus_raw:
            raise NotDiagnosable(
                "the in-database decomposition returned an empty reason set; a refusal "
                "with no reason set is the artefact this invariant exists to abolish"
            )
        return (
            Decomposition(
                diagnosis=diagnosis,
                mus=atoms_from_wire(mus_raw),
                naa=naa_from_wire(answer.get("naa")),
                naa_reason=answer.get("naa_reason"),
            ),
            answer,
        )

    @staticmethod
    def _translate(exc: Exception) -> Exception:
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate == _RAISE_EXCEPTION:
            # The database's own sentence, verbatim. It is the exhibit, and paraphrasing
            # it here would be the first step in a diagnosis disagreeing with a refusal.
            return NotDiagnosable(str(exc).strip())
        return exc
