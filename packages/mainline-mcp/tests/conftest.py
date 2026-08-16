# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Offline fixtures: a recording transport, a reference catalogue, and payload builders.

Nothing in this package's own test suite touches a network. The transport is a stub that
records every call, and the HTTP transport is exercised separately against
``httpx.MockTransport``, which drives the *real* client code — SSE framing, session
header, cluster pin — without a socket.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve()
_SRC = _HERE.parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mainline_mcp.catalogue import Catalogue, load_contract  # noqa: E402
from mainline_mcp.client import DEFAULT_DIALECT, Client, RawResponse  # noqa: E402
from mainline_mcp.limits import READ_VERBS, WRITE_VERB  # noqa: E402

FIXTURES = _HERE.parent / "fixtures"
REFERENCE_CONTRACT = FIXTURES / "audit-surface.contract.yaml"

Handler = Callable[[Mapping[str, Any]], "StubResponse"]


class StubResponse:
    """A canned tool response with an explicitly chosen byte count."""

    def __init__(self, payload: Mapping[str, Any], byte_count: int | None = None) -> None:
        self.payload = payload
        self.byte_count = (
            byte_count
            if byte_count is not None
            else len(json.dumps({"jsonrpc": "2.0", "id": 1, "result": payload}).encode("utf-8"))
        )


def rows_payload(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """A tool result carrying rows as JSON inside a text content block."""
    return {"content": [{"type": "text", "text": json.dumps({"rows": list(rows)})}]}


def text_payload(text: str, *, is_error: bool = False) -> Mapping[str, Any]:
    """A tool result carrying free text, optionally an error result."""
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class StubTransport:
    """Records calls and answers them from a handler table. Never opens a socket."""

    def __init__(
        self,
        *,
        cluster_id: str = "cl-stub-0001",
        handlers: Mapping[str, Handler] | None = None,
        tools: Sequence[str] = (*READ_VERBS, WRITE_VERB),
        default: StubResponse | None = None,
    ) -> None:
        self._cluster_id = cluster_id
        self._handlers = dict(handlers or {})
        self._tools = tuple(tools)
        self._default = default or StubResponse(rows_payload([]))
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    @property
    def cluster_id(self) -> str:
        return self._cluster_id

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> RawResponse:
        self.calls.append((name, dict(arguments)))
        handler = self._handlers.get(name)
        response = handler(arguments) if handler is not None else self._default
        return RawResponse(byte_count=response.byte_count, payload=response.payload)

    def list_tool_names(self) -> tuple[str, ...]:
        return self._tools

    def close(self) -> None:
        self.closed = True


def view_router(
    by_view: Mapping[str, StubResponse],
    *,
    fallback: StubResponse | None = None,
) -> Handler:
    """Route ``select_query`` by the view name that appears in the statement."""

    def handler(arguments: Mapping[str, Any]) -> StubResponse:
        # Keyed off the dialect rather than a literal: the SQL argument name is a
        # measured property of the live server (``query`` since 2026-08-16), and a
        # fixture that hard-codes it silently stops routing the day the real one moves.
        statement = str(arguments.get(DEFAULT_DIALECT.statement, ""))
        for view, response in by_view.items():
            if view in statement:
                return response
        return fallback or StubResponse(rows_payload([]))

    return handler


@pytest.fixture
def reference_contract_path() -> Path:
    """Path to the §17 reference contract shipped with this package's tests."""
    return REFERENCE_CONTRACT


@pytest.fixture
def catalogue(reference_contract_path: Path) -> Catalogue:
    """The reference catalogue, loaded through the real loader."""
    return load_contract(reference_contract_path)


@pytest.fixture
def transport() -> StubTransport:
    """A stub transport with no handlers: every call answers with zero rows."""
    return StubTransport()


@pytest.fixture
def client(transport: StubTransport) -> Client:
    """A client over the stub transport."""
    return Client(transport)
