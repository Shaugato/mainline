#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Re-derive the CockroachDB-feature and AWS-service census from the source tree.

``docs/TOOL-USAGE.md`` is the hackathon's *"which CockroachDB and AWS services did you
use, and how"* document. Every number in it is a count over this repository, and a count
in prose is a claim until something re-derives it. This program is that something.

**Three properties, each of them load-bearing.**

*Standard library only.* No third-party import, so a judge with a bare CPython 3.13 and a
clone of the repository can run it. There is no ``uv sync`` between the claim and its
check.

*No network and no credential.* The census is a function of files on disk. It never
reaches CockroachDB Cloud, never reaches AWS, and never reads an environment variable
holding a key. A document about which cloud services a project uses must not itself
require those cloud services to verify — otherwise the reader is trusting the same
credential the claim is about.

*No timestamp in the output.* This is the unusual one and it is deliberate. The two JSON
files are a **pure function of the tree**, so ``capture_tool_evidence.py --check`` after a
run is a genuine test: byte-identical output means the committed evidence still describes
the committed code, and a single differing byte means the document is stale. A
``generated_at`` field would make every run differ from every other and would quietly
destroy that property. Provenance lives in git, which records when the bytes changed and
who changed them, and is a better witness than a string the program writes about itself.

**Two exclusions worth stating out loud.** The scan skips ``evidence/tool-usage/`` and
``docs/TOOL-USAGE.md``. Both would otherwise match nearly every pattern below, so writing
the document would inflate the counts the document cites, and the census would be
measuring its own prose. A number that rises because you described it is not a
measurement.

Usage::

    python scripts/submission/capture_tool_evidence.py           # write the two JSON files
    python scripts/submission/capture_tool_evidence.py --check    # exit 1 if they are stale
    python scripts/submission/capture_tool_evidence.py --print    # census to stdout, write nothing
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

# --------------------------------------------------------------------------------------
# Scan set
# --------------------------------------------------------------------------------------

#: Directory names pruned wherever they appear. Caches, build output, virtualenvs and
#: vendored dependencies are not this project's source and counting them would make the
#: census depend on whether someone had recently run a build.
EXCLUDED_DIR_NAMES: Final = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hypothesis",
        ".hypothesis-corpus",
        ".import_linter_cache",
        ".terraform",
        "dist",
        "build",
        ".next",
        "out",
        "out_mainline",
        "out_trappoint_ref",
        "mine_templates",
        "site-packages",
    }
)

#: Paths, relative to the repository root, that are excluded because they are this
#: census's own output, the document it feeds, or this program itself. See the module
#: docstring. Excluding this file matters more than it looks: the patterns below are
#: string literals in it, so without this line the census would count itself as a use of
#: every feature it searches for.
EXCLUDED_RELPATHS: Final = (
    "evidence/tool-usage",
    "docs/TOOL-USAGE.md",
    "scripts/submission/capture_tool_evidence.py",
)

#: Extensions never opened. Binary content cannot contain a source token and decoding it
#: wastes the walk.
BINARY_SUFFIXES: Final = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".whl",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".mp4",
        ".mov",
        ".wav",
        ".so",
        ".dll",
        ".dylib",
        ".pyc",
        ".pyd",
        ".exe",
        ".bin",
        ".db",
        ".sqlite",
    }
)

#: Any file larger than this is skipped. Nothing in this tree that carries a meaningful
#: source token is bigger, and the ceiling keeps a stray artefact from dominating the run.
MAX_FILE_BYTES: Final = 4_000_000

#: Category ranking. Representative paths are chosen deterministically: sort by this rank,
#: then lexicographically, then take the first three. The ordering puts *executable
#: statements of the claim* ahead of *prose about the claim* — a migration or a Terraform
#: resource is stronger evidence than a planning document that mentions the same word.
CATEGORY_ORDER: Final = (
    "migration",
    "sql",
    "terraform",
    "python",
    "typescript",
    "config",
    "workflow",
    "docs",
    "other",
)


#: Suffix to bucket. Order does not matter; the two path-shape rules below run first.
SUFFIX_CATEGORY: Final = {
    ".sql": "sql",
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".rego": "terraform",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".md": "docs",
    ".rst": "docs",
    ".txt": "docs",
    ".toml": "config",
    ".yaml": "config",
    ".yml": "config",
    ".json": "config",
    ".cfg": "config",
    ".ini": "config",
    ".example": "config",
}


def categorise(relpath: str) -> str:
    """Bucket a repository-relative path. The buckets are the census's own taxonomy."""
    lower = relpath.lower()
    suffix = Path(lower).suffix
    # Two rules that depend on where the file sits, not what it is called. A migration is
    # a stronger exhibit than a loose .sql file, and a workflow than a loose .yml.
    if suffix == ".sql" and "/db/migrations/" in lower:
        return "migration"
    if lower.startswith(".github/workflows/"):
        return "workflow"
    if lower.endswith(".tf.fixture"):
        return "terraform"
    return SUFFIX_CATEGORY.get(suffix, "other")


