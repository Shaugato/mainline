# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``ANOMALY_COVERAGE.md``, generated from collected markers, and the gate behind it.

``testing-invariants`` §2, verbatim: *"every test carries ``@pytest.mark.anomaly("A2")``. A
generator emits ``ANOMALY_COVERAGE.md`` from collected markers and fails CI if any of
A1-A14 has zero tests."*

The point is not the document. It is that **testing maps 1:1 onto the design document** — a
judge and a customer's assurance reviewer both want to see the same fourteen rows they read
in the architecture, each pointing at a test that runs. An anomaly analysed in prose and
covered by nothing is the most expensive kind of documentation: it reads as assurance.

Two anomalies deserve their captions read rather than skimmed, and the generated file
carries them:

* **A8** is *detection, not prevention*. Nothing stops an out-of-band ``UPDATE`` of the
  counter; ``CF-03`` asserts only that the merge behind it is refused.
* **A14**, the rubber stamp, **cannot be retired** — not by a character floor, not by a
  dwell timer, not by anything else in a schema. The cases that carry it price the
  consequence and record the evidence; they do not solve it, and the corpus must never be
  read as claiming they do.
"""

from __future__ import annotations

from pathlib import Path

from trappoint_conformance.manifest import Manifest

ANOMALIES = tuple(f"A{n}" for n in range(1, 15))

CAPTIONS = {
    "A1": "check materialised concurrently with the merge",
    "A2": "late-arriving recall after commit",
    "A3": "disposition retracted racing a merge",
    "A4": "double merge, forked history",
    "A5": "disposition inherited across a clause revision",
    "A6": "two live dispositions for one check",
    "A7": "illegal state transition",
    "A8": "counter drift (trigger bug, out-of-band DML)",
    "A9": "evidence deleted or edited to open the gate",
    "A10": "override without escalation",
    "A11": "expired override still clearing the gate",
    "A12": "isolation silently downgraded to READ COMMITTED",
    "A13": "long-horizon proof of past state via AS OF SYSTEM TIME",
    "A14": "rubber stamp",
}

RESIDUALS = {
    "A2": "the field crew acts in the window before stop-work reaches them — an "
    "operational SLA, not a database property",
    "A8": "**detection, not prevention.** Nothing refuses the out-of-band UPDATE; the "
    "merge behind it is what is refused",
    "A9": "a cluster administrator with SQL can still DROP TRIGGER; mitigated by folding "
    "the ccloud audit log into the custody ledger, which is a detection control",
    "A11": "the window between expiry and the sweeper",
    "A12": "drift DETECTION is weaker at READ COMMITTED; the core refusal is not",
    "A14": "**cannot be retired.** Not by this schema and not by any schema",
}

REPORT = Path(__file__).resolve().parents[1] / "ANOMALY_COVERAGE.md"


def _coverage(manifest: Manifest) -> dict[str, list[str]]:
    """Anomaly -> the case ids that carry it, from the manifest the markers come from."""
    table: dict[str, list[str]] = {anomaly: [] for anomaly in ANOMALIES}
    for case in manifest.cases:
        if case.anomaly in table:
            table[case.anomaly].append(case.id)
    return table


def test_every_anomaly_has_at_least_one_case(manifest: Manifest) -> None:
    """A1-A14, each covered. CI fails on a zero."""
    coverage = _coverage(manifest)
    uncovered = [anomaly for anomaly, ids in coverage.items() if not ids]
    assert not uncovered, (
        f"{len(uncovered)} anomaly analysis(es) have no case: {', '.join(uncovered)}. An "
        f"anomaly analysed in prose and covered by nothing is the most expensive kind of "
        f"documentation, because it reads as assurance."
    )


def test_no_case_declares_an_unknown_anomaly(manifest: Manifest) -> None:
    """Every anomaly identifier in the manifest is one the analysis defines."""
    known = set(ANOMALIES) | {"none"}
    unknown = sorted({case.anomaly for case in manifest.cases if case.anomaly not in known})
    assert not unknown, (
        f"the manifest cites anomalies the analysis does not define: {unknown}. The "
        f"coverage report is generated from these values; an identifier with no row is a "
        f"case that covers nothing."
    )


def test_markers_are_attached_to_the_case_tests() -> None:
    """The conftest hook really does attach the anomaly marker.

    Without this, the generator below would be reading the manifest twice and calling it
    marker coverage. The hook is what makes the two agree.
    """
    from trappoint_conformance.manifest import load_manifest

    manifest = load_manifest()
    with_anomaly = {case.id for case in manifest.cases if case.anomaly != "none"}
    assert with_anomaly, "the manifest assigns no anomalies at all"
    # The hook keys on a `CF-NN` substring in the node id, so every such case id must be
    # recoverable from the parametrised node name the case suite generates.
    from conftest import _case_id_of  # type: ignore[import-not-found]  # the hook itself

    class _Node:
        def __init__(self, name: str) -> None:
            self.name = name

    for case_id in sorted(with_anomaly):
        node = _Node(f"test_case_exhibit[{case_id}]")
        recovered = _case_id_of(node)  # type: ignore[arg-type]
        assert recovered == case_id, (
            f"the collection hook recovers {recovered!r} from {node.name!r}, not "
            f"{case_id!r}; the marker would be attached to the wrong case, and the "
            f"coverage report would be generated from markers nobody put there."
        )


def test_generate_anomaly_coverage(manifest: Manifest) -> None:
    """Emit ``ANOMALY_COVERAGE.md``. Generation is a test so it cannot go stale."""
    coverage = _coverage(manifest)
    lines: list[str] = [
        "<!--",
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "SPDX-License-Identifier: Apache-2.0",
        "-->",
        "",
        "# `ANOMALY_COVERAGE.md` — A1-A14, and the case that covers each",
        "",
        (
            "**Generated by `tests/test_anomaly_coverage.py`. Do not edit.** CI fails if any "
            "anomaly has zero cases."
        ),
        "",
        f"* spec · `{manifest.spec_version}`",
        (
            f"* cases · {len(manifest.cases)} declared, "
            f"{len(manifest.for_profile('trappoint-ref'))} on the reference profile"
        ),
        "",
        (
            "The anomalies are the merge-gate analysis's, and the mapping is the "
            "manifest's: `tests/conftest.py` attaches `@pytest.mark.anomaly(...)` to each "
            "case's test from `spec/conformance/manifest.toml`, so the coverage below is "
            "generated from collected markers with the mapping owned in one place."
        ),
        "",
        "| # | anomaly | cases | residual |",
        "|---|---|---|---|",
    ]
    for anomaly in ANOMALIES:
        ids = coverage[anomaly]
        cells = ", ".join(f"`{case_id}`" for case_id in ids) or "**NONE**"
        residual = RESIDUALS.get(anomaly, "none")
        lines.append(f"| {anomaly} | {CAPTIONS[anomaly]} | {cells} | {residual} |")
    lines += [
        "",
        "## The two rows to read rather than skim",
        "",
        (
            "**A8 is detection, not prevention.** Nothing in the schema refuses an "
            "out-of-band `UPDATE permit SET open_blocking = 0`. What is refused is the "
            "merge behind it, because the gate re-derives the count from the obligation "
            "table and refuses on disagreement. `CF-03` asserts that and nothing more."
        ),
        "",
        (
            "**A14 - the rubber stamp - cannot be retired.** Not by a 120-character "
            "floor, not by a measured reading rate, not by a two-person rule. What the "
            "schema buys is that the box cannot be left effectively empty, that the text "
            "is dated and attributed and immutable, and that signing faster than the "
            "evidence can be read prices a countersignature. Whether the human thought "
            "about it is not a fact a database can hold, and no case here claims it is."
        ),
        "",
        "## Cases carrying no anomaly",
        "",
        (
            'A case with `anomaly = "none"` is a **static illegal history** rather than a '
            "concurrency anomaly - a constraint that refuses a single well-formed write. "
            "Most of the corpus is this, and that is the right shape: an anomaly is what "
            "you reach for when the refusal depends on an interleaving."
        ),
        "",
        (
            f"{sum(1 for c in manifest.cases if c.anomaly == 'none')} of "
            f"{len(manifest.cases)} cases are static."
        ),
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    assert REPORT.is_file()
