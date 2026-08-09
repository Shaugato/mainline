# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The fixed OPC parts: content types, relationships, and the two ``docProps`` files.

These are the parts nobody reads and everybody's build fingerprint hides in.  Three rules:

* **``docProps/core.xml`` carries the document's own effective date**, in both
  ``dcterms:created`` and ``dcterms:modified``.  Not the build date — the *document's* date.  A
  1980 stamp in a controlled document's properties would be visible in Word's own info panel and
  would contradict the letterhead; the build clock would be a fingerprint.  The document date is
  an input, so it may safely be output.
* **``docProps/app.xml`` carries no session state.**  ``TotalTime`` (editing minutes),
  ``LastPrinted``, ``Pages``/``Words``/``Characters`` (recomputed by Word at open) and any
  revision counter are omitted.  ``Application`` records this builder and its version, so a file
  on a stranger's disk says what made it.
* **No media, ever.**  ``[Content_Types].xml`` declares no image default extension, so a future
  edit that adds a picture fails loudly at package-validation time rather than quietly
  introducing ``word/media/image1.png`` — a part whose name depends on the order parts were
  added, which is a reproducibility hazard dressed as a feature.
"""

from __future__ import annotations

from typing import Final

from .ooxml import escape, part_header

__all__ = [
    "CONTENT_TYPES",
    "DOCUMENT_RELS",
    "PACKAGE_RELS",
    "PRODUCER",
    "PRODUCER_VERSION",
    "TEMPLATE_DATE",
    "app_xml",
    "core_xml",
]

#: Bump when the emitted markup changes.  It is an input to every digest in
#: ``MANIFEST.docx.sha256`` and is meant to be: a document produced by a different builder is a
#: different artefact even when the words match.
PRODUCER_VERSION: Final[str] = "1.0.0"
PRODUCER: Final[str] = f"MAINLINE corpusgen docx {PRODUCER_VERSION}"

#: Templates have no effective date of their own; they get a constant that is obviously not a
#: build clock.  It matches the zip member stamp, which makes the intent unmistakable.
TEMPLATE_DATE: Final[str] = "1980-01-01"

_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

#: A content type is a MIME type, **not** a namespace URI, and the two look similar enough that
#: the mistake is easy and silent: a package whose main part is typed with the WordprocessingML
#: *namespace* opens in this repository's own reader and is rejected by Word as "not a Word file".
#: It was rejected here by ``python-docx`` in ``verify.opens_with_python_docx``, which is exactly
#: the reason that optional check exists — our reader agreeing with our writer proves nothing.
_WML = "application/vnd.openxmlformats-officedocument.wordprocessingml"

CONTENT_TYPES: Final[str] = part_header(f'<Types xmlns="{_CT}">') + (
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    f'<Override PartName="/word/document.xml" ContentType="{_WML}.document.main+xml"/>'
    f'<Override PartName="/word/styles.xml" ContentType="{_WML}.styles+xml"/>'
    f'<Override PartName="/word/numbering.xml" ContentType="{_WML}.numbering+xml"/>'
    f'<Override PartName="/word/settings.xml" ContentType="{_WML}.settings+xml"/>'
    f'<Override PartName="/word/fontTable.xml" ContentType="{_WML}.fontTable+xml"/>'
    '<Override PartName="/docProps/core.xml" '
    'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    "</Types>"
)

PACKAGE_RELS: Final[str] = part_header(f'<Relationships xmlns="{_PKG_REL}">') + (
    f'<Relationship Id="rId1" Type="{_OFFICE_REL}/officeDocument" Target="word/document.xml"/>'
    f'<Relationship Id="rId2" Type="{_PKG_REL}/metadata/core-properties" '
    'Target="docProps/core.xml"/>'
    f'<Relationship Id="rId3" Type="{_OFFICE_REL}/extended-properties" Target="docProps/app.xml"/>'
    "</Relationships>"
)

DOCUMENT_RELS: Final[str] = part_header(f'<Relationships xmlns="{_PKG_REL}">') + (
    f'<Relationship Id="rId1" Type="{_OFFICE_REL}/styles" Target="styles.xml"/>'
    f'<Relationship Id="rId2" Type="{_OFFICE_REL}/numbering" Target="numbering.xml"/>'
    f'<Relationship Id="rId3" Type="{_OFFICE_REL}/settings" Target="settings.xml"/>'
    f'<Relationship Id="rId4" Type="{_OFFICE_REL}/fontTable" Target="fontTable.xml"/>'
    "</Relationships>"
)


def core_xml(
    *,
    title: str,
    subject: str,
    creator: str,
    category: str,
    revision: str,
    iso_date: str,
    keywords: str = "",
) -> str:
    """``docProps/core.xml`` with both timestamps pinned to ``iso_date`` at midnight UTC.

    Midnight UTC rather than the corpus's ``+10:00`` because ``dcterms:W3CDTF`` in a Word file is
    conventionally written as ``Z`` and Word normalises anything else on save; writing the form
    Word would write means a round trip through Word does not change the property, which keeps
    the fixture and a human-edited copy comparable.
    """
    stamp = f"{iso_date}T00:00:00Z"
    keywords_element = f"<cp:keywords>{escape(keywords)}</cp:keywords>" if keywords else ""
    return part_header(
        "<cp:coreProperties "
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    ) + (
        f"<dc:title>{escape(title)}</dc:title>"
        f"<dc:subject>{escape(subject)}</dc:subject>"
        f"<dc:creator>{escape(creator)}</dc:creator>"
        f"{keywords_element}"
        f"<cp:lastModifiedBy>{escape(creator)}</cp:lastModifiedBy>"
        f"<cp:revision>{escape(revision)}</cp:revision>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>'
        f"<cp:category>{escape(category)}</cp:category>"
        "<cp:contentStatus>Issued</cp:contentStatus>"
        "</cp:coreProperties>"
    )


def app_xml(*, template: str, company: str) -> str:
    """``docProps/app.xml``.  Every element here is constant or an input; none is session state."""
    return part_header(
        "<Properties "
        'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
    ) + (
        f"<Template>{escape(template)}</Template>"
        f"<Application>{escape(PRODUCER)}</Application>"
        f"<Company>{escape(company)}</Company>"
        "<AppVersion>1.0000</AppVersion>"
        "<DocSecurity>0</DocSecurity>"
        "<ScaleCrop>false</ScaleCrop>"
        "<LinksUpToDate>false</LinksUpToDate>"
        "<SharedDoc>false</SharedDoc>"
        "<HyperlinksChanged>false</HyperlinksChanged>"
        "</Properties>"
    )
