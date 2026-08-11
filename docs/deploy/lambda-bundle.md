<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The deployment package — one zip that is the whole demo

**Owner:** `w2-lambda-bundle`.
**Artefacts:** `out/lambda/mainline-demo-api-arm64.zip`, `out/lambda/mainline-demo-api-x86_64.zip`,
each with a `.zip.json` sidecar Terraform reads.
**Built by:** `scripts/deploy/build_lambda.sh` (POSIX) and `scripts/deploy/build_lambda.ps1`
(Windows) — twins that produce a **byte-identical** zip.
**Checked by:** `scripts/deploy/bundle_manifest.py`, which reads the finished zip and nothing else.
**Evidence:** `evidence/deploy/lambda-bundle.json`. Every number on this page came from a
command in that file.

---

## 1. What is in it, and why it is four things now

Decision **D1** — `docs/leads/ship-final.md` §1.4 — made the demo URL a public **Lambda
Function URL**, because this AWS account cannot create a CloudFront distribution
(`AccessDenied: Your account must be verified…`). One origin therefore serves the console,
the evidence bundle and the API, and this zip is that whole origin.

```
mainline-demo-api-arm64.zip
├── mainline_demo_api/           11 files    283 402 B   the handler package
├── psycopg/                     85 files    713 024 B   the pure-Python driver
├── psycopg_binary/              10 files  8 093 535 B   compiled libpq bindings
├── psycopg_binary.libs/         16 files 15 673 536 B   the .so files those need
├── psycopg-3.3.4.dist-info/      4 files     12 064 B
├── psycopg_binary-3.3.4.dist-info/ 5 files   16 806 B
└── web/                         75 files  3 571 990 B
    ├── index.html                                       GET /            (SPA shell)
    ├── assets/…                                         GET /assets/*    (immutable)
    ├── .vite/manifest.json                              Vite's build map, unrequested
    └── bundle/                  26 files    184 312 B   GET /bundle/*    (REPLAY source)
```

`web/` is the **contents** of `verticals/mainline/apps/console/dist/`; `web/bundle/` is
`verticals/mainline/apps/console/fixtures/bundles/demo-cloud/`, the EvidenceBundle captured
by `scripts/deploy/capture_demo_bundle.py` and recorded in `evidence/deploy/bundle-capture.json`
(`verdict: CAPTURED AND VERIFIED`, 24 files agree, manifest digest `7772131b…`).

The handler finds the site through **one contract, owned by W1**:
`$MAINLINE_WEB_ROOT`, set to `/var/task/web` by `infra/modules/demo-api/main.tf:145` from
`var.web_root`, and read by `mainline_demo_api.static_site.web_root()`. `/var/task` is
`$LAMBDA_TASK_ROOT`; `web/` is where this build puts `dist/`. Nothing else in the package
depends on where it is unpacked, because the console is built with `base: './'` and routes
on the URL hash (`vite.config.ts:71`), so it is correct from any prefix — including a
Function URL root — with no rebuild.

**No boto3.** The runtime ships one, and `db.py` signs its single SSM `GetParameter` call
itself, so the package's behaviour does not depend on which boto3 the runtime happens to
carry this month. No web framework. No `tzdata`. No `__pycache__`, no `RECORD`.

### Two numbers, per architecture, and the ceilings they are under

| | zipped | ceiling | unzipped | ceiling | entries |
|---|---|---|---|---|---|
| **arm64** | 7 989 296 B (7.62 MB) | 52 428 800 (50 MB) | 28 364 357 B (27.05 MB) | 262 144 000 (250 MB) | 206 |
| **x86_64** | 6 403 826 B (6.11 MB) | 52 428 800 (50 MB) | 23 598 529 B (22.51 MB) | 262 144 000 (250 MB) | 205 |

Headroom is 44.4 MB zipped and 233.8 MB unzipped on arm64. Both limits are **asserted on
every build**, not assumed: the builder refuses, and deletes the zip it just wrote, rather
than leave an artefact that cannot be uploaded.

---

## 2. Why `psycopg-binary`, and not `psycopg[c]`

`psycopg[c]` installs `psycopg-c`, a **source** distribution that compiles against `libpq`
headers at install time. That needs a compiler and the PostgreSQL development headers *for
the target*, which a Windows build machine cross-compiling for `aarch64` Linux does not
have and should not acquire. `psycopg[binary]` installs `psycopg-binary`, a prebuilt
manylinux wheel that vendors `libpq` and its dependencies into `psycopg_binary.libs/`.

