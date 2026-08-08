# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Path B: one zero-tool, schema-constrained call, and every way it can fail closed.

:class:`AdjudicationOracle` implements ``mainline_domain.contracts.DeltaOracle``.
It is the only object in the MAINLINE algorithms domain that reaches a model, and
it reaches one through ``mainline_agentkit`` — the repository's single model
surface — rather than holding a second Bedrock client of its own.

**What one call is.**  Two canonical clause texts, a blame-origin summary and a
deterministic control-tuple diff, rendered into a single untrusted block; the
``adjudication`` call profile at ``effort: high``, whose frozen prompt asks for a
directional NLI relation (``entails`` / ``contradicts`` / ``neutral`` /
``abstain``) plus the verbatim span that determines it; a strict JSON schema with
``additionalProperties: false``; no tools, no sampling parameters, one retry on a
schema violation and then a dead letter.

**What it cannot do.**  It cannot see the ``safe_direction`` registry, name a
rule id, or return anything shaped like a Path-A witness — enforced in
:mod:`mainline_delta_oracle.prompt` on the shipped path.  It cannot lower a
verdict, because the codomain it feeds is the abstention ratchet.  And it cannot
succeed quietly: every failure mode below produces ``abstained=True``, which
resolves to ``weaken``, which blocks the merge.

===========================  ==============================================
model refusal                ``stop_reason='refusal'`` — plausible on a
                             cyanide-leaching or H₂S corpus
Guardrail intervention       ``PROMPT_ATTACK`` blocked the response
truncation                   ``max_tokens`` / ``pause_turn`` / context window
schema violation             invalid twice; agentkit dead-letters
unknown stop reason          unmodelled: fail closed
throttle / timeout           the call never completed
fabricated evidence          the quote is not verbatim in clause B
unsupported numeric claim    ``entails`` + numeric disagreement + no number
the model's own abstention   ``relation='abstain'``
===========================  ==============================================

Everything **not** in that table — a cassette that was never recorded, a prompt
version that does not match the profile, a model id that is not an ``au.*``
profile — raises.  See :mod:`mainline_delta_oracle.errors` for why that line is
drawn where it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import ADJUDICATION, build_request, quarantined_call
from mainline_agentkit.profiles import Adjudication

from .errors import PromptVersionMismatch, abstention_code_for
from .mapping import BAND_MAP_VERSION, abstain, to_verdict
from .prompt import TRUSTED_CONTEXT, build_untrusted_text
from .transport import build_transport

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mainline_agentkit import AgentkitSettings, Transport
    from mainline_domain.contracts import OracleRequest, OracleVerdict

__all__ = ["PROFILE_ID", "PROMPT_VERSION", "AdjudicationOracle", "OracleOutcome"]

#: The frozen prompt version every request must declare.  A request built for a
#: different one is refused rather than answered, because decision A13 makes a
#: prompt edit a commit and a cassette replayed under an edited prompt is a green
#: test asserting something that no longer exists.
PROMPT_VERSION: Final[str] = ADJUDICATION.prompt_version
PROFILE_ID: Final[str] = ADJUDICATION.profile_id

#: A stable sentinel used only to compute the request identity for provenance.
#: The real call mints a fresh random one; the cassette key deliberately excludes
#: it, so this substitution changes no hash.
_PROVENANCE_SENTINEL: Final[str] = "provenance-only"


@dataclass(frozen=True, slots=True)
class OracleOutcome:
    """A verdict plus the replayability record §8.2 requires on every agent action."""

    verdict: OracleVerdict
    provenance: Mapping[str, Any]


