# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The verifier: what survives a model proposal, and what is dropped with a name.

The shape of this file is the argument. One test says a good proposal becomes a row;
seven say a bad one becomes a *recorded drop*. A drop that is not recorded is a silence,
and a silence in a recall path is the defect this product exists to refuse.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from corpus import (
    CLAUSE_ISOLATION,
    COMMIT_HEX,
    FABRICATED_QUOTE,
    ISOLATION_TEXT,
    OTHER_SITE,
    SITE,
)
from mainline_cartographer import (
    CONFIDENCE_P_LINK_MILLI,
    DROP_REASONS,
    BlameBasis,
    BlameLinkProposal,
    BlameState,
    ClauseCandidate,
    ProposedLink,
    QuoteAmbiguous,
    QuoteUnbound,
    bind_quote,
    verify_links,
)

UNTIL = datetime(2026, 12, 1, tzinfo=UTC)

GOOD_NARRATIVE_QUOTE = "the upstream isolation point was not locked"
GOOD_EVIDENCE_QUOTE = "isolation shall be applied at every upstream isolation point and locked"


def link(**overrides) -> ProposedLink:
    payload = {
        "candidate_label": "C1",
        "link_kind": "control_named",
        "control_class": "energy_isolation",
        "narrative_quote": GOOD_NARRATIVE_QUOTE,
        "evidence_quote": GOOD_EVIDENCE_QUOTE,
        "confidence_band": "high",
    }
    payload.update(overrides)
    return ProposedLink(**payload)


def proposal(*links: ProposedLink, **overrides) -> BlameLinkProposal:
    payload = {
        "abstained": not links,
        "abstain_reason": "none" if links else "no_candidate_linked",
        "links": list(links),
    }
    payload.update(overrides)
    return BlameLinkProposal(**payload)


def run(prop, event, candidates):
    return verify_links(
        prop,
        event=event,
        candidates=candidates,
        commit_id=COMMIT_HEX,
        model_id="au.anthropic.claude-opus-5",
        prompt_version="blame_link.v1+rubric.v1",
        provisional_until=UNTIL,
    )


def test_a_supported_link_becomes_a_provisional_inferred_edge(fatality, candidates):
    verified = run(proposal(link()), fatality, candidates)
    assert verified.dropped == ()
    (edge,) = verified.edges
    assert edge.clause_uuid == CLAUSE_ISOLATION
    assert edge.event_id == fatality.event_id
    assert edge.basis is BlameBasis.INFERRED_SEMANTIC
    assert edge.state is BlameState.PROVISIONAL
    # The score is ours, derived from a named band, and it is an integer.
    assert edge.p_link_milli == CONFIDENCE_P_LINK_MILLI["high"]
    assert isinstance(edge.p_link_milli, int)
    # We computed the span; the model never reported one.
    start, end = edge.evidence_span
    assert ISOLATION_TEXT[start:end] == GOOD_EVIDENCE_QUOTE
    assert edge.features["offsets_computed_by"].endswith("bind_quote")
    # Prose a human is shown, never a bare number.
    assert "provisional" in edge.attribution.lower()
    assert str(edge.p_link_milli) not in edge.attribution


def test_a_hallucinated_label_is_dropped_not_repaired(fatality, candidates):
    verified = run(proposal(link(candidate_label="C9")), fatality, candidates)
    assert verified.edges == ()
    (drop,) = verified.dropped
    assert drop.reason == "unknown_candidate"


def test_a_control_class_the_incident_never_recorded_is_dropped(fatality, candidates):
    """Layer 4. An injection can change a value; it cannot conjure a failed barrier."""
    verified = run(proposal(link(control_class="working_at_height")), fatality, candidates)
    assert verified.edges == ()
    (drop,) = verified.dropped
    assert drop.reason == "control_class_not_in_source"


def test_a_fabricated_evidence_quote_does_not_bind(fatality, candidates):
    """The poisoned clause's payoff: a quote that reads plausibly but is not in the text."""
    verified = run(
        proposal(link(candidate_label="C3", evidence_quote=FABRICATED_QUOTE)),
        fatality,
        candidates,
    )
    assert verified.edges == ()
    (drop,) = verified.dropped
    assert drop.reason == "evidence_quote_unbound"