Two consequences the build depends on:

* `pip --platform` **refuses to resolve an extra marker**, so `psycopg[binary]` cannot be
  used for a cross-platform target build at all. Both distributions are named explicitly,
  with `--no-deps`, at the same pin.
* The wheel is per-architecture, and **the tags are measured, not guessed** (2026-08-10,
  this machine):

| requested platform | resolved |
|---|---|
| `manylinux2014_x86_64` | `psycopg_binary-3.3.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` |
| `manylinux2014_aarch64` | **ERROR: no matching distribution** — aarch64 stops at 3.2.13 for that tag |
| `manylinux_2_28_aarch64` | `psycopg_binary-3.3.4-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` |

So the arm64 build asks for glibc **2.28**. Lambda's `python3.13` runtime is Amazon Linux
2023, glibc 2.34, which satisfies it; the container transcript is in
`infra/modules/demo-api/README.md`. That the right objects actually arrived is checked
after the fact by reading the ELF header of every `.so` in the zip: arm64 → 18 objects, all
`0xB7 EM_AARCH64`; x86_64 → 17, all `0x3E EM_X86_64`.

---

## 3. The determinism argument

Terraform decides whether to redeploy from `source_code_hash = filebase64sha256(var.package_path)`
(`infra/modules/demo-api/main.tf:254`). A zip whose bytes move because the *clock* moved
makes every `terraform plan` show a Lambda update, which trains an operator to skim the plan
four days before a deadline. So the hash must be a statement about the **content** and
nothing else.

Six things are fixed, and all six are re-read out of the finished archive by
`bundle_manifest.py --strict`:

| property | value | what it would otherwise leak |
|---|---|---|
| `ZipInfo.date_time` | `(1980, 1, 1, 0, 0, 0)` | the build clock |
| entry order | sorted on the UTF-8 bytes of the relative path | the filesystem's `readdir` order (NTFS ≠ ext4) |
| compression | `ZIP_DEFLATED`, `compresslevel=9` | the writer's default, which has changed between Python versions |
| `external_attr` | `0o755` for `*.so*`/`*.dylib`, `0o644` otherwise | the umask, and Windows' absent mode bits |
| `create_system` | `3` (Unix) | the build OS |
| directory entries | none written | `os.walk` order and empty-directory churn |

Two more fix the *inputs* rather than the writer: `pip --no-compile`, so no `.pyc` carries a
source mtime; and `pip install --no-index --find-links <wheelhouse>`, so the wheels are
copied from bytes already on disk rather than re-resolved against PyPI on each build.

**Measured, three builds per architecture, across both shells and three output directories:**

```
arm64   c85d7f00a5576e412dfb0124ad93c40104757011179d0029361d9a8db5b8a4b0   (x3)
x86_64  bd7f188df9118085e6520ed7d8893e353cd7d82531ced370fabaa1b241d709ba   (x3)
```

### The two builders are the same program

The staging/pruning/packing program is embedded in both `build_lambda.sh` (heredoc) and
`build_lambda.ps1` (here-string). Both normalise it to LF — this repository is checked out
on Windows, and a heredoc keeps the trailing newline while a here-string drops it, so the
PowerShell side appends one — and both **print its sha256**:

```
build_lambda: packer    sha256 eab069d1eb460c71b01d506acdab6eabfd53713cef4beafa34953c9c47e30711
```

Two builders that print the same *zip* hash could still be two different programs that agree
today. This makes the agreement itself checkable, in one line of output, from either shell.
It is embedded rather than shipped as a third file because a shared helper that one shell
could load and the other could not is a reproducibility bug waiting to happen.

---

## 4. Source maps are kept, on purpose

`web/assets/*.js.map` is **18 files, 2 586 960 B** — about 660 KB of the compressed package.
They stay.

A judge who opens DevTools on the demo should see component names and real stack frames
rather than `surface-Bv8EMlU6.js:1:20481`. This project's entire argument is that its claims
are checkable by the person reading them; shipping a deliberately unreadable bundle to save
bytes we are not short of would contradict it in the one place a judge is most likely to
look. `static_site.py` already names `.map` explicitly in its media-type table so DevTools
accepts them.

