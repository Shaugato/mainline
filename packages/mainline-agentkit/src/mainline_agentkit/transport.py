# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The wire: ``bedrock-runtime`` ``InvokeModel``, the Anthropic native body, ``au.*`` only.

Decision A3 pins the transport and names both rejected alternatives.

* **Not ``AnthropicBedrockMantle``.** The residency control is a VPC-endpoint policy on
  the ``bedrock-runtime`` endpoint enumerating ``au.*`` inference-profile ARNs
  (§10.1). The Mantle client terminates on ``bedrock-mantle.{region}.api.aws`` — a
  different endpoint whose policy surface is unverified. A residency claim that rests
  on an unverified endpoint policy is a claim we lose in the room.
* **Not ``Converse``.** It cannot express ``output_config.format``, which is the whole
  mechanism by which a T1 proposal is schema-constrained.

The ``modelId`` is an ``au.*`` inference-profile ARN **resolved at start-up** from
``bedrock:ListInferenceProfiles`` and pinned into the run record — never hard-coded.
AR-2 is the reason: if the current Claude generation has no ``au.*`` profile we ship
the previous one, and that must be a data change rather than a code change.

Two guards run on every body before it leaves this module, and both are cheap enough
that there is no argument for running them only in tests:

* :func:`assert_no_sampling_params` — decision A6. ``temperature``/``top_p``/``top_k``
  return 400 on this generation, and a parameter that cannot exist cannot be blamed
  for drift.
* :func:`assert_no_tool_surface` — the runtime half of the CaMeL quarantine. The
  compile-time half is that :func:`mainline_agentkit.call.quarantined_call` has no
  ``tools`` parameter at all.

**Provider selection defaults to ``cassette``.** The live path exists, is off, and is
never exercised in CI. Reaching it requires ``MAINLINE_AGENT_PROVIDER=bedrock`` *and*
``MAINLINE_AGENT_ALLOW_LIVE=1``, because a live call that happens by accident costs
money and non-determinism and must fail loudly instead.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .cache import CacheFacts, cache_facts_from_usage
from .errors import (
    ForbiddenRequestField,
    ResidencyRefused,
    ToolSurfaceConstructed,
    TransportUnavailable,
)

if TYPE_CHECKING:
    import threading
    from collections.abc import Mapping, Sequence

__all__ = [
    "ANTHROPIC_VERSION",
    "AUSTRALIAN_PREFIX",
    "BANNED_SAMPLING_KEYS",
    "BANNED_TOOL_KEYS",
    "AgentkitSettings",
    "BedrockTransport",
    "ModelRequest",
    "ModelResponse",
    "ResolvedProfile",
    "Transport",
    "Usage",
    "assert_australian_profile",
    "assert_no_sampling_params",
    "assert_no_tool_surface",
    "cache_facts",
    "resolve_inference_profile",
    "select_transport",
    "system_blocks_are_frozen",
]

#: The one value this package ever sends for ``anthropic_version`` on Bedrock.
ANTHROPIC_VERSION = "bedrock-2023-05-31"

#: The only inference-profile prefix permitted. ``global.*`` routes to every commercial
#: Region; ``apac.*`` can take a Queensland fatality narrative offshore.
AUSTRALIAN_PREFIX = "au."

#: Decision A6. The single definition of the ban, so the grep test has one exemption
#: rather than a policy of exemptions. Both the snake_case (native body) and camelCase
#: (Converse-style) spellings are here, because a body that acquired one by accident
#: would acquire it from a copied example.
BANNED_SAMPLING_KEYS: frozenset[str] = frozenset({"temperature", "top_p", "top_k", "topP", "topK"})

#: The keys whose *absence* is the structural quarantine.
BANNED_TOOL_KEYS: frozenset[str] = frozenset({"tools", "tool_choice", "toolConfig", "toolChoice"})

#: Subtrees the body guards record but do not descend into. A JSON Schema is **data**,
#: not request parameters: a mining procedure genuinely has a ``temperature`` setpoint,
#: and an extraction model with a ``temperature`` field must not be mistaken for a
#: sampling parameter. Descending into a schema would make the guard fire on the
#: corpus rather than on the request.
_OPAQUE_SUBTREE_KEYS: frozenset[str] = frozenset({"schema", "input_schema", "json_schema"})

