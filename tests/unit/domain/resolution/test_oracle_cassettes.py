# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The committed Path-B recordings: current, complete, and harmless when hostile.

Decision D12 makes the cassette store *the* Path B for every run in CI and on a
stranger's laptop, because AWS credentials are not valid on the build machine as
of 2026-08 and PL-3 forbids putting an unproven capability on a dated path.  A
store in that position has two failure modes that nothing else in this suite
catches, and this module is both of them.

**1. The store goes stale and nobody notices.**  A cassette key is
``sha256(profile_id ‖ prompt_version ‖ jcs(call_input))``, so editing the prompt,
the profile, the request builder or the CAT diff changes every key.  A stale
store does not fail loudly — the *one* scenario the integrity suite exercises may
still be on disk while ten others are orphaned files nothing replays.
``mainline_delta_oracle.cassettes.STORE_README`` and the committed
``tests/fixtures/domain/oracle/cassettes/README.md`` have both promised, since
the store was created, that this file compares the committed bytes against a
fresh generation.  Until now the file did not exist, so the promise was the only
thing holding.  :func:`divergences` is that comparison, and
``test_the_comparator_*`` run it against deliberately corrupted stores so that a
green result here means the comparator can go red.

**2. Ten of the eleven recordings are never replayed.**  ``test_cassette_integrity``
drives ``contradicts_high`` and nothing else; the four failure modes the worker's
exit criterion names — schema violation, model refusal, guardrail intervention,
truncation — live in cassettes that, until this module, no test replayed through
the real call path.  Every scenario is now driven end to end, from the recorded
bytes through ``quarantined_call`` → the deterministic verifier → ``to_verdict``
→ ``resolve``, and asserted to reach both its declared verdict and a delta of
record that still refuses the merge.

**What this module does not cover, deliberately.**  Throttle and timeout are not
recordable: they are exceptions raised by a transport that never returned a body,
so there is no cassette to hold them.  They are asserted against a raising
transport in
``tests/unit/domain/oracle_adversary/test_transport_hostility.py::test_a_transport_failure_is_an_abstention``.
The split is real and the cross-reference is here so that a reader counting the
failure modes does not conclude two are missing.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple

