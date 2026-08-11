# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The cluster, the schema, the seeded history, and a validator for the console's contracts.

FOUR THINGS THIS FILE PROVIDES, AND THE REASON EACH IS SHAPED THE WAY IT IS.

**1. A shared cluster, obtained the way the rest of the repository obtains one.**
``packages/trappoint-testkit`` publishes the session's DSN under four environment names
and skips with a written reason when there is none. This file reads those names and then
``127.0.0.1:26257``, and it never starts a container of its own — ``--crdb=reuse`` is the
convention, and thirteen private nodes is what happens when a module decides it is
special. **Every skip carries the reason it skipped.** A skip with no reason is
indistinguishable from a deleted test, which is the failure mode that lets a suite go
green while asserting nothing.

**2. A migrated database, cached by the fingerprint of the migration tree.**
Applying 271 files takes 46.7 s on this machine, which is fine once and intolerable per
run. The database is named for the SHA-256 of every migration's name and bytes, so a
second run reuses it and a single edited migration builds a new one. The marker table
``w3_fixture.ready`` carries the fingerprint AND the seeded identifiers, so a reused
database hands back the same permit id it was seeded with rather than being re-seeded.

**3. A seeded history that exercises all twelve resources.** Not the minimum for one
claim — the minimum for twelve reads, which is a different and larger thing: two events
with an edge between them, a two-checkpoint ledger with four leaves so the RFC 6962
consistency proof has something to prove, a signed disposition, a change request, and a
silence receipt whose ``boundary_proof`` actually has the shape the contract demands.

