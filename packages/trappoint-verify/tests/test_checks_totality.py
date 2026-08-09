# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Check 16's build-time half: the registry, the runners and the tests must agree.

``spec/custody/checks.yaml`` is normative and lives in the repository.
``trappoint_verify.checks.SPEC_ROWS`` is a copy of it inside the wheel, because
``uvx trappoint-verify explain-check 14`` has to work on a machine that has never seen
this repository. Two copies of one truth is a defect *unless* a machine compares them, so
this file compares them row by row.

The four totality rules ``checks.yaml`` states about itself, made executable:

1. every check id ``1..16`` appears exactly once;
2. a check whose status is ``implemented`` (or ``implemented_but_not_adverse``) names a
   module that resolves **and** a test that exists;
3. a check whose status is ``deferred`` is not reachable as ``PASS`` at runtime — or, where
   it *is* implemented ahead of the registry flip, the discrepancy is declared in
   ``SPEC_STATUS_LAG`` and therefore visible;
4. the ``offline`` column, not prose anywhere, is what the product claim is computed from.

Rule 3 needs a word. ``checks.yaml`` was frozen with all sixteen ``deferred``, which was
honest on 2026-08-07 because no verifier existed. It has one owner and this package does
not edit other people's files, so the flip to ``implemented`` lands with that worker. The
window between the two is real; the choice here is to **name it in code and assert its
exact extent** rather than to let either copy quietly imply something the other denies.

PyYAML is not used. This package's CI lane installs ``cryptography`` and nothing else, and
a test that only runs when an optional parser happens to be present is a test that is
absent exactly when someone is trimming dependencies. The reader below handles the shape
``checks.yaml`` is specified to have and raises on anything else.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PACKAGE_ROOT / "src"
if str(_SRC) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_SRC))

from trappoint_verify.checks import (  # noqa: E402
    CHECK_IDS,
    SPEC_ROWS,
    SPEC_STATUS_LAG,
    load_all,
    modules_for_checks,
    registered,
)

COMPARED_FIELDS = (
    "name",
    "proves",
    "defeats",
    "offline",
    "module",
    "test",
    "status",
    "target_status",
    "owner",
)
IMPLEMENTED_STATUSES = frozenset({"implemented", "implemented_but_not_adverse"})
#: ``checks.yaml`` computes the product claim from this column: fifteen of sixteen checks
#: need nothing from us. Only check 8's live half needs the network.
EXPECTED_ONLINE_CHECKS = frozenset({8})


def repo_root() -> Path | None:
    """The MAINLINE checkout containing this package, or ``None`` if we are outside one."""
    for candidate in [_PACKAGE_ROOT, *_PACKAGE_ROOT.parents]:
        if (candidate / "spec" / "custody" / "checks.yaml").is_file():
            return candidate
    return None


def _scalar(text: str) -> Any:
    if text in ("true", "false"):
        return text == "true"
    if text == "null":
        return None
    if text.lstrip("-").isdigit():
        return int(text)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def read_checks_yaml(path: Path) -> list[dict[str, Any]]:
    """Read the ``checks:`` sequence. Not a YAML parser — a reader for one known shape."""
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_checks = False
    folding: tuple[str, list[str]] | None = None

    def flush() -> None:
        nonlocal folding
        if folding is not None and current is not None:
            key, parts = folding
            current[key] = " ".join(" ".join(parts).split())
        folding = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())

        if indent == 0:
            flush()
            in_checks = stripped == "checks:"
            current = None
            continue
        if not in_checks:
            continue
        if indent == 2 and stripped.startswith("- "):
            flush()
            current = {}
            rows.append(current)
            key, _, value = stripped[2:].partition(":")
            current[key.strip()] = _scalar(value.strip())
            continue
        if current is None:
            continue
        if indent > 4 and folding is not None:
            folding[1].append(stripped)
            continue
        if indent != 4:
            continue
        flush()
        key, separator, value = stripped.partition(":")
        if not separator:
            raise ValueError(f"{path}: line {raw!r} is not `key: value`")
        value = value.strip()
        if value in ("", ">-", ">", "|"):
            folding = (key.strip(), [])
        else:
            current[key.strip()] = _scalar(value)
    flush()
    if not rows:
        raise ValueError(f"{path} lists no checks; a registry that empties itself is a defect")
    return rows


