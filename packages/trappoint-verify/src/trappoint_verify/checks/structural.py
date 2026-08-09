# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Checks 1, 2, 3, 9, 10, 13, 14, 15 and 16 — everything provable with ``hashlib`` alone.

These nine checks are the ones a stranger can run with **no key material, no network and
no cooperation from us**. Between them they answer three of the four propositions custody
exists to support: *non-alteration* (1), *non-omission* (2, 3, 9) and *provenance of
process* (10). The fourth — existence at a bracketed time — needs a signature, a timestamp
token and a beacon, and lives in worker 7's modules.

RFC 6962 is reimplemented here, deliberately
--------------------------------------------
:func:`verify_inclusion` and :func:`verify_consistency` are written from RFC 6962-bis
§2.1.3.2 and §2.1.4.2 against ``hashlib`` and nothing else. ``trappoint_ledger`` has
perfectly good versions of both and this module **must not import them**: the deliverable
is the sentence *"the verifier has zero MAINLINE dependencies"*, and a shared proof library
would make that sentence false in the one place it matters. Two independent
implementations of the same RFC also disagree loudly when one of them is wrong, which a
single shared one cannot.

Both functions are **total**. Adversarial input returns ``False``; it never raises. An
exception escaping a verifier is a crash report where a finding belongs.

What check 1 does not do
------------------------
It hashes the ``canon_bytes`` the bundle carries. It does **not** re-canonicalise the
parsed ``payload`` and hash that — doing so would test our canonicaliser against itself
and would pass on a bundle whose bytes had been replaced wholesale. The parsed payload is
compared against the carried bytes *separately*, and a disagreement is reported as its own
finding, because that disagreement is exactly what attack **A3** (swap the payload, leave
``canon_bytes``) looks like from the outside.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Final

from trappoint_verify.bundle import (
    GENESIS_LINK,
    HASH_BYTES,
    OPTIONAL_SECTIONS,
    Bundle,
    Checkpoint,
    ClosureGeneration,
    Leaf,
    Receipt,
)
from trappoint_verify.checks import CheckContext, register, spec_for
from trappoint_verify.report import Outcome, Verdict, failed, passed, skipped
from trappoint_verify.vendor import canon_v1

__all__ = [
    "CANONICALISERS",
    "empty_root",
    "leaf_hash",
    "node_hash",
    "verify_consistency",
    "verify_inclusion",
]

#: ``payload_ver`` -> the canonicaliser this verifier holds. An id absent from this map is
#: a **FAIL**, never a ``SKIP``: a bundle written under a canonicaliser we do not have is a
#: bundle we cannot verify, and saying "skipped" would imply we could have.
CANONICALISERS: Final[dict[int, str]] = {canon_v1.CANON_VERSION: "canon_v1"}

_SDR_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "typ",
        "entry_id",
        "leaf_hash",
        "site_code",
        "origin",
        "payload_ver",
        "issued_at",
        "mmd_seconds",
    }
)
_SDR_TYP: Final[str] = "MAINLINE-SDR-v1"
_SDR_MMD_SECONDS: Final[int] = 60
_HEX_LEN: Final[int] = 64
_FIRST_CLOSURE_GENERATION: Final[int] = 1
_MIN_PAIR_CHECKPOINTS: Final[int] = 2
_TOTALITY_CHECK_ID: Final[int] = 16


# --------------------------------------------------------------------------------------
# RFC 6962 §2.1 — the tree, from the RFC, on hashlib
# --------------------------------------------------------------------------------------


def empty_root() -> bytes:
    """``MTH({}) = SHA-256("")``. A log must be able to prove it was empty when it was."""
    return hashlib.sha256(b"").digest()


def leaf_hash(canon_bytes: bytes) -> bytes:
    """``SHA-256(0x00 || canon_bytes)`` — RFC 6962 §2.1 leaf hash, domain-separated."""
    return hashlib.sha256(b"\x00" + canon_bytes).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """``SHA-256(0x01 || left || right)`` — RFC 6962 §2.1 interior hash."""
    return hashlib.sha256(b"\x01" + left + right).digest()


def _is_digest(value: object) -> bool:
    return isinstance(value, bytes | bytearray) and len(value) == HASH_BYTES


