# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Clause prose for stage 3, and an honest account of where each sentence came from.

── THE PROVIDER CHAIN, HIGHEST AUTHORITY FIRST ──────────────────────────────────────────────

1. **authored** — ``fixtures/corpus/authored/clause_bodies.json``, hand-written by
   ``corpus-spine-authored``.  Everything on camera resolves here.
2. **cache** — ``fixtures/corpus/cache/clause_bodies.index.json``, written by
   ``corpus-render-cache``.  This file is the interface stage 3 publishes to stage 2: a flat
   ``{clause_uuid: {"body": str, "points": [str, ...], "renderer": str}}`` index, so the docx
   renderer never has to know the cache's internal key scheme (``sha256(prompt ‖ model_id ‖
   prompt_version)``) and stage 2 can change that scheme without breaking a committed ``.docx``
   digest for any reason other than the prose actually changing.
3. **structural** — composed here, from the gazetteer and from the clause's own facts.

Absent providers are *skipped*, never faked: if neither fixture exists the census in
``MANIFEST.docx.json`` says ``{"structural": 29}`` and the honesty card can state exactly that.
Decision **D2** says every camera-facing word is authored and the bulk is deterministic; the
census is how that claim is checked rather than asserted.

── WHY TIER 3 IS COMPOSED AND NOT DRAWN ─────────────────────────────────────────────────────

A structural body is a pure function of facts the corpus already asserts: the control class's
label and barrier role from ``control_classes.yaml``, the setpoint from ``setpoints.yaml``, the
citation from ``citations.yaml``, and — this is the part that matters — the **era vocabulary**
from ``phrases.yaml``.  A 2005 document says "danger tagging" where a 2025 document says
"positive isolation verification", because the vocabulary-drift injector's claim is that lexical
retrieval fails across twenty-two years.  If the rendered ``.docx`` did not drift, the documents
on screen would contradict the corpus they were rendered from.

There is no RNG in this module.  Frame selection is ``sha256`` over the clause's own identity,
so adding a clause cannot renumber the prose of any other clause — the same property decision
**D5** buys with per-stream RNG, obtained here without taking a stream at all.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..gazetteer import as_sequence, load

__all__ = [
    "BodyBank",
    "ClauseProse",
    "era_key",
    "era_surface",
]

#: Control class -> the ``phrases.yaml`` concept whose era surfaces belong in its prose.
#: Authored, small, and total-by-default: anything not named here uses ``critical_control``,
#: which exists in all four eras and is therefore always safe.
_CLASS_CONCEPT: Final[Mapping[str, str]] = {
    "ENERGY_SOURCE_IDENTIFICATION": "energy_isolation",
    "POSITIVE_ISOLATION_APPLICATION": "energy_isolation",
    "STORED_ENERGY_DISSIPATION": "trapped_energy",
    "ZERO_ENERGY_VERIFICATION": "verification",
    "ISOLATION_HANDBACK_CONTROL": "energy_isolation",
    "SEAL_SUPPORT_SYSTEM_INTEGRITY": "seal_support",
    "SEAL_FACE_TEMPERATURE_ALARM": "alarm_management",
    "GAS_TEST_BEFORE_AND_DURING_HOT_WORK": "gas_testing",
    "CONTINUOUS_ATMOSPHERIC_MONITORING": "gas_testing",
    "CONFINED_SPACE_ENTRY_PERMIT": "permit",
    "HOT_WORK_AUTHORISATION": "permit",
    "DROP_ZONE_EXCLUSION": "exclusion_zone",
    "BLAST_GUARDING_AND_CLEARANCE": "exclusion_zone",
    "PRESSURE_RELIEF_DEVICE_INTEGRITY": "pressure_relief",
    "LOAD_SUPPORT_FOR_MAINTENANCE": "dropped_object",
    "LIFTING_GEAR_INSPECTION": "dropped_object",
    "FATIGUE_AND_FITNESS_CONTROL": "fatigue",
    "PROXIMITY_DETECTION_AND_SEGREGATION": "exclusion_zone",
    "EXPOSURE_MONITORING": "verification",
    "PRESSURE_EQUIPMENT_INSPECTION": "verification",
}

