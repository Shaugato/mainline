#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Build G1/G2/G3/G4, the negative control, the THYMOGATE panel and GS0.

    uv run python scripts/recall/build_goldsets.py --from-fixtures    # hermetic, no network
    uv run python scripts/recall/build_goldsets.py --check            # rebuild and diff
    uv run python scripts/recall/build_goldsets.py --regenerate-fixtures
    uv run python scripts/recall/build_goldsets.py --from-cache       # the real corpora

``--from-fixtures`` is the default and the only mode CI runs. It reads the committed
synthetic replica under ``tests/fixtures/recall/inputs/``, runs the real loaders and the
real gold-set builders over it, and writes the gold sets back into
``tests/fixtures/recall/``. The outputs are committed on purpose: a gold set nobody can
read in a diff is a gold set nobody reviews.

``--check`` rebuilds into a temporary directory and compares byte-for-byte against what is
committed. It is the CI assertion that the committed gold sets really are the output of
the committed inputs, and it is what makes ``--from-fixtures`` safe to run in a working
tree.

``--from-cache`` builds from the real corpora fetched by ``fetch_corpora.py``. It refuses
to run without a cache manifest, and it refuses a demo destination outright.

Network
-------
None. This script opens no socket in any mode. ``--from-cache`` reads a directory the
fetch script populated; if that directory is absent the script says so and exits non-zero
rather than reaching for the internet.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGE_SRC: Final[Path] = REPO_ROOT / "packages" / "trappoint-recall" / "src"
if PACKAGE_SRC.is_dir() and str(PACKAGE_SRC) not in sys.path:
    # The uv workspace installs trappoint-recall editable, so this is normally a no-op. It
    # exists so the build also runs from a bare checkout: "the build would not import" must
    # never be why a gold set is missing.
    sys.path.insert(0, str(PACKAGE_SRC))

from trappoint_recall.corpora.build import (  # noqa: E402
    SYNTHETIC_PROVENANCE,
    build_goldsets,
    regenerate_fixtures,
    write_provenance_manifest,
)
from trappoint_recall.corpora.provenance import FixtureProvenance  # noqa: E402

FIXTURES_ROOT: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "recall"
CACHE_ROOT: Final[Path] = REPO_ROOT / "out" / "recall-corpora"

_COMPARED = (
    "goldsets/g1_citations.qrels.jsonl",
    "goldsets/g2_codes.qrels.jsonl",
    "goldsets/g3_adjudicated.qrels.jsonl",
    "goldsets/g4_retro.qrels.jsonl",
    "goldsets/g4_retro.queries.jsonl",
    "goldsets/g3_worksheet.jsonl",
    "goldsets/negative_control.queries.jsonl",
    "goldsets/gs0/queries.jsonl",
    "goldsets/gs0/qrels.jsonl",
    "goldsets/gs0/split.json",
    "goldsets/gs0/manifest.json",
    "thymogate_panel.json",
)
"""Files ``--check`` compares. ``build_report.json`` is excluded: it is a description of
the build, not the build, and comparing it would make the check fail on a reworded note."""


def _summarise(report: dict[str, object]) -> str:
    lines: list[str] = []
    loaders = report.get("loaders", {})
    if isinstance(loaders, dict):
        lines.append(
            f"  corpora    : {loaders.get('n_kept')}/{loaders.get('n_read')} records kept, "
            f"{loaders.get('n_dropped')} dropped {loaders.get('dropped')}"
        )
    for key, label in (
        ("g1_citations", "G1 citations"),
        ("g2_codes", "G2 codes"),
        ("g3_adjudicated", "G3 adjudicated"),
        ("g4_retro", "G4 retro"),
        ("negative_control", "negative ctl"),
        ("thymogate_panel", "THYMOGATE"),
        ("gs0", "GS0"),
    ):
        block = report.get(key)
        if isinstance(block, dict):
            lines.append(f"  {label:<11}: {json.dumps(block, sort_keys=True)[:300]}")
    return "\n".join(lines)


def _run_build(fixtures: Path, out: Path, provenance: FixtureProvenance) -> dict[str, object]:
    result = build_goldsets(fixtures, out, provenance=provenance)
    return dict(result.report)


