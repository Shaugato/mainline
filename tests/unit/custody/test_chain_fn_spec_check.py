# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CU-9 — the conformance check that keeps the chain trigger and its specification together.

``scripts/custody/check_chain_fn_matches_spec.py`` is the executable half of
``spec/custody/chain-verification.md``: the specification says what
``mainline.fn_permit_event_chain`` must be, and the check refuses to let the database and
the document drift apart. This file is what keeps *the check* honest.

**Nothing here needs a cluster.** The live assertions are exercised against a fake whose
four methods are the only cluster surface the check has, so every verdict the check can
reach — PASS, FAIL and each distinct SKIP — is reached here, on a laptop with no
credential. The measured behaviour of the real thing (CockroachDB v26.2.5) is recorded in
the module docstring of the check and in the fixtures below, each labelled with where the
string came from.

The assertions deliberately avoid pinning *today's* verdict on the real repository. The
spec and the shipped migration currently disagree, and that disagreement is a finding for
the leads to reconcile — not a fact this file should encode, because encoding it would
make the reconciliation break a test that has nothing to do with it. What is asserted
about the real tree is **totality**: every variant is reported on, and no assertion goes
silently missing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "custody" / "check_chain_fn_matches_spec.py"


def _load_check():
    """Import the check by path.

    It lives under ``scripts/`` and is not an installed distribution, so there is no
    import name for it. Registering the module in ``sys.modules`` before executing it is
    not optional: ``dataclasses`` resolves a class's module out of ``sys.modules`` while
    processing it, and a module absent from there raises ``AttributeError`` on the first
    ``@dataclass``.
    """
    spec = importlib.util.spec_from_file_location("trappoint_check_chain_fn", SCRIPT)
    assert spec is not None, f"{SCRIPT} is not importable"
    assert spec.loader is not None, f"{SCRIPT} has no loader"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = _load_check()


# ======================================================================================
# The scanner and the normaliser
# ======================================================================================


@pytest.mark.parametrize(
    ("left", "right", "equal"),
    [
        # Whitespace, case and the trailing semicolon are free.
        ("SELECT a FROM t;", "select   A\n  from  T", True),
        # Comments are not part of the routine.
        ("SELECT 1 -- trailing\n", "SELECT 1", True),
        ("SELECT /* block */ 1", "SELECT 1", True),
        ("SELECT /* /* nested */ still */ 1", "SELECT 1", True),
        # Literals and quoted identifiers are load-bearing and must survive verbatim.
        ("SELECT 'Refused'", "SELECT 'refused'", False),
        ('SELECT "Mixed"', 'SELECT "mixed"', False),
        # A comment marker inside a literal is data, not a comment.
        ("SELECT '-- not a comment'", "SELECT ''", False),
        ("SELECT '-- not a comment'", "SELECT '-- not a comment' ", True),
        # The dollar-quote tag is a delimiter, not content.
        ("f() AS $$ BEGIN RETURN 1; END $$", "f() as $body$ begin return 1; end $body$", True),
        # Semantic differences survive. These are exactly the ones §3 warns against
        # normalising away.
        ("IF a <> b", "IF a != b", False),
        ("IF a IS DISTINCT FROM b", "IF a IS NOT DISTINCT FROM b", False),
        ("IF (NEW).seq = 0", "IF NEW.seq = 0", False),
    ],
)
def test_normalisation_folds_only_what_is_free(left: str, right: str, equal: bool) -> None:
    assert (check.normalise_sql(left) == check.normalise_sql(right)) is equal


def test_semicolons_inside_a_body_do_not_split_statements() -> None:
    sql = (
        "CREATE FUNCTION f() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$\n"
        "BEGIN\n  RETURN NEW;\nEND $$;\n"
        "CREATE TRIGGER t BEFORE INSERT ON x FOR EACH ROW EXECUTE FUNCTION f();\n"
    )
    statements = check.split_statements(sql)
    assert len(statements) == 2
    assert check.normalise_sql(statements[0]).startswith("create function f()")
    assert check.normalise_sql(statements[1]).startswith("create trigger t")


def test_semicolons_inside_a_literal_do_not_split_statements() -> None:
    statements = check.split_statements("SELECT 'a;b'; SELECT 2;")
    assert len(statements) == 2


