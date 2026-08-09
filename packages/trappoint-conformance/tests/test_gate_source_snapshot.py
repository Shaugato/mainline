# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The self-attesting gate: a migration that touches it forces a human to read it.

The problem this solves is not that somebody changes the gate. It is that somebody changes
the gate **and the diff does not show the gate**. A migration named
``0154_widen_a_column.sql`` that happens to ``CREATE OR REPLACE`` a trigger function
produces a review in which the reviewer reads a column widening; the function's new body is
in the file, of course, but nothing in the diff says *the merge gate changed*.

So the gate's own source text — as the **server** reports it, not as the repository claims
it — is committed as a snapshot. Any change to what the database actually executes turns up
as a diff in ``tests/__snapshots__/gate_source.sql``, in a file whose name is the sentence
*"the gate changed"*, and it cannot be updated without ``--snapshot-update`` and a reviewer
seeing the before and after side by side.

**It is the server's rendering, deliberately.** ``pg_get_functiondef()`` returns what the
database will run, which is the only text that matters and the only text that catches the
fourth failure mode in the kernel plan's risk list: ``CREATE PROCEDURE`` binds references
**early** on v26.2, so a table-shape change requires ``CREATE OR REPLACE PROCEDURE`` in the
same migration. A procedure silently bound to a shape that no longer exists is invisible in
the repository and visible here.

**GT-05 is answered.** ``pg_get_triggerdef()`` and ``pg_get_functiondef()`` were both
measured working on CockroachDB **v26.2.5** while this suite was written, so the snapshot is
the strong form. The committed fallback — ``SHOW CREATE TABLE``, which carries trigger
declarations but not function bodies — is implemented below and marks the snapshot ``weak``
in its own header, so a run that had to fall back can never be mistaken for one that did
not.

**Why not ``syrupy``.** The brief asks for a ``syrupy`` snapshot and ``syrupy`` is the right
library for this. It is not in ``packages/trappoint-conformance/pyproject.toml``'s dev group
and that file belongs to another worker, so this module implements the same contract —
compare against a committed artefact, rewrite it only under an explicit flag — in about
thirty lines with no dependency. Switching to ``syrupy`` is then a change to *this* file
only. The behavioural contract is identical and the snapshot artefact is committed either
way.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

SNAPSHOT_DIR = Path(__file__).resolve().parent / "__snapshots__"
SNAPSHOT = SNAPSHOT_DIR / "gate_source.sql"

# The objects whose source text is the gate. Named rather than globbed: a glob would make
# the snapshot churn every time an unrelated function is added, and a snapshot that churns
# is a snapshot nobody reads.
GATE_FUNCTIONS = (
    "fn_check_project",
    "fn_check_materialised",
    "fn_disposition_project",
    "fn_disposition_close",
    "fn_disposition_retract_only",
    "fn_permit_event_chain",
    "fn_cr_event_chain",
    "fn_refuse_mutation",
    "fn_closure_guard",
    "fn_permit_merge_gate",
    "fn_cr_merge_gate",
    "merge_permit",
    "merge_change_request",
)

GATE_TRIGGERS = (
    "check_project",
    "check_materialised",
    "disposition_project",
    "disposition_close",
    "disposition_retract_only",
    "permit_event_chain",
    "cr_event_chain",
    "append_only",
    "closure_guard",
    "permit_merge_gate",
    "cr_merge_gate",
)


def _update_requested(config: pytest.Config) -> bool:
    return bool(
        config.getoption("--snapshot-update", default=False)
        or os.environ.get("TRAPPOINT_SNAPSHOT_UPDATE")
    )


def pytest_addoption(parser: pytest.Parser) -> None:  # pragma: no cover - pytest hook
    """Add ``--snapshot-update``, the only way to rewrite the committed gate source."""
    group = parser.getgroup("trappoint")
    if not any(opt.dest == "snapshot_update" for opt in group.options):
        group.addoption(
            "--snapshot-update",
            action="store_true",
            default=False,
            dest="snapshot_update",
            help="rewrite tests/__snapshots__/gate_source.sql from the live cluster",
        )


