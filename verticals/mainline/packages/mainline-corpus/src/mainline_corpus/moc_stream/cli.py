# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``moc-stream`` subcommand.

``mainline_corpus.registry`` discovers ``mainline_corpus/*/cli.py`` and registers a subcommand
from it.  The registry is owned by ``corpus-contract``; this module publishes the surface it can
bind to under the same conventional names stages 1 and 1b use, and it also stands alone::

    python -m mainline_corpus.moc_stream --out verticals/mainline/fixtures/corpus/moc-stream

A stage whose output can only be produced through another worker's not-yet-written entry point
cannot demonstrate its own reproducibility, which is this stage's completion test.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import build

__all__ = [
    "COMMAND",
    "HELP",
    "NAME",
    "add_arguments",
    "configure",
    "default_repo_root",
    "main",
    "run",
]

COMMAND = "moc-stream"
NAME = COMMAND
HELP = "Stage 1c: declare each change request's clause scope and plan its lifecycle acts."

#: What makes a directory the repository root, for this stage's purposes: the migration tree that
#: holds the authority for the change-request state machine.
_ROOT_MARKER = Path("verticals") / "mainline" / "db" / "migrations"


def default_repo_root() -> Path | None:
    """Walk up from this file looking for the migration tree.

    ``None`` when it is not found, which makes the state-machine check report ``SKIP`` with a
    reason rather than quietly trusting ``params.TERMINAL_TRANSITIONS`` — the whole value of that
    check is that ``params`` might be wrong.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / _ROOT_MARKER).is_dir():
            return candidate
    return None


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        metavar="DIR",
        help="directory to write the MOC-stream tree into (created if absent)",
    )
    parser.add_argument(
        "--answer-key",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "an existing stage-1b tree to CROSS-CHECK the rebuilt clause universe against; the "
            "world is always rebuilt in memory, and a mismatch is a refusal naming the difference"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "repository root. Used to read the seeded change_request edges out of "
            "0017b_subject_transition_seed.sql, and to pick up PROJECTED-COLUMNS.yaml when "
            "corpus-freeze-load has shipped it. Auto-detected when omitted"
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
    repo_root = getattr(args, "repo_root", None) or default_repo_root()
    result = build.generate(
        Path(args.out),
        answer_key_dir=getattr(args, "answer_key", None),
        repo_root=repo_root,
    )
    if not getattr(args, "quiet", False):
        print(f"moc-stream -> {result.out_dir}")
        for filename, digest in result.file_digests.items():
            rows = (
                f"{result.counts.get(filename.removesuffix('.jsonl'), 0):>6}"
                if filename.endswith(".jsonl")
                else "     -"
            )
            print(f"  {filename:<30} {rows}  {digest[:16]}")
        print(f"  {'index.json':<30} {'':>6}  {result.index_sha256[:16]}")
        print(f"  checks: {result.verify_summary}")
        print(f"  change requests declaring no scope: {result.unscoped}")
        if repo_root is None:
            print(
                "  NOTE: no repository root was found, so the planned edges were NOT checked "
                "against mainline.subject_transition. Pass --repo-root."
            )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpusgen moc-stream", description=HELP)
    add_arguments(parser)
    return run(parser.parse_args(list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
