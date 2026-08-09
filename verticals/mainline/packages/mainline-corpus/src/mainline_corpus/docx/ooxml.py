# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""WordprocessingML fragments, authored by hand and emitted as exact bytes.

── WHY THERE IS NO DOCUMENT LIBRARY UNDER THIS ─────────────────────────────────────────────────

The brief names ``python-docx`` and ``docxtpl``.  Neither is in ``uv.lock``, and ``uv.lock`` is a
plan invariant that exactly one worker owns; adding a dependency from here would mean editing a
file this worker does not own, or shipping a module CI cannot resolve.  Writing the markup
directly costs a few hundred lines and *removes* the problem the brief spends its longest
paragraph on: there is no ``_ZipPkgWriter`` to patch, because there is no ``_ZipPkgWriter``.
``docs/adr/0034-reproducible-docx.md`` records the trade in full, including what is given up.

A DOM library would also buy attribute ordering we do not control and namespace-prefix choices
that can change between versions.  Both are bytes, and every byte here is under a
reproducibility claim, so the markup is text and says exactly what this file says it says.

── RULES THIS MODULE ENFORCES ──────────────────────────────────────────────────────────────────

* **Compact output.**  No indentation and no newline inside a part except the one after the XML
  declaration.  Whitespace between block elements is ignorable in WordprocessingML, so pretty
  printing would buy nothing and would cost a whole class of CRLF-versus-LF differences on
  Windows checkouts.
* **``xml:space="preserve"`` on every ``w:t``.**  A leading or trailing space in a clause body is
  document content; a writer that lets Word strip it changes the text a digest was taken over.
* **Control characters are refused, not escaped.**  XML 1.0 cannot represent ``U+0000`` to
  ``U+0008`` at all.  Silently dropping them would leave the rendered document and the corpus
  row disagreeing about the clause text while every digest still matched something.
* **No locale, ever.**  :func:`format_long_date` uses a literal month table.  The C library's
  month-name formatter returns "August" or "aout" depending on the runner's ``LC_TIME``, and a
  fixture that renders differently on a French CI box is not reproducible.
