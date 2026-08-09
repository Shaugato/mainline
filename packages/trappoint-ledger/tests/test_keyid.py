# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Key IDs and the vkey form, against the worked vector in ``spec/wire/checkpoint.md`` §7.1.

Two traps are tested here because both of them fail *quietly*:

**The ``0x02`` key ID is not derived the Ed25519 way.** ``SHA-256(DER SPKI)[:4]`` — no
name, no algorithm byte. Deriving it as ``SHA-256(name ‖ 0x0A ‖ 0x02 ‖ pubkey)[:4]``
produces a four-byte value that indexes nothing, so every verifier ignores the signature
line and then reports "no known signature", which reads as a forged log rather than as a
build error.

**A vkey must be split on its first two ``+`` only.** The third field is standard base64,
whose alphabet contains ``+``. The vector's own key is one where a naive
``split("+")`` produces four fields, so this suite fails on the wrong parser rather than
waiting for the next key someone generates.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from trappoint_ledger.note.keyid import (
    ALGORITHM_ECDSA_P256_SHA256,
    ALGORITHM_ED25519,
    KEY_ID_BYTES,
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


def _spec_text() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "spec" / "wire" / "checkpoint.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    pytest.skip(f"spec/wire/checkpoint.md was not found above {here}")


SPEC = _spec_text()


def _table_value(label: str) -> str:
    match = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*`([0-9a-f]+)`\s*\|", SPEC)
    assert match is not None, f"§7.1 has no table row {label!r}"
    return match.group(1)


def _vkey() -> str:
    for line in SPEC.splitlines():
        if line.startswith("mainline.example/site/BLK-07+"):
            return line.strip()
    raise AssertionError("§7.1 publishes no vkey line")


SPKI_HEX = _table_value("DER SPKI (hex)")
SPKI_SHA256 = _table_value("`SHA-256(DER SPKI)`")
KEY_ID_HEX = _table_value("**key ID**")
VKEY = _vkey()


# ── The vector ─────────────────────────────────────────────────────────────────────────


def test_the_spec_key_id_derives_from_the_der_spki_alone():
    spki = bytes.fromhex(SPKI_HEX)
    assert hashlib.sha256(spki).hexdigest() == SPKI_SHA256
    assert key_id_ecdsa_p256(spki).hex() == KEY_ID_HEX
    assert key_id_hex(key_id_ecdsa_p256(spki)) == KEY_ID_HEX


def test_the_02_key_id_does_not_depend_on_the_key_name():
    """The asymmetry with ``0x01``, stated as an executable fact."""
    spki = bytes.fromhex(SPKI_HEX)
    one = PublicKey(name="mainline.example/site/BLK-07", algorithm=2, key_material=spki)
    other = PublicKey(name="something.else/site/ZZZ", algorithm=2, key_material=spki)
    assert one.key_id == other.key_id == bytes.fromhex(KEY_ID_HEX)


def test_the_01_key_id_does_depend_on_the_key_name():
    pubkey = bytes(range(32))
    assert key_id_ed25519("a", pubkey) != key_id_ed25519("b", pubkey)


def test_the_ed25519_derivation_is_the_documented_preimage():
    """Recomputed independently here, so the module cannot be 'proved' by itself."""
    name = "mainline.example/site/BLK-07"
    pubkey = bytes(range(32))
    expected = hashlib.sha256(name.encode("utf-8") + b"\x0a" + b"\x01" + pubkey).digest()[:4]
    assert key_id_ed25519(name, pubkey) == expected
    assert len(expected) == KEY_ID_BYTES


def test_an_ed25519_key_of_the_wrong_length_is_refused():
    with pytest.raises(ValueError, match="32 bytes"):
        key_id_ed25519("name", bytes.fromhex(SPKI_HEX))


def test_an_empty_spki_is_refused():
    with pytest.raises(ValueError, match="empty DER SPKI"):
        key_id_ecdsa_p256(b"")


def test_key_id_hex_requires_four_bytes():
    with pytest.raises(ValueError, match="4 bytes"):
        key_id_hex(b"\x00\x01\x02")


# ── The vkey ───────────────────────────────────────────────────────────────────────────


def test_the_vector_vkey_is_one_a_naive_parser_gets_wrong():
    """The trap is real for this exact key, not merely possible in principle."""
    assert VKEY.count("+") > 2
    assert len(VKEY.split("+")) > 3


def test_the_vkey_parses_into_exactly_three_fields():
    key = parse_vkey(VKEY)
    assert key.name == "mainline.example/site/BLK-07"
    assert key.key_id_hex == KEY_ID_HEX
    assert key.algorithm == ALGORITHM_ECDSA_P256_SHA256
    assert key.key_material.hex() == SPKI_HEX
    assert key.lookup == (key.name, bytes.fromhex(KEY_ID_HEX))


def test_the_vkey_round_trips():
    key = parse_vkey(VKEY)
    assert key.vkey() == VKEY
    assert format_vkey(key.name, key.algorithm, key.key_material) == VKEY


def test_a_vkey_whose_key_id_lies_is_refused():
    """§5.2: a conforming parser recomputes rather than trusts."""
    name, _stated, material = VKEY.split("+", 2)
    with pytest.raises(KeyIdMismatch, match="derives"):
        parse_vkey(f"{name}+00000000+{material}")


@pytest.mark.parametrize(
    "bad",
    [
        "no-separators",
        "name+e74111d1",
        "name+E74111D1+AjBZ",
        "name+e74111d+AjBZ",
        "name+e74111d1+not base64",
        "name+e74111d1+",
    ],
)
def test_a_malformed_vkey_is_refused(bad):
    with pytest.raises(MalformedVkey):
        parse_vkey(bad)


def test_a_vkey_for_an_unknown_algorithm_is_refused():
    """Refusing beats guessing: a guessed key ID matches nothing and reads as a forgery."""
    import base64

    blob = base64.b64encode(bytes([0x7F]) + bytes(32)).decode("ascii")
    with pytest.raises(UnsupportedAlgorithm, match="0x7f"):
        parse_vkey(f"name+00000000+{blob}")


def test_a_key_name_with_a_plus_or_whitespace_is_refused():
    spki = bytes.fromhex(SPKI_HEX)
    for name in ("has+plus", "has space", "has\tab", ""):
        with pytest.raises(ValueError, match="whitespace or '\\+'"):
            PublicKey(name=name, algorithm=ALGORITHM_ECDSA_P256_SHA256, key_material=spki)


def test_a_public_key_never_accepts_a_key_id():
    """The type makes a lying key ID unrepresentable rather than detectable."""
    assert "key_id" not in PublicKey.__dataclass_fields__
    assert set(PublicKey.__dataclass_fields__) == {"name", "algorithm", "key_material"}


def test_the_algorithm_constants_are_the_c2sp_ones():
    assert ALGORITHM_ED25519 == 0x01
    assert ALGORITHM_ECDSA_P256_SHA256 == 0x02
