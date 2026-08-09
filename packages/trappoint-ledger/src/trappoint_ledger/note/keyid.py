# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""C2SP signed-note key identity: key IDs, the vkey form, and the two derivations.

The key ID is four bytes and it is *not* derived the same way for every algorithm. That
asymmetry is the single most expensive bug in this format, because getting it wrong does
not produce an error — it produces a note whose signature line names a key that nobody
has, so every verifier silently ignores the line and then rejects the note for "no known
signature". The error message points at the wrong thing.

======================  ===========================================================
type ``0x01`` Ed25519   ``SHA-256(key_name ‖ 0x0A ‖ 0x01 ‖ pubkey)[:4]``
type ``0x02`` ECDSA     ``SHA-256(DER SPKI)[:4]`` — **no name, no algorithm byte**
======================  ===========================================================

``spec/wire/checkpoint.md`` §5.1 states both, normatively, and this module is the only
place in the repository that computes either. :class:`PublicKey` never *accepts* a key
ID: it recomputes one from the material every time it is constructed, so a key whose ID
disagrees with its bytes cannot be represented. :func:`parse_vkey` compares the
recomputed value against the field it was handed and refuses on mismatch, which is what
§5.2 requires of a conforming parser.

Dependency floor: ``hashlib``, ``base64``, ``re``, ``dataclasses``, ``typing``. Nothing
else. MAINLINE's log key lives in AWS KMS and this module never needs to touch it — a
DER SPKI blob is all a key ID is a function of.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "ALGORITHM_ECDSA_P256_SHA256",
    "ALGORITHM_ED25519",
    "KEY_ID_BYTES",
    "KEY_NAME_PATTERN",
    "KeyIdMismatch",
    "MalformedVkey",
    "PublicKey",
    "UnsupportedAlgorithm",
    "format_vkey",
    "key_id_ecdsa_p256",
    "key_id_ed25519",
    "key_id_hex",
    "parse_vkey",
]

#: C2SP signed-note signature type for Ed25519.
ALGORITHM_ED25519: Final = 0x01

#: C2SP signed-note signature type for ECDSA P-256 with SHA-256 — MAINLINE's log
#: signature, ruling CU-3. The signature bytes are ASN.1 DER, exactly as AWS KMS
#: returns them; see ``docs/adr/0043-log-signature-ecdsa-p256-note-type-02.md``.
ALGORITHM_ECDSA_P256_SHA256: Final = 0x02

#: A key ID is the first four bytes of a SHA-256 digest. Four bytes is a collision
#: domain of 2**32, which is a *routing* hint and not an authenticator: a verifier
#: matches on ``(name, key ID)`` to decide which key to try, and then the signature
#: itself decides. Nothing in this format trusts a key ID.
KEY_ID_BYTES: Final = 4

#: C2SP forbids ``+`` in a key name so that the vkey form parses on its first two
#: separators, and forbids whitespace so that a signature line is unambiguous.
KEY_NAME_PATTERN: Final = re.compile(r"\A[^\s+]+\Z")

_ALGORITHM_BYTE_MAX: Final = 0xFF
_ED25519_PUBLIC_KEY_BYTES: Final = 32
_VKEY_FIELDS: Final = 3
_KEY_ID_HEX_LEN: Final = KEY_ID_BYTES * 2


class MalformedVkey(ValueError):
    """A verifier key string does not have the shape ``name+keyid+base64``."""


class KeyIdMismatch(ValueError):
    """A vkey's stated key ID is not the one its key material derives.

    Raised rather than repaired. A vkey whose ID does not match its bytes is either a
    transcription error or an attempt to have a verifier index the right key material
    under the wrong name, and both are conditions the operator must see.
    """


class UnsupportedAlgorithm(ValueError):
    """A signature type this module has no key-ID derivation for.

    Refusing is correct and is not a limitation. A key ID computed by guessing at a
    derivation is a key ID that matches nothing, and the resulting note fails
    verification for a reason that reads as "the log is lying" rather than as "this
    build does not know that algorithm".
    """


