# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Canonical prompt assembly and the cache key.

The cache key is ``sha256(canonical_prompt ‖ model_id ‖ prompt_version)``.  Everything hard
about this module is in the word *canonical*, and the failure mode it prevents is silent: a
prompt assembled from a dict whose iteration order moved, or with a locale-formatted float, or
with CRLF on one machine and LF on another, produces a different key for the same node.  The
cache then misses, the render re-runs, the committed tree changes, and the reproducibility
claim that the whole judge-facing bundle rests on dies without a single error message.

So assembly is spelled out here, once, and nothing else in the package concatenates a prompt.

**The canonical form** is a fixed six-field block, LF-terminated::

    prompt: icam
    prompt_version: v1
    template_sha256: 43b8…
    node: event_narrative:INC-2013-044
    system:
    <normalised system text>
    user:
    <normalised user text>
    facts:
    {"asset":"P-4102",…}

``facts`` is serialised by :func:`mainline_corpus.skeleton.emit.canonical_json` — key-sorted,
tight separators, JSON-native values only, no ``default=`` escape hatch.  That function already
refuses a ``UUID``, a ``datetime`` or a non-finite float, which are the three things that would
otherwise reach the hash with a representation nobody chose.

**Why the template digest is in the body rather than only in the version.**  If only
``prompt_version`` distinguished prompts, an edit that forgot to bump the version would leave
every key unchanged and the committed cache would silently describe text that no longer exists.
With the digest inside the canonical prompt, editing the file re-keys everything it produced —
the entries do not go stale, they go *absent*, and the rebuild is visible in the diff.

**Why the node id is in the body.**  Two clause revisions can carry byte-identical facts (a
``restate`` of the same clause in two documents).  Without the node id they would share one
cache entry, and the renderer census would under-count by however many collisions there were.
The node id makes the key a function of the node, which is what the census counts.

**Why the separator is NUL.**  Concatenating three UTF-8 strings is not injective —
``("ab","c")`` and ``("a","bc")`` are the same bytes.  NUL cannot occur in any of the three
inputs, all of which this package produced, so it separates unambiguously.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from ..prompts import Prompt, normalise_text
from ..skeleton.emit import canonical_json
from .params import KEY_SEPARATOR

__all__ = ["cache_key", "canonical_prompt", "facts_json", "prompt_sha256"]


def facts_json(facts: Mapping[str, Any]) -> str:
    """Serialise the facts block canonically."""
    return canonical_json(facts)


def canonical_prompt(
    prompt: Prompt,
    *,
    node_id: str,
    facts: Mapping[str, Any],
    prompt_version: str,
) -> str:
    """Assemble the one string this stage ever hashes or sends.

    ``prompt_version`` is passed in rather than read off ``prompt`` so that a caller replaying
    a pinned version derives that version's key, and so that a mismatch between the pin and the
    file is visible here rather than three layers down.
    """
    if not node_id:
        raise ValueError("canonical_prompt requires a node id")
    body = "\n".join(
        (
            f"prompt: {prompt.kind}",
            f"prompt_version: {prompt_version}",
            f"template_sha256: {prompt.template_sha256}",
            f"node: {node_id}",
            "system:",
            prompt.system.rstrip("\n"),
            "user:",
            prompt.user.rstrip("\n"),
            "facts:",
            facts_json(facts),
        )
    )
    return normalise_text(body)


def prompt_sha256(canonical: str) -> str:
    """``sha256`` of the canonical prompt, hex."""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cache_key(canonical: str, *, model_id: str, prompt_version: str) -> str:
    """``sha256(canonical_prompt ‖ model_id ‖ prompt_version)``, hex.

    NUL-separated so the concatenation is injective (see the module docstring).
    """
    digest = hashlib.sha256()
    digest.update(canonical.encode("utf-8"))
    digest.update(KEY_SEPARATOR)
    digest.update(model_id.encode("utf-8"))
    digest.update(KEY_SEPARATOR)
    digest.update(prompt_version.encode("utf-8"))
    return digest.hexdigest()
