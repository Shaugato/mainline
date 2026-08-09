# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The templates, built from source rather than committed as opaque binaries.

Eight templates: four document families (``PRO``, ``STD``, ``MOC``, ``PTW``) times two house
generations.  Each is a real ``.docx`` carrying Jinja tags in the ``docxtpl`` idiom — ``{{ … }}``
for a value, ``{%p … %}`` for a statement that replaces its paragraph, ``{%tr … %}`` for one that
replaces its table row — and each is committed to ``fixtures/corpus/templates/``.

── WHY BUILT AND NOT DRAWN ──────────────────────────────────────────────────────────────────

A template authored in Word is a binary a reviewer cannot diff, produced by a tool nobody in the
repository can run, carrying ``w:rsid`` session identifiers and a wall-clock ``docProps``.  A
template built by this file is a function of this file.  ``corpusgen docx build-templates
--check`` re-derives all eight and compares bytes, so a hand-edited template fails CI instead of
silently becoming the source of truth.

── THE ONE THING TO WATCH WHEN EDITING ──────────────────────────────────────────────────────

A Jinja tag must live inside a **single** ``<w:t>``.  Word splits a run wherever it feels like
it — that is why ``docxtpl`` ships a "fix tags" step — but this builder emits each tag as one
run, and :func:`mainline_corpus.docx.template.assert_tags_intact` checks the property on every
render rather than trusting it.  Keep expressions free of ``<``, ``>``, ``&`` and ``"``: those
are XML-escaped on the way in and would reach Jinja as entities.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from . import ooxml
from .house_style import HouseStyle, for_generation
from .parts import (
    CONTENT_TYPES,
    DOCUMENT_RELS,
    PACKAGE_RELS,
    TEMPLATE_DATE,
    app_xml,
    core_xml,
)
from .zipwriter import write_package

__all__ = [
    "COMPANY",
    "FAMILIES",
    "TEMPLATE_KEYS",
    "build_all_templates",
    "build_template",
    "check_templates",
    "template_bytes",
    "templates_root",
    "write_templates",
]

FAMILIES: Final[tuple[str, ...]] = ("PRO", "STD", "MOC", "PTW")

TEMPLATE_KEYS: Final[tuple[str, ...]] = tuple(
    f"{family.lower()}_g{generation}" for family in FAMILIES for generation in (1, 2)
)

_FAMILY_BANNER: Final[Mapping[str, str]] = {
    "PRO": "CONTROLLED PROCEDURE",
    "STD": "CORPORATE STANDARD",
    "MOC": "MANAGEMENT OF CHANGE RECORD",
    "PTW": "PERMIT TO WORK FORM SET",
}

#: The four front-matter headings, per family.  A change record's second section is not "Scope";
#: calling it that would be a template pretending every document is a procedure.
_FAMILY_SECTIONS: Mapping[str, tuple[str, str, str, str]] = {
    "PRO": ("Purpose", "Scope", "Terms used in this revision", "Requirements"),
    "STD": ("Purpose", "Application", "Terms used in this revision", "Required controls"),
    "MOC": (
        "Purpose of this record",
        "Change declared",
        "Terms used in this record",
        "Clauses affected",
    ),
    "PTW": (
        "Purpose",
        "Application of this form set",
        "Terms used in this revision",
        "Requirements",
    ),
}

COMPANY: Final[str] = "Kestrel Resources Pty Ltd"

_CLOSING_NOTE: Final[str] = (
    "This document is controlled electronically. A printed copy is uncontrolled and is valid "
    "only on the day it was printed. The authoritative copy, its revision history and the "
    "identity of every clause are held in the site document register."
)


def templates_root() -> Path:
    """``verticals/mainline/fixtures/corpus/templates``."""
    return Path(__file__).resolve().parents[5] / "fixtures" / "corpus" / "templates"


def _content_width(style: HouseStyle) -> int:
    """A4 width minus this generation's own left and right margins, in twips."""
    return 11906 - style.margins["left"] - style.margins["right"]


# ── fragments ────────────────────────────────────────────────────────────────────────────────


