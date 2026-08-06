# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The grep test: no hard-coded Claude model id or inference-profile ARN in the package.

recall.md D5 / PL-3.  A model id written into source today is a claim nobody has checked,
because AWS credentials are not valid on the build machine.  Worse, a hard-coded profile
prefix is how a residency guarantee dies quietly: someone pastes a ``global.*`` id during a
Friday debug session and every fatality narrative in the corpus starts routing to whichever
Region has capacity.

One literal is permitted, in one file: the Titan v2 **embedding** model id, because
ARCHITECTURE §10.1 records that embedding models cannot use inference profiles at all —
there is no ARN to resolve, so the call is In-Region-or-nothing.  That exception is
asserted to stay confined to ``bedrock_titan.py``.

Patterns are assembled from fragments so this file does not itself contain the strings it
bans.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_VENDOR = "anthr" + "opic"
_CLAUDE = "cla" + "ude"

#: A Bedrock foundation-model id: `<vendor>.<model>-v<n>:<m>`.
MODEL_ID_RE = re.compile(r"\b[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9.-]*-v\d+:\d+\b")

#: A cross-region inference-profile id: `<region-prefix>.<vendor>.<model>`.
PROFILE_ID_RE = re.compile(
    r"\b(?:au|us|eu|apac|global|jp|ca|apne\d)\.(?:" + _VENDOR + r"|amazon|meta|cohere)\."
)

#: A bare vendor-qualified Claude id, with or without a region prefix.
CLAUDE_ID_RE = re.compile(re.escape(_VENDOR) + r"\." + re.escape(_CLAUDE))

#: A Bedrock ARN of any kind.
BEDROCK_ARN_RE = re.compile(r"arn:aws[a-z-]*:bedrock:")

TITAN_EXEMPT_FILE = "bedrock_titan.py"


def _package_root(package_src: Path) -> Path:
    return package_src / "mainline_recall_agent"


def _python_sources(package_src: Path) -> list[Path]:
    return sorted(p for p in _package_root(package_src).rglob("*.py"))


def test_the_package_has_sources_to_scan(package_src: Path) -> None:
    assert len(_python_sources(package_src)) >= 10


@pytest.mark.parametrize(
    ("label", "pattern"),
    [
        ("cross-region inference-profile id", PROFILE_ID_RE),
        ("vendor-qualified Claude model id", CLAUDE_ID_RE),
        ("bedrock ARN", BEDROCK_ARN_RE),
    ],
)
def test_no_claude_identifier_appears_anywhere_in_the_package(
    package_src: Path, label: str, pattern: re.Pattern[str]
) -> None:
    offenders: list[str] = []
    for path in _python_sources(package_src):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()[:120]}")
    assert not offenders, f"hard-coded {label} found:\n" + "\n".join(offenders)


def test_the_only_model_id_literal_is_titan_and_it_lives_in_one_file(
    package_src: Path,
) -> None:
    hits: dict[str, list[str]] = {}
    for path in _python_sources(package_src):
        found = MODEL_ID_RE.findall(path.read_text(encoding="utf-8"))
        if found:
            hits[path.name] = found
    assert set(hits) <= {TITAN_EXEMPT_FILE}, f"model-id literals outside the exemption: {hits}"
    assert hits.get(TITAN_EXEMPT_FILE), "the Titan embedding id went missing"
    assert set(hits[TITAN_EXEMPT_FILE]) == {"amazon.titan-embed-text-v2:0"}


def test_the_committed_json_artefacts_carry_no_claude_identifier(package_src: Path) -> None:
    for path in _package_root(package_src).rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not CLAUDE_ID_RE.search(text), path
        assert not PROFILE_ID_RE.search(text), path


def test_the_resolver_exposes_no_default_profile_id() -> None:
    """The ladder is first-party tier names, never Bedrock ids."""
    from mainline_recall_agent.providers.resolve import DEFAULT_TIER, TIER_LADDER

    assert DEFAULT_TIER == "claude-opus-5"
    for tier in TIER_LADDER:
        assert "." not in tier
        assert ":" not in tier


def test_the_residency_prefix_is_the_australian_one() -> None:
    from mainline_recall_agent.providers.resolve import (
        AU_PROFILE_PREFIX,
        BANNED_PROFILE_PREFIXES,
    )

    assert AU_PROFILE_PREFIX == "au."
    assert "global." in BANNED_PROFILE_PREFIXES
    assert "apac." in BANNED_PROFILE_PREFIXES
