# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``authored`` tier: every word that appears on camera, verbatim from a fixture.

``corpus-spine-authored`` hand-writes ``verticals/mainline/fixtures/corpus/authored/*.md`` —
the 2011 introduction of PRO-MEC-014 §7.3, the INC-2013-044 ICAM report, the 2013-08-04 commit
message with its U+2192 arrow, the 2016 retypeset, MOC-2019-0221, MOC-2026-0413, the WO-88213
permit and the 2009 fatality.  This tier reads those files and returns their text unchanged.

**It paraphrases nothing and composes nothing.**  A camera-facing string is asserted byte-equal
across four files (the fixture, ``VO.md``, ``SHOT-LIST.yaml`` and the generated honesty card);
a tier that "helpfully" normalised an em dash would break that test in the one place nobody
would think to look.

------------------------------------------------------------------------------------------
Resolution
------------------------------------------------------------------------------------------
A fixture claims its node in front matter.  ``node_id`` is the direct form and wins; the
alternatives exist because the spine is described in four different vocabularies across the
design documents, and a fixture author should be able to write the one natural to the file::

    node_id: event_narrative:INC-2013-044     # explicit, preferred
    event_ref: INC-2013-044                   # → event_narrative:INC-2013-044
    revision_key: MRD/PRO-MEC-014/007         # → revision_reason:MRD/PRO-MEC-014/007
    revision_key + clause_key                 # → clause_text:<revision_key>#<clause_key>
    cr_ref: MOC-2026-0413                     # → moc_justification:MOC-2026-0413

Two fixtures claiming one node is a refusal, not a precedence rule.

------------------------------------------------------------------------------------------
When the fixtures are not there yet
------------------------------------------------------------------------------------------
The two workers run concurrently.  A camera-facing node with no fixture raises
:class:`~mainline_corpus.render.protocol.MissingAuthored`, which ``--camera=require`` (the
default) turns into a build failure naming ``corpus-spine-authored``, and ``--camera=defer``
records in ``INDEX.json`` as an unrendered node with an owner.

Deferring is deliberately *not* "fall back to the template tier".  A committed cache entry
whose text is a machine paraphrase of a camera-facing beat would be wrong, would be committed,
and would have to be noticed rather than merely rebuilt.  Absent is honest; wrong is not.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from ..prompts import normalise_text
from .params import TIERS
from .protocol import MissingAuthored, RenderNode, RenderRefusal

__all__ = ["AUTHORED_RELPATH", "AuthoredFixture", "AuthoredRenderer", "load_fixtures"]

AUTHORED_RELPATH: Final[str] = "verticals/mainline/fixtures/corpus/authored"

#: This tier's census heading.  Checked against ``params.TIERS`` at import, because a tier
#: name absent from the census table would be counted under no heading at all.
TIER_NAME: Final[str] = "authored"
if TIER_NAME not in TIERS:  # pragma: no cover - import-time invariant
    raise ImportError(f"{TIER_NAME!r} is not one of params.TIERS")

#: Front-matter keys this tier understands.  Anything else in a fixture's front matter is that
#: worker's business (``printed_label``, ``ordinal``, ``template_gen``, ``effective_date`` …)
#: and is carried through untouched.
_NODE_KEYS: Final[tuple[str, ...]] = (
    "node_id",
    "node_kind",
    "event_ref",
    "external_ref",
    "revision_key",
    "clause_key",
    "cr_ref",
    "change_request_ref",
)


@dataclass(frozen=True, slots=True)
class AuthoredFixture:
    """One hand-authored fixture file."""

    node_id: str
    path: Path
    front_matter: Mapping[str, Any]
    body: str

    @property
    def node_kind(self) -> str:
        """The node kind this fixture claims."""
        return self.node_id.split(":", 1)[0]


def _split(text: str, *, path: Path) -> tuple[Mapping[str, Any], str]:
    body = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if not body.startswith("---"):
        raise RenderRefusal(
            f"{path}: authored fixture has no `---` YAML front matter. The front matter is how "
            "a fixture says which node it is; without it the file cannot be placed."
        )
    end = body.find("\n---", 3)
    if end == -1:
        raise RenderRefusal(f"{path}: authored fixture front matter is never closed")
    try:
        meta = yaml.safe_load(body[3:end])
    except yaml.YAMLError as exc:
        raise RenderRefusal(f"{path}: front matter is not valid YAML ({exc})") from exc
    if not isinstance(meta, Mapping):
        raise RenderRefusal(f"{path}: front matter must be a mapping")
    return meta, body[end + 4 :].lstrip("\n")


def _node_id_for(meta: Mapping[str, Any], *, path: Path) -> str | None:
    """Work out which node a fixture claims, or ``None`` if it claims none."""
    explicit = meta.get("node_id")
    if explicit:
        return str(explicit)

    revision_key = meta.get("revision_key")
    clause_key = meta.get("clause_key")
    if clause_key and revision_key:
        return f"clause_text:{revision_key}#{clause_key}"
    event_ref = meta.get("event_ref") or meta.get("external_ref")
    kind = meta.get("node_kind")
    if event_ref and (kind in {None, "event_narrative"}):
        return f"event_narrative:{event_ref}"
    cr_ref = meta.get("cr_ref") or meta.get("change_request_ref")
    if cr_ref:
        return f"moc_justification:{cr_ref}"
    if revision_key:
        return f"revision_reason:{revision_key}"
    if kind:
        raise RenderRefusal(
            f"{path}: front matter declares node_kind {kind!r} but no key identifying which "
            f"node it is. Declare `node_id:` explicitly, or one of {list(_NODE_KEYS)}."
        )
    return None


def load_fixtures(root: Path) -> dict[str, AuthoredFixture]:
    """Index every fixture under ``root`` by the node it claims.

    A missing directory yields an empty index rather than raising: the caller decides what an
    absent camera-facing fixture means, and that decision belongs at the policy layer.
    """
    index: dict[str, AuthoredFixture] = {}
    if not root.is_dir():
        return index
    for path in sorted(root.rglob("*.md")):
        if path.name.upper().startswith("README"):
            continue
        meta, body = _split(path.read_text(encoding="utf-8"), path=path)
        node_id = _node_id_for(meta, path=path)
        if node_id is None:
            continue  # a prose file that is not a render node — a note, an index, a caption
        if node_id in index:
            raise RenderRefusal(
                f"{path} and {index[node_id].path} both claim node {node_id!r}. Two authored "
                "texts for one camera-facing node means the film's words depend on directory "
                "order, and there is no correct answer to pick."
            )
        index[node_id] = AuthoredFixture(
            node_id=node_id, path=path, front_matter=meta, body=normalise_text(body)
        )
    return index


def _sections(body: str) -> dict[str, str]:
    """Split a fixture body on ``## HEADING`` lines into ``{lower_heading: text}``."""
    out: dict[str, str] = {}
    current = "body"
    buffer: list[str] = []
    for line in body.split("\n"):
        if line.startswith("## "):
            out[current] = normalise_text("\n".join(buffer)).strip()
            current = line[3:].strip().lower().replace(" ", "_")
            buffer = []
        else:
            buffer.append(line)
    out[current] = normalise_text("\n".join(buffer)).strip()
    return {key: value for key, value in out.items() if value}


def _iter_control_classes(facts: Mapping[str, Any]) -> Iterator[str]:
    for failure in facts.get("control_failures", ()):
        yield str(failure["control_class"])


@dataclass(slots=True)
class AuthoredRenderer:
    """Return the verbatim text of the fixture claiming this node."""

    root: Path
    fixtures: dict[str, AuthoredFixture] = field(default_factory=dict)
    name: str = TIER_NAME

    def __post_init__(self) -> None:
        if not self.fixtures:
            self.fixtures = load_fixtures(self.root)

    def has(self, node: RenderNode) -> bool:
        """Report whether a fixture claims this node."""
        return node.node_id in self.fixtures

    def render(self, node: RenderNode, prompt_version: str) -> Mapping[str, Any]:
        """Return the fixture's text, shaped to the node's schema."""
        del prompt_version
        fixture = self.fixtures.get(node.node_id)
        if fixture is None:
            raise MissingAuthored(node.node_id)
        builder: Callable[[AuthoredFixture, RenderNode], dict[str, Any]] | None = getattr(
            self, f"_shape_{node.kind}", None
        )
        if builder is None:
            raise RenderRefusal(f"{fixture.path}: node kind {node.kind!r} has no authored shape")
        return builder(fixture, node)

    # ── shaping: fixture text → the prompt's response schema ────────────────────────────
    #
    # The fixture is prose with headings; the schema is an object. The mapping is by heading
    # name, and a missing REQUIRED heading is a refusal — an authored ICAM report with no
    # findings section would produce an event whose control failures cannot be bound, and
    # discovering that at load time is four hours later than discovering it here.

    @staticmethod
    def _require(sections: Mapping[str, str], name: str, *, fixture: AuthoredFixture) -> str:
        try:
            return sections[name]
        except KeyError:
            raise RenderRefusal(
                f"{fixture.path}: authored fixture for {fixture.node_id} has no `## "
                f"{name.upper().replace('_', ' ')}` section, which the schema requires"
            ) from None

    def _shape_event_narrative(self, fixture: AuthoredFixture, node: RenderNode) -> dict[str, Any]:
        sections = _sections(fixture.body)
        findings_block = self._require(sections, "findings", fixture=fixture)
        findings = [line.strip() for line in findings_block.split("\n") if line.strip()]
        expected = list(_iter_control_classes(node.facts))
        if len(findings) != len(expected):
            raise RenderRefusal(
                f"{fixture.path}: the FINDINGS section has {len(findings)} lines but the event "
                f"has {len(expected)} control failures {expected}. Each failure's "
                "evidence_span is NOT NULL and is bound to one line; a mismatch would leave a "
                "row unloadable."
            )
        recommendations_block = sections.get("recommendations", "")
        return {
            "summary": self._require(sections, "summary", fixture=fixture),
            "sequence": self._require(sections, "sequence", fixture=fixture),
            "consequence": self._require(sections, "consequence", fixture=fixture),
            "defences": [
                {"control_class": control_class, "finding": finding}
                for control_class, finding in zip(expected, findings, strict=True)
            ],
            "recommendations": [
                line.strip() for line in recommendations_block.split("\n") if line.strip()
            ],
        }

    def _shape_clause_text(self, fixture: AuthoredFixture, node: RenderNode) -> dict[str, Any]:
        sections = _sections(fixture.body)
        body = sections.get("clause") or sections.get("body") or fixture.body.strip()
        declared = fixture.front_matter.get("obligation_verb")
        if declared:
            verb = str(declared)
        elif " must " in body:
            verb = "must"
        elif " should " in body:
            verb = "should"
        else:
            verb = "shall"
        if node.facts.get("printed_label") and fixture.front_matter.get("printed_label"):
            authored_label = str(fixture.front_matter["printed_label"])
            if authored_label != str(node.facts["printed_label"]):
                raise RenderRefusal(
                    f"{fixture.path}: declares printed_label {authored_label!r} but the corpus "
                    f"has {node.facts['printed_label']!r} for {node.node_id}. The label moves "
                    "at a retypeset and the identity does not; a disagreement here means one "
                    "of the two is describing a different revision."
                )
        return {"body": body, "obligation_verb": verb}

    def _shape_moc_justification(
        self, fixture: AuthoredFixture, node: RenderNode
    ) -> dict[str, Any]:
        del node
        sections = _sections(fixture.body)
        return {
            "justification": self._require(sections, "justification", fixture=fixture),
            "scope_note": self._require(sections, "scope", fixture=fixture),
            "risk_note": self._require(sections, "risk", fixture=fixture),
        }

    def _shape_revision_reason(self, fixture: AuthoredFixture, node: RenderNode) -> dict[str, Any]:
        sections = _sections(fixture.body)
        reason = self._require(sections, "reason", fixture=fixture)
        required = list(node.facts.get("required_citations", ()))
        lines = [line.strip() for line in sections.get("citations", "").split("\n") if line.strip()]
        if len(lines) != len(required):
            raise RenderRefusal(
                f"{fixture.path}: the CITATIONS section has {len(lines)} lines but "
                f"{node.node_id} must satisfy {len(required)} quote refs "
                f"{[str(item['quote_ref']) for item in required]}. Each ref's "
                "evidence_quote_sha256 is the digest of one line; a missing line leaves a "
                "documentary blame edge with nothing to point at."
            )
        return {
            "reason": reason,
            "citations": [
                {"quote_ref": str(citation["quote_ref"]), "line": line}
                for citation, line in zip(required, lines, strict=True)
            ],
        }
