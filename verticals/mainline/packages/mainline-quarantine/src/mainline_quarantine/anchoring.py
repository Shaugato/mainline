# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 4: a cue may only name anchors its own source document contains.

The cheapest high-value control in the posture, and the one that survives a paraphrase.
An attacker who wants a clause to attach to the wrong equipment, the wrong isolation
point or the wrong standard has to make the model *emit* that identifier - and the
identifier is not in the document, so a regex refuses the cue before it is inserted. No
threshold, no embedding, no calibration, nothing a model can be talked out of.

**The rule, exactly.** For a proposal (a "cue") drawn from a source document:

* every hard anchor the extractor finds **in the cue** must have its normalised form
  present in the anchor set extracted **from the source**, in the same class;
* every anchor the cue *declares* (the model's own ``anchors`` list) must either be
  recognised by the extractor and present in the source's set, or - if the extractor
  does not recognise it, which is the honest case for a substance name like
  ``hydrogen sulphide`` - appear **verbatim** in the source text after whitespace
  collapsing and case folding.

Anything absent is rejected, and the rejection names the anchor and the reason.

**Two boundaries, stated rather than hidden.**

*Setpoints are compared as written, never SI-folded.* ``0.35 MPa`` does not match
``350 kPa`` here and a cue that restates a setpoint in another unit is **rejected**. That
is deliberate: SI folding requires deciding gauge versus absolute, and ``50 psig ->
446 kPa(a)`` silently flips a safe-direction comparison. The unit algebra that raises on
a gauge/absolute crossing lives in the domain package and is the right place for that
decision; here the stricter comparison is the safe one, because its failure mode is a
nuisance rejection rather than an admitted weakening.

*``named_role`` is not checked.* It is not an identity class upstream either. Roles are
legitimately paraphrased between an incident report and a procedure - "the shift
supervisor" and "the Supervisor" - so requiring exact presence would manufacture
rejections that carry no information. :data:`CHECKED_CLASSES` is the list, and it is the
same in both extractor lanes.

**Two implementations, no stub.** :class:`DomainAnchorExtractor` wraps the algorithms
domain's ANCHORLOCK extractor when it is importable;
:class:`mainline_quarantine.gazetteer.GazetteerAnchorExtractor` is the committed-word-list
fallback. Both satisfy :class:`AnchorExtractor`. There is no third mode in which layer 4
returns "no anchors, nothing to check".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from .classes import Layer, Outcome
from .errors import AnchorExtractorUnavailable
from .normalise import collapse_whitespace

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "CHECKED_CLASSES",
    "Anchor",
    "AnchorExtractor",
    "AnchorRejection",
    "AnchorVerdict",
    "Cue",
    "DomainAnchorExtractor",
    "domain_extractor",
    "verify_anchors",
]

#: The anchor classes layer 4 checks. ``named_role`` is deliberately absent; see the
#: module docstring. ``setpoint`` is present here even though ANCHORLOCK excludes it from
#: its *identity* classes, because the two questions are different: ANCHORLOCK asks
#: "are these the same clause", and a moved setpoint must reach the delta lattice rather
#: than vanish behind a non-match. Layer 4 asks "did the model read this number in this
#: document", and a setpoint it did not read is a fabricated setpoint.
CHECKED_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "equipment_tag",
        "isolation_point_id",
        "instrument_loop",
        "regulatory_citation",
        "cas",
        "setpoint",
    }
)


@dataclass(frozen=True, slots=True)
class Anchor:
    """One extracted anchor, in the shape both lanes produce."""

    cls: str
    raw: str
    norm: str
    span: tuple[int, int]


@runtime_checkable
class AnchorExtractor(Protocol):
    """What layer 4 needs from an anchor extractor, and nothing more."""

    name: str

    def extract(self, text: str) -> tuple[tuple[str, str, str, tuple[int, int]], ...]:
        """Return ``(class, raw, norm, span)`` for every anchor in ``text``."""
        ...


@dataclass(frozen=True, slots=True)
class DomainAnchorExtractor:
    """Adapter over ``mainline_domain.anchors.extract_anchors``.

    Consumes the algorithms lead's extractor rather than reimplementing it, and converts
    its ``AnchorSet`` into the flat tuple shape the Protocol declares. The conversion is
    the entire adapter: no thresholds, no filtering, no reinterpretation of what that
    package decided was an anchor.
    """

    extract_fn: Any
    name: str = "mainline_domain.anchors"

    def extract(self, text: str) -> tuple[tuple[str, str, str, tuple[int, int]], ...]:
        """Extract with ANCHORLOCK and flatten the result."""
        anchor_set = self.extract_fn(text)
        return tuple(
            sorted(
                (anchor.cls.value, anchor.raw, anchor.norm, tuple(anchor.span))
                for anchor in anchor_set.items
            )
        )


def domain_extractor() -> DomainAnchorExtractor:
    """Build the ANCHORLOCK-backed extractor, or refuse with the import failure.

    Raises:
        AnchorExtractorUnavailable: ``mainline_domain.anchors`` is not importable. The
            caller chooses the fallback explicitly; this function never chooses it, so a
            missing integration lane is a visible decision rather than a silent
            downgrade.
    """
    # Resolved through `importlib` rather than an `import` statement, for two reasons that
    # are the same reason: this package's import graph stays standard-library-only, and a
    # type checker running where `mainline_domain` is absent reports nothing - because the
    # dependency is genuinely optional, and a `type: ignore` would go stale the moment it
    # were installed.
    import importlib

    try:
        module = importlib.import_module("mainline_domain.anchors")
    except ImportError as exc:
        raise AnchorExtractorUnavailable(
            f"mainline_domain.anchors is not importable ({exc}); the integration lane "
            f"skips and the committed-gazetteer fallback is used instead"
        ) from exc
    extract_fn = getattr(module, "extract_anchors", None)
    if extract_fn is None:
        raise AnchorExtractorUnavailable(
            "mainline_domain.anchors imported but has no extract_anchors; refusing rather "
            "than degrading to an extractor that finds nothing"
        )
    return DomainAnchorExtractor(extract_fn=extract_fn)


