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
    ),
    Row(
        key="crdb_as_of_system_time",
        name="AS OF SYSTEM TIME (bounded time travel, and its refusal)",
        kind="feature",
        pattern=r"AS OF SYSTEM TIME",
        case_sensitive=False,
        verdict="EXERCISED",
        verdict_basis=(
            "measured on the pinned local node: AS OF SYSTEM TIME '-90m' over system.namespace "
            "returned 3658 rows, while '-2160h' (90 days) was REFUSED with XXUUU 'found no "
            "descriptor'; ALTER DATABASE ... CONFIGURE ZONE pinned gc.ttlseconds to 4500 and "
            "SHOW ZONE CONFIGURATION read it back. What that pair demonstrates is that a "
            "far-past read is refused rather than answered — not the 4500 s boundary "
            "specifically, which is the conformance case CF-46 and has not been demonstrated"
        ),
        how=(
            "Used for consistent read-only snapshots — and, more importantly, used to mark "
            "the boundary of what it can prove. gc.ttlseconds is pinned locally to the Cloud "
            "value of 4500 s, so a query past the window is REFUSED rather than silently "
            "wrong, and long-horizon history is the application-level commit DAG instead."
        ),
        anchor="packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106",
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
    ),
    Row(
        key="crdb_internal",
        name="crdb_internal (used by us, forbidden to the audit identity)",
        kind="feature",
        pattern=r"crdb_internal",
        case_sensitive=True,
        verdict="EXERCISED",
        verdict_basis=(
            "measured on the pinned local node: the bare builtin cluster_logical_timestamp() "
            "returns, while crdb_internal is RESTRICTED BY DEFAULT on v26.2.5 — "
            "'SELECT count(*) FROM crdb_internal.tables' raises 42501 'Access to "
            "crdb_internal and system is restricted' and only succeeds after "
            "SET allow_unsafe_internals = true"
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
    ),
    Row(
        key="crdb_changefeed",
        name="CHANGEFEED (CDC out of the outbox)",
        kind="feature",
        pattern=r"CREATE CHANGEFEED",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "measured on the pinned local node: the machinery is present — "
            "kv.rangefeed.enabled is true and SHOW CHANGEFEED JOBS answers — and it reports "
            "0 jobs, because no changefeed has ever been created on any cluster in this "
            "project"
        ),
        how=(
            "CDC is deliberately NOT in a migration — CREATE CHANGEFEED in a migration makes "
            "migrations non-idempotent across a restore — so it is owned by the provisioning "
            "agent, and 0155a/0168 exist to observe changefeed health rather than to start "
            "one. RLS is never enabled on the outbox because CDC queries fail on RLS-enabled "
            "and multi-family tables."
        ),
        anchor="verticals/mainline/db/migrations/0168_v_changefeed_health.sql:37",
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
    ),
    Row(
        key="crdb_managed_mcp",
        name="CockroachDB Managed MCP Server (cockroachlabs.cloud/mcp)",
        kind="tool",
        pattern=r"cockroachlabs\.cloud/mcp|mcp-cluster-id|mainline_audit",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "packages/mainline-mcp implements the transport and the limits and its offline "
            "tests pass, but no live session against the managed endpoint is captured in "
            "evidence/; tests/integration/mcp skips with a reason when no key is present"
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
    ),
)