@dataclass(frozen=True)
class ScannedFile:
    """One readable text file, its bucket, and its body.

    The body is held in memory for the whole run so that each pattern is one pass over
    memory rather than a second walk of the disk. Case folding is left to the regex flag:
    caching a lowercased copy would double the footprint to save nothing.
    """

    relpath: str
    category: str
    text: str


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every candidate file under ``root``, pruning excluded directories."""
    excluded_abs = {(root / rel).resolve() for rel in EXCLUDED_RELPATHS}
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if entry.name in EXCLUDED_DIR_NAMES:
                        continue
                    if entry.resolve() in excluded_abs:
                        continue
                    stack.append(entry)
                elif entry.is_file():
                    if entry.resolve() in excluded_abs:
                        continue
                    yield entry
            except OSError:
                continue


@dataclass
class Scan:
    """The corpus every pattern below is counted against."""

    root: Path
    files: list[ScannedFile] = field(default_factory=list)
    skipped_binary: int = 0
    skipped_large: int = 0
    skipped_unreadable: int = 0

    @property
    def counts_by_category(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.files:
            out[f.category] = out.get(f.category, 0) + 1
        return {k: out[k] for k in sorted(out)}


def scan_tree(root: Path) -> Scan:
    """Read every text file once. Every pattern is then a pass over memory, not disk."""
    scan = Scan(root=root)
    for path in iter_files(root):
        if path.suffix.lower() in BINARY_SUFFIXES:
            scan.skipped_binary += 1
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            scan.skipped_unreadable += 1
            continue
        if len(raw) > MAX_FILE_BYTES:
            scan.skipped_large += 1
            continue
        if b"\x00" in raw[:8192]:
            scan.skipped_binary += 1
            continue
        text = raw.decode("utf-8", errors="replace")
        relpath = path.relative_to(root).as_posix()
        scan.files.append(
            ScannedFile(
                relpath=relpath,
                category=categorise(relpath),
                text=text,
            )
        )
    scan.files.sort(key=lambda f: f.relpath)
    return scan


# --------------------------------------------------------------------------------------
# The census rows
# --------------------------------------------------------------------------------------

VERDICTS: Final = ("EXERCISED", "DESIGNED", "NOT-AVAILABLE")


@dataclass(frozen=True)
class Row:
    """One CockroachDB tool/feature or one AWS service.

    ``pattern`` is a regular expression applied to the file body. It is published in the
    output verbatim so a reader can re-run the same search with their own tools and get
    the same number; a count whose search string is hidden is not reproducible.
    """

    key: str
    name: str
    kind: str  # "tool" | "feature" | "service"
    pattern: str
    case_sensitive: bool
    verdict: str
    verdict_basis: str
    how: str
    anchor: str  # "path:line" — the single most load-bearing occurrence, hand-checked
    #: A substring the anchor's line MUST contain, case-insensitively.
    #:
    #: Checking that ``path:line`` *resolves* only proves the file is long enough. It does
    #: not prove the line still says what the row is about, and on 2026-08-12 five AWS
    #: anchors were found pointing at a bare ``}``, a ``})``, a blank line, ``timeout =
    #: var.timeout`` and a fragment of an unrelated docstring — every one of them
    #: "resolving" perfectly. A judge following those citations reads a closing brace and
    #: concludes the document is decorative. So the anchor now has to prove its subject:
    #: :func:`main` REFUSES to write when this substring is absent, which turns silent
    #: citation rot into a red gate at the moment the line moves.
    anchor_must_contain: str
    scope: str = ""  # optional path prefix restriction, posix, "" = whole tree

    def compiled(self) -> re.Pattern[str]:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        return re.compile(self.pattern, flags)


CRDB_ROWS: Final[tuple[Row, ...]] = (
    Row(
        key="crdb_database",
        name="CockroachDB (the database) — v26.2.5",
        kind="tool",
        pattern=r"v26\.2\.5",
        case_sensitive=True,
        verdict="EXERCISED",
        verdict_basis=(
            "evidence/gate-refusal/proof-20260810T004200Z.json#cluster.version reports "
            "'CockroachDB CCL v26.2.5' from the node the proof ran against"
        ),
        how=(
            "The product's central claim is a database refusal. The image tag is pinned in "
            "compose.yaml and asserted by the proof run, so the version under the claim is "
            "recorded rather than assumed."
        ),
        anchor="compose.yaml:31",
        anchor_must_contain="cockroachdb/cockroach:v26.2.5",
    ),
    Row(
        key="crdb_serializable",
        name="SERIALIZABLE isolation (the default, never weakened under the gate)",
        kind="feature",
        pattern=r"serializable",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "measured on the pinned local node: SHOW default_transaction_isolation returns "
            "'serializable', and a write-skew pair — two transactions each reading sum(v), "
            "then each updating a different row — was REFUSED at commit with 40001 "
            "'restart transaction: TransactionRetryWithProtoRefreshError'. The isolation "
            "level is not merely reported; it refuses"
        ),
        how=(
            "The merge gate re-derives an obligation count and then writes; under anything "
            "weaker than SERIALIZABLE that read-then-write is a write-skew hole. Isolation "
            "is set explicitly on the connection instead of trusted as a default, and 40001 "
            "is the only SQLSTATE the harness retries."
        ),
        anchor="packages/trappoint-model/src/trappoint_model/cluster.py:222",
        anchor_must_contain="isolation",
    ),
    Row(
        key="crdb_triggers",
        name="PL/pgSQL triggers and functions (v26.2 feature)",
        kind="feature",
        pattern=r"CREATE (?:OR REPLACE )?TRIGGER",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "evidence/gate-refusal/proof-20260810T004200Z.json#drift_refusal raises "
            "P0001 from mainline.fn_permit_merge_gate — a trigger function executing"
        ),
        how=(
            "The gate is a BEFORE trigger, not application code, so it is enforced against "
            "psql, a migration script and a back-office correction alike. "
            "0115_fn_permit_merge_gate.sql:77 is the RAISE that produces the P0001 exhibit; "
            "0120_trg_check_project.sql:28 is the projection trigger."
        ),
        anchor="verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:77",
        anchor_must_contain="P0001",
    ),
    Row(
        key="crdb_check_constraints",
        name="Named CHECK constraints as the refusal exhibit",
        kind="feature",
        pattern=r"gate_closed_when_issued",
        case_sensitive=True,
        verdict="EXERCISED",
        verdict_basis=(
            "evidence/gate-refusal/proof-20260810T004200Z.json#refusal.constraint == "
            "'gate_closed_when_issued', source 'reported'"
        ),
        how=(
            "The constraint NAME is the deliverable, not the exception. A refusal with the "
            "right SQLSTATE and the wrong constraint name is the right outcome for the wrong "
            "reason, so every conformance case asserts both."
        ),
        anchor="verticals/mainline/db/migrations/0050_permit.sql:114",
        anchor_must_contain="gate_closed_when_issued",
    ),
    Row(
        key="crdb_vector_index",
        name="C-SPANN vector index (VECTOR INDEX, prefix-constrained ANN)",
        kind="feature",
        pattern=r"VECTOR INDEX|vector_index|cspann|C-SPANN|vector_cosine_ops",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "measured on the pinned local node: a table of this exact shape with 500 rows "
            "plans as '• vector search / table: clause_embedding@ce_ann' ONLY with the "
            "@ce_ann hint; the same query without the hint does not choose the index. Note "
            "the operator must match the opclass — <-> against a vector_cosine_ops index "
            "raises 42809 'index cannot be used for this query'"
        ),
        how=(
            "Recall over clauses and event cues is an ANN scan inside the same database that "
            "holds the gate, so retrieval and refusal share one transaction domain. The index "
            "is declared INLINE at CREATE TABLE — on v26.2 a CREATE VECTOR INDEX against a "
            "populated table is the slow path — and every prefix column must be a single "
            "value for the index to be chosen."
        ),
        anchor="verticals/mainline/db/migrations/0031_clause_embedding.sql:149",
        anchor_must_contain="VECTOR INDEX ce_ann",
    ),
    Row(
        key="crdb_as_of_system_time",
        name="AS OF SYSTEM TIME (bounded time travel, and its refusal)",
        kind="feature",
        pattern=r"AS OF SYSTEM TIME",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "measured on the pinned local node 2026-08-12 in scratch database "
            "w_w6_tool_usage: AS OF SYSTEM TIME '-90m' over system.namespace returned 1619 "
            "rows, while '-2160h' (90 days) was REFUSED with SQLSTATE XXUUU, message 'error "
            "in retrieving descs between ...: batch timestamp ... must be after replica GC "
            "threshold ... (r7: /Table/{0-4})'. What that pair demonstrates is that a "
            "far-past read is refused rather than answered — not the 4500 s boundary "
            "specifically, which is the conformance case CF-46 and has not been "
            "demonstrated. CORRECTION TO AN EARLIER BASIS, from re-running it rather than "
            "remembering it: the row count was quoted as 3658, a live cluster's count on a "
            "different day that was never going to reproduce, and the message was quoted as "
            "'found no descriptor', where this node names the GC threshold directly. The "
            "SQLSTATE XXUUU did reproduce exactly and is unchanged. Note it was read from "
            "psycopg's sqlstate field: the cockroach CLI renders this refusal WITHOUT a "
            "SQLSTATE line, and trusting that rendering would have produced a confident, "
            "false correction"
        ),
        how=(
            "Used for consistent read-only snapshots — and, more importantly, used to mark "
            "the boundary of what it can prove. gc.ttlseconds is pinned locally to the Cloud "
            "value of 4500 s, so a query past the window is REFUSED rather than silently "
            "wrong, and long-horizon history is the application-level commit DAG instead."
        ),
        anchor="packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106",
        anchor_must_contain="AS OF SYSTEM TIME",
    ),
    Row(
        key="crdb_follower_reads",
        name="Follower reads (follower_read_timestamp())",
        kind="feature",
        pattern=r"follower_read",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "SELECT follower_read_timestamp() and a count AS OF that timestamp both returned "
            "on the pinned local node in this worker's scratch database"
        ),
        how=(
            "Fixity patrol and coverage scans read at follower_read_timestamp() so that a "
            "background integrity sweep never contends with a merge. A patrol run that cannot "
            "state its follower-read timestamp is refused by its own emitter."
        ),
        anchor="verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37",
        anchor_must_contain="follower_read_timestamp()",
    ),
    Row(
        key="crdb_row_level_security",
        name="Row-level security (ENABLE / FORCE ROW LEVEL SECURITY)",
        kind="feature",
        pattern=r"ROW LEVEL SECURITY",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "ENABLE + FORCE + CREATE POLICY applied on the pinned local node in this worker's "
            "scratch database; pg_class reports relrowsecurity and relforcerowsecurity true"
        ),
        how=(
            "FORCE, so table owners are not exempt. Policy expressions carry no subquery and "
            "no session variable — a session variable is client-settable and would degrade RLS "
            "to an application-cooperative control against exactly the adversary it constrains "
            "— so the documented-safe shape is USING (col = CURRENT_USER)."
        ),
        anchor="verticals/mainline/db/migrations/0181a_permit_rls_force.sql:54",
        anchor_must_contain="FORCE ROW LEVEL SECURITY",
    ),
    Row(
        key="crdb_show_create",
        name="SHOW CREATE / pg_get_functiondef (schema self-attestation)",
        kind="feature",
        pattern=r"SHOW CREATE",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "SHOW CREATE TABLE on the pinned local node returned DDL naming the vector index; "
            "packages/trappoint-migrate/src/trappoint_migrate/attest.py:243 is the caller"
        ),
        how=(
            "The migration runner fingerprints the live schema from SHOW CREATE ALL "
            "SCHEMAS/TYPES/TABLES plus pg_get_triggerdef/pg_get_functiondef, normalises and "
            "hashes it, and chains the hash into schema_attestation. The gate's own source "
            "text is therefore inside the attestation: you cannot quietly edit the gate."
        ),
        anchor="packages/trappoint-migrate/src/trappoint_migrate/attest.py:243",
        anchor_must_contain="SHOW CREATE ALL SCHEMAS",
    ),
    Row(
        key="crdb_internal",
        name="crdb_internal (used by us, forbidden to the audit identity)",
        kind="feature",
        pattern=r"crdb_internal",
        case_sensitive=True,
        verdict="EXERCISED",
        verdict_basis=(
            "re-measured on the pinned local node 2026-08-12: the bare builtin "
            "cluster_logical_timestamp() returns, while crdb_internal is RESTRICTED BY "
            "DEFAULT on v26.2.5 — 'SELECT count(*) FROM crdb_internal.tables' raises 42501 "
            "'Access to crdb_internal and system is restricted' and only succeeds after "
            "SET allow_unsafe_internals = true. The restriction is not crdb_internal-"
            "specific: system.namespace is behind the same opt-in, as the "
            "crdb_as_of_system_time row's measurement had to discover. No row COUNT is "
            "quoted for the unlocked query, deliberately — it counts descriptors across "
            "every database on the node, so on a shared node it measures who else was "
            "working rather than anything about CockroachDB"
        ),
        how=(
            "Two opposite uses. Internally, cluster_logical_timestamp() is the HLC the "
            "sequencer orders appends by, since sequences are banned. Externally, "
            "crdb_internal is on the MCP identity's forbidden list — that it is unreachable "
            "is what proves the mainline_audit views are the API rather than a bypass. "
            "MEASURED CORRECTION: on v26.2.5 the qualified spelling "
            "crdb_internal.cluster_logical_timestamp() raises 42883 'unknown function'; the "
            "builtin is unqualified. The unreachability is therefore a platform default "
            "before it is a policy of ours, which strengthens the claim rather than weakening "
            "it."
        ),
        anchor="packages/mainline-mcp/src/mainline_mcp/limits.py:75",
        anchor_must_contain="FORBIDDEN_SCHEMAS",
    ),
    Row(
        key="crdb_changefeed",
        name="CHANGEFEED (CDC out of the outbox)",
        kind="feature",
        pattern=r"CREATE CHANGEFEED",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "measured on the pinned local node 2026-08-12: SHOW CHANGEFEED JOBS answers and "
            "reports 0 jobs, because no changefeed has ever been created on any cluster in "
            "this project. MEASURED CORRECTION, and it makes the verdict stronger rather "
            "than weaker: an earlier basis said 'kv.rangefeed.enabled is true'. It reads "
            "FALSE on this node today. So CDC here is not merely unstarted, it is not "
            "currently startable without flipping a cluster setting first — which is the "
            "honest shape of a DESIGNED verdict and is exactly what a reader would discover "
            "on their own node"
        ),
        how=(
            "CDC is deliberately NOT in a migration — CREATE CHANGEFEED in a migration makes "
            "migrations non-idempotent across a restore — so it is owned by the provisioning "
            "agent, and 0155a/0168 exist to observe changefeed health rather than to start "
            "one. RLS is never enabled on the outbox because CDC queries fail on RLS-enabled "
            "and multi-family tables."
        ),
        anchor="verticals/mainline/db/migrations/0168_v_changefeed_health.sql:37",
        anchor_must_contain="CREATE CHANGEFEED",
    ),
    Row(
        key="crdb_cloud_ccloud",
        name="CockroachDB Cloud + the ccloud CLI",
        kind="tool",
        pattern=r"ccloud",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "evidence/ccloud/cluster-list.txt is a captured transcript of "
            "`ccloud auth whoami` + `ccloud cluster list -o json` against mainline-dev"
        ),
        how=(
            "The Cloud cluster mainline-dev is Basic/Serverless on AWS aws-ap-southeast-1, "
            "capped at a spend_limit of 2500 (US$25.00). The CLI is driven with -o json and "
            "the JSON is parsed, never screen-scraped. LIMITATION, measured: ccloud 0.6.12 "
            "has no non-interactive service-account auth (auth exposes only login/logout/"
            "whoami, login is browser-based, CC_API_KEY is ignored), so headless paths use "
            "the Cloud REST API with the same key; and audit-log endpoints 404 on this tier."
        ),
        anchor="evidence/ccloud/README.md:37",
        anchor_must_contain="0.6.12",
    ),
    Row(
        key="crdb_managed_mcp",
        name="CockroachDB Managed MCP Server (cockroachlabs.cloud/mcp)",
        kind="tool",
        pattern=r"cockroachlabs\.cloud/mcp|mcp-cluster-id|mainline_audit",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "PROMOTED 2026-08-12, and the basis it replaces is worth reading: this row said "
            "'no live session against the managed endpoint is captured in evidence/' and "
            "that stopped being true on 2026-08-11. evidence/deploy/judge-run.json records "
            "an MCP session against https://cockroachlabs.cloud/mcp — payload channels.mcp."
            "ran true, protocol 2025-06-18, server cockroachdb-cloud 1.0.0, tools/list "
            "returning 12 tools — driving the whole "
            "evidence/deploy/judge-run.json#/questions = 16 question pack against the live "
            "Basic cluster 7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e, with "
            "evidence/deploy/judge-run.json#/channels/mcp/passed = 15 of "
            "evidence/deploy/judge-run.json#/channels/mcp/total = 16 PASS. THE FAILURE IS "
            "NOT ROUNDED OFF: the run's own verdict is 'DIVERGED - KNOWN GAP' because the "
            "managed-mcp identity can read mainline_qa.v_disposition_profile, which the "
            "pack asserted it could not. It also settles two questions pessimistically "
            "assumed before: the endpoint runs as SQL user 'managed-mcp', not root and not "
            "the database owner, and managed_mcp_availability.credential_publishable is "
            "FALSE, so this channel cannot be handed to anonymous judges. STILL TRUE AND "
            "UNCHANGED: tests/integration/mcp skips with a reason when no key is present "
            "rather than passing vacuously, so the SUITES remain unexercised in CI even "
            "though the endpoint is not"
        ),
        how=(
            "MCP Streamable HTTP, bearer service-account key, mcp-cluster-id header pinning "
            "exactly one cluster. Every documented cap is a type rather than a comment — one "
            "statement per call, 16384 chars, 20 s, 10240-byte response, 25 default rows — "
            "and a statement that would breach one is refused CLIENT-SIDE with an error "
            "naming the limit. The server TRUNCATES rather than raising, so a 10 KiB "
            "response is indistinguishable from an answer; the nine mainline_audit views are "
            "shaped aggregate-first to ≤25 rows and ≤8192 bytes, 80% of the cap, precisely "
            "so a truncated safety aggregate never reaches a reader."
        ),
        anchor="packages/mainline-mcp/src/mainline_mcp/limits.py:45",
        anchor_must_contain="cockroachlabs.cloud/mcp",
    ),
    Row(
        key="crdb_agent_skills",
        name="CockroachDB Agent Skills (authored, plus an upstream contribution)",
        kind="tool",
        pattern=r"designing-diachronic-gates|designing-vector-recall-prefixes"
        r"|cockroachdb-resilience-and-disaster-recovery",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "two skills are on disk, each shipping an executable assertion script; neither "
            "script's run is captured under evidence/, so they are shipped and not evidenced"
        ),
        how=(
            "Each skill ships a script that FAILS when the guarantee does not hold — "
            "assert_gate_refuses.py replays an illegal history and fails unless the expected "
            "SQLSTATE and constraint name are raised; assert_prefix_index_used.py fails "
            "unless the plan actually chooses the vector index. A skill whose advice cannot "
            "be falsified is a blog post. A de-branded resilience/DR skill is staged under "
            "skills/upstream/ for contribution back to Cockroach Labs."
        ),
        anchor="skills/designing-diachronic-gates/scripts/assert_gate_refuses.py:57",
        anchor_must_contain="_SQLSTATE",
    ),
)


AWS_ROWS: Final[tuple[Row, ...]] = (
    Row(
        key="aws_bedrock_runtime",
        name="Amazon Bedrock — Claude inference via au.* profiles",
        kind="service",
        pattern=r"bedrock",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "a live bedrock-runtime:Converse against the Australia-only inference profile "
            "au.anthropic.claude-haiku-4-5-20251001-v1:0 in ap-southeast-2 returned "
            "evidence/aws/probe/raw-haiku-converse.json#/payload/response/metadata/"
            "http_status = 200 with an AWS request id, stopReason end_turn, "
            "evidence/aws/probe/raw-haiku-converse.json#/payload/response/usage/inputTokens "
            "= 22 and evidence/aws/probe/raw-haiku-converse.json#/payload/response/usage/"
            "outputTokens = 8; the summary that checks it is "
            "evidence/aws/probe/bedrock-probe.json (payload.checks."
            "haiku_http_200_with_request_id). The PRODUCT's own agent layer then ran on it: "
            "evidence/aws/agent/live-run.json#/payload/leg_count = 7 live InvokeModel legs "
            "through that same au.* profile, each with an AWS request id and each recorded "
            "as a cassette, carrying "
            "evidence/aws/agent/live-run.json#/payload/token_ledger/0/input_tokens = 17429 "
            "input tokens (the output count is deliberately NOT quoted here: generation is "
            "not reproducible, and this repository claims replayability of recorded calls "
            "and never reproducibility of generation); evidence/aws/agent/determinism.json "
            "replays those cassettes twice "
            "to a byte-identical decision hash and refuses to load a tampered one. "
            "Corroborated from OUTSIDE this repository by AWS's own metric series for that "
            "ModelId in evidence/aws/cloudwatch/bedrock-metrics.json. WHAT THIS DOES NOT "
            "SAY: the live legs ran on claude-haiku-4-5 while the shipping request builders "
            "target the pinned claude-opus-5 generation, and four builder fields are refused "
            "on the wire by haiku — projected at the wire, named field by field, in "
            "evidence/aws/agent/live-run.json#/payload/measured_wire_refusals, never written "
            "back into a builder. And no live leg REFUSED "
            "(payload.refusal_behaviour.live_refusals_observed 0), so the "
            "refusal-degrades-the-run path was exercised against a CONSTRUCTED refusing "
            "transport rather than a model that said no. SECOND, INDEPENDENT TRANSCRIPT, "
            "different day and different program: evidence/deploy/aws-live.json records a "
            "bedrock-runtime:Converse on au.anthropic.claude-haiku-4-5-20251001-v1:0 at "
            "evidence/deploy/aws-live.json#/calls/3/http_status = 200, stop_reason "
            "end_turn, AWS REQUEST ID 3c7a283c-9f67-4d98-aa8f-26490d54d32d, "
            "evidence/deploy/aws-live.json#/calls/3/usage/output_tokens = 8. The request "
            "id is the load-bearing part: it is a string AWS minted and this repository "
            "could not have, so a reader with the account's CloudTrail can look it up and "
            "a reader without one can at least see that we did not round-number it"
        ),
        how=(
            "bedrock-runtime InvokeModel with the Anthropic native body. The modelId is an "
            "au.* inference-profile ARN RESOLVED AT START-UP from ListInferenceProfiles and "
            "pinned into the run record — never hard-coded — and any identifier without the "
            "au. prefix is refused by the transport as a residency violation. One model "
            "generation across the fleet, differentiated by effort rather than by model."
        ),
        anchor="packages/mainline-agentkit/src/mainline_agentkit/transport.py:273",
        anchor_must_contain="Refuse any model identifier",
    ),
    Row(
        key="aws_bedrock_embeddings",
        name="Amazon Bedrock — embeddings (Titan v2, Cohere embed v4)",
        kind="service",
        pattern=r"titan-embed-text-v2|cohere\.embed-v4|titan_embed|BedrockTitan",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "amazon.titan-embed-text-v2:0 produced "
            "evidence/aws/embeddings/manifest.json#/payload/totals/vectors = 2060 vectors of "
            "width evidence/aws/embeddings/manifest.json#/payload/dimensions = 1024 in "
            "ap-southeast-2, for "
            "evidence/aws/embeddings/manifest.json#/payload/totals/input_tokens = 177345 "
            "input tokens, enumerated one per row with a text digest, a vector digest and a "
            "token count; evidence/aws/ann/ann-proof.json then searched "
            "evidence/aws/ann/ann-proof.json#/payload/vectors/rows_searched = 1080 of them "
            "through CockroachDB's ce_ann index and names the same model at "
            "payload.vectors.embed_model_expected. TWO SINGLE-CALL ROUND TRIPS NAME AN AWS "
            "REQUEST ID EACH, and they are different calls on different days rather than "
            "one call quoted twice: evidence/aws/probe/raw-titan-invoke.json records "
            "request id 6dcdcdf0-38d3-453f-a476-fa69b2d87863 at "
            "evidence/aws/probe/raw-titan-invoke.json#/payload/response/metadata/"
            "http_status = 200, width "
            "evidence/aws/probe/raw-titan-invoke.json#/payload/derived/embedding_length = "
            "1024 and L2 norm "
            "evidence/aws/probe/raw-titan-invoke.json#/payload/derived/l2_norm = "
            "1.00000006; evidence/deploy/aws-live.json records request id "
            "b4d826e9-03ba-4368-9687-f00cc28a98ef at "
            "evidence/deploy/aws-live.json#/calls/2/http_status = 200 and width "
            "evidence/deploy/aws-live.json#/calls/2/embedding_dimension = 1024, whose L2 "
            "norm is recorded as evidence/deploy/aws-live.json#/calls/2/embedding_l2_norm "
            "= 1.0 because that program rounds and the probe does not — the two figures "
            "are not in conflict and neither may be quoted as the other. RESIDENCY "
            "FINDING, MEASURED AND PUBLISHED RATHER THAN WORKED AROUND: cohere.embed-v4:0 "
            "is REFUSED on-demand in ap-southeast-2 — ValidationException, "
            "evidence/aws/probe/raw-cohere-refusal.json#/payload/error/metadata/"
            "http_status = 400, request id a826eb16-e813-45aa-932e-4696e9979087 — and "
            "evidence/aws/bench/residency-finding.json#/payload/inference_profiles/"
            "count_containing_cohere_embed_v4 = 1 says the only profile carrying it is "
            "global.cohere.embed-v4:0, which AWS's own description calls global routing. "
            "The in-region answer is cohere.embed-english-v3 (ON_DEMAND, ap-southeast-2), "
            "and it carries its own limit: Bedrock refuses any single text over 2048 "
            "characters for it. WHAT THIS DOES NOT SAY: the corpus is "
            "SYNTHETIC, the vector blobs live under the gitignored out/ so the manifest's "
            "per-vector sha256 is the checkable part, and Tier-2 verification in VERIFY.md "
            "still needs no model call because the committed fixtures are unchanged"
        ),
        how=(
            "The embedding provider writes into the C-SPANN sidecar tables. Model ids are "
            "never hard-coded at a call site — tests/unit/recall_providers/"
            "test_no_hardcoded_model_ids.py enforces that — and every embedding row stores "
            "its embed_model and index_gen, because a vector whose model is unknown cannot "
            "be compared to anything."
        ),
        # Retargeted 2026-08-11. This anchor used to name line 39, which was inside the
        # module docstring until that docstring's stale "credentials are not valid here"
        # sentence was corrected; line 39 is now `from __future__ import annotations`. A
        # citation that has silently slid onto an import is the exact rot `resolve_anchor`
        # quotes line text to expose, and 55 is the constant the row is actually about.
        anchor=(
            "verticals/mainline/packages/mainline-recall-agent/src/"
            "mainline_recall_agent/providers/bedrock_titan.py:55"
        ),
        anchor_must_contain="amazon.titan-embed-text-v2:0",
    ),
    Row(
        key="aws_bedrock_rerank",
        name="Amazon Bedrock Rerank",
        kind="service",
        # Narrow on purpose. A bare /rerank/ also matches CockroachDB's own
        # `vector_search_rerank_multiplier` session variable and every discussion of
        # listwise reranking, and a NOT-AVAILABLE row inflated by unrelated hits is
        # exactly the kind of number this census exists to prevent.
        pattern=r"[Bb]edrock [Rr]erank|bedrock-agent-runtime|amazon\.rerank|cohere\.rerank",
        case_sensitive=False,
        verdict="NOT-AVAILABLE",
        verdict_basis=(
            "Bedrock Rerank is not offered in ap-southeast-2. The live control-plane census "
            "in evidence/aws/probe/model-availability.json enumerates what IS offered and it "
            "is not among them, and docs/HONESTY.md records the absence and confirms no "
            "dependency was taken on it. The absence cost nothing because listwise reranking "
            "was designed onto the Claude profile before it was checked, which is why this "
            "row anchors at that reranker rather than at the sentence announcing the gap"
        ),
        how=(
            "NOT USED, and named here because a services list that omits what you checked and "
            "could not have is a list you cannot audit. Listwise reranking is done by the "
            "Claude profile at high effort instead, and CockroachDB's own "
            "vector_search_rerank_multiplier session variable (observed at 50) governs the "
            "ANN side. The design assumed Rerank's absence before it was checked."
        ),
        # Re-pointed TWICE on 2026-08-12, and the second move is the instructive one.
        #
        # It named docs/HONESTY.md:276, a BLANK LINE — resolving perfectly, saying nothing.
        # Re-pointed to :658, the table row that makes the claim. Within the hour the new
        # `anchor_must_contain` guard fired: HONESTY.md is another worker's file, under
        # active edit, and the row had moved to :697. A line number into a prose document
        # somebody else is rewriting is a citation with a short half-life, however carefully
        # it is placed.
        #
        # So this row now anchors at the SUBSTITUTE rather than at the announcement. The
        # claim is "Rerank is unavailable and listwise reranking is done by the Claude
        # profile instead"; ListwiseReranker is the thing that does it, it is the reason the
        # absence cost nothing, and it moves only when the mechanism moves. HONESTY.md is
        # still cited in `how` as prose, where a drifting line number does no harm.
        anchor=(
            "verticals/mainline/packages/mainline-recall-agent/src/"
            "mainline_recall_agent/rerank/listwise.py:77"
        ),
        anchor_must_contain="class ListwiseReranker",
    ),
    Row(
        key="aws_s3_object_lock",
        name="Amazon S3 + Object Lock (COMPLIANCE mode) — the evidence store",
        kind="service",
        pattern=r"aws_s3_bucket|s3:PutObject|object[_ -]?lock",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "the module and its Rego policies are complete and the plan fixtures exercise "
            "them, but no bucket has been applied: the S3 object-lock comparison is one of "
            "the SEVEN cryptographic checks in the custody bundle that DID NOT RUN "
            "(qa/test-state.json#external_checks.custody_bundle_verification.counts."
            "not_checked)"
        ),
        how=(
            "Checkpoints of the tamper-evident ledger are written to a versioned bucket whose "
            "Object Lock configuration is COMPLIANCE mode — which even the root account cannot "
            "shorten — and object_lock_enabled is set AT BUCKET CREATION because it cannot be "
            "added afterwards, which is why the module refuses a second bucket. The writer "
            "identity is denied DeleteObjectVersion and denied PutObjectRetention with an "
            "unconstrained retention date."
        ),
        anchor="infra/modules/evidence-store/main.tf:100",
        anchor_must_contain="aws_s3_bucket_object_lock_configuration",
    ),
    Row(
        key="aws_kms",
        name="AWS KMS — ECC_NIST_P256 SIGN_VERIFY key",
        kind="service",
        pattern=r"aws_kms|kms:Sign|KMS_SIGNING_ALGORITHM|ECC_NIST_P256",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "the signer and its key policy are implemented against an injected client and "
            "unit-tested offline; the live KMS signature check is one of the seven "
            "cryptographic checks that did not run"
        ),
        how=(
            "Checkpoint signatures use an asymmetric ECC_NIST_P256 SIGN_VERIFY key with "
            "MessageType=RAW, so KMS hashes the message itself — passing pre-hashed bytes "
            "under DIGEST would have KMS hash our note text a second time and produce a "
            "signature over the wrong thing. DER signatures are stored exactly as KMS "
            "returns them, no re-encoding. Key deletion is gated and rotation is off, because "
            "a rotated signing key silently invalidates historical verification."
        ),
        anchor="packages/trappoint-ledger/src/trappoint_ledger/signer.py:63",
        anchor_must_contain="ECDSA_SHA_256",
    ),
    Row(
        key="aws_cloudtrail",
        name="AWS CloudTrail — custody of the custodian",
        kind="service",
        pattern=r"aws_cloudtrail|cloudtrail",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "one aws_cloudtrail resource with log-file validation and two advanced event "
            "selectors is written and never applied; no trail exists in the account"
        ),
        how=(
            "A multi-region trail with enable_log_file_validation, so AWS produces its own "
            "signed digest chain over the same events — weaker than ours because AWS holds "
            "the key, and useful for exactly that reason: it is a chain we could not have "
            "forged. Management events make kms:ScheduleKeyDeletion, PutKeyPolicy and "
            "PutObjectLockConfiguration visible to the custody patrol within one checkpoint "
            "cadence instead of at the next audit."
        ),
        anchor="infra/envs/evidence/main.tf:114",
        anchor_must_contain="aws_cloudtrail",
    ),
    Row(
        key="aws_lambda",
        name="AWS Lambda — the /v1/* demo API",
        kind="service",
        pattern=r"aws_lambda|lambda_function|LambdaFunctionURL",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "the module is complete (python3.13, arm64, 512 MB, 15 s, four alarms, one "
            "dashboard) and NOTHING IS DEPLOYED. A plan exists and a plan is not an apply: "
            "evidence/deploy/terraform-plan-furl.txt reads '11 to add, 0 to change, 0 to "
            "destroy' and terraform apply has not been run against it, so there is no "
            "function, no role, no log group and no demo URL as of this census. This row "
            "stays DESIGNED until an apply has happened — promoting it because an apply is "
            "planned and authorised is exactly the arithmetic the verdict column exists to "
            "refuse"
        ),
        how=(
            "One python3.13 arm64 function in ap-southeast-1, beside the Cloud cluster, "
            "because the same call from ap-southeast-2 pays about 90 ms each way and the "
            "gate screen makes six of them. Its execution role's entire non-managed grant "
            "is ssm:GetParameter on ONE parameter ARN plus a conditioned kms:Decrypt. "
            "MEASURED CORRECTION, and it is the kind that matters: an earlier census said "
            "this row's Function URL was 'AWS_IAM — never NONE'. THAT IS NOT WHAT THE "
            "COMMITTED PLAN DOES. var.url_authorization_type defaults to NONE and "
            "evidence/deploy/terraform-plan-furl.txt:326 plans authorization_type = "
            '"NONE", because AWS_IAM is only a hardening if a CloudFront distribution '
            "exists to be granted lambda:InvokeFunctionUrl — and this account cannot "
            "create one (see the aws_cloudfront row). An AWS_IAM URL with no principal "
            "behind it is not a hardened demo, it is a demo nobody can reach. So the URL "
            "is public and the module says so — and THE LIST OF WHAT BOUNDS IT IS NOW "
            "SHORTER THAN THIS ROW ONCE CLAIMED. This census used to say "
            "'reserved_concurrent_executions caps the bill'. It does not and it never "
            "did on this account: `aws lambda get-account-settings` reports "
            "AccountLimit.ConcurrentExecutions = 10 in both ap-southeast-1 and "
            "ap-southeast-2, min(20, 10) = 10, and every POSITIVE reservation is refused "
            "at apply — so the plan now carries "
            "evidence/deploy/terraform-plan-furl.txt:279 "
            "reserved_concurrent_executions = -1 and the reservation is not a control at "
            "all. What is left is genuinely load-bearing and is written down instead of "
            "assumed: the ACCOUNT concurrency ceiling of 10 (an AWS default nobody chose, "
            "and `Adjustable: true` — raising it raises the worst case linearly), the "
            "handler's write surface being one transaction that ends in ROLLBACK (which "
            "bounds database STATE, not spend), and the Basic cluster's own spend limit "
            "(which bounds the database side only — a flood's target is the static tree "
            "inside the zip, which opens no connection). The -concurrency alarm at "
            "evidence/deploy/terraform-plan-furl.txt:77 is a TRIPWIRE, not a bound: it "
            "reports and does not stop, and it plans threshold = 8 against that ceiling "
            "of 10 rather than the 20 it used to sit above. That is a smaller claim than "
            "'invocable by one distribution and nothing else', smaller again than the one "
            "this row carried yesterday, and it is the true one for this account."
        ),
        # Re-pointed 2026-08-12. This anchor named main.tf:257, which reads
        # `timeout = var.timeout` — a citation that resolved and proved nothing.
        # Re-pointed 2026-08-13: the deploy-safety wave rewrote this module and :310 slid
        # onto a prose comment line. :333 is `authorization_type = var.url_authorization
        # _type` — the authorisation decision itself, which is what the row turns on.
        anchor="infra/modules/demo-api/main.tf:333",
        anchor_must_contain="authorization_type",
    ),
    Row(
        key="aws_cloudfront",
        name="Amazon CloudFront + Origin Access Control — the demo site",
        kind="service",
        pattern=r"aws_cloudfront|CloudFront|origin_access_control",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "one distribution with two OACs is written, nothing is deployed, and — the "
            "part that is not a schedule problem — THIS ACCOUNT CANNOT CREATE ONE. A real "
            "terraform apply returned, verbatim: 'Error: creating CloudFront "
            "Distribution: StatusCode: 403, RequestID: "
            "3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied: Your account must be "
            "verified before you can add new CloudFront resources.' It reproduces from a "
            "bare `aws cloudfront create-distribution` with no Terraform involved, and the "
            "identity holds AdministratorAccess, so it is an account-level verification "
            "hold only AWS Support can lift — not a permissions bug and not something this "
            "repository can fix. CloudFront is therefore EXCLUDED from the committed plan: "
            "enable_cloudfront is false in evidence/deploy/terraform-plan-furl.json and no "
            "aws_cloudfront_* resource appears among its 11 planned additions. The "
            "transcript is at infra/modules/demo-api/main.tf:22 and docs/deploy/RUNBOOK.md"
        ),
        how=(
            "AS DESIGNED, and the design is on hold: a single distribution fronts the "
            "static console from a private S3 origin and the /v1/* Lambda Function URL, so "
            "a judge sees one origin and the bucket is never public. Origin Access Control "
            "(not the legacy OAI) signs both origins, which is what would let the Function "
            "URL keep AWS_IAM auth instead of NONE. With the verification hold in place "
            "there is no distribution, therefore no principal to grant "
            "lambda:InvokeFunctionUrl to, therefore the Function URL is public — which is "
            "why the aws_lambda row above reads NONE. One AWS account setting propagates "
            "into the security posture of a second service, and both rows say so rather "
            "than one of them quietly describing the plan that was abandoned."
        ),
        # Re-pointed 2026-08-12: main.tf:263 was a bare `}` inside an S3 lifecycle rule.
        anchor="infra/modules/demo-site/main.tf:299",
        anchor_must_contain="aws_cloudfront_distribution",
    ),
    Row(
        key="aws_cloudwatch",
        name="Amazon CloudWatch — logs, four alarms, one dashboard",
        kind="service",
        pattern=r"aws_cloudwatch|CloudWatch",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "METRICS READ, NOTHING PROVISIONED — and the second half of that sentence is "
            "the load-bearing half. "
            "evidence/aws/cloudwatch/bedrock-metrics.json#/payload/api_call_summary/"
            "GetMetricStatistics = 110 read-only calls against the AWS/Bedrock namespace in "
            "ap-southeast-2 recorded, for amazon.titan-embed-text-v2:0, "
            "evidence/aws/cloudwatch/bedrock-metrics.json#/payload/models/"
            "amazon.titan-embed-text-v2:0/sums/Invocations/value = 7542 and "
            "evidence/aws/cloudwatch/bedrock-metrics.json#/payload/models/"
            "amazon.titan-embed-text-v2:0/sums/InputTokenCount/value = 1026175 — each Sum "
            "taken at Period 300 and at 3600 and required to agree, because a Sum is "
            "resolution-invariant and a disagreement would mean a clipped bucket. "
            "evidence/aws/cloudwatch/reconciliation.json subtracts this repository's own "
            "token ledgers from AWS's counters and names every non-zero delta. NOTHING WAS "
            "PROVISIONED: no log group, alarm, dashboard, metric filter, IAM role or "
            "terraform apply, and the reader invoked no model — bedrock-metrics.json's "
            "prohibitions block asserts each of those false and cloudwatch_evidence.py's "
            "before-call guard raises for any operation outside its six-item read-only "
            "allow-list before the request is signed. The alarms and dashboard WRITTEN in "
            "infra/modules/demo-api remain unapplied and unexercised"
        ),
        how=(
            "A log group with a finite retention — an unbounded retention on a demo account is "
            "a cost bug, not a safety feature — plus four metric alarms and a dashboard that "
            "makes the demo's latency and error rate visible to a judge who wants to look."
        ),
        # Retargeted 2026-08-11 with the verdict. An EXERCISED row whose anchor points at
        # unapplied Terraform sends a judge to the half that did NOT run. `_guard` is the
        # line that makes "metrics read, nothing provisioned" mechanical rather than a
        # promise: it raises before an out-of-list request is signed. The alarms and the
        # dashboard are still described in `how`; after the 2026-08-13 deploy-safety wave
        # they start at infra/modules/demo-api/main.tf:456 (errors) and :627 (dashboard).
        # Re-pointed 2026-08-12: :248 had slid onto a fragment of an unrelated docstring
        # string literal. :299 is `def _guard`, the function this row's whole verdict
        # phrase rests on.
        anchor="scripts/aws/cloudwatch_evidence.py:299",
        anchor_must_contain="def _guard",
    ),
    Row(
        key="aws_iam",
        name="AWS IAM — deny-first policy documents",
        kind="service",
        pattern=r"aws_iam_|iam:PassRole|assume_role_policy",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "eleven aws_iam_policy_document data sources exist across infra/; the Rego suite "
            "asserts the deny statements against plan fixtures, offline"
        ),
        how=(
            "The interesting IAM here is what is DENIED. The evidence-store bucket policy "
            "denies the writer s3:DeleteObjectVersion and denies PutObjectRetention without a "
            "bounded retention date, so the identity that appends checkpoints cannot shorten "
            "or remove them. infra/policy/custody/*.rego asserts each denial against a "
            "compliant plan and a family of deliberately broken ones."
        ),
        anchor="infra/modules/evidence-store/main.tf:145",
        anchor_must_contain="aws_iam_policy_document",
    ),
    Row(
        key="aws_ssm_parameter_store",
        name="AWS Systems Manager Parameter Store — the DSN",
        kind="service",
        pattern=r"ssm:GetParameter|aws_ssm_",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "granted in the Lambda execution role and NOTHING DEPLOYED — no parameter has "
            "been written and no role exists. The grant is in the committed plan "
            "(aws_iam_role_policy.dsn_access, one of the 11 additions in "
            "evidence/deploy/terraform-plan-furl.txt) and a plan is not an apply, so this "
            "row stays DESIGNED"
        ),
        how=(
            "The CockroachDB Cloud DSN is a SecureString parameter, not a Lambda environment "
            "variable, so the connection string never appears in the function configuration "
            "that anyone with lambda:GetFunction can read. The role's grant is scoped to "
            "exactly one parameter ARN."
        ),
        # Re-pointed 2026-08-12: main.tf:146 was a bare `})` closing a locals block.
        # Re-pointed 2026-08-13: the deploy-safety wave rewrote this module and :192 slid
        # onto a bare `}`. :215 is `actions = ["ssm:GetParameter"]`, the grant itself.
        anchor="infra/modules/demo-api/main.tf:215",
        anchor_must_contain="ssm:GetParameter",
    ),
    Row(
        key="aws_eventbridge",
        name="Amazon EventBridge — scheduled patrol and steward runs",
        kind="service",
        pattern=r"EventBridge|aws_cloudwatch_event|events:PutEvents|event_bus",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "named in the steward schedule design and its runbooks, and there is NO "
            "aws_cloudwatch_event_* resource anywhere under infra/ — the schedule is a "
            "container entrypoint today, not an EventBridge rule"
        ),
        how=(
            "The custody patrol and the steward's periodic sweeps are described as scheduled "
            "invocations. Stated as DESIGNED rather than used: the schedule currently lives in "
            "verticals/mainline/apps/steward/schedules.yaml and its entrypoint, and no "
            "Terraform in this tree creates a rule or a bus."
        ),
        anchor="verticals/mainline/apps/steward/schedules.yaml:14",
        anchor_must_contain="EventBridge",
    ),
)


# --------------------------------------------------------------------------------------
# Counting
# --------------------------------------------------------------------------------------


def resolve_anchor(anchor: str, root: Path, expect: str = "") -> dict[str, Any]:
    """Resolve ``path:line`` against the tree, quote the line, and check its subject.

    The quoted text is the point. ``docs/TOOL-USAGE.md`` tells a judge to look at a file
    and a line; if the file is later reorganised, the citation silently starts pointing at
    a blank line or a closing brace and the document becomes confidently wrong. Quoting
    the line into the evidence file makes that rot visible in a diff.

    *Resolving is the weaker half of the check and was, for a while, the only half.* A
    citation onto line 257 of a 500-line Terraform module resolves whatever line 257 has
    become. So ``expect`` — the row's :attr:`Row.anchor_must_contain` — is matched against
    the line text case-insensitively, and :func:`main` refuses to write when it is absent.
    ``subject_holds`` is what a reader should look at; ``resolves`` only says the file was
    long enough.
    """
    path_part, _, line_part = anchor.rpartition(":")
    if path_part and line_part.isdigit():
        relpath, lineno = path_part, int(line_part)
    else:
        relpath, lineno = anchor, None

    def miss(**kw: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "path": relpath,
            "line": lineno,
            "resolves": False,
            "line_text": None,
            "must_contain": expect,
            "subject_holds": False,
        }
        base.update(kw)
        return base

    target = root / relpath
    if not target.is_file():
        return miss()
    if lineno is None:
        # A whole-file anchor cannot be checked line-wise; it carries no subject claim.
        return miss(resolves=True, subject_holds=not expect)

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 1 <= lineno <= len(lines):
        return miss()
    text = lines[lineno - 1].strip()
    return {
        "path": relpath,
        "line": lineno,
        "resolves": True,
        "line_text": text,
        "must_contain": expect,
        "subject_holds": (expect.lower() in text.lower()) if expect else True,
    }


def measure(row: Row, scan: Scan) -> dict[str, Any]:
    """Count the files matching ``row`` and pick three representative paths."""
    pattern = row.compiled()
    matched: list[ScannedFile] = []
    for f in scan.files:
        if row.scope and not f.relpath.startswith(row.scope):
            continue
        if pattern.search(f.text):
            matched.append(f)

    by_category: dict[str, int] = {}
    for f in matched:
        by_category[f.category] = by_category.get(f.category, 0) + 1

    rank = {name: i for i, name in enumerate(CATEGORY_ORDER)}
    representative = [
        f.relpath
        for f in sorted(matched, key=lambda f: (rank.get(f.category, len(rank)), f.relpath))[:3]
    ]

    if row.verdict not in VERDICTS:  # pragma: no cover - guarded by test below
        raise ValueError(f"{row.key}: verdict {row.verdict!r} not in {VERDICTS}")

    return {
        "key": row.key,
        "name": row.name,
        "kind": row.kind,
        "verdict": row.verdict,
        "verdict_basis": row.verdict_basis,
        "how": row.how,
        "anchor": row.anchor,
        "anchor_resolved": resolve_anchor(row.anchor, scan.root, row.anchor_must_contain),
        "file_count": len(matched),
        "files_by_category": {k: by_category[k] for k in sorted(by_category)},
        "representative_paths": representative,
        "search": {
            "pattern": row.pattern,
            "case_sensitive": row.case_sensitive,
            "scope": row.scope or "<repository root>",
        },
    }


def build(scan: Scan, rows: Sequence[Row], subject: str, note: str) -> dict[str, Any]:
    """Assemble one census document. Deliberately carries no timestamp."""
    measured = [measure(row, scan) for row in rows]
    tally: dict[str, int] = dict.fromkeys(VERDICTS, 0)
    kinds: dict[str, int] = {"tool": 0, "feature": 0, "service": 0}
    for m in measured:
        tally[m["verdict"]] += 1
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    return {
        "artefact": f"MAINLINE {subject} census",
        "subject": subject,
        "generated_by": "scripts/submission/capture_tool_evidence.py",
        "note": note,
        "verdict_meanings": {
            "EXERCISED": (
                "it ran, and a committed artefact or a check in this repository records the result"
            ),
            "DESIGNED": (
                "the code or configuration is complete and on disk; nothing recorded has run "
                "it end to end"
            ),
            "NOT-AVAILABLE": ("checked on this platform and absent; no dependency was taken on it"),
        },
        "scan": {
            "root": "<repository root>",
            "method": (
                "filesystem walk, NOT the git index. A count here will not equal `git grep "
                "-l <pattern> | wc -l`: the walk sees files that are present but not yet "
                "committed, and it prunes directories git tracks (out_mainline/, "
                "out_trappoint_ref/, .hypothesis-corpus/). The walk is the right unit for a "
                "submission document, because a judge checks out a working tree."
            ),
            "files_scanned": len(scan.files),
            "files_by_category": scan.counts_by_category,
            "skipped_binary": scan.skipped_binary,
            "skipped_too_large": scan.skipped_large,
            "skipped_unreadable": scan.skipped_unreadable,
            "excluded_dir_names": sorted(EXCLUDED_DIR_NAMES),
            "excluded_relpaths": list(EXCLUDED_RELPATHS),
            "max_file_bytes": MAX_FILE_BYTES,
            "category_order": list(CATEGORY_ORDER),
        },
        "totals": {
            "rows": len(measured),
            "by_verdict": tally,
            # `by_kind.tool` is the number the hackathon rule actually asks about — the bar
            # is "at least two CockroachDB tools". Separating it from `rows` keeps the
            # engine features from being counted as tools to inflate the answer.
            "by_kind": kinds,
        },
        # Keyed by `key`, not a list. docs/TOOL-USAGE.md cites these in the
        # `[src: file#path.to.value]` style docs/HONESTY.md established, and a citation
        # into a list would have to say "the fifth element", which silently retargets the
        # moment a row is inserted above it. JSON objects preserve insertion order, so the
        # reading order below is still the authored order.
        "rows": {m["key"]: m for m in measured},
    }


def render(document: dict[str, Any]) -> str:
    """One canonical serialisation, so a re-run either matches byte-for-byte or does not."""
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


LICENSE_SIDECAR: Final = (
    "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: CC-BY-4.0\n"
)


#: ``docs/TOOL-USAGE.md`` writes every count as ``<number> [src: <file>#<dotted.path>]``.
#: This is the convention ``docs/HONESTY.md`` established, and it is only worth anything if
#: something resolves it.
DOC_CITATION: Final = re.compile(r"(\d+)\s*\[src:\s*(evidence/tool-usage/[^\]\s]+)\]")

#: The document those citations live in. Named here rather than passed in, because a
#: check that can be pointed at a different file is a check that can be pointed away.
CITING_DOC: Final = "docs/TOOL-USAGE.md"


def _dotted(document: dict[str, Any], path: str) -> Any:
    """Resolve ``rows.aws_lambda.file_count`` against a census document."""
    cur: Any = document
    for token in path.split("."):
        if not isinstance(cur, dict) or token not in cur:
            return None
        cur = cur[token]
    return cur


def check_doc_citations(root: Path, documents: dict[str, dict[str, Any]]) -> list[str]:
    """Every ``N [src: evidence/tool-usage/…]`` in the citing document must equal ``N``.

    **Why this belongs in the same program that writes the census.** The two JSON files are
    a pure function of a tree that ten people edit at once, so a count moves whenever
    somebody adds a file that happens to match a pattern — no edit to the prose required,
    no diff on the document, and the sentence is now false. Regenerating the census used to
    *silence* that: the artefacts became fresh, ``--check`` went green, and the document
    they exist to support kept quoting yesterday's number. Freshness of the evidence and
    truth of the claim are different properties and only one of them was being tested.

    Returns a list of human-readable disagreements; empty means every citation resolves and
    agrees.
    """
    target = root / CITING_DOC
    if not target.is_file():
        return [f"{CITING_DOC}: missing, but the census exists to support it"]

    problems: list[str] = []
    for match in DOC_CITATION.finditer(target.read_text(encoding="utf-8")):
        claimed, ref = int(match.group(1)), match.group(2)
        filename, _, pointer = ref.partition("#")
        document = documents.get(Path(filename).name)
        if document is None:
            problems.append(f"{ref}: names no census this program writes")
            continue
        found = _dotted(document, pointer)
        if found is None:
            problems.append(f"{ref}: does not resolve in the census")
        elif found != claimed:
            problems.append(f"{ref}: {CITING_DOC} says {claimed}, the census says {found}")
    return problems


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def audit_anchors(
    documents: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Split every row's anchor into ``(dangling, drifted)`` complaints.

    Two failure modes, and the second is the one that actually happened in this
    repository: an anchor that no longer *resolves*, and an anchor that resolves perfectly
    onto a line that has nothing to do with the row. Only the first was ever checked.
    """
    dangling: list[str] = []
    drifted: list[str] = []
    for doc in documents.values():
        for row in doc["rows"].values():
            got = row["anchor_resolved"]
            where = f"{doc['subject']}: {row['key']} -> {row['anchor']}"
            if not got["resolves"]:
                dangling.append(where)
            elif not got["subject_holds"]:
                drifted.append(
                    f"{where}\n"
                    f"      expected the line to contain: {got['must_contain']!r}\n"
                    f"      the line actually reads:      {got['line_text']!r}"
                )
    return dangling, drifted