def _all_digests(values: object) -> bool:
    return isinstance(values, tuple | list) and all(_is_digest(v) for v in values)


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def verify_inclusion(
    computed_leaf_hash: bytes,
    leaf_index: int,
    tree_size: int,
    path: tuple[bytes, ...],
    root: bytes,
) -> bool:
    """RFC 6962-bis §2.1.3.2. Whether *path* shows the leaf sits at *leaf_index* under *root*."""
    if tree_size <= 0 or not 0 <= leaf_index < tree_size:
        return False
    if not _is_digest(computed_leaf_hash) or not _is_digest(root) or not _all_digests(path):
        return False

    node_index, last_index = leaf_index, tree_size - 1
    folded = bytes(computed_leaf_hash)
    for sibling in path:
        if last_index == 0:
            return False
        if node_index & 1 or node_index == last_index:
            folded = node_hash(sibling, folded)
            while node_index != 0 and not node_index & 1:
                node_index >>= 1
                last_index >>= 1
        else:
            folded = node_hash(folded, sibling)
        node_index >>= 1
        last_index >>= 1
    return last_index == 0 and folded == bytes(root)


def verify_consistency(  # noqa: PLR0911 — each return is a distinct, nameable refusal.
    first_size: int,
    first_root: bytes,
    second_size: int,
    second_root: bytes,
    path: tuple[bytes, ...],
) -> bool:
    """RFC 6962-bis §2.1.4.2: whether the ``first_size`` tree is a prefix of ``second_size``.

    This is the check that defeats attack **A1** — delete leaf *k*, renumber, recompute
    every ``link_hash`` in one ``UPDATE … FROM generate_series``. That attack leaves a
    perfectly self-consistent chain and cannot leave a consistent tree, because the earlier
    root was signed, timestamped and written to Object Lock storage before the attacker
    changed their mind.
    """
    if first_size < 0 or second_size < 0 or first_size > second_size:
        return False
    if not _is_digest(first_root) or not _is_digest(second_root) or not _all_digests(path):
        return False
    if first_size == 0:
        return len(path) == 0 and bytes(first_root) == empty_root()
    if first_size == second_size:
        return len(path) == 0 and bytes(first_root) == bytes(second_root)

    nodes = [bytes(element) for element in path]
    if _is_power_of_two(first_size):
        # A prefix that is itself a complete subtree has a root the proof does not carry.
        nodes.insert(0, bytes(first_root))
    if not nodes:
        return False

    node_index, last_index = first_size - 1, second_size - 1
    while node_index & 1:
        node_index >>= 1
        last_index >>= 1

    first_folded = nodes[0]
    second_folded = nodes[0]
    for sibling in nodes[1:]:
        if last_index == 0:
            return False
        if node_index & 1 or node_index == last_index:
            first_folded = node_hash(sibling, first_folded)
            second_folded = node_hash(sibling, second_folded)
            while node_index != 0 and not node_index & 1:
                node_index >>= 1
                last_index >>= 1
        else:
            second_folded = node_hash(second_folded, sibling)
        node_index >>= 1
        last_index >>= 1

    return (
        last_index == 0
        and first_folded == bytes(first_root)
        and second_folded == bytes(second_root)
    )


# --------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------


def _name(check_id: int) -> str:
    return spec_for(check_id).name


def _count(quantity: int, noun: str, plural: str = "") -> str:
    """``1 checkpoint`` / ``3 checkpoints``. A report a regulator reads is prose, not a log line."""
    return f"{quantity} {noun}" if quantity == 1 else f"{quantity} {plural or noun + 's'}"


def _sorted_checkpoints(bundle: Bundle) -> list[Checkpoint]:
    return sorted(bundle.checkpoints, key=lambda checkpoint: checkpoint.tree_size)


def _newest_checkpoint(bundle: Bundle) -> Checkpoint:
    return _sorted_checkpoints(bundle)[-1]


def _unknown_versions(bundle: Bundle) -> set[int]:
    seen = {bundle.canon.payload_ver} | {leaf.payload_ver for leaf in bundle.leaves}
    for envelope in bundle.receipts:
        version = envelope.receipt.get("payload_ver")
        if isinstance(version, int) and not isinstance(version, bool):
            seen.add(version)
    return {version for version in seen if version not in CANONICALISERS}


# --------------------------------------------------------------------------------------
# Check 1 — leaf_hash_recomputation
# --------------------------------------------------------------------------------------


def _payload_disagreement(leaf: Leaf) -> str | None:
    """Return a description of a payload/``canon_bytes`` disagreement, or ``None``."""
    if not leaf.has_payload:
        return None
    try:
        recomputed = canon_v1.canonicalise_payload(leaf.payload)
    except canon_v1.CanonicalisationError as exc:
        return f"leaf {leaf.seq}: the parsed payload does not canonicalise at all — {exc}"
    if recomputed != leaf.canon_bytes:
        return (
            f"leaf {leaf.seq}: the human-readable payload canonicalises to bytes that are "
            "not the bytes that were hashed (attack A3 — swap the payload, leave "
            "canon_bytes). The leaf hash below is authentic; the rendering beside it is not."
        )
    return None


