# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""What Path B is allowed to be told, and the guard that has now been made to refuse.

Two independent paths are worth running only if neither can forge the other.  The
lattice cannot forge a model opinion — it has no model.  The model could forge a
lattice finding, in exactly two ways, and ``mainline_delta_oracle.prompt`` blocks
both on the shipped path:

* **naming a rule id.**  A block that contains ``R1_DEONTIC`` invites a response
  that contains ``R1_DEONTIC``, and a rationale shaped like a ``DeltaWitness`` is
  one careless renderer away from being read as one.
* **being shown the ``safe_direction`` registry.**  DIRECTRIX decides which way a
  setpoint move is dangerous.  A model told the answer hands it back, and the
  second opinion becomes an echo of the first — two paths on paper, one in fact.

``assert_no_path_a_leakage`` has run on every build since the package was written
and had **no test**.  A guard that has never rejected anything is not a guard
(PL-2), and one whose positive direction is unasserted is worse: it could be
rejecting every real block and nobody would know until the first live call.  This
module asserts both directions — every forbidden token is refused, and every
block that actually ships passes.

**On the loud-failure direction.**  A clause whose own text contains ``R4_EXCEPTION``
makes the call fail rather than being silently scrubbed, and
``test_a_clause_carrying_a_rule_id_fails_loudly`` pins that choice.  A silent
strip is an edit to evidence: the model would then be shown a document that
differs from the one in custody, and the ``source_sha256`` stamped on the block
would be a digest of bytes nobody sent.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Final

import pytest
from mainline_delta_oracle.cassettes import SCENARIOS
from mainline_delta_oracle.oracle import PROMPT_VERSION
from mainline_delta_oracle.prompt import (
    FORBIDDEN_TOKENS,
    TRUSTED_CONTEXT,
    PathALeakage,
    assert_no_path_a_leakage,
    build_untrusted_text,
    render_block,
)
from mainline_delta_oracle.request import (
    MAX_ORIGIN_SUMMARY_CHARS,
    DeltaOracleRequest,
    OriginContext,
)
from mainline_domain.contracts import RULE_IDS, OracleRequest

_SCENARIO_IDS: Final[list[str]] = [item.name for item in SCENARIOS]

#: Field names that would mean the model is being shown Path A's answer.  Matched
#: as substrings against the contract's own field names, so a future field called
#: ``lattice_delta`` fails here rather than in a demo.
_VERDICT_SHAPED: Final[tuple[str, ...]] = ("delta", "verdict", "witness", "basis", "minimal")

_CLEAN = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing."
)


def _request(ancestor: str = _CLEAN, descendant: str = _CLEAN) -> DeltaOracleRequest:
    return DeltaOracleRequest(
        ancestor_text=ancestor,
        descendant_text=descendant,
        ancestor_cat=None,
        descendant_cat=None,
        parameter_hint="gas_test_interval",
        prompt_version=PROMPT_VERSION,
        origin=None,
        source_sha256="",
    )


# --------------------------------------------------------------------------- #
# The guard rejects what it claims to reject                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_the_guard_rejects_every_rule_id(rule_id: str) -> None:
    """All nine, individually, so that adding a rule cannot leave a hole."""
    with pytest.raises(PathALeakage, match=rule_id):
        assert_no_path_a_leakage(f"CLAUSE B\nthe finding was {rule_id} and it is decisive")


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_the_guard_is_case_insensitive(rule_id: str) -> None:
    """Lowercasing a token is the first thing an evasion tries."""
    with pytest.raises(PathALeakage):
        assert_no_path_a_leakage(f"see {rule_id.lower()} for the reasoning")


@pytest.mark.parametrize("token", ["safe_direction", "safe-direction", "directrix", "DIRECTRIX"])
def test_the_guard_rejects_the_registry_in_every_spelling(token: str) -> None:
    """A model told which way is dangerous returns which way is dangerous."""
    with pytest.raises(PathALeakage, match="safe_direction registry"):
        assert_no_path_a_leakage(f"PARAMETER\n{token} = lower_is_safer")


def test_the_guard_names_every_offending_token_at_once() -> None:
    """The diagnosis is the deliverable; one token at a time is three more builds."""
    with pytest.raises(PathALeakage) as raised:
        assert_no_path_a_leakage("R1_DEONTIC and R9_COVERAGE under safe_direction")
    message = str(raised.value)
    assert "R1_DEONTIC" in message
    assert "R9_COVERAGE" in message
    assert "safe_direction" in message


def test_the_guard_covers_every_rule_id_the_contract_declares() -> None:
    """A tenth rule added to ``contracts.RULE_IDS`` extends the guard for free.

    The token list splats ``RULE_IDS`` rather than restating it, and this is the
    assertion that keeps that true: a hand-maintained copy would drift on the
    first new rule, and the drift would be invisible.
    """
    assert set(RULE_IDS) <= set(FORBIDDEN_TOKENS)
    assert {"safe_direction", "safe-direction", "directrix"} <= set(FORBIDDEN_TOKENS)


