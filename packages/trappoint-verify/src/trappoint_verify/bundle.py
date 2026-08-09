# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The evidence-bundle loader and the C2SP signed-note parser.

Normative sources, implemented here and nowhere else:

* ``spec/wire/evidence-bundle.md`` v1.0 — the single self-describing JSON exhibit;
* ``spec/wire/checkpoint.md`` v1.0 §2, §3, §4, §6 — the note framing, the note text, the
  extension lines, and the *order* in which a conforming verifier does things.

Four rules this module obeys, each of which is a defect somewhere if it is broken
-------------------------------------------------------------------------------
**Bytes, not renderings.** ``canon_bytes_b64`` is carried verbatim and is what gets
hashed. The parsed ``payload`` beside it is a convenience for humans. A verifier that
hashed ``payload`` would have tested its own JSON library rather than our ledger, so the
loader keeps the two apart by *type*: :attr:`Leaf.canon_bytes` is ``bytes`` and
:attr:`Leaf.payload` is ``object``, and nothing in this package hashes the latter.

**Absence is a value.** :attr:`Bundle.present` records which optional sections the file
actually carried, so a check can say ``SKIP(no-witnesses)`` instead of quietly passing on
an empty list. An empty list and an absent member are different facts and both are kept.

**Unknown members are ignored.** The format is append-only (evidence-bundle.md §1.5), so a
bundle from a later minor version still loads under v1.0. Unknown *extension line names*
in a note are likewise ignored rather than refused.

**Parsing a note never raises.** Every byte of a note may have been chosen by an
adversary. :func:`parse_note` is total: it returns a :class:`ParsedNote` whose ``errors``
tuple is non-empty instead of throwing, because an exception escaping a verifier is a
crash report where a finding belongs. Loading the *bundle* is different — a file that
cannot be read far enough to run a check is not a finding about the log, it is a finding
about the file, and that raises :class:`BundleError`.

A refusal this module deliberately does not soften
--------------------------------------------------
Duplicate JSON member names raise. RFC 8785 §3.1 requires input free of them, and a
loader that resolves last-wins has silently chosen, on the writer's behalf, which of two
records the reader is looking at.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

__all__ = [
    "EM_DASH",
    "GENESIS_LINK",
    "HASH_BYTES",
    "OPTIONAL_SECTIONS",
    "Archive",
    "ArchiveObject",
    "Bundle",
    "BundleError",
    "Canon",
    "Checkpoint",
    "ClosureGeneration",
    "ConsistencyProof",
    "InclusionProof",
    "Leaf",
    "ParsedNote",
    "Receipt",
    "SchemaAttestation",
    "SignatureLine",
    "TsaToken",
    "WebAuthnAssertion",
    "WitnessCosignature",
    "load_bundle",
    "loads_bundle",
    "parse_note",
]

#: Every digest in this scheme is SHA-256.
HASH_BYTES: Final[int] = 32
#: ``link_hash`` genesis. An explicit 32 zero bytes rather than ``NULL``, so the
#: ``UNIQUE (site_code, prev_link_hash)`` linearity constraint applies from the first leaf.
GENESIS_LINK: Final[bytes] = b"\x00" * HASH_BYTES
#: U+2014. Not a hyphen, not U+2013. The single most common implementation error in the
#: signed-note format, and it fails in the most misleading possible way: the whole note
#: parses as one long text with no signature lines at all.
EM_DASH: Final[str] = "—"

_HEX_DIGITS: Final[str] = "0123456789abcdef"
_KEY_ID_BYTES: Final[int] = 4
_MIN_NOTE_TEXT_LINES: Final[int] = 3
_EXTENSION_ORDER: Final[tuple[str, ...]] = ("canon", "drand", "nist")
_BUNDLE_VERSION: Final[int] = 1
_CANON_SRC_HEX_LEN: Final[int] = 64
#: U+0020. Below it, every code point is an ASCII control character, and a note may carry
#: none of them except newline (checkpoint.md §2).
_FIRST_PRINTABLE: Final[int] = 0x20

