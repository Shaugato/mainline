# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E3, second leg — the SBOM diff against the previous image digest.

The AST scan proves the *source* holds no model client. It does not prove the
*image* holds none: a transitive dependency can pull ``anthropic`` in without a
single line of our code changing. ARCHITECTURE.md §8.2 therefore pairs E3's code
scan with an SBOM diff against the previous digest, and that is what this module
does.

Two rules, and the second is the one that survives a corpus of excuses:

* the current SBOM contains no denied component at all; and
* the diff against the baseline **introduced** none — stated separately so that a
  reviewer can tell "we never had it" from "we did not add it this build".

Two facts about the honest limits, stated because the check is worth less if
they are not: an SBOM that is not bound to an image digest proves nothing about
what shipped, so a digest-less SBOM is a violation rather than a pass; and the
absence of a committed baseline is a **skip with a reason**, never a pass, since
"no previous digest" and "no new model SDK" are not the same sentence.

CycloneDX 1.4 to 1.6 JSON and SPDX 2.x JSON are both accepted, because ``syft`` can
emit either and pinning the format would make the check hostage to a flag.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SbomParseError
from .findings import Enforcement, Report

AUTHORITY = "ARCHITECTURE.md §8.2 E3 (SBOM diff against the previous digest)"

#: Component names that mean a model client is in the image. Matched
#: case-insensitively against the whole name and against the purl.
DENIED_COMPONENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^anthropic(-|_|$)", re.IGNORECASE),
    re.compile(r"^claude[-_]agent[-_]sdk$", re.IGNORECASE),
    re.compile(r"^strands([-_]agents)?$", re.IGNORECASE),
    re.compile(r"^langgraph", re.IGNORECASE),
    re.compile(r"^langchain", re.IGNORECASE),
    re.compile(r"^llama[-_]index", re.IGNORECASE),
    re.compile(r"^openai$", re.IGNORECASE),
    re.compile(r"^litellm$", re.IGNORECASE),
    re.compile(r"^instructor$", re.IGNORECASE),
    re.compile(r"^mainline[-_]agentkit$", re.IGNORECASE),
    re.compile(r"^aws[-_]sdk[-_]bedrock", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class Component:
    name: str
    version: str
    purl: str = ""
    kind: str = "library"

    @property
    def key(self) -> str:
        return f"{self.name.lower()}"

    def __str__(self) -> str:
        return f"{self.name}@{self.version}" if self.version else self.name


@dataclass(frozen=True, slots=True)
class Sbom:
    """A parsed SBOM plus the image digest it claims to describe."""

    document_format: str
    spec_version: str
    subject: str
    digest: str
    components: tuple[Component, ...]
    source: str = ""

    def by_name(self) -> Mapping[str, Component]:
        return {c.key: c for c in self.components}

    def denied(self) -> tuple[Component, ...]:
        return tuple(c for c in self.components if is_denied_component(c))


def is_denied_component(component: Component) -> bool:
    haystacks = (component.name, component.purl)
    for pattern in DENIED_COMPONENT_PATTERNS:
        for haystack in haystacks:
            if not haystack:
                continue
            if pattern.search(haystack):
                return True
            # purls look like pkg:pypi/anthropic@0.40.0 — test the bare name too.
            if haystack.startswith("pkg:"):
                tail = haystack.split("/")[-1].split("@")[0]
                if pattern.search(tail):
                    return True
    return False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_sbom(document: Mapping[str, Any], *, source: str = "") -> Sbom:
    if "bomFormat" in document or "components" in document:
        return _parse_cyclonedx(document, source=source)
    if "spdxVersion" in document or "packages" in document:
        return _parse_spdx(document, source=source)
    raise SbomParseError(
        f"{source or '<document>'}: neither CycloneDX (bomFormat/components) nor "
        "SPDX (spdxVersion/packages)"
    )


def load_sbom(path: Path) -> Sbom:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SbomParseError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SbomParseError(f"{path}: top level is {type(raw).__name__}, expected an object")
    return parse_sbom(raw, source=str(path))


def _parse_cyclonedx(document: Mapping[str, Any], *, source: str) -> Sbom:
    components: list[Component] = []
    for entry in _as_sequence(document.get("components")):
        if not isinstance(entry, dict):
            continue
        components.append(
            Component(
                name=str(entry.get("name", "")),
                version=str(entry.get("version", "")),
                purl=str(entry.get("purl", "")),
                kind=str(entry.get("type", "library")),
            )
        )
        # CycloneDX allows nesting; a nested component still ships in the image.
        for nested in _as_sequence(entry.get("components")):
            if isinstance(nested, dict):
                components.append(
                    Component(
                        name=str(nested.get("name", "")),
                        version=str(nested.get("version", "")),
                        purl=str(nested.get("purl", "")),
                        kind=str(nested.get("type", "library")),
                    )
                )
    metadata = document.get("metadata")
    subject = ""
    digest = ""
    if isinstance(metadata, dict):
        component = metadata.get("component")
        if isinstance(component, dict):
            subject = str(component.get("name", ""))
            digest = _cyclonedx_digest(component)
    return Sbom(
        document_format="CycloneDX",
        spec_version=str(document.get("specVersion", "")),
        subject=subject,
        digest=digest,
        components=tuple(components),
        source=source,
    )


def _cyclonedx_digest(component: Mapping[str, Any]) -> str:
    version = str(component.get("version", ""))
    if version.startswith("sha256:"):
        return version
    for hash_entry in _as_sequence(component.get("hashes")):
        if isinstance(hash_entry, dict) and str(hash_entry.get("alg", "")).upper() == "SHA-256":
            content = str(hash_entry.get("content", ""))
            if content:
                return content if content.startswith("sha256:") else f"sha256:{content}"
    purl = str(component.get("purl", ""))
    if "sha256" in purl:
        marker = purl.split("sha256")[-1].lstrip(":%3A=")
        if marker:
            return f"sha256:{marker.split('&')[0]}"
    return ""


def _parse_spdx(document: Mapping[str, Any], *, source: str) -> Sbom:
    components: list[Component] = []
    subject = str(document.get("name", ""))
    digest = ""
    for entry in _as_sequence(document.get("packages")):
        if not isinstance(entry, dict):
            continue
        purl = ""
        for ref in _as_sequence(entry.get("externalRefs")):
            if isinstance(ref, dict) and ref.get("referenceType") == "purl":
                purl = str(ref.get("referenceLocator", ""))
                break
        components.append(
            Component(
                name=str(entry.get("name", "")),
                version=str(entry.get("versionInfo", "")),
                purl=purl,
                kind="library",
            )
        )
        for checksum in _as_sequence(entry.get("checksums")):
            if (
                not digest
                and isinstance(checksum, dict)
                and str(checksum.get("algorithm", "")).upper() == "SHA256"
                and entry.get("name") == subject
            ):
                digest = f"sha256:{checksum.get('checksumValue', '')}"
    return Sbom(
        document_format="SPDX",
        spec_version=str(document.get("spdxVersion", "")),
        subject=subject,
        digest=digest,
        components=tuple(components),
        source=source,
    )


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list) else ()


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SbomDiff:
    added: tuple[Component, ...]
    removed: tuple[Component, ...]
    changed: tuple[tuple[Component, Component], ...]

    @property
    def introduced_denied(self) -> tuple[Component, ...]:
        return tuple(c for c in self.added if is_denied_component(c))


