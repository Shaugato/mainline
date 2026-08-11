# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Both entry points, end to end, against the committed cassettes.

This is the brief's completion test.  Read it as four claims:

1. ``synthesise_event_cue`` and ``synthesise_exposure_cue`` emit **structurally identical**
   five-facet output.
2. The **per-facet** ``insufficient_evidence`` escape is honoured: no row, a logged reason,
   never a placeholder.
3. A cue naming an **equipment tag absent from its source** is rejected *before insert* and
   routed to human review with the offending span hash.
4. A refusal and a dead letter come back as ``CueOutcome`` objects carrying the
   silence-ledger reason, never as swallowed exceptions and never as "no candidates".

**What these cassettes are evidence of.**  They are ``provenance: "handwritten"``: AWS
credentials are not valid on the build machine, so no live Claude response exists to record.
They are evidence about *our pipeline* and about nothing else.  No assertion below claims
anything about how a real model behaves.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fixtures import (
    ACTIVITY_PATH,
    ASSET_CLASS_TYRE,
    CRUSHER_PATH,
    DIFF_EXPOSED,
    DIFF_ROUTINE,
    EVENT_ANCHOR_FABRICATION,
    EVENT_DEADLETTER,
    EVENT_FULL,
    EVENT_INSUFFICIENT,
    EVENT_REFUSAL,
    ISOLATION_EXPOSED,
    ISOLATION_ROUTINE,
    PERMIT_EXPOSED,
    PERMIT_ROUTINE,
)
from mainline_recall_agent.cue.anchors import span_sha256
from mainline_recall_agent.cue.prompts import PROMPT_VERSION
from mainline_recall_agent.cue.schema import FACETS, SYNTHESISED_FACETS, CueOutcome
from mainline_recall_agent.cue.source_text import (
    event_source_document,
    exposure_source_document,
)
from mainline_recall_agent.cue.synthesise import (
    VERBATIM_GEN_MODEL,
    synthesise_event_cue,
    synthesise_exposure_cue,
)
from mainline_recall_agent.cue.template import EMBED_TEMPLATE_SHA256

JudgeFactory = Callable[[], Any]


# --------------------------------------------------------------------------------------
# 1. The happy path, on both sides.
# --------------------------------------------------------------------------------------


