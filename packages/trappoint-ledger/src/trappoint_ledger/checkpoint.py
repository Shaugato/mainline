# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The checkpoint note text: build it, parse it, and never parse it before verifying.

A checkpoint is the only object in the custody design that leaves our trust boundary.
Its note text — three mandatory lines then extension lines — is what an RFC 3161
authority timestamps, what S3 Object Lock holds, and what a witness cosigns. This module
is the single place in the repository that assembles those bytes, and
``mainline_sequencer.append`` binds to :func:`build_body` rather than formatting the
lines itself, because two spellings of a signed object is how a log comes to disagree
with its own verifier.

::

    mainline.example/site/BLK-07
    5
    AMXd34nRXfv5+yNJ4K2tvMSlExtmEq38ha0N8gBdNZ4=
    canon: 1 260ed37d…
    drand: 52db9ba7…e971 31088494 7d045d05…
    nist: 2.0 2.29255654 d7a6237e…

**Order matters and is enforced in one direction only.** ``spec/wire/checkpoint.md`` §4
fixes the order of the three names it defines and requires a verifier to ignore names it
does not recognise. It does not say where an unrecognised name sits relative to a
recognised one — it cannot, since it does not know the name. :func:`parse_body` therefore
enforces that ``canon``, ``drand`` and ``nist`` appear in that relative order and at most
once each, and admits an unknown name anywhere. That reading is filed as gap G1 in
``docs/adr/0043-log-signature-ecdsa-p256-note-type-02.md``.

**Verify, then parse.** :func:`verify_checkpoint` is the entry point a verifier should
use. :func:`parse_body` on unverified bytes is a supported operation — the sequencer
parses its own output, and a diagnostic tool must be able to look at a note that does not
verify — but every such call site is knowingly reading attacker-controlled input.

Dependency floor: ``base64``, ``re``, ``dataclasses``, ``typing``, ``collections.abc``,
plus :mod:`trappoint_ledger.note`. No cryptography.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from trappoint_ledger.note.format import (
    Note,
    SignatureLine,
    SignatureVerifier,
    VerifiedNote,
    decode_note,
    encode_note,
    verify_note,
)
from trappoint_ledger.note.keyid import PublicKey

__all__ = [
    "CANON_EXTENSION",
    "DRAND_EXTENSION",
    "EXTENSION_NAME_PATTERN",
    "MANDATORY_LINES",
    "NIST_EXTENSION",
    "ORDERED_EXTENSIONS",
    "ROOT_HASH_BYTES",
    "CanonExtension",
    "CheckpointBody",
    "MalformedCheckpoint",
    "build_body",
    "build_checkpoint_note",
    "encode_root_hash",
    "parse_body",
    "verify_checkpoint",
]

#: origin, tree size, root hash.
MANDATORY_LINES: Final = 3

#: The RFC 6962 Merkle Tree Hash is a SHA-256 digest.
ROOT_HASH_BYTES: Final = 32

CANON_EXTENSION: Final = "canon"
DRAND_EXTENSION: Final = "drand"
NIST_EXTENSION: Final = "nist"

#: The three names ``spec/wire/checkpoint.md`` §4 defines, in the order it fixes.
ORDERED_EXTENSIONS: Final = (CANON_EXTENSION, DRAND_EXTENSION, NIST_EXTENSION)

#: ``[a-z][a-z0-9.]*`` — §4.
EXTENSION_NAME_PATTERN: Final = re.compile(r"\A[a-z][a-z0-9.]*\Z")

_TREE_SIZE_PATTERN: Final = re.compile(r"\A(?:0|[1-9][0-9]*)\Z")
_EXTENSION_LINE_PATTERN: Final = re.compile(r"\A([a-z][a-z0-9.]*): (.+)\Z")
_CANON_VALUE_PATTERN: Final = re.compile(r"\A([1-9][0-9]*) ([0-9a-f]{64})\Z")
_SHA256_HEX_LEN: Final = 64


