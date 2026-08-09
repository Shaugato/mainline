# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The novelty manifest validator — `docs/leads/algorithms.md` §6, enforced.

WHAT THIS PROTECTS
------------------
Every named algorithm in this domain ships a ``novelty/<slug>.yaml`` stating what
it claims, what the database refuses because of it, where it sits against prior
art, and — in a field called ``unverified`` — everything it has NOT proven.  The
whole point of that file is that the originality claims are *checkable*.  A claim
is checkable only while four things stay true, and this module is the four:

1. **``prior_art`` is never empty.**  An empty prior-art list is not a strong
   claim, it is an unsearched one.  Every entry must name a URL, what that work
   covers, and what it does not.
2. **``position`` is one of the four declared values.**  ``unclaimed``,
   ``composition``, ``transplant``, ``re-parameterisation``.  A fifth value —
   ``novel``, ``strong``, ``partially unclaimed`` — is how a re-parameterisation
   becomes a contribution in a submission without anybody deciding that it had.
3. **A claim that asserts a REFUSAL must name one.**  If the prose says the
   database refuses, raises, cannot store, or cites a SQLSTATE, then
   ``enforcement.refuses`` must be non-empty.  The MUTATION RATCHET fragment is
   the one entry allowed an empty list, and it is allowed it precisely because
   its claim says "measures; never gates" — so the rule is not "refuses must be
   non-empty", it is "the two must agree".
4. **Every cited test path exists.**  A fragment whose evidence points at a file
   nobody wrote is the most expensive kind of wrong: it reads as proof.

THE MANIFEST IS A SET OF FILES, NOT A DIRECTORY
------------------------------------------------
§6 says one file per algorithm per worker so that ten workers never touch one
manifest.  The fragments therefore live wherever their worker's distribution
lives, and :data:`NOVELTY_ROOTS` is the list of those directories.  Globbing one
directory would have forced two workers to share it, which is the collision §6
exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]

#: Every directory a worker may ship a novelty fragment into.  Add a root here
#: when a new distribution ships one; never move another worker's file.
NOVELTY_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "novelty",
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-mutation" / "novelty",
)

POSITIONS: frozenset[str] = frozenset(
    {"unclaimed", "composition", "transplant", "re-parameterisation"}
)

REQUIRED_KEYS: tuple[str, ...] = (
    "slug",
    "name",
    "mechanism",
    "claim",
    "enforcement",
    "position",
    "prior_art",
    "implemented_by",
    "tests",
    "unverified",
)

#: Words and patterns that make a claim a claim ABOUT A REFUSAL.  Deliberately
#: broad: the cost of a false positive here is a worker having to list the
#: refusal they already built, and the cost of a false negative is an
#: enforcement claim with nothing behind it.
_REFUSAL_LANGUAGE = re.compile(
    r"\b(refus\w*|reject\w*|raises?|raising|cannot be (?:stored|inserted|recorded)|"
    r"un-?insertable|P0001|23514|23503|CHECK constraint|write precondition)\b",
    re.IGNORECASE,
)


def _fragments() -> list[Path]:
    found: list[Path] = []
    for root in NOVELTY_ROOTS:
        if root.is_dir():
            found.extend(sorted(root.glob("*.yaml")))
    return found


FRAGMENTS = _fragments()


