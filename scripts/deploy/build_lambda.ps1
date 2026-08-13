#!/usr/bin/env pwsh
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#Requires -Version 7.0

<#
.SYNOPSIS
    Build the deterministic deployment package for the MAINLINE demo API Lambda.

.DESCRIPTION
    Windows twin of scripts/deploy/build_lambda.sh. The two produce a BYTE-IDENTICAL zip
    from the same tree, because the staging, pruning and packing are done by the same
    embedded Python program in both -- and both print that program's sha256, so "the
    same program" is a hash you can compare rather than a claim you have to trust.

    WHAT IS IN THE PACKAGE, AND WHY IT IS FOUR THINGS NOW
    Decision D1 (docs/leads/ship-final.md sec 1.4) made the demo URL a public Lambda
    Function URL rather than CloudFront, because this AWS account cannot create a
    distribution. One origin therefore serves the console SPA, the evidence bundle and
    /v1/*, and this zip is that whole origin:

        mainline_demo_api/   the handler package, copied from the vertical
        psycopg/             the pure-Python driver               (py3-none-any wheel)
        psycopg_binary/      the compiled libpq bindings          (manylinux wheel)
        web/                 verticals/mainline/apps/console/dist/   -- the website
        web/bundle/          .../console/fixtures/bundles/demo-cloud -- the EvidenceBundle

    No boto3 (the runtime has one and db.py signs its single SSM call itself), no web
    framework, no tzdata, no __pycache__, no RECORD.

    WHY THE PACKAGE MUST BE REPRODUCIBLE
    Terraform decides whether to redeploy from `source_code_hash =
    filebase64sha256(var.package_path)`. A zip whose bytes move because the clock moved
    makes every `terraform plan` show a Lambda update, which trains an operator to skim
    the plan four days before a deadline. Fixed entry timestamps (the DOS epoch), sorted
    entry order, a fixed compression level and a fixed file mode make the hash a
    statement about the CONTENT. Two builds of the same tree print the same sha256;
    evidence/deploy/lambda-bundle.json records both.

    SOURCE MAPS ARE STRIPPED BY DEFAULT, AND THE SERVED TREE SHIPS PRE-COMPRESSED
    This file used to argue that web/assets/*.js.map should stay, so a judge who opens
    DevTools on the demo sees real component names instead of
    `surface-Bv8EMlU6.js:1:20481`. That argument was sound while the package was a thing
    an operator downloaded. It stopped being sound the moment the same tree went behind a
    Lambda Function URL with `authorization_type = NONE`: every byte under web/ is then
    egress any caller on the internet can bill to this account at will, and the maps are
    18 files, 2,586,960 B -- 72.42 % of the 3,571,990 B served tree (measured
    2026-08-13) -- for a debugging convenience nobody has used on the deployed URL.
    -KeepSourceMaps builds the debuggable package on demand; the default builds the one
    that gets deployed.

    The same build writes a `<name>.gz` sibling beside every compressible web/** entry:
    gzip level 9, mtime 0, no filename in the gzip header, so the zip stays
    byte-reproducible. 289,312 B of siblings against 2,586,960 B removed, and the largest
    object the handler can put on the wire falls from 1,554,168 B to 433,396 B identity /
    124,127 B gzipped. That is interface I1 of docs/leads/cost-bound-plan.md; the serving
    half -- content negotiation, and a 404 for a direct request to a .gz path, because one
    set of bytes must not have two names -- belongs to static_site.py, not to this script.

    PLATFORM TAGS ARE MEASURED PER ARCHITECTURE, NOT GUESSED (2026-08-10, this machine):

        --platform manylinux2014_x86_64   ->  psycopg_binary-3.3.4-cp313-cp313-
                                              manylinux2014_x86_64.manylinux_2_17_x86_64.whl
        --platform manylinux2014_aarch64  ->  ERROR: no matching distribution
                                              (aarch64 stops at 3.2.13 for that tag)
        --platform manylinux_2_28_aarch64 ->  psycopg_binary-3.3.4-cp313-cp313-
                                              manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl

    So the arm64 build asks for glibc 2.28, not 2.17. Lambda's python3.13 runtime is
    Amazon Linux 2023, glibc 2.34, which satisfies it. infra/modules/demo-api/README.md
    carries the same table and the container proof.

.PARAMETER Arch
    `arm64` (default) or `x86_64`. Must match the Terraform module's `architecture`.

.PARAMETER Out
    Output zip path. Defaults to `<repo>/out/lambda/mainline-demo-api-<arch>.zip`.
    `out/` is in .gitignore; `build/` is not, which is why this is not `build/`.

.PARAMETER Python
    Interpreter used for `-m pip`. Defaults to the repository virtualenv
    (.venv/Scripts/python.exe on Windows, .venv/bin/python elsewhere), then `python`.
    `uv` is deliberately not used: it is not installed on the build machine.

.PARAMETER PsycopgVersion
    Version pinned for BOTH `psycopg` and `psycopg-binary`. Defaults to 3.3.4, which is
    what verticals/mainline/apps/demo-api/pyproject.toml pins.

.PARAMETER Platform
    Override the pip platform tag. Empty means "use the measured tag for -Arch".

.PARAMETER Wheelhouse
    Wheel cache directory. Defaults to `<out dir>/wheels-<arch>`. Reused when it already
    holds both pinned wheels, which makes a rebuild offline-repeatable.

.PARAMETER RefreshWheels
    Re-download the wheels even when the wheelhouse already holds them.

.PARAMETER KeepSourceMaps
    KEEP web/**/*.map (18 files, 2,586,960 B, 72.42 % of the served tree). Stripped by
    default, because that tree is served from a public Function URL and every byte of it
    is billable egress. Use this to build a package whose stack traces map in DevTools.

.PARAMETER StripSourceMaps
    Accepted, and already the default; kept so a command line recorded before 2026-08-13
    still runs. It is not silently ignored -- it says so.