_DEFAULT_REGION = "ap-southeast-2"
_DEFAULT_PROVIDER = "cassette"
_KNOWN_FOREIGN_PREFIXES = ("global.", "apac.", "us.", "eu.", "jp.", "ca.", "sa.", "us-gov.")


@dataclass(frozen=True, slots=True)
class Usage:
    """The token counters MAINLINE records for replayability (§8.2)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @classmethod
    def from_mapping(cls, usage: Mapping[str, Any] | None) -> Usage:
        """Read a usage block, treating an absent counter as an honest zero."""
        source = usage or {}
        return cls(
            input_tokens=int(source.get("input_tokens") or 0),
            output_tokens=int(source.get("output_tokens") or 0),
            cache_creation_input_tokens=int(source.get("cache_creation_input_tokens") or 0),
            cache_read_input_tokens=int(source.get("cache_read_input_tokens") or 0),
        )

    def to_mapping(self) -> dict[str, int]:
        """Ledger-shaped form for ``recall_run`` and ``agent_action_provenance``."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """One built request, plus everything needed to replay or attribute it.

    ``cassette_key`` and ``prefix_digest`` travel *with* the request rather than being
    recomputed inside a transport, so the cassette provider and the live provider agree
    on identity by construction instead of by two copies of one hashing rule.
    """

    body: Mapping[str, Any]
    model_id: str
    profile_id: str
    prompt_version: str
    cassette_key: str
    prefix_digest: str
    input_sha256: str

    def body_json(self) -> str:
        """Render the exact bytes placed in the ``InvokeModel`` ``body`` parameter."""
        return json.dumps(self.body, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """A parsed Anthropic native response.

    ``content`` is deliberately not touched by anything until
    :func:`mainline_agentkit.refusal.interpret` has classified ``stop_reason``.
    """

    stop_reason: str | None
    content: tuple[Mapping[str, Any], ...]
    usage: Usage
    model: str
    raw: Mapping[str, Any]

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> ModelResponse:
        """Parse the decoded ``InvokeModel`` response body."""
        content = body.get("content") or []
        blocks = tuple(block for block in content if isinstance(block, dict))
        return cls(
            stop_reason=body.get("stop_reason"),
            content=blocks,
            usage=Usage.from_mapping(body.get("usage")),
            model=str(body.get("model", "")),
            raw=body,
        )

    def last_text_block(self) -> str | None:
        """Return the final ``text`` block, which is where a structured output arrives.

        Thinking blocks precede it. Returns ``None`` when there is no text block at
        all, which the caller turns into a schema violation rather than a crash.
        """
        for block in reversed(self.content):
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                return str(block["text"])
        return None


@dataclass(frozen=True, slots=True)
class ResolvedProfile:
    """An ``au.*`` inference profile, resolved once and pinned into the run record."""

    profile_id: str
    profile_arn: str
    model_key: str
    region: str


@runtime_checkable
class Transport(Protocol):
    """What the call path needs from a provider: one shot, and one warming shot."""

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Issue one request and return the parsed response."""
        ...

    def warm(self, request: ModelRequest, *, first_token: threading.Event) -> ModelResponse:
        """Issue one request, setting ``first_token`` as soon as the prefix is processed.

        Decision A9: a cache entry becomes readable when the first response *begins
        streaming*. Setting the event at the first stream event and only then fanning
        out is what makes ``cache_read_input_tokens > 0`` on call #2 true rather than
        hoped for.
        """
        ...


