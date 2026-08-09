# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``corpusgen render --verify``: recompute the cache, and say exactly what was proven.

Three strengths, reported separately because they are not the same claim and pretending they
are is the failure this repository exists to punish.

**STRUCTURAL** — for every entry, the canonical prompt is reassembled from the prompt file on
disk plus the entry's own ``facts``, its ``prompt_sha256`` is recomputed, and the cache key is
recomputed from ``(prompt ‖ model_id ‖ prompt_version)``.  The key must equal the filename.
Catches: an edited fact block, a swapped model id, a renamed file, a prompt edited without a
rebuild, and an entry filed in the wrong bucket.

**INTEGRITY** — every entry's bytes match the digest ``INDEX.json`` records, and the set of
files on disk is exactly the set the index names.  Catches an edited response *provided the
index was not edited to match*, which is why ``corpus-freeze-load`` folds ``INDEX.json`` into
``MANIFEST.sha256``.

**RECOMPUTED** — the node is re-rendered from the corpus and compared byte for byte.  Available
for the ``authored`` and ``template`` tiers, which are deterministic.  A ``bedrock`` entry can
never reach this strength offline, and the report says ``not_recomputable`` for it rather than
``ok``.  That distinction is the entire point of reporting three strengths.

Structural and integrity run against the committed tree alone, so ``--verify`` works on a clean
checkout with the network guard armed.  Recomputation additionally rebuilds the world, which
takes a couple of seconds; ``--fast`` skips it and the report says so.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import prompts as prompt_pkg
from . import cache as cache_mod
from . import corpusio, netguard
from . import nodes as nodes_mod
from .authored import AUTHORED_RELPATH, AuthoredRenderer
from .canonical import cache_key, canonical_prompt, prompt_sha256
from .params import CACHE_RELPATH, TIER_MODEL_ID
from .validate import SchemaViolation, validate_response

__all__ = ["VerifyReport", "verify"]


