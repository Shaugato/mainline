#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Open a built Lambda deployment zip and say — from the zip alone — what is in it.

WHY THIS IS A SEPARATE PROGRAM
------------------------------
``scripts/deploy/build_lambda.sh`` and ``.ps1`` already print what they packed. That is a
**log**: it describes what the builder believed it was doing, in the process that did it.
This program describes what the artefact *is*, by reading the artefact, with no access to
the staging tree, the repository, or the builder's intentions. It therefore answers the
only question that matters at 03:00 four days before a deadline — *is the zip that is
about to be uploaded the zip we think it is?* — and it answers it about a file that may
have been produced on another machine, by another worker, last week.

Everything here is standard library. It runs against any zip, including one this
repository did not build, on any Python 3.9 or newer.

WHAT IT CHECKS
--------------
**Required roots** (gating, always). Under decision D1 — ``docs/leads/ship-final.md``
§1.4 — one Lambda serves the console SPA *and* ``/v1/*``, so a deployment package that is
missing any of these is a demo URL that answers with something the judges cannot use:

====================  ================================================================
``mainline_demo_api/``  the handler package; without it every invocation is an
                        ``Unable to import module 'mainline_demo_api.app'``
``psycopg/``            the driver; without it ``/v1/*`` is a 500 and ``/`` still works,
                        which is the most confusing failure of the four
``web/index.html``      the console shell; without it ``GET /`` is the handler's 503
                        ``web_root_not_bundled``
``web/bundle/``         the verified EvidenceBundle; without it the console's REPLAY
                        source 404s and the fallback the whole demo leans on is gone
====================  ================================================================

**Forbidden import roots** (gating, always). ``demo-api/pyproject.toml`` declares this
distribution's dependencies, and the zip is the only place that declaration can be
checked against bytes. :data:`DEFAULT_FORBIDDEN` names the twelve roots the declaration
excludes — every web framework, every AWS SDK and the three HTTP clients — and a package
carrying any of them is refused. There is no build mode of this package in which one of
them is legitimate, which is why this gate takes no flag: a Lambda invocation is already
a function call with a dict argument, so there is nothing for a server to do, and
``mainline_demo_api.db`` signs its one SSM ``GetParameter`` with ``hashlib`` and ``hmac``
so the package's behaviour does not depend on which boto3 the runtime image happens to
ship this month.

This is a statement about the ARTEFACT, and that is the point of making it here.
``demo-api/tests/test_envelope.py`` makes the matching statement about the import
CLOSURE, and it makes it in a fresh interpreter for the same reason: the earlier version
of that test read ``sys.modules`` in the shared pytest process, so a sibling package that
imported ``pydantic`` two thousand tests earlier made it report that *the deployment
package* had pulled ``pydantic`` in. It had not. A check whose verdict is decided by
something other than its subject is not a check, and this program's subject is a file.

**Size limits** (gating, always). Lambda refuses a direct upload over **50 MB zipped**
and refuses to unpack over **250 MB**. Both ceilings are AWS's, both are checked here
against the real numbers rather than assumed from a build that fitted last week.

**Source maps** (gating under ``--forbid-source-maps``). ``web/**/*.map`` is egress no
caller needs: 18 files and 2,586,960 B on the console build measured 2026-08-13, which is
72.42 % of the served tree. ``build_lambda`` strips them by default, so the gate exists to
catch a build that stopped stripping. It is a flag rather than a default because
``build_lambda --keep-source-maps`` is a legitimate, documented debug build, and a
describer that refused the artefact it was asked to make would not be a describer.

**Determinism properties** (reported always, gating under ``--strict``). These are
readable from the zip's own central directory and are exactly the fields a non-
reproducible writer gets wrong:

* every entry carries the fixed DOS epoch ``1980-01-01 00:00:00``;
* entry order in the central directory is byte-sorted by name;
* every entry is ``ZIP_DEFLATED``;
* every entry declares ``create_system = 3`` (Unix) and one of two fixed modes.

A zip that satisfies all four will hash identically to a rebuild from the same tree. A
zip that fails one of them may still be a perfectly good Lambda package — which is why
they gate only under ``--strict``, and why ``build_lambda`` passes ``--strict``.

