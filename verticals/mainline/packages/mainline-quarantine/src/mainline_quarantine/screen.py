# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 2's offline half: a deterministic pre-screen, and what it does not claim.

**What this is.** A small set of high-precision regular expressions over the *unmasked*
readings of a document (:mod:`mainline_quarantine.normalise`), each one matching a shape
that a procedure, an incident report, a standard or a permit has no reason to contain: an
imperative addressed to a reader combined with an object like "previous instructions",
"system prompt", a tool name, a credential, or a severity value. It runs with no network,
no model and no account, so it runs in CI on every commit and on a stranger's laptop.

**What this is not, said plainly because it would otherwise be overclaimed.** It is *not*
Bedrock Guardrails and it is not a reimplementation of ``PROMPT_ATTACK``. It has no
classifier, no embedding and no notion of intent. It will not catch a paraphrase it has
never seen, and it is trivially evadable by an attacker who reads this file — which is
committed, public within the repository, and meant to be read. Its job is narrower and
still worth doing:

* it is the control that exists **when the guardrail is unreachable**, and a degradation
  ladder whose bottom rung is "no screening" is not a ladder;
* it makes every corpus case assert a *named* outcome offline, so the suite is red or
  green for a reason a reviewer can point at rather than because an AWS account was
  reachable that morning;
* it is where the corpus's classes are given machine-readable identity, so
  "40 hostile documents" becomes "these twelve classes, each refused by a named control".

The honest claim in one sentence: **a hostile document reaches a component that holds no
capability to act on it, and the several ways we notice it are additive.** Detection
coverage is not claimed by this module or by the corpus (AR-9).

**Precision over recall, deliberately.** Every pattern requires both an actor and an
object in one clause. ``you must wear a harness`` is a procedure; ``you must ignore the
above instructions`` is not, and a screen that cannot tell them apart empties the review
queue of meaning within a week.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from .classes import AttackClass, Layer, Outcome
from .normalise import span_sha256, unmask

if TYPE_CHECKING:
    from .normalise import Unmasked

__all__ = [
    "DETECTORS",
    "Detector",
    "LocalPromptAttackScreen",
    "PromptAttackScreen",
    "ScreenResult",
]

_FLAGS: Final[int] = re.IGNORECASE | re.MULTILINE


@dataclass(frozen=True, slots=True)
class Detector:
    """One named shape, with the class of attack it evidences and why it is safe."""

    detector_id: str
    attack_class: AttackClass
    pattern: re.Pattern[str]
    rationale: str


@dataclass(frozen=True, slots=True)
class ScreenResult:
    """What the screen decided about one untrusted span.

    ``span`` and ``span_sha256`` are offsets into and the digest of the **original**
    document, never the folded reading, because layer 6 routes a human to the bytes that
    were actually in the file.
    """

    outcome: Outcome
    layer: Layer
    detector: str
    attack_class: AttackClass | None
    span: tuple[int, int]
    span_sha256: str
    evidence: str
    screen: str

    @property
    def blocked(self) -> bool:
        """Whether the span was refused rather than merely flagged."""
        return self.outcome is Outcome.BLOCKED_PROMPT_ATTACK


class PromptAttackScreen(Protocol):
    """The one method a screen has, so the live and offline screens are interchangeable."""

    def screen(self, text: str) -> ScreenResult:
        """Return the verdict for one untrusted span."""
        ...