@register(1)
def check_leaf_hash(context: CheckContext) -> Outcome:
    """Recompute every leaf hash from the bytes the bundle carries."""
    bundle = context.bundle
    name = _name(1)
    if not bundle.leaves:
        return skipped(1, name, "no-leaves", "the bundle carries no leaves to hash")

    findings: list[str] = []
    unknown = sorted({leaf.payload_ver for leaf in bundle.leaves} - set(CANONICALISERS))
    for leaf in bundle.leaves:
        recomputed = leaf_hash(leaf.canon_bytes)
        if recomputed != leaf.leaf_hash:
            findings.append(
                f"leaf {leaf.seq}: SHA-256(0x00 || canon_bytes) is {recomputed.hex()} "
                f"but the bundle says {leaf.leaf_hash.hex()}"
            )
        disagreement = _payload_disagreement(leaf)
        if disagreement is not None:
            findings.append(disagreement)

    if unknown:
        return failed(
            1,
            name,
            "unknown-payload-ver",
            f"payload_ver {unknown} is not a canonicaliser this verifier holds",
            detail=(
                *findings,
                (
                    f"Held: {sorted(CANONICALISERS)}. A leaf written under a canonicaliser we "
                    "do not have cannot be checked, and reporting that as a skip would imply "
                    "we could have checked it."
                ),
            ),
        )
    if findings:
        code = (
            "payload-disagrees-with-canon-bytes"
            if all("attack A3" in line or "canonicalise at all" in line for line in findings)
            else "leaf-hash-mismatch"
        )
        return failed(1, name, code, f"{len(findings)} leaf finding(s)", detail=tuple(findings))
    return passed(
        1,
        name,
        "leaf-hashes-recomputed",
        f"{_count(len(bundle.leaves), 'leaf hash', 'leaf hashes')} recomputed from carried "
        f"bytes under canon_v{bundle.canon.payload_ver}",
    )


# --------------------------------------------------------------------------------------
# Check 2 — inclusion_proof
# --------------------------------------------------------------------------------------


@register(2)
def check_inclusion(context: CheckContext) -> Outcome:
    """Verify one RFC 6962 inclusion proof per leaf, into a checkpoint the bundle carries."""
    bundle = context.bundle
    name = _name(2)
    if not bundle.leaves:
        return skipped(2, name, "no-leaves", "the bundle carries no leaves to include")
    if not bundle.has("inclusion_proofs") and not bundle.inclusion_proofs:
        return failed(
            2,
            name,
            "inclusion-proof-missing",
            f"the bundle carries {len(bundle.leaves)} leaves and no inclusion proofs",
            detail=(
                (
                    "evidence-bundle.md §6 requires one proof per leaf. Without them, "
                    "'that entry was never in your log' is unanswerable."
                ),
            ),
        )

    roots = bundle.checkpoint_roots()
    by_seq = {proof.seq: proof for proof in bundle.inclusion_proofs}
    findings: list[str] = []
    verified = 0
    for leaf in bundle.leaves:
        proof = by_seq.get(leaf.seq)
        if proof is None:
            findings.append(f"leaf {leaf.seq}: no inclusion proof")
            continue
        root = roots.get(proof.tree_size)
        if root is None:
            findings.append(
                f"leaf {leaf.seq}: its proof names tree_size {proof.tree_size}, which is "
                "not a checkpoint this bundle carries"
            )
            continue
        if not verify_inclusion(leaf.leaf_hash, leaf.seq, proof.tree_size, proof.path, root):
            findings.append(
                f"leaf {leaf.seq}: the audit path does not fold to root "
                f"{root.hex()} at tree_size {proof.tree_size}"
            )
            continue
        verified += 1

    if findings:
        code = (
            "inclusion-proof-missing"
            if all("no inclusion proof" in line for line in findings)
            else "inclusion-proof-failed"
        )
        return failed(
            2,
            name,
            code,
            f"{len(findings)} of {len(bundle.leaves)} leaves unproven",
            detail=tuple(findings),
        )
    return passed(
        2,
        name,
        "inclusion-verified",
        f"{_count(verified, 'inclusion proof')} verified against signed roots",
    )


# --------------------------------------------------------------------------------------
# Check 3 — consistency_proof_every_pair
# --------------------------------------------------------------------------------------