def stale_report(root: Path, out_dir: Path, documents: dict[str, dict[str, Any]]) -> list[str]:
    """Compare each committed census against a fresh one and describe any difference.

    The description matters as much as the verdict. Reporting *"30770 bytes on disk vs
    30770 bytes fresh"* — which is what a pure length comparison produces when one count
    goes ``64 -> 65`` while another goes ``23 -> 22``, and that happens routinely on a tree
    several people are editing — reads like a bug in the checker and sends the reader
    hunting for one. When the lengths agree, name the line that actually differs.
    """
    stale: list[str] = []
    for name, doc in documents.items():
        target = out_dir / name
        rel_name = target.relative_to(root).as_posix()
        fresh = render(doc)
        if not target.exists():
            stale.append(f"{rel_name}: missing")
            continue
        current = target.read_text(encoding="utf-8")
        if current == fresh:
            continue
        if len(current) != len(fresh):
            stale.append(f"{rel_name}: {len(current)} bytes on disk vs {len(fresh)} bytes fresh")
            continue
        on_disk, computed = current.splitlines(), fresh.splitlines()
        where = next(
            (i for i, (a, b) in enumerate(zip(on_disk, computed, strict=False), start=1) if a != b),
            0,
        )
        stale.append(
            f"{rel_name}: same length ({len(fresh)} bytes), different content; "
            f"first difference at line {where}:\n"
            f"      on disk: {on_disk[where - 1].strip()[:96]}\n"
            f"      fresh:   {computed[where - 1].strip()[:96]}"
        )
    return stale