def key_id_ed25519(key_name: str, public_key: bytes) -> bytes:
    """Return the C2SP type-``0x01`` key ID for an Ed25519 key.

    ``SHA-256(key_name ‖ 0x0A ‖ 0x01 ‖ pubkey)[:4]``, per c2sp.org/signed-note.

    Args:
        key_name: The key name, which for MAINLINE is the checkpoint origin line.
        public_key: The 32-byte raw Ed25519 public key.

    Returns:
        Four bytes.

    Raises:
        ValueError: If the name is unusable as a C2SP key name, or the key is not
            32 bytes.
    """
    _require_key_name(key_name)
    if len(public_key) != _ED25519_PUBLIC_KEY_BYTES:
        raise ValueError(
            f"an Ed25519 public key is {_ED25519_PUBLIC_KEY_BYTES} bytes, got "
            f"{len(public_key)}; a DER SPKI blob passed here would produce a key ID "
            "that matches nothing"
        )
    preimage = key_name.encode("utf-8") + b"\x0a" + bytes([ALGORITHM_ED25519]) + public_key
    return hashlib.sha256(preimage).digest()[:KEY_ID_BYTES]


def key_id_ecdsa_p256(spki_der: bytes) -> bytes:
    """Return the C2SP type-``0x02`` key ID for an ECDSA P-256 key.

    ``SHA-256(DER SPKI)[:4]``. **The name is not in the preimage and neither is the
    algorithm byte** — deriving this the Ed25519 way is the error
    ``spec/wire/checkpoint.md`` §5.1 exists to prevent.

    Args:
        spki_der: The DER ``SubjectPublicKeyInfo`` encoding of the public key, which is
            what ``KMS GetPublicKey`` returns in ``PublicKey`` and what
            ``cryptography``'s ``public_bytes(DER, SubjectPublicKeyInfo)`` produces.

    Returns:
        Four bytes.

    Raises:
        ValueError: If the SPKI is empty.
    """
    if not spki_der:
        raise ValueError("an empty DER SPKI has no key ID; pass the bytes KMS returned")
    return hashlib.sha256(spki_der).digest()[:KEY_ID_BYTES]


def key_id_hex(key_id: bytes) -> str:
    """Return the eight lowercase hex characters a vkey and an SDR envelope carry.

    Args:
        key_id: Exactly four bytes.

    Returns:
        Eight lowercase hex characters.

    Raises:
        ValueError: If the key ID is not four bytes.
    """
    if len(key_id) != KEY_ID_BYTES:
        raise ValueError(f"a key ID is {KEY_ID_BYTES} bytes, got {len(key_id)}")
    return key_id.hex()


def _require_key_name(key_name: str) -> None:
    if not KEY_NAME_PATTERN.match(key_name):
        raise ValueError(
            f"key name {key_name!r} is empty or contains whitespace or '+'; C2SP forbids "
            "both so that a signature line and a vkey are unambiguous "
            "(spec/wire/checkpoint.md §5.2)"
        )


@dataclass(frozen=True, slots=True)
class PublicKey:
    """A note-verification key: a name, an algorithm, and the material.

    The key ID is **derived**, never supplied. That is the whole point of the type: a
    :class:`PublicKey` that exists is a key whose four-byte ID provably belongs to its
    bytes, so every downstream ``(name, key ID)`` lookup is a lookup of something real.
    """

    name: str
    """The C2SP key name. For a MAINLINE log this is the checkpoint's origin line."""

    algorithm: int
    """The C2SP signature type byte: :data:`ALGORITHM_ED25519` or
    :data:`ALGORITHM_ECDSA_P256_SHA256`."""

    key_material: bytes
    """Raw 32-byte public key for ``0x01``; the DER SPKI encoding for ``0x02``."""

    def __post_init__(self) -> None:
        """Validate the name and refuse an algorithm with no key-ID derivation."""
        _require_key_name(self.name)
        if self.algorithm not in (ALGORITHM_ED25519, ALGORITHM_ECDSA_P256_SHA256):
            raise UnsupportedAlgorithm(
                f"signature type 0x{self.algorithm:02x} has no key-ID derivation in this "
                "build; a note line signed by it is IGNORED rather than rejected "
                "(spec/wire/checkpoint.md §6 step 4), so construct no key for it"
            )
        # Touch the derivation once at construction so that a malformed key cannot be
        # built and then fail later, in the middle of a verification, where the error
        # would read as a signature failure.
        object.__setattr__(self, "key_material", bytes(self.key_material))
        _ = self.key_id

    @property
    def key_id(self) -> bytes:
        """Return the four-byte C2SP key ID, derived from this key's own bytes."""
        if self.algorithm == ALGORITHM_ED25519:
            return key_id_ed25519(self.name, self.key_material)
        return key_id_ecdsa_p256(self.key_material)

    @property
    def key_id_hex(self) -> str:
        """Return the key ID as eight lowercase hex characters."""
        return key_id_hex(self.key_id)

    @property
    def lookup(self) -> tuple[str, bytes]:
        """Return the ``(name, key ID)`` pair a signature line is matched on."""
        return (self.name, self.key_id)

    def vkey(self) -> str:
        """Return the C2SP verifier-key string for this key."""
        return format_vkey(self.name, self.algorithm, self.key_material)