class MalformedCheckpoint(ValueError):
    """The note text is not a conforming checkpoint body.

    Every message names the clause of ``spec/wire/checkpoint.md`` that was violated. An
    opposing expert implementing their own verifier will hit these messages, and a
    message that only says "invalid" costs them a day and costs us the argument that the
    format was implementable from the document.
    """


@dataclass(frozen=True, slots=True)
class CanonExtension:
    """The parsed ``canon:`` line — which canonicaliser produced this tree's leaves."""

    payload_ver: int
    """The canonicaliser version. ``trappoint_jcs.CANONICALISERS`` dispatches on it."""

    source_sha256: bytes
    """SHA-256 over the canonicaliser source, LF-normalised. Verifier check 10 compares
    this against the canonicaliser it is itself running, which is what converts "we
    canonicalised correctly" from a claim into a comparison."""

    @property
    def value(self) -> str:
        """Return the extension line's value field."""
        return f"{self.payload_ver} {self.source_sha256.hex()}"


@dataclass(frozen=True, slots=True)
class CheckpointBody:
    """A parsed checkpoint note text.

    Constructing one does not make it true. It is a parse of bytes that a caller either
    verified first (:func:`verify_checkpoint`) or knowingly did not.
    """

    origin: str
    """Line 1. The log identity, ``mainline.<domain>/site/<site_code>`` for MAINLINE."""

    tree_size: int
    """Line 2. The number of *leaves*, not the number of intake rows. ``0`` is legal."""

    root_hash: bytes
    """Line 3, decoded. The 32-byte RFC 6962 Merkle Tree Hash at :attr:`tree_size`."""

    extensions: tuple[tuple[str, str], ...]
    """Lines 4+, as ``(name, value)`` pairs, in source order."""

    def extension(self, name: str) -> str | None:
        """Return the value of extension ``name``, or ``None`` if it is absent."""
        for extension_name, value in self.extensions:
            if extension_name == name:
                return value
        return None

    @property
    def canon(self) -> CanonExtension | None:
        """Return the parsed ``canon:`` line, or ``None`` if the note carries none."""
        value = self.extension(CANON_EXTENSION)
        if value is None:
            return None
        match = _CANON_VALUE_PATTERN.match(value)
        if match is None:
            raise MalformedCheckpoint(
                f"canon: value {value!r} is not '<payload_ver> <64 lowercase hex>' "
                "(spec/wire/checkpoint.md §4.1)"
            )
        return CanonExtension(
            payload_ver=int(match.group(1)),
            source_sha256=bytes.fromhex(match.group(2)),
        )

    @property
    def drand(self) -> str | None:
        """Return the raw ``drand:`` value.

        Parsing it is :func:`trappoint_ledger.beacon.parse_drand_extension`'s job; this
        module knows the note format and deliberately not the beacon formats.
        """
        return self.extension(DRAND_EXTENSION)

    @property
    def nist(self) -> str | None:
        """Return the raw ``nist:`` value."""
        return self.extension(NIST_EXTENSION)

    def to_text(self) -> str:
        """Render this body back to the note text, including its final newline."""
        return build_body(self.origin, self.tree_size, self.root_hash, self.extensions)

    @property
    def signed_bytes(self) -> bytes:
        """Return the bytes a checkpoint signature covers."""
        return self.to_text().encode("utf-8")


def encode_root_hash(root_hash: bytes) -> str:
    """Return the base64 form of a 32-byte root hash, with padding, per RFC 4648 §4.

    Args:
        root_hash: The Merkle Tree Hash.

    Returns:
        The base64 text of line 3.

    Raises:
        MalformedCheckpoint: If the hash is not 32 bytes.
    """
    if len(root_hash) != ROOT_HASH_BYTES:
        raise MalformedCheckpoint(
            f"a root hash is {ROOT_HASH_BYTES} bytes, got {len(root_hash)}; for the "
            'empty tree it is SHA-256(""), never an empty string'
        )
    return base64.b64encode(root_hash).decode("ascii")