# --------------------------------------------------------------------------- #
# The guard passes what it must not reject                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("item", SCENARIOS, ids=_SCENARIO_IDS)
def test_every_block_that_actually_ships_passes_the_guard(item) -> None:
    """The converse, over the eleven blocks the committed store was recorded from.

    Without this, a guard that rejected everything would satisfy the tests above
    and would have taken Path B off the wire entirely — which fails closed, and
    would therefore never have been noticed.
    """
    block = render_block(item.request)
    assert_no_path_a_leakage(block)
    untrusted = build_untrusted_text(item.request)
    assert untrusted.text == block
    assert len(untrusted.source_sha256) == 64


def test_a_clause_carrying_a_rule_id_fails_loudly(caplog: pytest.LogCaptureFixture) -> None:
    """Refused, not scrubbed: a silent strip is an edit to evidence."""
    poisoned = f"{_CLEAN} Refer to R4_EXCEPTION of the site standard."
    request = _request(descendant=poisoned)
    with pytest.raises(PathALeakage, match="R4_EXCEPTION"):
        build_untrusted_text(request)
    assert "R4_EXCEPTION" in request.descendant_text, (
        "the request must be untouched: a guard that edited the document would put a "
        "different text on the wire than the one the source digest covers"
    )
    assert caplog.records == [], "a refusal that is only logged is a refusal nobody sees"


# --------------------------------------------------------------------------- #
# What the block contains, and what it structurally cannot                     #
# --------------------------------------------------------------------------- #


def test_the_contract_has_no_field_shaped_like_a_path_a_verdict() -> None:
    """P7 at the type level: the model cannot be shown the answer it is checking.

    Asserted over the field names of both the contract and this package's
    subclass, because the leakage guard is a string search and a structured field
    would sail past it.
    """
    names = {field.name for field in fields(OracleRequest)} | {
        field.name for field in fields(DeltaOracleRequest)
    }
    offending = sorted(
        name for name in names if any(shape in name.lower() for shape in _VERDICT_SHAPED)
    )
    assert offending == [], (
        f"OracleRequest carries {offending}. Path B is given two texts, an incident "
        f"summary and a deterministic tuple diff. It is never given the verdict it "
        f"exists to be a second opinion on."
    )


def test_the_trusted_context_is_constant_and_document_free() -> None:
    """Everything that varies per pair is untrusted; the operator framing is not.

    A trusted context that carried document text would put caller-chosen strings
    inside the system prefix, which is layer 1 of the injection posture, and would
    also make the prefix digest vary per call — turning every cassette into a
    single-use recording.
    """
    rendered = " ".join(str(value) for value in TRUSTED_CONTEXT.values())
    assert "P-101A" not in rendered
    assert "gas_test_interval" not in rendered
    assert_no_path_a_leakage(rendered)
    assert TRUSTED_CONTEXT["compare"] == "B_to_A"
    first = render_block(_request())
    assert render_block(_request()) == first, "the block must be byte-stable for one request"


def test_the_block_carries_exactly_the_four_declared_sections() -> None:
    """Nothing reaches the model that is not one of the four things §6.3 names."""
    origin = OriginContext(
        event_summary="A fitter was overcome.", severity=5, occurred_on="2019-07-14"
    )
    request = DeltaOracleRequest(
        ancestor_text=_CLEAN,
        descendant_text=_CLEAN,
        ancestor_cat=None,
        descendant_cat=None,
        parameter_hint="gas_test_interval",
        prompt_version=PROMPT_VERSION,
        origin=origin,
        source_sha256="",
    )
    block = render_block(request)
    for header in (
        "CLAUSE A — the ancestor version",
        "CLAUSE B — the version under review",
        "BLAME ORIGIN — the recorded incident that wrote clause A",
        "PARAMETER UNDER REVIEW",
        "CONTROL TUPLE DIFF",
    ):
        assert header in block
    assert "coded severity 5" in block, (
        "MI14: severity reaches the model as a stated fact about an incident, carried "
        "rather than asked for, and never comes back"
    )
    assert "commit" not in block.lower()
    assert "permit" not in block.lower()


# --------------------------------------------------------------------------- #
# The injection surface is bounded                                             #
# --------------------------------------------------------------------------- #


def test_an_origin_summary_longer_than_the_bound_is_refused() -> None:
    """A pasted incident report is an unbounded injection surface for no gain."""
    with pytest.raises(ValueError, match="injection surface"):
        OriginContext(event_summary="x" * (MAX_ORIGIN_SUMMARY_CHARS + 1), severity=4)
    assert OriginContext(event_summary="x" * MAX_ORIGIN_SUMMARY_CHARS, severity=4).severity == 4


@pytest.mark.parametrize("severity", [-1, 6, 99])
def test_a_severity_outside_the_coded_scale_is_refused(severity: int) -> None:
    """Severity is coded, regulator-classified or signed — never inferred here."""
    with pytest.raises(ValueError, match=r"coded 0\.\.5 scale"):
        OriginContext(event_summary="A fitter was overcome.", severity=severity)
