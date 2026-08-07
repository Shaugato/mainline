# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Level 1 is frozen, and it is the buyer's own register.

ARCHITECTURE §5.4 puts it in the DDL comment and then in a CHECK::

    -- Level 1 is anchored to the buyer's ICMM Material Unwanted Event register and is FROZEN:
    -- prefix values are baked into the physical index, so re-inducting level 1 is a re-partition.
    CONSTRAINT l1_frozen CHECK (level <> 1 OR frozen = true)

The CHECK enforces *frozen*.  It cannot enforce *on the register*, because the register is
a customer artefact and not a table this schema owns.  That half is enforced here, and it
is the half that matters for the index: ``activity_root`` is the level-1 code denormalised
onto every descendant and, through ``event_cue.scope_id``, it is a prefix value of
``cue_scoped_idx``.  C-SPANN maintains **one K-means tree per distinct prefix value**, so a
fonds nobody put on the register is a tree nobody audits, and a fonds whose code changes is
not an update — every vector filed under the old code stays in the old tree, and the arm
generator will never bind that prefix again.

Hence three refusals, all of them loud:

* a level-1 node whose ``activity_root`` is not on the register (:class:`Level1OffRegister`);
* a level-1 node with ``frozen = false`` (:class:`Level1Unfrozen`) — refused here as well as
  by the database, so the writer never composes a statement it knows will be rejected;
* any attempt to *change* the level-1 code set (:class:`Level1Repartition`), whose message
  says what the correct operation actually is.

The register file itself is data, and it is treated as untrusted data: bounds on its size,
uniqueness of codes and labels, and every label put through the functional-label validator.
A register that ships a thing-or-place label would otherwise install one at the root of the
index, where it is hardest to remove.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from mainline_recall_agent.providers.canonical import canonical_json, sha256_hex

from .errors import (
    Level1OffRegister,
    Level1Repartition,
    Level1Unfrozen,
    RegisterMalformed,
    TaxonomyVersionError,
)
from .labels import validate_label
from .models import LEVEL_FONDS, ActivityNode, derive_scope_id

__all__ = [
    "MAX_LEVEL1_CODES",
    "MIN_LEVEL1_CODES",
    "REPARTITION_MESSAGE",
    "Level1Code",
    "Level1Register",
    "assert_level1_node",
    "load_level1_register",
    "refuse_level1_reinduction",
]

#: ``research/05-architecture/diachronic-recall.md`` §3: fonds cardinality 12-25.  A register
#: below the floor is not a risk taxonomy, and one above the ceiling is a subject index
#: wearing a functional one's clothes.
MIN_LEVEL1_CODES: Final[int] = 12
MAX_LEVEL1_CODES: Final[int] = 25

REPARTITION_MESSAGE: Final[str] = (
    "re-inducting level 1 is a RE-PARTITION, not an update: level-1 codes are prefix values "
    "baked into the physical vector index (C-SPANN maintains one K-means tree per distinct "
    "prefix value), so changing the code set orphans every vector filed under the old prefix "
    "rather than moving it. The supported operation is: add the new fonds at a new "
    "taxonomy_ver, re-embed the affected cues under the new scope ids, re-bond, prove the "
    "arm set covers both, and only then retire the old fonds."
)