**The shape of the served tree** (reported always, gating never). Under decision D1 this
package is the whole public origin behind a Function URL whose ``authorization_type`` is
``NONE``, so every byte under ``web/`` is egress any caller can bill to the account at
will. :func:`web_shape` reads the central directory and says what that tree costs: how
much of it is identity bytes and how much is the pre-compressed ``.gz`` siblings of
interface I1, the largest object a caller can pull with and without ``accept-encoding``,
how many gzipped objects clear 64 KiB, and — the two that catch a regression — which
compressible entries have **no** sibling and which siblings have **no** identity twin.

It does not gate, deliberately. This program must stay runnable against any zip,
including one with no ``web/`` at all, and a describer that refuses an input it was
built to describe is no longer a describer. The gating statement about the served tree
is the wire-ceiling assertion in the demo-api's own tests, which is measured over this
same package and fails when an asset outgrows the ceiling.

EXIT CODES
----------
====  ============================================================================
0     every gating check passed
2     a required root is missing, a forbidden import root is present, a size limit is
      exceeded, ``--forbid-source-maps`` and the served tree has one, or ``--strict``
      and a determinism property failed
1     usage error, unreadable file, or not a zip
====  ============================================================================

USAGE
-----
::

    python scripts/deploy/bundle_manifest.py out/lambda/mainline-demo-api-arm64.zip
    python scripts/deploy/bundle_manifest.py <zip> --list
    python scripts/deploy/bundle_manifest.py <zip> --json out/lambda/manifest.json --quiet
    python scripts/deploy/bundle_manifest.py <zip> --strict \
        --require mainline_demo_api/app.py --require web/bundle/manifest.json
    python scripts/deploy/bundle_manifest.py <zip> --forbid-source-maps --forbid psycopg_pool
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

__all__ = [
    "COMPRESSIBLE_SUFFIXES",
    "DEFAULT_FORBIDDEN",
    "DEFAULT_REQUIRED",
    "EPOCH",
    "GZ_LARGE_OBJECT_BYTES",
    "GZ_SUFFIX",
    "LAMBDA_MAX_UNZIPPED_BYTES",
    "LAMBDA_MAX_ZIPPED_BYTES",
    "MODULE_SUFFIXES",
    "SOURCE_MAP_SUFFIX",
    "WEB_ROOT",
    "check",
    "describe",
    "importable_as",
    "main",
    "web_shape",
]

#: The four roots the D1 single-origin demo cannot be served without. A trailing ``/``
#: means "at least one entry under this prefix"; anything else is an exact entry name.
DEFAULT_REQUIRED: tuple[str, ...] = (
    "mainline_demo_api/",
    "psycopg/",
    "web/index.html",
    "web/bundle/",
)

#: The twelve import roots ``demo-api/pyproject.toml`` declares this distribution does
#: not depend on: six web frameworks and the Lambda adapter, the AWS SDK and its core,
#: and the three HTTP clients. Unlike the source-map gate these are refused with no flag,
#: because no build mode of this package legitimately contains one — see this module's
#: docstring for why the handler needs neither a server nor an SDK.
#:
#: Held identical to ``BANNED_IMPORT_ROOTS`` in
#: ``verticals/mainline/apps/demo-api/tests/test_envelope.py``, which makes the same
#: statement about the import closure rather than about the bytes;
#: ``test_the_closure_claim_and_the_artefact_claim_name_the_same_roots`` fails if the two
#: lists drift apart.
DEFAULT_FORBIDDEN: tuple[str, ...] = (
    "aiohttp",
    "boto3",
    "botocore",
    "django",
    "fastapi",
    "flask",
    "httpx",
    "mangum",
    "pydantic",
    "requests",
    "starlette",
    "uvicorn",
)

#: The DOS epoch. ``zipfile`` cannot store anything earlier, so it is the canonical
#: "this timestamp is not information" value and the one ``build_lambda`` writes.
EPOCH: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)

#: AWS Lambda quotas, deployment package. Both are hard service limits, not defaults.
LAMBDA_MAX_ZIPPED_BYTES = 50 * 1024 * 1024
LAMBDA_MAX_UNZIPPED_BYTES = 250 * 1024 * 1024

#: The two modes ``build_lambda`` writes: 0755 for shared objects, 0644 for everything
#: else. Any other mode means some other writer produced the entry.
FIXED_MODES = (0o644, 0o755)

#: The prefix the served site lives under, and the only part of the package a caller on
#: the internet can pull bytes from.
WEB_ROOT = "web/"

#: The suffix interface I1 gives the pre-compressed sibling.
GZ_SUFFIX = ".gz"

