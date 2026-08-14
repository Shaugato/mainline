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
# SOURCE MAPS ARE STRIPPED BY DEFAULT, AND THE SERVED TREE SHIPS PRE-COMPRESSED
# -----------------------------------------------------------------------------
# This file used to argue that web/assets/*.js.map should stay, so a judge who opens
# DevTools on the demo sees real component names instead of `surface-Bv8EMlU6.js:1:20481`.
# That argument was sound while the package was a thing an operator downloaded. It stopped
# being sound the moment the same tree went behind a Lambda Function URL with
# `authorization_type = NONE`: every byte under web/ is then egress any caller on the
# internet can bill to this account at will, and the maps are 18 files, 2,586,960 B --
# 72.42 % of the 3,571,990 B served tree (measured 2026-08-13) -- for a debugging
# convenience nobody has used on the deployed URL. --keep-source-maps builds the
# debuggable package on demand; the default builds the one that gets deployed.
#
# The same build writes a `<name>.gz` sibling beside every compressible web/** entry:
# gzip level 9, mtime 0, no filename in the gzip header, so the zip stays
# byte-reproducible. 289,312 B of siblings against 2,586,960 B removed, and the largest
# object the handler can put on the wire falls from 1,554,168 B to 433,396 B identity /
# 124,127 B gzipped. That is interface I1 of docs/leads/cost-bound-plan.md; the serving
# half -- content negotiation, and a 404 for a direct request to a .gz path, because one
# set of bytes must not have two names -- belongs to static_site.py, not to this script.
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
# --console-transport IS REQUIRED, AND IT IS A DECLARATION
# --------------------------------------------------------
# It says what the console in dist/ is meant to DO ON LOAD -- live, replay or both -- and
# the packer refuses a dist that does something else. On 2026-08-14 the deployed artefact
# carried VITE_MAINLINE_API_BASE="" and VITE_MAINLINE_BUNDLE_URL="./bundle/", so every byte
# a judge saw was a recorded EvidenceBundle rather than the kernel the page was sitting on;
# the check that should have caught it keyed on the variable NAME and never on its VALUE,
# so it was unreachable. This flag is the thing the fixed check compares against, and it has
# no default on purpose: a guard that infers intent has to be right about intent.
#
# Usage:
#   scripts/deploy/build_lambda.sh --console-transport replay     # arm64, .env.demo as-is
#   scripts/deploy/build_lambda.sh --console-transport live       # a dist built with
#                                                                 # VITE_MAINLINE_API_BASE
#   scripts/deploy/build_lambda.sh --console-transport replay --arch x86_64
#   scripts/deploy/build_lambda.sh --console-transport replay --out /tmp/api.zip --keep-stage
#   scripts/deploy/build_lambda.sh --console-transport replay --keep-source-maps
#   scripts/deploy/build_lambda.sh --console-transport replay --refresh-wheels

set -euo pipefail

ARCH="arm64"
OUT=""
PYTHON=""
PSYCOPG_VERSION="3.3.4"
PLATFORM_TAG=""
WHEELHOUSE=""
KEEP_STAGE=0
KEEP_MAPS=0
REFRESH_WHEELS=0
PYTHON_VERSION="3.13"
# REQUIRED. No default: see the --console-transport block in usage() and ruling R4 of
# docs/leads/console-live-plan.md. A default here would be this script guessing, and the
# guess that shipped a REPLAY console to a live origin was exactly that.
CONSOLE_TRANSPORT=""

# Recorded verbatim in the sidecar manifest. Repo-relative on purpose: an absolute
# D:\... path in a tracked artefact is an `abs_windows_path` finding in
# scripts/submission/audit_public_readiness.py, and this manifest is quoted in
# evidence/deploy/lambda-bundle.json.
COMMAND_LINE="scripts/deploy/build_lambda.sh $*"

die() { printf 'build_lambda: %s\n' "$*" >&2; exit 1; }
step() { printf 'build_lambda: %s\n' "$*"; }

