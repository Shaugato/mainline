#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim.
# I: CI-CLUSTER-1 — the cluster lane's failures are CLASSIFIED, never SUPPRESSED. The
#    job's exit status is pytest's exit status; this program may only ADD a failure.
"""Classify a cluster-backed demo-api run: `known`, `unstable`, or **NEW**.

WHY THIS PROGRAM CANNOT MAKE A RED RUN GREEN, WHICH IS THE ONLY PROPERTY THAT MATTERS.

`qa/cluster-known-red.json` is an inventory of failures this repository already knows
about. An inventory of known failures is one edit away from being a suppression list —
add a node id, and the thing it names stops being reported. That edit must not be
available, so the refusal is structural rather than a matter of reviewer attention:

    --pytest-rc N is not advisory. When pytest exited non-zero, THIS PROGRAM EXITS N,
    whatever the inventory says about the node ids involved.

So adding a node id to the inventory cannot change the verdict of a run in which
anything failed. It changes only the sentence printed beside that failure. The two
verdicts this program owns are both ones that fire when **pytest was GREEN**:

  1. THE FLOOR (anti-vacuity). `release-proof.yml:219-320` records this exact defect
     live in this repository — *"pytest exits 0 when every test skips"* — so a lane that
     obtains no cluster runs 186 skips and reports success. `floor.min_executed` and
     `floor.max_skipped` in the inventory refuse that run by name.
  2. THE CEILING. A node id on the `groups` inventory that PASSED is a defect somebody
     fixed, and the inventory is now larger than the truth. That is a hard failure,
     because the list is a ceiling that must reach empty, and a ceiling nobody is forced
     to lower is a ceiling that never falls.

`unstable` is the one category exempt from the ceiling, and it exists because the
failure set for this suite is measurably not deterministic — see the inventory's own
`unstable` entries, each of which carries the runs it was observed over and the number
of those runs in which it failed. An entry with no such measurement is refused. Because
of `--pytest-rc` an `unstable` entry still cannot hide anything: when it fails, pytest
fails, and this program exits with pytest's status.

WHAT A NODE ID IS HERE. pytest's JUnit XML carries `classname` + `name`, not a node id,
and its `classname` is the module's dotted basename (`tests.test_reads`) because the
suite is imported in `prepend` mode. The node ids in the inventory are the real,
copy-pasteable ones, so the mapping is resolved against the FILESYSTEM: the first
component of `classname` that names a real module under `--suite-root` is the module,
and anything after it is a class path. A `classname` that resolves to no file on disk is
a hard failure rather than a silently-unmatched id — an id that cannot match the
inventory would be reported NEW forever, or worse, never reported at all.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import xml.etree.ElementTree as ET
from typing import Any

SCHEMA: str = "mainline.qa.cluster-known-red/1"
DEFAULT_KNOWN = pathlib.Path("qa/cluster-known-red.json")
DEFAULT_SUITE_ROOT = pathlib.Path("verticals/mainline/apps/demo-api/tests")

#: How many failing node ids get their assertion text rendered into `--summary`. EVERY
#: failing id is listed whatever this is; this caps only how many carry their text.
#: GitHub truncates `$GITHUB_STEP_SUMMARY` at 1 MiB SILENTLY, and a summary cut off by
#: GitHub is a summary whose end nobody can tell was removed. An explicit cap with a
#: printed marker is the alternative to that. This number decides nothing: the verdict is
#: `--pytest-rc` and the gates in `report()`, neither of which reads it.
SUMMARY_ASSERTIONS_RENDERED = 20

#: Per-assertion line cap inside `--summary`, for the same reason.
SUMMARY_ASSERTION_LINES = 24


class Refusal(Exception):
    """A condition under which this program refuses to report at all."""


# ── the inventory ──────────────────────────────────────────────────────────────────


def load_inventory(path: pathlib.Path) -> dict[str, Any]:
    """Read and validate the known-red inventory.

    Validation is not ceremony. Every field checked here is one whose absence would let
    the inventory grow an entry that means nothing: a group with no `cause` is a node id
    somebody added without saying why, which is the shape a suppression list takes.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Refusal(f"no known-red inventory at {path}") from exc
    except json.JSONDecodeError as exc:
        raise Refusal(f"{path} is not valid JSON: {exc}") from exc

    if data.get("schema") != SCHEMA:
        raise Refusal(f"{path} declares schema {data.get('schema')!r}, expected {SCHEMA!r}")

    floor = data.get("floor")
    if not isinstance(floor, dict):
        raise Refusal(f"{path} carries no `floor` object; the anti-vacuity gate has no numbers")
    for key in ("min_executed", "max_skipped"):
        if not isinstance(floor.get(key), int):
            raise Refusal(f"{path}: floor.{key} must be an integer")

    known = _read_groups(data, path)
    unstable = _read_unstable(data, known, path)
    return {"raw": data, "floor": floor, "known": known, "unstable": unstable}


