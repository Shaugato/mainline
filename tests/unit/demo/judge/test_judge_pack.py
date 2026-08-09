# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The shipped pack, validated: legal statements, refused negatives, bounded claims."""

from __future__ import annotations

import pytest
from judge import envelope as env
from judge.pack import (
    IMPLEMENTED_GUARDS,
    PackError,
    load_pack,
    parse_pack,
    selected_columns,
    validate_pack,
)


class TestSelectListParsing:
    def test_a_flat_list_is_read(self):
        assert selected_columns("SELECT a, b, c FROM t LIMIT 1") == ("a", "b", "c")

    def test_aliases_win_over_expressions(self):
        columns = selected_columns("SELECT count(*) AS n, x.y AS z FROM t LIMIT 1")
        assert columns == ("n", "z")

    def test_a_comma_inside_a_call_does_not_split_the_list(self):
        assert selected_columns("SELECT round(x, 3) AS r, y FROM t LIMIT 1") == ("r", "y")


class TestShippedPack:
    def test_it_loads(self, pack):
        assert len(pack) >= 10
        assert pack.positives()
        assert pack.negatives()

    def test_it_validates_with_no_failures(self, pack, repo_root):
        findings = validate_pack(pack, repo_root=repo_root)
        failures = [f.render() for f in findings if f.severity == "fail"]
        assert not failures, "\n".join(failures)

    def test_every_positive_statement_passes_the_envelope(self, pack):
        for question in pack.positives():
            env.enforce(question.sql, verb=question.verb)

    def test_every_negative_statement_is_refused(self, pack):
        assert pack.negatives(), "a pack with no negatives is a pack whose green means nothing"
        for question in pack.negatives():
            with pytest.raises(env.EnvelopeRefusal):
                env.enforce(question.sql, verb=question.verb)

    def test_every_negative_names_a_refusal_that_exists(self, pack):
        for question in pack.negatives():
            assert question.client_refusal in env.REFUSAL_BY_NAME

    def test_every_positive_says_what_it_does_not_prove(self, pack):
        for question in pack.positives():
            assert question.does_not_prove, question.qid

    def test_every_guard_is_implemented(self, pack):
        for question in pack.positives():
            assert question.completeness is not None
            assert question.completeness.guard in IMPLEMENTED_GUARDS

    def test_every_select_carries_an_explicit_page(self, pack):
        for question in pack.positives():
            scanned = env.scan(question.sql)
            assert scanned.explicit_limit is not None, question.qid
            assert scanned.explicit_limit <= env.SELECT_PAGE_ROWS

    def test_the_declared_envelope_equals_the_code(self, pack):
        for key, expected in env.DECLARED_ENVELOPE.items():
            assert pack.declared_envelope[key] == expected, key

    def test_the_on_camera_questions_name_a_shot(self, pack):
        filmed = [q for q in pack if q.beat is not None]
        assert filmed, "the pack carries none of the questions the film asks"
        for question in filmed:
            assert question.shot_id
            assert question.transcribed_from

    def test_every_exemption_states_a_reason(self, pack):
        for exemption in pack.exemptions:
            assert exemption.reason


class TestLoaderStrictness:
    def test_a_pack_without_questions_is_refused(self, tmp_path):
        target = tmp_path / "QUESTIONS.yaml"
        target.write_text("version: 1\nenvelope: {}\n", encoding="utf-8")
        with pytest.raises(PackError):
            load_pack(target)

    def test_an_exemption_without_a_reason_is_refused(self, pack, tmp_path):
        document = dict(pack.raw)
        document["verify_md_exemptions"] = [{"statement_contains": "DROP"}]
        with pytest.raises(PackError):
            parse_pack(document, source=tmp_path / "QUESTIONS.yaml")

    def test_a_missing_pack_is_refused_by_path(self, tmp_path):
        with pytest.raises(PackError):
            load_pack(tmp_path / "absent.yaml")
