# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Candidate generation for clause identity — stages S1 to S4.

Cheap first, each stage emitting calibrated candidates, **nothing
auto-committing and nothing silently dropping**::

    S1  exact        canon_sha256 equality                    score 1.0
    S2  anchor       identity-anchor-set equality + trigram    accept >= 0.92
    S3  lexical      MinHash/LSH banding, rescored in-app      accept >= 0.90, reject < 0.30
    S4  semantic     anchor-gated ANN over clause_embedding    accept >= 0.93, reject < 0.70

Typical use::

    from mainline_domain.identity.candidates import (
        LexicalCorpus,
        anchor_stage,
        exact_stage,
        lexical_stage,
        semantic_stage,
    )

    corpus = LexicalCorpus(site_id)
    corpus.extend(ancestor_records)

    s1 = exact_stage(query.canon_sha256, ancestor_records)
    s2 = anchor_stage(
        query_anchors=query.anchors, query_text=query.canon_text, corpus=ancestor_records
    )
    s3 = lexical_stage(
        query_text=query.canon_text, corpus=corpus, required_ancestors=blame_bearing_refs
    )
    s4 = semantic_stage(
        query_anchors=query.anchors,
        query_embedding=vec,
        arms=arms_for(site_id, roots),
        runner=runner,
        k=16,
        anchors_of=resolve_anchors,
    )

Four things this package will not do, each because doing it would break a
claim made elsewhere:

* **It never calls a model.**  Embeddings arrive from committed fixtures or the
  ingest path (decision D1, principle P7).  ``mainline_domain`` holds no SDK.
* **It never writes a residue row and never decides an assignment.**  Both
  belong to W8 (``margin-assignment``).  This package produces candidates and
  recorded refusals; the accounting that turns those into blocking rows is a
  separate worker's, and the separation is what keeps candidate generation from
  being able to quietly resolve its own uncertainty.
* **It never orders by a trigram distance operator.**  CockroachDB does not
  support the ``<->`` trigram family, ``word_similarity`` or
  ``strict_word_similarity``.  SQL filters with ``%`` and scores with
  ``similarity()``; edit distance is computed here, in the application, because
  ``levenshtein()`` caps its input at 255 characters.
* **It never issues an ANN query with an unconstrained prefix, and never issues
  an unhinted one.**  One arm per ``(site_id, activity_root)``, pinned to
  ``@ce_ann``, ``UNION ALL``'d, with the plan asserted.  Pinning is the F1
  ruling and it was measured to be load-bearing: on the pinned form CockroachDB
  v26.2.5 *refuses* an arm whose prefix is not constrained to specific values
  (SQLSTATE ``42809``), where the unhinted form plans a ``FULL SCAN`` instead.

The named mechanism is **MINHASH-BAND** and its honest position is recorded in
``novelty/minhash-band.yaml``: the banding is a re-parameterisation of published
practice, and what is unclaimed is the coupling — a committed permutation table
whose signatures are re-derivable years later, and an anchor veto that overrules
an accepted cosine in the direction of *more* adjudication.

**Import boundary.**  Importing this package, and every name it exports, requires
**nothing but the standard library**.  The one third-party dependency —
``rapidfuzz``, for edit distance — is loaded by :mod:`.rescore` on first use and
never at import time.

That is not tidiness.  The MinHash claim is that a signature computed today is
byte-reproducible by a stranger years from now from committed bytes.  A stranger
who must first resolve a wheel from a package index in order to recompute a hash
has not reproduced it from committed bytes — they have reproduced it from
committed bytes *and whatever that wheel contains on the day they ran it*.  An
import-time dependency would quietly make a third-party package part of the
evidence chain for a refusal.  ``test_minhash_determinism.py`` asserts the
property directly, by recomputing the signature under a **different CPython
installation in isolated mode** where nothing is installed at all.
"""

from __future__ import annotations

from .anchor_stage import ANCHOR_STAGE_SQL, anchor_stage, identity_anchor_array
from .band import (
    BAND_HASH_PERSON,
    INSERT_BAND_SQL,
    BandRow,
    InMemoryBandIndex,
    band_hashes,
    band_probe_params,
    band_probe_sql,
    band_rows,
)
from .exact import EXACT_SQL, exact_stage, exact_stage_from_refs
from .explain import (
    INDEX_REFUSED_SQLSTATE,
    ArmPlanAssertion,
    assert_arm_plan,
    assert_arm_set_plans,
    parse_plan,
)
from .lexical import LexicalCorpus, lexical_stage, lexical_stage_from_hits
from .minhash import (
    MERSENNE_61,
    MinHashParams,
    MinHashTableError,
    band_knee,
    default_params,
    derive_coefficients,
    exact_jaccard,
    jaccard_estimate,
    load_params,
    s_curve_probability,
    shingles,
    signature,
)
from .patience_diff import DiffOp, MovedBlock, moved_blocks, patience_diff, render, tokenise
from .records import (
    ClauseRecord,
    ClauseRef,
    DroppedCandidate,
    DropReason,
    StageResult,
    order_candidates,
)
from .rescore import RESCORE_VERSION, Rescore, rescore
from .semantic import (
    ARM_INDEX,
    ARM_SQL,
    ARM_TABLE,
    Arm,
    MissingAnchorSetError,
    arm_union_sql,
    arms_for,
    semantic_stage,
    vector_literal,
)
from .thresholds import DEFAULT_BANDS, StageBands
from .trigram import similarity as trigram_similarity

__all__ = [
    "ANCHOR_STAGE_SQL",
    "ARM_INDEX",
    "ARM_SQL",
    "ARM_TABLE",
    "BAND_HASH_PERSON",
    "DEFAULT_BANDS",
    "EXACT_SQL",
    "INDEX_REFUSED_SQLSTATE",
    "INSERT_BAND_SQL",
    "MERSENNE_61",
    "RESCORE_VERSION",
    "Arm",
    "ArmPlanAssertion",
    "BandRow",
    "ClauseRecord",
    "ClauseRef",
    "DiffOp",
    "DropReason",
    "DroppedCandidate",
    "InMemoryBandIndex",
    "LexicalCorpus",
    "MinHashParams",
    "MinHashTableError",
    "MissingAnchorSetError",
    "MovedBlock",
    "Rescore",
    "StageBands",
    "StageResult",
    "anchor_stage",
    "arm_union_sql",
    "arms_for",
    "assert_arm_plan",
    "assert_arm_set_plans",
    "band_hashes",
    "band_knee",
    "band_probe_params",
    "band_probe_sql",
    "band_rows",
    "default_params",
    "derive_coefficients",
    "exact_jaccard",
    "exact_stage",
    "exact_stage_from_refs",
    "identity_anchor_array",
    "jaccard_estimate",
    "lexical_stage",
    "lexical_stage_from_hits",
    "load_params",
    "moved_blocks",
    "order_candidates",
    "parse_plan",
    "patience_diff",
    "render",
    "rescore",
    "s_curve_probability",
    "semantic_stage",
    "shingles",
    "signature",
    "tokenise",
    "trigram_similarity",
    "vector_literal",
]
