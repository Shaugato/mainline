# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Signer protocol, a KMS adapter, a local signer, and the verify primitive.

Ruling **CU-3**: the log signature is ECDSA over NIST P-256 with SHA-256 — C2SP
signed-note type ``0x02`` — and **the signature bytes are the ASN.1 DER encoding exactly
as AWS KMS returns them**. No re-encoding to fixed-width ``r‖s``. C2SP defines ``0x02``
as the signatures produced by ``github.com/transparency-dev/witness``, whose verifier
calls Go's ``ecdsa.VerifyASN1``; KMS returns DER for ``ECDSA_SHA_256``; the two agree, so
the correct amount of code between them is none.

Three implementations of one protocol:

:class:`KmsSigner`
    Production. Constructed with an **injected client**, never with a region string and
    never importing ``boto3`` at module scope. That is a testability decision with a
    security consequence: an in-process fake can assert the exact call shape, so
    ``SigningAlgorithm='ECDSA_SHA_256'`` and ``MessageType='RAW'`` are covered by a test
    that runs on a laptop with no AWS credentials, in a repository where AWS credentials
    are not currently valid. A wrong ``MessageType`` would have KMS hash our note text a
    second time and produce a signature that verifies against nothing.

:class:`LocalP256Signer`
    Tests and the reference ledger only. It holds a private key in process, which is
    exactly the property KMS exists to avoid, so it names itself loudly and the reference
    bundle's key is published deliberately (ruling CU-6).

:func:`p256_sha256_verify`
    The verify primitive :func:`trappoint_ledger.note.verify_note` is injected with.

**``cryptography`` is imported lazily, inside the two functions that need it.** The
package declares no dependency on it, so :mod:`trappoint_ledger.note`,
:mod:`trappoint_ledger.checkpoint` and :mod:`trappoint_ledger.merkle` stay importable —
and testable — on the dependency floor ``trappoint-verify`` claims to a stranger. A
missing library raises :class:`SigningBackendUnavailable` with the install line, never an
``ImportError`` from three frames down.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from trappoint_ledger.note.format import SignatureLine, build_signature_line
from trappoint_ledger.note.keyid import ALGORITHM_ECDSA_P256_SHA256, PublicKey

__all__ = [
    "KMS_KEY_SPEC",
    "KMS_KEY_USAGE",
    "KMS_MESSAGE_TYPE",
    "KMS_SIGNING_ALGORITHM",
    "KmsResponseUnexpected",
    "KmsSigner",
    "LocalP256Signer",
    "Signer",
    "SigningBackendUnavailable",
    "p256_sha256_verify",
    "public_key_for",
    "sign_note_text",
]

#: The only signing algorithm MAINLINE's log key is ever asked for.
KMS_SIGNING_ALGORITHM: Final = "ECDSA_SHA_256"

#: ``RAW`` — KMS hashes the message itself. ``DIGEST`` would mean *we* hash the note text
#: and KMS signs that digest; passing the note text under ``DIGEST`` would have KMS treat
#: 446 bytes of text as if it were a SHA-256 digest and produce a signature no verifier
#: on earth accepts. The value is a constant here so it cannot be a parameter anywhere.
KMS_MESSAGE_TYPE: Final = "RAW"

#: What ``GetPublicKey`` must report for a MAINLINE log key.
KMS_KEY_SPEC: Final = "ECC_NIST_P256"
KMS_KEY_USAGE: Final = "SIGN_VERIFY"

_P256_PUBLIC_KEY_CURVE: Final = "secp256r1"


class SigningBackendUnavailable(RuntimeError):
    """A signing or verification backend this build needs is not installed.

    Raised instead of letting an ``ImportError`` escape, because the caller is usually a
    verifier reporting on evidence and "the library is missing" and "the signature is
    invalid" must never be confusable in that report.
    """


class KmsResponseUnexpected(RuntimeError):
    """AWS KMS returned a response that does not match what was asked for.

    Checked rather than assumed. A ``Sign`` response echoes the ``SigningAlgorithm`` it
    actually used; if that echo ever disagreed with what we sent, every checkpoint after
    it would be unverifiable and we would find out from a stranger.
    """