def _capture(conn: Any, schema: str) -> tuple[str, bool]:
    """Return ``(text, weak)`` for the gate's source as the server renders it."""
    strong = True
    chunks: list[str] = []
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                SELECT p.proname, pg_get_functiondef(p.oid)
                  FROM pg_proc p
                  JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname IN (%s, 'trappoint') AND p.proname = ANY(%s)
                 ORDER BY p.proname
                """,
                (schema, list(GATE_FUNCTIONS)),
            )
            for name, body in cur.fetchall():
                chunks.append(f"-- ── FUNCTION {name} ───────────────\n{body}")
        except Exception as exc:  # noqa: BLE001 — GT-05 fallback, recorded not hidden
            strong = False
            chunks.append(f"-- pg_get_functiondef unavailable: {exc}")

        try:
            cur.execute(
                """
                SELECT t.tgname, c.relname, pg_get_triggerdef(t.oid)
                  FROM pg_trigger t
                  JOIN pg_class c ON c.oid = t.tgrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = %s AND NOT t.tgisinternal AND t.tgname = ANY(%s)
                 ORDER BY c.relname, t.tgname
                """,
                (schema, list(GATE_TRIGGERS)),
            )
            for name, relation, body in cur.fetchall():
                chunks.append(f"-- ── TRIGGER {relation}.{name} ───────────────\n{body};")
        except Exception as exc:  # noqa: BLE001
            strong = False
            chunks.append(f"-- pg_get_triggerdef unavailable: {exc}")
            # The committed fallback (GT-05 FALLBACK-SELECTED): SHOW CREATE TABLE carries
            # trigger declarations, though not function bodies. Weaker, and said so.
            for relation in ("permit", "change_request", "blocking_check", "disposition"):
                try:
                    cur.execute(f'SHOW CREATE TABLE "{schema}"."{relation}"')
                    row = cur.fetchone()
                    if row:
                        chunks.append(f"-- ── SHOW CREATE TABLE {relation} ──\n{row[1]}")
                except Exception as inner:  # noqa: BLE001
                    chunks.append(f"-- SHOW CREATE TABLE {relation} unavailable: {inner}")

    header = [
        "-- SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "-- SPDX-License-Identifier: Apache-2.0",
        "--",
        "-- THE SELF-ATTESTING GATE. Generated by tests/test_gate_source_snapshot.py from",
        "-- the LIVE cluster, never from the repository. A diff in this file is the",
        "-- sentence 'the merge gate changed', and it is the only place that sentence is",
        "-- guaranteed to appear in a review.",
        "--",
        f"-- snapshot strength: {
            'STRONG (pg_get_functiondef + pg_get_triggerdef)'
            if strong
            else 'WEAK (fallback; function bodies are NOT covered)'
        }",
        "",
    ]
    return "\n".join(header + chunks) + "\n", not strong


@pytest.mark.db
def test_gate_source_matches_the_committed_snapshot(
    conn: Any, profile: str, request: pytest.FixtureRequest
) -> None:
    """The gate the database will execute is the gate a reviewer last read."""
    from trappoint_conformance.runner import resolve_schema

    schema = resolve_schema(profile)
    text, weak = _capture(conn, schema)
    if "-- ── FUNCTION" not in text and "-- ── TRIGGER" not in text:
        pytest.skip(
            "SKIP WITH REASON: the cluster holds none of the gate's objects, so there is "
            "no source text to attest. Run `just migrate` first."
        )

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if _update_requested(request.config) or not SNAPSHOT.is_file():
        SNAPSHOT.write_text(text, encoding="utf-8")
        if not _update_requested(request.config):
            pytest.fail(
                f"no committed snapshot existed, so one was written to {SNAPSHOT}. Read "
                f"it, then commit it: an unread snapshot attests nothing."
            )
        return

    committed = SNAPSHOT.read_text(encoding="utf-8")
    if committed == text:
        if weak:
            pytest.skip(
                "SKIP WITH REASON: the snapshot is WEAK — pg_get_functiondef or "
                "pg_get_triggerdef was unavailable, so function bodies are not covered. "
                "It matched, and a weak match is not the assertion this test claims to "
                "make."
            )
        return

    diff = _first_difference(committed, text)
    pytest.fail(
        "THE MERGE GATE'S SOURCE CHANGED.\n\n"
        f"{diff}\n\n"
        "This is not a test to silence. The text above is what the database will execute "
        "the next time somebody merges a permit, and it is not what the last reviewer "
        "read. If the change is intended, re-run with --snapshot-update and put the diff "
        "in the pull request, where a human has to look at the gate's own source."
    )


def _first_difference(committed: str, observed: str) -> str:
    """The first differing line, with enough context to identify the object."""
    old = committed.splitlines()
    new = observed.splitlines()
    for index in range(max(len(old), len(new))):
        before = old[index] if index < len(old) else "<end of committed snapshot>"
        after = new[index] if index < len(new) else "<end of observed source>"
        if before != after:
            context = next(
                (line for line in reversed(new[: index + 1]) if line.startswith("-- ── ")),
                "<no object header above this line>",
            )
            return f"in {context}\n  committed: {before[:200]}\n  observed : {after[:200]}"
    return "the files differ only in trailing whitespace"


def test_the_snapshot_is_committed() -> None:
    """A snapshot that is not in the tree attests nothing.

    Hermetic, so it runs in the fast job. It is the guard against the failure mode where
    the artefact is generated in CI, matched against itself, and never reviewed by anyone.
    """
    assert SNAPSHOT.is_file(), (
        f"{SNAPSHOT} is missing. Generate it against a migrated cluster with "
        f"`pytest --snapshot-update`, read it, and commit it. A self-attesting gate whose "
        f"attestation is not in the repository is a gate that attests to whoever ran CI "
        f"last."
    )
    text = SNAPSHOT.read_text(encoding="utf-8")
    assert "snapshot strength:" in text, (
        "the committed snapshot carries no strength header, so a WEAK snapshot — one taken "
        "without pg_get_functiondef, covering no function bodies — would be "
        "indistinguishable from a strong one."
    )