def test_strip_comments_leaves_submittable_sql() -> None:
    """The regression that the probe schema rewrite depends on.

    Migration ``0105``'s header comment quotes its own ``CREATE FUNCTION`` line. An
    unanchored rewrite over the raw statement renames the copy inside the comment, leaves
    the real one pointing at ``mainline``, and the server answers with a duplicate-function
    error that says nothing about the cause.
    """
    statement = (
        "-- CREATE FUNCTION mainline.fn_permit_event_chain - the chain is verified\n"
        "CREATE FUNCTION mainline.fn_permit_event_chain() RETURNS TRIGGER\n"
        "  LANGUAGE PLpgSQL AS $$ BEGIN RETURN NEW; END $$;"
    )
    stripped = check.strip_comments(statement)
    assert stripped.startswith("CREATE FUNCTION mainline.fn_permit_event_chain()")
    assert stripped.count("CREATE FUNCTION") == 1
    # Case and spacing inside the body are preserved; only comments are gone.
    assert "BEGIN RETURN NEW; END" in stripped


# ======================================================================================
# Reading the specification
# ======================================================================================


def test_the_real_specification_yields_both_normative_statements() -> None:
    """The document must keep the shape the check is specified against (§2, §3)."""
    text = (REPO_ROOT / check.SPEC_RELATIVE).read_text(encoding="utf-8")
    normative = check.extract_normative(text)
    assert check.normalise_sql(normative.create_function).startswith(
        "create function mainline.fn_permit_event_chain()"
    )
    shape = check.parse_trigger(normative.create_trigger)
    assert shape == check.TriggerShape(
        name="permit_event_chain",
        timing="before",
        events=("insert",),
        level="row",
        table="mainline.permit_event",
        function="mainline.fn_permit_event_chain",
    )


def test_a_document_without_the_normative_block_is_refused() -> None:
    with pytest.raises(check.SpecificationError):
        check.extract_normative("# nothing here\n\n```sql\nSELECT 1;\n```\n")


def test_a_document_with_two_normative_blocks_is_refused() -> None:
    block = (
        "```sql\nCREATE FUNCTION mainline.fn_permit_event_chain() RETURNS TRIGGER\n"
        "  LANGUAGE PLpgSQL AS $$ BEGIN RETURN NEW; END $$;\n```\n"
    )
    with pytest.raises(check.SpecificationError):
        check.extract_normative(block + "\n" + block)


def test_the_change_request_mirror_is_derived_not_transcribed() -> None:
    """§2: ``cr_event`` mirrors ``permit_event`` exactly, substituting ``cr_id``."""
    text = (REPO_ROOT / check.SPEC_RELATIVE).read_text(encoding="utf-8")
    mirrored = check.normative_for(check.extract_normative(text), check.CHANGE_REQUEST)
    body = check.normalise_sql(mirrored.create_function)
    assert "mainline.fn_cr_event_chain" in body
    assert "mainline.cr_event" in body
    assert "cr_id" in body
    assert "permit" not in body
    assert check.parse_trigger(mirrored.create_trigger).name == "cr_event_chain"


# ======================================================================================
# Trigger shapes — the rendering conventions differ, the shape must not
# ======================================================================================


def test_trigger_shape_ignores_database_qualification() -> None:
    """Measured on cockroachdb/cockroach:v26.2.5 — ``pg_get_triggerdef`` returns
    three-part names and no trailing semicolon, while the migration writes two-part
    names. Comparing strings would report a difference that is not one."""
    rendered = (
        "CREATE TRIGGER permit_event_chain BEFORE INSERT ON "
        "defaultdb.mainline.permit_event FOR EACH ROW EXECUTE FUNCTION "
        "defaultdb.mainline.fn_permit_event_chain()"
    )
    authored = (
        "CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event\n"
        "  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();"
    )
    assert check.parse_trigger(rendered) == check.parse_trigger(authored)


