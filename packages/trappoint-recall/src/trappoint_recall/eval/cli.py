# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-recall-eval`` — the command line the CI lane and the demo both use.

Subcommands::

    gates      run a backend over a corpus and evaluate the five G4-alpha gates
    metrics    the same run, full metric report, no verdicts
    ablation   run the configuration matrix and emit the published table
    floors     print the committed floors and their ratchet policy
    schema     emit the qrels JSON Schema
    selfcheck  cross-check this package's arithmetic against scipy and scikit-learn

Exit codes are the interface. ``0`` means every gate passed, ``1`` means at least one
gate is RED, ``2`` means the harness could not run at all. A CI lane that treats RED
and "could not run" the same way is a lane that goes green when the corpus disappears.

The default backend is :class:`~trappoint_recall.eval.backend.NullBackend`, so
``trappoint-recall-eval gates --corpus <dir>`` works with nothing implemented and
reports RED, which is the correct state of the world until a retriever exists.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, cast

from trappoint_recall.eval.ablation import (
    DEFAULT_MATRIX,
    AblationArm,
    matrix_config,
    run_ablation_sync,
)
from trappoint_recall.eval.backend import NullBackend, RetrievalBackend
from trappoint_recall.eval.corpus import CorpusError, load_corpus
from trappoint_recall.eval.crosscheck import CrosscheckUnavailable, crosscheck_all
from trappoint_recall.eval.gates import evaluate_g4alpha, load_floors, overall_status
from trappoint_recall.eval.harness import DEFAULT_K, compute_metrics, run_evaluation_sync
from trappoint_recall.eval.qrels import qrels_json_schema
from trappoint_recall.eval.report import (
    render_gate_markdown,
    render_metrics_markdown,
    render_status_json,
)

__all__ = ["build_parser", "main"]

EXIT_OK: Final = 0
EXIT_GATE_RED: Final = 1
EXIT_USAGE: Final = 2

DEFAULT_BACKEND: Final = "trappoint_recall.eval.backend:NullBackend"


class CliError(RuntimeError):
    """A problem with how the harness was invoked or configured, not a gate failure."""


def _load_object(spec: str) -> object:
    """Import ``module:attribute``."""
    if ":" not in spec:
        raise CliError(
            f"expected 'module:attribute', got {spec!r} "
            "(for example trappoint_recall.eval.backend:NullBackend)"
        )
    module_name, _, attribute = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise CliError(f"cannot import module {module_name!r}: {exc}") from exc
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise CliError(f"module {module_name!r} has no attribute {attribute!r}") from exc


def _load_backend(spec: str) -> RetrievalBackend:
    obj = _load_object(spec)
    candidate = obj() if isinstance(obj, type) else obj
    if not callable(getattr(candidate, "retrieve", None)):
        raise CliError(
            f"{spec} does not satisfy RetrievalBackend: no awaitable 'retrieve' attribute"
        )
    return cast(RetrievalBackend, candidate)


def _load_factory(spec: str) -> Callable[[AblationArm], RetrievalBackend]:
    obj = _load_object(spec)
    if not callable(obj):
        raise CliError(f"{spec} is not callable; an ablation factory takes an AblationArm")
    return cast(Callable[[AblationArm], RetrievalBackend], obj)


