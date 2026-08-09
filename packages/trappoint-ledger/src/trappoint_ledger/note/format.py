# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The C2SP signed-note wire format: encode, decode, and verify.

A signed note is::

    <note text, ending in U+000A>
    <U+000A>
    <one or more signature lines, each ending in U+000A>

Three properties of this module are load-bearing and each is tested:

**The signed bytes are the note text and nothing else.** Not the whole note, not the
text without its final newline. :attr:`Note.signed_bytes` is the one place that decides,
and every signature — ours, a witness's, a future Ed25519 one — is taken over its output.

**Unknown signature lines survive a decode/encode round trip byte for byte.** A witness
cosignature is a line whose key this build has never heard of. If re-encoding dropped it,
or re-rendered its base64 with different padding, then the act of *reading* a checkpoint
would destroy the evidence someone else added to it. :class:`SignatureLine` therefore
keeps the exact source line and re-emits it verbatim; the parsed fields are derived and
are never rendered back.

**Unverified note text is not data.** :func:`verify_note` returns the signed bytes; it
does not parse them, and nothing in this module parses a checkpoint body. Parsing lives
in :mod:`trappoint_ledger.checkpoint` behind
:func:`~trappoint_ledger.checkpoint.verify_checkpoint`, which verifies first. A verifier
that parses first has already admitted attacker-chosen bytes into its state machine —
``spec/wire/checkpoint.md`` §6 step 7.

Dependency floor: ``base64``, ``dataclasses``, ``typing``, ``collections.abc``. The
signature *primitive* is injected as a callable, so this module carries no cryptography
dependency and the same code verifies a KMS-signed note, a locally signed one, and a
note whose algorithm did not exist when it was written.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from trappoint_ledger.note.keyid import KEY_ID_BYTES, PublicKey

__all__ = [
    "EM_DASH",
    "MIN_SIGNATURE_LINES_ACCEPTED",
    "SIGNATURE_LINE_PREFIX",
    "MalformedNote",
    "Note",
    "NoteVerificationFailed",
    "SignatureLine",
    "SignatureVerifier",
    "VerifiedNote",
    "build_signature_line",
    "decode_note",
    "encode_note",
    "verify_note",
]

#: U+2014. Not U+002D (hyphen-minus) and not U+2013 (en dash). A note written with the
#: wrong dash parses as one long text with no signature lines, and then fails
#: verification with a message about missing signatures rather than about the dash. It
#: is the most common implementation error in this format and it is why
#: ``spec/wire/checkpoint.md`` §2 calls it out in a block quote.
EM_DASH: Final = "—"

#: Em dash, then exactly one space.
SIGNATURE_LINE_PREFIX: Final = EM_DASH + " "

#: ``spec/wire/checkpoint.md`` §2: a verifier MUST accept at least this many signature
#: lines. This module imposes no maximum — see ADR 0043 for why refusing a note for
#: having "too many" cosignatures would be the wrong failure.
MIN_SIGNATURE_LINES_ACCEPTED: Final = 16

_SEPARATOR: Final = "\n\n"
_MIN_SIGNATURE_BYTES: Final = KEY_ID_BYTES + 1


class MalformedNote(ValueError):
    """The bytes are not a signed note.

    Distinct from :class:`NoteVerificationFailed` on purpose. "This is not a note" and
    "this is a note that does not verify" are different findings: the first is a
    transport or encoding fault, the second is an accusation.
    """


class NoteVerificationFailed(ValueError):
    """A well-formed note failed verification against the keys it was given."""


class SignatureVerifier(Protocol):
    """The signature primitive :func:`verify_note` calls, injected by the caller.

    Implementations must return ``False`` on an invalid signature rather than raising,
    and must not raise for a malformed signature encoding either — a signature line is
    attacker-controlled and an exception escaping here would turn a refusal into a
    crash. :func:`trappoint_ledger.signer.p256_sha256_verify` is the reference
    implementation.
    """

    def __call__(self, key: PublicKey, message: bytes, signature: bytes) -> bool:
        """Return whether ``signature`` is a valid signature over ``message``."""
        ...


@dataclass(frozen=True, slots=True)
class SignatureLine:
    """One signature line, with the exact source text kept for byte-faithful re-encode."""

    key_name: str
    """The key name field, which for a MAINLINE checkpoint is the origin."""

    key_id: bytes
    """The four bytes the base64 value starts with."""

    signature: bytes
    """Everything after the key ID: for type ``0x02``, the ASN.1 DER ECDSA signature."""

    raw: str = field(compare=False)
    """The line exactly as it appeared, without its trailing newline.

    Compared out of equality deliberately: two lines with the same key and the same
    signature bytes are the same signature even if one was transcribed with different
    base64 padding. Re-encoding still emits this string, so a round trip is byte-exact
    while equality stays semantic.
    """

    @property
    def lookup(self) -> tuple[str, bytes]:
        """Return the ``(key name, key ID)`` pair used to find a key."""
        return (self.key_name, self.key_id)