class AdjudicationOracle:
    """The ``DeltaOracle`` implementation.  Cassette-first; live is opt-in and off."""

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        cassette_root: Path | None = None,
        settings: AgentkitSettings | None = None,
        model_id: str | None = None,
    ) -> None:
        """Bind a transport.

        Args:
            transport: injected provider.  When omitted, built from the
                environment, which defaults to the committed cassette store.
            cassette_root: an explicit cassette directory.
            settings: agentkit settings; read from the environment when omitted.
            model_id: the ``au.*`` inference-profile ARN for a live call.  On the
                replay lane this is the recorded model generation and defaults to
                the profile's ``model_key``; agentkit's live transport refuses a
                bare model id, so a live call without a resolved ARN fails at the
                residency assertion rather than silently bypassing the VPC
                endpoint policy.
        """
        self.profile = ADJUDICATION
        self.model_id = model_id or ADJUDICATION.model_key
        self._transport = (
            transport
            if transport is not None
            else build_transport(
                settings=settings,
                cassette_root=cassette_root,
                model_id=self.model_id,
            )
        )

    @property
    def prompt_version(self) -> str:
        """The frozen prompt version requests must declare."""
        return PROMPT_VERSION

    def _check_prompt_version(self, request: OracleRequest) -> None:
        if request.prompt_version != PROMPT_VERSION:
            raise PromptVersionMismatch(
                f"the request declares prompt_version={request.prompt_version!r} and this "
                f"oracle ships {PROMPT_VERSION!r}. A prompt edit is a commit (decision "
                f"A13); resolving a pair under a version the caller did not intend would "
                f"make the stored provenance false."
            )

    def request_identity(self, request: OracleRequest) -> Mapping[str, str]:
        """The cassette key and input digest for one pair, without calling anything.

        Used by the fixture generator and by provenance on the failure paths,
        where no ``Validated`` exists to read them off.
        """
        built = build_request(
            self.profile,
            build_untrusted_text(request),
            TRUSTED_CONTEXT,
            model_id=self.model_id,
            sentinel=_PROVENANCE_SENTINEL,
            validator_error=None,
        )
        return {
            "cassette_key": built.cassette_key,
            "input_sha256": built.input_sha256,
            "prefix_digest": built.prefix_digest,
        }

    def classify(self, request: OracleRequest) -> OracleVerdict:
        """Classify one ancestor/descendant pair.  Never raises on model behaviour."""
        return self.classify_with_provenance(request).verdict

    def classify_with_provenance(self, request: OracleRequest) -> OracleOutcome:
        """Classify, and return the ledger-shaped provenance alongside the verdict."""
        self._check_prompt_version(request)
        untrusted = build_untrusted_text(request)
        try:
            validated = quarantined_call(
                self.profile,
                untrusted,
                TRUSTED_CONTEXT,
                transport=self._transport,
                model_id=self.model_id,
            )
        except Exception as exc:  # noqa: BLE001 — classified, then re-raised or converted
            # The classifier returns None for anything that is not a model
            # BEHAVIOUR failure, and the `raise` below is what stops this from
            # being a blanket swallow: a broken deployment crashes, a model that
            # could not answer becomes an abstention. errors.py argues the line.
            code = abstention_code_for(exc)
            if code is None:
                raise
            return OracleOutcome(
                verdict=abstain(
                    code,
                    f"{type(exc).__name__}: {exc}",
                    model_id=self.model_id,
                    prompt_version=PROMPT_VERSION,
                ),
                provenance={
                    "profile_id": PROFILE_ID,
                    "prompt_version": PROMPT_VERSION,
                    "model_id": self.model_id,
                    "outcome": "abstained",
                    "abstention_code": code,
                    "exception_type": type(exc).__name__,
                    "band_map": BAND_MAP_VERSION,
                    **self.request_identity(request),
                },
            )

        proposal = validated.value
        if not isinstance(proposal, Adjudication):  # pragma: no cover - schema guarantees it
            raise TypeError(
                f"the adjudication profile returned {type(proposal).__name__}, not "
                f"Adjudication; the profile register has drifted from this caller"
            )
        verdict = to_verdict(
            proposal,
            descendant_text=request.descendant_text,
            model_id=validated.model_id,
            prompt_version=validated.prompt_version,
        )
        provenance = dict(validated.provenance())
        provenance.update(
            {
                "outcome": "abstained" if verdict.abstained else "ok",
                "relation": proposal.relation,
                "confidence_band": proposal.confidence_band,
                "numeric_disagreement": proposal.numeric_disagreement,
                "band_map": BAND_MAP_VERSION,
            }
        )
        return OracleOutcome(verdict=verdict, provenance=provenance)