def _slot(expression: str, **kwargs: object) -> str:
    """Build a run carrying a Jinja value placeholder, as one ``<w:t>``."""
    return ooxml.run(f"{{{{ {expression} }}}}", **kwargs)  # type: ignore[arg-type]


def _p_tag(code: str) -> str:
    """Build a paragraph carrying only a paragraph-level Jinja statement."""
    return ooxml.para(ooxml.run(f"{{%p {code} %}}"))


def _tr_tag(code: str, width: int) -> str:
    """Build a table row carrying only a row-level Jinja statement."""
    return ooxml.row([ooxml.cell(ooxml.para(ooxml.run(f"{{%tr {code} %}}")), width=width)])


def _letterhead(style: HouseStyle, family: str) -> str:
    width = _content_width(style)
    left = int(width * 0.62)
    right = width - left
    identity = ooxml.para(
        [
            ooxml.run(
                COMPANY.upper(),
                bold=True,
                caps=True,
                size_half_points=style.small_half_points + 4,
                colour=style.heading_colour,
            )
        ],
        spacing_after=0,
    ) + ooxml.para([_slot("doc.site_full_name")], style="KestrelMeta")
    stamp = (
        ooxml.para([ooxml.run(_FAMILY_BANNER[family], bold=True)], style="KestrelMeta", jc="right")
        + ooxml.para([ooxml.run("Document "), _slot("doc.code")], style="KestrelMeta", jc="right")
        + ooxml.para(
            [
                ooxml.run("Revision "),
                _slot("doc.rev"),
                ooxml.run("  ·  Effective "),
                _slot("doc.effective_on"),
            ],
            style="KestrelMeta",
            jc="right",
        )
    )
    return ooxml.table(
        [
            ooxml.row(
                [
                    ooxml.cell(identity, width=left, shade=style.letterhead_shade),
                    ooxml.cell(stamp, width=right, shade=style.letterhead_shade),
                ]
            )
        ],
        widths=[left, right],
        border_colour=style.rule_colour,
    ) + ooxml.para(style="KestrelMeta")


def _title_block() -> str:
    return ooxml.para([_slot("doc.title")], style="KestrelTitle", bottom_border=True) + ooxml.para(
        [
            _slot("doc.code"),
            ooxml.run("  ·  revision "),
            _slot("doc.rev"),
            ooxml.run("  ·  effective "),
            _slot("doc.effective_on_long"),
            ooxml.run("  ·  "),
            _slot("doc.site_name"),
        ],
        style="KestrelSubtitle",
    )


def _panel_table(style: HouseStyle) -> str:
    width = _content_width(style)
    label_width = int(width * 0.30)
    value_width = width - label_width
    return ooxml.table(
        [
            ooxml.row(
                [
                    ooxml.cell(
                        ooxml.para([ooxml.run("Document control")], style="KestrelTableHead"),
                        width=label_width,
                        shade=style.letterhead_shade,
                    ),
                    ooxml.cell(
                        ooxml.para([ooxml.run("")], style="KestrelTableHead"),
                        width=value_width,
                        shade=style.letterhead_shade,
                    ),
                ],
                header=True,
            ),
            _tr_tag("for entry in panel", width),
            ooxml.row(
                [
                    ooxml.cell(
                        ooxml.para([_slot("entry.label")], style="KestrelTableHead"),
                        width=label_width,
                    ),
                    ooxml.cell(
                        ooxml.para([_slot("entry.value")], style="KestrelTableCell"),
                        width=value_width,
                    ),
                ]
            ),
            _tr_tag("endfor", width),
        ],
        widths=[label_width, value_width],
        border_colour=style.rule_colour,
    ) + ooxml.para(style="KestrelMeta")


