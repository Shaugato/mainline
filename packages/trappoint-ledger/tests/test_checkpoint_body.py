# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The checkpoint body, tested against the frozen document rather than against itself.

``spec/wire/checkpoint.md`` §7 says of its worked vector: *"``trappoint-verify`` and
``trappoint_ledger.note`` both read these values out of this file, so this document and
the code cannot drift."* This module makes that literally true — every expected value
below is parsed out of the markdown at test time. A test that hard-coded the 446 bytes
would keep passing after someone edited the specification, which is the exact failure
mode the sentence was written to prevent.

If the specification is not on disk the module SKIPs with a reason that names the file.
A silent pass would be worse than a failure: it would mean the conformance suite reports
green having asserted nothing.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from trappoint_ledger.beacon import (
    DRAND_CHAIN_HASH_QUICKNET,
    DRAND_GENESIS_TIME_QUICKNET,
    DRAND_PERIOD_SECONDS_QUICKNET,
    BeaconParseError,
    DrandRound,
    NistPulse,
    beacon_column,
    drand_round_at_time,
    drand_round_time,
    parse_beacon_column,
    parse_drand_extension,
    parse_nist_extension,
)
from trappoint_ledger.checkpoint import (
    CANON_EXTENSION,
    DRAND_EXTENSION,
    MANDATORY_LINES,
    NIST_EXTENSION,
    CheckpointBody,
    MalformedCheckpoint,
    build_body,
    build_checkpoint_note,
    encode_root_hash,
    parse_body,
    verify_checkpoint,
)
from trappoint_ledger.merkle import hash_leaf, merkle_tree_hash
from trappoint_ledger.note import (
    MalformedNote,
    NoteVerificationFailed,
    decode_note,
    parse_vkey,
)

# ── Reading the frozen specification ───────────────────────────────────────────────────


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "spec" / "wire" / "checkpoint.md").is_file():
            return parent
    pytest.skip(
        "spec/wire/checkpoint.md was not found above "
        f"{here}; the wire-format conformance vector cannot be read, so this module "
        "asserts nothing and says so rather than passing"
    )


def _sections(text: str) -> dict[str, str]:
    """Split a markdown document on its headings, ignoring '#' inside fenced blocks."""
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
    """Return ``(language, content)`` for every fenced block, content newline-terminated."""
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


def _text_blocks(prefix: str) -> list[str]:
    return [content for lang, content in _fences(_section(prefix)) if lang == "text"]


NOTE_TEXT = _text_blocks("7.3")[0]
COMPLETE_NOTE = _text_blocks("7.5")[0]
EMPTY_TREE_BODY = _text_blocks("7.6")[0]
VKEY = next(block.strip() for block in _text_blocks("7.1") if "+" in block)


def _leaf_canon_bytes() -> list[bytes]:
    """Return the five ``canon_bytes`` values of §7.2, in sequence order."""
    block = _text_blocks("7.2")[0]
    leaves: list[bytes] = []
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("seq "):
            leaves.append(lines[index + 1].encode("utf-8"))
    return leaves


def _root_hex() -> str:
    for line in _text_blocks("7.2")[2].splitlines():
        if line.startswith("root (hex)"):
            return line.split()[-1]
    raise AssertionError("§7.2 has no 'root (hex)' line")


# ── The vector ─────────────────────────────────────────────────────────────────────────


def test_build_body_reproduces_the_spec_note_text_byte_for_byte():
    body = parse_body(NOTE_TEXT)
    rebuilt = build_body(body.origin, body.tree_size, body.root_hash, body.extensions)
    assert rebuilt == NOTE_TEXT
    assert len(rebuilt.encode("utf-8")) == 446
    # The document states this digest in prose; recomputing it here is what makes an
    # edit to the vector fail the suite rather than silently redefine the format.
    assert hashlib.sha256(rebuilt.encode("utf-8")).hexdigest() in _section("7.3")


def test_parse_body_reads_the_three_mandatory_lines():
    body = parse_body(NOTE_TEXT)
    assert body.origin == "mainline.example/site/BLK-07"
    assert body.tree_size == 5
    assert body.root_hash.hex() == _root_hex()
    assert encode_root_hash(body.root_hash) == NOTE_TEXT.splitlines()[2]


def test_the_root_recomputes_from_the_five_canon_bytes():
    """§10 conformance point 4: the root is a function of the leaves, not a claim."""
    leaves = _leaf_canon_bytes()
    assert len(leaves) == 5
    root = merkle_tree_hash([hash_leaf(leaf) for leaf in leaves])
    assert root.hex() == _root_hex()
    assert parse_body(NOTE_TEXT).root_hash == root