@pytest.mark.parametrize(
    "mutation",
    [
        "AFTER INSERT ON mainline.permit_event FOR EACH ROW",
        "BEFORE UPDATE ON mainline.permit_event FOR EACH ROW",
        "BEFORE INSERT ON mainline.permit_event FOR EACH STATEMENT",
        "BEFORE INSERT ON mainline.cr_event FOR EACH ROW",
    ],
)
def test_trigger_shape_notices_every_field(mutation: str) -> None:
    authored = (
        "CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event "
        "FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();"
    )
    mutated = (
        f"CREATE TRIGGER permit_event_chain {mutation} "
        "EXECUTE FUNCTION mainline.fn_permit_event_chain();"
    )
    assert check.parse_trigger(authored) != check.parse_trigger(mutated)


def test_an_unparseable_trigger_raises_rather_than_comparing_equal() -> None:
    with pytest.raises(check.SpecificationError):
        check.parse_trigger("CREATE TRIGGER t BEFORE INSERT ON x FOR EACH ROW")


# ======================================================================================
# End to end, offline, on a synthetic tree
# ======================================================================================


@pytest.mark.parametrize(
    ("mutate", "weld", "extra", "expected"),
    [
        (False, True, [], 0),
        (False, True, ["--strict"], 1),  # the live assertions SKIP; --strict makes that fatal
        (True, True, [], 1),  # a semantic change to the body
        (False, False, [], 1),  # the weld removed
        (True, False, [], 1),
    ],
)
def test_offline_end_to_end(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutate: bool,
    weld: bool,
    extra: list[str],
    expected: int,
) -> None:
    check._selftest_tree(tmp_path, mutate=mutate, weld=weld)
    assert check.main(["--repo-root", str(tmp_path), "--no-cluster", *extra]) == expected
    captured = capsys.readouterr().out
    # Whatever the verdict, both variants are reported on. A check that quietly stops
    # looking is the failure mode this whole domain exists to refuse.
    for variant in check.VARIANTS:
        assert f"A1 mainline.{variant.function}" in captured
        assert f"A2 {variant.trigger}" in captured


def test_a_missing_specification_fails_rather_than_skips(tmp_path: Path) -> None:
    assert check.main(["--repo-root", str(tmp_path), "--no-cluster"]) == 1


def test_a_missing_migration_skips_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    check._selftest_tree(tmp_path, mutate=False, weld=True)
    (tmp_path / check.MIGRATIONS_RELATIVE / check.PERMIT.function_migration).unlink()
    assert check.main(["--repo-root", str(tmp_path), "--no-cluster"]) == 0
    captured = capsys.readouterr().out
    assert "SKIP" in captured
    assert "NOT CHECKED" in captured
    assert check.main(["--repo-root", str(tmp_path), "--no-cluster", "--strict"]) == 1


def test_a_migration_that_defines_no_function_fails(tmp_path: Path) -> None:
    check._selftest_tree(tmp_path, mutate=False, weld=True)
    (tmp_path / check.MIGRATIONS_RELATIVE / check.PERMIT.function_migration).write_text(
        "-- the body was deleted\n", encoding="utf-8", newline="\n"
    )
    assert check.main(["--repo-root", str(tmp_path), "--no-cluster"]) == 1


def test_the_scripts_own_selftest_passes() -> None:
    """PL-2 in miniature: the check ships a proof that its assertions bite."""
    assert check.selftest() == 0


# ======================================================================================
# The live assertions, against a fake whose surface is the whole cluster surface
# ======================================================================================


SPEC_BODY = (
    "CREATE FUNCTION mainline.fn_permit_event_chain() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$\n"
    "DECLARE expected BYTES;\n"
    "BEGIN\n"
    "  IF NEW.seq = 0 THEN RETURN NEW; END IF;\n"
    "  RETURN NEW;\n"
    "END $$;"
)

SPEC_TRIGGER = (
    "CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event\n"
    "  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();"
)

SPEC_DOCUMENT = f"## 2. The normative body\n\n```sql\n{SPEC_BODY}\n\n{SPEC_TRIGGER}\n```\n"

#: Shaped like the real thing: measured on cockroachdb/cockroach:v26.2.5, the renderer
#: re-prints the parsed tree — attribute block inserted, ``NEW`` folded to ``new``,
#: comments gone. The check never compares this to source text, only to another rendering.
RENDERED = (
    "CREATE FUNCTION {schema}.fn_permit_event_chain()\n"
    "\tRETURNS TRIGGER\n\tVOLATILE\n\tNOT LEAKPROOF\n\tCALLED ON NULL INPUT\n"
    "\tLANGUAGE plpgsql\n\tSECURITY INVOKER\n\tAS $$\n"
    "\tDECLARE\n\texpected BYTES;\n\tBEGIN\n"
    "\tIF new.seq = 0 THEN\n\t\tRETURN new;\n\tEND IF;\n"
    "\t{tail}\n\tEND;\n$$"
)

