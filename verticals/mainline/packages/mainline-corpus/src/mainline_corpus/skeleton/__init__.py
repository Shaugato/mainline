# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1 — the deterministic world.

Zero LLM.  Zero AWS.  Zero database.  This package emits *structure only*: the site and asset
graph, the archival activity taxonomy, the people, the incident timeline, the control failures,
the document revision cadence and the MOC stream.  Prose is stage 2's job, documents are stage
3's, and the ground-truth blame edges are ``corpus-blame-key``'s.

The order is the point.  The failure mode of every synthetic-corpus attempt is asking a model for
"a realistic safety corpus" and receiving fluent prose with no causal structure: blame walks come
out one hop deep, precision cannot be computed, and the demo becomes theatre.  Authoring the
history first and rendering the text second means the answer key exists by construction.

── Public surface ───────────────────────────────────────────────────────────────────────────

    from mainline_corpus.skeleton import generate
    result = generate(Path("out/skeleton"))

    python -m mainline_corpus.skeleton --out out/skeleton      # standalone
    corpusgen skeleton --out out/skeleton                       # via the shared CLI

── The identity contract, for every other worker ────────────────────────────────────────────
Every id is ``uuid5(CORPUS_NS, "<entity>:<natural key>")`` — see :func:`mainline_corpus.rng.sid`.
Nothing needs to read this package's output to compute one::

    sid("site", "MRD")                 sid("event", "INC-2013-044")
    sid("doc", "MRD/PRO-MEC-014")      sid("change_request", "MOC-2026-0413")
    sid("permit", "WO-88213")          sid("activity_node", "MRD/1/3/<file label>")
    sid("control_failure", "<event ref>/<control class>")

── What this package refuses to do ──────────────────────────────────────────────────────────
* **Write a projected column.**  ``emit.Emitter`` raises on any row naming one (D8, P2).
* **Invent a value for a column it cannot know.**  ``narrative``, ``source_sha256``,
  ``evidence_span``, ``quote_sha256`` and ``merged_commit`` are emitted null and registered in
  ``pending.jsonl`` with the worker who fills each.  A plausible-looking hash in a custody column
  is worse than a null, because a null is refused and a wrong hash is believed.
* **Emit ``severity_gate >= 4`` with ``severity_basis = 'model_rated'``.**  That is a shipped
  ``CHECK`` (``model_cannot_arm``) and the loader would be refused, correctly.
* **Draw an asset tag, a citation or a name.**  Every literal comes from
  ``mainline_corpus.gazetteer``; see its ``README.md`` for why.
* **Touch a wall clock.**  ``datetime.now()`` appears nowhere; see ``clock.py``.
"""

from __future__ import annotations

from .build import Skeleton, SkeletonResult, build_skeleton, generate

__all__ = ["Skeleton", "SkeletonResult", "build_skeleton", "generate"]