@dataclass(frozen=True, slots=True)
class AgentkitSettings:
    """Process configuration, read once from the environment.

    Attributes:
        provider: ``cassette`` (the default, and the only one CI ever uses) or
            ``bedrock``.
        region: the Bedrock region. ``ap-southeast-2`` — where the ``au.*`` profiles
            and Titan v2 are — per §10.1.
        cassette_dir: where recorded interactions live.
        cassette_mode: ``replay`` or ``record``.
        allow_live: the second lock on the live path.
        ar1_enabled: the AR-1 tool-form fallback switch. Off.
        warm_timeout_s: how long ``warm_then_fanout`` waits for a first token.
    """

    provider: str = _DEFAULT_PROVIDER
    region: str = _DEFAULT_REGION
    cassette_dir: Path | None = None
    cassette_mode: str = "replay"
    allow_live: bool = False
    ar1_enabled: bool = False
    warm_timeout_s: float = 30.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AgentkitSettings:
        """Build settings from the environment, defaulting to the offline provider."""
        source = os.environ if env is None else env
        raw_dir = source.get("MAINLINE_CASSETTE_DIR")
        return cls(
            provider=source.get("MAINLINE_AGENT_PROVIDER", _DEFAULT_PROVIDER).strip().lower(),
            region=source.get("MAINLINE_BEDROCK_REGION", _DEFAULT_REGION).strip(),
            cassette_dir=Path(raw_dir) if raw_dir else None,
            cassette_mode=source.get("MAINLINE_CASSETTE_MODE", "replay").strip().lower(),
            allow_live=source.get("MAINLINE_AGENT_ALLOW_LIVE", "") == "1",
            ar1_enabled=source.get("MAINLINE_AR1_FALLBACK", "") == "1",
            warm_timeout_s=float(source.get("MAINLINE_WARM_TIMEOUT_S", "30")),
        )

    def with_cassette_dir(self, path: Path) -> AgentkitSettings:
        """Return a copy pointed at a different cassette store."""
        return replace(self, cassette_dir=path)


# ── residency ───────────────────────────────────────────────────────────────────


def assert_australian_profile(identifier: str) -> str:
    """Refuse any model identifier that is not an ``au.*`` inference profile.

    Accepts either a bare profile id (``au.anthropic.claude-opus-5``) or a full ARN
    (``arn:aws:bedrock:ap-southeast-2:1234:inference-profile/au.anthropic.claude-opus-5``).
    A **foundation-model id** is refused even though Bedrock would accept it, because a
    bare model id bypasses the inference profile the VPC-endpoint policy enumerates —
    the control would still be in the policy and no longer in the path.

    Returns:
        The profile id (the part after the last ``/``).

    Raises:
        ResidencyRefused: on anything else, naming the prefix that was seen.
    """
    if not identifier:
        raise ResidencyRefused(identifier, "empty model identifier")
    candidate = identifier.rsplit("/", 1)[-1]
    if identifier.startswith("arn:") and ":inference-profile/" not in identifier:
        raise ResidencyRefused(identifier, "ARN does not name an inference profile")
    for foreign in _KNOWN_FOREIGN_PREFIXES:
        if candidate.startswith(foreign):
            raise ResidencyRefused(identifier, f"cross-region profile prefix {foreign!r}")
    if not candidate.startswith(AUSTRALIAN_PREFIX):
        raise ResidencyRefused(
            identifier,
            "not an inference-profile identifier; a bare foundation-model id bypasses "
            "the VPC-endpoint policy that enumerates the au.* profile ARNs",
        )
    return candidate


def resolve_inference_profile(
    model_key: str,
    *,
    client: Any = None,
    region: str = _DEFAULT_REGION,
) -> ResolvedProfile:
    """Resolve ``model_key`` to an ``au.*`` inference profile at start-up.

    Args:
        model_key: the model generation, e.g. ``claude-opus-5``.
        client: a ``bedrock`` **control-plane** client. Injected by tests; built from
            ``boto3`` when omitted, which is the only place this package imports an
            AWS SDK.
        region: the region to build the client in.

    Raises:
        TransportUnavailable: when ``boto3`` is absent and no client was injected.
        ResidencyRefused: when no ``au.*`` profile exists for ``model_key``, or when
            the profile the API returned is not Australian. AR-2 is the operational
            answer to the first case: ship the previous generation and say so.
    """
    resolved_client = client if client is not None else _bedrock_control_plane(region)
    summaries = _list_inference_profiles(resolved_client)
    for summary in summaries:
        profile_id = str(summary.get("inferenceProfileId", ""))
        if not profile_id.startswith(AUSTRALIAN_PREFIX) or model_key not in profile_id:
            continue
        arn = str(summary.get("inferenceProfileArn", profile_id))
        assert_australian_profile(arn)
        return ResolvedProfile(
            profile_id=profile_id, profile_arn=arn, model_key=model_key, region=region
        )
    available = sorted(str(item.get("inferenceProfileId", "")) for item in summaries)
    raise ResidencyRefused(
        model_key,
        f"no au.* inference profile for this model generation in {region}; "
        f"available: {available}. AR-2: ship the previous generation and say so.",
    )


