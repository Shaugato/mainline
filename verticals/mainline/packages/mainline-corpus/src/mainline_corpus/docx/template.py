# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The render path: a committed template plus a context, in, byte-reproducible ``.docx`` out.

── THE ``docxtpl`` IDIOM, IMPLEMENTED RATHER THAN IMPORTED ──────────────────────────────────

``docxtpl`` is two ideas on top of Jinja2.  The first is that a statement written ``{%p … %}``
replaces the *paragraph* that carries it, and ``{%tr … %}`` replaces the *row*, so a loop does
not leave an empty paragraph between every iteration.  The second is that Word splits runs
arbitrarily, so tags have to be stitched back together before Jinja sees them.

Both are implemented here, in about forty lines, and the second is turned inside out: instead of
repairing split tags, :func:`assert_tags_intact` **refuses** a template whose tags are split.
That is available to us and not to ``docxtpl`` because the templates are built by
``build_templates.py`` rather than authored in Word — a split tag would mean the builder is
wrong, and repairing it would hide the bug.

``docxtpl`` and ``python-docx`` are named in the brief and are absent from ``uv.lock``, which
exactly one worker owns.  ``docs/adr/0034-reproducible-docx.md`` records the decision and the
consequence.  The templates remain ``docxtpl``-loadable: nothing here is a private dialect.

── THE NONDETERMINISTIC ``rId`` ─────────────────────────────────────────────────────────────

The brief warns that ``docxtpl``'s render is not always idempotent with respect to relationship
ids, and instructs us to normalise rather than accept the flake.  :func:`normalise_relationship_ids`
does that unconditionally, on every render, whatever produced the input: ids are renumbered
``rId1…rIdN`` in ``(Type, Target)`` order — the relationship's *meaning*, not its position in the
file — and every reference to them is rewritten in the same pass.

── ESCAPING HAPPENS ONCE, AT THE BOUNDARY ───────────────────────────────────────────────────

:func:`escape_context` XML-escapes every string in the context immediately before rendering.
Jinja's own ``autoescape`` is off, because it would HTML-escape (``&#39;`` for an apostrophe,
which is legal but noisy) and because a context escaped twice is a document that prints
``&amp;amp;``.  One escape, one place, and :func:`assert_rendered_clean` proves nothing was
missed by refusing any output that still contains a Jinja delimiter.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from jinja2 import Environment, StrictUndefined

from .ooxml import escape
from .parts import app_xml, core_xml
from .zipwriter import read_package, write_package

__all__ = [
    "RenderError",
    "assert_rendered_clean",
    "assert_tags_intact",
    "escape_context",
    "normalise_relationship_ids",
    "patch_tags",
    "render",
]


class RenderError(RuntimeError):
    """A template or its rendering is not in the shape the reproducibility claim requires."""


_P_TAG: Final[re.Pattern[str]] = re.compile(
    r"<w:p\b[^>]*>(?:(?!</w:p>).)*?\{%p\s(?P<code>.*?)%\}(?:(?!</w:p>).)*?</w:p>",
    re.DOTALL,
)
_TR_TAG: Final[re.Pattern[str]] = re.compile(
    r"<w:tr\b[^>]*>(?:(?!</w:tr>).)*?\{%tr\s(?P<code>.*?)%\}(?:(?!</w:tr>).)*?</w:tr>",
    re.DOTALL,
)
_TEXT_RUN: Final[re.Pattern[str]] = re.compile(r"<w:t\b[^>]*>(?P<text>.*?)</w:t>", re.DOTALL)
_DELIMITERS: Final[tuple[str, ...]] = ("{{", "}}", "{%", "%}")


def patch_tags(document_xml: str) -> str:
    """Lift ``{%p … %}`` out of its paragraph and ``{%tr … %}`` out of its row."""

    def lift(match: re.Match[str]) -> str:
        return "{% " + match.group("code").strip() + " %}"

    return _P_TAG.sub(lift, _TR_TAG.sub(lift, document_xml))


def assert_tags_intact(document_xml: str) -> None:
    """Refuse a template with a Jinja delimiter outside a ``<w:t>`` element.

    A delimiter outside a text run means the tag was split across runs, which would make Jinja
    see ``{`` and ``{ doc.title }}`` as ordinary text and emit a document with a brace in it.
    """
    inside = "".join(match.group("text") for match in _TEXT_RUN.finditer(document_xml))
    for delimiter in _DELIMITERS:
        total = document_xml.count(delimiter)
        contained = inside.count(delimiter)
        if total != contained:
            raise RenderError(
                f"{total - contained} occurrence(s) of {delimiter!r} lie outside a <w:t> element. "
                "A Jinja tag split across runs would render as literal text. The templates are "
                "built by build_templates.py, so this is a builder defect, not a template that "
                "needs repairing."
            )


def assert_rendered_clean(document_xml: str) -> None:
    """Refuse rendered output that still contains a Jinja delimiter."""
    leftovers = [delimiter for delimiter in _DELIMITERS if delimiter in document_xml]
    if leftovers:
        index = document_xml.find(leftovers[0])
        raise RenderError(
            f"rendered document still contains {leftovers!r}; the first is at offset {index}: "
            f"...{document_xml[max(0, index - 60) : index + 60]}... "
            "An unrendered tag means a paragraph-level statement was not patched out."
        )


