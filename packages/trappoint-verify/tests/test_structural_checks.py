# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Checks 1, 2, 3, 9, 10, 13, 14, 15 and 16: a passing case and a failing case for each.

PL-2, red before green. For a product whose deliverable is a *refusal*, a suite that has
never been red asserts nothing at all — a check that always returns PASS would pass every
positive test in this file. So every check here is exercised twice: once over a bundle
that is right, and once over a bundle broken in the specific way that check exists to
catch, asserting the specific machine ``code`` it must produce.

Where the fixture comes from
----------------------------
:func:`spec_bundle_dict` is not invented. Its five leaves, their ``canon_bytes``, their
leaf hashes, the link chain, the tree root, the complete signed note and the Signed
Disposition Receipt are **the frozen test vectors** of ``spec/wire/checkpoint.md`` §7 and
``spec/wire/receipt.md`` §5, copied verbatim. That makes this file a conformance test
against the wire format as well as a unit test of this package, and it means a change to
either document breaks it — which is the point of freezing them.

The inclusion and consistency proofs are generated here by a **recursive** implementation
of RFC 6962 §2.1.1 and §2.1.2, deliberately shaped nothing like the iterative verifier in
``checks/structural.py``. Two independent implementations of one RFC disagree loudly when
either is wrong; a shared helper would agree with itself.

:func:`unsigned_bundle_dict` exists for the multi-checkpoint cases. Its notes carry
**placeholder signature bytes that verify against nothing**, because the specification
publishes exactly one genuinely signed note and inventing more would be manufacturing
evidence. It is used only through direct calls to structural runners, never through a full
run, so no signature check is ever pointed at it.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from itertools import pairwise
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_SRC))

from trappoint_verify.bundle import loads_bundle  # noqa: E402
from trappoint_verify.checks import CheckContext, VerifyOptions  # noqa: E402
from trappoint_verify.checks import structural as S  # noqa: E402, N812
from trappoint_verify.report import Verdict  # noqa: E402

EM_DASH = "—"

ORIGIN = "mainline.example/site/BLK-07"
SITE_CODE = "BLK-07"
CANON_SRC_SHA256 = "260ed37ddc610f1fb94ddce98998fe4ae5ce883698ad5c7033839cd258dcd659"
VKEY = (
    "mainline.example/site/BLK-07+e74111d1+AjBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IABM7vTeyUxWuK"
    "0QAmVEOZYl6Cvb48JokLnOw5GETrRwDVysbYDJdybhpWsh3P4IGCNV+7w08nAFuOzYgm6rlc/3c="
)
DRAND_LINE = (
    "drand: 52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971 31088494 "
    "7d045d05caf218eff9f7bafe0acb452b94a8c369d138ce23c4807b4b62ce46c7"
)
NIST_LINE = (
    "nist: 2.0 2.29255654 d7a6237ed272c6c48bfa16552709fa2c564448e263906af4ba6a740aacef3cd4"
    "0431e945cdfcfc855f321c14056ac89a94b47b50472cc92aab890ceafa42baad"
)
CANON_LINE = f"canon: 1 {CANON_SRC_SHA256}"
#: The real signature from ``spec/wire/checkpoint.md`` §7.4, over the size-5 note text.
SIG_B64 = (
    "50ER0TBFAiEA4Eq/KIL+x2nHFWouxjZub5a27EaCfpR9t0fuHS7OKZoCIEBneSLOUaAMsvLSvZ156aNpTCn9"
    "iyEdowXF7ZmFD967"
)

