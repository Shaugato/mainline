# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""CATSEAL — the Control Assertion Tuple and ``cat_key``, identity axis 2.

Public surface::

    from mainline_domain.cat import extract_cat, normalise_cat, cat_key

    result = extract_cat(clause.canon_text, anchors=anchor_set)
    result.confidence  # 'ok' | 'low' | 'opaque'  -> cat_confidence
    key = cat_key(result.cat)  # 'cat1:...'               -> cat_key

Axis 1 (``canon_sha256``) answers *is this the same text*.  Axis 2 answers **is
this the same obligation** — it survives a rewrite in which every word changes,
because what it hashes is the control the clause asserts rather than the
sentence it asserts it in.  Blame attaches through that equality, which is why
the encoding is specified normatively in ``verticals/mainline/spec/cat-key-v1.md``
and pinned by fifteen committed golden vectors.

**Honest position** (see ``novelty/catseal.yaml``): this is a **composition**.
MeasEval-style quantity-and-context extraction is published, the
OBLIGATION/PROHIBITION/PERMISSION/RECOMMENDATION deontic taxonomy is published,
and content-addressed identity is ancient.  What the survey did not find is
hashing the extracted control tuple into a *second identity axis that a blame
edge attaches to*, so that a rewritten clause keeps its ancestry and a
substantively changed one does not.

**Path A only.**  Nothing in this package calls a model or touches the network,
and a test walks its AST to keep it that way (principle P7: no component that
can decide a state transition may reach a model, and the lattice this feeds
decides one).

Four modules, in the order data flows through them:

===================  ======================================================
``extract``          canon_text → CAT, with the opacity policy
``normalise``        CAT → canonical form (spec §7)
``preimage``         CAT → bytes → ``cat_key`` (spec §3-§6)
``schema``           the controlled vocabularies and ``validate_cat``
===================  ======================================================
"""

from __future__ import annotations

from .extract import (
    OPACITY_REASONS,
    ClauseHint,
    LayoutKind,
    extract_cat,
    extractor_version,
    opacity_reason,
)
from .lexicon import lexicon_fingerprint, load_lexicons
from .normalise import normalise_cat, normalise_list, normalise_phrase
from .preimage import canonical_decimal, cat_key, cat_preimage
from .quantity_bridge import (
    QuantityMatch,
    SiConverter,
    UnconvertibleUnitError,
    iter_quantities,
    si_normalise,
)
from .schema import (
    CAT_CONFIDENCES,
    COMPARATORS,
    COVERAGE_QUANTIFIERS,
    DEONTIC_LABELS,
    EMPTY_CAT,
    validate_cat,
    weakest_confidence,
)
from .version import CAT_EXTRACTOR_VERSION, CAT_FIELD_ORDER, CAT_KEY_VERSION, CAT_PREIMAGE_DOMAIN

__all__ = [
    "CAT_CONFIDENCES",
    "CAT_EXTRACTOR_VERSION",
    "CAT_FIELD_ORDER",
    "CAT_KEY_VERSION",
    "CAT_PREIMAGE_DOMAIN",
    "COMPARATORS",
    "COVERAGE_QUANTIFIERS",
    "DEONTIC_LABELS",
    "EMPTY_CAT",
    "OPACITY_REASONS",
    "ClauseHint",
    "LayoutKind",
    "QuantityMatch",
    "SiConverter",
    "UnconvertibleUnitError",
    "canonical_decimal",
    "cat_key",
    "cat_preimage",
    "extract_cat",
    "extractor_version",
    "iter_quantities",
    "lexicon_fingerprint",
    "load_lexicons",
    "normalise_cat",
    "normalise_list",
    "normalise_phrase",
    "opacity_reason",
    "si_normalise",
    "validate_cat",
    "weakest_confidence",
]
