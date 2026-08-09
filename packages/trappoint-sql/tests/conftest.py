# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the render engine's tests.

Two kinds of test live in this package and they need opposite things.

**Tests of the two REAL bindings** need the real repository: the real
``spec/binding/vertical.schema.json``, the real templates, the real committed SQL. They
take ``repo_root`` and read the tree in place. They must never write to it.

**Tests of a REFUSAL** need a binding that is deliberately wrong, and a wrong binding
must not be committed anywhere near the real ones — a stray malformed ``vertical.toml``
under ``verticals/`` would be discovered by ``trappoint render`` with no ``--binding``
and would turn a targeted test fixture into a repository-wide red build. So they take
``fake_root``: a throwaway tree carrying copies of exactly the three files the loader
reads out of a workspace (the binding schema, the conformance manifest that states the
spec version, and a ground-truth attestation), plus the ``compose.yaml`` marker that
makes ``repo_root()`` recognise it.

``binding_text()`` builds a minimal *valid* binding and takes surgical substitutions, so
every refusal test differs from a passing one by the single clause under test. A fixture
that is wrong in two ways proves nothing about either.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from trappoint_sql.binding import repo_root

# The workspace this test file lives in. Resolved once, from the file's own location, so
# the suite does not depend on the working directory pytest was started from.
REPO_ROOT = repo_root(Path(__file__).resolve().parent)
TEMPLATES = REPO_ROOT / "packages" / "trappoint-sql" / "templates"
MAINLINE_BINDING = REPO_ROOT / "verticals" / "mainline" / "vertical.toml"
REF_BINDING = REPO_ROOT / "packages" / "trappoint-sql" / "refvertical" / "vertical.toml"

_SPEC_FILES = (
    Path("spec/binding/vertical.schema.json"),
    Path("spec/conformance/manifest.toml"),
)
_ATTESTATION = Path("packages/trappoint-sql/g1-attestation.json")

# The minimal binding: one subject, one counter, one authority source. Every refusal
# fixture is this text with one clause replaced.
_MINIMAL = """\
emit_outbox = false

[vertical]
name         = "PROBE"
spec_version = "1.0.0-rc.1"
schema       = "probe"
output_dir   = "sql"
license      = "Apache-2.0"
description  = "A throwaway binding used to prove one refusal at a time."

[capabilities]
attestation   = "attest/g1-attestation.json"
stored_digest = "stored"
triggerdef    = "pg_get_triggerdef"
isolation     = "serializable"

[conformance]
profile = "trappoint-ref"
skip_requires = []

[[authority_source]]
projects    = ["blocking_check.severity"]
relation    = "probe.clause_blame_current"
key         = ["clause_uuid"]
key_columns = ["clause_uuid"]
columns     = ["max_severity"]
on_missing  = "raise"
raise_via   = "p0001"

[[obligation_source]]
relation      = "probe.blocking_check"
counter       = "open_blocking"
subject_kinds = ["permit"]
bumps_epoch   = true

[[subject]]
kind             = "permit"
table            = "permit"
id_column        = "permit_id"
epoch_column     = "gate_epoch"
state_column     = "state"
completing_state = "merged"

[[subject.counters]]
column     = "open_blocking"
constraint = "gate_closed_when_issued"
source     = "probe.blocking_check"
polarity   = "zero_when_complete"
"""


def binding_text(*substitutions: tuple[str, str]) -> str:
    """Return the minimal valid binding with *substitutions* applied in order.

    Each substitution is ``(old, new)`` and must match exactly once. A silent no-op
    substitution would produce a fixture that is valid when the test believes it is
    invalid, and the test would then pass for the wrong reason — the single most
    expensive failure mode a refusal suite has.
    """
    text = _MINIMAL
    for old, new in substitutions:
        count = text.count(old)
        if count != 1:
            raise AssertionError(f"substitution {old!r} matched {count} times, expected 1")
        text = text.replace(old, new)
    return text


@pytest.fixture(scope="session")
def repo_root_path() -> Path:
    """The real workspace root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def templates_dir() -> Path:
    """The real kernel template directory."""
    return TEMPLATES


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A throwaway workspace carrying the three files the binding loader reads.

    Also carries ``compose.yaml``, because ``repo_root()`` identifies a workspace by the
    presence of both ``spec/`` and ``compose.yaml`` — the same rule ``trappoint migrate``
    uses, so a fixture root that satisfied only one of them would be a tree the two
    commands disagree about.
    """
    for relative in _SPEC_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)
    attest = tmp_path / "attest" / "g1-attestation.json"
    attest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / _ATTESTATION, attest)
    (tmp_path / "compose.yaml").write_text("name: probe\n", encoding="utf-8")
    (tmp_path / "sql").mkdir()
    return tmp_path


@pytest.fixture
def write_binding(fake_root: Path) -> Callable[..., Path]:
    """Return a helper that writes a binding into the throwaway workspace.

    Bytes, with ``newline="\\n"``: the render engine compares bytes, and a fixture
    written in text mode on Windows would differ from the same fixture on Linux for a
    reason that has nothing to do with the binding.
    """

    def write(*substitutions: tuple[str, str], name: str = "vertical.toml") -> Path:
        path = fake_root / name
        path.write_bytes(binding_text(*substitutions).encode("utf-8"))
        return path

    return write


@pytest.fixture
def write_templates(tmp_path: Path) -> Callable[[Iterable[tuple[str, str]]], Path]:
    """Return a helper that writes a throwaway template directory.

    Kept out of ``fake_root`` on purpose: several tests render the REAL bindings against
    a FAKE template set (to prove a pragma refusal without editing a committed template)
    and several render a fake binding against the REAL templates. Coupling the two
    directories into one fixture would forbid both.
    """

    def write(files: Iterable[tuple[str, str]]) -> Path:
        directory = tmp_path / "templates"
        directory.mkdir(exist_ok=True)
        for name, text in files:
            (directory / name).write_bytes(text.encode("utf-8"))
        return directory

    return write
