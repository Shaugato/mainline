# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E3 — no model code path.

ARCHITECTURE.md §8.2 asserts E3 with an ``import-linter`` contract plus an SBOM
diff against the previous image digest. This module asserts the same **outcome**
without reading the kernel lead's ``import-linter`` configuration. That is not
politeness about file ownership; a contract file and the tool that reads it share
a failure mode — delete the contract, delete the check — and the entire value of
§8.2 is that its four enforcements do not.

**The trap, stated plainly.** ``verticals/mainline/packages/mainline-gate-svc``
does not exist yet. A scan over a path that is not there finds nothing, and
"found nothing" must not be printed as green. So the scan records
``E3-ROOT-ABSENT`` as a *skip with a reason*, this module refuses to call that a
pass, and the moment the path appears the skip vanishes and the scan is enforced
with zero edits to any file here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mainline_boundary.astscan import (
    DEFAULT_KERNEL_ROOTS,
    ImportGraph,
    ModuleIndex,
    scan_kernel_code_boundary,
    scan_source,
)
from mainline_boundary.repo import expand_roots
from mainline_boundary.sbom import (
    Component,
    check_sbom_pair,
    diff_sboms,
    is_denied_component,
    parse_sbom,
)
from mainline_boundary.testkit import assert_enforced

GATE_SVC_ROOT = "verticals/mainline/packages/mainline-gate-svc"
SBOM_BASELINE = "evidence/sbom/kernel/baseline.cdx.json"
SBOM_CURRENT = "evidence/sbom/kernel/current.cdx.json"


def test_kernel_plane_source_holds_no_model_client(repo_root: Path) -> None:
    assert_enforced(scan_kernel_code_boundary(repo_root))


def test_gate_service_scan_never_passes_by_absence(repo_root: Path) -> None:
    """The trap. While the path is absent this test SKIPS; it never passes."""
    report = scan_kernel_code_boundary(repo_root, roots=(GATE_SVC_ROOT,))
    present = (repo_root / GATE_SVC_ROOT).exists()
    skips = report.skips_for(GATE_SVC_ROOT)

    if not present:
        assert skips, (
            "the gate service is absent and the scan recorded no skip. That is the "
            "exact failure this test exists to prevent: a check that reports clean "
            "because it looked at nothing."
        )
        assert report.examined == 0
        pytest.skip(
            f"{GATE_SVC_ROOT} does not exist yet, so no kernel gate-service source was "
            f"scanned. NOT A PASS. Reason recorded by the scanner: {skips[0].reason}"
        )

    assert not skips, (
        f"{GATE_SVC_ROOT} exists but the scan still skipped it: {[str(s) for s in skips]}"
    )
    assert report.examined > 0, (
        f"{GATE_SVC_ROOT} exists but the scan examined nothing in it"
    )
    assert_enforced(report)


def test_root_patterns_are_the_ones_the_architecture_names(repo_root: Path) -> None:
    assert DEFAULT_KERNEL_ROOTS == (
        "packages/trappoint-*",
        "verticals/mainline/packages/mainline-gate-svc",
    )
    matched = expand_roots(repo_root, DEFAULT_KERNEL_ROOTS)
    assert matched["packages/trappoint-*"], (
        "no packages/trappoint-* package exists, so E3's other root is empty too and "
        "the whole enforcement would be vacuous"
    )


# ---------------------------------------------------------------------------
# PL-2: the scanner has to be seen catching each thing it claims to catch
# ---------------------------------------------------------------------------


def test_scanner_catches_a_direct_model_sdk_import(tmp_path: Path) -> None:
    source = "import anthropic\n\n\ndef go() -> None:\n    anthropic.Anthropic()\n"
    scan = scan_source(tmp_path / "kernel.py", source)
    assert [i.module for i in scan.denied_imports] == ["anthropic"]


def test_scanner_catches_a_bedrock_boto3_client(tmp_path: Path) -> None:
    source = 'import boto3\n\nclient = boto3.client("bedrock-runtime")\n'
    scan = scan_source(tmp_path / "kernel.py", source)
    assert [c.service for c in scan.denied_clients] == ["bedrock-runtime"]
    assert [literal.text for literal in scan.denied_literals] == ["bedrock-runtime"]


def test_scanner_catches_a_session_client_too(tmp_path: Path) -> None:
    source = 'import boto3\n\ns = boto3.Session()\nc = s.client(service_name="bedrock")\n'
    scan = scan_source(tmp_path / "kernel.py", source)
    assert [c.service for c in scan.denied_clients] == ["bedrock"]


def test_scanner_catches_the_agentkit_import(tmp_path: Path) -> None:
    source = "from mainline_agentkit.call import quarantined_call\n"
    scan = scan_source(tmp_path / "kernel.py", source)
    assert [i.module for i in scan.denied_imports] == ["mainline_agentkit"]


def test_allow_literal_pragma_is_recorded_not_hidden(tmp_path: Path) -> None:
    source = 'SERVICE = "bedrock-runtime"  # mainline-boundary: allow-literal doc only\n'
    scan = scan_source(tmp_path / "kernel.py", source)
    assert not scan.denied_literals
    assert [literal.text for literal in scan.exempted_literals] == ["bedrock-runtime"]


