# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""THE CODE DEMANDS; THE MATRIX GRANTS. NOTHING COMPARED THEM UNTIL THIS FILE.

The demo's Function URL is ``authorization_type = NONE`` by the founder's explicit
choice, so every anonymous caller in the world executes as one SQL login: ``mainline_api``.
What that login may reach is therefore the entire authorisation surface of this product,
and until 2026-08-15 it was decided in one place and asserted in none.

WHAT WENT WRONG, MEASURED, AND WHY A TEST AND NOT A FIX
-------------------------------------------------------
``docs/leads/grants-in-migrations-plan.md`` R4: thirty-nine schema-qualified relations are
referenced by the shipping demo-api source, and **eleven of them are named nowhere in
``scripts/deploy/cloud_roles.py``** — ``mainline.control_failure``,
``mainline.defeater_option``, ``mainline.delta_witness``, ``mainline.event_edge``,
``mainline.ledger_leaf``, ``mainline.ledger_node``, ``mainline.receipt_expiry``,
``mainline_meas.silence_ledger``, ``trappoint.deploy_chain``,
``trappoint.schema_attestation``, ``trappoint.schema_migration``. Those are precisely the
grants ``evidence/deploy/LIVE.md:60-64`` records as issued BY HAND against the live
cluster on 2026-08-14, after five separate outages. The cluster was repaired; the
repository never was. Re-running ``cloud_roles.py`` against a fresh cluster today would
reproduce all five.

Eight grants is the instance. **The class is that no comparison existed**, and a
comparison that runs in milliseconds with no cluster would have been red before the first
deploy. That is what this file is: Leg A of the plan's R7. Leg B —
``tests/integration/schema/test_privilege_conformance.py`` — asks the database instead,
because ``GRANTS.yaml``'s own header is unambiguous that behaviour, not intent, is the
control: *a GRANT is a claim about intent, a 42501 is evidence about behaviour*.

NEITHER LIST IS WRITTEN DOWN HERE
---------------------------------
The precedent is ``test_seed_covers_every_console_resource.py`` and its discipline is
binding: *a second copy of a list is a second thing to drift*, and drift between two
copies of THIS list is the exact defect the file is about. So:

* the demand comes from :mod:`mainline_boundary.sqlrefs`, which parses the SQL out of the
  shipping source with two independent extraction legs that must agree;
* the reach comes from ``GRANTS.yaml``, read through
  :mod:`trappoint_migrate.grants` — the parser the applier itself uses — and never through
  a second YAML reader. What is compared is the STATEMENTS ``grants apply`` would issue,
  so a section the matrix declares and ``apply_order`` never applies grants nothing here
  either, which is the truth on the cluster.

:func:`test_the_census_is_not_vacuous` runs first in reading order for the same reason the
console file re-runs ``resources.ts``'s own module-load assertion: a scanner that finds
nothing certifies a clean privilege surface, and that is a worse outcome than a red.

THE DIFFERENCE IS COMPUTED IN BOTH DIRECTIONS, AND THEY ARE NOT THE SAME QUESTION
---------------------------------------------------------------------------------
**Demanded but not granted** is asserted at ``(relation, verb)``. R4b is why:
``transitions.py:891`` issues ``INSERT INTO mainline.exposure_receipt`` and
``transitions.py:969`` issues ``INSERT INTO mainline.exposure_line``; both relations
appear in ``cloud_roles.API_READ``, which grants ``SELECT``, and in no write list. A
census that compared names only would call that satisfied.

**Granted but never demanded** is computed over grants written directly to
``mainline_api`` — inherited ones belong to the role that holds them — in both of its
shapes: a whole relation no statement names, and a verb beyond what the source issues on a
relation it does name. What it is JUDGED by is R4's own criterion, *a row you cannot
justify does not go in*, and not by the scan alone. The reason is measured rather than
assumed: every trigger function in migrations 0100-0149 executes as the INVOKING role and
none is ``SECURITY DEFINER``, so ``mainline.merge_permit``'s trigger chain reaches
relations this application names in no statement of its own.
``cloud_roles.API_GATE_READ`` is ten of them and its comment says outright that they were
*discovered by running it*. A census that called those over-grants would be inviting
somebody to delete a privilege the gate needs, mid-demo, in front of a judge. So a grant
the source does not issue must carry its reasoning **in the matrix**, where
``grants apply`` and ``cloud_roles.py``'s per-statement note can repeat it back to an
operator; one that carries none is red, and Leg B's probe is what decides whether a
justified one is truly reachable.

