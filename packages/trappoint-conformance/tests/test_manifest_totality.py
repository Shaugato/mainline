# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The manifest and the corpus are the same set, in both directions.

A conformance suite's worst failure mode is not a red case. It is a case that quietly
**stops existing** — deleted in a rebase, dropped from an import list to fix a lint, renamed
by half — leaving a suite that is smaller than the claim printed at the end of it. Nothing
goes red. The number just gets smaller, and the number is what people quote.

So the assertion is bidirectional and it has teeth in both directions:

* every ``CF-*`` in ``spec/conformance/manifest.toml`` has an implementation;
* every implementation has a manifest entry.

Deleting a manifest entry fails the second. Deleting a case module fails the first. There is
no edit that removes a case without turning this file red, which is the only property that
makes the count trustworthy.

Nothing here needs a database. That is deliberate: the guard against silent shrinkage must
run in the fastest job, on every pull request, in the environment least likely to be skipped.
"""

from __future__ import annotations

import re

import cases
import pytest

from trappoint_conformance.manifest import Manifest
from trappoint_conformance.runner import implemented_case_ids

# CF-01 is registered by trappoint_conformance.runner itself, not by this package: it is
# the case that was observed RED against an empty database, and that observation is the
# PL-2 proof artefact. It is expected to be implemented; it is expected NOT to live in
# cases/. Both halves are asserted below.
RUNNER_OWNED = frozenset({"CF-01"})


def test_every_manifest_case_has_an_implementation(manifest: Manifest) -> None:
    """No case is declared and unwritten."""
    cases.load_all()
    declared = {case.id for case in manifest.cases}
    implemented = implemented_case_ids()
    missing = sorted(declared - implemented, key=_order)
    assert not missing, (
        f"{len(missing)} case(s) are declared in {manifest.path} with no implementation: "
        f"{', '.join(missing)}. A manifest entry with no code is a claim with no test "
        f"behind it, and the runner reports it as PENDING rather than as a failure — "
        f"which is exactly how a suite comes to be smaller than the number it prints."
    )


def test_every_implementation_has_a_manifest_entry(manifest: Manifest) -> None:
    """No case is written and undeclared."""
    cases.load_all()
    declared = {case.id for case in manifest.cases}
    implemented = implemented_case_ids()
    undeclared = sorted(implemented - declared, key=_order)
    assert not undeclared, (
        f"{len(undeclared)} implementation(s) have no manifest entry: "
        f"{', '.join(undeclared)}. The manifest is the single source of truth for the "
        f"suite; a case it does not declare is a case no profile selects, no coverage "
        f"report counts, and no claim of conformance includes."
    )


def test_the_corpus_owns_every_case_except_the_red_before_green_one(manifest: Manifest) -> None:
    """`cases/` implements everything except the toolchain worker's CF-01."""
    cases.load_all()
    declared = {case.id for case in manifest.cases}
    from_modules = set()
    for name in cases.case_modules():
        match = re.match(r"cf(\d+)_", name)
        assert match, f"{name!r} does not name a case; case modules are `cfNN_<slug>.py`"
        from_modules.add(f"CF-{int(match.group(1)):02d}")
    expected = declared - RUNNER_OWNED
    assert from_modules == expected, (
        f"the corpus implements {sorted(from_modules - expected, key=_order)} it should "
        f"not and is missing {sorted(expected - from_modules, key=_order)}. CF-01 is "
        f"registered by the runner because it is the case that was observed red against an "
        f"empty database; re-registering it here would raise on the duplicate and would "
        f"take ownership of another worker's proof artefact."
    )


def test_one_module_per_case() -> None:
    """Exactly one module per case, and one case per module."""
    cases.load_all()
    modules = cases.case_modules()
    numbers = [int(re.match(r"cf(\d+)_", name).group(1)) for name in modules]  # type: ignore[union-attr]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert not duplicates, (
        f"more than one module implements case(s) {duplicates}. The registry refuses a "
        f"duplicate registration, so the module that lost would be decided by import "
        f"order — which is to say, by nothing."
    )


def test_declared_counts_match_the_manifest(manifest: Manifest) -> None:
    """The header's own arithmetic agrees with the body it heads."""
    assert manifest.declared_case_count == len(manifest.cases), (
        f"[manifest] case_count says {manifest.declared_case_count} and the file holds "
        f"{len(manifest.cases)} [[case]] entries. The header is quoted in claims of "
        f"conformance; a header that disagrees with its own file is a claim about nothing."
    )
    ref = manifest.for_profile("trappoint-ref")
    assert manifest.declared_ref_profile_case_count == len(ref), (
        f"[manifest] ref_profile_case_count says "
        f"{manifest.declared_ref_profile_case_count} and {len(ref)} cases carry the "
        f"trappoint-ref profile. `N/N · spec X · profile trappoint-ref` is the K1 exit "
        f"string and the N in it comes from this number."
    )


@pytest.mark.parametrize("field", ["expect_sqlstate", "expect_constraint", "milestone"])
def test_no_case_declares_an_empty_expectation(manifest: Manifest, field: str) -> None:
    """Every case names a code, an exhibit and a milestone."""
    blank = [case.id for case in manifest.cases if not getattr(case, field)]
    assert not blank, (
        f"{field} is empty on {blank!r}. A test asserting only that an exception was "
        f"raised is not conformant (spec/errors.md §3.1): the diagnosis is the deliverable."
    )


def _order(case_id: str) -> int:
    return int(case_id.split("-")[1])