_PREVENTIVE_FRAMES: Final[tuple[str, ...]] = (
    (
        "{Subject} shall be established and confirmed in place before the task begins, and "
        "shall remain in place until the work is complete and the area has been handed back."
    ),
    (
        "No person shall commence the task until {subject} has been completed and confirmed by "
        "the person in charge of the work."
    ),
    (
        "{Subject} shall be applied in accordance with {citation} and independently confirmed "
        "by a second competent person before work proceeds."
    ),
    (
        "The supervisor shall not authorise the task unless {subject} has been carried out for "
        "every energy source and every item of plant within the declared boundary."
    ),
)

_RECOVERY_FRAMES: Final[tuple[str, ...]] = (
    (
        "{Subject} shall be available and functional for the duration of the task; loss of "
        "function shall stop the work and place the plant in a safe state."
    ),
    (
        "Where {subject} is unavailable or has been overridden, the task shall be suspended and "
        "the area made safe before work resumes."
    ),
    (
        "{Subject} shall be proven at the interval set by the responsible engineer, and the "
        "result of each proof shall be recorded against the equipment tag."
    ),
    (
        "On activation of {subject}, the operator shall isolate the source, account for all "
        "persons, and record the event before any attempt at restoration."
    ),
)

_RECORD_FRAMES: Final[tuple[str, ...]] = (
    (
        "Evidence of compliance shall be recorded at the time of the check, and shall name the "
        "person who made it."
    ),
    (
        "The completed record shall be retained on the {doc_code} file under the site's "
        "{era_moc} arrangements."
    ),
    (
        "Any departure from this clause shall be raised as a {era_moc} before the work "
        "proceeds, and shall not be approved by the person performing the task."
    ),
)

_POINT_FRAMES: Final[tuple[str, ...]] = (
    "confirm that the control is in place and effective before the task starts;",
    "record the confirmation, the time it was made and the person who made it;",
    "stop the task and notify the supervisor if the control cannot be confirmed.",
)


def era_key(year: int, eras: Sequence[Mapping[str, Any]]) -> str:
    """Return the ``phrases.yaml`` era band a year falls in; out-of-range years clamp."""
    for era in eras:
        if int(era["from"]) <= year <= int(era["to"]):
            return str(era["key"])
    first, last = eras[0], eras[-1]
    return str(first["key"]) if year < int(first["from"]) else str(last["key"])


def era_surface(concept_key: str, year: int) -> str:
    """Return the words the industry used for ``concept_key`` in ``year``.

    Raises through :func:`mainline_corpus.gazetteer.as_sequence` if ``phrases.yaml`` is missing
    or empty — a silent fallback would remove the vocabulary drift that the corpus measures.
    """
    phrases = load("phrases")
    eras = as_sequence(phrases, "eras", origin="phrases.yaml")
    concepts = as_sequence(phrases, "concepts", origin="phrases.yaml")
    band = era_key(year, eras)
    for concept in concepts:
        if str(concept["key"]) == concept_key:
            return str(concept[band])
    raise KeyError(
        f"phrases.yaml has no concept {concept_key!r}; docx/bodies.py maps a control class onto "
        "it, so one of the two files is out of date"
    )


def _pick(frames: Sequence[str], *, salt: str) -> str:
    """Deterministic frame selection keyed by the clause's own identity.  No RNG stream."""
    index = int.from_bytes(hashlib.sha256(salt.encode("utf-8")).digest()[:4], "big")
    return frames[index % len(frames)]


@dataclass(frozen=True, slots=True)
class ClauseProse:
    """The prose for one clause, plus which tier produced it."""

    body: str
    points: tuple[str, ...]
    renderer: str


