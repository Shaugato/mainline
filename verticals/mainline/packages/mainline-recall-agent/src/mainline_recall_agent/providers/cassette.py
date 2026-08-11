# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Record/replay cassettes, keyed by ``sha256(JCS(request))``.

Replay is the **default** for CI and the demo (``MAINLINE_RECALL_PROVIDER=cassette``),
because neither AWS credentials nor a network are available on a fresh checkout and the
recall domain must still be runnable end to end.  Recording requires two explicit opt-ins
(``MAINLINE_RECALL_CASSETTE_MODE=record`` **and** ``MAINLINE_RECALL_ALLOW_NETWORK=1``), so
a test run can never quietly start spending money or shipping narratives to a live model.

Every cassette is self-verifying: it stores the canonical request alongside the digest it
claims, and loading recomputes the digest.  A cassette edited to change what the model
"said" fails to load rather than quietly rewriting a fixture that a gate test depends on.

Every cassette also declares its ``provenance``:

``bedrock-live`` / ``local-bge``
    Recorded from a real call.  These are evidence about the model.
``handwritten``
    Authored as a contract fixture.  These are evidence about **our client** — that a
    refusal raises, that the repair path fires exactly once, that the cache breakpoint sits
    on the last system block — and about nothing else.  A test that needs to make a claim
    about the model's behaviour must assert ``provenance != "handwritten"``.

That distinction is the honest core of this file: AWS credentials are not valid on the
build machine, so the judge cassettes committed today are handwritten, and they say so.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from .canonical import canonical_json, request_digest, sha256_hex
from .errors import (
    CassetteMiss,
    CassetteRecordingNotPermitted,
    CassetteTampered,
    ProviderError,
)
from .judge import JudgeTransport, TransportReply
from .types import EMBED_DIM, Vector256, Vector1024
from .vectors import b64_to_vector, vector_to_b64

__all__ = [
    "CASSETTE_SCHEMA",
    "LIVE_PROVENANCE",
    "CassetteJudgeTransport",
    "CassetteStore",
    "RecordingEmbeddingProvider",
    "RecordingJudgeTransport",
    "ReplayEmbeddingProvider",
    "assert_recording_permitted",
    "default_cassette_root",
    "embed_request",
]

CASSETTE_SCHEMA: Final[str] = "mainline.recall.cassette/1"
LIVE_PROVENANCE: Final[frozenset[str]] = frozenset({"bedrock-live", "local-bge"})
_VALID_PROVENANCE: Final[frozenset[str]] = LIVE_PROVENANCE | {"handwritten", "surrogate"}
_RELATIVE_ROOT: Final[tuple[str, ...]] = ("tests", "fixtures", "cassettes", "recall")

#: A cassette filename is the lowercase hex sha256 of its canonical request, nothing else.
_SHA256_HEX_LEN: Final[int] = 64


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def default_cassette_root() -> Path:
    """``tests/fixtures/cassettes/recall``, found by env var or by walking upward."""
    override = os.environ.get("MAINLINE_RECALL_CASSETTE_DIR")
    if override:
        return Path(override).resolve()
    starts = [Path.cwd(), Path(__file__).resolve()]
    for start in starts:
        for parent in [start, *start.parents]:
            candidate = parent.joinpath(*_RELATIVE_ROOT)
            if candidate.is_dir():
                return candidate.resolve()
    raise ProviderError(
        "cannot locate tests/fixtures/cassettes/recall; set MAINLINE_RECALL_CASSETTE_DIR"
    )


def assert_recording_permitted() -> None:
    """Recording is opt-in twice over, and says which switch is missing."""
    mode = (os.environ.get("MAINLINE_RECALL_CASSETTE_MODE") or "replay").strip().lower()
    if mode != "record":
        raise CassetteRecordingNotPermitted(
            "cassette recording requires MAINLINE_RECALL_CASSETTE_MODE=record",
            mode=mode,
        )
    if not _truthy(os.environ.get("MAINLINE_RECALL_ALLOW_NETWORK")):
        raise CassetteRecordingNotPermitted(
            "cassette recording additionally requires MAINLINE_RECALL_ALLOW_NETWORK=1; "
            "recording issues real, billable calls against live safety narratives"
        )