@register(3)
def check_consistency(context: CheckContext) -> Outcome:
    """Verify a consistency proof for EVERY consecutive checkpoint pair — not a sample."""
    bundle = context.bundle
    name = _name(3)
    checkpoints = _sorted_checkpoints(bundle)
    if len(checkpoints) < _MIN_PAIR_CHECKPOINTS:
        return skipped(
            3,
            name,
            "single-checkpoint",
            "the bundle carries one checkpoint, so there is no consecutive pair to prove",
            detail=(
                (
                    "Non-omission is the proposition plaintiffs actually attack, and a single "
                    "checkpoint cannot speak to it. This is a limit of the bundle, not of the log."
                ),
            ),
        )

    proofs = {(proof.from_size, proof.to_size): proof for proof in bundle.consistency_proofs}
    findings: list[str] = []
    verified = 0
    for earlier, later in pairwise(checkpoints):
        pair = (earlier.tree_size, later.tree_size)
        proof = proofs.get(pair)
        if proof is None:
            findings.append(
                f"pair {pair[0]} -> {pair[1]}: no consistency proof. A missing pair is a "
                "finding, not a shrug — it is exactly where a rewritten interval would hide."
            )
            continue
        if not verify_consistency(
            earlier.tree_size, earlier.root, later.tree_size, later.root, proof.path
        ):
            findings.append(
                f"pair {pair[0]} -> {pair[1]}: the proof does not show the earlier tree is "
                "a prefix of the later one (attack A1/A2)"
            )
            continue
        verified += 1

    if findings:
        code = (
            "consistency-proof-missing"
            if all("no consistency proof" in line for line in findings)
            else "consistency-proof-failed"
        )
        return failed(
            3,
            name,
            code,
            f"{len(findings)} of {len(checkpoints) - 1} consecutive pairs unproven",
            detail=tuple(findings),
        )
    return passed(
        3,
        name,
        "consistency-verified",
        f"every one of {_count(verified, 'consecutive checkpoint pair')} verified",
    )


# --------------------------------------------------------------------------------------
# Check 9 — link_chain_and_density
# --------------------------------------------------------------------------------------


def _density_findings(leaves: tuple[Leaf, ...]) -> list[str]:
    findings: list[str] = []
    for position, leaf in enumerate(leaves):
        if leaf.seq != position:
            findings.append(
                f"position {position} carries seq {leaf.seq}: the sequence is not dense "
                "0..n-1. CREATE SEQUENCE, nextval, SERIAL and unique_rowid() are banned "
                "repository-wide and seq is derived by compare-and-swap, so no mechanism "
                "exists that could have produced a legitimate gap. A gap MEANS tampering."
            )
            break
    return findings


@register(9)
def check_link_chain(context: CheckContext) -> Outcome:
    """Recompute the link chain from genesis and assert ``seq`` is dense ``0..n-1``."""
    bundle = context.bundle
    name = _name(9)
    if not bundle.leaves:
        return skipped(9, name, "no-leaves", "the bundle carries no leaves to chain")

    leaves = tuple(sorted(bundle.leaves, key=lambda leaf: leaf.seq))
    findings = _density_findings(leaves)

    previous = GENESIS_LINK
    for leaf in leaves:
        if leaf.prev_link_hash != previous:
            findings.append(
                f"leaf {leaf.seq}: prev_link_hash is {leaf.prev_link_hash.hex()} but its "
                f"predecessor's link_hash is {previous.hex()}"
                + (" (genesis must be 32 zero bytes)" if leaf.seq == 0 else "")
            )
        expected = hashlib.sha256(leaf.prev_link_hash + leaf.leaf_hash).digest()
        if expected != leaf.link_hash:
            findings.append(
                f"leaf {leaf.seq}: SHA-256(prev_link_hash || leaf_hash) is {expected.hex()} "
                f"but the bundle says {leaf.link_hash.hex()}"
            )
        previous = leaf.link_hash

    if findings:
        code = "seq-not-dense" if "not dense" in findings[0] else "link-chain-broken"
        return failed(9, name, code, f"{len(findings)} chain finding(s)", detail=tuple(findings))
    return passed(
        9,
        name,
        "link-chain-recomputed",
        f"seq dense 0..{len(leaves) - 1}, link chain recomputes from a 32-zero-byte genesis",
    )


# --------------------------------------------------------------------------------------
# Check 10 — canonicaliser_identity
# --------------------------------------------------------------------------------------


