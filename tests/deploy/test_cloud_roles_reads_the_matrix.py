# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""One authority for what ``mainline_api`` may reach, asserted rather than hoped for.

WHAT THIS FILE EXISTS TO PREVENT, MEASURED RATHER THAN IMAGINED
---------------------------------------------------------------
On 2026-08-14 eleven relations that the shipping demo-api references were granted BY HAND to
``mainline_api`` against the live cluster, during five outages, and were never written back into
``scripts/deploy/cloud_roles.py``::

    mainline.control_failure   mainline.ledger_leaf         trappoint.deploy_chain
    mainline.defeater_option   mainline.ledger_node         trappoint.schema_attestation
    mainline.delta_witness     mainline.receipt_expiry      trappoint.schema_migration
    mainline.event_edge        mainline_meas.silence_ledger

A rebuild from scratch would have reproduced all five outages. The repair is not to re-type the
eleven names into the deploy script — that produces the same defect one year later. It is to
delete the deploy script's copy and derive from ``verticals/mainline/db/GRANTS.yaml``, so that
the drift becomes UNREPRESENTABLE rather than merely detectable.

THE DISCIPLINE THIS FILE FOLLOWS, WHICH IS THE POINT OF IT
----------------------------------------------------------
``verticals/mainline/apps/demo-api/tests/test_seed_covers_every_console_resource.py`` states the
rule these tests obey: *a second copy of a list is a second thing to drift.* So **no test below
hard-codes what the matrix ought to say.** Every expected set is parsed from an authority:

* the SQL the deploy script would issue, read back out of :func:`cloud_roles.grant_plan`;
* the matrix itself, walked by an INDEPENDENT ``yaml.safe_load`` in this file rather than through
  the derivation under test, because a comparison of a function against itself is a tautology.

**The vacuity guard is mandatory and is the reason for the fixture matrices.** ``GRANTS.yaml``
does not declare ``mainline_api`` until the matrix worker lands it, and until then a comparison
against the committed file compares two empty sets and certifies nothing. So the equality is also
exercised against fixture matrices built by RELABELLING rows the committed file already carries —
never by inventing rows — which keeps the property under test today and every day after.

NO CLUSTER. Every test here runs on any machine with no database anywhere: the grant plan is
pure data, and the two places that take a connection are driven by a recording double.
"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml

from scripts.deploy import cloud_roles

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOUD_ROLES_SOURCE = REPO_ROOT / "scripts" / "deploy" / "cloud_roles.py"
COMMITTED_MATRIX = REPO_ROOT / "verticals" / "mainline" / "db" / "GRANTS.yaml"

#: The five names that used to be hand-maintained tuples in the deploy script. They still exist —
#: `judge_access.py` and `scripts/qa/regression_guard.py` read them — but they must now be
#: DERIVED. This list is the subject of the test, not an expectation about the product.
DERIVED_NAMES = ("API_READ", "API_GATE_READ", "API_WRITE", "AUDIT_VIEWS", "API_MEMBERSHIPS")

_GRANT_TABLE = re.compile(
    r'^GRANT (?P<privs>[A-Z, ]+) ON TABLE (?P<obj>[\w.]+) TO "(?P<role>\w+)"$'
)
_GRANT_SCHEMA = re.compile(
    r'^GRANT (?P<privs>[A-Z, ]+) ON SCHEMA (?P<schema>\w+) TO "(?P<role>\w+)"$'
)
_GRANT_ROLE = re.compile(r'^GRANT "(?P<role>\w+)" TO "(?P<member>\w+)"$')
_GRANT_ROUTINE = re.compile(
    r'^GRANT EXECUTE ON PROCEDURE (?P<routine>[\w.]+)\((?P<signature>[^)]*)\) TO "(?P<role>\w+)"$'
)
_REVOKE = re.compile(r"^REVOKE ")


# ═════════════════════════════════════════════════════════════════════════════════════
# reading the two authorities, each by its own path
# ═════════════════════════════════════════════════════════════════════════════════════


