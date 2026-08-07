# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Properties that must hold for structures the vectors never happened to contain.

A vector suite proves the canonicaliser is right about twenty-three inputs. These
properties are what let us say it is right about inputs nobody wrote down — which is the
only claim worth anything, because the payloads this thing will hash have not been
written yet.

The load-bearing one is **round-trip stability**: ``canonicalise(json.loads(
canonicalise(x))) == canonicalise(x)``. If it ever fails, then re-canonicalising a leaf
read back out of the ledger would produce different bytes from the ones that were signed,
and check 1 of the verifier would fail on honest data — the worst possible failure for a
tamper-evidence product, because it manufactures a false accusation.
"""

from __future__ import annotations

import json
from pathlib import Path

import tomllib
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from trappoint_jcs.canon_v1 import MAX_SAFE_INTEGER, canonicalise, canonicalise_payload

# Float-free by construction: the payload profile bans floats, and the round-trip property
# is stated for float-free structures because `json.loads` of "1e+21" yields a float
# whereas the source may have been an int — a JSON-level ambiguity, not a canonicaliser
# defect.
_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-MAX_SAFE_INTEGER, max_value=MAX_SAFE_INTEGER),
    st.text(max_size=40),
)

_json_values = st.recursive(
    _scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=6),
        st.dictionaries(st.text(max_size=12), children, max_size=6),
    ),
    max_leaves=25,
)


@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
@given(_json_values)
def test_round_trip_is_a_fixed_point(value: object) -> None:
    once = canonicalise(value)
    assert canonicalise(json.loads(once)) == once


@settings(max_examples=400)
@given(_json_values)
def test_output_is_valid_utf8_and_valid_json(value: object) -> None:
    raw = canonicalise(value)
    assert raw.decode("utf-8") is not None
    json.loads(raw)  # raises if it is not


@settings(max_examples=300)
@given(_json_values)
def test_payload_profile_agrees_with_conformance_path_on_float_free_data(
    value: object,
) -> None:
    assert canonicalise_payload(value) == canonicalise(value)


@settings(max_examples=300)
@given(st.dictionaries(st.text(max_size=12), _scalars, max_size=8))
def test_member_order_is_independent_of_insertion_order(mapping: dict[str, object]) -> None:
    reversed_insertion = dict(reversed(list(mapping.items())))
    assert canonicalise(mapping) == canonicalise(reversed_insertion)


@settings(max_examples=300)
@given(st.dictionaries(st.text(max_size=12), _scalars, min_size=2, max_size=8))
def test_members_appear_in_utf16_order(mapping: dict[str, object]) -> None:
    raw = canonicalise(mapping)
    expected = sorted(mapping, key=lambda name: name.encode("utf-16-be"))
    positions = [raw.index(canonicalise(name) + b":") for name in expected]
    assert positions == sorted(positions)


@settings(max_examples=200)
@given(st.text(max_size=60))
def test_string_escaping_round_trips_through_a_stock_json_parser(value: str) -> None:
    """Our escaping is not a private convention: ``json`` reads it back unchanged."""
    assert json.loads(canonicalise(value)) == value


@settings(max_examples=200)
@given(st.text(max_size=60))
def test_only_the_mandated_characters_are_escaped(value: str) -> None:
    raw = canonicalise(value).decode("utf-8")
    body = raw[1:-1]
    for character in value:
        code_point = ord(character)
        if code_point < 0x20 or character in '"\\':
            continue
        # Every other character appears literally, including U+007F and astral planes.
        assert character in body


def test_zero_runtime_dependencies() -> None:
    """The dependency floor is an assertion, not a sentence in a README.

    ``trappoint-verify`` vendors ``canon_v1`` and claims ``cryptography`` as its only
    dependency. That claim dies the moment this list stops being empty.
    """
    manifest = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with manifest.open("rb") as handle:
        parsed = tomllib.load(handle)
    assert parsed["project"]["dependencies"] == []


def test_canon_v1_imports_only_the_standard_library() -> None:
    """A package-relative import in ``canon_v1`` would break the vendored copy.

    The file is copied verbatim into ``trappoint_verify/vendor/`` and must import as a
    standalone module there. ``import ast`` rather than a regex, because a comment
    mentioning ``from trappoint_jcs`` should not fail the build and a real import should.
    """
    import ast

    source = (
        Path(__file__).resolve().parent.parent / "src" / "trappoint_jcs" / "canon_v1.py"
    ).read_text(encoding="utf-8")
    permitted = {"hashlib", "json", "math", "pathlib", "typing", "__future__"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in permitted, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import would not survive vendoring"
            assert node.module is not None
            assert node.module.split(".")[0] in permitted, node.module


def test_canon_src_sha256_is_stable_and_line_ending_independent() -> None:
    """Check 10 depends on this value being about the code, not about the checkout."""
    import hashlib

    from trappoint_jcs.canon_v1 import canon_src_sha256

    path = Path(__file__).resolve().parent.parent / "src" / "trappoint_jcs" / "canon_v1.py"
    normalised = path.read_bytes().replace(b"\r\n", b"\n")
    assert canon_src_sha256() == hashlib.sha256(normalised).digest()
    assert canon_src_sha256() == canon_src_sha256()
    # A CRLF checkout must not change the answer.
    assert hashlib.sha256(normalised.replace(b"\n", b"\r\n").replace(b"\r\n", b"\n")).digest() == (
        canon_src_sha256()
    )
