# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint render`` — the command line.

Exit codes, and they are load-bearing for CI (the same three ``trappoint migrate`` uses):

* ``0`` — the command did what it said.
* ``1`` — the renderer **refused**: an unbacked projected column, an unmeasured
  capability, a banned token, or a ``--check`` that found a diff.
* ``2`` — the invocation was wrong. Distinguished from ``1`` so a wrapper cannot mistake
  "you typed it wrong" for "the binding is unbacked" and retry forever.

``--check`` is the zero-diff assertion. It renders everything in memory and compares
bytes with what is committed; it writes nothing, ever, so it is safe to run on a
read-only checkout.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .binding import load_binding, repo_root
from .errors import RenderError, UsageError
from .render import RenderResult, check_units, render_binding, stem_collisions

__all__ = ["main"]

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

_TEMPLATES_RELPATH = Path("packages/trappoint-sql/templates")
_REF_BINDING = Path("packages/trappoint-sql/refvertical/vertical.toml")


def discover_bindings(root: Path) -> list[Path]:
    """Every ``vertical.toml`` in the tree, reference vertical first.

    Reference vertical first on purpose: it is the binding that must render before any
    real one is trusted, so when the output scrolls past, the substrate's own proof is
    at the top rather than buried under a vertical's forty files.
    """
    found: list[Path] = []
    reference = root / _REF_BINDING
    if reference.is_file():
        found.append(reference)
    found.extend(sorted(root.glob("verticals/*/vertical.toml")))
    return found


def _report(result: RenderResult, *, verbose: bool) -> None:
    binding = result.binding
    print(
        f"{binding.vertical.name} ({binding.vertical.schema}) · {len(result.units)} file(s) "
        f"-> {binding.vertical.output_dir}"
    )
    print(f"  {result.authority.summary}")
    for column in result.authority.pending:
        print(f"    pending  {column}  (declared; no template projects it yet)")
    for name in sorted(result.attestation.capabilities):
        answer = result.attestation.capabilities[name]
        print(f"  capability {name}: {answer.status} -> {answer.selects}  [{answer.gate}]")
    if verbose:
        for unit in result.units:
            print(f"    {unit.name}  <- {unit.template}")


def _report_collisions(result: RenderResult) -> None:
    collisions = stem_collisions(result.binding.output_dir)
    for stem, names in collisions:
        print(
            f"  COLLISION {stem}: {', '.join(names)} — two files claim one migration "
            "version. `trappoint migrate` refuses to discover this tree; one of them "
            "must be removed by whoever owns it.",
            file=sys.stderr,
        )


def _run_one(path: Path, templates: Path, *, check: bool, verbose: bool) -> int:
    binding = load_binding(path)
    result = render_binding(binding, templates)
    _report(result, verbose=verbose)

    if check:
        findings = check_units(result)
        _report_collisions(result)
        if findings:
            for finding in findings:
                print(f"  {finding.render()}", file=sys.stderr)
            print(
                f"  REFUSED: {len(findings)} file(s) differ from the templates that "
                "produced them. The Authority Source Contract is only binding while the "
                "committed SQL is what the declaration produced.",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        print("  check: zero diff")
        return EXIT_OK

    from .render import write_units  # local: keeps the write path out of --check's import

    changed = write_units(result)
    _report_collisions(result)
    if changed:
        print(f"  wrote {len(changed)} file(s)")
        for name in changed:
            print(f"    ~ {name}")
    else:
        print("  wrote 0 file(s) (already current)")
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trappoint render",
        description=(
            "Render the kernel's SQL templates for a vertical binding. Refuses to emit a "
            "gate template whose projected column has no declared authority source, and "
            "refuses to run at all without a ground-truth attestation for every "
            "capability the templates branch on."
        ),
    )
    parser.add_argument(
        "--binding",
        type=Path,
        action="append",
        dest="bindings",
        default=None,
        help="path to a vertical.toml; repeatable (default: every binding in the tree)",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        help="template directory (default: packages/trappoint-sql/templates)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; assert the committed SQL is byte-identical to the render",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="print the bindings that would be rendered, and exit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="name every rendered file and the template it came from",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``trappoint render`` and the ``trappoint-render`` script."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    try:
        root = repo_root()
        templates = args.templates or (root / _TEMPLATES_RELPATH)
        bindings = list(args.bindings) if args.bindings else discover_bindings(root)
        if not bindings:
            raise UsageError(
                f"no vertical.toml found under {root}. Pass --binding explicitly, or "
                "check that you are inside the workspace."
            )
        if args.list_only:
            for path in bindings:
                print(path)
            return EXIT_OK

        worst = EXIT_OK
        for path in bindings:
            worst = max(worst, _run_one(path, templates, check=args.check, verbose=args.verbose))
    except UsageError as exc:
        print(f"trappoint render: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except RenderError as exc:
        print(f"trappoint render: REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except OSError as exc:
        print(f"trappoint render: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    return worst


if __name__ == "__main__":  # pragma: no cover - exercised via `python -m trappoint_sql`
    raise SystemExit(main())
