# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``mainline_audit.v_cbm_ledger`` fits the managed MCP surface, and says when it does not.

The managed MCP connection caps a ``SELECT`` at 25 rows and a response at
10 KiB (``ARCHITECTURE.md`` section 17).  A view that silently returned the first
25 of 4,000 would be a view that lies by omission, and I13 — silence is logged —
does not exempt a rendering.  ``ledger_truncated`` is the honest half.

The size assertion below measures a real encoding of the real rows rather than
trusting the header's arithmetic.  The encoding used is JSON with ``str``
fallback, which is what an MCP response body looks like and is comfortably
larger than the wire format the driver actually uses — so passing here is a
conservative pass.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from _cbm_sql_support import build_scene, insert_residue, rows
from mainline_domain.cbm import LEDGER_ROW_CAP, insert_account, project_commit

psycopg = pytest.importorskip("psycopg")

pytestmark = [pytest.mark.schema, pytest.mark.slow]

RESPONSE_CAP_BYTES = 10 * 1024

_COLUMNS = (
    "site_id",
    "commit_hex",
    "account_gen",
    "inherited",
    "carried",
    "split_carried",
    "merge_carried",
    "residue_open",
    "residue_disposed",
    "balanced",
    "live_residue_open",
    "accounting_stale",
    "wrote_as",
    "projector_ver",
    "computed_at",
    "n_accounted_commits",
    "n_obligations_inherited",
    "n_obligations_open",
    "ledger_truncated",
)


def _ledger(conn: Any) -> list[dict[str, Any]]:
    result = conn.execute("SELECT * FROM mainline_audit.v_cbm_ledger").fetchall()
    return [dict(zip(_COLUMNS, row, strict=True)) for row in result]


@pytest.mark.timeout(300)
def test_the_ledger_is_capped_at_25_rows_and_says_it_was_truncated(
    isolated_conn: Any, site_id: uuid.UUID
) -> None:
    conn = isolated_conn
    for index in range(30):
        scene = build_scene(
            conn,
            site_id=site_id,
            seed=70_000 + index,
            n_ancestors=2,
            severities=[5, 4],
            dispositions=["matched", "residue_open"],
        )
        insert_account(
            conn, project_commit(conn, scene.child.commit_id), computed_by="agent_cartographer"
        )

    ledger = _ledger(conn)

    assert len(ledger) == LEDGER_ROW_CAP == 25
    assert all(row["n_accounted_commits"] == 30 for row in ledger)
    assert all(row["ledger_truncated"] is True for row in ledger), (
        "a reader who sees 25 rows must be told whether 25 was all of them"
    )
    assert all(row["balanced"] is True for row in ledger), (
        "cbm_balances makes this a tautology, and the tautology IS the claim"
    )
    assert all(row["inherited"] == 2 for row in ledger)
    assert all(row["residue_open"] == 1 for row in ledger)

    # The totals are over every account, not over the 25 rows returned.
    assert ledger[0]["n_obligations_inherited"] == 60
    assert ledger[0]["n_obligations_open"] == 30