def _read_groups(data: dict[str, Any], path: pathlib.Path) -> dict[str, str]:
    """Map every inventoried node id to the slug of the group that explains it."""
    known: dict[str, str] = {}
    for group in data.get("groups", []):
        slug = group.get("slug", "")
        if not slug:
            raise Refusal(f"{path}: a group carries no `slug`")
        if not (group.get("cause") or "").strip():
            raise Refusal(
                f"{path}: group {slug!r} carries no `cause`. A node id recorded without the "
                "reason it fails is indistinguishable from a node id somebody wanted to stop "
                "hearing about."
            )
        for nodeid in group.get("nodeids", []):
            if nodeid in known:
                raise Refusal(f"{path}: {nodeid} appears in two groups")
            known[nodeid] = slug
    return known


def _read_unstable(
    data: dict[str, Any], known: dict[str, str], path: pathlib.Path
) -> dict[str, dict[str, Any]]:
    """Validate the one category the ceiling does not police.

    Every rule here exists to stop `unstable` becoming the place a failing test is filed.
    An entry must name a measurement, and a node id that failed EVERY run it was seen in
    is not unstable — it is failing, and it belongs in a group with a cause and an owner.
    """
    unstable: dict[str, dict[str, Any]] = {}
    for entry in data.get("unstable", []):
        nodeid = entry.get("nodeid", "")
        if not nodeid:
            raise Refusal(f"{path}: an `unstable` entry carries no `nodeid`")
        if nodeid in known:
            raise Refusal(f"{path}: {nodeid} is both a known group member and `unstable`")
        observed, failed = entry.get("runs_observed"), entry.get("runs_failed")
        if not isinstance(observed, int) or not isinstance(failed, int) or observed <= 0:
            raise Refusal(
                f"{path}: unstable entry {nodeid} must carry measured `runs_observed` > 0 and "
                "`runs_failed`. `unstable` is the one category the ceiling does not police, so "
                "an entry without a measurement behind it is exactly the loophole this schema "
                "exists to close."
            )
        if failed >= observed:
            raise Refusal(
                f"{path}: unstable entry {nodeid} failed {failed} of {observed} run(s) - it is "
                "not unstable, it is failing. Move it into a `groups` entry with a cause."
            )
        if not (entry.get("reason") or "").strip():
            raise Refusal(f"{path}: unstable entry {nodeid} carries no `reason`")
        unstable[nodeid] = entry
    return unstable


# ── the run ────────────────────────────────────────────────────────────────────────


def resolve_nodeid(classname: str, name: str, suite_root: pathlib.Path) -> str:
    """Rebuild a real pytest node id from JUnit's `classname` + `name`."""
    parts = classname.split(".")
    for index, part in enumerate(parts):
        if (suite_root / f"{part}.py").is_file():
            trailing = [*parts[index + 1 :], name]
            return f"{suite_root.as_posix()}/{part}.py::" + "::".join(trailing)
    raise Refusal(
        f"cannot resolve JUnit classname {classname!r} to a module under {suite_root}. "
        "An id that resolves to nothing can never match the inventory, so it would be "
        "reported NEW on every run or, if the matching were loosened, never reported."
    )


