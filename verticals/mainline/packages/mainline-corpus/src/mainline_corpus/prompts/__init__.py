# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The four stage-2 prompts, parsed strictly.

See ``README.md`` in this directory for the file format and for why there are exactly four.

Three properties of this loader are load-bearing rather than tidy.

**The parse is strict.**  An unknown front-matter key, a missing ``## SYSTEM`` or ``## USER``
section, a schema that is not ``additionalProperties: false``, or a schema property that is not
in ``required`` — each is a ``PromptError``.  Bedrock's strict tool use is only strict if the
schema is; a schema that drifted open would let a model return four of five fields and the
render would look like it succeeded.

**The template digest is part of the prompt's identity.**  ``Prompt.template_sha256`` is taken
over the *normalised* file body, so editing a prompt changes every cache key it produced.  The
cache does not go stale; the entries go absent and are rebuilt.  ``prompt_version`` is what a
human reads in ``corpus.lock.json``, and the version is expected to move in the same commit —
``render.verify`` reports the disagreement, but it cannot invent the intent behind it.

**Normalisation happens once, here.**  CRLF to LF, trailing whitespace stripped per line, a
single trailing newline, Unicode NFC.  A prompt edited on Windows and a prompt edited on Linux
must hash the same, or the committed cache is only reproducible on the machine that built it.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final

import yaml

__all__ = [
    "KINDS",
    "Prompt",
    "PromptError",
    "kinds",
    "load",
    "load_all",
    "normalise_text",
    "prompt_versions",
]

_HERE: Final[Path] = Path(__file__).resolve().parent

#: Every prompt kind, in a fixed order.  The corpus has four render nodes and therefore four
#: prompts; a fifth file in this directory is a build error, not a feature.
KINDS: Final[tuple[str, ...]] = ("clause", "icam", "moc", "revreason")

#: Front-matter keys a prompt file may declare.  Closed on purpose: a typo'd key that was
#: silently ignored would mean a ``max_tokens`` or a ``tool_name`` that never took effect.
_FRONT_MATTER_KEYS: Final[frozenset[str]] = frozenset(
    {"prompt", "prompt_version", "tool_name", "max_tokens", "schema"}
)

_SECTION_SYSTEM: Final[str] = "## SYSTEM"
_SECTION_USER: Final[str] = "## USER"


class PromptError(RuntimeError):
    """A prompt file is missing, malformed, or declares a schema that is not strict."""


def normalise_text(text: str) -> str:
    """Return ``text`` in the one form this package ever hashes or sends.

    LF endings, no trailing whitespace on any line, exactly one trailing newline, NFC.  A BOM
    is stripped: a Windows editor that adds one would otherwise change every key in the cache.
    """
    body = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in body.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return unicodedata.normalize("NFC", "\n".join(lines) + "\n")


@dataclass(frozen=True, slots=True)
class Prompt:
    """One parsed prompt file."""

    kind: str
    version: str
    tool_name: str
    max_tokens: int
    schema: Mapping[str, Any]
    system: str
    user: str
    template_sha256: str
    path: Path

    @property
    def required_properties(self) -> tuple[str, ...]:
        """The schema's required property names, sorted."""
        required = self.schema.get("required", ())
        return tuple(sorted(str(name) for name in required))


def _strip_licence_comment(text: str) -> str:
    """Remove the leading REUSE HTML comment so the front matter starts at byte zero."""
    stripped = text.lstrip("﻿").lstrip()
    if not stripped.startswith("<!--"):
        return text
    end = stripped.find("-->")
    if end == -1:
        raise PromptError("prompt file opens an HTML comment it never closes")
    return stripped[end + 3 :].lstrip()


def _split_front_matter(text: str) -> tuple[str, str]:
    """Return ``(front_matter, body)`` for a file whose front matter is delimited by ``---``."""
    body = _strip_licence_comment(text)
    if not body.startswith("---"):
        raise PromptError("prompt file has no `---` front matter")
    end = body.find("\n---", 3)
    if end == -1:
        raise PromptError("prompt front matter is never closed by a `---` line")
    return body[3:end], body[end + 4 :]


def _split_sections(body: str) -> tuple[str, str]:
    """Return ``(system, user)`` from a body carrying ``## SYSTEM`` then ``## USER``."""
    system_at = body.find(_SECTION_SYSTEM)
    user_at = body.find(_SECTION_USER)
    if system_at == -1 or user_at == -1:
        raise PromptError(
            f"prompt body must contain both `{_SECTION_SYSTEM}` and `{_SECTION_USER}`"
        )
    if user_at < system_at:
        raise PromptError(f"`{_SECTION_USER}` must follow `{_SECTION_SYSTEM}`")
    system = body[system_at + len(_SECTION_SYSTEM) : user_at]
    user = body[user_at + len(_SECTION_USER) :]
    return normalise_text(system), normalise_text(user)