#: The suffix of a JavaScript source map, the thing ``--forbid-source-maps`` refuses.
SOURCE_MAP_SUFFIX = ".map"

#: The final suffixes a top-level SINGLE-FILE module can carry. Checked as well as the
#: ``root/`` directory shape, because a distribution that ships one module -- and several
#: on the forbidden list have shipped one at some point in their history -- would sail
#: past a check that only looked for a folder.
MODULE_SUFFIXES: tuple[str, ...] = ("py", "pyc", "pyd", "so")

#: Suffixes whose bytes compress. Held in step with the packer embedded in
#: ``build_lambda.{sh,ps1}`` and with ``mainline_demo_api.static_site.MEDIA_TYPES``:
#: exactly the entries that table marks as text, JavaScript, JSON, SVG or wasm. The image
#: and font types it also names are already-compressed containers, and this program uses
#: the list only to report which compressible entries are missing a sibling — so a
#: divergence from the packer shows up as a finding here rather than as silent egress.
COMPRESSIBLE_SUFFIXES: tuple[str, ...] = (
    ".css",
    ".html",
    ".js",
    ".json",
    ".map",
    ".mjs",
    ".svg",
    ".txt",
    ".wasm",
    ".webmanifest",
)

#: A gzipped object above this is one a wire ceiling has to be chosen around rather than
#: over. Reported, never enforced here.
GZ_LARGE_OBJECT_BYTES = 64 * 1024

_READ_BLOCK = 1 << 20