def escape_context(value: Any) -> Any:
    """Recursively XML-escape every string in a render context.  Non-strings pass through."""
    if isinstance(value, str):
        return escape(value)
    if isinstance(value, Mapping):
        return {key: escape_context(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [escape_context(item) for item in value]
    return value


def _environment() -> Environment:
    """Jinja, configured for XML rather than HTML.

    ``autoescape=False`` because :func:`escape_context` has already escaped, once.
    ``StrictUndefined`` because a missing context key must be a build failure: a template that
    silently rendered an empty revision number would produce a controlled document with no
    revision on it, and it would do so on camera.
    """
    return Environment(
        undefined=StrictUndefined,
        # S701 wants autoescape on.  It is off deliberately and the reason is above: Jinja's
        # autoescape is an HTML escaper, the output here is XML, and escape_context has already
        # escaped every string exactly once.  Turning it on would double-escape the corpus.
        autoescape=False,  # noqa: S701
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def normalise_relationship_ids(parts: Mapping[str, bytes]) -> dict[str, bytes]:
    """Renumber every relationship id to ``rId<n>`` in ``(Type, Target)`` order."""
    updated = dict(parts)
    for rels_name in sorted(name for name in parts if name.endswith(".rels")):
        rels_xml = parts[rels_name].decode("utf-8")
        rename = _rename_map(rels_xml, rels_name)
        if all(old == new for old, new in rename.items()):
            continue
        updated[rels_name] = _swap(rels_xml, rename, ("Id",)).encode("utf-8")
        owner = _rels_owner(rels_name)
        if owner is not None and owner in updated:
            updated[owner] = _swap(
                updated[owner].decode("utf-8"), rename, ("r:id", "r:embed", "r:link")
            ).encode("utf-8")
    return updated


_RELATIONSHIP: Final[re.Pattern[str]] = re.compile(r"<Relationship\b(?P<attrs>[^>]*?)/>")
_ATTR: Final[re.Pattern[str]] = re.compile(r'\b(?P<name>Id|Type|Target)="(?P<value>[^"]*)"')


def _rename_map(rels_xml: str, rels_name: str) -> dict[str, str]:
    entries: list[tuple[str, str, str]] = []
    for match in _RELATIONSHIP.finditer(rels_xml):
        attrs = {
            found.group("name"): found.group("value")
            for found in _ATTR.finditer(match.group("attrs"))
        }
        missing = {"Id", "Type", "Target"} - attrs.keys()
        if missing:
            raise RenderError(
                f"{rels_name}: a <Relationship> is missing {sorted(missing)}, so the package "
                "cannot be normalised deterministically"
            )
        entries.append((attrs["Type"], attrs["Target"], attrs["Id"]))
    entries.sort()
    return {old: f"rId{index}" for index, (_, _, old) in enumerate(entries, start=1)}


def _swap(xml: str, rename: Mapping[str, str], attributes: tuple[str, ...]) -> str:
    """Two-pass rename.  ``{rId1->rId2, rId2->rId1}`` applied in one pass collapses to one id."""
    result = xml
    for attribute in attributes:
        for old, new in rename.items():
            result = result.replace(f'{attribute}="{old}"', f'{attribute}="\x00{new}"')
    return result.replace('"\x00rId', '"rId')


def _rels_owner(rels_name: str) -> str | None:
    """``word/_rels/document.xml.rels`` -> ``word/document.xml``; ``_rels/.rels`` -> ``None``."""
    marker = "_rels/"
    index = rels_name.rfind(marker)
    if index < 0:
        return None
    prefix, leaf = rels_name[:index], rels_name[index + len(marker) :]
    if leaf == ".rels" or not leaf.endswith(".rels"):
        return None
    return f"{prefix}{leaf[: -len('.rels')]}"


def render(
    template: bytes,
    context: Mapping[str, Any],
    *,
    title: str,
    subject: str,
    creator: str,
    category: str,
    revision: str,
    iso_date: str,
    template_key: str,
    company: str,
) -> bytes:
    """Render ``template`` with ``context`` into a byte-reproducible ``.docx``.

    The result is a pure function of the arguments.  ``iso_date`` becomes both ``dcterms``
    timestamps — the *document's* effective date, never the build clock.
    """
    parts = read_package(template)
    document_xml = parts["word/document.xml"].decode("utf-8")
    assert_tags_intact(document_xml)
    rendered = _environment().from_string(patch_tags(document_xml)).render(escape_context(context))
    assert_rendered_clean(rendered)
    parts["word/document.xml"] = rendered.encode("utf-8")
    parts["docProps/core.xml"] = core_xml(
        title=title,
        subject=subject,
        creator=creator,
        category=category,
        revision=revision,
        iso_date=iso_date,
    ).encode("utf-8")
    parts["docProps/app.xml"] = app_xml(template=template_key, company=company).encode("utf-8")
    return write_package(normalise_relationship_ids(parts))
