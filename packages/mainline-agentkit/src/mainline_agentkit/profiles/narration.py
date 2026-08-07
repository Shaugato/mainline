# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Conflict narration — T2 prose for a human, at ``effort: high``.

The cherry-pick worker and the site adopter (§8.3, §8.4 row 7) hit three-way clause
merges whose *resolution* is deterministic and whose *explanation* is not. §8.3 states
the division in one line: **Claude explains a conflict, never resolves one.**

That line is a schema, not a convention. :class:`ConflictNarration` has a
``resolution_proposed`` field whose only legal value is ``"none"``, so the wire schema
itself carries the prohibition — a constrained decoder cannot emit anything else, and a
reviewer reading the schema sees the rule without reading the prompt.

T2 output attaches to a T1 row as evidence and is hashed (§8.2). It is never a field
the gate reads.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._model import DISPOSITION_FORBIDDEN_TOKENS, CallProfile, Effort, Tier
from ._rubric import COMMON_RUBRIC, RUBRIC_VERSION

__all__ = ["NARRATION", "ConflictNarration"]

_TASK = """\
TASK: EXPLAIN A MERGE CONFLICT

Three renderings of a clause are given inside the untrusted block: the common ancestor, \
the fleet-standard version, and the site's local version. A deterministic three-way \
merge has already run and has already failed. Your job is to explain to a site safety \
superintendent, in plain English, what the disagreement IS.

You are explaining, not resolving. You must not recommend a version, must not say which \
is safer, must not say which is more current, must not describe one as an improvement, \
and must not suggest wording that would reconcile them. The schema will not let you: \
resolution_proposed accepts only "none". If your narrative implicitly recommends a \
version, rewrite it until it does not.

narrative
  Plain English, at most twelve hundred characters. Lead with the substantive \
difference, not the mechanics of the merge. Name the equipment, the substance, the \
threshold or the step that differs. Where a number differs, state both numbers and both \
units. Where a step exists in one version and not the other, say so directly. Where the \
difference is only formatting, numbering or house style, say THAT — a reviewer who is \
told a conflict is cosmetic can dispose of it in seconds, and a reviewer who has to \
work that out themselves will eventually stop reading.

  Do not use hedging that makes a real difference sound optional: "slightly", "minor", \
"essentially the same". If the versions differ on a number, they differ.

conflicting_clause_ids
  The clause identifiers you were given in the trusted context, copied exactly, for the \
renderings that actually conflict. Do not invent identifiers and do not include a \
rendering that turned out to be identical to another.

resolution_proposed
  "none". There is no other legal value.
"""

_SYSTEM = (COMMON_RUBRIC, _TASK)


class ConflictNarration(BaseModel):
    """A human-readable account of a merge conflict, structurally unable to resolve it."""

    model_config = ConfigDict(extra="forbid")

    narrative: str = Field(
        min_length=1,
        max_length=1200,
        description="Plain-English account of what the disagreement is.",
    )
    conflicting_clause_ids: list[str] = Field(
        default_factory=list,
        max_length=16,
        description="Identifiers of the renderings that actually conflict.",
    )
    resolution_proposed: Literal["none"] = Field(
        default="none",
        description="Always 'none'. Claude explains a conflict and never resolves one.",
    )


NARRATION: CallProfile[ConflictNarration] = CallProfile(
    profile_id="narration",
    agent="cherry_pick_worker",
    tier=Tier.T2,
    effort=Effort.HIGH,
    model_key="claude-opus-5",
    prompt_version=f"narration.v1+{RUBRIC_VERSION}",
    system_blocks=_SYSTEM,
    max_tokens=14000,
    thinking_floor_tokens=9000,
    output_model=ConflictNarration,
    forbidden_output_tokens=DISPOSITION_FORBIDDEN_TOKENS,
)
