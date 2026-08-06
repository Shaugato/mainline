# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""CANONHOLD — the versioned canonicaliser.

Public surface::

    from mainline_domain.canon import canonicalise, CANON_VERSION

    result = canonicalise(raw_clause_text)
    result.canon_text      # every offset in the system is into this
    result.canon_sha256    # clause_version.canon_sha256
    result.printed_label   # '7.3.2(b)' — stored, never identity

**Honest position (see ``novelty/canonhold.yaml``): this is a
re-parameterisation.**  NFKC folding, de-hyphenation against a lexicon,
layout-first ingest and FastCDC segmentation are all published work.  The only
part that is not standard practice is that ``canon_version`` is a *migration*
rather than a config flag — re-normalising history is a deliberate, auditable
act, because the digests it moves are the ones blame edges were attached to.
"""

from __future__ import annotations

from .digest import canon_digest, segment_digest
from .furniture import FurnitureModel
from .lexicon import DomainLexicon, load_lexicon
from .pipeline import canonicalise
from .version import CANON_DIGEST_DOMAIN, CANON_VERSION

__all__ = [
    "CANON_DIGEST_DOMAIN",
    "CANON_VERSION",
    "DomainLexicon",
    "FurnitureModel",
    "canon_digest",
    "canonicalise",
    "load_lexicon",
    "segment_digest",
]
