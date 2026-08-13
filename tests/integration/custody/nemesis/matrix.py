# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Generate ``evidence/CUSTODY_ATTACK_MATRIX.md`` from a nemesis run, and enforce ATTACK-DEPTH.

*"Tamper-evident"* is an adjective, and a regulator cannot read an adjective. This module
crosses the run record — what actually happened, produced by
``tests/integration/custody/nemesis/`` against a real cluster — with
``spec/custody/attacks.yaml`` and ``spec/custody/checks.yaml``, and emits one table:
**attack x detecting check x detection latency**.

The generation direction matters and is not negotiable. The matrix is built from the RUN,
never from the registry. The registry records what we *expect*; printing an expectation as
a result is the precise dishonesty this artefact exists to remove, and the two are shown in
adjacent columns so a divergence is visible rather than resolved silently.

**The ATTACK-DEPTH rule**, enforced by :func:`evaluate`:

* an attack that ran and was detected by **zero** checks is a **failure** — a hole in the
  argument, not a row in a table;
* an attack detected by **exactly one** check is **flagged, not failed** — a single
  detector is a single point of failure in the argument;
* an attack that could not run is reported ``SKIP(reason)`` and appears in the matrix as
  such. **Never silently absent.**

Run it directly:

.. code-block:: console

   $ python tests/integration/custody/nemesis/matrix.py \\
         --run evidence/custody-nemesis-run.json \\
         --out evidence/CUSTODY_ATTACK_MATRIX.md --enforce
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
ATTACK_REGISTRY = REPO_ROOT / "spec" / "custody" / "attacks.yaml"
CHECK_REGISTRY = REPO_ROOT / "spec" / "custody" / "checks.yaml"


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        import yaml
    except ImportError:
        return None
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _check_names() -> dict[int, str]:
    registry = _load_yaml(CHECK_REGISTRY)
    if not registry:
        return {}
    return {int(check["id"]): str(check["name"]) for check in registry["checks"]}


def _expectations() -> dict[str, dict[str, Any]]:
    registry = _load_yaml(ATTACK_REGISTRY)
    if not registry:
        return {}
    return {str(attack["id"]): attack for attack in registry["attacks"]}


