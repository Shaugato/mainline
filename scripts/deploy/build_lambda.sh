#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# Build the reproducible deployment package for the MAINLINE demo API Lambda.
#
# POSIX twin of scripts/deploy/build_lambda.ps1. The two produce a BYTE-IDENTICAL zip on
# the same machine from the same inputs, because the pruning and the packing are done by
# the same embedded Python program in both, and because every field a zip writer would
# otherwise take from the environment - entry timestamps, entry order, file mode,
# compression level - is fixed here rather than observed.
#
# Runs on Linux, macOS, and on this project's Windows workstation under Git Bash. On Git
# Bash the interpreter is a native `python.exe`, which does not understand `/d/...`
# paths, so every path handed to it goes through `winpath` first.
#
#   out/lambda/mainline-demo-api-<arch>.zip        the artefact
#   out/lambda/mainline-demo-api-<arch>.zip.json   sha256, sizes, contents, prune list
#
# The package contains exactly three things: `mainline_demo_api/` copied from the
# vertical, `psycopg/`, and `psycopg_binary/`. No boto3 - the runtime ships one and
# `db.py` signs its single SSM GetParameter call itself, so the deployment package's
# behaviour does not depend on which boto3 the runtime happens to carry this month.
#
# PLATFORM TAGS, MEASURED 2026-08-10 (see infra/modules/demo-api/README.md):
#
#   --platform manylinux2014_x86_64    -> psycopg_binary-3.3.4-cp313-cp313-manylinux2014_x86_64...whl
#   --platform manylinux2014_aarch64   -> ERROR: no matching distribution (aarch64 stops at 3.2.13)
#   --platform manylinux_2_28_aarch64  -> psycopg_binary-3.3.4-cp313-cp313-manylinux_2_28_aarch64.whl
#
# The arm64 build therefore asks for glibc 2.28. Lambda's python3.13 runtime is Amazon
# Linux 2023 / glibc 2.34, verified by running the unzipped package inside
# `public.ecr.aws/lambda/python:3.13`; the transcript is in the module README.
#
# Usage:
#   scripts/deploy/build_lambda.sh                       # arm64, the deployed default
#   scripts/deploy/build_lambda.sh --arch x86_64
#   scripts/deploy/build_lambda.sh --out /tmp/api.zip --keep-stage

set -euo pipefail

ARCH="arm64"
OUT=""
PYTHON=""
PSYCOPG_VERSION="3.3.4"
PLATFORM_TAG=""
KEEP_STAGE=0
PYTHON_VERSION="3.13"

die() { printf 'build_lambda: %s\n' "$*" >&2; exit 1; }
step() { printf 'build_lambda: %s\n' "$*"; }

usage() {
  sed -n '2,40p' "$0"
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch)     ARCH="${2:?--arch needs a value}"; shift 2 ;;
    --out)      OUT="${2:?--out needs a value}"; shift 2 ;;
    --python)   PYTHON="${2:?--python needs a value}"; shift 2 ;;
    --psycopg)  PSYCOPG_VERSION="${2:?--psycopg needs a value}"; shift 2 ;;
    --platform) PLATFORM_TAG="${2:?--platform needs a value}"; shift 2 ;;
    --keep-stage) KEEP_STAGE=1; shift ;;
    -h|--help)  usage 0 ;;
    *)          die "unknown argument: $1 (try --help)" ;;
  esac
done

case "$ARCH" in
  arm64|x86_64) ;;
  *) die "--arch must be arm64 or x86_64, got '$ARCH'" ;;
esac

# ---------------------------------------------------------------------------------
# 1. Locate the repository, the interpreter and the source package
# ---------------------------------------------------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
SOURCE_PKG="$REPO_ROOT/verticals/mainline/apps/demo-api/src/mainline_demo_api"

[ -f "$SOURCE_PKG/app.py" ] || \
  die "handler package not found at $SOURCE_PKG (expected app.py, which provides mainline_demo_api.app.handler)"

