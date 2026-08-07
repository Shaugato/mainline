# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One prompt family, two entry points, one shared facet-definitions block.

The block below is **byte-identical** on the event side and the permit side, and a test
asserts it byte-for-byte.  That is not tidiness.  Query/document genre symmetry is the
entire reason Recurrence-Condition Cues exist (ARCHITECTURE §6.2): if the two sides drift
apart in what ``mechanism`` means, cosine between an exposure cue and an event cue stops
measuring hazard recurrence and goes back to measuring prose style — silently, with no
error anywhere, and with a number that still looks like 0.83.

**Block order is deliberate and differs from ``providers.build_system_blocks``.**  The
shared block goes **first**, so the two sides' prompts share a common byte prefix.  Honest
caveat: ``SystemPrefix.wire()`` places exactly one ``cache_control`` breakpoint, on the last
block, so today the event prefix and the exposure prefix are two cache entries that happen
to share their opening bytes rather than one shared cached segment.  Putting the shared
block first costs nothing now and is the only ordering under which a second breakpoint would
ever help; the reverse ordering forecloses it.

Prompt-injection posture (ARCHITECTURE §8.4): nothing from a document ever reaches this
module.  The rubric and the definitions are static bytes committed to the repository; the
narrative, the isolation plan and the clause diff go in the user turn, inside the sentinel
span built by ``providers.build_user_turn``, after the cache breakpoint.  This call holds
**no tools and no write credentials** — layer 1, structural quarantine, is enforced by the
fact that there is nothing here to hold them with.
"""

from __future__ import annotations

from typing import Any, Final

from mainline_recall_agent.providers.system_blocks import SystemBlock, SystemPrefix

from .schema import SYNTHESISED_FACETS
from .source_text import SourceDocument

__all__ = [
    "EVENT_EXAMPLES",
    "EVENT_RUBRIC",
    "EXPOSURE_EXAMPLES",
    "EXPOSURE_RUBRIC",
    "FACET_DEFINITIONS",
    "PROMPT_VERSION",
    "build_event_prefix",
    "build_exposure_prefix",
    "event_payload",
    "exposure_payload",
]

#: Bumping this is a commit, not a deploy: ``event_cue`` is UNIQUE on
#: ``(event_id, scope_id, facet, prompt_version)``, so a new version re-derives the corpus
#: rather than overwriting it, and the old cues remain quotable next to the runs that used
#: them (ARCHITECTURE §8.2).
PROMPT_VERSION: Final[str] = "mainline-cue-1"


# ======================================================================================
# THE SHARED BLOCK.  Byte-identical on both sides.  Do not fork it "just for the permit
# side" — that fork is the failure this whole design exists to prevent.
# ======================================================================================

FACET_DEFINITIONS: Final[str] = """\
A Recurrence-Condition Cue has five facets. Four are written; the fifth is copied.

Both sides of this system emit the same four facets from these same definitions: the past
side from an incident record, the future side from a permit package. That symmetry is the
point. Comparing a permit form against an investigator's prose compares two genres and
finds documents written the same way. Comparing a mechanism statement against a mechanism
statement finds hazards that can recur.

MECHANISM
  The physical or chemical process by which harm is realised, stated so that it would
  still be true on different plant at a different site. Gas liberation, stored-energy
  release, loss of containment, engulfment, inrush, arc flash, liquefaction, fall of
  ground. On the past side: the process that acted. On the future side: the process that
  could act if the proposed work goes wrong. Name the energy and name how it gets out. Do
  not name the injury. The injury is the consequence; the consequence is not the mechanism,
  and every record in this corpus shares the consequence.

PRECONDITION
  The state of the world that must hold for that mechanism to act. An interlock in bypass.
  A shared header with no positive isolation. A person inside the trajectory of a
  pressurised assembly. Ground above a trigger level. A vessel drained but not proven
  drained. On the past side: the state that held. On the future side: the state the
  proposed work creates, or relies on staying true. A condition that holds for every job on
  the site is not a precondition; it is a description of the site.

CONTROL_FAILURE
  Which class of control was defeated, absent, or defeated by design, and how - expressed
  as what the control existed to prevent, never as who failed to apply it. On the past
  side: the control that did not hold. On the future side: the control being stood down,
  weakened, or relied upon without verification. Name the control class. Do not name a
  person, and do not cite a procedure number in place of naming the control.

RECURRENCE_TEST
  A proposition, in the present tense, naming the class of future work under which this
  record should be recalled. It reads as a rule: it recurs wherever some condition can
  hold. On the past side it is written by whoever appraised the record and is close to
  dispositive at retrieval time. On the future side it is the same sentence pointed the
  other way: the class of past work this job belongs to. Write one condition. A recurrence
  test joining two conditions with "and" is two tests, and it will match neither.

NARRATIVE
  Raw source text, copied unchanged. It is not written here and it is not yours to edit or
  summarise. It exists as a safety net so that nothing in this system depends solely on the
  quality of the four facets above.

