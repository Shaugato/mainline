# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 3's top level: the render set in, ``fixtures/corpus/rendered/`` out.

One function does the work — :func:`render_document` — and everything else is bookkeeping over
it.  Two properties are worth stating because the rest of the package depends on them:

* **The output is a pure function of the committed inputs.**  Those inputs are the answer key,
  the gazetteer, the eight committed templates, the optional authored/cached body indexes, and
  the code in this package.  Nothing else — no clock, no environment variable, no filesystem
  ordering, no locale — reaches a byte.  ``verify.py`` proves this the four ways the brief asks
  for; this module is what makes the proof possible rather than lucky.
* **Templates are read from disk, not rebuilt.**  A render uses the ``.docx`` that is committed,
  so a template that drifted from its builder is caught by ``build-templates --check`` and not
  papered over by a renderer that quietly regenerated it.  ``--from-source`` exists for the one
  case where that is wrong: proving that the committed template *is* the built one.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from .bodies import BodyBank
from .build_templates import COMPANY, build_all_templates, template_bytes
from .model import DocumentRender
from .sources import RENDER_TARGETS, build_all, fixtures_root
from .template import render as render_template

__all__ = [
    "RENDER_TARGETS",
    "render_all",
    "render_document",
    "rendered_root",
    "write_rendered",
]

_LICENCE: Final[str] = (
    "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: FSL-1.1-ALv2\n"
)


def rendered_root() -> Path:
    """``verticals/mainline/fixtures/corpus/rendered``."""
    return fixtures_root() / "rendered"


def render_document(
    document: DocumentRender,
    *,
    templates: Mapping[str, bytes] | None = None,
) -> bytes:
    """Render one assembled document through its committed template."""
    template = (
        templates[document.template_key]
        if templates is not None
        else template_bytes(document.template_key)
    )
    return render_template(
        template,
        document.as_context(),
        title=f"{document.doc_code} - {document.title}",
        subject=(
            f"{document.site_full_name}; revision {document.rev_label}; "
            f"effective {document.effective_on}"
        ),
        creator=document.approver,
        category=f"Kestrel controlled document ({document.family})",
        revision=document.rev_label,
        iso_date=document.effective_on,
        template_key=document.template_key,
        company=COMPANY,
    )


def render_all(
    *,
    from_source: bool = False,
    bank: BodyBank | None = None,
) -> dict[str, bytes]:
    """Render every target.  Returns ``{output_name: bytes}`` in render-set order.

    ``from_source=True`` builds the templates in memory instead of reading the committed ones,
    which is how ``verify`` shows that the committed templates and their builder agree.
    """
    templates = build_all_templates() if from_source else None
    return {
        document.output_name: render_document(document, templates=templates)
        for document in build_all(bank=bank)
    }


def write_rendered(root: Path | None = None, *, from_source: bool = False) -> dict[str, Path]:
    """Write every rendered document and its REUSE sidecar; return the paths written."""
    target_root = root if root is not None else rendered_root()
    target_root.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, payload in render_all(from_source=from_source).items():
        path = target_root / name
        path.write_bytes(payload)
        (target_root / f"{name}.license").write_text(_LICENCE, encoding="utf-8", newline="\n")
        written[name] = path
    return written