#: ``spec/wire/checkpoint.md`` §7.2 — the five leaves, byte for byte.
CANON_BYTES: tuple[str, ...] = (
    (
        '{"applied_at":"2026-08-07T01:58:00.000Z","entry_kind":"schema",'
        '"migration":"0073_ledger_leaf","site_code":"BLK-07"}'
    ),
    (
        '{"advisory":12,"blocking":2,"candidates":41,"entry_kind":"recall",'
        '"permit_id":"018f3a2e-6c40-7b21-9c55-2a5c9e0f1b77","silenced":27,"site_code":"BLK-07"}'
    ),
    (
        '{"check_id":"018f3a2f-1104-7c88-b3aa-77c1de40e2b1",'
        '"clause_uuid":"018f3a30-2200-7d10-9f31-0c9a4e77bb02","entry_kind":"check_open",'
        '"severity":5,"site_code":"BLK-07","virulence":"blood_fatal"}'
    ),
    (
        '{"check_id":"018f3a2f-1104-7c88-b3aa-77c1de40e2b1","disposition_kind":"controlled",'
        '"entry_kind":"disposition","issued_at":"2026-08-07T02:11:42.006Z","signer_rank":4,'
        '"signer_sub":"auth0|4f2c","site_code":"BLK-07"}'
    ),
    (
        '{"entry_kind":"merge","merged_at":"2026-08-07T02:13:55.417Z","open_blocking":0,'
        '"permit_id":"018f3a2e-6c40-7b21-9c55-2a5c9e0f1b77","site_code":"BLK-07"}'
    ),
)
ENTRY_KINDS = ("schema", "recall", "check_open", "disposition", "merge")
ENTRY_IDS = (
    "018f3a2f-9a01-7e42-8b0d-51f6b2c30d40",
    "018f3a2f-9a01-7e42-8b0d-51f6b2c30d41",
    "018f3a2f-9a01-7e42-8b0d-51f6b2c30d42",
    "018f3a2f-9a01-7e42-8b0d-51f6b2c30d44",
    "018f3a2f-9a01-7e42-8b0d-51f6b2c30d45",
)
CLAUSE_UUID = "018f3a30-2200-7d10-9f31-0c9a4e77bb02"
AS_OF_COMMIT = "018f3a31-0000-7000-8000-000000000001"


# --------------------------------------------------------------------------------------
# RFC 6962 §2.1, generated recursively — the independent half of every proof test
# --------------------------------------------------------------------------------------


def mth(leaves: list[bytes]) -> bytes:
    """RFC 6962 §2.1 Merkle Tree Hash, written as the recurrence the RFC states."""
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    split = _largest_power_of_two_below(len(leaves))
    return hashlib.sha256(b"\x01" + mth(leaves[:split]) + mth(leaves[split:])).digest()


def _largest_power_of_two_below(size: int) -> int:
    split = 1
    while split * 2 < size:
        split *= 2
    return split


def inclusion_path(index: int, leaves: list[bytes]) -> list[bytes]:
    """RFC 6962 §2.1.1 PATH(m, D[n])."""
    if len(leaves) == 1:
        return []
    split = _largest_power_of_two_below(len(leaves))
    if index < split:
        return [*inclusion_path(index, leaves[:split]), mth(leaves[split:])]
    return [*inclusion_path(index - split, leaves[split:]), mth(leaves[:split])]


def consistency_path(first: int, leaves: list[bytes]) -> list[bytes]:
    """RFC 6962 §2.1.2 PROOF(m, D[n])."""
    return _subproof(first, leaves, known=True)


def _subproof(first: int, leaves: list[bytes], *, known: bool) -> list[bytes]:
    if first == len(leaves):
        return [] if known else [mth(leaves)]
    split = _largest_power_of_two_below(len(leaves))
    if first <= split:
        return [*_subproof(first, leaves[:split], known=known), mth(leaves[split:])]
    return [*_subproof(first - split, leaves[split:], known=False), mth(leaves[:split])]


# --------------------------------------------------------------------------------------
# Fixture construction
# --------------------------------------------------------------------------------------


def leaf_hashes() -> list[bytes]:
    """The five spec leaf hashes, recomputed from the spec canon bytes."""
    return [hashlib.sha256(b"\x00" + text.encode("utf-8")).digest() for text in CANON_BYTES]