def _bedrock_control_plane(region: str) -> Any:
    # Imported here, not at module scope, so that every offline path — every schema
    # vector, every refusal test, every cassette replay — runs with no AWS SDK
    # installed at all. `mainline-boundary`'s E3 SBOM scan reads the import graph.
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise TransportUnavailable(
            "boto3 is not installed; install the `bedrock` extra to reach the live path"
        ) from exc
    return boto3.client("bedrock", region_name=region)


def _list_inference_profiles(client: Any) -> list[Mapping[str, Any]]:
    summaries: list[Mapping[str, Any]] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"maxResults": 100}
        if token:
            kwargs["nextToken"] = token
        page = client.list_inference_profiles(**kwargs)
        summaries.extend(page.get("inferenceProfileSummaries", []))
        token = page.get("nextToken")
        if not token:
            return summaries


# ── body guards ─────────────────────────────────────────────────────────────────


def _walk(node: Any, path: str) -> list[tuple[str, str]]:
    """Every ``(key, json-path)`` pair in ``node``, not descending into opaque subtrees."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            found.append((str(key), child))
            if key not in _OPAQUE_SUBTREE_KEYS:
                found.extend(_walk(value, child))
    elif isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            found.extend(_walk(item, f"{path}[{index}]"))
    return found


def assert_no_sampling_params(body: Mapping[str, Any]) -> None:
    """Refuse a body carrying any sampling parameter, at any depth (decision A6)."""
    for key, path in _walk(body, ""):
        if key in BANNED_SAMPLING_KEYS:
            raise ForbiddenRequestField(key, path)


def assert_no_tool_surface(body: Mapping[str, Any]) -> None:
    """Refuse a body carrying a tool surface, at any depth.

    The one module permitted to construct such a body is
    :mod:`mainline_agentkit.fallback_toolform`, which is written, unused, switched off,
    and does not call this function.
    """
    for key, path in _walk(body, ""):
        if key in BANNED_TOOL_KEYS:
            raise ToolSurfaceConstructed(key, path)


# ── the live provider ───────────────────────────────────────────────────────────


class BedrockTransport:
    """``bedrock-runtime`` ``InvokeModel`` with the Anthropic native body.

    Constructing this class does **not** reach the network; the first ``invoke`` does.
    ``select_transport`` refuses to build it unless both live locks are open.
    """

    def __init__(
        self,
        *,
        region: str = _DEFAULT_REGION,
        client: Any = None,
        enforce_tool_absence: bool = True,
    ) -> None:
        """Bind a region and, optionally, an injected ``bedrock-runtime`` client."""
        self.region = region
        self._client = client
        self._enforce_tool_absence = enforce_tool_absence

    @property
    def client(self) -> Any:
        """The ``bedrock-runtime`` client, built on first use."""
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - exercised only without extra
                raise TransportUnavailable(
                    "boto3 is not installed; install the `bedrock` extra"
                ) from exc
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def _guard(self, request: ModelRequest) -> None:
        assert_australian_profile(request.model_id)
        assert_no_sampling_params(request.body)
        if self._enforce_tool_absence:
            assert_no_tool_surface(request.body)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Issue one ``InvokeModel`` call."""
        self._guard(request)
        raw = self.client.invoke_model(
            modelId=request.model_id,
            body=request.body_json(),
            accept="application/json",
            contentType="application/json",
        )
        return ModelResponse.from_body(_decode(raw["body"]))

    def warm(self, request: ModelRequest, *, first_token: threading.Event) -> ModelResponse:
        """Stream one call, releasing the fan-out at the first event, then accumulate.

        The first ``message_start`` event is emitted only after the prompt prefix has
        been processed, so it is the earliest honest moment at which the cache entry is
        readable. Everything after it is accumulated into the same response shape the
        non-streaming path produces, so the caller cannot tell which one ran.
        """
        self._guard(request)
        stream = self.client.invoke_model_with_response_stream(
            modelId=request.model_id,
            body=request.body_json(),
            accept="application/json",
            contentType="application/json",
        )
        accumulator = _StreamAccumulator()
        for event in stream["body"]:
            chunk = event.get("chunk")
            if chunk is None:
                continue
            payload = json.loads(chunk["bytes"])
            accumulator.feed(payload)
            first_token.set()
        return accumulator.finish()


