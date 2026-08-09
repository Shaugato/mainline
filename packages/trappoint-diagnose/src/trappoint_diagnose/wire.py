# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The wire boundary: load the shipped schema, validate against it, refuse otherwise.

Two rules govern everything here.

**The schema is loaded, never embedded.** ``spec/wire/refusal.schema.json`` is the
normative artefact and there is exactly one copy of it. A vendored duplicate would be a
second source of truth that drifts silently — and the drift would be invisible precisely
because both copies would keep validating their own emitter's output.

**Validation is a precondition of emission, not a test.** ``build_payload()`` validates
before it returns, and raises ``PayloadInvalid`` when the result does not conform. A
consumer that receives a payload from this package has the schema's guarantee, not this
package's promise.

The I15 scan is the one check that is NOT in the schema, and it is here because the schema
can only refuse a key it knows about. ``additionalProperties: false`` closes every atom,
so an unknown key is already refused — but the same words can arrive INSIDE a permitted
free-text field, and ``assert_no_person_metric()`` is what looks there. It is not a
content filter and does not pretend to be one; it refuses a specific closed vocabulary of
measurement words in the specific places a measurement about a human could hide.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .errors import PayloadInvalid
from .model import EvidenceItem, MusAtom, Naa, RefusalContext, RefusalPayload
from .schema import SchemaViolation, UnsupportedKeyword, validate

__all__ = [
    "FORBIDDEN_MEASURE_WORDS",
    "SCHEMA_RELPATH",
    "SPEC_ENV_VAR",
    "assert_no_person_metric",
    "build_payload",
    "load_refusal_schema",
    "now_rfc3339",
    "validate_payload",
]

SCHEMA_RELPATH = Path("spec") / "wire" / "refusal.schema.json"
SPEC_ENV_VAR = "TRAPPOINT_SPEC_DIR"

# Invariant I15, as a word list. Deliberately short and deliberately about MEASUREMENT:
# `signer_sub` is absent from it because who signed is a FACT and belongs in a refusal,
# while how trustworthy they are is a characterisation and does not. Extending this list
# is cheap; extending it in the wrong direction — adding a word that names a fact — makes
# the diagnosis worse, so each entry is a noun for a number about a person.
FORBIDDEN_MEASURE_WORDS: frozenset[str] = frozenset(
    {
        "attentiveness",
        "competence_score",
        "percentile",
        "rating",
        "reliability",
        "risk_score",
        "score",
        "trustworthiness",
    }
)

_DIAGNOSES = ("declarative", "quickxplain", "none")


def _candidate_roots() -> list[Path]:
    override = os.environ.get(SPEC_ENV_VAR)
    roots: list[Path] = []
    if override:
        roots.append(Path(override).parent if override.endswith("spec") else Path(override))
    roots.extend(Path(__file__).resolve().parents)
    return roots


def load_refusal_schema(path: str | Path | None = None) -> dict[str, Any]:
    """Load ``spec/wire/refusal.schema.json``.

    Resolution order: an explicit *path*; then ``TRAPPOINT_SPEC_DIR``; then the first
    ancestor directory of this module that contains ``spec/wire/refusal.schema.json``.
    The walk is what makes the package work from a source checkout without configuration;
    the environment variable is what makes it work from an installed wheel, where the
    specification is deployed beside the application rather than inside the distribution.

    Raises:
        PayloadInvalid: the schema cannot be found. Refusing here rather than falling back
            to an embedded copy is the point: a diagnoser that cannot find the contract it
            claims to satisfy must not claim to satisfy it.
    """
    if path is not None:
        return _read_schema(Path(path))
    for root in _candidate_roots():
        candidate = root / SCHEMA_RELPATH
        if candidate.is_file():
            return _read_schema(candidate)
    raise PayloadInvalid(
        f"cannot find {SCHEMA_RELPATH.as_posix()} above {Path(__file__).parent}. Set "
        f"{SPEC_ENV_VAR} to the directory holding `spec/`, or pass an explicit path. This "
        "package does not carry a vendored copy: a second copy of a normative schema "
        "drifts, and the drift is invisible because each copy validates its own emitter."
    )


