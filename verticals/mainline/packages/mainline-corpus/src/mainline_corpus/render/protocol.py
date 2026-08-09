# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``Renderer`` protocol, the node it renders, and this stage's refusal vocabulary.

A *node* is a unit of prose the corpus needs and the skeleton deliberately did not write: one
event's ICAM narrative, one clause revision's body, one MOC's justification, one document
revision's change record.  Stage 1 authored the causality and left these four columns pending
with an owner; this stage is that owner.

``RenderNode`` carries only what the prompt is allowed to see.  That is a real constraint and
not a tidiness: the *facts* mapping is what gets canonicalised into the cache key, so anything
put in it becomes part of the corpus's identity, and anything left out cannot influence the
text.  A node that carried, say, a wall-clock timestamp would produce a cache that never hits.

``Renderer`` is a ``Protocol`` rather than a base class because the three tiers share no
implementation at all — one reads a file, one composes from a gazetteer, one calls an API —
and a shared base class would only be a place for one of them to leak into the others.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "MissingAuthored",
    "RenderNode",
    "RenderRefusal",
    "Rendered",
    "Renderer",
]


class RenderRefusal(RuntimeError):
    """Stage 2 refuses to produce this node, and says why."""


class MissingAuthored(RenderRefusal):
    """A camera-facing node has no fixture in ``fixtures/corpus/authored/``.

    Separate from the general refusal because the caller's response is different: this one is
    a scheduling fact about another worker's deliverable, and ``--camera=defer`` records it
    rather than failing the build.
    """


@dataclass(frozen=True, slots=True)
class RenderNode:
    """One unit of prose the corpus needs.

    ``node_id`` is ``"<kind>:<key>"`` and is stable across runs — it is built from natural keys
    (``INC-2013-044``, ``MRD/PRO-MEC-014/007``), never from a counter or a draw, so a node keeps
    its identity when a generator upstream adds a row.
    """

    kind: str
    key: str
    facts: Mapping[str, Any]
    camera_facing: bool = False
    #: Free-form, never hashed, never emitted: what the orchestrator needs after rendering
    #: (the control-failure rows to bind, the quote refs to satisfy).  Kept out of ``facts`` on
    #: purpose — putting it in would make the cache key depend on data the prompt never saw.
    context: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def node_id(self) -> str:
        """``"<kind>:<key>"``."""
        return f"{self.kind}:{self.key}"


@dataclass(frozen=True, slots=True)
class Rendered:
    """One renderer's answer for one node."""

    #: The tool-schema-shaped object.  Validated against the prompt's schema before it is
    #: cached, whichever tier produced it — a deterministic renderer that drifted out of schema
    #: is exactly as broken as a model that did.
    response: Mapping[str, Any]
    #: ``authored`` / ``bedrock`` / ``template``.
    renderer: str
    #: Present only on the ``authored`` tier: the fixture the text came from, repo-relative.
    source: str | None = None


@runtime_checkable
class Renderer(Protocol):
    """What every tier implements.

    ``prompt_version`` is passed explicitly rather than read from the prompt file inside the
    renderer, so that a caller pinning an older version gets that version's behaviour and the
    key it derives is the key that version produced.
    """

    #: The tier name, one of :data:`mainline_corpus.render.params.TIERS`.
    name: str

    def render(self, node: RenderNode, prompt_version: str) -> Mapping[str, Any]:
        """Return the response object for ``node``, or raise :class:`RenderRefusal`."""
        ...