RENDERED_TRIGGER = (
    "CREATE TRIGGER permit_event_chain BEFORE INSERT ON defaultdb.mainline.permit_event "
    "FOR EACH ROW EXECUTE FUNCTION defaultdb.mainline.fn_permit_event_chain()"
)


class FakeCluster(check.LiveCluster):
    """The four methods :func:`check_live` calls, and nothing else.

    Subclassed from the real class so that a change to the cluster surface breaks this
    fake loudly rather than letting the tests pass against a shape that no longer exists.
    """

    def __init__(
        self,
        *,
        table: bool = True,
        function: str | None = None,
        trigger: str | None = None,
        probe_error: Exception | None = None,
    ) -> None:
        super().__init__(connection=None)
        self._table = table
        self._function = function
        self._trigger = trigger
        self._probe_error = probe_error
        self.rendered: list[str] = []

    # The arguments are unused on purpose: this fake answers a fixed scenario, and the
    # signatures exist to stay override-compatible with the real cluster surface.
    def table_exists(self, schema: str, table: str) -> bool:  # noqa: ARG002
        return self._table

    def function_definition(self, schema: str, name: str) -> str | None:  # noqa: ARG002
        return self._function

    def trigger_definition(
        self,
        schema: str,  # noqa: ARG002
        table: str,  # noqa: ARG002
        trigger: str,  # noqa: ARG002
    ) -> str | None:
        return self._trigger

    def render(self, create_function: str, variant: check.Variant) -> str:
        if self._probe_error is not None:
            raise self._probe_error
        self.rendered.append(create_function)
        return RENDERED.format(schema=variant.schema, tail="RETURN new;")


def _run_live(cluster: check.LiveCluster, *, probe: bool = True) -> check.Report:
    report = check.Report()
    normative = check.extract_normative(SPEC_DOCUMENT)
    check.check_live(cluster, normative, report, probe=probe)
    return report


def _verdicts(report: check.Report, prefix: str) -> list[str]:
    return [verdict for verdict, message in report.lines if message.startswith(prefix)]


def test_live_body_equal_to_the_specified_body_passes() -> None:
    cluster = FakeCluster(
        function=RENDERED.format(schema="mainline", tail="RETURN new;"),
        trigger=RENDERED_TRIGGER,
    )
    report = _run_live(cluster)
    assert _verdicts(report, "A3 mainline.fn_permit_event_chain") == [check.PASS]
    assert _verdicts(report, "A4 permit_event_chain") == [check.PASS]
    # The probe was handed the specified body, not the live one.
    assert "fn_permit_event_chain" in cluster.rendered[0]


def test_a_mutated_live_body_fails_with_a_diff() -> None:
    cluster = FakeCluster(
        function=RENDERED.format(schema="mainline", tail="RETURN NULL;"),
        trigger=RENDERED_TRIGGER,
    )
    report = _run_live(cluster)
    assert _verdicts(report, "A3 mainline.fn_permit_event_chain") == [check.FAIL]
    assert any("return null" in detail for detail in report.details)


def test_a_missing_live_function_fails_when_the_table_is_there() -> None:
    report = _run_live(FakeCluster(function=None, trigger=RENDERED_TRIGGER))
    assert _verdicts(report, "A3 mainline.fn_permit_event_chain") == [check.FAIL]
    assert any("A11" in message for _, message in report.lines)


def test_a_dropped_trigger_fails_and_names_the_attack() -> None:
    cluster = FakeCluster(
        function=RENDERED.format(schema="mainline", tail="RETURN new;"), trigger=None
    )
    report = _run_live(cluster)
    assert _verdicts(report, "A4 permit_event_chain") == [check.FAIL]
    assert any("A13" in message for _, message in report.lines)


