#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# Build the deterministic deployment package for the MAINLINE demo API Lambda.
#
# POSIX twin of scripts/deploy/build_lambda.ps1. The two produce a BYTE-IDENTICAL zip
# from the same tree, because the staging, pruning and packing are done by the same
# embedded Python program in both -- and that program's sha256 is printed by both, so
# "the same program" is a hash you can compare rather than a claim you have to trust.
#
# WHAT IS IN THE PACKAGE, AND WHY IT IS FOUR THINGS NOW
# ----------------------------------------------------
# Decision D1 (docs/leads/ship-final.md sec 1.4) made the demo URL a public Lambda
# Function URL rather than CloudFront, because this AWS account cannot create a
# distribution. One origin therefore serves the console SPA, the evidence bundle and
# /v1/*, and this zip is that whole origin:
#
#   mainline_demo_api/   the handler package, copied from the vertical
#   psycopg/             the pure-Python driver              (py3-none-any wheel)
#   psycopg_binary/      the compiled libpq bindings         (manylinux wheel)
#   web/                 verticals/mainline/apps/console/dist/   -- the website
#   web/bundle/          .../console/fixtures/bundles/demo-cloud -- the EvidenceBundle
#
# No boto3: the runtime ships one and db.py signs its single SSM GetParameter call
# itself, so the package's behaviour does not depend on which boto3 the runtime happens
# to carry this month. No web framework. No tzdata. No __pycache__, no RECORD.
#
# WHY REPRODUCIBILITY IS THE POINT
# --------------------------------
# Terraform decides whether to redeploy from `source_code_hash =
# filebase64sha256(var.package_path)`. A zip whose bytes move because the clock moved
# makes every `terraform plan` show a Lambda update, which trains an operator to skim
# the plan four days before a deadline. Fixed entry timestamps (the DOS epoch), sorted
# entry order, a fixed compression level and a fixed file mode make the hash a statement
# about the CONTENT and nothing else. Two builds from the same tree print the same
# sha256; evidence/deploy/lambda-bundle.json records both.
#
# SOURCE MAPS ARE KEPT ON PURPOSE
# -------------------------------
# web/assets/*.js.map is about 2.4 MB of the package. They stay: a judge who opens
# DevTools on the demo sees real component names and real stack frames instead of
# `surface-Bv8EMlU6.js:1:20481`, and this project's whole argument is that its claims
# are checkable. There is ample room -- see the size numbers this script prints -- and
# --strip-source-maps exists for the day there is not.
#
# PLATFORM TAGS ARE MEASURED PER ARCHITECTURE, NOT GUESSED (2026-08-10, this machine):
#
#   --platform manylinux2014_x86_64    -> psycopg_binary-3.3.4-cp313-cp313-manylinux2014_x86_64...whl
#   --platform manylinux2014_aarch64   -> ERROR: no matching distribution (aarch64 stops at 3.2.13)
#   --platform manylinux_2_28_aarch64  -> psycopg_binary-3.3.4-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
#
# The arm64 build therefore asks for glibc 2.28. Lambda's python3.13 runtime is Amazon
# Linux 2023 / glibc 2.34, verified by running the unzipped package inside
# public.ecr.aws/lambda/python:3.13; the transcript is in infra/modules/demo-api/README.md.
#
# Runs on Linux, macOS, and on this project's Windows workstation under Git Bash. On Git
# Bash the interpreter is a native python.exe, which cannot open a /d/... path, so every
# path handed to it goes through `winpath` first.
#
#   out/lambda/mainline-demo-api-<arch>.zip        the artefact
#   out/lambda/mainline-demo-api-<arch>.zip.json   the sidecar manifest Terraform reads
#   out/lambda/wheels-<arch>/                      the wheelhouse, reused when present
#
# Usage:
#   scripts/deploy/build_lambda.sh                          # arm64, the deployed default
#   scripts/deploy/build_lambda.sh --arch x86_64
#   scripts/deploy/build_lambda.sh --out /tmp/api.zip --keep-stage
#   scripts/deploy/build_lambda.sh --strip-source-maps      # smaller, less debuggable
#   scripts/deploy/build_lambda.sh --refresh-wheels         # re-resolve from PyPI