**4. A JSON Schema validator, over the contract files the CONSOLE loads.**
``jsonschema`` is not installed in this repository's virtualenv and installing it would
change shared state no worker owns. So the subset of draft 2020-12 that
``console/contracts/*.schema.json`` actually uses is implemented here — twenty-four
keywords, enumerated by walking the sixteen documents — and it reads the very files
``src/data/schema.ts`` reads. Validating against a re-typed copy would be testing the
copy.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
import uuid
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Final
from urllib.parse import urldefrag, urljoin

import pytest

# The distribution is not installed — `verticals/*/apps/*` is deliberately absent from
# the root workspace's member globs, because the console beside it is a pnpm workspace
# and mixing a TypeScript SPA into `uv.lock` would make the Python resolution depend on
# a toolchain that has nothing to do with it. So `src` goes on the path here rather than
# into the shared virtualenv, which no worker owns.
_TESTS = Path(__file__).resolve().parent
_SRC = _TESTS.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402


def _repo_root(start: Path) -> Path:
    """The workspace root: the nearest ancestor holding both ``spec/`` and ``compose.yaml``."""
    for candidate in (start, *start.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise RuntimeError(f"no workspace root above {start}")


REPO_ROOT: Final = _repo_root(_TESTS)
CONTRACTS_DIR: Final = REPO_ROOT / "verticals/mainline/apps/console/contracts"
MIGRATIONS_DIR: Final = REPO_ROOT / "verticals/mainline/db/migrations"
RESOURCES_TS: Final = REPO_ROOT / "verticals/mainline/apps/console/src/data/resources.ts"

#: The four names ``trappoint_testkit.cluster`` publishes a shared DSN under.
_DSN_ENV_NAMES: Final = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN")

#: Cloud runs ``gc.ttlseconds = 4500``; the local node defaults to 14400. Pinning the
#: stricter value locally means a `AS OF SYSTEM TIME` that works here works there.
_CLOUD_GC_TTL_SECONDS: Final = 4500

_ZERO32: Final = b"\x00" * 32


# ── The cluster ─────────────────────────────────────────────────────────────────────


def _candidate_dsns() -> list[tuple[str, str]]:
    import os

    found = [(name, os.environ[name]) for name in _DSN_ENV_NAMES if os.environ.get(name)]
    found.append(("default", "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"))
    return found


def _probe(dsn: str) -> str | None:
    try:
        with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
            row = conn.execute("SELECT version()").fetchone()
            return str(row[0]) if row else "unknown"
    except psycopg.Error:
        return None


def _testkit_state(config: pytest.Config) -> Any | None:
    """The ``trappoint-testkit`` plugin's decision for this session, or ``None``.

    The plugin resolves ``--crdb`` once in ``pytest_configure``, before collection, and
    stashes what it decided. Reading that stash is what makes ``--crdb=none`` mean
    something here: without it this module would probe ``127.0.0.1:26257`` directly and
    quietly use a node the session had explicitly declined to obtain — thirteen private
    containers is exactly the failure the convention exists to prevent, and a module that
    routes around the decision is the first of them.
    """
    try:
        from trappoint_testkit.plugin import STATE_KEY
    except ImportError:  # pragma: no cover - the plugin is a workspace dependency
        return None
    return config.stash.get(STATE_KEY, None)


@pytest.fixture(scope="session")
def admin_dsn(request: pytest.FixtureRequest) -> str:
    """A DSN for a CockroachDB this session may create databases in, or a skip that says why."""
    state = _testkit_state(request.config)
    if state is not None:
        if state.cluster is not None:
            return str(state.cluster.dsn)
        pytest.skip(
            "the session obtained no CockroachDB, so the twelve read resources cannot be "
            f"exercised against a real schema. trappoint-testkit says: {state.skip_reason}"
        )

    tried: list[str] = []
    for name, dsn in _candidate_dsns():
        if _probe(dsn) is not None:
            return dsn
        tried.append(f"{name}={dsn.split('@')[-1]}")
    pytest.skip(
        "trappoint-testkit is not loaded and no CockroachDB answered, so the twelve read "
        "resources cannot be exercised against a real schema. Tried, in order: "
        + ", ".join(tried)
        + ". Start the compose node (`docker compose up -d crdb`) or export MAINLINE_TEST_DSN. "
        "This session will NOT start a container of its own: the repository convention is "
        "--crdb=reuse and one shared node per session (packages/trappoint-testkit)."
    )


def _fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _dsn_for(admin: str, database: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(admin)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _apply_chain(dsn: str) -> tuple[int, list[str]]:
    """Bootstrap, then apply every migration in allocation order, each in its own transaction.

    Autocommit per file rather than one enclosing transaction: CockroachDB DDL inside a
    multi-statement transaction can fail at COMMIT even when every statement succeeded,
    so a shared transaction would retroactively un-apply files already counted.
    """
    from trappoint_migrate.bootstrap import bootstrap
    from trappoint_migrate.discovery import discover
    from trappoint_migrate.runner import DEFAULT_SCHEMA_PREFIXES, actor

    with psycopg.connect(dsn, autocommit=True) as conn:
        bootstrap(conn, applied_by=actor(), schema_prefixes=DEFAULT_SCHEMA_PREFIXES)

    applied = 0
    failures: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for migration in discover(MIGRATIONS_DIR):
            try:
                conn.execute(migration.path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            except psycopg.Error as exc:
                failures.append(
                    f"{migration.path.name} [{exc.sqlstate}] {str(exc).splitlines()[0][:120]}"
                )
            else:
                applied += 1
    return applied, failures


# ── The seeded history ──────────────────────────────────────────────────────────────


def _sha(*parts: bytes | str) -> bytes:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


def _jcs(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _mth(leaves: Sequence[bytes]) -> bytes:
    """RFC 6962 Merkle Tree Hash over already-hashed leaves — the fixture's own copy.

    Written out again here rather than imported from the module under test, so that the
    ledger fixture's checkpoint roots are not produced by the same code the test then
    checks the proofs against. A fixture that borrows the implementation it is testing
    proves the implementation is self-consistent and nothing else.
    """
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    split = 1 << (len(leaves) - 1).bit_length() - 1
    return hashlib.sha256(b"\x01" + _mth(leaves[:split]) + _mth(leaves[split:])).digest()


def _seed(conn: psycopg.Connection[Any]) -> dict[str, str]:
    """Insert the smallest history in which all twelve reads have something true to say."""
    site_id = uuid.uuid4()
    # `mainline.fn_recall_policy_anchored` compares ledger_checkpoint.site_code against
    # site_id::STRING, so the ledger partition key for a site is its own identifier.
    # A quirk of the shipped function, matched rather than worked around.
    site_code = str(site_id)
    site_role = "w3_site"
    signer, countersigner = "w3.signer", "w3.countersigner"
    signer_cred, cosign_cred = _sha("cred", "signer"), _sha("cred", "cosigner")
    commit_v1, commit_v2 = _sha("commit", "clause-v1"), _sha("commit", "clause-v2")
    clause_uuid, doc_id = uuid.uuid4(), uuid.uuid4()
    event_a, event_b = uuid.uuid4(), uuid.uuid4()
    permit_id, cr_id = uuid.uuid4(), uuid.uuid4()
    activity_root = "w3/isolation"
    competency = {"authorisations": ["ISOLATION_AUTHORITY"], "training": ["LOTO-3"], "source": "w3"}

    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (site_id, site_code, site_role, uuid.uuid4()),
    )
    for sub, org, rank in ((signer, "w3-operator", 5), (countersigner, "w3-assurer", 5)):
        conn.execute(
            "INSERT INTO mainline.person (signer_sub, effective_from, org, rank, "
            "competency_source_id, competency_sha256, competency_snapshot, identity_source, "
            "enrolment_assurance) VALUES (%s, now() - INTERVAL '30 days', %s, %s, %s, %s, %s, %s, "
            "%s)",
            (
                sub,
                org,
                rank,
                uuid.uuid4(),
                _sha("competency", sub),
                Jsonb(competency),
                "hr_system_of_record",
                "hr_system_of_record",
            ),
        )
    for cred, sub in ((signer_cred, signer), (cosign_cred, countersigner)):
        conn.execute(
            "INSERT INTO mainline.signing_credential (credential_id, signer_sub, public_key_cose, "
            "aaguid, transports, attachment, enrolment_assurance) "
            "VALUES (%s, %s, %s, %s, ARRAY['usb'], 'cross-platform', 'hr_system_of_record')",
            (cred, sub, _sha("cose", sub), _sha("aaguid", sub)[:16]),
        )

    for index, commit_id in enumerate((commit_v1, commit_v2), start=1):
        envelope = {"kind": "w3-commit", "clause": str(clause_uuid), "gen": index}
        conn.execute(
            "INSERT INTO mainline.commit_obj (commit_id, site_id, gen, ref_name, author_sub, "
            "message, envelope, envelope_bytes) "
            "VALUES (%s, %s, %s, 'refs/heads/main', %s, %s, %s, %s)",
            (
                commit_id,
                site_id,
                index,
                signer,
                f"clause version {index}",
                Jsonb(envelope),
                _jcs(envelope),
            ),
        )
    conn.execute(
        "INSERT INTO mainline.doc (doc_id, site_id, doc_code, title) VALUES (%s, %s, %s, %s)",
        (doc_id, site_id, "w3-sop-1", "Isolation of stored energy"),
    )
    conn.execute(
        "INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root, "
        "head_commit) "
        "VALUES (%s, %s, %s, %s, %s)",
        (clause_uuid, site_id, commit_v1, activity_root, commit_v2),
    )

    text_v1 = (
        "Before any intrusive work, stored energy shall be isolated, locked and verified at "
        "zero by a competent person."
    )
    text_v2 = (
        "Before any intrusive work, stored energy shall be isolated, locked and verified at "
        "zero by a competent person, and the verification shall be witnessed and recorded."
    )
    conn.execute(
        "INSERT INTO mainline.clause_version (clause_uuid, gen, commit_id, site_id, doc_id, "
        "activity_root, ordinal, printed_label, raw_text, canon_text, canon_version, canon_sha256, "
        "anchor_set, cat_confidence, control_delta, delta_basis, blood_root, blood_peaks, "
        "blood_size, "
        "sev_max) VALUES (%s, 1, %s, %s, %s, %s, 1, '7.3.2(b)', %s, %s, 1, %s, "
        "ARRAY['LOTO','ZERO_ENERGY'], 'ok', 'introduce', 'lattice', %s, ARRAY[]::BYTES[], 0, 4)",
        (
            clause_uuid,
            commit_v1,
            site_id,
            doc_id,
            activity_root,
            text_v1,
            text_v1,
            _sha(text_v1),
            _ZERO32,
        ),
    )
    conn.execute(
        "INSERT INTO mainline.clause_version (clause_uuid, gen, commit_id, site_id, doc_id, "
        "activity_root, parent_version, ordinal, printed_label, raw_text, canon_text, "
        "canon_version, "
        "canon_sha256, anchor_set, cat_confidence, control_delta, delta_basis, blood_root, "
        "blood_peaks, blood_size, sev_max) "
        "VALUES (%s, 2, %s, %s, %s, %s, %s, 1, '7.3.2(b)', %s, %s, 1, %s, "
        "ARRAY['LOTO','ZERO_ENERGY','WITNESS'], 'ok', 'strengthen', 'lattice', %s, "
        "ARRAY[]::BYTES[], 0, 4)",
        (
            clause_uuid,
            commit_v2,
            site_id,
            doc_id,
            activity_root,
            commit_v1,
            text_v2,
            text_v2,
            _sha(text_v2),
            _ZERO32,
        ),
    )
    conn.execute(
        "INSERT INTO mainline.delta_witness (clause_uuid, commit_id, witness_ord, rule_id, field, "
        "from_repr, to_repr, note, minimal) "
        "VALUES (%s, %s, 0, 'R6_VERIFICATION', 'verification', %s, %s, %s, true)",
        (
            clause_uuid,
            commit_v2,
            "verified at zero",
            "verified at zero, witnessed and recorded",
            "The verification obligation acquires a witness and a record; the control tightens.",
        ),
    )

    for event_id, ref, title, days in (
        (event_a, "INC-W3-1", "Stored energy release during intrusive work", 400),
        (event_b, "INC-W3-2", "Repeat release on the same isolation point", 120),
    ):
        conn.execute(
            "INSERT INTO mainline.event (event_id, site_id, external_ref, occurred_at, "
            "ingested_at, "
            "kind, title, narrative, source_object_key, source_sha256, severity_actual, "
            "severity_potential, severity_gate, severity_basis, canon_version) "
            # `make_interval(days => n)` is a syntax error on CockroachDB v26.2.5 — named
            # arguments are not accepted — so the multiplication is spelled out.
            "VALUES (%s, %s, %s, now() - (%s * INTERVAL '1 day'), now() - INTERVAL '2 days', "
            "'incident', %s, %s, %s, %s, 4, 4, 4, 'human_rated', 1)",
            (
                event_id,
                site_id,
                ref,
                days,
                title,
                (
                    "An isolation was signed off without verification at zero; residual "
                    "hydraulic pressure released while the guard was removed."
                ),
                f"w3/{ref.lower()}.pdf",
                _sha("incident", ref),
            ),
        )
    conn.execute(
        "INSERT INTO mainline.event_edge (child_event_id, parent_event_id, relation) "
        "VALUES (%s, %s, 'recurrence_of')",
        (event_b, event_a),
    )
    conn.execute(
        "INSERT INTO mainline.control_failure (failure_id, event_id, control_class, barrier_role, "
        "failure_mode, icam_tier, hazard_energy, evidence_span, quote_sha256) "
        "VALUES (%s, %s, 'zero_energy_verification', 'preventive', 'not_verified', "
        "'absent_or_failed_defence', 'pressure', ARRAY[0, 96], %s)",
        (uuid.uuid4(), event_a, _sha("quote", "w3-1")),
    )

    for event_id in (event_a, event_b):
        conn.execute(
            "INSERT INTO mainline.blame_edge (event_id, clause_uuid, basis, state, site_id, "
            "commit_id, features, attribution, evidence_doc_id, evidence_quote_sha256) "
            "VALUES (%s, %s, 'asserted_document', 'active', %s, %s, %s, %s, %s, %s)",
            (
                event_id,
                clause_uuid,
                site_id,
                commit_v2,
                Jsonb({"quote_offsets": [0, 96], "source": "investigation report §4"}),
                "The investigation names this clause as the control that failed.",
                doc_id,
                _sha("quote", str(event_id)),
            ),
        )
    # `fn_closure_guard` demands the FIRST generation for a clause version be zero.
    conn.execute(
        "INSERT INTO mainline.clause_blame_closure (clause_uuid, as_of_commit, closure_gen, "
        "site_id, "
        "ancestor_events, ancestor_count, max_severity, virulence, depth, truncated, computed_by, "
        "projector_ver) VALUES (%s, %s, 0, %s, ARRAY[%s, %s]::UUID[], 2, 4, 'blood_major', 2, "
        "false, "
        "'tests/conftest.py', 'w3-1')",
        (clause_uuid, commit_v2, site_id, event_a, event_b),
    )

    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name, "
        "horizon_at) VALUES (%s, %s, %s, 'PTW-W3-1', 'refs/permits/w3-1', "
        "now() + INTERVAL '30 days')",
        (permit_id, site_id, site_role),
    )
    conn.execute(
        "INSERT INTO mainline.permit_clause (permit_id, clause_uuid, commit_id, relation) "
        "VALUES (%s, %s, %s, 'relies_on')",
        (permit_id, clause_uuid, commit_v2),
    )
    conn.execute(
        "INSERT INTO mainline.boundary_certificate (permit_id, cert_gen, asset_graph_version, "
        "tags_declared, tags_resolved, tags_unmodelled, under_declared) "
        "VALUES (%s, 1, 'w3-asset-graph-1', 3, 3, 0, 0)",
        (permit_id,),
    )
    conn.execute(
        "INSERT INTO mainline.cbm_account (site_id, commit_id, account_gen, inherited, carried, "
        "split_carried, merge_carried, residue_open, residue_disposed, computed_by, wrote_as, "
        "projector_ver) VALUES (%s, %s, 0, 0, 0, 0, 0, 0, 0, 'tests/conftest.py', current_user, "
        "'w3-1')",
        (site_id, commit_v2),
    )
    conn.execute(
        "INSERT INTO mainline.change_request (cr_id, site_id, site_role, external_ref, ref_name, "
        "target_ref) VALUES (%s, %s, %s, 'MOC-2026-0413', 'refs/changes/w3-1', 'refs/heads/main')",
        (cr_id, site_id, site_role),
    )

    # ── The ledger: two checkpoints over four leaves, so a consistency proof exists.
    leaf_hashes: list[bytes] = []
    prev_link = _ZERO32
    entries: list[tuple[uuid.UUID, bytes, bytes]] = []
    for seq in range(4):
        entry_id = uuid.uuid4()
        payload = {"kind": "w3-entry", "seq": seq, "subject": str(permit_id)}
        canon = _jcs(payload)
        leaf_hash = hashlib.sha256(b"\x00" + canon).digest()
        link_hash = _sha(prev_link, leaf_hash)
        conn.execute(
            "INSERT INTO mainline.ledger_intake (entry_id, site_code, entry_kind, subject_id, "
            "actor, "
            "actor_kind, payload, canon_bytes, payload_ver, leaf_hash, is_sandbox, hlc, "
            "recorded_at) "
            "VALUES (%s, %s, 'permit_event', %s, %s, 'service', %s, %s, 1, %s, false, %s, now())",
            (
                entry_id,
                site_code,
                permit_id,
                "w3/sequencer",
                Jsonb(payload),
                canon,
                leaf_hash,
                seq + 1,
            ),
        )
        conn.execute(
            "INSERT INTO mainline.ledger_leaf (site_code, seq, entry_id, leaf_hash, "
            "prev_link_hash, "
            "link_hash, batch_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (site_code, seq, entry_id, leaf_hash, prev_link, link_hash, uuid.uuid4()),
        )
        entries.append((entry_id, leaf_hash, link_hash))
        leaf_hashes.append(leaf_hash)
        prev_link = link_hash

    for tree_size in (2, 4):
        root = _mth(leaf_hashes[:tree_size])
        conn.execute(
            "INSERT INTO mainline.ledger_checkpoint (site_code, tree_size, root_hash, body, "
            "beacon, "
            "log_sig, tsa_token, canon_src_sha256, admissible) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true)",
            (
                site_code,
                tree_size,
                root,
                f"mainline/{site_code}\n{tree_size}\n{root.hex()}\n",
                Jsonb({"drand_round": tree_size, "nist_pulse": tree_size}),
                _sha("logsig", site_code, str(tree_size)),
                _sha("tsa", str(tree_size)),
                _sha("canon-src"),
            ),
        )
        conn.execute(
            "INSERT INTO mainline.cosignature (site_code, tree_size, witness_id, trust_domain, "
            "adverse, sig) VALUES (%s, %s, 'witness.w3/hsr-1', 'union_hsr', true, %s)",
            (site_code, tree_size, _sha("cosig", site_code, str(tree_size))),
        )
    for level, index_, value in ((1, 0, _mth(leaf_hashes[:2])), (1, 1, _mth(leaf_hashes[2:4]))):
        conn.execute(
            "INSERT INTO mainline.ledger_node (site_code, level, idx, hash) VALUES (%s, %s, %s, "
            "%s)",
            (site_code, level, index_, value),
        )
    conn.execute(
        "INSERT INTO mainline.unwitnessed_debt (debt_id, site_code, permit_id, incurred_at, "
        "discharged_tree_size) VALUES (%s, %s, %s, now() - INTERVAL '1 hour', 4)",
        (uuid.uuid4(), site_code, permit_id),
    )

    # ── The recall pass, its silence, and its receipt.
    policy_version = "w3-recall-1.0"
    conn.execute(
        "INSERT INTO mainline_meas.recall_policy (policy_version, taxonomy_ver, embed_model, "
        "gen_model, prompt_version, beam_size, tau, arms, calibration_set_sha256, author_sub, "
        "signature, anchored_tree_size, anchored_at) "
        "VALUES (%s, 1, 'amazon.titan-embed-text-v2:0', 'au.anthropic.claude', 'p-1', 8, %s, %s, "
        "%s, "
        "%s, %s, 4, now())",
        (
            policy_version,
            Jsonb({"tau0": 5, "rho": 4}),
            Jsonb({"lexical": True, "vector": True}),
            _sha("calibration"),
            signer,
            _sha("policy-sig"),
        ),
    )
    run_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline_meas.recall_run (run_id, permit_id, site_id, corpus_commit, "
        "policy_version, index_plan_digest, index_generation, n_candidates, n_blocking, "
        "n_advisory, "
        "n_silenced, n_deduped, n_bonded_sev5, n_bonded_sev5_blocking, latency_ms) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'g1', 4, 1, 1, 1, 1, 0, 0, 412)",
        (run_id, permit_id, site_id, commit_v2, policy_version, _sha("plan")),
    )
    silence_receipt_id = uuid.uuid4()
    boundary_proof = {
        "leaf_s": {
            "index": 1,
            "leaf_hash_hex": leaf_hashes[1].hex(),
            "score": 0.51,
            "path_hex": [leaf_hashes[0].hex(), _mth(leaf_hashes[2:4]).hex()],
        },
        "leaf_s_plus_1": {
            "index": 2,
            "leaf_hash_hex": leaf_hashes[2].hex(),
            "score": 0.31,
            "path_hex": [leaf_hashes[3].hex(), _mth(leaf_hashes[:2]).hex()],
        },
    }
    conn.execute(
        "INSERT INTO mainline_meas.silence_receipt (silence_receipt_id, run_id, permit_id, "
        "corpus_root, candidate_root, theta, s, n, boundary_proof, policy_version) "
        "VALUES (%s, %s, %s, %s, %s, 0.45, 2, 4, %s, %s)",
        (
            silence_receipt_id,
            run_id,
            permit_id,
            _mth(leaf_hashes).hex() and _mth(leaf_hashes),
            _sha("candidate-root"),
            Jsonb(boundary_proof),
            policy_version,
        ),
    )
    conn.execute(
        "INSERT INTO mainline_meas.silence_ledger (silence_id, site_id, source, reason, "
        "subject_kind, "
        "subject_id, severity, score, threshold, arithmetic, policy_version, at) "
        "VALUES (%s, %s, 'recall', 'below_tau', 'permit', %s, 3, 0.31, 0.45, %s, %s, now())",
        (
            uuid.uuid4(),
            site_id,
            permit_id,
            Jsonb(
                {
                    "components": {"lexical": 0.12, "vector": 0.19},
                    "model": "titan-embed-text-v2",
                    "tau": 0.45,
                    "calibration_commit": commit_v2.hex(),
                }
            ),
            policy_version,
        ),
    )

    # ── The obligation, the vocabulary offered against it, and the exposure receipt.
    check_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.blocking_check (check_id, subject_kind, permit_id, site_id, "
        "clause_uuid, "
        "commit_id, precursor_event_id, origin, severity, virulence, closure_gen, recall_run_id, "
        "evidence_summary) VALUES (%s, 'permit', %s, %s, %s, %s, %s, 'blame_ancestry', 0, "
        "'routine', "
        "0, %s, %s)",
        (
            check_id,
            permit_id,
            site_id,
            clause_uuid,
            commit_v2,
            event_a,
            run_id,
            "Recalled precursor INC-W3-1 reaches the clause this permit relies on.",
        ),
    )
    vocab = _sha("defeater-vocab")
    for code, prompt in (
        ("MECHANISM_PRESENT_AND_VERIFIED", "which precondition of this mechanism is absent?"),
        ("SCOPE_EXCLUDES_HAZARD", "which part of this permit's scope excludes the hazard energy?"),
    ):
        conn.execute(
            "INSERT INTO mainline.defeater_option (check_id, defeater_code, prompt, vocab_sha256) "
            "VALUES (%s, %s, %s, %s)",
            (check_id, code, prompt, vocab),
        )

    receipt_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.exposure_receipt (receipt_id, subject_kind, permit_id, actor_sub, "
        "issued_at, issued_hlc, expires_at, corpus_root, silence_receipt_id, policy_version, "
        "total_tokens, receipt_digest) "
        "VALUES (%s, 'permit', %s, %s, now() - INTERVAL '10 minutes', %s, "
        "now() + INTERVAL '2 hours', "
        "%s, %s, %s, 200, %s)",
        (
            receipt_id,
            permit_id,
            signer,
            4,
            _mth(leaf_hashes),
            silence_receipt_id,
            policy_version,
            _sha("receipt", str(receipt_id)),
        ),
    )
    conn.execute(
        "INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens) "
        "VALUES (%s, %s, %s, 200)",
        (receipt_id, check_id, _sha("line", str(check_id))),
    )

    # ── One signed disposition. Almost every column here is overwritten by
    #    `fn_disposition_project` from authoritative rows; what the signer chooses is
    #    the kind, the defeater code, the rationale and the signature.
    disposition_id = uuid.uuid4()
    rationale = (
        "The recalled precursor INC-W3-1 is answered by a verified zero-energy isolation "
        "procedure that was re-issued after the incident, and the permit's scope is covered by "
        "that procedure in full. Verification at zero is witnessed and recorded before any "
        "intrusive work begins, so the mechanism the incident found missing is present and "
        "exercised on this permit."
    )
    conn.execute(
        "INSERT INTO mainline.disposition (disposition_id, check_id, receipt_id, subject_kind, "
        "permit_id, site_id, kind, virulence, closure_gen, defeater_code, defeater_vocab_sha256, "
        "rationale, evidence_sha256, signer_sub, signer_rank, signer_org, signer_credential_id, "
        "countersigner_sub, countersigner_credential_id, signature_alg, authenticator_data, "
        "client_data_json, user_verified, competency_snapshot, competency_source_id, "
        "competency_sha256, req_compensating, req_second_signer, req_foreign_org, req_predicate, "
        "req_reassert, min_signer_rank, severity_snapshot, deliberation_seconds, evidence_opened, "
        "prior_override_count) "
        "VALUES (%s, %s, %s, 'permit', %s, %s, 'applied', 'routine', 0, "
        "'MECHANISM_PRESENT_AND_VERIFIED', %s, %s, %s, %s, 1, 'x', %s, %s, %s, 'ES256', %s, %s, "
        "true, "
        "%s, %s, %s, false, false, false, false, false, 1, 0, 0, true, 0)",
        (
            disposition_id,
            check_id,
            receipt_id,
            permit_id,
            site_id,
            vocab,
            rationale,
            _sha("evidence", str(disposition_id)),
            signer,
            signer_cred,
            countersigner,
            cosign_cred,
            _sha("authenticator", str(disposition_id)),
            _jcs({"challenge": disposition_id.hex, "type": "webauthn.get"}),
            Jsonb(competency),
            uuid.uuid4(),
            _sha("competency", signer),
        ),
    )

    # ── One agent action, so the audit surface's call log is a column and not a hole.
    conn.execute(
        "INSERT INTO mainline_meas.agent_action (action_id, agent_role, tool, transport, model_id, "
        "prompt_version, subject_kind, subject_id, input_sha256, output_sha256, granted_scopes, "
        "outcome, sqlstate, latency_ms, at) "
        "VALUES (%s, 'agent_reader', 'sql_select', 'pgwire', NULL, NULL, 'permit', %s, %s, %s, "
        "ARRAY['mainline_audit:select'], 'ok', NULL, 37, now())",
        (uuid.uuid4(), permit_id, _sha("mcp-in"), _sha("mcp-out")),
    )

    return {
        "site_id": str(site_id),
        "site_code": site_code,
        "permit_id": str(permit_id),
        "cr_id": str(cr_id),
        "clause_uuid": str(clause_uuid),
        "commit_v1": commit_v1.hex(),
        "commit_v2": commit_v2.hex(),
        "event_a": str(event_a),
        "event_b": str(event_b),
        "check_id": str(check_id),
        "receipt_id": str(receipt_id),
        "run_id": str(run_id),
        "silence_receipt_id": str(silence_receipt_id),
        "disposition_id": str(disposition_id),
        "signer_sub": signer,
    }


@pytest.fixture(scope="session")
def demo_database(admin_dsn: str) -> tuple[str, dict[str, str]]:
    """A migrated, seeded database, cached by the fingerprint of the migration tree."""
    fingerprint = _fingerprint()
    database = f"w3_demo_api_{fingerprint}"
    dsn = _dsn_for(admin_dsn, database)

    # Existence is decided by CONNECTING, not by querying `information_schema.schemata`:
    # that view describes the schemas of the database you are connected to, so it reports
    # nothing about a sibling database and the check silently said "absent" for one that
    # was there. A connect that raises `3D000` is unambiguous.
    marker: dict[str, Any] | None = None
    try:
        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as probe:
            try:
                marker = probe.execute(
                    "SELECT seed FROM w3_fixture.ready WHERE fingerprint = %s", (fingerprint,)
                ).fetchone()
            except psycopg.Error:
                marker = None
    except psycopg.Error:
        marker = None
    if marker is not None:
        return dsn, dict(marker["seed"])

    with psycopg.connect(admin_dsn, autocommit=True, row_factory=dict_row) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")
        admin.execute(f"CREATE DATABASE {database}")
        admin.execute(
            f"ALTER DATABASE {database} CONFIGURE ZONE USING "
            f"gc.ttlseconds = {_CLOUD_GC_TTL_SECONDS}"
        )

    applied, failures = _apply_chain(dsn)
    if failures:
        pytest.skip(
            f"{len(failures)} of {applied + len(failures)} migrations did not apply into "
            f"{database}, so the read surface cannot be exercised against the real schema. "
            "First three: " + "; ".join(failures[:3])
        )

    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        seed = _seed(conn)
        conn.execute("CREATE SCHEMA IF NOT EXISTS w3_fixture")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS w3_fixture.ready ("
            "  fingerprint STRING PRIMARY KEY,"
            "  built_at    TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  migrations  INT8 NOT NULL,"
            "  seed        JSONB NOT NULL)"
        )
        conn.execute(
            "UPSERT INTO w3_fixture.ready (fingerprint, migrations, seed) VALUES (%s, %s, %s)",
            (fingerprint, applied, Jsonb(seed)),
        )
    return dsn, seed


@pytest.fixture(scope="session")
def demo_dsn(demo_database: tuple[str, dict[str, str]]) -> str:
    """The DSN of the migrated, seeded database."""
    return demo_database[0]


@pytest.fixture(scope="session")
def seed(demo_database: tuple[str, dict[str, str]]) -> dict[str, str]:
    """The identifiers the fixture minted, so a test names its own subject."""
    return demo_database[1]


@pytest.fixture
def conn(demo_dsn: str) -> Iterator[psycopg.Connection[Any]]:
    """One connection per test, through the module under test, so its caching is exercised."""
    from mainline_demo_api import db as demo_db

    demo_db.reset_dsn_cache()
    try:
        yield demo_db.connection(dsn=demo_dsn)
    finally:
        demo_db.reset_dsn_cache()


# ── A validator for the console's contracts ─────────────────────────────────────────

#: Keywords whose value is a single subschema rather than a list or a mapping of them.
_SUBSCHEMA_KEYWORDS: Final = frozenset(
    {"not", "if", "then", "else", "items", "additionalProperties"}
)

_DATE_TIME = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def _is_date_time(value: str) -> bool:
    """RFC 3339 §5.6, as strictly as ``console/src/data/schema.ts`` asserts it.

    A real calendar date and a real clock time, so ``2026-02-30T00:00:00Z`` is refused —
    a contract that accepts an impossible date has not checked the date.
    """
    match = _DATE_TIME.match(value)
    if match is None:
        return False
    year, month, day, hour, minute, second = (int(match.group(index)) for index in range(1, 7))
    if not (1 <= month <= 12) or hour > 23 or minute > 59 or second > 60:
        return False
    try:
        _dt.date(year, month, day)
    except ValueError:
        return False
    return True


class SchemaRegistry:
    """Draft 2020-12, restricted to the keywords ``console/contracts/`` actually uses.

    The set was not guessed: it is the result of walking all sixteen documents and
    counting keys. An unimplemented keyword is a hard error rather than a silent pass —
    the same rule ``src/data/schema.ts`` states for itself, and for the same reason. A
    validator that ignores a keyword it never implemented turns every conformance test
    green while asserting less than it claims.
    """

    SUPPORTED: Final = frozenset(
        {
            "$ref",
            "allOf",
            "anyOf",
            "oneOf",
            "not",
            "if",
            "then",
            "else",
            "properties",
            "additionalProperties",
            "items",
            "required",
            "type",
            "enum",
            "const",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "pattern",
            "minItems",
            "maxItems",
            "minProperties",
            "maxProperties",
            "format",
        }
    )
    ANNOTATIONS: Final = frozenset(
        {"$schema", "$id", "$comment", "title", "description", "default", "examples", "$defs"}
    )

    def __init__(self, directory: Path) -> None:
        self.documents: dict[str, Any] = {}
        for path in sorted(directory.glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            self.documents[str(document["$id"])] = document
        for identifier, document in self.documents.items():
            self._audit(document, identifier)

    def _audit(self, node: Any, identifier: str, path: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in self.ANNOTATIONS:
                    if key == "$defs":
                        for name, child in value.items():
                            self._audit(child, identifier, f"{path}/$defs/{name}")
                    continue
                if key not in self.SUPPORTED:
                    raise AssertionError(
                        f"{identifier}{path}: keyword {key!r} is not implemented by this "
                        "validator. Implement it in tests/conftest.py rather than letting a "
                        "contract assert something nothing checks."
                    )
                if key in {"properties"}:
                    for name, child in value.items():
                        self._audit(child, identifier, f"{path}/properties/{name}")
                elif key in {"allOf", "anyOf", "oneOf"}:
                    for index, child in enumerate(value):
                        self._audit(child, identifier, f"{path}/{key}/{index}")
                elif key in _SUBSCHEMA_KEYWORDS and isinstance(value, dict):
                    self._audit(value, identifier, f"{path}/{key}")

    def _resolve(self, ref: str, base: str) -> tuple[Any, str]:
        absolute = urljoin(base, ref)
        document_id, fragment = urldefrag(absolute)
        document = self.documents.get(document_id)
        if document is None:
            raise AssertionError(f"$ref {ref!r} from {base} names unknown document {document_id!r}")
        node: Any = document
        for segment in (part for part in fragment.split("/") if part):
            node = node[segment.replace("~1", "/").replace("~0", "~")]
        return node, document_id

    def validate(self, schema_id: str, instance: Any) -> list[str]:
        """Return the list of violations. Empty means the payload satisfies the contract."""
        schema = self.documents.get(schema_id)
        if schema is None:
            return [
                f"$: no contract with $id {schema_id!r} is held (have {sorted(self.documents)})"
            ]
        errors: list[str] = []
        self._check(schema, instance, schema_id, "$", errors)
        return errors

    def _check(self, schema: Any, value: Any, base: str, path: str, errors: list[str]) -> None:  # noqa: PLR0912
        if schema is True or schema == {}:
            return
        if schema is False:
            errors.append(f"{path}: schema is false; nothing validates")
            return
        if not isinstance(schema, dict):
            return

        if "$ref" in schema:
            target, new_base = self._resolve(str(schema["$ref"]), base)
            self._check(target, value, new_base, path, errors)

        if "type" in schema:
            names = schema["type"]
            names = [names] if isinstance(names, str) else list(names)
            if not any(self._is_type(value, name) for name in names):
                errors.append(f"{path}: expected type {names}, got {self._type_of(value)}")
                return
        if "enum" in schema and not any(value == option for option in schema["enum"]):
            errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(f"{path}: shorter than minLength {schema['minLength']}")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(f"{path}: longer than maxLength {schema['maxLength']} ({len(value)})")
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                errors.append(f"{path}: {value[:60]!r} does not match {schema['pattern']}")
            if schema.get("format") == "date-time" and not _is_date_time(value):
                errors.append(f"{path}: {value!r} is not an RFC 3339 date-time")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: {value} < minimum {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{path}: {value} > maximum {schema['maximum']}")
            if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
                errors.append(f"{path}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}")
            if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
                errors.append(f"{path}: {value} >= exclusiveMaximum {schema['exclusiveMaximum']}")

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: {len(value)} items < minItems {schema['minItems']}")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append(f"{path}: {len(value)} items > maxItems {schema['maxItems']}")
            if "items" in schema:
                for position, item in enumerate(value):
                    self._check(schema["items"], item, base, f"{path}/{position}", errors)

        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    errors.append(f"{path}: required property {name!r} is absent")
            if "minProperties" in schema and len(value) < schema["minProperties"]:
                errors.append(
                    f"{path}: {len(value)} properties < minProperties {schema['minProperties']}"
                )
            if "maxProperties" in schema and len(value) > schema["maxProperties"]:
                errors.append(
                    f"{path}: {len(value)} properties > maxProperties {schema['maxProperties']}"
                )
            declared = schema.get("properties", {})
            for name, child in declared.items():
                if name in value:
                    self._check(child, value[name], base, f"{path}/{name}", errors)
            extra = schema.get("additionalProperties")
            if extra is False:
                for name in value:
                    if name not in declared:
                        errors.append(f"{path}: additional property {name!r} is not permitted")
            elif isinstance(extra, dict):
                for name, item in value.items():
                    if name not in declared:
                        self._check(extra, item, base, f"{path}/{name}", errors)

        for child in schema.get("allOf", []):
            self._check(child, value, base, path, errors)
        if "anyOf" in schema and not any(
            not self._collect(child, value, base) for child in schema["anyOf"]
        ):
            errors.append(f"{path}: satisfies none of the {len(schema['anyOf'])} anyOf branches")
        if "oneOf" in schema:
            passing = [
                index
                for index, child in enumerate(schema["oneOf"])
                if not self._collect(child, value, base)
            ]
            if len(passing) != 1:
                errors.append(
                    f"{path}: matched {len(passing)} of {len(schema['oneOf'])} oneOf branches "
                    f"(exactly one is required); value={_preview(value)}"
                )
        if "not" in schema and not self._collect(schema["not"], value, base):
            errors.append(f"{path}: matched a schema it must not match")
        if "if" in schema:
            if not self._collect(schema["if"], value, base):
                if "then" in schema:
                    self._check(schema["then"], value, base, path, errors)
            elif "else" in schema:
                self._check(schema["else"], value, base, path, errors)

    def _collect(self, schema: Any, value: Any, base: str) -> list[str]:
        errors: list[str] = []
        self._check(schema, value, base, "$", errors)
        return errors

    @staticmethod
    def _is_type(value: Any, name: str) -> bool:  # noqa: PLR0911 - one return per JSON type
        if name == "null":
            return value is None
        if name == "boolean":
            return isinstance(value, bool)
        if name == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if name == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if name == "string":
            return isinstance(value, str)
        if name == "array":
            return isinstance(value, list)
        if name == "object":
            return isinstance(value, dict)
        raise AssertionError(f"unknown JSON Schema type {name!r}")

    @staticmethod
    def _type_of(value: Any) -> str:  # noqa: PLR0911 - one return per JSON type
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        return "object"


def _preview(value: Any) -> str:
    text = json.dumps(value, default=str)
    return text if len(text) <= 120 else f"{text[:117]}..."


@pytest.fixture(scope="session")
def registry() -> SchemaRegistry:
    """The console's own contract files, compiled once."""
    if not CONTRACTS_DIR.is_dir():
        pytest.skip(
            f"the console's contracts are not present at {CONTRACTS_DIR}, so no payload emitted "
            "by this API can be checked against the schema its client will enforce"
        )
    return SchemaRegistry(CONTRACTS_DIR)
