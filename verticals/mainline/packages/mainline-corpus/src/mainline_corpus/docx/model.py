# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The render request: what a controlled document is, as far as stage 3 is concerned.

Stage 3 renders; it does not decide.  Every field below arrives from an authoritative fixture —
``clause_revision.jsonl``, ``clause_registry.jsonl``, ``injector_retypeset.jsonl``,
``spine.json`` — or from the gazetteer.  Nothing here is invented at render time, and the two
places where a value *could* have been inferred instead **derive it and assert it**:

* :func:`g2_heading` derives a generation-2 chapter title from the clause's control class in
  ``gazetteer/control_classes.yaml`` and then checks that the printed label's barrier digit
  agrees with that class's ``barrier_role``.  The renderer never trusts the digit it was handed.
  This is the same posture as **P2** on the database side: a value a layout reads is derived
  from an authoritative source, and the derivation raises when the source is missing.
* :func:`g1_heading` maps the section number to a generation-1 procedural section title and
  raises past the end of the authored list rather than repeating the last one.

Both raise ``LayoutError``.  A document whose headings silently disagreed with its clause
ordering would still render, still digest, and still be wrong — on camera.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from .house_style import G1_SECTION_TITLES

__all__ = [
    "ClauseRender",
    "DocumentRender",
    "LayoutError",
    "RevisionRow",
    "g1_heading",
    "g2_heading",
    "order_clauses",
    "parse_label",
]

#: ``7.3`` · ``7.3.2`` · ``7.3.2(b)`` · ``5.2.1`` — every label form the answer key contains.
_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<a>\d+)\.(?P<b>\d+)(?:\.(?P<c>\d+))?(?:\((?P<item>[a-h])\))?$"
)

#: Barrier role to the digit generation 2 puts in the middle of a label.  Two roles, two digits;
#: ``control_classes.yaml`` constrains ``barrier_role`` to exactly these.
_BARRIER_DIGIT: Final[Mapping[str, int]] = {"preventive": 1, "recovery": 2}


class LayoutError(RuntimeError):
    """A printed label and the authoritative vocabulary disagree about the document's shape."""


def parse_label(label: str) -> tuple[int, int, int | None, str | None]:
    """``"7.3.2(b)"`` -> ``(7, 3, 2, "b")``.  Raises on any form the corpus does not contain."""
    match = _LABEL_RE.match(label)
    if match is None:
        raise LayoutError(
            f"printed label {label!r} is not a form this corpus produces. The generation-1 "
            "scheme is section.position[.sub][(item)] and the generation-2 scheme is "
            "chapter.barrier.item; a label outside both means the clause layout is wrong, not "
            "that the renderer needs a new case."
        )
    sub = match.group("c")
    return (
        int(match.group("a")),
        int(match.group("b")),
        None if sub is None else int(sub),
        match.group("item"),
    )


def g1_heading(label: str) -> tuple[int, str]:
    """``(section number, section title)`` for a generation-1 clause label."""
    section, _, _, _ = parse_label(label)
    if not 1 <= section <= len(G1_SECTION_TITLES):
        raise LayoutError(
            f"clause {label!r} is in section {section}, but the generation-1 house style has "
            f"{len(G1_SECTION_TITLES)} authored sections. Extend G1_SECTION_TITLES deliberately; "
            "repeating the last title would put two different sections under one heading."
        )
    return section, G1_SECTION_TITLES[section - 1]


def g2_heading(
    label: str,
    control_class: str,
    classes: Mapping[str, Mapping[str, object]],
) -> tuple[int, str, int, str]:
    """``(chapter, chapter title, barrier digit, barrier title)`` for a generation-2 label.

    The chapter title is the control class's ``label`` from ``control_classes.yaml`` — that is
    what "a chapter per control class" means — and the barrier digit is checked against that
    class's ``barrier_role`` rather than read off the label.
    """
    chapter, barrier, item, _ = parse_label(label)
    if item is None:
        raise LayoutError(
            f"generation-2 label {label!r} has only two components. The 2016 scheme is "
            "chapter.barrier.item and every clause carries all three."
        )
    entry = classes.get(control_class)
    if entry is None:
        raise LayoutError(
            f"control class {control_class!r} is not in gazetteer/control_classes.yaml, so the "
            "generation-2 chapter title cannot be derived. The renderer refuses to invent one: a "
            "chapter titled from the label would assert a control vocabulary that does not exist."
        )
    role = str(entry["barrier_role"])
    expected = _BARRIER_DIGIT.get(role)
    if expected is None:
        raise LayoutError(f"control class {control_class!r} has unknown barrier_role {role!r}")
    if barrier != expected:
        raise LayoutError(
            f"clause {label!r} is class {control_class!r}, whose barrier_role is {role!r} and "
            f"which the 2016 scheme therefore places in division {expected}; the printed label "
            f"says division {barrier}. The label and the control vocabulary disagree, and the "
            "renderer will not paper over it."
        )
    return chapter, str(entry["label"]), barrier, f"{role.capitalize()} controls"