def link_chain(hashes: list[bytes]) -> list[bytes]:
    """``link_hash[0] = SHA-256(0…0 ‖ leaf_hash[0])``, thereafter chained."""
    chain: list[bytes] = []
    previous = b"\x00" * 32
    for digest in hashes:
        previous = hashlib.sha256(previous + digest).digest()
        chain.append(previous)
    return chain


def note_text(tree_size: int, root: bytes) -> str:
    """The signed note text: origin, size, base64 root, then the three extension lines."""
    return (
        f"{ORIGIN}\n"
        f"{tree_size}\n"
        f"{base64.b64encode(root).decode('ascii')}\n"
        f"{CANON_LINE}\n"
        f"{DRAND_LINE}\n"
        f"{NIST_LINE}\n"
    )


def whole_note(tree_size: int, root: bytes, signature_b64: str) -> str:
    """Note text, the separating blank line, then one signature line."""
    return f"{note_text(tree_size, root)}\n{EM_DASH} {ORIGIN} {signature_b64}\n"


def placeholder_signature(tree_size: int, root: bytes) -> str:
    """A syntactically valid signature line that verifies against nothing (see the docstring)."""
    body = hashlib.sha256(note_text(tree_size, root).encode("utf-8")).digest()
    return base64.b64encode(bytes.fromhex("e74111d1") + b"\x30\x44" + body[:30]).decode("ascii")


def _leaf_entry(index: int, hashes: list[bytes], chain: list[bytes]) -> dict[str, object]:
    return {
        "seq": index,
        "entry_id": ENTRY_IDS[index],
        "entry_kind": ENTRY_KINDS[index],
        "subject_id": "018f3a2f-1104-7c88-b3aa-77c1de40e2b1",
        "payload_ver": 1,
        "canon_bytes_b64": base64.b64encode(CANON_BYTES[index].encode("utf-8")).decode("ascii"),
        "payload": json.loads(CANON_BYTES[index]),
        "leaf_hash_hex": hashes[index].hex(),
        "link_hash_hex": chain[index].hex(),
        "prev_link_hash_hex": (chain[index - 1] if index else b"\x00" * 32).hex(),
        "is_sandbox": False,
        "actor": "auth0|4f2c",
        "actor_kind": "human",
        "recorded_at": "2026-08-07T02:11:42.006Z",
        "batch_id": "018f3a30-9f00-7a11-8c22-4d5e6f708192",
    }


def _closure_rows() -> list[dict[str, object]]:
    return [
        {
            "clause_uuid": CLAUSE_UUID,
            "as_of_commit": AS_OF_COMMIT,
            "closure_gen": generation,
            "max_severity": severity,
            "ancestor_count": 11 * generation,
            "truncated": False,
            "leaf_seq": 2,
        }
        for generation, severity in ((1, 3), (2, 5))
    ]


def _spec_receipt() -> dict[str, object]:
    """The Signed Disposition Receipt envelope from ``spec/wire/receipt.md`` §5, verbatim."""
    return {
        "sdr_version": 1,
        "receipt": {
            "typ": "MAINLINE-SDR-v1",
            "entry_id": "018f3a2f-9a01-7e42-8b0d-51f6b2c30d44",
            "leaf_hash": "7210abaaa02da99e69515827e6b73629f0ebb503fa248214980de321d9d7a103",
            "site_code": "BLK-07",
            "origin": ORIGIN,
            "payload_ver": 1,
            "issued_at": "2026-08-07T02:11:42.310Z",
            "mmd_seconds": 60,
        },
        "key_id": "e74111d1",
        "sig": (
            "MEUCIQDidhgEM1fGO6zlKrLOiDhjJiB+oWA1CZsj1q7qvB9SrAIgSkjGgpMK1fn4W0jg/"
            "LwbYaQgL/tDQWDX1+Jk567u4go="
        ),
    }


