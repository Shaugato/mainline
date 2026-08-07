# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The cached system prefix for taxonomy induction.

Built with the providers package's :class:`~...providers.system_blocks.SystemPrefix`, which
enforces two things this module needs and cannot enforce itself: every block is declared
stable and is scanned for per-request content, and the cache breakpoint lands on the last
block.  The candidates and narratives go in the user turn, after the breakpoint, wrapped in
the datamarking sentinel (ARCHITECTURE §8.4 layer 2) — narratives are third-party prose and
an injected instruction inside one must not be able to present itself as frame.

The naming constraint is stated in the prompt *and* enforced by
:mod:`~mainline_recall_agent.taxonomy.labels` after the answer comes back.  Both, not
either: the prompt is how the model is asked to behave, and the validator is how we find
out that it did not.  A prompt-only constraint on a label that becomes a vector-index
prefix is a hope with a K-means tree attached to it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mainline_recall_agent.providers.system_blocks import SystemBlock, SystemPrefix

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .register import Level1Register

__all__ = [
    "INDUCTION_PROMPT_VERSION",
    "NAMING_RULE",
    "build_induction_prefix",
]

#: Bumped whenever any byte of the prefix changes.  It is written onto every
#: ``TaxonomyVersion``, and a taxonomy induced under a different prompt is a different
#: taxonomy even when the labels happen to coincide.
INDUCTION_PROMPT_VERSION: Final[str] = "mainline-taxonomy-induction-1"

NAMING_RULE: Final[str] = (
    "A label names a FUNCTION PERFORMED. It never names a thing, a place, an asset, an "
    "organisation or a person."
)

_RUBRIC: Final[str] = """
You are inducting a business classification scheme for a mining safety archive, in the
ISO 15489 / DIRKS sense: records are classified by the FUNCTION and ACTIVITY they arise
from, not by the asset involved or the part of the site they happened in.

Why this matters, so that you can apply it rather than pattern-match it. Asset tags,
contractors, fleet numbers and pit names are re-issued every few years. The work does not
change: people still isolate stored energy before opening a system, still enter confined
atmospheres, still stand clear of suspended loads. A scheme built on things has to be
rebuilt whenever the things are renamed, and every historical record filed under the old
name stops being findable. A scheme built on functions survives.

A LABEL NAMES A FUNCTION PERFORMED. It never names a thing, a place, an asset, an
organisation or a person.

Accept:
  isolating stored energy before intrusive work
  proving zero energy before opening a system
  restraining people working at height
  verifying atmosphere before and during entry

Refuse, and rewrite as the work being done:
  energy isolation              -> a topic, not work: name the doing
  tyre and rim                  -> two objects
  haul truck maintenance        -> an object plus a topic
  north pit                     -> a place
  crusher three                 -> an asset

Every label is lowercase, at most twelve words, contains no digits except chemical
formulae such as h2s or co2, and begins with the verb form of the work: isolating,
proving, entering, restraining, transporting, charging, testing, and so on.

Three levels, and only levels 2 and 3 are yours to propose:
  level 1  fonds   the operating function. FROZEN. Choose from the codes given below and
                   never invent one. If no code fits, say so with insufficient_evidence.
  level 2  series  an activity class: the family of work the record belongs to.
  level 3  file    the specific activity: the work that was actually being performed.

Level 3 is narrower than level 2, and level 2 is narrower than level 1. If the narrative
does not tell you what work was being performed, set insufficient_evidence and leave the
labels empty. A guess is worse than an abstention here: the label decides which part of
the index this incident can ever be retrieved from.
""".strip()

_PHASES: Final[str] = """
You will be asked for one of two phases, named in the payload's "phase" field.

phase "propose"
  The payload carries a list of narratives, each with a doc_id. For each one, return a
  level-1 code from the register, a level-2 series label and a level-3 file label, under
  the naming rule above. Return one entry per doc_id, in the order given, and no others.

phase "merge"
  The payload carries the accumulated pool of proposed labels with their support counts.
  Fold near-duplicates together: labels that name the same work in different words, or
  that differ only by an object, a synonym or an inflection. For each resulting group
  return the canonical wording, the members folded into it, and its total support.
  Preserve the parent relationship: a level-3 group names the level-2 label it sits under,
  and that name must be one of the canonical level-2 labels in the same answer.
  Do not merge two labels that name genuinely different work merely because they share
  vocabulary, and do not invent a label that no member proposed unless the canonical
  wording of the group requires it under the naming rule.
""".strip()


def _register_block(register: Level1Register) -> str:
    lines = [
        "The frozen level-1 register. These codes are the buyer's own Material Unwanted",
        "Event list. They are the only legal values of activity_root. They are also the",
        "physical partition keys of the retrieval index, so an invented code is not a",
        "labelling mistake, it is a partition nobody will ever search.",
        "",
    ]
    for code in register.codes:
        lines.append(f"  {code.activity_root}  {code.label}")
        lines.append(f"      register wording: {code.mue_title}")
    return "\n".join(lines)


def build_induction_prefix(register: Level1Register) -> SystemPrefix:
    """The byte-frozen system prefix for both induction phases.

    One prefix for both phases, not two: the rubric and the register are the expensive
    part, they are identical either way, and a second prefix would halve the cache hit
    rate for no gain.  Which phase is being run is a field in the *user* turn, after the
    breakpoint, where the volatile content belongs.
    """
    return SystemPrefix(
        [
            SystemBlock(label="taxonomy_rubric", text=_RUBRIC),
            SystemBlock(label="level1_register", text=_register_block(register)),
            SystemBlock(label="phases", text=_PHASES),
        ],
        prompt_version=INDUCTION_PROMPT_VERSION,
    )