def test_unparseable_source_is_a_violation_not_a_skip(tmp_path: Path) -> None:
    scan = scan_source(tmp_path / "broken.py", "def (:\n")
    assert scan.syntax_error is not None


def test_import_graph_finds_an_indirect_reach(tmp_path: Path) -> None:
    """A kernel module two hops from a model SDK is still a kernel module with one."""
    kernel_src = tmp_path / "packages" / "trappoint-demo" / "src"
    (kernel_src / "kdemo").mkdir(parents=True)
    (kernel_src / "kdemo" / "__init__.py").write_text(
        "from kdemo import gate\n", encoding="utf-8"
    )
    (kernel_src / "kdemo" / "gate.py").write_text(
        "from helper import narrate\n", encoding="utf-8"
    )
    # `helper` lives OUTSIDE the kernel root, so only the import graph can find it.
    # This is the case import-linter exists for and the case a naive file scan
    # misses: the kernel package itself is clean.
    other_src = tmp_path / "packages" / "mainline-helper" / "src"
    (other_src / "helper").mkdir(parents=True)
    (other_src / "helper" / "__init__.py").write_text(
        "import anthropic\n\n\ndef narrate() -> None:\n    anthropic.Anthropic()\n",
        encoding="utf-8",
    )
    report = scan_kernel_code_boundary(tmp_path, roots=("packages/trappoint-*",))
    rules = report.rules_violated()
    assert "E3-IMPORT-REACHABLE" in rules, report.summary()
    reachable = ImportGraph.build(ModuleIndex.build(tmp_path)).reachable_with_paths(
        ["kdemo.gate"]
    )
    assert "helper" in reachable


def test_absent_root_is_a_skip_with_a_reason(tmp_path: Path) -> None:
    report = scan_kernel_code_boundary(tmp_path, roots=("packages/does-not-exist",))
    assert report.examined == 0
    assert report.skips
    assert "NOT a pass" in report.skips[0].reason
    # assert_enforced turns a zero-subject report into a skip, never a pass.
    with pytest.raises(pytest.skip.Exception):
        assert_enforced(report)


# ---------------------------------------------------------------------------
# The SBOM leg
# ---------------------------------------------------------------------------


def _cyclonedx(components: list[dict[str, str]], digest: str) -> dict[str, object]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "metadata": {
            "component": {
                "type": "container",
                "name": "mainline-kernel",
                "version": digest,
                "hashes": [{"alg": "SHA-256", "content": digest.removeprefix("sha256:")}],
            }
        },
        "components": components,
    }


def test_sbom_diff_detects_an_introduced_model_sdk() -> None:
    baseline = parse_sbom(
        _cyclonedx(
            [
                {"name": "psycopg", "version": "3.2.1", "purl": "pkg:pypi/psycopg@3.2.1"},
                {"name": "pydantic", "version": "2.12.0", "purl": "pkg:pypi/pydantic@2.12.0"},
            ],
            "sha256:" + "a" * 64,
        )
    )
    current = parse_sbom(
        _cyclonedx(
            [
                {"name": "psycopg", "version": "3.2.1", "purl": "pkg:pypi/psycopg@3.2.1"},
                {"name": "pydantic", "version": "2.12.0", "purl": "pkg:pypi/pydantic@2.12.0"},
                {"name": "anthropic", "version": "0.71.0", "purl": "pkg:pypi/anthropic@0.71.0"},
            ],
            "sha256:" + "b" * 64,
        )
    )
    delta = diff_sboms(baseline, current)
    assert [c.name for c in delta.introduced_denied] == ["anthropic"]
    assert baseline.digest and current.digest and baseline.digest != current.digest


def test_denied_component_matching_uses_the_purl_too() -> None:
    assert is_denied_component(Component(name="", version="", purl="pkg:pypi/langgraph@0.6"))
    assert not is_denied_component(Component(name="psycopg", version="3.2.1"))


def test_sbom_leg_skips_with_a_reason_while_no_sbom_is_committed(repo_root: Path) -> None:
    baseline = repo_root / SBOM_BASELINE
    current = repo_root / SBOM_CURRENT
    report = check_sbom_pair(baseline, current)
    if not current.exists():
        assert report.skips, "a missing SBOM must be a stated skip, never silence"
        assert report.examined == 0
        pytest.skip(
            f"no kernel-image SBOM is committed at {SBOM_CURRENT}, so the image contents "
            f"are unproven. NOT A PASS. Reason: {report.skips[0].reason}"
        )
    assert_enforced(report)


def test_a_digestless_sbom_is_a_violation(tmp_path: Path) -> None:
    """An SBOM not bound to a digest describes no artefact that ever shipped."""
    import json

    document = _cyclonedx([{"name": "psycopg", "version": "3.2.1"}], "")
    document["metadata"] = {"component": {"type": "container", "name": "mainline-kernel"}}
    path = tmp_path / "current.cdx.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    report = check_sbom_pair(None, path)
    assert "E3-SBOM-NO-DIGEST" in report.rules_violated(), report.summary()