@register(10)
def check_canon_identity(context: CheckContext) -> Outcome:
    """Compare the bundle's ``canon_src_sha256`` against the canonicaliser actually loaded.

    ``canon_v1.canon_src_sha256()`` hashes **its own source file**, LF-normalised. So this
    is not a comparison against a constant we typed in: it is a comparison against the
    bytes of the code that is running, which is what makes the scheme's own code part of
    the scheme (and what makes a canonicaliser downgrade, attack A5, visible).
    """
    bundle = context.bundle
    name = _name(10)
    running = canon_v1.canon_src_sha256()
    findings: list[str] = []

    if bundle.canon.payload_ver not in CANONICALISERS:
        return failed(
            10,
            name,
            "unknown-payload-ver",
            f"the bundle declares payload_ver {bundle.canon.payload_ver}, which this "
            "verifier does not hold",
            detail=(f"Held: {sorted(CANONICALISERS)}.",),
        )
    if bundle.canon.canon_src_sha256 != running:
        findings.append(
            f"the bundle declares canon_src_sha256 {bundle.canon.canon_src_sha256.hex()}; "
            f"the canonicaliser this verifier is running hashes to {running.hex()}"
        )

    expected_line = f"{bundle.canon.payload_ver} {running.hex()}"
    for checkpoint in _sorted_checkpoints(bundle):
        line = checkpoint.parsed.extension("canon")
        if line is None:
            findings.append(
                f"checkpoint {checkpoint.tree_size}: the signed note carries no `canon:` "
                "extension line, so it names no canonicaliser at all"
            )
        elif line != expected_line:
            findings.append(
                f"checkpoint {checkpoint.tree_size}: its signed `canon:` line is {line!r}, "
                f"expected {expected_line!r}"
            )

    if findings:
        code = (
            "canon-source-mismatch"
            if "the bundle declares canon_src_sha256" in findings[0]
            else "checkpoint-canon-line-mismatch"
        )
        return failed(
            10, name, code, f"{len(findings)} canonicaliser finding(s)", detail=tuple(findings)
        )
    return passed(
        10,
        name,
        "canon-identity-matched",
        f"canon_v{bundle.canon.payload_ver} source digest {running.hex()[:16]}... matches "
        "the bundle and every signed checkpoint",
    )


# --------------------------------------------------------------------------------------
# Check 13 — no_sandbox_leaf
# --------------------------------------------------------------------------------------


@register(13)
def check_no_sandbox(context: CheckContext) -> Outcome:
    """Refuse a bundle that mixes sandbox leaves into an evidentiary tree (attack A12)."""
    bundle = context.bundle
    name = _name(13)
    if not bundle.leaves:
        return skipped(13, name, "no-leaves", "the bundle carries no leaves to classify")
    offending = [leaf.seq for leaf in bundle.leaves if leaf.is_sandbox]
    if offending:
        return failed(
            13,
            name,
            "sandbox-leaf-present",
            f"{len(offending)} leaf/leaves carry is_sandbox = true",
            detail=(
                f"seq {offending}",
                (
                    "An anonymous demo write inside an evidentiary tree is attack A12: it makes "
                    "every other leaf in the tree arguable."
                ),
            ),
        )
    return passed(
        13,
        name,
        "no-sandbox-leaves",
        f"none of {_count(len(bundle.leaves), 'leaf', 'leaves')} is a sandbox leaf",
    )


# --------------------------------------------------------------------------------------
# Check 14 — closure_generation_monotone
# --------------------------------------------------------------------------------------


def _group_closures(
    rows: tuple[ClosureGeneration, ...],
) -> dict[tuple[str, str], list[ClosureGeneration]]:
    grouped: dict[tuple[str, str], list[ClosureGeneration]] = {}
    for row in rows:
        grouped.setdefault((row.clause_uuid, row.as_of_commit), []).append(row)
    for rows_for_key in grouped.values():
        rows_for_key.sort(key=lambda row: row.closure_gen)
    return grouped


@register(14)
def check_closure_monotone(context: CheckContext) -> Outcome:
    """Assert generations are dense from 1 and ``max_severity`` never falls — the S2 detector.

    The blame closure sits under *every* ancestry gate. One ``UPDATE … SET max_severity =
    0`` from a Lambda execution role — the least-protected identity in the architecture —
    would evaporate every weakening gate while every dashboard reported full coverage. A
    mass rewrite downward (attack **A10**) either breaks monotonicity or leaves a
    generation gap, and either way it is visible to someone who has never touched the
    cluster.
    """
    bundle = context.bundle
    name = _name(14)
    if not bundle.has("closure_generations"):
        return skipped(
            14,
            name,
            "no-closure-rows",
            "the bundle carries no closure_generations section",
            detail=(
                (
                    "Without it, a mass closure rewrite is invisible to this run. The section "
                    "is optional in the wire format and its absence is a limit of this bundle."
                ),
            ),
        )
    if not bundle.closure_generations:
        return skipped(
            14, name, "no-closure-rows", "the closure_generations section is present but empty"
        )

    findings: list[str] = []
    grouped = _group_closures(bundle.closure_generations)
    for (clause_uuid, as_of_commit), rows in sorted(grouped.items()):
        expected = _FIRST_CLOSURE_GENERATION
        highest = None
        for row in rows:
            if row.closure_gen != expected:
                findings.append(
                    f"({clause_uuid}, {as_of_commit}): generation {expected} is missing — "
                    f"the next row present is {row.closure_gen}"
                )
                break
            if highest is not None and row.max_severity < highest:
                findings.append(
                    f"({clause_uuid}, {as_of_commit}): max_severity fell from {highest} to "
                    f"{row.max_severity} at generation {row.closure_gen} — a closure may "
                    "gain severity as ancestry is walked, never lose it (attack A10)"
                )
            highest = row.max_severity if highest is None else max(highest, row.max_severity)
            expected += 1

    if findings:
        code = (
            "closure-generation-gap"
            if "is missing" in findings[0]
            else "closure-severity-decreased"
        )
        return failed(14, name, code, f"{len(findings)} closure finding(s)", detail=tuple(findings))
    return passed(
        14,
        name,
        "closure-monotone",
        f"{_count(len(bundle.closure_generations), 'row')} over "
        f"{_count(len(grouped), '(clause, commit) pair')}: dense from 1, severity non-decreasing",
    )


