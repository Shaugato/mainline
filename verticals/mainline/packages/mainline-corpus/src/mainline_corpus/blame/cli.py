# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``blame`` subcommand.

``mainline_corpus.registry`` discovers ``mainline_corpus/*/cli.py`` and registers a subcommand
from it.  The registry is owned by ``corpus-contract``; this module publishes the surface it can
bind to under the same conventional names stage 1 uses, and it also stands alone::

    python -m mainline_corpus.blame --out verticals/mainline/fixtures/corpus/answer-key

A stage whose output can only be produced through another worker's not-yet-written entry point
cannot demonstrate its own reproducibility, which is this worker's completion test.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import build

__all__ = ["COMMAND", "HELP", "NAME", "add_arguments", "configure", "main", "run"]

COMMAND = "blame"
NAME = COMMAND
HELP = "Stage 1b: author causality, run the eight realism injectors, emit gold set GS0."


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        metavar="DIR",
        help="directory to write the answer key into (created if absent)",
    )
    parser.add_argument(
        "--skeleton",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "an existing stage-1 tree to CROSS-CHECK the rebuilt world against; the world is "
            "always rebuilt in memory, and a mismatch is a refusal naming the difference"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "repository root, used only to pick up PROJECTED-COLUMNS.yaml when "
            "corpus-freeze-load has shipped it; the built-in denylist applies either way"
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the per-file summary; the exit code still reports success",
    )
    return parser


#: Alias, for a registry that looks for ``configure``.
configure = add_arguments


def run(args: argparse.Namespace) -> int:
    result = build.generate(
        Path(args.out),
        skeleton_dir=getattr(args, "skeleton", None),
        repo_root=getattr(args, "repo_root", None),
    )
    if not getattr(args, "quiet", False):
        print(f"blame -> {result.out_dir}")
        for filename, digest in result.file_digests.items():
            # Row counts belong to tables; a JSON document has one body and no rows, and
            # printing `0` next to it reads as "this file is empty".
            rows = (
                f"{result.counts.get(filename.removesuffix('.jsonl'), 0):>6}"
                if filename.endswith(".jsonl")
                else "     -"
            )
            print(f"  {filename:<36} {rows}  {digest[:16]}")
        print(f"  {'index.json':<36} {'':>6}  {result.index_sha256[:16]}")
        print(f"  blame_edges/clause_versions = {result.blame_ratio}")
        print(f"  basis histogram: {result.basis_histogram}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpusgen blame", description=HELP)
    add_arguments(parser)
    return run(parser.parse_args(list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
