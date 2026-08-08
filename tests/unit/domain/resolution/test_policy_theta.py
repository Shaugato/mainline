# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""theta has no default, and this file is what makes that sentence checkable.

A threshold nobody signed is a threshold nobody can be cross-examined about.  The
tests below assert the *absence* of a value — which is exactly the kind of claim
that rots quietly, because adding a default makes every one of them pass except
these.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest
from mainline_domain.resolution import policy as policy_module
from mainline_domain.resolution import (
    PolicyIncomplete,
    PolicyTheta,
    load_policy_theta,
    resolve,
    theta_from_policy,
)

_GOOD = """
[policy]
version = "identity-policy-v1"

[resolution]
oracle_confidence_theta = 0.75
"""


def _write(tmp_path: Path, text: str, name: str = "identity-policy-v1.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_theta_is_read_with_the_hash_of_the_bytes_it_came_from(tmp_path: Path) -> None:
    path = _write(tmp_path, _GOOD)
    loaded = load_policy_theta(path)
    assert loaded.theta == 0.75
    assert loaded.policy_version == "identity-policy-v1"
    assert loaded.policy_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_policy_without_the_section_refuses(tmp_path: Path) -> None:
    with pytest.raises(PolicyIncomplete, match="carries no"):
        load_policy_theta(_write(tmp_path, '[policy]\nversion = "v1"\n'))


def test_a_policy_without_the_key_refuses(tmp_path: Path) -> None:
    with pytest.raises(PolicyIncomplete, match="oracle_confidence_theta"):
        load_policy_theta(_write(tmp_path, "[resolution]\nsomething_else = 1\n"))


@pytest.mark.parametrize("value", ['"0.75"', "true", "[0.75]"])
def test_a_non_numeric_theta_refuses(tmp_path: Path, value: str) -> None:
    with pytest.raises(PolicyIncomplete, match="must be a real number"):
        load_policy_theta(_write(tmp_path, f"[resolution]\noracle_confidence_theta = {value}\n"))


@pytest.mark.parametrize("value", ["-0.1", "1.5"])
def test_a_theta_outside_the_unit_interval_refuses(tmp_path: Path, value: str) -> None:
    with pytest.raises(PolicyIncomplete, match=r"outside \[0, 1\]"):
        load_policy_theta(_write(tmp_path, f"[resolution]\noracle_confidence_theta = {value}\n"))


def test_a_policy_theta_without_a_hash_refuses() -> None:
    with pytest.raises(PolicyIncomplete, match="untraceable"):
        PolicyTheta(theta=0.75, policy_version="v1", policy_sha256="")


def test_the_version_falls_back_to_the_filename_and_never_to_a_placeholder(
    tmp_path: Path,
) -> None:
    loaded = load_policy_theta(_write(tmp_path, "[resolution]\noracle_confidence_theta = 0.5\n"))
    assert loaded.policy_version == "identity-policy-v1"


def test_the_missing_committed_policy_fails_loudly_rather_than_defaulting() -> None:
    """Worker W8 owns ``data/policy/identity-policy-v1.toml``.

    Until it lands, the default path must raise ``FileNotFoundError`` — not
    return a number this package invented. When it lands carrying the key, this
    test starts asserting that it parses, with no edit here.
    """
    try:
        loaded = load_policy_theta()
    except FileNotFoundError as exc:
        assert "identity-policy-v1.toml" in str(exc)
        return
    assert 0.0 <= loaded.theta <= 1.0
    assert loaded.policy_sha256


def test_no_signature_in_this_package_carries_a_default_theta() -> None:
    """The absence, asserted mechanically rather than by reading."""
    for module in (policy_module, __import__("mainline_domain.resolution.resolve", fromlist=["x"])):
        for _name, function in inspect.getmembers(module, inspect.isfunction):
            signature = inspect.signature(function)
            theta = signature.parameters.get("theta")
            if theta is not None:
                assert theta.default is inspect.Parameter.empty, (
                    f"{module.__name__}.{_name} carries a default theta. A threshold with "
                    f"a default is a threshold nobody authored."
                )


def test_resolve_requires_theta_as_a_keyword() -> None:
    with pytest.raises(TypeError):
        resolve(None, None)  # type: ignore[call-arg]


def test_theta_from_policy_accepts_an_integer_zero(tmp_path: Path) -> None:
    """``0`` is a legal theta — accept every band — and must not read as absent."""
    loaded = theta_from_policy(
        {"resolution": {"oracle_confidence_theta": 0}},
        policy_version="v1",
        policy_sha256="ab" * 32,
    )
    assert loaded.theta == 0.0