def evaluate(run: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return ``(failures, flags)`` under the ATTACK-DEPTH rule."""
    failures: list[str] = []
    flags: list[str] = []

    # A partial run is not an ATTACK-DEPTH proof, and it is easy to produce by accident —
    # `pytest -k a13` writes a one-row record and the matrix is rewritten from it. Missing
    # rows are a failure of the RUN, listed here so the artefact can never quietly describe
    # less than the registry claims.
    recorded = {str(outcome["id"]) for outcome in run["attacks"]}
    for attack_id in sorted(set(_expectations()) - recorded, key=lambda a: int(a.lstrip("A"))):
        failures.append(
            f"{attack_id} is in spec/custody/attacks.yaml and is ABSENT from this run. An "
            "attack missing from the matrix is indistinguishable from one nobody thought of"
        )

    for outcome in run["attacks"]:
        if not outcome["ran"]:
            continue
        detectors = outcome["detected_by"]
        if not detectors:
            failures.append(
                f"{outcome['id']} ({outcome['name']}) ran and was detected by ZERO checks"
            )
        elif len(detectors) == 1:
            flags.append(
                (
                    f"{outcome['id']} ({outcome['name']}) is detected by exactly one check "
                    f"(check {detectors[0]})"
                ),
            )
    return failures, flags


def _detector_cell(outcome: dict[str, Any], expectation: dict[str, Any]) -> str:
    if not outcome["ran"]:
        return f"— SKIP({outcome['skipped_reason']})"
    if not outcome["detected_by"]:
        return "**NONE — this is a hole in the argument**"
    primary = expectation.get("primary_detector")
    ordered = sorted(outcome["detected_by"], key=lambda c: (c != primary, c))
    return " · ".join(f"check {c}" + (" *(primary)*" if c == primary else "") for c in ordered)


def _latency_cell(outcome: dict[str, Any]) -> str:
    if not outcome["ran"]:
        return "not run"
    if outcome["detection_latency_ms"] is None:
        return "**never**"
    return f"{outcome['detection_latency_ms']} ms"


def _narrative(
    outcome: dict[str, Any], expectation: dict[str, Any], checks: dict[int, str]
) -> list[str]:
    """The prose section for one attack: what it did, what refused it, what caught it.

    Separated from :func:`render` because the table and the narrative answer different
    questions — the table is what a regulator reads in ten minutes, and this is what an
    engineer reads when the table surprises them.
    """
    lines = [f"### {outcome['id']} · `{outcome['name']}` ({outcome['tier']})", ""]
    summary = str(expectation.get("summary", "")).strip()
    if summary:
        lines += [f"> {summary}", ""]

    if not outcome["ran"]:
        lines += [
            (
                f"**SKIP({outcome['skipped_reason']})** — this attack was not executed by "
                "this run, and is recorded here rather than omitted."
            ),
            "",
        ]
        if outcome["note"]:
            lines += [outcome["note"], ""]
        return lines

    if outcome["note"]:
        lines += [f"{outcome['note']}.", ""]
    if outcome["database_refusals"]:
        lines += ["Database refusals observed on the way:", ""]
        lines += [f"- `{refusal}`" for refusal in outcome["database_refusals"]]
        lines.append("")
    if outcome["findings"]:
        lines += ["Findings (first six):", ""]
        lines += [f"- {finding}" for finding in outcome["findings"]]
        lines.append("")
    else:
        lines += ["**No finding was produced.**", ""]
    if outcome["skipped_checks"]:
        lines += [
            "Checks that reported SKIP during this run, printed as loudly as a failure:",
            "",
        ]
        skips = sorted(outcome["skipped_checks"].items(), key=lambda kv: int(kv[0]))
        for check_id, reason in skips:
            name = checks.get(int(check_id), "")
            label = f" `{name}`" if name else ""
            lines.append(f"- check {check_id}{label}: `SKIP({reason})`")
        lines.append("")
    return lines


def render(run: dict[str, Any]) -> str:
    checks = _check_names()
    expectations = _expectations()
    failures, flags = evaluate(run)
    environment = run.get("environment", {})
    ran = [o for o in run["attacks"] if o["ran"]]
    skipped = [o for o in run["attacks"] if not o["ran"]]
    verifiers = sorted({o["verifier"] for o in ran})

    lines: list[str] = [
        "<!--",
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "SPDX-License-Identifier: CC-BY-4.0",
        "",
        "GENERATED FILE — do not edit.",
        "Produced by tests/integration/custody/nemesis/matrix.py from a nemesis run against a",
        "real, disposable CockroachDB. Regenerate with:",
        "  python -m pytest tests/integration/custody/nemesis",
        "-->",
        "",
        "# ATTACK-DEPTH — the custody attack matrix",
        "",
        (
            "**Generated from a run, not written by hand.** Each row below is what happened when "
            "the attack was executed as real SQL against a disposable single-node CockroachDB "
            "seeded with the reference log, and a bundle exported from the mutated database was "
            "then put through the check set."
        ),
        "",
        f"- attacks executed: **{len(ran)}** of {len(run['attacks'])}",
        f"- reported `SKIP`: **{len(skipped)}**"
        + (f" — {', '.join(o['id'] for o in skipped)}" if skipped else ""),
        f"- detected by zero checks: **{len(failures)}**",
        f"- detected by exactly one check (flagged, not failed): **{len(flags)}**",
        f"- verifier that produced these rows: {', '.join(verifiers) if verifiers else 'none'}",
        "",
    ]

    if environment:
        lines += [
            "| Environment | |",
            "|---|---|",
            *[f"| {key} | {value} |" for key, value in sorted(environment.items())],
            "",
        ]

    lines += [
        "## The matrix",
        "",
        "| Attack | Tier | Detected by (observed) | Latency | Expected (registry) | Agrees |",
        "|---|---|---|---|---|---|",
    ]
    for outcome in run["attacks"]:
        expectation = expectations.get(outcome["id"], {})
        expected = expectation.get("detected_by") or []
        observed = set(outcome["detected_by"])
        if not outcome["ran"]:
            agrees = "n/a"
        elif not expected:
            agrees = "registry unavailable"
        elif observed & set(expected):
            agrees = "yes" if observed <= set(expected) else "yes (+extra)"
        else:
            agrees = "**NO**"
        row_template = (
            "| **{id}** `{name}` | {tier} | {detected} | {latency} | {expected} | {agrees} |"
        )
        lines.append(
            row_template.format(
                id=outcome["id"],
                name=outcome["name"],
                tier=outcome["tier"],
                detected=_detector_cell(outcome, expectation),
                latency=_latency_cell(outcome),
                expected=", ".join(f"check {c}" for c in expected) or "—",
                agrees=agrees,
            )
        )

    lines += [
        "",
        (
            "Latency is measured from the moment the attack commits to the moment the first "
            "finding exists — the question a reader is actually asking is *how long after the "
            "attack would somebody know?* For attacks whose primary defence is a database "
            "refusal the honest answer is *before it happened*, and those refusals are listed "
            "below rather than folded into a millisecond count."
        ),
        "",
    ]

    if failures:
        lines += [
            "## Holes in the argument — CI FAILS on this section being non-empty",
            "",
            *[f"- {failure}" for failure in failures],
            "",
        ]
    if flags:
        lines += [
            "## Single-detector attacks — flagged, not failed",
            "",
            (
                "A single detector is a single point of failure in the argument, not in the "
                "code. These are listed so that the next detector is a known piece of work "
                "rather than a discovery."
            ),
            "",
            *[f"- {flag}" for flag in flags],
            "",
        ]

    lines += ["## What each attack did, and what the database said", ""]
    for outcome in run["attacks"]:
        lines += _narrative(outcome, expectations.get(outcome["id"], {}), checks)

    lines += [
        "## What is not defeated",
        "",
        (
            "- **T3** — a managed-service operator with storage-path access is outside every "
            "mechanism in the database. Only Object Lock in a separate account and external "
            "witnesses touch that adversary, and neither is a complete answer."
        ),
        (
            "- **T4** — a cloud-org admin colluding with the signer can mint valid-looking "
            "history *going forward*. What they cannot do is change history a timestamp "
            "authority already timestamped or a witness already cosigned. The window of "
            "undetectable mutation is ~60 seconds and that is the honest number."
        ),
        (
            "- **Insincerity** — nothing here detects a rubber-stamped disposition. The chain "
            "makes rubber-stamping *measurable*; it does not make it impossible."
        ),
        "",
        (
            "Cross-referenced to [`spec/custody/attacks.yaml`](../spec/custody/attacks.yaml) and "
            "[`spec/custody/checks.yaml`](../spec/custody/checks.yaml)."
        ),
        "",
    ]
    return "\n".join(lines) + "\n"


#: What the environment table says when the run record carries no ``generated_at``. Such a
#: record predates :func:`nemesis_harness.OutcomeRecorder.write` stamping one, and the
#: honest thing to print is that nobody recorded the time — not the time of the render,
#: which is a fact about this process and not about the attacks.
_UNSTAMPED = "unrecorded — the run record carries no generated_at"


def write_matrix(run_path: Path, out_path: Path) -> Path:
    """Render ``run_path`` to ``out_path``. **The output is a pure function of the input.**

    Until 2026-08-13 this stamped ``generated_at = now()`` on the way through, which made
    the matrix a function of the run record *and the clock*. Two consequences, both bad and
    both measured on this tree:

    * re-rendering an OLD run record re-dated somebody else's attacks to today, so the
      artefact asserted that a run had just happened when none had — a hand-written value
      in all but authorship; and
    * ``custody-chain.yml`` regenerates the matrix immediately after the suite has already
      written it, so a re-render was never a no-op. Measured on this tree on 2026-08-13,
      before anything below changed: ``git diff evidence/CUSTODY_ATTACK_MATRIX.md`` read
      ``1 insertion(+), 1 deletion(-)`` and the one line was ``generated_at``. A diff a
      reviewer must learn to ignore is a diff that hides the next real one.

    The run record now carries its own ``generated_at``, stamped by the recorder at the
    moment the run finished. Rendering the same record twice is byte-identical, which is
    what lets *"generated from a run, not written by hand"* be checked by a machine —
    regenerate, then ``git diff --exit-code``.

    ``newline="\\n"`` is the other half of that sentence, and it is not cosmetic. This
    repository is developed on Windows and verified on ubuntu-24.04; a bare
    ``write_text()`` translates every ``\\n`` to ``\\r\\n`` under the developer and leaves
    it alone under CI, so the same run record rendered on the two machines produces two
    different files. Measured at ``2dc5c86``: the committed matrix carried **67 CRLF and 0
    bare LF**, having last been regenerated on Windows, while `custody-chain.yml` rewrites
    it on Linux every run. An evidence artefact whose bytes depend on who pressed the
    button cannot be diffed, cannot be hashed, and cannot support the claim above.
    """
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run.setdefault("environment", {}).setdefault("generated_at", _UNSTAMPED)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(run), encoding="utf-8", newline="\n")
    return out_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--run", type=Path, default=REPO_ROOT / "evidence" / "custody-nemesis-run.json"
    )
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "evidence" / "CUSTODY_ATTACK_MATRIX.md"
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="exit non-zero if any executed attack was detected by zero checks",
    )
    args = parser.parse_args(argv)

    if not args.run.is_file():
        print(
            (
                f"SKIP(no-run): {args.run} does not exist. The matrix is generated from a "
                "nemesis run against a real cluster; without one there is nothing to render "
                "and spec/custody/attacks.yaml is a list of expectations, not a matrix."
            ),
            file=sys.stderr,
        )
        return 0 if not args.enforce else 3

    write_matrix(args.run, args.out)
    run = json.loads(args.run.read_text(encoding="utf-8"))
    failures, flags = evaluate(run)
    for flag in flags:
        print(f"FLAG: {flag}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    print(f"wrote {args.out}")
    if failures and args.enforce:
        print(
            (
                "\nATTACK-DEPTH: an attack detected by zero checks is a hole in the argument, "
                "not a row in a table."
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
