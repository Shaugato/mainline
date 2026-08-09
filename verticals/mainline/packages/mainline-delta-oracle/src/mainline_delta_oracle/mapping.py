# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Turning a validated model proposal into an ``OracleVerdict`` — and checking it first.

§8.2 tier T1: *proposals under a JSON Schema, always re-checked by a deterministic
verifier*.  The schema is agentkit's; the deterministic verifier is this module,
and it is not decorative.  Two checks reject a proposal that validated perfectly:

* **The supporting quote must be verbatim in clause B.**  A quote that is not in
  the text is fabricated evidence, and a fabricated span attached to a real
  refusal is worse than no refusal.  Matching is whitespace- and case-insensitive
  and nothing else — a "quote" that differs in a word is not a quote.
* **An ``entails`` that admits a numeric disagreement must quote a number.**  The
  profile's own rubric promises the model that this is hard-rejected, and the
  rejection has to exist somewhere.  It is here.  "B is at least as demanding as
  A" while the two state different values, with no number in the evidence, is the
  exact shape of a loosened setpoint reported as a tightening.

Both rejections produce ``abstained=True``, which the ratchet resolves to
``weaken``.  A model that fabricates evidence blocks a merge; it never clears one.

**Bands are not probabilities, and this is the honesty note.**  The profile emits
``confidence_band`` — ``low``/``medium``/``high`` — described in its own prompt as
*a named band, never a probability: the calibration is ours, not yours*.
``OracleVerdict.confidence`` is a float, so the band is mapped onto ``[0, 1]`` by
the committed table below.  **The three numbers are an ordinal encoding, not a
calibrated posterior**: nothing has measured how often a ``high`` is right.  theta
must be chosen on this scale and read as "which bands count", which is why the
midpoints are spread far apart — a theta of 0.75 means *high only*, 0.5 means
*medium and above*, and there is no meaningful value between them.  The mapping is
versioned so that changing it is a visible commit rather than a tuning knob.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mainline_domain.contracts import ControlDelta, OracleVerdict
from mainline_domain.resolution.silence import stamp_rationale

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mainline_agentkit.profiles import Adjudication

__all__ = [
    "BAND_CONFIDENCE",
    "BAND_MAP_VERSION",
    "RELATION_TO_DELTA",
    "abstain",
    "locate_quote",
    "to_verdict",
]

#: The relation vocabulary of the ``adjudication`` profile, mapped onto the SQL
#: enum.  ``abstain`` is deliberately **not** in this table: it is not a delta,
#: and giving it one — even ``weaken`` — would let an abstention be read as a
#: model finding.
RELATION_TO_DELTA: Final[Mapping[str, ControlDelta]] = {
    "entails": ControlDelta.STRENGTHEN,
    "contradicts": ControlDelta.WEAKEN,
    "neutral": ControlDelta.RESTATE,
}

#: Bumped whenever a number below changes.  Written into the silence arithmetic
#: through the verdict's rationale so a retro-tuned band map is visible.
BAND_MAP_VERSION: Final[str] = "band.v1"

#: Ordinal encoding of the named bands.  See the module docstring: these are not
#: calibrated probabilities and must never be reported as any.
BAND_CONFIDENCE: Final[Mapping[str, float]] = {
    "low": 0.25,
    "medium": 0.55,
    "high": 0.85,
}

#: The label an abstention carries.  ``OracleVerdict`` requires one and the
#: resolution table ignores it whenever ``abstained`` is set; ``weaken`` is chosen
#: so that a consumer which ignored the flag would still fail closed.
ABSTENTION_LABEL: Final[ControlDelta] = ControlDelta.WEAKEN

_DIGITS: Final[frozenset[str]] = frozenset("0123456789")