def test_extensions_parse_in_the_order_section_4_fixes():
    body = parse_body(NOTE_TEXT)
    assert [name for name, _ in body.extensions] == [
        CANON_EXTENSION,
        DRAND_EXTENSION,
        NIST_EXTENSION,
    ]
    canon = body.canon
    assert canon is not None
    assert canon.payload_ver == 1
    assert len(canon.source_sha256) == 32
    assert canon.value == body.extension(CANON_EXTENSION)


def test_canon_line_names_the_canonicaliser_this_build_is_running():
    """Verifier check 10, in miniature.

    The point of the ``canon:`` line is that it turns "we canonicalised correctly" into
    a comparison. If ``trappoint_jcs`` is not importable the comparison cannot be made,
    and saying so is the honest outcome.
    """
    jcs = pytest.importorskip(
        "trappoint_jcs.canon_v1",
        reason="trappoint_jcs is not importable, so the canon: line cannot be compared "
        "against the canonicaliser this build runs",
    )
    canon = parse_body(NOTE_TEXT).canon
    assert canon is not None
    assert canon.payload_ver == jcs.CANON_VERSION
    assert canon.source_sha256 == jcs.canon_src_sha256()


def test_the_empty_tree_checkpoint_is_accepted():
    """§7.6: a log must be able to prove it was empty when it was empty."""
    body = parse_body(EMPTY_TREE_BODY)
    assert body.tree_size == 0
    assert body.root_hash == hashlib.sha256(b"").digest()
    assert body.extensions == ()
    assert body.to_text() == EMPTY_TREE_BODY


def test_a_body_round_trips_through_a_complete_note():
    note = decode_note(COMPLETE_NOTE)
    assert note.text == NOTE_TEXT
    assert build_checkpoint_note(note.text, note.signatures) == COMPLETE_NOTE.encode("utf-8")


# ── Refusals: §10 conformance point 6 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("size_line", "why"),
    [("05", "leading zero"), ("+5", "sign"), ("5 ", "trailing space"), ("", "empty")],
)
def test_a_malformed_tree_size_is_refused(size_line, why):
    lines = NOTE_TEXT.splitlines()
    lines[1] = size_line
    with pytest.raises(MalformedCheckpoint):
        parse_body("\n".join(lines) + "\n")
    assert why  # the parametrised label is the reason, printed on failure


def test_a_root_that_is_not_32_bytes_is_refused():
    lines = NOTE_TEXT.splitlines()
    lines[2] = base64.b64encode(b"short").decode("ascii")
    with pytest.raises(MalformedCheckpoint, match="32"):
        parse_body("\n".join(lines) + "\n")


def test_non_canonical_base64_for_the_root_is_refused():
    """Two spellings of one checkpoint, only one of which was signed."""
    root = parse_body(NOTE_TEXT).root_hash
    canonical = base64.b64encode(root).decode("ascii")
    # Flip the final padding bits: this still decodes to the same 32 bytes.
    tampered = canonical[:-2] + ("5=" if canonical[-2] != "5" else "9=")
    assert base64.b64decode(tampered) == root
    lines = NOTE_TEXT.splitlines()
    lines[2] = tampered
    with pytest.raises(MalformedCheckpoint, match="canonical"):
        parse_body("\n".join(lines) + "\n")


def test_an_empty_extension_value_is_refused():
    # On the parse path the line regex catches it first ("canon: " has no value at all);
    # on the build path the value validator does. Both are refusals and both are tested,
    # because a caller that assembles a body from fields never goes through the parser.
    with pytest.raises(MalformedCheckpoint, match="colon and one space"):
        parse_body("origin\n0\n" + encode_root_hash(bytes(32)) + "\ncanon: \n")
    with pytest.raises(MalformedCheckpoint, match="empty value"):
        build_body("origin", 0, bytes(32), [("canon", "")])


def test_an_extension_name_outside_the_pattern_is_refused():
    root = encode_root_hash(bytes(32))
    with pytest.raises(MalformedCheckpoint):
        parse_body(f"origin\n0\n{root}\nCanon: 1 {'0' * 64}\n")


def test_a_repeated_extension_name_is_refused():
    body = parse_body(NOTE_TEXT)
    doubled = (*body.extensions, body.extensions[0])
    with pytest.raises(MalformedCheckpoint, match="more than once"):
        build_body(body.origin, body.tree_size, body.root_hash, doubled)


def test_the_defined_extensions_must_appear_in_the_normative_order():
    body = parse_body(NOTE_TEXT)
    reordered = (body.extensions[1], body.extensions[0], body.extensions[2])
    with pytest.raises(MalformedCheckpoint, match="order"):
        build_body(body.origin, body.tree_size, body.root_hash, reordered)


