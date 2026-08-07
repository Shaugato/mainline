#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fetch the real corpora into a gitignored cache. **CI never runs this.**

    uv run python scripts/recall/fetch_corpora.py --plan            # print, fetch nothing
    uv run python scripts/recall/fetch_corpora.py --source msha_part50
    uv run python scripts/recall/fetch_corpora.py --all             # everything

Why a separate script
---------------------
The evaluation build (``scripts/recall/build_goldsets.py --from-fixtures``) is hermetic:
no network, no cloud account, no download. This script is the only place that reaches the
internet, it writes only into a cache directory that git ignores, and nothing in CI
invokes it. That separation is what makes "the tests are hermetic" a structural fact
rather than a claim.

What is downloaded, and what is *not* committed
------------------------------------------------
MSHA Part 50 extracts and fatality investigation reports, CSB investigation reports, and
Australian state-regulator safety alerts. **None of it is ever committed.** Some of it for
licence reasons — CSB and MSHA material is US federal work product and effectively public
domain, Australian regulator material is Crown copyright with per-jurisdiction terms — and
all of it because every record is a real injury or a real death, and a repository is a
copy. The committed fixtures are a synthetic replica
(:mod:`trappoint_recall.corpora.synthetic`).

PDF text extraction
--------------------
Fatality reports are PDFs. This package takes **no** PDF dependency. Extraction uses, in
order: ``pypdf`` if it happens to be importable, then a ``pdftotext`` binary if one is on
``PATH``. If neither is available the PDF is cached, the manifest records
``extraction: "unavailable"``, and the report is **not** turned into a text envelope. It
is never faked: an envelope with empty text would be dropped by the loader anyway, and an
envelope with invented text would be a fabricated record in a fatality corpus.

Honesty about the URLs
----------------------
The endpoints below are transcribed from the published documentation and have **not** been
exercised from this machine — this build has no network. They are declared here so a fetch
is a reviewable act rather than a hard-coded string somewhere in a loader, and every
failure is reported with its status code rather than swallowed. Expect to adjust a path;
that is what ``--plan`` is for.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DEFAULT_CACHE: Final[Path] = REPO_ROOT / "out" / "recall-corpora"
"""Default cache root.

``out/`` is already in the repository's ``.gitignore``, so the cache is ignored without
this worker editing a file it does not own. Override with
``$MAINLINE_RECALL_CORPUS_CACHE``."""

CACHE_ENV: Final = "MAINLINE_RECALL_CORPUS_CACHE"
USER_AGENT: Final = "mainline-recall-corpora/0.1 (+https://github.com/Shaugato/mainline)"
TIMEOUT_SECONDS: Final = 120


@dataclass(frozen=True, slots=True)
class Source:
    """One downloadable corpus, with the licence and audience rules attached."""

    key: str
    name: str
    url: str
    filename: str
    licence: str
    corpus_class: str
    tenant_use: str
    notes: str


SOURCES: Final[tuple[Source, ...]] = (
    Source(
        key="msha_part50",
        name="MSHA Part 50 accident/injury extract",
        url="https://arlweb.msha.gov/OpenGovernmentData/DataSets/Accidents.zip",
        filename="Accidents.zip",
        licence="US federal work product; effectively public domain (17 USC 105)",
        corpus_class="real_regulator",
        tenant_use="harness_only",
        notes=(
            "Bar-delimited. NARRATIVE is VARCHAR2(384), so this corpus feeds G2 and not "
            "G1/G4. A definition file is published alongside; the loader is header-driven "
            "and refuses a file whose columns it cannot resolve."
        ),
    ),
    Source(
        key="msha_fatality_index",
        name="MSHA fatality investigation report index",
        url="https://www.msha.gov/data-and-reports/fatality-reports",
        filename="fatality_index.html",
        licence="US federal work product; effectively public domain (17 USC 105)",
        corpus_class="real_regulator",
        tenant_use="harness_only",
        notes=(
            "An index page, not the reports. Report PDFs are fetched from the links it "
            "carries, one at a time, and are the rich material G1 and G4 depend on."
        ),
    ),
    Source(
        key="csb_reports",
        name="CSB completed investigation reports",
        url="https://www.csb.gov/investigations/completed-investigations/",
        filename="csb_index.html",
        licence="US federal work product; effectively public domain (17 USC 105)",
        corpus_class="real_regulator",
        tenant_use="harness_only",
        notes="Process-safety investigations; severity is taken from the casualty counts.",
    ),
    Source(
        key="au_nsw_alerts",
        name="NSW Resources Regulator safety alerts",
        url="https://www.resourcesregulator.nsw.gov.au/safety-and-health/publications/safety-alerts",
        filename="nsw_alerts.html",
        licence="Crown copyright (NSW); check the page's own licence before redistribution",
        corpus_class="real_regulator",
        tenant_use="harness_only",
        notes=(
            "Severity comes from the regulator's classification, not from a casualty "
            "count, so these records carry severity_basis='regulator_class'."
        ),
    ),
    Source(
        key="au_qld_alerts",
        name="Queensland RSHQ safety alerts and notices",
        url="https://www.rshq.qld.gov.au/safety-notices",
        filename="qld_alerts.html",
        licence="Crown copyright (Qld); check the page's own licence before redistribution",
        corpus_class="real_regulator",
        tenant_use="harness_only",
        notes="Same classification-based severity as NSW.",
    ),
)


