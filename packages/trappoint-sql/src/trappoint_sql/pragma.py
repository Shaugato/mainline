# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""Template pragmas — how a template declares what it projects and what it needs.

Three pragmas, all written as Jinja comments so they vanish from the rendered SQL and
cannot be mistaken for executable text:

``{# @projects blocking_check.severity, blocking_check.virulence #}``
    Marks gate columns this template renders as **projections**. Every column named
    here must be backed by a ``[[authority_source]]`` entry in the binding, or
    ``trappoint render`` refuses (`A-1`). This is the pragma the Authority Source
    Contract exists for.

``{# @capability stored_digest #}``
    Declares that this template branches on a platform capability. The renderer refuses
    unless the ground-truth attestation answers that capability ``PASS`` or
    ``FALLBACK-SELECTED`` (ruling `D5`). A template may not read
    ``capabilities.<name>`` without declaring it, because an undeclared branch is a
    branch nobody audited.

``{# @file 0010_type_control_delta.sql #}``
    Not scanned here — see ``render.split_units``. Named in this docstring only so the
    three pragma forms are documented in one place.

The scan is over the **template source**, deliberately. A pragma that only appeared in
rendered output could be introduced by a loop variable, and the contract has to be
decidable before a single line of SQL exists.
"""

from __future__ import annotations

import re

__all__ = [
    "CAPABILITY_PRAGMA",
    "PROJECTS_PRAGMA",
    "capabilities_of",
    "projected_columns_of",
    "rendered_projection_header",
]

PROJECTS_PRAGMA = re.compile(r"\{#-?\s*@projects\s+(?P<body>[^#]*?)\s*-?#\}")
CAPABILITY_PRAGMA = re.compile(r"\{#-?\s*@capability\s+(?P<body>[^#]*?)\s*-?#\}")

_SPLIT = re.compile(r"[,\s]+")


def _tokens(body: str) -> list[str]:
    return [token for token in _SPLIT.split(body.strip()) if token]


def projected_columns_of(source: str) -> tuple[str, ...]:
    """Return every relation-qualified column marked ``@projects`` in *source*.

    Order is source order, and duplicates are preserved: a template that names the same
    column twice is a template whose author lost track, and the caller (`A-4`'s
    neighbour check in ``binding.py``) is entitled to see it.
    """
    out: list[str] = []
    for match in PROJECTS_PRAGMA.finditer(source):
        out.extend(_tokens(match.group("body")))
    return tuple(out)


def capabilities_of(source: str) -> tuple[str, ...]:
    """Return every capability name declared with ``@capability`` in *source*, sorted."""
    out: set[str] = set()
    for match in CAPABILITY_PRAGMA.finditer(source):
        out.update(_tokens(match.group("body")))
    return tuple(sorted(out))


def rendered_projection_header(
    columns: tuple[str, ...], relation: str, key_columns: tuple[str, ...], key: tuple[str, ...]
) -> str:
    """Build the machine-readable header block a rendered projection carries.

    ``spec/binding/authority-source.md`` §4 makes these three lines contractual: they are
    what lets ``trappoint render --check`` and the migration linter verify that the
    committed SQL still corresponds to the declaration that produced it. Kept here rather
    than in a template so that every vertical's projections carry the identical shape.
    """
    authority_side = ", ".join(key_columns)
    projected_side = ", ".join(key)
    return "\n".join(
        (
            f"-- @projects {', '.join(columns)}",
            f"-- @authority {relation} ({authority_side}) <= NEW ({projected_side})",
            "-- @on_missing raise",
        )
    )