@pytest.fixture(scope="module")
def yaml_rows() -> list[dict[str, Any]]:
    root = repo_root()
    if root is None:  # pragma: no cover - only when the wheel is tested outside the repo
        pytest.skip(
            "not running inside the MAINLINE checkout; spec/custody/checks.yaml is unreachable"
        )
    return read_checks_yaml(root / "spec" / "custody" / "checks.yaml")


# --------------------------------------------------------------------------------------
# Rule 1 — every id exactly once, in both copies
# --------------------------------------------------------------------------------------


def test_every_check_id_appears_exactly_once(yaml_rows: list[dict[str, Any]]):
    ids = [row["id"] for row in yaml_rows]
    assert ids == list(range(1, 17)), ids
    assert list(CHECK_IDS) == ids


def test_the_embedded_registry_matches_the_normative_yaml(yaml_rows: list[dict[str, Any]]):
    """Row by row, field by field. The wheel and the repository say the same thing or fail."""
    by_id = {row["id"]: row for row in yaml_rows}
    for spec in SPEC_ROWS:
        row = by_id[spec.id]
        for field in COMPARED_FIELDS:
            expected = row[field]
            actual = getattr(spec, field)
            if isinstance(expected, str):
                expected = " ".join(expected.split())
                actual = " ".join(str(actual).split())
            assert actual == expected, (
                f"check {spec.id}.{field}: the copy in trappoint_verify.checks says "
                f"{actual!r}; spec/custody/checks.yaml says {expected!r}"
            )


# --------------------------------------------------------------------------------------
# Rule 2 — implemented means a module and a test really exist
# --------------------------------------------------------------------------------------


def test_every_implemented_row_names_a_module_and_a_test(yaml_rows: list[dict[str, Any]]):
    root = repo_root()
    assert root is not None
    load_all()
    for row in yaml_rows:
        if row["status"] not in IMPLEMENTED_STATUSES:
            continue
        module = row["module"]
        assert module in sys.modules, f"check {row['id']}: {module} did not import"
        assert row["id"] in registered(), f"check {row['id']}: {module} registered no runner"
        assert _test_target_exists(root, row["test"]), row["test"]


def _test_target_exists(root: Path, target: str) -> bool:
    path_text, _, function = target.partition("::")
    path = root / path_text
    if not path.is_file():
        return False
    if not function:
        return True
    return f"def {function}(" in path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# Rule 3 — the lag between the two registries is declared, not hidden
# --------------------------------------------------------------------------------------


def test_the_declared_status_lag_is_exactly_the_real_one(yaml_rows: list[dict[str, Any]]):
    """Fails if a check is implemented without declaring the lag, and when the flip lands."""
    load_all()
    deferred = {row["id"] for row in yaml_rows if row["status"] == "deferred"}
    implemented_here = set(registered())
    actual_lag = tuple(sorted(deferred & implemented_here))
    assert actual_lag == tuple(sorted(SPEC_STATUS_LAG)), (
        "checks.SPEC_STATUS_LAG says the registry lags for "
        f"{tuple(sorted(SPEC_STATUS_LAG))}, but the real discrepancy is {actual_lag}. "
        "Either a check was implemented without declaring the lag, or checks.yaml has "
        "been flipped and this tuple must shrink in the same commit."
    )


def test_every_lagging_check_still_names_a_test_that_exists(yaml_rows: list[dict[str, Any]]):
    """A row may lag on `status`; it may not lag on whether its test is real."""
    root = repo_root()
    assert root is not None
    by_id = {row["id"]: row for row in yaml_rows}
    for check_id in SPEC_STATUS_LAG:
        assert _test_target_exists(root, by_id[check_id]["test"]), by_id[check_id]["test"]


def test_a_check_with_no_runner_reports_skip_and_never_pass():
    """Rule 3's runtime half: an unimplemented check cannot be reached as PASS."""
    from test_structural_checks import context_for, spec_bundle_dict

    from trappoint_verify.checks import VerifyOptions, run_all
    from trappoint_verify.report import Verdict

    load_all()
    bundle = context_for(spec_bundle_dict()).bundle
    report = run_all(bundle, VerifyOptions(), tool_version="test")
    unbound = set(CHECK_IDS) - set(registered())
    for outcome in report.outcomes:
        if outcome.check_id in unbound:
            assert outcome.verdict is Verdict.SKIP
            assert outcome.reason == "not-implemented"


