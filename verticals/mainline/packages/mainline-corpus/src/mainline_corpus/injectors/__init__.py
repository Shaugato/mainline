# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The eight realism injectors from ``research/06-build/demo-engineering.md`` §1 stage 5.

Each one exists to make exactly one architectural claim provable on camera, and each is written
here as a *schedule* rather than as prose or as a rendered artefact — the renderer, the .docx
builder and the embedding lane consume these schedules, and none of them has to re-derive which
clause moved where.

===========================  =====================================  ==========================
Injector                     Rate                                   Proves
===========================  =====================================  ==========================
Full retypeset               1 per document, 2016-11-21             clause identity survives
                                                                    a complete reflow
Document split / migration   8 documents, 2019                      blame crosses document
                                                                    boundaries
Orphan clauses               12                                     "MAINLINE *believes* an
                                                                    event wrote this — say yes
                                                                    or no under signature"
Slow weakening               4 chains, 3 MOCs, ~6 years             fixity patrol and bisect
Author churn                 30 % of authors, already in stage 1    why you cannot simply ask
                                                                    someone
Decoy events                 60                                     mechanism matching, not
                                                                    vocabulary matching
Fleet siblings               9 groups, one alert, three sites       cherry-pick, and
                                                                    dedup-to-one-check
Vocabulary drift             continuous, 2004 -> 2026               why lexical-only fails
===========================  =====================================  ==========================

Two of these are **selections, not injections**, and the distinction is load-bearing.
``mainline.event`` is stage 1's table and has exactly one writer; a second generator appending
rows to it would fork the corpus and make the severity histogram, the Poisson intensity and the
excitation term all quietly wrong.  So the decoy set and the fleet-sibling set are *found* in
the sampled timeline against a stated predicate, and the schedule records which rows satisfied
it.  A decoy that the corpus already contained is a better decoy than one written to be found.

Author churn is consumed rather than produced for the same reason: stage 1 already separates
30 % of its people, and re-deriving that here would give two numbers where the corpus needs one.
"""

from __future__ import annotations

from . import churn, decoys, drift, fleet, orphans, retypeset, split, weakening

__all__ = [
    "churn",
    "decoys",
    "drift",
    "fleet",
    "orphans",
    "retypeset",
    "split",
    "weakening",
]
