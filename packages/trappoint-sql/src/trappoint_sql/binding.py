# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""THE AUTHORITY SOURCE CONTRACT — specification rule `P-2` as a build error.

`P-2` says a projection trigger must derive its value from a declared authority source
and must never derive it from the inserted row. As a rule in a document that is a
discipline somebody has to remember during code review. Here it is a **non-zero exit**.

The failure this defends against is not a deleted constraint. It is a column that
*looks* projected and is in fact supplied:

.. code-block:: sql

    CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)
    INSERT INTO blocking_check (..., severity, virulence) VALUES (..., 1, 'routine');

Every constraint still exists. Every test still passes. The gate is now enforcing a
claim the writer made about itself. Nothing is missing except *authority*, and absence
of authority is invisible to every other check in the repository.

So: a template marks a projected gate column with ``{# @projects blocking_check.severity #}``,
and ``trappoint render`` refuses to emit that template unless ``vertical.toml`` carries a
matching ``[[authority_source]]`` entry whose ``on_missing`` is ``"raise"``.

Rules `A-1` … `A-9` are ``spec/binding/authority-source.md`` §3 verbatim, with one
scoping decision this module had to make and states out loud:

**`A-5` (an entry projects a column no template declares) is enforced per relation.**
An entry projecting ``blocking_check.severity`` when *no template in the tree renders
any projection on* ``blocking_check`` is reported as **pending**, not refused — the
gate templates land in migration band `0100+`, several workers after this one, and a
renderer that refused a correct declaration for a table that does not exist yet would
force every binding to be written backwards. The moment *any* template projects onto
``blocking_check``, `A-5` becomes a hard refusal for every column of that relation. The
scope is derived from the template set, never from the binding, so it cannot be
configured away — which is the property that matters.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AuthoritySourceRefused, BindingInvalid, UsageError
from .jsonschema import SchemaViolation, UnsupportedKeyword, validate
from .model import (
    AuthoritySource,
    Binding,
    Capabilities,
    Counter,
    ObligationSource,
    SubjectBinding,
    VerticalMeta,
)

__all__ = [
    "AuthorityReport",
    "check_authority_contract",
    "load_binding",
    "repo_root",
    "spec_version_of_tree",
]

_SCHEMA_RELPATH = Path("spec/binding/vertical.schema.json")
_MANIFEST_RELPATH = Path("spec/conformance/manifest.toml")
_LEGAL_ON_MISSING = "raise"
_STRICTEST_PROJECTION = "strictest_projection"


def repo_root(start: Path | None = None) -> Path:
    """Find the workspace root: the nearest ancestor holding both ``spec/`` and ``compose.yaml``.

    Both, not either — the same rule ``trappoint migrate`` uses, so the two commands can
    never disagree about which tree they are operating on.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise UsageError(
        f"no workspace root above {here}: looked for a directory holding both `spec/` "
        "and `compose.yaml`"
    )


def spec_version_of_tree(root: Path) -> str:
    """Return the TRAPPOINT specification version this checkout carries.

    Read from ``spec/conformance/manifest.toml``, which is the one machine-readable
    statement of it in the tree and is owned by the spec worker.
    """
    manifest = root / _MANIFEST_RELPATH
    if not manifest.is_file():
        raise UsageError(f"no conformance manifest at {manifest}; cannot determine spec version")
    with manifest.open("rb") as handle:
        document = tomllib.load(handle)
    section = document.get("manifest")
    version = section.get("spec_version") if isinstance(section, Mapping) else None
    if not isinstance(version, str):
        raise UsageError(f"{manifest} does not declare [manifest].spec_version")
    return version


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _subject(raw: Mapping[str, Any], default_transition_table: str) -> SubjectBinding:
    counters = tuple(
        Counter(
            column=str(entry["column"]),
            constraint=str(entry["constraint"]),
            source=str(entry["source"]) if "source" in entry else None,
            polarity=str(entry.get("polarity", "zero_when_complete")),
            offset_column=str(entry["offset_column"]) if "offset_column" in entry else None,
        )
        for entry in raw["counters"]
    )
    return SubjectBinding(
        kind=str(raw["kind"]),
        table=str(raw["table"]),
        id_column=str(raw["id_column"]),
        epoch_column=str(raw["epoch_column"]),
        state_column=str(raw["state_column"]),
        completing_state=str(raw["completing_state"]),
        transition_table=str(raw.get("transition_table", default_transition_table)),
        event_table=str(raw["event_table"]) if "event_table" in raw else None,
        completion_table=str(raw["completion_table"]) if "completion_table" in raw else None,
        epoch_pin_constraint=(
            str(raw["epoch_pin_constraint"]) if "epoch_pin_constraint" in raw else None
        ),
        counters=counters,
    )


def _authority(raw: Mapping[str, Any]) -> AuthoritySource:
    key = _as_str_tuple(raw["key"])
    return AuthoritySource(
        projects=_as_str_tuple(raw["projects"]),
        relation=str(raw["relation"]),
        key=key,
        key_columns=_as_str_tuple(raw["key_columns"]) if "key_columns" in raw else key,
        columns=_as_str_tuple(raw["columns"]),
        on_missing=_LEGAL_ON_MISSING,
        raise_via=str(raw.get("raise_via", "p0001")),
        strictest=dict(raw.get("strictest", {})),
    )


def load_binding(path: Path, *, root: Path | None = None) -> Binding:
    """Parse and validate one ``vertical.toml``.

    Validation is against ``spec/binding/vertical.schema.json`` — the specification's own
    schema, read from the tree rather than embedded here, so a binding and the schema it
    is judged by can never drift apart inside one checkout.

    Raises:
        UsageError: the file or the schema is missing.
        BindingInvalid: the document does not satisfy the schema.
    """
    if not path.is_file():
        raise UsageError(f"no binding at {path}")
    tree_root = root if root is not None else repo_root(path.parent)

    schema_path = tree_root / _SCHEMA_RELPATH
    if not schema_path.is_file():
        raise UsageError(f"no binding schema at {schema_path}")
    import json  # local: keeps `json` off the import path of callers that only need TOML

    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    with path.open("rb") as handle:
        document = tomllib.load(handle)

    try:
        validate(document, schema)
    except SchemaViolation as exc:
        raise BindingInvalid(f"{path}{exc.pointer}: {exc.message}") from exc
    except UnsupportedKeyword as exc:
        raise BindingInvalid(f"{schema_path}: {exc}") from exc

    meta_raw = document["vertical"]
    schema_name = str(meta_raw["schema"])
    meta = VerticalMeta(
        name=str(meta_raw["name"]),
        spec_version=str(meta_raw["spec_version"]),
        schema=schema_name,
        output_dir=str(meta_raw["output_dir"]),
        license=str(meta_raw.get("license", "Apache-2.0")),
        description=str(meta_raw.get("description", "")),
    )
    capabilities_raw = document["capabilities"]
    capabilities = Capabilities(
        attestation=str(capabilities_raw["attestation"]),
        stored_digest=str(capabilities_raw["stored_digest"]),
        triggerdef=str(capabilities_raw["triggerdef"]),
        isolation=str(capabilities_raw.get("isolation", "serializable")),
    )
    conformance = document.get("conformance", {})

    return Binding(
        source=path,
        repo_root=tree_root,
        vertical=meta,
        subjects=tuple(
            _subject(entry, f"{schema_name}.subject_transition") for entry in document["subject"]
        ),
        authority_sources=tuple(_authority(entry) for entry in document["authority_source"]),
        obligation_sources=tuple(
            ObligationSource(
                relation=str(entry["relation"]),
                counter=str(entry["counter"]),
                subject_kinds=_as_str_tuple(entry.get("subject_kinds", [])),
                dedupe_key_column=(
                    str(entry["dedupe_key_column"]) if "dedupe_key_column" in entry else None
                ),
                bumps_epoch=bool(entry.get("bumps_epoch", True)),
            )
            for entry in document.get("obligation_source", [])
        ),
        capabilities=capabilities,
        emit_outbox=bool(document.get("emit_outbox", False)),
        role_overrides={str(k): str(v) for k, v in document.get("roles", {}).items()},
        conformance_profile=(
            str(conformance["profile"]) if isinstance(conformance, Mapping) and "profile" in conformance else None
        ),
        skip_requires=(
            _as_str_tuple(conformance.get("skip_requires", []))
            if isinstance(conformance, Mapping)
            else ()
        ),
        raw=document,
    )


@dataclass(frozen=True, slots=True)
class AuthorityReport:
    """What the contract concluded, for the render summary.

    ``pending`` is the honest half: declarations that are correct today and unexercised
    today, because the template that projects them has not been written yet. Printing
    them is what keeps "the contract passed" from being read as "every projection in the
    design is backed".
    """

    backed: tuple[str, ...]
    pending: tuple[str, ...]
    rendered_relations: tuple[str, ...]

    @property
    def summary(self) -> str:
        """One line for the render report."""
        return (
            f"authority: {len(self.backed)} projected column(s) backed, "
            f"{len(self.pending)} declared-and-pending"
        )


def check_authority_contract(
    binding: Binding,
    template_projections: Mapping[str, tuple[str, ...]],
    *,
    tree_spec_version: str,
) -> AuthorityReport:
    """Enforce `A-1` … `A-9` of ``spec/binding/authority-source.md``.

    Args:
        binding: the parsed, schema-valid binding.
        template_projections: template name -> the qualified columns its ``@projects``
            pragmas name. The *template set*, not the binding, decides which relations
            are in scope for `A-5`.
        tree_spec_version: the specification version this checkout carries.

    Returns:
        What was backed and what is declared-but-not-yet-rendered.

    Raises:
        AuthoritySourceRefused: any of `A-1` … `A-9`.
    """
    # ── A-8: MAJOR agreement with the specification in this tree ────────────────
    if _major(binding.vertical.spec_version) != _major(tree_spec_version):
        raise AuthoritySourceRefused(
            f"A-8: binding targets TRAPPOINT {binding.vertical.spec_version}; this tree "
            f"is {tree_spec_version}. Adding an invariant is a MAJOR bump, so a MAJOR "
            "mismatch means the binding was written against a different set of "
            "invariants than the one that would be enforced."
        )

    declared_by_template: dict[str, str] = {}
    for template, columns in sorted(template_projections.items()):
        for column in columns:
            declared_by_template.setdefault(column, template)
    rendered_relations = {column.split(".", 1)[0] for column in declared_by_template}

    # ── A-2, A-3, A-9, A-6, A-7, A-4 over each entry ────────────────────────────
    owner_of: dict[str, str] = {}
    for entry in binding.authority_sources:
        if entry.on_missing != _LEGAL_ON_MISSING:
            raise AuthoritySourceRefused(
                f'A-2: authority_source.on_missing must be "raise" '
                f"(got {entry.on_missing!r}). Absence of evidence refuses; a binding that "
                "defaults, infers or passes on a missing authority row is not TRAPPOINT."
            )
        if len(entry.projects) != len(entry.columns):
            raise AuthoritySourceRefused(
                f"A-3: authority_source projects/columns length mismatch for "
                f"{entry.relation}: {len(entry.projects)} projected column(s) against "
                f"{len(entry.columns)} source column(s). They are positional, and a "
                "silent off-by-one writes a severity into a generation counter while the "
                "gate keeps working, wrongly."
            )
        if len(entry.key) != len(entry.key_columns):
            raise AuthoritySourceRefused(
                f"A-9: authority_source key/key_columns length mismatch for "
                f"{entry.relation}: {len(entry.key)} against {len(entry.key_columns)}"
            )
        if "." not in entry.relation:
            raise AuthoritySourceRefused(
                f"A-6: authority relation {entry.relation!r} is unqualified"
            )
        if (
            entry.relation_schema == binding.vertical.schema
            and entry.relation_table in binding.subject_tables
        ) or entry.relation in binding.obligation_relations:
            raise AuthoritySourceRefused(
                f"A-6: authority relation must not be a gated relation of this binding "
                f"(got {entry.relation}). If the authority is writable by the role that "
                "writes the projected table, the projection is derived from the inserter "
                "with an extra step and P-2 is violated while every declaration looks "
                "correct."
            )
        if entry.raise_via == _STRICTEST_PROJECTION:
            missing = [
                column.split(".", 1)[1]
                for column in entry.projects
                if column.split(".", 1)[1] not in entry.strictest
            ]
            if missing:
                raise AuthoritySourceRefused(
                    f"A-7: strictest_projection requires a strictest value for "
                    f"{', '.join(sorted(missing))}"
                )
        for column in entry.projects:
            previous = owner_of.get(column)
            if previous is not None:
                raise AuthoritySourceRefused(
                    f"A-4: column projected from two authority sources: {column} "
                    f"({previous} and {entry.relation})"
                )
            owner_of[column] = entry.relation

    # ── A-1: every @projects pragma is backed ───────────────────────────────────
    for column, template in sorted(declared_by_template.items()):
        if column not in owner_of:
            raise AuthoritySourceRefused(
                f"unbacked projected column: {column}\n"
                f"  declared by template {template}\n"
                f"  binding              {binding.source}\n"
                "A-1: a gate reads this column, so something must say where its value "
                "comes from and what happens when that source is missing. Add an "
                '[[authority_source]] entry listing it in `projects`, with on_missing = "raise".'
            )

    # ── A-5: no stale declaration for a relation this tree already renders ──────
    backed: list[str] = []
    pending: list[str] = []
    for column in sorted(owner_of):
        relation = column.split(".", 1)[0]
        if column in declared_by_template:
            backed.append(column)
        elif relation in rendered_relations:
            raise AuthoritySourceRefused(
                f"A-5: authority_source projects an unrendered column: {column}. "
                f"Templates in this tree already render projections onto {relation!r} "
                f"({', '.join(sorted(c for c in declared_by_template if c.startswith(relation + '.')))}), "
                "so this declaration is stale rather than early. Remove it, or add the "
                "pragma that projects it."
            )
        else:
            pending.append(column)

    return AuthorityReport(
        backed=tuple(backed),
        pending=tuple(pending),
        rendered_relations=tuple(sorted(rendered_relations)),
    )
