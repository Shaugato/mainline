<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Building the console for the demo URL

**Owner:** `w8-console-composition`.
**Artefact:** `verticals/mainline/apps/console/dist/` — the whole demo site, static files only.
**Consumed by:** `w5-tf-site` (the S3 bucket behind CloudFront) and `w7-env-and-deploy`
(the one-command deploy).
**Measured:** 2026-08-10, node v24.14.0, pnpm 11.5.3, on this machine. Every number below
was produced by a command in this document.

---

## 1. The command

> **THE SHIPPABLE COMMAND IS THE PHASE-2 ONE. Corrected 2026-08-14, after the deployed
> console reached the founder reading `TRANSPORT REPLAY (staged)`.** This section used to
> present Phase 1 first and Phase 2 as an addendum, and the deploy ran what it read first.
> The artefact that ships must carry **both** sources — the live kernel it is sitting on,
> and the bundle that cannot fail, one control away (`src/app/source-select.ts:16-18`;
> lead's ruling **R2**). Phase 1 is still a build this repository performs, and it is still
> what `.env.demo` alone produces; it is not what gets uploaded.

```powershell
cd verticals\mainline\apps\console
pnpm install --frozen-lockfile          # once; node_modules is already present here
$env:VITE_MAINLINE_API_BASE = '/'
$env:MAINLINE_BUILD_ID = (git rev-parse --short HEAD)
pnpm exec vite build --mode demo
```

`--mode demo` makes Vite read `.env.demo`, which is committed beside `package.json` and
is annotated line by line. That file alone builds **Phase 1**: a console over a
cryptographically verified EvidenceBundle, with no API and no database in the request
path. `docs/leads/deploy-plan.md` §4 is explicit about why that is the default —
*"Nobody is allowed to let the live path hold the URL hostage."*

```bash
# Phase 1 — the demo that cannot fail, and the artefact that was deployed by mistake
pnpm exec vite build --mode demo
```

**Phase 2 supplies one variable in the ENVIRONMENT**, which Vite applies after every `.env`
file, so a deploy never edits a committed file — `.env.demo`'s own header states that rule
and `tests/deploy/test_console_repro.py` enforces it by pinning the committed values:

```bash
MSYS_NO_PATHCONV=1 VITE_MAINLINE_API_BASE=/ MAINLINE_BUILD_ID=… pnpm exec vite build --mode demo
```

> **Measured hazard — do not run that line in Git Bash on Windows.** MSYS path
> conversion rewrites a bare `/` into the MSYS root, and the value compiled into the
> artefact becomes `C:/Program Files/Git/`. Observed on 2026-08-10:
> `VITE_MAINLINE_API_BASE:"C:/Program Files/Git/"` in `dist/assets/index-*.js`. Use
> PowerShell — `$env:VITE_MAINLINE_API_BASE='/'` — or prefix the bash line with
> `MSYS_NO_PATHCONV=1`. **Always verify the compiled value**:
>
> ```bash
> grep -o 'VITE_MAINLINE_API_BASE:"[^"]*"' dist/assets/index-*.js
> ```

> ### THE VERIFY STEP IS NOT OPTIONAL, AND HERE IS WHAT IT COST TO LEARN THAT
>
> **Added 2026-08-14, after the compiled value shipped wrong to a public URL.** The
> `grep` above reads like belt-and-braces beside an already-explained hazard. It is not.
> It is **the only step in this procedure that observes the artefact rather than the
> intention**, and every failure this section knows about is a failure of intention:
>
> | what went wrong | what the operator intended | what the artefact carried |
> |---|---|---|
> | MSYS path conversion, 2026-08-10 | `VITE_MAINLINE_API_BASE=/` | `"C:/Program Files/Git/"` |
> | the variable never reached the build, 2026-08-14 | a LIVE console on the demo URL | `VITE_MAINLINE_API_BASE:""` — REPLAY, §7 |
>
> Both are invisible in the shell's exit code, in the build log, and in `dist/`'s file
> list. **Both are one `grep` away from being obvious**, and in the second case nobody ran
> it, so a REPLAY console sat on an origin with a live kernel behind it until a human
> opened the page and read the badge. Run the `grep`. If the value is not the one you
> typed, the build is wrong no matter what the command said.
>
> Two more values are worth the same three seconds, for the same reason — they are
> build-time literals that no test can see afterwards:
>
> ```bash
> grep -o 'VITE_MAINLINE_BUNDLE_URL:"[^"]*"' dist/assets/index-*.js   # the REPLAY source
> grep -o 'buildId:"[^"]*"' dist/assets/index-*.js                    # must not be "dev"
> ```
>
> §7's packaging guard now refuses a mismatch at package time, so this check is no longer
> the *only* thing standing between a wrong literal and a judge. It is still the fastest,
> and it is the one that tells you *before* you have built a zip.

`/` and not a hostname, because the console and the API are served from **one** CloudFront
distribution (deploy-plan §2.1): `/v1/…` resolves against whatever origin the page was
loaded from, there is no CORS anywhere, and the built artefact names no domain — so the
same `dist/` works behind any distribution, including one created after the build.

### What each variable does

| Variable | Read by | Effect |
|---|---|---|
| `VITE_MAINLINE_BUNDLE_URL` | `src/app/source-select.ts` | REPLAY source. `./bundle/`, relative; `src/app/composition.tsx` resolves it against `document.baseURI`, so the site works from a bucket root, a sub-path and `file://`. |
| `VITE_MAINLINE_API_BASE` | `src/app/source-select.ts` | LIVE source. Empty ⇒ unset ⇒ this build has no live source. |
| `VITE_MAINLINE_LOG_VKEY` | `src/verify/config.ts` | The checkpoint trust anchor. Unset ⇒ the signature check is a **named SKIP**, the seal is amber, and the chrome says so. File digests are still recomputed and a mismatch still refuses to render. |
| `VITE_MAINLINE_CANON_SHA256` | `src/verify/config.ts` | Pins the canonicaliser; unset ⇒ ledger check 10 SKIPs. |
| `MAINLINE_BUILD_ID` | `vite.config.ts` `define` | The `build` cell of the honesty chrome. A screenshot must name the artefact it came from. |

Both variables set ⇒ the console starts **LIVE** and renders a control that switches to
**REPLAY**. One set ⇒ that one, and no control. Neither ⇒ nothing is constructed and every
surface keeps its own NO SOURCE panel, unchanged.

### Then upload

```
dist/                       → s3://mainline-demo-site/           (the console)
evidence bundle (w9)        → s3://mainline-demo-site/bundle/    (must match VITE_MAINLINE_BUNDLE_URL)
```

The bundle directory is **not** produced by this build. `w9-evidence-bundle` produces it;
this build only compiles the path at which the console will look for it.

### Is this build reproducible? MEASURED 2026-08-14, and the answer is yes

A content-hashed filename is pinned as a constant in three places
(`test_response_contract.py`, `test_static_site.py`, `tests/deploy/test_furl_compression.py`).
That is legitimate **only** if the build reproduces. It was checked rather than assumed, by
`scripts/deploy/console_repro.py`, which builds N≥3 times from a clean state and records the
name, byte size and **sha256 of every emitted asset** into
`evidence/deploy/console-repro.json` together with the exact argv and every input it read.

```powershell
.venv\Scripts\python.exe scripts\deploy\console_repro.py --builds 3 --source rev:HEAD --label committed-phase1
.venv\Scripts\python.exe scripts\deploy\console_repro.py --builds 3 --source rev:HEAD --api-base '/' --label committed-phase2
```

`--source rev:HEAD` exports the console subtree with `git archive` and builds **there**, so
the measurement is of the committed bytes and not of whatever a working tree happens to hold.

| run, by its label in `evidence/deploy/console-repro.json` | entry chunk | identity | three builds | source-select verdict |
|---|---|---|---|---|
| Phase 1 — `committed-phase1`, `measured_at` 2026-08-15T02:44:52+1000 | `assets/index-DzVoV1YM.js` | **433,564 B** | byte identical 3/3, tree digest `bf3ec22e…` | REPLAY, no control |
| Phase 2 — `committed-phase2`, `measured_at` 2026-08-15T02:46:58+1000 | `assets/index-CmIr4_KY.js` | **433,565 B** | byte identical 3/3, tree digest `857ce28b…` | **LIVE, with a control that switches to REPLAY** |

Phase 2 is **one byte** larger: `VITE_MAINLINE_API_BASE:""` becomes `…:"/"`. And the Phase-1
entry chunk is `sha256 4596d00cb33ee2d1…`, which is **byte for byte** the
`web/assets/index-DzVoV1YM.js` that `evidence/deploy/judge-walk.json` records the Function
URL serving, and that package `sha256 12fcba7a…` carried. The committed source reproduces
that chunk exactly; it read REPLAY because the deploy ran the Phase-1 command, not because
the build varies.

> **CORRECTED 2026-08-15 — the package at `out/lambda/mainline-demo-api-arm64.zip` is no
> longer that one, and has since been replaced a second time.** It is
> `sha256 7c97b532ea9016fadc2be8ddd2c9e95b28820758e38d0439916940cd41022d22`, packed from HEAD
> `f0ba767` `--console-transport live` with `MAINLINE_BUILD_ID=f0ba767`, and its entry chunk is
> `assets/index-LoN3Sn_L.js`, **490,950 B**, `sha256 7eb3ec715dc3113c…`. (Between the two it
> was `sha256 6802872f…` with `assets/index-BH5dfAvF.js` at 457,123 B, `MAINLINE_BUILD_ID=
> b822fdc`.) Neither chunk is emitted by any run in the table above. The sentence above is
> about the committed source and the object the walk recorded; it is not a claim about what
> the zip on disk holds today — and it is not a claim about the origin either, which is still
> answering with `assets/index-DzVoV1YM.js` because nothing has been redeployed.

#### The tree digests moved and this document does not say why — HANDED ON

**Recorded 2026-08-15 by `w5-decision-record`.** Until today this table quoted tree digests
**`89042d19…`** (Phase 1) and **`53cd5a97…`** (Phase 2) for those same two builds. The
evidence file holds **`bf3ec22e…`** and **`857ce28b…`**. The table now quotes what the
evidence holds. **That is a correction of the document, not an explanation of the
divergence, and the divergence is unexplained.** The two figures are *not* one measurement
re-expressed: `bf3ec22e…` comes from a **different invocation** of `scripts/deploy/console_repro.py`,
run at the `measured_at` stamped beside it.

What is established, and by whom — points 1, 2 and 4 were re-read here from the evidence
file, from `console_repro.py` and from `git`; point 3 is the constants lead's first-hand
finding (`docs/leads/reconcile-constants-plan.md` §5):

* **Every entry-chunk figure agrees across the two records.** Phase 1 is
  `assets/index-DzVoV1YM.js` at 433,564 B and Phase 2 is `assets/index-CmIr4_KY.js` at
  433,565 B in both, each byte-identical across 3/3 builds, and the Phase-1 chunk's
  `sha256 4596d00cb33ee2d1…` is unchanged.
* **`tree_digest` is much wider than the entry chunk**, so that agreement says nothing about
  it. It is `rollup_digest(tree_digests(dist))` — a `sha256` over `name\0size\0sha256\n` for
  **every one of the 49 files the build emits**, including 18 `.js.map` files and
  `.vite/manifest.json` (`scripts/deploy/console_repro.py:148-176, 421-426`).
* **The "it was a different temp directory" explanation is RULED OUT.** A `.map`'s `sources`
  entries are **relative** (`../../src/design/primitives/ConstraintName.tsx`) and
  `sourceRoot` is absent, so the scratch export path cannot leak into a map's bytes.
* **The record behind `89042d19…` exists nowhere.** `evidence/deploy/console-repro.json` is
  **untracked** — `git log --` on it is empty and `git show HEAD:` on it fails with *"exists
  on disk, but not in 'HEAD'"* — so git holds no earlier version, and the per-asset
  `{name, bytes, sha256}` map of that run was overwritten in place.

**No cause is asserted here, and none should be inferred.** There is a plausible mechanism —
that the earlier run's inputs carried CRLF where a `git archive` export carries LF, changing
`sourcesContent` in all 18 maps while leaving the emitted JavaScript identical — and it is
*consistent* with the `"i/lf w/crlf": 31` EOL census this same file records and with the
CRLF-changes-the-bundle behaviour measured two subsections down. **It is a hypothesis, no
artefact supports it, and writing it down as the cause would be the exact failure this
correction exists to undo.**

**What would settle it, named so the next worker does not have to invent it:** the per-asset
`{name, bytes, sha256}` map of the run that produced `89042d19…`, diffed against the recorded
run's. **If only `.map` files differ, the mechanism is source text. If any `.js` differs, the
build is not deterministic — a larger finding than any number on this page, and one that
would put every content-hashed constant in this repository back in question.** That record is
gone, so the substitute is to re-establish the current baseline first:

```powershell
.venv\Scripts\python.exe scripts\deploy\console_repro.py --builds 1 --source rev:HEAD --out <scratch>\probe.json
```

`--source rev:HEAD` exports with `git archive` and `--out` writes to a scratch path, so
neither the worktree console nor `verticals/mainline/apps/console/dist` is touched — which is
mandatory: a prior agent ran this against the worktree and clobbered both. Confirm
`bf3ec22e…` is stable for the committed source, then re-run under the suspected earlier input
and see whether `89042d19…` reappears.

#### Reproducible, yes — but not yet of the filename that ships (caveat **R16**)

**Recorded 2026-08-15.** Both runs above build the **committed** console (`--source rev:HEAD`)
and emit 433,564 / 433,565 B. The package of record was built from the **worktree** console,
which is genuinely different: `git diff --stat HEAD -- verticals/mainline/apps/console` is
**14 files changed, 1,689 insertions**, and `src/data/contracts.ts:49` imports
`'../../contracts/gate-run.schema.json?raw'` in the worktree while `git grep` at HEAD finds
no such import. **That import is the +23,559 B** between 433,564 and 457,123.

* **What IS proven:** the console build is **deterministic** — same source, same bytes, 3/3,
  at two different sources. That is what ruling **R1**'s gate asked for, and it is satisfied,
  which is why `docs/decisions/response-ceiling-authoritative-tree.md` may treat the byte
  constants as measurements of a build.
* **What is NOT proven, UPDATED 2026-08-15:** the older form of this bullet said
  `assets/index-BH5dfAvF.js` was not reproducible *because its source was not committed*.
  **That half is fixed.** The current package of record, `sha256 7c97b532…`, was built from
  HEAD `f0ba767` and `git diff --stat HEAD -- verticals/mainline/apps/console` is empty, so
  the source of `assets/index-LoN3Sn_L.js` **is** in git. What is still missing is a **run**:
  `console_repro.py` has not been executed against it, and
  `evidence/deploy/console-repro.json` still records an older console's 3/3. So that chunk is
  reproducible-in-principle, not reproduced-in-fact, and any document identifying the artefact
  must still name it by **package digest** (`sha256 7c97b532…`) rather than by content hash.
  Do not upgrade this bullet without re-running the tool.
* `evidence/deploy/console-repro.json` records `"worktree_matches_committed": true`,
  `measured_at` 2026-08-15T02:44:52+1000. That was measured **before** the console work
  reached the worktree, so it is stale as a reading of *these* bytes even though its claim is
  now independently true of HEAD. The file is **not regenerated here** — regenerating it is a
  build, and the safe form of that build is the `--out`-to-scratch probe above.

#### The two recorded hashes at 433,564 B — which one is wrong, and why

`docs/ci/cluster-lane-package.md` §4 records `assets/index-BKZMI9SJ.js` at **433,564 B** with
a 124,173 B gzipped sibling as *"the fresh build at HEAD `eefae1c`"*. The tests, package
`12fcba7a…` and the live URL record `assets/index-DzVoV1YM.js` at the **same 433,564 B** with
a 124,177 B sibling. `git diff eefae1c HEAD -- verticals/mainline/apps/console` is **empty**, so the
source at those two commits is identical and one of the records is wrong.

**`index-BKZMI9SJ.js` is the wrong record.** Reproduced deliberately: export HEAD, convert
`src/design/primitives/instrument.module.css` from LF to CRLF, change nothing else, build.

```
committed (LF)                    assets/index-DzVoV1YM.js  433,564 B   identity total 794,736 B
one CSS module CRLF               assets/index-BKZMI9SJ.js  433,564 B   identity total 794,741 B
all 51 drifted files CRLF         assets/index-BKZMI9SJ.js  433,564 B   identity total 794,741 B  (identical to the row above)
```

A CSS-module scoped class name is a hash of the module's bytes and a hash is a **fixed-length**
string, so its value moves and the bundle's length does not — which is exactly how two
different files end up recorded at one identical byte count. Thirty-seven identity assets
change name; only `Counter-*.css` changes size, by five bytes. Of the 51 drifted files, **one**
reaches the emitted identity bytes; the other fifty move only source maps, which the packer
strips.

> **`git status` will not show you this, and that is the point.** Git for Windows ships
> `core.autocrlf=true` at system scope. A file checked out under it holds CRLF in the worktree
> and LF in the index, and the index's cached **stat size** is the CRLF size — so git declares
> the entry unmodified without re-reading it. Measured on this tree:
>
> ```
> index blob 4eee3112…   4,429 B   0 CRLF        git status  -> clean
> worktree               4,563 B   134 CRLF      git diff    -> empty
> ```
>
> §3.3 of `cluster-lane-package.md` states *"the console source is clean against HEAD
> (`git status --porcelain` names nothing under `apps/console`)"*. That sentence was true as
> git reported it and false as a matter of bytes, and it is why a build nobody could
> re-measure was recorded as the repository's.

`tests/deploy/test_console_repro.py` now fails, by name, on any `src/**` file whose worktree
bytes differ from the commit **only** in line endings. A genuine edit is not drift and does
not fail it. Restore drifted bytes rather than re-recording a hash measured while they were
there.

#### A measurement this section owed to whoever re-records the ceiling — **RESOLVED (R10)**

The runs above are of the **committed** source. The block below is of the **working tree** as
it stood on 2026-08-14 — the same Phase-2 command over a console that had gained a
seventeenth declared resource and the `gate-run.schema.json` contract:

```
worktree Phase 2, 2026-08-14      assets/index-CSYj1JjN.js   457,037 B identity   129,371 B gzip(9)
package 12fcba7a…, 2026-08-14     assets/index-DzVoV1YM.js   433,564 B identity   124,177 B gzip(9)
package 6802872f…, 2026-08-15     assets/index-BH5dfAvF.js   457,123 B identity   129,400 B gzip(9)
package 7c97b532…, 2026-08-15     assets/index-LoN3Sn_L.js   490,950 B identity   138,177 B gzip(9)
```

The gzip figure is produced by the packer's own method — `zlib.compressobj(9, DEFLATED,
-MAX_WBITS)` plus an 18-byte container. Against package `12fcba7a…` it reproduced
`web/assets/index-DzVoV1YM.js.gz` at exactly 124,177 B; the last two rows are read straight out
of the central directory of the package they name, and the **package of record is now the
fourth row** — `sha256 7c97b532ea9016fadc2be8ddd2c9e95b28820758e38d0439916940cd41022d22`,
built from HEAD `f0ba767` with `MAINLINE_BUILD_ID=f0ba767`, where
`web/assets/index-LoN3Sn_L.js.gz` is **138,177 B**. It carries the seven-screen console
(commit `9c902e0`) and 69 identity objects where the row above it carries 57.

**Read the identity column down that block rather than the filenames.** A build-id-only
re-release moves every name here and leaves every identity size alone, because
`vite.config.ts` inlines `__MAINLINE_BUILD_ID__` into the emitted bytes and a Vite content hash
is a fixed-width field. When a name moves and the identity size does not, nothing about the
console changed. When both move — as they did on the last two rows — the console really did.

> **Two provenance notes, 2026-08-15, so nobody re-derives these from thin air.** The
> `worktree Phase 2` figures are **not in `evidence/deploy/console-repro.json` today** — that
> file holds exactly two runs, `committed-phase1` and `committed-phase2` — so this block is
> their only surviving record. And package `12fcba7a…` is no longer at
> `out/lambda/mainline-demo-api-arm64.zip`, so its 124,177 B reproduction cannot be repeated
> against it; it stands as measured on 2026-08-14, not as a command a reader can run today.

~~**129,371 B is outside the window `119,158 ≤ g ≤ 126,604` that keeps the authoritative
`DEFAULT_MAX_RESPONSE_BYTES == 139_264` derivable** (lead's ruling **R4**). Re-deriving the
ceiling from this build yields 147,456, which is raising a ceiling to fit a bigger bundle.
Recorded here as a measurement, not a decision: the ceiling belongs to
`docs/decisions/response-ceiling-authoritative-tree.md` and R4 directs the re-recording
worker to **stop and report to the lead** rather than move it.~~

**SUPERSEDED 2026-08-15 — the lead resolved it as ruling R10**
(`docs/leads/reconcile-constants-plan.md` §1;
`docs/decisions/response-ceiling-authoritative-tree.md` §10). The struck paragraph stays
because its refusal was correct: nobody raised a ceiling to fit a bigger bundle, and nobody
may. What the ruling settled is that the **derivation window was never the law**. The law is
the straddle and interface I3, and over the package of record they hold, measured:

```
g = 138,177   C = 139,264 (UNCHANGED)   I = 490,950
0 < 138,177 < 139,264 < 490,950          straddle HOLDS
139,264 < 1.20 x 138,177 = 165,812.4     I3 HOLDS, ratio 1.008
exactly one of 69 identity objects is refused by the ceiling
```

*(Over the previous package of record, `sha256 6802872f…`, the same block read
`g = 129,400 / I = 457,123`, ratio 1.076, one of 57. Only the measurements moved.)*

`DEFAULT_MAX_RESPONSE_BYTES` did not move: it is `136 * 1024 = 139,264`, as it was, and
`git diff` on `static_site.py` shows no change to it. The derivation
`ceil(floor(1.10·g)/8192)·8192` is now **dated provenance** — the record of how 139,264 was
chosen, over `g = 124,177` — and **`119,158 ≤ g ≤ 126,604` is no longer a live constraint on
this build or on any document.**

**The number that warns instead is the headroom, and it is now 1,087 gzipped bytes — 0.78 %**
(`139,264 − 138,177`; it was 9,864 over `6802872f…` and 15,087 before that). **Say what
crossing it costs**: when `g` exceeds the ceiling this origin answers **413 for its own entry
JavaScript**, to every client rather than only to the ones refusing compression. `GET /` still
returns 200 and the 4,655 B shell, the shell asks for its single module, it receives a JSON
problem document, and the reader is looking at a **blank page**. That is a total outage of the
demo URL with the origin reporting itself healthy throughout.

**So a console change adding more than 1,087 bytes to the entry chunk's gzipped size has to be
discussed before it is packed — and the remedy is a code-split, never a larger ceiling.** Since
2026-08-15 `test_static_site.py::_MINIMUM_HEADROOM_BYTES = 1024` makes that conversation happen
in CI: the next growth past **63 gzipped bytes** goes red while this origin is still serving
every object it has. The guard was falsified before it was trusted — a planted violation turned
the declaration test, the end-to-end tree test and its own five falsification cases red, and
the plant was reverted.

#### Every build input, and where it comes from

`vite.config.ts` declares its two environment reads in one `BUILD_INPUTS` table and its two
filesystem probes in one `ATTESTATION_CANDIDATES` array; `console_repro.BUILD_INPUT_NAMES`
lists those two plus the four `VITE_*` names Vite reads from `.env.demo`; and the test fails
if either file grows an input the other does not know about. Today
`evidence/attestations/g1-attestation.json` and `evidence/g1-attestation.json` are both
**absent**, so the build compiles `signature_path: "unknown"` / `attestation_source: "absent"`
— recorded as a resolved input, not left to be inferred.

---

## 2. What comes out — measured, 2026-08-10

```
dist/ (this build's output, pre-packaging — NOT what the origin serves)
dist bytes: 3 380 488  (3.2 MB)      49 files
  sourcemaps: 2 580 278  (2.5 MB)    18 files
  everything else: 800 210 (781 KB)  31 files
```

> **RE-MEASURED 2026-08-14 from the committed source, three builds, byte identical** —
> `evidence/deploy/console-repro.json` → `runs["committed-phase1"]`, which records the name,
> size and sha256 of every one of these files individually:
>
> ```
> dist bytes: 3 382 562                49 files    (Phase 2: 3 382 564, +2)
>   sourcemaps: 2 581 568              18 files
>   everything else: 800 994           31 files
> ```
>
> The file *count* is unchanged; the block above is 2,074 B light because the console source
> moved between 2026-08-10 and today. The 49th file is `.vite/manifest.json`, which
> `scripts/check-budgets.ts` reads — it is an emitted file and it is digested with the rest.

> **WHICH TREE THIS IS, AND WHY IT MATTERS (added 2026-08-14).** Every figure in this block
> describes **`dist/`, the tree this build emits**, measured 2026-08-10. It is an input to
> the Lambda packer, **not** the tree a browser reaches. The packer strips source maps by
> default, so the **deployed** `web/**` tree carries **114 entries, 1,274,342 B and 0 source
> maps** (`evidence/deploy/cost/package-shape.json` → `architectures[arm64].after.web`).
> Its pre-strip `before.web` counterpart is 75 entries / 3,571,990 B — also not this block,
> because `web/**` in the package is a superset of `dist/`. **A byte figure that does not
> name its tree is wrong whichever tree it came from**
> (`docs/leads/docs-and-cloud-plan.md` RULING 2), so: this one is `dist/`.
>
> **Dated 2026-08-15.** That `114 / 1,274,342 / 0 maps` reading is what
> `package-shape.json` holds, and that artefact describes the 2026-08-13 package (its
> `after.web` largest identity object is `web/assets/index-BjAGxrVJ.js` at 433,396 B). The
> package of record, `sha256 6802872f…`, reads **114 entries / 1,308,543 B / 0 source maps**
> out of its own central directory. The *shape* — 114 entries, 57 identity objects, 57 `.gz`
> siblings, no maps — is unchanged across all three packages; only the bytes moved.
> Regenerating `package-shape.json` is a build and is not done here.

| Chunk | Purpose |
|---|---|
| `assets/index-*.js` | the evidentiary shell: router, honesty chrome, composition root, both transports, the contract registry, the in-browser verifier |
| `assets/DemoDriver-*.js` | **10 594 bytes** — the four demo controls, a lazy chunk, loaded only on `#/gate` |
| `assets/surface-*.js` × 7 | one per feature surface, lazy (`src/app/surfaces.ts`'s glob) |

`scripts/check-budgets.ts`, which is the gate (D13 — budgets are tests):

```
  manifest: 20 chunks
  PASS  evidentiary-shell          124.6 KB gzip  /   220 KB  (57%, 2 files)
  lazy boundary: 63 modules inside the entry closure
```

### The entry chunk grew, and by how much

| | before this worker | after |
|---|---|---|
| evidentiary shell, gzip | **70.1 KB** (32 % of budget) | **124.6 KB** (57 %) |
| modules in the entry closure | 22 | 63 |

The +54.5 KB is `src/data/contracts.ts` (seventeen JSON Schema documents, previously a
lazy `contracts-*.js` chunk because only feature surfaces imported it) and `src/verify/**`
(RFC 8785, RFC 6962, ECDSA P-256, the ledger and boundary checks). Both are now on the
critical path because the composition root constructs a transport before any surface
loads, and **both transports validate every response against its contract** while the
replay transport **cannot serve a frame before verification resolves**.

That cost is accepted rather than optimised away, and the reason is not budget headroom:
a lazily-loaded verifier is one more thing that can fail to load between the bytes and the
seal, and on the Phase-1 demo the verifier *is* the product. The number is recorded here
so the next person to look at the budget knows what moved and why.

### ~~Sourcemaps ship. Here is the argument.~~ Sourcemaps are BUILT here and do NOT ship.

> **CORRECTED 2026-08-14. THE HEADING WAS FALSE ABOUT THE DEPLOYED ARTEFACT.** This build
> still sets `sourcemap: true` and still emits the 18 maps counted in §2 — that part is
> unchanged and the argument below is preserved because it is why they are still *built*.
> **What is false is "ship".** `--strip-source-maps` is now the **default** in both Lambda
> builders, so the packaged tree carries **0** source maps, gated on every build by
> `bundle_manifest.py --forbid-source-maps`
> (`docs/deploy/lambda-bundle.md` §4.4; `evidence/deploy/cost/package-shape.json` →
> `architectures[].after.web`). A judge who opens devtools against the **deployed origin**
> gets no maps; a judge who runs this build locally does.
>
> The reason the decision flipped is recorded verbatim in the evidence artefact's
> `what_changed.one`: the keep-the-maps argument *"was sound while the package was something
> an operator downloaded and is not sound for a tree served from a Function URL with
> `authorization_type = NONE`"* — which the plan confirms is the shipping shape
> (`evidence/deploy/terraform-plan-furl.txt:351`). Point 2 below priced the maps in **S3**;
> the shipping origin is a **Lambda Function URL**, where the bytes are egress from the
> function, not S3 storage. **`vite.config.ts` belongs to the UI domain and was not touched
> by this correction** — only the claim about what reaches a browser.

The four points below are the original argument for building them, retained unedited:

`vite.config.ts` sets `sourcemap: true` and this build keeps it, deliberately.

1. **They are the claim.** The console's central assertion (D6) is that it re-derives
   every claim in the browser and shows the derivation. A judge who opens devtools can
   read the actual RFC 6962 hashing that produced the seal, and diff it against the
   repository they were told to clone. Stripping the maps would leave *"trust our
   minifier"* exactly where the product says *"check it yourself."*
2. **They cost nothing to serve.** 2.5 MB in S3 Standard, ap-southeast-1, is
   ≈ **USD 0.00006/month**. A `.map` is fetched only when devtools is open, so no judge,
   and no page load, pays for one.
3. **They are never on the critical path.** The 124.6 KB gzip budget is JavaScript and
   CSS; the maps are outside it by construction, which is why the number above did not
   move when they were added.
4. **They leak nothing.** `import.meta.env` is inlined into the JavaScript whether or not
   a map exists, the build carries no credential (the DSN lives in SSM and only the Lambda
   reads it), and the repository must be **public** to satisfy the hackathon's Stage One
   rules anyway. There is no secret for a map to reveal that a `grep` of `dist/` would not.

If a future build must drop them, `sourcemap: false` in `vite.config.ts` is the one-line
change — and `vite.config.ts` belongs to the UI domain, not to this one.

---

## 3. The composition root, in one paragraph

`src/app/composition.tsx` is the only place in the console that constructs a transport.
Every `src/features/<id>/transport-context.ts` defaults to `null` and renders an honest NO
SOURCE panel; this module is what fills them, and it fills all six with **one** object, so
there is one cache, one clock and one verification state. D7's property — *`LIVE` and
`REPLAY` differ in one line of composition and in one badge, never in a code path* — is
kept by `buildTransport`, which is one `if`, two constructors and the same
`MainlineTransport` returned either way. The badge is read from
`transport.describe().mode`, off the object holding the bytes, never from the build-time
selection beside it: two places for one fact is one place for them to disagree.

In REPLAY the root injects the real in-browser verifier and drives it before any surface
asks for a frame. There is no permissive default, no `?skip_verification`, and no null
case — `BundleTransportOptions.verifier` is required. A bundle that does not verify
produces a panel, not a screen.

---

## 4. Verified in a browser, against a real database

Not asserted — run, on 2026-08-10, with the built `dist/` and a single local origin
serving `dist/` plus `/v1/*` through the real Lambda handler
(`mainline_demo_api.app.handler`) against CockroachDB CCL **v26.2.5** on the local node.
That is the same two-behaviours-one-origin shape CloudFront gives the deployed demo, so
there was no CORS to paper over.

**LIVE** — `VITE_MAINLINE_API_BASE=http://127.0.0.1:8787`, `#/gate?permit=aee27ab8-…`:

```
honesty chrome   transport = LIVE      clock skew = −191 ms   seal = NOT VERIFIED
source chrome    LIVE   http://127.0.0.1:8787   [switch to REPLAY]
gate surface     the permit, its seven projected counters and the CHECK that reads each,
                 every value carrying a db:column provenance chip
```

The clock skew is the proof that this was an exchange rather than a render: it is
`server_date − Date.now()`, and only a payload can supply the first half.

**REPLAY** — `VITE_MAINLINE_BUNDLE_URL=./bundle/` only, the bundle staged into
`dist/bundle/`:

```
honesty chrome   transport = REPLAY   seal = VERIFIED IN THIS BROWSER   bundle = 4ab2e066046e
source chrome    REPLAY   ./bundle/   (no switch — this build carries one source)
verifier         21 file digest(s) recomputed in this browser and all matched;
                 1 check(s) were NOT RUN and are listed below.
                 ledger/checkpoint-000005.note  skip:checkpoint-signature —
                 no verification key is configured
press POST /v1/permits/018f3a2f-…/merge  →  23514   gate_closed_when_issued
```

Both `data-sqlstate="23514"` and `data-constraint="gate_closed_when_issued"` were read out
of the live DOM, and the screen simultaneously carried the STAGED badge declaring the
fixture bundle hand-authored — the honesty machinery working on the same screen as the
claim.

**Switching** — with both variables set, one click moved the badge LIVE → REPLAY and back,
the surface node below it was never remounted, and the seal was withdrawn on the way back
rather than left reading `VERIFICATION FAILED` beside live bytes.

**The failure path** — with `./bundle/` absent, the reader gets:

```
verification failed — no frame was served
manifest is not JSON: SyntaxError: Unexpected token '<', "<!doctype "... is not valid JSON
```

which is the correct diagnosis of an SPA host answering a missing bundle with `index.html`,
and no surface below it was given a frame.

---

## 5. CI

`pnpm run ci` = `lint && typecheck && test && vite build && check:budgets && check:licences`.

**It had never been invoked before today.** It was expected to be red; it was not. Both
runs, before and after this worker's changes:

| | before | after |
|---|---|---|
| `eslint . --max-warnings 0` | clean | clean |
| `tsc` × 2 projects | clean | clean |
| vitest | 78 files, **1438** tests, all passing | 79 files, **1461** tests, all passing |
| `vite build` | ✓ | ✓ |
| `check:budgets` | PASS 70.1 KB / 220 KB | PASS 124.6 KB / 220 KB |
| `check:licences` | 372 audited, 12 licences, all permissive | unchanged |

`tests/unit/app/composition.test.tsx` (23 of the 23 added) asserts the four properties the
composition root exists to have: nothing is constructed when nothing is configured; one
live transport reaches all six surface contexts; a bundle whose verifier rejects serves no
frame and renders a failure state; and switching changes the badge and nothing else —
asserted by **DOM node identity**, so a switch that quietly remounted the surface would
fail.

---

## 6. Known gaps — what this build does not yet do

* ~~**`POST /v1/demo/gate-run` is not addressable from the console.** The four-beat driver
  is written, styled, tested and mounted, and on the running console it renders an
  actionable absence naming the three files that must declare the endpoint — none of which
  this worker owns:
  `src/data/resources.ts` (a seventeenth `declare()`), `src/data/contracts.ts`
  (`gate-run.schema.json` registered, as a verbatim copy of the demo-api's), and
  `verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py`
  (`Route("POST", "/v1/demo/gate-run", "demo_gate_run")` plus a `SCHEMA_IDS` entry).~~
  **CLOSED 2026-08-14 IN THE TREE. Not yet closed in the deployed artefact — see §7.**
  All three files named above now carry what the struck text asked for, and each half was
  re-measured rather than taken from the bullet that asked for it:
  `resources.ts` carries **17** `declare()` calls and **17** `RESOURCE_KEYS`, the
  seventeenth being `demo_gate_run`; `contracts.ts` registers `gate-run.schema.json`, whose
  console copy is **byte-identical** to the demo-api's (both 23,138 B, both
  `sha256:0948f853f65a29ff…`, compared as bytes); and `app.py:229` carries
  `Route("POST", "/v1/demo/gate-run", "demo_gate_run")` as the seventeenth route. Measured
  against the deployed Function URL on 2026-08-14 that path answers **`503 dsn_unset`**,
  which is a reachable endpoint refusing honestly — **it does not 404**.
  `docs/deploy/gate-run-contract.md` §9 records the same closure from the other side, with
  the one API-side item that is genuinely still open (`SCHEMA_IDS`).
  The struck text stays because it is the record of a gap that was real; what it stopped
  being able to say is that the endpoint is unreachable, and
  `tests/deploy/test_docs_are_true.py::test_no_live_document_asserts_the_demo_route_is_unrouted_or_404s`
  now goes red against any document that says it again.
  While the deployed artefact remains the pre-fix one, the three beats are reachable in the
  demo only through the gate surface's own single merge attempt — which does render `23514`
  / `gate_closed_when_issued` verbatim (§4), but not the projection-drift attack or the
  admission, because those need a savepoint a browser cannot hold.
* **The demo subject is write-protected (`423`).** `gate-run-contract.md` §7 states that a
  mutating transition aimed at the seeded demo permit is refused, so one judge cannot brick
  the demo for the next. If that holds as written, the deployed LIVE console's merge
  control answers `423` with a plain error body, which the transport classifies as a
  `status` failure and the surface renders as one — correct, and not a refusal. **This is
  the reason the LIVE demo is not yet the full three beats.** It is *not verified here*:
  the only migrated database on this machine belongs to another worker's fixture and this
  session made GET requests exclusively, because a POST would have mutated it. Whoever
  seeds the demo subject should press the control once and record what comes back.
* **`.env.demo.local` is not ignored by git.** The root `.gitignore` has `.env`, which
  does not match `.env.demo.local`. This document deliberately routes Phase 2 through an
  environment variable instead, so no `.local` file is needed — but if one is ever
  created, `.gitignore` needs a line. Not this worker's file.
* **No Playwright spec covers the composition root.** `tests/browser/gate.spec.ts` and its
  siblings belong to the cinema-conformance-harness worker. The browser evidence in §4 is
  a measured session, not a spec that will re-run in CI.
* ~~**Sourcemaps are shipped** (§2). Stated here because it is a decision, not an oversight.~~
  **CORRECTED 2026-08-14: they are BUILT here and do NOT ship.** `--strip-source-maps` is
  the default in both Lambda builders and the deployed tree carries **0** maps, refused on
  every build by `bundle_manifest.py --forbid-source-maps`. Still a decision rather than an
  oversight — just the opposite decision from the one this line recorded. See §2.

---

## 7. The packaging transport guard — `--console-transport`

**Added 2026-08-14, because a REPLAY console was packaged for an origin that had a live
kernel behind it, and nothing in the pipeline objected.**

### 7.1 What the deployed artefact actually carried

Not inferred from the build command. Extracted from the JavaScript the Function URL served,
on 2026-08-14, by fetching the entry chunk and grepping it:

```bash
curl -s https://<the demo URL>/ -o index.html
grep -o 'assets/[A-Za-z0-9._-]*\.js' index.html            # → assets/index-DzVoV1YM.js
curl -s --compressed https://<the demo URL>/assets/index-DzVoV1YM.js -o app.js
grep -o 'VITE_MAINLINE_[A-Z_]*:"[^"]*"' app.js | sort -u
grep -o 'buildId:"[^"]*"' app.js
```

```
VITE_MAINLINE_API_BASE:""
VITE_MAINLINE_BUNDLE_URL:"./bundle/"
VITE_MAINLINE_LOG_VKEY:""
MODE:"demo"
buildId:"dev"
signaturePath:"unknown"
```

The entry chunk is **124,177 B** over the wire with `accept-encoding: gzip`, and it contains
**zero** occurrences of `gate-run`, `gate_run` or `demo_gate_run`.

> **Two `buildId` literals are in that file and only one of them is this build's answer.**
> The `grep` above returns `buildId:"dev"` *and* `buildId:"unknown"`, and they come from
> two different places:
>
> * `src/app/App.tsx:127` compiles
>   `buildId: typeof __MAINLINE_BUILD_ID__ === 'string' ? __MAINLINE_BUILD_ID__ : 'dev'`,
>   and `vite.config.ts:76` defines that constant as
>   `JSON.stringify(process.env['MAINLINE_BUILD_ID'] ?? 'dev')`. The minifier folds the whole
>   ternary to **one** literal, and on this artefact that literal is `"dev"` — **the value
>   the build falls back to when `MAINLINE_BUILD_ID` was not in the environment.**
> * `src/app/honesty.ts:57` carries `buildId: 'unknown'` as the EMPTY honesty record's
>   constant. It is in **every** build ever made and says nothing about this one.
>
> So the gate keys on the **presence of `"dev"`**, never on "there is exactly one build id" —
> a rule of that second shape would have been red on every artefact in the project's history.
> Reported here because a reader running the `grep` gets two lines and should not have to
> guess which one is the claim.

Read those six lines against §1's table and the artefact explains itself. `src/app/source-select.ts`
treats `""` as unset — its `trimmed()` returns `null` for the empty string — so **exactly one**
source was configured, `switchable` was false, and the honesty chrome read **`TRANSPORT REPLAY`**
with no control to change it. The bundle it plays declares `"staged": true`, which is why the badge
reads `REPLAY (staged)`. **Every byte on that screen was a recording**, on an origin whose
`/v1/*` routes reach a real handler.

`buildId:"dev"` is a **second** defect in the same artefact and a worse one to explain:
`MAINLINE_BUILD_ID` was never supplied, so the honesty chrome could not name the artefact a
screenshot came from — which §1's table says is the entire reason that field exists.

### 7.2 Why the existing warning did not fire, and could never have fired for this build

`build_lambda.sh` has had a console detector since it was written, and it prints a warning
when a `dist/` carries neither source variable. The warning is real, it is quoted in
[`RUNBOOK.md`](RUNBOOK.md) §5.6.0 step 1 from a live transcript — and it **cannot fire for a
`--mode demo` build**, which is the only build the deploy ships.

The reason is one line. `probe_console()` collects the compiled literals with

```
ENV_LITERAL = re.compile(r'(VITE_MAINLINE_[A-Z_]+):"((?:[^"\\]|\\.)*)"')
…
found.setdefault(key, value)
```

— **keyed on the variable NAME, with no test on the VALUE.** `.env.demo` declares
`VITE_MAINLINE_API_BASE=` (empty, deliberately: §1 explains that Phase 1 is the default), so
Vite inlines `VITE_MAINLINE_API_BASE:""` into every demo-mode build. `found` is therefore
never empty, the `if console["configured"]:` branch is always taken, and the `else` that
carries the warning is **unreachable code for this mode**. It printed, cheerfully:

```
console   VITE_MAINLINE_API_BASE=(empty), VITE_MAINLINE_BUNDLE_URL=./bundle/
```

and packaged it. **The machinery to notice existed; it was measuring the wrong thing** — the
presence of a name rather than the presence of a value.

> The `MODE=production` transcript in `RUNBOOK.md` §5.6.0 is not contradicted by this and was
> re-checked before this section was written. `pnpm run build` reads **no** `.env` file —
> the console has `.env.demo` and no `.env` — so Vite inlines neither key, `found` really is
> empty, and the warning really does fire. The branch is live for the build nobody ships and
> dead for the build everybody ships, which is the worst of both and is why a warning was
> the wrong instrument here in the first place.

### 7.3 The guard: a declaration, and a refusal

Ratified as ruling **R4** and **R5** of [`docs/leads/console-live-plan.md`](../leads/console-live-plan.md),
and implemented in `scripts/deploy/build_lambda.sh` and its PowerShell twin by the
`packaging-transport-guard` worker.

`probe_console()` now applies the same `trimmed()` semantics `src/app/source-select.ts`
applies — **an empty string is UNSET** — and reports the *effective* sources rather than the
present keys. On top of that the packer takes a **required** declaration of the transport the
operator intends:

```
--console-transport live | replay | both
```

and **refuses**, through the same `refuse()` path every other packaging invariant uses, when
the `dist/` it was handed does not carry what was declared. Under `--console-transport live`
it also refuses a `buildId` of `dev`, per R5.

**Naming it explicitly is the point.** A guard that *infers* intent has to be right about
intent, and there is no signal in a `dist/` that distinguishes "Phase 1 on purpose" from
"Phase 2 with the variable lost". This guard compares two things a human wrote down: what the
operator said they were shipping, and what the bytes say. It cannot be right or wrong about
intent because it is not guessing at it.

**It is a refusal, not a warning, and that is not a stylistic preference.** The warning that
already existed is the counter-example: a message on stdout in a ten-stage deploy is a message
nobody reads, and this one could not have been read even by somebody looking for it.
`continue-on-error` and `|| true` are banned repo-wide and are banned here.

The falsification test is the part that matters:
`tests/deploy/test_console_transport_guard.py` builds a synthetic `dist/` carrying **exactly
the three literals §7.1 measured off the deployed artefact** — `VITE_MAINLINE_API_BASE:""`,
`VITE_MAINLINE_BUNDLE_URL:"./bundle/"`, `buildId:"dev"` — and requires it to be **REFUSED**
under `--console-transport live` and **accepted** under `--console-transport replay`. A guard
with no test that proves it fires is a guard nobody has run, which is the state the old
warning was in for its entire life.

### 7.4 What this does not fix

**The deployed artefact is still the pre-fix one.** Everything in §7.1 was measured against
what the Function URL serves today, and it will keep serving it until the orchestrator
rebuilds and redeploys — no worker in this wave deploys anything. Until then a judge opening
the URL sees `TRANSPORT REPLAY (staged)`, `BUILD dev`, and no gate-run control.

> **Updated 2026-08-15 — the rebuild half has happened; the deploy half is not established
> here.** The package at `out/lambda/mainline-demo-api-arm64.zip` is now
> `sha256 6802872f805740dd1a7de891eca7a8d1cf6c11f5eb5b639aec5677f5d78ae13b`, packed
> `--console-transport live`, and the literals read back out of its packaged entry chunk are
> `VITE_MAINLINE_API_BASE:"/"`, `VITE_MAINLINE_BUNDLE_URL:"./bundle/"`, `MODE:"demo"` and
> `buildId:"3933b97"` — both sources present, and a build id that is not `dev`, which is what
> §7.3's guard exists to require. The entry chunk also carries `gate-run` eleven times, where
> the object §7.1 measured carried it zero times. **Whether that package has reached the
> Function URL this document does not say**: `evidence/deploy/judge-walk.json` still records
> `context.transport_mode` as `REPLAY` and an entry chunk of `assets/index-DzVoV1YM.js`, and
> re-running the walk against the origin is the step that would move that reading. Deploying
> remains the orchestrator's step.

**And a LIVE rebuild will not, on its own, produce a working gate run.** The Lambda cannot
read `/mainline/demo/cockroach_dsn` — the parameter does not exist, and writing it is the
founder's step. `GET /v1/health` and `POST /v1/demo/gate-run` both answer **503** naming that
parameter. What a correct LIVE build buys today is that the console **attempts its own
kernel** and renders the refusal verbatim instead of playing a recording. See
[`RUNBOOK.md`](RUNBOOK.md) §5.10 for what that looks like on screen and why it is worth
showing a judge rather than hiding.
