# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""OpenTofu / Terraform ``show -json`` plan → typed facts.

E1, E2 and E4 all read a plan rather than a live account, because AWS credentials
are not valid on the build machine as of 2026-08 and PL-3 forbids putting an
unproven capability on a dated path. A plan is a weaker artefact than an account,
and this module is written around the one way that weakness usually goes unnoticed:

**At plan time almost every id is unknown.** ``aws_iam_policy.arn``,
``aws_subnet.id``, ``aws_security_group.id`` are all *known after apply*, so a
checker that looks for a role whose ``permissions_boundary`` equals a policy ARN
finds ``null`` and — if it is careless — concludes "no violation". That is a pass
by absence, the single failure mode this whole domain exists to refuse.

So this parser exposes three things rather than one:

* ``values`` — what the plan does know (literals, tags, ports, service names);
* ``unknown`` — what it explicitly marks *known after apply*, from
  ``resource_changes[].change.after_unknown``; and
* ``references`` — the configuration-level reference graph, from
  ``configuration.*.resources[].expressions.<attr>.references``, which is how a
  role is linked to its boundary policy when the ARN does not exist yet.

Callers resolve an attribute by value **or** by reference, and every attribute
that resolves to neither is a *violation*, not a shrug.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import PlanParseError

#: Tag key that carries the plane a resource belongs to (ARCHITECTURE.md §8.1).
#: Every security-relevant resource must carry it; an untagged subnet or security
#: group could be a kernel one, so the checks fail closed on its absence.
PLANE_TAG = "Plane"

#: Tag key on endpoint-plane resources naming the plane they serve.
SERVES_TAG = "Serves"


@dataclass(frozen=True, slots=True)
class Resource:
    """One planned resource, with its known values and its unknown-attribute map."""

    address: str
    type: str
    name: str
    module_address: str
    values: Mapping[str, Any]
    unknown: Mapping[str, Any] = field(default_factory=dict)
    mode: str = "managed"

    @property
    def tags(self) -> Mapping[str, str]:
        for key in ("tags", "tags_all"):
            raw = self.values.get(key)
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items()}
        return {}

    @property
    def plane(self) -> str | None:
        value = self.tags.get(PLANE_TAG)
        return value.strip().lower() if value else None

    @property
    def serves(self) -> str | None:
        value = self.tags.get(SERVES_TAG)
        return value.strip().lower() if value else None

    def get(self, attribute: str, default: Any = None) -> Any:
        return self.values.get(attribute, default)

    def is_unknown(self, attribute: str) -> bool:
        marker = self.unknown.get(attribute)
        if marker is True:
            return True
        if isinstance(marker, list):
            return any(m is True for m in marker)
        if isinstance(marker, dict):
            return any(v is True for v in marker.values())
        return False

    def __str__(self) -> str:
        return self.address


@dataclass(frozen=True, slots=True)
class Reference:
    """A configuration-level reference from one attribute to a resource address."""

    source_address: str
    attribute: str
    target_address: str
    target_attribute: str = ""


