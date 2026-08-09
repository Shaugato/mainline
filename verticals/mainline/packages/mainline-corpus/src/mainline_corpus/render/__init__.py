# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 2 — the three-tier renderer and the committed content-addressed cache.

Stage 1 authored causality and left four columns pending with this worker named as the owner.
This package fills them, and it fills them **offline by default**.

── The three tiers (decision D2) ────────────────────────────────────────────────────────────

``authored``   Verbatim from ``fixtures/corpus/authored/``.  Every word that appears on camera
               comes from here and nothing paraphrases it.  Owned by ``corpus-spine-authored``.
``template``   A deterministic composer over the skeleton, the gazetteer and the dated
               vocabulary-drift schedule.  It renders the other four thousand three hundred
               nodes with no model, no network and no draw.
``bedrock``    Claude on ``au.anthropic.claude-sonnet-4-5-20250929-v1:0``, strict forced tool
               use, temperature 0, region ``ap-southeast-2``.  Reachable only under
               ``--allow-live`` with ``--policy=model-rendered``, and **never exercised on a
               dated path**: AWS credentials are not valid on the founder's machine and PL-3
               forbids putting an unproven capability on one.

── The cache ────────────────────────────────────────────────────────────────────────────────

    fixtures/corpus/cache/<first2>/<sha256(prompt ‖ model_id ‖ prompt_version)>.json

Committed, closed-shape, free of any wall clock or ambient value, one entry per rendered node
whichever tier produced it.  It is why the corpus rebuilds on a judge's laptop with zero
Bedrock calls, why ``corpus.lock.json``'s renderer census is a fact rather than an assertion,
and why the honesty card cannot lie about how much of this prose a model wrote.

── Public surface ───────────────────────────────────────────────────────────────────────────

    from mainline_corpus.render import generate, verify
    result = generate(Path("build/render"), repo_root=Path("."))
    report = verify(repo_root=Path("."))

    python -m mainline_corpus.render --out build/render        # standalone
    corpusgen render --verify                                   # via the shared CLI

── What this package refuses to do ──────────────────────────────────────────────────────────
* **Open a socket.**  ``--offline`` is the default and is enforced by a guard that raises, not
  by a sentence in a README (:mod:`mainline_corpus.render.netguard`).
* **Trust a model-reported offset.**  Every span is computed here by an exact, unique
  ``find()`` into the canonical text (:mod:`mainline_corpus.render.spans`).
* **Substitute generated prose for a camera-facing node.**  A missing authored fixture is a
  refusal naming ``corpus-spine-authored``, or a recorded deferral.  Never a paraphrase.
* **Write a projected column.**  The stage-2 tree goes through the same ``Emitter`` guard
  stage 1 uses (D8, P2).
* **Retry a model call inside the hashed path.**  A retry loop with jitter is a machine for
  producing two responses under one key.
"""

from __future__ import annotations

from .build import RenderResult, generate
from .params import BEDROCK_MODEL_ID, CACHE_RELPATH, NODE_KINDS, TIERS
from .protocol import MissingAuthored, Rendered, Renderer, RenderNode, RenderRefusal
from .verify import VerifyReport, verify

__all__ = [
    "BEDROCK_MODEL_ID",
    "CACHE_RELPATH",
    "NODE_KINDS",
    "TIERS",
    "MissingAuthored",
    "RenderNode",
    "RenderRefusal",
    "RenderResult",
    "Rendered",
    "Renderer",
    "VerifyReport",
    "generate",
    "verify",
]