OPTIONAL_SECTIONS: Final[tuple[str, ...]] = (
    "receipts",
    "witness_cosignatures",
    "schema_attestations",
    "closure_generations",
    "webauthn_assertions",
    "archive",
)


class BundleError(ValueError):
    """The file could not be read far enough to run a check over it.

    This is not a verdict about the log. It is a verdict about the bytes handed to the
    verifier, and the CLI reports it with its own exit code so that "your bundle is
    malformed" is never mistaken for "your ledger is broken", or the reverse.
    """


# --------------------------------------------------------------------------------------
# Scalar readers. Every one names the JSON path it failed at.
# --------------------------------------------------------------------------------------


def _require(node: dict[str, Any], key: str, path: str) -> Any:
    if key not in node:
        raise BundleError(f"{path}.{key} is REQUIRED and is absent")
    return node[key]


def _as_str(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise BundleError(f"{path} must be a string, not {type(value).__name__}")
    return value


def _as_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BundleError(f"{path} must be an integer, not {type(value).__name__}")
    return value


def _as_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise BundleError(f"{path} must be true or false, not {type(value).__name__}")
    return value


def _as_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise BundleError(f"{path} must be an array, not {type(value).__name__}")
    return value


def _as_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError(f"{path} must be an object, not {type(value).__name__}")
    return value


def _as_hex_digest(value: Any, path: str) -> bytes:
    """Read a ``*_hex`` member: exactly 64 **lowercase** hex characters.

    Lowercase is normative (evidence-bundle.md §2). It is enforced rather than normalised
    because the mixed hex/base64 vocabulary in this format exists precisely so that a
    verifier cannot end up comparing one encoding to another and passing.
    """
    text = _as_str(value, path)
    if len(text) != _CANON_SRC_HEX_LEN or any(c not in _HEX_DIGITS for c in text):
        raise BundleError(f"{path} must be 64 lowercase hexadecimal characters; got {text!r}")
    return bytes.fromhex(text)


def _as_b64(value: Any, path: str) -> bytes:
    """Read a base64 member (RFC 4648 §4, padded), refusing non-canonical encodings."""
    text = _as_str(value, path)
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BundleError(f"{path} is not valid padded base64: {exc}") from exc
    if base64.b64encode(raw).decode("ascii") != text:
        raise BundleError(
            f"{path} is non-canonical base64 — it re-encodes to different characters, "
            "which means two readers can disagree about what it says"
        )
    return raw


def _as_rfc3339(value: Any, path: str) -> datetime:
    """Read an RFC 3339 timestamp, refusing a naive one.

    A naive datetime in an evidentiary payload is an unanswerable question under
    cross-examination: which clock, in which zone, on whose machine.
    """
    text = _as_str(value, path)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise BundleError(f"{path} is not an RFC 3339 timestamp: {text!r}") from exc
    if parsed.tzinfo is None:
        raise BundleError(f"{path} has no UTC offset: {text!r}")
    return parsed.astimezone(UTC)


def _optional_rfc3339(node: dict[str, Any], key: str, path: str) -> datetime | None:
    if key not in node or node[key] is None:
        return None
    return _as_rfc3339(node[key], f"{path}.{key}")


def _optional_str(node: dict[str, Any], key: str, path: str) -> str:
    if key not in node or node[key] is None:
        return ""
    return _as_str(node[key], f"{path}.{key}")


def _digest_list(value: Any, path: str) -> tuple[bytes, ...]:
    return tuple(
        _as_hex_digest(item, f"{path}[{index}]") for index, item in enumerate(_as_list(value, path))
    )


# --------------------------------------------------------------------------------------
# The signed note (spec/wire/checkpoint.md §2-§4)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignatureLine:
    """One ``— <name> <base64>`` line, decoded but **not** verified.

    Verification is check 4 and lives in ``checks/signature.py``. This module's job is to
    hand that check an unambiguous key name, key ID and signature, and to refuse to guess
    when the line is malformed.
    """

    key_name: str
    key_id: bytes
    signature: bytes
    raw: str


@dataclass(frozen=True, slots=True)
class ParsedNote:
    """A note, decomposed. ``errors`` non-empty means *do not read the other fields*.

    checkpoint.md §6 step 7: **unverified note text is not data**. The fields below are
    populated so that a verifier can *compare them against the bundle's own index* (check
    16) and so that check 4 has bytes to verify — nothing here is evidence until a
    signature over :attr:`signed_text` has been checked.
    """

    signed_text: str
    origin: str
    tree_size: int
    root: bytes
    extensions: tuple[tuple[str, str], ...]
    signature_lines: tuple[SignatureLine, ...]
    errors: tuple[str, ...]

    @property
    def signed_bytes(self) -> bytes:
        """The exact bytes a ``0x02`` signature covers: the note text, UTF-8, and nothing else."""
        return self.signed_text.encode("utf-8")

    def extension(self, name: str) -> str | None:
        """Return the value of extension line *name*, or ``None`` if it is absent."""
        for key, value in self.extensions:
            if key == name:
                return value
        return None


def _split_note(note: str) -> tuple[str, str] | None:
    """Split at the **last** empty line; the text keeps its own trailing newline."""
    index = note.rfind("\n\n")
    if index < 0:
        return None
    return note[: index + 1], note[index + 2 :]


def _control_characters(note: str) -> bool:
    """Whether the note carries an ASCII control character other than newline (§2)."""
    return any(ord(c) < _FIRST_PRINTABLE and c != "\n" for c in note)


def _parse_tree_size(line: str, errors: list[str]) -> int:
    if not line or any(c not in "0123456789" for c in line):
        errors.append(f"tree size line {line!r} is not ASCII decimal")
        return -1
    if len(line) > 1 and line[0] == "0":
        errors.append(f"tree size {line!r} has a leading zero")
        return -1
    return int(line)


def _parse_root(line: str, errors: list[str]) -> bytes:
    try:
        root = base64.b64decode(line, validate=True)
    except (binascii.Error, ValueError):
        errors.append(f"root hash line {line!r} is not valid base64")
        return b""
    if len(root) != HASH_BYTES:
        errors.append(f"root hash decodes to {len(root)} bytes, not {HASH_BYTES}")
        return b""
    return root


def _parse_extensions(lines: list[str], errors: list[str]) -> tuple[tuple[str, str], ...]:
    """Parse ``<name>: <value>`` lines, refusing duplicates and out-of-order known names."""
    extensions: list[tuple[str, str]] = []
    seen: set[str] = set()
    highest = -1
    for line in lines:
        if not line:
            errors.append("an extension line is empty")
            continue
        name, separator, value = line.partition(": ")
        if not separator or not name or not name[0].islower():
            errors.append(f"extension line {line!r} is not `<name>: <value>`")
            continue
        if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789." for c in name):
            errors.append(f"extension name {name!r} is outside [a-z][a-z0-9.]*")
            continue
        if name in seen:
            errors.append(f"extension line {name!r} appears more than once")
            continue
        seen.add(name)
        if name in _EXTENSION_ORDER:
            position = _EXTENSION_ORDER.index(name)
            if position < highest:
                errors.append(
                    f"extension line {name!r} appears out of the order the format fixes "
                    f"({', '.join(_EXTENSION_ORDER)})"
                )
            highest = max(highest, position)
        extensions.append((name, value))
    return tuple(extensions)


def _parse_signature_lines(block: str, errors: list[str]) -> tuple[SignatureLine, ...]:
    lines: list[SignatureLine] = []
    for raw in block.splitlines():
        if not raw:
            continue
        if not raw.startswith(f"{EM_DASH} "):
            errors.append(
                f"signature line {raw!r} does not begin with U+2014 and a space "
                "(a hyphen or U+2013 here parses as text and verifies against nothing)"
            )
            continue
        body = raw[2:]
        name, separator, encoded = body.partition(" ")
        if not separator or not name:
            errors.append(f"signature line {raw!r} has no key name and signature")
            continue
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            errors.append(f"signature line for {name!r} is not valid base64")
            continue
        if len(decoded) <= _KEY_ID_BYTES:
            errors.append(f"signature line for {name!r} carries no signature after the key ID")
            continue
        lines.append(
            SignatureLine(
                key_name=name,
                key_id=decoded[:_KEY_ID_BYTES],
                signature=decoded[_KEY_ID_BYTES:],
                raw=raw,
            )
        )
    return tuple(lines)


def parse_note(note: str) -> ParsedNote:
    """Decompose a C2SP signed note. Total: adversarial input yields ``errors``, never a raise.

    Follows checkpoint.md §6 in order — split, refuse control characters, parse the text,
    decode the signature lines — and stops short of step 5 because verifying a signature
    needs a key and a cryptographic library, neither of which belongs in a parser.
    """
    errors: list[str] = []
    if _control_characters(note):
        errors.append("the note contains an ASCII control character other than newline")
    split = _split_note(note)
    if split is None:
        return ParsedNote(
            "",
            "",
            -1,
            b"",
            (),
            (),
            ("the note has no empty line separating text from signatures",),
        )
    signed_text, signature_block = split
    text_lines = signed_text.split("\n")
    if text_lines and text_lines[-1] == "":
        text_lines.pop()
    if len(text_lines) < _MIN_NOTE_TEXT_LINES:
        errors.append(
            f"the note text has {len(text_lines)} lines; at least "
            f"{_MIN_NOTE_TEXT_LINES} (origin, size, root) are required"
        )
        return ParsedNote(signed_text, "", -1, b"", (), (), tuple(errors))

    origin = text_lines[0]
    if not origin:
        errors.append("the origin line is empty")
    if "+" in origin:
        errors.append("the origin line contains '+', which the vkey format forbids in a key name")
    tree_size = _parse_tree_size(text_lines[1], errors)
    root = _parse_root(text_lines[2], errors)
    extensions = _parse_extensions(text_lines[3:], errors)
    signature_lines = _parse_signature_lines(signature_block, errors)
    if not signature_lines:
        errors.append("the note carries no parseable signature line")

    return ParsedNote(
        signed_text=signed_text,
        origin=origin,
        tree_size=tree_size,
        root=root,
        extensions=extensions,
        signature_lines=signature_lines,
        errors=tuple(errors),
    )


# --------------------------------------------------------------------------------------
# Bundle sections
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Canon:
    """The bundle's declared canonicaliser: ``payload_ver`` and the source digest."""

    payload_ver: int
    canon_src_sha256: bytes


@dataclass(frozen=True, slots=True)
class TsaToken:
    """One RFC 3161 ``TimeStampToken`` over a checkpoint's note text (check 5)."""

    issuer: str
    token: bytes


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """One signed checkpoint, plus the bundle's own index fields for it.

    ``tree_size`` and ``root`` are **redundant** with :attr:`parsed` on purpose: a bundle
    whose index disagrees with its own contents was assembled by something that did not
    read them, and check 16 says so.
    """

    tree_size: int
    root: bytes
    note: str
    log_key: str
    tsa_tokens: tuple[TsaToken, ...]
    observed_at: datetime | None
    parsed: ParsedNote


@dataclass(frozen=True, slots=True)
class Leaf:
    """One sequenced ledger leaf, as carried in the bundle."""

    seq: int
    entry_id: str
    entry_kind: str
    subject_id: str
    payload_ver: int
    canon_bytes: bytes
    payload: object
    has_payload: bool
    leaf_hash: bytes
    link_hash: bytes
    prev_link_hash: bytes
    is_sandbox: bool
    actor: str
    actor_kind: str
    recorded_at: datetime | None
    batch_id: str


@dataclass(frozen=True, slots=True)
class InclusionProof:
    """RFC 6962 §2.1.1 audit path for leaf ``seq`` into the tree of size ``tree_size``."""

    seq: int
    tree_size: int
    path: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class ConsistencyProof:
    """RFC 6962 §2.1.2 proof that the tree at ``from_size`` is a prefix of ``to_size``."""

    from_size: int
    to_size: int
    path: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class Receipt:
    """A Signed Disposition Receipt envelope (``spec/wire/receipt.md`` §3).

    The envelope is not signed; only :attr:`receipt` is, over its JCS bytes. A verifier
    re-canonicalises that object and MUST NOT verify over the envelope bytes as received.
    """

    sdr_version: int
    receipt: dict[str, Any]
    key_id: str
    sig: bytes

    @property
    def leaf_hash_hex(self) -> str:
        """``receipt.leaf_hash`` as carried, or ``""`` if it is missing or not a string."""
        value = self.receipt.get("leaf_hash")
        return value if isinstance(value, str) else ""

    @property
    def entry_id(self) -> str:
        """``receipt.entry_id`` as carried, or ``""``."""
        value = self.receipt.get("entry_id")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class WitnessCosignature:
    """One witness cosignature over ``(origin, size, root)`` — check 7's input."""

    tree_size: int
    witness_id: str
    trust_domain: str
    adverse: bool
    sig_line: str
    witness_key: str
    received_at: datetime | None


@dataclass(frozen=True, slots=True)
class SchemaAttestation:
    """A trigger/constraint definition captured at migration time — check 11's input.

    ``source`` is load-bearing: ``pg_get_triggerdef`` is per-trigger, ``SHOW CREATE TABLE``
    is coarse, and a report that cannot tell them apart overstates one of them.
    """

    captured_at: datetime | None
    migration: str
    object_name: str
    kind: str
    definition: str
    definition_sha256: bytes
    source: str
    leaf_seq: int


@dataclass(frozen=True, slots=True)
class ClosureGeneration:
    """One ``clause_blame_closure`` generation row — check 14's input (adversarial finding S2)."""

    clause_uuid: str
    as_of_commit: str
    closure_gen: int
    max_severity: int
    ancestor_count: int
    truncated: bool
    leaf_seq: int


@dataclass(frozen=True, slots=True)
class WebAuthnAssertion:
    """One WebAuthn assertion and the inputs its challenge reconstructs from — check 12."""

    disposition_id: str
    credential_id: bytes
    cose_public_key: bytes
    authenticator_data: bytes
    client_data_json: bytes
    signature: bytes
    sign_count: int
    uv_required: bool
    challenge_inputs: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ArchiveObject:
    """One S3 object version recorded in the bundle — check 8's offline half."""

    tree_size: int
    key: str
    version_id: str
    object_lock_mode: str
    retain_until: datetime | None
    last_modified: datetime | None
    etag_hex: str


@dataclass(frozen=True, slots=True)
class Archive:
    """The archive section. Offline, this is a claim by us about our own archive."""

    bucket: str
    objects: tuple[ArchiveObject, ...]


@dataclass(frozen=True, slots=True)
class Bundle:
    """A whole evidence bundle, loaded and typed.

    :attr:`present` is the set of optional section names the file actually carried.
    ``"receipts" in bundle.present`` and ``bundle.receipts == ()`` are different facts:
    the first says "the bundle claims there are none", the second alone would let a check
    pass for having found nothing to look at.
    """

    subject: str
    bundle_version: int
    generated_at: str
    generator: str
    origin: str
    site_code: str
    canon: Canon
    checkpoints: tuple[Checkpoint, ...]
    consistency_proofs: tuple[ConsistencyProof, ...]
    leaves: tuple[Leaf, ...]
    inclusion_proofs: tuple[InclusionProof, ...]
    receipts: tuple[Receipt, ...]
    witness_cosignatures: tuple[WitnessCosignature, ...]
    schema_attestations: tuple[SchemaAttestation, ...]
    closure_generations: tuple[ClosureGeneration, ...]
    webauthn_assertions: tuple[WebAuthnAssertion, ...]
    webauthn_redacted: int | None
    archive: Archive | None
    present: frozenset[str]
    raw: dict[str, Any]

    def has(self, section: str) -> bool:
        """Whether the file carried *section* at all (as opposed to carrying it empty)."""
        return section in self.present

    def checkpoint_roots(self) -> dict[int, bytes]:
        """``tree_size -> root``, from the bundle's index fields."""
        return {checkpoint.tree_size: checkpoint.root for checkpoint in self.checkpoints}


# --------------------------------------------------------------------------------------
# Section readers
# --------------------------------------------------------------------------------------


def _read_canon(node: dict[str, Any]) -> Canon:
    canon = _as_object(_require(node, "canon", "$"), "$.canon")
    return Canon(
        payload_ver=_as_int(_require(canon, "payload_ver", "$.canon"), "$.canon.payload_ver"),
        canon_src_sha256=_as_hex_digest(
            _require(canon, "canon_src_sha256", "$.canon"), "$.canon.canon_src_sha256"
        ),
    )


def _read_checkpoint(node: dict[str, Any], path: str) -> Checkpoint:
    note = _as_str(_require(node, "note", path), f"{path}.note")
    tokens = tuple(
        TsaToken(
            issuer=_optional_str(_as_object(token, f"{path}.tsa_tokens[{index}]"), "issuer", path),
            token=_as_b64(
                _require(
                    _as_object(token, f"{path}.tsa_tokens[{index}]"),
                    "token_b64",
                    f"{path}.tsa_tokens[{index}]",
                ),
                f"{path}.tsa_tokens[{index}].token_b64",
            ),
        )
        for index, token in enumerate(_as_list(node.get("tsa_tokens", []), f"{path}.tsa_tokens"))
    )
    return Checkpoint(
        tree_size=_as_int(_require(node, "tree_size", path), f"{path}.tree_size"),
        root=_as_hex_digest(_require(node, "root_hex", path), f"{path}.root_hex"),
        note=note,
        log_key=_optional_str(node, "log_key", path),
        tsa_tokens=tokens,
        observed_at=_optional_rfc3339(node, "observed_at", path),
        parsed=parse_note(note),
    )


def _read_leaf(node: dict[str, Any], path: str) -> Leaf:
    return Leaf(
        seq=_as_int(_require(node, "seq", path), f"{path}.seq"),
        entry_id=_optional_str(node, "entry_id", path),
        entry_kind=_optional_str(node, "entry_kind", path),
        subject_id=_optional_str(node, "subject_id", path),
        payload_ver=_as_int(_require(node, "payload_ver", path), f"{path}.payload_ver"),
        canon_bytes=_as_b64(_require(node, "canon_bytes_b64", path), f"{path}.canon_bytes_b64"),
        payload=node.get("payload"),
        has_payload="payload" in node,
        leaf_hash=_as_hex_digest(_require(node, "leaf_hash_hex", path), f"{path}.leaf_hash_hex"),
        link_hash=_as_hex_digest(_require(node, "link_hash_hex", path), f"{path}.link_hash_hex"),
        prev_link_hash=_as_hex_digest(
            _require(node, "prev_link_hash_hex", path), f"{path}.prev_link_hash_hex"
        ),
        is_sandbox=_as_bool(_require(node, "is_sandbox", path), f"{path}.is_sandbox"),
        actor=_optional_str(node, "actor", path),
        actor_kind=_optional_str(node, "actor_kind", path),
        recorded_at=_optional_rfc3339(node, "recorded_at", path),
        batch_id=_optional_str(node, "batch_id", path),
    )


def _read_inclusion(node: dict[str, Any], path: str) -> InclusionProof:
    return InclusionProof(
        seq=_as_int(_require(node, "seq", path), f"{path}.seq"),
        tree_size=_as_int(_require(node, "tree_size", path), f"{path}.tree_size"),
        path=_digest_list(_require(node, "path_hex", path), f"{path}.path_hex"),
    )


def _read_consistency(node: dict[str, Any], path: str) -> ConsistencyProof:
    return ConsistencyProof(
        from_size=_as_int(_require(node, "from_size", path), f"{path}.from_size"),
        to_size=_as_int(_require(node, "to_size", path), f"{path}.to_size"),
        path=_digest_list(_require(node, "path_hex", path), f"{path}.path_hex"),
    )


def _read_receipt(node: dict[str, Any], path: str) -> Receipt:
    return Receipt(
        sdr_version=_as_int(_require(node, "sdr_version", path), f"{path}.sdr_version"),
        receipt=_as_object(_require(node, "receipt", path), f"{path}.receipt"),
        key_id=_as_str(_require(node, "key_id", path), f"{path}.key_id"),
        sig=_as_b64(_require(node, "sig", path), f"{path}.sig"),
    )


def _read_cosignature(node: dict[str, Any], path: str) -> WitnessCosignature:
    return WitnessCosignature(
        tree_size=_as_int(_require(node, "tree_size", path), f"{path}.tree_size"),
        witness_id=_as_str(_require(node, "witness_id", path), f"{path}.witness_id"),
        trust_domain=_as_str(_require(node, "trust_domain", path), f"{path}.trust_domain"),
        adverse=_as_bool(_require(node, "adverse", path), f"{path}.adverse"),
        sig_line=_as_str(_require(node, "sig_line", path), f"{path}.sig_line"),
        witness_key=_optional_str(node, "witness_key", path),
        received_at=_optional_rfc3339(node, "received_at", path),
    )


def _read_attestation(node: dict[str, Any], path: str) -> SchemaAttestation:
    return SchemaAttestation(
        captured_at=_optional_rfc3339(node, "captured_at", path),
        migration=_optional_str(node, "migration", path),
        object_name=_as_str(_require(node, "object", path), f"{path}.object"),
        kind=_as_str(_require(node, "kind", path), f"{path}.kind"),
        definition=_as_str(_require(node, "definition", path), f"{path}.definition"),
        definition_sha256=_as_hex_digest(
            _require(node, "definition_sha256_hex", path), f"{path}.definition_sha256_hex"
        ),
        source=_as_str(_require(node, "source", path), f"{path}.source"),
        leaf_seq=_as_int(_require(node, "leaf_seq", path), f"{path}.leaf_seq"),
    )


def _read_closure(node: dict[str, Any], path: str) -> ClosureGeneration:
    return ClosureGeneration(
        clause_uuid=_as_str(_require(node, "clause_uuid", path), f"{path}.clause_uuid"),
        as_of_commit=_as_str(_require(node, "as_of_commit", path), f"{path}.as_of_commit"),
        closure_gen=_as_int(_require(node, "closure_gen", path), f"{path}.closure_gen"),
        max_severity=_as_int(_require(node, "max_severity", path), f"{path}.max_severity"),
        ancestor_count=_as_int(_require(node, "ancestor_count", path), f"{path}.ancestor_count"),
        truncated=_as_bool(_require(node, "truncated", path), f"{path}.truncated"),
        leaf_seq=_as_int(_require(node, "leaf_seq", path), f"{path}.leaf_seq"),
    )


def _read_webauthn(node: dict[str, Any], path: str) -> WebAuthnAssertion:
    return WebAuthnAssertion(
        disposition_id=_as_str(_require(node, "disposition_id", path), f"{path}.disposition_id"),
        credential_id=_as_b64(
            _require(node, "credential_id_b64", path), f"{path}.credential_id_b64"
        ),
        cose_public_key=_as_b64(
            _require(node, "cose_public_key_b64", path), f"{path}.cose_public_key_b64"
        ),
        authenticator_data=_as_b64(
            _require(node, "authenticator_data_b64", path), f"{path}.authenticator_data_b64"
        ),
        client_data_json=_as_b64(
            _require(node, "client_data_json_b64", path), f"{path}.client_data_json_b64"
        ),
        signature=_as_b64(_require(node, "signature_b64", path), f"{path}.signature_b64"),
        sign_count=_as_int(_require(node, "sign_count", path), f"{path}.sign_count"),
        uv_required=_as_bool(_require(node, "uv_required", path), f"{path}.uv_required"),
        challenge_inputs=_as_object(
            _require(node, "challenge_inputs", path), f"{path}.challenge_inputs"
        ),
    )


def _read_archive_object(node: dict[str, Any], path: str) -> ArchiveObject:
    return ArchiveObject(
        tree_size=_as_int(_require(node, "tree_size", path), f"{path}.tree_size"),
        key=_as_str(_require(node, "key", path), f"{path}.key"),
        version_id=_optional_str(node, "version_id", path),
        object_lock_mode=_optional_str(node, "object_lock_mode", path),
        retain_until=_optional_rfc3339(node, "retain_until", path),
        last_modified=_optional_rfc3339(node, "last_modified", path),
        etag_hex=_optional_str(node, "etag_hex", path),
    )


def _read_archive(node: dict[str, Any]) -> Archive:
    objects = _as_list(node.get("objects", []), "$.archive.objects")
    return Archive(
        bucket=_optional_str(node, "bucket", "$.archive"),
        objects=tuple(
            _read_archive_object(
                _as_object(item, f"$.archive.objects[{i}]"), f"$.archive.objects[{i}]"
            )
            for i, item in enumerate(objects)
        ),
    )


def _read_webauthn_section(
    node: dict[str, Any],
) -> tuple[tuple[WebAuthnAssertion, ...], int | None]:
    """Return the assertions, or the count when ``--redact-webauthn`` produced the bundle."""
    if "webauthn_assertions" not in node:
        return (), None
    section = node["webauthn_assertions"]
    if isinstance(section, dict) and section.get("redacted") is True:
        return (), _as_int(section.get("count", 0), "$.webauthn_assertions.count")
    return (
        tuple(
            _read_webauthn(
                _as_object(item, f"$.webauthn_assertions[{i}]"), f"$.webauthn_assertions[{i}]"
            )
            for i, item in enumerate(_as_list(section, "$.webauthn_assertions"))
        ),
        None,
    )


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for name, value in pairs:
        if name in seen:
            raise BundleError(
                f"JSON member {name!r} appears more than once. A loader that resolved this "
                "would be choosing, on the writer's behalf, which of two records you are "
                "looking at."
            )
        seen[name] = value
    return seen


def _read_section(
    node: dict[str, Any],
    key: str,
    reader: Any,
) -> tuple[Any, ...]:
    return tuple(
        reader(_as_object(item, f"$.{key}[{i}]"), f"$.{key}[{i}]")
        for i, item in enumerate(_as_list(node.get(key, []), f"$.{key}"))
    )


def loads_bundle(text: str | bytes, subject: str = "<stdin>") -> Bundle:
    """Parse an evidence bundle from JSON text.

    Raises :class:`BundleError` on anything the checks could not be run over.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    try:
        node = json.loads(text, object_pairs_hook=_reject_duplicate_members)
    except json.JSONDecodeError as exc:
        raise BundleError(f"{subject} is not valid JSON: {exc}") from exc
    if not isinstance(node, dict):
        raise BundleError(f"{subject} is not a JSON object")

    version = _as_int(_require(node, "bundle_version", "$"), "$.bundle_version")
    if version != _BUNDLE_VERSION:
        raise BundleError(
            f"$.bundle_version is {version}; this verifier implements v1.0 and refuses to "
            "guess at a format it has not read"
        )

    checkpoints = _read_section(node, "checkpoints", _read_checkpoint)
    if not checkpoints:
        raise BundleError("$.checkpoints is REQUIRED and must carry at least one checkpoint")

    present = frozenset(name for name in OPTIONAL_SECTIONS if name in node)
    assertions, redacted = _read_webauthn_section(node)

    return Bundle(
        subject=subject,
        bundle_version=version,
        generated_at=_optional_str(node, "generated_at", "$"),
        generator=_optional_str(node, "generator", "$"),
        origin=_optional_str(node, "origin", "$"),
        site_code=_optional_str(node, "site_code", "$"),
        canon=_read_canon(node),
        checkpoints=checkpoints,
        consistency_proofs=_read_section(node, "consistency_proofs", _read_consistency),
        leaves=_read_section(node, "leaves", _read_leaf),
        inclusion_proofs=_read_section(node, "inclusion_proofs", _read_inclusion),
        receipts=_read_section(node, "receipts", _read_receipt),
        witness_cosignatures=_read_section(node, "witness_cosignatures", _read_cosignature),
        schema_attestations=_read_section(node, "schema_attestations", _read_attestation),
        closure_generations=_read_section(node, "closure_generations", _read_closure),
        webauthn_assertions=assertions,
        webauthn_redacted=redacted,
        archive=(
            _read_archive(_as_object(node["archive"], "$.archive")) if "archive" in node else None
        ),
        present=present,
        raw=node,
    )


def load_bundle(path: Path | str) -> Bundle:
    """Read and parse an evidence bundle from disk."""
    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as exc:
        raise BundleError(f"cannot read {location}: {exc}") from exc
    return loads_bundle(text, subject=str(location))
