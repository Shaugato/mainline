# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``template`` tier: the whole corpus, in prose, with no model and no network.

This is the tier that makes D2 true.  AWS credentials are not valid on the founder's machine,
so the corpus cannot be *allowed* to depend on a model call; ``authored`` covers every word on
camera and this covers the other four thousand three hundred nodes.

------------------------------------------------------------------------------------------
Three properties, and each one is a downstream test
------------------------------------------------------------------------------------------
**Deterministic.**  No draw, no clock, no dict-order dependence, no locale.  The same node
renders to the same bytes on Windows and on ubuntu-latest, which is what lets ``--verify``
recompute an entry rather than merely trust it.

**Era-correct.**  Every concept the text reaches for is looked up by the node's own date in the
vocabulary-drift schedule ``corpus-blame-key`` emitted.  A 2005 record says "danger tagging";
a 2024 record says "positive isolation verification".  If this module reached for the current
surface form the corpus would contain no drift, and ``corpus-embed-lift``'s ``drift_margin``
would measure zero for a reason nobody would notice until capture day.

**Bindable.**  ``mainline.control_failure.evidence_span`` is ``INT8[2] NOT NULL``.  Every
control failure therefore needs a sentence in its event's narrative that occurs **exactly
once**, because the ingestion contract is quote-or-abstain with exact-and-unique matching and
a duplicated sentence silently discards the row.  Each finding sentence names its
``control_class``, and ``(event, control_class)`` is unique by construction upstream — but this
module does not rely on that argument alone.  :mod:`mainline_corpus.render.spans` re-checks
every quote with ``count() == 1`` and refuses the build if a collision ever appears.

------------------------------------------------------------------------------------------
Why the prose is composed rather than sampled
------------------------------------------------------------------------------------------
There is no randomness here at all.  Variety comes from the facts — six event kinds, five
failure modes, four ICAM tiers, eight hazard energies, forty-seven control classes, four
vocabulary eras — and their product is large enough that the corpus does not read as one
sentence repeated.  A sampled synonym table would have added apparent variety and destroyed the
property that matters: that a reader can point at any sentence and say which fact produced it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from . import vocab
from .nodes import long_date
from .params import TIERS
from .protocol import RenderNode, RenderRefusal

__all__ = ["TemplateRenderer"]

#: This tier's census heading, checked against ``params.TIERS`` at import.
TIER_NAME: Final[str] = "template"
if TIER_NAME not in TIERS:  # pragma: no cover - import-time invariant
    raise ImportError(f"{TIER_NAME!r} is not one of params.TIERS")

#: How a document family is referred to in running text.
_FAMILY_NOUN: Final[dict[str, str]] = {
    "ALERT": "safety alert",
    "MOC": "change record",
    "PRO": "procedure",
    "PTW": "permit-to-work form set",
    "STD": "standard",
}

#: The modal a clause revision is written around.  A strengthening reaches for the stronger
#: word and a weakening for the weaker one, so the obligation's direction is legible in the
#: sentence and not only in a column.
_DELTA_MODAL: Final[dict[str, str]] = {
    "introduce": "shall",
    "remove": "shall",
    "restate": "shall",
    "strengthen": "must",
    "weaken": "should",
}

_MODAL_ENUM: Final[dict[str, str]] = {"shall": "shall", "must": "must", "should": "should"}


def _number(value: Any) -> str:
    """Format a setpoint: ``150.0`` prints as ``150``, ``12.5`` as ``12.5``.

    Explicit because ``str(float)`` and ``%g`` disagree at the edges and a locale-aware
    formatter would put a comma in a decimal on a machine set to de_DE.
    """
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.10g}"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _tags(assets: Sequence[Mapping[str, Any]]) -> str:
    return vocab.join_clauses([str(asset["tag"]) for asset in assets])