usage() {
  cat <<'USAGE_EOF'
build_lambda.sh --console-transport live|replay|both [options]

  --console-transport   REQUIRED. What the console artefact in dist/ is meant to DO ON
        live            LOAD. The packer refuses a dist that does something else.
        replay
        both              live    dist/ starts LIVE: a NON-EMPTY VITE_MAINLINE_API_BASE is
                                  compiled in. A dist carrying both sources satisfies this,
                                  because src/app/source-select.ts starts LIVE when both
                                  are present.
                          replay  dist/ starts REPLAY: a bundle URL and NO live source.
                          both    both compiled in, so the badge is switchable.

                        There is no default. On 2026-08-14 the deployed artefact carried
                        VITE_MAINLINE_API_BASE="" and VITE_MAINLINE_BUNDLE_URL="./bundle/",
                        every byte a judge saw was a recording, and no packaging step said
                        a word -- because the check keyed on the variable NAME and never on
                        its VALUE. This flag is the thing the check compares against.

  --arch arm64|x86_64   target architecture (default arm64)
  --out PATH            output zip (default out/lambda/mainline-demo-api-<arch>.zip)
  --python PATH         interpreter used for -m pip (default the repo .venv)
  --psycopg VERSION     psycopg and psycopg-binary pin (default 3.3.4)
  --platform TAG        override the measured pip platform tag
  --wheelhouse PATH     wheel cache (default out/lambda/wheels-<arch>)
  --refresh-wheels      re-download the wheels even if the wheelhouse has them
  --keep-source-maps    KEEP web/**/*.map (18 files, 2,586,960 B, 72.42 % of the served
                        tree). Stripped by default, because that tree is served from a
                        public Function URL and every byte of it is billable egress.
                        Use this to build a package whose stack traces map in DevTools.
  --strip-source-maps   accepted, and already the default; kept so a command line
                        recorded before 2026-08-13 still runs
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
    --console-transport) CONSOLE_TRANSPORT="${2:?--console-transport needs a value}"; shift 2 ;;
    --refresh-wheels) REFRESH_WHEELS=1; shift ;;
    --keep-source-maps) KEEP_MAPS=1; shift ;;
    # Stripping is the default as of 2026-08-13. This is not silently ignored: it says
    # so, because a flag that quietly does nothing is how an operator comes to believe a
    # build did something it did not.
    --strip-source-maps) step "note      --strip-source-maps is the default now; --keep-source-maps is the opt-out"; KEEP_MAPS=0; shift ;;
    --keep-stage) KEEP_STAGE=1; shift ;;
    -h|--help)  usage 0 ;;
    *)          die "unknown argument: $1 (try --help)" ;;
  esac
done

case "$ARCH" in
  arm64|x86_64) ;;
  *) die "--arch must be arm64 or x86_64, got '$ARCH'" ;;
esac

# Validated HERE as well as in the packer, so a missing declaration costs nothing: this
# runs before the interpreter is located, before pip, before anything is staged.
case "$CONSOLE_TRANSPORT" in
  live|replay|both) ;;
  "") die "--console-transport is REQUIRED and must be live, replay or both.
   It declares what the console artefact in dist/ is meant to DO ON LOAD, so this build can
   refuse a dist that does something else. It is not inferred: on 2026-08-14 the deployed
   artefact carried VITE_MAINLINE_API_BASE=\"\" and VITE_MAINLINE_BUNDLE_URL=\"./bundle/\",
   so every byte a judge saw was a recorded EvidenceBundle rather than the kernel the page
   was sitting on, and the packaging step printed a cheerful line and packaged it anyway.
   See --help, and docs/leads/console-live-plan.md ruling R4." ;;
  *) die "--console-transport must be live, replay or both, got '$CONSOLE_TRANSPORT'" ;;
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
step "transport $CONSOLE_TRANSPORT (declared; the packer refuses a dist that does otherwise)"
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

THE TRANSPORT THE CONSOLE CARRIES IS DECLARED, NOT INFERRED
-----------------------------------------------------------
--console-transport live|replay|both is REQUIRED in preflight and in build, and the
packer refuses a dist that does not do what was declared. It exists because the version
of this program that shipped on 2026-08-14 packaged a REPLAY console for an origin with a
live kernel behind it and printed a cheerful line about it: probe_console() keyed on the
variable NAME rather than its VALUE, .env.demo declares VITE_MAINLINE_API_BASE and leaves
it empty, so "configured" was always true and the warning branch was unreachable. See
probe_console and console_gate. A guard that infers intent has to be right about intent;
this one compares two things a human wrote down.

AND THE DECLARATION IS TESTED AGAINST THE PACKAGED BYTES, NOT ONLY AGAINST A DIRECTORY
---------------------------------------------------------------------------------------
Ruling R6 of docs/leads/package-and-verify-plan.md: the subject of the assertion is the
web/ entries of out/lambda/mainline-demo-api-<arch>.zip. dist/ is this program's INPUT and
<stage>/web is its SCRATCH; the zip is the thing that is uploaded, served and opened. So
after pack() the archive is re-opened through its own central directory, read by
probe_console_package, and held to the declaration a second time by package_console_gate --
which also refuses when the archive and the staging tree disagree, because "the copy, the
prune, the strip and the pack did not change what the console carries" is exactly the claim
a build log cannot make about itself. It is the same discipline bundle_manifest.py already
applies to the determinism properties, pointed at the one property that reached the founder.

