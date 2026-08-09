# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Signer protocol, the KMS call shape, and the P-256 verify primitive.

The KMS assertions here are the ones that matter most in this repository, because **AWS
credentials are not valid on the machine MAINLINE is built on**. ``MessageType='RAW'``
and ``SigningAlgorithm='ECDSA_SHA_256'`` are the two parameters the entire custody
argument rests on: get ``MessageType`` wrong and KMS hashes our 446-byte note text a
second time, producing a signature that verifies against nothing anyone can compute; get
``SigningAlgorithm`` wrong and the encoding changes. An in-process fake asserting the
exact keyword set turns both from an intention into a test that runs anywhere.

The subprocess tests at the bottom prove two claims that are made in prose elsewhere and
would otherwise be unfalsifiable: that ``boto3`` is never imported on a path a test
exercises, and that :mod:`trappoint_ledger.note`, :mod:`trappoint_ledger.checkpoint` and
:mod:`trappoint_ledger.merkle` stay importable with ``cryptography`` absent — the
dependency floor ``trappoint-verify`` promises a stranger.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from trappoint_ledger.checkpoint import build_body, build_checkpoint_note, parse_body
from trappoint_ledger.note import decode_note, parse_vkey, verify_note
from trappoint_ledger.signer import (
    KMS_KEY_SPEC,
    KMS_KEY_USAGE,
    KMS_MESSAGE_TYPE,
    KMS_SIGNING_ALGORITHM,
    KmsResponseUnexpected,
    KmsSigner,
    LocalP256Signer,
    Signer,
    p256_sha256_verify,
    public_key_for,
    sign_note_text,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

cryptography = pytest.importorskip(
    "cryptography",
    reason="'cryptography' is not installed. It is NOT a declared dependency of "
    "trappoint-ledger — note, checkpoint and merkle deliberately do not need it — so "
    "the signing tests skip rather than fail. See the dependency-floor tests at the "
    "bottom of this module, which run without it.",
)


def _spec_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "spec" / "wire" / "checkpoint.md"
        if candidate.is_file():
            return candidate
    pytest.skip(f"spec/wire/checkpoint.md was not found above {here}")


SPEC = _spec_path().read_text(encoding="utf-8")


def _pem_block(marker: str) -> bytes:
    start = SPEC.index(f"-----BEGIN {marker}-----")
    end = SPEC.index(f"-----END {marker}-----") + len(f"-----END {marker}-----")
    return (SPEC[start:end] + "\n").encode("ascii")


def _fenced_after(heading: str) -> str:
    section = SPEC.split(heading, 1)[1]
    body = section.split("```", 2)[1]
    return body.split("\n", 1)[1]


PRIVATE_KEY_PEM = _pem_block("PRIVATE KEY")
NOTE_TEXT = _fenced_after("### 7.3 The note text")
VKEY = next(
    line.strip() for line in SPEC.splitlines() if line.startswith("mainline.example/site/BLK-07+")
)
LOG_KEY = parse_vkey(VKEY)
ORIGIN = LOG_KEY.name


@pytest.fixture
def local_signer() -> LocalP256Signer:
    """The deliberately public key from §7.1 — it signs nothing but the document."""
    return LocalP256Signer.from_pem(PRIVATE_KEY_PEM)


class FakeKmsClient:
    """An in-process stand-in for ``boto3.client('kms')`` that records its call shape.

    Every method takes ``**kwargs`` only, exactly as a botocore client does, so a
    positional argument or a stray parameter shows up as a failure rather than being
    absorbed.
    """

    def __init__(
        self,
        signer: LocalP256Signer,
        *,
        echo_algorithm: str = KMS_SIGNING_ALGORITHM,
        key_spec: str = KMS_KEY_SPEC,
        key_usage: str = KMS_KEY_USAGE,
        omit_signature: bool = False,
    ) -> None:
        self.signer = signer
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.echo_algorithm = echo_algorithm
        self.key_spec = key_spec
        self.key_usage = key_usage
        self.omit_signature = omit_signature

    def sign(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("sign", dict(kwargs)))
        message = kwargs["Message"]
        assert isinstance(message, bytes)
        response: dict[str, object] = {
            "KeyId": kwargs["KeyId"],
            "SigningAlgorithm": self.echo_algorithm,
        }
        if not self.omit_signature:
            response["Signature"] = self.signer.sign(message)
        return response

    def get_public_key(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("get_public_key", dict(kwargs)))
        return {
            "KeyId": kwargs["KeyId"],
            "PublicKey": self.signer.public_key_spki_der(),
            "KeySpec": self.key_spec,
            "KeyUsage": self.key_usage,
        }


KEY_ARN = "arn:aws:kms:ap-southeast-2:000000000000:key/11111111-2222-3333-4444-555555555555"


# ── The KMS call shape ─────────────────────────────────────────────────────────────────


def test_kms_sign_is_called_with_raw_and_ecdsa_sha_256_and_nothing_else(local_signer):
    client = FakeKmsClient(local_signer)
    signer = KmsSigner(client, KEY_ARN)
    body = NOTE_TEXT.encode("utf-8")
    signature = signer.sign(body)

    assert len(client.calls) == 1
    name, kwargs = client.calls[0]
    assert name == "sign"
    assert kwargs == {
        "KeyId": KEY_ARN,
        "Message": body,
        "MessageType": "RAW",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }
    assert KMS_MESSAGE_TYPE == "RAW"
    assert KMS_SIGNING_ALGORITHM == "ECDSA_SHA_256"
    assert p256_sha256_verify(LOG_KEY, body, signature)


def test_the_der_signature_is_returned_unmodified(local_signer):
    """CU-3: KMS returns DER, C2SP type 0x02 is DER, so there is no re-encoding step."""
    client = FakeKmsClient(local_signer)
    signature = KmsSigner(client, KEY_ARN).sign(b"anything")
    assert signature[0] == 0x30  # ASN.1 SEQUENCE
    assert signature[1] == len(signature) - 2  # a well-formed DER length, not r‖s padding
    assert signature[2] == 0x02  # first INTEGER: r
    assert len(signature) != 64  # fixed-width r‖s for P-256 is exactly 64 bytes
    assert 8 <= len(signature) <= 72


def test_a_signing_algorithm_echo_that_disagrees_is_refused(local_signer):
    client = FakeKmsClient(local_signer, echo_algorithm="ECDSA_SHA_384")
    with pytest.raises(KmsResponseUnexpected, match="ECDSA_SHA_384"):
        KmsSigner(client, KEY_ARN).sign(b"x")


def test_a_response_with_no_signature_is_refused(local_signer):
    client = FakeKmsClient(local_signer, omit_signature=True)
    with pytest.raises(KmsResponseUnexpected, match="no Signature"):
        KmsSigner(client, KEY_ARN).sign(b"x")


def test_get_public_key_checks_the_key_spec_and_usage_and_caches(local_signer):
    client = FakeKmsClient(local_signer)
    signer = KmsSigner(client, KEY_ARN)
    first = signer.public_key_spki_der()
    second = signer.public_key_spki_der()
    assert first == second == local_signer.public_key_spki_der()
    assert [name for name, _ in client.calls] == ["get_public_key"]
    assert client.calls[0][1] == {"KeyId": KEY_ARN}


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [("key_spec", "ECC_NIST_P384", "KeySpec"), ("key_usage", "ENCRYPT_DECRYPT", "KeyUsage")],
)
def test_a_key_that_cannot_produce_a_conforming_signature_is_refused(
    local_signer, field, value, needle
):
    client = FakeKmsClient(local_signer, **{field: value})
    with pytest.raises(KmsResponseUnexpected, match=needle):
        KmsSigner(client, KEY_ARN).public_key_spki_der()


