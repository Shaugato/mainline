# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this module makes no database claim of its own. It drives
#     `scripts/demo/demo_ready.py` against a LOCAL database and against recorded bytes the
#     deployed API sent, and asserts what that program says about what it found.
"""Hold `scripts/demo/demo_ready.py` to the two things it is for.

**IT MUST GO GREEN ON A GOOD WORLD AND RED ON A BAD ONE.** A pre-flight check that cannot
fail is a green light nobody earned, and this repository has already shipped one guard whose
baseline was 77 tests below the truth. So half of this module is falsification: every fact
`demo_ready` checks is fed a world in which that fact is false, and the line is required to
say `FAIL`.

**AND IT MUST BE IDEMPOTENT AGAINST AN ALREADY-SEEDED DATABASE**, which is the trap this
repository has been bitten by and the reason `--repair` is tested twice in a row.
`docs/deploy/cloud-database.md` §5 measured it: `ON CONFLICT DO NOTHING` does NOT suppress an
exception a BEFORE INSERT trigger has already raised — conflict resolution happens after the
trigger runs — and a second run of `demo_world.sql` raised

    P0001  MAINLINE: closure generations must be dense and monotone

from `fn_closure_guard` and aborted the whole batch. Three tables therefore use
`INSERT ... SELECT ... WHERE NOT EXISTS` (`clause_version`, `clause_blame_closure`,
`cbm_account`) and the two `permit_event` rows use the same form for a different reason: the
second event's `prev_digest` must read the first's trigger-computed `chain_digest`.
:func:`test_repair_twice_writes_nothing_the_second_time` runs the whole command twice against
an already-seeded database and requires byte-identical verdicts and a census that did not
move.

WHERE THE RECORDED BYTES COME FROM
-----------------------------------
`verticals/mainline/apps/console/fixtures/memory-loop/` — raw response bodies the deployed
API returned on 2026-08-15, captured by `scripts/demo/capture_memory_loop.py` and owned by the
memory-visible lead. This module does not own them; it reads them, checks each one against the
SHA-256 in that directory's own `manifest.json`, and fails loudly if a body has been edited by
hand. Two of `demo_ready`'s five requests — `GET /v1/health` and
`GET /v1/change-requests/{cr_id}` — have no committed capture, so their payloads here are
MODELS of the deployed shape, read off the live URL on 2026-08-16 and reduced to the members
`demo_ready` actually looks at. They are labelled as models where they are built.

THE NETWORK IS NOT REACHED BY DEFAULT. Nothing in this module puts traffic on the public
deployment unless `MAINLINE_DEMO_READY_LIVE=1` is exported, and the one test that does says so
in its skip reason. A suite that quietly hit the live URL would go red on a bad network and
green on a bad world, which is the wrong way round for both.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_READY_PY = REPO_ROOT / "scripts" / "demo" / "demo_ready.py"
SEED_DEMO_PY = REPO_ROOT / "scripts" / "deploy" / "seed_demo.py"
DEMO_WORLD_SQL = REPO_ROOT / "verticals" / "mainline" / "db" / "seeds" / "demo" / "demo_world.sql"
SEEDS_DIR = REPO_ROOT / "verticals" / "mainline" / "db" / "seeds" / "demo"
MIGRATIONS_DIR = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"
CAPTURE_MEMORY_LOOP_PY = REPO_ROOT / "scripts" / "demo" / "capture_memory_loop.py"
DOC = REPO_ROOT / "docs" / "demo" / "DEMO-READY.md"
FIXTURES = REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "fixtures" / "memory-loop"

#: The scratch database this module repairs. Lowercase because CockroachDB folds an unquoted
#: identifier: `CREATE DATABASE w_P1` produces `w_p1`, and a fixture that spelled it the other
#: way would look for a database the cluster does not have.
SCRATCH_DATABASE = "w_p1"

LIVE_ENV = "MAINLINE_DEMO_READY_LIVE"


def _load(path: Path, name: str) -> Any:
    """Import a script by path, handing ``sys.path`` straight back.

    The same manoeuvre, for the same measured reason, as
    ``verticals/mainline/apps/demo-api/tests/conftest.py::_deployer``: the script inserts the
    repository ROOT on ``sys.path`` so its own sibling imports resolve, and a root left there
    makes eight top-level directories importable as namespace packages for everything
    collected afterwards. That is a session-wide change no test owns.
    """
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"no importable module at {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    restore = list(sys.path)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.path[:] = restore
    return module


@pytest.fixture(scope="module")
def demo_ready() -> Any:
    return _load(DEMO_READY_PY, "mainline_demo_ready_under_test")


@pytest.fixture(scope="module")
def seed_demo() -> Any:
    return _load(SEED_DEMO_PY, "mainline_seed_demo_for_demo_ready_tests")


# ── the recorded bytes, checked against the manifest that describes them ───────────────────


def _capture(name: str) -> Any:
    """One recorded body, verified against ``manifest.json`` before it is parsed.

    The digest check is the whole reason this is a function rather than a `json.load`. These
    bytes are evidence about the deployed API; a body somebody edited to make a test pass is
    the exact defect the falsification tests below exist to catch, one layer down.
    """
    manifest_path = FIXTURES / "manifest.json"
    assert manifest_path.is_file(), (
        f"{manifest_path} is absent. These captures are recorded by "
        "scripts/demo/capture_memory_loop.py and are owned by the memory-visible lead; this "
        "module reads them and does not write them. Re-capture, or say why they went."
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((row for row in manifest["captures"] if row["name"] == name), None)
    assert entry is not None, f"{name!r} is not in {manifest_path}"
    raw = (FIXTURES / entry["file"]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == entry["sha256_hex"], (
        f"{entry['file']} does not match the SHA-256 its own manifest records. The recording "
        "was edited by hand, which makes it evidence about nothing."
    )
    return json.loads(raw.decode("utf-8"))


#: A MODEL, not a capture: `GET /v1/health` has no committed recording. Every member below
#: was read off the deployed origin on 2026-08-16 and the set is reduced to what
#: `demo_ready._fact_target_live` looks at. If a capture is ever committed, replace this.
def _health_model(**overrides: Any) -> dict[str, Any]:
    body = {
        "ok": True,
        "database": "mainline_demo",
        "deploy_chain_applied": 271,
        "deploy_chain_files": 271,
    }
    body.update(overrides)
    return body


#: A MODEL, same reason: `GET /v1/change-requests/{cr_id}` has no committed recording. The
#: `constraints` list is the deployed one reduced to the CHECK this fact is about.
def _change_request_model(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "cr_id": "dec0de00-000c-4000-8000-000000000001",
        "external_ref": "DEMO-MOC-0001",
        "state": "checks_materialised",
        "merged_commit": None,
        "counters": {"open_blocking": 1, "open_conflicts": 0, "open_residue": 0},
        "constraints": [
            {
                "constraint": "cr_gate_closed_when_merged",
                "blamed_by_refusal": False,
                "counters": [{"column": "open_blocking", "value": 1}],
            }
        ],
    }
    data.update(overrides)
    return {"data": data, "envelope_version": 1}


# ── the constants, held to the files that own them ────────────────────────────────────────


def test_the_four_exit_codes_are_four_different_numbers(demo_ready: Any) -> None:
    codes = {
        "OK": demo_ready.EXIT_OK,
        "NOT_READY": demo_ready.EXIT_NOT_READY,
        "USAGE": demo_ready.EXIT_USAGE,
        "ACTION_REQUIRED": demo_ready.EXIT_ACTION_REQUIRED,
    }
    assert list(codes.values()) == [0, 1, 2, 3]
    # The whole point of a fourth code: "a human must act" must never be read as "the gate
    # did not refuse". Collapsing 3 into 1 is what this assertion exists to stop.
    assert len(set(codes.values())) == 4


def test_the_identifiers_agree_with_the_files_that_write_them(
    demo_ready: Any, seed_demo: Any
) -> None:
    assert demo_ready.PERMIT_ID == seed_demo.PERMIT_ID
    assert demo_ready.CHECK_ID == seed_demo.CHECK_ID
    # `seed_demo` carries no change-request constant, so the CR is held to the seed file that
    # writes the row. `demo_world.sql` is the only place it comes from.
    sql = DEMO_WORLD_SQL.read_text(encoding="utf-8")
    assert demo_ready.CR_ID in sql
    assert demo_ready.CR_EXTERNAL_REF in sql
    assert demo_ready.PERMIT_EXTERNAL_REF in (
        sql + (SEEDS_DIR / "demo_permit.sql").read_text(encoding="utf-8")
    )
    assert demo_ready.SIGNER_SUB in sql
    assert demo_ready.COUNTERSIGNER_SUB in sql


def test_the_refusal_it_expects_is_the_one_seed_demo_expects(
    demo_ready: Any, seed_demo: Any
) -> None:
    assert demo_ready.EXPECTED_REFUSAL_SQLSTATE == seed_demo.EXPECTED_SQLSTATE
    assert demo_ready.EXPECTED_REFUSAL_CONSTRAINT == seed_demo.EXPECTED_CONSTRAINT
    # …and it is beat 2 of the four the deployed gate-run drives, spelled identically.
    beat = next(b for b in demo_ready.EXPECTED_BEATS if b[0] == "merge")
    assert beat[2] == seed_demo.EXPECTED_SQLSTATE
    assert beat[3] == seed_demo.EXPECTED_CONSTRAINT


def test_the_origin_is_the_one_the_other_tool_addresses(demo_ready: Any) -> None:
    """Two programs pointing at two different deployments is a demo that films two worlds."""
    source = CAPTURE_MEMORY_LOOP_PY.read_text(encoding="utf-8")
    match = re.search(r'^DEFAULT_BASE = "([^"]+)"', source, re.MULTILINE)
    assert match is not None, f"no DEFAULT_BASE in {CAPTURE_MEMORY_LOOP_PY}"
    capture_tool_base = match.group(1)
    manifest_base = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))["base_url"]
    assert capture_tool_base == demo_ready.DEFAULT_BASE
    assert manifest_base == demo_ready.DEFAULT_BASE


def test_only_five_requests_are_possible_and_only_one_is_a_post() -> None:
    """The wire surface is read off the source, not off a promise in a docstring.

    Every `/v1/…` string anywhere in the file, comments and docstrings included, has to be one
    of the five plan §R4 permits. Naming a sixth in a comment is how a sixth gets sent.
    """
    source = DEMO_READY_PY.read_text(encoding="utf-8")
    allowed = (
        "/v1/health",
        "/v1/demo/subjects",
        "/v1/demo/gate-run",
        "/v1/permits/",
        "/v1/change-requests/",
    )
    for path in sorted(set(re.findall(r"/v1/[A-Za-z0-9\-_{}/.:]*", source))):
        assert path.startswith(allowed), f"{path!r} is not one of the five permitted requests"
    # One POST, and it is the one plan §R4 permits by name.
    assert source.count('self._send("POST"') == 1
    assert '"POST", "/v1/demo/gate-run"' in source
    assert source.count('self._send("GET"') == 1


def test_nothing_in_this_program_can_reach_aws() -> None:
    """No AWS client, no terraform verb, no SSM write, no credential. Plan §R2.

    ``aws`` itself is not a bannable substring — the deployed Function URL ends in
    ``.on.aws`` — so the ban is on the things that would actually reach the account.
    """
    source = DEMO_READY_PY.read_text(encoding="utf-8").lower()
    for forbidden in (
        "boto3",
        "botocore",
        "terraform",
        "put_parameter",
        "secretsmanager",
        "aws_access_key",
        "aws_secret",
        "get_credentials",
    ):
        assert forbidden not in source, f"{forbidden!r} appears in {DEMO_READY_PY}"


# ── the report: deterministic, aligned, and honest about its mode ──────────────────────────


def _facts(demo_ready: Any, *, all_pass: bool = True) -> list[Any]:
    return [
        demo_ready.Fact("target", True, "GET /v1/health", "ok=true"),
        demo_ready.Fact("obligation", all_pass, "GET /v1/permits/{permit_id}/blocking-checks", "x"),
    ]


def test_render_is_byte_identical_between_two_calls(demo_ready: Any) -> None:
    facts = _facts(demo_ready)
    header = ["target    x", "mode      y", "asked by  z"]
    first = demo_ready.render(facts, header, demo_ready.FOOTNOTES_LIVE)
    second = demo_ready.render(facts, header, demo_ready.FOOTNOTES_LIVE)
    assert first == second
    # Nothing that moves between two runs may reach stdout.
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", first)
    assert "elapsed" not in first


def test_one_failed_fact_is_enough_to_refuse_the_verdict(demo_ready: Any) -> None:
    good = demo_ready.render(_facts(demo_ready), [], demo_ready.FOOTNOTES_LIVE)
    bad = demo_ready.render(_facts(demo_ready, all_pass=False), [], demo_ready.FOOTNOTES_LIVE)
    assert "VERDICT  READY" in good and "Roll camera." in good
    assert "VERDICT  NOT READY" in bad and "1 FAILED" in bad
    assert "Roll camera." not in bad
    assert "Do not roll" in bad


def test_the_table_columns_line_up(demo_ready: Any) -> None:
    lines = [
        demo_ready.Fact("target", True, "GET /v1/health", "a").line(),
        demo_ready.Fact("change_request", False, "SELECT mainline.change_request", "b").line(),
    ]
    starts = {line.index("  ", 0) for line in lines}
    assert starts == {4}
    for line in lines:
        assert line[:4] in ("PASS", "FAIL")
        assert line[6 : 6 + 14].strip() in ("target", "change_request")


def test_the_notes_describe_the_mode_they_are_printed_in(demo_ready: Any) -> None:
    """A note that names a request the run never made is this file explaining fiction."""
    live = dict(demo_ready.FOOTNOTES_LIVE)
    local = dict(demo_ready.FOOTNOTES_LOCAL)
    assert "gate-run" in live["unchanged"]
    assert "gate-run" not in local["unchanged"]
    assert "seed_demo" in local["refusal"] and "refusal" not in live
    # Both modes name the projector beside the four. Plan §R9.
    for notes in (live, local):
        assert "mainline.fn_check_project" in notes["obligation"]
        assert "MI25" in notes["obligation"]
    # `--repair` DID write. The word "unchanged" must not be allowed to imply it did not.
    repair = dict(demo_ready.FOOTNOTES_LOCAL_REPAIR)
    assert set(repair) == set(local)
    assert "APPLIED the two seed files" in repair["unchanged"]
    assert "APPLIED the two seed files" not in local["unchanged"]
    assert repair["obligation"] == local["obligation"]


# ── falsification: every fact is shown a world in which it is false ────────────────────────


def test_the_recorded_gate_run_passes_all_four_of_its_facts(demo_ready: Any) -> None:
    """The control. Without this, the four failures below prove only that the code raises."""
    facts = demo_ready._gate_run_facts(200, _capture("gate-run"))
    assert [f.fact_id for f in facts] == ["zeros", "signers", "refusal", "unchanged"]
    assert all(f.ok for f in facts), [f.line() for f in facts if not f.ok]


def test_the_eight_facts_are_declared_once_and_the_orderer_refuses_a_seventh(
    demo_ready: Any,
) -> None:
    assert len(demo_ready.FACT_ORDER) == len(set(demo_ready.FACT_ORDER)) == 8
    good = [demo_ready.Fact(name, True, "s", "d") for name in demo_ready.FACT_ORDER]
    assert [f.fact_id for f in demo_ready._in_order(list(reversed(good)))] == list(
        demo_ready.FACT_ORDER
    )
    with pytest.raises(RuntimeError, match="FACT_ORDER"):
        demo_ready._in_order(good[:-1])
    with pytest.raises(RuntimeError, match="FACT_ORDER"):
        demo_ready._in_order([*good, demo_ready.Fact("ninth", True, "s", "d")])


@pytest.mark.parametrize(
    ("pointer", "value", "should_fail"),
    [
        (("data", "persisted"), True, "unchanged"),
        (("data", "persistence_check", "identical"), False, "unchanged"),
        (("data", "persistence_check", "self_persisted"), True, "unchanged"),
        (("data", "verdict"), "NOT PROVEN", "refusal"),
        (("data", "outcome"), "aborted", "signers"),
    ],
)
def test_a_gate_run_that_moved_makes_its_own_fact_fail(
    demo_ready: Any, pointer: tuple[str, ...], value: Any, should_fail: str
) -> None:
    payload = _capture("gate-run")
    node = payload
    for key in pointer[:-1]:
        node = node[key]
    node[pointer[-1]] = value
    facts = {f.fact_id: f for f in demo_ready._gate_run_facts(200, payload)}
    assert not facts[should_fail].ok, facts[should_fail].line()


def test_a_disposition_row_makes_the_two_zeros_fail(demo_ready: Any) -> None:
    payload = _capture("gate-run")
    payload["data"]["persistence_check"]["before"]["row_counts"]["mainline.disposition"] = 1
    facts = {f.fact_id: f for f in demo_ready._gate_run_facts(200, payload)}
    assert not facts["zeros"].ok
    assert "mainline.disposition=1" in facts["zeros"].detail


def test_a_beat_that_stopped_refusing_makes_the_refusal_fail(demo_ready: Any) -> None:
    """The forged-counter beat is the strongest thing we own. It is checked by name."""
    payload = _capture("gate-run")
    attack = payload["data"]["beats"][2]
    assert attack["name"] == "projection_drift_attack"
    attack["outcome"], attack["sqlstate"], attack["constraint"] = "admitted", "00000", None
    facts = {f.fact_id: f for f in demo_ready._gate_run_facts(200, payload)}
    assert not facts["refusal"].ok
    assert "projection_drift_attack" in facts["refusal"].detail


def test_a_non_200_fails_every_fact_that_request_feeds(demo_ready: Any) -> None:
    facts = demo_ready._gate_run_facts(429, {"error": "rate limited"})
    assert not any(f.ok for f in facts)
    assert all("429" in f.detail for f in facts)
    assert "rate-limits" in facts[0].detail


def test_the_recorded_subjects_and_checks_pass(demo_ready: Any) -> None:
    permit, data = demo_ready._fact_permit_live(200, _capture("subjects"))
    assert permit.ok, permit.line()
    assert data["permit_id"] == demo_ready.PERMIT_ID
    obligation = demo_ready._fact_obligation_live(200, _capture("blocking-checks"))
    assert obligation.ok, obligation.line()
    assert "severity=4" in obligation.detail and "blood_major" in obligation.detail


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("state", "merged"),
        ("open_blocking", 0),
        ("gate_epoch", 2),
        ("permit_id", "dec0de00-0006-4000-8000-000000000002"),
        ("external_ref", "DEMO-PTW-0002"),
        ("count", 2),
    ],
)
def test_a_permit_that_moved_fails(demo_ready: Any, key: str, value: Any) -> None:
    payload = _capture("subjects")
    payload["data"]["subjects"]["permit"][key] = value
    fact, _data = demo_ready._fact_permit_live(200, payload)
    assert not fact.ok, fact.line()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("open", False),
        ("disposition_id", "9b24b84c-1313-44c4-9589-867c9267a1a8"),
        ("severity", 3),
        ("virulence", "routine"),
        ("origin", "manual"),
        ("check_id", "dec0de00-0007-4000-8000-000000000002"),
    ],
)
def test_an_obligation_that_was_answered_fails(demo_ready: Any, key: str, value: Any) -> None:
    payload = _capture("blocking-checks")
    payload["data"]["checks"][0][key] = value
    fact = demo_ready._fact_obligation_live(200, payload)
    assert not fact.ok, fact.line()


def test_a_second_open_obligation_fails(demo_ready: Any) -> None:
    payload = _capture("blocking-checks")
    payload["data"]["checks"].append(dict(payload["data"]["checks"][0]))
    fact = demo_ready._fact_obligation_live(200, payload)
    assert not fact.ok
    assert "2 open checks" in fact.detail


def test_the_modelled_health_passes_and_every_way_it_can_go_wrong_fails(demo_ready: Any) -> None:
    assert demo_ready._fact_target_live(200, _health_model()).ok
    assert not demo_ready._fact_target_live(200, _health_model(ok=False)).ok
    part = demo_ready._fact_target_live(200, _health_model(deploy_chain_applied=270))
    assert not part.ok and "part-applied" in part.detail
    grown = demo_ready._fact_target_live(
        200, _health_model(deploy_chain_applied=272, deploy_chain_files=272)
    )
    # A LONGER chain is not broken — it is a chain nobody re-recorded, and the film's overlay
    # says 271. The line must say that rather than "part-applied".
    assert not grown.ok and "overlay" in grown.detail
    assert not demo_ready._fact_target_live(200, _health_model(database="w_p1")).ok
    assert not demo_ready._fact_target_live(503, {}).ok


def test_the_modelled_change_request_passes_and_a_merged_one_fails(demo_ready: Any) -> None:
    assert demo_ready._fact_change_request_live(200, _change_request_model()).ok
    merged = demo_ready._fact_change_request_live(
        200, _change_request_model(state="merged", merged_commit="ab" * 32)
    )
    assert not merged.ok and "MERGED" in merged.detail
    ungated = demo_ready._fact_change_request_live(
        200, _change_request_model(counters={"open_blocking": 0})
    )
    assert not ungated.ok and "nothing gates it" in ungated.detail


# ── the refusals, which happen before anything is opened ───────────────────────────────────


def test_repair_refuses_the_protected_database_and_names_the_orchestrators_command(
    demo_ready: Any,
) -> None:
    with pytest.raises(demo_ready.ActionRequired) as refused:
        demo_ready.guard_target(
            "postgresql://root@localhost:26257/mainline_demo?sslmode=disable",
            "mainline_demo",
            repair=True,
        )
    assert demo_ready.ORCHESTRATOR_SEED_COMMAND in str(refused.value)
    # The set of protected names is IMPORTED from the program that already protects them.
    from scripts.deploy import verify_demo_checkpoints

    assert "mainline_demo" in verify_demo_checkpoints.PROTECTED_DATABASES


def test_repair_refuses_a_remote_host_and_check_calls_it_usage(demo_ready: Any) -> None:
    remote = "postgresql://root@a.cloud.example:26257/mainline_demo?sslmode=require"
    with pytest.raises(demo_ready.ActionRequired):
        demo_ready.guard_target(remote, "mainline_demo", repair=True)
    with pytest.raises(demo_ready.Unreachable):
        demo_ready.guard_target(remote, "mainline_demo", repair=False)


def test_repair_with_no_local_database_is_action_required(demo_ready: Any) -> None:
    with pytest.raises(demo_ready.ActionRequired) as refused:
        demo_ready.guard_target(None, "", repair=True)
    assert demo_ready.ORCHESTRATOR_SEED_COMMAND in str(refused.value)


def test_check_against_a_read_only_local_mirror_is_allowed(demo_ready: Any) -> None:
    """Reading the local `mainline_demo` mirror is fine; only writing to it is refused."""
    demo_ready.guard_target(
        "postgresql://root@localhost:26257/mainline_demo?sslmode=disable",
        "mainline_demo",
        repair=False,
    )


def test_main_exits_three_and_prints_the_command(demo_ready: Any) -> None:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = demo_ready.main(
            [
                "--dsn",
                "postgresql://root@localhost:26257/mainline_demo?sslmode=disable",
                "--repair",
            ]
        )
    assert code == demo_ready.EXIT_ACTION_REQUIRED == 3
    assert "ACTION REQUIRED" in out.getvalue()
    assert demo_ready.ORCHESTRATOR_SEED_COMMAND in out.getvalue()
    # Nothing was measured, so nothing may be reported: a refusal that also printed a table
    # would read as a verdict about the world.
    assert "VERDICT" not in out.getvalue()


# ── the local database: the same command, twice, against a world it must not move ──────────


def _census(dsn: str, tables: tuple[str, ...]) -> dict[str, int]:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=30, autocommit=True) as conn:
        return {
            table: int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608
            for table in tables
        }


def _seeded(dsn: str, permit_id: str) -> bool:
    import psycopg

    try:
        with psycopg.connect(dsn, connect_timeout=30, autocommit=True) as conn:
            row = conn.execute(
                "SELECT count(*) FROM mainline.permit WHERE permit_id = %s", (permit_id,)
            ).fetchone()
    except psycopg.Error:
        return False
    return bool(row and row[0] == 1)


@pytest.fixture(scope="module")
def seeded_scratch(shared_cluster: Any, demo_ready: Any, seed_demo: Any) -> str:
    """A LOCAL, non-protected database carrying the demo world. Built once if absent.

    The build is the deployment's own: ``trappoint_migrate``'s discovery over
    ``verticals/mainline/db/migrations``, then ``seed_demo.apply_seeds`` through
    ``seed_demo.Applier`` — the function that puts the demo into CockroachDB Cloud, called
    rather than copied. It costs minutes on a cold cluster and nothing at all on a warm one,
    because a database that already carries the permit is adopted.
    """
    from urllib.parse import urlsplit, urlunsplit

    import psycopg

    parts = urlsplit(shared_cluster.dsn)
    admin = urlunsplit((parts.scheme, parts.netloc, "/defaultdb", parts.query, parts.fragment))
    dsn = urlunsplit(
        (parts.scheme, parts.netloc, f"/{SCRATCH_DATABASE}", parts.query, parts.fragment)
    )
    # The program's own guard is asked, rather than a second opinion about the same set: this
    # database must be one `--repair` is ALLOWED to write to, or the two tests below would be
    # asserting the refusal instead of the idempotence.
    demo_ready.guard_target(dsn, SCRATCH_DATABASE, repair=True)

    if _seeded(dsn, demo_ready.PERMIT_ID):
        return dsn

    with psycopg.connect(admin, connect_timeout=30, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE IF NOT EXISTS {SCRATCH_DATABASE}")

    sys.path.insert(0, str(REPO_ROOT / "packages" / "trappoint-migrate" / "src"))
    try:
        from trappoint_migrate.bootstrap import bootstrap
        from trappoint_migrate.discovery import discover
        from trappoint_migrate.runner import DEFAULT_SCHEMA_PREFIXES, actor
    finally:
        sys.path.pop(0)

    with psycopg.connect(dsn, autocommit=True) as conn:
        bootstrap(conn, applied_by=actor(), schema_prefixes=DEFAULT_SCHEMA_PREFIXES)
        failures = []
        for migration in discover(MIGRATIONS_DIR):
            try:
                conn.execute(migration.path.read_text(encoding="utf-8"))
            except psycopg.Error as exc:
                failures.append(f"{migration.path.name} [{exc.sqlstate}]")
        assert not failures, f"the deploy chain did not apply: {failures[:5]}"

    applier = seed_demo.Applier(dsn)
    try:
        rows = seed_demo.apply_seeds(applier, SEEDS_DIR)
    finally:
        applier.close()
    assert not [row for row in rows if row["error"]], rows
    assert _seeded(dsn, demo_ready.PERMIT_ID)
    return dsn


def _run(demo_ready: Any, argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = demo_ready.main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.requires_cluster
def test_check_twice_is_byte_identical_and_writes_nothing(
    demo_ready: Any, seed_demo: Any, seeded_scratch: str
) -> None:
    before = _census(seeded_scratch, seed_demo.COUNTED)
    first_code, first_out, _ = _run(demo_ready, ["--dsn", seeded_scratch])
    second_code, second_out, _ = _run(demo_ready, ["--dsn", seeded_scratch])
    after = _census(seeded_scratch, seed_demo.COUNTED)

    assert first_code == second_code == demo_ready.EXIT_OK, first_out
    assert "VERDICT  READY" in first_out
    assert first_out == second_out, "two --check runs disagreed about an unchanged world"
    assert before == after, "--check is read-only and it wrote something"
    # The SAME eight facts as the deployment answers, in the same order. A mode with a
    # different fact set would mean "ready" meant two things.
    printed = [line.split()[1] for line in first_out.splitlines() if line[:4] in ("PASS", "FAIL")]
    assert tuple(printed) == demo_ready.FACT_ORDER


@pytest.mark.requires_cluster
def test_repair_twice_writes_nothing_the_second_time(
    demo_ready: Any, seed_demo: Any, seeded_scratch: str
) -> None:
    """The trap. `docs/deploy/cloud-database.md` §5, measured.

    `ON CONFLICT DO NOTHING` does not suppress a BEFORE INSERT trigger's exception, and a
    second run of `demo_world.sql` once raised `P0001 closure generations must be dense and
    monotone` from `fn_closure_guard` and aborted the batch. If that ever comes back, this is
    where it is found out: the second run below would raise rather than agree.
    """
    first_code, first_out, _ = _run(demo_ready, ["--dsn", seeded_scratch, "--repair"])
    between = _census(seeded_scratch, seed_demo.COUNTED)
    second_code, second_out, second_err = _run(demo_ready, ["--dsn", seeded_scratch, "--repair"])
    after = _census(seeded_scratch, seed_demo.COUNTED)

    assert first_code == second_code == demo_ready.EXIT_OK, first_out + second_out
    assert first_out == second_out, "two --repair runs disagreed about an unchanged world"
    assert between == after, f"the second --repair wrote rows: {between} -> {after}"
    # The seed files WERE applied — a run that skipped them would prove nothing about
    # idempotence. `seed_demo`'s own lines are passed through to stderr, so they are here.
    assert "demo_world.sql" in second_err and "demo_permit.sql" in second_err
    assert "VERDICT  READY" in second_out


@pytest.mark.requires_cluster
def test_repair_pointed_at_mainline_demo_writes_nothing(
    demo_ready: Any, seed_demo: Any, shared_cluster: Any
) -> None:
    """Exit 3 against the local mirror, and the mirror is measured before and after."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(shared_cluster.dsn)
    mirror = urlunsplit((parts.scheme, parts.netloc, "/mainline_demo", parts.query, parts.fragment))
    if not _seeded(mirror, demo_ready.PERMIT_ID):
        pytest.skip(
            "there is no local mainline_demo mirror on this cluster, so there is nothing to "
            "measure before and after. The refusal itself is asserted without a cluster by "
            "test_main_exits_three_and_prints_the_command."
        )
    before = _census(mirror, seed_demo.COUNTED)
    code, out, _err = _run(demo_ready, ["--dsn", mirror, "--repair"])
    after = _census(mirror, seed_demo.COUNTED)
    assert code == demo_ready.EXIT_ACTION_REQUIRED
    assert demo_ready.ORCHESTRATOR_SEED_COMMAND in out
    assert before == after


