# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1b — authored causality, the clause universe it acts on, and gold set GS0.

The corpus is generated **history first, text second** (demo-engineering.md §1).  Stage 1 built
the world; this stage decides *what wrote what*, and it decides it by construction rather than
by inference.  That is the whole reason the corpus has an answer key at all: an LLM asked for "a
realistic safety corpus" returns fluent prose with no causal structure, blame walks come out one
hop deep, and precision cannot be computed.  Here the causal fact exists first and the record of
it is written afterwards — sometimes completely, sometimes partially, and sometimes not at all,
which is exactly the distribution a real archive has.

Read the modules in this order:

``params``      every rate, in one place.
``eventindex``  the one index the timeline is read through — the mechanism join key, enforced.
``clauses``     the clause universe: identity, both numbering schemes, split migrations.
``revisions``   one chronological walk of the cadence; what each revision touched.
``causality``   which event generated which clause revision, whether it left a documentary
                trace, and therefore which of the four bases the edge carries.
``goldset``     GS0: true edges, decoys, negative controls, and the schema they validate against.
``build``       orchestration and emission.
``verify``      this stage's own completion test, runnable with nothing else built.

**No module in this package imports another worker's unwritten entry point**, and nothing here
calls a model, a clock or a network.  ``blame`` is deliberately empty of imports so that
``mainline_corpus.injectors`` can read ``mainline_corpus.blame.params`` without a cycle.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