def matrix_declares(document: dict[str, Any], role: str) -> dict[str, set[Any]]:
    """Walk the matrix for one role, WITHOUT using the derivation under test.

    A deliberately dumb second reader. It knows only what the file's own header says the sections
    mean, so when it disagrees with :mod:`cloud_roles` one of the two is wrong and the failure
    names which objects.
    """
    tables: set[tuple[str, str]] = set()
    for row in document.get("table_privileges") or []:
        if not isinstance(row, dict) or row.get("role") != role:
            continue
        for privilege in row.get("privileges") or []:
            tables.add((str(row["object"]), str(privilege).upper()))
    schemas: set[tuple[str, str]] = set()
    for row in document.get("schema_privileges") or []:
        if not isinstance(row, dict) or row.get("role") != role:
            continue
        for schema in row.get("schemas") or []:
            for privilege in row.get("privileges") or []:
                schemas.add((str(schema), str(privilege).upper()))
    memberships = {
        str(row["role"])
        for row in document.get("memberships") or []
        if isinstance(row, dict) and row.get("member") == role
    }
    return {"tables": tables, "schemas": schemas, "memberships": memberships}


def plan_grants(plan: tuple[cloud_roles.Planned, ...], role: str) -> dict[str, set[Any]]:
    """What the deploy script would grant, read back out of the SQL it would issue.

    The SQL is the thing that reaches the cluster, so the SQL is what is parsed. Reading the
    module's derived constants instead would test the constants and not the statements.
    """
    tables: set[tuple[str, str]] = set()
    schemas: set[tuple[str, str]] = set()
    memberships: set[str] = set()
    routines: set[str] = set()
    unparsed: list[str] = []
    for item in plan:
        table = _GRANT_TABLE.match(item.sql)
        schema = _GRANT_SCHEMA.match(item.sql)
        member = _GRANT_ROLE.match(item.sql)
        routine = _GRANT_ROUTINE.match(item.sql)
        if table:
            if table["role"] == role:
                tables.update((table["obj"], p.strip()) for p in table["privs"].split(","))
        elif schema:
            if schema["role"] == role:
                schemas.update((schema["schema"], p.strip()) for p in schema["privs"].split(","))
        elif member:
            if member["member"] == role:
                memberships.add(member["role"])
        elif routine:
            if routine["role"] == role:
                routines.add(routine["routine"])
        elif not _REVOKE.match(item.sql):
            unparsed.append(item.sql)
    assert not unparsed, (
        "this test parses the deploy script's SQL back into (object, privilege) pairs and does "
        "not recognise these statements. A statement shape it cannot read is a grant it cannot "
        "compare against the matrix, which is the whole control:\n  " + "\n  ".join(unparsed)
    )
    return {
        "tables": tables,
        "schemas": schemas,
        "memberships": memberships,
        "routines": routines,
    }