Four modes:
  --mode preflight    refuse, before pip runs, if an input the package needs is absent, or
                      if dist/ does not carry the declared transport
  --mode wheelcheck   say whether a wheelhouse already holds both pinned wheels
  --mode build        copy, prune, strip, pre-compress, pack, hash, gate on size, on the
                      declared transport and on the PACKAGED console, write the manifest
  --mode consolecheck read a zip that already exists and say which source its console would
                      select, exiting 2 when that is not what --console-transport declares.
                      The build's own gate, with no staging tree, no pip and no network, so
                      an artefact that is already built -- including one that is already
                      deployed -- can be held to the rule without being rebuilt
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

# src/app/App.tsx compiles `buildId: typeof __MAINLINE_BUILD_ID__ === 'string' ?
# __MAINLINE_BUILD_ID__ : 'dev'`, and vite.config.ts defines that constant as
# JSON.stringify(process.env.MAINLINE_BUILD_ID ?? 'dev'), so the minifier folds the whole
# ternary down to ONE literal. A SECOND literal, buildId:"unknown", is the EMPTY constant
# in src/app/honesty.ts and is present in every build ever made -- measured on this tree,
# dist/assets/index-*.js carries buildId:"dev" AND buildId:"unknown". That is why the gate
# below keys on the PRESENCE of "dev" and never on "there is exactly one build id".
BUILD_ID_LITERAL = re.compile(r'buildId:"((?:[^"\\]|\\.)*)"')

# What vite.config.ts substitutes when MAINLINE_BUILD_ID was not supplied. An artefact
# carrying it cannot name itself, so a screenshot taken from it cannot name the artefact it
# came from -- which docs/deploy/console-build.md sec 1 says is the entire reason the field
# exists. Measured 2026-08-14: the DEPLOYED artefact carries buildId:"dev".
DEV_BUILD_ID = "dev"

# The two build-time variables src/app/source-select.ts reads, by the source each selects.
SOURCE_VARIABLE = {"live": "VITE_MAINLINE_API_BASE", "replay": "VITE_MAINLINE_BUNDLE_URL"}

# The intended transport, DECLARED on the command line and never inferred. A guard that
# infers intent has to be right about intent; this one compares two things a human wrote
# down -- the flag, and the literals the compiler put in the artefact.
#
# The three declarations are the three things selectSource() can do, transcribed:
#
#   live    the artefact must START live. selectSource returns `initial: live` whenever a
#           non-empty VITE_MAINLINE_API_BASE is compiled in, whether or not a bundle URL is
#           there too ("LIVE is the default because a demo that can reach the database
#           should"), so a both-carrying artefact satisfies this and a replay-only one
#           cannot.
#   replay  the artefact must START replay, which means it carries a bundle URL and NO live
#           source: with both compiled in, selectSource starts LIVE, so "replay" would be a
#           false description of what the page does on load.
#   both    the artefact must be SWITCHABLE -- both sources compiled in, one badge, one
#           control. This is strictly more than `live` asks for.
CONSOLE_TRANSPORTS = ("live", "replay", "both")

# Every declaration whose artefact STARTS live, and is therefore an artefact a judge could
# be looking at while it talks to a kernel. Ruling R5 holds these to the build-id gate.
LIVE_TRANSPORTS = ("live", "both")

CONSOLE_LIVE_BUILD = (
    "cd verticals/mainline/apps/console && pnpm install --frozen-lockfile && "
    "VITE_MAINLINE_API_BASE=<origin> MAINLINE_BUILD_ID=<id> pnpm exec vite build --mode demo"
)

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

        # Ruling R4, and it runs HERE -- before pip touches the network -- for the same
        # reason the missing-dist check does: a transport the operator did not get is
        # knowable from the tree, and learning it after a 7 MB download and a 200-file
        # install wastes a minute the build did not have to spend.
        for line in console_gate(probe_console(args.dist), args.console_transport):
            say("console   WARNING %s" % line)

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


def trimmed(value):
    """src/app/source-select.ts:104, transcribed. AN EMPTY STRING IS UNSET.

    Three lines, and the whole defect this file was reopened for lives in them. The console
    has always read the two source variables through this rule; the packer used to read them
    by NAME. So the artefact and the program that packages it disagreed about what "carries a
    live source" means, and the disagreement shipped.
    """
    if value is None:
        return None
    text = value.strip()
    return None if text == "" else text