class PlanFacts:
    """Typed, queryable view over a plan JSON document."""

    def __init__(
        self,
        *,
        format_version: str,
        tool_version: str,
        resources: Sequence[Resource],
        references: Mapping[str, Mapping[str, tuple[str, ...]]],
        raw: Mapping[str, Any],
    ) -> None:
        self.format_version = format_version
        self.tool_version = tool_version
        self.resources: tuple[Resource, ...] = tuple(resources)
        self._by_address: dict[str, Resource] = {r.address: r for r in self.resources}
        #: address → attribute → raw reference strings ("aws_subnet.kernel_a.id", "var.x")
        self._references = references
        self.raw = raw

    # -- construction ----------------------------------------------------

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> PlanFacts:
        if not isinstance(document, Mapping):
            raise PlanParseError("plan document is not a JSON object")
        planned = document.get("planned_values")
        if not isinstance(planned, Mapping):
            raise PlanParseError(
                "plan has no 'planned_values'; this is not the output of "
                "`tofu show -json <planfile>`"
            )
        root = planned.get("root_module")
        if not isinstance(root, Mapping):
            raise PlanParseError("plan has no 'planned_values.root_module'")

        unknowns = _unknown_map(document.get("resource_changes"))
        resources = list(_walk_module(root, module_address="", unknowns=unknowns))
        references = _configuration_references(document.get("configuration"))
        return cls(
            format_version=str(document.get("format_version", "")),
            tool_version=str(
                document.get("terraform_version") or document.get("tofu_version") or ""
            ),
            resources=resources,
            references=references,
            raw=document,
        )

    @classmethod
    def from_file(cls, path: Path) -> PlanFacts:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PlanParseError(f"{path}: {exc}") from exc
        return cls.from_dict(raw)

    # -- queries ---------------------------------------------------------

    def by_type(self, *types: str) -> tuple[Resource, ...]:
        wanted = set(types)
        return tuple(r for r in self.resources if r.type in wanted)

    def get(self, address: str) -> Resource | None:
        resource = self._by_address.get(address)
        if resource is not None:
            return resource
        # A configuration address ("aws_subnet.kernel_a") may correspond to an
        # indexed planned address ("aws_subnet.kernel_a[0]") under count/for_each.
        for candidate in self.resources:
            if candidate.address.startswith(f"{address}[") or candidate.address == address:
                return candidate
        return None

    def all_matching(self, address: str) -> tuple[Resource, ...]:
        return tuple(
            r for r in self.resources if r.address == address or r.address.startswith(f"{address}[")
        )

    def references(self, address: str, attribute: str) -> tuple[str, ...]:
        """Raw configuration references for ``address.attribute``."""
        base = _strip_index(address)
        return self._references.get(base, {}).get(attribute, ())

    def referenced_resources(
        self, address: str, attribute: str
    ) -> tuple[tuple[Resource, ...], tuple[str, ...]]:
        """Resolve ``address.attribute`` references to resources.

        Returns ``(resolved, unresolvable)``. ``unresolvable`` holds references
        that point at variables, locals or iteration values — things a plan
        cannot follow. A caller that ignores the second element is writing a
        check that passes by absence.
        """
        resolved: list[Resource] = []
        unresolvable: list[str] = []
        for raw in self.references(address, attribute):
            target = _normalise_reference(raw)
            if target is None:
                unresolvable.append(raw)
                continue
            matches = self.all_matching(target)
            if matches:
                resolved.extend(matches)
            else:
                unresolvable.append(raw)
        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: list[Resource] = []
        for resource in resolved:
            if resource.address not in seen:
                seen.add(resource.address)
                unique.append(resource)
        return tuple(unique), tuple(dict.fromkeys(unresolvable))

    def resolve_attribute_resources(
        self, resource: Resource, attribute: str, *, target_types: Sequence[str] = ()
    ) -> tuple[tuple[Resource, ...], tuple[str, ...]]:
        """Resolve an attribute to resources by value **or** by reference.

        Order matters: a concrete value (an ARN or an id that is already known) is
        matched against resource ``arn``/``id`` values first; otherwise the
        configuration reference graph is used. If neither yields anything the
        second element of the tuple explains why, and it is never empty when the
        first is.
        """
        value = resource.get(attribute)
        candidates = self.by_type(*target_types) if target_types else self.resources
        if isinstance(value, str) and value:
            hits = tuple(
                c for c in candidates if value in {c.get("arn"), c.get("id"), c.get("name")}
            )
            if hits:
                return hits, ()
        if isinstance(value, list) and value:
            hits = tuple(
                c
                for c in candidates
                if c.get("id") in value or c.get("arn") in value or c.get("name") in value
            )
            if hits:
                return hits, ()
        resolved, unresolvable = self.referenced_resources(resource.address, attribute)
        if target_types:
            wanted = set(target_types)
            filtered = tuple(r for r in resolved if r.type in wanted)
            dropped = tuple(
                f"{r.address} (type {r.type})" for r in resolved if r.type not in wanted
            )
            resolved, unresolvable = filtered, (*unresolvable, *dropped)
        if resolved:
            return resolved, unresolvable
        if not unresolvable:
            detail = (
                f"attribute {attribute!r} is absent from the plan"
                if value is None and not resource.is_unknown(attribute)
                else f"attribute {attribute!r} is known-after-apply and has no configuration "
                "reference to follow"
            )
            return (), (detail,)
        return (), unresolvable

    def __iter__(self) -> Iterator[Resource]:
        return iter(self.resources)

    def __len__(self) -> int:
        return len(self.resources)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _walk_module(
    module: Mapping[str, Any],
    *,
    module_address: str,
    unknowns: Mapping[str, Mapping[str, Any]],
) -> Iterator[Resource]:
    for entry in module.get("resources") or ():
        if not isinstance(entry, Mapping):
            continue
        address = str(entry.get("address", ""))
        if not address:
            continue
        raw_values = entry.get("values")
        values: Mapping[str, Any] = raw_values if isinstance(raw_values, Mapping) else {}
        yield Resource(
            address=address,
            type=str(entry.get("type", "")),
            name=str(entry.get("name", "")),
            module_address=module_address,
            values=values,
            unknown=unknowns.get(address, {}),
            mode=str(entry.get("mode", "managed")),
        )
    for child in module.get("child_modules") or ():
        if not isinstance(child, Mapping):
            continue
        yield from _walk_module(
            child,
            module_address=str(child.get("address", module_address)),
            unknowns=unknowns,
        )