def run_check(
    root: Path,
    out_dir: Path,
    documents: dict[str, dict[str, Any]],
    files_scanned: int,
) -> int:
    """``--check``: the committed census must be fresh AND the document must agree with it.

    Two questions, and both have to be asked. Freshness alone was the whole test until
    2026-08-12, and it has a blind spot big enough to drive a submission through:
    regenerating the artefacts makes ``--check`` green without touching a word of the prose
    those artefacts exist to support. A fresh census under a stale sentence is a *worse*
    state than a stale census, because the gate now certifies it.
    """
    stale = stale_report(root, out_dir, documents)
    if stale:
        sys.stderr.write("tool-usage census is STALE:\n")
        for line in stale:
            sys.stderr.write(f"  {line}\n")
        sys.stderr.write("  run: python scripts/submission/capture_tool_evidence.py\n")
        return 1

    disagreements = check_doc_citations(root, documents)
    if disagreements:
        sys.stderr.write(f"{CITING_DOC} quotes numbers the census does not agree with:\n")
        for line in disagreements:
            sys.stderr.write(f"  {line}\n")
        sys.stderr.write(
            "  The census is fresh; the prose is not. Edit the number in the document\n"
            "  to match the artefact it cites - never the other way round.\n"
        )
        return 1

    cited = sum(1 for _ in DOC_CITATION.finditer((root / CITING_DOC).read_text("utf-8")))
    sys.stdout.write(
        f"tool-usage census is current ({files_scanned} files scanned) and all "
        f"{cited} {CITING_DOC} citations agree with it\n"
    )
    return 0