@dataclass(frozen=True, slots=True)
class ClauseRender:
    """One clause as it appears on a page, at one revision, in one generation."""

    clause_uuid: str
    clause_key: str
    printed_label: str
    ordinal: int
    control_class: str
    barrier_role: str
    body: str
    points: tuple[str, ...]
    setpoint_text: str
    citation: str
    heading_key: str
    heading_number: int
    heading_title: str
    subheading_title: str
    first_in_heading: bool
    first_in_subheading: bool
    renderer: str

    def as_context(self) -> dict[str, object]:
        """Return the mapping the Jinja template sees; flat, because templates do no maths."""
        return {
            "uuid": self.clause_uuid,
            "key": self.clause_key,
            "label": self.printed_label,
            "ordinal": self.ordinal,
            "control_class": self.control_class,
            "barrier_role": self.barrier_role,
            "body": self.body,
            "points": list(self.points),
            "setpoint_text": self.setpoint_text,
            "citation": self.citation,
            "heading_number": self.heading_number,
            "heading_title": self.heading_title,
            "subheading_title": self.subheading_title,
            "first_in_heading": self.first_in_heading,
            "first_in_subheading": self.first_in_subheading,
        }


@dataclass(frozen=True, slots=True)
class RevisionRow:
    """One line of the revision-history table."""

    rev_label: str
    effective_on: str
    effective_on_long: str
    delta: str
    reason: str
    author: str
    driven_by: str

    def as_context(self) -> dict[str, object]:
        return {
            "rev": self.rev_label,
            "effective_on": self.effective_on,
            "effective_on_long": self.effective_on_long,
            "delta": self.delta,
            "reason": self.reason,
            "author": self.author,
            "driven_by": self.driven_by,
        }


@dataclass(frozen=True, slots=True)
class DocumentRender:
    """A whole controlled document, ready to render through one template."""

    output_name: str
    template_key: str
    family: str
    generation: int
    doc_code: str
    site_code: str
    site_name: str
    site_full_name: str
    title: str
    revision_key: str
    rev_no: int
    effective_on: str
    effective_on_long: str
    classification: str
    mue: str
    owner: str
    approver: str
    custodian: str
    purpose: str
    scope: str
    clauses: tuple[ClauseRender, ...]
    revisions: tuple[RevisionRow, ...]
    definitions: tuple[tuple[str, str], ...]
    panel: tuple[tuple[str, str], ...]
    front_note: str
    renderer_census: Mapping[str, int] = field(default_factory=dict)

    @property
    def rev_label(self) -> str:
        """``007`` — the printed revision number, zero-padded as the house style prints it."""
        return f"{self.rev_no:03d}"

    def as_context(self) -> dict[str, object]:
        """Return the complete Jinja context; everything a template can reach lives here."""
        return {
            "doc": {
                "code": self.doc_code,
                "title": self.title,
                "site_code": self.site_code,
                "site_name": self.site_name,
                "site_full_name": self.site_full_name,
                "family": self.family,
                "generation": self.generation,
                "revision_key": self.revision_key,
                "rev": self.rev_label,
                "effective_on": self.effective_on,
                "effective_on_long": self.effective_on_long,
                "classification": self.classification,
                "mue": self.mue,
                "owner": self.owner,
                "approver": self.approver,
                "custodian": self.custodian,
                "purpose": self.purpose,
                "scope": self.scope,
                "front_note": self.front_note,
                "clause_count": len(self.clauses),
            },
            "clauses": [clause.as_context() for clause in self.clauses],
            "revisions": [revision.as_context() for revision in self.revisions],
            "definitions": [
                {"term": term, "meaning": meaning} for term, meaning in self.definitions
            ],
            "panel": [{"label": label, "value": value} for label, value in self.panel],
        }

    def clause_by_uuid(self, clause_uuid: str) -> ClauseRender | None:
        """Return the clause with this identity, or ``None``; the pair assertion uses it."""
        for clause in self.clauses:
            if clause.clause_uuid == clause_uuid:
                return clause
        return None


def order_clauses(clauses: Sequence[ClauseRender]) -> tuple[ClauseRender, ...]:
    """Sort by ordinal and recompute the ``first_in_*`` flags the templates branch on.

    The flags are computed here rather than in the template because a template that decided when
    to emit a heading would be doing arithmetic on the corpus, and a bug there would look like a
    formatting glitch instead of a wrong document.
    """
    ordered = sorted(clauses, key=lambda clause: clause.ordinal)
    result: list[ClauseRender] = []
    previous_heading = ""
    previous_sub = ""
    for clause in ordered:
        sub_key = f"{clause.heading_key}\x1f{clause.subheading_title}"
        result.append(
            ClauseRender(
                **{
                    **{
                        name: getattr(clause, name)
                        for name in clause.__slots__
                        if name not in {"first_in_heading", "first_in_subheading"}
                    },
                    "first_in_heading": clause.heading_key != previous_heading,
                    "first_in_subheading": sub_key != previous_sub,
                }
            )
        )
        previous_heading = clause.heading_key
        previous_sub = sub_key
    return tuple(result)