# ── the deployment, only when somebody asks for it ─────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get(LIVE_ENV) != "1",
    reason=(
        f"opt-in: export {LIVE_ENV}=1 to put four GETs and one POST /v1/demo/gate-run on the "
        "public deployment. Not a pass — this run did not ask the deployment anything."
    ),
)
def test_the_deployment_answers_the_same_way_twice(demo_ready: Any) -> None:
    first_code, first_out, first_err = _run(demo_ready, [])
    second_code, second_out, _ = _run(demo_ready, [])
    assert first_code == second_code == demo_ready.EXIT_OK, first_out
    assert first_out == second_out
    assert "VERDICT  READY" in first_out
    assert "OVER THE BOUND" not in first_err


# ── the document, held to the program ──────────────────────────────────────────────────────


def test_the_document_states_the_exit_code_table(demo_ready: Any) -> None:
    text = DOC.read_text(encoding="utf-8")
    for code, word in (
        (demo_ready.EXIT_OK, "READY"),
        (demo_ready.EXIT_NOT_READY, "NOT READY"),
        (demo_ready.EXIT_USAGE, "USAGE"),
        (demo_ready.EXIT_ACTION_REQUIRED, "ACTION REQUIRED"),
    ):
        assert re.search(rf"^\|\s*`{code}`\s*\|\s*{re.escape(word)}\b", text, re.MULTILINE), (
            f"{DOC} has no exit-code row for {code} = {word}"
        )


def test_the_document_names_the_trap_and_its_measurement() -> None:
    text = DOC.read_text(encoding="utf-8")
    for phrase in (
        "ON CONFLICT DO NOTHING",
        "BEFORE INSERT",
        "P0001",
        "closure generations must be dense and monotone",
        "fn_closure_guard",
        "INSERT ... SELECT ... WHERE NOT EXISTS",
        "clause_version",
        "clause_blame_closure",
        "cbm_account",
        "permit_event",
        "prev_digest",
        "chain_digest",
        "docs/deploy/cloud-database.md",
    ):
        assert phrase in text, f"{DOC} does not name {phrase!r}"


def test_the_document_names_every_fact_the_program_checks(demo_ready: Any) -> None:
    text = DOC.read_text(encoding="utf-8")
    facts = demo_ready._gate_run_facts(200, _capture("gate-run"))
    ids = {f.fact_id for f in facts} | {"target", "permit", "obligation", "change_request"}
    for fact_id in sorted(ids):
        assert f"`{fact_id}`" in text, f"{DOC} does not document the fact {fact_id!r}"
