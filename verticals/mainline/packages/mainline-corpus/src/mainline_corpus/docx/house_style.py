# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The two house styles, as real style sheets rather than as a string substitution.

Decision **D6**: the 2016 retypeset is a genuinely different second template — different
numbering scheme, different style set, different clause ordering.  ``injectors/retypeset.py``
states the organising principle each generation encodes, and this module is where that
principle becomes ``styles.xml`` and ``numbering.xml``:

* **Generation 1 (2004-2016)** numbers a document the way the *work* is done — numbered
  procedural sections, ``7.3`` or ``7.3.2(b)`` — sets it in Arial, rules the letterhead in
  black, and puts the revision history at the **back**, where a controlled document of that era
  put it, after the content it describes.
* **Generation 2 (post-2016)** numbers it the way the *controls* are organised — a chapter per
  control class, a division by barrier role, then an item: ``5.2.1`` — sets it in Calibri with a
  slate heading colour, and puts the revision history at the **front**, immediately under the
  title block, because the 2016 house rules made currency the first thing a reader sees.

Those are not cosmetic differences dressed up.  A reader shown the two files side by side can
say which is which without reading a word of the body, which is the point: the film's claim is
that clause identity survives a change of *this* magnitude.

── WHAT IS AUTHORED HERE, STATED PLAINLY ────────────────────────────────────────────────────

``G1_SECTION_TITLES`` is authored surface language for the generation-1 template — the
procedural phases a 2004-era procedure was organised into.  It is template furniture, not a
camera-quoted string: nothing in ``VO.md``, ``SHOT-LIST.yaml`` or the honesty card quotes it,
so it cannot drift against them.  Generation 2's chapter titles are **not** authored: they are
the control-class labels from ``gazetteer/control_classes.yaml``, because "a chapter per control
class" is exactly what the generation-2 scheme means.  See
:func:`mainline_corpus.docx.model.g2_chapter_title`, which *derives* the title and *asserts*
the barrier digit rather than trusting the printed label.

── NO LOCALE, NO IMAGES, NO RSIDS ───────────────────────────────────────────────────────────

``w:lang`` is pinned to ``en-AU`` in ``docDefaults`` rather than left to the authoring
application's default, so a runner with a different system language cannot change a byte.  No
part references a media item.  No ``w:rsid`` element is written anywhere: revision-save
identifiers are session state, and session state in a committed fixture is a fingerprint.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from . import ooxml

__all__ = [
    "G1",
    "G1_SECTION_TITLES",
    "G2",
    "HouseStyle",
    "for_generation",
]


#: The retypeset generation.  Named so that a comparison against it reads as a fact about the
#: corpus rather than as an unexplained literal.
RETYPESET_GENERATION: Final[int] = 2