def assertion_of(element: Any) -> list[str]:
    """Pull the assertion out of one `<failure>`/`<error>` body, for `--summary` only.

    THIS IS DIAGNOSIS AND IT TOUCHES NO VERDICT. Nothing below `report()` reads the result;
    it is rendered into the Markdown summary and nowhere else. If this function returned an
    empty list on every input, every gate in this program would still fire identically.

    WHY IT IS HERE RATHER THAN IMPORTED FROM `scripts/ci/lane_log_digest.py`, WHICH DOES
    THE SAME JOB. This program is the one that must be able to report. An `import` of a
    sibling module is a new way for it to fail before it reaches `load_inventory`, and the
    failure mode of a *verdict* program is not the same cost as the failure mode of a
    diagnosis program. Twenty lines duplicated is the cheaper of the two.

    THE ASSERTION IS AT THE END OF THE BODY, NOT THE START. pytest writes the whole
    longrepr: fixture reprs, then the test source *including its docstring*, then the `>`
    line that failed, then the `E` block. Taking the head would print a docstring. The
    calibration case — `test_reads.py::test_the_disposition_carries_the_lattice_and_the_
    projected_requirements` — is 53 lines of which the first ~40 are its docstring.
    """
    lines = [line.rstrip() for line in (element.text or "").replace("\r\n", "\n").split("\n")]
    exception_at = [index for index, line in enumerate(lines) if line.lstrip().startswith("E ")]
    marked_at = [index for index, line in enumerate(lines) if line.lstrip().startswith(">")]
    non_empty = [index for index, line in enumerate(lines) if line.strip()]

    if exception_at:
        start = marked_at[-1] if marked_at and marked_at[-1] < exception_at[0] else exception_at[0]
        picked = [line for line in lines[start : exception_at[-1] + 1] if line.strip()]
        location = lines[non_empty[-1]] if non_empty else ""
        if location and location not in picked:
            picked.append(location)
    else:
        # No `E` block: a fixture raised during setup, or the body is not a pytest
        # longrepr at all. The TAIL is the diagnosis in that shape.
        picked = [line for line in lines if line.strip()][-SUMMARY_ASSERTION_LINES:]

    if not picked:
        # `message` is pytest's own one-line summary, and it is ellipsised - it is the
        # fallback, never the first choice. A one-element list is always truthy, so the
        # empty case is tested on the STRING; ruff's SIM222 caught that written the other
        # way round, where the placeholder could never have been reached.
        message = " ".join((element.get("message") or "").split())
        picked = [message] if message else ["(the element carried no message and no text)"]
    return picked


def read_run(junit: pathlib.Path, suite_root: pathlib.Path) -> dict[str, Any]:
    """Parse the JUnit XML into totals plus the outcome of every test case."""
    try:
        root = ET.parse(junit).getroot()  # noqa: S314 - pytest's own output, not hostile input
    except FileNotFoundError as exc:
        raise Refusal(
            f"pytest wrote no JUnit report at {junit}. The run did not reach the point of "
            "writing one, so there is nothing to classify and nothing may be reported."
        ) from exc
    except ET.ParseError as exc:
        raise Refusal(f"{junit} is not parseable XML: {exc}") from exc

    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise Refusal(f"{junit} carries no <testsuite>; nothing was collected")

    bad: dict[str, str] = {}
    passed: set[str] = set()
    # `assertions` is DIAGNOSIS ONLY and is read by `--summary` and by nothing else. It is
    # a separate mapping rather than a richer `bad` on purpose: `bad` is what guard 0, the
    # classification and the ceiling are computed from, and none of them may acquire a new
    # shape because the summary wanted a sentence to print.
    assertions: dict[str, list[str]] = {}
    for case in suite.iter("testcase"):
        nodeid = resolve_nodeid(case.get("classname", ""), case.get("name", ""), suite_root)
        for kind in ("failure", "error"):
            found = case.find(kind)
            if found is not None:
                bad[nodeid] = kind
                assertions[nodeid] = assertion_of(found)
                break
        else:
            if case.find("skipped") is None:
                passed.add(nodeid)

    tests = int(suite.get("tests", "0"))
    skipped = int(suite.get("skipped", "0"))
    return {
        "tests": tests,
        "skipped": skipped,
        "executed": tests - skipped,
        "failures": int(suite.get("failures", "0")),
        "errors": int(suite.get("errors", "0")),
        "bad": bad,
        "passed": passed,
        "assertions": assertions,
    }