def probe_console(root):
    """Report which sources the console artefact EFFECTIVELY carries, and what it calls itself.

    `root` is the directory that holds `assets/` -- `dist/` before pip runs, `<stage>/web`
    after the copy -- so the same probe answers for the tree that was BUILT and for the tree
    that SHIPS, and a disagreement between the two is a staging bug this program can name
    rather than a difference nobody looked for.

    THE DEFECT THIS FUNCTION WAS REWRITTEN AROUND (measured 2026-08-14)
    ------------------------------------------------------------------
    The previous version collected `found.setdefault(key, value)` -- keyed on the variable
    NAME, with no test on the VALUE -- and its caller branched on `if console["configured"]`.
    `.env.demo` DECLARES VITE_MAINLINE_API_BASE and leaves it EMPTY, on purpose, so vite
    inlines `VITE_MAINLINE_API_BASE:""` into every build and `found` was never empty. The
    warning branch was therefore unreachable: dead code that had never executed and could
    not. The deployed artefact is the proof -- it carries

        VITE_MAINLINE_API_BASE:""   VITE_MAINLINE_BUNDLE_URL:"./bundle/"   buildId:"dev"

    the packer printed a cheerful `console VITE_MAINLINE_API_BASE=(empty),
    VITE_MAINLINE_BUNDLE_URL=./bundle/`, and a judge opening the demo URL got a REPLAY
    console -- every byte on screen a recording -- on an origin with a live kernel behind it.

    So this reports the EFFECTIVE sources, through the same `trimmed()` rule `selectSource`
    applies, and it reports `initial` and `switchable` by the same reasoning selectSource
    uses: one rule written twice rather than two rules that can drift apart. `console_gate`
    turns that report into a refusal.

    Only *.js is read, so the *.js.gz siblings written beside them are not scanned twice and
    are not read as text.
    """
    literals = {}
    build_ids = {}
    modes = set()
    assets = os.path.join(root, "assets")
    if not os.path.isdir(assets):
        return {
            "literals": {},
            "sources": {"live": None, "replay": None},
            "effective": [],
            "initial": None,
            "switchable": False,
            "build_ids": [],
            "names_itself": False,
            "mode": None,
            "scanned": 0,
            "note": "no assets/ directory under %s" % root,
        }
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
            literals.setdefault(key, {}).setdefault(value, []).append(name)
        for value in BUILD_ID_LITERAL.findall(text):
            build_ids.setdefault(value, []).append(name)
        modes.update(ENV_MODE.findall(text))

    return _classify(literals, build_ids, modes, scanned, None)


def _classify(literals, build_ids, modes, scanned, note):
    """selectSource, transcribed ONCE, over literals gathered from any tree.

    Both readers end here -- the directory one above, which answers for `dist/` and for
    `<stage>/web`, and `probe_console_package` below, which answers for the finished zip.
    One rule in one place: a staging tree and an artefact judged by two transcriptions of
    the same three lines is the drift this file was reopened for, one level up.
    """
    sources = {}
    for kind in ("live", "replay"):
        chosen = None
        for value in sorted(literals.get(SOURCE_VARIABLE[kind], {})):
            text = trimmed(value)
            if text is not None:
                chosen = text
                break
        sources[kind] = chosen

    # selectSource, transcribed: with both compiled in the console starts LIVE and shows a
    # control; with one, that one and no control; with neither, NO SOURCE on every surface.
    initial = "live" if sources["live"] else ("replay" if sources["replay"] else None)
    return {
        "literals": dict(
            (key, sorted(values)) for key, values in sorted(literals.items())
        ),
        "sources": sources,
        "effective": [kind for kind in ("live", "replay") if sources[kind]],
        "initial": initial,
        "switchable": bool(sources["live"] and sources["replay"]),
        "build_ids": sorted(build_ids),
        "names_itself": DEV_BUILD_ID not in build_ids,
        "mode": sorted(modes)[0] if modes else None,
        "scanned": scanned,
        "note": note or (
            "effective sources are read through the same empty-is-unset rule "
            "src/app/source-select.ts applies, so a compiled-in VITE_MAINLINE_API_BASE=\"\" "
            "is UNSET here exactly as it is in the browser. initial and switchable are what "
            "selectSource would return for these literals. build_ids lists every buildId "
            "literal in the artefact; \"unknown\" is honesty.ts's EMPTY constant and is "
            "expected, \"dev\" means MAINLINE_BUILD_ID was not supplied."
        ),
    }


def probe_console_package(package):
    """The same reading, taken from the FINISHED ZIP's central directory. Ruling R6.

    THE LAST WORD BELONGS TO THE ARTEFACT. `probe_console` answers for `dist/`, which is
    this program's INPUT, and for `<stage>/web`, which is its SCRATCH. What a judge's
    browser executes is the bytes inside out/lambda/mainline-demo-api-<arch>.zip, and the
    three are the same tree only if every step between them did what it says. "The copy,
    the prune, the strip and the pack did what they say" is exactly the claim a build log
    cannot make about itself, which is why bundle_manifest.py re-opens the zip rather than
    trusting the staging census -- this is that same discipline applied to the one property
    that reached the founder.

    verticals/mainline/apps/demo-api/tests/test_response_contract.py:880-882 has already
    ruled, for a cost question, that the packer's input tree is deliberately NOT accepted as
    a stand-in for the deployed tree. A transport question deserves the same answer.

    Only web/assets/*.js is read. The *.js.gz siblings are the same bytes under a name
    interface I1 refuses to serve directly, so reading them as text would count one artefact
    twice; and an entry outside web/assets/ is not something vite's `define` writes into, so
    a build that put its chunks somewhere else reads here as NO SOURCE and is refused, which
    is the direction a guard should fail in.
    """
    literals = {}
    build_ids = {}
    modes = set()
    scanned = 0
    archive = zipfile.ZipFile(package)
    try:
        names = sorted(
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
            and info.filename.startswith("web/assets/")
            and info.filename.endswith(".js")
        )
        for name in names:
            scanned += 1
            text = archive.read(name).decode("utf-8", "replace")
            for key, value in ENV_LITERAL.findall(text):
                literals.setdefault(key, {}).setdefault(value, []).append(name)
            for value in BUILD_ID_LITERAL.findall(text):
                build_ids.setdefault(value, []).append(name)
            modes.update(ENV_MODE.findall(text))
    finally:
        archive.close()
    return _classify(
        literals,
        build_ids,
        modes,
        scanned,
        "read from the central directory of %s, over its web/assets/*.js entries: the bytes "
        "a browser executes, not the tree they were packed from. Everything else in this "
        "record means what it means for the directory probe." % os.path.basename(package),
    )


