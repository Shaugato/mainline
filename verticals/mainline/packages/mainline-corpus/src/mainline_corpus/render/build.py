# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 2 orchestration: render every node, fill the cache, bind every quote.

The order is fixed and each step depends only on what precedes it::

    arm the offline guard        --offline is the default and is ENFORCED
      -> load the world          stage 1 rebuilt in memory + the committed stage-1b trees
      -> build 4324 nodes        clause_text, event_narrative, moc_justification, revision_reason
      -> assign tiers            by policy: camera-facing -> authored, bulk -> template|bedrock
      -> render or hit cache     a bedrock miss under --offline is a hard error, by name
      -> validate                every tier's output, against the prompt's strict schema
      -> write the cache entry   content-addressed, closed shape, no volatile field
      -> assemble canon text     the text offsets are computed against and .docx typesets
      -> bind every quote        exact-and-unique find(); we compute offsets, never trust one
      -> emit the stage-2 tree   the four pending columns, filled, for the loader
      -> prune + write INDEX     stale entries deleted so the census cannot describe dead prose

------------------------------------------------------------------------------------------
Why the cache holds every tier and not only ``bedrock``
------------------------------------------------------------------------------------------
A cache that stored only model output would today be **empty**, ``--verify`` would pass
vacuously, and ``corpus-freeze-load`` would have nothing to fold into ``MANIFEST.sha256``.  The
cache is stage 2's *output*, content-addressed: one entry per rendered node, whichever tier
produced it, carrying the renderer that did.  That is what makes ``corpus.lock.json``'s
renderer census a fact about the corpus rather than a number somebody typed, and it is what
makes the honesty card unable to lie about how much of this prose a model wrote.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import prompts as prompt_pkg
from ..skeleton.emit import Emitter, TableSpec
from . import cache as cache_mod
from . import corpusio, netguard, spans
from . import nodes as nodes_mod
from .authored import AUTHORED_RELPATH, AuthoredRenderer
from .bedrock import BedrockRenderer
from .canonical import cache_key, canonical_prompt, prompt_sha256
from .params import (
    CACHE_RELPATH,
    CAMERA_OWNER,
    DEFAULT_POLICY,
    GENERATOR,
    NODE_KINDS,
    NODE_PROMPT,
    TIER_MODEL_ID,
    TIERS,
    camera_owner_hint,
    tier_for,
)
from .protocol import MissingAuthored, RenderNode, RenderRefusal
from .validate import validate_response

__all__ = ["RenderResult", "generate"]

_LICENCE_TEXT = (
    "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: FSL-1.1-ALv2\n"
)


@dataclass(slots=True)
class RenderResult:
    """What the caller gets back."""

    out_dir: Path
    cache_dir: Path
    nodes: int
    census: dict[str, int]
    hits: int
    misses: int
    deferred: list[dict[str, Any]]
    pruned: list[str]
    counts: dict[str, int]
    file_digests: dict[str, str]
    spans_bound: int
    quotes_bound: int
    index_sha256: str


