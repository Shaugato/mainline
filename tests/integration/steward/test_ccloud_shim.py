# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The ``ccloud`` leg: parsed, never screen-scraped, and a missing field is fatal.

``ARCHITECTURE.md`` §9.3 states the rule and gives the reason in the same sentence:
*parse the JSON — never screen-scrape — and treat a missing field as a hard failure,
because a silently renamed field is how a provisioning agent lies.*

The whole suite runs against committed fixtures in ``fixtures/ccloud/``, because unattended
``ccloud`` authentication is undocumented and this build has no CockroachDB Cloud
organisation. The live lane exists, is opt-in, and skips with a reason.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from mainline_steward import CustodianPatrol, FixtureCcloud
from mainline_steward.ccloud import require_field, resolve_shim
from mainline_steward.errors import CcloudFieldMissing, CcloudUnavailable, ConfigurationRefused

from trappoint_jcs import canonicalise


@pytest.fixture
def fixtures(paths) -> Path:
    return paths["ccloud_fixtures"]


@pytest.fixture
def patrol(fixtures) -> CustodianPatrol:
    return CustodianPatrol(FixtureCcloud(fixtures), cluster_id="cl-steward-fixture")


class TestTheThreeI4Reads:
    def test_cluster_info_requires_the_fields_it_names(self, patrol):
        page = patrol.cluster_info()
        assert page.source == "cluster_info"
        assert page.document["state"] == "CREATED"
        assert page.command.startswith("ccloud cluster info ")

    def test_backup_list_requires_backups(self, patrol):
        page = patrol.backup_list()
        assert len(page.document["backups"]) == 2

    def test_audit_list_requires_an_explicit_window(self, patrol):
        with pytest.raises(ConfigurationRefused):
            patrol.audit_list("")

    def test_audit_list_reads_the_window_it_was_given(self, patrol):
        page = patrol.audit_list("2026-08-04T14:40:00Z")
        assert "--starting-from 2026-08-04T14:40:00Z" in page.command
        assert len(page.document["entries"]) == 2

    def test_all_three_run_in_i4_order(self, patrol):
        pages = patrol.run(starting_from="2026-08-04T14:40:00Z")
        assert [page.source for page in pages] == ["cluster_info", "backup_list", "audit_list"]


class TestPagesAreCanonicalisedAndHashed:
    def test_the_digest_is_over_the_canonical_bytes_of_the_decoded_document(self, patrol):
        page = patrol.cluster_info()
        assert page.canon_bytes == canonicalise(page.document)
        assert len(page.page_sha256) == 64

    def test_two_spellings_of_one_response_hash_the_same(self, tmp_path, fixtures):
        # A `ccloud` upgrade that reorders keys or reflows whitespace must not read as
        # custody drift, or an operator learns to ignore the one signal this patrol emits.
        reordered = tmp_path / "reordered"
        reordered.mkdir()
        document = json.loads((fixtures / "cluster-info.json").read_text(encoding="utf-8"))
        (reordered / "cluster-info.json").write_text(
            json.dumps(dict(reversed(list(document.items()))), indent=8), encoding="utf-8"
        )
        a = CustodianPatrol(FixtureCcloud(fixtures), cluster_id="c").cluster_info()
        b = CustodianPatrol(FixtureCcloud(reordered), cluster_id="c").cluster_info()
        assert a.page_sha256 == b.page_sha256


class TestAMissingFieldIsAHardFailure:
    def test_a_renamed_top_level_field_refuses_and_says_what_was_there(self, fixtures):
        patrol = CustodianPatrol(
            FixtureCcloud(fixtures / "renamed-field"), cluster_id="cl-steward-fixture"
        )
        with pytest.raises(CcloudFieldMissing) as caught:
            patrol.audit_list("2026-08-04T14:40:00Z")
        assert caught.value.field == "entries"
        assert "auditEntries" in caught.value.present
        assert "a silently renamed field is how a provisioning agent lies" in str(caught.value)

    def test_require_field_refuses_a_non_mapping_response(self):
        with pytest.raises(CcloudFieldMissing):
            require_field([1, 2, 3], "entries", command="ccloud audit list")

    def test_a_present_but_null_field_is_accepted_and_a_missing_one_is_not(self):
        assert require_field({"entries": None}, "entries", command="c") is None
        with pytest.raises(CcloudFieldMissing):
            require_field({}, "entries", command="c")


class TestResolution:
    def test_an_explicit_shim_wins_and_is_recorded_as_explicit(self, fixtures):
        shim = FixtureCcloud(fixtures)
        resolved, source = resolve_shim(explicit=shim)
        assert resolved is shim
        assert source == "explicit"

    def test_a_fixture_directory_is_recorded_in_the_source_string(self, fixtures):
        _, source = resolve_shim(fixtures=fixtures)
        assert source.startswith("fixtures:")

    def test_nothing_resolvable_refuses_rather_than_reporting_an_empty_patrol(self, monkeypatch):
        for name in (
            "MAINLINE_STEWARD_CCLOUD_PROVIDER",
            "MAINLINE_STEWARD_CCLOUD_LIVE",
            "MAINLINE_STEWARD_CCLOUD_FIXTURES",
        ):
            monkeypatch.delenv(name, raising=False)
        with pytest.raises(CcloudUnavailable) as caught:
            resolve_shim()
        assert "must not be reportable as a clean one" in str(caught.value)

    def test_an_absent_fixture_directory_refuses_at_construction(self, tmp_path):
        with pytest.raises(CcloudUnavailable):
            FixtureCcloud(tmp_path / "not-here")

    def test_an_unmapped_command_refuses_rather_than_guessing_a_file(self, fixtures):
        shim = FixtureCcloud(fixtures)
        with pytest.raises(CcloudUnavailable) as caught:
            shim(["cluster", "delete", "cl-steward-fixture"])
        assert "no fixture is mapped" in str(caught.value)

    def test_a_bad_provider_specification_refuses_instead_of_falling_back(self, monkeypatch):
        monkeypatch.setenv("MAINLINE_STEWARD_CCLOUD_PROVIDER", "not-a-module-spec")
        with pytest.raises(ConfigurationRefused):
            resolve_shim()

    def test_the_protocol_accepts_a_plain_callable(self):
        # The cloud lead's `cc()` is a function, not a class. The Protocol has to admit one.
        calls: list[list[str]] = []

        def cc(argv):
            calls.append(list(argv))
            return {"id": "c", "name": "n", "state": "CREATED"}

        page = CustodianPatrol(cc, cluster_id="c").cluster_info()
        assert calls == [["cluster", "info", "c"]]
        assert page.document["state"] == "CREATED"


class TestTheLiveLaneSkipsCleanly:
    @pytest.mark.requires_cluster
    @pytest.mark.skipif(
        os.environ.get("MAINLINE_STEWARD_CCLOUD_LIVE") != "1",
        reason=(
            "unattended `ccloud` auth is undocumented (§9.3: --no-redirect exists for "
            "headless login; no API-key flag or environment variable is published), and "
            "this build has no CockroachDB Cloud organisation. Set "
            "MAINLINE_STEWARD_CCLOUD_LIVE=1 with a logged-in ccloud to exercise it. This "
            "SKIPS rather than passing, because a green live lane with nothing to talk to "
            "would assert nothing."
        ),
    )
    def test_the_live_binary_answers(self):  # pragma: no cover - never runs in CI
        from mainline_steward import SubprocessCcloud

        shim = SubprocessCcloud()
        assert Path(shim.binary).is_absolute()