def transport_satisfied(console, transport):
    """Does this reading DO what `transport` declares? One test, called from both gates."""
    if transport == "both":
        return console["switchable"]
    return console["initial"] == transport


def console_gate(console, transport):
    """REFUSE a dist that does not carry the transport the operator declared. Ruling R4.

    A packaging step that produces a REPLAY console for an origin with a live kernel behind
    it must FAIL, not warn. The machinery to notice already existed and was measuring the
    wrong thing (see probe_console); this is the same machinery pointed at the value, given
    something to compare against, and moved from `say` to `refuse`.

    The declaration is REQUIRED and is never inferred. `transport` is one of
    CONSOLE_TRANSPORTS and says what the operator intends the artefact to DO ON LOAD; the
    literals say what it will do. This compares them, names the difference, and names the
    command that would produce the artefact that was asked for.

    Returns the advisory lines. Refusals go through refuse(): main() prints them to stderr
    and exits 2, and a build that has already written its zip deletes it, so a refused
    package is never left where a later step could upload it.
    """
    warnings = []

    if console["scanned"] == 0:
        refuse(
            "NO CONSOLE ASSETS",
            "no assets/*.js were found to read (%s), so this program cannot tell which "
            "source the console carries and must not vouch for it. A dist/ with no "
            "JavaScript is not a built site. Build it with:  %s"
            % (console["note"], PNPM_BUILD),
        )
        return warnings

    # A key that carries two different values across chunks is two builds' output in one
    # tree. Whichever one selectSource reads at runtime, the artefact is not the artefact
    # anybody asked for, and no declaration can be true of both halves.
    for key in sorted(console["literals"]):
        values = console["literals"][key]
        distinct = sorted(set(t for t in (trimmed(v) for v in values) if t is not None))
        if len(distinct) > 1 or (distinct and len(values) > len(distinct)):
            refuse(
                "MIXED CONSOLE",
                "%s is compiled into this dist with more than one value (%s). That is two "
                "builds' chunks in one tree, and no --console-transport declaration can be "
                "true of both. Delete dist/ and rebuild it in one command."
                % (key, ", ".join('"%s"' % value for value in values)),
            )

    if console["initial"] is None:
        refuse(
            "CONSOLE NO SOURCE",
            "this dist carries neither VITE_MAINLINE_API_BASE nor VITE_MAINLINE_BUNDLE_URL "
            "with a NON-EMPTY value (import.meta.env MODE=%s; literals %s). "
            "src/app/source-select.ts treats an empty string as unset, so this site loads "
            "and then renders NO SOURCE on every surface: a website with no data. Rebuild "
            "dist/ with:  %s" % (console["mode"], _literal_report(console), PNPM_BUILD),
        )
        return warnings

    satisfied = transport_satisfied(console, transport)
    if transport == "both":
        wanted = "both sources compiled in, so the badge is switchable"
    else:
        wanted = "the console starts %s on load" % transport.upper()

    if not satisfied:
        refuse(
            "CONSOLE TRANSPORT",
            "--console-transport %s was declared, which requires that %s. This dist carries "
            "%s (%s), so selectSource would start it %s and switchable would be %s. %s"
            % (
                transport,
                wanted,
                ", ".join(console["effective"]) or "no source",
                _literal_report(console),
                console["initial"].upper(),
                "true" if console["switchable"] else "false",
                _transport_remedy(console, transport),
            ),
        )

    # Ruling R5. An artefact that cannot name itself is the same class of defect as one that
    # cannot name its source, and both shipped in the same build for the same reason: a
    # variable nobody supplied and nothing checked.
    if not console["names_itself"]:
        detail = (
            'this dist carries buildId:"%s" (build ids found: %s), so the honesty chrome '
            "cannot name the artefact a screenshot came from. Supply MAINLINE_BUILD_ID when "
            "you build dist/:  %s"
            % (
                DEV_BUILD_ID,
                ", ".join('"%s"' % value for value in console["build_ids"]),
                CONSOLE_LIVE_BUILD,
            )
        )
        if transport in LIVE_TRANSPORTS:
            refuse("CONSOLE BUILD ID", detail)
        else:
            # A replay artefact is the local/CI build: .github/actions/build-demo-package
            # leaves MAINLINE_BUILD_ID unset ON PURPOSE, because inlining a run id would move
            # the content hash of assets/index-<hash>.js on every run and unpin the byte
            # counts the cost ratchets read. That is a good reason, and it is only a good
            # reason for an artefact nobody deploys.
            warnings.append(detail)

    return warnings


