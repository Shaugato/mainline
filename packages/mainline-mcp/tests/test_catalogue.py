# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The contract loader: tolerant about spelling, strict about substance.

The contract of record is another worker's file. So a plausible synonym for a key must
not break the build — but a missing view, a schema outside ``mainline_audit`` or a
non-integer budget must, and must say which entry was wrong.
"""

from __future__ import annotations

import pytest
import yaml
from mainline_mcp.catalogue import (
    ARCHITECTURE_VIEWS,
    ContractError,
    contract_path,
    load_contract,
    negative_assertions_path,
    parse_contract,
)
from mainline_mcp.limits import BUDGET_RESPONSE_BYTES, BUDGET_ROWS


class TestReferenceFixture:
    def test_reference_fixture_matches_architecture(self, catalogue):
        assert catalogue.names() == ARCHITECTURE_VIEWS

    def test_no_divergence_in_either_direction(self, catalogue):
        missing, extra = catalogue.divergence_from_architecture()
        assert missing == ()
        assert extra == ()

    def test_every_view_generates_its_own_statement(self, catalogue):
        for view in catalogue.views:
            expected = f"SELECT * FROM mainline_audit.{view.name} LIMIT {view.row_cap}"  # noqa: S608
            assert view.statement == expected

    def test_defaults_are_the_eighty_percent_budget(self, catalogue):
        assert catalogue.default_byte_budget == BUDGET_RESPONSE_BYTES
        assert catalogue.default_row_cap == BUDGET_ROWS
        for view in catalogue.views:
            assert view.byte_budget == BUDGET_RESPONSE_BYTES
            assert view.row_cap == BUDGET_ROWS

    def test_the_two_views_with_a_completeness_flag_declare_it(self, catalogue):
        flagged = {v.name for v in catalogue.views if v.truncation_flag is not None}
        assert flagged == {"v_weakenings_without_disposition", "v_disposition_coverage"}
        for name in flagged:
            assert catalogue.by_name(name).truncation_flag == "ancestry_complete"

    def test_an_unknown_view_is_refused_with_the_available_list(self, catalogue):
        with pytest.raises(ContractError) as excinfo:
            catalogue.by_name("v_not_a_view")
        assert "v_open_gate_summary" in str(excinfo.value)


class TestTolerance:
    def test_views_may_be_a_mapping_instead_of_a_list(self):
        document = yaml.safe_load(
            """
            views:
              v_ledger_health:
                purpose: health
                columns: [site_code, tree_size]
            """
        )
        loaded = parse_contract(document)
        assert loaded.names() == ("v_ledger_health",)

    def test_budget_key_synonyms_are_accepted(self):
        document = yaml.safe_load(
            """
            defaults: {max_rows: 10, budget_bytes: 4096}
            views:
              - view_name: v_ledger_health
                cols: [site_code]
                completeness_flag: ancestry_complete
            """
        )
        loaded = parse_contract(document)
        view = loaded.by_name("v_ledger_health")
        assert view.row_cap == 10
        assert view.byte_budget == 4096
        assert view.truncation_flag == "ancestry_complete"

    def test_a_null_truncation_flag_is_no_flag_not_the_string_none(self):
        document = yaml.safe_load("views:\n  - name: v_ledger_health\n    truncation_flag: null\n")
        assert parse_contract(document).by_name("v_ledger_health").truncation_flag is None


class TestStrictness:
    def test_a_missing_views_section_is_refused(self):
        with pytest.raises(ContractError, match="views"):
            parse_contract({"version": 1})

    def test_an_empty_views_section_is_refused(self):
        with pytest.raises(ContractError):
            parse_contract({"views": []})

    def test_a_view_without_a_name_is_refused_by_index(self):
        with pytest.raises(ContractError, match=r"views\[0\]"):
            parse_contract({"views": [{"columns": ["a"]}]})

    def test_a_duplicate_view_is_refused(self):
        document = {"views": [{"name": "v_x"}, {"name": "v_x"}]}
        with pytest.raises(ContractError, match="twice"):
            parse_contract(document)

    def test_a_view_outside_mainline_audit_is_refused(self):
        # mainline_qa in the audit contract would be the single worst mistake this
        # loader could accept, so it is the one it refuses by name.
        document = {"views": [{"name": "v_disposition_profile", "schema": "mainline_qa"}]}
        with pytest.raises(ContractError, match="mainline_audit"):
            parse_contract(document)

    def test_a_non_integer_budget_is_refused_naming_the_view(self):
        document = {"views": [{"name": "v_x", "byte_budget": "lots"}]}
        with pytest.raises(ContractError, match=r"v_x\.byte_budget"):
            parse_contract(document)

    def test_a_zero_budget_is_refused(self):
        with pytest.raises(ContractError):
            parse_contract({"views": [{"name": "v_x", "row_cap": 0}]})

    def test_columns_must_be_a_list(self):
        with pytest.raises(ContractError, match="columns"):
            parse_contract({"views": [{"name": "v_x", "columns": "site_id"}]})

    def test_a_missing_contract_file_says_who_owns_it(self, tmp_path):
        with pytest.raises(ContractError, match="fleet-contracts worker"):
            load_contract(tmp_path / "nope.yaml")

    def test_malformed_yaml_is_refused_as_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("views: [\n", encoding="utf-8")
        with pytest.raises(ContractError, match="not valid YAML"):
            load_contract(bad)


class TestPaths:
    def test_contract_path_is_the_spec_location(self, tmp_path):
        assert contract_path(tmp_path).as_posix().endswith("spec/mcp/audit-surface.contract.yaml")

    def test_negative_assertions_path_is_the_spec_location(self, tmp_path):
        assert (
            negative_assertions_path(tmp_path)
            .as_posix()
            .endswith("spec/mcp/negative-assertions.yaml")
        )


class TestDivergence:
    def test_a_dropped_view_is_reported_as_missing(self):
        document = {"views": [{"name": name} for name in ARCHITECTURE_VIEWS[:-1]]}
        missing, extra = parse_contract(document).divergence_from_architecture()
        assert missing == (ARCHITECTURE_VIEWS[-1],)
        assert extra == ()

    def test_an_added_view_is_reported_as_extra(self):
        document = {"views": [{"name": name} for name in (*ARCHITECTURE_VIEWS, "v_new")]}
        missing, extra = parse_contract(document).divergence_from_architecture()
        assert missing == ()
        assert extra == ("v_new",)