def test_event_cue_emits_five_facets_with_computed_spans(replay_judge: JudgeFactory) -> None:
    outcome = synthesise_event_cue(
        EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    assert outcome.status == "synthesised"
    assert outcome.cue is not None
    assert outcome.populated_facets == FACETS
    assert outcome.embed_template_sha256 == EMBED_TEMPLATE_SHA256
    assert outcome.prompt_version == PROMPT_VERSION
    assert outcome.rejections == ()

    document = event_source_document(EVENT_FULL)
    assert outcome.source_sha256 == document.sha256
    # Offsets are ours: every row's span must reproduce a quote out of the exact bytes the
    # model was shown.
    for row in outcome.rows:
        start, end = row.source_span
        assert 0 <= start < end <= len(document.text)
        assert document.text[start:end], "a span must delimit real text"
    narrative_rows = outcome.rows_for("narrative")
    assert {row.source_span for row in narrative_rows} == {document.narrative_span}
    assert {row.cue_text for row in narrative_rows} == {document.narrative}


def test_exposure_cue_emits_the_same_shape_from_permit_inputs(
    replay_judge: JudgeFactory,
) -> None:
    outcome = synthesise_exposure_cue(
        PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED, judge=replay_judge()
    )
    assert outcome.status == "synthesised"
    assert outcome.populated_facets == FACETS
    document = exposure_source_document(PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED)
    assert outcome.source_sha256 == document.sha256
    assert outcome.subject_kind == "exposure"


def test_the_two_sides_produce_structurally_identical_output(
    replay_judge: JudgeFactory,
) -> None:
    """Same model, same fields, same facets, same provenance columns.  Different subject."""
    event = synthesise_event_cue(EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge())
    exposure = synthesise_exposure_cue(
        PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED, judge=replay_judge()
    )
    assert type(event) is type(exposure) is CueOutcome
    assert event.cue is not None and exposure.cue is not None
    assert type(event.cue) is type(exposure.cue)
    assert set(type(event.cue).model_fields) == set(FACETS)
    assert event.populated_facets == exposure.populated_facets
    left_row = event.rows_for("mechanism")[0]
    right_row = exposure.rows_for("mechanism")[0]
    assert type(left_row) is type(right_row)
    assert left_row.prompt_version == right_row.prompt_version
    assert left_row.gen_model == right_row.gen_model
    assert left_row.subject_kind != right_row.subject_kind


def test_rows_are_fanned_across_every_archival_level(replay_judge: JudgeFactory) -> None:
    """The Level-Materialised Bond shape: one row per (facet, level), each its own tree."""
    outcome = synthesise_event_cue(
        EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    assert len(outcome.rows) == len(FACETS) * len(ACTIVITY_PATH.nodes)
    for facet in FACETS:
        levels = sorted(row.scope_level for row in outcome.rows_for(facet))
        assert levels == [node.level for node in ACTIVITY_PATH.nodes]
        scopes = {row.scope_id for row in outcome.rows_for(facet)}
        assert scopes == {node.scope_id for node in ACTIVITY_PATH.nodes}

    shorter = synthesise_exposure_cue(
        PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED, judge=replay_judge()
    )
    assert len(shorter.rows) == len(FACETS) * len(CRUSHER_PATH.nodes)


def test_every_row_carries_its_provenance(replay_judge: JudgeFactory) -> None:
    outcome = synthesise_event_cue(
        EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    for row in outcome.rows:
        assert row.is_derived is True
        assert row.prompt_version == PROMPT_VERSION
        assert row.source_sha256 == outcome.source_sha256
        assert row.embeddable is True
        payload = row.insert_payload()
        assert set(payload) == {
            "event_id",
            "site_id",
            "scope_id",
            "scope_level",
            "facet",
            "taxonomy_ver",
            "cue_text",
            "source_span",
            "is_derived",
            "gen_model",
            "prompt_version",
        }
    derived = [row for row in outcome.rows if row.facet != "narrative"]
    assert {row.gen_model for row in derived} == {"cassette://au-profile-unresolved"}
    # The narrative was copied, not generated.  Attributing it to a model would be a small
    # lie that a later reader would take as evidence the model wrote it.
    assert {row.gen_model for row in outcome.rows_for("narrative")} == {VERBATIM_GEN_MODEL}


def test_the_embedded_text_uses_the_one_template_on_both_sides(
    replay_judge: JudgeFactory,
) -> None:
    event = synthesise_event_cue(EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge())
    exposure = synthesise_exposure_cue(
        PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED, judge=replay_judge()
    )
    for outcome in (event, exposure):
        for row in outcome.rows:
            assert row.embed_text == (
                f"{row.activity_path} | {row.asset_class} | {row.facet}: {row.cue_text.strip()}"
            )


# --------------------------------------------------------------------------------------
# 2. The per-facet escape.
# --------------------------------------------------------------------------------------


def test_an_insufficient_facet_produces_no_row_and_a_logged_reason(
    replay_judge: JudgeFactory,
) -> None:
    outcome = synthesise_event_cue(
        EVENT_INSUFFICIENT, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    assert outcome.status == "synthesised"
    assert outcome.populated_facets == ("precondition", "recurrence_test", "narrative")
    assert outcome.rows_for("mechanism") == ()
    assert outcome.rows_for("control_failure") == ()

    silenced = {silence.facet: silence for silence in outcome.facet_silences}
    assert set(silenced) == {"mechanism", "control_failure"}
    for silence in silenced.values():
        assert silence.cause == "insufficient_evidence"
        assert silence.reason.strip()
    assert "ignition" in silenced["mechanism"].reason


def test_no_placeholder_string_ever_reaches_a_row(replay_judge: JudgeFactory) -> None:
    """The whole point of the escape: absence is recorded as absence, not as a string."""
    outcome = synthesise_event_cue(
        EVENT_INSUFFICIENT, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    banned = ("insufficient", "n/a", "unknown", "not applicable", "none")
    for row in outcome.rows:
        assert row.cue_text.strip().lower() not in banned


def test_a_routine_permit_may_honestly_report_three_escapes(
    replay_judge: JudgeFactory,
) -> None:
    """A routine permit that manufactures a mechanism is how people learn to click through."""
    outcome = synthesise_exposure_cue(
        PERMIT_ROUTINE, ISOLATION_ROUTINE, DIFF_ROUTINE, judge=replay_judge()
    )
    assert outcome.status == "synthesised"
    assert outcome.populated_facets == ("mechanism", "narrative")
    assert len(outcome.facet_silences) == 3
    assert {s.cause for s in outcome.facet_silences} == {"insufficient_evidence"}
    # The safety net still ships, so the permit remains comparable at all.
    assert outcome.rows_for("narrative")


def test_the_narrative_row_survives_every_escape(replay_judge: JudgeFactory) -> None:
    for outcome in (
        synthesise_event_cue(
            EVENT_INSUFFICIENT, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
        ),
        synthesise_exposure_cue(
            PERMIT_ROUTINE, ISOLATION_ROUTINE, DIFF_ROUTINE, judge=replay_judge()
        ),
    ):
        assert outcome.rows_for("narrative"), "the safety net is not optional"


# --------------------------------------------------------------------------------------
# 3. Anchor rejection — the done_when case, end to end.
# --------------------------------------------------------------------------------------


def test_a_cue_citing_a_tag_absent_from_its_source_is_rejected_before_insert(
    replay_judge: JudgeFactory,
) -> None:
    outcome = synthesise_event_cue(
        EVENT_ANCHOR_FABRICATION, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    assert outcome.status == "synthesised"

    # No row, anywhere, at any level, carrying the fabricated tag.
    assert outcome.rows_for("mechanism") == ()
    assert all("K-401" not in row.cue_text for row in outcome.rows)
    assert all("K-401" not in row.embed_text for row in outcome.rows)

    assert len(outcome.rejections) == 1
    rejection = outcome.rejections[0]
    assert rejection.facet == "mechanism"
    assert rejection.anchor_kind == "equipment_tag"
    assert rejection.anchor_normalised == "K-401"
    assert rejection.anchor_sha256 == span_sha256("K-401")
    assert len(rejection.span_sha256) == 64

    # The other three facets are unaffected: rejection is per facet, not per cue set.
    assert outcome.populated_facets == (
        "precondition",
        "control_failure",
        "recurrence_test",
        "narrative",
    )


def test_the_rejected_text_does_not_survive_into_the_cue(
    replay_judge: JudgeFactory,
) -> None:
    """A caller reading ``outcome.cue.mechanism`` must not be able to reach the fabrication."""
    outcome = synthesise_event_cue(
        EVENT_ANCHOR_FABRICATION, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    assert outcome.cue is not None
    assert outcome.cue.mechanism.insufficient is True
    assert outcome.cue.mechanism.cue_text is None
    assert "anchor verification" in (outcome.cue.mechanism.insufficient_reason or "")


def test_the_rejection_routes_to_human_review_with_the_span_hash(
    replay_judge: JudgeFactory,
) -> None:
    """*The injection is evidence* (ARCHITECTURE §8.4 layer 6)."""
    outcome = synthesise_event_cue(
        EVENT_ANCHOR_FABRICATION, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    assert len(outcome.review_routes) == 1
    route = outcome.review_routes[0]
    assert route.finding_kind == "anchor_absent"
    assert route.subject_kind == "event"
    assert route.subject_id == EVENT_ANCHOR_FABRICATION.event_id
    assert route.source_sha256 == outcome.source_sha256
    assert route.anchor_raw == "K-401"
    assert route.prompt_version == PROMPT_VERSION
    assert "absent from the source" in route.detail
    # The finding carries a digest, not the offending text: it is read by people who may
    # not hold the document's classification, and the span may be the injection itself.
    assert route.span_sha256 == outcome.rejections[0].span_sha256
    assert "K-401" not in route.span_sha256


def test_an_anchor_rejection_is_also_a_facet_silence(replay_judge: JudgeFactory) -> None:
    outcome = synthesise_event_cue(
        EVENT_ANCHOR_FABRICATION, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    causes = {silence.facet: silence.cause for silence in outcome.facet_silences}
    assert causes == {"mechanism": "anchor_absent"}


# --------------------------------------------------------------------------------------
# 4. Refusal and dead letter — silence, recorded, never swallowed.
# --------------------------------------------------------------------------------------


def test_a_refusal_becomes_a_silence_record_not_an_exception(
    replay_judge: JudgeFactory,
) -> None:
    """A precursor the model declined to summarise must still block the merge."""
    outcome = synthesise_event_cue(
        EVENT_REFUSAL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
    )
    assert outcome.status == "silenced"
    assert outcome.cue is None
    assert outcome.rows == ()
    assert outcome.silence is not None
    assert outcome.silence.reason == "model_refusal"
    assert outcome.silence.exception_type == "ModelRefusal"
    assert outcome.silence.detail
    assert outcome.source_sha256  # the document still exists and is still identified


def test_a_dead_letter_becomes_abstained_after_exactly_two_calls(
    replay_judge: JudgeFactory,
) -> None:
    """One call, one repair, then stop.  Never a free-text retry loop (ARCHITECTURE §8.4)."""
    judge = replay_judge()
    outcome = synthesise_event_cue(EVENT_DEADLETTER, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=judge)
    assert outcome.status == "silenced"
    assert outcome.silence is not None
    assert outcome.silence.reason == "abstained"
    assert outcome.silence.exception_type == "DeadLetter"
    assert outcome.attempts == 2
    assert judge.call_count == 2


def test_the_silence_reason_is_in_the_closed_vocabulary(replay_judge: JudgeFactory) -> None:
    from mainline_recall_agent.providers.errors import CANONICAL_SILENCE_REASONS

    for outcome in (
        synthesise_event_cue(EVENT_REFUSAL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()),
        synthesise_event_cue(
            EVENT_DEADLETTER, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge()
        ),
    ):
        assert outcome.silence is not None
        assert outcome.silence.reason in CANONICAL_SILENCE_REASONS


def test_a_missing_cassette_is_an_error_rather_than_a_silence(
    replay_judge: JudgeFactory,
) -> None:
    """``CassetteMiss`` has no ``silence_reason``: it is our fixtures being wrong.

    If it were swallowed as silence, a prompt change that invalidated every cassette would
    produce a fully green, fully empty corpus.
    """
    from mainline_recall_agent.cue.models import EventInput
    from mainline_recall_agent.providers.errors import CassetteMiss

    unseen = EventInput(
        event_id=EVENT_FULL.event_id,
        site_id=EVENT_FULL.site_id,
        taxonomy_ver=3,
        kind="incident",
        title="A record no cassette was ever recorded for",
        narrative="Nothing in this narrative matches any committed cassette request.",
        external_ref="FIX-EVT-UNSEEN",
    )
    with pytest.raises(CassetteMiss):
        synthesise_event_cue(unseen, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge())


# --------------------------------------------------------------------------------------
# Replay hygiene.
# --------------------------------------------------------------------------------------


def test_synthesis_is_deterministic_under_replay(replay_judge: JudgeFactory) -> None:
    left = synthesise_event_cue(EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge())
    right = synthesise_event_cue(EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge())
    assert left.model_dump(mode="json") == right.model_dump(mode="json")


def test_every_committed_cue_cassette_declares_handwritten_provenance(
    cassette_root: Path,
) -> None:
    """No test in this file may claim anything about a real model, and this is why."""
    from mainline_recall_agent.providers.cassette import CassetteStore

    documents = CassetteStore(cassette_root).iter_documents("judge")
    assert documents, "the cue cassettes are missing; run make_cue_cassettes.py"
    assert {doc["provenance"] for doc in documents} == {"handwritten"}


@pytest.mark.parametrize("facet", SYNTHESISED_FACETS)
def test_the_facet_vocabulary_is_closed(facet: str) -> None:
    assert facet in FACETS