class BodyBank:
    """The provider chain, loaded once per build.

    ``fixtures_root`` is the ``fixtures/corpus`` directory.  Missing provider files are recorded
    as absent and skipped; a malformed one raises, because a body index that is present and
    unreadable is a defect rather than an absence.
    """

    def __init__(self, fixtures_root: Path) -> None:
        self._authored = self._read_index(fixtures_root / "authored" / "clause_bodies.json")
        self._cached = self._read_index(fixtures_root / "cache" / "clause_bodies.index.json")

    @property
    def authored_available(self) -> bool:
        """Whether ``corpus-spine-authored``'s body fixture has landed yet."""
        return bool(self._authored)

    @property
    def cache_available(self) -> bool:
        """Whether ``corpus-render-cache``'s published body index has landed yet."""
        return bool(self._cached)

    @staticmethod
    def _read_index(path: Path) -> dict[str, dict[str, Any]]:
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{path} exists but is not valid JSON: {exc}. A present-but-unreadable body "
                "index is a defect; stage 3 will not fall back to composed prose and pretend "
                "the authored text was used."
            ) from exc
        if not isinstance(raw, dict):
            raise TypeError(f"{path} must contain a JSON object keyed by clause_uuid")
        return {str(key): dict(value) for key, value in raw.items()}

    def prose(
        self,
        *,
        clause_uuid: str,
        control_class: str,
        barrier_role: str,
        doc_code: str,
        year: int,
        citation: str,
    ) -> ClauseProse:
        """Return the clause's prose from the highest-authority provider that has it."""
        for source, tier in ((self._authored, "authored"), (self._cached, "cache")):
            entry = source.get(clause_uuid)
            if entry is not None:
                return ClauseProse(
                    body=str(entry["body"]),
                    points=tuple(str(point) for point in entry.get("points", ())),
                    renderer=str(entry.get("renderer", tier)),
                )
        return self._compose(
            clause_uuid=clause_uuid,
            control_class=control_class,
            barrier_role=barrier_role,
            doc_code=doc_code,
            year=year,
            citation=citation,
        )

    def _compose(
        self,
        *,
        clause_uuid: str,
        control_class: str,
        barrier_role: str,
        doc_code: str,
        year: int,
        citation: str,
    ) -> ClauseProse:
        classes = _control_class_index()
        entry = classes.get(control_class)
        if entry is None:
            raise KeyError(
                f"control class {control_class!r} is not in gazetteer/control_classes.yaml; "
                "stage 3 will not compose prose for a control the corpus does not define"
            )
        class_label = str(entry["label"])
        # Two vocabularies, in two sentences, on purpose.  The obligation sentence names the
        # control in the corpus's STABLE vocabulary, so a reader in 2026 knows what it is.  The
        # sentence after it names the same control in the words of the document's own decade, so
        # the lexical drift the corpus measures is genuinely present in the rendered page rather
        # than only in the JSONL behind it.  Folding the era term into the obligation sentence
        # was the first attempt and produced "on activation of alarm setpoint for seal-face
        # high-temperature alarm" — drift is not worth ungrammatical prose.
        subject_phrase = f"the {class_label}"
        frames = _PREVENTIVE_FRAMES if barrier_role == "preventive" else _RECOVERY_FRAMES
        lead = _pick(frames, salt=f"lead|{clause_uuid}").format(
            subject=subject_phrase,
            Subject=f"The {class_label}",
            citation=citation,
        )
        concept = _CLASS_CONCEPT.get(control_class, "critical_control")
        era_sentence = (
            f"In this revision the control is administered under the site's "
            f"{era_surface(concept, year)} arrangements."
        )
        record = _pick(_RECORD_FRAMES, salt=f"record|{clause_uuid}").format(
            doc_code=doc_code,
            era_moc=era_surface("management_of_change", year),
        )
        return ClauseProse(
            body=f"{lead} {era_sentence} {record}",
            points=_POINT_FRAMES,
            renderer="structural",
        )


def _control_class_index() -> Mapping[str, Mapping[str, Any]]:
    """``{key: entry}`` over ``control_classes.yaml``.  The gazetteer loader already caches."""
    classes = as_sequence(load("control_classes"), "classes", origin="control_classes.yaml")
    return {str(entry["key"]): entry for entry in classes}
