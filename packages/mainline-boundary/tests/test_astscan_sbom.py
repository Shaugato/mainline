# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the E3 scanner and the SBOM differ.

The scanner is the leg most likely to rot into a no-op, because a scan of a clean
tree looks identical to a scan of no tree. Every test here therefore checks that
something specific was *found*, not merely that nothing was reported.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mainline_boundary.astscan import (
    DENIED_TOP_LEVEL_IMPORTS,
    ImportGraph,
    ModuleIndex,
    scan_kernel_code_boundary,
    scan_source,
)
from mainline_boundary.errors import SbomParseError
from mainline_boundary.sbom import (
    Component,
    check_sbom_pair,
    diff_sboms,
    is_denied_component,
    load_sbom,
    parse_sbom,
)


def test_the_denied_import_set_covers_what_the_brief_names() -> None:
    for module in ("anthropic", "strands", "langgraph", "mainline_agentkit"):
        assert module in DENIED_TOP_LEVEL_IMPORTS


def test_relative_imports_are_not_mistaken_for_top_level(tmp_path: Path) -> None:
    scan = scan_source(tmp_path / "m.py", "from . import sibling\nfrom .. import parent\n")
    assert scan.imports == ()


def test_dotted_import_records_only_the_top_level_name(tmp_path: Path) -> None:
    scan = scan_source(tmp_path / "m.py", "import anthropic.types.beta\n")
    assert [i.module for i in scan.imports] == ["anthropic"]


def test_non_bedrock_boto3_clients_are_not_flagged(tmp_path: Path) -> None:
    scan = scan_source(tmp_path / "m.py", 'import boto3\nc = boto3.client("kms")\n')
    assert scan.denied_clients == ()


def test_a_variable_service_name_is_invisible_and_that_is_documented(tmp_path: Path) -> None:
    """E3 cannot see ``boto3.client(service)``. E1 and E2 are why that is survivable."""
    scan = scan_source(tmp_path / "m.py", "import boto3\nc = boto3.client(service)\n")
    assert scan.denied_clients == ()


def test_test_files_may_name_the_string_they_forbid(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    target = tests / "test_boundary.py"
    target.write_text('ASSERT_ABSENT = "bedrock-runtime"\n', encoding="utf-8")
    from mainline_boundary.astscan import scan_file

    scan = scan_file(target)
    assert scan.denied_literals == ()
    assert [literal.text for literal in scan.exempted_literals] == ["bedrock-runtime"]


def test_module_index_prefers_the_src_layout(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "trappoint-x" / "src" / "tx"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "gate.py").write_text("", encoding="utf-8")
    index = ModuleIndex.build(tmp_path)
    assert index.path_for("tx.gate") is not None
    assert index.resolve_import("tx.gate.something") == "tx.gate"


def test_import_graph_records_the_path_that_reaches_a_module(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "trappoint-x" / "src"
    (src / "tx").mkdir(parents=True)
    (src / "tx" / "__init__.py").write_text("from tx import a\n", encoding="utf-8")
    (src / "tx" / "a.py").write_text("from tx import b\n", encoding="utf-8")
    (src / "tx" / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    graph = ImportGraph.build(ModuleIndex.build(tmp_path))
    reachable = graph.reachable_with_paths(["tx"])
    assert reachable["tx.b"] == ("tx", "tx.a", "tx.b")


def test_a_clean_kernel_tree_examines_something(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "trappoint-x" / "src" / "tx"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("import json\n", encoding="utf-8")
    report = scan_kernel_code_boundary(tmp_path, roots=("packages/trappoint-*",))
    assert report.ok
    assert report.examined >= 1, "a clean result over zero files is not a clean result"


# ---------------------------------------------------------------------------
# SBOM
# ---------------------------------------------------------------------------


def test_spdx_documents_parse_too() -> None:
    document = {
        "spdxVersion": "SPDX-2.3",
        "name": "mainline-kernel",
        "packages": [
            {
                "name": "anthropic",
                "versionInfo": "0.71.0",
                "externalRefs": [
                    {"referenceType": "purl", "referenceLocator": "pkg:pypi/anthropic@0.71.0"}
                ],
            }
        ],
    }
    sbom = parse_sbom(document)
    assert sbom.document_format == "SPDX"
    assert [c.name for c in sbom.denied()] == ["anthropic"]


def test_an_unrecognised_document_is_an_error() -> None:
    with pytest.raises(SbomParseError, match="neither CycloneDX"):
        parse_sbom({"hello": "world"})


def test_nested_cyclonedx_components_are_counted() -> None:
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "components": [
            {
                "name": "app",
                "version": "1",
                "components": [{"name": "langgraph", "version": "0.6"}],
            }
        ],
    }
    sbom = parse_sbom(document)
    assert [c.name for c in sbom.denied()] == ["langgraph"]


def test_version_changes_are_reported_separately() -> None:
    before = parse_sbom(
        {"bomFormat": "CycloneDX", "components": [{"name": "psycopg", "version": "3.2.1"}]}
    )
    after = parse_sbom(
        {"bomFormat": "CycloneDX", "components": [{"name": "psycopg", "version": "3.2.4"}]}
    )
    delta = diff_sboms(before, after)
    assert delta.added == () and delta.removed == ()
    assert delta.changed[0][1].version == "3.2.4"
    assert delta.introduced_denied == ()


def test_missing_baseline_is_a_skip_with_a_reason(tmp_path: Path) -> None:
    current = tmp_path / "current.cdx.json"
    current.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "metadata": {
                    "component": {
                        "name": "mainline-kernel",
                        "version": "sha256:" + "c" * 64,
                    }
                },
                "components": [{"name": "psycopg", "version": "3.2.1"}],
            }
        ),
        encoding="utf-8",
    )
    report = check_sbom_pair(tmp_path / "nope.json", current)
    assert report.ok
    assert any(s.rule == "E3-SBOM-BASELINE-ABSENT" for s in report.skips)
    assert "not" in report.skips[0].reason


def test_a_denied_component_in_the_current_image_fails(tmp_path: Path) -> None:
    current = tmp_path / "current.cdx.json"
    current.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "metadata": {
                    "component": {"name": "k", "version": "sha256:" + "d" * 64}
                },
                "components": [{"name": "strands-agents", "version": "1.50.2"}],
            }
        ),
        encoding="utf-8",
    )
    report = check_sbom_pair(None, current)
    assert "E3-SBOM-MODEL-SDK" in report.rules_violated(), report.summary()
    assert load_sbom(current).digest.startswith("sha256:")


def test_ordinary_dependencies_are_not_denied() -> None:
    for name in ("psycopg", "pydantic", "numpy", "boto3", "opentelemetry-sdk"):
        assert not is_denied_component(Component(name=name, version="1"))