# ── the report ─────────────────────────────────────────────────────────────────────


def report(
    run: dict[str, Any], inv: dict[str, Any], out: list[str], pytest_rc: int = 0
) -> list[str]:
    """Print the classification; return the list of verdicts that failed."""
    floor, known, unstable = inv["floor"], inv["known"], inv["unstable"]
    verdicts: list[str] = []

    out.append(
        f"cluster lane: {run['tests']} collected, {run['executed']} executed, "
        f"{run['skipped']} skipped, {run['failures']} failed, {run['errors']} errored"
    )
    out.append("")

    # 0. THE HARNESS STILL HAS PYTEST'S EXIT STATUS. Everything below rests on
    #    `--pytest-rc` being the real one; a report told the run passed while its own XML
    #    records failures is a report whose caller dropped the status, and that is the one
    #    rewiring that would let a fully-inventoried red run present as green.
    #
    #    A JUNIT DOCUMENT GIVES TWO ACCOUNTS OF A RUN, AND THIS LINE READS BOTH. The
    #    `<testsuite>` element carries summary attributes; the `<testcase>` children carry
    #    the outcomes, and `run["bad"]` is the parsed body — the account the classification
    #    below is itself computed from. pytest derives the first from the second, so on any
    #    honest run they agree and the third clause is dead weight. But the subject of this
    #    guard is a caller that has ALREADY been rewired, and until 2026-08-14 the guard
    #    read the summary alone: a document whose summary said `failures="0"` while its body
    #    carried `<failure>` children passed the floor, the classification and the ceiling
    #    and exited 0, provided the node ids were inventoried — the exact outcome this
    #    guard exists to refuse, arriving through the half of the document it was not
    #    reading. `tests/ci/test_cluster_lane_report.py` proved it and now holds it shut;
    #    the fix ADDED a clause and relaxed nothing, so it cannot move the verdict of a run
    #    pytest actually produced.
    if pytest_rc == 0 and (run["failures"] or run["errors"] or run["bad"]):
        verdicts.append(
            "::error title=the lane lost pytest's exit status::the JUnit report records "
            f"{run['failures']} failure(s) and {run['errors']} error(s) in its summary and "
            f"{len(run['bad'])} failing test case(s) in its body, but this program was told "
            "pytest exited 0. The caller is not passing pytest's real status to --pytest-rc, "
            "so the inventory would be deciding the verdict on its own."
        )

    # 1. THE FLOOR. A lane that runs nothing and exits 0 is worse than no lane.
    if run["executed"] < floor["min_executed"]:
        verdicts.append(
            f"::error title=the cluster lane proved nothing::only {run['executed']} of "
            f"{run['tests']} demo-api tests EXECUTED; the floor is {floor['min_executed']}. "
            "pytest exits 0 when every test skips, so without this line the lane would report "
            "the product's headline path as covered on a run that never reached a database."
        )
    if run["skipped"] > floor["max_skipped"]:
        verdicts.append(
            f"::error title=the cluster lane skipped::{run['skipped']} test(s) skipped, ceiling "
            f"{floor['max_skipped']}. A skip here means the suite could not reach the cluster "
            "this job started, and a skip is indistinguishable from a green tick on a dashboard."
        )

    # 2. CLASSIFY every failure. This half never changes the verdict of a red run — see
    #    the module docstring — it changes what the log says about it.
    new: list[str] = []
    for nodeid in sorted(run["bad"]):
        kind = run["bad"][nodeid]
        if nodeid in known:
            out.append(f"  known    [{known[nodeid]}] {kind}: {nodeid}")
        elif nodeid in unstable:
            seen = unstable[nodeid]
            out.append(
                f"  unstable ({seen['runs_failed']}/{seen['runs_observed']} runs) {kind}: {nodeid}"
            )
        else:
            new.append(nodeid)
            out.append(f"  NEW      {kind}: {nodeid}")
    if new:
        verdicts.append(
            f"::error title={len(new)} NEW cluster failure(s)::"
            + "; ".join(new[:5])
            + ("; …" if len(new) > 5 else "")
            + ". These are not on qa/cluster-known-red.json. Either this run found a defect the "
            "inventory has never seen, or a known one changed its node id."
        )

    # 3. THE CEILING. The inventory must reach empty, so a fix must be recorded as one.
    fixed = sorted(nodeid for nodeid in known if nodeid in run["passed"])
    if fixed:
        out.append("")
        for nodeid in fixed:
            out.append(f"  FIXED    [{known[nodeid]}] {nodeid}")
        verdicts.append(
            f"::error title={len(fixed)} known-red test(s) now PASS::"
            + "; ".join(fixed[:5])
            + ("; …" if len(fixed) > 5 else "")
            + ". Remove them from qa/cluster-known-red.json in the commit that fixed them. This "
            "list is a ceiling that must reach empty, and a ceiling nobody is made to lower is a "
            "ceiling that never falls."
        )

    # 4. An `unstable` entry that passed is NOT a failure — that is the whole point of the
    #    category — but it is not silent either. Without this notice, the day somebody
    #    fixes the contamination is a day nothing anywhere says the exemptions can go, and
    #    an exemption nobody is reminded of is an exemption that becomes permanent.
    quiet = sorted(nodeid for nodeid in unstable if nodeid in run["passed"])
    if quiet:
        out.append("")
        for nodeid in quiet:
            out.append(f"  (unstable, passed this run) {nodeid}")
        out.append(
            f"::notice::{len(quiet)} declared-unstable test(s) passed this run. If the "
            "cross-test contamination behind them has been fixed, delete them from "
            "qa/cluster-known-red.json - an exemption nobody is reminded of becomes permanent."
        )

    still = sorted(nodeid for nodeid in known if nodeid in run["bad"])
    out.append("")
    out.append(
        f"inventory: {len(known)} known, {len(still)} still failing, {len(fixed)} now passing, "
        f"{len(unstable)} declared unstable, {len(new)} NEW"
    )
    return verdicts