def cache_root(explicit: str | None = None) -> Path:
    """Resolve the cache directory: flag, then env, then ``out/recall-corpora``."""
    if explicit:
        return Path(explicit).resolve()
    from_env = os.environ.get(CACHE_ENV)
    if from_env:
        return Path(from_env).resolve()
    return DEFAULT_CACHE


def _guard_cache(root: Path) -> None:
    """Refuse a cache inside a tracked fixture tree, and self-ignore the directory.

    A ``.gitignore`` containing ``*`` is written into the cache itself, so even a cache
    pointed somewhere unexpected cannot be committed by accident. Belt and braces, because
    the cost of the mistake is a fatality corpus in a git history.
    """
    tracked = (REPO_ROOT / "tests" / "fixtures", REPO_ROOT / "packages", REPO_ROOT / "spec")
    for forbidden in tracked:
        try:
            root.relative_to(forbidden)
        except ValueError:
            continue
        raise SystemExit(
            f"refusing to cache real regulator data inside the tracked directory "
            f"{forbidden}. Real corpora are never committed: every record is a real "
            f"injury or a real death, and a repository is a copy. Use {DEFAULT_CACHE} or "
            f"set ${CACHE_ENV}."
        )
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("*\n", encoding="utf-8")


def _download(source: Source, destination: Path) -> dict[str, object]:
    request = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})
    started = datetime.now(UTC)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = response.read()
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return {
            "key": source.key,
            "ok": False,
            "status": exc.code,
            "error": f"HTTP {exc.code} {exc.reason}",
        }
    except urllib.error.URLError as exc:
        return {"key": source.key, "ok": False, "status": None, "error": str(exc.reason)}
    except TimeoutError:
        return {
            "key": source.key,
            "ok": False,
            "status": None,
            "error": f"timed out after {TIMEOUT_SECONDS}s",
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "key": source.key,
        "ok": True,
        "status": status,
        "path": destination.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "retrieved_at": started.isoformat(),
        "url": source.url,
        "licence": source.licence,
        "corpus_class": source.corpus_class,
        "tenant_use": source.tenant_use,
    }


def extract_pdf_text(pdf: Path) -> tuple[str | None, str]:
    """Extract text from a PDF, or return ``(None, reason)``. Never fabricates.

    Order: ``pypdf`` if importable, then ``pdftotext`` if on ``PATH``. If neither is
    present the caller records ``extraction: "unavailable"`` and moves on — a fatality
    report with invented text would be a fabricated record, which is worse than a missing
    one by a distance that does not need arguing.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        pass
    else:
        try:
            reader = PdfReader(str(pdf))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
            return (text, "pypdf") if text else (None, "pypdf produced no text")
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            return None, f"pypdf failed: {type(exc).__name__}: {exc}"
    binary = shutil.which("pdftotext")
    if binary:
        try:
            completed = subprocess.run(  # noqa: S603
                [binary, "-layout", str(pdf), "-"],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"pdftotext failed: {exc}"
        text = completed.stdout.decode("utf-8", errors="replace").strip()
        if text:
            return text, "pdftotext"
        return None, "pdftotext produced no text"
    return None, "unavailable: neither pypdf nor pdftotext is present"


def print_plan(sources: Sequence[Source], root: Path) -> None:
    print(f"cache root: {root}")
    print(f"(override with ${CACHE_ENV}; 'out/' is already gitignored)\n")
    for source in sources:
        print(f"  {source.key}")
        print(f"    name    : {source.name}")
        print(f"    url     : {source.url}")
        print(f"    into    : {root / source.filename}")
        print(f"    licence : {source.licence}")
        print(f"    audience: {source.tenant_use} ({source.corpus_class})")
        print(f"    note    : {source.notes}")
        print()
    print(
        "Nothing was downloaded. These URLs are transcribed from published documentation "
        "and have not been exercised from this machine; run without --plan to fetch, and "
        "expect to adjust a path."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch_corpora",
        description=(
            "Fetch real safety corpora into a gitignored cache. CI never runs this; the "
            "gold-set build is hermetic and reads committed synthetic fixtures."
        ),
    )
    parser.add_argument("--cache", help=f"cache root (default {DEFAULT_CACHE}, ${CACHE_ENV})")
    parser.add_argument(
        "--source",
        action="append",
        choices=[s.key for s in SOURCES],
        help="fetch one source; repeatable",
    )
    parser.add_argument("--all", action="store_true", help="fetch every source")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="print what would be fetched and exit without touching the network",
    )
    args = parser.parse_args(argv)

    root = cache_root(args.cache)
    selected = (
        SOURCES
        if args.all or not args.source
        else tuple(s for s in SOURCES if s.key in set(args.source))
    )

    if args.plan or (not args.all and not args.source):
        print_plan(selected, root)
        return 0

    _guard_cache(root)
    results: list[dict[str, object]] = []
    for source in selected:
        print(f"fetching {source.key} … ", end="", flush=True)
        result = _download(source, root / source.filename)
        results.append(result)
        print("ok" if result.get("ok") else f"FAILED ({result.get('error')})")

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cache_root": str(root),
        "statement": (
            "Real regulator data. tenant_use='harness_only' for every entry: the demo "
            "tenant is synthetic, and a real fatality is never presented as a fictional "
            "site's record. Nothing in this directory may be committed."
        ),
        "results": results,
    }
    (root / "cache_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    failures = [r for r in results if not r.get("ok")]
    if failures:
        print(f"\n{len(failures)} of {len(results)} sources failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure['key']}: {failure['error']}", file=sys.stderr)
        return 1
    print(f"\nmanifest: {root / 'cache_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
