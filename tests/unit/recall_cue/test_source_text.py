# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The canonical document: the bytes shown to the model are the bytes offsets index into."""

from __future__ import annotations

import hashlib

import pytest
from fixtures import (
    DIFF_EXPOSED,
    DIFF_ROUTINE,
    EVENT_FULL,
    ISOLATION_EXPOSED,
    ISOLATION_ROUTINE,
    PERMIT_EXPOSED,
    PERMIT_ROUTINE,
    SITE_ID,
)
from mainline_recall_agent.cue.errors import SourceDocumentError
from mainline_recall_agent.cue.models import EventInput
from mainline_recall_agent.cue.source_text import (
    canonicalise,
    event_source_document,
    exposure_source_document,
)


def test_canonicalisation_is_idempotent() -> None:
    """Otherwise ``source_sha256`` depends on how many times the pipeline ran."""
    messy = "  Line one   with   spaces \r\n\r\n\r\n\r\n Line two \t\n"
    once = canonicalise(messy)
    assert canonicalise(once) == once
    assert "\r" not in once
    assert "\n\n\n" not in once
    assert once == "Line one with spaces\n\nLine two"


def test_the_event_document_carries_the_narrative_at_the_span_it_declares() -> None:
    doc = event_source_document(EVENT_FULL)
    assert doc.text[doc.narrative_start : doc.narrative_end] == doc.narrative
    assert doc.narrative == canonicalise(EVENT_FULL.narrative)
    assert doc.sha256 == hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
    assert "NARRATIVE" in doc.text
    assert "RECORDED CONTROL FAILURES" in doc.text


def test_the_event_document_omits_severity_and_dates() -> None:
    """A cue that reads more alarmingly because the outcome was worse is a rating leak.

    ``EventInput`` has no severity field and no ``occurred_at`` field at all, so this is a
    structural property rather than a filtering step that could be forgotten.
    """
    assert "severity" not in EventInput.model_fields
    assert "occurred_at" not in EventInput.model_fields
    assert "severity" not in event_source_document(EVENT_FULL).text.lower()


def test_the_exposure_document_joins_scope_isolation_and_diff() -> None:
    doc = exposure_source_document(PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED)
    assert doc.narrative == canonicalise(PERMIT_EXPOSED.scope_of_work)
    assert "ISOLATION PLAN" in doc.text
    assert "CLAUSES BEING WAIVED OR WEAKENED" in doc.text
    assert "CR-201" in doc.text


def test_only_waived_or_weakened_clauses_reach_the_exposure_document() -> None:
    """A strengthened clause is not an exposure, and showing it invites a cue about a
    control that is being *added* — which would then retrieve precursors for a hazard this
    permit reduces."""
    doc = exposure_source_document(PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED)
    assert "MEM 4.3" in doc.text
    assert "MEM 9.1" not in doc.text
    assert "[strengthen]" not in doc.text


def test_a_permit_with_no_waivers_still_renders() -> None:
    doc = exposure_source_document(PERMIT_ROUTINE, ISOLATION_ROUTINE, DIFF_ROUTINE)
    assert "CLAUSES BEING WAIVED OR WEAKENED" not in doc.text
    assert doc.narrative.startswith("Replace the pressure transmitter")


def test_a_record_with_a_blank_narrative_is_refused() -> None:
    """The safety net is not optional: a cue set with no narrative has no fallback when
    every synthesised facet turns out to be insufficient."""
    with pytest.raises(SourceDocumentError, match="safety-net narrative"):
        event_source_document(
            EventInput(
                event_id=EVENT_FULL.event_id,
                site_id=SITE_ID,
                taxonomy_ver=3,
                kind="incident",
                title="Title only",
                narrative="   \n  ",
            )
        )


def test_the_document_is_stable_across_calls() -> None:
    left = event_source_document(EVENT_FULL)
    right = event_source_document(EVENT_FULL)
    assert left.sha256 == right.sha256
    assert left.text == right.text