def _check(fixtures: Path, committed: Path, provenance: FixtureProvenance) -> int:
    with tempfile.TemporaryDirectory(prefix="mainline-goldsets-") as temporary:
        scratch = Path(temporary)
        _run_build(fixtures, scratch, provenance)
        mismatched: list[str] = []
        missing: list[str] = []
        for relative in _COMPARED:
            rebuilt = scratch / relative
            existing = committed / relative
            if not existing.is_file():
                missing.append(relative)
                continue
            if not filecmp.cmp(rebuilt, existing, shallow=False):
                mismatched.append(relative)
        if missing or mismatched:
            print("gold sets are not reproducible from the committed inputs:", file=sys.stderr)
            for relative in missing:
                print(f"  MISSING   {relative}", file=sys.stderr)
            for relative in mismatched:
                print(f"  DIFFERS   {relative}", file=sys.stderr)
            print(
                "\nRun --from-fixtures and commit the result. A gold set that cannot be "
                "rebuilt from its inputs is a gold set nobody can review.",
                file=sys.stderr,
            )
            return 1
    print(f"OK: {len(_COMPARED)} artefacts rebuild byte-identically from the committed inputs")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_goldsets",
        description="Build the recall gold sets. No network in any mode.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--from-fixtures",
        action="store_true",
        help="build from the committed synthetic fixtures (default; hermetic)",
    )
    mode.add_argument(
        "--from-cache",
        action="store_true",
        help="build from the real corpora fetched into the gitignored cache",
    )
    mode.add_argument(
        "--regenerate-fixtures",
        action="store_true",
        help="rewrite the committed inputs from the deterministic generator",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="rebuild into a temporary directory and diff against what is committed",
    )
    parser.add_argument("--fixtures", help=f"fixtures root (default {FIXTURES_ROOT})")
    parser.add_argument("--cache", help=f"cache root (default {CACHE_ROOT})")
    parser.add_argument("--out", help="output root (default: the fixtures root)")
    parser.add_argument(
        "--destination-use",
        default="harness_only",
        choices=["harness_only", "demo_tenant"],
        help=(
            "who the outputs are for. Real regulator data with a demo destination is "
            "refused: the demo tenant is synthetic and a real fatality is never presented "
            "as a fictional site's record."
        ),
    )
    args = parser.parse_args(argv)

    fixtures = Path(args.fixtures).resolve() if args.fixtures else FIXTURES_ROOT

    if args.regenerate_fixtures:
        summary = regenerate_fixtures(fixtures)
        manifest = write_provenance_manifest(fixtures)
        print(f"regenerated inputs under {fixtures / 'inputs'}")
        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"provenance: {len(manifest.files)} files digested")
        print(
            "\nNow run --from-fixtures to rebuild the gold sets, then --check to confirm "
            "they are reproducible."
        )
        return 0

    if args.from_cache:
        cache = Path(args.cache).resolve() if args.cache else CACHE_ROOT
        manifest_path = cache / "cache_manifest.json"
        if not manifest_path.is_file():
            print(
                f"no cache manifest at {manifest_path}. Run "
                "scripts/recall/fetch_corpora.py first. This script opens no socket: a "
                "missing cache is reported, never fetched on the fly.",
                file=sys.stderr,
            )
            return 2
        provenance = FixtureProvenance(
            corpus_class="real_regulator",
            tenant_use="harness_only",
            source_name="MSHA / CSB / AU state regulators",
            licence="mixed; see cache_manifest.json per source",
            retrieved_at=None,
            notes=(
                "Fetched by scripts/recall/fetch_corpora.py. Harness only, without "
                "exception: every record is a real injury or a real death."
            ),
        )
        out = Path(args.out).resolve() if args.out else cache / "goldsets-out"
        report = _run_build(cache, out, provenance)
        print(f"built from the real corpora into {out}")
        print(_summarise(report))
        return 0

    if args.check:
        return _check(fixtures, fixtures, SYNTHETIC_PROVENANCE)

    out = Path(args.out).resolve() if args.out else fixtures
    if args.destination_use != "harness_only":
        # Synthetic replica data would pass the provenance check, but the build refuses
        # anyway when the caller has not thought about it: see build_goldsets().
        print(
            "note: destination-use is not harness_only; provenance will be checked and a "
            "real corpus would be refused."
        )
    result = build_goldsets(
        fixtures, out, provenance=SYNTHETIC_PROVENANCE, destination_use=args.destination_use
    )
    print(f"built into {out}")
    print(_summarise(dict(result.report)))
    panel = out / "thymogate_panel.json"
    if panel.is_file():
        print(f"  panel      : {panel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