@dataclass(frozen=True, slots=True)
class HouseStyle:
    """Everything that differs between the two generations, in one object."""

    generation: int
    key: str
    label: str
    body_font: str
    heading_font: str
    body_half_points: int
    small_half_points: int
    title_half_points: int
    heading_half_points: int
    heading_colour: str
    rule_colour: str
    heading_word: str
    sub_list_format: str
    sub_list_text: str
    revision_table_at: str
    clause_indent: int
    clause_hanging: int
    margins: Mapping[str, int]
    letterhead_shade: str

    # ── the four style-bearing parts ─────────────────────────────────────────────────────

    def styles_xml(self) -> str:
        """``word/styles.xml`` for this generation."""
        return ooxml.part_header(f"<w:styles {ooxml.W_NS}>") + (
            self._doc_defaults()
            + self._style("Normal", "Normal", default=True, run_props="", para_props="")
            + self._style(
                "KestrelTitle",
                "Kestrel Title",
                run_props=(
                    f'<w:rFonts w:ascii="{self.heading_font}" w:hAnsi="{self.heading_font}"/>'
                    f"<w:b/><w:caps/>"
                    f'<w:color w:val="{self.heading_colour}"/>'
                    f'<w:sz w:val="{self.title_half_points}"/>'
                    f'<w:szCs w:val="{self.title_half_points}"/>'
                ),
                para_props='<w:spacing w:before="120" w:after="60"/>',
            )
            + self._style(
                "KestrelSubtitle",
                "Kestrel Subtitle",
                run_props=(
                    f'<w:rFonts w:ascii="{self.heading_font}" w:hAnsi="{self.heading_font}"/>'
                    f'<w:color w:val="{self.heading_colour}"/>'
                    f'<w:sz w:val="{self.small_half_points + 4}"/>'
                    f'<w:szCs w:val="{self.small_half_points + 4}"/>'
                ),
                para_props='<w:spacing w:after="240"/>',
            )
            + self._style(
                "KestrelHeading",
                "Kestrel Heading",
                run_props=(
                    f'<w:rFonts w:ascii="{self.heading_font}" w:hAnsi="{self.heading_font}"/>'
                    f"<w:b/>{self._heading_case()}"
                    f'<w:color w:val="{self.heading_colour}"/>'
                    f'<w:sz w:val="{self.heading_half_points}"/>'
                    f'<w:szCs w:val="{self.heading_half_points}"/>'
                ),
                para_props=(
                    '<w:keepNext/><w:spacing w:before="280" w:after="120"/>'
                    f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" '
                    f'w:color="{self.rule_colour}"/></w:pBdr>'
                ),
            )
            + self._style(
                "KestrelSubheading",
                "Kestrel Subheading",
                run_props=(
                    f'<w:rFonts w:ascii="{self.heading_font}" w:hAnsi="{self.heading_font}"/>'
                    f"<w:b/><w:i/>"
                    f'<w:sz w:val="{self.body_half_points}"/>'
                    f'<w:szCs w:val="{self.body_half_points}"/>'
                ),
                para_props='<w:keepNext/><w:spacing w:before="160" w:after="80"/>',
            )
            + self._style(
                "KestrelClause",
                "Kestrel Clause",
                run_props="",
                para_props=(
                    f'<w:ind w:left="{self.clause_indent}" w:hanging="{self.clause_hanging}"/>'
                    '<w:spacing w:after="120"/><w:jc w:val="both"/>'
                ),
            )
            + self._style(
                "KestrelPoint",
                "Kestrel Clause Point",
                run_props="",
                para_props=(
                    f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
                    f'<w:ind w:left="{self.clause_indent + 340}" w:hanging="340"/>'
                    '<w:spacing w:after="60"/>'
                ),
            )
            + self._style(
                "KestrelSetpoint",
                "Kestrel Setpoint",
                run_props="<w:b/>",
                para_props=(
                    f'<w:ind w:left="{self.clause_indent}"/>'
                    '<w:spacing w:before="60" w:after="160"/>'
                ),
            )
            + self._style(
                "KestrelMeta",
                "Kestrel Meta",
                run_props=(
                    f'<w:sz w:val="{self.small_half_points}"/>'
                    f'<w:szCs w:val="{self.small_half_points}"/>'
                ),
                para_props='<w:spacing w:after="0"/>',
            )
            + self._style(
                "KestrelTableHead",
                "Kestrel Table Heading",
                run_props=(
                    "<w:b/>"
                    f'<w:sz w:val="{self.small_half_points}"/>'
                    f'<w:szCs w:val="{self.small_half_points}"/>'
                ),
                para_props='<w:spacing w:after="0"/>',
            )
            + self._style(
                "KestrelTableCell",
                "Kestrel Table Cell",
                run_props=(
                    f'<w:sz w:val="{self.small_half_points}"/>'
                    f'<w:szCs w:val="{self.small_half_points}"/>'
                ),
                para_props='<w:spacing w:after="0"/>',
            )
            + "</w:styles>"
        )

    def numbering_xml(self) -> str:
        """``word/numbering.xml``: the sub-point list, and it is genuinely different per era.

        Generation 1 lettered its sub-points ``(a) (b) (c)``, which is why a generation-1 clause
        label can end in ``(b)``.  Generation 2 numbered them ``1) 2) 3)``.  The list is used —
        every clause that carries more than a single obligation renders its obligations through
        it — so this part is load-bearing rather than decorative.
        """
        return ooxml.part_header(f"<w:numbering {ooxml.W_NS}>") + (
            '<w:abstractNum w:abstractNumId="0">'
            '<w:multiLevelType w:val="singleLevel"/>'
            '<w:lvl w:ilvl="0">'
            '<w:start w:val="1"/>'
            f'<w:numFmt w:val="{self.sub_list_format}"/>'
            f'<w:lvlText w:val="{self.sub_list_text}"/>'
            '<w:lvlJc w:val="left"/>'
            f'<w:pPr><w:ind w:left="{self.clause_indent + 340}" w:hanging="340"/></w:pPr>'
            "</w:lvl>"
            "</w:abstractNum>"
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            "</w:numbering>"
        )

    def settings_xml(self) -> str:
        """``word/settings.xml``.  No ``w:rsid*``: see the module docstring."""
        return ooxml.part_header(f"<w:settings {ooxml.W_NS}>") + (
            '<w:zoom w:percent="100"/>'
            '<w:defaultTabStop w:val="720"/>'
            '<w:characterSpacingControl w:val="doNotCompress"/>'
            '<w:themeFontLang w:val="en-AU"/>'
            "<w:compat>"
            '<w:compatSetting w:name="compatibilityMode" '
            'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
            "</w:compat>"
            "</w:settings>"
        )

    def font_table_xml(self) -> str:
        """``word/fontTable.xml``, naming only the two fonts this generation asks for."""
        fonts = "".join(
            f'<w:font w:name="{name}"><w:charset w:val="00"/>'
            '<w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>'
            for name in sorted({self.body_font, self.heading_font})
        )
        return ooxml.part_header(f"<w:fonts {ooxml.W_NS}>") + fonts + "</w:fonts>"

    # ── helpers ──────────────────────────────────────────────────────────────────────────

    def _heading_case(self) -> str:
        """Return the heading case: full capitals before 2016, small capitals after."""
        return "<w:smallCaps/>" if self.generation == RETYPESET_GENERATION else "<w:caps/>"

    def _doc_defaults(self) -> str:
        return (
            "<w:docDefaults><w:rPrDefault><w:rPr>"
            f'<w:rFonts w:ascii="{self.body_font}" w:hAnsi="{self.body_font}" '
            f'w:cs="{self.body_font}"/>'
            f'<w:sz w:val="{self.body_half_points}"/><w:szCs w:val="{self.body_half_points}"/>'
            '<w:lang w:val="en-AU" w:eastAsia="en-AU" w:bidi="ar-SA"/>'
            "</w:rPr></w:rPrDefault>"
            "<w:pPrDefault><w:pPr>"
            '<w:spacing w:after="120" w:line="240" w:lineRule="auto"/>'
            "</w:pPr></w:pPrDefault></w:docDefaults>"
        )

    @staticmethod
    def _style(
        style_id: str,
        name: str,
        *,
        run_props: str,
        para_props: str,
        default: bool = False,
    ) -> str:
        default_attr = ' w:default="1"' if default else ""
        based = "" if style_id == "Normal" else '<w:basedOn w:val="Normal"/>'
        p_pr = f"<w:pPr>{para_props}</w:pPr>" if para_props else ""
        r_pr = f"<w:rPr>{run_props}</w:rPr>" if run_props else ""
        return (
            f'<w:style w:type="paragraph"{default_attr} w:styleId="{style_id}">'
            f'<w:name w:val="{ooxml.escape(name)}"/>{based}<w:qFormat/>{p_pr}{r_pr}</w:style>'
        )