def test_a_kms_signer_needs_a_key_id(local_signer):
    with pytest.raises(ValueError, match="key ID"):
        KmsSigner(FakeKmsClient(local_signer), "")


def test_kms_and_local_signers_both_satisfy_the_protocol(local_signer):
    assert isinstance(local_signer, Signer)
    assert isinstance(KmsSigner(FakeKmsClient(local_signer), KEY_ARN), Signer)


def test_the_key_id_a_kms_signer_derives_matches_the_spec(local_signer):
    signer = KmsSigner(FakeKmsClient(local_signer), KEY_ARN)
    assert public_key_for(signer, ORIGIN).key_id_hex == LOG_KEY.key_id_hex


# ── The verify primitive ───────────────────────────────────────────────────────────────


def test_the_spec_signature_verifies_against_the_spec_note_text():
    """§10 conformance point 1, at the primitive level."""
    note = decode_note(_fenced_after("### 7.5 The complete note").encode("utf-8"))
    (line,) = note.signatures
    assert p256_sha256_verify(LOG_KEY, note.signed_bytes, line.signature)


def test_a_tampered_message_does_not_verify():
    note = decode_note(_fenced_after("### 7.5 The complete note").encode("utf-8"))
    (line,) = note.signatures
    assert not p256_sha256_verify(LOG_KEY, note.signed_bytes + b"x", line.signature)


@pytest.mark.parametrize("garbage", [b"", b"\x00", b"not der at all", b"\x30\x82\xff\xff"])
def test_a_malformed_signature_returns_false_rather_than_raising(garbage):
    """A signature line is attacker-controlled; an exception here is a crash, not a refusal."""
    assert p256_sha256_verify(LOG_KEY, b"message", garbage) is False


