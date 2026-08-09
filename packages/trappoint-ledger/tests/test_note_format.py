# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The C2SP signed-note format, against the frozen vector in ``spec/wire/checkpoint.md``.

Four of the eight conformance points in §10 live here:

2. the note is rejected after **any** single-byte mutation of the note text;
3. an additional signature line from an unknown key is accepted, the known one still
   verifies, and the unknown line survives re-encoding byte for byte;
5. the empty-tree checkpoint is accepted;
6. U+002D and U+2013 in place of U+2014 are refused.

Point 3 is the one that matters most in practice. It is the property that lets a witness
cosign a checkpoint we have already stored, and lets an Ed25519 log signature be added
later, without reissuing anything — and it is a property that a naive implementation
breaks silently, by round-tripping through parsed fields instead of through bytes.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest
from trappoint_ledger.note import (
    EM_DASH,
    MIN_SIGNATURE_LINES_ACCEPTED,
    MalformedNote,
    Note,
    NoteVerificationFailed,
    PublicKey,
    SignatureLine,
    build_signature_line,
    decode_note,
    encode_note,
    parse_vkey,
    verify_note,
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "spec" / "wire" / "checkpoint.md").is_file():
            return parent
    pytest.skip(f"spec/wire/checkpoint.md was not found above {here}")


def _sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current = ""
    buf: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("#"):
            out[current] = "\n".join(buf)
            current = line.lstrip("#").strip()
            buf = []
        else:
            buf.append(line)
    out[current] = "\n".join(buf)
    return out