def _force_utf8_streams() -> None:
    """Make stdout/stderr UTF-8 capable before anything is written to them.

    MEASURED BUG, 2026-08-12. ``--print`` — a command ``docs/TOOL-USAGE.md`` Part 5 tells a
    reader to run — died on Windows with::

        UnicodeEncodeError: 'charmap' codec can't encode character '\\u2264'

    because the default console encoding is cp1252 and the census prose contains ``≤`` and
    ``—``. The program that exists to make this document checkable was not runnable by a
    judge on the most common desktop platform, and it failed *after* printing a header, so
    it looked like a partial success. ``errors="replace"`` is deliberately NOT used: a
    census with mangled characters is a census a reader cannot compare byte-for-byte
    against the committed file, which is the one property the whole design rests on.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # pragma: no cover - detached / redirected-to-null streams cannot reconfigure
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="capture_tool_evidence.py",
        description=(
            "Re-derive evidence/tool-usage/crdb-features.json and aws-services.json from the "
            "source tree. Standard library only, no network, no credential."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if the committed files differ from a fresh census",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="write the census to stdout and touch no file",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root (default: two levels above this script)",
    )
    args = parser.parse_args(argv)

    root = (args.root or repo_root()).resolve()
    scan = scan_tree(root)

    documents = {
        "crdb-features.json": build(
            scan,
            CRDB_ROWS,
            "CockroachDB tool and feature",
            note=(
                "file_count is the number of scanned files whose text matches `search.pattern` "
                "— it counts where a feature is used AND where it is discussed, which is why "
                "every row also carries an `anchor` naming one hand-checked occurrence. The "
                "scan excludes this census's own output and docs/TOOL-USAGE.md, so writing the "
                "document cannot inflate the numbers the document cites."
            ),
        ),
        "aws-services.json": build(
            scan,
            AWS_ROWS,
            "AWS service",
            note=(
                "No AWS account identifier appears in this file, by construction: the census "
                "reads the tree and writes counts, never credentials or account numbers. "
                "DESIGNED dominates on purpose — most of this infrastructure is written and "
                "unapplied, and saying so is the point of the verdict column."
            ),
        ),
    }

    # A dangling citation is a defect, not a warning. docs/TOOL-USAGE.md sends a judge to
    # every one of these anchors, so the census refuses to produce evidence it knows is
    # already wrong. Two failure modes, and the second is the one that actually happened:
    # an anchor that no longer resolves, and an anchor that resolves onto the wrong line.
    dangling, drifted = audit_anchors(documents)
    if dangling or drifted:
        if dangling:
            sys.stderr.write("REFUSING: anchor does not resolve\n")
            for line in dangling:
                sys.stderr.write(f"  {line}\n")
        if drifted:
            sys.stderr.write(
                "REFUSING: anchor resolves but has drifted off its subject.\n"
                "  A citation onto a closing brace is worse than no citation: it sends a\n"
                "  reader somewhere and tells them nothing. Re-point the anchor, or change\n"
                "  anchor_must_contain if the row's subject genuinely moved.\n"
            )
            for line in drifted:
                sys.stderr.write(f"  {line}\n")
        return 2

    out_dir = root / "evidence" / "tool-usage"

    if args.print_only:
        for name, doc in documents.items():
            sys.stdout.write(f"===== {name} =====\n")
            sys.stdout.write(render(doc))
        return 0

    if args.check:
        return run_check(root, out_dir, documents, len(scan.files))

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, doc in documents.items():
        target = out_dir / name
        target.write_text(render(doc), encoding="utf-8")
        (out_dir / f"{name}.license").write_text(LICENSE_SIDECAR, encoding="utf-8")
        sys.stdout.write(
            f"wrote {target.relative_to(root).as_posix()} "
            f"({doc['totals']['rows']} rows, "
            f"{doc['totals']['by_verdict']['EXERCISED']} EXERCISED / "
            f"{doc['totals']['by_verdict']['DESIGNED']} DESIGNED / "
            f"{doc['totals']['by_verdict']['NOT-AVAILABLE']} NOT-AVAILABLE)\n"
        )
    sys.stdout.write(f"scanned {len(scan.files)} files under {root.as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