def test_a_quote_from_the_wrong_candidate_does_not_bind(fatality, candidates):
    verified = run(
        proposal(link(candidate_label="C2", control_class="atmospheric_testing")),
        fatality,
        candidates,
    )
    assert verified.edges == ()
    (drop,) = verified.dropped
    assert drop.reason == "evidence_quote_unbound"


def test_an_ambiguous_quote_is_dropped(fatality):
    """A span that could be either of two places is not a span."""
    repeated = "the isolation shall be applied"
    doubled = ClauseCandidate(
        label="C1",
        clause_uuid=CLAUSE_ISOLATION,
        site_id=SITE,
        canon_text=f"1. {repeated} at the valve. 2. {repeated} at the pump.",
    )
    verified = run(proposal(link(evidence_quote=repeated)), fatality, (doubled,))
    assert verified.edges == ()
    (drop,) = verified.dropped
    assert drop.reason == "evidence_quote_ambiguous"


def test_a_narrative_quote_that_is_not_in_the_incident_is_dropped(fatality, candidates):
    verified = run(
        proposal(link(narrative_quote="the second person confirmed the isolation")),
        fatality,
        candidates,
    )
    assert verified.edges == ()
    (drop,) = verified.dropped
    assert drop.reason == "narrative_quote_unbound"


def test_a_cross_site_link_is_dropped(fatality):
    offsite = ClauseCandidate(
        label="C1", clause_uuid=CLAUSE_ISOLATION, site_id=OTHER_SITE, canon_text=ISOLATION_TEXT
    )
    verified = run(proposal(link()), fatality, (offsite,))
    assert verified.edges == ()
    (drop,) = verified.dropped
    assert drop.reason == "site_mismatch"


def test_the_same_clause_twice_is_dropped_once(fatality, candidates):
    """blame_edge's primary key is (clause_uuid, event_id, basis)."""
    verified = run(proposal(link(), link(confidence_band="low")), fatality, candidates)
    assert len(verified.edges) == 1
    (drop,) = verified.dropped
    assert drop.reason == "duplicate_link"


def test_every_drop_reason_is_in_the_closed_vocabulary(fatality, candidates):
    verified = run(
        proposal(
            link(candidate_label="C9"),
            link(control_class="working_at_height"),
            link(candidate_label="C3", evidence_quote=FABRICATED_QUOTE),
        ),
        fatality,
        candidates,
    )
    assert {drop.reason for drop in verified.dropped} <= DROP_REASONS
    arithmetic = verified.arithmetic()
    assert arithmetic["proposed"] == 3
    assert arithmetic["verified"] == 0
    assert arithmetic["dropped"] == 3


def test_an_injection_note_survives_into_the_result(fatality, candidates):
    """The injection is evidence. It is recorded; it is never acted on."""
    verified = run(
        proposal(
            link(),
            injection_noted=True,
            injection_note="clause C3 contained a line addressed to the reader",
        ),
        fatality,
        candidates,
    )
    assert verified.injection_noted is True
    assert "C3" in verified.injection_note
    assert verified.arithmetic()["injection_noted"] is True


def test_bind_quote_refuses_rather_than_guessing():
    with pytest.raises(QuoteUnbound):
        bind_quote("alpha beta", "gamma", where="test")
    with pytest.raises(QuoteAmbiguous):
        bind_quote("alpha alpha", "alpha", where="test")
    assert bind_quote("alpha beta", "beta", where="test") == (6, 10)


def test_provisional_until_must_be_timezone_aware(fatality, candidates):
    with pytest.raises(ValueError, match="naive datetime"):
        verify_links(
            proposal(link()),
            event=fatality,
            candidates=candidates,
            commit_id=COMMIT_HEX,
            model_id="au.anthropic.claude-opus-5",
            prompt_version="blame_link.v1+rubric.v1",
            provisional_until=datetime(2026, 12, 1),  # noqa: DTZ001 - the point of the test
        )


def test_provenance_is_folded_into_features(fatality, candidates):
    verified = verify_links(
        proposal(link()),
        event=fatality,
        candidates=candidates,
        commit_id=COMMIT_HEX,
        model_id="au.anthropic.claude-opus-5",
        prompt_version="blame_link.v1+rubric.v1",
        provisional_until=UNTIL + timedelta(days=1),
        provenance={"input_sha256": "0" * 64, "attempts": 1},
    )
    (edge,) = verified.edges
    assert edge.features["provenance"]["input_sha256"] == "0" * 64
