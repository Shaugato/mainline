# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The CI grep: one sentence, three places, and it cannot be dropped from any of them.

> **An LLM ops report is evidence that a review occurred, not evidence of a condition.**

Risk AR-8 is not mitigated; it is *stated*. We cannot prove a Steward finding is true —
only that a review ran. The per-finding SQL and result-row hash are what make the weaker
claim checkable, and this sentence is what stops the weaker claim from being read as the
stronger one.

It is a constant in the code (``mainline_steward.findings.EVIDENCE_OF_REVIEW``) rather
than three hand-typed copies, so a rewording is one edit and a deletion is a red test.
The three required places are the emitter's module docstring, the operations runbook, and
this distribution's README.

This module also asserts the payload of a real run carries the sentence, because the
sentence in the source is a promise and the sentence in the record is the thing a reader
actually receives.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from mainline_steward.findings import EVIDENCE_OF_REVIEW


def _flat(text: str) -> str:
    """Whitespace-normalised, lower-cased text.

    The grep is deliberately insensitive to line wrapping. A sentence that has to survive
    reflowing in three documents must not break CI because somebody's editor rewrapped a
    paragraph — the check is about the words, and a check people learn to work around is
    already dead.
    """
    return " ".join(text.split()).lower()


NEEDLE = _flat(EVIDENCE_OF_REVIEW)


def _required_sites(repo: Path) -> dict[str, Path]:
    package = repo / "verticals" / "mainline" / "packages" / "mainline-steward"
    app = repo / "verticals" / "mainline" / "apps" / "steward"
    return {
        "the emitter's module docstring": package / "src" / "mainline_steward" / "attestation.py",
        "the operations runbook": app / "runbooks" / "steward-operations.md",
        "the distribution README": package / "README.md",
    }


@pytest.fixture(scope="module")
def sites(request) -> dict[str, Path]:
    return _required_sites(request.config.rootpath)


class TestTheSentence:
    def test_the_constant_is_exactly_the_sentence(self):
        assert EVIDENCE_OF_REVIEW == (
            "an LLM ops report is evidence that a review occurred, not evidence of a condition"
        )

    @pytest.mark.parametrize(
        "where",
        ["the emitter's module docstring", "the operations runbook", "the distribution README"],
    )
    def test_the_sentence_is_present(self, sites, where):
        path = sites[where]
        assert path.is_file(), f"{where} is missing at {path}"
        haystack = _flat(path.read_text(encoding="utf-8"))
        assert NEEDLE in haystack, (
            f"{where} ({path}) no longer carries the sentence. It is the only claim a "
            "Steward run supports, and a report that has stopped saying so will be read "
            "as evidence of a condition"
        )

    def test_the_emitter_carries_it_in_the_docstring_and_not_only_in_a_comment(self, sites):
        module = ast.parse(sites["the emitter's module docstring"].read_text(encoding="utf-8"))
        docstring = _flat(ast.get_docstring(module) or "")
        assert NEEDLE in docstring, (
            "a comment is strippable and a docstring is not; `help(mainline_steward."
            "attestation)` must show the sentence to somebody who never opens the file"
        )

    def test_the_run_payload_carries_it_too(self, run_config, client):
        from mainline_steward import Emitter, StewardRun, load_schedules

        occurrence = (
            load_schedules(run_config.schedules_path)
            .by_id("operations-weekly")
            .occurrence("2026-08-03T17:00:00Z")
        )
        result = StewardRun(
            run_config, client=client, emitter=Emitter(client, dry_run=True)
        ).execute(occurrence)
        assert result.attestation.payload["disclaimer"] == EVIDENCE_OF_REVIEW

    def test_the_shared_prompt_preamble_states_it_to_the_model_as_well(self, request):
        preamble = (
            request.config.rootpath
            / "verticals"
            / "mainline"
            / "apps"
            / "steward"
            / "prompts"
            / "system-preamble.md"
        )
        assert "{{evidence_of_review}}" in preamble.read_text(encoding="utf-8"), (
            "the preamble substitutes the constant rather than restating it, so the model "
            "is told the same sentence the record carries"
        )