class TemplateRenderer:
    """Compose prose from the skeleton, the gazetteer and the drift schedule."""

    name = TIER_NAME

    def render(self, node: RenderNode, prompt_version: str) -> Mapping[str, Any]:
        """Return the response object for ``node``."""
        del prompt_version  # the tier's output is versioned by TIER_MODEL_ID, not by the prompt
        handler: Callable[[Mapping[str, Any]], dict[str, Any]] | None = getattr(
            self, f"_render_{node.kind}", None
        )
        if handler is None:
            raise RenderRefusal(f"template tier cannot render node kind {node.kind!r}")
        return handler(node.facts)

    # ── ICAM narrative ──────────────────────────────────────────────────────────────────

    def _render_event_narrative(self, facts: Mapping[str, Any]) -> dict[str, Any]:
        words = facts["vocabulary"]
        assets = facts["assets"]
        tags = _tags(assets)
        site = facts["site"]
        date = long_date(facts["occurred_on"])
        phase = facts["task_phase"]
        energy = facts["hazard_energy"]
        medium = facts["hazard_media"][0]
        failures = facts["control_failures"]
        primary = failures[0] if failures else None

        summary = self._event_summary(facts, tags=tags, site=site, date=date, phase=phase)

        sequence_parts = [
            (
                f"Work was under way in {facts['activity_series']}, "
                f"specifically {facts['activity_file']}."
            ),
            (
                f"{assets[0]['tag']} ({assets[0]['label']}) is in service for "
                f"{assets[0]['service']}."
            ),
        ]
        if primary is not None:
            sequence_parts.append(
                f"The task proceeded {phase} while the {primary['control_label']} "
                f"{vocab.failure_phrase(str(primary['failure_mode']))}."
            )
        sequence_parts.append(
            f"The {energy} energy involved is held as {medium}, and the recorded presentation "
            f"was {facts['hazard_release']}."
        )
        for fact in facts["summary_facts"]:
            sequence_parts.append(f"The record states that {fact}.")

        consequence = self._event_consequence(facts)

        defences = [
            {
                "control_class": str(failure["control_class"]),
                "finding": (
                    f"Control {failure['control_class']}: the {failure['control_label']} "
                    f"{vocab.failure_phrase(str(failure['failure_mode']))}, and the "
                    f"{words['investigation']} classified this as "
                    f"{vocab.icam_tier_phrase(str(failure['icam_tier']))}."
                ),
            }
            for failure in failures
        ]

        recommendations = [
            (
                f"Restore the {failure['control_label']} on {tags} and record the "
                f"{words['verification']} before this task is next authorised."
            )
            for failure in failures
            if failure["icam_tier"] == "absent_or_failed_defence"
        ][:3]
        if not recommendations and failures:
            recommendations = [
                (
                    f"Confirm at the next {words['verification']} that the "
                    f"{failures[0]['control_label']} on {tags} performs as designed."
                )
            ]

        return {
            "summary": summary,
            "sequence": " ".join(sequence_parts),
            "consequence": consequence,
            "defences": defences,
            "recommendations": recommendations,
        }

    @staticmethod
    def _event_summary(
        facts: Mapping[str, Any], *, tags: str, site: str, date: str, phase: str
    ) -> str:
        words = facts["vocabulary"]
        energy = facts["hazard_energy"]
        medium = facts["hazard_media"][0]
        kind = facts["kind"]
        failures = facts["control_failures"]
        first_label = failures[0]["control_label"] if failures else "the control under review"

        if kind == "incident":
            return (
                f"On {date} an incident occurred on {tags} at {site} {phase}, releasing "
                f"{energy} energy held as {medium}."
            )
        if kind == "near_miss":
            return (
                f"On {date} a {words['near_miss']} was recorded on {tags} at {site} {phase}; "
                f"{energy} energy held as {medium} was not released."
            )
        if kind == "audit_finding":
            return (
                f"On {date} a planned {words['verification']} of {tags} at {site} found the "
                f"{first_label} not effective."
            )
        if kind == "capa":
            return (
                f"On {date} a corrective action on {tags} at {site} was reviewed against the "
                f"{words['critical_control']} it was raised to restore."
            )
        if kind == "regulator_notice":
            return (
                f"On {date} a regulatory notice was issued concerning {tags} at {site} "
                f"following {phase.removeprefix('during ')}."
            )
        if kind == "oem_alert":
            return (
                f"On {date} the original equipment manufacturer issued an advisory affecting "
                f"{tags} at {site}."
            )
        raise RenderRefusal(
            f"event kind {kind!r} has no summary form in the template tier. A default sentence "
            "here would make two events read identically and break the evidence binding."
        )

    @staticmethod
    def _event_consequence(facts: Mapping[str, Any]) -> str:
        consequence = facts["consequence"]
        injuries = int(consequence["injuries"])
        days = int(consequence["days_lost"])
        parts = [f"The recorded outcome was {consequence['label']}"]
        if injuries:
            parts.append(f"{injuries} {_plural(injuries, 'person')} injured")
        if days:
            parts.append(f"{days} {_plural(days, 'day')} lost")
        sentence = (
            ", with ".join([parts[0], vocab.join_clauses(parts[1:])])
            if injuries or days
            else parts[0]
        )
        actual = int(facts["severity_actual"])
        potential = int(facts["severity_potential"])
        tail = ""
        if potential > actual:
            tail = (
                f" The potential outcome was rated {potential} against the site's consequence "
                f"scale, above the {actual} actually realised."
            )
        return f"{sentence}.{tail}"

    # ── clause body ─────────────────────────────────────────────────────────────────────

    def _render_clause_text(self, facts: Mapping[str, Any]) -> dict[str, Any]:
        words = facts["vocabulary"]
        delta = str(facts["control_delta"])
        modal = _DELTA_MODAL.get(delta)
        if modal is None:
            raise RenderRefusal(f"control_delta {delta!r} has no wording in the template tier")
        family = _FAMILY_NOUN.get(str(facts["doc_family"]), "controlled document")
        label = str(facts["control_label"])
        setpoint = facts["setpoint"]

        if delta == "introduce":
            body = (
                f"The {label} {modal} be provided and maintained for work covered by this {family}."
            )
        elif delta == "strengthen":
            body = (
                f"The {label} {modal} be provided, and its effectiveness {modal} be recorded "
                f"as a {words['verification']} before the task proceeds."
            )
        elif delta == "weaken":
            body = (
                f"The {label} {modal} be provided; the {words['verification']} may be recorded "
                f"at the next scheduled review rather than before the task proceeds."
            )
        elif delta == "restate":
            body = (
                f"The {label} {modal} be provided and maintained wherever this {family} "
                f"applies, and its condition {modal} be treated as a {words['critical_control']}."
            )
        else:  # remove
            body = (
                f"This requirement is withdrawn. The {label} is no longer imposed by this "
                f"{family}; the duty is discharged under the document that supersedes this "
                f"clause."
            )

        if setpoint is not None and setpoint.get("to") is not None:
            body += (
                f" The {setpoint['label']} {modal} be set at "
                f"{_number(setpoint['to'])} {setpoint['unit']}."
            )
        if str(facts["activity_root"]) and delta != "remove":
            body += (
                f" This clause applies to activities archived under "
                f"{facts['activity_root']} at {facts['site']}."
            )

        return {"body": body, "obligation_verb": _MODAL_ENUM[modal]}

    # ── MOC justification ───────────────────────────────────────────────────────────────

    def _render_moc_justification(self, facts: Mapping[str, Any]) -> dict[str, Any]:
        words = facts["vocabulary"]
        ref = str(facts["moc_ref"])
        date = long_date(facts["opened_on"])
        intent = str(facts["intent"])
        clauses = int(facts["clause_count"])
        precursors = [str(item["event_ref"]) for item in facts["precursor_events"]]
        docs = [str(code) for code in facts["doc_codes"]]

        if precursors:
            opening = (
                f"{ref} was raised at {facts['site']} on {date} following "
                f"{len(precursors)} recorded {_plural(len(precursors), 'event')} in the "
                f"archive, including {vocab.join_clauses(precursors[:3])}."
            )
        else:
            opening = (
                f"{ref} was raised at {facts['site']} on {date} as a scheduled change under "
                f"{words['management_of_change']}; no event precedes it in the record."
            )

        if clauses:
            coverage = (
                f"The {words['management_of_change']} record covers {clauses} "
                f"{_plural(clauses, 'clause')} across "
                f"{len(docs)} controlled {_plural(len(docs), 'document')}."
            )
        else:
            coverage = (
                f"The {words['management_of_change']} record carries no clause change; it "
                f"records the assessment only."
            )

        intent_sentence = self._moc_intent_sentence(intent, words)
        state = f"The record reached the state {facts['terminal_state']} in the change stream."

        scope_note = (
            f"The documents in scope are {vocab.join_clauses(docs)}."
            if docs
            else "No controlled document is in scope; the change is administrative."
        )

        steps = int(facts["weakening_steps"])
        if intent == "weaken" or steps:
            risk_note = (
                f"This change relaxes a control: {steps} "
                f"{_plural(steps, 'step')} of relaxation "
                f"{'is' if steps == 1 else 'are'} recorded against it, and the residual risk "
                f"position rests on that relaxation having been accepted deliberately."
            )
        else:
            risk_note = (
                f"No control is relaxed by this change; the residual risk position is unchanged "
                f"or improved, and the {words['critical_control']} set is preserved."
            )

        return {
            "justification": " ".join([opening, coverage, intent_sentence, state]),
            "scope_note": scope_note,
            "risk_note": risk_note,
        }

    @staticmethod
    def _moc_intent_sentence(intent: str, words: Mapping[str, str]) -> str:
        sentences = {
            "introduce": (
                "The intent is to introduce a duty the documents in scope did not previously carry."
            ),
            "replace": (
                "The intent is to replace an existing requirement with one written to the "
                "current house style."
            ),
            "restate": (
                "The intent is to restate an existing duty without altering what it requires."
            ),
            "split": (
                "The intent is to move a body of requirements into a separate controlled "
                "document while preserving each clause's identity."
            ),
            "strengthen": (
                f"The intent is to strengthen the {words['critical_control']} named in the "
                f"documents in scope."
            ),
            "weaken": (
                f"The intent is to relax a {words['critical_control']} requirement, and the "
                f"basis for the relaxation is recorded with the change."
            ),
        }
        try:
            return sentences[intent]
        except KeyError:
            raise RenderRefusal(
                f"MOC intent {intent!r} has no wording in the template tier"
            ) from None

    # ── revision reason ─────────────────────────────────────────────────────────────────

    def _render_revision_reason(self, facts: Mapping[str, Any]) -> dict[str, Any]:
        words = facts["vocabulary"]
        driver = str(facts["driver"])
        touched = int(facts["clauses_touched"])
        rev_no = int(facts["rev_no"])
        family = _FAMILY_NOUN.get(str(facts["doc_family"]), "controlled document")
        year = str(facts["effective_on"])[:4]

        if driver == "incident" and facts["driving_event_ref"]:
            reason = (
                f"Revised after {facts['driving_event_ref']}; {touched} "
                f"{_plural(touched, 'clause')} amended."
            )
        elif driver == "moc" and facts["driving_change_ref"]:
            reason = (
                f"Revised under {facts['driving_change_ref']}; {touched} "
                f"{_plural(touched, 'clause')} amended."
            )
        elif driver == "retypeset":
            reason = (
                f"Full retypeset to the {year} house style; numbering reissued, requirements "
                f"unchanged."
            )
        elif driver == "introduce":
            reason = f"First issue of this {family}."
        else:
            reason = (
                f"Scheduled review at revision {rev_no}; {touched} "
                f"{_plural(touched, 'clause')} restated."
            )

        citations = [
            {
                "quote_ref": str(citation["quote_ref"]),
                "line": self._citation_line(citation, family=family, rev_no=rev_no, words=words),
            }
            for citation in facts["required_citations"]
        ]
        return {"reason": reason, "citations": citations}

    @staticmethod
    def _citation_line(
        citation: Mapping[str, Any], *, family: str, rev_no: int, words: Mapping[str, str]
    ) -> str:
        event_ref = str(citation["event_ref"])
        control = citation.get("control_label")
        subject = f"the {control}" if control else "the control named in the record"
        kind = str(citation["kind"])
        if kind == "revision_history_line":
            return (
                f"Revision {rev_no} was raised in response to {event_ref}, and {subject} was "
                f"amended as a result."
            )
        if kind == "capa_action":
            return (
                f"The corrective action recorded against {event_ref} required {subject} to be "
                f"restated in this {family}."
            )
        if kind == "moc_reference":
            return (
                f"The {words['management_of_change']} record for this revision cites "
                f"{event_ref} as the reason {subject} was amended."
            )
        if kind == "investigation_recommendation":
            return (
                f"The {words['investigation']} into {event_ref} recommended that {subject} be "
                f"strengthened in this {family}."
            )
        if kind == "regulator_requirement":
            return (
                f"A regulatory requirement arising from {event_ref} obliges this {family} to "
                f"carry {subject}."
            )
        raise RenderRefusal(
            f"quote_ref kind {kind!r} has no citation wording in the template tier. Adding a "
            "default here would make two citation lines identical, and an ambiguous quote is "
            "discarded rather than guessed."
        )
