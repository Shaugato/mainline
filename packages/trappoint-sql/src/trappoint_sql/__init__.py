# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""TRAPPOINT's render engine and the Authority Source Contract.

Two things live in this distribution, and the second is the reason it exists.

**A deterministic SQL renderer.** Kernel templates plus one vertical binding produce
committed, reviewable SQL. ``trappoint render --check`` is a zero-diff assertion in CI,
so the SQL a database applies is provably the SQL the templates and the binding
describe — not something a hand edit drifted into.

**A compile-time refusal.** A template marks a projected gate column with a
``{# @projects … #}`` pragma. If ``vertical.toml`` carries no ``[[authority_source]]``
entry backing that column, ``trappoint render`` exits non-zero and names the column.
Specification rule `P-2` — *a projection is derived from a declared authority, never
from the inserter* — stops being a discipline someone remembers during code review and
becomes a build error. Adversarial finding `S1`, the one where the flagship claim is
launderable one hop upstream, becomes impossible to introduce silently.

Both bindings this repository ships render from the same templates: the MAINLINE
vertical and a **reference vertical** (`trappoint_ref`) that exists so the substrate is
proved at K1 rather than at K12. Two bindings that both render is the entire substrate
claim; one binding is a template engine with an audience of one.
"""

from __future__ import annotations

from .attestation import Attestation, CapabilityAnswer, load_attestation
from .binding import AuthorityReport, check_authority_contract, load_binding, repo_root
from .errors import (
    AttestationRefused,
    AuthoritySourceRefused,
    BindingInvalid,
    RenderError,
    RenderRefused,
    TemplateRefused,
    UsageError,
)
from .model import Binding, RoleSlot, SchemaZone
from .render import RenderResult, Unit, check_units, render_binding, write_units

__all__ = [
    "Attestation",
    "AttestationRefused",
    "AuthorityReport",
    "AuthoritySourceRefused",
    "Binding",
    "BindingInvalid",
    "CapabilityAnswer",
    "RenderError",
    "RenderRefused",
    "RenderResult",
    "RoleSlot",
    "SchemaZone",
    "TemplateRefused",
    "Unit",
    "UsageError",
    "check_authority_contract",
    "check_units",
    "load_attestation",
    "load_binding",
    "render_binding",
    "repo_root",
    "write_units",
]

__version__ = "0.1.0"