def _literal_report(console):
    """The compiled-in literals, verbatim, with the empty ones visible as empty."""
    rows = []
    for key in sorted(console["literals"]):
        values = console["literals"][key]
        rows.append(
            "%s=%s" % (key, ", ".join(value if value else "(empty)" for value in values))
        )
    return "; ".join(rows) or "no VITE_MAINLINE_* literals at all"


def _transport_remedy(console, transport):
    """Name the command that produces the artefact that was asked for."""
    if transport in ("live", "both") and not console["sources"]["live"]:
        return (
            "VITE_MAINLINE_API_BASE is what selects the LIVE source and .env.demo leaves it "
            "EMPTY on purpose, so it has to arrive in the ENVIRONMENT:  %s  -- and it is "
            "worth reading the compiled value back out of dist/, because on Git Bash a bare "
            "/ becomes C:/Program Files/Git/ through MSYS path conversion "
            "(docs/deploy/console-build.md sec 1, observed in a real artefact 2026-08-10)."
            % CONSOLE_LIVE_BUILD
        )
    if transport == "replay" and console["sources"]["live"]:
        return (
            "this dist DOES carry a live source (VITE_MAINLINE_API_BASE=%s), so selectSource "
            "starts it LIVE and REPLAY is one control away rather than what a judge first "
            "sees. Declare --console-transport both if that is what you meant, or build "
            "without VITE_MAINLINE_API_BASE in the environment if it is not."
            % console["sources"]["live"]
        )
    if transport == "both" and not console["sources"]["replay"]:
        return (
            "VITE_MAINLINE_BUNDLE_URL is what selects the REPLAY source; .env.demo sets it to "
            "./bundle/ and this build did not get it. Declare --console-transport live if a "
            "live-only artefact is what you meant."
        )
    return "Declare the transport this dist actually carries, or rebuild dist/."


#: The reading's fields that say WHAT THE CONSOLE WILL DO. `scanned` and `note` are left
#: out on purpose: they describe the reading, not the artefact, and a gate that compared
#: them would go red for a difference nobody can act on.
CONSOLE_MEANING = ("literals", "sources", "effective", "initial", "switchable", "build_ids", "mode")


def package_console_gate(staged, packaged, transport):
    """Hold the PACKAGED BYTES to the declaration, and to the tree they were packed from.

    Ruling R6 of docs/leads/package-and-verify-plan.md: *the assertion goes on the `web/`
    entries of out/lambda/mainline-demo-api-*.zip, not on console/dist and not on source.*
    The defect that reached the founder was a packaged artefact, and every check that ran
    over an input tree passed over it.

    Two questions, asked separately because they fail for different reasons and a reader
    deserves to know which one happened:

      * does the ARTEFACT do what --console-transport declared? That is console_gate's
        question asked of the zip. It would have caught 2026-08-14 whichever tree the
        earlier probe had been pointed at, and it is the only form of the question that
        stays true after the copy, the prune, the strip and the pack have all run;
      * does the artefact AGREE with the tree it was packed from? A disagreement is a
        packing defect -- a filter, a prune or a copy that changed what the console
        carries -- and it is invisible to any check that reads only one of the two.

    Nothing here is a second transcription of selectSource: both readings come out of
    `_classify`, and the declaration is tested by `transport_satisfied`, which is the same
    function `console_gate` calls.
    """
    if packaged["scanned"] == 0:
        refuse(
            "PACKAGE NO CONSOLE ASSETS",
            "the finished zip carries no web/assets/*.js at all (%s), so this program "
            "cannot say what the console it just packaged would do, and must not vouch for "
            "it. The staging tree read %d such file(s), so the loss happened between the "
            "stage and the archive." % (packaged["note"], staged["scanned"]),
        )
        return

    differing = [field for field in CONSOLE_MEANING if staged[field] != packaged[field]]
    if differing:
        refuse(
            "PACKAGE CONSOLE DRIFT",
            "the packaged web/assets/*.js do not carry what the staging tree did: %s. The "
            "staging tree reads %s (starts %s); the archive reads %s (starts %s). One of "
            "them is not the artefact anybody asked for and the difference was introduced "
            "by this program, between the copy and the archive."
            % (
                ", ".join(differing),
                ", ".join(staged["effective"]) or "no source",
                (staged["initial"] or "nowhere").upper(),
                ", ".join(packaged["effective"]) or "no source",
                (packaged["initial"] or "nowhere").upper(),
            ),
        )

    if not transport_satisfied(packaged, transport):
        refuse(
            "PACKAGE CONSOLE TRANSPORT",
            "--console-transport %s was declared, but the web/assets/*.js INSIDE THE ZIP "
            "carry %s (%s), so the console this package serves would start %s and "
            "switchable would be %s. This is the artefact, read through its own central "
            "directory -- not dist/, not the staging tree. On 2026-08-14 a package in "
            "exactly this state was uploaded, served, and opened by the founder: every byte "
            "on screen was a recording from web/bundle/ while a live kernel sat behind the "
            "same origin. %s"
            % (
                transport,
                ", ".join(packaged["effective"]) or "no source",
                _literal_report(packaged),
                (packaged["initial"] or "nowhere").upper(),
                "true" if packaged["switchable"] else "false",
                _transport_remedy(packaged, transport),
            ),
        )


