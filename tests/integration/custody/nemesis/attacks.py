# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The fifteen attacks, the exporter they attack through, and the checks that catch them.

**ATTACK-DEPTH.** The kernel proves *refusal depth ≥ 2* by unwelding one mechanism at a
time. This module proves **detection depth** the same way: each attack is executed as real
SQL against a real, disposable CockroachDB seeded with the reference log, a bundle is then
exported from the mutated database, and the full check set is run over it. What comes out
is not an adjective. It is a row: *attack x detecting check x detection latency*.

Three properties make the result worth reading:

1. **The commitments the attacker must contradict already left their control.** The eight
   checkpoints seeded into the database are the ones committed to this repository —
   timestamped by an RFC 3161 authority whose token they cannot re-mint, and cosigned. A
   rewrite of the leaves therefore has to disagree with something an outsider holds, which
   is the entire reason a hash chain inside a table the adversary owns is a checksum and
   not evidence.
2. **The verifier is named in the output.** When ``trappoint_verify`` is importable it is
   what runs. When it is not, :class:`ReferenceChecks` runs — an orchestration of the
   algorithms workers 2 and 3 already shipped (``trappoint_jcs.canon_v1``,
   ``trappoint_ledger.merkle``, ``trappoint_ledger.chain``) plus arithmetic — and the
   matrix says so on its face. A matrix that did not say which verifier produced it would
   be the same kind of claim this whole domain exists to refuse.
3. **A check that could not run is a SKIP, not an absence.** Signature verification needs
   ``cryptography``; where it is missing, checks 4 and 12 report ``SKIP(no-cryptography)``
   and the matrix prints it as loudly as a failure.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from typing import Any

from trappoint_ledger.chain import GENESIS_LINK_HASH
from trappoint_ledger.merkle import (
    EMPTY_ROOT,
    consistency_proof,
    hash_leaf,
    inclusion_proof,
    merkle_tree_hash,
    verify_consistency,
    verify_inclusion,
)

from trappoint_jcs.canon_v1 import canon_src_sha256, canonicalise_payload

try:  # pragma: no cover — availability is environmental, and is reported, never assumed
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives import serialization as _serialization
    from cryptography.hazmat.primitives.asymmetric import ec as _ec

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:  # pragma: no cover
    CRYPTOGRAPHY_AVAILABLE = False

DRAND_GENESIS = 1692803367
DRAND_PERIOD_S = 3
MMD_SECONDS = 60


# =======================================================================================
# Findings and outcomes
# =======================================================================================


@dataclass(frozen=True)
class Finding:
    check: int
    detail: str


@dataclass
class VerifierResult:
    provenance: str
    findings: list[Finding] = field(default_factory=list)
    skipped: dict[int, str] = field(default_factory=dict)

    @property
    def detecting_checks(self) -> list[int]:
        return sorted({finding.check for finding in self.findings})


@dataclass
class AttackOutcome:
    """One row of ``evidence/CUSTODY_ATTACK_MATRIX.md``, produced by a run."""

    id: str
    name: str
    tier: str
    ran: bool
    detected_by: list[int]
    detection_latency_ms: int | None
    verifier: str
    database_refusals: list[str] = field(default_factory=list)
    skipped_reason: str | None = None
    findings: list[str] = field(default_factory=list)
    skipped_checks: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# =======================================================================================
# The exporter — what the operator would hand over, after the attack
# =======================================================================================


def _origin_key_id(reference: dict[str, Any]) -> bytes:
    """The 4-byte key ID out of the reference bundle's vkey, without any crypto.

    ``spec/wire/checkpoint.md`` §5.2: parse on the FIRST TWO ``+`` only. The third field is
    standard base64, whose alphabet includes ``+``, so splitting on every plus yields four
    fields for most keys and three for the rest — a bug that passes in testing and fails on
    the next key you generate.
    """
    _, key_hex, _ = reference["checkpoints"][0]["log_key"].split("+", 2)
    return bytes.fromhex(key_hex)


def _witness_lines(reference: dict[str, Any], tree_size: int) -> list[str]:
    return [
        cosig["sig_line"]
        for cosig in reference["witness_cosignatures"]
        if cosig["tree_size"] == tree_size
    ]