def _require_origin(origin: str) -> None:
    if not origin:
        raise MalformedCheckpoint("the origin line is empty (spec/wire/checkpoint.md §3)")
    if "+" in origin:
        raise MalformedCheckpoint(
            f"origin {origin!r} contains '+', which the vkey form in §5.2 reserves as its "
            "field separator"
        )
    if any(char.isspace() for char in origin):
        raise MalformedCheckpoint(
            f"origin {origin!r} contains whitespace; §3 forbids Unicode spaces because the "
            "origin is also the C2SP key name, and a key name with a space makes a "
            "signature line ambiguous"
        )


def _validate_extension(name: str, value: str) -> None:
    if EXTENSION_NAME_PATTERN.match(name) is None:
        raise MalformedCheckpoint(
            f"extension name {name!r} does not match [a-z][a-z0-9.]* (spec/wire/checkpoint.md §4)"
        )
    if not value:
        raise MalformedCheckpoint(f"extension {name!r} has an empty value; §4 requires one")
    if "\n" in value:
        raise MalformedCheckpoint(f"extension {name!r} value contains a newline")
    for char in value:
        if char != "\n" and char < " ":
            raise MalformedCheckpoint(
                f"extension {name!r} value contains control character U+{ord(char):04X}"
            )


def _check_extension_order(names: Sequence[str]) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise MalformedCheckpoint(
                f"extension {name!r} appears more than once; §4 requires at most one of "
                "each name so that the note text is a function of its content"
            )
        seen.add(name)
    ranked = [ORDERED_EXTENSIONS.index(n) for n in names if n in ORDERED_EXTENSIONS]
    if ranked != sorted(ranked):
        present = [n for n in names if n in ORDERED_EXTENSIONS]
        raise MalformedCheckpoint(
            f"the defined extension lines appear as {present}, not in the order "
            f"{list(ORDERED_EXTENSIONS)} that §4 makes normative"
        )


def build_body(
    origin: str,
    tree_size: int,
    root_hash: bytes,
    extensions: Iterable[tuple[str, str]] = (),
) -> str:
    """Build a checkpoint note text.

    Args:
        origin: Line 1.
        tree_size: Line 2. Rendered as ASCII decimal with no leading zeroes.
        root_hash: Line 3, as 32 raw bytes.
        extensions: ``(name, value)`` pairs for lines 4+, in the order §4 fixes for the
            names it defines.

    Returns:
        The note text, including its final newline. These are the bytes to sign.

    Raises:
        MalformedCheckpoint: If any field violates ``spec/wire/checkpoint.md`` §3 or §4.
    """
    _require_origin(origin)
    if tree_size < 0:
        raise MalformedCheckpoint(f"tree size {tree_size} is negative")
    pairs = tuple((str(name), str(value)) for name, value in extensions)
    for name, value in pairs:
        _validate_extension(name, value)
    _check_extension_order([name for name, _ in pairs])
    lines = [origin, str(tree_size), encode_root_hash(root_hash)]
    lines.extend(f"{name}: {value}" for name, value in pairs)
    return "\n".join(lines) + "\n"


def _parse_tree_size(line: str) -> int:
    if _TREE_SIZE_PATTERN.match(line) is None:
        raise MalformedCheckpoint(
            f"tree size {line!r} is not ASCII decimal without leading zeroes; §3 forbids "
            "a leading zero so that the note text is a function of the tree size"
        )
    return int(line)


