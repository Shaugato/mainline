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

    SOURCE MAPS ARE KEPT ON PURPOSE
    web/assets/*.js.map is about 2.4 MB of the package. They stay: a judge who opens
    DevTools on the demo sees real component names and real stack frames instead of
    `surface-Bv8EMlU6.js:1:20481`, and this project's whole argument is that its claims
    are checkable. There is ample room, and -StripSourceMaps exists for the day there
    is not.

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

.PARAMETER StripSourceMaps
    Drop web/**/*.map from the package (about 2.4 MB). Kept by default.

.PARAMETER KeepStage
    Leave the staging tree and the extracted packer in place for inspection.

.EXAMPLE
    pwsh scripts/deploy/build_lambda.ps1
    pwsh scripts/deploy/build_lambda.ps1 -Arch x86_64
    pwsh scripts/deploy/build_lambda.ps1 -StripSourceMaps -KeepStage
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
if ($StripSourceMaps) { $CommandLine += ' -StripSourceMaps' }
if ($RefreshWheels) { $CommandLine += ' -RefreshWheels' }

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

Three modes:
  --mode preflight   refuse, before pip runs, if an input the package needs is absent
  --mode wheelcheck  say whether a wheelhouse already holds both pinned wheels
  --mode build       copy, prune, pack, hash, gate on size, write the sidecar manifest
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

EPOCH = (1980, 1, 1, 0, 0, 0)
COMPRESSLEVEL = 9
MODE_EXEC = 0o755
MODE_FILE = 0o644
LAMBDA_MAX_ZIPPED = 50 * 1024 * 1024
LAMBDA_MAX_UNZIPPED = 250 * 1024 * 1024

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


def strip_maps(stage):
    """Remove web/**/*.map. Off by default; the wrapper's help says why."""
    removed = []
    web = os.path.join(stage, "web")
    for dirpath, _dirnames, filenames in os.walk(web):
        for name in sorted(filenames):
            if name.endswith(".map"):
                full = os.path.join(dirpath, name)
                os.remove(full)
                removed.append(os.path.relpath(full, stage).replace(os.sep, "/"))
    return sorted(removed)


def probe_console(stage):
    """Report which build-time source variables the console artefact actually carries.

    Vite inlines import.meta.env as an object literal and the console's
    src/app/source-select.ts reads exactly two keys off it. With neither key set, the
    console renders its NO SOURCE panel on every surface: a site that loads, is honest,
    and shows nothing. That is a console-build fact and not a packaging fact, so this
    reports it loudly and does not refuse -- this program does not own dist/.
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
    stripped = strip_maps(stage) if args.strip_source_maps else []

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
        "source_maps": "stripped" if args.strip_source_maps else "kept",
        "source_maps_stripped": stripped,
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
            "zipped is %d bytes, %d over Lambda's 50 MB direct-upload ceiling. Either "
            "drop the source maps (--strip-source-maps, about 2.4 MB of this tree) or "
            "move the package to S3, which infra/modules/demo-api does not do."
            % (zipped, zipped - LAMBDA_MAX_ZIPPED),
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
    parser.add_argument("--strip-source-maps", action="store_true")
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
    if ($StripSourceMaps) { $packArgs += '--strip-source-maps' }

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