@dataclass(slots=True)
class VerifyReport:
    """What ``--verify`` found."""

    cache_dir: Path
    entries: int
    structural_ok: int
    integrity_ok: int
    recomputed_ok: int
    not_recomputable: int
    skipped_recompute: bool
    census: dict[str, int]
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Report whether nothing failed."""
        return not self.failures

    def summary(self) -> list[str]:
        """Human-readable lines, in the order a reader wants them."""
        lines = [
            f"cache          {self.cache_dir}",
            f"entries        {self.entries}",
            f"structural     {self.structural_ok}/{self.entries} recomputed keys match",
            f"integrity      {self.integrity_ok}/{self.entries} digests match INDEX.json",
        ]
        if self.skipped_recompute:
            lines.append("recomputed     SKIPPED (--fast); responses were not re-derived")
        else:
            lines.append(
                f"recomputed     {self.recomputed_ok} re-rendered byte-identical, "
                f"{self.not_recomputable} not recomputable offline (bedrock tier)"
            )
        lines.append(f"census         {self.census}")
        return lines


def _fail(report: VerifyReport, message: str) -> None:
    report.failures.append(message)


def _structural_problem(entry: cache_mod.CacheEntry) -> str | None:
    """Recompute one entry's key and digests.  Returns the first problem, or ``None``.

    Split out from :func:`verify` so that the strength-1 checks read as one list rather than as
    a limb of a long loop: this is the function a reviewer reads to answer "what exactly does
    STRUCTURAL prove?"
    """
    try:
        prompt = prompt_pkg.load(entry.prompt_kind)
        canonical = canonical_prompt(
            prompt,
            node_id=entry.node_id,
            facts=entry.facts,
            prompt_version=entry.prompt_version,
        )
        recomputed_key = cache_key(
            canonical, model_id=entry.model_id, prompt_version=entry.prompt_version
        )
        checks: tuple[tuple[bool, str], ...] = (
            (
                prompt_sha256(canonical) != entry.prompt_sha256,
                (
                    f"prompt_sha256 does not recompute for node {entry.node_id!r}; the facts "
                    "block or the prompt file has changed since the entry was written"
                ),
            ),
            (
                recomputed_key != entry.key,
                (
                    f"recomputed key is {recomputed_key}. The entry does not describe the node "
                    f"it is filed under ({entry.node_id!r})."
                ),
            ),
            (
                entry.model_id != TIER_MODEL_ID.get(entry.renderer),
                (
                    f"renderer {entry.renderer!r} is recorded with model id "
                    f"{entry.model_id!r}, which is not that tier's identity"
                ),
            ),
            (
                cache_mod.response_digest(entry.response) != entry.response_sha256,
                "response_sha256 does not match the response body",
            ),
        )
        for failed, message in checks:
            if failed:
                return message
        validate_response(
            entry.response, prompt.schema, node_id=entry.node_id, renderer=entry.renderer
        )
    except (prompt_pkg.PromptError, SchemaViolation) as exc:
        return str(exc)
    return None


def _check_index_agrees(
    report: VerifyReport,
    *,
    index: Mapping[str, Any],
    on_disk: set[str],
    digests: set[str],
) -> None:
    """Check that the index names exactly the files on disk, under the prompts on disk."""
    for key in sorted(digests - on_disk):
        _fail(report, f"{key}: named by INDEX.json but absent from the cache tree")
    for key in sorted(on_disk - digests):
        _fail(report, f"{key}: present in the cache tree but not named by INDEX.json")

    recorded = dict(index.get("prompt_template_sha256", {}))
    for prompt in prompt_pkg.load_all():
        if recorded.get(prompt.kind) not in (None, prompt.template_sha256):
            _fail(
                report,
                f"prompt {prompt.kind!r}: file on disk digests to "
                f"{prompt.template_sha256[:16]}… but INDEX.json records "
                f"{str(recorded[prompt.kind])[:16]}…. The prompt was edited without rebuilding "
                "the cache; run `corpusgen render` and bump prompt_version.",
            )


def verify(
    *,
    repo_root: Path,
    cache_dir: Path | None = None,
    fast: bool = False,
    max_failures: int = 20,
) -> VerifyReport:
    """Verify the committed cache.  Never opens a socket."""
    repo_root = Path(repo_root).resolve()
    cache_dir = Path(cache_dir) if cache_dir is not None else repo_root / CACHE_RELPATH
    cache = cache_mod.RenderCache(root=cache_dir)
    report = VerifyReport(
        cache_dir=cache_dir,
        entries=0,
        structural_ok=0,
        integrity_ok=0,
        recomputed_ok=0,
        not_recomputable=0,
        skipped_recompute=fast,
        census={},
    )

    with netguard.arm():
        try:
            index = cache.read_index()
        except cache_mod.CacheCorruption as exc:
            _fail(report, str(exc))
            return report

        digests: dict[str, str] = dict(index.get("digests", {}))
        on_disk = {path.stem: path for path in cache.iter_paths()}
        report.entries = len(on_disk)

        _check_index_agrees(report, index=index, on_disk=set(on_disk), digests=set(digests))

        census: dict[str, int] = {}
        entries: list[cache_mod.CacheEntry] = []
        for key, path in sorted(on_disk.items()):
            raw = path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            expected = digests.get(key)
            if expected is None:
                pass  # already reported above
            elif actual != expected:
                _fail(report, f"{key}: bytes digest {actual[:16]}… != INDEX.json {expected[:16]}…")
            else:
                report.integrity_ok += 1

            try:
                entry = cache._parse(path)
            except cache_mod.CacheCorruption as exc:
                _fail(report, str(exc))
                continue
            entries.append(entry)
            census[entry.renderer] = census.get(entry.renderer, 0) + 1

            problem = _structural_problem(entry)
            if problem is None:
                report.structural_ok += 1
            else:
                _fail(report, f"{key}: {problem}")

            if len(report.failures) >= max_failures:
                _fail(report, f"… stopping after {max_failures} failures")
                report.census = census
                return report

        report.census = census

        if fast:
            return report

        _recompute(report, repo_root=repo_root, entries=entries, max_failures=max_failures)

    return report


def _recompute(
    report: VerifyReport,
    *,
    repo_root: Path,
    entries: Sequence[cache_mod.CacheEntry],
    max_failures: int,
) -> None:
    """Re-render every deterministic entry and compare byte for byte."""
    from .template import TemplateRenderer

    by_key = {entry.key: entry for entry in entries}
    if not by_key:
        return
    try:
        world = corpusio.load_world(repo_root=repo_root)
    except corpusio.CorpusUnavailable as exc:
        _fail(report, f"cannot recompute: {exc}")
        return

    authored = AuthoredRenderer(root=repo_root / AUTHORED_RELPATH)
    template = TemplateRenderer()
    renderers: dict[str, Any] = {"authored": authored, "template": template}

    for node in nodes_mod.build_nodes(world):
        prompt = prompt_pkg.load(_prompt_kind(node.kind))
        for tier in ("authored", "template"):
            key = cache_key(
                canonical_prompt(
                    prompt,
                    node_id=node.node_id,
                    facts=node.facts,
                    prompt_version=prompt.version,
                ),
                model_id=TIER_MODEL_ID[tier],
                prompt_version=prompt.version,
            )
            entry = by_key.get(key)
            if entry is None:
                continue
            try:
                response = renderers[tier].render(node, prompt.version)
            except Exception as exc:  # noqa: BLE001 - any refusal is a verification failure
                _fail(report, f"{key}: re-render of {node.node_id} failed: {exc}")
                continue
            # Compared against the digest of the body ACTUALLY on disk, not against the entry's
            # recorded `response_sha256`: an attacker who edited the body would also edit the
            # recorded digest, and a check that trusted it would pass.
            if cache_mod.response_digest(response) != cache_mod.response_digest(entry.response):
                _fail(
                    report,
                    f"{key}: re-rendered response for {node.node_id} does not match the "
                    "committed one. The entry has been edited, or the renderer changed without "
                    "its producer id being bumped.",
                )
                continue
            report.recomputed_ok += 1
            if len(report.failures) >= max_failures:
                _fail(report, f"… stopping after {max_failures} failures")
                return

    report.not_recomputable = sum(1 for entry in entries if entry.renderer == "bedrock")


def _prompt_kind(node_kind: str) -> str:
    from .params import NODE_PROMPT

    return NODE_PROMPT[node_kind]