AWS_ROWS: Final[tuple[Row, ...]] = (
    Row(
        key="aws_bedrock_runtime",
        name="Amazon Bedrock — Claude inference via au.* profiles",
        kind="service",
        pattern=r"bedrock",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "eight au.* Claude inference profiles are listed live in region ap-southeast-2, "
            "but every agent test in this repository replays a recorded cassette; no live "
            "model call is captured under evidence/, and docs/HONESTY.md says so"
        ),
        how=(
            "bedrock-runtime InvokeModel with the Anthropic native body. The modelId is an "
            "au.* inference-profile ARN RESOLVED AT START-UP from ListInferenceProfiles and "
            "pinned into the run record — never hard-coded — and any identifier without the "
            "au. prefix is refused by the transport as a residency violation. One model "
            "generation across the fleet, differentiated by effort rather than by model."
        ),
        anchor="packages/mainline-agentkit/src/mainline_agentkit/transport.py:273",
    ),
    Row(
        key="aws_bedrock_embeddings",
        name="Amazon Bedrock — embeddings (Titan v2, Cohere embed v4)",
        kind="service",
        pattern=r"titan-embed-text-v2|cohere\.embed-v4|titan_embed|BedrockTitan",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "amazon.titan-embed-text-v2:0 and cohere.embed-v4:0 are both available in "
            "ap-southeast-2 and the provider is implemented; the committed embeddings are "
            "fixtures, so Tier-2 verification needs no model call at all"
        ),
        how=(
            "The embedding provider writes into the C-SPANN sidecar tables. Model ids are "
            "never hard-coded at a call site — tests/unit/recall_providers/"
            "test_no_hardcoded_model_ids.py enforces that — and every embedding row stores "
            "its embed_model and index_gen, because a vector whose model is unknown cannot "
            "be compared to anything."
        ),
        anchor=(
            "verticals/mainline/packages/mainline-recall-agent/src/"
            "mainline_recall_agent/providers/bedrock_titan.py:39"
        ),
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
            "Bedrock Rerank is not offered in ap-southeast-2; docs/HONESTY.md records it as "
            "absent and confirms no dependency was taken on it"
        ),
        how=(
            "NOT USED, and named here because a services list that omits what you checked and "
            "could not have is a list you cannot audit. Listwise reranking is done by the "
            "Claude profile at high effort instead, and CockroachDB's own "
            "vector_search_rerank_multiplier session variable (observed at 50) governs the "
            "ANN side. The design assumed Rerank's absence before it was checked."
        ),
        anchor="docs/HONESTY.md:276",
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
    ),
    Row(
        key="aws_lambda",
        name="AWS Lambda — the /v1/* demo API",
        kind="service",
        pattern=r"aws_lambda|lambda_function|LambdaFunctionURL",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "the module is complete (python3.13, IAM-only Function URL, four alarms) and "
            "nothing is deployed: the repository has no demo URL as of this census"
        ),
        how=(
            "One python3.13 function behind a Function URL whose authorization_type is "
            "AWS_IAM — never NONE — invoked only by CloudFront with an OAC signature. It runs "
            "in ap-southeast-1 beside the Cloud cluster, because the same call from "
            "ap-southeast-2 pays about 90 ms each way and the gate screen makes six of them. "
            "Its execution role's entire non-managed grant is ssm:GetParameter on one "
            "parameter plus a conditioned kms:Decrypt."
        ),
        anchor="infra/modules/demo-api/main.tf:257",
    ),
    Row(
        key="aws_cloudfront",
        name="Amazon CloudFront + Origin Access Control — the demo site",
        kind="service",
        pattern=r"aws_cloudfront|CloudFront|origin_access_control",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis=(
            "one distribution with two OACs is written; nothing is deployed and the "
            "submission's demo URL is unresolved"
        ),
        how=(
            "A single distribution fronts the static console from a private S3 origin and "
            "the /v1/* Lambda Function URL, so the judge sees one origin and the bucket is "
            "never public. Origin Access Control (not the legacy OAI) signs both origins, "
            "which is what lets the Function URL keep AWS_IAM auth instead of NONE."
        ),
        anchor="infra/modules/demo-site/main.tf:263",
    ),
    Row(
        key="aws_cloudwatch",
        name="Amazon CloudWatch — logs, four alarms, one dashboard",
        kind="service",
        pattern=r"aws_cloudwatch|CloudWatch",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis="written in infra/modules/demo-api; nothing deployed, so no metric exists",
        how=(
            "A log group with a finite retention — an unbounded retention on a demo account is "
            "a cost bug, not a safety feature — plus four metric alarms and a dashboard that "
            "makes the demo's latency and error rate visible to a judge who wants to look."
        ),
        anchor="infra/modules/demo-api/main.tf:391",
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
    ),
    Row(
        key="aws_ssm_parameter_store",
        name="AWS Systems Manager Parameter Store — the DSN",
        kind="service",
        pattern=r"ssm:GetParameter|aws_ssm_",
        case_sensitive=False,
        verdict="DESIGNED",
        verdict_basis="granted in the Lambda execution role; nothing deployed",
        how=(
            "The CockroachDB Cloud DSN is a SecureString parameter, not a Lambda environment "
            "variable, so the connection string never appears in the function configuration "
            "that anyone with lambda:GetFunction can read. The role's grant is scoped to "
            "exactly one parameter ARN."
        ),
        anchor="infra/modules/demo-api/main.tf:146",
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
    ),
)


