# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The ccloud leg: a missing field is fatal, a cursor is never guessed, bytes reproduce.

Three properties are asserted here and each one is a claim made elsewhere in the
repository that would otherwise be prose:

1. **A missing field is a hard failure, never a default** (``ARCHITECTURE.md`` §9.3).
   The failing case is committed as a fixture — ``renamed-field/audit-list.json`` — so
   the assertion is against a recorded shape rather than against a mock we wrote to
   pass.
2. **Pagination is refused rather than guessed** (GT-21). A response with a non-null
   cursor and no ``PageCursor`` refuses; with one, every page is folded and the row
   count is the sum.
3. **The digest is over RFC 8785 bytes**, so two responses that differ only in key order
   or whitespace produce the same attestation — otherwise the patrol reports drift on
   every CLI upgrade and a reader learns to ignore it.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
REPO_ROOT = HERE.parents[4]

for _source_root in (
    HERE.parent / "src",
    REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    REPO_ROOT / "packages" / "trappoint-migrate" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from mainline_custody_patrol.ccloud import (  # noqa: E402
    CcloudFieldMissing,
    CcloudPaginationUnresolved,
    CcloudUnavailable,
    FixtureCcloud,
    PageCursor,
    audit_list,
    backup_list,
    require_field,
    resolve_shim,
    rfc3339,
)

WINDOW_FROM = datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC)
WINDOW_TO = datetime(2026, 8, 9, 13, 15, 0, tzinfo=UTC)


class RecordingShim:
    """A shim that answers from a scripted list of documents and records every argv."""

    def __init__(self, documents: Sequence[Any]) -> None:
        self.documents = list(documents)
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> Any:
        self.calls.append(list(argv))
        if not self.documents:
            raise AssertionError("the fold asked for more pages than were scripted")
        return self.documents.pop(0)


def _page(entries: list[dict[str, Any]], next_page: str | None) -> dict[str, Any]:
    return {"entries": entries, "pagination": {"next_page": next_page, "page_size": 100}}


# ---------------------------------------------------------------- the happy path


def test_the_fixture_audit_stream_folds_with_its_row_count():
    shim = FixtureCcloud(FIXTURES)
    fold = audit_list(shim, starting_from=WINDOW_FROM, window_to=WINDOW_TO, source="fixtures")

    assert fold.kind == "ccloud_audit"
    assert fold.row_count == 3
    assert len(fold.pages) == 1
    assert fold.document["window_from"] == "2026-08-09T13:00:00Z"
    assert fold.document["window_to"] == "2026-08-09T13:15:00Z"
    assert fold.document["shim_source"] == "fixtures"
    # The fixture carries a DISABLE TRIGGER in the audit stream on purpose: that is the
    # tier-T1 act the whole attestation exists to make visible to somebody other than
    # the person who did it (attack A13).
    actions = [entry["action"] for entry in fold.pages[0].document["entries"]]
    assert "CLUSTER_SQL_STATEMENT_EXECUTED" in actions


def test_the_backup_window_is_a_point_not_an_invented_interval():
    shim = FixtureCcloud(FIXTURES)
    fold = backup_list(shim, cluster_id="cl-custody-fixture", at=WINDOW_TO)

    assert fold.kind == "ccloud_backup"
    assert fold.row_count == 2
    assert fold.window_from == fold.window_to == WINDOW_TO


def test_the_digest_is_over_canonical_bytes_so_key_order_is_irrelevant():
    ordered = _page([{"id": "au-1", "action": "X"}], None)
    reordered = {
        "pagination": {"page_size": 100, "next_page": None},
        "entries": [{"action": "X", "id": "au-1"}],
    }

    first = audit_list(RecordingShim([ordered]), starting_from=WINDOW_FROM, window_to=WINDOW_TO)
    second = audit_list(RecordingShim([reordered]), starting_from=WINDOW_FROM, window_to=WINDOW_TO)

    assert first.sha256 == second.sha256
    assert first.canon_bytes == second.canon_bytes


def test_two_folds_of_the_same_response_hash_identically():
    shim_a, shim_b = FixtureCcloud(FIXTURES), FixtureCcloud(FIXTURES)
    a = audit_list(shim_a, starting_from=WINDOW_FROM, window_to=WINDOW_TO, source="fixtures")
    b = audit_list(shim_b, starting_from=WINDOW_FROM, window_to=WINDOW_TO, source="fixtures")
    assert a.sha256_hex == b.sha256_hex


# ------------------------------------------------------ a missing field is fatal


def test_a_renamed_field_is_a_hard_failure_naming_what_was_present():
    shim = FixtureCcloud(FIXTURES / "renamed-field")

    with pytest.raises(CcloudFieldMissing) as caught:
        audit_list(shim, starting_from=WINDOW_FROM, window_to=WINDOW_TO)

    message = str(caught.value)
    assert "entries" in message
    # The realistic cause is a renamed field, so the NEW name is the one piece of
    # information the operator needs and it must be in the message.
    assert "items" in message
    assert caught.value.field.startswith("entries")


def test_a_scalar_where_an_array_was_expected_is_the_same_failure():
    document = {"entries": 3, "pagination": {"next_page": None}}
    with pytest.raises(CcloudFieldMissing):
        audit_list(RecordingShim([document]), starting_from=WINDOW_FROM, window_to=WINDOW_TO)