def test_a_reshaped_trigger_fails() -> None:
    cluster = FakeCluster(
        function=RENDERED.format(schema="mainline", tail="RETURN new;"),
        trigger=RENDERED_TRIGGER.replace("BEFORE INSERT", "AFTER INSERT"),
    )
    assert _verdicts(_run_live(cluster), "A4 permit_event_chain") == [check.FAIL]


def test_an_unmigrated_cluster_skips_rather_than_failing() -> None:
    report = _run_live(FakeCluster(table=False))
    assert report.failed == 0
    assert report.skipped == len(check.VARIANTS)


def test_a_refused_probe_skips_with_the_servers_own_reason() -> None:
    cluster = FakeCluster(
        function=RENDERED.format(schema="mainline", tail="RETURN new;"),
        trigger=RENDERED_TRIGGER,
        probe_error=RuntimeError("permission denied for database defaultdb"),
    )
    report = _run_live(cluster)
    assert _verdicts(report, "A3 mainline.fn_permit_event_chain") == [check.SKIP]
    assert any("permission denied" in message for _, message in report.lines)
    # The weld is still checked; one unavailable assertion does not silence the others.
    assert _verdicts(report, "A4 permit_event_chain") == [check.PASS]


def test_no_probe_skips_loudly_rather_than_comparing_source_to_a_rendering() -> None:
    cluster = FakeCluster(
        function=RENDERED.format(schema="mainline", tail="RETURN new;"),
        trigger=RENDERED_TRIGGER,
    )
    report = _run_live(cluster, probe=False)
    assert _verdicts(report, "A3 mainline.fn_permit_event_chain") == [check.SKIP]
    assert cluster.rendered == []


def test_no_dsn_anywhere_is_a_skip_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in check.DSN_ENV:
        monkeypatch.delenv(name, raising=False)
    check._selftest_tree(tmp_path, mutate=False, weld=True)
    assert check.main(["--repo-root", str(tmp_path)]) == 0
    captured = capsys.readouterr().out
    assert "NOT CHECKED" in captured
    assert "no cluster" in captured
    assert check.main(["--repo-root", str(tmp_path), "--strict"]) == 1


# ======================================================================================
# Totality over the real repository
# ======================================================================================


def test_every_shipped_migration_yields_the_statement_the_check_reads() -> None:
    """Independent of whether the bodies agree, the files must remain readable.

    A migration the check cannot parse would report FAIL for a reason that has nothing to
    do with drift, and the diagnosis is the deliverable.
    """
    migrations = REPO_ROOT / check.MIGRATIONS_RELATIVE
    for variant in check.VARIANTS:
        function_path = migrations / variant.function_migration
        trigger_path = migrations / variant.trigger_migration
        if not function_path.is_file() or not trigger_path.is_file():
            pytest.skip(f"{variant.label}: migrations have not landed yet")
        body = check.find_statement(
            check.split_statements(function_path.read_text(encoding="utf-8")),
            f"CREATE FUNCTION {variant.schema}.{variant.function}(",
        )
        assert body is not None, f"{variant.function_migration} defines no {variant.function}"
        assert check.strip_comments(body).upper().startswith("CREATE FUNCTION")
        welded = check.find_statement(
            check.split_statements(trigger_path.read_text(encoding="utf-8")),
            f"CREATE TRIGGER {variant.trigger} ",
        )
        assert welded is not None, f"{variant.trigger_migration} welds no {variant.trigger}"
        assert check.parse_trigger(welded).function == f"{variant.schema}.{variant.function}"


def test_the_real_repository_is_reported_on_in_full(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Totality, not verdict.

    Whether the shipped body currently matches the specification is a question for the
    leads; whether every assertion produced a line is a question for this file. A check
    that drops an assertion on the floor reports a smaller number of failures and looks
    like progress.
    """
    for name in check.DSN_ENV:
        monkeypatch.delenv(name, raising=False)
    exit_code = check.main(["--repo-root", str(REPO_ROOT), "--no-cluster"])
    assert exit_code in (0, 1)
    captured = capsys.readouterr().out
    for variant in check.VARIANTS:
        assert f"A1 mainline.{variant.function}" in captured
        assert f"A2 {variant.trigger}" in captured
    assert "A3/A4 live conformance" in captured
    assert "chain function conformance:" in captured