set -euo pipefail

ARCH="arm64"
OUT=""
PYTHON=""
PSYCOPG_VERSION="3.3.4"
PLATFORM_TAG=""
WHEELHOUSE=""
KEEP_STAGE=0
STRIP_MAPS=0
REFRESH_WHEELS=0
PYTHON_VERSION="3.13"

# Recorded verbatim in the sidecar manifest. Repo-relative on purpose: an absolute
# D:\... path in a tracked artefact is an `abs_windows_path` finding in
# scripts/submission/audit_public_readiness.py, and this manifest is quoted in
# evidence/deploy/lambda-bundle.json.
COMMAND_LINE="scripts/deploy/build_lambda.sh $*"

die() { printf 'build_lambda: %s\n' "$*" >&2; exit 1; }
step() { printf 'build_lambda: %s\n' "$*"; }

usage() {
  cat <<'USAGE_EOF'
build_lambda.sh [options]

  --arch arm64|x86_64   target architecture (default arm64)
  --out PATH            output zip (default out/lambda/mainline-demo-api-<arch>.zip)
  --python PATH         interpreter used for -m pip (default the repo .venv)
  --psycopg VERSION     psycopg and psycopg-binary pin (default 3.3.4)
  --platform TAG        override the measured pip platform tag
  --wheelhouse PATH     wheel cache (default out/lambda/wheels-<arch>)
  --refresh-wheels      re-download the wheels even if the wheelhouse has them
  --strip-source-maps   drop web/**/*.map (about 2.4 MB; the console stops being
                        debuggable in a judge's DevTools -- kept by default)
  --keep-stage          leave the staging tree and the extracted packer in place
  -h, --help            this text
USAGE_EOF
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch)     ARCH="${2:?--arch needs a value}"; shift 2 ;;
    --out)      OUT="${2:?--out needs a value}"; shift 2 ;;
    --python)   PYTHON="${2:?--python needs a value}"; shift 2 ;;
    --psycopg)  PSYCOPG_VERSION="${2:?--psycopg needs a value}"; shift 2 ;;
    --platform) PLATFORM_TAG="${2:?--platform needs a value}"; shift 2 ;;
    --wheelhouse) WHEELHOUSE="${2:?--wheelhouse needs a value}"; shift 2 ;;
    --refresh-wheels) REFRESH_WHEELS=1; shift ;;
    --strip-source-maps) STRIP_MAPS=1; shift ;;
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
# 1. Locate the repository, the interpreter and the four inputs
# ---------------------------------------------------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
SOURCE_PKG="$REPO_ROOT/verticals/mainline/apps/demo-api/src/mainline_demo_api"
CONSOLE_DIST="$REPO_ROOT/verticals/mainline/apps/console/dist"
EVIDENCE_BUNDLE="$REPO_ROOT/verticals/mainline/apps/console/fixtures/bundles/demo-cloud"
MANIFEST_TOOL="$REPO_ROOT/scripts/deploy/bundle_manifest.py"

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
[ -n "$WHEELHOUSE" ] || WHEELHOUSE="$OUT_DIR/wheels-$ARCH"

# Version strings for the manifest. `pip --version` is NOT used: it prints the absolute
# path of the pip package, which would put a D:\... path into a tracked evidence file.
PYTHON_REPORT="$("$PYTHON" -c 'import platform;print("%s %s"%(platform.python_implementation(),platform.python_version()))')"
PIP_REPORT="$("$PYTHON" -c 'import importlib.metadata as m;print("pip "+m.version("pip"))')"

step "repo      $REPO_ROOT"
step "python    $PYTHON ($PYTHON_REPORT, $PIP_REPORT)"
step "arch      $ARCH"
step "platform  $PLATFORM_TAG"
step "psycopg   $PSYCOPG_VERSION"
step "console   $CONSOLE_DIST"
step "bundle    $EVIDENCE_BUNDLE"
step "out       $OUT"