def format_vkey(name: str, algorithm: int, key_material: bytes) -> str:
    """Render a C2SP verifier key: ``<name>+<8 hex key ID>+<base64(alg ‖ material)>``.

    Args:
        name: The C2SP key name.
        algorithm: The signature type byte.
        key_material: Raw public key for ``0x01``, DER SPKI for ``0x02``.

    Returns:
        The vkey string ``trappoint-verify --log-key`` accepts.

    Raises:
        UnsupportedAlgorithm: If the algorithm has no key-ID derivation here.
        ValueError: If the algorithm does not fit in a byte.
    """
    if not 0 <= algorithm <= _ALGORITHM_BYTE_MAX:
        raise ValueError(f"signature type {algorithm} does not fit in one byte")
    key = PublicKey(name=name, algorithm=algorithm, key_material=key_material)
    encoded = base64.b64encode(bytes([algorithm]) + key.key_material).decode("ascii")
    return f"{key.name}+{key.key_id_hex}+{encoded}"


def parse_vkey(vkey: str) -> PublicKey:
    """Parse a C2SP verifier key, recomputing its key ID rather than trusting it.

    **Splits on the first two ``+`` only.** The third field is standard base64, whose
    alphabet contains ``+``; splitting on every plus yields four fields for most keys and
    three for the rest, which is a bug that passes in testing and fails on the next key
    anyone generates. ``spec/wire/checkpoint.md`` §5.2 makes the two-split limit
    normative for exactly that reason.

    Args:
        vkey: The verifier key string.

    Returns:
        The :class:`PublicKey`.

    Raises:
        MalformedVkey: If the string does not have three ``+``-separated fields, if the
            key-ID field is not eight hex characters, or if the base64 does not decode.
        KeyIdMismatch: If the stated key ID is not the one the material derives.
        UnsupportedAlgorithm: If the algorithm byte has no key-ID derivation here.
    """
    fields = vkey.split("+", _VKEY_FIELDS - 1)
    if len(fields) != _VKEY_FIELDS:
        raise MalformedVkey(
            f"a vkey is name+keyid+base64 and this has {len(fields)} field(s): {vkey!r}"
        )
    name, stated_id, encoded = fields
    if len(stated_id) != _KEY_ID_HEX_LEN or any(c not in "0123456789abcdef" for c in stated_id):
        raise MalformedVkey(
            f"key-ID field {stated_id!r} is not {_KEY_ID_HEX_LEN} lowercase hex characters"
        )
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedVkey(f"vkey key material is not standard base64: {exc}") from exc
    if not blob:
        raise MalformedVkey("vkey key material is empty; it must be alg-byte ‖ key material")
    key = PublicKey(name=name, algorithm=blob[0], key_material=blob[1:])
    if key.key_id_hex != stated_id:
        raise KeyIdMismatch(
            f"vkey states key ID {stated_id} but its key material derives "
            f"{key.key_id_hex}; a conforming parser recomputes rather than trusts "
            "(spec/wire/checkpoint.md §5.2)"
        )
    return key
