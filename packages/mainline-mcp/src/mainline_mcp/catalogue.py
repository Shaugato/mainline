# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The audit-surface catalogue: the contract file, loaded and made strict.

``spec/mcp/audit-surface.contract.yaml`` is written by the fleet-contracts worker and
implemented as DDL by the data-model lead (decision A12: *two leads cannot own one
migration band*). This module is the third corner of that triangle — the thing that
**consumes** the contract and can therefore say, in CI, that the implementation and the
contract disagree.

Two properties are worth naming:

* **The architecture's view list is compiled in here, not inferred.**
  :data:`ARCHITECTURE_VIEWS` is ``ARCHITECTURE.md`` §17 transcribed. A contract file that
  drops a view does not quietly shrink the audit surface; it produces a divergence that
  :meth:`Catalogue.divergence_from_architecture` reports and a test asserts on. A surface
  that can silently lose a view is a surface that can silently stop answering the one
  question that mattered.

* **The loader is tolerant about spelling and strict about substance.** Key aliases are
  accepted, because the contract is another worker's file and a plausible synonym should
  not break the build; a missing view name, a non-integer budget or an unknown schema is
  a :class:`ContractError` naming the offending entry, because those are substance.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from .limits import (
    AUDIT_SCHEMA,
    BUDGET_RESPONSE_BYTES,
    BUDGET_ROWS,
    McpClientError,
)

CONTRACT_RELPATH: Final = Path("spec") / "mcp" / "audit-surface.contract.yaml"
"""Where the contract lives, relative to the repository root."""

NEGATIVE_RELPATH: Final = Path("spec") / "mcp" / "negative-assertions.yaml"
"""Where the negative assertions live, relative to the repository root."""


ARCHITECTURE_VIEWS: Final = (
    "v_open_gate_summary",
    "v_weakenings_without_disposition",
    "v_blame_coverage",
    "v_disposition_coverage",
    "v_silence_summary",
    "v_recall_conservation",
    "v_ledger_health",
    "v_fixity_coverage",
    "v_agent_actions",
    "v_gate_latency_daily",
    "v_txn_restart_daily",
    "v_unused_indexes",
    "v_changefeed_health",
)
"""Every ``mainline_audit`` view named in ``ARCHITECTURE.md`` §17, in source order.

The last four are the ops family the Steward's stock CockroachDB skills read *instead of*
``crdb_internal`` — which the MCP surface cannot reach. That substitution is the clearest
example of the pattern this whole domain runs on: the platform's limitation, taken
seriously, becomes the product's ops API.
"""


class ContractError(McpClientError):
    """The audit-surface contract is absent, malformed, or disagrees with itself."""


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    """Return the first present key among ``names``, or ``None``."""
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _as_int(value: Any, *, field_name: str, view: str, default: int) -> int:
    """Coerce a budget field to a positive int, or refuse with the offending entry named."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{view}.{field_name} must be an integer, got {value!r}")
    if value < 1:
        raise ContractError(f"{view}.{field_name} must be positive, got {value!r}")
    return value


def _as_tuple(value: Any, *, field_name: str, view: str) -> tuple[str, ...]:
    """Coerce a list-of-strings field to a tuple, or refuse."""
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ContractError(f"{view}.{field_name} must be a list of strings, got {value!r}")
    return tuple(str(item) for item in value)


@dataclass(frozen=True, slots=True)
class ViewSpec:
    """One contracted audit view: what it is called, what it returns, and what it may cost."""

    name: str
    schema: str
    columns: tuple[str, ...]
    truncation_flag: str | None
    row_cap: int
    byte_budget: int
    purpose: str

    @property
    def qualified(self) -> str:
        """``schema.name``, as it appears in a statement."""
        return f"{self.schema}.{self.name}"

    @property
    def statement(self) -> str:
        """The exact statement the prober and the auditor persona send for this view.

        It is generated, never taken from a caller. The auditor persona therefore has no
        path by which a question — however phrased — becomes arbitrary SQL: the only
        statements this package emits are ``SELECT * FROM <contracted view> LIMIT <cap>``.
        """
        # S608: the two interpolated values are a contracted view name validated against
        # `mainline_audit` and an integer row cap. No caller-supplied text reaches here —
        # that is the property `mainline_mcp.auditor` depends on.
        return f"SELECT * FROM {self.qualified} LIMIT {self.row_cap}"  # noqa: S608


@dataclass(frozen=True, slots=True)
class Catalogue:
    """The contracted views, with the defaults that applied when they were loaded."""

    views: tuple[ViewSpec, ...]
    source: Path | None
    default_row_cap: int = BUDGET_ROWS
    default_byte_budget: int = BUDGET_RESPONSE_BYTES

    def names(self) -> tuple[str, ...]:
        """Contracted view names, in contract order."""
        return tuple(view.name for view in self.views)

    def by_name(self, name: str) -> ViewSpec:
        """Return one view by name, or refuse naming what is available."""
        for view in self.views:
            if view.name == name:
                return view
        raise ContractError(f"{name!r} is not a contracted audit view; have {self.names()}")

    def has(self, name: str) -> bool:
        """Whether ``name`` is contracted."""
        return any(view.name == name for view in self.views)

    def divergence_from_architecture(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return ``(missing, extra)`` against ``ARCHITECTURE.md`` §17.

        ``missing`` is views the architecture names that the contract does not — the
        dangerous direction, because it shrinks the audit surface. ``extra`` is views the
        contract adds, which is expansion and merely needs to be deliberate.
        """
        contracted = set(self.names())
        architectural = set(ARCHITECTURE_VIEWS)
        missing = tuple(n for n in ARCHITECTURE_VIEWS if n not in contracted)
        extra = tuple(n for n in self.names() if n not in architectural)
        return missing, extra

    def __len__(self) -> int:
        """Return the number of contracted views."""
        return len(self.views)

    def __iter__(self) -> Iterator[ViewSpec]:
        """Iterate the contracted views."""
        return iter(self.views)


