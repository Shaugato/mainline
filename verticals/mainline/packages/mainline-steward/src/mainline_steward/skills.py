# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The consumed CockroachDB Agent Skills, pinned by commit and verified by digest.

``ARCHITECTURE.md`` §9.4 has the Steward *consuming* the upstream skills repository —
observability nightly, security weekly, operations weekly, the three populated domains.
A consumed skill is an input to a statement we then sign, so it is pinned the way every
other input to a signed statement in this repository is pinned: by content.

**Two pins, and they do different jobs.**

* ``commit`` is the upstream 40-hex commit SHA. It makes the reference non-floating: a
  branch name would let the text under our sentence change without our knowledge, and
  ``main`` moving is not an event anybody here would see.
* ``skill_sha256`` is the digest of the checked-out skill directory, computed by
  :func:`~mainline_steward.digest.tree_sha256` at run time and written into the
  attestation. It is what makes "this run consumed *these bytes*" checkable by a reader
  who does not trust our clone.

**Why some lock entries ship with ``expected_sha256: null``.** The build machine that
wrote this file had the upstream commit SHA (read from the public repository on
2026-08-04) and did **not** have the upstream bytes. Writing a digest we had not computed
would have been an invented fact in an evidentiary file, so the field is null and
:meth:`SkillLock.verify` treats a null as *record, do not compare*. The first live
materialisation records the real digests with ``mainline-steward skills record``, and
from that commit forward a mismatch is a hard refusal. The state of each pin is visible
in the attestation as ``pin_state`` — ``enforced`` or ``recorded_only`` — so a reader
never has to guess which of the two they are looking at.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any, Final

from .digest import tree_file_count, tree_sha256
from .errors import SkillPinRefused

__all__ = [
    "DEFAULT_LOCK_RESOURCE",
    "MaterialisedSkill",
    "SkillLock",
    "SkillPin",
    "default_lock",
    "load_lock",
]

DEFAULT_LOCK_RESOURCE: Final = "skills.lock.json"
"""The lock shipped inside this distribution, under ``mainline_steward.data``."""

_SHA1_HEX: Final = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA256_HEX: Final = re.compile(r"\A[0-9a-f]{64}\Z")

_PIN_ENFORCED: Final = "enforced"
_PIN_RECORDED_ONLY: Final = "recorded_only"


@dataclass(frozen=True, slots=True)
class SkillPin:
    """One upstream skill, pinned by repository, commit and (optionally) content."""

    skill_id: str
    repo: str
    commit: str
    path: str
    domain: str
    expected_sha256: str | None
    why: str

    @property
    def pin_state(self) -> str:
        """``enforced`` when a content digest is recorded, ``recorded_only`` otherwise."""
        return _PIN_ENFORCED if self.expected_sha256 else _PIN_RECORDED_ONLY

    @property
    def upstream_url(self) -> str:
        """A URL a reader can paste to see exactly the bytes this pin names."""
        return f"https://github.com/{self.repo}/tree/{self.commit}/{self.path}"


@dataclass(frozen=True, slots=True)
class MaterialisedSkill:
    """A pin plus the digest actually computed over the checked-out directory."""

    pin: SkillPin
    skill_sha256: str
    file_count: int
    local_path: str

    def to_payload(self) -> dict[str, Any]:
        """Return this skill's attestation fragment. Every field is a fact, not a hope."""
        return {
            "skill_id": self.pin.skill_id,
            "domain": self.pin.domain,
            "repo": self.pin.repo,
            "commit": self.pin.commit,
            "path": self.pin.path,
            "skill_sha256": self.skill_sha256,
            "file_count": self.file_count,
            "pin_state": self.pin.pin_state,
            "upstream_url": self.pin.upstream_url,
        }


def _require(document: Mapping[str, Any], key: str, *, where: str) -> Any:
    if key not in document:
        raise SkillPinRefused(f"{where}: lock entry has no {key!r}")
    return document[key]


def _optional_digest(value: Any, *, where: str) -> str | None:
    if value is None:
        return None
    text = str(value).lower()
    if not _SHA256_HEX.match(text):
        raise SkillPinRefused(
            f"{where}: expected_sha256 {value!r} is not 64 lowercase hex characters"
        )
    return text