@dataclass(frozen=True, slots=True)
class Note:
    """A decoded signed note: the signed text, and every signature line in order."""

    text: str
    """The note text, **including** its own final newline and excluding the blank
    separator line. These are the bytes that were signed."""

    signatures: tuple[SignatureLine, ...]
    """Every signature line, in source order, known keys and unknown keys alike."""

    @property
    def signed_bytes(self) -> bytes:
        """Return the exact bytes a signature covers."""
        return self.text.encode("utf-8")

    def encode(self) -> bytes:
        """Re-encode this note.

        Returns:
            The note bytes. For a note produced by :func:`decode_note` this is
            byte-identical to the input, including signature lines whose keys are
            unknown to this build.
        """
        return encode_note(self.text, self.signatures)

    def signature_for(self, key: PublicKey) -> SignatureLine | None:
        """Return the first signature line matching ``key``'s ``(name, key ID)``."""
        for line in self.signatures:
            if line.lookup == key.lookup:
                return line
        return None


@dataclass(frozen=True, slots=True)
class VerifiedNote:
    """The result of a successful :func:`verify_note`."""

    note: Note
    """The note as decoded."""

    verified: tuple[PublicKey, ...]
    """Every known key whose signature line verified. Never empty."""

    ignored: tuple[SignatureLine, ...]
    """Signature lines whose ``(name, key ID)`` matched no supplied key.

    Reported rather than discarded. An operator who pinned the wrong witness key sees a
    note that verified with an ignored line, which is the difference between "quorum not
    met" and "quorum met but I am not configured to see it".
    """

    @property
    def signed_bytes(self) -> bytes:
        """Return the verified signed bytes — the only bytes callers may then parse."""
        return self.note.signed_bytes


def _check_control_characters(text: str) -> None:
    """Refuse any ASCII control character below U+0020 other than newline.

    ``spec/wire/checkpoint.md`` §2 states this over the whole note; §6 step 2 states it
    over everything outside the signature lines. This enforces the §2 reading, which is
    strictly stronger and cannot reject a conforming note: a key name may not contain
    whitespace and base64 has no control characters in its alphabet. The discrepancy is
    filed as gap G2 in ADR 0043.
    """
    for index, char in enumerate(text):
        if char != "\n" and char < " ":
            raise MalformedNote(
                f"byte {index} is control character U+{ord(char):04X}; a signed note may "
                "contain no ASCII control character below U+0020 other than newline "
                "(spec/wire/checkpoint.md §2)"
            )


def _parse_signature_line(line: str, index: int) -> SignatureLine:
    if not line.startswith(SIGNATURE_LINE_PREFIX):
        hint = ""
        if line[:1] in {"-", "–"}:  # noqa: RUF001 - hyphen-minus and en dash ARE the bug
            hint = (
                " — it begins with U+002D or U+2013 where the format requires U+2014; "
                "see spec/wire/checkpoint.md §2"
            )
        raise MalformedNote(
            f"signature line {index} does not begin with an em dash and a space{hint}: {line!r}"
        )
    rest = line[len(SIGNATURE_LINE_PREFIX) :]
    key_name, separator, encoded = rest.partition(" ")
    if not separator or not key_name or not encoded:
        raise MalformedNote(f"signature line {index} is not '— <name> <base64>': {line!r}")
    if " " in encoded:
        raise MalformedNote(f"signature line {index} has a space inside its base64 field: {line!r}")
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedNote(
            f"signature line {index} is not standard base64 with padding (RFC 4648 §4): {exc}"
        ) from exc
    if len(blob) < _MIN_SIGNATURE_BYTES:
        raise MalformedNote(
            f"signature line {index} decodes to {len(blob)} bytes; it must be a "
            f"{KEY_ID_BYTES}-byte key ID followed by a signature"
        )
    return SignatureLine(
        key_name=key_name,
        key_id=blob[:KEY_ID_BYTES],
        signature=blob[KEY_ID_BYTES:],
        raw=line,
    )


def decode_note(data: bytes | str) -> Note:
    """Decode a signed note, preserving every signature line exactly as written.

    Splits at the **last** empty line, per ``spec/wire/checkpoint.md`` §6 step 1: the
    note text may itself contain a blank line, so splitting at the first one truncates
    the signed bytes and produces a signature failure that looks like tampering.

    Args:
        data: The note bytes, or a ``str`` that will be encoded as UTF-8.

    Returns:
        The decoded :class:`Note`.

    Raises:
        MalformedNote: If the bytes are not valid UTF-8, contain a forbidden control
            character, have no blank separator line, have an empty note text, carry no
            signature line, or carry a signature line this format cannot parse.
    """
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MalformedNote(f"a signed note must be valid UTF-8: {exc}") from exc
    _check_control_characters(text)
    if not text.endswith("\n"):
        raise MalformedNote("a signed note ends with a newline; these bytes do not")
    separator = text.rfind(_SEPARATOR)
    if separator < 0:
        raise MalformedNote(
            "no blank line separates the note text from the signature lines; the bytes "
            "may be a bare checkpoint body rather than a signed note"
        )
    note_text = text[: separator + 1]
    signature_blob = text[separator + 2 :]
    if not note_text.strip("\n"):
        raise MalformedNote("the note text is empty")
    if not signature_blob:
        raise MalformedNote(
            "a signed note carries one or more signature lines and this carries none "
            "(spec/wire/checkpoint.md §2)"
        )
    lines = signature_blob.split("\n")
    # The blob ends with a newline, so `split` leaves a trailing empty element.
    trailing = lines.pop()
    if trailing:
        raise MalformedNote("the final signature line does not end with a newline")
    signatures = tuple(_parse_signature_line(line, i) for i, line in enumerate(lines))
    return Note(text=note_text, signatures=signatures)