def consolecheck(args):
    """Read a zip that already exists and say which source its console would select.

    The build's own gate, applied to any artefact on disk, with no staging tree, no pip and
    no network. This is how a package that is ALREADY BUILT -- including one that is already
    deployed -- can be held to the rule that would refuse it now, without rebuilding it and
    without losing the bytes a judge actually met.

    Exit 0 when the artefact does what --console-transport declares, 2 when it does not.
    """
    if not os.path.isfile(args.package):
        sys.stderr.write("build_lambda: --package %s is not a file\n" % args.package)
        return 1
    packaged = probe_console_package(args.package)
    reading = {
        "artifact": os.path.basename(args.package),
        "sha256": sha256_file(args.package),
        "transport_declared": args.console_transport,
        "console": packaged,
    }
    say("package   %s" % reading["artifact"])
    say("sha256    %s" % reading["sha256"])
    say_console(packaged, args.console_transport, [])
    if packaged["scanned"] == 0:
        refuse(
            "PACKAGE NO CONSOLE ASSETS",
            "%s carries no web/assets/*.js entries, so there is nothing to read and this "
            "program will not vouch for it." % reading["artifact"],
        )
    elif not transport_satisfied(packaged, args.console_transport):
        refuse(
            "PACKAGE CONSOLE TRANSPORT",
            "--console-transport %s was declared, but the web/assets/*.js inside %s carry "
            "%s (%s), so the console this package serves would start %s and switchable "
            "would be %s. %s"
            % (
                args.console_transport,
                reading["artifact"],
                ", ".join(packaged["effective"]) or "no source",
                _literal_report(packaged),
                (packaged["initial"] or "nowhere").upper(),
                "true" if packaged["switchable"] else "false",
                _transport_remedy(packaged, args.console_transport),
            ),
        )
    reading["refusals"] = list(refusals)
    reading["verdict"] = "REFUSED" if refusals else "ACCEPTED"
    if args.report:
        handle = open(args.report, "w", encoding="utf-8")
        try:
            json.dump(reading, handle, indent=2, sort_keys=True)
            handle.write("\n")
        finally:
            handle.close()
        say("report    %s" % os.path.basename(args.report))
    if refusals:
        for line in refusals:
            sys.stderr.write("build_lambda: %s\n" % line)
        return 2
    say("console   ACCEPTED: this artefact starts %s, as declared" % args.console_transport.upper())
    return 0