#: The generation-1 procedural sections.  Authored template furniture; see the module docstring.
#: Twelve entries because ``clause_registry.section`` reaches 12 in the committed answer key, and
#: :func:`mainline_corpus.docx.model.g1_section_title` raises rather than falling off the end.
G1_SECTION_TITLES: Final[tuple[str, ...]] = (
    "Purpose and scope of the task",
    "Preparation and planning",
    "Isolation and making safe",
    "Access, entry and atmosphere",
    "Execution of the work",
    "Verification and testing",
    "Monitoring, alarms and setpoints",
    "Abnormal conditions and emergency response",
    "Return to service and handback",
    "Records, retention and review",
    "Competency and authorisation",
    "References and related documents",
)


G1: Final[HouseStyle] = HouseStyle(
    generation=1,
    key="g1",
    label="Kestrel house style, 2004-2016",
    body_font="Arial",
    heading_font="Arial",
    body_half_points=20,
    small_half_points=16,
    title_half_points=28,
    heading_half_points=24,
    heading_colour="000000",
    rule_colour="000000",
    heading_word="SECTION",
    sub_list_format="lowerLetter",
    sub_list_text="(%1)",
    revision_table_at="back",
    clause_indent=851,
    clause_hanging=851,
    margins={"top": 1134, "right": 1134, "bottom": 1134, "left": 1418},
    letterhead_shade="FFFFFF",
)

G2: Final[HouseStyle] = HouseStyle(
    generation=2,
    key="g2",
    label="Kestrel house style, 2016 retypeset",
    body_font="Calibri",
    heading_font="Calibri",
    body_half_points=21,
    small_half_points=17,
    title_half_points=32,
    heading_half_points=26,
    heading_colour="1F3864",
    rule_colour="8496B0",
    heading_word="CHAPTER",
    sub_list_format="decimal",
    sub_list_text="%1)",
    revision_table_at="front",
    clause_indent=992,
    clause_hanging=992,
    margins={"top": 1418, "right": 1134, "bottom": 1134, "left": 1134},
    letterhead_shade="EDF1F6",
)


def for_generation(generation: int) -> HouseStyle:
    """Return the house style for ``generation``.

    Raises on anything but 1 or 2.  There is no third generation and a silent default would put
    a document in the wrong house style, which is the one error this whole module exists to make
    impossible to make by accident.
    """
    if generation == 1:
        return G1
    if generation == RETYPESET_GENERATION:
        return G2
    raise ValueError(
        f"there is no generation {generation!r} house style. The corpus has exactly two: "
        "1 (2004-2016) and 2 (the 2016 retypeset)."
    )
