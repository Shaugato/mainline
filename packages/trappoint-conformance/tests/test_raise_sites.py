# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The exhibit registry is grounded in the SQL it claims to describe.

``cases/_exhibit.py`` recovers the raising object for a ``P0001`` from a registry of message
fragments. A registry that had drifted from the migrations would be worse than no registry
at all: it would confer confidence on a stale mapping, and every ``P0001`` exhibit in the
suite would be an assertion about a function that no longer raises that sentence.

So the registry is checked against both trees, in both directions, with no cluster involved:

* every registered ``(object, fragment)`` pair appears inside that object's own definition;
* every ``RAISE … MESSAGE`` in either tree is matched by at least one registry entry.

The second is the one that catches growth. A new guard with a new sentence is invisible to
the first assertion and fails the second the day it lands, which is the day somebody still
remembers what it does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from cases._exhibit import MANIFEST_NAMESPACE, SITES, resolve_object, split_message

from trappoint_conformance.manifest import Manifest

_OBJECT = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+([a-z0-9_]+)\.([a-z0-9_]+)",
    re.IGNORECASE,
)
_MESSAGE = re.compile(r"MESSAGE\s*=\s*'((?:[^']|'')*)'")

TREES = (
    Path("packages/trappoint-sql/refvertical/sql"),
    Path("verticals/mainline/db/migrations"),
)


def _definitions(repo_root: Path) -> dict[str, list[str]]:
    """Map every raising object's local name to the message bodies it raises."""
    found: dict[str, list[str]] = {}
    for tree in TREES:
        directory = repo_root / tree
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            match = _OBJECT.search(text)
            if match is None:
                continue
            local = match.group(2)
            for raw in _MESSAGE.findall(text):
                _, body = split_message(raw)
                found.setdefault(local, []).append(body)
    return found


def test_every_registered_site_exists_in_the_migrations(repo_root: Path) -> None:
    """No entry in the registry describes a RAISE that is not there."""
    definitions = _definitions(repo_root)
    if not definitions:
        pytest.skip("SKIP WITH REASON: no migration tree in this checkout to ground against")
    orphans = [
        f"{site.obj}: {site.fragment!r}"
        for site in SITES
        if not any(site.fragment in body for body in definitions.get(site.obj, ()))
    ]
    assert not orphans, (
        "These registry entries describe a RAISE the migrations do not contain:\n  "
        + "\n  ".join(orphans)
        + "\n\nA registry that has drifted from the SQL is worse than no registry: it "
        "confers confidence on a stale mapping."
    )


def test_every_raise_in_the_tree_is_registered(repo_root: Path) -> None:
    """No guard raises a sentence the resolver cannot attribute."""
    definitions = _definitions(repo_root)
    if not definitions:
        pytest.skip("SKIP WITH REASON: no migration tree in this checkout to ground against")
    unknown: list[str] = []
    for local, bodies in definitions.items():
        for body in bodies:
            if not any(site.fragment in body for site in SITES if site.obj == local):
                unknown.append(f"{local}: {body[:90]!r}")
    assert not unknown, (
        "These RAISE sites are not in cases/_exhibit.py, so a case refused by one of them "
        "would report EXHIBIT UNRESOLVED:\n  " + "\n  ".join(sorted(set(unknown)))
    )


def test_ambiguous_fragments_carry_a_relation() -> None:
    """Where two objects share a sentence, both entries declare their relation."""
    by_fragment: dict[str, set[str]] = {}
    for site in SITES:
        by_fragment.setdefault((site.prefix, site.fragment), set()).add(site.obj)  # type: ignore[arg-type]
    for key, objects in by_fragment.items():
        if len(objects) < 2:
            continue
        for site in SITES:
            if (site.prefix, site.fragment) == key:
                assert site.relation, (
                    f"{site.obj} shares the message {site.fragment!r} with "
                    f"{sorted(objects - {site.obj})} and declares no relation. The "
                    f"resolver refuses to pick: an exhibit chosen by tie-break is not an "
                    f"exhibit."
                )


def test_manifest_p0001_exhibits_use_the_manifest_namespace(manifest: Manifest) -> None:
    """Every P0001 exhibit is written in one namespace, whatever the profile."""
    wrong = [
        f"{case.id}: {case.expect_constraint}"
        for case in manifest.cases
        if case.expect_sqlstate == "P0001"
        and not case.expect_constraint.startswith(f"{MANIFEST_NAMESPACE}.")
    ]
    assert not wrong, (
        f"These P0001 exhibits are not in the {MANIFEST_NAMESPACE!r} namespace:\n  "
        + "\n  ".join(wrong)
        + "\n\ncases/_exhibit.py re-homes every resolved object into that namespace "
        "because the manifest is one document and the schema is a property of the "
        "binding. An exhibit written in another namespace can never match."
    )


def test_resolution_refuses_an_unregistered_message() -> None:
    """An unknown sentence resolves to nothing rather than to something plausible."""
    from cases._exhibit import ExhibitUnresolved

    with pytest.raises(ExhibitUnresolved):
        resolve_object("MAINLINE: a sentence no migration in this repository contains")
    with pytest.raises(ExhibitUnresolved):
        resolve_object("this message has no prefix at all")


def test_ambiguous_message_without_a_relation_refuses() -> None:
    """The shared event-chain sentence is refused, not guessed, when unqualified."""
    from cases._exhibit import ExhibitUnresolved

    shared = "MAINLINE: prev_digest does not match the predecessor chain digest"
    with pytest.raises(ExhibitUnresolved):
        resolve_object(shared)
    assert resolve_object(shared, relation="permit_event")[0] == "fn_permit_event_chain"
    assert resolve_object(shared, relation="cr_event")[0] == "fn_cr_event_chain"


def test_a_self_naming_message_is_reported_not_inferred() -> None:
    """The merge gate names itself, and the resolver records that it was reported."""
    obj, self_named = resolve_object(
        "TRAPPOINT_REF: merge refused by trappoint_ref.fn_permit_merge_gate — because"
    )
    assert obj == "fn_permit_merge_gate"
    assert self_named, (
        "the merge gate spells its own name into the message, so the exhibit is REPORTED "
        "rather than inferred and must not be flagged as weakened"
    )