@runtime_checkable
class Signer(Protocol):
    """What the checkpoint and receipt paths need from a signing key."""

    def sign(self, body: bytes) -> bytes:
        """Return the ASN.1 DER ECDSA signature over ``body``.

        ``body`` is the message, not a digest: the implementation is responsible for the
        SHA-256, exactly as ``MessageType='RAW'`` makes KMS responsible for it.
        """
        ...

    def public_key_spki_der(self) -> bytes:
        """Return the DER ``SubjectPublicKeyInfo`` encoding of the public key."""
        ...


def _load_cryptography() -> tuple[Any, Any, Any]:
    """Import ``cryptography`` lazily and report its absence as our own error.

    Returns:
        ``(serialization, ec, hashes)``.

    Raises:
        SigningBackendUnavailable: If ``cryptography`` is not installed.
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError as exc:  # pragma: no cover - exercised only on a floor install
        raise SigningBackendUnavailable(
            "the 'cryptography' package is required to sign or verify a P-256 note "
            "signature and is not installed. trappoint_ledger.note, .checkpoint and "
            ".merkle do not need it and stay importable without it; install "
            "'cryptography>=42' to use LocalP256Signer or p256_sha256_verify."
        ) from exc
    return serialization, ec, hashes


def p256_sha256_verify(key: PublicKey, message: bytes, signature: bytes) -> bool:
    """Verify a C2SP type-``0x02`` signature: ECDSA P-256, SHA-256, DER.

    Conforms to :class:`trappoint_ledger.note.format.SignatureVerifier`: it returns
    ``False`` for an invalid or malformed signature rather than raising, because a
    signature line is attacker-controlled and an exception escaping a verifier turns a
    refusal into a crash report.

    Args:
        key: The public key. Its ``key_material`` is the DER SPKI.
        message: The signed bytes — for a checkpoint, the note text.
        signature: The DER signature, exactly as it came off the wire.

    Returns:
        ``True`` if the signature verifies.

    Raises:
        SigningBackendUnavailable: If ``cryptography`` is absent.
        ValueError: If ``key`` is not a type-``0x02`` key. This is a configuration fault
            in the *verifier*, not a property of the evidence, so it is loud.
    """
    if key.algorithm != ALGORITHM_ECDSA_P256_SHA256:
        raise ValueError(
            f"p256_sha256_verify was given a type-0x{key.algorithm:02x} key; note type "
            "0x01 (Ed25519) needs its own primitive, and silently returning False here "
            "would report a configuration error as a forged signature"
        )
    serialization, ec, hashes = _load_cryptography()
    try:
        public_key = serialization.load_der_public_key(key.key_material)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"key {key.name!r} does not carry a loadable DER SPKI: {exc}") from exc
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        # ValueError, not TypeError: the caller passed a well-typed PublicKey whose
        # key_material decoded to the wrong kind of key. The VALUE is wrong.
        raise ValueError(  # noqa: TRY004
            f"key {key.name!r} is not an elliptic-curve key"
        )
    if public_key.curve.name != _P256_PUBLIC_KEY_CURVE:
        raise ValueError(
            f"key {key.name!r} is on curve {public_key.curve.name!r}, not "
            f"{_P256_PUBLIC_KEY_CURVE!r}; note type 0x02 is P-256 only"
        )
    try:
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    except Exception:  # noqa: BLE001 - see below
        # Deliberately blanket. `cryptography` raises InvalidSignature for a bad
        # signature and ValueError/TypeError for a malformed DER encoding, and both mean
        # exactly one thing to a verifier: this line did not verify. Naming the classes
        # would couple a refusal to a backend's exception taxonomy, and a taxonomy change
        # in a dependency would turn "invalid signature" into a traceback.
        return False
    return True


@dataclass(frozen=True, slots=True)
class LocalP256Signer:
    """A P-256 signer holding its private key in this process.

    **For tests and the reference ledger only.** A software key in a process's memory is
    precisely what ruling CU-3 refuses for production: the rogue-DBA argument rests on a
    T1 adversary with arbitrary SQL having no path to ``kms:Sign``, and a key in a
    Lambda's memory has such a path. ``evidence/reference-ledger`` signs with a key it
    publishes on purpose, so that a stranger can regenerate the bundle — a fixture nobody
    can reproduce is a screenshot.
    """

    private_key: Any
    """A ``cryptography`` ``EllipticCurvePrivateKey`` on P-256."""

    @classmethod
    def from_pem(cls, pem: bytes, password: bytes | None = None) -> LocalP256Signer:
        """Load a signer from a PEM private key.

        Args:
            pem: The PEM bytes.
            password: The passphrase, if the key is encrypted.

        Returns:
            The signer.

        Raises:
            SigningBackendUnavailable: If ``cryptography`` is absent.
            ValueError: If the key is not an unencrypted-or-decryptable P-256 private key.
        """
        serialization, ec, _hashes = _load_cryptography()
        key = serialization.load_pem_private_key(pem, password=password)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            # ValueError for the same reason as in p256_sha256_verify: the argument is
            # bytes of the right type carrying the wrong content.
            raise ValueError(  # noqa: TRY004
                "the PEM does not carry an elliptic-curve private key"
            )
        if key.curve.name != _P256_PUBLIC_KEY_CURVE:
            raise ValueError(
                f"the PEM key is on curve {key.curve.name!r}, not {_P256_PUBLIC_KEY_CURVE!r}"
            )
        return cls(private_key=key)

    @classmethod
    def generate(cls) -> LocalP256Signer:
        """Generate a fresh P-256 key in memory.

        Returns:
            The signer.

        Raises:
            SigningBackendUnavailable: If ``cryptography`` is absent.
        """
        _serialization, ec, _hashes = _load_cryptography()
        return cls(private_key=ec.generate_private_key(ec.SECP256R1()))

    def sign(self, body: bytes) -> bytes:
        """Return the DER ECDSA signature over ``body``.

        ECDSA is randomised: signing the same bytes twice produces different signatures
        that both verify. Nothing in this repository may assert a signature's bytes.
        """
        _serialization, ec, hashes = _load_cryptography()
        signature: bytes = self.private_key.sign(body, ec.ECDSA(hashes.SHA256()))
        return signature

    def public_key_spki_der(self) -> bytes:
        """Return the DER SPKI encoding of the public key."""
        serialization, _ec, _hashes = _load_cryptography()
        der: bytes = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return der

    def private_key_pem(self) -> bytes:
        """Return the unencrypted PKCS#8 PEM of the private key.

        Only the reference ledger calls this, and only for a key that is public by
        design. It exists so that ``evidence/reference-ledger`` can commit the key it
        signed with rather than describing it.
        """
        serialization, _ec, _hashes = _load_cryptography()
        pem: bytes = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return pem


class KmsSigner:
    """Sign with an AWS KMS ``ECC_NIST_P256`` key, over an injected client.

    The client is injected — never constructed here, and ``boto3`` is never imported by
    this module on any path — so the exact call shape is asserted by an in-process fake
    in ``tests/test_signer.py``. That matters more than usual here: MAINLINE is built in
    a repository where AWS credentials are not valid, and "we send ``MessageType='RAW'``"
    would otherwise be an unverified claim about the one call the entire custody argument
    rests on.

    The response is checked, not trusted. ``Sign`` echoes the algorithm it used and
    ``GetPublicKey`` reports the key spec and usage; a disagreement means every
    checkpoint signed afterwards is unverifiable, and the right time to find that out is
    the first call rather than the deposition.
    """

    __slots__ = ("_cached_spki", "_client", "_key_id")

    def __init__(self, client: Any, key_id: str) -> None:
        """Bind a KMS client and the key ARN or alias to sign with.

        Args:
            client: Anything with ``sign`` and ``get_public_key`` methods taking the
                boto3 keyword arguments. In production this is ``boto3.client("kms")``,
                constructed by the caller.
            key_id: The KMS key ID, ARN or alias.

        Raises:
            ValueError: If ``key_id`` is empty.
        """
        if not key_id:
            raise ValueError("a KMS signer needs a key ID, ARN or alias")
        self._client = client
        self._key_id = key_id
        self._cached_spki: bytes | None = None

    @property
    def key_id(self) -> str:
        """Return the KMS key identifier this signer was bound to."""
        return self._key_id

    def sign(self, body: bytes) -> bytes:
        """Sign ``body`` with ``kms:Sign`` and return the DER signature unmodified.

        Args:
            body: The message — the checkpoint note text, or the canonical bytes of a
                receipt. Not a digest.

        Returns:
            The ``Signature`` field exactly as KMS returned it. **No re-encoding**: KMS
            returns ASN.1 DER for ``ECDSA_SHA_256`` and C2SP type ``0x02`` is DER, so
            converting to fixed-width ``r‖s`` here would produce the single most common
            interoperability failure in the format (CU-3).

        Raises:
            KmsResponseUnexpected: If the response omits ``Signature`` or echoes a
                different signing algorithm than the one requested.
        """
        response = self._client.sign(
            KeyId=self._key_id,
            Message=body,
            MessageType=KMS_MESSAGE_TYPE,
            SigningAlgorithm=KMS_SIGNING_ALGORITHM,
        )
        signature = response.get("Signature")
        if not signature:
            raise KmsResponseUnexpected(
                f"kms:Sign for key {self._key_id!r} returned no Signature field"
            )
        echoed = response.get("SigningAlgorithm", KMS_SIGNING_ALGORITHM)
        if echoed != KMS_SIGNING_ALGORITHM:
            raise KmsResponseUnexpected(
                f"kms:Sign echoed SigningAlgorithm={echoed!r}, not "
                f"{KMS_SIGNING_ALGORITHM!r}; the signature would not verify as a C2SP "
                "type-0x02 note signature"
            )
        return bytes(signature)

    def public_key_spki_der(self) -> bytes:
        """Fetch and cache the DER SPKI public key via ``kms:GetPublicKey``.

        Returns:
            The ``PublicKey`` field, which KMS documents as DER ``SubjectPublicKeyInfo``
            — the exact preimage of the C2SP type-``0x02`` key ID.

        Raises:
            KmsResponseUnexpected: If the response omits ``PublicKey``, or reports a key
                spec or usage that cannot produce a conforming log signature.
        """
        if self._cached_spki is not None:
            return self._cached_spki
        response = self._client.get_public_key(KeyId=self._key_id)
        spki = response.get("PublicKey")
        if not spki:
            raise KmsResponseUnexpected(
                f"kms:GetPublicKey for key {self._key_id!r} returned no PublicKey field"
            )
        spec = response.get("KeySpec", KMS_KEY_SPEC)
        if spec != KMS_KEY_SPEC:
            raise KmsResponseUnexpected(
                f"KMS key {self._key_id!r} has KeySpec={spec!r}, not {KMS_KEY_SPEC!r}; "
                "C2SP note type 0x02 is P-256 only"
            )
        usage = response.get("KeyUsage", KMS_KEY_USAGE)
        if usage != KMS_KEY_USAGE:
            raise KmsResponseUnexpected(
                f"KMS key {self._key_id!r} has KeyUsage={usage!r}, not {KMS_KEY_USAGE!r}"
            )
        self._cached_spki = bytes(spki)
        return self._cached_spki


def public_key_for(signer: Signer, key_name: str) -> PublicKey:
    """Return the :class:`PublicKey` a signer's checkpoints are verified against.

    Args:
        signer: Any :class:`Signer`.
        key_name: The C2SP key name, which for a MAINLINE checkpoint is the origin.

    Returns:
        The public key, with its four-byte ID derived from the SPKI.
    """
    return PublicKey(
        name=key_name,
        algorithm=ALGORITHM_ECDSA_P256_SHA256,
        key_material=signer.public_key_spki_der(),
    )


def sign_note_text(signer: Signer, key_name: str, text: str) -> SignatureLine:
    """Sign a note text and render the signature line.

    Args:
        signer: The signing key.
        key_name: The C2SP key name — the origin, for a checkpoint.
        text: The note text, including its final newline. These bytes are signed
            verbatim; nothing here strips, normalises or re-wraps them.

    Returns:
        The signature line to place after the blank separator.
    """
    key = public_key_for(signer, key_name)
    return build_signature_line(key, signer.sign(text.encode("utf-8")))