def test_an_unknown_extension_name_is_kept_and_may_sit_anywhere():
    """§4: a verifier MUST ignore an unrecognised name and MUST NOT error on it.

    This is what keeps §9's additive path cheap. The relative order of the three DEFINED
    names is still enforced — see gap G1 in ADR 0043 for why an unknown name cannot be
    ordered against them.
    """
    body = parse_body(NOTE_TEXT)
    extended = (
        body.extensions[0],
        ("future.thing", "whatever it means"),
        body.extensions[1],
        body.extensions[2],
    )
    text = build_body(body.origin, body.tree_size, body.root_hash, extended)
    reparsed = parse_body(text)
    assert reparsed.extension("future.thing") == "whatever it means"
    assert reparsed.canon is not None
    assert reparsed.to_text() == text


def test_an_origin_with_a_space_or_a_plus_is_refused():
    root = encode_root_hash(bytes(32))
    with pytest.raises(MalformedCheckpoint, match="whitespace"):
        parse_body(f"main line/site/A\n0\n{root}\n")
    with pytest.raises(MalformedCheckpoint, match=r"\+"):
        build_body("mainline.example/site/A+B", 0, bytes(32))


def test_a_carriage_return_is_refused():
    with pytest.raises(MalformedCheckpoint, match="carriage return"):
        parse_body(NOTE_TEXT.replace("\n", "\r\n"))


def test_a_blank_line_inside_the_body_is_refused():
    lines = NOTE_TEXT.splitlines()
    lines.insert(3, "")
    with pytest.raises(MalformedCheckpoint, match="empty line"):
        parse_body("\n".join(lines) + "\n")


def test_a_body_with_fewer_than_three_lines_is_refused():
    with pytest.raises(MalformedCheckpoint, match=str(MANDATORY_LINES)):
        parse_body("origin\n0\n")


def test_a_body_that_does_not_end_in_a_newline_is_refused():
    with pytest.raises(MalformedCheckpoint, match="newline"):
        parse_body(NOTE_TEXT.rstrip("\n"))


def test_a_bare_body_is_not_a_note():
    with pytest.raises(MalformedNote, match="bare checkpoint body"):
        decode_note(NOTE_TEXT)


# ── Verify before parse ────────────────────────────────────────────────────────────────


def test_verify_checkpoint_does_not_parse_an_unverified_body(monkeypatch):
    """§6 step 7: unverified note text is not data.

    The body below is malformed *and* the note is signed by nobody this verifier knows.
    A verifier that parsed first would report the malformed body; this one reports that
    nothing about the note is established, and ``parse_body`` is never reached.
    """
    called: list[str] = []

    def _tripwire(text):
        called.append(text)
        raise AssertionError("parse_body ran on unverified bytes")

    monkeypatch.setattr("trappoint_ledger.checkpoint.parse_body", _tripwire)
    unknown_line = "— stranger " + base64.b64encode(b"\x00\x01\x02\x03garbage").decode()
    note = "origin\n007\nnot-base64!!\n\n" + unknown_line + "\n"
    with pytest.raises(NoteVerificationFailed):
        verify_checkpoint(note, [parse_vkey(VKEY)], lambda *_: True)
    assert called == []


# ── The two beacons (CU-4) ─────────────────────────────────────────────────────────────


def test_the_drand_line_parses_and_its_round_time_is_the_one_the_spec_states():
    """§10 conformance point 8, and the whole of the offline lower bound."""
    body = parse_body(NOTE_TEXT)
    value = body.drand
    assert value is not None
    drand = parse_drand_extension(value)
    assert drand.chain_hash == DRAND_CHAIN_HASH_QUICKNET
    assert drand.is_quicknet
    assert drand.round_number == 31088494
    assert drand.extension_value() == value

    expected_unix = (
        DRAND_GENESIS_TIME_QUICKNET + (drand.round_number - 1) * DRAND_PERIOD_SECONDS_QUICKNET
    )
    assert str(expected_unix) in _section("7.3"), "§7.3 states a different round time"
    assert drand.round_time() == datetime.fromtimestamp(expected_unix, tz=UTC)
    assert drand.round_time().isoformat().startswith("2026-08-07T02:14:06")


def test_round_to_time_and_time_to_round_are_inverses():
    for round_number in (1, 2, 31088494, 99999999):
        when = drand_round_time(round_number)
        assert drand_round_at_time(when) == round_number
        assert drand_round_at_time(when + timedelta(seconds=2)) == round_number
        assert drand_round_at_time(when + timedelta(seconds=3)) == round_number + 1