@dataclass(frozen=True, slots=True)
class Level1Code:
    """One entry of the buyer's Material Unwanted Event register.

    ``mue_title`` is the register's own wording and is kept verbatim so an auditor can
    match this row to the customer's document.  ``label`` is the *functional rendering*
    that becomes ``activity_node.label``: MUE titles name events ("fall from height"),
    and an archival label has to name the work ("restraining people working at height").
    Keeping both is what lets the second be defended to the person who wrote the first.
    """

    activity_root: str
    mue_title: str
    label: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_root": self.activity_root,
            "mue_title": self.mue_title,
            "label": self.label,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class Level1Register:
    """A loaded, validated, frozen level-1 register."""

    register_id: str
    register_title: str
    provenance: str
    codes: tuple[Level1Code, ...]
    sha256: str
    source_path: str = ""

    @property
    def roots(self) -> tuple[str, ...]:
        return tuple(code.activity_root for code in self.codes)

    def by_root(self, activity_root: str) -> Level1Code | None:
        return next((c for c in self.codes if c.activity_root == activity_root), None)

    def contains(self, activity_root: str) -> bool:
        return self.by_root(activity_root) is not None

    def label_for(self, activity_root: str) -> str:
        code = self.by_root(activity_root)
        if code is None:
            raise Level1OffRegister(
                "activity_root is not on the frozen level-1 register",
                activity_root=activity_root,
                register_id=self.register_id,
                on_register=list(self.roots),
            )
        return code.label

    def nodes(self, *, site_id: str, taxonomy_ver: int) -> tuple[ActivityNode, ...]:
        """The level-1 rows to write for one site, in register order.

        ``induced_by='icmm_mue'`` and ``frozen=True`` are not parameters.  There is no
        legitimate way to write a fonds that is neither on the register nor frozen, so
        this function offers no way to express it.
        """
        return tuple(
            ActivityNode(
                scope_id=derive_scope_id(
                    site_id=site_id,
                    taxonomy_ver=taxonomy_ver,
                    level=LEVEL_FONDS,
                    label_path=[code.label],
                ),
                site_id=site_id,
                level=LEVEL_FONDS,
                parent_scope=None,
                label=code.label,
                activity_root=code.activity_root,
                taxonomy_ver=taxonomy_ver,
                induced_by="icmm_mue",
                frozen=True,
            )
            for code in self.codes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "register_id": self.register_id,
            "register_title": self.register_title,
            "provenance": self.provenance,
            "sha256": self.sha256,
            "codes": [code.to_dict() for code in self.codes],
        }


def _require(payload: Mapping[str, Any], key: str, kind: type, *, path: Path) -> Any:
    if key not in payload:
        raise RegisterMalformed(
            "level-1 register is missing a required key", key=key, path=str(path)
        )
    value = payload[key]
    if not isinstance(value, kind):
        raise RegisterMalformed(
            "level-1 register key has the wrong type",
            key=key,
            expected=kind.__name__,
            found=type(value).__name__,
            path=str(path),
        )
    return value


