# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The cassette provider — the default everywhere, and the only provider CI has.

``MAINLINE_AGENT_PROVIDER`` defaults to ``cassette``. Everything in this repository
that reasons runs, in CI and on a stranger's laptop, against recorded interactions
with **no AWS account and no network**. That is not a convenience; PL-1 says every
milestone's proof must run on a machine with no credential of ours, and a proof that
needs a model endpoint is not that.

**Key.** ``sha256(profile_id ‖ 0x1f ‖ prompt_version ‖ 0x1f ‖ jcs(input))``. The unit
separator is a deviation from the plan's bare concatenation and it is deliberate:
without a separator, ``("triage", "v11")`` and ``("triagev1", "1")`` collide, and a
cassette collision is a test that silently asserts the wrong thing.

**The key excludes the per-request sentinel.** Layer 2 of the injection posture puts a
fresh random sentinel in every user turn; including it would make every key unique and
every replay a miss. The sentinel is a delimiting control, not part of the input's
identity.

**A miss is fatal.** Replay never falls through to a live call. A provider that quietly
reached the network on a miss would make every green run a claim about a call that may
never have been recorded.

**Prefix drift is fatal.** Each interaction records the digest of the frozen system
prefix it was recorded against, and replay refuses a mismatch. AR-7 accepts that
cassettes can drift from live behaviour; it does not accept a cassette replaying under
a rubric that has since been edited, because decision A13 makes a prompt edit a commit.

**Provenance is stated, never implied.** Every interaction carries a ``provenance``
field. The cassettes committed with this package are ``synthetic`` — hand-built
responses that exercise the code paths — because AWS credentials are not valid on the
build machine as of 2026-08-07. When the live lane records real interactions they are
written with ``provenance: "live"`` and the field is what tells the two apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._canon import canonical_json_bytes, sha256_hex
from .errors import CassetteMiss, CassettePrefixDrift, TransportUnavailable
from .transport import ModelRequest, ModelResponse

if TYPE_CHECKING:
    import threading
    from collections.abc import Mapping

__all__ = [
    "PROVENANCE_LIVE",
    "PROVENANCE_SYNTHETIC",
    "CassetteStore",
    "CassetteTransport",
    "Interaction",
    "cassette_key",
]

PROVENANCE_SYNTHETIC = "synthetic"
PROVENANCE_LIVE = "live"
_MODES = frozenset({"replay", "record"})


def cassette_key(profile_id: str, prompt_version: str, call_input: Any) -> str:
    """Compute the committed cassette key for one call.

    ``call_input`` must be JCS-canonicalisable: objects, arrays, strings, integers,
    booleans, null. Floats are refused by :mod:`mainline_agentkit._canon` because a key
    whose bytes depend on IEEE-754 formatting is not a stable key.
    """
    return sha256_hex(
        profile_id.encode("utf-8"),
        prompt_version.encode("utf-8"),
        canonical_json_bytes(call_input),
    )


@dataclass(frozen=True, slots=True)
class Interaction:
    """One recorded request/response pair."""

    key: str
    profile_id: str
    prompt_version: str
    prefix_digest: str
    model_id: str
    provenance: str
    response: Mapping[str, Any]
    recorded_at: str

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> Interaction:
        """Parse a cassette file body."""
        missing = [
            name
            for name in (
                "key",
                "profile_id",
                "prompt_version",
                "prefix_digest",
                "model_id",
                "provenance",
                "response",
            )
            if name not in payload
        ]
        if missing:
            raise TransportUnavailable(f"cassette is missing required fields: {missing}")
        return cls(
            key=str(payload["key"]),
            profile_id=str(payload["profile_id"]),
            prompt_version=str(payload["prompt_version"]),
            prefix_digest=str(payload["prefix_digest"]),
            model_id=str(payload["model_id"]),
            provenance=str(payload["provenance"]),
            response=dict(payload["response"]),
            recorded_at=str(payload.get("recorded_at", "")),
        )

    def to_json(self) -> dict[str, Any]:
        """Render the exact on-disk shape."""
        return {
            "key": self.key,
            "profile_id": self.profile_id,
            "prompt_version": self.prompt_version,
            "prefix_digest": self.prefix_digest,
            "model_id": self.model_id,
            "provenance": self.provenance,
            "recorded_at": self.recorded_at,
            "response": dict(self.response),
        }


