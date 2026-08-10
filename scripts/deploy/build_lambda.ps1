#!/usr/bin/env pwsh
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#Requires -Version 5.1

<#
.SYNOPSIS
    Build the reproducible deployment package for the MAINLINE demo API Lambda.

.DESCRIPTION
    Produces `out/lambda/mainline-demo-api-<arch>.zip`, byte-for-byte identical across
    runs on the same machine, containing exactly three things:

        mainline_demo_api/   the handler package, copied from the vertical
        psycopg/             the pure-Python driver           (py3-none-any wheel)
        psycopg_binary/      the compiled libpq bindings      (manylinux wheel)

    Nothing else. No boto3 (the runtime has one and `db.py` signs its single SSM call
    itself), no web framework, no tzdata, no `__pycache__`, no `RECORD`.

    WHY THE PACKAGE MUST BE REPRODUCIBLE
    Terraform decides whether to redeploy from `source_code_hash =
    filebase64sha256(var.package_path)`. A zip whose bytes move because the clock moved
    makes every `terraform plan` show a Lambda update, which trains an operator to
    ignore the plan four days before a deadline. Fixed entry timestamps, sorted entry
    order and a fixed compression level make the hash a statement about the CONTENT.

    PLATFORM TAGS ARE PER-ARCHITECTURE AND MEASURED, NOT GUESSED
    psycopg-binary 3.3.4 does not publish the same manylinux tag for both machines.
    Measured on 2026-08-10 with this repository's interpreter:

        --platform manylinux2014_x86_64   ->  psycopg_binary-3.3.4-cp313-cp313-
                                              manylinux2014_x86_64.manylinux_2_17_x86_64.whl
        --platform manylinux2014_aarch64  ->  ERROR: no matching distribution
                                              (aarch64 stops at 3.2.13 for that tag)
        --platform manylinux_2_28_aarch64 ->  psycopg_binary-3.3.4-cp313-cp313-
                                              manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl

    So the arm64 build asks for glibc 2.28, not glibc 2.17. The Lambda `python3.13`
    runtime is Amazon Linux 2023, glibc 2.34, which satisfies it. `infra/modules/
    demo-api/README.md` carries the same table and the container proof.

.PARAMETER Arch
    `arm64` (default) or `x86_64`. Must match the Terraform module's `architecture`.

.PARAMETER Out
    Output zip path. Defaults to `<repo>/out/lambda/mainline-demo-api-<arch>.zip`.
    `out/` is in `.gitignore`; `build/` is not, which is why this is not `build/`.

.PARAMETER Python
    Interpreter used for `-m pip`. Defaults to the repository virtualenv
    (`.venv/Scripts/python.exe` on Windows, `.venv/bin/python` elsewhere), then `python`.
    `uv` is deliberately not used: it is not installed on the build machine.

.PARAMETER PsycopgVersion
    Version pinned for BOTH `psycopg` and `psycopg-binary`. Defaults to 3.3.4, which is
    what `verticals/mainline/apps/demo-api/pyproject.toml` pins.

.PARAMETER Platform
    Override the pip platform tag. Empty means "use the measured tag for -Arch".

.PARAMETER KeepStage
    Leave the unzipped staging directory in place for inspection.

.EXAMPLE
    pwsh scripts/deploy/build_lambda.ps1
    pwsh scripts/deploy/build_lambda.ps1 -Arch x86_64
#>