WHY THIS IS RED TODAY, AND WHAT IT MAY NOT DO ABOUT THAT
--------------------------------------------------------
``GRANTS.yaml`` declares nineteen roles and ``mainline_api`` is not among them (R3). Until
W2 lands, every assertion here fails naming W2's deliverable. **That is the intended
sequence and it is never a skip**: a skip here is indistinguishable from a deleted test,
and the whole wave exists because a privilege surface nobody asserted anything about
shipped to a public URL. This file may not add a grant, may not edit ``GRANTS.yaml`` or
``cloud_roles.py``, and may not narrow a difference to obtain a green. A non-empty
difference is the finding.
"""

from __future__ import annotations

import functools
import re
import sys
import tempfile
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pytest

from conftest import REPO_ROOT

# `packages/*/src` is on `sys.path` for the workspace packages this suite already imports;
# `mainline_boundary` inserts its own source root at import time (see its `__init__`), so
# this is belt and braces for a bare checkout rather than a second mechanism.
_BOUNDARY_SRC: Final = REPO_ROOT / "packages/mainline-boundary/src"
if _BOUNDARY_SRC.is_dir() and str(_BOUNDARY_SRC) not in sys.path:
    sys.path.insert(0, str(_BOUNDARY_SRC))
_MIGRATE_SRC: Final = REPO_ROOT / "packages/trappoint-migrate/src"
if _MIGRATE_SRC.is_dir() and str(_MIGRATE_SRC) not in sys.path:
    sys.path.insert(0, str(_MIGRATE_SRC))

from yaml import YAMLError  # noqa: E402

from mainline_boundary.sqlrefs import (  # noqa: E402
    MINIMUM_LITERAL_RELATIONS,
    MINIMUM_RESOLVED_RELATIONS,
    MINIMUM_ROUTINE_DEMANDS,
    PRIVILEGED_SCHEMAS,
    RefScan,
    check_sql_reference_census,
)
from trappoint_migrate import grants as grants_module  # noqa: E402
from trappoint_migrate.errors import UsageError  # noqa: E402

# `yaml` is imported for its EXCEPTION TYPE and for nothing else. The parse itself goes
# through `trappoint_migrate.grants`, which is the parser `trappoint migrate grants apply`
# uses; naming the error class here is what lets a malformed matrix arrive as a sentence
# an operator can act on rather than as a scanner traceback fifty frames deep.

#: The login the Lambda connects as, and therefore the login an anonymous caller on the
#: public Function URL executes as. `scripts/deploy/cloud_roles.py:104` names it.
API_ROLE: Final = "mainline_api"

#: The matrix. One file, applied idempotently by `trappoint migrate grants apply`.
GRANTS_YAML: Final = REPO_ROOT / "verticals/mainline/db/GRANTS.yaml"

#: What to say when the role is not there yet. Named explicitly, because "the test failed"
#: is not an instruction and this failure has exactly one owner.
W2_DELIVERABLE: Final = (
    "W2 owns verticals/mainline/db/GRANTS.yaml and its brief is "
    "docs/leads/grants-in-migrations-plan.md §3 (W2 — THE MATRIX): declare `mainline_api` "
    "and `mainline_judge` as first-class roles with `login: true`, carrying every "
    "privilege scripts/deploy/cloud_roles.py currently issues (API_READ, API_GATE_READ, "
    "API_WRITE, AUDIT_VIEWS, API_MEMBERSHIPS) PLUS the eleven relations of R4 that no code "
    "in this repository grants, plus USAGE ON SCHEMA trappoint. Until that lands this file "
    "is RED BY SEQUENCE, and it will not skip: a skip here is indistinguishable from a "
    "deleted test, and a privilege surface nobody asserts anything about is what shipped "
    "to a public URL on 2026-08-14."
)

#: S14. `mainline_qa` is scanned by the census precisely so that a demo-api statement
#: naming it produces a finding rather than a grant request.
FORBIDDEN_SCHEMA: Final = "mainline_qa"

#: `trappoint` is created by `trappoint migrate bootstrap`, not by this vertical's
#: migrations, which is why GRANTS.yaml's `schemas:` key does not name it — and why R6
#: records `USAGE ON SCHEMA trappoint` as a row the matrix is missing.
BOOTSTRAP_SCHEMA: Final = "trappoint"


# ═════════════════════════════════════════════════════════════════════════════════════
# The demand: what the shipping source issues SQL for.
# ═════════════════════════════════════════════════════════════════════════════════════


@functools.cache
def _census() -> tuple[RefScan, Any]:
    return check_sql_reference_census(REPO_ROOT)


def _scan() -> RefScan:
    return _census()[0]


# ═════════════════════════════════════════════════════════════════════════════════════
# The reach: what GRANTS.yaml would actually issue, parsed back off the statements.
# ═════════════════════════════════════════════════════════════════════════════════════
#
# The statements and not the document, deliberately. `apply_order` is authoritative and a
# section the matrix declares but never orders is REPORTED and not applied
# (`GrantPlan.unapplied_sections`); reading the document directly would credit
# `mainline_api` with privileges no cluster would ever hold. `plan()` also validates every
# identifier and every privilege against its closed set, so a malformed matrix arrives
# here as a UsageError naming the row rather than as a quietly shorter list.

_CREATE_ROLE: Final = re.compile(
    r"^CREATE ROLE IF NOT EXISTS (?P<name>\S+) (?P<login>LOGIN|NOLOGIN)$"
)
_MEMBERSHIP: Final = re.compile(
    r"^GRANT (?P<role>[a-z_][a-z0-9_]*) TO (?P<member>[a-z_][a-z0-9_]*)$"
)
_ALL_TABLES: Final = re.compile(
    r"^GRANT (?P<privs>.+?) ON ALL TABLES IN SCHEMA (?P<schema>\S+) TO (?P<role>\S+)$"
)
_ON_SCHEMA: Final = re.compile(
    r"^GRANT (?P<privs>.+?) ON SCHEMA (?P<schemas>.+?) TO (?P<role>\S+)$"
)
_ON_TABLE: Final = re.compile(r"^GRANT (?P<privs>.+?) ON TABLE (?P<object>\S+) TO (?P<role>\S+)$")
_ON_ROUTINE: Final = re.compile(
    r"^GRANT (?P<privs>.+?) ON (?:PROCEDURE|FUNCTION|ROUTINE) "
    r"(?P<object>[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s*(?:\([^)]*\))? TO (?P<role>\S+)$"
)
_DEFAULTS: Final = re.compile(
    r"^ALTER DEFAULT PRIVILEGES FOR ROLE \S+ IN SCHEMA (?P<schema>\S+) "
    r"GRANT (?P<privs>.+?) ON (?P<object_type>\S+) TO (?P<role>\S+)$"
)
_REVOKE: Final = re.compile(
    r"^REVOKE (?P<privs>.+?) ON (?P<object_type>SCHEMA|TABLE|DATABASE|ALL TABLES IN SCHEMA) "
    r"(?P<objects>.+?) FROM (?P<grantee>\S+)$"
)


class Reach:
    """What ``grants apply`` would leave ``mainline_api`` holding, and where each bit came from."""

    def __init__(self) -> None:
        self.declared_roles: set[str] = set()
        self.logins: set[str] = set()
        self.member_of: dict[str, set[str]] = {}
        self.schema_usage: dict[tuple[str, str], set[str]] = {}
        self.on_table: dict[tuple[str, str], set[str]] = {}
        self.on_routine: dict[tuple[str, str], set[str]] = {}
        self.schema_wide: dict[tuple[str, str], set[str]] = {}
        self.future_only: list[str] = []
        self.unrecognised: list[str] = []

    # -- queries ---------------------------------------------------------

    def closure(self, role: str) -> frozenset[str]:
        """*role* plus every role it is a member of, transitively.

        Membership is not decoration. ``cloud_roles.py`` makes ``mainline_api`` a member of
        ``auditor_ro``, ``agent_gate`` and ``svc_disposition`` for RLS policy scope, and a
        member inherits the granted role's privileges as well — so a census that ignored
        the closure would report privileges as missing that the login in fact holds, and
        an operator acting on that report would add grants nobody needs.
        """
        seen = {role}
        frontier = [role]
        while frontier:
            for parent in sorted(self.member_of.get(frontier.pop(), set())):
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)
        return frozenset(seen)

    def privileges_on(self, role: str, qualified: str) -> frozenset[str]:
        schema = qualified.split(".", 1)[0]
        held: set[str] = set()
        for member in self.closure(role):
            held |= self.on_table.get((member, qualified), set())
            held |= self.on_routine.get((member, qualified), set())
            held |= self.schema_wide.get((member, schema), set())
        return frozenset(held)

    def covers(self, role: str, qualified: str, verb: str) -> bool:
        held = self.privileges_on(role, qualified)
        return verb in held or "ALL" in held

    def has_schema_usage(self, role: str, schema: str) -> bool:
        return any(
            {"USAGE", "ALL"} & self.schema_usage.get((member, schema), set())
            for member in self.closure(role)
        )

    def directly_granted_objects(self, role: str) -> dict[str, frozenset[str]]:
        """Objects named in a row whose ``role:`` IS *role* — the surface an over-grant lands on.

        Inherited privileges are excluded on purpose. ``auditor_ro``'s schema-wide SELECT
        exists for the human auditors, and calling it an over-grant *on mainline_api* would
        be a sentence about the wrong role. What this returns is what W2 and W3 write.
        """
        out: dict[str, set[str]] = {}
        for (owner, obj), privileges in (*self.on_table.items(), *self.on_routine.items()):
            if owner == role:
                out.setdefault(obj, set()).update(privileges)
        # An entry emptied by a REVOKE — or created by one that named an object never
        # granted — is not a grant. Reporting it as an over-grant with no privileges beside
        # it would send an operator looking for a row that is not there.
        return {obj: frozenset(privs) for obj, privs in sorted(out.items()) if privs}

    def directly_granted_wildcards(self, role: str) -> tuple[str, ...]:
        return tuple(sorted(schema for (owner, schema) in self.schema_wide if owner == role))


def _privileges(text: str) -> set[str]:
    return {part.strip().upper() for part in text.split(",") if part.strip()}


def _add(
    table: dict[tuple[str, str], set[str]], key: tuple[str, str], privileges: set[str]
) -> None:
    table.setdefault(key, set()).update(privileges)


def _apply_revocation(reach: Reach, match: re.Match[str]) -> None:
    """Subtract a revocation. ``FROM public`` never subtracts an explicit grant.

    ``public`` is the pseudo-role every login implicitly belongs to; revoking from it
    removes an implicit privilege and leaves an explicit ``GRANT … TO mainline_api``
    exactly where it was. Modelling it as a subtraction would understate the reach, which
    is the direction that makes an over-grant invisible.
    """
    grantee = match.group("grantee")
    if grantee == "public":
        return
    privileges = _privileges(match.group("privs"))
    object_type = match.group("object_type").upper()

    def strip(held: set[str]) -> None:
        # `REVOKE ALL` takes everything, including privileges it does not enumerate. A
        # set-difference against the literal token "ALL" would leave SELECT standing and
        # report reach the login does not have, which is the direction that hides an
        # over-grant rather than inventing one.
        if "ALL" in privileges:
            held.clear()
        else:
            held.difference_update(privileges)

    for name in (o.strip() for o in match.group("objects").split(",")):
        if object_type in {"SCHEMA", "ALL TABLES IN SCHEMA"}:
            strip(reach.schema_usage.setdefault((grantee, name), set()))
            strip(reach.schema_wide.setdefault((grantee, name), set()))
            for owner, obj in list(reach.on_table):
                if owner == grantee and obj.startswith(f"{name}."):
                    strip(reach.on_table[(owner, obj)])
            for owner, obj in list(reach.on_routine):
                if owner == grantee and obj.startswith(f"{name}."):
                    strip(reach.on_routine[(owner, obj)])
        elif object_type == "TABLE":
            strip(reach.on_table.setdefault((grantee, name), set()))


def _build_reach(statements) -> Reach:
    reach = Reach()
    for statement in statements:
        sql = statement.sql.strip()
        if (match := _CREATE_ROLE.match(sql)) is not None:
            reach.declared_roles.add(match.group("name"))
            if match.group("login") == "LOGIN":
                reach.logins.add(match.group("name"))
        elif (match := _MEMBERSHIP.match(sql)) is not None:
            reach.member_of.setdefault(match.group("member"), set()).add(match.group("role"))
        elif (match := _ALL_TABLES.match(sql)) is not None:
            _add(
                reach.schema_wide,
                (match.group("role"), match.group("schema")),
                _privileges(match.group("privs")),
            )
        elif (match := _ON_SCHEMA.match(sql)) is not None:
            for schema in (s.strip() for s in match.group("schemas").split(",")):
                _add(
                    reach.schema_usage,
                    (match.group("role"), schema),
                    _privileges(match.group("privs")),
                )
        elif (match := _ON_TABLE.match(sql)) is not None:
            _add(
                reach.on_table,
                (match.group("role"), match.group("object")),
                _privileges(match.group("privs")),
            )
        elif (match := _ON_ROUTINE.match(sql)) is not None:
            _add(
                reach.on_routine,
                (match.group("role"), match.group("object")),
                _privileges(match.group("privs")),
            )
        elif (match := _DEFAULTS.match(sql)) is not None:
            # ALTER DEFAULT PRIVILEGES governs objects created AFTER it runs. It grants
            # nothing on a relation that already exists, so it may not satisfy a demand;
            # it is recorded so that "the matrix says SELECT" and "the login can read it"
            # do not get confused for one another.
            reach.future_only.append(sql)
        elif (match := _REVOKE.match(sql)) is not None:
            _apply_revocation(reach, match)
        else:
            reach.unrecognised.append(sql)
    return reach


def _unreadable(action: str, exc: Exception) -> AssertionError:
    """Turn a matrix that will not parse into a sentence instead of a parser traceback.

    A ``yaml.ScannerError`` fifty frames deep tells a reader that PyYAML has opinions. It
    does not tell them which file, which owner, or that every assertion below is now
    asserting nothing. This does.
    """
    return AssertionError(
        f"{GRANTS_YAML} could not be {action}: {type(exc).__name__}: {exc}\n\n"
        "The privilege census compares two documents and this is one of them, so a matrix "
        "that does not parse is not a precondition failure — it is the whole comparison "
        "silently ceasing to exist. `trappoint migrate grants apply` reads this file with "
        "the same parser and would refuse it too, which means a cluster provisioned from "
        f"the current tree would hold no grants at all.\n\n{W2_DELIVERABLE}"
    )


@functools.cache
def _plan() -> Any:
    try:
        return grants_module.plan(GRANTS_YAML)
    except (YAMLError, UsageError) as exc:
        raise _unreadable("rendered into grant statements", exc) from exc


@functools.cache
def _reach() -> Reach:
    return _build_reach(_plan().statements)


@functools.cache
def _document() -> Mapping[str, Any]:
    try:
        return grants_module.load_matrix(GRANTS_YAML)
    except (YAMLError, UsageError) as exc:
        raise _unreadable("parsed", exc) from exc


def _plan_of_text(body: str) -> Any:
    """Render a throwaway matrix, to MEASURE what ``grants.py`` can and cannot express.

    Used where this file would otherwise have to take a claim about the renderer on trust.
    A committed comment saying "an EXECUTE row would emit the wrong statement" is a claim;
    rendering one and reading the SQL back is a measurement, and the difference is the
    whole reason this repository prefers probes to matrices.
    """
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "GRANTS.yaml"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return grants_module.plan(path)


def _role_is_declared() -> bool:
    return API_ROLE in _reach().declared_roles


def _require_the_role(what: str) -> None:
    """Fail — never skip — with W2 named, when the role the endpoint runs as is undeclared."""
    if _role_is_declared():
        return
    raise AssertionError(
        f"{what} cannot be asserted because {GRANTS_YAML.name} declares no role named "
        f"{API_ROLE!r}. That is R3 of docs/leads/grants-in-migrations-plan.md and it is the "
        "defect, not a precondition: the role an anonymous caller on "
        "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws executes "
        "as has its entire privilege surface in five Python tuples in a deploy script, "
        f"outside the declarative matrix that every other role in this system lives in.\n\n"
        f"{W2_DELIVERABLE}\n\n"
        f"Roles the matrix does declare: {', '.join(sorted(_reach().declared_roles))}."
    )


def _where(scan: RefScan, qualified: str, verb: str) -> str:
    sites = scan.sites_for(qualified, verb)
    shown = ", ".join(sites[:4])
    return shown + (f" (+{len(sites) - 4} more)" if len(sites) > 4 else "")


# ═════════════════════════════════════════════════════════════════════════════════════
# 1. The census must be worth believing before anything is diffed against it.
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_census_is_not_vacuous() -> None:
    """A scanner that finds nothing certifies a clean privilege surface. Guard it first.

    Everything below is a difference between two sets. If the left-hand set silently
    empties — a regex that stops matching, a source root that moved, a file that will not
    parse — every difference collapses and the board goes green while asserting nothing.
    So the scanner's own report is asserted here: two independent extraction legs agreeing,
    no unparseable file, no unresolved dynamic reference, and both floors cleared.
    """
    scan, report = _census()
    assert report.ok, report.summary()
    assert report.examined >= 1, report.summary()
    assert not scan.parse_failures, [f.path for f in scan.parse_failures]
    assert scan.disagreement() == (frozenset(), frozenset()), scan.disagreement()
    assert len(scan.literal_relations()) >= MINIMUM_LITERAL_RELATIONS
    assert len(scan.resolved_relations()) >= MINIMUM_RESOLVED_RELATIONS


def test_the_schemas_the_census_scans_are_the_schemas_the_matrix_declares() -> None:
    """The scanner's schema list is checked against its authority, never merely trusted.

    ``sqlrefs.PRIVILEGED_SCHEMAS`` is a constant, and a constant that nothing compares
    against a source of truth is the second copy of a list this whole wave is about. Its
    authority is ``GRANTS.yaml``'s own ``schemas:`` key, plus ``trappoint`` — created by
    ``trappoint migrate bootstrap`` rather than by this vertical, which is exactly why the
    matrix does not name it and why R6 records ``USAGE ON SCHEMA trappoint`` as missing.
    A sixth schema added to the matrix goes unscanned until somebody reads this failure.
    """
    declared = _document().get("schemas")
    assert isinstance(declared, list) and declared, (
        f"{GRANTS_YAML} no longer carries a parsable `schemas:` list, which is what the "
        "census checks its own scanned-schema constant against."
    )
    assert set(PRIVILEGED_SCHEMAS) == set(declared) | {BOOTSTRAP_SCHEMA}, (
        "mainline_boundary.sqlrefs.PRIVILEGED_SCHEMAS and GRANTS.yaml's `schemas:` have "
        f"diverged. Scanned: {sorted(PRIVILEGED_SCHEMAS)}. Matrix: {sorted(declared)} "
        f"(+ {BOOTSTRAP_SCHEMA}, the bootstrap schema). A schema the census does not scan "
        "is a schema whose grants nothing compares."
    )


def test_the_demo_api_names_no_relation_in_the_forbidden_schema() -> None:
    """S14. ``mainline_qa`` is scanned so that a reference to it is a finding, not a request.

    ``cloud_roles.py`` re-REVOKEs the schema from both logins on every run and ``--verify``
    asserts ``42501`` on it. If the shipping source ever names it, the honest outcomes are
    to delete the statement or to change S14 deliberately — never to grant it.
    """
    offenders = sorted(d for d in _scan().demands if d.schema == FORBIDDEN_SCHEMA)
    assert not offenders, (
        f"the demo-api source issues SQL against schema {FORBIDDEN_SCHEMA!r}, which S14 says "
        "neither demo login may ever reach:\n"
        + "\n".join(f"  {d.qualified} {d.verb}  <- {d.where}" for d in offenders)
        + "\nDo not close this by granting the schema."
    )


def test_the_matrix_statement_vocabulary_is_fully_understood() -> None:
    """Every statement ``grants apply`` would issue is one this census can read.

    A shape this file does not recognise contributes NOTHING to the computed reach, so an
    unrecognised ``GRANT`` would show up below as a missing privilege and an unrecognised
    ``REVOKE`` would show up as reach the login does not have. Both are wrong answers
    delivered confidently, which is worse than a red.
    """
    reach = _reach()
    assert not reach.unrecognised, (
        "GRANTS.yaml renders statement shapes this census cannot parse, so the reach it "
        "computes is incomplete and every difference below is unreliable:\n"
        + "\n".join(f"  {sql}" for sql in reach.unrecognised)
        + "\nTeach test_privilege_census.py the shape; do not delete the statement."
    )
    assert _plan().statements, f"{GRANTS_YAML} rendered no statements at all"
    assert reach.declared_roles, "the matrix declared no roles at all"


# ═════════════════════════════════════════════════════════════════════════════════════
# 2. The role itself. R3 — this is the finding the brief did not name.
# ═════════════════════════════════════════════════════════════════════════════════════


def test_grants_yaml_declares_the_role_the_public_endpoint_runs_as() -> None:
    """``mainline_api`` must be a first-class role in the matrix, with ``login: true``."""
    _require_the_role("the privilege census")
    assert API_ROLE in _reach().logins, (
        f"{GRANTS_YAML.name} declares {API_ROLE!r} with `login: false`. The Lambda connects "
        "as this role over the wire; a NOLOGIN role cannot authenticate, so the matrix "
        "would render a cluster the demo cannot reach. The credential itself stays in "
        "scripts/deploy/cloud_roles.py and never enters this file."
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# 3. Demanded but not granted — today's outage, in both of its shapes.
# ═════════════════════════════════════════════════════════════════════════════════════


def test_every_schema_the_demo_api_names_carries_usage_for_the_api_role() -> None:
    """``USAGE`` is the right to NAME a schema, and without it every grant inside is inert.

    R6 records this as a real gap: ``cloud_roles.py`` issues ``GRANT EXECUTE ON PROCEDURE
    mainline.merge_permit`` and never grants ``USAGE ON SCHEMA trappoint``, so the health
    endpoint's three ``trappoint.*`` reads depend on a privilege nothing declares.
    """
    _require_the_role("schema USAGE for the demo API role")
    scan, reach = _scan(), _reach()
    missing = sorted(
        {d.schema for d in scan.demands if not reach.has_schema_usage(API_ROLE, d.schema)}
    )
    assert not missing, (
        f"{API_ROLE} issues SQL against {len(missing)} schema(s) it holds no USAGE on:\n"
        + "\n".join(
            f"  SCHEMA {schema:<16} <- e.g. "
            + ", ".join(sorted({d.where for d in scan.demands if d.schema == schema})[:3])
            for schema in missing
        )
        + "\n\nUSAGE is the right to name a schema. Without it every table grant inside it "
        "is unusable and the statement returns 42501 naming the SCHEMA, not the table — "
        f"which is why the fix is a `schema_privileges` row in {GRANTS_YAML.name} and not a "
        "table grant. W2 owns that file."
    )


def test_every_relation_the_demo_api_reads_or_writes_is_reachable_by_the_api_role() -> None:
    """The direction that took the demo down five times on 2026-08-14.

    Asserted at ``(relation, verb)``. R4b is why the verb is carried: granting ``SELECT``
    where an ``INSERT`` is issued looks identical to a satisfied demand from a
    name-only comparison, and identical to a working deployment right up until a judge
    drives the path.
    """
    _require_the_role("what the demo API role must be able to reach")
    scan, reach = _scan(), _reach()
    missing = sorted(
        {
            d.pair
            for d in scan.demands
            # EXECUTE is not a table privilege and the matrix's grammar cannot spell a
            # routine signature; that whole class has its own test below, so that a red
            # here always means a missing TABLE grant and can say so without qualification.
            if d.verb != "EXECUTE" and not reach.covers(API_ROLE, d.qualified, d.verb)
        }
    )
    assert not missing, (
        f"{API_ROLE} issues {len(missing)} statement(s) it holds no privilege for. Every "
        "one of these is a 42501 the moment the path is driven, on an endpoint any stranger "
        "can call:\n\n"
        + "\n".join(
            f"  {qualified:<34} {verb:<7} <- {_where(scan, qualified, verb)}"
            for qualified, verb in missing
        )
        + f"\n\nThe demand is parsed out of the shipping source under "
        "verticals/mainline/apps/demo-api/src/mainline_demo_api/ by "
        "mainline_boundary.sqlrefs; the reach is what `trappoint migrate grants apply` "
        f"would issue from {GRANTS_YAML.name}. Add the missing rows to the MATRIX (W2 owns "
        "it) — do not add them to scripts/deploy/cloud_roles.py, which is the second copy "
        "of this list that drifted eleven relations behind the cluster it provisioned. "
        "Do not delete a demand to close this: the statement is in the shipping artefact."
    )


#: Where a routine grant is issued when the matrix cannot spell one. Read, never restated:
#: the assertion below is that the routine's NAME appears in this file, so a refactor that
#: drops it turns this test red rather than turning the demo's first beat into a 42501.
CLOUD_ROLES_PY: Final = REPO_ROOT / "scripts/deploy/cloud_roles.py"


def test_every_routine_the_demo_api_calls_holds_execute_from_some_authority_here() -> None:
    """``CALL mainline.merge_permit(…)`` and ``SELECT trappoint.explain_refusal(…)``.

    EXECUTE is the one demand ``GRANTS.yaml`` structurally cannot carry, and that is
    MEASURED here rather than taken from the file's own comment: ``grants.py`` renders
    ``table_privileges`` as ``GRANT … ON TABLE``, and its identifier grammar is lower_snake
    with at most one dot, so it can spell ``mainline.merge_permit`` and cannot spell the
    argument list CockroachDB needs to disambiguate an overload. Both facts are asserted
    below by rendering probe matrices through the public ``plan()``.

    So the claim this test makes is the honest one: **the EXECUTE grant is issued
    somewhere this repository declares it**, and NOT that an undeclared routine is
    refused — CockroachDB grants ``EXECUTE`` on a new function to ``public`` by default,
    measured, and the failure message carries that measurement so nobody reads a red here
    as an outage. If the matrix grows a routine builder the first branch passes and nothing
    here needs editing; until then the fallback authority is
    ``scripts/deploy/cloud_roles.py``, and a refactor that drops a routine from it goes red.
    """
    _require_the_role("EXECUTE on the routines the demo API calls")
    scan, reach = _scan(), _reach()
    routines = sorted(scan.routines())
    assert len(routines) >= MINIMUM_ROUTINE_DEMANDS, routines

    ungranted = [r for r in routines if not reach.covers(API_ROLE, r, "EXECUTE")]
    if not ungranted:
        return

    # The matrix's inability is measured, not asserted.
    probe = _plan_of_text(
        "apply_order: [roles, table_privileges]\n"
        "roles:\n  - {name: probe_role, login: true}\n"
        "table_privileges:\n"
        "  - {role: probe_role, object: mainline.merge_permit, privileges: [EXECUTE]}\n"
    )
    assert probe.statements[-1].sql.startswith("GRANT EXECUTE ON TABLE "), (
        "GRANTS.yaml can now render a routine grant, so the fallback below is no longer "
        f"the honest answer: {probe.statements[-1].sql}. Declare these routines in the "
        "matrix and delete this branch."
    )

    source = CLOUD_ROLES_PY.read_text(encoding="utf-8") if CLOUD_ROLES_PY.is_file() else ""
    unnamed = [r for r in ungranted if r not in source]
    assert not unnamed, (
        f"{API_ROLE} invokes {len(unnamed)} routine(s) that NO DECLARATION IN THIS "
        "REPOSITORY mentions:\n\n"
        + "\n".join(f"  {r:<34} EXECUTE <- {_where(scan, r, 'EXECUTE')}" for r in unnamed)
        + f"\n\n{GRANTS_YAML.name} cannot carry the grant, and that is measured above "
        "rather than taken from its comment: its table_privileges section renders "
        "`GRANT … ON TABLE`, and its identifier grammar has no room for the argument list "
        "CockroachDB needs to disambiguate an overload. So the fallback authority is "
        f"{CLOUD_ROLES_PY.relative_to(REPO_ROOT).as_posix()} — and the routine is not named "
        "there either.\n\n"
        "THIS IS NOT A CLAIM THAT THE CALL RETURNS 42501, AND THE REASON IS MEASURED. On "
        "CockroachDB CCL v26.2.5 (local single node, 2026-08-15) a freshly created function "
        "carries EXECUTE granted to `public` by default — `SHOW GRANTS ON FUNCTION` returns "
        "a `public / EXECUTE` row, and a login holding only CONNECT plus USAGE ON SCHEMA "
        "executed it. Migrations 0007a-0007e revoke `public` from the five mainline schemas "
        "ON SCHEMA, which does not touch routine EXECUTE, and nothing revokes it from "
        "`trappoint` at all.\n\n"
        "So the finding is the OTHER direction, and it is worse: this login can probably "
        "execute EVERY routine in EVERY schema it holds USAGE on, and this repository "
        "declares nothing either way about any of them. On an authorization_type = NONE "
        "endpoint an undeclared privilege is the defect whether or not it is currently "
        "held. Resolve it by declaring the grant where grants are issued, or by recording "
        "the measured default as a decision with Leg B's probe output beside it "
        "(tests/integration/schema/test_privilege_conformance.py). Do NOT close it by "
        "assuming the default holds on the deployed cluster — that is the assumption this "
        "wave exists to replace with evidence."
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# 4. Granted but never demanded — tomorrow's over-grant on an anonymous endpoint.
# ═════════════════════════════════════════════════════════════════════════════════════


#: The keys a matrix row may carry its reasoning in. ``grants.py`` models ``why`` on every
#: grant-bearing row and ``purpose`` on a role, and ignores unknown keys so a document may
#: carry more. A YAML ``#`` comment is NOT on this list and cannot be: it is invisible to
#: `grants apply`, to `apply_chain.py --grants`, to `cloud_roles.py`'s per-statement note
#: and to this census, so a reason written there is a reason no consumer of the file can
#: repeat back to an operator.
JUSTIFICATION_KEYS: Final = ("why", "purpose", "note", "rationale", "evidence")

#: DELIBERATELY NOT A JUSTIFICATION. ``census_note:`` is where W2 recorded the rows it
#: could not justify and referred to this census — *"No reference found by the 2026-08-15
#: static sweep. Carried across; candidate over-grant for W1."* An open question is not an
#: answer, so a row carrying only this stays red; the census has now run, and its result is
#: the answer that key was waiting for. Renaming the key to ``why:`` would settle the
#: question by typing, which is why the two are told apart here rather than merged.
DEFERRAL_KEYS: Final = ("census_note",)


def _justification(row: Mapping[str, Any]) -> str:
    return " ".join(str(row.get(key, "")) for key in JUSTIFICATION_KEYS).strip()


def _deferral(row: Mapping[str, Any]) -> str:
    return " ".join(str(row.get(key, "")) for key in DEFERRAL_KEYS).strip()


def _api_rows() -> list[Mapping[str, Any]]:
    return [
        row
        for section in ("table_privileges", "schema_wide", "subject_access_views")
        for row in _document().get(section) or []
        if isinstance(row, Mapping) and row.get("role") == API_ROLE
    ]


def _justifications() -> dict[str, str]:
    """Object → the reasoning the matrix gives for granting it to ``mainline_api``."""
    out: dict[str, str] = {}
    for row in _api_rows():
        name = str(row.get("object", row.get("schema", "")))
        out[name] = (out.get(name, "") + " " + _justification(row)).strip()
    return out


def _deferrals() -> dict[str, str]:
    """Object → the open question the matrix recorded against it, if any."""
    out: dict[str, str] = {}
    for row in _api_rows():
        name = str(row.get("object", row.get("schema", "")))
        out[name] = (out.get(name, "") + " " + _deferral(row)).strip()
    return {name: text for name, text in out.items() if text}


def test_nothing_is_granted_to_the_api_role_that_it_cannot_justify() -> None:
    """The over-grant direction, judged by R4: *a row you cannot justify does not go in*.

    THE CLAIM: every privilege this login holds is either issued by a statement in the
    shipping source, or answered for in the matrix.

    An over-grant on an ``authorization_type = NONE`` endpoint is a defect and not a safety
    margin, so a privilege this login holds and no statement in the shipping source issues
    has to answer for itself. What it may NOT be judged by is the static scan alone, and
    the reason is measured rather than assumed: every trigger function in migrations
    0100-0149 executes as the INVOKING role, none is ``SECURITY DEFINER``, so
    ``mainline.merge_permit``'s trigger chain reads and writes relations this application
    names in no statement of its own. ``cloud_roles.API_GATE_READ`` is ten such relations
    and its comment says outright that they were *discovered by running it*; deleting one
    because a scanner could not see it would fail the demo's second beat in front of a
    judge, with a privilege error.

    So the criterion is R4's: **a row you cannot justify does not go in**. A grant the
    source does not issue must carry its reasoning in the matrix — where every consumer of
    the file can repeat it back — and one that carries none is red. Leg B
    (``tests/integration/schema/test_privilege_conformance.py``) is what decides whether a
    justified one is truly reachable; this file makes sure it is never silent.

    Both classes are computed and both are printed on failure: a whole RELATION the source
    never names, and a VERB beyond what the source issues on a relation it does name. The
    second is R4b's shape inverted, and it is where an over-grant is easiest to hide. A
    third class is separated out in the message rather than merged into either: rows the
    matrix itself marked ``census_note:`` — *"candidate over-grant for W1"* — which are
    open questions addressed to this census. They are still red; what changes is that the
    message says the census has now run and what it found.
    """
    _require_the_role("what the demo API role must NOT be able to reach")
    scan, reach = _scan(), _reach()
    demanded = scan.relations()
    justified, deferred = _justifications(), _deferrals()

    unjustified: list[str] = []
    open_questions: list[str] = []
    explained: list[str] = []
    for obj, privileges in reach.directly_granted_objects(API_ROLE).items():
        beyond = sorted(privileges - scan.verbs_for(obj) - {"ALL"})
        if obj not in demanded:
            line = f"  {obj:<34} {', '.join(sorted(privileges)):<16} no statement names it"
        elif beyond:
            line = (
                f"  {obj:<34} {', '.join(beyond):<16} source issues only "
                f"{', '.join(sorted(scan.verbs_for(obj)))}"
            )
        else:
            continue
        if justified.get(obj):
            explained.append(line)
        elif deferred.get(obj):
            open_questions.append(line)
        else:
            unjustified.append(line)

    difference = [*unjustified, *open_questions]
    assert not difference, (
        f"{GRANTS_YAML.name} grants {API_ROLE} {len(difference)} privilege(s) the shipping "
        "demo-api source issues no statement for:\n\n"
        + (
            "DEFERRED TO THIS CENSUS BY THE MATRIX ITSELF (`census_note:`) — and the census "
            "has now run over 40 relations and 2 routines with two agreeing extraction "
            "legs, and found no reference:\n" + "\n".join(open_questions) + "\n\n"
            if open_questions
            else ""
        )
        + ("NO REASON RECORDED AT ALL:\n" + "\n".join(unjustified) + "\n\n" if unjustified else "")
        + (
            f"({len(explained)} further such grant(s) DO carry a `why:` and are not counted "
            "here; Leg B's probe is what decides whether they are reachable.)\n\n"
            if explained
            else ""
        )
        + "This login is what every anonymous caller on the public Function URL executes "
        "as, so its reach is this product's entire authorisation surface. Each line above "
        "is either a read or write a TRIGGER performs as the invoking role — which is why "
        "cloud_roles.API_GATE_READ exists and why mainline.ledger_intake and "
        "mainline_ops.outbox are on API_WRITE — or an over-grant to be removed. Resolve it "
        f"in {GRANTS_YAML.name}: delete the row, or replace `census_note:` with a `why:` "
        "that says which trigger reaches it. Do NOT rename the key to close this — that "
        "settles an open question by typing. Do NOT add a reference to the source. Do NOT "
        "put the reason in a YAML comment: `grants apply` cannot read one, so the "
        "operator's terminal would still name the grant with no reason beside it."
    )


def test_the_api_role_holds_no_schema_wide_wildcard() -> None:
    """A wildcard makes the over-grant direction unmeasurable, so it is refused outright.

    ``GRANT … ON ALL TABLES IN SCHEMA mainline`` silently picks up whatever the next
    migration adds. ``cloud_roles.py`` enumerates its 33 read relations by name for exactly
    this reason, and ``GRANTS.yaml``'s §5 header says wildcards are used only for SELECT
    and only where a schema is constitutionally view-only.
    """
    _require_the_role("the absence of a wildcard grant")
    wildcards = _reach().directly_granted_wildcards(API_ROLE)
    assert not wildcards, (
        f"{GRANTS_YAML.name} grants {API_ROLE} every table in {', '.join(wildcards)}. The "
        "test above cannot then say what is over-granted, because a wildcard's reach is "
        "whatever the schema happens to contain. Enumerate the relations by name."
    )


def test_every_row_the_matrix_writes_for_the_api_role_is_a_row_this_census_can_weigh() -> None:
    """The mechanism behind the test above, asserted rather than assumed.

    :func:`_justifications` reads the reasoning off the document. If ``GRANTS.yaml`` ever
    spells a grant row for this role in a section that function does not read, the row's
    privileges would still count as reach — ``_build_reach`` works off the rendered
    statements — while its reason would be invisible, and the over-grant test would demand
    a justification that is right there in the file. That is a confusing red, so it is
    caught here as a clear one.
    """
    _require_the_role("the matrix rows that carry this role's reasoning")
    named_in_rows = {str(r.get("object", r.get("schema", ""))) for r in _api_rows()}
    granted = set(_reach().directly_granted_objects(API_ROLE))
    unreachable_rows = sorted(granted - named_in_rows)
    assert not unreachable_rows, (
        f"{GRANTS_YAML.name} grants {API_ROLE} these objects through a section this census "
        "does not read the reasoning from, so their `why:` cannot be weighed:\n"
        + "\n".join(f"  {obj}" for obj in unreachable_rows)
        + "\nSections read: table_privileges, schema_wide, subject_access_views. Add the "
        "new section to _api_rows()."
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# 5. The reader itself. Its mechanisms are exercised, not trusted.
# ═════════════════════════════════════════════════════════════════════════════════════
#
# These build a throwaway matrix in `tmp_path` and read it through the same
# `trappoint_migrate.grants` parser. That is a fixture for the READER, not a second copy
# of the committed list: nothing here restates a privilege the real matrix holds.


def _matrix(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "GRANTS.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _reach_of(tmp_path: Path, body: str) -> Reach:
    return _build_reach(grants_module.plan(_matrix(tmp_path, body)).statements)


def test_the_reader_follows_role_membership_into_the_privileges_it_inherits(
    tmp_path: Path,
) -> None:
    reach = _reach_of(
        tmp_path,
        """
        apply_order: [roles, memberships, schema_privileges, table_privileges]
        roles:
          - {name: parent_role, login: false}
          - {name: child_role, login: true}
        memberships:
          - {role: parent_role, member: child_role}
        schema_privileges:
          - {role: parent_role, schemas: [mainline], privileges: [USAGE]}
        table_privileges:
          - {role: parent_role, object: mainline.permit, privileges: [SELECT]}
        """,
    )
    assert reach.closure("child_role") == frozenset({"child_role", "parent_role"})
    assert reach.covers("child_role", "mainline.permit", "SELECT")
    assert reach.has_schema_usage("child_role", "mainline")
    assert not reach.covers("child_role", "mainline.permit", "INSERT")
    # Inherited, so it is not part of what an over-grant review of `child_role` covers.
    assert reach.directly_granted_objects("child_role") == {}


def test_the_reader_credits_a_schema_wide_grant_and_names_it_as_a_wildcard(
    tmp_path: Path,
) -> None:
    reach = _reach_of(
        tmp_path,
        """
        apply_order: [roles, schema_wide]
        roles:
          - {name: wide_role, login: true}
        schema_wide:
          - {role: wide_role, schema: mainline, privileges: [SELECT]}
        """,
    )
    assert reach.covers("wide_role", "mainline.anything_at_all", "SELECT")
    assert reach.directly_granted_wildcards("wide_role") == ("mainline",)


def test_the_reader_subtracts_a_revocation_aimed_at_the_role(tmp_path: Path) -> None:
    reach = _reach_of(
        tmp_path,
        """
        apply_order: [roles, table_privileges, revocations]
        roles:
          - {name: revoked_role, login: true}
        table_privileges:
          - {role: revoked_role, object: mainline_qa.v_my_record, privileges: [SELECT]}
        revocations:
          - {grantee: revoked_role, object_type: SCHEMA, objects: [mainline_qa], privileges: [ALL]}
        """,
    )
    assert not reach.covers("revoked_role", "mainline_qa.v_my_record", "SELECT")


def test_the_reader_ignores_a_revocation_aimed_at_public(tmp_path: Path) -> None:
    """``REVOKE … FROM public`` removes an implicit privilege, never an explicit grant.

    Modelling it as a subtraction would understate the role's reach, and understating the
    reach is the direction that makes an over-grant invisible.
    """
    reach = _reach_of(
        tmp_path,
        """
        apply_order: [roles, table_privileges, revocations]
        roles:
          - {name: kept_role, login: true}
        table_privileges:
          - {role: kept_role, object: mainline.permit, privileges: [SELECT]}
        revocations:
          - {grantee: public, object_type: SCHEMA, objects: [mainline], privileges: [ALL]}
        """,
    )
    assert reach.covers("kept_role", "mainline.permit", "SELECT")


def test_a_section_the_matrix_declares_and_never_applies_grants_nothing(
    tmp_path: Path,
) -> None:
    """``apply_order`` is authoritative; ``subject_access_views`` is the standing example."""
    path = _matrix(
        tmp_path,
        """
        apply_order: [roles]
        roles:
          - {name: hopeful_role, login: true}
        subject_access_views:
          - {role: hopeful_role, object: mainline_qa.v_my_record, privileges: [SELECT]}
        """,
    )
    grant_plan = grants_module.plan(path)
    assert "subject_access_views" in grant_plan.unapplied_sections
    assert not _build_reach(grant_plan.statements).covers(
        "hopeful_role", "mainline_qa.v_my_record", "SELECT"
    )


class _Rendered:
    """One rendered statement, standing in for ``grants.Statement`` where a shape is tested."""

    def __init__(self, sql: str) -> None:
        self.sql = sql


def test_a_statement_shape_the_reader_cannot_parse_is_collected_not_dropped() -> None:
    """The mechanism behind :func:`test_the_matrix_statement_vocabulary_is_fully_understood`."""
    sql = "GRANT SELECT ON SEQUENCE mainline.some_seq TO mainline_api"
    reach = _build_reach([_Rendered(sql)])
    assert reach.unrecognised == [sql]
    assert not reach.covers(API_ROLE, "mainline.some_seq", "SELECT")


def test_an_execute_grant_on_a_routine_is_read_as_reach(tmp_path: Path) -> None:
    """``CALL mainline.merge_permit(…)`` needs EXECUTE, and the census must be able to see it.

    ``grants.py`` renders ``table_privileges`` as ``GRANT … ON TABLE``, so a matrix that
    declares EXECUTE that way is read here as reach on the named object. Whether the
    CLUSTER accepts the statement is a question about behaviour, and Leg B is what asks it.
    """
    reach = _reach_of(
        tmp_path,
        """
        apply_order: [roles, table_privileges]
        roles:
          - {name: caller_role, login: true}
        table_privileges:
          - {role: caller_role, object: mainline.merge_permit, privileges: [EXECUTE]}
        """,
    )
    assert reach.covers("caller_role", "mainline.merge_permit", "EXECUTE")


@pytest.mark.parametrize(
    ("sql", "routine"),
    [
        (
            "GRANT EXECUTE ON PROCEDURE mainline.merge_permit(UUID, BYTES) TO mainline_api",
            "mainline.merge_permit",
        ),
        ("GRANT EXECUTE ON FUNCTION mainline.fn_thing() TO mainline_api", "mainline.fn_thing"),
        (
            "GRANT EXECUTE ON ROUTINE trappoint.explain_refusal TO mainline_api",
            "trappoint.explain_refusal",
        ),
    ],
)
def test_the_reader_understands_a_routine_grant_however_it_is_spelled(
    sql: str, routine: str
) -> None:
    """So that a matrix which grows a routine section is read, not reported as unparsable.

    ``grants.py`` has no routine builder today, so no such statement is rendered from the
    committed matrix. The shapes are understood in advance because the alternative — the
    day one appears — is :func:`test_the_matrix_statement_vocabulary_is_fully_understood`
    going red on a correct matrix, which teaches a reader to widen the parser under time
    pressure.
    """
    reach = _build_reach([_Rendered(sql)])
    assert not reach.unrecognised, reach.unrecognised
    assert reach.covers(API_ROLE, routine, "EXECUTE")
