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

**Size limits** (gating, always). Lambda refuses a direct upload over **50 MB zipped**
and refuses to unpack over **250 MB**. Both ceilings are AWS's, both are checked here
against the real numbers rather than assumed from a build that fitted last week.

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

EXIT CODES
----------
====  ============================================================================
0     every gating check passed
2     a required root is missing, a size limit is exceeded, or ``--strict`` and a
      determinism property failed
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
    "DEFAULT_REQUIRED",
    "EPOCH",
    "LAMBDA_MAX_UNZIPPED_BYTES",
    "LAMBDA_MAX_ZIPPED_BYTES",
    "check",
    "describe",
    "main",
]

#: The four roots the D1 single-origin demo cannot be served without. A trailing ``/``
#: means "at least one entry under this prefix"; anything else is an exact entry name.
DEFAULT_REQUIRED: tuple[str, ...] = (
    "mainline_demo_api/",
    "psycopg/",
    "web/index.html",
    "web/bundle/",
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
        "entries": entries,
    }


def _zip_size(path: str) -> int:
    return Path(path).stat().st_size


# ── Deciding ────────────────────────────────────────────────────────────────────────


def check(
    manifest: dict[str, Any],
    *,
    required: tuple[str, ...] = DEFAULT_REQUIRED,
    strict: bool = False,
    max_zipped: int = LAMBDA_MAX_ZIPPED_BYTES,
    max_unzipped: int = LAMBDA_MAX_UNZIPPED_BYTES,
) -> dict[str, Any]:
    """Turn a manifest into a verdict. Pure: takes a dict, returns a dict."""
    names = [entry["path"] for entry in manifest["entries"]]
    name_set = set(names)

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
    verdict = check(
        manifest,
        required=required,
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
