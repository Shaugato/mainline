# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint_ledger.note`` — the C2SP signed-note format and its key identity.

Two modules, and the split is not cosmetic. :mod:`~trappoint_ledger.note.keyid` owns
the two key-ID derivations and the vkey form; :mod:`~trappoint_ledger.note.format` owns
the bytes. Neither imports a cryptographic library: the signature primitive is a
callable the caller supplies, so this subpackage verifies a KMS-signed checkpoint, a
locally signed reference bundle, and a witness cosignature under an algorithm that did
not exist when this was written, with the same code.

**Dependency floor.** Everything reachable from this import uses ``base64``, ``hashlib``,
``re``, ``dataclasses``, ``typing`` and ``collections.abc``, and nothing else — the same
contract :mod:`trappoint_ledger.merkle` holds itself to, for the same reason:
``trappoint-verify`` lifts these algorithms and its one-dependency claim is a promise
made to strangers.
"""

from __future__ import annotations

from trappoint_ledger.note.format import (
    EM_DASH,
    MIN_SIGNATURE_LINES_ACCEPTED,
    SIGNATURE_LINE_PREFIX,
    MalformedNote,
    Note,
    NoteVerificationFailed,
    SignatureLine,
    SignatureVerifier,
    VerifiedNote,
    build_signature_line,
    decode_note,
    encode_note,
    verify_note,
)
from trappoint_ledger.note.keyid import (
    ALGORITHM_ECDSA_P256_SHA256,
    ALGORITHM_ED25519,
    KEY_ID_BYTES,
    KEY_NAME_PATTERN,
    KeyIdMismatch,
    MalformedVkey,
    PublicKey,
    UnsupportedAlgorithm,
    format_vkey,
    key_id_ecdsa_p256,
    key_id_ed25519,
    key_id_hex,
    parse_vkey,
)

__all__ = [
    "ALGORITHM_ECDSA_P256_SHA256",
    "ALGORITHM_ED25519",
    "EM_DASH",
    "KEY_ID_BYTES",
    "KEY_NAME_PATTERN",
    "MIN_SIGNATURE_LINES_ACCEPTED",
    "SIGNATURE_LINE_PREFIX",
    "KeyIdMismatch",
    "MalformedNote",
    "MalformedVkey",
    "Note",
    "NoteVerificationFailed",
    "PublicKey",
    "SignatureLine",
    "SignatureVerifier",
    "UnsupportedAlgorithm",
    "VerifiedNote",
    "build_signature_line",
    "decode_note",
    "encode_note",
    "format_vkey",
    "key_id_ecdsa_p256",
    "key_id_ed25519",
    "key_id_hex",
    "parse_vkey",
    "verify_note",
]
