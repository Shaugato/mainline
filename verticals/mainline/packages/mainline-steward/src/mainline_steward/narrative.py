# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Reading the Claude Code session's prose, and refusing to let it become evidence.

The Steward's tool loop lives in a headless ``claude -p`` process (decision A2). That
process reads the pinned CockroachDB Agent Skills, calls the Managed MCP read verbs, and
writes a report. This module is the *only* place that report re-enters this package, and
it re-enters through one narrow door:

    a JSON object of the form ``{"narratives": {"<subject>": "<prose>"}}``

Everything about that door is deliberate:

* **Subjects are matched, never trusted.** A narrative whose subject is not one of the
  findings already built is dropped and counted. The model cannot introduce a finding by
  naming one, because findings are built from the contract before this file is opened.
* **A parse failure is not a run failure.** ``narrative_source`` becomes ``"unparsed"``,
  every finding keeps ``narrative: null``, and the attestation is emitted. The narrative
  is not evidence; losing it costs a reader some prose and costs the record nothing.
* **The transcript is hashed as it arrived.** ``transcript_sha256`` is over the raw bytes
  of the session output, with no normalisation, so a reader handed the transcript file can
  reproduce the digest exactly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .digest import sha256_hex
from .findings import Finding

__all__ = [
    "NARRATIVE_ENVELOPE_KEY",
    "NarrativeSet",
    "attach_narratives",
    "read_transcript",
]

NARRATIVE_ENVELOPE_KEY: Final = "narratives"
"""The single key the prompts instruct the session to emit."""

_FENCED_JSON: Final = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_MAX_NARRATIVE_CHARS: Final = 2_000


@dataclass(frozen=True, slots=True)
class NarrativeSet:
    """What was recovered from a session transcript, and what was thrown away."""

    narratives: Mapping[str, str]
    transcript_sha256: str | None
    transcript_bytes: int
    source: str
    dropped_subjects: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        """Return the ``runtime`` fragment describing where the prose came from."""
        return {
            "narrative_source": self.source,
            "narrative_count": len(self.narratives),
            "narrative_dropped_subjects": list(self.dropped_subjects),
            "transcript_sha256": self.transcript_sha256,
            "transcript_bytes": self.transcript_bytes,
        }


def _decode_session_output(text: str) -> str:
    """Return the assistant's final text from a ``claude -p`` output document.

    ``--output-format json`` produces an object carrying a ``result`` string. Anything
    else — a plain-text run, a stream that was concatenated — is returned unchanged, so a
    change of output format degrades to "we read the whole file", not to a crash.
    """
    stripped = text.strip()
    if not stripped.startswith("{") and not stripped.startswith("["):
        return text
    try:
        document = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    if isinstance(document, Mapping) and isinstance(document.get("result"), str):
        return str(document["result"])
    return text


def _extract_envelope(text: str) -> Mapping[str, Any] | None:
    """Find the last fenced JSON object carrying ``narratives``, or ``None``."""
    candidates: list[str] = [m.group(1) for m in _FENCED_JSON.finditer(text)]
    stripped = text.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)
    for candidate in reversed(candidates):
        try:
            document = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(document, Mapping) and isinstance(
            document.get(NARRATIVE_ENVELOPE_KEY), Mapping
        ):
            return document
    return None


def read_transcript(path: Path | None, *, subjects: Sequence[str]) -> NarrativeSet:
    """Read a session transcript and recover the narratives for known subjects.

    Args:
        path: the session output file, or ``None`` when the run had no model leg.
        subjects: the finding subjects that already exist. A narrative for anything else
            is dropped: the model may describe a read, and may not invent one.

    Returns:
        The recovered narratives, the transcript digest, and what was dropped.
    """
    if path is None:
        return NarrativeSet({}, None, 0, "absent", ())
    if not path.is_file():
        return NarrativeSet({}, None, 0, "missing", ())
    raw = path.read_bytes()
    digest = sha256_hex(raw)
    text = _decode_session_output(raw.decode("utf-8", errors="replace"))
    envelope = _extract_envelope(text)
    if envelope is None:
        return NarrativeSet({}, digest, len(raw), "unparsed", ())
    known = set(subjects)
    recovered: dict[str, str] = {}
    dropped: list[str] = []
    for subject, prose in envelope[NARRATIVE_ENVELOPE_KEY].items():
        name = str(subject)
        if name not in known:
            dropped.append(name)
            continue
        recovered[name] = str(prose).strip()[:_MAX_NARRATIVE_CHARS]
    return NarrativeSet(recovered, digest, len(raw), "session_json", tuple(sorted(dropped)))


def attach_narratives(
    findings: Sequence[Finding], narratives: Mapping[str, str]
) -> tuple[Finding, ...]:
    """Return the findings with prose attached where a subject matched.

    ``Finding.with_narrative`` is the only mutator on a finding and it reaches exactly one
    field, so nothing here can change a statement or a result hash.
    """
    return tuple(finding.with_narrative(narratives.get(finding.subject)) for finding in findings)
