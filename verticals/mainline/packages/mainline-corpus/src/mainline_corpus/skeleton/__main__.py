# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``python -m mainline_corpus.skeleton --out DIR``.

The shared ``corpusgen`` entry point belongs to ``corpus-contract``.  This module exists so that
stage 1 is runnable, testable and provably byte-reproducible on its own — a worker whose output
can only be produced through another worker's not-yet-written CLI cannot demonstrate its own
completion test.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
