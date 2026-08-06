# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Committed data files for the domain.

Everything under this package is **evidence, not configuration**.  A gazetteer,
a permutation table or a unit definition file that can drift between runs makes
every downstream digest unfalsifiable, so these files are committed, versioned
with the algorithm that reads them, and never fetched at runtime.

Subdirectories are owned by different workers and are kept apart on purpose:

======================  ====================================================
``gazetteer/``          ANCHORLOCK gazetteers + the de-hyphenation lexicon (W1)
``units/``              Pint unit definitions (W2)
``registry/``           ``safe_direction`` seed (W2)
``lexicon/``            deontic / hedge lexicons (W3)
``minhash/``            committed permutation table (W7)
``policy/``             ``identity_policy-v1.toml`` (W8)
======================  ====================================================

Loading uses a plain filesystem path.  A zipimported distribution is not
supported and would be caught immediately by any test that reads a gazetteer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

__all__ = ["DATA_ROOT", "data_file"]

DATA_ROOT: Final[Path] = Path(__file__).resolve().parent


def data_file(*parts: str) -> Path:
    """Resolve a committed data file, raising if it is missing.

    A missing data file is never a soft failure: a canonicaliser running
    without its lexicon silently changes every digest it produces.
    """
    path = DATA_ROOT.joinpath(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"committed data file is missing: {path}")
    return path