def test_verifying_with_a_non_02_key_is_a_loud_configuration_error():
    from trappoint_ledger.note.keyid import PublicKey

    ed25519 = PublicKey(name="k", algorithm=1, key_material=bytes(32))
    with pytest.raises(ValueError, match="0x01"):
        p256_sha256_verify(ed25519, b"m", b"s")


def test_a_key_whose_material_is_not_a_der_spki_is_a_loud_error():
    from trappoint_ledger.note.keyid import PublicKey

    broken = PublicKey(name="k", algorithm=2, key_material=b"not a spki")
    with pytest.raises(ValueError, match="DER SPKI"):
        p256_sha256_verify(broken, b"m", b"s")


# ── End to end: sign a checkpoint and verify it ────────────────────────────────────────


def test_sign_note_text_produces_a_line_that_verifies(local_signer):
    body = parse_body(NOTE_TEXT)
    text = build_body(body.origin, body.tree_size, body.root_hash, body.extensions)
    line = sign_note_text(local_signer, ORIGIN, text)
    note_bytes = build_checkpoint_note(text, [line])
    result = verify_note(note_bytes, [LOG_KEY], p256_sha256_verify)
    assert result.signed_bytes == NOTE_TEXT.encode("utf-8")
    assert result.verified[0].key_id_hex == LOG_KEY.key_id_hex


def test_ecdsa_is_randomised_so_no_test_may_assert_signature_bytes(local_signer):
    body = NOTE_TEXT.encode("utf-8")
    first = local_signer.sign(body)
    second = local_signer.sign(body)
    assert first != second
    assert p256_sha256_verify(LOG_KEY, body, first)
    assert p256_sha256_verify(LOG_KEY, body, second)


def test_a_generated_signer_round_trips_through_a_note():
    signer = LocalP256Signer.generate()
    key = public_key_for(signer, "mainline.example/site/GEN-01")
    text = build_body(key.name, 0, bytes.fromhex("e3b0c44298fc1c149afbf4c8996fb924" * 2))
    note = build_checkpoint_note(text, [sign_note_text(signer, key.name, text)])
    assert verify_note(note, [key], p256_sha256_verify).verified == (key,)


def test_a_private_key_pem_round_trips(local_signer):
    reloaded = LocalP256Signer.from_pem(local_signer.private_key_pem())
    assert reloaded.public_key_spki_der() == local_signer.public_key_spki_der()


def test_a_non_p256_pem_is_refused():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pem = ec.generate_private_key(ec.SECP384R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with pytest.raises(ValueError, match="secp384r1"):
        LocalP256Signer.from_pem(pem)


# ── Claims that are only worth something as subprocess tests ───────────────────────────

_BLOCKER = """
import sys, importlib.abc

class _Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {names!r}:
            raise ImportError(fullname + " is blocked by the test harness")
        return None

sys.meta_path.insert(0, _Blocked())
for name in list(sys.modules):
    if name.split(".")[0] in {names!r}:
        del sys.modules[name]
"""


def _run_blocked(names: set[str], body: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    script = _BLOCKER.format(names=names) + body
    # A fixed interpreter and an in-repo script string: no shell, no user input.
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_boto3_is_never_imported_on_a_path_a_test_exercises():
    result = _run_blocked(
        {"boto3", "botocore"},
        """
from trappoint_ledger.signer import KmsSigner, KMS_MESSAGE_TYPE

class Fake:
    def sign(self, **kw):
        assert kw["MessageType"] == KMS_MESSAGE_TYPE
        return {"Signature": b"\\x30\\x06", "SigningAlgorithm": kw["SigningAlgorithm"]}

assert KmsSigner(Fake(), "alias/x").sign(b"body") == b"\\x30\\x06"
assert "boto3" not in __import__("sys").modules
print("OK")
""",
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_ledger_still_imports_and_verifies_structure_without_cryptography():
    """The dependency floor, as a 200 ms fact rather than a promise."""
    result = _run_blocked(
        {"cryptography"},
        """
from trappoint_ledger import checkpoint, chain, merkle, note
from trappoint_ledger.signer import SigningBackendUnavailable, p256_sha256_verify
from trappoint_ledger.note.keyid import PublicKey

body = checkpoint.build_body("mainline.example/site/A", 0, merkle.EMPTY_ROOT)
assert checkpoint.parse_body(body).tree_size == 0
assert note.decode_note(body + "\\n\\u2014 k AAAAAWs=\\n").signatures

key = PublicKey(name="k", algorithm=2, key_material=b"spki")
try:
    p256_sha256_verify(key, b"m", b"s")
except SigningBackendUnavailable as exc:
    assert "cryptography" in str(exc)
else:
    raise AssertionError("expected SigningBackendUnavailable")
print("OK")
""",
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
