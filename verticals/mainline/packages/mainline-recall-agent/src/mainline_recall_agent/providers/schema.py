# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Pydantic model -> strict JSON Schema for ``output_config.format``.

recall.md D6 / ARCHITECTURE §8.4: every T1 call declares
``output_config: {format: {type: "json_schema", ...}}`` with ``additionalProperties: false``
and ``strict: true``, **and** the result is re-validated client-side with Pydantic.

Both, not either.  The server-side schema is the vendor's promise; the client-side
validator is ours, and it is the one that runs on a cassette, on a replay, and on the day
the vendor's enforcement changes shape.  Belt and braces is the correct posture when the
failure mode is a silent extraction gap in a safety record.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .errors import ProviderError

__all__ = ["output_config", "to_strict_json_schema"]

_STRIP_KEYS = ("title", "default")


def _harden(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _STRIP_KEYS:
                # Dropped for determinism of the request digest and to keep the declared
                # schema minimal; a default in a strict schema is dead weight because the
                # validator, not the model, supplies it.
                continue
            out[key] = _harden(value)
        if out.get("type") == "object" or "properties" in out:
            out.setdefault("properties", {})
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_harden(item) for item in node]
    return node


def to_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Derive a strict JSON Schema from a Pydantic model.

    ``additionalProperties: false`` is applied to every object node, including ``$defs``,
    because an injection's only remaining lever under structural quarantine is to smuggle
    an *extra field* past a permissive schema (ARCHITECTURE §8.4 layer 3).
    """
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise ProviderError("schema must be a pydantic BaseModel subclass")
    raw = model.model_json_schema(ref_template="#/$defs/{model}")
    hardened = _harden(raw)
    if not isinstance(hardened, dict):  # pragma: no cover - model_json_schema returns a dict
        raise ProviderError("unexpected schema shape")
    return hardened


def output_config(model: type[BaseModel], *, name: str | None = None) -> dict[str, Any]:
    """The ``output_config`` object sent with the request.

    Wire-shape note (honesty): the exact field names below follow the Anthropic Messages
    API structured-output contract as pinned by the ``anthropic`` SDK version in
    ``uv.lock``.  They are exercised here only through cassettes — no live call has been
    made from this machine — so a live smoke test against the resolved ``au.*`` profile is
    part of ``GT-RC-01`` rather than something this package claims to have verified.
    """
    return {
        "format": {
            "type": "json_schema",
            "name": name or model.__name__,
            "strict": True,
            "schema": to_strict_json_schema(model),
        }
    }