@dataclass(slots=True)
class _Rendered:
    node: RenderNode
    key: str
    renderer: str
    response: Mapping[str, Any]
    canon: str
    from_cache: bool
    source: str | None = None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class _Pipeline:
    repo_root: Path
    cache_dir: Path
    policy: str
    camera: str
    allow_live: bool
    prompts: dict[str, Any] = field(default_factory=dict)
    deferred: list[dict[str, Any]] = field(default_factory=list)
    hits: int = 0
    misses: int = 0

    def __post_init__(self) -> None:
        self.prompts = {kind: prompt_pkg.load(NODE_PROMPT[kind]) for kind in NODE_KINDS}

    def render_one(
        self,
        node: RenderNode,
        *,
        cache: cache_mod.RenderCache,
        authored: AuthoredRenderer,
        template: Any,
        bedrock: BedrockRenderer,
    ) -> _Rendered | None:
        """Render or fetch one node.  ``None`` means the node was deferred."""
        prompt = self.prompts[node.kind]
        tier = tier_for(policy=self.policy, camera_facing=node.camera_facing)

        if tier == "authored" and not authored.has(node):
            if self.camera == "require":
                raise MissingAuthored(camera_owner_hint(node.node_id))
            self.deferred.append(
                {
                    "node_id": node.node_id,
                    "owner": CAMERA_OWNER,
                    "reason": (
                        "camera-facing; no fixture in "
                        f"{AUTHORED_RELPATH}. Deferred rather than machine-paraphrased: an "
                        "absent entry is honest, a wrong committed one is not."
                    ),
                }
            )
            return None

        model_id = TIER_MODEL_ID[tier]
        canonical = canonical_prompt(
            prompt, node_id=node.node_id, facts=node.facts, prompt_version=prompt.version
        )
        key = cache_key(canonical, model_id=model_id, prompt_version=prompt.version)

        if cache.has(key):
            entry = cache.load(key)
            if entry.node_id != node.node_id:
                raise RenderRefusal(
                    f"cache entry {key} claims node {entry.node_id!r} but was derived for "
                    f"{node.node_id!r}; the key is not a function of the node"
                )
            self.hits += 1
            validate_response(
                entry.response, prompt.schema, node_id=node.node_id, renderer=entry.renderer
            )
            return _Rendered(
                node=node,
                key=key,
                renderer=entry.renderer,
                response=entry.response,
                canon=spans.canon_text(node.kind, entry.response),
                from_cache=True,
                source=entry.source,
            )

        if tier == "bedrock" and not self.allow_live:
            raise RenderRefusal(
                f"cache miss under --offline.\n"
                f"  node: {node.node_id}\n"
                f"  key:  {key}\n"
                f"  path: {cache_mod.entry_path(self.cache_dir, key)}\n"
                "This node is assigned the bedrock tier by the "
                f"{self.policy!r} policy and its response is not in the committed cache. "
                "Offline is the default because AWS credentials are not valid on this machine; "
                "either commit the entry, switch to --policy=offline, or pass --allow-live and "
                "accept that the corpus then depends on a live model call."
            )

        renderer = {"authored": authored, "bedrock": bedrock, "template": template}[tier]
        response = renderer.render(node, prompt.version)
        validate_response(response, prompt.schema, node_id=node.node_id, renderer=tier)
        source: str | None = None
        if tier == "authored":
            fixture = authored.fixtures[node.node_id]
            source = fixture.path.relative_to(self.repo_root).as_posix()
        self.misses += 1
        entry = cache_mod.build_entry(
            key=key,
            node_id=node.node_id,
            prompt_kind=prompt.kind,
            prompt_version=prompt.version,
            prompt_sha256=prompt_sha256(canonical),
            prompt_template_sha256=prompt.template_sha256,
            model_id=model_id,
            renderer=tier,
            facts=node.facts,
            response=response,
            source=source,
        )
        cache.put(entry)
        return _Rendered(
            node=node,
            key=key,
            renderer=tier,
            response=response,
            canon=spans.canon_text(node.kind, response),
            from_cache=False,
            source=source,
        )


# ── the stage-2 tree ────────────────────────────────────────────────────────────────────

_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        filename="event_narrative.jsonl",
        table="mainline.event",
        sort_key=lambda row: (row["event_ref"],),
        description="mainline.event.narrative: the ICAM body, and the text every span indexes",
    ),
    TableSpec(
        filename="control_failure_evidence.jsonl",
        table="mainline.control_failure",
        sort_key=lambda row: (row["event_ref"], row["control_class"]),
        description="mainline.control_failure.evidence_span + quote_sha256, bound exact-and-unique",
    ),
    TableSpec(
        filename="clause_version_text.jsonl",
        table="mainline.clause_version",
        sort_key=lambda row: (row["revision_key"], row["clause_key"]),
        description="mainline.clause_version.canon_text, one row per clause revision",
    ),
    TableSpec(
        filename="moc_justification.jsonl",
        table=None,
        sort_key=lambda row: (row["moc_ref"],),
        description="corpus scaffolding: the MOC dossier body corpus-docx typesets into MOC-*.docx",
    ),
    TableSpec(
        filename="doc_revision_canon.jsonl",
        table=None,
        sort_key=lambda row: (row["revision_key"],),
        description=(
            "corpus scaffolding: the revision-history reason cell and its citation lines, "
            "assembled; blame-edge spans index into this text"
        ),
    ),
    TableSpec(
        filename="blame_edge_evidence.jsonl",
        table="mainline.blame_edge",
        sort_key=lambda row: (row["quote_ref"],),
        description="mainline.blame_edge.evidence_quote_sha256, digested from the bound line",
    ),
)


_Payloads = dict[str, list[dict[str, Any]]]