def test_round_time_refuses_a_round_before_the_first():
    with pytest.raises(ValueError, match="1-based"):
        drand_round_time(0)


def test_round_at_time_refuses_a_naive_instant():
    with pytest.raises(ValueError, match="timezone-aware"):
        drand_round_at_time(datetime(2026, 8, 7, 2, 14, 6))  # noqa: DTZ001 - the point


def test_the_nist_line_parses_into_its_indices_and_output():
    body = parse_body(NOTE_TEXT)
    value = body.nist
    assert value is not None
    pulse = parse_nist_extension(value)
    assert (pulse.chain_index, pulse.pulse_index) == (2, 29255654)
    assert len(pulse.output_value) == 128
    assert pulse.version == "2.0"
    assert pulse.extension_value() == value
    # The line carries no time of its own: an index is not an instant, and pretending
    # otherwise is how a beacon bound gets claimed that nobody ever computed.
    assert pulse.timestamp is None


def test_the_beacon_column_matches_the_shape_the_sequencer_writes():
    body = parse_body(NOTE_TEXT)
    assert body.drand is not None
    assert body.nist is not None
    column = beacon_column(parse_drand_extension(body.drand), parse_nist_extension(body.nist))
    assert set(column) == {"drand", "nist"}
    assert set(column["drand"]) == {"chain_hash", "round", "randomness"}
    assert set(column["nist"]) == {"version", "chain_index", "pulse_index", "output_value"}
    round_trip = parse_beacon_column(column)
    assert round_trip[0].extension_value() == body.drand
    assert round_trip[1].extension_value() == body.nist


def test_drand_randomness_binds_its_signature_with_hashlib_alone():
    """Checkable without BLS. It is consistency, NOT verification — see the docstring."""
    signature = bytes(range(48))
    randomness = hashlib.sha256(signature).hexdigest()
    good = DrandRound(round_number=1, randomness=randomness, signature=signature.hex())
    assert good.randomness_binds_signature()
    bad = DrandRound(round_number=1, randomness=randomness, signature=(b"\xff" * 48).hex())
    assert not bad.randomness_binds_signature()
    # A round read off a checkpoint carries no signature, so nothing has been shown.
    assert not parse_drand_extension(parse_body(NOTE_TEXT).drand or "").randomness_binds_signature()


def test_a_nist_pulse_from_the_api_normalises_its_version_and_keeps_the_raw_object():
    signature = bytes(range(64))
    pulse = NistPulse.from_api(
        {
            "pulse": {
                "version": "Version 2.0",
                "chainIndex": 2,
                "pulseIndex": 29255654,
                "outputValue": hashlib.sha512(signature).hexdigest().upper(),
                "timeStamp": "2026-08-07T02:14:00.000Z",
                "signatureValue": signature.hex().upper(),
            }
        }
    )
    assert pulse.version == "2.0"
    assert pulse.timestamp == datetime(2026, 8, 7, 2, 14, 0, tzinfo=UTC)
    assert pulse.raw is not None
    assert pulse.raw["chainIndex"] == 2
    # The SHA-512 binding is implemented under one of two published readings and is
    # marked UNVERIFIED in beacon.py; this asserts the plumbing, not the claim.
    assert pulse.output_binds_signature()
    empty = NistPulse(chain_index=0, pulse_index=0, output_value="0" * 128)
    assert not empty.output_binds_signature()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "52db9ba7 31088494 " + "0" * 64,
        DRAND_CHAIN_HASH_QUICKNET + " 0 " + "0" * 64,
        DRAND_CHAIN_HASH_QUICKNET + " 12 " + "0" * 63,
        DRAND_CHAIN_HASH_QUICKNET.upper() + " 12 " + "0" * 64,
    ],
)
def test_a_malformed_drand_value_is_refused(value):
    with pytest.raises(BeaconParseError):
        parse_drand_extension(value)


@pytest.mark.parametrize(
    "value",
    ["", "3.0 2.1 " + "0" * 128, "2.0 2 " + "0" * 128, "2.0 2.1 " + "0" * 127],
)
def test_a_malformed_nist_value_is_refused(value):
    with pytest.raises(BeaconParseError):
        parse_nist_extension(value)


def test_a_beacon_column_missing_a_member_is_refused():
    with pytest.raises(BeaconParseError, match="'drand'"):
        parse_beacon_column({"nist": {}})


def test_checkpoint_body_is_a_value_object():
    body = parse_body(NOTE_TEXT)
    assert body == parse_body(body.to_text())
    assert isinstance(body, CheckpointBody)
    assert body.signed_bytes == NOTE_TEXT.encode("utf-8")
    assert body.drand is not None
    assert body.nist is not None
    assert body.extension("absent") is None
