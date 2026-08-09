# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The hostile corpus: every case asserts a NAMED outcome, not that something went wrong.

Read one failure message from this file and you know which document, which layer, which
detector, and what the corpus expected instead. That is the whole design: a suite that
only proved "an exception was raised" could not tell a reviewer whether the right control
fired, and in a six-layer posture the identity of the layer is most of the information.

Four properties are asserted over the corpus as a whole, and they are what stop it from
being a list of things that happen to pass:

* **every named class has at least one case** - a class with no evidence is a claim;
* **every negative control is clean** - a screen that refuses everything would otherwise
  pass a corpus made entirely of attacks;
* **every non-clean outcome wrote a finding** - layer 6, tested rather than asserted;
* **both anchor extractors agree, document by document** - so the offline lane and the
  integration lane are the same control rather than two similar ones.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from corpus_loader import CASES
from mainline_quarantine.anchoring import Cue, verify_anchors
from mainline_quarantine.classes import OUTCOME_LAYER, AttackClass, Layer, Outcome
from mainline_quarantine.errors import SentinelCollision
from mainline_quarantine.finding import utc_now
from mainline_quarantine.pipeline import UntrustedDocument, intake

FIXED_INSTANT = utc_now()

IDS = [case["id"] for case in CASES]


def _document(case) -> UntrustedDocument:
    return UntrustedDocument(
        doc_id=case["id"],
        text=case["document"],
        source_sha256=case["document_sha256"],
        media_type=case.get("media_type", "text/plain"),
    )


def _cue(case) -> Cue | None:
    raw = case.get("cue")
    if raw is None:
        return None
    return Cue(
        cue_id=raw["cue_id"],
        text=raw["text"],
        declared_anchors=tuple(raw.get("declared_anchors", ())),
    )


def _run(case, screen, extractor, extraction_schema):
    cue = _cue(case)
    return intake(
        _document(case),
        screen=screen,
        proposal=case.get("proposal"),
        schema=extraction_schema if case.get("proposal") is not None else None,
        baseline=case.get("baseline"),
        cue=cue,
        extractor=extractor if cue is not None else None,
        observed_at=FIXED_INSTANT,
        sentinel="MAINLINE-UNTRUSTED-0000000000000000",
        tag_suffix="corpusfixed",
    )