def _common(item: _Rendered) -> dict[str, Any]:
    """Return the three provenance fields every emitted row carries."""
    return {
        "cache_key": item.key,
        "canon_sha256": _sha256_text(item.canon),
        "renderer": item.renderer,
    }


def _emit_event(item: _Rendered, payloads: _Payloads) -> int:
    """Emit one narrative and bind one evidence span per control failure.  Returns the count."""
    node, canon = item.node, item.canon
    severity_span = spans.bind(
        canon, str(item.response["consequence"]), origin=f"{node.node_id}/consequence"
    )
    payloads["event_narrative.jsonl"].append(
        {
            **_common(item),
            "canon_text": canon,
            "canon_version": 1,
            "event_id": node.context["event_id"],
            "event_ref": node.key,
            "severity_span": list(severity_span),
            "word_count": len(canon.split()),
        }
    )
    failures = {str(row["control_class"]): row for row in node.context["control_failures"]}
    named: set[str] = set()
    for defence in item.response["defences"]:
        control_class = str(defence["control_class"])
        named.add(control_class)
        failure = failures.get(control_class)
        if failure is None:
            raise RenderRefusal(
                f"{node.node_id}: the render names control class {control_class!r}, which this "
                "event does not have. Evidence bound to a control failure that does not exist "
                "is worse than no evidence."
            )
        quote = str(defence["finding"])
        start, end = spans.bind(canon, quote, origin=f"{node.node_id}/{control_class}")
        payloads["control_failure_evidence.jsonl"].append(
            {
                "control_class": control_class,
                "evidence_span": [start, end],
                "event_id": node.context["event_id"],
                "event_ref": node.key,
                "failure_id": str(failure["failure_id"]),
                "quote": quote,
                "quote_sha256": spans.quote_sha256(quote),
            }
        )
    missing = sorted(set(failures) - named)
    if missing:
        raise RenderRefusal(
            f"{node.node_id}: control failures {missing} have no finding sentence. "
            "mainline.control_failure.evidence_span is NOT NULL; a row with no evidence cannot "
            "be loaded, so this is a build error and not a warning."
        )
    return len(named)


def _emit_clause(item: _Rendered, payloads: _Payloads) -> int:
    payloads["clause_version_text.jsonl"].append(
        {
            **_common(item),
            "canon_text": item.canon,
            "canon_version": 1,
            "clause_key": item.node.context["clause_key"],
            "clause_uuid": item.node.context["clause_uuid"],
            "obligation_verb": str(item.response["obligation_verb"]),
            "ordinal": item.node.context["ordinal"],
            "printed_label": item.node.context["printed_label"],
            "revision_key": item.node.context["revision_key"],
        }
    )
    return 0


def _emit_moc(item: _Rendered, payloads: _Payloads) -> int:
    payloads["moc_justification.jsonl"].append(
        {
            **_common(item),
            "canon_text": item.canon,
            "cr_id": item.node.context["cr_id"],
            "moc_ref": item.node.key,
        }
    )
    return 0


def _emit_revision(item: _Rendered, payloads: _Payloads) -> int:
    """Emit one revision block and digest the citation line each quote_ref points at."""
    node, canon = item.node, item.canon
    payloads["doc_revision_canon.jsonl"].append(
        {
            **_common(item),
            "canon_text": canon,
            "doc_id": node.context["doc_id"],
            "reason": str(item.response["reason"]),
            "revision_key": node.key,
        }
    )
    for citation in item.response["citations"]:
        quote = str(citation["line"])
        start, end = spans.bind(canon, quote, origin=f"{node.node_id}/{citation['quote_ref']}")
        payloads["blame_edge_evidence.jsonl"].append(
            {
                "evidence_anchor": f"doc_revision_canon:{node.key}",
                "evidence_quote_sha256": spans.quote_sha256(quote),
                "evidence_span": [start, end],
                "quote": quote,
                "quote_ref": str(citation["quote_ref"]),
                "revision_key": node.key,
            }
        )
    return 0


_EMITTERS: dict[str, Any] = {
    "clause_text": _emit_clause,
    "event_narrative": _emit_event,
    "moc_justification": _emit_moc,
    "revision_reason": _emit_revision,
}