def load_level1_register(path: str | Path) -> Level1Register:
    """Load, validate and digest the frozen level-1 register.

    The digest is over RFC 8785 canonical JSON of the *parsed* document, not over the file
    bytes: reformatting the file must not change the identity of the register, and adding
    a key must.  It is recorded on every ``TaxonomyVersion`` so that "which fonds set was
    this taxonomy induced under" has an answer that survives the file being edited.
    """
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegisterMalformed(
            "level-1 register file cannot be read; level 1 is not optional and there is no "
            "default register to fall back to",
            path=str(source),
            error=type(exc).__name__,
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegisterMalformed(
            "level-1 register is not valid JSON", path=str(source), error=str(exc)
        ) from exc
    if not isinstance(payload, dict):
        raise RegisterMalformed("level-1 register must be a JSON object", path=str(source))

    if not _require(payload, "frozen", bool, path=source):
        raise Level1Unfrozen(
            "the level-1 register declares frozen=false; level 1 is frozen by construction "
            "and a register that says otherwise is refused rather than reinterpreted",
            path=str(source),
        )

    entries = _require(payload, "codes", list, path=source)
    if not (MIN_LEVEL1_CODES <= len(entries) <= MAX_LEVEL1_CODES):
        raise RegisterMalformed(
            "level-1 register size is outside the fonds cardinality band",
            count=len(entries),
            minimum=MIN_LEVEL1_CODES,
            maximum=MAX_LEVEL1_CODES,
            path=str(source),
        )

    codes: list[Level1Code] = []
    seen_roots: set[str] = set()
    seen_labels: set[str] = set()
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RegisterMalformed(
                "level-1 register entry is not an object", position=position, path=str(source)
            )
        root = str(entry.get("activity_root", "")).strip()
        title = str(entry.get("mue_title", "")).strip()
        label = str(entry.get("label", "")).strip()
        if not root or not title or not label:
            raise RegisterMalformed(
                "a level-1 register entry needs activity_root, mue_title and label",
                position=position,
                path=str(source),
            )
        if entry.get("frozen", True) is not True:
            raise Level1Unfrozen(
                "a level-1 register entry declares frozen=false",
                activity_root=root,
                path=str(source),
            )
        if root in seen_roots:
            raise RegisterMalformed(
                "duplicate activity_root on the level-1 register; the code IS the index "
                "prefix and two fonds cannot share one tree",
                activity_root=root,
                path=str(source),
            )
        if label in seen_labels:
            raise RegisterMalformed(
                "duplicate level-1 label; UNIQUE (site_id, taxonomy_ver, level, label) "
                "would refuse the second row",
                label=label,
                path=str(source),
            )
        seen_roots.add(root)
        seen_labels.add(label)
        codes.append(
            Level1Code(
                activity_root=root,
                mue_title=title,
                label=validate_label(label, where=f"level-1 label for {root}"),
                notes=str(entry.get("notes", "")).strip(),
            )
        )

    register = Level1Register(
        register_id=str(_require(payload, "register_id", str, path=source)),
        register_title=str(payload.get("register_title", "")),
        provenance=str(payload.get("provenance", "")),
        codes=tuple(codes),
        sha256=sha256_hex(canonical_json(payload)),
        source_path=str(source),
    )
    return register


def assert_level1_node(node: ActivityNode, register: Level1Register) -> ActivityNode:
    """Refuse a level-1 node that is off-register, unfrozen, or mislabelled.

    Returns the node unchanged when it is legal, so it can be used inline in a writer:
    ``rows = [assert_level1_node(n, register) for n in proposed]``.
    """
    if node.level != LEVEL_FONDS:
        raise TaxonomyVersionError(
            "assert_level1_node was handed a node that is not a fonds",
            level=node.level,
            label=node.label,
        )
    if not node.frozen:
        # Reachable despite ``ActivityNode.__post_init__`` refusing the same thing: pickle
        # and ``copy`` reconstruct a dataclass without calling ``__init__``, so a node that
        # crossed a process boundary has never been through that check.
        raise Level1Unfrozen(
            "refusing to write a level-1 node with frozen=false",
            activity_root=node.activity_root,
            label=node.label,
        )
    if node.induced_by != "icmm_mue":
        raise Level1OffRegister(
            "a level-1 node is anchored to the buyer's register and is therefore "
            "induced_by='icmm_mue'; an induced or hand-entered fonds is a new index "
            "partition arriving without a register entry",
            induced_by=node.induced_by,
            activity_root=node.activity_root,
        )
    if not register.contains(node.activity_root):
        raise Level1OffRegister(
            "refusing to write a level-1 node whose activity_root is not on the frozen "
            "ICMM Material Unwanted Event register",
            activity_root=node.activity_root,
            label=node.label,
            register_id=register.register_id,
            on_register=list(register.roots),
        )
    expected = register.label_for(node.activity_root)
    if node.label != expected:
        raise Level1OffRegister(
            "level-1 label does not match the register entry for this code; the fonds "
            "label is register data, not a local rewording",
            activity_root=node.activity_root,
            proposed=node.label,
            on_register=expected,
        )
    return node


def refuse_level1_reinduction(
    register: Level1Register, existing_roots: Iterable[str] | Sequence[str]
) -> None:
    """Compare the register to the level-1 codes already installed, and refuse a change.

    ``existing_roots`` is whatever the deployment currently has — typically
    ``SELECT DISTINCT activity_root FROM mainline.activity_node WHERE level = 1``.  An
    empty set means level 1 has never been installed, which is an install and not a
    re-induction, so it passes.
    """
    existing = {root for root in existing_roots if root}
    if not existing:
        return
    proposed = set(register.roots)
    if existing == proposed:
        return
    raise Level1Repartition(
        REPARTITION_MESSAGE,
        register_id=register.register_id,
        added=sorted(proposed - existing),
        removed=sorted(existing - proposed),
    )