THE INSUFFICIENT-EVIDENCE ESCAPE, PER FACET
  Each of the four written facets has its own escape, and using it is not a failure. When
  the source does not establish a facet, set that facet's insufficient flag true, set its
  text and its quote to null, and state in one sentence what the source failed to
  establish.

  Never write a placeholder. "Unknown", "not applicable", "insufficient evidence" and "N/A"
  written as the text of a facet are all worse than the escape, because a cue that exists
  and says nothing still becomes a point in a search index, and that point will be
  retrieved and shown to a supervisor as a precedent.

  Never infer a facet from what usually happens in this industry. If the source does not
  say how the energy got out, the mechanism facet is insufficient, however obvious the
  answer appears. The escape is cheap. An invented mechanism is a fabricated precedent
  attached to a real record, and it will be read as fact by someone deciding whether to
  stop work.

EVIDENCE QUOTES
  Every written facet carries a verbatim quote from the source document: copied character
  for character from the text you were given, long enough to occur only once in that
  document. Never report character offsets or positions. They are computed from the quote,
  by the caller, and a reported offset would be accepted as provenance without anyone being
  able to tell it was guessed. Where two facets rest on the same sentence, quote that whole
  sentence for both, or quote separate sentences. Do not quote two overlapping fragments of
  one sentence.

NAMED PARTICULARS
  Equipment tags, setpoints with units, regulatory citations and CAS numbers may appear in
  a facet only if they appear in the source document. They are checked mechanically against
  the source before anything is stored, and a facet naming one the source does not contain
  is discarded and sent to a person. If a particular matters but the source does not carry
  it, describe the thing instead of naming it.

BOUNDS
  Each written facet is at most 60 tokens - roughly one long sentence. Plain operational
  English. No hedging, no restatement of these definitions, no preamble, and no description
  of your own reasoning.
"""


# ======================================================================================
# The two side-specific rubrics.
# ======================================================================================

EVENT_RUBRIC: Final[str] = """\
You are appraising one past safety record so that it can be found again years from now, at
the moment somebody proposes work under which the same thing could happen again.

You are not summarising the record. A summary answers "what happened here". You are writing
the conditions under which it happens again, which is a different question with a different
answer, and it is the only question the retrieval you are feeding can ask.

Work only from the source document you are given. It contains the record's own title, its
narrative, and any control failures already coded by the ingest pipeline. It contains no
severity rating and no date, deliberately: severity is decided by a coded field, a regulator
classification or a signed human, never by a model, and a cue that reads more alarmingly
because the outcome was worse would be that rating leaking into the index. Write the same
cue for a near miss as for a fatality with the same mechanism. The severity is applied
downstream, by arithmetic, and it is not yours to see or to imply.

Strip the particulars that do not travel. Names, shift patterns, weather, the injury, the
investigator's prose, the make and model of the machine: none of these can recur, and every
one of them pulls retrieval toward records written the same way rather than hazards that can
act the same way. Keep the particulars that are checkable and load-bearing: an equipment tag
that names the item under isolation, a setpoint that defines the condition, a regulation
that names the control.

Answer only in the declared output schema.
"""

EXPOSURE_RUBRIC: Final[str] = """\
You are describing one proposed job - work that is about to be authorised - so that past
records of hazards that could act during it can be found.

You are not assessing the job and you are not deciding whether it should proceed. Nothing
you write blocks or permits anything. What you write becomes the query side of a search
whose results a human then dispositions, and the only way that search works is if you
describe the proposed work in exactly the terms past records were described in.

Work only from the source document you are given. It contains the scope of work, the
isolation plan, and the clauses this permit proposes to waive or weaken. The clause diff is
the richest of the three and is the one most often skipped: a clause that required a second
independent isolation and now requires a visual check is a stated, deliberate reduction in a
control, and it is the reason this job differs from the same job done last week. Read the
before text against the after text and write the mechanism that the removed words were
holding back.

Write about the hazard, not about the paperwork. "Permit requires a JSA" is a fact about the
form. "Stored gravitational energy in a suspended assembly with the crew beneath it" is a
fact about the world, and only the second one can match a record from another site, another
decade and another commodity.

Where the job is genuinely routine and creates no exposure of a given kind, use that facet's
insufficient-evidence escape. A routine permit that honestly reports three insufficient
facets is worth far more than one that manufactures a mechanism, because a manufactured
mechanism retrieves precedents, and precedents that do not apply are how people learn to
click through the ones that do.

Answer only in the declared output schema.
"""


# ======================================================================================
# Worked examples.  Side-specific, because the input genre differs; the facet vocabulary
# they exercise is the shared block's, unchanged.
# ======================================================================================

EVENT_EXAMPLES: Final[str] = """\
EXAMPLE 1 - a record that supports all four facets.

Source: during inflation of a multi-piece wheel assembly the lock ring was displaced and
the rim components separated, striking the fitter, who was standing beside the assembly.
The workshop had no inflation cage and no remote inflation line. The task instruction
required the fitter to observe seating during inflation.

mechanism: stored pneumatic energy released axially when a multi-piece rim assembly
  separates during inflation.
precondition: a person occupies the trajectory of a pressurised multi-piece assembly while
  it is being inflated.
