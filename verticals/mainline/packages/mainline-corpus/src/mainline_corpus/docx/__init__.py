# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 3 — controlled documents that look like controlled documents, and prove they are.

Prose in JSONL does not survive contact with a screen.  A procedure has to be legible as a
controlled document in a two-second shot: a letterhead, numbered clause styles, and a
revision-history table.  This package renders the committed answer key into real ``.docx`` files
and does it **byte-reproducibly**, which is the part that is hard and the part that is
non-negotiable — ``MANIFEST.docx.sha256`` is a claim a judge can check on a laptop in seconds,
and a claim that depends on when the build ran is false.

── THE SHAPE OF IT ──────────────────────────────────────────────────────────────────────────

``zipwriter``   the OPC container, with every source of variance pinned.
``ooxml``       WordprocessingML fragments, authored as exact bytes.
``parts``       content types, relationships, and the two ``docProps`` files.
``house_style`` the two house styles as real style sheets — decision **D6**.
``build_templates``  eight templates (four families x two generations), built from source.
``bodies``      the clause-prose provider chain: authored, then cached, then composed.
``sources``     the committed answer key folded into render requests.
``model``       what a document is, plus the layout derivations that *assert* rather than trust.
``template``    the ``docxtpl`` idiom, implemented: ``{%p %}``, ``{%tr %}``, rId normalisation.
``render``      the render set in, ``fixtures/corpus/rendered/`` out.
``manifest``    ``MANIFEST.docx.sha256`` in ``sha256sum`` format, plus a provenance sidecar.
``verify``      the four-way proof, and the red control that keeps it from passing by accident.
``cli``         ``build-templates`` · ``render`` · ``verify`` · ``digests`` · ``list`` · ``probe``

── THE CLAIM, AND ITS EXACT LIMIT ───────────────────────────────────────────────────────────

Claimed and executed here: the same inputs produce the same bytes across two in-process renders,
two subprocess renders, and the committed files on disk; the 2016 retypeset moves the spine
clause from ``7.3`` to ``5.2.1`` and moves its ordinal while its ``clause_uuid`` does not change.

Engineered here and **asserted elsewhere**: equality across ubuntu-latest and windows-latest.
The engineering is stored compression (so no zlib build can differ), pinned member metadata, LF
in every generated part, no locale lookup and no clock.  The CI matrix job that proves it lives
in ``.github/workflows/corpus.yml``, which this worker does not own.  Nothing here claims that
job is green.
"""

from __future__ import annotations

from .build_templates import TEMPLATE_KEYS, build_all_templates, build_template, templates_root
from .manifest import JSON_NAME, MANIFEST_NAME, manifest_text
from .model import ClauseRender, DocumentRender, RevisionRow
from .parts import PRODUCER, PRODUCER_VERSION
from .render import render_all, render_document, rendered_root, write_rendered
from .sources import RENDER_TARGETS, RenderTarget, build_all, build_document, fixtures_root
from .verify import check_all
from .zipwriter import FIXED_DATE_TIME, read_package, write_package

__all__ = [
    "FIXED_DATE_TIME",
    "JSON_NAME",
    "MANIFEST_NAME",
    "PRODUCER",
    "PRODUCER_VERSION",
    "RENDER_TARGETS",
    "TEMPLATE_KEYS",
    "ClauseRender",
    "DocumentRender",
    "RenderTarget",
    "RevisionRow",
    "build_all",
    "build_all_templates",
    "build_document",
    "build_template",
    "check_all",
    "fixtures_root",
    "manifest_text",
    "read_package",
    "render_all",
    "render_document",
    "rendered_root",
    "templates_root",
    "write_package",
    "write_rendered",
]