import pytest
from mainline_agentkit import AgentkitSettings
from mainline_delta_oracle.cassettes import SCENARIOS, Scenario, record_scenarios
from mainline_delta_oracle.oracle import PROMPT_VERSION, AdjudicationOracle
from mainline_delta_oracle.transport import default_cassette_root
from mainline_domain.contracts import ControlDelta, DeltaVerdict, DeltaWitness, force
from mainline_domain.resolution import (
    REASON_FOR_ABSTENTION_CODE,
    abstention_code_of,
    explain,
    requires_silence_record,
    silence_record,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# --------------------------------------------------------------------------- #
# Fixtures of record                                                           #
# --------------------------------------------------------------------------- #

#: The store that ships in the repository.  Everything here is measured against it.
_COMMITTED: Final[Path] = default_cassette_root()

#: The offline lane, stated explicitly rather than inherited from the process
#: environment: a test whose provider depends on an env var is a test that
#: silently changes meaning on a developer machine with credentials.
_OFFLINE: Final[AgentkitSettings] = AgentkitSettings(provider="cassette", cassette_mode="replay")

#: The one field a re-recording is allowed to change.  ``recorded_at`` is wall
#: clock; every other byte is a function of the profile, the prompt and the
#: request, and a change in any of them is the thing this module exists to catch.
_VOLATILE_FIELDS: Final[frozenset[str]] = frozenset({"recorded_at"})

_SCENARIO_IDS: Final[list[str]] = [item.name for item in SCENARIOS]


class Expected(NamedTuple):
    """What one recorded scenario must produce when it is replayed."""

    abstained: bool
    label: ControlDelta
    confidence: float
    code: str | None


#: The expectation table, declared here rather than derived from the scenario's
#: own prose, so that a change in behaviour is a failing assertion instead of a
#: quietly-agreeing pair of strings.  ``test_the_table_agrees_with_the_scenario_prose``
#: then checks the two against each other in the one direction that is safe.
EXPECTED: Final[dict[str, Expected]] = {
    "contradicts_high": Expected(False, ControlDelta.WEAKEN, 0.85, None),
    "entails_high": Expected(False, ControlDelta.STRENGTHEN, 0.85, None),
    "neutral_high": Expected(False, ControlDelta.RESTATE, 0.85, None),
    "neutral_low": Expected(False, ControlDelta.RESTATE, 0.25, None),
    "model_abstains": Expected(True, ControlDelta.WEAKEN, 0.0, "model_abstained"),
    "quote_not_verbatim": Expected(True, ControlDelta.WEAKEN, 0.0, "quote_not_verbatim"),
    "unsupported_numeric_claim": Expected(
        True, ControlDelta.WEAKEN, 0.0, "unsupported_numeric_claim"
    ),
    "schema_violation": Expected(True, ControlDelta.WEAKEN, 0.0, "schema_violation"),
    "truncated": Expected(True, ControlDelta.WEAKEN, 0.0, "truncated"),
    "guardrail_intervention": Expected(True, ControlDelta.WEAKEN, 0.0, "guardrail_intervention"),
    "model_refusal": Expected(True, ControlDelta.WEAKEN, 0.0, "model_refusal"),
}

#: The failure modes the worker's exit criterion names by hand.  Kept as a
#: separate constant so that deleting a scenario cannot quietly delete the
#: coverage claim with it.
NAMED_FAILURE_MODES: Final[frozenset[str]] = frozenset(
    {"schema_violation", "model_refusal", "guardrail_intervention", "truncated"}
)


def _witnessed_weaken() -> DeltaVerdict:
    """A well-formed Path-A weakening — witnessed, because decision D8 requires it."""
    return DeltaVerdict(
        delta=ControlDelta.WEAKEN,
        basis="lattice",
        witnesses=(
            DeltaWitness(
                rule_id="R7_FREQUENCY",
                field="frequency",
                from_repr="30 min",
                to_repr="120 min",
                note="the gas-test interval was lengthened fourfold",
            ),
        ),
        minimal=True,
    )


def _restate() -> DeltaVerdict:
    """A zero-force Path-A verdict, which needs no witness."""
    return DeltaVerdict(delta=ControlDelta.RESTATE, basis="lattice", witnesses=(), minimal=True)


def _oracle(root: Path | None = None) -> AdjudicationOracle:
    return AdjudicationOracle(cassette_root=root or _COMMITTED, settings=_OFFLINE)


@pytest.fixture(scope="module")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A store recorded from scratch by the shipped generator, this run."""
    root = tmp_path_factory.mktemp("regenerated") / "cassettes"
    written = record_scenarios(root)
    assert written, "the generator recorded nothing; the comparison below would be vacuous"
    return root


@pytest.fixture
def writable(tmp_path: Path) -> Path:
    """A private, mutable copy of the committed store, for the corruption tests."""
    root = tmp_path / "cassettes"
    root.mkdir()
    for path in _COMMITTED.glob("*.json"):
        shutil.copy2(path, root / path.name)
    assert list(root.glob("*.json")), "the committed store is empty"
    return root


# --------------------------------------------------------------------------- #
# The comparator                                                               #
# --------------------------------------------------------------------------- #


def _payload(path: Path) -> dict[str, Any]:
    body: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise TypeError(f"{path} is not a JSON object")
    return {name: value for name, value in body.items() if name not in _VOLATILE_FIELDS}


def divergences(expected_root: Path, actual_root: Path) -> list[str]:
    """Every way ``actual_root`` differs from ``expected_root``, ``recorded_at`` aside.

    Written as a function returning findings rather than as a bare ``assert``
    because two of the tests below run it against stores that are corrupted on
    purpose.  A comparator that has only ever been run against a matching pair
    asserts nothing about a mismatched one.

    Returns:
        One human-readable finding per divergence, sorted, empty when the two
        stores agree.  Each finding names the key, because a message that says
        only "the fixtures are stale" leaves the reader to find which one.
    """
    expected = {path.stem: path for path in expected_root.glob("*.json")}
    actual = {path.stem: path for path in actual_root.glob("*.json")}
    found: list[str] = [
        f"missing: {key} is committed and the generator did not produce it"
        for key in expected.keys() - actual.keys()
    ]
    found.extend(
        f"orphan: {key} was generated and is not committed"
        for key in actual.keys() - expected.keys()
    )
    for key in sorted(expected.keys() & actual.keys()):
        left = _payload(expected[key])
        right = _payload(actual[key])
        if left == right:
            continue
        fields = sorted(
            name for name in left.keys() | right.keys() if left.get(name) != right.get(name)
        )
        found.append(f"changed: {key} differs in {fields}")
    return sorted(found)


# --------------------------------------------------------------------------- #
# 1. The store is current                                                      #
# --------------------------------------------------------------------------- #


def test_the_committed_store_is_what_the_generator_produces(fresh: Path) -> None:
    """The promise made in two READMEs, finally asserted.

    A failure here means the prompt, the profile, the request builder or a
    scenario changed and the recordings did not.  Regenerate with
    ``mainline_delta_oracle.cassettes.record_scenarios(root)`` and commit the
    result; do not edit a cassette by hand, because the key is a digest of the
    input and a hand-edited body is a recording of a call that was never made.
    """
    found = divergences(_COMMITTED, fresh)
    assert found == [], "the committed cassette store is stale:\n  " + "\n  ".join(found)


def test_the_key_set_is_exactly_the_recorded_calls(fresh: Path) -> None:
    """No orphan recordings, and one file per call the generator actually issued."""
    generated = record_scenarios(fresh)  # idempotent; returns the keys by scenario
    expected_keys = {key for keys in generated.values() for key in keys}
    on_disk = {path.stem for path in _COMMITTED.glob("*.json")}
    assert on_disk == expected_keys
    assert set(generated) == set(EXPECTED), "a scenario was added or removed without a table entry"
    assert len(generated["schema_violation"]) == 2, (
        "the dead-letter path records the retry as a second call, and both keys must be "
        "on disk or the path cannot be replayed at all"
    )


def test_recorded_at_is_the_only_field_the_comparison_ignores(writable: Path) -> None:
    """The exclusion list is narrow on purpose, and the narrowness is asserted."""
    target = next(iter(sorted(writable.glob("*.json"))))
    body = json.loads(target.read_text(encoding="utf-8"))
    assert body["recorded_at"], "a recording with no timestamp cannot be dated in evidence"
    body["recorded_at"] = "1999-12-31T23:59:59+00:00"
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert divergences(_COMMITTED, writable) == []


# --------------------------------------------------------------------------- #
# 2. The comparator can go red (PL-2)                                          #
# --------------------------------------------------------------------------- #


def test_the_comparator_reports_a_deleted_recording(writable: Path) -> None:
    """The staleness a prompt edit actually produces: keys that moved."""
    victim = sorted(writable.glob("*.json"))[0]
    victim.unlink()
    found = divergences(_COMMITTED, writable)
    assert found == [f"missing: {victim.stem} is committed and the generator did not produce it"]


def test_the_comparator_reports_an_orphan_recording(writable: Path) -> None:
    """The other half of a key change: a file nothing replays."""
    (writable / f"{'0' * 64}.json").write_text(
        json.dumps({"key": "0" * 64}, indent=2) + "\n", encoding="utf-8"
    )
    found = divergences(_COMMITTED, writable)
    assert found == [f"orphan: {'0' * 64} was generated and is not committed"]


def test_the_comparator_reports_an_edited_body(writable: Path) -> None:
    """A hand-edited recording is a recording of a call that was never made."""
    target = writable / f"{_key_for('contradicts_high')}.json"
    body = json.loads(target.read_text(encoding="utf-8"))
    body["response"]["stop_reason"] = "max_tokens"
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    found = divergences(_COMMITTED, writable)
    assert found == [f"changed: {target.stem} differs in ['response']"]


def test_the_comparator_reports_a_forged_provenance(writable: Path) -> None:
    """``synthetic`` → ``live`` is the one-word edit that would fake a Bedrock run."""
    target = writable / f"{_key_for('model_refusal')}.json"
    body = json.loads(target.read_text(encoding="utf-8"))
    body["provenance"] = "live"
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    found = divergences(_COMMITTED, writable)
    assert found == [f"changed: {target.stem} differs in ['provenance']"]


# --------------------------------------------------------------------------- #
# 3. Every recording is replayed, through the real call path                   #
# --------------------------------------------------------------------------- #


def _key_for(name: str) -> str:
    item = _scenario(name)
    return _oracle().request_identity(item.request)["cassette_key"]


def _scenario(name: str) -> Scenario:
    for item in SCENARIOS:
        if item.name == name:
            return item
    raise KeyError(name)


@pytest.mark.parametrize("item", SCENARIOS, ids=_SCENARIO_IDS)
def test_every_scenario_replays_to_its_declared_outcome(item: Scenario) -> None:
    """From the committed bytes to an ``OracleVerdict``, once per behaviour.

    Ten of these eleven had no replay test before this module existed, which
    means the deterministic verifier's two rejections, the dead-letter path, the
    truncation path, the Guardrail path and the refusal path were all reachable
    only through code review.
    """
    want = EXPECTED[item.name]
    outcome = _oracle().classify_with_provenance(item.request)
    verdict = outcome.verdict

    assert verdict.abstained is want.abstained
    assert verdict.label is want.label
    assert verdict.confidence == pytest.approx(want.confidence)
    assert abstention_code_of(verdict.rationale) == want.code
    assert verdict.prompt_version == PROMPT_VERSION
    assert outcome.provenance["outcome"] == ("abstained" if want.abstained else "ok")
    assert (verdict.cited_spans == ()) is want.abstained, (
        "a verdict carries a located evidence span exactly when it is not an abstention"
    )


@pytest.mark.parametrize("item", SCENARIOS, ids=_SCENARIO_IDS)
def test_no_recorded_scenario_clears_a_lattice_weakening(item: Scenario) -> None:
    """The money assertion, once per recording, at both ends of the theta range.

    theta is swept because the whole family of threshold bugs — ``>`` for ``>=``,
    a band midpoint landing exactly on the boundary — only shows up at one value.
    """
    lattice = _witnessed_weaken()
    verdict = _oracle().classify(item.request)
    for theta in (0.0, 0.25, 0.5, 0.85, 1.0):
        resolved = explain(lattice, verdict, theta=theta)
        assert force(resolved.verdict.delta) >= force(ControlDelta.WEAKEN), (
            f"{item.name} at theta={theta} cleared a lattice weakening: "
            f"{resolved.verdict.delta.value}"
        )
        assert resolved.verdict.witnesses == lattice.witnesses
        assert resolved.verdict.basis in {"lattice", "lattice+model", "abstain_to_weaken"}


@pytest.mark.parametrize(
    "item",
    [item for item in SCENARIOS if EXPECTED[item.name].abstained],
    ids=sorted(name for name, want in EXPECTED.items() if want.abstained),
)
def test_every_abstaining_recording_is_ledgerable(item: Scenario) -> None:
    """P5: an abstention that writes no arithmetic is a silence nobody can audit."""
    verdict = _oracle().classify(item.request)
    resolved = explain(_restate(), verdict, theta=0.75)

    assert resolved.verdict.delta is ControlDelta.WEAKEN
    assert resolved.verdict.basis == "abstain_to_weaken"
    assert requires_silence_record(resolved) is True

    row = silence_record(
        resolved,
        site_id="00000000-0000-0000-0000-00000000site",
        subject_id="00000000-0000-0000-0000-0000000clause",
        max_ancestral_severity=5,
        policy_version="identity-policy-v1",
        policy_sha256="0" * 64,
    )
    code = abstention_code_of(verdict.rationale)
    assert code is not None
    assert row.reason == REASON_FOR_ABSTENTION_CODE[code]
    assert row.source == "delta_neutral"
    assert row.arithmetic["abstention_code"] == code
    assert row.arithmetic["path_a_delta"] == "restate"
    assert row.arithmetic["resolved_delta"] == "weaken"


def test_the_named_failure_modes_are_all_covered_by_a_committed_recording() -> None:
    """The worker's exit criterion, read as a coverage claim over the store.

    Throttle and timeout are deliberately absent: they are exceptions from a
    transport that returned no body, so no cassette can hold them.  See the
    module docstring for where they are asserted instead.
    """
    recorded = {item.name for item in SCENARIOS}
    assert recorded >= NAMED_FAILURE_MODES
    for name in sorted(NAMED_FAILURE_MODES):
        want = EXPECTED[name]
        assert want.abstained is True
        assert want.code == name, (
            f"{name} is named as a failure mode and its abstention code is {want.code!r}; "
            f"the two vocabularies have drifted"
        )
        verdict = _oracle().classify(_scenario(name).request)
        resolved = explain(_restate(), verdict, theta=0.0)
        assert force(resolved.verdict.delta) >= force(ControlDelta.WEAKEN), (
            f"{name} did not fail closed even at theta=0, where every confidence counts"
        )


def test_the_table_agrees_with_the_scenario_prose() -> None:
    """The generator's ``expects`` string and this module's table cannot drift apart."""
    for item in SCENARIOS:
        want = EXPECTED[item.name]
        assert item.expects.startswith("abstained") is want.abstained, (
            f"{item.name} declares {item.expects!r} and the table says abstained={want.abstained}"
        )


# --------------------------------------------------------------------------- #
# 4. The lane is offline, and the index is true                                #
# --------------------------------------------------------------------------- #


def test_replaying_the_whole_store_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """PL-1: the proof runs on a machine with no credential and no network.

    ``test_the_default_lane_is_offline`` in the adversary suite asserts the
    *settings*.  This asserts the behaviour, which is a different claim: a
    provider can be configured for replay and still resolve a hostname.
    """

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the replay lane opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    oracle = _oracle()
    for item in SCENARIOS:
        oracle.classify(item.request)


def _readme_rows() -> Iterator[tuple[str, list[str]]]:
    """Parse the committed index: one ``(scenario, key prefixes)`` pair per row."""
    text = (_COMMITTED / "README.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        name = cells[0].strip("`")
        prefixes = [
            token for token in re.findall(r"`([0-9a-f]+)[^`]*`", cells[2]) if len(token) >= 8
        ]
        yield name, prefixes


def test_the_store_readme_indexes_every_scenario(fresh: Path) -> None:
    """A human-readable index that has drifted from the keys is worse than none."""
    generated = record_scenarios(fresh)
    rows = dict(_readme_rows())
    assert set(rows) == set(generated), (
        f"the README indexes {sorted(rows)} and the generator produces {sorted(generated)}"
    )
    for name, prefixes in rows.items():
        keys = generated[name]
        assert len(prefixes) == len(keys), (
            f"{name}: the README lists {len(prefixes)} keys and the generator produced {len(keys)}"
        )
        for prefix, key in zip(prefixes, keys, strict=True):
            assert key.startswith(prefix), f"{name}: README says {prefix}…, the key is {key}"


def test_the_store_readme_names_this_file() -> None:
    """The promise that produced this module, asserted so it cannot go stale again.

    Both the committed index and ``cassettes.STORE_README`` tell a reader that a
    fresh generation is compared against the committed bytes *here*.  For most of
    this store's life that path did not exist, which is the quietest kind of
    false claim: a reader checks the sentence, not the filesystem.
    """
    promised = "tests/unit/domain/resolution/test_oracle_cassettes.py"
    index = (_COMMITTED / "README.md").read_text(encoding="utf-8")
    assert promised in index
    repo_root = Path(__file__).resolve().parents[4]
    assert (repo_root / promised).is_file()
    assert Path(__file__).resolve() == (repo_root / promised).resolve()
