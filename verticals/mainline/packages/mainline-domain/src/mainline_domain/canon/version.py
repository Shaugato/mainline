# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The canonicaliser version.  **Changing this constant is a migration.**

``canon_version`` is stored on every ``mainline.clause_version`` row because
re-normalising history must be a deliberate, auditable act — not a config flag,
not an environment variable, not a constructor argument.

Concretely, the rules this module exists to enforce:

* ``CANON_VERSION`` is a module-level ``int`` constant.  It is **never** read
  from ``os.environ``, a TOML file, a CLI flag or a database row.  There is a
  test that reads this module's source and fails if the words ``environ`` or
  ``getenv`` appear anywhere in the ``canon`` package.
* :func:`mainline_domain.canon.canonicalise` takes **no** version parameter.
  One process, one canon version, decided at build time.
* The version is bound into the digest preimage (see
  :mod:`mainline_domain.canon.digest`), so a bump changes every digest.  That is
  the intended cost: bumping ``canon_version`` without re-normalising and
  re-matching history would make the S1 exact stage silently stop matching, and
  a silent stop is exactly the failure mode this whole product exists to refuse.
* Bumping it therefore requires: a new migration that re-canonicalises the
  affected ``clause_version`` rows, a re-run of the identity cascade over the
  touched commits, and CBM accounts that still balance afterwards.

Version log
-----------
``1`` — initial CANONHOLD: NFKC + confusable/whitespace folding, discretionary
break removal, lexicon-driven de-hyphenation across line wraps, positional and
repetition-based page-furniture stripping, numbering-prefix excision, OCR
confusable repair restricted to numeric token classes, FastCDC segmentation
(Gear rolling hash, min/avg/max = 40/120/400 tokens).
"""

from __future__ import annotations

from typing import Final

__all__ = ["CANON_DIGEST_DOMAIN", "CANON_VERSION"]

CANON_VERSION: Final[int] = 1

CANON_DIGEST_DOMAIN: Final[bytes] = b"mainline/canon/v"
"""Domain-separation prefix for the clause digest preimage.

Full preimage: ``CANON_DIGEST_DOMAIN || ascii(version) || 0x1F || utf8(canon_text)``.
The unit separator makes the version field unambiguous without length-prefixing,
because the version is ASCII digits and ``0x1F`` cannot occur in them.
"""
