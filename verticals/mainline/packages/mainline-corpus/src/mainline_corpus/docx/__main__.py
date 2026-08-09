# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``python -m mainline_corpus.docx`` — see :mod:`mainline_corpus.docx.cli`.

This module exists so the subprocess leg of the reproducibility proof has something stable to
invoke.  ``verify`` spawns ``python -m mainline_corpus.docx digests`` in a fresh interpreter; if
that entry point moved, the proof would quietly become a single-process proof.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