# ── Reading ─────────────────────────────────────────────────────────────────────────


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(_READ_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as handle:
        for block in iter(lambda: handle.read(_READ_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _suffix(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    dot = base.rfind(".")
    return base[dot:].lower() if dot > 0 else ""


def importable_as(name: str, root: str) -> bool:
    """Would ``import root`` find zip entry *name* with the package root on ``sys.path``?

    Pure, and deliberately narrow. Only the FIRST path segment can answer an unqualified
    import, so ``psycopg/vendor/boto3/x.py`` is not a hit — vendored bytes inside another
    distribution are that distribution's business and are not importable as ``boto3``.

    Two shapes count. ``root/…`` is the package directory. ``root.py`` and its compiled
    forms are a single-file module, and the tail is compared rather than the whole suffix
    so an extension module's platform tag — ``_psycopg.cpython-313-x86_64-linux-gnu.so``
    — is recognised. ``psycopg_binary.libs/`` is therefore NOT a hit for
    ``psycopg_binary``: ``libs`` is not one of :data:`MODULE_SUFFIXES`, and that directory
    holds shared objects the loader finds by path, not by import.
    """
    head = name.split("/", 1)[0]
    if head == root:
        return True
    stem, dot, tail = head.partition(".")
    return bool(dot) and stem == root and tail.rsplit(".", 1)[-1].lower() in MODULE_SUFFIXES


def web_shape(entries: list[dict[str, Any]], *, root: str = WEB_ROOT) -> dict[str, Any]:
    """What the served tree costs, from the central directory alone. Pure.

    Two numbers matter and they are not the same number. ``largest_identity_object`` is
    what a caller that sent no ``accept-encoding`` can pull in one request;
    ``largest_gz_object`` is what every modern browser pulls. Under interface I1 a direct
    request for a path ending ``.gz`` is a 404, so the sibling is reachable only through
    negotiation and the two are one object under one name.

    ``compressible_without_sibling`` and ``gz_without_identity`` are the regression
    detectors. The first is a text object that will go out uncompressed — the exact
    failure a build that quietly stopped pre-compressing would produce, and one that no
    size total would reveal, because dropping the siblings makes the package *smaller*.
    The second is dead weight that can never be served.
    """
    web = [e for e in entries if e["path"].startswith(root) and not e["is_dir"]]
    identity = [e for e in web if not e["path"].endswith(GZ_SUFFIX)]
    siblings = [e for e in web if e["path"].endswith(GZ_SUFFIX)]

    identity_names = {e["path"] for e in identity}
    sibling_names = {e["path"] for e in siblings}

    def biggest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        top = max(rows, key=lambda e: e["bytes"])
        return {"path": top["path"], "bytes": top["bytes"]}

    maps = [e for e in identity if e["path"].endswith(".map")]

    return {
        "root": root,
        "entries": len(web),
        "bytes": sum(e["bytes"] for e in web),
        "identity": {"entries": len(identity), "bytes": sum(e["bytes"] for e in identity)},
        "gz": {
            "entries": len(siblings),
            "bytes": sum(e["bytes"] for e in siblings),
            "above_large_object": sum(1 for e in siblings if e["bytes"] > GZ_LARGE_OBJECT_BYTES),
            "large_object_threshold": GZ_LARGE_OBJECT_BYTES,
        },
        "source_maps": {"entries": len(maps), "bytes": sum(e["bytes"] for e in maps)},
        "largest_identity_object": biggest(identity),
        "largest_gz_object": biggest(siblings),
        "compressible_without_sibling": sorted(
            e["path"]
            for e in identity
            if _suffix(e["path"]) in COMPRESSIBLE_SUFFIXES
            and e["path"] + GZ_SUFFIX not in sibling_names
        ),
        "gz_without_identity": sorted(
            name for name in sibling_names if name[: -len(GZ_SUFFIX)] not in identity_names
        ),
    }


def describe(path: str, *, hash_entries: bool = True) -> dict[str, Any]:
    """Return the full manifest of the zip at *path*. Reads; decides nothing."""
    with zipfile.ZipFile(path, "r") as archive:
        # `infolist()` preserves central-directory order, which is what a reproducible
        # writer controls and what `sorted_entries` below is a statement about.
        infos = archive.infolist()

        entries: list[dict[str, Any]] = []
        for info in infos:
            entry: dict[str, Any] = {
                "path": info.filename,
                "bytes": info.file_size,
                "bytes_compressed": info.compress_size,
                "date_time": list(info.date_time),
                "compress_type": info.compress_type,
                "create_system": info.create_system,
                "mode": (info.external_attr >> 16) & 0o7777,
                "is_dir": info.is_dir(),
            }
            if hash_entries and not info.is_dir():
                entry["sha256"] = _sha256_member(archive, info)
            entries.append(entry)

    names = [entry["path"] for entry in entries]
    unzipped = sum(entry["bytes"] for entry in entries)

    # Top-level layout: one row per first path segment, so "what is in this zip" fits on
    # a screen even when the zip has two hundred entries.
    layout: dict[str, dict[str, int]] = {}
    for entry in entries:
        head = entry["path"].split("/", 1)[0]
        row = layout.setdefault(head, {"entries": 0, "bytes": 0})
        row["entries"] += 1
        row["bytes"] += entry["bytes"]

    return {
        "artifact": path.replace("\\", "/").rsplit("/", 1)[-1],
        "sha256": _sha256_file(path),
        "bytes_zipped": _zip_size(path),
        "bytes_unzipped": unzipped,
        "entry_count": len(entries),
        "top_level": {name: layout[name] for name in sorted(layout)},
        "determinism": {
            "fixed_timestamps": all(tuple(e["date_time"]) == EPOCH for e in entries),
            "sorted_entries": names == sorted(names),
            "all_deflated": all(
                e["compress_type"] == zipfile.ZIP_DEFLATED for e in entries if not e["is_dir"]
            ),
            "unix_create_system": all(e["create_system"] == 3 for e in entries),
            "fixed_modes": all(e["mode"] in FIXED_MODES for e in entries if not e["is_dir"]),
            "no_directory_entries": not any(e["is_dir"] for e in entries),
        },
        "web_shape": web_shape(entries),
        "entries": entries,
    }


def _zip_size(path: str) -> int:
    return Path(path).stat().st_size


# ── Deciding ────────────────────────────────────────────────────────────────────────


def check(
    manifest: dict[str, Any],
    *,
    required: tuple[str, ...] = DEFAULT_REQUIRED,
    forbidden: tuple[str, ...] = DEFAULT_FORBIDDEN,
    forbid_source_maps: bool = False,
    strict: bool = False,
    max_zipped: int = LAMBDA_MAX_ZIPPED_BYTES,
    max_unzipped: int = LAMBDA_MAX_UNZIPPED_BYTES,
) -> dict[str, Any]:
    """Turn a manifest into a verdict. Pure: takes a dict, returns a dict."""
    names = [entry["path"] for entry in manifest["entries"]]
    name_set = set(names)
    sizes = {entry["path"]: entry["bytes"] for entry in manifest["entries"]}

    roots: list[dict[str, Any]] = []
    for want in required:
        if want.endswith("/"):
            matched = sum(1 for name in names if name.startswith(want))
            present = matched > 0
        else:
            matched = 1 if want in name_set else 0
            present = want in name_set
        roots.append({"root": want, "present": present, "entries": matched})

    missing = [row["root"] for row in roots if not row["present"]]

    # Every forbidden root is reported, present or absent, so the JSON says what was
    # LOOKED FOR and not only what was found. A gate that records nothing when it passes
    # cannot be told apart later from a gate that was never run.
    forbidden_rows: list[dict[str, Any]] = []
    for banned in forbidden:
        hits = sorted(name for name in names if importable_as(name, banned))
        forbidden_rows.append(
            {
                "root": banned,
                # Where the ban came from, so the refusal can cite the right authority.
                # A root the pyproject declares absent and a root the caller typed on the
                # command line are both refused, but only one of them is a broken promise.
                "source": "pyproject" if banned in DEFAULT_FORBIDDEN else "--forbid",
                "present": bool(hits),
                "entries": len(hits),
                "bytes": sum(sizes[name] for name in hits),
                "example": hits[0] if hits else None,
            }
        )
    forbidden_present = [row["root"] for row in forbidden_rows if row["present"]]

    map_entries = [
        name
        for name in names
        if name.startswith(WEB_ROOT) and name.lower().endswith(SOURCE_MAP_SUFFIX)
    ]
    source_maps = {
        "entries": len(map_entries),
        "bytes": sum(sizes[name] for name in map_entries),
        "gating": forbid_source_maps,
        "ok": not (forbid_source_maps and map_entries),
        "example": map_entries[0] if map_entries else None,
    }

    limits = [
        {
            "limit": "zipped",
            "measured": manifest["bytes_zipped"],
            "ceiling": max_zipped,
            "ok": manifest["bytes_zipped"] <= max_zipped,
            "why": "AWS Lambda refuses a direct (non-S3) upload above 50 MB.",
        },
        {
            "limit": "unzipped",
            "measured": manifest["bytes_unzipped"],
            "ceiling": max_unzipped,
            "ok": manifest["bytes_unzipped"] <= max_unzipped,
            "why": "AWS Lambda refuses to unpack a deployment package above 250 MB.",
        },
    ]
    exceeded = [row["limit"] for row in limits if not row["ok"]]

    determinism = manifest["determinism"]
    broken_properties = sorted(name for name, ok in determinism.items() if not ok)

    refusals: list[str] = []
    for root in missing:
        refusals.append(f"REFUSED [MISSING ROOT] {root} is not in this package")
    for root in forbidden_present:
        row = next(item for item in forbidden_rows if item["root"] == root)
        why = (
            "the demo-api pyproject declares it absent"
            if row["source"] == "pyproject"
            else "it was named with --forbid"
        )
        refusals.append(
            "REFUSED [FORBIDDEN ROOT] {root} is importable from this package -- {entries} "
            "entries, {bytes} bytes, e.g. {example}. Refused because {why}.".format(**row, why=why)
        )
    if not source_maps["ok"]:
        refusals.append(
            "REFUSED [SOURCE MAPS] {} entries under {} total {} bytes -- e.g. {}. This build "
            "asked for none, and nothing serves them.".format(
                source_maps["entries"], WEB_ROOT, source_maps["bytes"], source_maps["example"]
            )
        )
    for name in exceeded:
        row = next(item for item in limits if item["limit"] == name)
        # ASCII only in everything this program PRINTS: a Windows console is cp1252 by
        # default, and a refusal that arrives as `?` where the reason should be is a
        # refusal nobody acts on.
        refusals.append(
            "REFUSED [SIZE] {limit} {measured} bytes exceeds the Lambda ceiling of "
            "{ceiling} bytes -- {why}".format(**row)
        )
    if strict:
        for name in broken_properties:
            refusals.append(
                f"REFUSED [DETERMINISM] {name} is false; this zip will not hash the same "
                "as a rebuild from the same tree"
            )

    return {
        "required_roots": roots,
        "missing_roots": missing,
        "forbidden_roots": forbidden_rows,
        "forbidden_present": forbidden_present,
        "source_maps": source_maps,
        "limits": limits,
        "limits_exceeded": exceeded,
        "determinism": determinism,
        "determinism_failed": broken_properties,
        "strict": strict,
        "refusals": refusals,
        "verdict": "PASS" if not refusals else "REFUSED",
    }


# ── Printing ────────────────────────────────────────────────────────────────────────


def _mb(value: int) -> str:
    return f"{value / 1048576.0:.2f} MB"


def _gate_lines(verdict: dict[str, Any]) -> list[str]:
    """The two gates that describe what was LOOKED FOR, not only what was found.

    Both counts are printed even when the answer is zero. "0 present" and "nobody
    checked" render identically otherwise, and the second is the state this program
    exists to make impossible to mistake for the first.
    """
    lines = [
        "  forbidden import roots             {:>7} declared, {} present".format(
            len(verdict["forbidden_roots"]), len(verdict["forbidden_present"])
        )
    ]
    lines.extend(
        "  {:<34} {:>7}  {:>11}  e.g. {}".format(
            row["root"], row["entries"], row["bytes"], row["example"]
        )
        for row in verdict["forbidden_roots"]
        if row["present"]
    )
    maps = verdict["source_maps"]
    lines.append(
        "  source maps                        {:>7}  {:>11}  gating={}".format(
            maps["entries"], maps["bytes"], "yes" if maps["gating"] else "no"
        )
    )
    return lines


def _render(manifest: dict[str, Any], verdict: dict[str, Any], *, listing: bool) -> str:
    out: list[str] = []
    out.append(f"bundle_manifest: {manifest['artifact']}")
    out.append(f"  sha256        {manifest['sha256']}")
    out.append(
        "  zipped        {} ({})".format(manifest["bytes_zipped"], _mb(manifest["bytes_zipped"]))
    )
    out.append(
        "  unzipped      {} ({})".format(
            manifest["bytes_unzipped"], _mb(manifest["bytes_unzipped"])
        )
    )
    out.append(f"  entries       {manifest['entry_count']}")
    out.append("")
    out.append("  top-level                          entries        bytes")
    out.append("  " + "-" * 60)
    for name, row in manifest["top_level"].items():
        out.append(f"  {name:<34} {row['entries']:>7}  {row['bytes']:>11}")
    out.append("")
    out.append("  required root                      present     entries")
    out.append("  " + "-" * 60)
    for row in verdict["required_roots"]:
        mark = "yes" if row["present"] else "NO"
        out.append(f"  {row['root']:<34} {mark:>7}  {row['entries']:>11}")
    out.append("")
    out.extend(_gate_lines(verdict))

    out.append("")
    out.append("  limit          measured        ceiling   ok")
    out.append("  " + "-" * 60)
    for row in verdict["limits"]:
        out.append(
            "  {:<13} {:>12}  {:>12}   {}".format(
                row["limit"], row["measured"], row["ceiling"], "yes" if row["ok"] else "NO"
            )
        )
    out.append("")
    flags = " ".join(
        f"{name}={'yes' if ok else 'NO'}" for name, ok in sorted(verdict["determinism"].items())
    )
    out.append(f"  determinism   {flags}")
    if verdict["strict"]:
        out.append("  determinism is GATING (--strict)")

    shape = manifest["web_shape"]
    if shape["entries"]:
        out.append("")
        out.append(f"  served tree ({shape['root']})            entries        bytes")
        out.append("  " + "-" * 60)
        out.append(
            "  {:<34} {:>7}  {:>11}".format(
                "identity", shape["identity"]["entries"], shape["identity"]["bytes"]
            )
        )
        out.append(
            "  {:<34} {:>7}  {:>11}".format(
                "pre-compressed .gz siblings", shape["gz"]["entries"], shape["gz"]["bytes"]
            )
        )
        out.append(
            "  {:<34} {:>7}  {:>11}".format(
                "of which source maps",
                shape["source_maps"]["entries"],
                shape["source_maps"]["bytes"],
            )
        )
        for label, key in (
            ("largest identity", "largest_identity_object"),
            ("largest gz", "largest_gz_object"),
        ):
            row = shape[key]
            if row:
                out.append(f"  {label:<34} {row['bytes']:>20}  {row['path']}")
        out.append(
            "  {:<34} {:>20}  (threshold {})".format(
                "gz objects above the threshold",
                shape["gz"]["above_large_object"],
                shape["gz"]["large_object_threshold"],
            )
        )
        # Not refusals. A finding here means the served tree costs more than it should,
        # which is a bill, not a broken package — see this module's docstring.
        for label, key in (
            ("compressible, NO .gz sibling", "compressible_without_sibling"),
            (".gz with NO identity twin", "gz_without_identity"),
        ):
            rows = shape[key]
            if rows:
                out.append(f"  {label:<34} {len(rows):>20}  e.g. {rows[0]}")

    if listing:
        out.append("")
        out.append("  " + "sha256".ljust(64) + "        bytes  path")
        out.append("  " + "-" * 100)
        for entry in manifest["entries"]:
            out.append(
                "  {:<64} {:>12}  {}".format(
                    entry.get("sha256", "-" * 64), entry["bytes"], entry["path"]
                )
            )

    out.append("")
    for line in verdict["refusals"]:
        out.append(f"  {line}")
    out.append(f"  VERDICT {verdict['verdict']}")
    return "\n".join(out)


# ── Entry point ─────────────────────────────────────────────────────────────────────


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bundle_manifest.py",
        description=(
            "Manifest and check a MAINLINE demo-api Lambda deployment zip, reading only "
            "the zip. Exits 2 when a required root is missing or a Lambda size limit is "
            "exceeded."
        ),
    )
    parser.add_argument("zip", help="path to the deployment package")
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        metavar="PATH",
        help="also write the full manifest, per entry, to this file",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print every entry with its size and sha256 (long)",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        metavar="ROOT",
        help=(
            "an additional required entry. A trailing / means 'at least one entry under "
            "this prefix'. Repeatable. The four D1 roots are always required."
        ),
    )
    parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        metavar="ROOT",
        help=(
            "an additional import root this package must not contain. Matches ROOT/ and "
            "top-level ROOT.py|.pyc|.pyd|.so. Repeatable. The twelve roots the pyproject "
            "declares absent are always forbidden and need no flag."
        ),
    )
    parser.add_argument(
        "--forbid-source-maps",
        action="store_true",
        help=(
            "also refuse when web/**/*.map is present. A flag rather than a default "
            "because build_lambda --keep-source-maps is a legitimate debug build."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also refuse when a determinism property of the archive is false",
    )
    parser.add_argument(
        "--max-zipped-mb",
        type=float,
        default=LAMBDA_MAX_ZIPPED_BYTES / 1048576.0,
        help="override the 50 MB zipped ceiling (for testing the ratchet)",
    )
    parser.add_argument(
        "--max-unzipped-mb",
        type=float,
        default=LAMBDA_MAX_UNZIPPED_BYTES / 1048576.0,
        help="override the 250 MB unzipped ceiling (for testing the ratchet)",
    )
    parser.add_argument(
        "--no-entry-hashes",
        action="store_true",
        help="skip per-entry sha256 (the zip's own sha256 is still computed)",
    )
    parser.add_argument("--quiet", action="store_true", help="print only the verdict line")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        if not zipfile.is_zipfile(args.zip):
            sys.stderr.write(f"bundle_manifest: not a zip file: {args.zip}\n")
            return 1
        manifest = describe(args.zip, hash_entries=not args.no_entry_hashes)
    except FileNotFoundError:
        sys.stderr.write(f"bundle_manifest: no such file: {args.zip}\n")
        return 1
    except (OSError, zipfile.BadZipFile) as exc:
        sys.stderr.write(f"bundle_manifest: cannot read {args.zip}: {exc}\n")
        return 1

    required = tuple(DEFAULT_REQUIRED) + tuple(
        item for item in args.require if item not in DEFAULT_REQUIRED
    )
    forbidden = tuple(DEFAULT_FORBIDDEN) + tuple(
        item for item in args.forbid if item not in DEFAULT_FORBIDDEN
    )
    verdict = check(
        manifest,
        required=required,
        forbidden=forbidden,
        forbid_source_maps=args.forbid_source_maps,
        strict=args.strict,
        max_zipped=int(args.max_zipped_mb * 1048576),
        max_unzipped=int(args.max_unzipped_mb * 1048576),
    )

    if args.json_path:
        payload = dict(manifest)
        payload["check"] = {key: value for key, value in verdict.items() if key != "entries"}
        with Path(args.json_path).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    if args.quiet:
        for line in verdict["refusals"]:
            sys.stderr.write(line + "\n")
        print(
            "bundle_manifest: {} sha256={} zipped={} unzipped={} entries={} VERDICT {}".format(
                manifest["artifact"],
                manifest["sha256"],
                manifest["bytes_zipped"],
                manifest["bytes_unzipped"],
                manifest["entry_count"],
                verdict["verdict"],
            )
        )
    else:
        print(_render(manifest, verdict, listing=args.list))

    return 0 if verdict["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