def _fold(text: str) -> tuple[str, tuple[int, ...]]:
    """Collapse whitespace and case, keeping an index map back to ``text``.

    The map is built per character because ``str.lower`` is not
    length-preserving for every codepoint, and a span computed against a shorter
    or longer folded string would point at the wrong words.
    """
    folded: list[str] = []
    positions: list[int] = []
    in_space = True  # leading whitespace is dropped
    for index, char in enumerate(text):
        if char.isspace():
            if not in_space:
                folded.append(" ")
                positions.append(index)
                in_space = True
            continue
        in_space = False
        for lowered in char.lower():
            folded.append(lowered)
            positions.append(index)
    while folded and folded[-1] == " ":
        folded.pop()
        positions.pop()
    return "".join(folded), tuple(positions)


def locate_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Find ``quote`` in ``text``, returning a half-open span into ``text``.

    Matching ignores whitespace runs and case; everything else must be identical.
    Returns ``None`` when the quote is not present, which the caller turns into an
    abstention rather than into a verdict with no evidence.
    """
    folded_text, positions = _fold(text)
    folded_quote, _ = _fold(quote)
    if not folded_quote:
        return None
    found = folded_text.find(folded_quote)
    if found < 0:
        return None
    start = positions[found]
    end = positions[found + len(folded_quote) - 1] + 1
    return (start, end)


def abstain(
    code: str,
    detail: str,
    *,
    model_id: str,
    prompt_version: str,
) -> OracleVerdict:
    """Build the one shape of verdict this package emits when it cannot answer.

    Confidence is exactly ``0.0``: an abstention carries no evidence and must not
    be able to clear a theta comparison by accident.
    """
    return OracleVerdict(
        label=ABSTENTION_LABEL,
        confidence=0.0,
        rationale=stamp_rationale(code, detail),
        cited_spans=(),
        model_id=model_id,
        prompt_version=prompt_version,
        abstained=True,
    )


def to_verdict(
    adjudication: Adjudication,
    *,
    descendant_text: str,
    model_id: str,
    prompt_version: str,
) -> OracleVerdict:
    """Map a validated proposal to an ``OracleVerdict``, verifying it on the way.

    Args:
        adjudication: the schema-validated proposal.
        descendant_text: clause B's canonical text, which the supporting quote
            must be verbatim in.
        model_id: the inference profile or model generation actually called.
        prompt_version: the profile's frozen prompt version.

    Returns:
        Either a verdict carrying the relation and the located evidence span, or
        an abstention naming which deterministic check rejected the proposal.
    """
    if adjudication.relation == "abstain":
        return abstain(
            "model_abstained",
            f"the model reported it could not tell (band {adjudication.confidence_band}): "
            f"{adjudication.notes or 'no note given'}",
            model_id=model_id,
            prompt_version=prompt_version,
        )

    if (
        adjudication.relation == "entails"
        and adjudication.numeric_disagreement
        and not (_DIGITS & set(adjudication.supporting_quote))
    ):
        return abstain(
            "unsupported_numeric_claim",
            "the model reported that B entails A while also reporting that the two "
            "state different values, and its supporting quote contains no number. "
            "That is the shape of a loosened setpoint described as a tightening.",
            model_id=model_id,
            prompt_version=prompt_version,
        )

    span = locate_quote(descendant_text, adjudication.supporting_quote)
    if span is None:
        return abstain(
            "quote_not_verbatim",
            f"the supporting quote is not present in clause B: "
            f"{adjudication.supporting_quote[:120]!r}. Evidence that is not in the "
            f"document is not evidence.",
            model_id=model_id,
            prompt_version=prompt_version,
        )

    return OracleVerdict(
        label=RELATION_TO_DELTA[adjudication.relation],
        confidence=BAND_CONFIDENCE[adjudication.confidence_band],
        rationale=(
            f"relation={adjudication.relation} band={adjudication.confidence_band} "
            f"band_map={BAND_MAP_VERSION} numeric_disagreement="
            f"{adjudication.numeric_disagreement} notes={adjudication.notes or '-'}"
        ),
        cited_spans=(span,),
        model_id=model_id,
        prompt_version=prompt_version,
        abstained=False,
    )
