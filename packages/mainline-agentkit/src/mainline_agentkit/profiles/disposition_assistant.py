# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The disposition assistant — T2, display-only, and structurally unable to fill a field.

§8.4 row 5 is the strictest row in the fleet table. The disposition assistant holds *no*
tools, is invoked as a pure function, returns display text, and the decision it does not
make is **everything**. It may summarise the precursor and render the generated defeater
vocabulary. It may not draft rationale, suggest a ``defeater_code``, or pre-fill a field.

Three independent things enforce that here, and none of them is the prompt:

1. **The output model has no field it could fill.** :class:`DisplayOnlyText` carries a
   summary, a vocabulary list and a list of precursor ids. There is no rationale field,
   no code field, no free slot.
2. **The profile declares the forbidden tokens**, and
   :class:`mainline_agentkit.profiles._model.CallProfile` refuses at **import time** if
   any output-model property name contains one. Adding ``defeater_code`` to this model
   does not produce a bad disposition; it produces a failed import.
3. **This module exports no writer.** ``__all__`` is the profile and the model. There is
   no function here that returns a disposition, a code, or anything a caller could put
   in one — asserted by ``tests/test_disposition_assistant.py``.

Underneath all three sits the fact that makes them redundant rather than load-bearing:
``svc_disposition`` is the only SQL role that can ``INSERT mainline.disposition``, no
agent holds it, and since §5.1 an agent could not sign even if it did, because it has no
enrolled WebAuthn credential. These controls exist so the prohibition is visible in the
code a reviewer reads first.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._model import DISPOSITION_FORBIDDEN_TOKENS, CallProfile, Effort, Tier
from ._rubric import COMMON_RUBRIC, RUBRIC_VERSION

__all__ = ["DISPOSITION_ASSISTANT", "DisplayOnlyText"]

_TASK = """\
TASK: SUMMARISE A PRECURSOR FOR A HUMAN WHO IS ABOUT TO DISPOSE OF IT

A safety superintendent is looking at a recalled precursor and must decide, personally \
and under their own signature, whether the work in front of them is defended against it. \
You are writing the paragraph they read first. You are not helping them decide.

Everything below is forbidden, and the schema gives you nowhere to put it in any case:
  - proposing or hinting at a defeater code, a disposition, or a category of disposition;
  - drafting, sketching, or beginning any wording they might sign;
  - saying whether the precursor applies, is defended, is relevant, or is a duplicate;
  - saying that a control is adequate, in place, sufficient, or already handled;
  - recommending, advising, suggesting, or noting what "typically" happens here;
  - naming an individual, or characterising anyone's conduct in the source incident.

If you find yourself writing "this appears to be already controlled by", stop. That \
sentence is the disposition, and it is not yours to write.

precursor_summary
  At most nine hundred characters, plain English, past tense for what happened and \
present tense for what the record says. What occurred, to what equipment or substance, \
under what conditions, and what the investigation identified as the control that was \
absent or ineffective. Numbers with their units. No adjectives that grade seriousness — \
"catastrophic", "minor", "significant" are all judgements the record already carries in \
a coded field you have not been shown.

vocabulary_terms
  The generated defeater vocabulary you were given in the trusted context, rendered for \
display, copied exactly and not reworded. This is a rendering task: the vocabulary is \
generated deterministically elsewhere. Return the subset that is legible in the context \
of this precursor, at most twelve terms, in the order you were given them. Do not invent \
a term. Do not order them by which you think fits best.

precursor_ids
  The precursor identifiers from the trusted context that this summary covers, copied \
exactly.
"""

_SYSTEM = (COMMON_RUBRIC, _TASK)


class DisplayOnlyText(BaseModel):
    """Display text for a human about to sign. Carries no field a disposition needs.

    Every property name here is checked against
    :data:`mainline_agentkit.profiles._model.DISPOSITION_FORBIDDEN_TOKENS` at import
    time. The check is what stops a future edit from quietly adding a field that a UI
    would then quietly pre-fill.
    """

    model_config = ConfigDict(extra="forbid")

    precursor_summary: str = Field(
        min_length=1,
        max_length=900,
        description="What happened, to what, under what conditions, and what was missing.",
    )
    vocabulary_terms: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Deterministically generated vocabulary, rendered for display only.",
    )
    precursor_ids: list[str] = Field(
        default_factory=list, max_length=25, description="Precursor ids this summary covers."
    )


DISPOSITION_ASSISTANT: CallProfile[DisplayOnlyText] = CallProfile(
    profile_id="disposition_assistant",
    agent="disposition_assistant",
    tier=Tier.T2,
    effort=Effort.LOW,
    model_key="claude-opus-5",
    prompt_version=f"disposition_assistant.v1+{RUBRIC_VERSION}",
    system_blocks=_SYSTEM,
    max_tokens=4000,
    thinking_floor_tokens=2000,
    output_model=DisplayOnlyText,
    forbidden_output_tokens=DISPOSITION_FORBIDDEN_TOKENS,
)