def _revision_history(style: HouseStyle) -> str:
    width = _content_width(style)
    columns = [
        int(width * 0.09),
        int(width * 0.17),
        int(width * 0.17),
        int(width * 0.37),
        0,
    ]
    columns[4] = width - sum(columns[:4])
    headings = ("Rev", "Effective", "Change", "Reason for change", "Approved by")
    header = ooxml.row(
        [
            ooxml.cell(
                ooxml.para([ooxml.run(heading)], style="KestrelTableHead"),
                width=column,
                shade=style.letterhead_shade,
            )
            for heading, column in zip(headings, columns, strict=True)
        ],
        header=True,
    )
    fields = (
        "revision.rev",
        "revision.effective_on_long",
        "revision.delta",
        "revision.reason",
        "revision.author",
    )
    body = ooxml.row(
        [
            ooxml.cell(ooxml.para([_slot(field)], style="KestrelTableCell"), width=column)
            for field, column in zip(fields, columns, strict=True)
        ]
    )
    return (
        ooxml.para([ooxml.run("Revision history")], style="KestrelHeading")
        + ooxml.table(
            [header, _tr_tag("for revision in revisions", width), body, _tr_tag("endfor", width)],
            widths=columns,
            border_colour=style.rule_colour,
        )
        + ooxml.para(style="KestrelMeta")
    )


def _definitions_table(style: HouseStyle) -> str:
    width = _content_width(style)
    term_width = int(width * 0.32)
    meaning_width = width - term_width
    header = ooxml.row(
        [
            ooxml.cell(
                ooxml.para([ooxml.run(heading)], style="KestrelTableHead"),
                width=column,
                shade=style.letterhead_shade,
            )
            for heading, column in (
                ("Term", term_width),
                ("Meaning in this revision", meaning_width),
            )
        ],
        header=True,
    )
    body = ooxml.row(
        [
            ooxml.cell(
                ooxml.para([_slot("definition.term")], style="KestrelTableHead"), width=term_width
            ),
            ooxml.cell(
                ooxml.para([_slot("definition.meaning")], style="KestrelTableCell"),
                width=meaning_width,
            ),
        ]
    )
    return ooxml.table(
        [
            header,
            _tr_tag("for definition in definitions", width),
            body,
            _tr_tag("endfor", width),
        ],
        widths=[term_width, meaning_width],
        border_colour=style.rule_colour,
    ) + ooxml.para(style="KestrelMeta")


def _clause_loop(style: HouseStyle) -> str:
    """Build the clause loop: heading break, clause, sub-points, setpoint, citation.

    The generation-2 branch emits the barrier-division subheading that the 2016 scheme's middle
    digit stands for.  Generation 1 has no such division — its middle digit is a position within
    a procedural section — so the template simply never reaches that paragraph, because
    ``clause.subheading_title`` is empty for every generation-1 clause.
    """
    heading = ooxml.para(
        [
            ooxml.run(f"{style.heading_word} "),
            _slot("clause.heading_number"),
            ooxml.run("  -  "),
            _slot("clause.heading_title"),
        ],
        style="KestrelHeading",
    )
    subheading = ooxml.para([_slot("clause.subheading_title")], style="KestrelSubheading")
    clause = ooxml.para(
        [
            _slot("clause.label", bold=True),
            "<w:r><w:tab/></w:r>",
            _slot("clause.body"),
        ],
        style="KestrelClause",
    )
    point = ooxml.para([_slot("point")], style="KestrelPoint")
    setpoint = ooxml.para([_slot("clause.setpoint_text")], style="KestrelSetpoint")
    citation = ooxml.para(
        [ooxml.run("Reference: ", italic=True), _slot("clause.citation", italic=True)],
        style="KestrelMeta",
    )
    return "".join(
        (
            _p_tag("for clause in clauses"),
            _p_tag("if clause.first_in_heading"),
            heading,
            _p_tag("endif"),
            _p_tag("if clause.first_in_subheading and clause.subheading_title"),
            subheading,
            _p_tag("endif"),
            clause,
            _p_tag("for point in clause.points"),
            point,
            _p_tag("endfor"),
            _p_tag("if clause.setpoint_text"),
            setpoint,
            _p_tag("endif"),
            _p_tag("if clause.citation"),
            citation,
            _p_tag("endif"),
            _p_tag("endfor"),
        )
    )


def _section_heading(number: int, title: str) -> str:
    return ooxml.para([ooxml.run(f"{number}  {title}")], style="KestrelHeading")