def encode_note(text: str, signatures: Sequence[SignatureLine]) -> bytes:
    """Encode a signed note from a note text and its signature lines.

    Args:
        text: The note text, including its own final newline.
        signatures: The signature lines, emitted in the order given. Each is re-emitted
            from its ``raw`` field, so lines produced by :func:`decode_note` survive
            byte for byte.

    Returns:
        The note bytes.

    Raises:
        MalformedNote: If the text does not end in a newline, ends in a blank line, or
            no signature line is supplied.
    """
    if not text.endswith("\n"):
        raise MalformedNote("the note text must end with a newline")
    if text.endswith(_SEPARATOR):
        raise MalformedNote(
            "the note text ends with a blank line, which would move the separator and "
            "silently change which bytes are signed"
        )
    if not signatures:
        raise MalformedNote("a signed note carries at least one signature line")
    _check_control_characters(text)
    body = "".join(line.raw + "\n" for line in signatures)
    return (text + "\n" + body).encode("utf-8")


def build_signature_line(key: PublicKey, signature: bytes) -> SignatureLine:
    """Render a signature line for ``key`` over an already-computed signature.

    Args:
        key: The signing key, whose name and derived key ID the line carries.
        signature: The raw signature bytes — for type ``0x02``, the DER encoding exactly
            as ``KMS Sign`` returned it, with no re-encoding.

    Returns:
        The :class:`SignatureLine`, with ``raw`` set to the rendered text.

    Raises:
        ValueError: If the signature is empty.
    """
    if not signature:
        raise ValueError("an empty signature is not a signature")
    encoded = base64.b64encode(key.key_id + signature).decode("ascii")
    return SignatureLine(
        key_name=key.name,
        key_id=key.key_id,
        signature=bytes(signature),
        raw=f"{SIGNATURE_LINE_PREFIX}{key.name} {encoded}",
    )


def _index_keys(keys: Iterable[PublicKey]) -> Mapping[tuple[str, bytes], PublicKey]:
    indexed: dict[tuple[str, bytes], PublicKey] = {}
    for key in keys:
        if key.lookup in indexed:
            raise ValueError(
                f"two keys share the name {key.name!r} and key ID {key.key_id_hex}; a "
                "verifier cannot decide which one a signature line meant"
            )
        indexed[key.lookup] = key
    return indexed


def verify_note(
    note: Note | bytes | str,
    keys: Iterable[PublicKey],
    verify: SignatureVerifier,
) -> VerifiedNote:
    """Verify a signed note, in the order ``spec/wire/checkpoint.md`` §6 fixes.

    Signature lines whose ``(name, key ID)`` matches no supplied key are **ignored**,
    which is what lets a witness cosign, and what lets an Ed25519 log signature be added
    later, without a format change. A line whose key *is* known and whose signature does
    not verify rejects the whole note: a partially valid note is not a weaker exhibit,
    it is a forged one.

    Args:
        note: A decoded :class:`Note`, or bytes to decode first.
        keys: The keys this verifier trusts.
        verify: The signature primitive.

    Returns:
        A :class:`VerifiedNote` carrying the signed bytes, the keys that verified, and
        the lines that were ignored.

    Raises:
        MalformedNote: If ``note`` is bytes that do not decode.
        NoteVerificationFailed: If a known key's signature fails, or if no known key
            signed the note at all.
    """
    decoded = note if isinstance(note, Note) else decode_note(note)
    indexed = _index_keys(keys)
    message = decoded.signed_bytes
    verified: list[PublicKey] = []
    ignored: list[SignatureLine] = []
    for line in decoded.signatures:
        key = indexed.get(line.lookup)
        if key is None:
            ignored.append(line)
            continue
        if not verify(key, message, line.signature):
            raise NoteVerificationFailed(
                f"the signature line for key {key.name!r} ({key.key_id_hex}) does not "
                "verify against the note text; the whole note is rejected "
                "(spec/wire/checkpoint.md §6 step 6)"
            )
        verified.append(key)
    if not verified:
        known = ", ".join(sorted(f"{n}+{k.hex()}" for n, k in indexed)) or "(none supplied)"
        raise NoteVerificationFailed(
            "no signature line was signed by a known key, so nothing about this note is "
            f"established. Known keys: {known}. Lines present: "
            f"{[line.key_name + '+' + line.key_id.hex() for line in decoded.signatures]}"
        )
    return VerifiedNote(note=decoded, verified=tuple(verified), ignored=tuple(ignored))