* **No media.**  Nothing here can emit a ``word/media/*`` part.  Media part names depend on the
  order parts were added, which is a reproducibility hazard dressed as a feature; the letterheads
  are ruled, not drawn.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

__all__ = [
    "MONTHS",
    "W_NS",
    "cell",
    "escape",
    "format_long_date",
    "para",
    "part_header",
    "row",
    "run",
    "sect_pr",
    "table",
]

#: The two namespace declarations every part this package writes needs.  Two, not twelve: with no
#: media there is no drawing-ML and no VML, and an unused declaration is a byte with no meaning.
W_NS: Final[str] = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)

#: Literal month names.  See the module docstring: this is the anti-locale measure.
MONTHS: Final[tuple[str, ...]] = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

#: ``YYYY``, ``MM``, ``DD``.  Named so the check below reads as the format's definition.
_ISO_DATE_PARTS: Final[int] = 3

_XML_DECL: Final[str] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

#: Everything XML 1.0 cannot carry, including the two non-characters at the end of the BMP.
_ILLEGAL: Final[re.Pattern[str]] = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def part_header(root_open: str) -> str:
    """Return the XML declaration and an opening root tag, with exactly one LF between."""
    return _XML_DECL + root_open


def escape(text: str) -> str:
    """XML-escape ``text``, refusing anything XML 1.0 cannot represent.

    ``&`` is replaced first, or the replacements escape each other.  ``'`` is deliberately left
    alone: it is legal unescaped in both element content and a double-quoted attribute value, and
    escaping it would put ``&apos;`` into the visible text of every possessive in the corpus the
    moment a caller double-escaped.
    """
    found = _ILLEGAL.search(text)
    if found is not None:
        raise ValueError(
            f"text contains U+{ord(found.group()):04X}, which XML 1.0 cannot represent. Escaping "
            "it is impossible and dropping it would make the rendered document and the corpus row "
            "disagree about the text a digest was taken over."
        )
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def format_long_date(iso_date: str) -> str:
    """``2013-08-04`` -> ``4 August 2013``, without touching the C locale."""
    parts = iso_date.split("-")
    if len(parts) != _ISO_DATE_PARTS:
        raise ValueError(f"{iso_date!r} is not an ISO date")
    year, month, day = (int(part) for part in parts)
    if not 1 <= month <= len(MONTHS):
        raise ValueError(f"{iso_date!r} has no month {month}")
    return f"{day} {MONTHS[month - 1]} {year}"


def run(
    text: str,
    *,
    style: str | None = None,
    bold: bool = False,
    italic: bool = False,
    caps: bool = False,
    size_half_points: int | None = None,
    colour: str | None = None,
) -> str:
    """One ``w:r``.  Direct formatting is used only where no named style would be reused."""
    props: list[str] = []
    if style is not None:
        props.append(f'<w:rStyle w:val="{escape(style)}"/>')
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if caps:
        props.append("<w:caps/>")
    if colour is not None:
        props.append(f'<w:color w:val="{escape(colour)}"/>')
    if size_half_points is not None:
        props.append(f'<w:sz w:val="{size_half_points}"/><w:szCs w:val="{size_half_points}"/>')
    r_pr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f'<w:r>{r_pr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(
    runs: Iterable[str] | str = (),
    *,
    style: str | None = None,
    jc: str | None = None,
    spacing_before: int | None = None,
    spacing_after: int | None = None,
    indent_left: int | None = None,
    indent_hanging: int | None = None,
    keep_next: bool = False,
    page_break_before: bool = False,
    bottom_border: bool = False,
) -> str:
    """One ``w:p``.  ``runs`` may be a single already-built run or an iterable of them."""
    body = runs if isinstance(runs, str) else "".join(runs)
    props: list[str] = []
    if style is not None:
        props.append(f'<w:pStyle w:val="{escape(style)}"/>')
    if keep_next:
        props.append("<w:keepNext/>")
    if page_break_before:
        props.append("<w:pageBreakBefore/>")
    if bottom_border:
        props.append(
            '<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="4" w:color="404040"/></w:pBdr>'
        )
    spacing = [
        f'w:{name}="{value}"'
        for name, value in (("before", spacing_before), ("after", spacing_after))
        if value is not None
    ]
    if spacing:
        props.append(f"<w:spacing {' '.join(spacing)}/>")
    indent = [
        f'w:{name}="{value}"'
        for name, value in (("left", indent_left), ("hanging", indent_hanging))
        if value is not None
    ]
    if indent:
        props.append(f"<w:ind {' '.join(indent)}/>")
    if jc is not None:
        props.append(f'<w:jc w:val="{escape(jc)}"/>')
    p_pr = f"<w:pPr>{''.join(props)}</w:pPr>" if props else ""
    return f"<w:p>{p_pr}{body}</w:p>"


def cell(content: str | Sequence[str], *, width: int, shade: str | None = None) -> str:
    """One ``w:tc``.  A cell must contain at least one ``w:p``; an empty one is refused.

    Not advisory: Word reports a table cell with no paragraph as a *corrupt document*, and the
    failure surfaces when a judge opens the file rather than when CI builds it.
    """
    body = content if isinstance(content, str) else "".join(content)
    if "<w:p>" not in body and "<w:p " not in body:
        raise ValueError(
            "a table cell must contain at least one paragraph; Word treats a cell with no w:p as "
            "a corrupt document rather than an empty one"
        )
    shading = f'<w:shd w:val="clear" w:color="auto" w:fill="{escape(shade)}"/>' if shade else ""
    return f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shading}</w:tcPr>{body}</w:tc>'


def row(cells: Iterable[str], *, header: bool = False) -> str:
    """One ``w:tr``.  A header row repeats across a page break, which a revision table wants."""
    tr_pr = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
    return f"<w:tr>{tr_pr}{''.join(cells)}</w:tr>"


def table(rows: Iterable[str], *, widths: Sequence[int], border_colour: str = "808080") -> str:
    """One ``w:tbl`` with a fixed grid.  Callers append a trailing ``w:p`` themselves.

    The explicit ``w:tblGrid`` and ``w:tblLayout fixed`` matter for reproducibility of
    *appearance*: without them Word computes column widths from content at open time, and a
    document that lays itself out differently depending on the installed font is not a document
    anyone can film twice.
    """
    sides = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="{escape(border_colour)}"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
    return (
        "<w:tbl><w:tblPr>"
        '<w:tblW w:w="0" w:type="auto"/>'
        f"<w:tblBorders>{sides}</w:tblBorders>"
        '<w:tblLayout w:type="fixed"/>'
        '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
        '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
        f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{''.join(rows)}</w:tbl>"
    )


def sect_pr(margins: Mapping[str, int]) -> str:
    """Build the section properties: A4 portrait, with this generation's own margins."""
    return (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        f'<w:pgMar w:top="{margins["top"]}" w:right="{margins["right"]}" '
        f'w:bottom="{margins["bottom"]}" w:left="{margins["left"]}" '
        'w:header="709" w:footer="709" w:gutter="0"/>'
        '<w:cols w:space="708"/>'
        '<w:docGrid w:linePitch="360"/>'
        "</w:sectPr>"
    )