def test_an_absent_pagination_member_is_a_hard_failure_not_an_assumed_single_page():
    # Assuming "no pagination object means one page" is assuming non-omission, which is
    # exactly the proposition this ledger exists to defend.
    document = {"entries": []}
    with pytest.raises(CcloudFieldMissing) as caught:
        audit_list(RecordingShim([document]), starting_from=WINDOW_FROM, window_to=WINDOW_TO)
    assert "pagination" in str(caught.value)


def test_require_field_refuses_a_non_mapping_document():
    with pytest.raises(CcloudFieldMissing):
        require_field(["not", "a", "mapping"], "entries", command="ccloud audit list")


# ----------------------------------------------------- pagination is never guessed


def test_a_cursor_without_a_page_cursor_refuses_rather_than_truncating():
    document = _page([{"id": "au-1"}], "cursor-page-2")

    with pytest.raises(CcloudPaginationUnresolved) as caught:
        audit_list(RecordingShim([document]), starting_from=WINDOW_FROM, window_to=WINDOW_TO)

    message = str(caught.value)
    assert "cursor-page-2" in message
    assert "GT-21" in message


def test_a_supplied_page_cursor_follows_every_page_and_sums_the_rows():
    pages = [
        _page([{"id": "au-1"}, {"id": "au-2"}], "cursor-2"),
        _page([{"id": "au-3"}], None),
    ]
    shim = RecordingShim(pages)
    cursor = PageCursor(argv_for=lambda token: ("--page-token", token), limit=8)

    fold = audit_list(
        shim, starting_from=WINDOW_FROM, window_to=WINDOW_TO, cursor=cursor, source="scripted"
    )

    assert fold.row_count == 3
    assert len(fold.pages) == 2
    assert shim.calls[1][-2:] == ["--page-token", "cursor-2"]
    assert fold.document["page_count"] == 2
    # Each page keeps its own digest, so a bundle reader can point at the page that
    # carried a given record rather than at the fold as an undifferentiated blob.
    assert len({page["page_sha256"] for page in fold.document["pages"]}) == 2


def test_an_endless_cursor_stops_at_the_limit_rather_than_paging_forever():
    endless = [_page([{"id": f"au-{n}"}], f"cursor-{n + 1}") for n in range(6)]
    cursor = PageCursor(argv_for=lambda token: ("--page-token", token), limit=3)

    with pytest.raises(CcloudPaginationUnresolved) as caught:
        audit_list(
            RecordingShim(endless), starting_from=WINDOW_FROM, window_to=WINDOW_TO, cursor=cursor
        )
    assert "3 pages" in str(caught.value)


# ----------------------------------------------------------------- shim resolution


def test_resolve_shim_refuses_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("MAINLINE_CUSTODY_CCLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("MAINLINE_CUSTODY_CCLOUD_FIXTURES", raising=False)
    monkeypatch.setitem(sys.modules, "mainline_provision", None)

    with pytest.raises(CcloudUnavailable) as caught:
        resolve_shim()

    # The refusal must name the alternatives, because the operator's next action is to
    # pick one of them.
    assert "MAINLINE_CUSTODY_CCLOUD_PROVIDER" in str(caught.value)
    assert "no silent default" in str(caught.value)


def test_resolve_shim_names_where_the_answer_came_from(monkeypatch):
    monkeypatch.delenv("MAINLINE_CUSTODY_CCLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("MAINLINE_CUSTODY_CCLOUD_FIXTURES", str(FIXTURES))
    monkeypatch.setitem(sys.modules, "mainline_provision", None)

    shim, source = resolve_shim()

    assert isinstance(shim, FixtureCcloud)
    # A reader must be able to tell a live patrol from a fixture one without reading our
    # code — that is the difference between evidence and a screenshot.
    assert source.startswith("fixtures:")


def test_a_missing_fixture_directory_refuses_immediately():
    with pytest.raises(CcloudUnavailable):
        FixtureCcloud(FIXTURES / "does-not-exist")


def test_an_unmapped_command_refuses_rather_than_guessing_a_file():
    shim = FixtureCcloud(FIXTURES)
    with pytest.raises(CcloudUnavailable) as caught:
        shim(["cluster", "delete", "cl-1"])
    assert "no fixture is mapped" in str(caught.value)


# -------------------------------------------------------------------- time hygiene


def test_a_naive_datetime_cannot_enter_an_attestation_window():
    with pytest.raises(ValueError, match="naive datetime"):
        rfc3339(datetime(2026, 8, 9, 13, 0, 0))  # noqa: DTZ001 - the point of the test


def test_a_reversed_window_is_refused_before_the_database_would_refuse_it():
    with pytest.raises(ValueError, match="ends before it starts"):
        audit_list(
            RecordingShim([_page([], None)]),
            starting_from=WINDOW_TO,
            window_to=WINDOW_FROM,
        )


def test_rfc3339_is_second_grained_so_two_collections_of_one_window_agree():
    moment = datetime(2026, 8, 9, 13, 15, 0, 123456, tzinfo=UTC)
    assert rfc3339(moment) == "2026-08-09T13:15:00Z"
    assert rfc3339(moment + timedelta(microseconds=1)) == rfc3339(moment)
