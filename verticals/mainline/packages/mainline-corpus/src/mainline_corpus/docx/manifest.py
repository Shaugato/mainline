# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``MANIFEST.docx.sha256`` — the judge-facing claim, in a format they already have a tool for.

Two files are written, and the split is deliberate.

``MANIFEST.docx.sha256`` is **exactly** GNU ``sha256sum`` output: ``<64 hex><two spaces><path>``,
LF-terminated, sorted by path, no comments and no header.  A reader who does not trust a word of
this repository can run

    cd verticals/mainline/fixtures/corpus && sha256sum -c rendered/MANIFEST.docx.sha256

and get an answer from a tool we did not write.  A comment line would break that, which is why
every word of explanation lives somewhere else.

``MANIFEST.docx.json`` is that somewhere else: producer version, the renderer census (how much
prose each tier actually wrote — decision **D2**'s honesty is generated from here, not asserted),
per-document clause counts, and the retypeset-pair record that states the K3 claim as data.
Paths in both files are relative to ``fixtures/corpus`` and always forward-slashed, so the
manifest does not become a statement about which operating system built it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

__all__ = [
    "JSON_NAME",
    "MANIFEST_NAME",
    "manifest_text",
    "read_manifest",
    "write_manifest",
]

#: A SHA-256 in hex.  Named because ``len(head) != 64`` in a parser reads as a magic number
#: and is in fact the format's definition.
_HEX_DIGEST_LENGTH: Final[int] = 64

MANIFEST_NAME: Final[str] = "MANIFEST.docx.sha256"
JSON_NAME: Final[str] = "MANIFEST.docx.json"


def digest(payload: bytes) -> str:
    """SHA-256, lower-case hex.  One spelling of "the digest" in this package."""
    return hashlib.sha256(payload).hexdigest()


def manifest_text(entries: Mapping[str, bytes]) -> str:
    """``sha256sum``-format text for ``{relative path: bytes}``, sorted by path.

    Two spaces between digest and path, because that is what ``sha256sum`` writes for a file read
    in text mode and what ``sha256sum -c`` parses.  A single space is a different format and
    fails on some implementations.
    """
    lines = [f"{digest(payload)}  {path}" for path, payload in sorted(entries.items())]
    return "\n".join(lines) + "\n"


def read_manifest(path: Path) -> dict[str, str]:
    """Parse a ``sha256sum`` file into ``{path: digest}``.  Raises on a malformed line."""
    result: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        head, separator, tail = line.partition("  ")
        if not separator or len(head) != _HEX_DIGEST_LENGTH:
            raise ValueError(
                f"{path}:{number}: not a sha256sum line. The manifest is machine-checkable by "
                "design; a comment or a stray column would break `sha256sum -c`."
            )
        result[tail] = head
    return result


def _census(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    total: dict[str, int] = {}
    for entry in documents.values():
        for tier, count in entry["renderer_census"].items():
            total[tier] = total.get(tier, 0) + int(count)
    return dict(sorted(total.items()))


def json_sidecar(
    *,
    producer: str,
    entries: Mapping[str, bytes],
    documents: Mapping[str, Mapping[str, Any]],
    templates: Mapping[str, str],
    pair: Mapping[str, Any],
    providers: Mapping[str, bool],
) -> str:
    """Render the provenance sidecar as canonical, LF-terminated JSON."""
    payload = {
        "producer": producer,
        "manifest": MANIFEST_NAME,
        "file_count": len(entries),
        "templates": dict(sorted(templates.items())),
        "documents": {name: documents[name] for name in sorted(documents)},
        "renderer_census": _census(documents),
        "body_providers_available": dict(sorted(providers.items())),
        "retypeset_pair": pair,
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_manifest(root: Path, entries: Mapping[str, bytes], sidecar: str) -> tuple[Path, Path]:
    """Write both manifest files under ``root`` (``fixtures/corpus/rendered``)."""
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / MANIFEST_NAME
    json_path = root / JSON_NAME
    manifest_path.write_text(manifest_text(entries), encoding="utf-8", newline="\n")
    json_path.write_text(sidecar, encoding="utf-8", newline="\n")
    for path in (manifest_path, json_path):
        path.with_suffix(path.suffix + ".license").write_text(
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
            "SPDX-License-Identifier: FSL-1.1-ALv2\n",
            encoding="utf-8",
            newline="\n",
        )
    return manifest_path, json_path