def diff_sboms(previous: Sbom, current: Sbom) -> SbomDiff:
    before = previous.by_name()
    after = current.by_name()
    added = tuple(after[k] for k in sorted(set(after) - set(before)))
    removed = tuple(before[k] for k in sorted(set(before) - set(after)))
    changed = tuple(
        (before[k], after[k])
        for k in sorted(set(before) & set(after))
        if before[k].version != after[k].version
    )
    return SbomDiff(added=added, removed=removed, changed=changed)


# ---------------------------------------------------------------------------
# The enforcement
# ---------------------------------------------------------------------------


def check_sbom_pair(baseline: Path | None, current: Path | None) -> Report:
    """Assert the shipped image carries no model SDK, and introduced none.

    ``baseline``/``current`` may be ``None`` or missing; every absence becomes a
    named skip with the reason spelled out, and the caller must treat a report
    that examined nothing as unproven.
    """
    report = Report(enforcement=Enforcement.E3_CODE)

    if current is None or not current.exists():
        report.skip(
            rule="E3-SBOM-CURRENT-ABSENT",
            subject=str(current) if current else "<unset>",
            reason=(
                "no SBOM for the current kernel image is committed, so the image contents "
                "are unproven. The AST scan still stands on its own; this leg does not."
            ),
        )
        return report

    current_sbom = load_sbom(current)
    report.examine(len(current_sbom.components))

    if not current_sbom.digest:
        report.violate(
            rule="E3-SBOM-NO-DIGEST",
            subject=current_sbom.source or str(current),
            detail=(
                "SBOM is not bound to an image digest; it therefore describes no particular "
                "artefact and cannot support a claim about what shipped"
            ),
            authority=AUTHORITY,
        )

    for component in current_sbom.denied():
        report.violate(
            rule="E3-SBOM-MODEL-SDK",
            subject=str(component),
            detail=(
                f"kernel image SBOM ({current_sbom.digest or 'no digest'}) contains a model "
                f"client component: {component.name}"
            ),
            authority=AUTHORITY,
        )

    if baseline is None or not baseline.exists():
        report.skip(
            rule="E3-SBOM-BASELINE-ABSENT",
            subject=str(baseline) if baseline else "<unset>",
            reason=(
                "no previous-digest SBOM is committed, so no diff was computed. "
                "'No previous digest' is not 'no new model SDK'."
            ),
        )
        return report

    baseline_sbom = load_sbom(baseline)
    delta = diff_sboms(baseline_sbom, current_sbom)
    report.note(
        f"SBOM diff {baseline_sbom.digest or 'baseline'} -> {current_sbom.digest or 'current'}: "
        f"+{len(delta.added)} -{len(delta.removed)} ~{len(delta.changed)}"
    )
    for component in delta.introduced_denied:
        report.violate(
            rule="E3-SBOM-INTRODUCED",
            subject=str(component),
            detail=(
                f"this build introduced a model client component absent from "
                f"{baseline_sbom.digest or 'the baseline image'}"
            ),
            authority=AUTHORITY,
        )
    return report
