# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Adjudication — CAT/NLI relation between two clauses, at ``effort: high``.

The Cartographer's judgement call (§8.4 row 2), used where the deterministic cascade
stages S1-S5 — ``canon_sha256``, MinHash/LSH banding, deterministic fuzzy matching,
prefix-constrained ANN and constrained bipartite assignment — have narrowed a pair down
but cannot decide it. Those five stages are **pure code**; this call never replaces
them and never reorders them.

``high`` effort is decision A4's second band. The relation between two safety clauses
turns on quantifier scope, on the difference between "shall" and "should", and on
whether a numeric bound was tightened or loosened — none of which survive a cheap pass.

**This profile cannot emit a resolution.** It reports a relation and whether the numbers
disagree. The delta lattice decides what the relation *means*, and abstain-implies-weaken
is the lattice's rule, not the model's.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._model import DISPOSITION_FORBIDDEN_TOKENS, CallProfile, Effort, Tier
from ._rubric import COMMON_RUBRIC, RUBRIC_VERSION

__all__ = ["ADJUDICATION", "Adjudication"]

_TASK = """\
TASK: CLAUSE RELATION

You are given two clauses, A and B, inside the untrusted block, each delimited and \
labelled. Report the relation of B to A. Nothing else about them is your business: not \
which is better, not which is current, not which should apply.

relation
  "entails"      Every situation satisfying B satisfies A. B is at least as demanding \
as A on every dimension the two share. A narrower interval, a tighter bound, an \
additional required step, a superset of the same requirements.
  "contradicts"  There is a situation satisfying B that violates A. A looser bound, a \
longer interval, a removed step, an exemption A does not grant, a permission A forbids.
  "neutral"      The two are about different things, or they overlap without either \
constraining the other. This is the correct answer far more often than it feels.
  "abstain"      You cannot tell. Ambiguous scope, missing units, a reference to a \
document you were not given, text too damaged to parse. Downstream, an abstention is \
treated as a WEAKENING and blocks the merge, so abstaining is safe and guessing is not.

numeric_disagreement
  True when A and B both state a value for the same measurable thing and the values \
differ — regardless of the relation you chose, and regardless of which is larger. A \
verifier hard-rejects the pair when this is true and the relation is "entails" without \
a supporting quote showing the direction of the change. Set it on any doubt.

confidence_band
  "high"    the relation is determined by explicit text in both clauses.
  "medium"  the relation follows from the text but requires reading a defined term or \
resolving a pronoun.
  "low"     you are inferring from context. Prefer "abstain" over a "low" that is \
really a guess.

supporting_quote
  A verbatim span from B that determines the relation. Where the relation turns on a \
number, the span must contain the number and its comparator words.

notes
  Free prose for a human reviewer, at most six hundred characters. Say what made this \
hard. Do not restate the relation, do not recommend an action, and do not say what \
should be done about it.
"""

_SYSTEM = (COMMON_RUBRIC, _TASK)


class Adjudication(BaseModel):
    """The relation of clause B to clause A, with the span that determines it."""

    model_config = ConfigDict(extra="forbid")

    relation: Literal["entails", "contradicts", "neutral", "abstain"] = Field(
        description="Relation of B to A. Abstain is treated downstream as a weakening."
    )
    confidence_band: Literal["low", "medium", "high"] = Field(
        description="Named band, never a probability: the calibration is ours, not yours."
    )
    numeric_disagreement: bool = Field(
        description="True when A and B state different values for the same measurable thing."
    )
    supporting_quote: str = Field(
        min_length=1, max_length=400, description="Verbatim span from B determining the relation."
    )
    notes: str = Field(
        default="",
        max_length=600,
        description="What made this hard. Never a recommendation.",
    )


ADJUDICATION: CallProfile[Adjudication] = CallProfile(
    profile_id="adjudication",
    agent="cartographer",
    tier=Tier.T1,
    effort=Effort.HIGH,
    model_key="claude-opus-5",
    prompt_version=f"adjudication.v1+{RUBRIC_VERSION}",
    system_blocks=_SYSTEM,
    # High effort thinks a great deal before a small object. The floor is most of the
    # budget on purpose: a truncated adjudication is a silent weakening.
    max_tokens=16000,
    thinking_floor_tokens=12000,
    output_model=Adjudication,
    forbidden_output_tokens=DISPOSITION_FORBIDDEN_TOKENS,
)