class _StreamAccumulator:
    """Rebuild a non-streaming response body from the Anthropic event stream."""

    def __init__(self) -> None:
        self.blocks: dict[int, dict[str, Any]] = {}
        self.stop_reason: str | None = None
        self.usage: dict[str, Any] = {}
        self.model = ""
        self.raw: dict[str, Any] = {}

    def feed(self, payload: Mapping[str, Any]) -> None:
        """Apply one stream event."""
        kind = payload.get("type")
        if kind == "message_start":
            message = payload.get("message", {})
            self.model = str(message.get("model", ""))
            self.usage.update(message.get("usage") or {})
            self.raw.update({k: v for k, v in message.items() if k != "content"})
        elif kind == "content_block_start":
            self.blocks[int(payload.get("index", 0))] = dict(payload.get("content_block") or {})
        elif kind == "content_block_delta":
            self._apply_delta(int(payload.get("index", 0)), payload.get("delta") or {})
        elif kind == "message_delta":
            delta = payload.get("delta") or {}
            if "stop_reason" in delta:
                self.stop_reason = delta["stop_reason"]
            self.usage.update(payload.get("usage") or {})

    def _apply_delta(self, index: int, delta: Mapping[str, Any]) -> None:
        block = self.blocks.setdefault(index, {"type": "text", "text": ""})
        if "text" in delta:
            block["text"] = str(block.get("text", "")) + str(delta["text"])
        elif "thinking" in delta:
            block["thinking"] = str(block.get("thinking", "")) + str(delta["thinking"])
        elif "partial_json" in delta:
            block["partial_json"] = str(block.get("partial_json", "")) + str(delta["partial_json"])

    def finish(self) -> ModelResponse:
        """Produce the response the non-streaming path would have produced."""
        body = dict(self.raw)
        body["content"] = [self.blocks[index] for index in sorted(self.blocks)]
        body["stop_reason"] = self.stop_reason
        body["usage"] = self.usage
        body["model"] = self.model
        return ModelResponse.from_body(body)


def _decode(stream: Any) -> Mapping[str, Any]:
    payload = stream.read() if hasattr(stream, "read") else stream
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise TransportUnavailable("InvokeModel returned a non-object body")
    return decoded


def cache_facts(response: ModelResponse, *, digest: str, warmed: bool) -> CacheFacts:
    """Read the cache counters off a response. Thin, but it keeps the import in one place."""
    return cache_facts_from_usage(response.usage.to_mapping(), digest=digest, warmed=warmed)


# ── provider selection ──────────────────────────────────────────────────────────


def select_transport(
    settings: AgentkitSettings | None = None,
    *,
    cassette_root: Path | None = None,
) -> Transport:
    """Build the configured provider. Defaults to the offline cassette provider.

    Raises:
        TransportUnavailable: when the live provider is selected without
            ``MAINLINE_AGENT_ALLOW_LIVE=1``, or when the provider name is unknown.
    """
    resolved = settings or AgentkitSettings.from_env()
    if resolved.provider == "cassette":
        # Imported here to break the module cycle: the cassette provider needs
        # ModelRequest/ModelResponse from this module. PLC0415 is disabled repo-wide
        # for exactly this shape and it is documented at every site.
        from .cassette import CassetteStore, CassetteTransport

        root = cassette_root or resolved.cassette_dir
        if root is None:
            raise TransportUnavailable(
                "the cassette provider needs a store: set MAINLINE_CASSETTE_DIR or pass "
                "cassette_root=. Replay never falls through to a live call."
            )
        return CassetteTransport(CassetteStore(root, mode=resolved.cassette_mode))
    if resolved.provider == "bedrock":
        if not resolved.allow_live:
            raise TransportUnavailable(
                "the live Bedrock provider is locked: set MAINLINE_AGENT_ALLOW_LIVE=1 as "
                "well. A live call that happens by accident costs money and "
                "non-determinism, so it fails loudly instead."
            )
        return BedrockTransport(region=resolved.region)
    raise TransportUnavailable(f"unknown provider {resolved.provider!r}; use cassette or bedrock")


def system_blocks_are_frozen(blocks: Sequence[Mapping[str, Any]]) -> bool:
    """Whether every system block is a plain text block (the shape a prefix digest covers)."""
    return all(
        block.get("type") == "text" and isinstance(block.get("text"), str) for block in blocks
    )
