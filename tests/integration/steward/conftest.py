# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Offline fixtures for the Steward suite: a stub MCP transport and a materialised world.

Nothing in this directory touches a network, a cluster, a Cloud organisation or AWS. The
Managed-MCP transport is a stub that records every call and answers from a table, the
``ccloud`` leg reads the committed JSON in ``fixtures/ccloud/``, and the skills checkout
is synthesised in ``tmp_path``. That is deliberate and it is the point of the whole
package: a Steward run has to be provable on a machine that holds none of our credentials,
because ``VERIFY.md`` says every proof must run on a stranger's.

The live lane exists and is a separate module. It **skips** with a reason rather than
passing, because a green run with nothing to talk to would assert nothing.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
for _src in (
    _REPO_ROOT / "packages" / "mainline-mcp" / "src",
    _REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-steward" / "src",
):
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

from mainline_mcp.client import DEFAULT_DIALECT, Client, RawResponse  # noqa: E402
from mainline_mcp.limits import READ_VERBS, WRITE_VERB  # noqa: E402
from mainline_steward import default_lock  # noqa: E402

FIXTURES = _HERE.parent / "fixtures"
CCLOUD_FIXTURES = FIXTURES / "ccloud"
APP_DIR = _REPO_ROOT / "verticals" / "mainline" / "apps" / "steward"
PACKAGE_DIR = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-steward"

#: The contract of record when the fleet-contracts worker's file is present, and this
#: suite's own transcription of ARCHITECTURE.md §17 when it is not. Which one was used is
#: printed by `contract_path`, so a green run never hides which contract it ran against.
CONTRACT_OF_RECORD = _REPO_ROOT / "spec" / "mcp" / "audit-surface.contract.yaml"
CONTRACT_FALLBACK = FIXTURES / "audit-surface.contract.yaml"


def repo_root() -> Path:
    """The repository root, resolved from this file."""
    return _REPO_ROOT


class RecordingTransport:
    """A Managed-MCP transport that records every call and never opens a socket."""

    def __init__(
        self,
        *,
        cluster_id: str = "cl-steward-fixture",
        rows_by_view: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        failing_views: Sequence[str] = (),
    ) -> None:
        """Bind the canned answers."""
        self._cluster_id = cluster_id
        self._rows = dict(rows_by_view or {})
        self._failing = set(failing_views)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    @property
    def cluster_id(self) -> str:
        """The pinned cluster."""
        return self._cluster_id

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> RawResponse:
        """Answer one call, recording it first."""
        self.calls.append((name, dict(arguments)))
        # Keyed off the dialect, not a literal: the live SQL argument is ``query``
        # (measured 2026-08-16) and a fixture that hard-codes the old name routes
        # everything to the empty fallback instead of failing loudly.
        statement = str(arguments.get(DEFAULT_DIALECT.statement, ""))
        for view in self._failing:
            if view in statement:
                payload = {
                    "content": [{"type": "text", "text": f"relation {view} does not exist"}],
                    "isError": True,
                }
                return RawResponse(byte_count=len(json.dumps(payload)), payload=payload)
        rows: Sequence[Mapping[str, Any]] = []
        for view, canned in self._rows.items():
            if view in statement:
                rows = canned
                break
        payload = {"content": [{"type": "text", "text": json.dumps({"rows": list(rows)})}]}
        return RawResponse(byte_count=len(json.dumps(payload)), payload=payload)

    def list_tool_names(self) -> tuple[str, ...]:
        """The verbs the Managed MCP surface advertises."""
        return (*READ_VERBS, WRITE_VERB)

    def close(self) -> None:
        """Mark the transport closed."""
        self.closed = True


OPS_ROWS: dict[str, list[dict[str, Any]]] = {
    "v_gate_latency_daily": [
        {
            "site_id": "BLK-07",
            "d": "2026-08-03",
            "p50_ms": 41,
            "p95_ms": 180,
            "p99_ms": 402,
            "n": 91,
        },
        {
            "site_id": "BLK-07",
            "d": "2026-08-04",
            "p50_ms": 44,
            "p95_ms": 210,
            "p99_ms": 455,
            "n": 88,
        },
    ],
    "v_txn_restart_daily": [
        {"site_id": "BLK-07", "d": "2026-08-04", "restarts": 7, "txns": 88, "restart_ratio": 0.0795}
    ],
    "v_changefeed_health": [
        {
            "feed_name": "cf_custody",
            "status": "running",
            "high_water_lag_s": 4,
            "last_error_at": None,
        },
        {
            "feed_name": "cf_outbox",
            "status": "running",
            "high_water_lag_s": 2,
            "last_error_at": None,
        },
    ],
    "v_ledger_health": [
        {
            "site_code": "BLK-07",
            "tree_size": 20412,
            "admissible_checkpoints": 331,
            "inadmissible_checkpoints": 0,
            "open_debt": 2,
        }
    ],
    "v_fixity_coverage": [
        {
            "site_id": "BLK-07",
            "patrol_class": "setpoint",
            "last_completed": "2026-08-04",
            "not_checked_ratio": 0.11,
        }
    ],
    "v_unused_indexes": [
        {
            "table_name": "event_cue_coarse",
            "index_name": "cue_sweep_idx",
            "last_read": None,
            "total_reads": 0,
        }
    ],
    "v_open_gate_summary": [
        {
            "site_id": "BLK-07",
            "state": "open",
            "permits": 3,
            "open_blocking": 5,
            "open_residue": 0,
            "open_conflicts": 1,
            "open_warrants": 0,
            "unmodelled_assets": 0,
            "overrides_30d": 1,
        }
    ],
    "v_agent_actions": [
        {
            "agent_role": "agent_recaller",
            "tool": "select_query",
            "outcome": "ok",
            "n": 412,
            "last_at": "2026-08-04",
        }
    ],
    "v_weakenings_without_disposition": [
        {
            "site_id": "BLK-07",
            "activity_root": "confined-space",
            "sev_max": 5,
            "n": 2,
            "most_recent": "2026-07-30",
            "ancestry_complete": True,
        }
    ],
    "v_disposition_coverage": [
        {
            "site_id": "BLK-07",
            "q": "2026Q3",
            "surfaced": 40,
            "dispositioned": 37,
            "orphans": 3,
            "worst_ancestor": "EV-2004-11",
            "ancestry_complete": False,
        }
    ],
}
"""Canned rows for every view any declared schedule reads.

``restart_ratio`` and ``not_checked_ratio`` are IEEE-754 floats on purpose: they are what
the server actually returns, and they exercise the split between ``canonicalise`` (used
for the row digest, which must reproduce what the server sent) and ``canonicalise_payload``
(used for the ledger payload, which refuses floats under CU-5). A fixture with only
integers in it would let that distinction rot unnoticed.
"""