# ---------------------------------------------------------------------------------
# 2. Extract the packer
# ---------------------------------------------------------------------------------
#
# The packer is embedded rather than shipped as a third file because this worker owns
# exactly two build scripts, and because a shared helper that one of them could load and
# the other could not is a reproducibility bug waiting to happen. build_lambda.ps1
# carries a byte-identical copy. Both normalise it to LF before writing -- this file may
# be checked out with CRLF -- and both print its sha256, so a drift between the two
# scripts is one line of output apart, not a subtle difference in an artefact.

PACKER="$OUT_DIR/_pack_$ARCH.py"
cleanup() { if [ "$KEEP_STAGE" -eq 0 ]; then rm -f "$PACKER"; fi; }
trap cleanup EXIT

cat > "$PACKER.crlf" <<'PACKER_EOF'
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
PACKER_EOF

# This file may be checked out with CRLF on Windows; the heredoc would then carry the
# CRs into the extracted program and its digest would differ from the PowerShell twin's
# for a reason that has nothing to do with what it does.
tr -d '\r' < "$PACKER.crlf" > "$PACKER"
rm -f "$PACKER.crlf"

PACKER_SHA="$("$PYTHON" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$(winpath "$PACKER")")"
step "packer    sha256 $PACKER_SHA"
step "          build_lambda.ps1 prints the same digest, or the two have drifted"

PACKER_WIN="$(winpath "$PACKER")"

# ---------------------------------------------------------------------------------
# 3. Preflight, BEFORE pip touches the network
# ---------------------------------------------------------------------------------
#
# A missing console dist/ is the failure this exists to catch. Discovering it after a
# 7 MB download and a 200-file install wastes a minute; discovering it after the upload
# wastes the demo.

"$PYTHON" "$PACKER_WIN" --mode preflight \
  --source-pkg "$(winpath "$SOURCE_PKG")" \
  --dist "$(winpath "$CONSOLE_DIST")" \
  --bundle "$(winpath "$EVIDENCE_BUNDLE")"

# ---------------------------------------------------------------------------------
# 4. The wheelhouse
# ---------------------------------------------------------------------------------
#
# Wheels are downloaded once per architecture and then reused, so a rebuild on a machine
# that has built before needs no network at all and cannot silently pick up a different
# artefact from PyPI. --refresh-wheels re-resolves deliberately. Every wheel's name and
# sha256 goes into the sidecar manifest either way, so "reused" is never "unknown".

WHEEL_SOURCE="wheelhouse (reused)"
if [ "$REFRESH_WHEELS" -eq 1 ] || \
   ! "$PYTHON" "$PACKER_WIN" --mode wheelcheck \
       --wheelhouse "$(winpath "$WHEELHOUSE")" \
       --psycopg-version "$PSYCOPG_VERSION" >/dev/null 2>&1; then
  mkdir -p "$WHEELHOUSE"
  step "pip download --dest $WHEELHOUSE --platform $PLATFORM_TAG ..."
  # --no-deps AND both distributions named explicitly: `--platform` refuses to resolve
  # an extra marker, so `psycopg[binary]` cannot be used for a cross-platform target.
  if "$PYTHON" -m pip download \
      --dest "$(winpath "$WHEELHOUSE")" \
      --no-deps \
      --disable-pip-version-check \
      --no-input \
      --platform "$PLATFORM_TAG" \
      --implementation cp \
      --python-version "$PYTHON_VERSION" \
      --only-binary=:all: \
      "psycopg==$PSYCOPG_VERSION" \
      "psycopg-binary==$PSYCOPG_VERSION"; then
    WHEEL_SOURCE="pypi (downloaded)"
  else
    # The network is not always there. An incomplete wheelhouse is still fatal; a
    # complete one from an earlier run is a legitimate offline build, and it says so.
    "$PYTHON" "$PACKER_WIN" --mode wheelcheck \
      --wheelhouse "$(winpath "$WHEELHOUSE")" \
      --psycopg-version "$PSYCOPG_VERSION" \
      || die "pip download failed and $WHEELHOUSE does not already hold psycopg==$PSYCOPG_VERSION and psycopg-binary==$PSYCOPG_VERSION. If pip said 'no matching distribution' for psycopg-binary, the platform tag $PLATFORM_TAG is wrong for this version -- see the measured tag table at the top of this file."
    WHEEL_SOURCE="wheelhouse (reused; pip download failed)"
  fi