def _emit_tree(
    out_dir: Path,
    *,
    repo_root: Path,
    rendered: Sequence[_Rendered],
    world: corpusio.World,
    policy: str,
    census: Mapping[str, int],
    deferred: Sequence[Mapping[str, Any]],
    only: Sequence[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str], int, int]:
    """Assemble every emitted row, binding spans as it goes."""
    payloads: dict[str, list[dict[str, Any]]] = {spec.filename: [] for spec in _SPECS}
    spans_bound = 0
    quotes_bound = 0

    for item in rendered:
        emitter_fn = _EMITTERS.get(item.node.kind)
        if emitter_fn is None:  # pragma: no cover - NODE_KINDS is closed
            raise RenderRefusal(f"no emission rule for node kind {item.node.kind!r}")
        spans_bound += emitter_fn(item, payloads)
        if item.node.kind == "revision_reason":
            quotes_bound += len(item.response["citations"])

    # Every quote_ref the answer key declared must have been satisfied. A blame edge whose
    # basis is `asserted_document` carries a NOT NULL check on evidence_quote_sha256, so an
    # unsatisfied ref is a row the loader cannot write.
    #
    # Skipped under `--only`, and only there: a partial render deliberately leaves nodes
    # unrendered, so the check would report the filter rather than a defect. The stage-2
    # `index.json` records `partial: true` so that nothing downstream mistakes such a tree for
    # a complete one.
    check_quote_refs = not only
    declared = {
        str(record["quote_ref"])
        for records in world.quote_refs_by_revision.values()
        for record in records
    }
    satisfied = {row["quote_ref"] for row in payloads["blame_edge_evidence.jsonl"]}
    deferred_revisions = {
        str(item["node_id"]).split(":", 1)[1]
        for item in deferred
        if str(item["node_id"]).startswith("revision_reason:")
    }
    unsatisfied = sorted(
        ref
        for ref in declared - satisfied
        if ref.split(":", 1)[1].split("#", 1)[0] not in deferred_revisions
    )
    if unsatisfied and check_quote_refs:
        raise RenderRefusal(
            f"{len(unsatisfied)} quote ref(s) declared by the answer key were never bound, "
            f"e.g. {unsatisfied[:3]}. mainline.blame_edge CHECKs that an asserted_document edge "
            "carries evidence_quote_sha256; an unbound ref is a row that cannot be loaded."
        )

    emitter = Emitter(out_dir=out_dir, repo_root=repo_root)
    digests: dict[str, str] = {}
    counts: dict[str, int] = {}
    for spec in _SPECS:
        record = emitter.write(spec, payloads[spec.filename])
        digests[spec.filename] = record.sha256
        counts[spec.filename.removesuffix(".jsonl")] = record.rows
        (out_dir / f"{spec.filename}.license").write_text(_LICENCE_TEXT, encoding="utf-8")

    index_record = emitter.write_index(
        {
            "cache_relpath": CACHE_RELPATH,
            "counts": dict(sorted(counts.items())),
            "deferred": [dict(item) for item in deferred],
            "generator": GENERATOR,
            "nodes": len(rendered),
            "only": list(only),
            "partial": bool(only),
            "policy": policy,
            "prompt_versions": prompt_pkg.prompt_versions(),
            "renderer_census": dict(census),
            "span_convention": spans.SPAN_CONVENTION,
            "span_sql": spans.SPAN_SQL,
            "stage": "render",
        }
    )
    (out_dir / "index.json.license").write_text(_LICENCE_TEXT, encoding="utf-8")
    digests["index.json"] = index_record.sha256
    return payloads, dict(sorted(digests.items())), spans_bound, quotes_bound