class CassetteStore:
    """A directory of digest-keyed cassettes."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root).resolve() if root is not None else default_cassette_root()

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, kind: str, digest: str) -> Path:
        if kind not in {"judge", "embed"}:
            raise ProviderError("unknown cassette kind", kind=kind)
        if len(digest) != _SHA256_HEX_LEN or any(c not in "0123456789abcdef" for c in digest):
            raise ProviderError("cassette digest must be lowercase sha256 hex", digest=digest)
        return self._root / kind / f"{digest}.json"

    def has(self, kind: str, request: dict[str, Any]) -> bool:
        return self.path_for(kind, request_digest(request)).is_file()

    def load(self, kind: str, request: dict[str, Any]) -> dict[str, Any]:
        digest = request_digest(request)
        path = self.path_for(kind, digest)
        if not path.is_file():
            raise CassetteMiss(
                "no cassette for this request; record one with "
                "MAINLINE_RECALL_CASSETTE_MODE=record MAINLINE_RECALL_ALLOW_NETWORK=1",
                kind=kind,
                digest=digest,
                path=str(path),
            )
        return self._read(path, expected_digest=digest)

    def _read(self, path: Path, *, expected_digest: str | None = None) -> dict[str, Any]:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise CassetteTampered(
                "a cassette must be a JSON object",
                path=str(path),
                json_type=type(loaded).__name__,
            )
        document: dict[str, Any] = loaded
        if document.get("schema") != CASSETTE_SCHEMA:
            raise CassetteTampered(
                "unknown cassette schema", path=str(path), schema=document.get("schema")
            )
        claimed = str(document.get("request_digest", ""))
        recomputed = sha256_hex(canonical_json(document["request"]))
        if claimed != recomputed:
            raise CassetteTampered(
                "cassette request does not hash to its recorded digest; the fixture has "
                "been edited",
                path=str(path),
                claimed=claimed,
                recomputed=recomputed,
            )
        if expected_digest is not None and claimed != expected_digest:
            raise CassetteTampered(
                "cassette digest does not match its filename",
                path=str(path),
                claimed=claimed,
            )
        provenance = str(document.get("provenance", ""))
        if provenance not in _VALID_PROVENANCE:
            raise CassetteTampered(
                "cassette does not declare a known provenance",
                path=str(path),
                provenance=provenance,
            )
        return document

    def save(
        self,
        kind: str,
        request: dict[str, Any],
        response: dict[str, Any],
        *,
        provenance: str,
        note: str = "",
        recorder: str = "mainline-recall-agent",
    ) -> Path:
        if provenance not in _VALID_PROVENANCE:
            raise ProviderError("unknown cassette provenance", provenance=provenance)
        digest = request_digest(request)
        path = self.path_for(kind, digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema": CASSETTE_SCHEMA,
            "kind": kind,
            "request_digest": digest,
            "provenance": provenance,
            "recorder": recorder,
            "recorded_at": self._recorded_at(
                path,
                provenance=provenance,
                recorder=recorder,
                note=note,
                request=request,
                response=response,
            ),
            "note": note,
            "request": request,
            "response": response,
        }
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _recorded_at(
        path: Path,
        *,
        provenance: str,
        recorder: str,
        note: str,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> str:
        """Now, unless re-emitting a byte-identical constructed cassette.

        For ``bedrock-live`` / ``local-bge`` the timestamp is *evidence*: it says when the
        call was actually observed, so a re-record always re-stamps even if the bytes match.

        For ``handwritten`` / ``surrogate`` the cassette is a **construction**, not an
        observation, and the timestamp carries no evidentiary content.  Re-stamping it would
        make every regeneration of the fixture set produce a diff in every file, which is
        how a real change to a fixture — the kind a gate test depends on — becomes invisible
        in review.  So an unchanged construction keeps the timestamp it already had.
        """
        now = datetime.now(UTC).isoformat(timespec="seconds")
        if provenance in LIVE_PROVENANCE or not path.is_file():
            return now
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - unreadable ⇒ rewrite
            return now
        if not isinstance(existing, dict):  # pragma: no cover - malformed ⇒ rewrite
            return now
        unchanged = (
            existing.get("provenance") == provenance
            and existing.get("recorder") == recorder
            and existing.get("note") == note
            and existing.get("request") == request
            and existing.get("response") == response
        )
        previous = existing.get("recorded_at")
        if unchanged and isinstance(previous, str) and previous:
            return previous
        return now

    def iter_documents(self, kind: str | None = None) -> list[dict[str, Any]]:
        kinds = [kind] if kind else ["judge", "embed"]
        out: list[dict[str, Any]] = []
        for one in kinds:
            directory = self._root / one
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                out.append(self._read(path))
        return out


# --------------------------------------------------------------------------------------
# Judge transports
# --------------------------------------------------------------------------------------


class CassetteJudgeTransport:
    """Replay transport.  Implements ``JudgeTransport``."""

    def __init__(self, store: CassetteStore | None = None) -> None:
        self._store = store or CassetteStore()
        self.last_document: dict[str, Any] | None = None

    def send(self, request: dict[str, Any]) -> TransportReply:
        document = self._store.load("judge", request)
        self.last_document = document
        return TransportReply.model_validate(document["response"])


class RecordingJudgeTransport:
    """Wraps a live transport and writes what it saw.  Implements ``JudgeTransport``."""

    def __init__(
        self,
        inner: JudgeTransport,
        store: CassetteStore | None = None,
        *,
        provenance: str = "bedrock-live",
        note: str = "",
    ) -> None:
        assert_recording_permitted()
        self._inner = inner
        self._store = store or CassetteStore()
        self._provenance = provenance
        self._note = note

    def send(self, request: dict[str, Any]) -> TransportReply:
        reply: TransportReply = self._inner.send(request)
        self._store.save(
            "judge",
            request,
            reply.model_dump(mode="json"),
            provenance=self._provenance,
            note=self._note,
        )
        return reply


# --------------------------------------------------------------------------------------
# Embedding replay
# --------------------------------------------------------------------------------------


def embed_request(
    *, embed_model: str, facet: str, text: str, dim: int = EMBED_DIM, side: str = "document"
) -> dict[str, Any]:
    """The canonical embedding request — one cassette per text, not per batch.

    Per text rather than per batch so a cassette is reusable across differently-sized
    batches, which is what makes the fixture corpus survive a caller changing its chunking.
    """
    return {
        "kind": "embed",
        "embed_model": embed_model,
        "facet": facet,
        "dim": dim,
        "side": side,
        "text": text,
    }


class ReplayEmbeddingProvider:
    """Replays recorded vectors for a named embedding space.  Implements ``EmbeddingProvider``.

    ``coarse`` is *not* replayed: it is client-side arithmetic (Matryoshka truncation or the
    committed projection) with no service call in it, so replaying it would only hide a
    regression in our own code.
    """

    def __init__(
        self,
        *,
        model_id: str,
        index_gen: str,
        is_semantic: bool,
        coarse_impl: Any,
        store: CassetteStore | None = None,
        side: str = "document",
    ) -> None:
        self._model_id = model_id
        self._index_gen = index_gen
        self._is_semantic = is_semantic
        self._coarse_impl = coarse_impl
        self._store = store or CassetteStore()
        self._side = side

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def index_gen(self) -> str:
        return self._index_gen

    @property
    def is_semantic(self) -> bool:
        return self._is_semantic

    def embed(self, texts: list[str], facet: str) -> list[Vector1024]:
        from .base import validate_batch

        prepared = validate_batch(texts, facet)
        out: list[Vector1024] = []
        for text in prepared:
            request = embed_request(
                embed_model=self._model_id, facet=facet, text=text, side=self._side
            )
            document = self._store.load("embed", request)
            payload = document["response"]
            out.append(Vector1024(b64_to_vector(str(payload["embedding_b64"]), EMBED_DIM)))
        return out

    def coarse(self, vecs: Sequence[Vector1024]) -> list[Vector256]:
        return [self._coarse_impl(vec) for vec in vecs]


class RecordingEmbeddingProvider:
    """Wraps a live embedder and records one cassette per text.

    Implements ``EmbeddingProvider``.
    """

    def __init__(
        self,
        inner: Any,
        store: CassetteStore | None = None,
        *,
        provenance: str,
        side: str = "document",
        note: str = "",
    ) -> None:
        assert_recording_permitted()
        self._inner = inner
        self._store = store or CassetteStore()
        self._provenance = provenance
        self._side = side
        self._note = note

    @property
    def model_id(self) -> str:
        return str(self._inner.model_id)

    @property
    def index_gen(self) -> str:
        return str(self._inner.index_gen)

    @property
    def is_semantic(self) -> bool:
        return bool(self._inner.is_semantic)

    def embed(self, texts: list[str], facet: str) -> list[Vector1024]:
        from .base import validate_batch

        prepared = validate_batch(texts, facet)
        vectors = self._inner.embed(list(prepared), facet)
        for text, vector in zip(prepared, vectors, strict=True):
            request = embed_request(
                embed_model=self.model_id, facet=facet, text=text, side=self._side
            )
            self._store.save(
                "embed",
                request,
                {"embedding_b64": vector_to_b64(vector), "dim": EMBED_DIM},
                provenance=self._provenance,
                note=self._note,
            )
        return list(vectors)

    def coarse(self, vecs: Sequence[Vector1024]) -> list[Vector256]:
        result: list[Vector256] = self._inner.coarse(vecs)
        return result