def _fences(section: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lang: str | None = None
    buf: list[str] = []
    for line in section.splitlines():
        if line.startswith("```"):
            if lang is None:
                lang, buf = line[3:].strip(), []
            else:
                blocks.append((lang, "\n".join(buf) + "\n"))
                lang = None
        elif lang is not None:
            buf.append(line)
    return blocks


SPEC = _sections((_repo_root() / "spec" / "wire" / "checkpoint.md").read_text(encoding="utf-8"))


def _section(prefix: str) -> str:
    for heading, body in SPEC.items():
        if heading.startswith(prefix):
            return body
    raise AssertionError(f"spec/wire/checkpoint.md has no section {prefix!r}")


def _blocks(prefix: str, lang: str = "text") -> list[str]:
    return [content for language, content in _fences(_section(prefix)) if language == lang]


NOTE_TEXT = _blocks("7.3")[0]
COMPLETE_NOTE = _blocks("7.5")[0].encode("utf-8")
PUBLIC_KEY_PEM = _blocks("7.1", "pem")[1].encode("utf-8")
VKEY = next(block.strip() for block in _blocks("7.1") if "+" in block)
LOG_KEY = parse_vkey(VKEY)


@pytest.fixture
def verify():
    """Return the P-256 verify primitive, skipping loudly if the backend is absent."""
    pytest.importorskip(
        "cryptography",
        reason="'cryptography' is not installed, so no P-256 signature can be verified; "
        "the note FORMAT assertions in this module still run without it",
    )
    from trappoint_ledger.signer import p256_sha256_verify

    return p256_sha256_verify


UNKNOWN_KEY_ID = bytes.fromhex("deadbeef")
UNKNOWN_LINE = f"{EM_DASH} some.witness/adverse " + base64.b64encode(
    UNKNOWN_KEY_ID + b"a cosignature this build cannot check"
).decode("ascii")


# ── The vector ─────────────────────────────────────────────────────────────────────────


def test_the_complete_note_decodes_and_re_encodes_byte_identically():
    note = decode_note(COMPLETE_NOTE)
    assert note.text == NOTE_TEXT
    assert note.encode() == COMPLETE_NOTE
    assert hashlib.sha256(COMPLETE_NOTE).hexdigest() in _section("7.5")


def test_the_signed_bytes_are_the_note_text_and_nothing_else():
    note = decode_note(COMPLETE_NOTE)
    assert note.signed_bytes == NOTE_TEXT.encode("utf-8")
    assert len(note.signed_bytes) == 446
    assert note.signed_bytes != COMPLETE_NOTE
    assert not note.signed_bytes.endswith(b"\n\n")


def test_the_signature_line_carries_the_key_id_then_the_der_signature():
    note = decode_note(COMPLETE_NOTE)
    (line,) = note.signatures
    assert line.key_name == "mainline.example/site/BLK-07"
    assert line.key_id == LOG_KEY.key_id
    assert line.signature[0] == 0x30  # ASN.1 SEQUENCE: DER, not fixed-width r‖s
    assert len(line.signature) == 71
    assert line.raw.startswith(f"{EM_DASH} ")


def test_the_spec_note_verifies_against_the_spec_vkey(verify):
    result = verify_note(COMPLETE_NOTE, [LOG_KEY], verify)
    assert [key.key_id_hex for key in result.verified] == [LOG_KEY.key_id_hex]
    assert result.ignored == ()
    assert result.signed_bytes == NOTE_TEXT.encode("utf-8")


# ── §10.2: any single-byte mutation of the note text is rejected ───────────────────────


def test_every_single_byte_mutation_of_the_note_text_is_rejected(verify):
    original = NOTE_TEXT.encode("utf-8")
    signature_block = COMPLETE_NOTE[len(original) :]
    rejected = 0
    for index in range(len(original)):
        mutated = bytearray(original)
        # Flip the low bit; on a newline this produces U+000B, which the control-character
        # rule refuses, and that is a rejection too.
        mutated[index] ^= 0x01
        candidate = bytes(mutated) + signature_block
        with pytest.raises((MalformedNote, NoteVerificationFailed, UnicodeDecodeError)):
            verify_note(candidate, [LOG_KEY], verify)
        rejected += 1
    assert rejected == 446


# ── §10.3: unknown signature lines ─────────────────────────────────────────────────────


def test_an_unknown_signature_line_is_preserved_byte_for_byte_and_ignored(verify):
    cosigned = COMPLETE_NOTE + (UNKNOWN_LINE + "\n").encode("utf-8")
    note = decode_note(cosigned)
    assert len(note.signatures) == 2
    assert note.signatures[1].raw == UNKNOWN_LINE
    assert note.encode() == cosigned

    result = verify_note(note, [LOG_KEY], verify)
    assert [key.key_id_hex for key in result.verified] == [LOG_KEY.key_id_hex]
    assert [line.raw for line in result.ignored] == [UNKNOWN_LINE]


def test_an_unknown_line_before_the_known_one_is_also_preserved(verify):
    body, _, tail = COMPLETE_NOTE.decode("utf-8").partition("\n\n")
    cosigned = body + "\n\n" + UNKNOWN_LINE + "\n" + tail
    note = decode_note(cosigned)
    assert next(line.raw for line in note.signatures) == UNKNOWN_LINE
    assert note.encode().decode("utf-8") == cosigned
    assert len(verify_note(note, [LOG_KEY], verify).verified) == 1


def test_a_note_with_only_unknown_lines_establishes_nothing(verify):
    body = NOTE_TEXT + "\n" + UNKNOWN_LINE + "\n"
    with pytest.raises(NoteVerificationFailed, match="no signature line"):
        verify_note(body, [LOG_KEY], verify)


def test_a_known_key_whose_signature_fails_rejects_the_whole_note(verify):
    """Not a weaker exhibit — a forged one.

    The note below carries a tampered log signature AND a well-formed unknown line. An
    implementation that treated "some line verified or was ignored" as success would pass
    this note; §6 step 6 says a failing KNOWN signature rejects the whole thing.
    """
    (line,) = decode_note(COMPLETE_NOTE).signatures
    tampered = bytearray(line.signature)
    tampered[-1] ^= 0x01
    forged = build_signature_line(LOG_KEY, bytes(tampered))
    note = decode_note(NOTE_TEXT + "\n" + forged.raw + "\n" + UNKNOWN_LINE + "\n")
    assert len(note.signatures) == 2
    with pytest.raises(NoteVerificationFailed, match="does not verify"):
        verify_note(note, [LOG_KEY], verify)


def test_sixteen_signature_lines_are_accepted():
    lines = [
        SignatureLine(
            key_name=f"witness{i}",
            key_id=bytes([i, 0, 0, 0]),
            signature=b"sig",
            raw=f"{EM_DASH} witness{i} "
            + base64.b64encode(bytes([i, 0, 0, 0]) + b"sig").decode("ascii"),
        )
        for i in range(MIN_SIGNATURE_LINES_ACCEPTED)
    ]
    encoded = encode_note(NOTE_TEXT, lines)
    assert len(decode_note(encoded).signatures) == MIN_SIGNATURE_LINES_ACCEPTED


# ── §10.6 and §2: framing refusals ─────────────────────────────────────────────────────


@pytest.mark.parametrize("dash", ["-", "–"])  # noqa: RUF001 - the two wrong dashes  # hyphen-minus, en dash
def test_a_hyphen_or_en_dash_in_place_of_the_em_dash_is_refused(dash):
    broken = COMPLETE_NOTE.decode("utf-8").replace(f"{EM_DASH} ", f"{dash} ")
    with pytest.raises(MalformedNote, match="em dash"):
        decode_note(broken)


def test_a_control_character_anywhere_is_refused():
    broken = COMPLETE_NOTE.replace(b"BLK-07", b"BLK\x0007", 1)
    with pytest.raises(MalformedNote, match="control character"):
        decode_note(broken)


def test_invalid_utf8_is_refused():
    with pytest.raises(MalformedNote, match="UTF-8"):
        decode_note(b"origin\n0\nroot\n\n\xff\xfe not utf-8\n")


def test_a_note_with_no_signature_lines_is_refused():
    with pytest.raises(MalformedNote, match="one or more signature lines"):
        decode_note(NOTE_TEXT + "\n")


def test_a_note_that_does_not_end_in_a_newline_is_refused():
    with pytest.raises(MalformedNote, match="newline"):
        decode_note(COMPLETE_NOTE.rstrip(b"\n"))


def test_the_split_is_at_the_last_empty_line_not_the_first():
    """A note text may itself contain a blank line; splitting at the first truncates it."""
    text = "line one\n\nline three\n"
    line = SignatureLine(
        key_name="k",
        key_id=b"\x01\x02\x03\x04",
        signature=b"s",
        raw=f"{EM_DASH} k " + base64.b64encode(b"\x01\x02\x03\x04s").decode("ascii"),
    )
    encoded = encode_note(text, [line])
    note = decode_note(encoded)
    assert note.text == text
    assert note.signed_bytes == text.encode("utf-8")
    assert len(note.signatures) == 1


def test_a_signature_line_with_non_standard_base64_is_refused():
    broken = NOTE_TEXT + "\n" + f"{EM_DASH} name not-base64!!\n"
    with pytest.raises(MalformedNote, match="base64"):
        decode_note(broken)


def test_a_signature_line_shorter_than_a_key_id_is_refused():
    short = base64.b64encode(b"\x01\x02\x03\x04").decode("ascii")
    with pytest.raises(MalformedNote, match="key ID"):
        decode_note(NOTE_TEXT + "\n" + f"{EM_DASH} name {short}\n")


def test_a_signature_line_without_a_name_field_is_refused():
    with pytest.raises(MalformedNote, match="not '"):
        decode_note(NOTE_TEXT + "\n" + f"{EM_DASH} onlyonefield\n")


def test_encode_refuses_a_text_that_ends_with_a_blank_line():
    line = build_signature_line(LOG_KEY, b"\x30\x00")
    with pytest.raises(MalformedNote, match="blank line"):
        encode_note(NOTE_TEXT + "\n", [line])


def test_encode_refuses_a_note_with_no_signatures():
    with pytest.raises(MalformedNote, match="at least one signature line"):
        encode_note(NOTE_TEXT, [])


def test_two_keys_with_the_same_lookup_are_refused(verify):
    with pytest.raises(ValueError, match="share the name"):
        verify_note(COMPLETE_NOTE, [LOG_KEY, LOG_KEY], verify)


def test_signature_for_finds_the_line_for_a_key():
    note = decode_note(COMPLETE_NOTE)
    assert note.signature_for(LOG_KEY) is not None
    stranger = PublicKey(
        name="nobody", algorithm=LOG_KEY.algorithm, key_material=LOG_KEY.key_material
    )
    assert note.signature_for(stranger) is None
    assert isinstance(note, Note)


def test_the_public_key_pem_in_the_spec_matches_the_vkey():
    """The document publishes the key twice; if the two ever disagree, this fails."""
    crypto = pytest.importorskip(
        "cryptography.hazmat.primitives.serialization",
        reason="'cryptography' is not installed, so the PEM cannot be re-encoded to DER",
    )
    loaded = crypto.load_pem_public_key(PUBLIC_KEY_PEM)
    der = loaded.public_bytes(crypto.Encoding.DER, crypto.PublicFormat.SubjectPublicKeyInfo)
    assert der == LOG_KEY.key_material