@dataclass(frozen=True, slots=True)
class Cue:
    """A model proposal about one document, in the two forms layer 4 reads.

    Attributes:
        cue_id: identifier for the proposal, carried into the finding.
        text: every free-text field of the proposal, concatenated. Anchors are extracted
            from this, because an equipment tag smuggled into a ``quote`` is exactly as
            dangerous as one in an ``anchors`` list.
        declared_anchors: the model's own ``anchors`` array, checked verbatim as well.
    """

    cue_id: str
    text: str
    declared_anchors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnchorRejection:
    """One anchor that is not in the source, and why that was decided."""

    anchor_class: str
    value: str
    reason: str

    def describe(self) -> str:
        """One line an operator can act on."""
        return f"{self.anchor_class}:{self.value} ({self.reason})"


@dataclass(frozen=True, slots=True)
class AnchorVerdict:
    """What layer 4 decided about one cue."""

    outcome: Outcome
    layer: Layer
    extractor: str
    rejections: tuple[AnchorRejection, ...]
    source_anchor_count: int
    cue_anchor_count: int

    @property
    def rejected(self) -> bool:
        """Whether the cue was refused."""
        return self.outcome is Outcome.ANCHOR_REJECTED


def verify_anchors(
    cue: Cue,
    source_text: str,
    extractor: AnchorExtractor,
    *,
    checked_classes: frozenset[str] = CHECKED_CLASSES,
) -> AnchorVerdict:
    """Reject a cue whose hard anchors are absent from its source document.

    Args:
        cue: the model's proposal.
        source_text: the canonicalised text the proposal was drawn from.
        extractor: ANCHORLOCK or the committed-gazetteer fallback.
        checked_classes: the classes to enforce over. Narrowing this is a decision with a
            reason, never a convenience; the default is :data:`CHECKED_CLASSES`.

    Returns:
        A verdict naming every rejected anchor. An empty rejection tuple means every
        anchor the cue names was read in the source.
    """
    source_anchors = _by_class(extractor.extract(source_text))
    cue_anchors = extractor.extract(cue.text)
    folded_source = collapse_whitespace(source_text).casefold()

    rejections: list[AnchorRejection] = []

    for anchor_class, _raw, norm, _span in cue_anchors:
        if anchor_class not in checked_classes:
            continue
        if norm not in source_anchors.get(anchor_class, frozenset()):
            rejections.append(
                AnchorRejection(
                    anchor_class=anchor_class,
                    value=norm,
                    reason=(
                        "absent from the source document's anchor set for this class"
                        if source_anchors.get(anchor_class)
                        else "the source document carries no anchor of this class at all"
                    ),
                )
            )

    for declared in cue.declared_anchors:
        rejection = _check_declared(
            declared, extractor, source_anchors, folded_source, checked_classes
        )
        if rejection is not None:
            rejections.append(rejection)

    deduped = tuple(dict.fromkeys(rejections))
    return AnchorVerdict(
        outcome=Outcome.ANCHOR_REJECTED if deduped else Outcome.CLEAN,
        layer=Layer.L4_SEMANTIC_ANCHORING,
        extractor=extractor.name,
        rejections=deduped,
        source_anchor_count=sum(len(values) for values in source_anchors.values()),
        cue_anchor_count=len(cue_anchors),
    )


def _check_declared(
    declared: str,
    extractor: AnchorExtractor,
    source_anchors: dict[str, frozenset[str]],
    folded_source: str,
    checked_classes: frozenset[str],
) -> AnchorRejection | None:
    """Check one declared anchor string. ``None`` means it is present in the source."""
    candidate = declared.strip()
    if not candidate:
        return AnchorRejection("declared", declared, "empty declared anchor")

    recognised = [
        (anchor_class, norm)
        for anchor_class, _raw, norm, _span in extractor.extract(candidate)
        if anchor_class in checked_classes
    ]
    if recognised:
        for anchor_class, norm in recognised:
            if norm not in source_anchors.get(anchor_class, frozenset()):
                return AnchorRejection(
                    anchor_class=anchor_class,
                    value=norm,
                    reason="declared by the model but absent from the source anchor set",
                )
        return None

    # Not a shape the extractor knows - a substance name, a standard's title. The honest
    # check is verbatim presence, and it is still a refusal when it fails: the model may
    # only name what it read.
    if collapse_whitespace(candidate).casefold() in folded_source:
        return None
    return AnchorRejection(
        anchor_class="unrecognised",
        value=candidate,
        reason="not a known anchor shape and not present verbatim in the source text",
    )


def _by_class(
    anchors: Sequence[tuple[str, str, str, tuple[int, int]]],
) -> dict[str, frozenset[str]]:
    grouped: dict[str, set[str]] = {}
    for anchor_class, _raw, norm, _span in anchors:
        grouped.setdefault(anchor_class, set()).add(norm)
    return {key: frozenset(value) for key, value in grouped.items()}