The escape hatch is measured, not hypothetical:

| | entries | zipped | unzipped |
|---|---|---|---|
| arm64, maps kept | 206 | 7 989 296 | 28 364 357 |
| arm64, `--strip-source-maps` | 188 | 7 328 963 | 25 777 397 |

`sha256 6b35e89f25a1d273bf3d119b634323a0653c6f4e440f23072de8b33ecccb1f49` for the stripped
build — a different artefact, deterministic in its own right.

---

## 5. Building it on a clean machine

Prerequisites: **Python 3.13** (the repository `.venv` is used automatically), and a
**built console**. Nothing else — no `uv`, no `just`, no Docker, no AWS credentials. The
build never contacts AWS.

```bash
# 1. the console, once (node v24.14.0, pnpm 11.5.3 measured on this machine)
cd verticals/mainline/apps/console
pnpm install --frozen-lockfile
pnpm exec vite build --mode demo          # see docs/deploy/console-build.md

# 2. the package, from the repository root
scripts/deploy/build_lambda.sh                      # arm64, the deployed default
scripts/deploy/build_lambda.sh --arch x86_64
```

or, on Windows:

```powershell
pwsh scripts/deploy/build_lambda.ps1
pwsh scripts/deploy/build_lambda.ps1 -Arch x86_64
```

Useful flags: `--out PATH` / `-Out`, `--keep-stage` / `-KeepStage` (leaves the staging tree
*and* the extracted packer), `--strip-source-maps` / `-StripSourceMaps`, `--refresh-wheels` /
`-RefreshWheels`, `--psycopg VERSION`, `--platform TAG`.

### It is offline after the first run

Wheels land in `out/lambda/wheels-<arch>/` and are reused whenever that directory already
holds both pins, so a second build needs no network and cannot silently pick up a different
artefact from PyPI. If `pip download` fails and the wheelhouse is already complete, the
build proceeds and says so — `wheels wheelhouse (reused; pip download failed)` — and the
name and sha256 of every wheel used goes into the sidecar either way, so *reused* is never
*unknown*. If the wheelhouse is incomplete and the download fails, the build dies.

### What it refuses, and what it says

| situation | refusal |
|---|---|
| `dist/` missing or has no `index.html` | `REFUSED [NO CONSOLE] … Build it with: cd verticals/mainline/apps/console && pnpm install --frozen-lockfile && pnpm exec vite build --mode demo` |
| `index.html` names an asset that is not in `dist/` | `REFUSED [STALE CONSOLE] … references ./assets/…, which is not in dist/` |
| the EvidenceBundle directory or its `manifest.json` is missing | `REFUSED [NO EVIDENCE BUNDLE] … Capture it with: python scripts/deploy/capture_demo_bundle.py` |
| `dist/` already contains `bundle/` | `REFUSED [BUNDLE COLLISION]` — two trees cannot own one path |
| `app.py` missing from the handler package | `REFUSED [NO HANDLER]` |
| the staging tree is missing one of the five load-bearing files | `REFUSED [MISSING]` |
| over 50 MB zipped or 250 MB unzipped | `REFUSED [SIZE]`, **and the zip and sidecar are deleted** |

The first four run **before** `pip` touches the network, so a forgotten `pnpm build` costs a
second rather than a minute.

### A warning that is not a refusal

If `dist/` was built without `VITE_MAINLINE_API_BASE` or `VITE_MAINLINE_BUNDLE_URL`, the
build prints:

```
build_lambda: console   WARNING this dist/ carries neither VITE_MAINLINE_API_BASE nor
build_lambda: console           VITE_MAINLINE_BUNDLE_URL (import.meta.env MODE=production). …
```

and records the probe in the sidecar under `console`. Vite inlines `import.meta.env` as an
object literal and `src/app/source-select.ts` selects a transport from exactly those two
keys, so a build with neither produces a site that loads, mounts, and then renders its
`NO SOURCE` panel on every surface. **That is the state of the committed `dist/` as this
page is written** — it was built as a plain `vite build`, not `vite build --mode demo`. It
is a warning rather than a refusal because `dist/` is not this worker's file and because the
package is still a correct, serveable website; converting another domain's build-flag
omission into an unbuildable deployment artefact would be the wrong trade. The rebuild
command is printed in full, every run.

