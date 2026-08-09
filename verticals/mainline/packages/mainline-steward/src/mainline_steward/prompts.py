# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Rendering a prompt for one occurrence, from content-addressed assets.

Decision A13: **prompt edits are commits, not deploys.** ``prompt_version`` is the digest
of the prompt tree and is one of the seven inputs to ``agent_identity``, so editing a
prompt mints a different agent — which is the property that makes "a quiet prompt change
suppressed a class of precursor" an attributable event.

The rendering rule is deliberately impoverished. Two files are concatenated — the shared
system preamble and the schedule's own asset — and exactly five ``{{placeholders}}`` are
substituted, from typed run data. There is no template language, no conditionals and no
includes, because a prompt assembled by logic is a prompt whose text is not the thing the
digest covers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from .errors import ConfigurationRefused
from .findings import EVIDENCE_OF_REVIEW
from .schedule import Occurrence

__all__ = [
    "PLACEHOLDERS",
    "PREAMBLE_ASSET",
    "render_prompt",
]

PREAMBLE_ASSET: Final = "system-preamble.md"
"""Prepended to every schedule's asset. The posture lives in one file, not in four."""

PLACEHOLDERS: Final = (
    "schedule_id",
    "occurrence_ts",
    "prompt_version",
    "views",
    "evidence_of_review",
)
"""The complete substitution set. Anything else in double braces is left alone."""

_PLACEHOLDER: Final = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def render_prompt(prompts_dir: Path, occurrence: Occurrence, *, prompt_version: str) -> str:
    """Return the full prompt text for one occurrence.

    Args:
        prompts_dir: the directory holding the Markdown prompt assets.
        occurrence: the schedule and the instant it was delivered for.
        prompt_version: the digest of ``prompts_dir``, passed in rather than recomputed so
            that the text and the identity are demonstrably derived from the same read.

    Returns:
        The preamble followed by the schedule's asset, with the five placeholders filled.

    Raises:
        ConfigurationRefused: an asset is missing. A prompt assembled from whatever files
            happened to be present would be a different prompt with the same version.
    """
    preamble = prompts_dir / PREAMBLE_ASSET
    asset = prompts_dir / occurrence.schedule.prompt
    for path in (preamble, asset):
        if not path.is_file():
            raise ConfigurationRefused(f"no prompt asset at {path}")
    values = {
        "schedule_id": occurrence.schedule.schedule_id,
        "occurrence_ts": occurrence.occurrence_ts,
        "prompt_version": prompt_version,
        "views": "\n".join(f"- mainline_audit.{name}" for name in occurrence.schedule.views),
        "evidence_of_review": EVIDENCE_OF_REVIEW,
    }

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        return values.get(name, match.group(0))

    body = preamble.read_text(encoding="utf-8") + "\n\n---\n\n" + asset.read_text(encoding="utf-8")
    return _PLACEHOLDER.sub(substitute, body)