# --------------------------------------------------------------------------------------
# Rule 4 — the product claim is computed from the `offline` column
# --------------------------------------------------------------------------------------


def test_the_offline_claim_is_computed_and_not_asserted(yaml_rows: list[dict[str, Any]]):
    online = {row["id"] for row in yaml_rows if row["offline"] is False}
    assert online == EXPECTED_ONLINE_CHECKS, online
    assert {spec.id for spec in SPEC_ROWS if not spec.offline} == EXPECTED_ONLINE_CHECKS


# --------------------------------------------------------------------------------------
# Both directions: no orphan modules, no orphan runners
# --------------------------------------------------------------------------------------


def test_every_registered_runner_has_a_registry_row():
    load_all()
    assert set(registered()) <= set(CHECK_IDS)


def test_every_check_module_named_in_the_registry_is_wired_for_import():
    """A module nobody imports is a module whose checks can never run."""
    load_all()
    for module, ids in modules_for_checks().items():
        if module in sys.modules:
            continue
        assert not (set(ids) & set(registered())), (
            f"{module} registered runners for {ids} without being importable, which is "
            "impossible unless the registry and the loader disagree"
        )


def test_the_registry_hook_admits_a_new_runner_and_exit_zero_becomes_reachable():
    """The hook worker 7 registers through, exercised — and the proof that ``0`` is reachable.

    Today a real run exits :data:`EXIT_NOT_CHECKED` because seven check modules have not
    landed. That is the honest state, and a test suite in which the clean exit code has
    never been observed could not tell the difference between "unreachable by design" and
    "unreachable because of a bug". So: bind stub runners for the seven ids worker 7 owns,
    run over a bundle every structural check passes, and watch the report reach ``0`` with
    no ``NOT CHECKED`` banner at all.
    """
    from test_structural_checks import context_for, unsigned_bundle_dict

    from trappoint_verify.checks import (
        CheckContext,
        VerifyOptions,
        register_runner,
        run_all,
        spec_for,
        unregister,
    )
    from trappoint_verify.report import EXIT_NOT_CHECKED, EXIT_OK, passed

    load_all()
    stubbed = tuple(check_id for check_id in CHECK_IDS if check_id not in registered())
    assert stubbed, "nothing to stub; worker 7 has landed and this test needs rewriting"
    bundle = context_for(unsigned_bundle_dict()).bundle

    before = run_all(bundle, VerifyOptions(), tool_version="test")
    assert before.exit_code == EXIT_NOT_CHECKED
    assert "NOT CHECKED" in before.render(colour=False)

    def stub(check_id: int):
        def runner(_context: CheckContext):
            return passed(check_id, spec_for(check_id).name, "stub", "stub runner")

        return runner

    for check_id in stubbed:
        register_runner(check_id, stub(check_id))
    try:
        after = run_all(bundle, VerifyOptions(), tool_version="test")
        assert not after.failures, [(o.check_id, o.code, o.detail) for o in after.failures]
        assert not after.skips, [(o.check_id, o.reason) for o in after.skips]
        assert after.exit_code == EXIT_OK
        assert "NOT CHECKED" not in after.render(colour=False)
    finally:
        for check_id in stubbed:
            unregister(check_id)
    assert set(registered()) == set(CHECK_IDS) - set(stubbed)


def test_a_skip_without_a_reason_cannot_be_constructed():
    """The loud-SKIP rule is enforced at construction, not at rendering time."""
    from trappoint_verify.report import Outcome, Verdict

    with pytest.raises(ValueError, match="SKIP with no reason"):
        Outcome(check_id=1, name="x", verdict=Verdict.SKIP, code="", headline="h")


def test_the_structural_module_owns_exactly_the_checks_this_worker_implements():
    """The nine offline structural checks, and no others, come from checks/structural.py."""
    owned = modules_for_checks()["trappoint_verify.checks.structural"]
    assert owned == (1, 2, 3, 9, 10, 13, 14, 15, 16)
    load_all()
    assert set(owned) <= set(registered())