if [ -z "$PYTHON" ]; then
  # The repository virtualenv first. `uv` is deliberately not consulted: it is not
  # installed on the build machine, and every `just` recipe that shells out to `uv run`
  # is dead there (docs/leads/deploy-plan.md sec 7.4).
  for candidate in "$REPO_ROOT/.venv/Scripts/python.exe" "$REPO_ROOT/.venv/bin/python"; do
    if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
  done
fi
if [ -z "$PYTHON" ]; then
  PYTHON="$(command -v python3 || command -v python || true)"
fi
[ -n "$PYTHON" ] || die "no interpreter: pass --python, or create the repo .venv"

# Git Bash hands POSIX paths to a native python.exe, which cannot open them. `cygpath -m`
# yields D:/... , which both shells and the Windows interpreter accept.
winpath() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

if [ -z "$PLATFORM_TAG" ]; then
  if [ "$ARCH" = "arm64" ]; then
    PLATFORM_TAG="manylinux_2_28_aarch64"
  else
    PLATFORM_TAG="manylinux2014_x86_64"
  fi
fi

[ -n "$OUT" ] || OUT="$REPO_ROOT/out/lambda/mainline-demo-api-$ARCH.zip"
OUT_DIR="$(dirname -- "$OUT")"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd -- "$OUT_DIR" && pwd)"
OUT="$OUT_DIR/$(basename -- "$OUT")"
STAGE="$OUT_DIR/stage-$ARCH"

step "repo      $REPO_ROOT"
step "python    $PYTHON"
step "arch      $ARCH"
step "platform  $PLATFORM_TAG"
step "psycopg   $PSYCOPG_VERSION"
step "out       $OUT"

# ---------------------------------------------------------------------------------
# 2. Stage: wheels first, then the handler package
# ---------------------------------------------------------------------------------

rm -rf "$STAGE"
mkdir -p "$STAGE"

# --no-deps AND both distributions named explicitly: `--platform` refuses to resolve an
# extra marker, so `psycopg[binary]` cannot be used for a cross-platform target build.
# --no-compile: .pyc files carry the source mtime and would make the zip non-reproducible.
step "pip install --target $STAGE --platform $PLATFORM_TAG ..."
"$PYTHON" -m pip install \
  --no-deps \
  --no-compile \
  --disable-pip-version-check \
  --no-input \
  --target "$(winpath "$STAGE")" \
  --platform "$PLATFORM_TAG" \
  --implementation cp \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  "psycopg==$PSYCOPG_VERSION" \
  "psycopg-binary==$PSYCOPG_VERSION" \
  || die "pip failed. If it says 'no matching distribution' for psycopg-binary==$PSYCOPG_VERSION, the platform tag $PLATFORM_TAG is wrong for this version - see the tag table at the top of this file."

step "copy      $SOURCE_PKG -> $STAGE/mainline_demo_api"
cp -R "$SOURCE_PKG" "$STAGE/mainline_demo_api"

# ---------------------------------------------------------------------------------
# 3. Prune and pack, in Python, so Windows and Linux produce the same bytes
# ---------------------------------------------------------------------------------

# The packer is embedded rather than shipped as a third file because this worker owns
# exactly two build scripts, and because a shared helper that one of them could load and
# the other could not is a reproducibility bug waiting to happen. build_lambda.ps1
# carries a byte-identical copy; `diff` of the two extracted programs is expected to be
# empty, and the two scripts are expected to print the same sha256.
PACKER="$OUT_DIR/_pack_$ARCH.py"
cleanup() { rm -f "$PACKER"; }
trap cleanup EXIT

cat > "$PACKER" <<'PACKER_EOF'
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
PACKER_EOF

"$PYTHON" "$(winpath "$PACKER")" "$(winpath "$STAGE")" "$(winpath "$OUT")" "$ARCH" "$PLATFORM_TAG"

if [ "$KEEP_STAGE" -eq 0 ]; then
  rm -rf "$STAGE"
else
  step "stage     $STAGE (kept)"
fi

step "ok        $OUT"