def spec_bundle_dict() -> dict[str, object]:
    """The one bundle whose every cryptographic value is published in a frozen spec.

    One checkpoint, at tree size 5, carrying the genuine note and the genuine signature
    from ``spec/wire/checkpoint.md`` §7.5. Check 3 correctly reports
    ``SKIP(single-checkpoint)`` over it: a bundle with one checkpoint has no consecutive
    pair, and saying so is more useful than manufacturing a second one.
    """
    hashes = leaf_hashes()
    chain = link_chain(hashes)
    root = mth(hashes)
    return {
        "bundle_version": 1,
        "generated_at": "2026-08-07T02:15:00.000Z",
        "generator": "trappoint-ledger 0.1.0",
        "origin": ORIGIN,
        "site_code": SITE_CODE,
        "canon": {"payload_ver": 1, "canon_src_sha256": CANON_SRC_SHA256},
        "checkpoints": [
            {
                "tree_size": 5,
                "root_hex": root.hex(),
                "note": whole_note(5, root, SIG_B64),
                "log_key": VKEY,
                "tsa_tokens": [],
                "observed_at": "2026-08-07T02:14:07.481Z",
            }
        ],
        "consistency_proofs": [],
        "leaves": [_leaf_entry(index, hashes, chain) for index in range(5)],
        "inclusion_proofs": [
            {
                "seq": index,
                "tree_size": 5,
                "path_hex": [digest.hex() for digest in inclusion_path(index, hashes)],
            }
            for index in range(5)
        ],
        "receipts": [_spec_receipt()],
        "closure_generations": _closure_rows(),
    }


def unsigned_bundle_dict(sizes: tuple[int, ...] = (2, 4, 5)) -> dict[str, object]:
    """A multi-checkpoint bundle whose notes carry placeholder signatures. Structural use only."""
    hashes = leaf_hashes()
    chain = link_chain(hashes)
    bundle = spec_bundle_dict()
    checkpoints = []
    proofs = []
    for size in sizes:
        root = mth(hashes[:size])
        checkpoints.append(
            {
                "tree_size": size,
                "root_hex": root.hex(),
                "note": whole_note(size, root, placeholder_signature(size, root)),
                "log_key": VKEY,
                "tsa_tokens": [],
                "observed_at": "2026-08-07T02:14:07.481Z",
            }
        )
    for earlier, later in pairwise(sizes):
        proofs.append(
            {
                "from_size": earlier,
                "to_size": later,
                "path_hex": [digest.hex() for digest in consistency_path(earlier, hashes[:later])],
            }
        )
    bundle["checkpoints"] = checkpoints
    bundle["consistency_proofs"] = proofs
    bundle["leaves"] = [_leaf_entry(index, hashes, chain) for index in range(max(sizes))]
    bundle["inclusion_proofs"] = [
        {
            "seq": index,
            "tree_size": max(sizes),
            "path_hex": [digest.hex() for digest in inclusion_path(index, hashes[: max(sizes)])],
        }
        for index in range(max(sizes))
    ]
    return bundle


def context_for(payload: dict[str, object]) -> CheckContext:
    """Load a bundle dict and wrap it in a context with default (offline) options."""
    bundle = loads_bundle(json.dumps(payload), subject="<fixture>")
    return CheckContext(bundle=bundle, options=VerifyOptions())


def mutated(**_unused: object) -> None:  # pragma: no cover - documentation only
    """Fixtures are mutated by ``copy.deepcopy(spec_bundle_dict())`` in each test."""


# --------------------------------------------------------------------------------------
# The RFC 6962 primitives, against the independent generator
# --------------------------------------------------------------------------------------