[CmdletBinding()]
param(
    [ValidateSet('arm64', 'x86_64')]
    [string]$Arch = 'arm64',

    [string]$Out = '',

    [string]$Python = '',

    [string]$PsycopgVersion = '3.3.4',

    [string]$Platform = '',

    [switch]$KeepStage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# PowerShell 7 only. Without it a non-zero exit from pip is invisible and this script
# would cheerfully zip an empty staging directory and print a stable hash for it.
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$PythonVersion = '3.13'
$Handler = 'mainline_demo_api.app.handler'

function Fail([string]$Message) {
    Write-Host "build_lambda: $Message" -ForegroundColor Red
    exit 1
}

function Step([string]$Message) {
    Write-Host "build_lambda: $Message"
}

# ---------------------------------------------------------------------------------
# 1. Locate the repository, the interpreter and the source package
# ---------------------------------------------------------------------------------

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
$SourcePkg = Join-Path $RepoRoot 'verticals/mainline/apps/demo-api/src/mainline_demo_api'

if (-not (Test-Path -LiteralPath (Join-Path $SourcePkg 'app.py'))) {
    Fail "handler package not found at $SourcePkg (expected app.py, which provides $Handler)"
}

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
$Out = Join-Path ((Resolve-Path -LiteralPath $OutDir).Path) (Split-Path -Leaf $Out)

$Stage = Join-Path $OutDir "stage-$Arch"

Step "repo      $RepoRoot"
Step "python    $Python"
Step "arch      $Arch"
Step "platform  $Platform"
Step "psycopg   $PsycopgVersion"
Step "out       $Out"

# ---------------------------------------------------------------------------------
# 2. Stage: wheels first, then the handler package
# ---------------------------------------------------------------------------------

if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

# --no-deps AND both distributions named explicitly: `--platform` refuses to resolve an
# extra marker, so `psycopg[binary]` cannot be used for a cross-platform target build.
# --no-compile: .pyc files carry the source mtime and would make the zip non-reproducible.
$pipArgs = @(
    '-m', 'pip', 'install',
    '--no-deps',
    '--no-compile',
    '--disable-pip-version-check',
    '--no-input',
    '--target', $Stage,
    '--platform', $Platform,
    '--implementation', 'cp',
    '--python-version', $PythonVersion,
    '--only-binary=:all:',
    "psycopg==$PsycopgVersion",
    "psycopg-binary==$PsycopgVersion"
)

Step "pip install --target $Stage --platform $Platform ..."
& $Python @pipArgs
if ($LASTEXITCODE -ne 0) {
    Fail "pip failed (exit $LASTEXITCODE). If it says 'no matching distribution' for psycopg-binary==$PsycopgVersion, the platform tag $Platform is wrong for this version - see the tag table at the top of this file."
}

Step "copy      $SourcePkg -> $Stage/mainline_demo_api"
Copy-Item -LiteralPath $SourcePkg -Destination (Join-Path $Stage 'mainline_demo_api') -Recurse -Force

# ---------------------------------------------------------------------------------
# 3. Prune and pack, in Python, so Windows and Linux produce the same bytes
# ---------------------------------------------------------------------------------

# The packer is embedded rather than shipped as a third file because this worker owns
# exactly two build scripts, and because a shared helper that one of them could load and
# the other could not is a reproducibility bug waiting to happen. build_lambda.sh carries
# a byte-identical copy; `diff` of the two extracted programs is expected to be empty.
$Packer = @'
"""Prune a Lambda staging tree and pack it into a reproducible zip."""

import hashlib
import json
import os
import shutil
import sys
import zipfile

stage = os.path.abspath(sys.argv[1])
out = os.path.abspath(sys.argv[2])
manifest_path = out + ".json"
arch = sys.argv[3]
platform_tag = sys.argv[4]

PRUNE_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "tzdata"}
PRUNE_NAMES = {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"}
PRUNE_SUFFIXES = (".pyc", ".pyo")

# ZIP's own epoch. Every entry gets it, so the archive says nothing about when it was
# built and everything about what is in it.
EPOCH = (1980, 1, 1, 0, 0, 0)

pruned = []
for dirpath, dirnames, filenames in os.walk(stage, topdown=True):
    for name in sorted(dirnames):
        if name in PRUNE_DIRS:
            target = os.path.join(dirpath, name)
            shutil.rmtree(target)
            pruned.append(os.path.relpath(target, stage).replace(os.sep, "/") + "/")
            dirnames.remove(name)
    for name in sorted(filenames):
        if name in PRUNE_NAMES or name.endswith(PRUNE_SUFFIXES):
            target = os.path.join(dirpath, name)
            os.remove(target)
            pruned.append(os.path.relpath(target, stage).replace(os.sep, "/"))

entries = []
for dirpath, dirnames, filenames in os.walk(stage):
    dirnames.sort()
    for name in filenames:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, stage).replace(os.sep, "/")
        entries.append((rel, full))
