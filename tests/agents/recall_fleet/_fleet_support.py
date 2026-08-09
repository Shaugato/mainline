# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Offline doubles for the recall-agent ⇄ fleet binding suite.

Imported by bare name, matching `tests/concurrency/recall/_late_recall_support.py`:
pytest's prepend import mode puts a test directory without an ``__init__.py`` on
``sys.path``, and a shared module is how the sibling suites in this repository do it.

Everything here is offline by construction — a fake agentkit transport that returns a
body the test wrote.  The binding's whole surface is a request shape and an exception
translation, and neither needs a network to be asserted.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from mainline_agentkit import ModelResponse
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mainline_agentkit import ModelRequest

__all__ = ["TEST_PROFILE_ARN", "FakeTransport", "RerankVerdict", "text_response"]

#: A syntactically valid Australian inference-profile ARN.  It names no real account —
#: the account id is all zeroes — because a fixture carrying a real ARN would put an
#: account number in a repository.
TEST_PROFILE_ARN = (
    "arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/au.anthropic.claude-opus-5"
)


class RerankVerdict(BaseModel):
    """A minimal stand-in for the rerank output model.

    The real schema lives in `mainline_recall_agent.rerank.schema`.  This suite asserts
    the *call shape*, so it uses the smallest model that exercises strict JSON-schema
    validation without coupling the binding's tests to the rubric's field names.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mechanism: str
    precondition: str
    relevant: bool


class FakeTransport:
    """An agentkit `Transport` that replays whatever the test queued.

    Records every `ModelRequest` it was handed, which is how the body assertions reach
    the exact bytes that would have gone on the wire.
    """

    def __init__(self, responses: Sequence[Mapping[str, Any]]) -> None:
        """Queue one response body per expected call."""
        self.requests: list[ModelRequest] = []
        self._responses = list(responses)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Return the next queued response, recording the request."""
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(
                f"the transport was called {len(self.requests)} times but only "
                f"{len(self.requests) - 1} responses were queued; an unexpected extra "
                f"call is the retry-count regression this suite exists to catch"
            )
        return ModelResponse.from_body(self._responses.pop(0))

    def warm(self, request: ModelRequest, *, first_token: threading.Event) -> ModelResponse:
        """Fan-out warming is not part of the judge seam; implemented, not used."""
        response = self.invoke(request)
        first_token.set()
        return response


def text_response(text: str, *, stop_reason: str = "end_turn", **extra: Any) -> dict[str, Any]:
    """A well-formed Anthropic native response body carrying one text block."""
    body: dict[str, Any] = {
        "stop_reason": stop_reason,
        "content": [{"type": "text", "text": text}],
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 90,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 1024,
        },
        "model": "au.anthropic.claude-opus-5",
    }
    body.update(extra)
    return body