def _fence(lines: list[str]) -> str:
    """A code fence longer than any backtick run inside the text it will wrap.

    An assertion diff can contain a triple backtick — this repository's messages quote
    code — and a fence the text can close is a summary that renders as garbage from that
    point down. That would silently swallow the failures listed after it.
    """
    longest = 0
    for line in lines:
        run = 0
        for char in line:
            run = run + 1 if char == "`" else 0
            longest = max(longest, run)
    return "`" * max(3, longest + 1)


def summary_failures(run: dict[str, Any], inv: dict[str, Any]) -> list[str]:
    """The Markdown block that names WHAT failed, not merely HOW MANY did.

    WHY THIS EXISTS. `$GITHUB_STEP_SUMMARY` renders at the TOP of the run page, which is
    where a reader lands. Until 2026-08-14 the summary carried the classification — the
    counts table above — but not the sentence that failed, so a reader who opened a red
    cluster run still had to scroll ~180 lines up from the bottom of a 1,023-line log,
    past 60 lines of CockroachDB session log, to find one assertion. Measured over run
    `31735341117`; `docs/ci/cluster-lane-diagnosis.md` records the measurement and why the
    container log is NOT the thing to delete.

    WHAT IT DOES NOT DO. It adds no verdict, reads no floor and no ceiling, and cannot
    change an exit status: `main()` calls it after every gate has already run, and its
    return value is written to a file. Deleting this function would leave every refusal in
    this program exactly as it is — which is the property that made it safe to add to the
    program that owns the verdict.
    """
    bad, known, unstable = run["bad"], inv["known"], inv["unstable"]
    if not bad:
        return ["### failing tests", "", "None. Every executed test passed.", ""]

    ordered = sorted(bad)
    rows = [
        "### failing tests",
        "",
        (
            f"{len(ordered)} failing test(s), each with the assertion that failed. The "
            "verdict is above and in the job's exit status; this section is what failed, "
            "not whether the lane passed."
        ),
        "",
    ]

    for index, nodeid in enumerate(ordered, start=1):
        slug = known.get(nodeid)
        seen = unstable.get(nodeid)
        if slug is not None:
            label = f"known [`{slug}`]"
        elif seen is not None:
            label = f"unstable ({seen['runs_failed']}/{seen['runs_observed']} runs)"
        else:
            label = "**NEW**"
        rows.append(f"{index}. {label} — `{run['bad'][nodeid]}` — `{nodeid}`")

        if index > SUMMARY_ASSERTIONS_RENDERED:
            # The id is still listed above. Only its text is withheld, and the marker
            # below says so once, after the loop.
            continue

        text = run["assertions"].get(nodeid, [])
        kept = text[:SUMMARY_ASSERTION_LINES]
        if kept:
            fence = _fence(kept)
            rows.extend(["", f"{fence}text", *kept])
            if len(kept) < len(text):
                rows.append(
                    f"[{len(kept)} of {len(text)} line(s) shown; the rest is in the "
                    "JUnit XML this job uploaded]"
                )
            rows.extend([fence, ""])

    if len(ordered) > SUMMARY_ASSERTIONS_RENDERED:
        rows.extend(
            [
                "",
                (
                    f"Every one of the {len(ordered)} failing ids is listed above; the "
                    f"assertion text is rendered for the first {SUMMARY_ASSERTIONS_RENDERED}. "
                    "GitHub truncates this summary at 1 MiB without saying so, and a cap "
                    "nobody can see is worse than one that is written down. The full text "
                    "for every id is in the JUnit XML."
                ),
                "",
            ]
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify a cluster-backed demo-api run against the known-red inventory.",
        epilog=(
            "This program may only ADD a failure. When --pytest-rc is non-zero it exits with "
            "that status regardless of the inventory, so no edit to the inventory can turn a "
            "red run green."
        ),
    )
    parser.add_argument("--junit", type=pathlib.Path, required=True, help="pytest's JUnit XML")
    parser.add_argument(
        "--known",
        type=pathlib.Path,
        default=DEFAULT_KNOWN,
        help=(
            "the known-red inventory (default: %(default)s). Overridable so the falsifiability "
            "lane can prove that a doctored copy still cannot suppress a failure."
        ),
    )
    parser.add_argument("--suite-root", type=pathlib.Path, default=DEFAULT_SUITE_ROOT)
    parser.add_argument(
        "--pytest-rc",
        type=int,
        default=0,
        help=(
            "the exit status pytest itself returned. NON-ZERO IS FINAL: this program exits with "
            "it, whatever the classification says."
        ),
    )
    parser.add_argument(
        "--summary",
        type=pathlib.Path,
        default=None,
        help="append a Markdown table here (GitHub's $GITHUB_STEP_SUMMARY)",
    )
    args = parser.parse_args(argv)

    out: list[str] = []
    try:
        inv = load_inventory(args.known)
        run = read_run(args.junit, args.suite_root)
        verdicts = report(run, inv, out, args.pytest_rc)
    except Refusal as exc:
        print("\n".join(out))
        print(f"::error title=the cluster lane cannot be reported::{exc}")
        # A report that cannot be produced is never a pass, and never quieter than pytest.
        return args.pytest_rc or 1

    print("\n".join(out))
    for verdict in verdicts:
        print(verdict)

    if args.summary is not None:
        floor = inv["floor"]
        still = sum(1 for n in inv["known"] if n in run["bad"])
        fresh = sum(1 for n in run["bad"] if n not in inv["known"] and n not in inv["unstable"])
        rows = [
            "## cluster lane",
            "",
            "| measure | value |",
            "|---|---|",
            f"| collected | {run['tests']} |",
            f"| executed | {run['executed']} (floor {floor['min_executed']}) |",
            f"| skipped | {run['skipped']} (ceiling {floor['max_skipped']}) |",
            f"| known-red still failing | {still} of {len(inv['known'])} |",
            f"| NEW | {fresh} |",
            f"| pytest exit status | {args.pytest_rc} |",
            "",
        ]
        rows.extend(summary_failures(run, inv))
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")

    if args.pytest_rc:
        print(
            f"::notice::pytest exited {args.pytest_rc}; this lane exits with pytest's status. "
            "The classification above is the message, not the verdict."
        )
        return args.pytest_rc
    return 1 if verdicts else 0


if __name__ == "__main__":
    sys.exit(main())
