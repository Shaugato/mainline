# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``BedrockTitanV2`` — Titan Text Embeddings v2, 1024-d, coarse by Matryoshka truncation.

This is the **one** place in the package where a Bedrock model identifier is a literal,
and it has to be: ARCHITECTURE §10.1 records that *embedding models cannot use inference
profiles at all*, so the Titan call is genuinely In-Region-or-nothing and there is no ARN
to resolve.  Everything Claude-shaped is resolved at runtime (see ``resolve.py``); a test
asserts that this constant is the sole model-id literal in the package.

Titan v2 **is** Matryoshka-trained and documents 256/512/1024 as selectable widths, so
truncate-then-renormalise is a supported operation here in a way it is not for bge.  We
request 1024-d and derive 256-d client-side rather than issuing a second call: two calls
would double the RPM cost on the leg that ARCHITECTURE §13.1 identifies as RPM-bound, and
would give a 256-d vector that is not a prefix of the stored 1024-d one — so the coarse
sweep and the graded arms would disagree about where a cue sits.

**Verified live, in region.**  The request and response shapes below are no longer written
from the InvokeModel contract alone.  ``scripts/aws/probe_bedrock.py`` issued exactly the
body :meth:`request_body` builds — ``inputText`` with ``dimensions`` 1024 and ``normalize``
true — against ``amazon.titan-embed-text-v2:0`` in ``ap-southeast-2`` and recorded HTTP 200
with an ``embedding`` array of 1024 floats and Bedrock's own ``inputTextTokenCount``.  The
full request and the full response are committed at
``evidence/aws/probe/raw-titan-invoke.json``.

That file settles two things this docstring previously only asserted.  The returned width is
the width both ``EMBED_DIM`` and the DDL declare.  And the vector arrives with an L2 norm of
1.00000006, so ``normalize: true`` is honoured to about 1e-7: the renormalisation in
:meth:`_vector_from_payload` is *not* what makes the stored vectors unit — Bedrock already
did — it corrects a rounding-scale residue.  It stays anyway, because the invariant that
every stored vector is unit is ours to hold rather than the vendor's to promise, and a
measurement of one response is not a guarantee about the next one.

What remains unexercised is this *class*: no test in this package calls Bedrock, and every
provider test still runs through cassettes.  ``GT-RC-01`` (day-1 checks) is what turns the
class itself from designed into observed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from typing import Any, Final

from .base import validate_batch
from .errors import ProviderError, ProviderUnavailable, VectorShapeError
from .types import EMBED_DIM, Vector256, Vector1024
from .vectors import l2_normalise, matryoshka_coarse, to_float32

__all__ = ["TITAN_EMBED_MODEL_ID", "BedrockTitanV2"]

#: The Titan v2 embedding model identifier.  See the module docstring for why this single
#: literal is legitimate where a Claude model id would not be.
TITAN_EMBED_MODEL_ID: Final[str] = "amazon.titan-embed-text-v2:0"

#: Residency (ARCHITECTURE §10.1): cognition stays in ap-southeast-2, always.
REQUIRED_REGION: Final[str] = "ap-southeast-2"


class BedrockTitanV2:
    """In-region Bedrock embedder.  Implements ``EmbeddingProvider``."""

    def __init__(
        self,
        *,
        region: str | None = None,
        client: Any | None = None,
        index_gen: str = "titan2-1",
        allow_foreign_region: bool = False,
    ) -> None:
        self._region = region or os.environ.get("AWS_REGION") or REQUIRED_REGION
        if self._region != REQUIRED_REGION and not allow_foreign_region:
            raise ProviderError(
                "refusing to embed Australian safety narratives outside the residency "
                "region; cognition stays in ap-southeast-2 (ARCHITECTURE §10.1)",
                region=self._region,
                required=REQUIRED_REGION,
            )
        self._index_gen = index_gen
        self._client = client

    def _bedrock(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - boto3 is a declared dependency
            raise ProviderUnavailable("boto3 is not installed") from exc
        try:
            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        except Exception as exc:  # pragma: no cover - requires a live AWS session
            raise ProviderUnavailable(
                "cannot construct a bedrock-runtime client (no credentials or no route)",
                region=self._region,
            ) from exc
        return self._client

    @property
    def model_id(self) -> str:
        return TITAN_EMBED_MODEL_ID

    @property
    def index_gen(self) -> str:
        return self._index_gen

    @property
    def is_semantic(self) -> bool:
        return True

    def request_body(self, text: str) -> dict[str, Any]:
        """The InvokeModel body, exposed so the cassette layer keys the exact request."""
        return {"inputText": text, "dimensions": EMBED_DIM, "normalize": True}

    def embed(self, texts: list[str], facet: str) -> list[Vector1024]:
        prepared = validate_batch(texts, facet)
        client = self._bedrock()
        out: list[Vector1024] = []
        for text in prepared:
            # Titan Text Embeddings takes ONE inputText per call; there is no batch form.
            # The loop is the API, not a missing optimisation.
            try:
                response = client.invoke_model(
                    modelId=TITAN_EMBED_MODEL_ID,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(self.request_body(text)).encode("utf-8"),
                )
            except Exception as exc:  # pragma: no cover - requires a live endpoint
                raise ProviderUnavailable(
                    "Bedrock InvokeModel failed on the Titan leg; recall degrades to "
                    "channels A+B and records arms_degraded",
                    region=self._region,
                    error=type(exc).__name__,
                ) from exc
            payload = json.loads(_read_body(response["body"]))
            out.append(self._vector_from_payload(payload))
        return out

    def _vector_from_payload(self, payload: dict[str, Any]) -> Vector1024:
        raw = payload.get("embedding")
        if not isinstance(raw, list):
            raise VectorShapeError("Titan response carried no embedding array")
        vec = tuple(float(x) for x in raw)
        if len(vec) != EMBED_DIM:
            raise VectorShapeError(
                "Titan returned an unexpected width; the DDL declares VECTOR(1024)",
                actual=len(vec),
            )
        # `normalize: true` is requested, but we renormalise anyway: the invariant that
        # every stored vector is unit is ours to hold, not the vendor's to promise.
        return Vector1024(to_float32(l2_normalise(vec)))

    def coarse(self, vecs: Sequence[Vector1024]) -> list[Vector256]:
        """Matryoshka truncation to 256-d plus client-side renormalisation."""
        return [matryoshka_coarse(vec) for vec in vecs]

    def describe(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "index_gen": self.index_gen,
            "is_semantic": True,
            "region": self._region,
            "coarse_method": "matryoshka_truncation_renormalised",
        }


def _read_body(body: Any) -> bytes:
    """Bedrock returns a StreamingBody; tests and cassettes hand back bytes or str."""
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    read = getattr(body, "read", None)
    if read is None:
        raise ProviderError("unreadable Bedrock response body", body_type=type(body).__name__)
    data = read()
    return data if isinstance(data, bytes) else str(data).encode("utf-8")