# --------------------------------------------------------------------------------------
# Check 15 — receipt_coverage
# --------------------------------------------------------------------------------------


def _receipt_shape_findings(envelope: Receipt, index: int, origin: str) -> list[str]:
    """Structural conformance of one SDR against ``spec/wire/receipt.md`` §2.1."""
    findings: list[str] = []
    members = set(envelope.receipt)
    missing = sorted(_SDR_MEMBERS - members)
    extra = sorted(members - _SDR_MEMBERS)
    if missing:
        findings.append(f"receipt {index}: missing member(s) {missing}")
    if extra:
        findings.append(f"receipt {index}: member(s) {extra} are not permitted by v1.0")
    if envelope.receipt.get("typ") != _SDR_TYP:
        findings.append(
            f"receipt {index}: typ is {envelope.receipt.get('typ')!r}, not {_SDR_TYP!r} — "
            "domain separation is what stops a signature over one JCS object being replayed "
            "as a signature over another"
        )
    if envelope.receipt.get("mmd_seconds") != _SDR_MMD_SECONDS:
        findings.append(
            f"receipt {index}: mmd_seconds is {envelope.receipt.get('mmd_seconds')!r}; v1.0 "
            f"fixes it at {_SDR_MMD_SECONDS}"
        )
    digest = envelope.leaf_hash_hex
    if len(digest) != _HEX_LEN or any(c not in "0123456789abcdef" for c in digest):
        findings.append(f"receipt {index}: leaf_hash is not 64 lowercase hex characters")
    if origin and envelope.receipt.get("origin") != origin:
        findings.append(
            f"receipt {index}: origin {envelope.receipt.get('origin')!r} is not this log's "
            f"origin {origin!r} — a sandbox receipt presented against an evidentiary bundle "
            "fails here (attack A12)"
        )
    return findings


def _receipt_deadline(envelope: Receipt, index: int) -> tuple[datetime | None, str | None]:
    raw = envelope.receipt.get("issued_at")
    if not isinstance(raw, str):
        return None, f"receipt {index}: issued_at is missing or is not a string"
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        issued = datetime.fromisoformat(candidate)
    except ValueError:
        return None, f"receipt {index}: issued_at {raw!r} is not an RFC 3339 timestamp"
    if issued.tzinfo is None:
        return None, f"receipt {index}: issued_at {raw!r} has no UTC offset"
    mmd = envelope.receipt.get("mmd_seconds")
    seconds = mmd if isinstance(mmd, int) and not isinstance(mmd, bool) else _SDR_MMD_SECONDS
    return issued.astimezone(UTC) + timedelta(seconds=seconds), None


def _covering_checkpoint(bundle: Bundle, seq: int) -> Checkpoint | None:
    for checkpoint in _sorted_checkpoints(bundle):
        if checkpoint.tree_size > seq:
            return checkpoint
    return None


