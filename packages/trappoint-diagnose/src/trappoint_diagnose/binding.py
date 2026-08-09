# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""What the diagnoser needs to know about a vertical, read from its own ``vertical.toml``.

This is a READER, not a second declaration. It parses the same file
``trappoint render`` parses and takes four things from it: the schema and spec version,
the gated subjects, their counters (column, constraint, polarity and the offset column a
counter may be satisfied by instead), and the obligation relations that feed each counter.
Nothing here may be written anywhere else; a value this module cannot find is a value the
diagnosis does without, and it says so in the payload.

**Why not import `trappoint_sql.binding`.** Two reasons, and the second is the real one.
It would put Jinja2 on the import path of a package whose whole argument is that it has
no dependencies. And `trappoint_sql`'s render context deliberately does not expose
``offset_column`` or ``[[obligation_source]]`` to a template — so the SQL decomposition
cannot name the offsetting counter of ``reading_floor_when_issued`` and this one can.
Reading the binding directly is what closes that gap, and it closes it in the layer that
can afford to: Python, off the gate path, where being wrong costs a worse sentence in a
payload rather than a broken migration.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["CounterBinding", "GateBinding", "SubjectBinding", "load_gate_binding"]


@dataclass(frozen=True, slots=True)
class CounterBinding:
    """One projected counter and the CHECK whose name is the exhibit."""

    column: str
    constraint: str
    polarity: str
    source: str | None = None
    offset_column: str | None = None

    @property
    def offset_allowed(self) -> bool:
        """True when the constraint is satisfiable by a companion instead of by zero."""
        return self.polarity == "offset_allowed"


@dataclass(frozen=True, slots=True)
class SubjectBinding:
    """One gated subject kind and everything the decomposition reads off it."""

    kind: str
    table: str
    id_column: str
    epoch_column: str
    state_column: str
    completing_state: str
    counters: tuple[CounterBinding, ...]

    def counter_for(self, constraint: str) -> CounterBinding | None:
        """Return the counter this constraint gates, or None if it gates none of them."""
        for counter in self.counters:
            if counter.constraint == constraint:
                return counter
        return None


@dataclass(frozen=True, slots=True)
class GateBinding:
    """A vertical, as the diagnoser sees it."""

    name: str
    schema: str
    spec_version: str
    profile: str | None
    subjects: tuple[SubjectBinding, ...]
    obligation_relations: Mapping[str, str]

    def subject(self, kind: str) -> SubjectBinding | None:
        """Return the subject binding for *kind*, or None when no such kind is declared."""
        for subject in self.subjects:
            if subject.kind == kind:
                return subject
        return None

    def counter_for(self, subject_kind: str, constraint: str) -> CounterBinding | None:
        """Return the counter that *constraint* gates on *subject_kind*."""
        subject = self.subject(subject_kind)
        return None if subject is None else subject.counter_for(constraint)

    def relation_for(self, counter_column: str) -> str | None:
        """Return the qualified relation whose rows feed *counter_column*, if one is declared."""
        return self.obligation_relations.get(counter_column)

    @property
    def subject_kinds(self) -> tuple[str, ...]:
        """Every gated subject kind, in declaration order."""
        return tuple(subject.kind for subject in self.subjects)


def _as_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: expected a non-empty string, got {value!r}")
    return value


def _counters(raw: Iterable[Any], where: str) -> tuple[CounterBinding, ...]:
    out: list[CounterBinding] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{where}[{index}]: expected a table")  # noqa: TRY004 - one exception type for one unusable binding
        out.append(
            CounterBinding(
                column=_as_str(entry.get("column"), f"{where}[{index}].column"),
                constraint=_as_str(entry.get("constraint"), f"{where}[{index}].constraint"),
                polarity=_as_str(entry.get("polarity"), f"{where}[{index}].polarity"),
                source=entry.get("source"),
                offset_column=entry.get("offset_column"),
            )
        )
    return tuple(out)


def _subjects(raw: Sequence[Any]) -> tuple[SubjectBinding, ...]:
    out: list[SubjectBinding] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"[[subject]][{index}]: expected a table")  # noqa: TRY004 - one exception type for one unusable binding
        where = f"[[subject]][{index}]"
        out.append(
            SubjectBinding(
                kind=_as_str(entry.get("kind"), f"{where}.kind"),
                table=_as_str(entry.get("table"), f"{where}.table"),
                id_column=_as_str(entry.get("id_column"), f"{where}.id_column"),
                epoch_column=_as_str(entry.get("epoch_column"), f"{where}.epoch_column"),
                state_column=_as_str(entry.get("state_column"), f"{where}.state_column"),
                completing_state=_as_str(
                    entry.get("completing_state"), f"{where}.completing_state"
                ),
                counters=_counters(entry.get("counters", ()), f"{where}.counters"),
            )
        )
    return tuple(out)


def load_gate_binding(path: str | Path) -> GateBinding:
    """Read a ``vertical.toml`` and return the parts the diagnoser needs.

    Raises:
        FileNotFoundError: there is no binding at *path*.
        ValueError: the binding declares no gated subject, or a subject is malformed. A
            binding with no subject cannot produce a gate refusal, so a diagnoser built
            from one would answer every question with silence.
    """
    source = Path(path)
    with source.open("rb") as handle:
        raw: dict[str, Any] = tomllib.load(handle)

    vertical = raw.get("vertical")
    if not isinstance(vertical, dict):
        raise ValueError(f"{source}: no [vertical] table")  # noqa: TRY004 - one exception type for one unusable binding

    subjects = _subjects(raw.get("subject", ()))
    if not subjects:
        raise ValueError(
            f"{source}: declares no [[subject]]. A binding with no gated subject cannot "
            "produce a gate refusal, and a diagnoser built from one would answer every "
            "question with silence rather than with a refusal to answer."
        )

    relations: dict[str, str] = {}
    for entry in raw.get("obligation_source", ()):
        if isinstance(entry, dict):
            counter = entry.get("counter")
            relation = entry.get("relation")
            if isinstance(counter, str) and isinstance(relation, str):
                relations[counter] = relation

    conformance = raw.get("conformance")
    profile = None
    if isinstance(conformance, dict):
        candidate = conformance.get("profile")
        profile = candidate if isinstance(candidate, str) and candidate else None

    return GateBinding(
        name=_as_str(vertical.get("name"), "[vertical].name"),
        schema=_as_str(vertical.get("schema"), "[vertical].schema"),
        spec_version=_as_str(vertical.get("spec_version"), "[vertical].spec_version"),
        profile=profile,
        subjects=subjects,
        obligation_relations=relations,
    )
