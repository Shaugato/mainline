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
**Evidence:** `evidence/deploy/lambda-bundle.json` for the build-time record, and — for
every size, count and hash on this page — `bundle_manifest.py --strict --forbid-source-maps`
re-read out of the **committed packages on 2026-08-14**, plus
`tests/deploy/test_furl_compression.py` for §4.2, which asserts the serving path over a real
socket rather than quoting it. Where a figure has not been re-measured against this tree, the
page says so instead of carrying the old one forward (§3, §4.4).

---

## 1. What is in it, and why it is four things now

Decision **D1** — `docs/leads/ship-final.md` §1.4 — made the demo URL a public **Lambda
Function URL**, because this AWS account cannot create a CloudFront distribution
(`AccessDenied: Your account must be verified…`). One origin therefore serves the console,
the evidence bundle and the API, and this zip is that whole origin.

```
mainline-demo-api-arm64.zip                             246 entries
├── mainline_demo_api/           12 files    333 886 B   the handler package
├── psycopg/                     85 files    713 024 B   the pure-Python driver
├── psycopg_binary/              10 files  8 093 535 B   compiled libpq bindings
├── psycopg_binary.libs/         16 files 15 673 536 B   the .so files those need
├── psycopg-3.3.4.dist-info/      4 files     12 064 B
├── psycopg_binary-3.3.4.dist-info/ 5 files   16 806 B
└── web/                        114 files  1 274 342 B   57 objects, each twice
    ├── index.html  + index.html.gz                      GET /            (SPA shell)
    ├── assets/…    + assets/….gz                        GET /assets/*    (immutable)
    ├── .vite/manifest.json (+ .gz)                      Vite's build map, unrequested
    └── bundle/                  52 files    240 774 B   GET /bundle/*    (REPLAY source)
```

**`web/` is 114 entries and 57 objects.** Every compressible entry ships twice — once as
itself and once as a `<name>.gz` sibling — and the sibling is what a browser actually
receives. `.gz` is a *representation*, not a second object: it has no URL, no media type
and no cache entry of its own. §4 is the whole of that argument, measured.

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
| **arm64** | 7 646 264 B (7.29 MB) | 52 428 800 (50 MB) | 26 117 193 B (24.91 MB) | 262 144 000 (250 MB) | 246 |
| **x86_64** | 6 060 794 B (5.78 MB) | 52 428 800 (50 MB) | 21 351 365 B (20.36 MB) | 262 144 000 (250 MB) | 245 |

`sha256 09af589cf3b73e1708b2e3209a41ac3e2078db3df916e39827b2cfe930f45914` (arm64),
`116c14eb23c7b4871c819996775b271bba2e544a49de623892cef5ca09011a4c` (x86_64) — both read out
of the committed packages by `bundle_manifest.py --strict --forbid-source-maps` on
**2026-08-14**, which is also where every other number on this page comes from. The entry
count rose from 206 because the `.gz` siblings are now written (§4) and the zipped size fell
anyway because the source maps are now stripped by default (§4.3).

Headroom is 44.8 MB zipped and 236.0 MB unzipped on arm64. Both limits are **asserted on
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

**Measured, three builds per architecture, across both shells and three output directories,
on 2026-08-10:**

```
arm64   c85d7f00a5576e412dfb0124ad93c40104757011179d0029361d9a8db5b8a4b0   (x3)
x86_64  bd7f188df9118085e6520ed7d8893e353cd7d82531ced370fabaa1b241d709ba   (x3)
```

**Those are not the hashes of the packages committed today**, and the difference is
content, not clock: the siblings of §4 were added and the source maps were removed, both of
which change what is packed. The current artefacts are

```
arm64   09af589cf3b73e1708b2e3209a41ac3e2078db3df916e39827b2cfe930f45914
x86_64  116c14eb23c7b4871c819996775b271bba2e544a49de623892cef5ca09011a4c
```

read from the committed zips and from their own `.zip.json` sidecars, which agree. **The
three-builds-per-architecture repetition has not been re-run against this tree**, so what is
measured today is the six determinism properties above — re-read out of these artefacts by
`bundle_manifest.py --strict`, `VERDICT PASS` on both — and not a fresh reproducibility
run. Re-running it is two commands per shell; until somebody does, this page claims the
properties and not the repetition.

### The two builders are the same program

The staging/pruning/packing program is embedded in both `build_lambda.sh` (heredoc) and
`build_lambda.ps1` (here-string). Both normalise it to LF — this repository is checked out
on Windows, and a heredoc keeps the trailing newline while a here-string drops it, so the
PowerShell side appends one — and both **print its sha256**:

```
build_lambda: packer    sha256 9e0847f8001144e151e032ad63404a2bda5b641fed088be29d918ded29c31aa6
```