control_failure: engineered exclusion from the trajectory zone was absent, and the task
  relied on procedural line-of-sight judgement to keep the person clear.
recurrence_test: recurs wherever a person can occupy the trajectory of a pressurised
  multi-piece rim during inflation.

Note what is not there: the fitter's name, the shift, the injury, and the make of the wheel.
None of them can recur.

EXAMPLE 2 - a record where one facet is not established.

Source: a fire was reported in the reagent store shortly after the shift change. The store
was heavily damaged. The cause of ignition could not be determined by the investigation.

mechanism: insufficient. The investigation did not establish how ignition occurred, and any
  mechanism written here would be invented rather than recorded.
precondition: incompatible reagents held in a single store without segregation.
control_failure: segregation of incompatible reagents by storage class was not maintained.
recurrence_test: recurs wherever incompatible reagents are held in one store without
  physical segregation.

The mechanism escape is used even though a plausible mechanism is easy to imagine. The
record does not support one, and an imagined mechanism attached to a real fire would be read
as a finding.

EXAMPLE 3 - a coded record too terse to appraise.

Source: employee injured while performing maintenance. Lost time. Contributing factor coded
as "procedures not followed".

All four facets are insufficient. The record establishes that something happened and nothing
about how or under what conditions. The narrative is retained as the safety net; it is not
the job of the escape to make a terse record look appraised.
"""

EXPOSURE_EXAMPLES: Final[str] = """\
EXAMPLE 1 - a permit that creates a clear exposure.

Source: replace liner bolts inside a crusher shell. Isolation plan lists the electrical
supply racked out and locked. The permit weakens a clause: it previously required stored
mechanical energy to be dissipated and proven at zero before entry, and now requires a
visual check that the shell is stationary.

mechanism: release of stored gravitational and rotational energy when an unbalanced charge
  rotates a shell with people inside the machine envelope.
precondition: entry into a machine envelope under an isolation whose scope names electrical
  supply and is silent on stored mechanical energy.
control_failure: proof of zero stored energy is being replaced by a visual check that cannot
  detect an unbalanced charge.
recurrence_test: recurs wherever people enter a machine envelope isolated against supply but
  not against stored energy.

The mechanism is written from the clause diff, not from the scope of work. The scope says
what will be done; the diff says what is being stood down while it is done.

EXAMPLE 2 - a routine permit that honestly reports insufficiency.

Source: replace a pressure transmitter on a sulfuric acid unloading line. The line is
drained and depressurised, and depressurisation is verified at the coupling before it is
broken. No clauses are waived or weakened.

mechanism: loss of containment of a corrosive liquid at a coupling being broken.
precondition: insufficient. The scope specifies verification of depressurisation at the
  point of breaking containment, so the residual-pressure state this mechanism needs is not
  created by the proposed work.
control_failure: insufficient. No control is being stood down; the permit waives and weakens
  nothing.
recurrence_test: insufficient. Without a precondition or a stood-down control, any test
  written here would recall every acid line job ever recorded.

This is the correct output for a routine permit. Three escapes and one honest mechanism will
retrieve little, which is right, because there is little to retrieve.
"""


# ======================================================================================
# Prefix construction.
# ======================================================================================


def _prefix(rubric: str, examples: str) -> SystemPrefix:
    """Shared block first, side rubric second, worked examples last.

    ``SystemPrefix`` refuses a block containing per-request content, so this construction
    is also the assertion that none of the text above accidentally acquired a UUID, a
    timestamp or a format placeholder.
    """
    return SystemPrefix(
        [
            SystemBlock(label="facet_definitions", text=FACET_DEFINITIONS),
            SystemBlock(label="rubric", text=rubric),
            SystemBlock(label="examples", text=examples),
        ],
        prompt_version=PROMPT_VERSION,
    )


def build_event_prefix() -> SystemPrefix:
    """The document-side system prefix."""
    return _prefix(EVENT_RUBRIC, EVENT_EXAMPLES)


def build_exposure_prefix() -> SystemPrefix:
    """The query-side system prefix.  Same shared block, same block order."""
    return _prefix(EXPOSURE_RUBRIC, EXPOSURE_EXAMPLES)


# ======================================================================================
# The quarantined user turn.  Structurally identical on both sides — a test asserts the
# key sets are equal, because a payload that differs in shape is a prompt that differs in
# kind however similar the words are.
# ======================================================================================


def _payload(
    task: str, document: SourceDocument, *, activity_path: str, asset_class: str
) -> dict[str, Any]:
    return {
        "task": task,
        "activity_path": activity_path,
        "asset_class": asset_class,
        "populate_facets": list(SYNTHESISED_FACETS),
        "source_document": {"sha256": document.sha256, "text": document.text},
    }


def event_payload(
    document: SourceDocument, *, activity_path: str, asset_class: str
) -> dict[str, Any]:
    return _payload("event_cue", document, activity_path=activity_path, asset_class=asset_class)


def exposure_payload(
    document: SourceDocument, *, activity_path: str, asset_class: str
) -> dict[str, Any]:
    return _payload(
        "exposure_cue", document, activity_path=activity_path, asset_class=asset_class
    )