# --------------------------------------------------------------------------- #
# The corpus itself                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case_produces_its_named_outcome(case, screen, fallback_extractor, extraction_schema):
    """Each document produces the exact outcome its file declares."""
    if case.get("expects_sentinel_collision"):
        with pytest.raises(SentinelCollision):
            _run(case, screen, fallback_extractor, extraction_schema)
        # The document is still screened, because a refusal to send is not a record of
        # what was sent. Layer 6 wants the finding either way.
        result = screen.screen(case["document"])
        assert result.outcome is Outcome(case["expected_outcome"]), case["_path"]
        return

    verdict = _run(case, screen, fallback_extractor, extraction_schema)
    expected = Outcome(case["expected_outcome"])
    assert verdict.outcome is expected, (
        f"{case['_path']}: expected {expected}, got {verdict.outcome} "
        f"(detector={verdict.screen.detector if verdict.screen else None!r})"
    )


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case_is_attributed_to_the_layer_it_names(
    case, screen, fallback_extractor, extraction_schema
):
    """The outcome and the layer agree, so a case cannot pass because a different control fired."""
    if case.get("expects_sentinel_collision"):
        pytest.skip("refused before the pipeline runs; covered by test_layers.py")
    verdict = _run(case, screen, fallback_extractor, extraction_schema)
    if not case["expected_layer"]:
        assert verdict.layer is None, case["_path"]
        return
    expected_layer = Layer(case["expected_layer"])
    assert verdict.layer is expected_layer, case["_path"]
    assert OUTCOME_LAYER[verdict.outcome] is expected_layer, (
        f"{case['_path']}: the outcome/layer table disagrees with the case file"
    )


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("expected_detector")],
    ids=[case["id"] for case in CASES if case.get("expected_detector")],
)
def test_named_detector_is_the_one_that_fired(case, screen):
    """A blocked case names the rule that blocked it, so a broad regex cannot absorb the corpus."""
    result = screen.screen(case["document"])
    assert result.detector == case["expected_detector"], (
        f"{case['_path']}: expected detector {case['expected_detector']!r}, got {result.detector!r}"
    )


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("expected_rejections")],
    ids=[case["id"] for case in CASES if case.get("expected_rejections")],
)
def test_anchor_rejections_name_the_forged_anchor(case, fallback_extractor):
    """A layer-4 case names which anchor was forged, not merely that one was."""
    cue = _cue(case)
    assert cue is not None
    verdict = verify_anchors(cue, case["document"], fallback_extractor)
    described = {f"{rejection.anchor_class}:{rejection.value}" for rejection in verdict.rejections}
    for expected in case["expected_rejections"]:
        assert expected in described, (
            f"{case['_path']}: expected rejection {expected!r}, got {sorted(described)}"
        )


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("expected_distorted_fields")],
    ids=[case["id"] for case in CASES if case.get("expected_distorted_fields")],
)
def test_value_only_distortion_names_the_fields_that_moved(
    case, screen, fallback_extractor, extraction_schema
):
    """The residual is reported as field paths. 'At worst a value' is a number, not a hope."""
    verdict = _run(case, screen, fallback_extractor, extraction_schema)
    assert verdict.containment is not None
    assert sorted(verdict.containment.distorted_fields) == sorted(
        case["expected_distorted_fields"]
    ), case["_path"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_injected_span_is_actually_in_the_document(case):
    """A case whose declared attack is not in its own document is a case that proves nothing."""
    if not case["injected_span"]:
        assert case.get("benign"), case["_path"]
        return
    assert case["injected_span"] in case["document"], (
        f"{case['_path']}: declared injected_span is not a substring of the document"
    )


# --------------------------------------------------------------------------- #
# Properties of the corpus as a whole                                          #
# --------------------------------------------------------------------------- #


def test_corpus_is_large_enough_to_be_a_corpus():
    """At least forty hostile documents, plus negative controls."""
    hostile = [case for case in CASES if not case.get("benign")]
    benign = [case for case in CASES if case.get("benign")]
    assert len(hostile) >= 40, f"only {len(hostile)} hostile documents"
    assert len(benign) >= 5, f"only {len(benign)} negative controls"


def test_every_named_attack_class_has_a_case():
    """A class with no case is a claim with no evidence."""
    covered = {case["class"] for case in CASES if not case.get("benign")}
    missing = sorted(
        attack_class.value for attack_class in AttackClass if attack_class.value not in covered
    )
    assert not missing, f"attack classes with no corpus case: {missing}"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_document_sha256_is_the_digest_of_the_source_bytes(case, corpus_dir):
    """The join back to the Object-Locked object, checked rather than assumed.

    A finding whose ``document_sha256`` does not identify the bytes it came from is an
    anecdote, not evidence. A stranger adding a case computes this the same way: sha256
    of the document text as UTF-8, or of the PDF file when the case has one.
    """
    if case.get("pdf"):
        source = (corpus_dir / case["pdf"]).read_bytes()
    else:
        source = case["document"].encode("utf-8")
    assert case["document_sha256"] == hashlib.sha256(source).hexdigest(), case["_path"]


def test_case_ids_are_unique():
    """Two cases with one id would silently overwrite each other in the corpus directory."""
    assert len(IDS) == len(set(IDS))


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("benign")],
    ids=[case["id"] for case in CASES if case.get("benign")],
)
def test_negative_controls_are_clean(case, screen, fallback_extractor, extraction_schema):
    """A screen that refuses everything passes a corpus made entirely of attacks."""
    verdict = _run(case, screen, fallback_extractor, extraction_schema)
    assert verdict.outcome is Outcome.CLEAN, (
        f"{case['_path']}: benign document was not clean "
        f"({verdict.outcome}, detector="
        f"{verdict.screen.detector if verdict.screen else None!r})"
    )
    assert verdict.findings == ()


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_every_non_clean_outcome_wrote_a_finding(
    case, screen, fallback_extractor, extraction_schema
):
    """Layer 6. A refusal that writes nothing turns an attack into silence."""
    if case.get("expects_sentinel_collision"):
        pytest.skip("refused before the pipeline runs; covered by test_layers.py")
    verdict = _run(case, screen, fallback_extractor, extraction_schema)
    if verdict.outcome is Outcome.CLEAN:
        assert verdict.findings == ()
        return
    assert verdict.findings, f"{case['_path']}: {verdict.outcome} produced no finding"
    finding = verdict.findings[-1]
    assert finding.outcome is verdict.outcome
    assert finding.route == "human_review"
    assert finding.document_sha256 == case["document_sha256"]
    row = finding.to_row()
    assert row["document_sha256"] == case["document_sha256"]
    assert case["document"] not in json.dumps(row), (
        f"{case['_path']}: the finding row reproduced the document text; findings carry "
        f"the digest of a span, never the span"
    )


# --------------------------------------------------------------------------- #
# The two extractors are one control                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_both_anchor_extractors_agree_on_every_document(
    case, fallback_extractor, domain_anchor_extractor
):
    """ANCHORLOCK and the committed-gazetteer fallback extract the same anchors.

    Skips - loudly, with the import error - when ``mainline_domain`` is not importable.
    That is the whole point of the Protocol: the integration lane is consumed when it is
    there and never simulated when it is not.
    """
    checked = {
        "equipment_tag",
        "isolation_point_id",
        "instrument_loop",
        "regulatory_citation",
        "cas",
        "setpoint",
    }

    def normed(extractor, text):
        return {(cls, norm) for cls, _raw, norm, _span in extractor.extract(text) if cls in checked}

    document = case["document"]
    assert normed(fallback_extractor, document) == normed(domain_anchor_extractor, document), (
        f"{case['_path']}: the fallback extractor and ANCHORLOCK disagree. One of the two "
        f"has changed what counts as an anchor, which changes what layer 4 refuses."
    )


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("cue")],
    ids=[case["id"] for case in CASES if case.get("cue")],
)
def test_layer_four_verdict_is_the_same_in_both_lanes(
    case, fallback_extractor, domain_anchor_extractor
):
    """Both extractors reach the same layer-4 outcome on every anchored case."""
    cue = _cue(case)
    assert cue is not None
    fallback = verify_anchors(cue, case["document"], fallback_extractor)
    integration = verify_anchors(cue, case["document"], domain_anchor_extractor)
    assert fallback.outcome is integration.outcome, case["_path"]
    assert {(r.anchor_class, r.value) for r in fallback.rejections} == {
        (r.anchor_class, r.value) for r in integration.rejections
    }, case["_path"]