@dataclass(frozen=True, slots=True)
class SkillLock:
    """The set of pinned skills, keyed by ``skill_id``."""

    pins: tuple[SkillPin, ...]
    source: str

    def __iter__(self) -> Iterator[SkillPin]:
        """Iterate the pins in lock order."""
        return iter(self.pins)

    def __len__(self) -> int:
        """Return the number of pinned skills."""
        return len(self.pins)

    def ids(self) -> tuple[str, ...]:
        """Pinned skill ids, in lock order."""
        return tuple(pin.skill_id for pin in self.pins)

    def by_id(self, skill_id: str) -> SkillPin:
        """Return one pin, or refuse naming what is pinned."""
        for pin in self.pins:
            if pin.skill_id == skill_id:
                return pin
        raise SkillPinRefused(f"{skill_id!r} is not a pinned skill; have {list(self.ids())}")

    def for_ids(self, skill_ids: Sequence[str]) -> tuple[SkillPin, ...]:
        """Return the pins named by ``skill_ids``, refusing any that is not pinned."""
        return tuple(self.by_id(skill_id) for skill_id in skill_ids)

    def verify(self, pin: SkillPin, root: Path) -> MaterialisedSkill:
        """Digest the checked-out skill at ``root`` and compare it against the pin.

        Args:
            pin: the lock entry being materialised.
            root: the directory the skill was checked out into.

        Returns:
            The materialised skill, carrying the digest that was actually computed.

        Raises:
            SkillPinRefused: the directory is absent, empty, or — when the pin carries an
                ``expected_sha256`` — its bytes differ from the recorded digest.
        """
        try:
            digest = tree_sha256(root)
            count = tree_file_count(root)
        except FileNotFoundError as exc:
            raise SkillPinRefused(
                f"{pin.skill_id}: nothing was checked out at {root}. The skill is pinned at "
                f"{pin.repo}@{pin.commit}:{pin.path} — see {pin.upstream_url}"
            ) from exc
        if count == 0:
            raise SkillPinRefused(
                f"{pin.skill_id}: {root} contains no files. An empty checkout and a correct "
                "one must never produce the same attestation"
            )
        if pin.expected_sha256 is not None and digest != pin.expected_sha256:
            raise SkillPinRefused(
                f"{pin.skill_id}: content digest {digest} does not match the pinned "
                f"{pin.expected_sha256}. The commit is {pin.commit}; either the checkout is "
                "not that commit, or the bytes were modified after checkout. A consumed "
                "skill whose text can change under our sentence is not a pin"
            )
        return MaterialisedSkill(
            pin=pin,
            skill_sha256=digest,
            file_count=count,
            local_path=str(root),
        )

    def with_recorded(self, materialised: Sequence[MaterialisedSkill]) -> SkillLock:
        """Return a copy of this lock with ``expected_sha256`` filled in from ``materialised``.

        Used by ``mainline-steward skills record``, which is run once against a real
        checkout and whose output is committed. It is a separate verb rather than a
        side effect of a run: a lock file that heals itself on every run pins nothing.
        """
        recorded = {item.pin.skill_id: item.skill_sha256 for item in materialised}
        return replace(
            self,
            pins=tuple(
                replace(pin, expected_sha256=recorded.get(pin.skill_id, pin.expected_sha256))
                for pin in self.pins
            ),
        )

    def to_document(self) -> dict[str, Any]:
        """Serialise back to the lock-file shape, for ``skills record``."""
        return {
            "version": 1,
            "skills": [
                {
                    "skill_id": pin.skill_id,
                    "domain": pin.domain,
                    "repo": pin.repo,
                    "commit": pin.commit,
                    "path": pin.path,
                    "expected_sha256": pin.expected_sha256,
                    "why": pin.why,
                }
                for pin in self.pins
            ],
        }


def parse_lock(document: Mapping[str, Any], *, source: str) -> SkillLock:
    """Build a :class:`SkillLock` from an already-parsed lock document."""
    entries = _require(document, "skills", where=source)
    if not isinstance(entries, list) or not entries:
        raise SkillPinRefused(f"{source}: `skills` must be a non-empty list")
    pins: list[SkillPin] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{source}[{index}]"
        if not isinstance(entry, Mapping):
            raise SkillPinRefused(f"{where}: entry must be a mapping")
        skill_id = str(_require(entry, "skill_id", where=where))
        if skill_id in seen:
            raise SkillPinRefused(f"{where}: skill_id {skill_id!r} appears twice")
        seen.add(skill_id)
        commit = str(_require(entry, "commit", where=where)).lower()
        if not _SHA1_HEX.match(commit):
            raise SkillPinRefused(
                f"{where}: commit {commit!r} is not a 40-hex object name. A branch or tag "
                "is a floating reference, and the text under our sentence would be free to "
                "change without anybody here seeing it"
            )
        pins.append(
            SkillPin(
                skill_id=skill_id,
                repo=str(_require(entry, "repo", where=where)),
                commit=commit,
                path=str(_require(entry, "path", where=where)),
                domain=str(_require(entry, "domain", where=where)),
                expected_sha256=_optional_digest(entry.get("expected_sha256"), where=where),
                why=str(entry.get("why", "")),
            )
        )
    return SkillLock(pins=tuple(pins), source=source)


def load_lock(path: Path) -> SkillLock:
    """Load and validate a lock file from ``path``."""
    if not path.is_file():
        raise SkillPinRefused(f"no skill lock at {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillPinRefused(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(document, Mapping):
        raise SkillPinRefused(f"{path} must contain a JSON object at the top level")
    return parse_lock(document, source=str(path))


def default_lock() -> SkillLock:
    """Load the lock shipped inside this distribution."""
    resource = resources.files("mainline_steward.data").joinpath(DEFAULT_LOCK_RESOURCE)
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise SkillPinRefused(f"{DEFAULT_LOCK_RESOURCE} must contain a JSON object")
    return parse_lock(document, source=f"mainline_steward.data/{DEFAULT_LOCK_RESOURCE}")