Two builders that print the same *zip* hash could still be two different programs that agree
today. This makes the agreement itself checkable, in one line of output, from either shell.
It is embedded rather than shipped as a third file because a shared helper that one shell
could load and the other could not is a reproducibility bug waiting to happen.

---

## 4. The 57 `.gz` siblings — what they are, and that they are served

### 4.1 What ships

| | entries | bytes |
|---|---|---|
| identity objects under `web/` | 57 | 985 030 |
| `<name>.gz` siblings | 57 | 289 312 |
| of which source maps | 0 | 0 |
| largest identity | | 433 396 — `web/assets/index-BjAGxrVJ.js` |
| largest sibling | | 124 127 — the same object, compressed |

**Every identity object has a sibling and every sibling has an identity object**: 57 and 57,
no orphan either way. The siblings are 29.4 % of the identity bytes — 695 718 B less on the
wire per full page load — and **not one of them is larger than the object it stands for**,
so there is no case in which negotiating costs bytes.

`scripts/deploy/build_lambda.{sh,ps1}` writes them, one pass over the staged tree, at gzip
level 9 with `mtime 0` and no filename in the gzip header, so the sibling is a pure function
of its input and the zip stays byte-reproducible. Only the ten suffixes
`static_site.MEDIA_TYPES` marks as text, JavaScript, JSON, SVG or wasm get one; `.png`,
`.jpg`, `.webp`, `.ico`, `.woff` and `.woff2` are already-compressed containers, where a
sibling would cost package bytes and save nothing.

### 4.2 THE SIBLINGS ARE SERVED, and this is the code path

They are not dead weight and they are not a package the origin ignores. The path, end to
end, in `verticals/mainline/apps/demo-api/src/mainline_demo_api/`:

| step | code | what it decides |
|---|---|---|
| 1 | `app._accept_encoding(event)` | pulls `accept-encoding` out of the Function URL event, case-insensitively; absent, empty or non-string → `None` |
| 2 | `app.handler` → `static_site.serve(method, path, accept_encoding=…)` (`app.py:501`) | the header reaches the static surface on **every** non-`/v1` request |
| 3 | `static_site.accepts_gzip(header)` | RFC 9110 §12.5.3: `gzip;q=0` is a **refusal**, `x-gzip` is a spelling of `gzip`, `*` permits it, an explicit `gzip;q=0` beside a `*` still refuses |
| 4 | `static_site._sibling(path, header)` | returns `<name>.gz` when the caller permits gzip **and** the file exists; `None` otherwise, so a build that stopped pre-compressing degrades to a bigger bill, never to a 404 |
| 5 | `static_site._file(...)` | the sibling's **bytes**, `content-length` and `content-encoding: gzip`; the **identity** object's media type, cache policy and name |
| 6 | `static_site._vary(...)` | `vary: accept-encoding` on every response whose bytes depend on the header — including the 413 |
| 7 | `static_site._answer(...)` | a direct request for any path ending `.gz` is a **404**, decided from the request before the web root is even consulted |

Two of those steps are the ones that are easy to get wrong and expensive to get wrong:

* **Step 5 keeps the media type.** A `.js.gz` is JavaScript that arrived compressed, not a
  new format. Served as `application/gzip` it is a module the browser refuses to run.
* **Steps 6 and 7 are the same bug seen from two sides.** Without `vary`, a shared cache
  replays the compressed answer to the next client that asked for identity. With a URL of
  its own, the `.gz` becomes a second name for one set of bytes — a second cache entry, and
  a browser holding gzip nobody told it to inflate. So the sibling has **no** URL: the only
  way to reach those bytes is `accept-encoding: gzip` on the identity path.

**The proof, not the claim.** `tests/deploy/test_furl_compression.py` runs the real handler
behind the real Function URL emulator (`scripts/deploy/local_furl.py`) over a **real TCP
socket** and asserts it for **all 57**, three exchanges each: the gzip request answers 200
with `content-encoding: gzip`, the sibling's exact byte count, `vary`, and a body that
inflates to the identity object byte for byte; the identity request answers with the *same*
media type and the identity bytes; and `<path>.gz` answers 404. The two named objects also
get the token-matching table — twelve `Accept-Encoding` values including `x-gzip-nope`,
`notgzip` and `gzipper` — and the five spellings of `gzip;q=0`. 30 controls, and the file
refuses to run at all against `console/dist`, which carries **zero** siblings.

### 4.3 What would have to change for them to become dead weight

Each of these is currently false, and each has a control that fails if it becomes true:

| if this changed | the siblings become | caught by |
|---|---|---|
| `app.py` stopped passing `accept_encoding=` to `serve()` | dead — `serve()` defaults to `None`, which means identity, so the origin would ship 289 KB it never sends | the sweep: all 57 answer without `content-encoding` |
| `accepts_gzip()` started refusing valid headers | dead for the clients it refuses | the twelve-value token table |
| a sibling grew past `MAINLINE_MAX_RESPONSE_BYTES` (139 264 B today) | worse than dead — that object stops being servable **at all**, in either representation | the sweep asserts exactly one object is over the ceiling in identity and **none** in gzip |
| the console build started emitting `.gz` files itself | a build refusal, not dead bytes — `REFUSED [GZ COLLISION]` | the builder, before `pip` runs |
| an identity object were dropped but its sibling kept | genuinely dead — an orphan `.gz` has no URL under interface I1 and nothing can ever reach it | the inventory control: `orphans == []` |

The last row is the only case where *stop shipping them* would be the right answer, and it
is the one case that cannot happen without the inventory control failing first.

### 4.4 Source maps are stripped by default

`--strip-source-maps` **is the default** in both builders; `--keep-source-maps` is the
opt-out, and the flag is still accepted so an old command line keeps working. The committed
packages carry **0** source maps, gated rather than observed:
`bundle_manifest.py --forbid-source-maps` is run on every build and refuses the artefact if
one appears.

This reversed an earlier decision, and the reason is the one this page has to state plainly:
a judge opening DevTools benefits from maps, but `web/assets/*.js.map` is **18 files,
2 586 960 B** in the input tree — **72.4 %** of the served tree — and this origin's cost is
dominated by what it puts on the wire under an unauthenticated URL. The maps are still one
flag away for a debug build; the bill is not.

**No maps-kept build has been measured against the current tree**, so this page publishes no
zipped-delta figure for one. The 660 333 B contrast that used to sit here was measured
against a tree with no `.gz` siblings and a smaller handler package, and re-quoting it now
would be quoting a number about a different artefact. Build one with `--keep-source-maps` if
you need the comparison; it is deterministic in its own right.

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
| `GET /` | 200, 4 655 B, `index.html` |
| `GET /` with `accept-encoding: gzip` | 200, 2 122 B, `content-encoding: gzip` — §4.2 |
| `GET /assets/index-BjAGxrVJ.js` with `accept-encoding: gzip` | 200, 124 127 B compressed |
| `GET /assets/index-BjAGxrVJ.js` identity | **413** — 433 396 B against a 139 264 B wire ceiling |
| `GET /assets/index-BjAGxrVJ.js.gz` | 404 — the sibling has no URL of its own |
| `GET /bundle/manifest.json` | 200, 8 435 B |
| `GET /#/gate` | 200, the SPA fallback |
| `GET /assets/missing-Xxxx.js` | 404 — an asset miss is never the fallback |
| `GET /../etc/passwd` | 403 |
| `GET /%2e%2e%2fetc/passwd` | 403 — decoded exactly once, so this *is* a traversal |
| `POST /` | 405 |

The first six rows are asserted over a real socket for all 57 objects by
`tests/deploy/test_furl_compression.py`, not read off one manual run.

---

## 7. What to do when the size ratchet refuses

In order. Stop at the first one that fits.

1. **`--strip-source-maps` is already spent.** It is the default (§4.4), so it is not a
   lever you still have; the artefact carries 0 maps. If a package is over the ceiling
   today, the maps are not why.
2. **Check what grew.** `bundle_manifest.py <zip> --list` sorted by size answers it in one
   command. On this package `psycopg_binary.libs/` is 15.7 MB of the 26.1 MB unzipped and
   `web/` is 1.27 MB; a surprise elsewhere is a mistake, not a diet problem.
   **Do not reach for the `.gz` siblings.** They are 289 KB of the package and they are the
   bytes every browser actually receives (§4.2); deleting them to fit would multiply this
   origin's egress by 3.4 to save a quarter of a megabyte of upload.
3. **Do not delete the EvidenceBundle to fit.** It is the demo's answer when the database is
   unreachable (`docs/deploy/replay-fallback.md`). A package that fits by removing the
   fallback has traded the failure mode you can survive for the one you cannot.
4. **Only then, S3.** Above 50 MB a deployment package must be uploaded to S3 and referenced
   by `s3_bucket`/`s3_key`; `infra/modules/demo-api/main.tf:249` uses `filename =`, a direct
   upload, so this is a **module change** and not a build flag. It also re-introduces a
   bucket that D1 deliberately removed from the deploy path.
5. The 250 MB unzipped ceiling has no flag at all — past it, the function must become a
   container image, which is a different deployment story end to end. Current headroom is
   236.0 MB, so this is a note for a successor, not a plan.

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
