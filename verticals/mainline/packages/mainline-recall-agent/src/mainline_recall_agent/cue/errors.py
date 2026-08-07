# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Cue-synthesis failures.

Every exception here is a **defect or a fabrication**, never a fact about the corpus, so
none of them carries a ``silence_reason``.  The failures that *are* facts about the corpus
— a refusal, a dead letter, a truncation, an unreachable provider — are raised by
``..providers.errors`` and are converted by :mod:`.synthesise` into a
:class:`~.schema.SilenceRecord` on the returned :class:`~.schema.CueOutcome`.

The split matters.  ``silence_ledger.reason`` is a closed vocabulary and the conservation
law (MI17) counts its rows; a bug in *our* prompt or *our* span arithmetic that quietly
became ``abstained`` would be indistinguishable, in the ledger and in the exhibit, from a
model that declined to answer.  So our bugs crash and the model's silences are recorded.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AnchorGazetteerError",
    "CueError",
    "FacetContract",
    "SourceDocumentError",
    "SpanAmbiguous",
    "SpanOverlap",
    "SpanUnresolvable",
]


class CueError(Exception):
    """Base class for cue-synthesis defects.

    ``silence_reason`` is ``None`` and stays ``None``.  Mirrors the shape of
    ``providers.errors.ProviderError`` so a caller can branch on the attribute uniformly
    without importing both hierarchies.
    """

    silence_reason: str | None = None

    def __init__(self, message: str, /, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} [{rendered}]"


class FacetContract(CueError):
    """A facet answer violates the five-field contract.

    Raised for a placeholder string standing in for the ``insufficient_evidence`` escape,
    for a facet that is simultaneously populated and insufficient, and for a facet that
    exceeds the length bound.  All three are the same underlying mistake: a cue row that
    exists but says nothing, which is retrievable evidence of nothing.
    """


class SpanUnresolvable(CueError):
    """An evidence quote does not occur in the canonical source text.

    The model was shown the canonical text verbatim, so a quote that is not in it was not
    copied from it.  That is the fabrication case, and it fails the step.
    """


class SpanAmbiguous(CueError):
    """An evidence quote occurs more than once in the canonical source text.

    ``source_span`` is a pair of integers that a human will later use to find the words the
    cue came from.  Two candidate positions means we do not know which words those are, and
    guessing the first would make the exhibit wrong in a way nobody could detect.
    """


class SpanOverlap(CueError):
    """Two facets resolved to partially overlapping spans.

    Nesting and exact identity are legal — two facets may be supported by the same sentence
    or by a sentence inside a paragraph.  A *partial* overlap means the two quotes were
    carved out of one another, so neither pair of offsets honestly delimits its own
    evidence, and the set of spans is refused rather than half-recorded.
    """


class SourceDocumentError(CueError):
    """A canonical source document is malformed, empty, or inconsistent with its span."""


class AnchorGazetteerError(CueError):
    """The unit gazetteer or an anchor pattern is internally inconsistent.

    A programmer error in the deterministic layer, surfaced loudly: the anchor extractor is
    the injection control that runs without a model, so it may not degrade quietly.
    """