@pytest.fixture(scope="session")
def contract_path() -> Path:
    """The audit-surface contract this suite runs against, of record or fallback."""
    if CONTRACT_OF_RECORD.is_file():
        return CONTRACT_OF_RECORD
    print(
        f"\nthe contract of record is absent ({CONTRACT_OF_RECORD}); running against this "
        f"suite's transcription of ARCHITECTURE.md §17 at {CONTRACT_FALLBACK}"
    )
    return CONTRACT_FALLBACK


@pytest.fixture(scope="session")
def contract_of_record() -> Path:
    """Where the fleet-contracts worker's contract lives, present or not."""
    return CONTRACT_OF_RECORD


@pytest.fixture(scope="session")
def paths() -> dict[str, Path]:
    """The four directories this suite asserts against."""
    return {
        "repo": _REPO_ROOT,
        "app": APP_DIR,
        "package": PACKAGE_DIR,
        "ccloud_fixtures": CCLOUD_FIXTURES,
    }


@pytest.fixture
def ops_rows() -> dict[str, list[dict[str, Any]]]:
    """The canned rows, as a fixture so no test imports ``conftest`` directly."""
    return OPS_ROWS


@pytest.fixture
def make_client():
    """Build a client over a recording transport with a chosen set of failing views."""

    def build(*, failing_views: Sequence[str] = ()) -> tuple[Client, RecordingTransport]:
        transport = RecordingTransport(rows_by_view=OPS_ROWS, failing_views=failing_views)
        return Client(transport), transport

    return build


@pytest.fixture
def transport() -> RecordingTransport:
    """A transport answering every ops view with canned rows."""
    return RecordingTransport(rows_by_view=OPS_ROWS)


@pytest.fixture
def client(transport: RecordingTransport) -> Client:
    """A Managed-MCP client over the recording transport."""
    return Client(transport)


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    """A synthesised checkout of every pinned skill, one Markdown file each."""
    root = tmp_path / "skills"
    for pin in default_lock():
        directory = root / pin.path
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"# {pin.skill_id}\n\nStub for the offline suite. Upstream: {pin.upstream_url}\n",
            encoding="utf-8",
        )
    return root


@pytest.fixture
def transcript(tmp_path: Path) -> Path:
    """A ``claude -p --output-format json`` document carrying a narrative envelope.

    One narrative names a view that was never read. The suite asserts it is dropped and
    counted rather than becoming a finding — the model may describe a read and may not
    invent one.
    """
    envelope = {
        "narratives": {
            "mainline_audit.v_gate_latency_daily": "p95 moved from 180 ms to 210 ms overnight.",
            "mainline_audit.v_changefeed_health": "Both feeds running; custody lag 4 s.",
            "mainline_audit.v_nonexistent_view": "This view was never read.",
        }
    }
    document = {
        "type": "result",
        "subtype": "success",
        "num_turns": 6,
        "result": "Review complete.\n\n```json\n" + json.dumps(envelope, indent=2) + "\n```",
    }
    path = tmp_path / "session.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.fixture
def run_config(tmp_path: Path, contract_path: Path, skills_root: Path, transcript: Path):
    """A complete, fully-populated run configuration pointing at the shipped app directory."""
    from mainline_steward import RunConfig

    return RunConfig(
        app_dir=APP_DIR,
        contract_path=contract_path,
        site_code="BLK-07",
        mcp_cluster_id="cl-steward-fixture",
        iam_role_arn="arn:aws:iam::000000000000:role/mainline-steward",
        model_id="au.anthropic.claude-opus-5",
        inference_profile_arn=(
            "arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/"
            "au.anthropic.claude-opus-5"
        ),
        schema_version="sha256:fixture-schema-version",
        claude_code_version="2.1.221 (Claude Code)",
        skills_root=skills_root,
        transcript=transcript,
        out_dir=tmp_path / "run",
        state_dir=tmp_path / "state",
        ccloud_fixtures=CCLOUD_FIXTURES,
        dry_run=True,
    )