def _unknown_map(resource_changes: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    if not isinstance(resource_changes, list):
        return out
    for entry in resource_changes:
        if not isinstance(entry, Mapping):
            continue
        address = str(entry.get("address", ""))
        change = entry.get("change")
        if not address or not isinstance(change, Mapping):
            continue
        after_unknown = change.get("after_unknown")
        if isinstance(after_unknown, Mapping):
            out[address] = after_unknown
    return out


def _configuration_references(
    configuration: Any,
) -> dict[str, dict[str, tuple[str, ...]]]:
    out: dict[str, dict[str, tuple[str, ...]]] = {}
    if not isinstance(configuration, Mapping):
        return out
    root = configuration.get("root_module")
    if isinstance(root, Mapping):
        _collect_module_references(root, prefix="", out=out)
    return out


def _collect_module_references(
    module: Mapping[str, Any], *, prefix: str, out: dict[str, dict[str, tuple[str, ...]]]
) -> None:
    for entry in module.get("resources") or ():
        if not isinstance(entry, Mapping):
            continue
        address = str(entry.get("address", ""))
        if not address:
            continue
        full = f"{prefix}{address}"
        expressions = entry.get("expressions")
        if not isinstance(expressions, Mapping):
            continue
        table = out.setdefault(full, {})
        for attribute, expression in expressions.items():
            refs = _expression_references(expression)
            if refs:
                table[str(attribute)] = refs
    module_calls = module.get("module_calls")
    if isinstance(module_calls, Mapping):
        for call_name, call in module_calls.items():
            if not isinstance(call, Mapping):
                continue
            inner = call.get("module")
            if isinstance(inner, Mapping):
                _collect_module_references(inner, prefix=f"{prefix}module.{call_name}.", out=out)


def _expression_references(expression: Any) -> tuple[str, ...]:
    """Collect ``references`` from an expression, including nested blocks."""
    found: list[str] = []
    stack: list[Any] = [expression]
    while stack:
        node = stack.pop()
        if isinstance(node, Mapping):
            refs = node.get("references")
            if isinstance(refs, list):
                found.extend(str(r) for r in refs)
            for key, value in node.items():
                if key != "references":
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return tuple(dict.fromkeys(found))


_UNRESOLVABLE_PREFIXES = ("var.", "local.", "each.", "count.", "path.", "terraform.", "self.")


def _normalise_reference(raw: str) -> str | None:
    """``"aws_iam_policy.kernel_boundary.arn"`` → ``"aws_iam_policy.kernel_boundary"``.

    Returns ``None`` for anything a plan cannot follow to a resource.
    """
    text = raw.strip()
    if not text or text.startswith(_UNRESOLVABLE_PREFIXES):
        return None
    parts = text.split(".")
    if parts[0] == "data":
        if len(parts) < 3:
            return None
        return ".".join(parts[:3])
    if parts[0] == "module":
        # module.foo.aws_x.y → keep the module-qualified resource address
        if len(parts) < 4:
            return None
        return ".".join(parts[:4])
    if len(parts) < 2:
        return None
    if not parts[0].startswith(("aws_", "awscc_", "null_", "random_", "tls_")):
        return None
    return ".".join(parts[:2])


def _strip_index(address: str) -> str:
    return address.split("[", 1)[0]