def _audit_one_receipt(  # noqa: PLR0911 — five distinct receipt verdicts, each nameable.
    bundle: Bundle,
    envelope: Receipt,
    index: int,
    by_hash: dict[str, Leaf],
) -> tuple[Verdict, str]:
    """Return the verdict for one receipt and the sentence that explains it."""
    leaf = by_hash.get(envelope.leaf_hash_hex)
    deadline, error = _receipt_deadline(envelope, index)
    if error is not None:
        return Verdict.FAIL, error
    if leaf is not None:
        covering = _covering_checkpoint(bundle, leaf.seq)
        if covering is None:
            return (
                Verdict.FAIL,
                (
                    f"receipt {index}: leaf {leaf.seq} is present but no checkpoint in this "
                    "bundle is large enough to contain it"
                ),
            )
        if (
            deadline is not None
            and covering.observed_at is not None
            and covering.observed_at > deadline
        ):
            return (
                Verdict.PASS,
                (
                    f"receipt {index}: covered by checkpoint {covering.tree_size}, whose "
                    f"observed_at is after the MMD deadline {deadline.isoformat()} — the "
                    "earlier checkpoint that met the deadline may simply not be in this bundle"
                ),
            )
        return Verdict.PASS, f"receipt {index}: covered by checkpoint {covering.tree_size}"

    newest = _newest_checkpoint(bundle)
    if newest.observed_at is None:
        return (
            Verdict.SKIP,
            (
                f"receipt {index}: its leaf is absent and no checkpoint carries observed_at, so "
                "the MMD cannot be evaluated"
            ),
        )
    if deadline is not None and newest.observed_at <= deadline:
        return (
            Verdict.SKIP,
            (
                f"receipt {index}: its leaf is absent and the MMD has not expired "
                f"(deadline {deadline.isoformat()}, newest checkpoint observed "
                f"{newest.observed_at.isoformat()})"
            ),
        )
    return (
        Verdict.FAIL,
        (
            f"receipt {index}: THE LOG OPERATOR ISSUED A SIGNED PROMISE AND DID NOT KEEP IT. "
            f"The leaf is absent and the MMD expired at "
            f"{deadline.isoformat() if deadline else 'an unparseable time'}; the newest "
            f"checkpoint here was observed at {newest.observed_at.isoformat()} (attack A14)."
        ),
    )


@register(15)
def check_receipt_coverage(context: CheckContext) -> Outcome:
    """Every SDR whose MMD has expired has its leaf present and included under a checkpoint.

    This is the only finding in the whole set that accuses the log operator of an **act**
    rather than reporting a mismatch, and it is worded that way on purpose. The receipt's
    *signature* is check 4's business: receipts are signed by the same key as the
    checkpoints for their origin.
    """
    bundle = context.bundle
    name = _name(15)
    if not bundle.has("receipts"):
        return skipped(
            15,
            name,
            "no-receipts",
            "the bundle carries no receipts section",
            detail=(
                (
                    "A receipt whose leaf never appears is portable proof of log misbehaviour "
                    "held by the person we gave it to. With no receipts, that instrument is "
                    "simply not exercised by this run."
                ),
            ),
        )
    if not bundle.receipts:
        return skipped(15, name, "no-receipts", "the receipts section is present but empty")

    origin = bundle.origin or _sorted_checkpoints(bundle)[0].parsed.origin
    by_hash = {leaf.leaf_hash.hex(): leaf for leaf in bundle.leaves}
    shape: list[str] = []
    lines: list[str] = []
    verdicts: list[Verdict] = []
    for index, envelope in enumerate(bundle.receipts):
        shape.extend(_receipt_shape_findings(envelope, index, origin))
        verdict, sentence = _audit_one_receipt(bundle, envelope, index, by_hash)
        verdicts.append(verdict)
        lines.append(f"[{verdict.value}] {sentence}")

    if shape:
        return failed(
            15,
            name,
            "receipt-malformed",
            f"{len(shape)} receipt(s) do not conform to receipt.md v1.0",
            detail=(*shape, *lines),
        )
    if Verdict.FAIL in verdicts:
        return failed(
            15,
            name,
            "receipt-orphaned",
            f"{verdicts.count(Verdict.FAIL)} of {len(verdicts)} receipts are not covered",
            detail=tuple(lines),
        )
    if Verdict.SKIP in verdicts:
        return skipped(
            15,
            name,
            "within-mmd",
            f"{verdicts.count(Verdict.SKIP)} of {len(verdicts)} receipts cannot yet be judged",
            detail=tuple(lines),
        )
    return passed(
        15,
        name,
        "receipts-covered",
        f"all {_count(len(verdicts), 'receipt')} have their leaf present and covered",
        detail=tuple(lines),
    )


# --------------------------------------------------------------------------------------
# Check 16 — bundle_totality
# --------------------------------------------------------------------------------------


def _note_index_findings(bundle: Bundle) -> list[str]:
    findings: list[str] = []
    for checkpoint in bundle.checkpoints:
        parsed = checkpoint.parsed
        if parsed.errors:
            findings.append(
                f"checkpoint {checkpoint.tree_size}: its note does not parse — "
                + "; ".join(parsed.errors)
            )
            continue
        if parsed.tree_size != checkpoint.tree_size:
            findings.append(
                f"checkpoint indexed at tree_size {checkpoint.tree_size} carries a note "
                f"that says {parsed.tree_size}"
            )
        if parsed.root != checkpoint.root:
            findings.append(
                f"checkpoint {checkpoint.tree_size}: root_hex is {checkpoint.root.hex()} "
                f"but its note says {parsed.root.hex()}"
            )
    return findings