def _document_xml(family: str, style: HouseStyle) -> str:
    one, two, three, four = _FAMILY_SECTIONS[family]
    front = _revision_history(style) if style.revision_table_at == "front" else ""
    back = _revision_history(style) if style.revision_table_at == "back" else ""
    body = "".join(
        (
            _letterhead(style, family),
            _title_block(),
            front,
            _panel_table(style),
            _section_heading(1, one),
            ooxml.para([_slot("doc.purpose")]),
            _section_heading(2, two),
            ooxml.para([_slot("doc.scope")]),
            _section_heading(3, three),
            _definitions_table(style),
            _section_heading(4, four),
            _clause_loop(style),
            back,
            ooxml.para([ooxml.run(_CLOSING_NOTE, italic=True)], style="KestrelMeta"),
            ooxml.sect_pr(style.margins),
        )
    )
    return ooxml.part_header(f"<w:document {ooxml.W_NS}>") + f"<w:body>{body}</w:body></w:document>"


# ── packaging ────────────────────────────────────────────────────────────────────────────────


def build_template(family: str, generation: int) -> bytes:
    """One template ``.docx``, as bytes."""
    if family not in FAMILIES:
        raise ValueError(f"{family!r} is not one of the corpus's document families: {FAMILIES}")
    style = for_generation(generation)
    key = f"{family.lower()}_g{generation}"
    parts: dict[str, bytes] = {
        "[Content_Types].xml": CONTENT_TYPES.encode("utf-8"),
        "_rels/.rels": PACKAGE_RELS.encode("utf-8"),
        "docProps/app.xml": app_xml(template=key, company=COMPANY).encode("utf-8"),
        "docProps/core.xml": core_xml(
            title=f"{_FAMILY_BANNER[family].title()} template ({style.label})",
            subject=f"MAINLINE corpus stage 3 template, family {family}, generation {generation}",
            creator="MAINLINE corpusgen",
            category="MAINLINE stage-3 template",
            revision="1",
            iso_date=TEMPLATE_DATE,
            keywords="template",
        ).encode("utf-8"),
        "word/_rels/document.xml.rels": DOCUMENT_RELS.encode("utf-8"),
        "word/document.xml": _document_xml(family, style).encode("utf-8"),
        "word/fontTable.xml": style.font_table_xml().encode("utf-8"),
        "word/numbering.xml": style.numbering_xml().encode("utf-8"),
        "word/settings.xml": style.settings_xml().encode("utf-8"),
        "word/styles.xml": style.styles_xml().encode("utf-8"),
    }
    return write_package(parts)


def build_all_templates() -> dict[str, bytes]:
    """Every template, keyed ``pro_g1`` … ``ptw_g2``."""
    return {
        f"{family.lower()}_g{generation}": build_template(family, generation)
        for family in FAMILIES
        for generation in (1, 2)
    }


def template_bytes(key: str, *, root: Path | None = None) -> bytes:
    """Read a committed template.  Raises with the rebuild command if it is not there."""
    path = (root if root is not None else templates_root()) / f"{key}.docx"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing. Run `python -m mainline_corpus.docx build-templates` to write "
            "the committed templates; they are generated artefacts and are not hand-authored."
        )
    return path.read_bytes()


def write_templates(root: Path | None = None) -> dict[str, Path]:
    """Write all eight templates plus their REUSE sidecars, returning the paths written."""
    target = root if root is not None else templates_root()
    target.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for key, payload in sorted(build_all_templates().items()):
        path = target / f"{key}.docx"
        path.write_bytes(payload)
        licence = target / f"{key}.docx.license"
        licence.write_text(
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
            "SPDX-License-Identifier: FSL-1.1-ALv2\n",
            encoding="utf-8",
            newline="\n",
        )
        written[key] = path
    return written


def check_templates(root: Path | None = None) -> Sequence[str]:
    """Return the keys whose committed bytes differ from a fresh build.  Empty means clean."""
    target = root if root is not None else templates_root()
    drifted: list[str] = []
    for key, payload in sorted(build_all_templates().items()):
        path = target / f"{key}.docx"
        if not path.is_file() or path.read_bytes() != payload:
            drifted.append(key)
    return tuple(drifted)
