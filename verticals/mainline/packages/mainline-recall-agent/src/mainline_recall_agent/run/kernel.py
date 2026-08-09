# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The one call this agent makes to the kernel: ``checks:materialise``.

``POST /v1/permits/{id}/checks:materialise`` is a thin authenticator in front of exactly one
server-side procedure, ``trappoint.materialise_checks()``, which issues the exposure receipt
and materialises ``blocking_check`` rows in one SERIALIZABLE transaction. The recall agent
holds no ``INSERT`` on ``blocking_check`` and never will: the boundary is a grant, not a
convention, and this module is the only place the agent's work becomes an obligation.

Two refusals are distinguished on the wire because they mean different things to an operator:

``409`` / ``412`` on an already-merged subject
    :class:`~mainline_recall_agent.run.errors.LateRecall`. The permit's gate epoch is pinned
    by ``merge_record``'s composite foreign key, so the database **physically cannot** attach
    a new precursor to it (MI07). The declared answer is to suspend the issued permit and
    fork a child whose gate is cleared afresh — never a retry, and never a silent no-op.

anything else non-2xx
    :class:`~mainline_recall_agent.run.errors.KernelRefused`, carrying the status and the
    body, because the diagnosis is the deliverable.

The transport is a protocol with a standard-library default. No ``requests``, no ``httpx``:
this is one POST of one JSON document, and a dependency here would be a dependency the
Fargate image carries for no reason.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

from trappoint_recall.run.contract import CandidateSet

from mainline_recall_agent.run.errors import KernelRefused, LateRecall

__all__ = [
    "MATERIALISE_PATH",
    "KernelTransport",
    "MaterialiseClient",
    "MaterialiseResult",
    "UrllibTransport",
]

MATERIALISE_PATH: Final = "/v1/permits/{permit_id}/checks:materialise"

_MEDIA_TYPE: Final = "application/json"
_LATE_RECALL_STATUSES: Final[frozenset[int]] = frozenset({409, 412})
_DEFAULT_TIMEOUT_S: Final = 30.0

#: The 2xx band. Named because "the kernel accepted the candidate set" is a decision this
#: agent makes on a number, and a bare 200/300 pair in a conditional is where an off-by-one
#: in that decision hides.
_HTTP_SUCCESS_FLOOR: Final = 200
_HTTP_SUCCESS_CEILING: Final = 300


class KernelTransport(Protocol):
    """One POST. Returns ``(status, body)`` and raises only for a transport failure."""

    def post(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        """Send ``body`` to ``url`` and return the status and response bytes."""
        ...


class UrllibTransport:
    """The default transport: :mod:`urllib.request`, standard library only."""

    def post(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        """POST and return ``(status, body)``. A non-2xx status is a value, not an exception."""
        # Imported here so that a run which never POSTs — the fixture and cassette paths —
        # does not pay for the urllib import graph. Documented PLC0415 exception.
        import urllib.error
        import urllib.request

        if not url.startswith("https://") and not url.startswith("http://localhost"):
            raise KernelRefused(
                f"refusing to POST a candidate set to {url!r}: the kernel endpoint must be "
                "https, or explicitly localhost for a local demo"
            )
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()


@dataclass(frozen=True, slots=True)
class MaterialiseResult:
    """What the kernel reports back after materialising the set."""

    status: int
    receipt_id: str | None
    open_blocking: int | None
    gate_epoch: int | None
    body: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class MaterialiseClient:
    """Posts a frozen candidate set to the kernel and interprets the answer."""

    base_url: str
    transport: KernelTransport
    token_provider: Callable[[], str] | None = None
    timeout_s: float = _DEFAULT_TIMEOUT_S

    def url_for(self, permit_id: str) -> str:
        """The endpoint for one permit."""
        return self.base_url.rstrip("/") + MATERIALISE_PATH.format(permit_id=permit_id)

    def materialise(self, candidate_set: CandidateSet) -> MaterialiseResult:
        """POST the set. The agent's work becomes an obligation here, or nowhere.

        Raises:
            LateRecall: the subject has already merged and its gate epoch is pinned.
            KernelRefused: any other non-2xx answer, or an unreadable body.
        """
        payload = candidate_set.model_dump_json(by_alias=True).encode("utf-8")
        headers: dict[str, str] = {
            "content-type": _MEDIA_TYPE,
            "accept": _MEDIA_TYPE,
            "idempotency-key": str(candidate_set.run_id),
        }
        if self.token_provider is not None:
            headers["authorization"] = f"Bearer {self.token_provider()}"

        status, raw = self.transport.post(
            self.url_for(str(candidate_set.permit_id)), payload, headers, self.timeout_s
        )
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            body = {"raw": raw[:512].hex()}
        if not isinstance(body, dict):
            body = {"value": body}

        if status in _LATE_RECALL_STATUSES:
            raise LateRecall(
                f"the kernel refused to materialise checks on permit "
                f"{candidate_set.permit_id} with HTTP {status}: {body}. The subject's gate "
                "epoch is pinned by merge_record, so a new precursor cannot be attached to "
                "it (MI07). Suspend the issued permit and fork a child whose gate is cleared "
                "afresh; do not retry."
            )
        if not _HTTP_SUCCESS_FLOOR <= status < _HTTP_SUCCESS_CEILING:
            raise KernelRefused(
                f"checks:materialise returned HTTP {status} for permit "
                f"{candidate_set.permit_id}: {body}"
            )

        def _int(name: str) -> int | None:
            value = body.get(name)
            return int(value) if isinstance(value, int) else None

        receipt_id = body.get("receipt_id")
        return MaterialiseResult(
            status=status,
            receipt_id=str(receipt_id) if receipt_id is not None else None,
            open_blocking=_int("open_blocking"),
            gate_epoch=_int("gate_epoch"),
            body=body,
        )