def relabelled_matrix(target: Path, moves: dict[str, str], *, memberships: bool = True) -> Path:
    """A fixture matrix built by RENAMING roles the committed file already carries.

    Nothing is invented: every object, privilege and ``why`` comes from
    ``verticals/mainline/db/GRANTS.yaml`` as committed. Only the role name on the row changes.
    That is what makes this fixture legitimate under the wave's "never invent a row" rule and
    what makes the equality property testable before the matrix worker's rows land.
    """
    try:
        document = copy.deepcopy(yaml.safe_load(COMMITTED_MATRIX.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:  # the authority is unreadable; say which file and why
        pytest.fail(
            f"{COMMITTED_MATRIX} is not valid YAML, so nothing downstream of it can be "
            f"asserted: {exc}"
        )
    for source, destination in moves.items():
        document["roles"].append(
            {"name": destination, "login": True, "purpose": f"fixture: {source}'s reach, renamed"}
        )
        for section in ("schema_privileges", "table_privileges", "schema_wide"):
            for row in list(document.get(section) or []):
                if isinstance(row, dict) and row.get("role") == source:
                    clone = dict(row)
                    clone["role"] = destination
                    document[section].append(clone)
    if memberships:
        document["memberships"] = [
            {"role": name, "member": next(iter(moves.values())), "why": "fixture: RLS scope"}
            for name in sorted(moves)
        ]
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


@pytest.fixture
def fixture_matrix(tmp_path: Path) -> Path:
    """``agent_gate``'s reach relabelled onto ``mainline_api``, the auditor's onto the judge."""
    return relabelled_matrix(
        tmp_path / "GRANTS.yaml",
        {"agent_gate": cloud_roles.API_USER, "mainline_auditor": cloud_roles.JUDGE_USER},
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# 1 — THE COPY IS GONE
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_five_object_lists_are_bound_but_not_literal():
    """Each name still exists for its consumers, and none of them is a written-down list."""
    tree = ast.parse(CLOUD_ROLES_SOURCE.read_text(encoding="utf-8"))
    bound: dict[str, ast.expr] = {}
    for node in tree.body:
        targets = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in DERIVED_NAMES:
                bound[target.id] = node.value

    assert sorted(bound) == sorted(DERIVED_NAMES), (
        "every one of these names is imported or AST-scanned by something else in the tree "
        "(scripts/deploy/judge_access.py reads AUDIT_VIEWS; scripts/qa/regression_guard.py reads "
        "API_GATE_READ). Deleting one is a break, not a cleanup; it must be DERIVED, not removed."
    )
    for name, value in sorted(bound.items()):
        try:
            literal = ast.literal_eval(value)
        except ValueError:
            continue  # not a literal: it is computed, which is the point
        assert not literal, (
            f"{name} is a written-down list again ({literal!r}). That copy drifted eleven "
            "relations behind the cluster it provisioned and cost five outages on 2026-08-14. "
            f"It must be derived from {COMMITTED_MATRIX.name}."
        )


def test_the_module_reads_the_matrix_through_the_repositorys_own_parser():
    source = CLOUD_ROLES_SOURCE.read_text(encoding="utf-8")
    assert "from trappoint_migrate.grants import load_matrix" in source, (
        "the matrix must be read with trappoint_migrate.grants, which is the parser "
        "`trappoint migrate grants apply` uses. A second YAML reader is a second set of rules "
        "about what the file means."
    )
    assert cloud_roles.matrix_path() == COMMITTED_MATRIX
    assert COMMITTED_MATRIX.is_file()


def test_no_planned_statement_can_carry_a_credential(fixture_matrix: Path):
    """No GRANT this program issues names a password, and none of them is ever a CREATE USER."""
    plan = cloud_roles.grant_plan(cloud_roles.derive(fixture_matrix))
    offenders = [item.sql for item in plan if "PASSWORD" in item.sql.upper()]
    assert not offenders, offenders
    assert not [item for item in plan if "CREATE USER" in item.sql.upper()]


# ═════════════════════════════════════════════════════════════════════════════════════
# 2 — THE PROPERTY: what the script would grant EQUALS what the matrix declares
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_plan_equals_the_fixture_matrix_in_both_directions(fixture_matrix: Path):
    """The equality, exercised on real rows today rather than on an empty set.

    Both directions are asserted. Granted-but-not-declared is an over-grant on a login an
    anonymous caller executes as; declared-but-not-granted is the 2026-08-14 outage.
    """
    document = yaml.safe_load(fixture_matrix.read_text(encoding="utf-8"))
    derived = cloud_roles.derive(fixture_matrix)
    assert derived.declared, derived.status
    plan = cloud_roles.grant_plan(derived)

    for role in (cloud_roles.API_USER, cloud_roles.JUDGE_USER):
        declared = matrix_declares(document, role)
        granted = plan_grants(plan, role)
        assert declared["tables"], (
            f"the fixture put no table row on {role}; a comparison of two empty sets certifies "
            "nothing, which is the exact failure this file exists to refuse"
        )
        assert granted["tables"] == declared["tables"], {
            "declared but never granted": sorted(declared["tables"] - granted["tables"]),
            "granted but never declared": sorted(granted["tables"] - declared["tables"]),
        }
        assert granted["schemas"] == declared["schemas"], {
            "declared but never granted": sorted(declared["schemas"] - granted["schemas"]),
            "granted but never declared": sorted(granted["schemas"] - declared["schemas"]),
        }
        assert granted["memberships"] == declared["memberships"]


def test_the_plan_equals_the_committed_matrix_or_the_script_refuses_to_run():
    """The same property against the file that ships — and a refusal while it is still silent.

    ``GRANTS.yaml`` does not declare ``mainline_api`` until the matrix worker lands it. Until it
    does, the honest assertion is not an empty comparison: it is that the deploy script REFUSES,
    naming the file to edit, rather than provisioning a login that can reach nothing. Both
    branches assert something; neither is a soft pass.
    """
    derived = cloud_roles.MATRIX  # the module's own import-time read of the committed file
    assert derived.source == COMMITTED_MATRIX
    if not derived.declared:
        with pytest.raises(cloud_roles.MatrixIncomplete) as refusal:
            cloud_roles.grant_plan(derived)
        message = str(refusal.value)
        assert "GRANTS.yaml" in message
        assert cloud_roles.API_READ == ()
        assert cloud_roles.API_GATE_READ == ()
        assert cloud_roles.API_WRITE == ()
        assert cloud_roles.AUDIT_VIEWS == ()
        assert cloud_roles.API_MEMBERSHIPS == ()
        return

    document = yaml.safe_load(COMMITTED_MATRIX.read_text(encoding="utf-8"))
    plan = cloud_roles.grant_plan(derived)
    for role in (cloud_roles.API_USER, cloud_roles.JUDGE_USER):
        declared = matrix_declares(document, role)
        granted = plan_grants(plan, role)
        assert granted["tables"] == declared["tables"], {
            "declared but never granted": sorted(declared["tables"] - granted["tables"]),
            "granted but never declared": sorted(granted["tables"] - declared["tables"]),
        }
        assert granted["schemas"] == declared["schemas"]
        assert granted["memberships"] == declared["memberships"]


def test_the_derived_constants_name_exactly_what_the_plan_grants(fixture_matrix: Path):
    """``API_READ`` and friends must describe the statements, not a parallel story about them."""
    derived = cloud_roles.derive(fixture_matrix)
    plan = cloud_roles.grant_plan(derived)
    granted = plan_grants(plan, cloud_roles.API_USER)

    selects = {obj for obj, privilege in granted["tables"] if privilege == "SELECT"}
    writes = {(obj, privilege) for obj, privilege in granted["tables"] if privilege != "SELECT"}
    reads = {g.object for g in cloud_roles._api_selects(derived) if not g.gate_chain}
    gate = {g.object for g in cloud_roles._api_selects(derived) if g.gate_chain}
    views = {f"mainline_audit.{name}" for name in cloud_roles._audit_views(derived.api_tables)}
    assert reads | gate == selects
    assert views <= selects
    assert writes == {
        (g.object, p) for g in derived.api_tables for p in g.privileges if p in {"INSERT", "UPDATE"}
    }


def test_a_relation_added_to_the_matrix_reaches_the_plan_with_no_edit_here(fixture_matrix: Path):
    """The 2026-08-14 defect, made unrepresentable.

    The relation used is one the committed matrix already names for another role, so nothing is
    invented — only the row's role changes.
    """
    document = yaml.safe_load(fixture_matrix.read_text(encoding="utf-8"))
    before = plan_grants(
        cloud_roles.grant_plan(cloud_roles.derive(fixture_matrix)), cloud_roles.API_USER
    )
    borrowed = next(
        row
        for row in document["table_privileges"]
        if isinstance(row, dict)
        and row.get("role") != cloud_roles.API_USER
        and (str(row["object"]), "SELECT") not in before["tables"]
        and "SELECT" not in [str(p).upper() for p in row.get("privileges") or []]
    )
    document["table_privileges"].append(
        {
            "role": cloud_roles.API_USER,
            "object": borrowed["object"],
            "privileges": ["SELECT"],
            "why": "fixture: a relation the deploy script has never heard of",
        }
    )
    fixture_matrix.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    after = plan_grants(
        cloud_roles.grant_plan(cloud_roles.derive(fixture_matrix)), cloud_roles.API_USER
    )
    assert after["tables"] - before["tables"] == {(str(borrowed["object"]), "SELECT")}


def test_a_relation_removed_from_the_matrix_leaves_the_plan(fixture_matrix: Path):
    """The converse. An over-grant is closed by editing one file, and only one file."""
    document = yaml.safe_load(fixture_matrix.read_text(encoding="utf-8"))
    dropped = next(
        row for row in document["table_privileges"] if row.get("role") == cloud_roles.API_USER
    )
    target = str(dropped["object"])
    # EVERY row for that object, not merely the first: the matrix legitimately carries more than
    # one row per (role, object) — a read row and a gate-chain row, say — and closing an
    # over-grant means closing all of them. A test that removed one and asserted the object was
    # gone would be asserting a shape the file does not have.
    document["table_privileges"] = [
        row
        for row in document["table_privileges"]
        if not (row.get("role") == cloud_roles.API_USER and str(row.get("object")) == target)
    ]
    fixture_matrix.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    granted = plan_grants(
        cloud_roles.grant_plan(cloud_roles.derive(fixture_matrix)), cloud_roles.API_USER
    )
    assert not [obj for obj, _ in granted["tables"] if obj == target]


def test_a_section_outside_apply_order_is_refused_rather_than_honoured(fixture_matrix: Path):
    """What ``grants apply`` would not apply, this program will not apply either.

    One file, two consumers, and they must not disagree about it. A row in a section the matrix's
    own ``apply_order`` omits is a grant ``trappoint migrate grants apply`` never makes.
    """
    document = yaml.safe_load(fixture_matrix.read_text(encoding="utf-8"))
    document["apply_order"] = [s for s in document["apply_order"] if s != "table_privileges"]
    fixture_matrix.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(cloud_roles.MatrixIncomplete, match="table_privileges"):
        cloud_roles.derive(fixture_matrix)


def test_an_execute_row_the_script_cannot_spell_is_refused_not_dropped(fixture_matrix: Path):
    """A dropped EXECUTE surfaces as a 42501 in the first beat, in front of a judge."""
    document = yaml.safe_load(fixture_matrix.read_text(encoding="utf-8"))
    document["table_privileges"].append(
        {
            "role": cloud_roles.API_USER,
            "object": "mainline.merge_change_request",
            "privileges": ["EXECUTE"],
            "why": "fixture: a routine whose signature this module does not know",
        }
    )
    fixture_matrix.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(cloud_roles.MatrixIncomplete, match="merge_change_request"):
        cloud_roles.grant_plan(cloud_roles.derive(fixture_matrix))


# ═════════════════════════════════════════════════════════════════════════════════════
# 3 — WHAT MUST NOT HAVE CHANGED
# ═════════════════════════════════════════════════════════════════════════════════════


class FakeResult:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class FakeConn:
    """A recording connection. Never a socket, never a cluster, never a credential anywhere."""

    def __init__(
        self, *, existing: tuple[str, ...] = (), raises: dict[str, Exception] | None = None
    ):
        self.statements: list[str] = []
        self.existing = set(existing)
        self.raises = raises or {}
        self.closed = False

    def execute(self, sql: Any, params: Any = None) -> FakeResult:
        text = str(sql)
        self.statements.append(text)
        for needle, error in self.raises.items():
            if needle in text:
                raise error
        if "SHOW USERS" in text:
            name = params[0] if params else ""
            return FakeResult((1 if name in self.existing else 0,))
        return FakeResult(None)

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class InsecureRefusal(psycopg.errors.FeatureNotSupported):
    """CockroachDB's own words on an ``--insecure`` node, verbatim."""

    def __init__(self) -> None:
        super().__init__("setting or updating a password is not supported in insecure mode")


class CheckViolation(psycopg.errors.CheckViolation):
    def __init__(self, constraint: str) -> None:
        super().__init__(f"failed to satisfy CHECK constraint {constraint}")
        self._constraint = constraint

    @property
    def diag(self) -> Any:
        return type("Diag", (), {"sqlstate": "23514", "constraint_name": self._constraint})()


def test_there_is_no_password_option_and_never_will_be():
    """An operator who cannot pass a password on a command line cannot leave one in history."""
    options = {
        option for action in cloud_roles.build_parser()._actions for option in action.option_strings
    }
    assert "--password" not in options
    assert "--rotate" in options
    assert "--verify" in options
    assert "--password-from-env" in options


def test_the_program_cannot_write_a_password_to_a_file():
    """The credential is printed once and there is no file-writing call in the module at all."""
    tree = ast.parse(CLOUD_ROLES_SOURCE.read_text(encoding="utf-8"))
    writers = {"write_text", "write_bytes", "writelines", "dump", "open"}
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & writers, sorted(called & writers)


def test_the_password_is_url_safe_and_fresh_every_time():
    first, second = cloud_roles.generate_password(), cloud_roles.generate_password()
    assert first != second
    assert re.fullmatch(r"[A-Za-z0-9_-]{30,}", first), first


def test_a_password_is_set_on_create_and_a_re_run_leaves_the_live_credential_alone(
    fixture_matrix: Path,
):
    """A deploy script that silently rotates a secret takes the demo down on every re-run."""
    derived = cloud_roles.derive(fixture_matrix)

    fresh = FakeConn()
    issued, _ = cloud_roles.provision(fresh, "mainline_demo", rotate=False, derived=derived)
    assert issued[cloud_roles.API_USER]
    assert any("CREATE USER" in s and "PASSWORD" in s for s in fresh.statements)

    again = FakeConn(existing=(cloud_roles.API_USER, cloud_roles.JUDGE_USER))
    issued, log = cloud_roles.provision(again, "mainline_demo", rotate=False, derived=derived)
    assert issued == {cloud_roles.API_USER: None, cloud_roles.JUDGE_USER: None}
    assert not [s for s in again.statements if "PASSWORD" in s.upper()]
    assert any("password left alone" in entry["note"] for entry in log)

    rotated = FakeConn(existing=(cloud_roles.API_USER, cloud_roles.JUDGE_USER))
    issued, log = cloud_roles.provision(rotated, "mainline_demo", rotate=True, derived=derived)
    assert issued[cloud_roles.API_USER]
    assert any("ALTER USER" in s for s in rotated.statements)
    assert any("rotated" in entry["note"] for entry in log)


def test_an_insecure_cluster_gets_a_login_with_no_password_and_the_output_says_so(
    fixture_matrix: Path,
):
    """A rehearsal on the laptop must be possible, and must never look like a deployment."""
    derived = cloud_roles.derive(fixture_matrix)
    conn = FakeConn(raises={"WITH LOGIN PASSWORD": InsecureRefusal()})
    issued, log = cloud_roles.provision(conn, "mainline_demo", rotate=False, derived=derived)

    assert issued == {cloud_roles.API_USER: "", cloud_roles.JUDGE_USER: ""}
    stated = [entry["note"] for entry in log if "insecure" in entry["note"]]
    assert len(stated) == 2, stated
    assert all("WITHOUT a password" in note for note in stated)
    passwordless = f'CREATE USER IF NOT EXISTS "{cloud_roles.API_USER}" WITH LOGIN'
    assert passwordless in conn.statements
    assert not [s for s in conn.statements if "ALTER USER" in s]


def test_a_non_insecure_failure_on_create_still_aborts(fixture_matrix: Path):
    """The insecure branch is a branch, not a blanket ``except``."""
    derived = cloud_roles.derive(fixture_matrix)
    conn = FakeConn(raises={"WITH LOGIN PASSWORD": psycopg.errors.InsufficientPrivilege("nope")})
    with pytest.raises(psycopg.Error):
        cloud_roles.provision(conn, "mainline_demo", rotate=False, derived=derived)


@pytest.mark.parametrize("sqlstate", ["42P01", "42883", "3F000"])
def test_a_missing_object_is_a_warning_that_names_it_and_never_an_abort(sqlstate: str):
    """``GRANTS.yaml``'s contract: a part-way migrated cluster must still be grantable."""
    conn = FakeConn(raises={"GRANT": psycopg.errors.lookup(sqlstate)("relation absent")})
    result = cloud_roles.apply_statement(
        conn, "GRANT SELECT ON TABLE mainline.nothing TO x", note="the reason it exists"
    )
    assert result["skipped"] is True
    assert result["sqlstate"] == sqlstate
    assert result["note"] == "the reason it exists"
    assert "ok" not in result


def test_any_other_failure_is_a_failure_and_carries_its_note():
    conn = FakeConn(raises={"GRANT": psycopg.errors.InsufficientPrivilege("no")})
    result = cloud_roles.apply_statement(conn, "GRANT SELECT ON TABLE x TO y", note="why it exists")
    assert result["ok"] is False
    assert result["sqlstate"] == "42501"
    assert result["note"] == "why it exists"


def test_every_statement_reaches_the_terminal_with_the_reason_it_exists(fixture_matrix: Path):
    """A log in which "SELECT on mainline.cr_event" carries no clue why is a worse log."""
    derived = cloud_roles.derive(fixture_matrix)
    plan = cloud_roles.grant_plan(derived)
    assert plan
    for item in plan:
        assert item.note.strip(), item.sql
        assert item.kind in {
            "schema",
            "membership",
            "read",
            "gate_read",
            "audit",
            "write",
            "routine",
            "revocation",
        }, item.kind

    matrix_reasons = {g.why for g in derived.api_tables if g.why} | {
        s.why for s in derived.api_schemas if s.why
    }
    assert matrix_reasons, "the fixture carried no `why` at all, so this asserts nothing"
    carried = {item.note for item in plan}
    for reason in matrix_reasons:
        assert any(reason[:60] in note for note in carried), reason[:80]


def test_the_revocations_are_re_asserted_on_every_run(fixture_matrix: Path):
    """Drift is additive and a migration runs once, so these are issued every single time."""
    plan = cloud_roles.grant_plan(cloud_roles.derive(fixture_matrix))
    revokes = [item.sql for item in plan if item.sql.startswith("REVOKE")]
    for user in (cloud_roles.API_USER, cloud_roles.JUDGE_USER):
        for schema in cloud_roles.FORBIDDEN_SCHEMAS:
            assert f'REVOKE ALL ON SCHEMA {schema} FROM "{user}"' in revokes
            assert f'REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM "{user}"' in revokes
    assert cloud_roles.FORBIDDEN_SCHEMAS == ("mainline_qa",)


def test_the_judge_may_name_the_schemas_it_traverses_and_read_nothing_in_them(
    fixture_matrix: Path,
):
    """USAGE is the right to name a schema; the REVOKE is what says it is not the right to read."""
    derived = cloud_roles.derive(fixture_matrix)
    plan = cloud_roles.grant_plan(derived)
    revoked = {
        item.sql.split(" IN SCHEMA ")[1].split(" FROM ")[0]
        for item in plan
        if item.sql.startswith("REVOKE ALL ON ALL TABLES IN SCHEMA")
        and cloud_roles.JUDGE_USER in item.sql
    }
    readable = {g.object.split(".", 1)[0] for g in derived.judge_tables if g.privileges}
    traversed = {s.schema for s in derived.judge_schemas}
    assert revoked >= (traversed - readable)
    assert not (revoked & readable), "a schema the judge must read is not one to revoke in"


# ═════════════════════════════════════════════════════════════════════════════════════
# 4 — THE GATE PROBE, WHICH TESTS THE WHOLE CHAIN AND NOT ONE PRIVILEGE
# ═════════════════════════════════════════════════════════════════════════════════════


def _with_fake_connect(monkeypatch: pytest.MonkeyPatch, conn: FakeConn) -> None:
    monkeypatch.setattr(cloud_roles.psycopg, "connect", lambda *_a, **_k: conn)


def test_the_gate_probe_expects_the_products_refusal_not_a_privilege_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """23514 / gate_closed_when_issued is a working product. 42501 is a missing grant."""
    conn = FakeConn(
        raises={"CALL mainline.merge_permit": CheckViolation("gate_closed_when_issued")}
    )
    monkeypatch.setattr(conn, "execute", _seeded_execute(conn, seeded=True), raising=False)
    _with_fake_connect(monkeypatch, conn)

    result = cloud_roles.gate_probe("postgresql://ignored/db")
    assert result is not None
    assert result["expected"] == "23514"
    assert result["observed"] == "23514"
    assert result["agreed"] is True
    assert result["detail"] == "gate_closed_when_issued"


def test_the_gate_probe_calls_a_privilege_error_a_disagreement(monkeypatch: pytest.MonkeyPatch):
    conn = FakeConn(
        raises={"CALL mainline.merge_permit": psycopg.errors.InsufficientPrivilege("42501")}
    )
    monkeypatch.setattr(conn, "execute", _seeded_execute(conn, seeded=True), raising=False)
    _with_fake_connect(monkeypatch, conn)

    result = cloud_roles.gate_probe("postgresql://ignored/db")
    assert result is not None
    assert result["observed"] == "42501"
    assert result["agreed"] is False


def test_the_gate_probe_reports_not_seeded_distinctly_from_not_privileged(
    monkeypatch: pytest.MonkeyPatch,
):
    """``cloud_roles.py`` runs BEFORE ``seed_demo.py``, so "no permit" is not "no grant"."""
    conn = FakeConn()
    monkeypatch.setattr(conn, "execute", _seeded_execute(conn, seeded=False), raising=False)
    _with_fake_connect(monkeypatch, conn)

    assert cloud_roles.gate_probe("postgresql://ignored/db") is None


def test_an_admitted_merge_is_a_disagreement_not_a_pass(monkeypatch: pytest.MonkeyPatch):
    """If the gate did not refuse an open obligation, the demo's claim is false."""
    conn = FakeConn()
    monkeypatch.setattr(conn, "execute", _seeded_execute(conn, seeded=True), raising=False)
    _with_fake_connect(monkeypatch, conn)

    result = cloud_roles.gate_probe("postgresql://ignored/db")
    assert result is not None
    assert result["agreed"] is False
    assert "ADMITTED" in result["detail"]


def _seeded_execute(conn: FakeConn, *, seeded: bool):
    def execute(sql: Any, _params: Any = None) -> FakeResult:
        text = str(sql)
        conn.statements.append(text)
        for needle, error in conn.raises.items():
            if needle in text:
                raise error
        if "FROM mainline.permit WHERE permit_id" in text:
            return FakeResult((1 if seeded else 0,))
        return FakeResult(None)

    return execute


# ═════════════════════════════════════════════════════════════════════════════════════
# 5 — THE REFUSAL PATH: no DDL when the matrix is silent
# ═════════════════════════════════════════════════════════════════════════════════════


def test_provision_refuses_before_it_creates_anything_when_the_matrix_is_silent():
    """A login this program cannot grant correctly is a login it does not create."""
    silent = cloud_roles.Derived(
        source=COMMITTED_MATRIX,
        declared=False,
        status="fixture: the matrix declares neither login",
        api_schemas=(),
        api_memberships=(),
        api_tables=(),
        judge_schemas=(),
        judge_tables=(),
    )
    conn = FakeConn()
    with pytest.raises(cloud_roles.MatrixIncomplete):
        cloud_roles.provision(conn, "mainline_demo", rotate=False, derived=silent)
    assert conn.statements == [], (
        "the refusal must happen before the first CREATE USER: a run that cannot grant "
        "correctly must not leave a login behind that can reach nothing"
    )


def test_the_module_imports_with_an_incomplete_matrix_rather_than_exploding():
    """``judge_access.py`` imports AUDIT_VIEWS. An import that raises takes it down with it."""
    assert isinstance(cloud_roles.MATRIX_DECLARES_LOGINS, bool)
    assert cloud_roles.MATRIX_STATUS.strip()
    if not cloud_roles.MATRIX_DECLARES_LOGINS:
        assert "GRANTS.yaml" in cloud_roles.MATRIX_STATUS
