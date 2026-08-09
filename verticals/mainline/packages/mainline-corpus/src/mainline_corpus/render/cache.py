# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The committed, content-addressed render cache.

``fixtures/corpus/cache/<first2>/<key>.json``, one file per rendered node, plus an
``INDEX.json`` at the root.  The cache is **committed**, which is the whole point: a judge with
no AWS account and no model access rebuilds the corpus from it, and CI reproduces
``MANIFEST.sha256`` from it with zero Bedrock calls.

------------------------------------------------------------------------------------------
The entry shape is CLOSED
------------------------------------------------------------------------------------------
Exactly the keys in :data:`ENTRY_KEYS`, always, in every entry.  Not a convention — the writer
refuses an unexpected key and the reader refuses a missing one.  A cache whose entries grew an
optional field would have two shapes, and "reproduce the tree byte for byte" would then depend
on which shape the producer happened to be on.

**No entry contains a timestamp, a wall clock, a random value, a hostname, a path, a duration,
a token count or a request id.**  Every one of those is a thing a naive cache records and every
one of them makes two runs differ.  :func:`build_entry` constructs the object field by field
from arguments, so there is no place for an ambient value to enter, and
:func:`_refuse_volatile` re-checks the serialised body against a list of names that would
indicate one crept in anyway.

------------------------------------------------------------------------------------------
What ``--verify`` can and cannot prove
------------------------------------------------------------------------------------------
Verification has three strengths and the difference between them is stated rather than blurred:

1. **Structural** — the key on the filename recomputes from the entry's own
   ``facts`` + ``model_id`` + ``prompt_version`` against the prompt file on disk, and
   ``prompt_sha256`` recomputes from the same. This catches an edited fact block, a swapped
   model id, a renamed file, and a prompt edited without rebuilding.
2. **Integrity** — every entry's bytes match the digest ``INDEX.json`` records, and the set of
   files on disk equals the set the index names. This catches an edited *response*, provided
   the index was not edited to match.
3. **Recomputed** — for the two deterministic tiers, the node is re-rendered from the corpus
   and compared byte for byte. This catches an edited response outright, index or no index.

A ``bedrock`` entry can only reach strength 2, because its response is not recomputable without
the model.  That is a real limit and it is why ``INDEX.json``'s digests are folded into
``MANIFEST.sha256`` by ``corpus-freeze-load``: the cache is tamper-**evident**, not
tamper-proof, and this file does not pretend otherwise.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..skeleton.emit import canonical_json
from .params import CACHE_VERSION, GENERATOR, TIERS

__all__ = [
    "ENTRY_KEYS",
    "CacheCorruption",
    "CacheEntry",
    "CacheMiss",
    "RenderCache",
    "entry_path",
]

#: The closed key set of a cache entry.
ENTRY_KEYS: Final[tuple[str, ...]] = (
    "cache_version",
    "facts",
    "key",
    "model_id",
    "node_id",
    "prompt_kind",
    "prompt_sha256",
    "prompt_template_sha256",
    "prompt_version",
    "renderer",
    "response",
    "response_sha256",
    "source",
)

#: Substrings that must never appear as a key anywhere inside an entry.  A belt-and-braces
#: check on top of the closed key set, because ``facts`` and ``response`` are nested free-form
#: objects and this is where an ambient value would hide.
_VOLATILE_NAME_PARTS: Final[tuple[str, ...]] = (
    "timestamp",
    "generated_at",
    "rendered_at",
    "created_at",
    "requested_at",
    "request_id",
    "latency",
    "elapsed",
    "duration_ms",
    "hostname",
    "cwd",
    "tmpdir",
    "usage",
    "run_id",
)

#: A key is a hex sha256; the first two characters name its bucket directory.
_KEY_LENGTH: Final[int] = 64
_BUCKET_LENGTH: Final[int] = 2

#: JSON that is stable to write and pleasant to read in a diff.  ``indent=2`` costs bytes and
#: buys a reviewable cache: a corrupted entry is meant to be *seen*, and a one-line blob is not.
_JSON_KWARGS: Final[dict[str, Any]] = {"sort_keys": True, "ensure_ascii": False, "indent": 2}

_LICENCE_HEADER: Final[str] = (
    "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: FSL-1.1-ALv2\n"
)


class CacheMiss(KeyError):
    """The cache has no entry for this key."""


class CacheCorruption(RuntimeError):
    """A cache entry is not what it claims to be."""