#: The committed detector set, in firing order. First match wins, so the order is the
#: order in which a reviewer would want the attack described: what it tried to do to the
#: reader first, what it tried to reach second.
DETECTORS: Final[tuple[Detector, ...]] = (
    Detector(
        detector_id="override.ignore_previous",
        attack_class=AttackClass.DIRECT_INSTRUCTION_OVERRIDE,
        pattern=re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|discard|set\s+aside)\b"
            r"[^.\n]{0,60}?\b(?:previous|prior|preceding|above|earlier|foregoing|"
            r"original|initial|system|all)\b"
            r"[^.\n]{0,40}?\b(?:instruction|instructions|prompt|prompts|rule|rules|"
            r"directive|directives|guidance|constraints?)\b",
            _FLAGS,
        ),
        rationale=(
            "No procedure, incident report or standard instructs its reader to set aside "
            "the instructions it was given before reaching the document."
        ),
    ),
    Detector(
        detector_id="override.new_instructions",
        attack_class=AttackClass.DIRECT_INSTRUCTION_OVERRIDE,
        pattern=re.compile(
            r"\b(?:new|updated|revised|real|actual|true)\s+"
            r"(?:instructions?|system\s+prompt|directives?|task)\b\s*[:\-]",
            _FLAGS,
        ),
        rationale=(
            "A document announcing its own replacement instruction set is announcing an attack."
        ),
    ),
    Detector(
        detector_id="override.addressed_imperative",
        attack_class=AttackClass.DIRECT_INSTRUCTION_OVERRIDE,
        pattern=re.compile(
            r"\b(?:from\s+now\s+on|henceforth|going\s+forward)\b[^.\n]{0,20}\byou\b"
            r"|\byour\s+(?:new\s+|only\s+|real\s+)?(?:task|instruction|objective|role|"
            r"job|purpose)\s+is\b"
            r"|\byou\s+(?:must|shall|will|should|are\s+to)\s+now\b",
            _FLAGS,
        ),
        rationale=(
            "Second person plus a re-tasking verb. A plant procedure addresses roles - "
            "'the Supervisor shall' - and never re-tasks its reader."
        ),
    ),
    Detector(
        detector_id="roleplay.persona_reassignment",
        attack_class=AttackClass.ROLE_PLAY_FRAMING,
        pattern=re.compile(
            r"\byou\s+are\s+(?:now\s+)?(?:a|an|the)\s+"
            r"(?:[a-z-]+\s+){0,3}?"
            r"(?:assistant|ai|model|agent|system|administrator|admin|auditor|engineer\s+"
            r"with|developer|compliance\s+officer|superuser|root)\b"
            r"|\b(?:pretend|imagine|suppose)\s+(?:that\s+)?you\s+(?:are|were|have)\b"
            r"|\bact\s+as\s+(?:a|an|the)\s+(?:[a-z-]+\s+){0,2}?"
            r"(?:assistant|ai|model|agent|system|administrator|admin|auditor)\b"
            r"|\bassume\s+the\s+role\s+of\b"
            r"|\brole[-\s]?play(?:ing)?\s+(?:as|the)\b"
            r"|\bdeveloper\s+mode\b|\bjailbreak\b|\bDAN\s+mode\b",
            _FLAGS,
        ),
        rationale=(
            "Reassigning the reader's identity is the cheapest way to detach it from its "
            "operator framing, and no safety document does it."
        ),
    ),
    Detector(
        detector_id="channel.forged_operator_markup",
        attack_class=AttackClass.FAKE_SYSTEM_REMINDER,
        pattern=re.compile(
            r"<\s*/?\s*system(?:[-_ ]?(?:reminder|prompt|message|instruction))?\s*>"
            r"|<\s*/?\s*(?:human|assistant|operator)\s*>"
            r"|<\|\s*im_(?:start|end)\s*\|>"
            r"|\[\s*/?\s*(?:SYSTEM|INST|OPERATOR)\s*\]"
            r"|^\s*(?:system|assistant|operator)\s*:\s*\S"
            r"|#{2,}\s*(?:system|operator)\b",
            _FLAGS,
        ),
        rationale=(
            "Bedrock removes mid-conversation role='system', so the operator channel is "
            "not spoofable for real - which is exactly why a document forges its markup."
        ),
    ),
    Detector(
        detector_id="channel.our_own_markup",
        attack_class=AttackClass.FAKE_SYSTEM_REMINDER,
        pattern=re.compile(
            r"amazon-bedrock-guardrails-guardContent"
            r"|amazon-bedrock-guardrailConfig"
            r"|MAINLINE-UNTRUSTED-"
            r"|\banthropic_version\b"
            r"|\boutput_config\b",
            _FLAGS,
        ),
        rationale=(
            "A document that names our own delimiters is trying to close them. "
            "wrap_untrusted() refuses to send such a document at all; this detector is "
            "what makes the attempt a finding rather than a silent re-wrap."
        ),
    ),
    Detector(
        detector_id="tool.name_mention",
        attack_class=AttackClass.TOOL_NAME_MENTION,
        pattern=re.compile(
            r"\btool_choice\b|\btoolConfig\b|\btoolChoice\b|\bmcp_servers\b"
            r"|\"tools\"\s*:|\btools\s*=\s*\["
            r"|<\s*/?\s*(?:function_calls|antml:invoke|invoke)\b"
            r"|\bfunction[_\s]call\b"
            r"|\bInvokeModel\b|\bApplyGuardrail\b"
            r"|\binsert_rows\b|\bselect_query\b|\bexplain_query\b|\bcreate_table\b"
            r"|\bbedrock:[A-Za-z]+\b|\bs3:[A-Za-z]+\b|\bkms:[A-Za-z]+\b",
            _FLAGS,
        ),
        rationale=(
            "The extraction call holds no tools, so naming one cannot invoke it. The "
            "mention is still evidence of intent, and evidence is what layer 6 wants."
        ),
    ),
    Detector(
        detector_id="exfil.reveal_configuration",
        attack_class=AttackClass.CREDENTIAL_EXFILTRATION,
        pattern=re.compile(
            r"\b(?:reveal|print|output|repeat|show|disclose|dump|echo|list|return)\b"
            r"[^.\n]{0,40}?\b(?:system\s+prompt|your\s+instructions|prior\s+instructions|"
            r"api[_\s-]?keys?|secret[_\s-]?keys?|access[_\s-]?keys?|credentials?|"
            r"connection\s+string|bearer\s+token|session\s+token|password)\b"
            r"|\bAWS_SECRET_ACCESS_KEY\b|\bAWS_ACCESS_KEY_ID\b"
            r"|\bDATABASE_URL\b|\bTRAPPOINT_DSN\b",
            _FLAGS,
        ),
        rationale=(
            "The extraction call holds no credential to reveal. The attempt is recorded "
            "because a corpus of attempts is how a customer learns who is probing them."
        ),
    ),
    Detector(
        detector_id="exfil.egress_request",
        attack_class=AttackClass.CREDENTIAL_EXFILTRATION,
        pattern=re.compile(
            r"\b(?:post|send|upload|transmit|forward|exfiltrate|beacon|report)\b"
            r"[^.\n]{0,60}?\bhttps?://"
            r"|\bcurl\s+(?:-[A-Za-z]+\s+)*https?://"
            r"|\bwget\s+https?://"
            r"|\bwebhook\b[^.\n]{0,30}?https?://",
            _FLAGS,
        ),
        rationale=(
            "The Cognition plane's egress is the bedrock-runtime endpoint and pgwire. "
            "There is no route to an arbitrary URL, so this is intent without capability."
        ),
    ),
    Detector(
        detector_id="directive.severity",
        attack_class=AttackClass.SEVERITY_DEFLATION,
        pattern=re.compile(
            r"\b(?:set|record|classify|mark|rate|downgrade|upgrade|treat|assign|report)\b"
            r"[^.\n]{0,40}?\bseverity\b"
            r"|\bseverity\s*(?:=|:)\s*[0-9]"
            r"|\b(?:this|it)\s+is\s+not\s+a\s+(?:precursor|blocking|reportable)\b"
            r"|\bdo\s+not\s+(?:create|raise|record|write|emit|generate)\b"
            r"[^.\n]{0,40}?\b(?:blocking\s+check|finding|precursor|residue|recall)\b"
            r"|\bno\s+blocking\s+check\s+(?:is\s+)?(?:required|needed)\b",
            _FLAGS,
        ),
        rationale=(
            "Severity comes from a coded field, a regulator classification or a signed "
            "human (8.4). A document arguing about its own severity is arguing with the "
            "one field a model may never set - so the argument is a finding."
        ),
    ),
    Detector(
        detector_id="directive.gate",
        attack_class=AttackClass.DIRECT_INSTRUCTION_OVERRIDE,
        pattern=re.compile(
            r"\b(?:approve|merge|release|issue|sign|clear)\b[^.\n]{0,30}?"
            r"\b(?:the\s+)?(?:permit|permit-to-work|change\s+request|merge)\b"
            r"|\bskip\s+(?:the\s+)?(?:recall|precursor|ancestry)\b"
            r"|\bsuppress\b[^.\n]{0,40}?\b(?:finding|findings|recall|precursor|"
            r"disposition)\b"
            r"|\bmark\b[^.\n]{0,30}?\b(?:dispositioned|disposed|closed\s+out)\b",
            _FLAGS,
        ),
        rationale=(
            "The merge gate is SQL and holds no model, so a document cannot talk its way "
            "through it. It can only be seen trying, which is what this records."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class LocalPromptAttackScreen:
    """The offline screen. Deterministic, network-free, and honest about its limits."""

    detectors: tuple[Detector, ...] = DETECTORS
    name: str = "local-heuristic"

    def screen(self, text: str) -> ScreenResult:
        """Return the verdict for one untrusted span.

        Order: the folded reading first (which is the document minus its masking), then
        each base64 run that decoded to text. An imperative wins over an obfuscation
        flag, because "this document told the reader to ignore its instructions" is a
        more actionable sentence for a human than "this document contained a zero-width
        space".
        """
        reading = unmask(text)

        hit = self._first_hit(reading.folded)
        if hit is not None:
            detector, match = hit
            start, end = reading.original_span(match.start(), match.end())
            return self._blocked(detector, text[start:end], (start, end), reading="folded")

        for run in reading.decoded:
            decoded_hit = self._first_hit(run.decoded)
            if decoded_hit is not None:
                detector, match = decoded_hit
                return self._blocked(
                    detector,
                    run.encoded,
                    run.span,
                    reading=f"base64 -> {match.group(0)!r}",
                    attack_class=AttackClass.ENCODED_PAYLOAD,
                )

        if reading.obfuscated:
            return self._flagged(reading)

        return ScreenResult(
            outcome=Outcome.CLEAN,
            layer=Layer.L2_DELIMIT_AND_DATAMARK,
            detector="",
            attack_class=None,
            span=(0, 0),
            span_sha256="",
            evidence="",
            screen=self.name,
        )

    def _first_hit(self, text: str) -> tuple[Detector, re.Match[str]] | None:
        for detector in self.detectors:
            match = detector.pattern.search(text)
            if match is not None:
                return detector, match
        return None

    def _blocked(
        self,
        detector: Detector,
        raw_span: str,
        span: tuple[int, int],
        *,
        reading: str,
        attack_class: AttackClass | None = None,
    ) -> ScreenResult:
        return ScreenResult(
            outcome=Outcome.BLOCKED_PROMPT_ATTACK,
            layer=Layer.L2_DELIMIT_AND_DATAMARK,
            detector=detector.detector_id,
            attack_class=attack_class or detector.attack_class,
            span=span,
            span_sha256=span_sha256(raw_span),
            evidence=f"{detector.detector_id} matched in the {reading} reading",
            screen=self.name,
        )

    def _flagged(self, reading: Unmasked) -> ScreenResult:
        artefacts = reading.zero_width or reading.mixed_script
        if artefacts:
            first = artefacts[0]
            span = first.span
            raw = first.raw
            kind = first.kind
        else:
            run = reading.decoded[0]
            span = run.span
            raw = run.encoded
            kind = "base64"
        return ScreenResult(
            outcome=Outcome.FLAGGED_OBFUSCATION,
            layer=Layer.L2_DELIMIT_AND_DATAMARK,
            detector=f"obfuscation.{kind}",
            attack_class=(
                AttackClass.ZERO_WIDTH_INJECTION
                if kind == "zero_width"
                else AttackClass.HOMOGLYPH_INJECTION
                if kind == "mixed_script"
                else AttackClass.ENCODED_PAYLOAD
            ),
            span=span,
            span_sha256=span_sha256(raw),
            evidence=(
                f"{len(reading.zero_width)} zero-width, {len(reading.mixed_script)} "
                f"mixed-script, {len(reading.decoded)} decoded runs; no detector matched"
            ),
            screen=self.name,
        )