---

## 6. Checking a package you did not build

```bash
python scripts/deploy/bundle_manifest.py out/lambda/mainline-demo-api-arm64.zip
python scripts/deploy/bundle_manifest.py <zip> --list                 # every entry + sha256
python scripts/deploy/bundle_manifest.py <zip> --json manifest.json --quiet
```

Standard library only, Python 3.9 or newer, no repository access. It opens the zip and
reports: every entry with its size and sha256, the totals, the top-level layout, whether the
four required roots — `mainline_demo_api/`, `psycopg/`, `web/index.html`, `web/bundle/` — are
present, both size limits, and the six determinism properties.

**Exit codes:** `0` pass · `2` a required root missing, a size limit exceeded, or `--strict`
and a determinism property false · `1` unreadable, or not a zip.

That it is a *check* and not a *log* is the point: the builder already says what it packed,
in the process that packed it. This says what the artefact **is**, from the artefact, and it
runs against a zip built on another machine last week. Proven both ways — `VERDICT PASS`,
exit 0 on both packages; and on the arm64 zip rewritten without its 26 `web/bundle/*`
entries:

```
REFUSED [MISSING ROOT] web/bundle/ is not in this package
VERDICT REFUSED                                              exit 2
```

Every build ends by running it with `--strict` and four extra `--require`s. If the checker
ever disagrees with the builder, the disagreement is between the artefact and the build —
exactly the class of failure a build log cannot report about itself.

### It really does serve the site

Unzipped into a scratch directory, with `MAINLINE_WEB_ROOT` pointed at its `web/` and the
package on `sys.path`, W1's `static_site.serve()` answers:

| request | status |
|---|---|
| `GET /` | 200, 4 641 B, `index.html` |
| `GET /assets/index-BjAGxrVJ.js` | 200, 433 097 B |
| `GET /bundle/manifest.json` | 200, 8 424 B |
| `GET /#/gate` | 200, the SPA fallback |
| `GET /assets/missing-Xxxx.js` | 404 — an asset miss is never the fallback |
| `GET /../etc/passwd` | 403 |
| `GET /%2e%2e%2fetc/passwd` | 403 — decoded exactly once, so this *is* a traversal |
| `POST /` | 405 |

---

## 7. What to do when the size ratchet refuses

In order. Stop at the first one that fits.

1. **`--strip-source-maps`.** Measured: −660 333 B zipped, −2 586 960 B unzipped, and the
   console stops being debuggable in DevTools. Cheapest, and reversible.
2. **Check what grew.** `bundle_manifest.py <zip> --list` sorted by size answers it in one
   command. On this package `psycopg_binary.libs/` is 15.7 MB of the 28.4 MB and `web/` is
   3.6 MB; a surprise elsewhere is a mistake, not a diet problem.
3. **Do not delete the EvidenceBundle to fit.** It is the demo's answer when the database is
   unreachable (`docs/deploy/replay-fallback.md`). A package that fits by removing the
   fallback has traded the failure mode you can survive for the one you cannot.
4. **Only then, S3.** Above 50 MB a deployment package must be uploaded to S3 and referenced
   by `s3_bucket`/`s3_key`; `infra/modules/demo-api/main.tf:249` uses `filename =`, a direct
   upload, so this is a **module change** and not a build flag. It also re-introduces a
   bucket that D1 deliberately removed from the deploy path.
5. The 250 MB unzipped ceiling has no flag at all — past it, the function must become a
   container image, which is a different deployment story end to end. Current headroom is
   233.8 MB, so this is a note for a successor, not a plan.

---

## 8. Boundaries

* **The handler is W1's.** This worker copies `mainline_demo_api/` and depends on exactly
  one documented thing: `MAINLINE_WEB_ROOT` points at the bundled `web/`.
* **`dist/` is the console domain's.** This worker verifies it, refuses without it, warns
  about its build flags, and never writes to it.
* **The EvidenceBundle is `capture_demo_bundle.py`'s.** It is copied verbatim; the prune
  rules are path-scoped precisely so that nothing in this build can alter a sealed tree.
* **Nothing here deploys.** `terraform apply` is not run by this worker
  (`docs/leads/ship-final.md` §2.2). The package, its hash and its sidecar are the input the
  apply consumes.