.PARAMETER KeepStage
    Leave the staging tree and the extracted packer in place for inspection.

.EXAMPLE
    pwsh scripts/deploy/build_lambda.ps1
    pwsh scripts/deploy/build_lambda.ps1 -Arch x86_64
    pwsh scripts/deploy/build_lambda.ps1 -KeepSourceMaps -KeepStage
#>

[CmdletBinding()]
param(
    [ValidateSet('arm64', 'x86_64')]
    [string]$Arch = 'arm64',

    [string]$Out = '',

    [string]$Python = '',

    [string]$PsycopgVersion = '3.3.4',

    [string]$Platform = '',

    [string]$Wheelhouse = '',

    [switch]$RefreshWheels,

    [switch]$KeepSourceMaps,

    [switch]$StripSourceMaps,

    [switch]$KeepStage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Native exit codes are checked BY HAND after every call below, and this is why the
# automatic version is turned off: two of those calls -- the wheelhouse probe and the
# pip download that may legitimately fail on a machine with no network -- return
# non-zero as INFORMATION. With $PSNativeCommandUseErrorActionPreference = $true they
# would throw, and an offline rebuild that should succeed from the wheelhouse would die
# with a stack trace instead.
$PSNativeCommandUseErrorActionPreference = $false

$PythonVersion = '3.13'

function Fail([string]$Message) {
    Write-Host "build_lambda: $Message" -ForegroundColor Red
    exit 1
}

function Step([string]$Message) {
    Write-Host "build_lambda: $Message"
}

# ---------------------------------------------------------------------------------
# 1. Locate the repository, the interpreter and the four inputs
# ---------------------------------------------------------------------------------

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
$SourcePkg = Join-Path $RepoRoot 'verticals/mainline/apps/demo-api/src/mainline_demo_api'
$ConsoleDist = Join-Path $RepoRoot 'verticals/mainline/apps/console/dist'
$EvidenceBundle = Join-Path $RepoRoot 'verticals/mainline/apps/console/fixtures/bundles/demo-cloud'
$ManifestTool = Join-Path $RepoRoot 'scripts/deploy/bundle_manifest.py'

if ([string]::IsNullOrWhiteSpace($Python)) {
    $candidates = @(
        (Join-Path $RepoRoot '.venv/Scripts/python.exe'),
        (Join-Path $RepoRoot '.venv/bin/python')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { $Python = $candidate; break }
    }
    if ([string]::IsNullOrWhiteSpace($Python)) {
        $found = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $found) { $found = Get-Command python3 -ErrorAction SilentlyContinue }
        if ($null -eq $found) { Fail 'no interpreter: pass -Python, or create the repo .venv' }
        $Python = $found.Source
    }
}
if (-not (Test-Path -LiteralPath $Python)) { Fail "interpreter not found: $Python" }

# The platform tag is a measured fact per architecture, not a template. See the comment
# block at the top of this file for the pip transcript that produced each one.
if ([string]::IsNullOrWhiteSpace($Platform)) {
    $Platform = if ($Arch -eq 'arm64') { 'manylinux_2_28_aarch64' } else { 'manylinux2014_x86_64' }
}

if ([string]::IsNullOrWhiteSpace($Out)) {
    $Out = Join-Path $RepoRoot "out/lambda/mainline-demo-api-$Arch.zip"
}
$OutDir = Split-Path -Parent $Out
if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path
$Out = Join-Path $OutDir (Split-Path -Leaf $Out)

$Stage = Join-Path $OutDir "stage-$Arch"
if ([string]::IsNullOrWhiteSpace($Wheelhouse)) {
    $Wheelhouse = Join-Path $OutDir "wheels-$Arch"
}

# Recorded verbatim in the sidecar manifest, and reconstructed rather than echoed: an
# absolute D:\... path in a tracked artefact is an `abs_windows_path` finding in
# scripts/submission/audit_public_readiness.py, and this manifest is quoted in
# evidence/deploy/lambda-bundle.json.
$CommandLine = "scripts/deploy/build_lambda.ps1 -Arch $Arch"
if ($KeepSourceMaps) { $CommandLine += ' -KeepSourceMaps' }
if ($RefreshWheels) { $CommandLine += ' -RefreshWheels' }

# Stripping is the default as of 2026-08-13. -StripSourceMaps is not silently ignored:
# it says so, because a flag that quietly does nothing is how an operator comes to
# believe a build did something it did not.
if ($StripSourceMaps) {
    Step 'note      -StripSourceMaps is the default now; -KeepSourceMaps is the opt-out'
}

# `pip --version` is NOT used: it prints the absolute path of the pip package, which
# would put a D:\... path into a tracked evidence file.
$PythonReport = & $Python -c 'import platform;print("%s %s"%(platform.python_implementation(),platform.python_version()))'
if ($LASTEXITCODE -ne 0) { Fail 'could not ask the interpreter for its version' }
$PipReport = & $Python -c 'import importlib.metadata as m;print("pip "+m.version("pip"))'
if ($LASTEXITCODE -ne 0) { Fail 'could not ask the interpreter for its pip version' }

Step "repo      $RepoRoot"
Step "python    $Python ($PythonReport, $PipReport)"
Step "arch      $Arch"
Step "platform  $Platform"
Step "psycopg   $PsycopgVersion"
Step "console   $ConsoleDist"
Step "bundle    $EvidenceBundle"
Step "out       $Out"

# ---------------------------------------------------------------------------------
# 2. Extract the packer
# ---------------------------------------------------------------------------------
#
# The packer is embedded rather than shipped as a third file because this worker owns
# exactly two build scripts, and because a shared helper that one of them could load and
# the other could not is a reproducibility bug waiting to happen. build_lambda.sh
# carries a byte-identical copy. Both normalise it to LF and append exactly one trailing
# newline before writing -- a here-string drops the final newline and a heredoc keeps it
# -- and both print its sha256, so a drift between the two scripts is one line of output
# apart rather than a subtle difference in an artefact.