def export_bundle(ctx: Any, *, extra_receipts: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    """Build an evidence bundle from the CURRENT state of the database.

    This is the honest export: whatever the ledger now says is what goes in the file. The
    proofs are recomputed from the leaves that are actually there, which is exactly what a
    log operator handing over a bundle after a rewrite would produce — a perfectly
    self-consistent artefact that contradicts a root somebody else already holds.
    """
    reference = ctx.reference
    site = ctx.site_code

    # `observed_at` is load-bearing for check 15: it is the clock the MMD deadline is
    # compared against, and stamping every checkpoint with the same value would make a
    # receipt whose leaf never arrived look like a receipt still inside its merge window.
    # The seeded log's real per-size times come from the reference; a checkpoint an attack
    # invented inherits the newest real one, which is the most favourable reading for the
    # attacker and therefore the honest default.
    observed_by_size = {
        int(entry["tree_size"]): str(entry["observed_at"]) for entry in reference["checkpoints"]
    }
    newest_observed = observed_by_size[max(observed_by_size)]
    recorded_by_entry = {
        str(leaf["entry_id"]): str(leaf["recorded_at"]) for leaf in reference["leaves"]
    }

    rows = ctx.sql(
        "SELECT l.seq, l.entry_id::STRING, encode(l.leaf_hash,'hex'), "
        "       encode(l.prev_link_hash,'hex'), encode(l.link_hash,'hex'), "
        "       l.batch_id::STRING, i.entry_kind, i.subject_id::STRING, i.actor, "
        "       i.actor_kind, i.payload::STRING, encode(i.canon_bytes,'hex'), "
        "       i.payload_ver, i.is_sandbox "
        "  FROM mainline.ledger_leaf l "
        "  JOIN mainline.ledger_intake i "
        "    ON i.site_code = l.site_code AND i.entry_id = l.entry_id "
        " WHERE l.site_code = %s ORDER BY l.seq",
        (site,),
    )
    leaves = [
        {
            "actor": row[8],
            "actor_kind": row[9],
            "batch_id": row[5],
            "canon_bytes_b64": base64.b64encode(bytes.fromhex(row[11])).decode("ascii"),
            "entry_id": row[1],
            "entry_kind": row[6],
            "is_sandbox": bool(row[13]),
            "leaf_hash_hex": row[2],
            "link_hash_hex": row[4],
            "payload": json.loads(row[10]),
            "payload_ver": int(row[12]),
            "prev_link_hash_hex": row[3],
            "recorded_at": recorded_by_entry.get(row[1], reference["leaves"][0]["recorded_at"]),
            "seq": int(row[0]),
            "subject_id": row[7],
        }
        for row in rows
    ]
    leaf_hashes = [bytes.fromhex(leaf["leaf_hash_hex"]) for leaf in leaves]

    key_id = _origin_key_id(reference)
    checkpoints: list[dict[str, Any]] = []
    for size, root_hex, body, log_sig_hex, token_hex in ctx.sql(
        "SELECT tree_size, encode(root_hash,'hex'), body, encode(log_sig,'hex'), "
        "       encode(tsa_token,'hex') FROM mainline.ledger_checkpoint "
        " WHERE site_code = %s ORDER BY tree_size",
        (site,),
    ):
        lines = [
            "— {} {}".format(
                reference["origin"],
                base64.b64encode(key_id + bytes.fromhex(log_sig_hex)).decode("ascii"),
            )
        ]
        lines.extend(_witness_lines(reference, int(size)))
        token = bytes.fromhex(token_hex) if token_hex else None
        checkpoints.append(
            {
                "log_key": reference["checkpoints"][0]["log_key"],
                "note": body + "\n" + "\n".join(lines) + "\n",
                "observed_at": observed_by_size.get(int(size), newest_observed),
                "root_hex": root_hex,
                "tree_size": int(size),
                "tsa_tokens": (
                    [
                        {
                            "issuer": "reference-tsa.mainline.example",
                            "token_b64": base64.b64encode(token).decode("ascii"),
                        }
                    ]
                    if token
                    else []
                ),
            }
        )

    sizes = [entry["tree_size"] for entry in checkpoints]
    inclusion_target = max((s for s in sizes if 0 < s <= len(leaves)), default=0)
    inclusion_proofs = []
    if inclusion_target:
        for leaf in leaves[:inclusion_target]:
            path = inclusion_proof(leaf_hashes[:inclusion_target], leaf["seq"], inclusion_target)
            inclusion_proofs.append(
                {
                    "path_hex": [h.hex() for h in path],
                    "seq": leaf["seq"],
                    "tree_size": inclusion_target,
                }
            )

    consistency_proofs = []
    for earlier, later in pairwise(sizes):
        if later > len(leaves):
            continue  # the pair cannot be proved at all; check 3 and check 16 both say so
        path = [] if earlier == 0 else consistency_proof(leaf_hashes[:later], earlier, later)
        consistency_proofs.append(
            {"from_size": earlier, "path_hex": [h.hex() for h in path], "to_size": later}
        )

    # `leaf_seq` binds a closure generation to the leaf that committed it. It is looked up
    # in the LEAVES AS THEY NOW STAND, so an attack that moved or removed the leaf shows up
    # as a closure row pointing at nothing rather than as a quietly plausible integer.
    closure_leaf_seq = {
        (str(leaf["payload"].get("clause_uuid")), int(leaf["payload"].get("closure_gen", -1))): int(
            leaf["seq"]
        )
        for leaf in leaves
        if leaf["entry_kind"] == "closure"
    }
    closure_generations = [
        {
            "ancestor_count": int(count),
            "as_of_commit": commit_hex,
            "clause_uuid": str(clause),
            "closure_gen": int(generation),
            "leaf_seq": closure_leaf_seq.get((str(clause), int(generation)), -1),
            "max_severity": int(severity),
            "truncated": bool(truncated),
        }
        for clause, commit_hex, generation, count, severity, truncated in ctx.sql(
            "SELECT clause_uuid::STRING, encode(as_of_commit,'hex'), closure_gen, "
            "       ancestor_count, max_severity, truncated "
            "  FROM mainline.clause_blame_closure ORDER BY clause_uuid, closure_gen"
        )
    ]

    cosignatures = [
        {
            "adverse": bool(adverse),
            "received_at": reference["witness_cosignatures"][0]["received_at"]
            if reference["witness_cosignatures"]
            else "",
            "sig_line": next((line for line in _witness_lines(reference, int(size))), ""),
            "tree_size": int(size),
            "trust_domain": domain,
            "witness_id": witness,
            "witness_key": reference["witness_cosignatures"][0]["witness_key"]
            if reference["witness_cosignatures"]
            else "",
        }
        for size, witness, domain, adverse in ctx.sql(
            "SELECT tree_size, witness_id, trust_domain, adverse FROM mainline.cosignature "
            " WHERE site_code = %s ORDER BY tree_size, witness_id",
            (site,),
        )
    ]

    return {
        "archive": reference["archive"],
        "bundle_version": 1,
        "canon": reference["canon"],
        "checkpoints": checkpoints,
        "closure_generations": closure_generations,
        "consistency_proofs": consistency_proofs,
        "generated_at": reference["generated_at"],
        "generator": "nemesis export",
        "inclusion_proofs": inclusion_proofs,
        "leaves": leaves,
        # The receipt holder keeps their own copy; an operator cannot delete a signed
        # promise they already handed to somebody else. That asymmetry IS check 15.
        "observed_schema": ctx.capture_triggerdefs(),
        "origin": reference["origin"],
        "receipts": [*reference["receipts"], *extra_receipts],
        "schema_attestations": reference["schema_attestations"],
        "site_code": reference["site_code"],
        "webauthn_assertions": reference["webauthn_assertions"],
        "witness_cosignatures": cosignatures,
    }


# =======================================================================================
# The checks
# =======================================================================================


def _normalise_triggerdef(text: str) -> str:
    """Strip the DATABASE qualifier CockroachDB prepends, keeping schema and object.

    ``pg_get_triggerdef()`` on v26.2.5 returns ``<database>.<schema>.<object>``. The
    database name is a property of where the migration ran, not of the mechanism, so an
    attestation captured in one database must still be comparable with the same trigger in
    another. Nothing else is normalised: the ``:::TYPE`` annotations and the exact
    predicate text stay, because those ARE the mechanism.
    """
    return re.sub(r"\b[A-Za-z_][A-Za-z0-9_$]*\.(mainline\.)", r"\1", text).strip()


class ReferenceChecks:
    """The sixteen checks, run over an exported bundle.

    This is a nemesis-local checker, not a second verifier: every hash, proof and
    canonicalisation below is computed by the shipped algorithms in ``trappoint_ledger``
    and ``trappoint_jcs``, and what is added is the orchestration and the arithmetic that
    ``spec/custody/checks.yaml`` specifies. It exists so the attack matrix can be produced
    from a real run before ``trappoint-verify`` lands, and the matrix names it as the
    verifier that produced the row.
    """

    provenance = "ReferenceChecks (nemesis-local; trappoint_verify not importable)"

    def run(self, bundle: dict[str, Any]) -> VerifierResult:
        result = VerifierResult(provenance=self.provenance)
        leaves = bundle["leaves"]
        leaf_hashes = [bytes.fromhex(leaf["leaf_hash_hex"]) for leaf in leaves]
        roots = {
            int(entry["tree_size"]): bytes.fromhex(entry["root_hex"])
            for entry in bundle["checkpoints"]
        }

        self._check_1(bundle, result)
        self._check_2(bundle, leaf_hashes, roots, result)
        self._check_3(bundle, roots, len(leaves), result)
        self._check_4(bundle, result)
        self._check_5(bundle, result)
        self._check_6(bundle, result)
        self._check_7(bundle, result)
        result.skipped[8] = "offline: --s3 not given; archive metadata is a claim by us"
        self._check_9(bundle, result)
        self._check_10(bundle, result)
        self._check_11(bundle, result)
        self._check_12(bundle, result)
        self._check_13(bundle, result)
        self._check_14(bundle, result)
        self._check_15(bundle, result)
        self._check_16(bundle, roots, result)
        return result

    # -- 1 ------------------------------------------------------------------------------
    def _check_1(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        declared = int(bundle["canon"]["payload_ver"])
        for leaf in bundle["leaves"]:
            canon = base64.b64decode(leaf["canon_bytes_b64"])
            if hash_leaf(canon).hex() != leaf["leaf_hash_hex"]:
                result.findings.append(
                    Finding(1, f"seq {leaf['seq']}: leaf_hash != SHA-256(0x00 || canon_bytes)")
                )
            if int(leaf["payload_ver"]) != declared:
                # Reported under check 10, not check 1: a leaf claiming a canonicaliser the
                # SIGNED checkpoint does not name is the canonicaliser-downgrade signature
                # (A5), and `canon_src_sha256` being inside the signature is what makes it
                # undeniable. Check 1 stays about bytes and their hash.
                result.findings.append(
                    Finding(
                        10,
                        f"seq {leaf['seq']}: payload_ver {leaf['payload_ver']} is not the "
                        f"canonicaliser named by the signed checkpoints ({declared}). No "
                        "verifier has a canonicaliser for it, and the checkpoint that "
                        "covers this leaf never named one",
                    )
                )
                continue
            try:
                recanonicalised = canonicalise_payload(leaf["payload"])
            except Exception as exc:  # noqa: BLE001 — an unencodable payload is a finding
                result.findings.append(Finding(1, f"seq {leaf['seq']}: payload {exc}"))
                continue
            if recanonicalised != canon:
                result.findings.append(
                    Finding(
                        1,
                        f"seq {leaf['seq']}: the human-readable payload disagrees with the "
                        "bytes that were hashed",
                    )
                )

    # -- 2 ------------------------------------------------------------------------------
    def _check_2(
        self,
        bundle: dict[str, Any],
        leaf_hashes: list[bytes],
        roots: dict[int, bytes],
        result: VerifierResult,
    ) -> None:
        for proof in bundle["inclusion_proofs"]:
            size = int(proof["tree_size"])
            index = int(proof["seq"])
            if size not in roots:
                result.findings.append(Finding(2, f"seq {index}: no checkpoint at size {size}"))
                continue
            if index >= len(leaf_hashes):
                result.findings.append(Finding(2, f"seq {index}: leaf is absent from the log"))
                continue
            path = [bytes.fromhex(h) for h in proof["path_hex"]]
            if not verify_inclusion(leaf_hashes[index], index, size, path, roots[size]):
                result.findings.append(
                    Finding(
                        2,
                        f"seq {index}: inclusion proof does not reach the signed root at "
                        f"size {size}",
                    )
                )

    # -- 3 ------------------------------------------------------------------------------
    def _check_3(
        self,
        bundle: dict[str, Any],
        roots: dict[int, bytes],
        leaf_count: int,
        result: VerifierResult,
    ) -> None:
        sizes = sorted(roots)
        proved = {(int(p["from_size"]), int(p["to_size"])) for p in bundle["consistency_proofs"]}
        for earlier, later in pairwise(sizes):
            if (earlier, later) not in proved:
                result.findings.append(
                    Finding(
                        3,
                        f"no consistency proof for the consecutive pair ({earlier}, {later})"
                        + (
                            f"; the log now holds {leaf_count} leaves and cannot produce one"
                            if later > leaf_count
                            else ""
                        ),
                    )
                )
        for proof in bundle["consistency_proofs"]:
            earlier, later = int(proof["from_size"]), int(proof["to_size"])
            path = [bytes.fromhex(h) for h in proof["path_hex"]]
            if not verify_consistency(earlier, roots[earlier], later, roots[later], path):
                result.findings.append(
                    Finding(
                        3,
                        f"the tree at size {earlier} is not a prefix of the tree at size "
                        f"{later}: the log was rewritten behind a root that had already "
                        "left the operator's control",
                    )
                )

    # -- 4 ------------------------------------------------------------------------------
    def _check_4(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        if not CRYPTOGRAPHY_AVAILABLE:
            result.skipped[4] = (
                "no-cryptography: the nemesis environment has no `cryptography`, so no "
                "signature was verified by this run"
            )
            return
        known: dict[str, Any] = {}
        candidates = [bundle["checkpoints"][0]["log_key"]] if bundle["checkpoints"] else []
        candidates += [c["witness_key"] for c in bundle["witness_cosignatures"] if c["witness_key"]]
        for vkey in candidates:
            name, key_hex, encoded = vkey.split("+", 2)
            blob = base64.b64decode(encoded)
            if blob[0] != 0x02:
                result.findings.append(Finding(4, f"{name}: not a C2SP type 0x02 key"))
                continue
            public = _serialization.load_der_public_key(blob[1:])
            if hashlib.sha256(blob[1:]).digest()[:4].hex() != key_hex:
                result.findings.append(Finding(4, f"{name}: key id is not SHA-256(SPKI)[:4]"))
            known[name] = public
        for entry in bundle["checkpoints"]:
            note = entry["note"]
            text, _, signatures = note.rpartition("\n\n")
            signed = (text + "\n").encode("utf-8")
            verified = 0
            for line in signatures.splitlines():
                if not line:
                    continue
                if not line.startswith("— "):
                    result.findings.append(
                        Finding(4, "a signature line does not begin with U+2014 U+0020")
                    )
                    continue
                name, _, encoded = line[2:].rpartition(" ")
                if name not in known:
                    continue  # unknown keys are IGNORED, which is what lets witnesses cosign
                try:
                    known[name].verify(
                        base64.b64decode(encoded)[4:], signed, _ec.ECDSA(_hashes.SHA256())
                    )
                except Exception:  # noqa: BLE001 — every failure is the same finding
                    result.findings.append(
                        Finding(4, f"size {entry['tree_size']}: signature from {name} fails")
                    )
                else:
                    verified += 1
            if verified == 0:
                result.findings.append(
                    Finding(4, f"size {entry['tree_size']}: no known key verified this note")
                )

    # -- 5 ------------------------------------------------------------------------------
    def _check_5(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        """RFC 3161 upper bound, read from the token rather than believed.

        Two properties, and the second is what makes the bracket two-sided: the token's
        ``messageImprint`` must be ``SHA-256(note text)``, and ``genTime`` must not run
        backwards as the tree grows. A larger tree timestamped earlier than a smaller one is
        not a clock problem; it is minted history.
        """
        previous: tuple[int, str] | None = None
        for entry in bundle["checkpoints"]:
            size = int(entry["tree_size"])
            tokens = entry.get("tsa_tokens") or []
            if not tokens:
                result.skipped[5] = f"no-tsa-token: checkpoint at size {size} carries none"
                continue
            token = base64.b64decode(tokens[0]["token_b64"])
            text, _, _ = entry["note"].rpartition("\n\n")
            imprint = hashlib.sha256((text + "\n").encode("utf-8")).digest()
            if imprint not in token:
                result.findings.append(
                    Finding(
                        5,
                        f"size {size}: the RFC 3161 messageImprint is not SHA-256(note "
                        "text) — the note travelling with this token is not the note that "
                        "was timestamped",
                    )
                )
            gen_time = _extract_gen_time(token)
            if gen_time is None:
                result.findings.append(Finding(5, f"size {size}: no genTime in the token"))
                continue
            if previous is not None and gen_time < previous[1]:
                result.findings.append(
                    Finding(
                        5,
                        f"size {size} is timestamped {gen_time}, earlier than the smaller "
                        f"tree at size {previous[0]} ({previous[1]}): history was minted "
                        "and dated backwards",
                    )
                )
            previous = (size, gen_time)

    # -- 6 ------------------------------------------------------------------------------
    def _check_6(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        """Beacon lower bound. The arithmetic half is fully offline and fully checkable."""
        result.skipped[6] = (
            "optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature "
            "are not verified — `cryptography` has no BLS, and the pulse itself is an "
            "online fetch. Only the round->time arithmetic ran"
        )
        for entry in bundle["checkpoints"]:
            size = int(entry["tree_size"])
            text, _, _ = entry["note"].rpartition("\n\n")
            round_number: int | None = None
            for line in text.splitlines():
                if line.startswith("drand: "):
                    parts = line.split()
                    if len(parts) >= 3:
                        round_number = int(parts[2])
            if round_number is None:
                continue
            round_time = DRAND_GENESIS + (round_number - 1) * DRAND_PERIOD_S
            tokens = entry.get("tsa_tokens") or []
            if not tokens:
                continue
            gen_time = _extract_gen_time(base64.b64decode(tokens[0]["token_b64"]))
            if gen_time is None:
                continue
            gen_epoch = _gen_time_epoch(gen_time)
            if round_time > gen_epoch:
                result.findings.append(
                    Finding(
                        6,
                        f"size {size}: the checkpoint quotes drand round {round_number}, "
                        f"issued at {round_time}, which is AFTER the RFC 3161 genTime "
                        f"{gen_epoch} — it quotes a round that did not yet exist",
                    )
                )

    # -- 7 ------------------------------------------------------------------------------
    def _check_7(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        cosignatures = bundle["witness_cosignatures"]
        if not cosignatures:
            result.skipped[7] = "no-witnesses: the bundle carries no cosignature"
            return
        if not any(c["adverse"] for c in cosignatures):
            result.skipped[7] = (
                "not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a "
                "claim about legal interest, not a cryptographic property, and split-view "
                "resistance is NOT claimed"
            )

    # -- 9 ------------------------------------------------------------------------------
    def _check_9(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        previous = GENESIS_LINK_HASH
        for index, leaf in enumerate(bundle["leaves"]):
            if int(leaf["seq"]) != index:
                result.findings.append(
                    Finding(
                        9,
                        f"position {index} holds seq {leaf['seq']}: the sequence is not "
                        "dense. There is no sequence generator in this system, so a gap "
                        "MEANS tampering",
                    )
                )
            if bytes.fromhex(leaf["prev_link_hash_hex"]) != previous:
                result.findings.append(
                    Finding(9, f"seq {leaf['seq']}: prev_link_hash is not the previous link")
                )
            previous = hashlib.sha256(
                bytes.fromhex(leaf["prev_link_hash_hex"]) + bytes.fromhex(leaf["leaf_hash_hex"])
            ).digest()
            if previous.hex() != leaf["link_hash_hex"]:
                result.findings.append(
                    Finding(9, f"seq {leaf['seq']}: link_hash does not recompute")
                )

    # -- 10 -----------------------------------------------------------------------------
    def _check_10(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        ours = canon_src_sha256().hex()
        if bundle["canon"]["canon_src_sha256"] != ours:
            result.findings.append(
                Finding(
                    10,
                    "the bundle names a canonicaliser this verifier is not running "
                    f"({bundle['canon']['canon_src_sha256'][:16]}… vs {ours[:16]}…)",
                )
            )
        for entry in bundle["checkpoints"]:
            text, _, _ = entry["note"].rpartition("\n\n")
            for line in text.splitlines():
                if not line.startswith("canon: "):
                    continue
                version, digest = line.removeprefix("canon: ").split()
                if digest != bundle["canon"]["canon_src_sha256"] or int(version) != int(
                    bundle["canon"]["payload_ver"]
                ):
                    result.findings.append(
                        Finding(
                            10,
                            f"size {entry['tree_size']}: the signed canon line disagrees "
                            "with the bundle's declared canonicaliser",
                        )
                    )

    # -- 11 -----------------------------------------------------------------------------
    def _check_11(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        """The gate is self-attesting: what was sequenced must still be what is running."""
        observed = bundle.get("observed_schema")
        if observed is None:
            result.skipped[11] = "no-live-schema: the bundle carries no observed schema"
            return
        live = {_normalise_triggerdef(text) for text in observed.values()}
        for attestation in bundle["schema_attestations"]:
            definition = attestation["definition"]
            if (
                hashlib.sha256(definition.encode("utf-8")).hexdigest()
                != attestation["definition_sha256_hex"]
            ):
                result.findings.append(
                    Finding(11, f"{attestation['object']}: attested text and hash disagree")
                )
            if _normalise_triggerdef(definition) not in live:
                result.findings.append(
                    Finding(
                        11,
                        f"{attestation['object']}: the mechanism attested at migration "
                        f"{attestation['migration']} is not present and enabled in the live "
                        "catalogue. The exhibit can no longer show the source of the "
                        "mechanism that refused",
                    )
                )

    # -- 12 -----------------------------------------------------------------------------
    def _check_12(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        assertions = bundle.get("webauthn_assertions") or []
        if not assertions:
            result.skipped[12] = "no-assertions"
            return
        if not CRYPTOGRAPHY_AVAILABLE:
            result.skipped[12] = (
                "no-cryptography: the assertion signature was not verified by this run"
            )
            return
        for assertion in assertions:
            client_data = base64.b64decode(assertion["client_data_json_b64"])
            authenticator = base64.b64decode(assertion["authenticator_data_b64"])
            cose = base64.b64decode(assertion["cose_public_key_b64"])
            x = int.from_bytes(cose[-67:-35], "big")
            y = int.from_bytes(cose[-32:], "big")
            public = _ec.EllipticCurvePublicNumbers(x, y, _ec.SECP256R1()).public_key()
            try:
                public.verify(
                    base64.b64decode(assertion["signature_b64"]),
                    authenticator + hashlib.sha256(client_data).digest(),
                    _ec.ECDSA(_hashes.SHA256()),
                )
            except Exception:  # noqa: BLE001
                result.findings.append(
                    Finding(12, "the assertion does not verify against the ENROLLED key")
                )
            inputs = assertion["challenge_inputs"]
            reconstructed = hashlib.sha256(
                bytes.fromhex(inputs["receipt_digest_hex"])
                + str(inputs["check_id"]).encode("utf-8")
                + str(inputs["defeater_code"]).encode("utf-8")
                + bytes.fromhex(inputs["rationale_sha256_hex"])
                + str(inputs["disposition_kind"]).encode("utf-8")
                + str(inputs["gate_epoch"]).encode("ascii")
            ).digest()
            stated = json.loads(client_data)["challenge"]
            expected = base64.urlsafe_b64encode(reconstructed).decode("ascii").rstrip("=")
            if stated != expected:
                result.findings.append(
                    Finding(
                        12,
                        "the challenge does not reconstruct from the exposure receipt: the "
                        "signature is over something other than what was rendered",
                    )
                )

    # -- 13 -----------------------------------------------------------------------------
    def _check_13(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        for leaf in bundle["leaves"]:
            if leaf["is_sandbox"]:
                result.findings.append(
                    Finding(
                        13,
                        f"seq {leaf['seq']}: a sandbox leaf is inside an evidentiary tree",
                    )
                )

    # -- 14 -----------------------------------------------------------------------------
    def _check_14(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        grouped: dict[tuple[str, str], list[tuple[int, int]]] = {}
        for row in bundle["closure_generations"]:
            grouped.setdefault((row["clause_uuid"], row["as_of_commit"]), []).append(
                (int(row["closure_gen"]), int(row["max_severity"]))
            )
        for (clause, commit), rows in sorted(grouped.items()):
            rows.sort()
            if [generation for generation, _ in rows] != list(range(1, len(rows) + 1)):
                result.findings.append(
                    Finding(
                        14,
                        f"{clause}@{commit[:8]}: closure generations are not dense from 1",
                    )
                )
            severities = [severity for _, severity in rows]
            for before, after in pairwise(severities):
                if after < before:
                    result.findings.append(
                        Finding(
                            14,
                            f"{clause}@{commit[:8]}: max_severity fell from {before} to "
                            f"{after}. Every ancestry gate reads this scalar, so a fall "
                            "evaporates weakening gates while coverage views stay green",
                        )
                    )
                    break

    # -- 15 -----------------------------------------------------------------------------
    def _check_15(self, bundle: dict[str, Any], result: VerifierResult) -> None:
        present = {leaf["leaf_hash_hex"] for leaf in bundle["leaves"]}
        newest = max((int(e["tree_size"]) for e in bundle["checkpoints"]), default=0)
        for envelope in bundle["receipts"]:
            receipt = envelope["receipt"]
            if receipt["leaf_hash"] in present:
                continue
            # Inside the MMD this is SKIP(within-mmd) with the deadline printed. Every
            # checkpoint in this fixture is minutes old, so any missing leaf is outside it.
            result.findings.append(
                Finding(
                    15,
                    f"receipt {receipt['entry_id']} promised leaf "
                    f"{receipt['leaf_hash'][:16]}… within {receipt['mmd_seconds']} s and the "
                    f"log's newest checkpoint is at size {newest} without it. This is log "
                    "misbehaviour, and the holder of the receipt can prove it without us",
                )
            )

    # -- 16 -----------------------------------------------------------------------------
    def _check_16(
        self, bundle: dict[str, Any], roots: dict[int, bytes], result: VerifierResult
    ) -> None:
        leaves = bundle["leaves"]
        for entry in bundle["checkpoints"]:
            text, _, _ = entry["note"].rpartition("\n\n")
            lines = text.splitlines()
            if len(lines) < 3:
                result.findings.append(Finding(16, "a checkpoint note has fewer than 3 lines"))
                continue
            if int(lines[1]) != int(entry["tree_size"]):
                result.findings.append(
                    Finding(16, "a checkpoint's index tree_size disagrees with its own note")
                )
            if base64.b64decode(lines[2]).hex() != entry["root_hex"]:
                result.findings.append(
                    Finding(16, "a checkpoint's index root disagrees with its own note")
                )
            size = int(entry["tree_size"])
            if size > len(leaves):
                result.findings.append(
                    Finding(
                        16,
                        f"a checkpoint commits to {size} leaves and the bundle carries "
                        f"{len(leaves)}: entries that were once in the log are not here",
                    )
                )
            covered = [bytes.fromhex(x["leaf_hash_hex"]) for x in leaves[:size]]
            expected = merkle_tree_hash(covered) if size else EMPTY_ROOT
            if size <= len(leaves) and expected != roots[size]:
                result.findings.append(
                    Finding(
                        16,
                        f"the leaves in this bundle do not hash to the signed root at size {size}",
                    )
                )
        proved = {int(p["seq"]) for p in bundle["inclusion_proofs"]}
        target = max((int(p["tree_size"]) for p in bundle["inclusion_proofs"]), default=0)
        for leaf in leaves[:target]:
            if int(leaf["seq"]) not in proved:
                result.findings.append(Finding(16, f"seq {leaf['seq']} has no inclusion proof"))


#: The ``code`` and ``reason`` tokens ``trappoint-verify`` uses for a check whose module has
#: not landed. Those are the only SKIPs the local fallback may answer: a check that ran and
#: chose to skip (``offline``, ``no-witnesses``, ``within-mmd``) has looked and decided, and
#: overriding its decision would be substituting our opinion for the verifier's.
_NOT_IMPLEMENTED_TOKENS = frozenset({"not-implemented", "no-runner", "unbound"})


class TrappointVerifyAdapter:
    """Run the shipped verifier, and fill only the checks it has no runner for.

    The composition is deliberate and it is reported on the matrix's face. Where
    ``trappoint-verify`` has a runner, its verdict is the verdict — it is the artefact a
    stranger runs and no local opinion may overrule it. Where a check module has not landed
    it reports ``SKIP(not-implemented)``, and a matrix that let that stand would show an
    attack as undetected when the design's answer to it simply has not shipped yet. So for
    exactly those ids, :class:`ReferenceChecks` answers, and every row records which side
    produced it.
    """

    def __init__(self, bundle_module: Any, checks_module: Any, version: str) -> None:
        self._bundle = bundle_module
        self._checks = checks_module
        self._load_report = checks_module.load_all()
        self._version = version
        self._fallback = ReferenceChecks()
        self.provenance = f"trappoint-verify {version}"

    def run(self, bundle: dict[str, Any]) -> VerifierResult:
        try:
            parsed = self._bundle.loads_bundle(json.dumps(bundle), subject="nemesis export")
        except Exception as exc:  # noqa: BLE001 — an unusable bundle is itself the finding
            result = VerifierResult(provenance=f"{self.provenance} (bundle rejected)")
            result.findings.append(Finding(16, f"the exported bundle is unusable: {exc}"))
            return result

        report = self._checks.run_all(parsed, tool_version=self._version)
        local = self._fallback.run(bundle)
        result = VerifierResult(provenance=self.provenance)
        delegated: list[int] = []

        for outcome in report.outcomes:
            check_id = int(outcome.check_id)
            verdict = str(outcome.verdict)
            if verdict == "FAIL":
                result.findings.append(Finding(check_id, f"{outcome.headline} [{outcome.code}]"))
                continue
            if verdict == "SKIP" and str(outcome.reason) in _NOT_IMPLEMENTED_TOKENS:
                delegated.append(check_id)
                result.findings.extend(f for f in local.findings if f.check == check_id)
                if check_id in local.skipped:
                    result.skipped[check_id] = (
                        f"{local.skipped[check_id]} [nemesis-local fallback; "
                        f"trappoint-verify has no runner for check {check_id} yet]"
                    )
                elif not any(f.check == check_id for f in local.findings):
                    result.skipped[check_id] = (
                        "not-implemented in trappoint-verify, and the nemesis-local "
                        "fallback found nothing to report"
                    )
                continue
            if verdict == "SKIP":
                result.skipped[check_id] = str(outcome.reason)

        if delegated:
            result.provenance = (
                f"{self.provenance}; checks {', '.join(map(str, delegated))} answered by the "
                "nemesis-local fallback because no runner has landed for them"
            )
        return result


def build_verifier() -> Any:
    """Prefer the shipped verifier; fall back to :class:`ReferenceChecks`, and say which."""
    try:
        import trappoint_verify  # type: ignore[import-not-found]
        from trappoint_verify import bundle as bundle_module  # type: ignore[import-not-found]
        from trappoint_verify import checks as checks_module  # type: ignore[import-not-found]
    except ImportError:
        return ReferenceChecks()
    required = (
        getattr(bundle_module, "loads_bundle", None),
        getattr(checks_module, "run_all", None),
        getattr(checks_module, "load_all", None),
    )
    if not all(callable(entry) for entry in required):
        # Refuse to guess at an API. A harness that half-called the verifier and reported
        # the result as the verifier's would be worse than one that did not call it at all.
        return ReferenceChecks()
    return TrappointVerifyAdapter(
        bundle_module, checks_module, str(getattr(trappoint_verify, "__version__", "0.0.0"))
    )


# =======================================================================================
# Small DER helpers, used only to read back what a TSA already signed
# =======================================================================================


def _extract_gen_time(token: bytes) -> str | None:
    """Return the ``genTime`` string from a DER ``TimeStampToken``, or ``None``.

    A GeneralizedTime is tag ``0x18``; a TSTInfo carries exactly one. Scanning for the tag
    with a plausible length and a ``Z`` terminator is enough to read a value out of a token
    this suite minted itself, and it is deliberately NOT a general ASN.1 parser — CU-8 puts
    that inside ``trappoint-verify``, where hostile input actually arrives.
    """
    index = 0
    while index < len(token) - 2:
        if token[index] == 0x18:
            length = token[index + 1]
            if 13 <= length <= 20:
                candidate = token[index + 2 : index + 2 + length]
                if candidate.endswith(b"Z") and candidate[:8].isdigit():
                    return candidate.decode("ascii")
        index += 1
    return None


def _gen_time_epoch(gen_time: str) -> int:
    import datetime as _dt

    # ``YYYYMMDDHHMMSS`` is fourteen characters; the trailing ``Z`` and any fractional part
    # are not part of the format string.
    return int(
        _dt.datetime.strptime(gen_time[:14], "%Y%m%d%H%M%S").replace(tzinfo=_dt.UTC).timestamp()
    )


# =======================================================================================
# Running one attack
# =======================================================================================


REGISTRY: dict[str, tuple[str, str]] = {
    "A1": ("delete_and_relink", "T1"),
    "A2": ("renumber_only", "T1"),
    "A3": ("payload_substitute", "T1"),
    "A4": ("canon_substitute", "T1"),
    "A5": ("canon_version_downgrade", "T1"),
    "A6": ("fork", "T1"),
    "A7": ("checkpoint_swap", "T4"),
    "A8": ("backdate_forward", "T4"),
    "A9": ("backdate_backward", "T4"),
    "A10": ("closure_mass_rewrite", "T1"),
    "A11": ("prev_digest_forgery", "T1"),
    "A12": ("sandbox_smuggle", "T0"),
    "A13": ("trigger_disable", "T1"),
    "A14": ("receipt_orphan", "T1"),
    "A15": ("object_lock_downgrade", "T2"),
}


def run_attack(
    ctx: Any,
    attack_id: str,
    mutate: Callable[[Any], dict[str, Any]],
) -> AttackOutcome:
    """Execute one attack, export, verify, and time the detection.

    ``mutate`` performs the SQL and returns a dict with optional ``refusals`` (database
    refusals observed on the way, which are themselves part of the defence) and
    ``extra_receipts``. Latency is measured from the moment the mutation commits to the
    moment the first finding exists, because that is what a reader of the matrix is asking:
    *how long after the attack would somebody know?*
    """
    name, tier = REGISTRY[attack_id]
    detail = mutate(ctx)
    started = time.perf_counter()
    bundle = export_bundle(ctx, extra_receipts=detail.get("extra_receipts", ()))
    verifier = build_verifier()
    result = verifier.run(bundle)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return AttackOutcome(
        id=attack_id,
        name=name,
        tier=tier,
        ran=True,
        detected_by=result.detecting_checks,
        detection_latency_ms=elapsed_ms if result.findings else None,
        verifier=result.provenance,
        database_refusals=list(detail.get("refusals", [])),
        findings=[f"check {f.check}: {f.detail}" for f in result.findings][:6],
        skipped_checks={str(k): v for k, v in sorted(result.skipped.items())},
        note=str(detail.get("note", "")),
    )


def skipped_attack(attack_id: str, reason: str, note: str = "") -> AttackOutcome:
    name, tier = REGISTRY[attack_id]
    return AttackOutcome(
        id=attack_id,
        name=name,
        tier=tier,
        ran=False,
        detected_by=[],
        detection_latency_ms=None,
        verifier="not run",
        skipped_reason=reason,
        note=note,
    )


def expect_refusal(ctx: Any, statement: str, params: tuple[Any, ...] = ()) -> str | None:
    """Run a statement that SHOULD be refused; return the refusal, or ``None`` if it was not.

    ``None`` is itself a result and the caller records it. A nemesis harness that asserted
    "the database refused" and stopped would never observe the case this product is honest
    about: some bypasses succeed, and the answer to those is detection, not denial.
    """
    try:
        ctx.sql(statement, params)
    except Exception as exc:  # noqa: BLE001 — any refusal is the observation
        state = getattr(exc, "sqlstate", None)
        return f"{state or type(exc).__name__}: {str(exc).splitlines()[0]}"
    return None


# =======================================================================================
# The fifteen mutations
# =======================================================================================


def a1_delete_and_relink(ctx: Any) -> dict[str, Any]:
    """THE attack. Delete leaf k, renumber k+1..n, recompute every link_hash in one UPDATE.

    Afterwards the table is *perfectly self-consistent*: `seq` is dense, every `link_hash`
    recomputes from its predecessor, and every in-database integrity check passes. This is
    why gap-freedom is only evidence once an independent party already holds a commitment
    to the head — and it is why check 3 exists.
    """
    site, victim = ctx.site_code, 40
    refusals = [
        expect_refusal(
            ctx,
            "DELETE FROM mainline.ledger_leaf WHERE site_code = %s AND seq = %s",
            (site, victim),
        )
    ]
    if refusals[0] is None:
        # No append-only trigger guards mainline.ledger_leaf today, so the delete SUCCEEDS.
        # Recorded rather than hidden: the design's answer to T1 is external commitment, not
        # a trigger a DBA can drop — but the absence is worth an operator knowing about.
        ctx.sql(
            "DELETE FROM mainline.ledger_leaf WHERE site_code = %s AND seq = %s", (site, victim)
        )
    ctx.sql(
        "UPDATE mainline.ledger_leaf SET seq = seq - 1 WHERE site_code = %s AND seq > %s",
        (site, victim),
    )
    _relink(ctx)
    return {
        "refusals": [r for r in refusals if r],
        "note": (
            "the ledger table is left perfectly self-consistent: dense seq, every link_hash "
            "recomputes. Nothing inside the database can see it"
        ),
    }


def _relink(ctx: Any) -> None:
    """Recompute the whole link chain in the database, as a rogue DBA would.

    One recursive CTE, then one UPDATE. CockroachDB v26.2.5 runs both — measured, not
    assumed — which is precisely why this attack is the one the design exists for.
    """
    ctx.sql(
        """
        WITH RECURSIVE ordered AS (
          SELECT seq, leaf_hash FROM mainline.ledger_leaf WHERE site_code = %s
        ), chain(seq, prev_link_hash, link_hash) AS (
          SELECT o.seq,
                 '\\x0000000000000000000000000000000000000000000000000000000000000000'::BYTES,
                 digest('\\x0000000000000000000000000000000000000000000000000000000000000000'::BYTES
                        || o.leaf_hash, 'sha256')
            FROM ordered o WHERE o.seq = 0
          UNION ALL
          SELECT o.seq, c.link_hash, digest(c.link_hash || o.leaf_hash, 'sha256')
            FROM chain c JOIN ordered o ON o.seq = c.seq + 1
        )
        UPDATE mainline.ledger_leaf AS l
           SET prev_link_hash = c.prev_link_hash, link_hash = c.link_hash
          FROM chain c
         WHERE l.site_code = %s AND l.seq = c.seq
        """,
        (ctx.site_code, ctx.site_code),
    )


def a2_renumber_only(ctx: Any) -> dict[str, Any]:
    """Close the gap a delete left, and forget to re-link — the lazy A1, and the one a bug writes.

    Shifting *downward* into vacated numbers is the only direction that does not collide
    with ``ledger_leaf_pkey`` row by row, which is itself worth knowing: the primary key
    makes the careless version of this attack fail loudly, and the careful version is A1.
    """
    site = ctx.site_code
    ctx.sql("DELETE FROM mainline.ledger_leaf WHERE site_code = %s AND seq = 30", (site,))
    ctx.sql(
        "UPDATE mainline.ledger_leaf SET seq = seq - 1 WHERE site_code = %s AND seq > 30",
        (site,),
    )
    return {
        "note": (
            "seq is dense again and every prev_link_hash now points at the wrong "
            "predecessor. No re-linking was attempted, which is what separates this from A1"
        )
    }


def a3_payload_substitute(ctx: Any) -> dict[str, Any]:
    """Swap what a human reads, leave what a machine hashed."""
    ctx.sql(
        "UPDATE mainline.ledger_intake SET payload = "
        "jsonb_set(payload, ARRAY['entry_kind'], '\"advisory\"'::JSONB) "
        "WHERE entry_id = (SELECT entry_id FROM mainline.ledger_leaf "
        "                   WHERE site_code = %s AND seq = 8)",
        (ctx.site_code,),
    )
    return {
        "note": (
            "the console would show 'advisory' where the tree commits to 'disposition': the "
            "exhibit and the proof would describe different documents"
        )
    }


def a4_canon_substitute(ctx: Any) -> dict[str, Any]:
    """Swap the bytes AND the leaf hash together, so check 1 passes.

    This is the sophisticated version, and it is the one that shows why a chain is not
    enough: everything internal recomputes. Only a root that left our control disagrees.
    """
    forged_payload = {
        "check_id": "00000000-0000-4000-8000-000000000000",
        "disposition_kind": "controlled",
        "entry_kind": "disposition",
        "issued_at": "2026-08-07T02:00:00.000Z",
        "signer_rank": 9,
        "signer_sub": "auth0|forged",
        "site_code": ctx.site_code,
    }
    canon = canonicalise_payload(forged_payload)
    leaf = hash_leaf(canon)
    entry = ctx.sql(
        "SELECT entry_id FROM mainline.ledger_leaf WHERE site_code = %s AND seq = 8",
        (ctx.site_code,),
    )[0][0]
    ctx.sql(
        "UPDATE mainline.ledger_intake SET payload = %s, canon_bytes = %s, leaf_hash = %s "
        "WHERE entry_id = %s",
        (json.dumps(forged_payload), canon, leaf, entry),
    )
    ctx.sql(
        "UPDATE mainline.ledger_leaf SET leaf_hash = %s WHERE site_code = %s AND seq = 8",
        (leaf, ctx.site_code),
    )
    _relink(ctx)
    return {"note": "check 1 passes: the bytes and the hash agree. They agree about a lie"}


def a5_canon_version_downgrade(ctx: Any) -> dict[str, Any]:
    """Re-canonicalise an old leaf under a different `payload_ver`, to make new bytes legal."""
    entry = ctx.sql(
        "SELECT entry_id FROM mainline.ledger_leaf WHERE site_code = %s AND seq = 12",
        (ctx.site_code,),
    )[0][0]
    ctx.sql("UPDATE mainline.ledger_intake SET payload_ver = 2 WHERE entry_id = %s", (entry,))
    return {
        "note": (
            "the leaf now claims a canonicaliser the signed checkpoint does not name; "
            "canon_src_sha256 is inside the signature, so the downgrade cannot be hidden"
        )
    }


def a6_fork(ctx: Any) -> dict[str, Any]:
    """Two leaves claiming the same head. Unweld one constraint at a time, then both.

    Refusal depth 2 in the database: ``ledger_leaf_pkey`` and ``ledger_linear``. The point
    of dropping them one at a time is that a defence proven only with everything switched on
    has not been proven at all.
    """
    site = ctx.site_code
    last_seq, fork_point = ctx.sql(
        "SELECT seq, prev_link_hash FROM mainline.ledger_leaf "
        " WHERE site_code = %s ORDER BY seq DESC LIMIT 1",
        (site,),
    )[0]
    fork_point = bytes(fork_point)
    donor, forged_hash = _spare_entry(ctx, "fork")

    def attempt(seq: int) -> str | None:
        return expect_refusal(
            ctx,
            "INSERT INTO mainline.ledger_leaf "
            "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                site,
                seq,
                donor,
                forged_hash,
                fork_point,
                hashlib.sha256(fork_point + forged_hash).digest(),
                str(uuid.uuid4()),
            ),
        )

    # Unweld one mechanism at a time. A defence proven only with everything switched on has
    # not been proven at all — the whole point of refusal depth is that each layer refuses
    # ALONE.
    refusals = [f"both constraints armed, colliding seq -> {attempt(int(last_seq))}"]

    ctx.sql("ALTER TABLE mainline.ledger_leaf DROP CONSTRAINT ledger_linear")
    refusals.append(f"ledger_linear dropped, ledger_leaf_pkey alone -> {attempt(int(last_seq))}")
    ctx.sql(
        "ALTER TABLE mainline.ledger_leaf "
        "ADD CONSTRAINT ledger_linear UNIQUE (site_code, prev_link_hash)"
    )
    refusals.append(f"ledger_linear alone, fresh seq -> {attempt(int(last_seq) + 1)}")

    # Both unwelded: the fork lands, and the verifier catches what the database no longer
    # does. Two leaves now claim the same predecessor.
    ctx.sql("ALTER TABLE mainline.ledger_leaf DROP CONSTRAINT ledger_linear")
    ctx.sql(
        "INSERT INTO mainline.ledger_leaf "
        "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (
            site,
            int(last_seq) + 1,
            donor,
            forged_hash,
            fork_point,
            hashlib.sha256(fork_point + forged_hash).digest(),
            str(uuid.uuid4()),
        ),
    )
    return {
        "refusals": [r for r in refusals if not r.endswith("None")],
        "note": (
            f"two leaves now name the same predecessor {fork_point.hex()[:16]}…, which is "
            "two histories with one past. Refusal depth 2 held until BOTH constraints were "
            "dropped; at verify time the fork is a single-detector finding, because the "
            "forked leaf sits beyond the newest checkpoint and no proof covers it yet — "
            "which is exactly the ~60 s window this design states rather than denies"
        ),
    }


def _spare_entry(ctx: Any, label: str) -> tuple[str, bytes]:
    """Insert an unsequenced intake row and return its id and leaf hash."""
    payload = {"entry_kind": "advisory", "note": label, "site_code": ctx.site_code}
    canon = canonicalise_payload(payload)
    leaf = hash_leaf(canon)
    entry_id = str(uuid.uuid4())
    ctx.sql(
        "INSERT INTO mainline.ledger_intake "
        "(entry_id, site_code, entry_kind, subject_id, actor, actor_kind, payload, "
        " canon_bytes, payload_ver, leaf_hash, hlc) "
        "VALUES (%s,%s,'advisory',%s,'attacker','external',%s,%s,1,%s,9999)",
        (entry_id, ctx.site_code, str(uuid.uuid4()), json.dumps(payload), canon, leaf),
    )
    return entry_id, leaf


FIXTURE_LOG_KEY = (
    __import__("pathlib").Path(__file__).resolve().parents[4]
    / "evidence"
    / "reference-ledger"
    / "keys"
    / "reference-log.NOT-SECRET.key.pem"
)


def _resign(ctx: Any, tree_size: int, body: str) -> str | None:
    """Re-sign a mutated checkpoint body with the fixture log key — the T4 model.

    A7, A8 and A9 are **T4** attacks: the cloud-org admin colluding with the signer. Their
    whole premise is that the signature is not the obstacle. A harness that could not
    re-sign would leave check 4 firing on a broken signature, and the matrix would then
    credit the log signature with a detection a real T4 adversary would never hand it — the
    attack would look better defended than it is.

    The fixture log key is committed and published by design (CU-6), so modelling this
    faithfully costs nothing. Returns ``None`` when ``cryptography`` is unavailable, and the
    caller records that the run's A7/A8/A9 rows are optimistic by exactly one check.
    """
    if not CRYPTOGRAPHY_AVAILABLE or not FIXTURE_LOG_KEY.is_file():
        return None
    key = _serialization.load_pem_private_key(FIXTURE_LOG_KEY.read_bytes(), password=None)
    signature = key.sign(body.encode("utf-8"), _ec.ECDSA(_hashes.SHA256()))
    ctx.sql(
        "UPDATE mainline.ledger_checkpoint SET log_sig = %s "
        " WHERE site_code = %s AND tree_size = %s",
        (signature, ctx.site_code, tree_size),
    )
    return "re-signed with the committed fixture log key (T4: the signer is complicit)"


def a7_checkpoint_swap(ctx: Any) -> dict[str, Any]:
    """Replace a checkpoint body with a self-consistent one over a different tree.

    T4: the adversary holds the signing key, so the *signature* is not the obstacle. The
    obstacle is a timestamp somebody else issued over the note that used to be there.
    """
    site = ctx.site_code
    size, body = ctx.sql(
        "SELECT tree_size, body FROM mainline.ledger_checkpoint "
        " WHERE site_code = %s AND tree_size = 50",
        (site,),
    )[0]
    forged_root = hashlib.sha256(b"a different tree entirely").digest()
    lines = body.splitlines()
    lines[2] = base64.b64encode(forged_root).decode("ascii")
    forged_body = "\n".join(lines) + "\n"
    ctx.sql(
        "UPDATE mainline.ledger_checkpoint SET body = %s, root_hash = %s "
        " WHERE site_code = %s AND tree_size = %s",
        (forged_body, forged_root, site, size),
    )
    resigned = _resign(ctx, int(size), forged_body)
    return {
        "note": (
            "internally self-consistent and signed by the right key"
            + (f" — {resigned}" if resigned else _UNSIGNED_CAVEAT)
            + ". The RFC 3161 token is over the note that WAS there, and cannot be "
            "re-minted with yesterday's date"
        )
    }


#: Said out loud rather than left to be inferred: without the key, one of the detections
#: reported for a T4 attack is an artefact of the harness, not of the defence.
_UNSIGNED_CAVEAT = (
    " — NOT re-signed (`cryptography` unavailable), so any check-4 detection reported for "
    "this attack is an artefact of the harness rather than a defence a T4 adversary faces"
)


def a8_backdate_forward(ctx: Any) -> dict[str, Any]:
    """Mint history and claim it existed earlier than the authority saw it.

    Concretely: issue a checkpoint over a LARGER tree and attach the timestamp token of an
    earlier, smaller one. Two independent things then break — the imprint no longer matches
    the note, and a bigger tree is dated before a smaller one.
    """
    site = ctx.site_code
    # The oldest non-empty checkpoint donates its timestamp; the newest donates its shape.
    # Chosen from the log rather than hard-coded, so growing the reference fixture does not
    # silently turn this attack into an IndexError that looks like a passing suite.
    donor_token = ctx.sql(
        "SELECT tsa_token FROM mainline.ledger_checkpoint "
        " WHERE site_code = %s AND tree_size > 0 ORDER BY tree_size ASC LIMIT 1",
        (site,),
    )[0][0]
    template = ctx.sql(
        "SELECT body, encode(log_sig,'hex'), canon_src_sha256, tree_size "
        "  FROM mainline.ledger_checkpoint "
        " WHERE site_code = %s ORDER BY tree_size DESC LIMIT 1",
        (site,),
    )[0]
    minted_size = int(template[3]) + 24
    lines = template[0].splitlines()
    lines[1] = str(minted_size)
    forged_root = hashlib.sha256(f"minted history at size {minted_size}".encode()).digest()
    lines[2] = base64.b64encode(forged_root).decode("ascii")
    forged_body = "\n".join(lines) + "\n"
    ctx.sql(
        "INSERT INTO mainline.ledger_checkpoint "
        "(site_code, tree_size, root_hash, body, beacon, log_sig, tsa_token, canon_src_sha256) "
        "VALUES (%s, %s, %s, %s, '{}'::JSONB, decode(%s,'hex'), %s, %s)",
        (site, minted_size, forged_root, forged_body, template[1], donor_token, template[2]),
    )
    resigned = _resign(ctx, minted_size, forged_body)
    return {
        "note": (
            f"a {minted_size}-leaf tree carrying the timestamp of the log's first checkpoint"
            + (f", {resigned}" if resigned else _UNSIGNED_CAVEAT)
            + ". The authority is not ours and will not re-date anything"
        )
    }


def a9_backdate_backward(ctx: Any) -> dict[str, Any]:
    """Claim a checkpoint existed BEFORE the beacon round it quotes.

    The lower half of the bracket. The adversary edits the drand line to a round that had
    not been issued when the token says the note was timestamped, which is arithmetic and
    needs no key at all to catch.
    """
    site = ctx.site_code
    body = ctx.sql(
        "SELECT body FROM mainline.ledger_checkpoint WHERE site_code = %s AND tree_size = 34",
        (site,),
    )[0][0]
    lines = []
    for line in body.splitlines():
        if line.startswith("drand: "):
            chain_hash, round_number, value = line.removeprefix("drand: ").split()
            lines.append(f"drand: {chain_hash} {int(round_number) + 200000} {value}")
        else:
            lines.append(line)
    forged_body = "\n".join(lines) + "\n"
    ctx.sql(
        "UPDATE mainline.ledger_checkpoint SET body = %s WHERE site_code = %s AND tree_size = 34",
        (forged_body, site),
    )
    resigned = _resign(ctx, 34, forged_body)
    return {
        "note": (
            "the quoted round is issued ~7 days after the note was timestamped"
            + (f", and the note was {resigned}" if resigned else _UNSIGNED_CAVEAT)
        )
    }


def a10_closure_mass_rewrite(ctx: Any) -> dict[str, Any]:
    """S2. One UPDATE from a Lambda execution role evaporates every weakening gate."""
    refusal = expect_refusal(
        ctx, "UPDATE mainline.clause_blame_closure SET max_severity = 0 WHERE closure_gen = 2"
    )
    ctx.sql("ALTER TABLE mainline.clause_blame_closure DISABLE TRIGGER append_only")
    ctx.sql("UPDATE mainline.clause_blame_closure SET max_severity = 0 WHERE closure_gen = 2")
    return {
        "refusals": [r for r in [refusal] if r],
        "note": (
            "the append-only trigger refuses the UPDATE; DISABLE TRIGGER succeeds and then "
            "it lands. Every coverage view still reports full coverage"
        ),
    }


def a11_prev_digest_forgery(ctx: Any) -> dict[str, Any]:
    """S9. The chain_digest was computed server-side; its INPUT was not."""
    permit_id = ctx.sql("SELECT permit_id FROM mainline.permit LIMIT 1")[0][0]
    forged = hashlib.sha256(b"a digest of nothing that happened").digest()
    refusal = expect_refusal(
        ctx,
        "INSERT INTO mainline.permit_event "
        "(permit_id, seq, prev_seq, from_state, to_state, actor_sub, payload, prev_digest) "
        "VALUES (%s, 2, 1, 'proposed', 'permitted', 'attacker', '{}'::JSONB, %s)",
        (permit_id, forged),
    )
    ctx.sql("ALTER TABLE mainline.permit_event DISABLE TRIGGER permit_event_chain")
    ctx.sql(
        "INSERT INTO mainline.permit_event "
        "(permit_id, seq, prev_seq, from_state, to_state, actor_sub, payload, prev_digest) "
        "VALUES (%s, 2, 1, 'proposed', 'permitted', 'attacker', '{}'::JSONB, %s)",
        (permit_id, forged),
    )
    return {
        "refusals": [r for r in [refusal] if r],
        "note": (
            "the primary defence is a P0001 refusal, not a verifier finding. Check 11 is "
            "what catches the case where the trigger was removed first"
        ),
    }


def a12_sandbox_smuggle(ctx: Any) -> dict[str, Any]:
    """Land an `is_sandbox = true` leaf inside an evidentiary tree, from the guest surface."""
    entry_id, leaf = _spare_entry(ctx, "sandbox")
    ctx.sql("UPDATE mainline.ledger_intake SET is_sandbox = true WHERE entry_id = %s", (entry_id,))
    site = ctx.site_code
    head, next_seq = ctx.sql(
        "SELECT link_hash, seq + 1 FROM mainline.ledger_leaf "
        " WHERE site_code = %s ORDER BY seq DESC LIMIT 1",
        (site,),
    )[0]
    ctx.sql(
        "INSERT INTO mainline.ledger_leaf "
        "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (
            site,
            next_seq,
            entry_id,
            leaf,
            bytes(head),
            hashlib.sha256(bytes(head) + leaf).digest(),
            str(uuid.uuid4()),
        ),
    )
    return {"note": "a demo write is now inside the tree an inspector would be handed"}


def a13_trigger_disable(ctx: Any) -> dict[str, Any]:
    """Disable the merge gate, then merge a permit that carries an open obligation.

    **The demo beat, and the honest one.** The gate refuses. The raw-SQL bypass refuses.
    ``ALTER TABLE … DISABLE TRIGGER`` SUCCEEDS — measured on CockroachDB v26.2.5 — and the
    merge then lands. Showing the successful bypass is the point: a product that claims
    nothing can be disabled is lying, and one that detects the disabling is telling the
    truth.
    """
    permit_id = ctx.sql("SELECT permit_id FROM mainline.permit LIMIT 1")[0][0]
    refusals = [
        expect_refusal(
            ctx, "UPDATE mainline.permit SET state = 'merged' WHERE permit_id = %s", (permit_id,)
        )
    ]
    ctx.sql("ALTER TABLE mainline.permit DISABLE TRIGGER permit_merge_gate")
    ctx.sql("UPDATE mainline.permit SET state = 'merged' WHERE permit_id = %s", (permit_id,))
    merged = ctx.sql(
        "SELECT state::STRING FROM mainline.permit WHERE permit_id = %s", (permit_id,)
    )[0][0]
    return {
        "refusals": [r for r in refusals if r],
        "note": (
            f"the gate refused; DISABLE TRIGGER succeeded; the permit is now {merged!r} with "
            "an undischarged obligation. The trigger is still in pg_trigger but disabled, "
            "which is exactly the state check 11 has to notice"
        ),
    }


def a14_receipt_orphan(ctx: Any) -> dict[str, Any]:
    """Issue a Signed Disposition Receipt and never sequence its leaf.

    The detection is held by the counterparty, not by us: the signer walks away with a
    signed statement from us that our own log contradicts. That is why one detector is
    tolerable here in a way it would not be anywhere else.
    """
    entry_id, leaf = _spare_entry(ctx, "orphan")
    receipt = {
        "entry_id": entry_id,
        "issued_at": "2026-08-07T02:01:00.000Z",
        "leaf_hash": leaf.hex(),
        "mmd_seconds": MMD_SECONDS,
        "origin": ctx.reference["origin"],
        "payload_ver": 1,
        "site_code": ctx.site_code,
        "typ": "MAINLINE-SDR-v1",
    }
    envelope = {
        "key_id": ctx.reference["receipts"][0]["key_id"],
        "receipt": receipt,
        "sdr_version": 1,
        # The signature is not re-minted here: check 15 is STRUCTURAL (set membership and
        # MMD arithmetic) and check 4 is what verifies an SDR signature, using the same key
        # as the checkpoints. Carrying the donor signature keeps the two checks separate.
        "sig": ctx.reference["receipts"][0]["sig"],
    }
    return {
        "extra_receipts": [envelope],
        "note": "intake accepted it, the sequencer never did, and the holder can prove it",
    }