def _read_schema(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PayloadInvalid(f"{path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PayloadInvalid(f"{path}: the refusal schema is not a JSON object")
    return loaded


def now_rfc3339(moment: datetime | None = None) -> str:
    """Render *moment* (default: now, UTC) as an RFC 3339 instant with millisecond precision.

    Millisecond precision rather than microsecond because the payload is compared against
    a ledger row whose timestamp comes from the database, and matching precision is the
    difference between two records that agree and two that look like they disagree.
    """
    at = (moment or datetime.now(tz=UTC)).astimezone(UTC)
    return at.strftime("%Y-%m-%dT%H:%M:%S.") + f"{at.microsecond // 1000:03d}Z"


def _walk_strings(node: Any, pointer: str = "") -> list[tuple[str, str]]:
    if isinstance(node, dict):
        found: list[tuple[str, str]] = []
        for key, value in node.items():
            found.append((f"{pointer}/{key}", str(key)))
            found.extend(_walk_strings(value, f"{pointer}/{key}"))
        return found
    if isinstance(node, list):
        found = []
        for index, value in enumerate(node):
            found.extend(_walk_strings(value, f"{pointer}/{index}"))
        return found
    if isinstance(node, str):
        return [(pointer, node)]
    return []


def assert_no_person_metric(payload: Mapping[str, Any]) -> None:
    """Refuse a payload carrying a measurement word about a person (invariant I15).

    Scans every key and every string value. A word from ``FORBIDDEN_MEASURE_WORDS`` in a
    KEY is refused outright; in a VALUE it is refused only when the value also names a
    person-shaped subject, because "the reading floor was unmet" must stay sayable while
    "the signer's attentiveness score was 0.3" must not.

    Raises:
        PayloadInvalid: a forbidden measurement appears.
    """
    for pointer, text in _walk_strings(payload):
        lowered = text.lower()
        for word in FORBIDDEN_MEASURE_WORDS:
            if word not in lowered:
                continue
            if pointer.endswith(f"/{text}"):
                raise PayloadInvalid(
                    f"{pointer}: the key {text!r} names a measurement. Invariant I15: no "
                    "substrate artefact may carry a threshold, score or flag "
                    "characterising a named human's conduct."
                )
            if any(marker in lowered for marker in ("signer", "person", "operator", "crew")):
                raise PayloadInvalid(
                    f"{pointer}: {text!r} attaches a measurement to a person. Invariant "
                    "I15: a refusal names facts, rows and rules, never a human's "
                    "competence, honesty or attentiveness."
                )


def validate_payload(payload: Mapping[str, Any], schema: Mapping[str, Any] | None = None) -> None:
    """Validate a wire payload and enforce the allegation firewall.

    Raises:
        PayloadInvalid: the payload does not validate, or it carries a person metric.
    """
    document = dict(schema) if schema is not None else load_refusal_schema()
    try:
        validate(dict(payload), document)
    except SchemaViolation as exc:
        raise PayloadInvalid(f"refusal payload is invalid — {exc}") from exc
    except UnsupportedKeyword as exc:
        raise PayloadInvalid(
            f"the shipped refusal schema uses a keyword this validator does not "
            f"implement ({exc}). Refusing rather than validating vacuously."
        ) from exc
    assert_no_person_metric(payload)


def build_payload(
    context: RefusalContext,
    *,
    spec_version: str,
    diagnosis: Literal["declarative", "quickxplain", "none"],
    mus: Sequence[MusAtom],
    naa: Naa | None,
    naa_reason: str | None,
    probe_calls: int = 0,
    profile: str | None = None,
    evidence: Sequence[EvidenceItem] = (),
    ext: Mapping[str, Any] | None = None,
    refusal_id: str | None = None,
    observed_at: str | None = None,
    schema: Mapping[str, Any] | None = None,
) -> RefusalPayload:
    """Assemble a payload, validate it against the shipped schema, and return it.

    Validation happens HERE rather than in a test, because a payload that does not
    conform is not a weaker payload — it is one no consumer contracted to parse, and
    emitting it would make the wire schema advisory.

    Raises:
        PayloadInvalid: the assembled payload does not validate.
        ValueError: the arguments contradict each other (from ``RefusalPayload``).
    """
    if diagnosis not in _DIAGNOSES:
        raise ValueError(f"{diagnosis!r} is not one of {', '.join(_DIAGNOSES)}")
    payload = RefusalPayload(
        spec_version=spec_version,
        refusal_id=refusal_id or str(uuid.uuid4()),
        observed_at=observed_at or now_rfc3339(),
        context=context,
        diagnosis=diagnosis,
        probe_calls=probe_calls,
        mus=list(mus),
        naa=naa,
        naa_reason=naa_reason,
        profile=profile,
        evidence=list(evidence),
        ext=dict(ext or {}),
    )
    validate_payload(payload.to_wire(), schema)
    return payload
