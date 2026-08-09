# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``python -m mainline_corpus.docx`` — stage 3's command surface.

Six verbs, each of which does exactly one thing:

``build-templates``  write the eight committed templates (``--check`` compares instead).
``render``           render the thirteen documents and both manifest files.
``verify``           the reproducibility proof and the red control; exit 1 on any failure.
``digests``          print ``{output name: sha256}`` as JSON — the subprocess leg of the proof.
``list``             print the render set and why each document is in it.
``probe``            read a produced ``.docx`` back and say what it actually contains.

``probe`` exists because "the generator believes it wrote X" and "the file says X" are different
statements, and only the second one survives a judge opening the file.  It reads the package the
same way any other consumer would.

This module owns stdout for stage 3; nothing else in the package prints.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .bodies import BodyBank
from .build_templates import (
    TEMPLATE_KEYS,
    build_all_templates,
    check_templates,
    write_templates,
)
from .manifest import digest, json_sidecar, write_manifest
from .parts import PRODUCER
from .render import render_all, rendered_root, write_rendered
from .sources import RENDER_TARGETS, build_all, fixtures_root
from .verify import Finding, check_all, failed, manifest_entries, retypeset_pair_record
from .zipwriter import read_package

__all__ = ["main"]


def _build_templates(namespace: argparse.Namespace) -> int:
    if namespace.check:
        drifted = check_templates()
        if drifted:
            print(f"templates differ from their builder: {', '.join(drifted)}")
            print("edit build_templates.py and re-run without --check; never edit a .docx")
            return 1
        print(f"all {len(TEMPLATE_KEYS)} templates match their builder")
        return 0
    written = write_templates()
    for key, path in sorted(written.items()):
        print(f"{digest(path.read_bytes())}  templates/{key}.docx")
    print(f"wrote {len(written)} templates to {written[next(iter(sorted(written)))].parent}")
    return 0


def _render(namespace: argparse.Namespace) -> int:
    written = write_rendered(from_source=namespace.from_source)
    rendered = {name: path.read_bytes() for name, path in written.items()}
    entries = manifest_entries(rendered)
    bank = BodyBank(fixtures_root())
    documents = {
        document.output_name: {
            "template": document.template_key,
            "family": document.family,
            "generation": document.generation,
            "site_code": document.site_code,
            "doc_code": document.doc_code,
            "revision": document.rev_label,
            "effective_on": document.effective_on,
            "clause_count": len(document.clauses),
            "revision_rows": len(document.revisions),
            "renderer_census": dict(sorted(document.renderer_census.items())),
            "note": document.front_note,
        }
        for document in build_all(bank=bank)
    }
    sidecar = json_sidecar(
        producer=PRODUCER,
        entries=entries,
        documents=documents,
        templates={key: digest(payload) for key, payload in build_all_templates().items()},
        pair=retypeset_pair_record(),
        providers={
            "authored": bank.authored_available,
            "cache": bank.cache_available,
        },
    )
    manifest_path, json_path = write_manifest(rendered_root(), entries, sidecar)
    for path in sorted(written.values()):
        print(f"{digest(path.read_bytes())}  rendered/{path.name}")
    print(f"wrote {len(written)} documents, {manifest_path.name} and {json_path.name}")
    return 0


def _verify(_: argparse.Namespace) -> int:
    findings: Sequence[Finding] = check_all()
    for finding in findings:
        print(finding.line())
    problems = failed(findings)
    if problems:
        print(f"\n{len(problems)} check(s) failed")
        return 1
    print(f"\n{len(findings)} check(s) passed")
    return 0


def _digests(_: argparse.Namespace) -> int:
    payload = {name: digest(data) for name, data in render_all().items()}
    print(json.dumps(payload, indent=None, sort_keys=True))
    return 0


def _list(_: argparse.Namespace) -> int:
    for target in RENDER_TARGETS:
        print(f"{target.output_name}\n    template {target.template_key}: {target.note}")
    return 0


def _probe(namespace: argparse.Namespace) -> int:
    """Read a produced ``.docx`` back and report what the file itself says."""
    path = Path(namespace.path)
    if not path.is_file():
        print(f"{path} does not exist")
        return 1
    parts = read_package(path.read_bytes())
    document_xml = parts["word/document.xml"].decode("utf-8")
    core_xml = parts["docProps/core.xml"].decode("utf-8")
    print(f"parts: {len(parts)}")
    for name in sorted(parts):
        print(f"  {len(parts[name]):>8}  {name}")
    print(f"sha256: {digest(path.read_bytes())}")
    for element in ("dc:title", "dcterms:created", "dcterms:modified", "cp:revision"):
        start = core_xml.find(f"<{element}")
        if start >= 0:
            end = core_xml.find(f"</{element}>", start)
            print(f"{element}: {core_xml[core_xml.find('>', start) + 1 : end]}")
    print(f"text runs: {document_xml.count('<w:t ')}")
    print(f"paragraphs: {document_xml.count('<w:p>') + document_xml.count('<w:p ')}")
    if namespace.grep:
        needle = namespace.grep
        print(f"occurrences of {needle!r} in word/document.xml: {document_xml.count(needle)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point.  Returns a process exit code; never raises ``SystemExit`` itself."""
    parser = argparse.ArgumentParser(
        prog="mainline_corpus.docx",
        description="Stage 3: byte-reproducible controlled documents for the MAINLINE corpus.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    templates = sub.add_parser("build-templates", help="write (or check) the eight templates")
    templates.add_argument(
        "--check",
        action="store_true",
        help="compare the committed templates against a fresh build instead of writing",
    )
    templates.set_defaults(handler=_build_templates)

    render = sub.add_parser("render", help="render the documents and both manifest files")
    render.add_argument(
        "--from-source",
        action="store_true",
        help="build templates in memory instead of reading the committed ones",
    )
    render.set_defaults(handler=_render)

    sub.add_parser("verify", help="the reproducibility proof and its red control").set_defaults(
        handler=_verify
    )
    sub.add_parser("digests", help="print {output name: sha256} as JSON").set_defaults(
        handler=_digests
    )
    sub.add_parser("list", help="list the render set").set_defaults(handler=_list)

    probe = sub.add_parser("probe", help="read a produced .docx back and report its contents")
    probe.add_argument("path", help="path to a .docx produced by this package")
    probe.add_argument("--grep", default="", help="count occurrences of a literal in document.xml")
    probe.set_defaults(handler=_probe)

    namespace = parser.parse_args(argv)
    handler = namespace.handler
    result: int = handler(namespace)
    return result


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.py
    sys.exit(main())