class CassetteStore:
    """A directory of ``<key>.json`` interactions."""

    def __init__(self, root: Path | str, *, mode: str = "replay") -> None:
        """Bind a directory and a mode.

        Raises:
            TransportUnavailable: on an unknown mode, or when replaying a directory
                that does not exist — an empty store would otherwise present as "every
                key missing", which reads as a code bug rather than a setup one.
        """
        if mode not in _MODES:
            raise TransportUnavailable(f"unknown cassette mode {mode!r}; use {sorted(_MODES)}")
        self.root = Path(root)
        self.mode = mode
        if mode == "replay" and not self.root.is_dir():
            raise TransportUnavailable(
                f"cassette store {self.root} does not exist; record it with "
                f"tests/make_cassettes.py before replaying"
            )
        if mode == "record":
            self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        """Where the interaction for ``key`` lives."""
        return self.root / f"{key}.json"

    def get(self, key: str) -> Interaction:
        """Load one interaction.

        Raises:
            CassetteMiss: when it is not on disk. Replay never falls through.
        """
        path = self.path_for(key)
        if not path.is_file():
            raise CassetteMiss(key, str(self.root))
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TransportUnavailable(f"cassette {path} is not a JSON object")
        return Interaction.from_json(payload)

    def put(self, interaction: Interaction) -> Path:
        """Write one interaction and return its path."""
        if self.mode != "record":
            raise TransportUnavailable("cassette store is in replay mode; refusing to write")
        path = self.path_for(interaction.key)
        path.write_text(
            json.dumps(interaction.to_json(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def record(
        self,
        request: ModelRequest,
        response_body: Mapping[str, Any],
        *,
        provenance: str = PROVENANCE_SYNTHETIC,
    ) -> Path:
        """Record a response body against the identity carried by ``request``."""
        return self.put(
            Interaction(
                key=request.cassette_key,
                profile_id=request.profile_id,
                prompt_version=request.prompt_version,
                prefix_digest=request.prefix_digest,
                model_id=request.model_id,
                provenance=provenance,
                response=dict(response_body),
                recorded_at=datetime.now(tz=UTC).isoformat(),
            )
        )

    def keys(self) -> list[str]:
        """Every key in the store, sorted."""
        return sorted(path.stem for path in self.root.glob("*.json"))


class CassetteTransport:
    """A :class:`mainline_agentkit.transport.Transport` backed by a store.

    Satisfies the protocol exactly, including :meth:`warm` — which sets the first-token
    event immediately, because a recorded interaction's prefix is by definition already
    processed. The cold-fan-out refusal is therefore still exercised in CI: it fires
    when ``warm`` was never called, not when the network was slow.
    """

    def __init__(self, store: CassetteStore) -> None:
        """Bind a store."""
        self.store = store
        self.calls: list[ModelRequest] = []

    def _load(self, request: ModelRequest) -> ModelResponse:
        interaction = self.store.get(request.cassette_key)
        if interaction.prefix_digest != request.prefix_digest:
            raise CassettePrefixDrift(
                request.cassette_key, interaction.prefix_digest, request.prefix_digest
            )
        self.calls.append(request)
        return ModelResponse.from_body(interaction.response)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Replay the interaction recorded for this request."""
        return self._load(request)

    def warm(self, request: ModelRequest, *, first_token: threading.Event) -> ModelResponse:
        """Replay the warming call, releasing the fan-out immediately."""
        try:
            response = self._load(request)
        finally:
            # Set even on a miss: leaving the event clear would turn a CassetteMiss on
            # the warming call into a WarmTimeout in the caller, hiding the real cause.
            first_token.set()
        return response