$Packer = @'
"""Stage, prune and pack the MAINLINE demo-api Lambda package, reproducibly.

Embedded BYTE-IDENTICALLY in scripts/deploy/build_lambda.sh and build_lambda.ps1. Both
extract it, normalise every line ending to LF, print its sha256 and run it with the same
arguments -- so "the two builders agree" is a hash a reader can compare rather than a
claim. This text is deliberately ASCII-only: a smart quote would be one byte in one
extraction and two in the other, and the equality proof would be about encodings.

Nothing here reads the environment, consults a clock, or resolves the repository layout.
Every input is a path handed in by the wrapper, so two runs that differ only in WHEN they
happened cannot differ in WHAT they produce.

WHAT THE WEB TREE COSTS, AND WHY THIS PROGRAM SHAPES IT
-------------------------------------------------------
Under decision D1 this zip is the whole public origin, reached through a Lambda Function
URL whose authorization_type is NONE. Every byte under web/ is therefore egress that any
caller on the internet can bill to this account at will, and the served tree is the only
place a build can bound it. Two mechanisms, both here:

  * source maps are STRIPPED by default (--keep-source-maps builds the debuggable
    package). Measured 2026-08-13: 18 files, 2,586,960 B, 72.42 % of a 3,571,990 B tree,
    for a debugging convenience that is worth having on a laptop and is not worth
    publishing on an unauthenticated URL;
  * every compressible web/** entry gets a <name>.gz sibling at level 9. Measured on the
    same tree: 289,312 B of siblings against 2,586,960 B removed, and the largest object
    the handler can put on the wire falls from 1,554,168 B to 433,396 B identity /
    124,127 B gzipped.

Interface I1 in docs/leads/cost-bound-plan.md sec 2 fixes the contract this half of it
implements: the sibling carries no filename in its gzip header and mtime 0, so the zip
stays byte-reproducible; static_site.py owns serving it, and owes a 404 on a direct
request for a path ending .gz, because one set of bytes must not have two names.

Three modes:
  --mode preflight   refuse, before pip runs, if an input the package needs is absent
  --mode wheelcheck  say whether a wheelhouse already holds both pinned wheels
  --mode build       copy, prune, strip, pre-compress, pack, hash, gate on size, write
                     the sidecar manifest
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
import zlib

EPOCH = (1980, 1, 1, 0, 0, 0)
COMPRESSLEVEL = 9
MODE_EXEC = 0o755
MODE_FILE = 0o644
LAMBDA_MAX_ZIPPED = 50 * 1024 * 1024
LAMBDA_MAX_UNZIPPED = 250 * 1024 * 1024

# Suffix -> does a second compression pass buy anything. Held in step with
# static_site.MEDIA_TYPES: exactly the entries that table marks as text, JavaScript,
# JSON, SVG or wasm. The image and font types it also names -- .png .jpg .jpeg .webp
# .ico .woff .woff2 -- are already-compressed containers, and a .gz beside one of those
# costs package bytes, costs build time and saves nothing on the wire.
COMPRESSIBLE_SUFFIXES = (
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
GZ_SUFFIX = ".gz"

# Reported, not enforced. A gzipped object above this is the one a wire ceiling has to
# be chosen around, so the count belongs in the manifest where W3's ceiling test and
# W7's cost model can both read it instead of re-deriving it.
GZ_LARGE_OBJECT = 64 * 1024

PNPM_BUILD = (
    "cd verticals/mainline/apps/console && pnpm install --frozen-lockfile && "
    "pnpm exec vite build --mode demo"
)
CAPTURE_BUNDLE = (
    "python scripts/deploy/capture_demo_bundle.py "
    "(the last capture is recorded in evidence/deploy/bundle-capture.json)"
)

ASSET_REF = re.compile(r'(?:src|href)="\./(assets/[^"?#]+)')
ENV_LITERAL = re.compile(r'(VITE_MAINLINE_[A-Z_]+):"((?:[^"\\]|\\.)*)"')
ENV_MODE = re.compile(r'MODE:"([^"]*)"')

refusals = []


def refuse(code, message):
    refusals.append("REFUSED [%s] %s" % (code, message))


def say(message):
    sys.stdout.write("build_lambda: %s\n" % message)


def need(args, names):
    for name in names:
        if not getattr(args, name):
            sys.stderr.write("build_lambda: --%s is required in this mode\n" % name.replace("_", "-"))
            raise SystemExit(1)


# -- mode: preflight ----------------------------------------------------------------


def preflight(args):
    """Everything knowable before pip runs. Cheap, and every refusal names its fix."""
    app = os.path.join(args.source_pkg, "app.py")
    if not os.path.isfile(app):
        refuse(
            "NO HANDLER",
            "%s is missing. mainline_demo_api.app.handler is the Lambda entry point; "
            "without app.py every invocation is an import error." % app,
        )

    index = os.path.join(args.dist, "index.html")
    if not os.path.isdir(args.dist):
        refuse(
            "NO CONSOLE",
            "%s does not exist. Under decision D1 this Lambda IS the website, so a "
            "package built without it is a demo URL that answers 503 at /. Build it "
            "with:  %s" % (args.dist, PNPM_BUILD),
        )
    elif not os.path.isfile(index):
        refuse(
            "NO CONSOLE",
            "%s exists but holds no index.html, so it is not a built site. Build it "
            "with:  %s" % (args.dist, PNPM_BUILD),
        )
    else:
        # A dist/ whose index.html names an asset that is not beside it is a white page
        # with a console error, and it passes every check that only looks for index.html.
        handle = open(index, "r", encoding="utf-8", errors="replace")
        try:
            html = handle.read()
        finally:
            handle.close()
        for ref in sorted(set(ASSET_REF.findall(html))):
            if not os.path.isfile(os.path.join(args.dist, ref.replace("/", os.sep))):
                refuse(
                    "STALE CONSOLE",
                    "%s references ./%s, which is not in dist/. That tree is a partial "
                    "or interrupted build. Rebuild it with:  %s" % (index, ref, PNPM_BUILD),
                )

    if os.path.isdir(os.path.join(args.dist, "bundle")):
        refuse(
            "BUNDLE COLLISION",
            "%s already contains bundle/, and this build writes the EvidenceBundle to "
            "web/bundle/. Two trees cannot own one path." % args.dist,
        )

    if not os.path.isdir(args.bundle):
        refuse(
            "NO EVIDENCE BUNDLE",
            "%s does not exist. It is the console's REPLAY source and the demo's answer "
            "when the database is unreachable. Capture it with:  %s"
            % (args.bundle, CAPTURE_BUNDLE),
        )
    elif not os.path.isfile(os.path.join(args.bundle, "manifest.json")):
        refuse(
            "NO EVIDENCE BUNDLE",
            "%s holds no manifest.json, so it is not a sealed bundle. Capture it with:  %s"
            % (args.bundle, CAPTURE_BUNDLE),
        )


# -- mode: wheelcheck ---------------------------------------------------------------


def wheel_names(wheelhouse):
    if not wheelhouse or not os.path.isdir(wheelhouse):
        return []
    return sorted(name for name in os.listdir(wheelhouse) if name.endswith(".whl"))


def wheelcheck(args):
    """Exit 0 when the wheelhouse already holds both pinned wheels, 3 when it does not.

    The wrapper uses the exit code to decide whether to reach for the network. A build
    on a machine that has run once before is therefore offline-repeatable, and the
    wheels it reuses are hashed into the manifest, so "offline" is never "unknown".
    """
    names = wheel_names(args.wheelhouse)
    version = args.psycopg_version
    have_pure = any(name.startswith("psycopg-%s-" % version) for name in names)
    have_binary = any(name.startswith("psycopg_binary-%s-" % version) for name in names)
    for name in names:
        say("wheel     %s" % name)
    if have_pure and have_binary:
        return 0
    say(
        "wheelhouse %s lacks psycopg==%s and/or psycopg-binary==%s"
        % (args.wheelhouse, version, version)
    )
    return 3


# -- mode: build --------------------------------------------------------------------


def prune(stage):
    """Delete what must not ship, and return the sorted list for the manifest.

    Path-scoped on purpose. A blanket "delete every file called RECORD" would reach into
    web/bundle/, a sealed tree this build does not own and must not change the meaning of.
    """
    removed = []

    def rel(path):
        return os.path.relpath(path, stage).replace(os.sep, "/")

    for dirpath, dirnames, filenames in os.walk(stage, topdown=True):
        parent = os.path.basename(dirpath)
        for name in sorted(list(dirnames)):
            full = os.path.join(dirpath, name)
            drop = name == "__pycache__"
            # tzdata is a psycopg extra this package does not install (--no-deps) and
            # does not need: the runtime carries zoneinfo and the demo speaks UTC.
            drop = drop or (name == "tzdata" and os.path.dirname(full) == stage)
            if drop:
                shutil.rmtree(full)
                removed.append(rel(full) + "/")
                dirnames.remove(name)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            # A .pyc carries the source mtime in its header and would move the zip hash
            # on a machine that byte-compiled at a different second.
            drop = name.endswith(".pyc") or name.endswith(".pyo")
            # RECORD is a per-file hash list pip regenerates on every install and Lambda
            # never reads; INSTALLER, REQUESTED and direct_url.json are pip bookkeeping.
            drop = drop or (
                parent.endswith(".dist-info")
                and name in ("RECORD", "INSTALLER", "REQUESTED", "direct_url.json")
            )
            if drop:
                os.remove(full)
                removed.append(rel(full))

    return sorted(removed)


def web_files(stage):
    """Every file under web/, as (repo-style relative path, absolute path), byte-sorted."""
    rows = []
    web = os.path.join(stage, "web")
    if not os.path.isdir(web):
        return rows
    for dirpath, dirnames, filenames in os.walk(web):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rows.append((os.path.relpath(full, stage).replace(os.sep, "/"), full))
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    return rows


def web_census(stage):
    """Entries and bytes under web/. The number every cost figure starts from."""
    rows = web_files(stage)
    return {"entries": len(rows), "bytes": sum(os.path.getsize(full) for _rel, full in rows)}


def largest_web(stage, want_gz):
    """The biggest object under web/ that the handler could put on the wire.

    A .gz sibling and its identity twin are two names for one set of bytes, and under
    interface I1 a direct request for a path ending .gz is a 404 -- the sibling is
    reachable only through content negotiation. So the two are measured apart: the
    identity number bounds a caller that sent no accept-encoding, the gz number bounds
    every modern browser, and a wire ceiling has to be chosen against both.
    """
    best = None
    for rel, full in web_files(stage):
        if rel.endswith(GZ_SUFFIX) != want_gz:
            continue
        size = os.path.getsize(full)
        if best is None or size > best["bytes"]:
            best = {"path": rel, "bytes": size}
    return best


def strip_maps(stage):
    """Remove web/**/*.map. The DEFAULT; --keep-source-maps opts out."""
    removed = []
    web = os.path.join(stage, "web")
    for dirpath, _dirnames, filenames in os.walk(web):
        for name in sorted(filenames):
            if name.endswith(".map"):
                full = os.path.join(dirpath, name)
                os.remove(full)
                removed.append(os.path.relpath(full, stage).replace(os.sep, "/"))
    return sorted(removed)


def gzip_bytes(data):
    """Level-9 gzip with every field a writer could take from its surroundings pinned.

    NOT gzip.compress. That helper writes the OS byte of the zlib the interpreter was
    linked against and, on older interpreters, the current clock into MTIME -- so the
    same input would produce different files on the Windows workstation and the Linux
    runner this project builds on, and the zip's sha256 would move for a reason that is
    not content. The container is therefore written out by hand:

        1f 8b   magic
        08      deflate
        00      flags: NO FNAME. The name is the zip entry's job, and a filename in the
                header would carry a staging path into a tracked artefact.
        00 x4   MTIME 0. There is no clock in this program.
        02      XFL: the compressor used maximum compression.
        ff      OS: unknown, on purpose -- 03 (Unix) or 0b (Windows) would make the
                artefact a statement about the machine that built it.

    then the raw deflate stream, then CRC32 and ISIZE little-endian, which is what RFC
    1952 sec 2.2 specifies and what every gzip reader checks.
    """
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    body = compressor.compress(data) + compressor.flush()
    return (
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
        + body
        + (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "little")
        + (len(data) & 0xFFFFFFFF).to_bytes(4, "little")
    )


def gzip_siblings(stage):
    """Write <name>.gz beside every compressible web/** entry. Interface I1.

    The whole served tree is pre-compressed at build time rather than per request for
    two reasons that are both measured: gzipping the 433,396 B asset in the handler costs
    25.9 ms at level 9 on the build workstation, which is charged to every request and
    to the invocation duration the cost model turns on; and a build-time sibling can be
    level 9 for free, where a request-time compressor has to be level 6 to be affordable.

    The listing is taken BEFORE anything is written, so this walks a tree it is not also
    growing, and its output cannot depend on whether a filesystem reports a file created
    mid-walk.
    """
    written = []
    for rel, full in web_files(stage):
        if rel.endswith(GZ_SUFFIX):
            # Under I1 the handler 404s a direct request for a .gz path and serves the
            # sibling only through content negotiation. A .gz that arrived in dist/ has
            # no identity twin this build can vouch for, so refusing beats guessing.
            refuse(
                "GZ COLLISION",
                "%s is already a .gz. This build writes the pre-compressed siblings and "
                "interface I1 gives them no name of their own; a .gz that came from the "
                "console build would be one set of bytes with two names. Remove it from "
                "dist/, or from the evidence bundle, and rebuild." % rel,
            )
            continue
        if os.path.splitext(rel)[1].lower() not in COMPRESSIBLE_SUFFIXES:
            continue
        handle = open(full, "rb")
        try:
            data = handle.read()
        finally:
            handle.close()
        blob = gzip_bytes(data)
        handle = open(full + GZ_SUFFIX, "wb")
        try:
            handle.write(blob)
        finally:
            handle.close()
        written.append(
            {
                "source": rel,
                "sibling": rel + GZ_SUFFIX,
                "bytes": len(data),
                "gz_bytes": len(blob),
            }
        )
    written.sort(key=lambda row: row["sibling"].encode("utf-8"))
    return written


def probe_console(stage):
    """Report which build-time source variables the console artefact actually carries.

    Vite inlines import.meta.env as an object literal and the console's
    src/app/source-select.ts reads exactly two keys off it. With neither key set, the
    console renders its NO SOURCE panel on every surface: a site that loads, is honest,
    and shows nothing. That is a console-build fact and not a packaging fact, so this
    reports it loudly and does not refuse -- this program does not own dist/.

    Only *.js is read, so the *.js.gz siblings written beside them are not scanned twice
    and are not read as text.
    """
    found = {}
    modes = set()
    assets = os.path.join(stage, "web", "assets")
    if not os.path.isdir(assets):
        return {"configured": {}, "mode": None, "scanned": 0, "note": "no web/assets directory"}
    scanned = 0
    for name in sorted(os.listdir(assets)):
        if not name.endswith(".js"):
            continue
        scanned += 1
        handle = open(os.path.join(assets, name), "r", encoding="utf-8", errors="replace")
        try:
            text = handle.read()
        finally:
            handle.close()
        for key, value in ENV_LITERAL.findall(text):
            found.setdefault(key, value)
        modes.update(ENV_MODE.findall(text))
    return {
        "configured": found,
        "mode": sorted(modes)[0] if modes else None,
        "scanned": scanned,
        "note": (
            "VITE_MAINLINE_API_BASE selects the LIVE source, VITE_MAINLINE_BUNDLE_URL the "
            "REPLAY source; with neither compiled in, every console surface renders NO SOURCE."
        ),
    }


def pack(stage, out):
    """Write the zip. Every field a writer could take from the environment is fixed."""
    entries = []
    for dirpath, dirnames, filenames in os.walk(stage):
        dirnames.sort()
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, stage).replace(os.sep, "/")
            entries.append((rel, full))
    # Sort on the UTF-8 bytes of the relative path: the one ordering that does not depend
    # on the filesystem's readdir order, which differs between NTFS and ext4.
    entries.sort(key=lambda item: item[0].encode("utf-8"))

    if os.path.exists(out):
        os.remove(out)

    unzipped = 0
    archive = zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=COMPRESSLEVEL)
    try:
        for rel, full in entries:
            handle = open(full, "rb")
            try:
                data = handle.read()
            finally:
                handle.close()
            unzipped += len(data)
            info = zipfile.ZipInfo(rel, date_time=EPOCH)
            info.create_system = 3  # Unix, so external_attr is read as a mode
            base = rel.rsplit("/", 1)[-1]
            executable = ".so" in base or base.endswith(".dylib")
            info.external_attr = (MODE_EXEC if executable else MODE_FILE) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    finally:
        archive.close()

    return entries, unzipped


def sha256_file(path):
    digest = hashlib.sha256()
    handle = open(path, "rb")
    try:
        block = handle.read(1 << 20)
        while block:
            digest.update(block)
            block = handle.read(1 << 20)
    finally:
        handle.close()
    return digest.hexdigest()


def wheels_of(wheelhouse):
    rows = []
    for name in wheel_names(wheelhouse):
        full = os.path.join(wheelhouse, name)
        rows.append({"wheel": name, "bytes": os.path.getsize(full), "sha256": sha256_file(full)})
    return rows


def build(args):
    stage = args.stage
    say("stage     %s" % stage)
    say("copy      %s -> mainline_demo_api/" % args.source_pkg)
    shutil.copytree(args.source_pkg, os.path.join(stage, "mainline_demo_api"))
    say("copy      %s -> web/" % args.dist)
    shutil.copytree(args.dist, os.path.join(stage, "web"))
    say("copy      %s -> web/bundle/" % args.bundle)
    shutil.copytree(args.bundle, os.path.join(stage, "web", "bundle"))

    pruned = prune(stage)

    # The three censuses are taken from the staging tree at three moments, so the
    # sidecar can state what the two egress levers actually did on THIS tree rather than
    # repeat a figure someone measured once. evidence/deploy/cost/package-shape.json is
    # rebuilt from the finished zips and must agree with these.
    before = web_census(stage)
    stripped = [] if args.keep_source_maps else strip_maps(stage)
    after_strip = web_census(stage)
    siblings = gzip_siblings(stage)
    after_gzip = web_census(stage)

    # A zip missing one of these is a 502, or a blank page, at 03:00 rather than a failed
    # build at 15:00. The same five are re-checked from the finished zip by
    # scripts/deploy/bundle_manifest.py, which reads the artefact and not the tree.
    required = [
        "mainline_demo_api/app.py",
        "psycopg/__init__.py",
        "psycopg_binary/__init__.py",
        "web/index.html",
        "web/bundle/manifest.json",
    ]
    for name in required:
        if not os.path.exists(os.path.join(stage, *name.split("/"))):
            refuse("MISSING", "the staging tree holds no %s" % name)
    if refusals:
        return None

    shape = {
        "web_before": before,
        "web_after_strip": after_strip,
        "web_after_gzip_siblings": after_gzip,
        "source_maps_removed": {
            "entries": len(stripped),
            "bytes": before["bytes"] - after_strip["bytes"],
        },
        "gzip_siblings": {
            "entries": len(siblings),
            "bytes": sum(row["gz_bytes"] for row in siblings),
            "identity_bytes": sum(row["bytes"] for row in siblings),
            "above_large_object": sum(
                1 for row in siblings if row["gz_bytes"] > GZ_LARGE_OBJECT
            ),
            "large_object_threshold": GZ_LARGE_OBJECT,
        },
        "largest_identity_object": largest_web(stage, False),
        "largest_gz_object": largest_web(stage, True),
        "compressible_suffixes": list(COMPRESSIBLE_SUFFIXES),
        "note": (
            "web_before is the tree as the console build and the evidence bundle left it. "
            "largest_identity_object is what a caller that sent no accept-encoding can "
            "pull; largest_gz_object is what every modern browser pulls. Under interface "
            "I1 a direct request for a path ending .gz is a 404, so the two are the same "
            "bytes under one name."
        ),
    }

    console = probe_console(stage)
    entries, unzipped = pack(stage, args.out)
    zipped = os.path.getsize(args.out)
    digest = sha256_file(args.out)

    top = sorted(set(rel.split("/", 1)[0] for rel, _ in entries))
    layout = {}
    for rel, full in entries:
        head = rel.split("/", 1)[0]
        row = layout.setdefault(head, {"entries": 0, "bytes": 0})
        row["entries"] += 1
        row["bytes"] += os.path.getsize(full)

    manifest = {
        "artifact": os.path.basename(args.out),
        "sha256": digest,
        "architecture": args.arch,
        "platform_tag": args.platform_tag,
        "handler": "mainline_demo_api.app.handler",
        "runtime": "python3.13",
        "web_root": "/var/task/web",
        "files": len(entries),
        "bytes_zipped": zipped,
        "bytes_unzipped": unzipped,
        "top_level": top,
        "layout": layout,
        "distributions": sorted(name for name in top if name.endswith(".dist-info")),
        "pruned": pruned,
        "source_maps": "kept" if args.keep_source_maps else "stripped",
        "source_maps_stripped": stripped,
        "gzip_siblings": [row["sibling"] for row in siblings],
        "package_shape": shape,
        "console": console,
        "build": {
            "builder": args.builder,
            "command_line": args.command_line,
            "python": args.python_report,
            "pip": args.pip_report,
            "python_version_target": args.python_version,
            "psycopg_version": args.psycopg_version,
            "wheelhouse": os.path.basename(args.wheelhouse.rstrip("/\\")),
            "wheel_source": args.wheel_source,
            "wheels": wheels_of(args.wheelhouse),
            "packer_sha256": args.packer_sha256,
        },
        "limits": {
            "zipped_ceiling": LAMBDA_MAX_ZIPPED,
            "unzipped_ceiling": LAMBDA_MAX_UNZIPPED,
            "zipped_headroom": LAMBDA_MAX_ZIPPED - zipped,
            "unzipped_headroom": LAMBDA_MAX_UNZIPPED - unzipped,
        },
    }

    say("files     %d" % len(entries))
    for name in top:
        say("  %-30s %5d entries %11d bytes" % (name, layout[name]["entries"], layout[name]["bytes"]))
    say(
        "unzipped  %d bytes (%.2f MB) of %d (%d MB) allowed"
        % (unzipped, unzipped / 1048576.0, LAMBDA_MAX_UNZIPPED, LAMBDA_MAX_UNZIPPED // 1048576)
    )
    say(
        "zipped    %d bytes (%.2f MB) of %d (%d MB) allowed"
        % (zipped, zipped / 1048576.0, LAMBDA_MAX_ZIPPED, LAMBDA_MAX_ZIPPED // 1048576)
    )
    say("maps      %s" % manifest["source_maps"])
    say("web       %5d entries %10d bytes  as the console and the bundle left it"
        % (before["entries"], before["bytes"]))
    say("          %5d entries %10d bytes  after the source-map strip (-%d files, -%d bytes)"
        % (
            after_strip["entries"],
            after_strip["bytes"],
            shape["source_maps_removed"]["entries"],
            shape["source_maps_removed"]["bytes"],
        ))
    say("          %5d entries %10d bytes  with the .gz siblings (+%d files, +%d bytes)"
        % (
            after_gzip["entries"],
            after_gzip["bytes"],
            shape["gzip_siblings"]["entries"],
            shape["gzip_siblings"]["bytes"],
        ))
    if shape["largest_identity_object"]:
        say("wire      largest identity %10d bytes  %s"
            % (shape["largest_identity_object"]["bytes"], shape["largest_identity_object"]["path"]))
    if shape["largest_gz_object"]:
        say("          largest gzipped  %10d bytes  %s"
            % (shape["largest_gz_object"]["bytes"], shape["largest_gz_object"]["path"]))
    say("          %d gz object(s) above %d bytes" % (
        shape["gzip_siblings"]["above_large_object"], GZ_LARGE_OBJECT))
    if console["configured"]:
        pairs = sorted(console["configured"].items())
        say("console   %s" % ", ".join("%s=%s" % (k, v if v else "(empty)") for k, v in pairs))
    else:
        say("console   WARNING this dist/ carries neither VITE_MAINLINE_API_BASE nor")
        say("console           VITE_MAINLINE_BUNDLE_URL (import.meta.env MODE=%s). The site" % console["mode"])
        say("console           loads and then renders NO SOURCE on every surface. It is a")
        say("console           website with no data. Rebuild dist/ with:")
        say("console             %s" % PNPM_BUILD)
    say("sha256    %s" % digest)

    if zipped > LAMBDA_MAX_ZIPPED:
        refuse(
            "SIZE",
            "zipped is %d bytes, %d over Lambda's 50 MB direct-upload ceiling. The source "
            "maps are already stripped by default, so the remaining moves are dropping a "
            "dependency or moving the package to S3, which infra/modules/demo-api does not "
            "do." % (zipped, zipped - LAMBDA_MAX_ZIPPED),
        )
    if unzipped > LAMBDA_MAX_UNZIPPED:
        refuse(
            "SIZE",
            "unzipped is %d bytes, %d over Lambda's 250 MB ceiling. Nothing but a "
            "container image raises that; see docs/deploy/lambda-bundle.md."
            % (unzipped, unzipped - LAMBDA_MAX_UNZIPPED),
        )

    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(prog="build_lambda packer", add_help=True)
    parser.add_argument("--mode", default="build", choices=("preflight", "wheelcheck", "build"))
    parser.add_argument("--stage", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--arch", default="")
    parser.add_argument("--platform-tag", default="")
    parser.add_argument("--source-pkg", default="")
    parser.add_argument("--dist", default="")
    parser.add_argument("--bundle", default="")
    parser.add_argument("--python-version", default="3.13")
    parser.add_argument("--psycopg-version", default="")
    parser.add_argument("--python-report", default="")
    parser.add_argument("--pip-report", default="")
    parser.add_argument("--wheelhouse", default="")
    parser.add_argument("--wheel-source", default="")
    parser.add_argument("--command-line", default="")
    parser.add_argument("--builder", default="")
    parser.add_argument("--packer-sha256", default="")
    # The default is STRIP. This flag is the opt-out, and it is spelled as the thing it
    # does rather than as the negation of a flag that no longer exists, so a reader of a
    # recorded command line can see what was built without knowing this file's history.
    parser.add_argument("--keep-source-maps", action="store_true")
    args = parser.parse_args(argv)

    if args.mode == "wheelcheck":
        need(args, ["wheelhouse", "psycopg_version"])
        return wheelcheck(args)

    need(args, ["source_pkg", "dist", "bundle"])
    preflight(args)
    if refusals:
        for line in refusals:
            sys.stderr.write("build_lambda: %s\n" % line)
        return 2
    if args.mode == "preflight":
        say("preflight ok: handler package, console dist/ and evidence bundle are all present")
        return 0

    need(args, ["stage", "out", "arch", "platform_tag"])
    manifest = build(args)
    if refusals:
        for line in refusals:
            sys.stderr.write("build_lambda: %s\n" % line)
        # A refused build must leave nothing behind that a later step could upload. The
        # size gate fires AFTER the zip is written -- it can only be measured on the
        # finished file -- so the finished file is removed here.
        for leftover in (args.out, args.out + ".json"):
            if os.path.exists(leftover):
                os.remove(leftover)
                say("removed   %s (the build was refused)" % os.path.basename(leftover))
        return 2

    handle = open(args.out + ".json", "w", encoding="utf-8")
    try:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    finally:
        handle.close()
    say("manifest  %s.json" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'@

$PackerPath = Join-Path $OutDir "_pack_$Arch.py"
$PackerLf = ($Packer -replace "`r`n", "`n") + "`n"
[System.IO.File]::WriteAllText($PackerPath, $PackerLf, (New-Object System.Text.UTF8Encoding($false)))

$PackerSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackerPath).Hash.ToLower()
Step "packer    sha256 $PackerSha"
Step "          build_lambda.sh prints the same digest, or the two have drifted"

try {

    # -----------------------------------------------------------------------------
    # 3. Preflight, BEFORE pip touches the network
    # -----------------------------------------------------------------------------
    #
    # A missing console dist/ is the failure this exists to catch. Discovering it after
    # a 7 MB download and a 200-file install wastes a minute; discovering it after the
    # upload wastes the demo.

    & $Python $PackerPath --mode preflight `
        --source-pkg $SourcePkg `
        --dist $ConsoleDist `
        --bundle $EvidenceBundle
    if ($LASTEXITCODE -ne 0) { Fail "preflight refused this tree (exit $LASTEXITCODE)" }

    # -----------------------------------------------------------------------------
    # 4. The wheelhouse
    # -----------------------------------------------------------------------------
    #
    # Wheels are downloaded once per architecture and then reused, so a rebuild on a
    # machine that has built before needs no network at all and cannot silently pick up
    # a different artefact from PyPI. -RefreshWheels re-resolves deliberately. Every
    # wheel's name and sha256 goes into the sidecar manifest either way, so "reused" is
    # never "unknown".

    $WheelSource = 'wheelhouse (reused)'
    $needDownload = [bool]$RefreshWheels
    if (-not $needDownload) {
        & $Python $PackerPath --mode wheelcheck `
            --wheelhouse $Wheelhouse `
            --psycopg-version $PsycopgVersion 2>&1 | Out-Null
        $needDownload = ($LASTEXITCODE -ne 0)
    }

    if ($needDownload) {
        if (-not (Test-Path -LiteralPath $Wheelhouse)) {
            New-Item -ItemType Directory -Path $Wheelhouse -Force | Out-Null
        }
        Step "pip download --dest $Wheelhouse --platform $Platform ..."
        # --no-deps AND both distributions named explicitly: `--platform` refuses to
        # resolve an extra marker, so `psycopg[binary]` cannot be used for a
        # cross-platform target build.
        & $Python -m pip download `
            --dest $Wheelhouse `
            --no-deps `
            --disable-pip-version-check `
            --no-input `
            --platform $Platform `
            --implementation cp `
            --python-version $PythonVersion `
            --only-binary=:all: `
            "psycopg==$PsycopgVersion" `
            "psycopg-binary==$PsycopgVersion"
        if ($LASTEXITCODE -eq 0) {
            $WheelSource = 'pypi (downloaded)'
        }
        else {
            # The network is not always there. An incomplete wheelhouse is still fatal;
            # a complete one from an earlier run is a legitimate offline build, and it
            # says so in the manifest.
            & $Python $PackerPath --mode wheelcheck `
                --wheelhouse $Wheelhouse `
                --psycopg-version $PsycopgVersion
            if ($LASTEXITCODE -ne 0) {
                Fail "pip download failed and $Wheelhouse does not already hold psycopg==$PsycopgVersion and psycopg-binary==$PsycopgVersion. If pip said 'no matching distribution' for psycopg-binary, the platform tag $Platform is wrong for this version -- see the measured tag table at the top of this file."
            }
            $WheelSource = 'wheelhouse (reused; pip download failed)'
        }
    }
    Step "wheels    $WheelSource"

    # -----------------------------------------------------------------------------
    # 5. Stage the wheels
    # -----------------------------------------------------------------------------
    #
    # --no-index: install from the wheelhouse and nowhere else, so this step is a copy
    # of known bytes rather than a second resolution that could differ from the first.
    # --no-compile: a .pyc carries the source mtime and would move the zip's hash.

    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
    New-Item -ItemType Directory -Path $Stage -Force | Out-Null

    Step "pip install --target $Stage --no-index --find-links $Wheelhouse ..."
    & $Python -m pip install `
        --no-deps `
        --no-compile `
        --disable-pip-version-check `
        --no-input `
        --no-index `
        --find-links $Wheelhouse `
        --target $Stage `
        --platform $Platform `
        --implementation cp `
        --python-version $PythonVersion `
        --only-binary=:all: `
        "psycopg==$PsycopgVersion" `
        "psycopg-binary==$PsycopgVersion"
    if ($LASTEXITCODE -ne 0) { Fail "pip install from the wheelhouse failed (exit $LASTEXITCODE)" }

    # -----------------------------------------------------------------------------
    # 6. Copy, prune, pack, hash, and gate on size
    # -----------------------------------------------------------------------------

    $packArgs = @(
        '--mode', 'build',
        '--stage', $Stage,
        '--out', $Out,
        '--arch', $Arch,
        '--platform-tag', $Platform,
        '--source-pkg', $SourcePkg,
        '--dist', $ConsoleDist,
        '--bundle', $EvidenceBundle,
        '--python-version', $PythonVersion,
        '--psycopg-version', $PsycopgVersion,
        '--python-report', $PythonReport,
        '--pip-report', $PipReport,
        '--wheelhouse', $Wheelhouse,
        '--wheel-source', $WheelSource,
        '--command-line', $CommandLine,
        '--builder', 'scripts/deploy/build_lambda.ps1',
        '--packer-sha256', $PackerSha
    )
    if ($KeepSourceMaps) { $packArgs += '--keep-source-maps' }

    & $Python $PackerPath @packArgs
    if ($LASTEXITCODE -ne 0) { Fail "the packer refused this build (exit $LASTEXITCODE)" }

    # -----------------------------------------------------------------------------
    # 7. Re-check the finished artefact with a program that never saw the staging tree
    # -----------------------------------------------------------------------------
    #
    # bundle_manifest.py opens the zip and nothing else. If it disagrees with what was
    # just packed, the disagreement is between the artefact and the build, which is
    # exactly the class of failure a build log cannot report about itself. --strict
    # makes the four determinism properties gating here, where they are ours to
    # guarantee.

    Step 'check     scripts/deploy/bundle_manifest.py --strict'
    & $Python $ManifestTool $Out `
        --strict `
        --quiet `
        --require mainline_demo_api/app.py `
        --require psycopg_binary/ `
        --require web/assets/ `
        --require web/bundle/manifest.json
    if ($LASTEXITCODE -ne 0) {
        Fail "the finished zip did not pass scripts/deploy/bundle_manifest.py (exit $LASTEXITCODE)"
    }
}
finally {
    if (-not $KeepStage) {
        Remove-Item -LiteralPath $PackerPath -Force -ErrorAction SilentlyContinue
    }
}

if (-not $KeepStage) {
    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
}
else {
    Step "stage     $Stage (kept)"
    Step "packer    $PackerPath (kept)"
}

Step "ok        $Out"