@pytest.mark.timeout(300)
def test_the_response_fits_the_10_kib_cap(isolated_conn: Any, site_id: uuid.UUID) -> None:
    """MEASURED, and it produced a finding worth writing down.

    A tabular result can be encoded two ways, and only one of them fits:

    * ``{"columns": [...], "rows": [[...], ...]}`` — column names once, values as
      arrays.  This is what a SQL tool over MCP returns, and 25 full rows of this
      view measure comfortably inside the cap.
    * ``[{"site_id": …, "commit_hex": …}, …]`` — one dict per row.  The nineteen
      column NAMES are then repeated 25 times, which is roughly 11 KiB of keys
      before a single value is written, and the response does not fit at any
      realistic column set.

    The finding is therefore about the RENDERER, not about the view: a console or
    MCP shim that serialises this view as per-row objects will breach the cap and
    be truncated, and truncation that the client performs is exactly the silent
    partial answer ``ledger_truncated`` exists to prevent.  Both numbers are
    asserted below so that neither can drift unnoticed.
    """
    conn = isolated_conn
    for index in range(26):
        scene = build_scene(
            conn,
            site_id=site_id,
            seed=71_000 + index,
            n_ancestors=3,
            severities=[5, 5, 4],
            dispositions=["matched", "split", "residue_disposed"],
        )
        insert_account(
            conn,
            project_commit(conn, scene.child.commit_id),
            computed_by="arn:aws:lambda:ap-southeast-2:000000000000:function:closure-projector",
        )

    ledger = _ledger(conn)
    assert len(ledger) == LEDGER_ROW_CAP

    compact = json.dumps(
        {"columns": list(_COLUMNS), "rows": [[row[c] for c in _COLUMNS] for row in ledger]},
        default=str,
    ).encode("utf-8")
    assert len(compact) <= RESPONSE_CAP_BYTES, (
        f"the ledger encoded to {len(compact)} bytes in the columns-plus-rows form, over the "
        f"{RESPONSE_CAP_BYTES}-byte MCP response cap; the two substring() clips in 0151 are "
        "what keep it under and one of them has been widened or removed"
    )

    per_row_dicts = json.dumps(ledger, default=str).encode("utf-8")
    assert len(per_row_dicts) > RESPONSE_CAP_BYTES, (
        "a per-row-dict rendering of this view used to be too large for the cap and now is "
        "not. That is good news, but the view header and novelty/cbm-ledger.yaml both record "
        "the constraint, so update them rather than deleting this assertion"
    )


@pytest.mark.timeout(300)
def test_a_stale_account_is_flagged_and_sorted_first(
    isolated_conn: Any, site_id: uuid.UUID
) -> None:
    """The column that actually moves, and the one an operator acts on.

    A merge citing this commit is refused right now by ``z_cbm_gate`` with
    "blame accounting is stale for a cited commit", and the remedy is one more
    account generation.
    """
    conn = isolated_conn
    fresh = build_scene(
        conn,
        site_id=site_id,
        seed=72_001,
        n_ancestors=1,
        severities=[5],
        dispositions=["matched"],
    )
    insert_account(
        conn, project_commit(conn, fresh.child.commit_id), computed_by="agent_cartographer"
    )

    stale = build_scene(
        conn,
        site_id=site_id,
        seed=72_002,
        n_ancestors=2,
        severities=[5, 5],
        dispositions=["matched", "matched"],
    )
    insert_account(
        conn, project_commit(conn, stale.child.commit_id), computed_by="agent_cartographer"
    )
    insert_residue(
        conn,
        site_id=site_id,
        commit=stale.child,
        ancestor=stale.ancestors[0],
        reason="anchor_drop",
    )

    ledger = _ledger(conn)
    assert len(ledger) == 2
    assert ledger[0]["commit_hex"] == stale.child.commit_id.hex()[:16]
    assert ledger[0]["accounting_stale"] is True
    assert (ledger[0]["residue_open"], ledger[0]["live_residue_open"]) == (0, 1)
    assert ledger[1]["accounting_stale"] is False
    assert all(row["ledger_truncated"] is False for row in ledger)


@pytest.mark.timeout(300)
def test_wrote_as_records_the_cluster_s_answer_and_not_the_projector_s_claim(
    conn: Any, site_id: uuid.UUID
) -> None:
    """``computed_by`` is what the projector says; ``wrote_as`` is what the cluster saw.

    The projector below claims to be a Lambda ARN and the connection is ``root``.
    Both are recorded, and a disagreement between them is a finding rather than a
    mystery.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=73_001,
        n_ancestors=1,
        severities=[5],
        dispositions=["matched"],
    )
    insert_account(
        conn,
        project_commit(conn, scene.child.commit_id),
        computed_by="arn:aws:lambda:ap-southeast-2:000000000000:function:cbm-projector",
    )

    stored = rows(
        conn,
        "SELECT computed_by, wrote_as FROM mainline.cbm_account WHERE commit_id = %s",
        (scene.child.commit_id,),
    )
    assert len(stored) == 1
    claimed, actual = stored[0]
    assert claimed.startswith("arn:aws:lambda:")
    assert actual != "-", "the placeholder must not survive — 0140a overwrites it"
    assert actual == rows(conn, "SELECT current_user")[0][0]