def _parse_root_hash(line: str) -> bytes:
    try:
        root = base64.b64decode(line, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedCheckpoint(
            f"root hash line {line!r} is not standard base64 with padding: {exc}"
        ) from exc
    if len(root) != ROOT_HASH_BYTES:
        raise MalformedCheckpoint(f"root hash decodes to {len(root)} bytes, not {ROOT_HASH_BYTES}")
    if base64.b64encode(root).decode("ascii") != line:
        raise MalformedCheckpoint(
            f"root hash line {line!r} is not the canonical base64 of the bytes it "
            "decodes to; non-canonical padding bits would let two spellings of one "
            "checkpoint exist, and only one of them would be the one that was signed"
        )
    return root


def parse_body(text: str | bytes) -> CheckpointBody:
    """Parse a checkpoint note text, strictly.

    Args:
        text: The note text, including its final newline.

    Returns:
        The :class:`CheckpointBody`.

    Raises:
        MalformedCheckpoint: On any deviation from ``spec/wire/checkpoint.md`` §3 and §4.
    """
    raw = text if isinstance(text, str) else bytes(text).decode("utf-8", errors="strict")
    if "\r" in raw:
        raise MalformedCheckpoint(
            "the note text contains a carriage return; the line terminator is U+000A "
            "alone, and a CRLF checkout would otherwise sign different bytes than it "
            "verifies"
        )
    if not raw.endswith("\n"):
        raise MalformedCheckpoint("the note text must end with a newline")
    lines = raw[:-1].split("\n")
    if len(lines) < MANDATORY_LINES:
        raise MalformedCheckpoint(
            f"a checkpoint body has at least {MANDATORY_LINES} lines (origin, tree size, "
            f"root hash); this has {len(lines)}"
        )
    if any(line == "" for line in lines):
        raise MalformedCheckpoint(
            "the note text contains an empty line; §3 forbids one because the blank line "
            "belongs to the framing, not to the text"
        )
    origin = lines[0]
    _require_origin(origin)
    tree_size = _parse_tree_size(lines[1])
    root_hash = _parse_root_hash(lines[2])
    extensions: list[tuple[str, str]] = []
    for index, line in enumerate(lines[MANDATORY_LINES:], start=MANDATORY_LINES + 1):
        match = _EXTENSION_LINE_PATTERN.match(line)
        if match is None:
            raise MalformedCheckpoint(
                f"line {index} is not '<name>: <value>' with exactly a colon and one "
                f"space: {line!r}"
            )
        name, value = match.group(1), match.group(2)
        _validate_extension(name, value)
        extensions.append((name, value))
    _check_extension_order([name for name, _ in extensions])
    return CheckpointBody(
        origin=origin,
        tree_size=tree_size,
        root_hash=root_hash,
        extensions=tuple(extensions),
    )


def build_checkpoint_note(body: str, signatures: Sequence[SignatureLine]) -> bytes:
    """Assemble the complete signed note from a body and its signature lines.

    Args:
        body: The note text from :func:`build_body`.
        signatures: One or more signature lines.

    Returns:
        The note bytes: what goes to the TSA, to Object Lock, and to a witness.

    Raises:
        MalformedNote: If the body or the signature set is unusable.
    """
    return encode_note(body, signatures)


def verify_checkpoint(
    note: Note | bytes | str,
    keys: Iterable[PublicKey],
    verify: SignatureVerifier,
) -> tuple[CheckpointBody, VerifiedNote]:
    """Verify a checkpoint note and only then parse its body.

    The ordering is the contract. ``spec/wire/checkpoint.md`` §6 step 7 reads
    "**Unverified note text is not data**"; a verifier that parses first has already let
    attacker-chosen bytes reach its state machine, and every field it then reports — the
    tree size, the root, the beacon round — is a field the attacker chose.

    Args:
        note: The signed note.
        keys: The trusted keys.
        verify: The signature primitive; see
            :func:`trappoint_ledger.signer.p256_sha256_verify`.

    Returns:
        The parsed body and the verification result, in that order.

    Raises:
        MalformedNote: If the note does not decode.
        NoteVerificationFailed: If no known key signed it, or a known key's signature
            failed.
        MalformedCheckpoint: If the *verified* text is not a conforming checkpoint body.
            Reaching this means the log signed something malformed, which is a finding
            about the log rather than about the transport.
    """
    decoded = note if isinstance(note, Note) else decode_note(note)
    verified = verify_note(decoded, keys, verify)
    return parse_body(verified.note.text), verified