# --------------------------------------------------------------------------------------
# Counting
# --------------------------------------------------------------------------------------


def resolve_anchor(anchor: str, root: Path) -> dict[str, Any]:
    """Resolve ``path:line`` against the tree and quote the line it lands on.

    The quoted text is the point. ``docs/TOOL-USAGE.md`` tells a judge to look at a file
    and a line; if the file is later reorganised, the citation silently starts pointing at
    a blank line or a closing brace and the document becomes confidently wrong. Quoting
    the line into the evidence file makes that rot visible in a diff, and
    :func:`main` refuses to write when an anchor no longer resolves at all.
    """
    path_part, _, line_part = anchor.rpartition(":")
    if path_part and line_part.isdigit():
        relpath, lineno = path_part, int(line_part)
    else:
        relpath, lineno = anchor, None

    target = root / relpath
    if not target.is_file():
        return {"path": relpath, "line": lineno, "resolves": False, "line_text": None}
    if lineno is None:
        return {"path": relpath, "line": None, "resolves": True, "line_text": None}

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 1 <= lineno <= len(lines):
        return {"path": relpath, "line": lineno, "resolves": False, "line_text": None}
    return {
        "path": relpath,
        "line": lineno,
        "resolves": True,
        "line_text": lines[lineno - 1].strip(),
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
        "anchor_resolved": resolve_anchor(row.anchor, scan.root),
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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
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
    # already wrong.
    dangling = [
        f"{doc['subject']}: {r['key']} -> {r['anchor']}"
        for doc in documents.values()
        for r in doc["rows"].values()
        if not r["anchor_resolved"]["resolves"]
    ]
    if dangling:
        sys.stderr.write("REFUSING: anchor does not resolve\n")
        for line in dangling:
            sys.stderr.write(f"  {line}\n")
        return 2

    out_dir = root / "evidence" / "tool-usage"

    if args.print_only:
        for name, doc in documents.items():
            sys.stdout.write(f"===== {name} =====\n")
            sys.stdout.write(render(doc))
        return 0

    if args.check:
        stale: list[str] = []
        for name, doc in documents.items():
            target = out_dir / name
            fresh = render(doc)
            if not target.exists():
                stale.append(f"{target.relative_to(root).as_posix()}: missing")
                continue
            current = target.read_text(encoding="utf-8")
            if current != fresh:
                stale.append(
                    f"{target.relative_to(root).as_posix()}: "
                    f"{len(current)} bytes on disk vs {len(fresh)} bytes fresh"
                )
        if stale:
            sys.stderr.write("tool-usage census is STALE:\n")
            for line in stale:
                sys.stderr.write(f"  {line}\n")
            sys.stderr.write("  run: python scripts/submission/capture_tool_evidence.py\n")
            return 1
        sys.stdout.write(f"tool-usage census is current ({len(scan.files)} files scanned)\n")
        return 0

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