def _write(text: str, out: Path | None) -> None:
    if out is None:
        sys.stdout.write(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    sys.stderr.write(f"written: {out}\n")


# --------------------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------------------


def cmd_gates(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.corpus)
    backend = _load_backend(args.backend)
    run = run_evaluation_sync(backend, corpus, k=args.k, concurrency=args.concurrency)
    bundle = compute_metrics(run, corpus)
    results = evaluate_g4alpha(bundle)
    text = (
        render_status_json(bundle, results)
        if args.format == "json"
        else render_gate_markdown(bundle, results)
    )
    _write(text, args.out)
    status = overall_status(results)
    if args.format != "json":
        sys.stderr.write(f"G4alpha lane: {'GREEN' if status == 'PASS' else 'RED'}\n")
    return EXIT_OK if status == "PASS" else EXIT_GATE_RED


def cmd_metrics(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.corpus)
    backend = _load_backend(args.backend)
    run = run_evaluation_sync(backend, corpus, k=args.k, concurrency=args.concurrency)
    bundle = compute_metrics(run, corpus)
    text = (
        json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else render_metrics_markdown(bundle)
    )
    _write(text, args.out)
    return EXIT_OK


def cmd_ablation(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.corpus)
    factory = _load_factory(args.factory)
    table = run_ablation_sync(
        factory, corpus, matrix=DEFAULT_MATRIX, k=args.k, concurrency=args.concurrency
    )
    text = table.to_json() if args.format == "json" else table.to_markdown()
    _write(text, args.out)
    return EXIT_OK


def cmd_floors(args: argparse.Namespace) -> int:
    _write(json.dumps(load_floors(), indent=2, sort_keys=True) + "\n", args.out)
    return EXIT_OK


def cmd_matrix(args: argparse.Namespace) -> int:
    _write(json.dumps(matrix_config(), indent=2, sort_keys=True) + "\n", args.out)
    return EXIT_OK


def cmd_schema(args: argparse.Namespace) -> int:
    _write(json.dumps(qrels_json_schema(), indent=2, sort_keys=True) + "\n", args.out)
    return EXIT_OK


def cmd_selfcheck(args: argparse.Namespace) -> int:
    results = crosscheck_all()
    lines = [r.render() for r in results]
    payload = (
        json.dumps([r.to_dict() for r in results], indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else "\n".join(lines) + "\n"
    )
    _write(payload, args.out)
    return EXIT_OK if all(r.agrees for r in results) else EXIT_GATE_RED


# --------------------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trappoint-recall-eval",
        description=(
            "Recall evaluation harness. Every number it prints carries an interval, a "
            "sample size and the split policy that produced it."
        ),
        epilog=(
            "Exit codes: 0 all gates pass, 1 at least one gate is RED, 2 the harness could not run."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser, *, backend: bool = True) -> None:
        p.add_argument("--corpus", type=Path, required=True, help="corpus directory")
        if backend:
            p.add_argument(
                "--backend",
                default=DEFAULT_BACKEND,
                help=f"module:attribute of a RetrievalBackend (default: {DEFAULT_BACKEND})",
            )
        p.add_argument("--k", type=int, default=DEFAULT_K, help="retrieval depth")
        p.add_argument("--concurrency", type=int, default=8, help="concurrent permits")
        p.add_argument("--format", choices=("md", "json"), default="md")
        p.add_argument("--out", type=Path, default=None, help="output file (default: stdout)")

    gates = sub.add_parser("gates", help="evaluate the five G4-alpha release gates")
    add_common(gates)
    gates.set_defaults(func=cmd_gates)

    metrics = sub.add_parser("metrics", help="full metric report, no verdicts")
    add_common(metrics)
    metrics.set_defaults(func=cmd_metrics)

    ablation = sub.add_parser("ablation", help="run the configuration matrix")
    add_common(ablation, backend=False)
    ablation.add_argument(
        "--factory",
        required=True,
        help="module:attribute of a callable taking an AblationArm and returning a backend",
    )
    ablation.set_defaults(func=cmd_ablation)

    floors = sub.add_parser("floors", help="print the committed release floors")
    floors.add_argument("--out", type=Path, default=None)
    floors.set_defaults(func=cmd_floors)

    matrix = sub.add_parser("matrix", help="print the ablation matrix as data")
    matrix.add_argument("--out", type=Path, default=None)
    matrix.set_defaults(func=cmd_matrix)

    schema = sub.add_parser("schema", help="emit the qrels JSON Schema")
    schema.add_argument("--out", type=Path, default=None)
    schema.set_defaults(func=cmd_schema)

    selfcheck = sub.add_parser(
        "selfcheck", help="cross-check the arithmetic against scipy and scikit-learn"
    )
    selfcheck.add_argument("--format", choices=("md", "json"), default="md")
    selfcheck.add_argument("--out", type=Path, default=None)
    selfcheck.set_defaults(func=cmd_selfcheck)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = cast(Callable[[argparse.Namespace], int], args.func)
    try:
        return handler(args)
    except (CliError, CorpusError, CrosscheckUnavailable) as exc:
        sys.stderr.write(f"trappoint-recall-eval: {exc}\n")
        return EXIT_USAGE
    except FileNotFoundError as exc:
        sys.stderr.write(f"trappoint-recall-eval: file not found: {exc}\n")
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