def test_inclusion_and_consistency_agree_with_a_recursive_rfc6962_generator():
    """Iterative verifier vs recursive generator, over every index of every size to 33."""
    digests = [hashlib.sha256(f"leaf-{index}".encode()).digest() for index in range(33)]
    for size in range(1, 34):
        root = mth(digests[:size])
        for index in range(size):
            path = tuple(inclusion_path(index, digests[:size]))
            assert S.verify_inclusion(digests[index], index, size, path, root)
            assert not S.verify_inclusion(digests[index], index, size, path, bytes(32))
        for first in range(1, size + 1):
            path = tuple(consistency_path(first, digests[:size]))
            assert S.verify_consistency(first, mth(digests[:first]), size, root, path)


def test_verifiers_are_total_on_adversarial_input():
    """Malformed input returns False; it never raises. A traceback is not a verdict."""
    assert not S.verify_inclusion(b"short", 0, 1, (), bytes(32))
    assert not S.verify_inclusion(bytes(32), 5, 1, (), bytes(32))
    assert not S.verify_inclusion(bytes(32), 0, 0, (), bytes(32))
    assert not S.verify_consistency(3, bytes(32), 2, bytes(32), ())
    assert not S.verify_consistency(1, bytes(31), 2, bytes(32), ())
    assert not S.verify_consistency(1, bytes(32), 2, bytes(32), (b"nope",))


def test_empty_tree_root_is_sha256_of_nothing():
    """RFC 6962 §2.1: a log must be able to prove it was empty when it was empty."""
    assert S.empty_root() == hashlib.sha256(b"").digest()
    assert S.verify_consistency(0, S.empty_root(), 4, bytes(32), ())


# --------------------------------------------------------------------------------------
# Check 1 — leaf_hash_recomputation
# --------------------------------------------------------------------------------------