def _check_strict_schema(schema: Any, *, where: str) -> None:
    """Refuse a tool schema that a model could satisfy partially.

    Applied recursively to every nested object, because ``additionalProperties: false`` at the
    top level says nothing about an array item three levels down — and the ICAM prompt's
    ``defences[]`` is exactly such an item.
    """
    if not isinstance(schema, Mapping):
        raise PromptError(f"{where}: schema node must be a mapping, got {type(schema).__name__}")
    node_type = schema.get("type")
    if node_type == "object":
        if schema.get("additionalProperties") is not False:
            raise PromptError(f"{where}: object schema must set `additionalProperties: false`")
        properties = schema.get("properties")
        if not isinstance(properties, Mapping) or not properties:
            raise PromptError(f"{where}: object schema must declare at least one property")
        required = schema.get("required")
        if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
            raise PromptError(f"{where}: object schema must declare a `required` list")
        missing = sorted(set(properties) - {str(name) for name in required})
        if missing:
            raise PromptError(
                f"{where}: every property must be required; optional {missing}. "
                "An optional field is a field the model may omit, and a render that omitted one "
                "would pass this stage and fail four stages downstream."
            )
        for name, child in properties.items():
            _check_strict_schema(child, where=f"{where}.{name}")
    elif node_type == "array":
        items = schema.get("items")
        if items is None:
            raise PromptError(f"{where}: array schema must declare `items`")
        _check_strict_schema(items, where=f"{where}[]")
    elif node_type not in {"string", "integer", "number", "boolean"}:
        raise PromptError(f"{where}: unsupported schema type {node_type!r}")


@cache
def load(kind: str) -> Prompt:
    """Parse and return the prompt for ``kind``.

    Cached: the four files are read once per process and every cache key derived afterwards is
    a pure function of the parsed result.
    """
    if kind not in KINDS:
        raise PromptError(f"unknown prompt kind {kind!r}; the corpus has exactly {list(KINDS)}")
    path = _HERE / f"{kind}.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"{path}: cannot read prompt file ({exc})") from exc

    front_matter, body = _split_front_matter(raw)
    try:
        meta = yaml.safe_load(front_matter)
    except yaml.YAMLError as exc:
        raise PromptError(f"{path}: front matter is not valid YAML ({exc})") from exc
    if not isinstance(meta, Mapping):
        raise PromptError(f"{path}: front matter must be a mapping")

    unknown = sorted(set(meta) - _FRONT_MATTER_KEYS)
    if unknown:
        raise PromptError(f"{path}: unknown front-matter key(s) {unknown}")
    missing = sorted(_FRONT_MATTER_KEYS - set(meta))
    if missing:
        raise PromptError(f"{path}: missing front-matter key(s) {missing}")
    if meta["prompt"] != kind:
        raise PromptError(f"{path}: declares prompt {meta['prompt']!r} but is named {kind!r}")

    version = str(meta["prompt_version"])
    if not version.startswith("v") or not version[1:].isdigit():
        raise PromptError(f"{path}: prompt_version must look like `v1`, got {version!r}")
    max_tokens = meta["max_tokens"]
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
        raise PromptError(f"{path}: max_tokens must be a positive integer")

    _check_strict_schema(meta["schema"], where=f"{kind}.schema")
    system, user = _split_sections(body)

    return Prompt(
        kind=kind,
        version=version,
        tool_name=str(meta["tool_name"]),
        max_tokens=max_tokens,
        schema=meta["schema"],
        system=system,
        user=user,
        # Over the NORMALISED whole file, licence comment included: the digest answers "is the
        # file on disk the file that produced these entries", and a licence header edit is a
        # file edit like any other.
        template_sha256=hashlib.sha256(normalise_text(raw).encode("utf-8")).hexdigest(),
        path=path,
    )


def load_all() -> tuple[Prompt, ...]:
    """Every prompt, in :data:`KINDS` order, with the directory checked for strays."""
    on_disk = {path.stem for path in _HERE.glob("*.md") if path.stem != "README"}
    strays = sorted(on_disk - set(KINDS))
    if strays:
        raise PromptError(
            f"{_HERE}: undeclared prompt file(s) {strays}. The corpus renders four node kinds; "
            "a fifth prompt is prose nobody declared and no census would count it."
        )
    return tuple(load(kind) for kind in KINDS)


def kinds() -> tuple[str, ...]:
    """Return the four prompt kinds."""
    return KINDS


def prompt_versions() -> dict[str, str]:
    """``{kind: version}``, for ``corpus.lock.json`` and the honesty card."""
    return {prompt.kind: prompt.version for prompt in load_all()}