def _load(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a YAML mapping"
    return loaded


# PLR0912: the branch count IS the rule set made visible. Each branch is one of
# the four failure conditions the brief names, plus the structural checks they
# depend on, and each produces a different sentence for the worker fixing the
# fragment. Splitting them into helpers would hide which rule refused.
def validate(document: dict[str, Any], *, name: str) -> list[str]:  # noqa: PLR0912
    """Return every problem with one fragment.  Empty means valid.

    A list rather than a raise, so a worker fixing a fragment sees all of its
    problems at once instead of one per run.  The test functions below turn the
    list into a failure; :func:`validate` is importable so that
    ``MECHANISMS.md`` generation can use the same rules the tests do rather than
    a second, drifting copy.
    """
    problems: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in document:
            problems.append(f"{name}: missing required key {key!r}")
    if problems:
        return problems

    position = document["position"]
    if position not in POSITIONS:
        problems.append(
            f"{name}: position {position!r} is not one of {sorted(POSITIONS)}. A fifth value is "
            "how a re-parameterisation becomes a contribution without anybody deciding it had"
        )

    prior_art = document["prior_art"]
    if not isinstance(prior_art, list) or not prior_art:
        problems.append(
            f"{name}: prior_art is empty. An empty prior-art list is not a strong claim, it is "
            "an unsearched one"
        )
    else:
        for index, entry in enumerate(prior_art):
            if not isinstance(entry, dict):
                problems.append(f"{name}: prior_art[{index}] is not a mapping")
                continue
            for field in ("url", "what_it_covers", "what_it_does_not"):
                if not str(entry.get(field, "")).strip():
                    problems.append(f"{name}: prior_art[{index}] has an empty {field!r}")

    enforcement = document["enforcement"]
    if not isinstance(enforcement, dict):
        problems.append(f"{name}: enforcement is not a mapping")
        return problems
    refuses = enforcement.get("refuses", [])
    if not isinstance(refuses, list):
        problems.append(f"{name}: enforcement.refuses is not a list")
        refuses = []
    depth = enforcement.get("refusal_depth")
    if not isinstance(depth, int) or depth < 0:
        problems.append(f"{name}: enforcement.refusal_depth {depth!r} is not a non-negative int")

    claim = str(document["claim"])
    if not claim.strip():
        problems.append(f"{name}: claim is empty")
    elif _REFUSAL_LANGUAGE.search(claim) and not refuses:
        problems.append(
            f"{name}: the claim asserts a refusal and enforcement.refuses is empty. Either the "
            "refusal exists and must be named with its SQLSTATE, or the claim is prose about "
            "something the database does not do"
        )
    # DELIBERATELY NOT CHECKED: that `refusal_depth` is non-zero when `refuses`
    # is non-empty. `abstention-ratchet.yaml` and `minhash-band.yaml` both list
    # APPLICATION-level refusals at depth 0, and both explain at length that the
    # database refusals downstream of them are already claimed at their true
    # depth by another fragment. Counting them again is the inflation the field
    # exists to make visible, so declaring 0 there is the honest answer and a
    # validator that refused it would be pushing every worker toward a bigger
    # number. Depth is checked for TYPE and never for size.

    for field in ("implemented_by", "tests", "unverified"):
        if not isinstance(document[field], list):
            problems.append(f"{name}: {field} is not a list")

    return problems


def _test_file(citation: str) -> Path:
    return REPO_ROOT / citation.split("::", 1)[0]


# --------------------------------------------------------------------------- #
# The tests                                                                    #
# --------------------------------------------------------------------------- #


def test_at_least_one_fragment_exists():
    assert FRAGMENTS, (
        f"no novelty fragment was found under any of {[str(r) for r in NOVELTY_ROOTS]}. The "
        "originality claims are supposed to be checkable and there is nothing to check"
    )


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_the_fragment_validates(path):
    problems = validate(_load(path), name=path.name)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_the_slug_matches_the_filename(path):
    assert _load(path)["slug"] == path.stem, (
        f"{path.name} declares a slug that is not its filename; MECHANISMS.md generation keys "
        "on one of the two and a reader keys on the other"
    )


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_every_cited_test_path_exists(path):
    document = _load(path)
    missing = [
        citation for citation in document["tests"] if not _test_file(str(citation)).exists()
    ]
    assert not missing, (
        f"{path.name} cites tests that do not exist: {missing}. A fragment whose evidence points "
        "at a file nobody wrote is the most expensive kind of wrong, because it reads as proof"
    )


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_every_implementation_path_exists(path):
    document = _load(path)
    missing = [
        cited for cited in document["implemented_by"] if not (REPO_ROOT / str(cited)).exists()
    ]
    assert not missing, (
        f"{path.name} claims to be implemented by files that do not exist: {missing}"
    )


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_nothing_unproven_hides_inside_the_claim(path):
    """``unverified`` must not be empty on a fragment that claims enforcement.

    §6 puts everything unproven under ``unverified`` and NEVER inside ``claim``.
    A fragment that lists refusals and has nothing unverified is either the first
    completely finished mechanism in the history of software or a fragment whose
    author did not look.
    """
    document = _load(path)
    if document["enforcement"].get("refuses"):
        assert document["unverified"], (
            f"{path.name} lists refusals and declares nothing unverified. Every mechanism in "
            "this domain has a stated honest limit; an empty list is a claim that this one "
            "does not"
        )


def test_no_two_fragments_share_a_slug():
    slugs = [_load(path)["slug"] for path in FRAGMENTS]
    duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
    assert not duplicates, f"two fragments declare the same slug: {duplicates}"


# --------------------------------------------------------------------------- #
# The validator's own red half — it must FAIL on a broken fragment             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_emptying_prior_art_makes_the_fragment_invalid(path):
    """`done_when`: the validator fails when prior_art is emptied from any one of them."""
    document = _load(path)
    document["prior_art"] = []
    problems = validate(document, name=path.name)
    assert any("prior_art is empty" in p for p in problems), (
        "a validator that passes a fragment with no prior art is not validating anything"
    )


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_an_unrecognised_position_makes_the_fragment_invalid(path):
    document = _load(path)
    document["position"] = "novel"
    problems = validate(document, name=path.name)
    assert any("is not one of" in p for p in problems)


@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.stem)
def test_a_missing_required_key_makes_the_fragment_invalid(path):
    document = _load(path)
    del document["unverified"]
    problems = validate(document, name=path.name)
    assert any("missing required key 'unverified'" in p for p in problems)


def test_a_refusal_claim_with_no_refusal_is_invalid():
    """The third failure condition, on a constructed fragment rather than a real one."""
    fabricated = {
        "slug": "fabricated",
        "name": "FABRICATED",
        "mechanism": "M1",
        "claim": "the database refuses the merge with 23514 when the accounting does not balance",
        "enforcement": {"refuses": [], "refusal_depth": 0},
        "position": "unclaimed",
        "prior_art": [{"url": "x", "what_it_covers": "y", "what_it_does_not": "z"}],
        "implemented_by": [],
        "tests": [],
        "unverified": [],
    }
    problems = validate(fabricated, name="fabricated.yaml")
    assert any("asserts a refusal and enforcement.refuses is empty" in p for p in problems)


def test_a_measurement_fragment_may_have_no_refusals():
    """The MUTATION RATCHET case: "measures; never gates" is a legal, non-empty claim."""
    measuring = {
        "slug": "measuring",
        "name": "MEASURING",
        "mechanism": "M1",
        "claim": "the residual risk is measured per class with a Wilson lower bound and published",
        "enforcement": {"refuses": [], "refusal_depth": 0},
        "position": "re-parameterisation",
        "prior_art": [{"url": "x", "what_it_covers": "y", "what_it_does_not": "z"}],
        "implemented_by": [],
        "tests": [],
        "unverified": [],
    }
    assert validate(measuring, name="measuring.yaml") == []


def test_a_nonexistent_test_path_is_caught():
    assert not _test_file("tests/e2e/mutation/test_that_was_never_written.py").exists()