def test_leaf_hash():
    """POSITIVE: every spec leaf hash recomputes from the carried canonical bytes."""
    outcome = S.check_leaf_hash(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "leaf-hashes-recomputed"


def test_leaf_hash_refuses_a_substituted_record():
    """NEGATIVE: one flipped byte of canon_bytes and the leaf hash no longer recomputes."""
    payload = copy.deepcopy(spec_bundle_dict())
    original = base64.b64decode(payload["leaves"][2]["canon_bytes_b64"])
    payload["leaves"][2]["canon_bytes_b64"] = base64.b64encode(
        original.replace(b'"severity":5', b'"severity":1')
    ).decode("ascii")
    outcome = S.check_leaf_hash(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "leaf-hash-mismatch"


def test_leaf_hash_reports_a3_when_the_payload_disagrees_with_the_bytes():
    """NEGATIVE: attack A3 — swap the human-readable payload, leave ``canon_bytes`` alone."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["leaves"][2]["payload"]["severity"] = 1
    outcome = S.check_leaf_hash(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "payload-disagrees-with-canon-bytes"
    assert "A3" in " ".join(outcome.detail)


def test_leaf_hash_refuses_an_unknown_canonicaliser_rather_than_skipping():
    """NEGATIVE: an unheld ``payload_ver`` is a FAIL. A skip would imply we could have looked."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["leaves"][0]["payload_ver"] = 2
    outcome = S.check_leaf_hash(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "unknown-payload-ver"


# --------------------------------------------------------------------------------------
# Check 2 — inclusion_proof
# --------------------------------------------------------------------------------------


def test_inclusion():
    """POSITIVE: five audit paths fold to the signed root."""
    outcome = S.check_inclusion(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "inclusion-verified"


def test_inclusion_refuses_a_corrupted_audit_path():
    """NEGATIVE: one wrong sibling and the fold no longer reaches the root."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["inclusion_proofs"][3]["path_hex"][0] = "00" * 32
    outcome = S.check_inclusion(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "inclusion-proof-failed"


def test_inclusion_refuses_a_missing_proof():
    """NEGATIVE: 'that entry was never in your log' is unanswerable without a proof."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["inclusion_proofs"] = [p for p in payload["inclusion_proofs"] if p["seq"] != 1]
    outcome = S.check_inclusion(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "inclusion-proof-missing"


# --------------------------------------------------------------------------------------
# Check 3 — consistency_proof_every_pair
# --------------------------------------------------------------------------------------


def test_consistency():
    """POSITIVE: every consecutive pair of 2 -> 4 -> 5 verifies."""
    outcome = S.check_consistency(context_for(unsigned_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "consistency-verified"


def test_consistency_refuses_a_missing_pair():
    """NEGATIVE: a gap in the pairs is exactly where a rewritten interval would hide."""
    payload = unsigned_bundle_dict()
    payload["consistency_proofs"] = [
        proof for proof in payload["consistency_proofs"] if proof["from_size"] != 4
    ]
    outcome = S.check_consistency(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "consistency-proof-missing"


def test_consistency_refuses_a_rewritten_interval():
    """NEGATIVE: attack A1 — the chain would recompute; the tree does not."""
    payload = unsigned_bundle_dict()
    payload["consistency_proofs"][0]["path_hex"][0] = "11" * 32
    outcome = S.check_consistency(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "consistency-proof-failed"


def test_consistency_skips_loudly_on_a_single_checkpoint():
    """A bundle with one checkpoint cannot speak to non-omission, and says so."""
    outcome = S.check_consistency(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.SKIP
    assert outcome.reason == "single-checkpoint"


# --------------------------------------------------------------------------------------
# Check 9 — link_chain_and_density
# --------------------------------------------------------------------------------------


def test_link_chain():
    """POSITIVE: the chain recomputes from a 32-zero-byte genesis and ``seq`` is dense."""
    outcome = S.check_link_chain(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "link-chain-recomputed"


def test_link_chain_refuses_a_gap():
    """NEGATIVE: a gap MEANS tampering — no sequence generator exists that could make one."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["leaves"] = [leaf for leaf in payload["leaves"] if leaf["seq"] != 2]
    outcome = S.check_link_chain(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "seq-not-dense"


def test_link_chain_refuses_a_broken_link():
    """NEGATIVE: one rewritten ``link_hash`` and the recomputation diverges."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["leaves"][3]["link_hash_hex"] = "ab" * 32
    outcome = S.check_link_chain(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "link-chain-broken"


def test_link_chain_refuses_a_non_zero_genesis():
    """NEGATIVE: genesis is 32 zero bytes, explicitly, so linearity applies from leaf 0."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["leaves"][0]["prev_link_hash_hex"] = "01" * 32
    outcome = S.check_link_chain(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "link-chain-broken"
    assert "genesis" in " ".join(outcome.detail)


# --------------------------------------------------------------------------------------
# Check 10 — canonicaliser_identity
# --------------------------------------------------------------------------------------


def test_canon_identity():
    """POSITIVE: the vendored canonicaliser hashes to the value the spec and the note pin."""
    outcome = S.check_canon_identity(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "canon-identity-matched"


def test_canon_identity_refuses_a_bundle_that_names_another_canonicaliser():
    """NEGATIVE: the bundle claims bytes this verifier's code could not have produced."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["canon"]["canon_src_sha256"] = "0" * 64
    outcome = S.check_canon_identity(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "canon-source-mismatch"


def test_canon_identity_refuses_a_downgraded_canon_line():
    """NEGATIVE: attack A5 — re-canonicalise under another version; the signed line changes."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["checkpoints"][0]["note"] = payload["checkpoints"][0]["note"].replace(
        CANON_LINE, f"canon: 1 {'f' * 64}"
    )
    outcome = S.check_canon_identity(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "checkpoint-canon-line-mismatch"


# --------------------------------------------------------------------------------------
# Check 13 — no_sandbox_leaf
# --------------------------------------------------------------------------------------


def test_no_sandbox():
    """POSITIVE: no leaf in the spec bundle is a sandbox leaf."""
    outcome = S.check_no_sandbox(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS
    assert outcome.code == "no-sandbox-leaves"


def test_no_sandbox_refuses_a_smuggled_demo_write():
    """NEGATIVE: attack A12 — one sandbox leaf makes every other leaf arguable."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["leaves"][1]["is_sandbox"] = True
    outcome = S.check_no_sandbox(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "sandbox-leaf-present"


# --------------------------------------------------------------------------------------
# Check 14 — closure_generation_monotone
# --------------------------------------------------------------------------------------


def test_closure_monotone():
    """POSITIVE: generations dense from 1, severity non-decreasing."""
    outcome = S.check_closure_monotone(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "closure-monotone"


def test_closure_monotone_refuses_a_mass_rewrite_downward():
    """NEGATIVE: adversarial finding S2 / attack A10 — ``UPDATE … SET max_severity = 0``."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["closure_generations"][1]["max_severity"] = 0
    outcome = S.check_closure_monotone(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "closure-severity-decreased"


def test_closure_monotone_refuses_a_generation_gap():
    """NEGATIVE: the other shape a mass rewrite leaves behind."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["closure_generations"][0]["closure_gen"] = 2
    payload["closure_generations"][1]["closure_gen"] = 3
    outcome = S.check_closure_monotone(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "closure-generation-gap"


def test_closure_monotone_skips_loudly_when_the_section_is_absent():
    """An absent section is a named SKIP, never a quiet pass."""
    payload = copy.deepcopy(spec_bundle_dict())
    del payload["closure_generations"]
    outcome = S.check_closure_monotone(context_for(payload))
    assert outcome.verdict is Verdict.SKIP
    assert outcome.reason == "no-closure-rows"


# --------------------------------------------------------------------------------------
# Check 15 — receipt_coverage
# --------------------------------------------------------------------------------------


def test_receipt_coverage():
    """POSITIVE: the spec receipt's leaf is present and covered by the size-5 checkpoint."""
    outcome = S.check_receipt_coverage(context_for(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "receipts-covered"


def test_receipt_coverage_accuses_the_log_operator_when_the_mmd_expired():
    """NEGATIVE: attack A14 — a signed promise whose leaf never appeared."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["receipts"][0]["receipt"]["leaf_hash"] = "cd" * 32
    outcome = S.check_receipt_coverage(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "receipt-orphaned"
    assert "DID NOT KEEP IT" in " ".join(outcome.detail)


def test_receipt_coverage_skips_inside_the_mmd_with_the_deadline_printed():
    """Inside the MMD the honest verdict is SKIP, with the deadline stated."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["receipts"][0]["receipt"]["leaf_hash"] = "cd" * 32
    payload["receipts"][0]["receipt"]["issued_at"] = "2026-08-07T02:14:00.000Z"
    outcome = S.check_receipt_coverage(context_for(payload))
    assert outcome.verdict is Verdict.SKIP
    assert outcome.reason == "within-mmd"
    assert "2026-08-07T02:15:00" in " ".join(outcome.detail)


def test_receipt_coverage_refuses_a_receipt_from_another_origin():
    """NEGATIVE: a sandbox receipt presented against an evidentiary bundle fails on origin."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["receipts"][0]["receipt"]["origin"] = "mainline.example/site/SANDBOX"
    outcome = S.check_receipt_coverage(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "receipt-malformed"


def test_receipt_coverage_refuses_a_receipt_with_an_extra_member():
    """NEGATIVE: receipt.md §2.1 permits exactly eight members and no others."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["receipts"][0]["receipt"]["note"] = "please ignore the other one"
    outcome = S.check_receipt_coverage(context_for(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "receipt-malformed"


# --------------------------------------------------------------------------------------
# Check 16 — bundle_totality
# --------------------------------------------------------------------------------------


def _totality_context(payload: dict[str, object]) -> CheckContext:
    """Build the context check 16 sees after checks 1..15 have run."""
    base = context_for(payload)
    prior = tuple(
        runner(base)
        for runner in (
            S.check_leaf_hash,
            S.check_inclusion,
            S.check_consistency,
            S.check_link_chain,
            S.check_canon_identity,
            S.check_no_sandbox,
            S.check_closure_monotone,
            S.check_receipt_coverage,
        )
    )
    return CheckContext(
        bundle=base.bundle,
        options=base.options,
        prior=prior,
        selection=(1, 2, 3, 9, 10, 13, 14, 15, 16),
    )


def test_bundle_totality():
    """POSITIVE: index matches note, every leaf is proven, every absence is a named SKIP."""
    outcome = S.check_bundle_totality(_totality_context(spec_bundle_dict()))
    assert outcome.verdict is Verdict.PASS, outcome.detail
    assert outcome.code == "bundle-total"


def test_bundle_totality_refuses_an_index_that_disagrees_with_its_note():
    """NEGATIVE: a bundle whose index disagrees with its contents was not read by its assembler."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["checkpoints"][0]["root_hex"] = "ee" * 32
    outcome = S.check_bundle_totality(_totality_context(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "checkpoint-index-disagrees-with-note"


def test_bundle_totality_refuses_an_unknown_payload_version():
    """NEGATIVE: an unheld canonicaliser is a FAIL, never a SKIP."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["canon"]["payload_ver"] = 7
    outcome = S.check_bundle_totality(_totality_context(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "unknown-payload-ver"


def test_bundle_totality_refuses_a_leaf_with_no_inclusion_proof():
    """NEGATIVE: totality is about the run, not only about the file."""
    payload = copy.deepcopy(spec_bundle_dict())
    payload["inclusion_proofs"] = payload["inclusion_proofs"][:3]
    outcome = S.check_bundle_totality(_totality_context(payload))
    assert outcome.verdict is Verdict.FAIL
    assert outcome.code == "bundle-not-total"


def test_bundle_totality_refuses_a_check_that_produced_no_outcome():
    """NEGATIVE: a silently absent check is the failure this check exists to detect."""
    base = context_for(spec_bundle_dict())
    context = CheckContext(bundle=base.bundle, options=base.options, prior=())
    outcome = S.check_bundle_totality(context)
    assert outcome.verdict is Verdict.FAIL
    assert "produced no outcome at all" in " ".join(outcome.detail)


# --------------------------------------------------------------------------------------
# The loader's own refusals
# --------------------------------------------------------------------------------------


def test_the_loader_refuses_duplicate_json_members():
    """A last-wins loader chooses, on the writer's behalf, which record you are looking at."""
    text = json.dumps(spec_bundle_dict())
    doubled = text.replace(
        '"site_code": "BLK-07"', '"site_code": "BLK-07", "site_code": "OTHER"', 1
    )
    with pytest.raises(Exception, match="appears more than once"):
        loads_bundle(doubled)


def test_the_note_parser_refuses_a_hyphen_where_the_em_dash_belongs():
    """checkpoint.md §2: U+002D or U+2013 here parses as text and verifies against nothing."""
    from trappoint_verify.bundle import parse_note

    hashes = leaf_hashes()
    root = mth(hashes)
    good = parse_note(whole_note(5, root, SIG_B64))
    assert not good.errors, good.errors
    assert good.tree_size == 5
    assert good.root == root
    assert good.extension("canon") == f"1 {CANON_SRC_SHA256}"

    bad = parse_note(whole_note(5, root, SIG_B64).replace(EM_DASH, "-"))
    assert bad.errors


def test_the_note_parser_refuses_a_leading_zero_in_the_tree_size():
    """checkpoint.md §3: ASCII decimal, no leading zeroes, so the text is a function of content."""
    from trappoint_verify.bundle import parse_note

    hashes = leaf_hashes()
    root = mth(hashes)
    note = whole_note(5, root, SIG_B64).replace("\n5\n", "\n05\n", 1)
    assert any("leading zero" in error for error in parse_note(note).errors)
