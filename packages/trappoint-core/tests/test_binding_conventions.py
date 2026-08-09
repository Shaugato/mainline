# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The conventions the merge-gate templates derive names from, checked against reality.

Migrations ``0115``-``0119`` and ``0130``-``0131`` are rendered from one template pair
per subject, and every name in them is derived from the binding's ``id_column``::

    permit_id → permit → permit_event, permit_clause, fn_permit_merge_gate, merge_permit
    cr_id     → cr     → cr_event,     cr_clause,     fn_cr_merge_gate,     merge_change_request

The bindings ALSO declare ``event_table``, ``completion_table``,
``epoch_pin_constraint`` and ``[[obligation_source]]`` explicitly — and
``trappoint_sql.render._context()`` does not pass any of them to a template. So the
templates derive what the bindings declare, and the two could silently disagree.

These tests are that disagreement made loud. They read both committed ``vertical.toml``
files with ``tomllib`` and nothing else — no import of the renderer, so a change to the
renderer cannot make them pass by accident.

**They are a stopgap and they say so.** The fix is to expose those four fields in the
render context, which is ``kernel/render-and-foundation``'s file; a cross-domain note is
filed. Until then, a binding that names its event table something else is caught here
rather than by a migration that will not apply.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BINDINGS = (
    REPO_ROOT / "verticals" / "mainline" / "vertical.toml",
    REPO_ROOT / "packages" / "trappoint-sql" / "refvertical" / "vertical.toml",
)


def load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def bindings() -> list[tuple[str, dict[str, Any]]]:
    return [(path.name, load(path)) for path in BINDINGS if path.is_file()]


@pytest.fixture(params=[str(path) for path in BINDINGS], ids=lambda p: Path(p).parent.name)
def binding(request) -> dict[str, Any]:
    path = Path(request.param)
    if not path.is_file():
        pytest.skip(f"{path} is not committed yet")
    return load(path)


def stem_of(subject: dict[str, Any]) -> str:
    """``permit_id`` -> ``permit``; ``cr_id`` -> ``cr``. The derivation, in one place."""
    identifier = subject["id_column"]
    assert identifier.endswith("_id"), f"{identifier!r} must end in `_id` for the derivation"
    return str(identifier[: -len("_id")])


def test_the_event_table_is_what_the_templates_derive(binding):
    for subject in binding["subject"]:
        assert subject["event_table"] == f"{stem_of(subject)}_event", (
            "migrations 0117/0118 insert into `<stem>_event`; this binding declares "
            f"{subject['event_table']!r}, so the rendered procedure would name a table "
            "that does not exist and CREATE PROCEDURE would refuse it at 42P01"
        )


def test_the_completion_table_is_the_substrate_one(binding):
    for subject in binding["subject"]:
        assert subject["completion_table"] == "merge_record"


def test_the_epoch_pin_constraint_is_what_the_templates_document(binding):
    for subject in binding["subject"]:
        assert subject["epoch_pin_constraint"] == f"epoch_pin_{stem_of(subject)}"


def test_every_gated_subject_carries_the_obligation_counter_the_gate_re_derives(binding):
    for subject in binding["subject"]:
        columns = {counter["column"] for counter in subject["counters"]}
        assert "open_blocking" in columns, (
            "fn_<subject>_merge_gate compares its anti-join re-derivation against "
            "`open_blocking`; a subject without that counter has no projection to "
            "disagree with and the drift arm would be unreachable"
        )


def test_blocking_check_is_the_relation_that_feeds_that_counter(binding):
    sources = binding["obligation_source"]
    feeding = [s for s in sources if s["counter"] == "open_blocking"]
    assert len(feeding) == 1
    assert feeding[0]["relation"].endswith(".blocking_check"), (
        "the gate's anti-join is written against `<schema>.blocking_check` and "
        "`<schema>.disposition`, which MR-2 lists as substrate objects"
    )
    assert feeding[0]["bumps_epoch"] is True


def test_the_boundary_certificate_arm_matches_its_declared_relation(binding):
    sources = binding["obligation_source"]
    certifying = [s for s in sources if s["counter"] == "unmodelled_asset_count"]
    assert len(certifying) == 1
    assert certifying[0]["relation"].endswith(".boundary_certificate"), (
        "the certified-null arm of fn_permit_merge_gate reads "
        "`<schema>.boundary_certificate` by leaf name; a binding that called it "
        "something else would render a gate naming a relation it does not own"
    )


def test_the_authority_source_for_the_check_projection_is_declared(binding):
    # The gate's fail-closed arm is rendered FROM this entry, so a binding without it
    # cannot render a gate at all — `trappoint render` refuses with an undefined name
    # rather than emitting a gate whose authority nobody declared (rule P-2).
    entries = [
        entry
        for entry in binding["authority_source"]
        if "blocking_check.severity" in entry["projects"]
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["on_missing"] == "raise"
    assert len(entry["key"]) == len(entry.get("key_columns", entry["key"]))


def test_both_bindings_are_present_so_the_substrate_claim_is_exercised():
    # One binding is a template engine with an audience of one. If this ever fails, the
    # merge-gate templates have stopped being proved against a second vertical.
    assert len(bindings()) == 2