def _refuse_volatile(node: Any, *, path: str) -> None:
    """Raise if any key anywhere in ``node`` looks like an ambient value."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            lowered = str(key).lower()
            for part in _VOLATILE_NAME_PARTS:
                if part in lowered:
                    raise CacheCorruption(
                        f"{path}.{key}: field name contains {part!r}. Nothing in a cache entry "
                        "may vary between two runs of the same input; a cache that recorded "
                        "when it was built could never reproduce byte for byte."
                    )
            _refuse_volatile(value, path=f"{path}.{key}")
    elif isinstance(node, list):
        for position, item in enumerate(node):
            _refuse_volatile(item, path=f"{path}[{position}]")


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """One rendered node, as committed."""

    key: str
    node_id: str
    prompt_kind: str
    prompt_version: str
    prompt_sha256: str
    prompt_template_sha256: str
    model_id: str
    renderer: str
    facts: Mapping[str, Any]
    response: Mapping[str, Any]
    response_sha256: str
    source: str | None

    def to_json_object(self) -> dict[str, Any]:
        """Return the exact object written to disk."""
        return {
            "cache_version": CACHE_VERSION,
            "facts": dict(self.facts),
            "key": self.key,
            "model_id": self.model_id,
            "node_id": self.node_id,
            "prompt_kind": self.prompt_kind,
            "prompt_sha256": self.prompt_sha256,
            "prompt_template_sha256": self.prompt_template_sha256,
            "prompt_version": self.prompt_version,
            "renderer": self.renderer,
            "response": dict(self.response),
            "response_sha256": self.response_sha256,
            "source": self.source,
        }

    @classmethod
    def from_json_object(cls, body: Mapping[str, Any], *, origin: str) -> CacheEntry:
        """Parse an entry, refusing any shape but the closed one."""
        unknown = sorted(set(body) - set(ENTRY_KEYS))
        missing = sorted(set(ENTRY_KEYS) - set(body))
        if unknown or missing:
            raise CacheCorruption(
                f"{origin}: entry shape is not the closed shape "
                f"(unknown={unknown}, missing={missing})"
            )
        if body["cache_version"] != CACHE_VERSION:
            raise CacheCorruption(
                f"{origin}: cache_version {body['cache_version']!r} != {CACHE_VERSION}"
            )
        if body["renderer"] not in TIERS:
            raise CacheCorruption(f"{origin}: unknown renderer {body['renderer']!r}")
        _refuse_volatile(body["facts"], path=f"{origin}.facts")
        _refuse_volatile(body["response"], path=f"{origin}.response")
        return cls(
            key=str(body["key"]),
            node_id=str(body["node_id"]),
            prompt_kind=str(body["prompt_kind"]),
            prompt_version=str(body["prompt_version"]),
            prompt_sha256=str(body["prompt_sha256"]),
            prompt_template_sha256=str(body["prompt_template_sha256"]),
            model_id=str(body["model_id"]),
            renderer=str(body["renderer"]),
            facts=body["facts"],
            response=body["response"],
            response_sha256=str(body["response_sha256"]),
            source=None if body["source"] is None else str(body["source"]),
        )


def response_digest(response: Mapping[str, Any]) -> str:
    """``sha256`` over the canonically serialised response."""
    return hashlib.sha256(canonical_json(response).encode("utf-8")).hexdigest()


def build_entry(
    *,
    key: str,
    node_id: str,
    prompt_kind: str,
    prompt_version: str,
    prompt_sha256: str,
    prompt_template_sha256: str,
    model_id: str,
    renderer: str,
    facts: Mapping[str, Any],
    response: Mapping[str, Any],
    source: str | None,
) -> CacheEntry:
    """Construct an entry, field by field, from arguments only."""
    _refuse_volatile(facts, path=f"{node_id}.facts")
    _refuse_volatile(response, path=f"{node_id}.response")
    return CacheEntry(
        key=key,
        node_id=node_id,
        prompt_kind=prompt_kind,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha256,
        prompt_template_sha256=prompt_template_sha256,
        model_id=model_id,
        renderer=renderer,
        facts=facts,
        response=response,
        response_sha256=response_digest(response),
        source=source,
    )


def entry_path(root: Path, key: str) -> Path:
    """``<root>/<key[:2]>/<key>.json``."""
    if len(key) != _KEY_LENGTH or any(char not in "0123456789abcdef" for char in key):
        raise ValueError(f"cache key must be {_KEY_LENGTH} lowercase hex characters, got {key!r}")
    return root / key[:_BUCKET_LENGTH] / f"{key}.json"


def _write_text(path: Path, text: str) -> bytes:
    """Write ``text`` with LF endings and return the bytes written."""
    encoded = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return encoded


@dataclass(slots=True)
class RenderCache:
    """Read/write access to one cache tree."""

    root: Path
    _written: dict[str, dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._written = {}

    # ── reading ─────────────────────────────────────────────────────────────────────────

    def has(self, key: str) -> bool:
        """Report whether an entry file exists for ``key``."""
        return entry_path(self.root, key).is_file()

    def load(self, key: str) -> CacheEntry:
        """Return the entry for ``key``, or raise :class:`CacheMiss`."""
        path = entry_path(self.root, key)
        if not path.is_file():
            raise CacheMiss(key)
        return self._parse(path)

    def _parse(self, path: Path) -> CacheEntry:
        raw = path.read_bytes()
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CacheCorruption(f"{path}: not valid UTF-8 JSON ({exc})") from exc
        if not isinstance(body, Mapping):
            raise CacheCorruption(f"{path}: entry must be a JSON object")
        entry = CacheEntry.from_json_object(body, origin=str(path))
        if entry.key != path.stem:
            raise CacheCorruption(
                f"{path}: entry declares key {entry.key!r} but is filed under {path.stem!r}"
            )
        if entry.key[:_BUCKET_LENGTH] != path.parent.name:
            raise CacheCorruption(
                f"{path}: entry key {entry.key!r} does not belong in bucket {path.parent.name!r}"
            )
        return entry

    def iter_paths(self) -> Iterator[Path]:
        """Every entry file on disk, in a stable order."""
        if not self.root.is_dir():
            return
        for bucket in sorted(self.root.iterdir()):
            if not bucket.is_dir() or len(bucket.name) != _BUCKET_LENGTH:
                continue
            yield from sorted(bucket.glob("*.json"))

    def iter_entries(self) -> Iterator[CacheEntry]:
        """Every entry on disk, parsed, in key order."""
        for path in self.iter_paths():
            yield self._parse(path)

    # ── writing ─────────────────────────────────────────────────────────────────────────

    def put(self, entry: CacheEntry) -> int:
        """Write one entry and return the byte count.

        Writing the same key twice with a *different* body is a refusal, not a last-write-wins:
        two nodes that derived one key would mean the key is not a function of the node, and
        the census would be wrong by however many collisions there were.
        """
        body = entry.to_json_object()
        text = json.dumps(body, **_JSON_KWARGS) + "\n"
        previous = self._written.get(entry.key)
        if previous is not None and previous != body:
            raise CacheCorruption(
                f"key collision on {entry.key}: nodes {previous['node_id']!r} and "
                f"{entry.node_id!r} derived the same cache key with different bodies. The key "
                "must be a function of the node; if it is not, the renderer census is wrong."
            )
        self._written[entry.key] = body
        return len(_write_text(entry_path(self.root, entry.key), text))

    def write_index(
        self,
        *,
        prompt_versions: Mapping[str, str],
        prompt_template_sha256: Mapping[str, str],
        policy: str,
        deferred: Sequence[Mapping[str, Any]],
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write ``INDEX.json`` over everything on disk and return it.

        Written last and computed from the *files*, not from what this process believed it
        wrote, so a build that died halfway leaves a tree whose index disagrees with it — which
        ``--verify`` reports — rather than one that looks complete.
        """
        digests: dict[str, str] = {}
        census = dict.fromkeys(TIERS, 0)
        by_prompt: dict[str, int] = {}
        total_bytes = 0
        for path in self.iter_paths():
            raw = path.read_bytes()
            entry = self._parse(path)
            digests[entry.key] = hashlib.sha256(raw).hexdigest()
            census[entry.renderer] += 1
            by_prompt[entry.prompt_kind] = by_prompt.get(entry.prompt_kind, 0) + 1
            total_bytes += len(raw)

        index: dict[str, Any] = {
            "bytes": total_bytes,
            "cache_version": CACHE_VERSION,
            "count": len(digests),
            "counts_by_prompt": dict(sorted(by_prompt.items())),
            "deferred": sorted(
                (dict(item) for item in deferred), key=lambda item: str(item.get("node_id", ""))
            ),
            "digests": dict(sorted(digests.items())),
            "generator": GENERATOR,
            "policy": policy,
            "prompt_template_sha256": dict(sorted(prompt_template_sha256.items())),
            "prompt_versions": dict(sorted(prompt_versions.items())),
            "renderer_census": census,
        }
        if extra:
            for key, value in extra.items():
                if key in index:
                    raise ValueError(f"INDEX.json: {key!r} is already a reserved field")
                index[key] = value
        _refuse_volatile(index, path="INDEX")
        _write_text(self.root / "INDEX.json", json.dumps(index, **_JSON_KWARGS) + "\n")
        _write_text(self.root / "INDEX.json.license", _LICENCE_HEADER)
        return index

    def read_index(self) -> dict[str, Any]:
        """Parse ``INDEX.json``."""
        path = self.root / "INDEX.json"
        if not path.is_file():
            raise CacheCorruption(
                f"{path}: absent. The cache index is what makes the tree checkable; a cache "
                "without one can be verified only against itself."
            )
        body = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(body, Mapping):
            raise CacheCorruption(f"{path}: must be a JSON object")
        return dict(body)

    def prune(self, keep: set[str]) -> list[str]:
        """Delete entries whose key is not in ``keep``; return the deleted keys, sorted.

        A prompt edit re-keys every entry it produced.  Without this the old entries would sit
        in the tree forever, ``INDEX.json`` would count them, and the renderer census on the
        honesty card would describe prose that is no longer in the corpus.
        """
        removed: list[str] = []
        for path in list(self.iter_paths()):
            if path.stem not in keep:
                path.unlink()
                removed.append(path.stem)
        for bucket in sorted(self.root.iterdir()) if self.root.is_dir() else []:
            if bucket.is_dir() and len(bucket.name) == _BUCKET_LENGTH and not any(bucket.iterdir()):
                bucket.rmdir()
        return sorted(removed)