def _ordering_findings(bundle: Bundle) -> list[str]:
    sizes = [checkpoint.tree_size for checkpoint in bundle.checkpoints]
    findings: list[str] = []
    if sizes != sorted(sizes):
        findings.append(f"checkpoints are not listed in ascending tree_size: {sizes}")
    if len(set(sizes)) != len(sizes):
        findings.append(f"checkpoints carry a duplicate tree_size: {sizes}")
    return findings


def _coverage_findings(bundle: Bundle) -> list[str]:
    findings: list[str] = []
    proof_seqs = {proof.seq for proof in bundle.inclusion_proofs}
    leaf_seqs = {leaf.seq for leaf in bundle.leaves}
    for seq in sorted(leaf_seqs - proof_seqs):
        findings.append(f"leaf {seq} has no inclusion proof")
    for seq in sorted(proof_seqs - leaf_seqs):
        findings.append(f"inclusion proof for seq {seq} names a leaf the bundle does not carry")
    pairs = {(proof.from_size, proof.to_size) for proof in bundle.consistency_proofs}
    checkpoints = _sorted_checkpoints(bundle)
    for earlier, later in pairwise(checkpoints):
        if (earlier.tree_size, later.tree_size) not in pairs:
            findings.append(
                f"consecutive checkpoint pair {earlier.tree_size} -> {later.tree_size} has "
                "no consistency proof"
            )
    return findings


def _run_findings(context: CheckContext) -> list[str]:
    """Assert the *run* looked at everything, not merely that the bundle is tidy.

    A command-line selection narrows what "everything" means — and that narrowing is
    already announced by the report's ``SELECTED RUN`` banner, so this check does not
    double-count it as a defect.
    """
    findings: list[str] = []
    seen = {outcome.check_id for outcome in context.prior}
    expected = set(range(1, _TOTALITY_CHECK_ID))
    if context.selection is not None:
        expected &= set(context.selection)
    for missing in sorted(expected - seen):
        findings.append(
            f"check {missing} produced no outcome at all. A check that is silently absent "
            "is the failure this check exists to detect."
        )
    findings.extend(
        f"check {outcome.check_id} skipped without stating a reason"
        for outcome in context.prior
        if outcome.verdict is Verdict.SKIP and not outcome.reason
    )
    return findings


_NOTE_DISAGREEMENT_MARKERS: Final[tuple[str, ...]] = (
    "carries a note that says",
    "but its note says",
    "its note does not parse",
)


def _totality_code(findings: list[str], *, unknown: bool) -> str:
    """Pick the stable machine token for the first, most explanatory finding."""
    if unknown:
        return "unknown-payload-ver"
    first = findings[0]
    if any(marker in first for marker in _NOTE_DISAGREEMENT_MARKERS):
        return "checkpoint-index-disagrees-with-note"
    return "bundle-not-total"


@register(16)
def check_bundle_totality(context: CheckContext) -> Outcome:
    """Assert the bundle is internally consistent and the run looked at all of it.

    This is the check that makes the other fifteen honest.

    If this fails, no other verdict in the report may be read as complete — and the report
    says so at the top rather than at the bottom.
    """
    bundle = context.bundle
    name = _name(16)
    findings: list[str] = []
    findings.extend(_note_index_findings(bundle))
    findings.extend(_ordering_findings(bundle))
    findings.extend(_coverage_findings(bundle))

    unknown = sorted(_unknown_versions(bundle))
    if unknown:
        findings.append(
            f"payload_ver {unknown} appears in this bundle and is not a canonicaliser this "
            f"verifier holds ({sorted(CANONICALISERS)}). An unknown version is a FAIL and "
            "never a SKIP: a canonicaliser we do not have is one whose bytes we cannot "
            "reproduce, and a skip would imply we could have."
        )
    findings.extend(_run_findings(context))

    if findings:
        return failed(
            16,
            name,
            _totality_code(findings, unknown=bool(unknown)),
            f"{len(findings)} totality finding(s) — read no other verdict as complete",
            detail=tuple(findings),
        )
    absent = sorted(section for section in OPTIONAL_SECTIONS if not bundle.has(section))
    return passed(
        16,
        name,
        "bundle-total",
        f"{_count(len(bundle.checkpoints), 'checkpoint')} and "
        f"{_count(len(bundle.leaves), 'leaf', 'leaves')} are internally consistent and every "
        "one was looked at",
        detail=(
            (
                f"Optional sections absent from this bundle, each of which produced a named "
                f"SKIP above: {absent or 'none'}."
            ),
        ),
    )
