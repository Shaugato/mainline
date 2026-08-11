# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``skeleton`` subcommand.

``mainline_corpus.registry`` discovers ``mainline_corpus/*/cli.py`` and registers a subcommand
from it.  The registry is owned by ``corpus-contract``; this module publishes the surface it can
bind to, under several conventional names so that whichever one the registry reaches for is
present:

* ``COMMAND`` / ``NAME``   — the subcommand word, ``"skeleton"``.
* ``HELP`` / ``__doc__``   — one-line help.
* ``add_arguments(parser)`` / ``configure(parser)`` — argparse wiring.
* ``run(args) -> int``     — the body; returns a process exit code.
* ``main(argv) -> int``    — a standalone entry point, so this stage is runnable and testable
  without the shared CLI existing at all.

That last one is deliberate.  A worker whose output can only be produced through another
worker's not-yet-written entry point has no way to prove its own output is byte-reproducible,
which is the completion test.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import build

__all__ = ["COMMAND", "HELP", "NAME", "add_arguments", "configure", "main", "run"]

COMMAND = "skeleton"
NAME = COMMAND
HELP = (
    "Stage 1: emit the deterministic world (sites, energy graph, taxonomy, people, events, MOCs)."
)


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        metavar="DIR",
        help="directory to write the skeleton JSONL tree into (created if absent)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "repository root, used only to pick up PROJECTED-COLUMNS.yaml when corpus-freeze-load "
            "has shipped it; the built-in denylist applies either way"
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
    result = build.generate(Path(args.out), repo_root=getattr(args, "repo_root", None))
    if not getattr(args, "quiet", False):
        print(f"skeleton -> {result.out_dir}")
        for filename, digest in result.file_digests.items():
            rows = result.counts.get(filename.removesuffix(".jsonl"), 0)
            print(f"  {filename:<32} {rows:>6}  {digest[:16]}")
        print(f"  {'index.json':<32} {'':>6}  {result.index_sha256[:16]}")
        print(f"  severity_gate histogram: {result.severity_histogram}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpusgen skeleton", description=HELP)
    add_arguments(parser)
    return run(parser.parse_args(list(sys.argv[1:] if argv is None else argv)))