def say_console(console, transport, warnings):
    """The reading, printed the same way by --mode build and by --mode consolecheck.

    The EFFECTIVE sources, never the present keys. The line this replaced printed
    `VITE_MAINLINE_API_BASE=(empty), VITE_MAINLINE_BUNDLE_URL=./bundle/` and read as
    configuration; it was a REPLAY-only artefact, and nothing in the output said so.
    """
    say("console   declared  --console-transport %s" % transport)
    say(
        "console   effective %s  (selectSource would start it %s, switchable %s)"
        % (
            ", ".join(console["effective"]) or "NO SOURCE",
            (console["initial"] or "nowhere").upper(),
            "true" if console["switchable"] else "false",
        )
    )
    say("console   literals  %s" % _literal_report(console))
    say(
        "console   buildId   %s"
        % (", ".join(console["build_ids"]) or "no buildId literal in the artefact")
    )
    for line in warnings:
        say("console   WARNING   %s" % line)


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

    # Re-probed from the STAGING tree, not from dist/. preflight already gated the input
    # tree and main() returns before this on a refusal, so the only way this fires is a
    # staging bug -- a copy that changed which source the artefact carries. That is exactly
    # the class of failure a build log cannot report about itself, and it is cheap to ask.
    console = probe_console(os.path.join(stage, "web"))
    console_warnings = console_gate(console, args.console_transport)
    console["transport_declared"] = args.console_transport

    entries, unzipped = pack(stage, args.out)
    zipped = os.path.getsize(args.out)
    digest = sha256_file(args.out)

    # Ruling R6: the ARTEFACT has the last word, and it is asked through its own central
    # directory. Everything above this line read a tree on the filesystem; from here down
    # the subject is the zip whose sha256 Terraform is about to hash and whose bytes a
    # judge's browser will execute. A refusal here deletes the file (see main()), so a
    # package this program will not vouch for is never left where a later step could
    # upload it.
    packaged = probe_console_package(args.out)
    package_console_gate(console, packaged, args.console_transport)
    console["packaged"] = packaged

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
    say_console(console, args.console_transport, console_warnings)
    # Printed even when it agrees, and printed SECOND, so the last thing a reader sees about
    # the console is what the ARCHIVE carries. A build log whose only console line described
    # a directory is how "the tree I built" came to stand in for "the bytes I shipped".
    say(
        "package   console %d web/assets/*.js in the archive: effective %s (starts %s)"
        % (
            packaged["scanned"],
            ", ".join(packaged["effective"]) or "NO SOURCE",
            (packaged["initial"] or "nowhere").upper(),
        )
    )
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
    parser.add_argument(
        "--mode", default="build", choices=("preflight", "wheelcheck", "build", "consolecheck")
    )
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
    # REQUIRED in preflight and build. No default, deliberately: a default would be this
    # program guessing what the operator meant, and the guess that shipped a REPLAY console
    # to a live origin was exactly that. Ruling R4.
    parser.add_argument("--console-transport", default="", choices=("",) + CONSOLE_TRANSPORTS)
    # --mode consolecheck only: the FINISHED zip to read, and where to record the reading.
    # There is no --stage and no --dist here on purpose. Ruling R6 makes the artefact the
    # subject, and a mode that would accept a directory as a stand-in for a package is the
    # substitution that let a REPLAY console through in the first place.
    parser.add_argument("--package", default="")
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    if args.mode == "wheelcheck":
        need(args, ["wheelhouse", "psycopg_version"])
        return wheelcheck(args)

    if args.mode == "consolecheck":
        need(args, ["package"])
        require_transport(args)
        return consolecheck(args)

    need(args, ["source_pkg", "dist", "bundle"])
    require_transport(args)
    preflight(args)
    if refusals:
        for line in refusals:
            sys.stderr.write("build_lambda: %s\n" % line)
        return 2
    if args.mode == "preflight":
        say(
            "preflight ok: handler package, console dist/ and evidence bundle are all "
            "present, and dist/ carries the declared --console-transport %s"
            % args.console_transport
        )
        return 0

    need(args, ["stage", "out", "arch", "platform_tag"])
    manifest = build(args)
    if refusals:
        for line in refusals:
            sys.stderr.write("build_lambda: %s\n" % line)
        # A refused build must leave nothing behind that a later step could upload. The
        # size gate and the packaged-console gate both fire AFTER the zip is written -- they
        # can only be measured on the finished file -- so the finished file is removed here.
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


def require_transport(args):
    """--console-transport is REQUIRED and is never inferred. Ruling R4, unchanged.

    Lifted out of main() so --mode consolecheck asks for it in the same words: a flag that
    is mandatory in one mode and optional in another is a flag an operator learns to leave
    off.
    """
    if not args.console_transport:
        sys.stderr.write(
            "build_lambda: --console-transport is REQUIRED in --mode %s and must be one of "
            "%s.\n"
            "build_lambda: It declares what the console artefact is meant to DO ON LOAD, so "
            "the packer can refuse a dist that does something else. It is not inferred: the "
            "artefact that shipped on 2026-08-14 carried VITE_MAINLINE_API_BASE=\"\" and "
            "VITE_MAINLINE_BUNDLE_URL=\"./bundle/\", every byte on screen was a recording, "
            "and no packaging step said a word.\n"
            "build_lambda:   live    the artefact starts LIVE (a non-empty "
            "VITE_MAINLINE_API_BASE is compiled in)\n"
            "build_lambda:   replay  the artefact starts REPLAY (a bundle URL, and NO live "
            "source)\n"
            "build_lambda:   both    both are compiled in and the badge is switchable\n"
            % (args.mode, "|".join(CONSOLE_TRANSPORTS))
        )
        raise SystemExit(1)


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
  --bundle "$(winpath "$EVIDENCE_BUNDLE")" \
  --console-transport "$CONSOLE_TRANSPORT"

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
  --console-transport "$CONSOLE_TRANSPORT"
)
if [ "$KEEP_MAPS" -eq 1 ]; then PACK_ARGS+=(--keep-source-maps); fi

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