fi
step "wheels    $WHEEL_SOURCE"

# ---------------------------------------------------------------------------------
# 5. Stage the wheels
# ---------------------------------------------------------------------------------
#
# --no-index: install from the wheelhouse and nowhere else, so this step is a copy of
# known bytes rather than a second resolution that could differ from the first.
# --no-compile: a .pyc carries the source mtime and would move the zip's hash.

rm -rf "$STAGE"
mkdir -p "$STAGE"

step "pip install --target $STAGE --no-index --find-links $WHEELHOUSE ..."
"$PYTHON" -m pip install \
  --no-deps \
  --no-compile \
  --disable-pip-version-check \
  --no-input \
  --no-index \
  --find-links "$(winpath "$WHEELHOUSE")" \
  --target "$(winpath "$STAGE")" \
  --platform "$PLATFORM_TAG" \
  --implementation cp \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  "psycopg==$PSYCOPG_VERSION" \
  "psycopg-binary==$PSYCOPG_VERSION" \
  || die "pip install from the wheelhouse failed"

# ---------------------------------------------------------------------------------
# 6. Copy, prune, pack, hash, and gate on size
# ---------------------------------------------------------------------------------

PACK_ARGS=(
  --mode build
  --stage "$(winpath "$STAGE")"
  --out "$(winpath "$OUT")"
  --arch "$ARCH"
  --platform-tag "$PLATFORM_TAG"
  --source-pkg "$(winpath "$SOURCE_PKG")"
  --dist "$(winpath "$CONSOLE_DIST")"
  --bundle "$(winpath "$EVIDENCE_BUNDLE")"
  --python-version "$PYTHON_VERSION"
  --psycopg-version "$PSYCOPG_VERSION"
  --python-report "$PYTHON_REPORT"
  --pip-report "$PIP_REPORT"
  --wheelhouse "$(winpath "$WHEELHOUSE")"
  --wheel-source "$WHEEL_SOURCE"
  --command-line "$COMMAND_LINE"
  --builder "scripts/deploy/build_lambda.sh"
  --packer-sha256 "$PACKER_SHA"
)
if [ "$STRIP_MAPS" -eq 1 ]; then PACK_ARGS+=(--strip-source-maps); fi

"$PYTHON" "$PACKER_WIN" "${PACK_ARGS[@]}"

# ---------------------------------------------------------------------------------
# 7. Re-check the finished artefact with a program that never saw the staging tree
# ---------------------------------------------------------------------------------
#
# bundle_manifest.py opens the zip and nothing else. If it disagrees with what was just
# packed, the disagreement is between the artefact and the build, which is exactly the
# class of failure a build log cannot report about itself. --strict makes the four
# determinism properties gating here, where they are ours to guarantee.

step "check     scripts/deploy/bundle_manifest.py --strict"
"$PYTHON" "$(winpath "$MANIFEST_TOOL")" "$(winpath "$OUT")" \
  --strict \
  --quiet \
  --require mainline_demo_api/app.py \
  --require psycopg_binary/ \
  --require web/assets/ \
  --require web/bundle/manifest.json \
  || die "the finished zip did not pass scripts/deploy/bundle_manifest.py"

if [ "$KEEP_STAGE" -eq 0 ]; then
  rm -rf "$STAGE"
else
  step "stage     $STAGE (kept)"
  step "packer    $PACKER (kept)"
fi

step "ok        $OUT"