def generate(
    out_dir: Path,
    *,
    repo_root: Path,
    cache_dir: Path | None = None,
    policy: str = DEFAULT_POLICY,
    camera: str = "require",
    allow_live: bool = False,
    only: Sequence[str] = (),
    prune: bool = True,
) -> RenderResult:
    """Render the corpus and write the cache and the stage-2 tree."""
    repo_root = Path(repo_root).resolve()
    out_dir = Path(out_dir)
    cache_dir = Path(cache_dir) if cache_dir is not None else repo_root / CACHE_RELPATH
    only = tuple(only)
    for kind in only:
        if kind not in NODE_KINDS:
            raise ValueError(f"unknown node kind {kind!r}; known: {list(NODE_KINDS)}")

    guard = netguard.arm() if not allow_live else _null_context()
    with guard:
        world = corpusio.load_world(repo_root=repo_root)
        all_nodes = nodes_mod.build_nodes(world)
        selected = [node for node in all_nodes if not only or node.kind in only]

        cache = cache_mod.RenderCache(root=cache_dir)
        pipeline = _Pipeline(
            repo_root=repo_root,
            cache_dir=cache_dir,
            policy=policy,
            camera=camera,
            allow_live=allow_live,
        )
        authored = AuthoredRenderer(root=repo_root / AUTHORED_RELPATH)
        from .template import TemplateRenderer

        template = TemplateRenderer()
        bedrock = BedrockRenderer(prompts=pipeline.prompts, allow_live=allow_live)

        rendered: list[_Rendered] = []
        for node in selected:
            item = pipeline.render_one(
                node, cache=cache, authored=authored, template=template, bedrock=bedrock
            )
            if item is not None:
                rendered.append(item)

        census = dict.fromkeys(TIERS, 0)
        for item in rendered:
            census[item.renderer] += 1

        payloads, file_digests, spans_bound, quotes_bound = _emit_tree(
            out_dir,
            repo_root=repo_root,
            rendered=rendered,
            world=world,
            policy=policy,
            census=census,
            deferred=pipeline.deferred,
            only=only,
        )

        pruned: list[str] = []
        if prune and not only:
            pruned = cache.prune({item.key for item in rendered})
        index = cache.write_index(
            prompt_versions=prompt_pkg.prompt_versions(),
            prompt_template_sha256={
                prompt.kind: prompt.template_sha256 for prompt in prompt_pkg.load_all()
            },
            policy=policy,
            deferred=pipeline.deferred,
            extra={
                "camera_facing_nodes": sum(1 for node in all_nodes if node.camera_facing),
                "node_kinds": dict(
                    sorted(
                        (kind, sum(1 for node in all_nodes if node.kind == kind))
                        for kind in NODE_KINDS
                    )
                ),
                "span_convention": spans.SPAN_CONVENTION,
            },
        )
        _write_cache_readme(cache_dir)
        index_bytes = (cache_dir / "INDEX.json").read_bytes()

    counts = {spec.filename.removesuffix(".jsonl"): len(payloads[spec.filename]) for spec in _SPECS}
    counts["cache_entries"] = int(index["count"])
    return RenderResult(
        out_dir=out_dir,
        cache_dir=cache_dir,
        nodes=len(rendered),
        census=census,
        hits=pipeline.hits,
        misses=pipeline.misses,
        deferred=pipeline.deferred,
        pruned=pruned,
        counts=dict(sorted(counts.items())),
        file_digests=file_digests,
        spans_bound=spans_bound,
        quotes_bound=quotes_bound,
        index_sha256=hashlib.sha256(index_bytes).hexdigest(),
    )


class _null_context:  # noqa: N801 - reads as a context manager at the call site
    """A no-op ``with`` block, used when ``--allow-live`` disarms the guard."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> None:
        return None


_CACHE_README = """<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The committed render cache

Generated by `corpusgen render`. **Do not hand-edit.** Every file here is
`sha256(canonical_prompt ‖ model_id ‖ prompt_version).json`, filed under the first two
characters of its key, and `corpusgen render --verify` recomputes each one.

* `INDEX.json` — the digest of every entry, the renderer census, the prompt versions and
  template digests, and the list of nodes deferred to `corpus-spine-authored`.
* `<xx>/<key>.json` — one rendered node. The shape is closed: see
  `mainline_corpus.render.cache.ENTRY_KEYS`.

The cache is committed so that a judge with no AWS account rebuilds the corpus from it, and so
that CI reproduces `MANIFEST.sha256` with zero Bedrock calls. It is tamper-**evident**, not
tamper-proof: `INDEX.json`'s digests are folded into `MANIFEST.sha256` by `corpus-freeze-load`.

`REUSE.toml` carries the licence for the whole tree rather than a `.license` sidecar per entry,
because there are thousands of entries and eight thousand files would be a worse artefact than
one declaration.
"""

_CACHE_REUSE_TOML = """# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
version = 1

[[annotations]]
path = "**"
precedence = "aggregate"
SPDX-FileCopyrightText = "2026 MAINLINE contributors"
SPDX-License-Identifier = "FSL-1.1-ALv2"
"""


def _write_cache_readme(cache_dir: Path) -> None:
    """Keep the cache tree self-describing and REUSE-clean without 8000 sidecar files."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    for name, text in (("README.md", _CACHE_README), ("REUSE.toml", _CACHE_REUSE_TOML)):
        with (cache_dir / name).open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