entries.sort(key=lambda item: item[0])

# A zip that is missing the handler, or the driver, is a 502 at 03:00 rather than a
# failed build. Refuse here instead.
required = ["mainline_demo_api/app.py", "psycopg/__init__.py", "psycopg_binary/__init__.py"]
missing = [name for name in required if not os.path.exists(os.path.join(stage, name))]
if missing:
    sys.stderr.write("build_lambda: staging tree is missing %r\n" % (missing,))
    raise SystemExit(2)

if os.path.exists(out):
    os.remove(out)

unzipped = 0
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for rel, full in entries:
        with open(full, "rb") as handle:
            data = handle.read()
        unzipped += len(data)
        info = zipfile.ZipInfo(rel, date_time=EPOCH)
        info.create_system = 3  # Unix, so external_attr is read as a mode
        base = rel.rsplit("/", 1)[-1]
        mode = 0o755 if (".so" in base or base.endswith(".dylib")) else 0o644
        info.external_attr = mode << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, data)

digest = hashlib.sha256()
with open(out, "rb") as handle:
    for block in iter(lambda: handle.read(1 << 20), b""):
        digest.update(block)
sha256 = digest.hexdigest()
zipped = os.path.getsize(out)

top = sorted({rel.split("/", 1)[0] for rel, _ in entries})
dists = sorted(name for name in top if name.endswith(".dist-info"))

manifest = {
    "artifact": os.path.basename(out),
    "sha256": sha256,
    "architecture": arch,
    "platform_tag": platform_tag,
    "handler": "mainline_demo_api.app.handler",
    "runtime": "python3.13",
    "files": len(entries),
    "bytes_zipped": zipped,
    "bytes_unzipped": unzipped,
    "top_level": top,
    "distributions": dists,
    "pruned": pruned,
}
with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
    handle.write("\n")

print("build_lambda: files      %d" % len(entries))
print("build_lambda: unzipped   %d bytes (%.1f MB)" % (unzipped, unzipped / 1048576.0))
print("build_lambda: zipped     %d bytes (%.1f MB)" % (zipped, zipped / 1048576.0))
print("build_lambda: top-level  %s" % ", ".join(top))
print("build_lambda: manifest   %s" % manifest_path)
print("build_lambda: sha256     %s" % sha256)

# Lambda's direct-upload ceiling is 50 MB zipped; above it the package has to go via S3,
# which this module's `filename =` does not do. 250 MB is the unzipped ceiling.
if zipped > 50 * 1024 * 1024:
    sys.stderr.write("build_lambda: WARNING zipped package exceeds Lambda's 50 MB direct-upload limit\n")
if unzipped > 250 * 1024 * 1024:
    sys.stderr.write("build_lambda: WARNING unzipped package exceeds Lambda's 250 MB limit\n")
'@

$PackerPath = Join-Path $OutDir "_pack_$Arch.py"
[System.IO.File]::WriteAllText($PackerPath, $Packer, (New-Object System.Text.UTF8Encoding($false)))

try {
    & $Python $PackerPath $Stage $Out $Arch $Platform
    if ($LASTEXITCODE -ne 0) { Fail "packer failed (exit $LASTEXITCODE)" }
}
finally {
    Remove-Item -LiteralPath $PackerPath -Force -ErrorAction SilentlyContinue
}

if (-not $KeepStage) {
    Remove-Item -LiteralPath $Stage -Recurse -Force
}
else {
    Step "stage     $Stage (kept)"
}

Step "ok        $Out"