def _view_entries(document: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """Normalise the ``views`` section, which may be a list or a name-keyed mapping."""
    raw = _first(document, "views", "audit_views", "view")
    if raw is None:
        raise ContractError("contract has no `views` section")
    entries: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(raw, Mapping):
        for name, body in raw.items():
            if not isinstance(body, Mapping):
                raise ContractError(f"view {name!r} must be a mapping, got {type(body).__name__}")
            entries.append((str(name), body))
        return entries
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        for index, body in enumerate(raw):
            if not isinstance(body, Mapping):
                raise ContractError(f"views[{index}] must be a mapping, got {type(body).__name__}")
            name = _first(body, "name", "view", "view_name")
            if not name:
                raise ContractError(f"views[{index}] has no `name`")
            entries.append((str(name), body))
        return entries
    raise ContractError(f"`views` must be a list or a mapping, got {type(raw).__name__}")


def parse_contract(document: Mapping[str, Any], *, source: Path | None = None) -> Catalogue:
    """Build a :class:`Catalogue` from an already-parsed contract document."""
    defaults_raw = _first(document, "defaults", "default") or {}
    if not isinstance(defaults_raw, Mapping):
        raise ContractError("`defaults` must be a mapping")
    default_rows = _as_int(
        _first(defaults_raw, "row_cap", "max_rows", "rows"),
        field_name="row_cap",
        view="defaults",
        default=BUDGET_ROWS,
    )
    default_bytes = _as_int(
        _first(defaults_raw, "byte_budget", "budget_bytes", "max_bytes"),
        field_name="byte_budget",
        view="defaults",
        default=BUDGET_RESPONSE_BYTES,
    )

    views: list[ViewSpec] = []
    seen: set[str] = set()
    for name, body in _view_entries(document):
        if name in seen:
            raise ContractError(f"view {name!r} appears twice in the contract")
        seen.add(name)
        schema = str(_first(body, "schema", "schema_name") or AUDIT_SCHEMA)
        if schema != AUDIT_SCHEMA:
            raise ContractError(
                f"view {name!r} is declared in schema {schema!r}; the MCP audit surface is "
                f"{AUDIT_SCHEMA!r} only — a view outside it is not part of this contract"
            )
        flag_raw = _first(body, "truncation_flag", "truncation", "completeness_flag")
        truncation_flag = None if flag_raw in (None, False, "", "none") else str(flag_raw)
        views.append(
            ViewSpec(
                name=name,
                schema=schema,
                columns=_as_tuple(_first(body, "columns", "cols"), field_name="columns", view=name),
                truncation_flag=truncation_flag,
                row_cap=_as_int(
                    _first(body, "row_cap", "max_rows", "rows"),
                    field_name="row_cap",
                    view=name,
                    default=default_rows,
                ),
                byte_budget=_as_int(
                    _first(body, "byte_budget", "budget_bytes", "max_bytes"),
                    field_name="byte_budget",
                    view=name,
                    default=default_bytes,
                ),
                purpose=str(_first(body, "purpose", "question", "description") or ""),
            )
        )
    if not views:
        raise ContractError("contract declares no views; there is nothing to budget")
    return Catalogue(
        views=tuple(views),
        source=source,
        default_row_cap=default_rows,
        default_byte_budget=default_bytes,
    )


def load_contract(path: Path) -> Catalogue:
    """Load and validate the audit-surface contract from ``path``."""
    if not path.is_file():
        raise ContractError(
            f"audit-surface contract not found at {path}; it is owned by the fleet-contracts "
            "worker (spec/mcp/audit-surface.contract.yaml) and the budget prober cannot "
            "invent a budget for a view it has never been told about"
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContractError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(document, Mapping):
        raise ContractError(f"{path} must contain a mapping at the top level")
    return parse_contract(document, source=path)


def contract_path(repo_root: Path) -> Path:
    """Absolute path to the contract for a given repository root."""
    return repo_root / CONTRACT_RELPATH


def negative_assertions_path(repo_root: Path) -> Path:
    """Absolute path to the negative-assertions file for a given repository root."""
    return repo_root / NEGATIVE_RELPATH
