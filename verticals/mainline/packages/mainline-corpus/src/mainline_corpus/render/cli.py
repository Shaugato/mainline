# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``render`` subcommand.

``mainline_corpus.registry`` discovers ``mainline_corpus/*/cli.py`` and registers a subcommand
from it.  The registry is owned by ``corpus-contract``; this module publishes the surface it
binds to under the same conventional names stages 1 and 1b use, and it also stands alone::

    python -m mainline_corpus.render --out build/render
    python -m mainline_corpus.render --verify

Standing alone is deliberate.  A stage whose output can only be produced through another
worker's not-yet-written entry point cannot demonstrate its own reproducibility, which is this
worker's completion test.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .params import DEFAULT_POLICY, NODE_KINDS, POLICIES

__all__ = ["COMMAND", "HELP", "NAME", "add_arguments", "configure", "main", "run"]

COMMAND = "render"
NAME = COMMAND
HELP = "Stage 2: render every node through the three tiers into the committed cache."


def _default_repo_root() -> Path:
    """Walk up from this file to the repository root.

    ``src/mainline_corpus/render/cli.py`` → six parents.  Checked rather than assumed: a wrong
    root would silently render against an empty answer key.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "verticals" / "mainline" / "fixtures" / "corpus").is_dir():
            return candidate
    return Path.cwd()


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "directory for the stage-2 tree (the four filled columns and their spans); "
            "required unless --verify"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="repository root; defaults to the checkout this package is inside",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="the committed content-addressed cache; defaults to fixtures/corpus/cache",
    )
    parser.add_argument(
        "--policy",
        choices=POLICIES,
        default=DEFAULT_POLICY,
        help=(
            "tier assignment. `offline` (default): camera-facing -> authored, bulk -> template. "
            "`model-rendered`: bulk -> bedrock, which needs a committed cache or --allow-live"
        ),
    )
    parser.add_argument(
        "--camera",
        choices=("require", "defer"),
        default="require",
        help=(
            "what to do with a camera-facing node that has no authored fixture: `require` "
            "(default) refuses and names corpus-spine-authored; `defer` records it in "
            "INDEX.json and renders the rest. Deferring never substitutes generated prose"
        ),
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help=(
            "disarm the offline guard and permit Bedrock calls. Offline is the default because "
            "AWS credentials are not valid on this machine and PL-3 forbids an unproven "
            "capability on a dated path"
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=NODE_KINDS,
        default=None,
        metavar="KIND",
        help="render one node kind only (repeatable); disables cache pruning",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="keep cache entries no live node derives (they will be counted by the census)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="recompute every committed cache key and digest instead of rendering",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="--verify only: skip re-rendering; structural and integrity checks still run",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the summary; the exit code still reports success",
    )
    return parser


#: Alias, for a registry that looks for ``configure``.
configure = add_arguments


def _run_verify(args: argparse.Namespace) -> int:
    # Imported from the submodule by path, not as `from . import verify`: the package's
    # `__init__` re-exports the *function* under that name, so the attribute lookup would find
    # the function and not the module.
    from .verify import verify as run_verify

    report = run_verify(
        repo_root=args.repo_root or _default_repo_root(),
        cache_dir=args.cache_dir,
        fast=bool(args.fast),
    )
    if not args.quiet:
        for line in report.summary():
            print(line)
        for failure in report.failures:
            print(f"FAIL  {failure}")
    if report.failures:
        print(f"render --verify FAILED with {len(report.failures)} problem(s)", file=sys.stderr)
        return 1
    return 0


def run(args: argparse.Namespace) -> int:
    if args.verify:
        return _run_verify(args)

    if args.out is None:
        print("render: --out DIR is required unless --verify is given", file=sys.stderr)
        return 2

    from . import build
    from .cache import CacheCorruption
    from .corpusio import CorpusUnavailable
    from .netguard import OfflineViolation
    from .protocol import RenderRefusal
    from .spans import BindingFailure
    from .validate import SchemaViolation

    # A refusal is this product's deliverable, so on the command line it reads as a message and
    # an exit code — not as a traceback that buries the sentence a person needs.
    try:
        result = build.generate(
            Path(args.out),
            repo_root=args.repo_root or _default_repo_root(),
            cache_dir=args.cache_dir,
            policy=args.policy,
            camera=args.camera,
            allow_live=bool(args.allow_live),
            only=tuple(args.only or ()),
            prune=not args.no_prune,
        )
    except (
        BindingFailure,
        CacheCorruption,
        CorpusUnavailable,
        OfflineViolation,
        RenderRefusal,
        SchemaViolation,
    ) as exc:
        print(f"render: REFUSED\n{exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"render -> {result.out_dir}")
        print(f"  cache          {result.cache_dir}")
        print(
            f"  nodes          {result.nodes}  (cache hits {result.hits}, rendered {result.misses})"
        )
        print(f"  census         {result.census}")
        for filename, digest in result.file_digests.items():
            rows = result.counts.get(filename.removesuffix(".jsonl"), "")
            print(f"  {filename:<34} {rows!s:>6}  {digest[:16]}")
        print(f"  cache entries  {result.counts.get('cache_entries', 0)}")
        print(f"  spans bound    {result.spans_bound}  quote refs bound {result.quotes_bound}")
        if result.pruned:
            print(f"  pruned         {len(result.pruned)} stale cache entries")
        for item in result.deferred:
            print(f"  DEFERRED       {item['node_id']}  -> {item['owner']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpusgen render", description=HELP)
    add_arguments(parser)
    return run(parser.parse_args(list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
