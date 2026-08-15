<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Re-certified 2026-08-15 — TENTH verification, and the first one taken by OPENING THE
CONSOLE IN A BROWSER rather than by reading its source.** Every number on this page came from
a command run on this machine today, against the tree described in §0. Suite totals are read
from `--junitxml` root elements and from nowhere else, and the artefact figures are read out
of the **zip's own central directory**, never out of a document and never out of `dist/`.
Deadline **2026-08-18**.

**VERDICT: NOT READY — and the addressing wave is a real, honest repair that stops one step
short of the deployment.** The console defects the founder found by clicking are **fixed and
re-measured here by clicking**: eight screens render real seeded data, the Gate opens on the
seeded permit with no query string, and the honesty strip's `unknown` chips now carry
sentences. **No invention was found anywhere in the wave** — §12.1, and that is the finding
this page cared about most. What blocks the verdict is §12.4: the seed's hex→base64
checkpoint repair is **correct in the file and cannot reach the deployed database**, because
every insert in §8 of `demo_world.sql` is guarded by `WHERE NOT EXISTS` and no statement in
the tree updates a `body` that is already there. Measured today against both the live URL and
a local database in the same state.

> **THE FRAMING THAT STILL MATTERS MORE THAN THE VERDICT.** The founder found every defect in
> the last wave by opening the URL and clicking. No test in this repository found any of them,
> because they all read source and none read what is served. **This verification was performed
> the way he performs one** — a real build, served by the real handler, driven in a real
> browser — and it found the remaining blocker the same way: not by reading the seed, but by
> re-running it and then asking the database what it now held. The seed's own comment
> diagnoses this exact failure mode one section higher up, for the checkpoint it deletes. The
> encoding fix one section lower repeats it.

---

## 0 · The tree this page is certified against

| | |
|---|---|
| local `HEAD` | `3933b97` — *evidence(deploy): the apply happened — 24 resources, the demo URL, and first light* |
| `origin/master` | **`3933b97` — level with local `HEAD`, 0 commits ahead** |
| working tree | **86 paths: 59 modified, 27 untracked, none staged** — this is the entire wave |
| of those 59 modified | **20 differ from `HEAD` in line endings only** (`git diff HEAD` sees 39 files, `git status` sees 59). See §2.4 |
| local CockroachDB | CCL **v26.2.5** on `127.0.0.1:26257` |
| interpreter | `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe` — pytest 9.1.1, ruff 0.16.1, node v24.14.0 (`uv` is not on PATH) |
| **package in the deploy path** | `out/lambda/mainline-demo-api-arm64.zip`, `sha256 6802872f805740dd1a7de891eca7a8d1cf6c11f5eb5b639aec5677f5d78ae13b`, 7,721,537 B, built **`--console-transport live`**, `MAINLINE_BUILD_ID=b822fdc`. **Untouched by this verification — read, never rebuilt.** |
| **package on the origin** | `sha256 12fcba7a…` — the **REPLAY** build the founder opened. Still what the Function URL answers with. |

**Those last two rows are the whole shape of this page.** They are two different artefacts and
this verification never lets them share a sentence.

**What the eighth verification said and what has changed since.** Its §2.4 reported eight LINT
regressions; they are **gone** (§2.4 below, measured). Its §8 reported a STOP on the response
ceiling; it is **resolved by ruling R10** and re-measured here (§8). Its §0 named the deploy
path as holding `12fcba7a…`; the orchestrator has since packed the LIVE console into it. Its
§3 reported the suite as `579 / 578` "in both orders"; **both halves of that sentence were
wrong and are corrected in §3** — the collection is 580 and the second run was not randomised.

**The verifications this page supersedes, named so that the preserved history in the HTML twin
stays checkable.** Nothing below is deleted from either syntax; a claim deleted is not a claim
corrected. Verification 4 certified `073dfea`; 5 and 6 certified `eefae1c`, with `898ad55` —
*"a judge can now sign"* — the commit that made their struck claims false; 7 certified
`d098721`, then four ahead of the public `7535670` by `5e6932e`, `f68abb7`, `c9a7253`,
`d098721`; 8 certified `3933b97` plus 77 paths. **All of that is now behind `3933b97`, which is
public.**

---

## 12 · THE JUDGE-EYE WALK — the tenth verification, taken in a browser

**Method, stated first because it is the point.** A real `vite build` with
`VITE_MAINLINE_API_BASE=/`, served by `scripts/deploy/local_furl.py` — which calls the same
`mainline_demo_api.app.handler` the Lambda carries — against a local CockroachDB v26.2.5
holding the demo world. Every screen below was opened in Chrome and read off the page. The
live Function URL was measured directly for the two claims that are about the deployment.

### 12.1 · NO INVENTION — the first check, and it passes

**Nothing in this wave mints a row, a seal, a checkpoint or a tick that the kernel did not
produce, and no claim was weakened to make a screen render.** The three highest-risk diffs
were read in full and each survives:

| Change | What it actually is | Verdict |
|---|---|---|
| `demo_world.sql` §8.4 — a `DELETE` in a seed file | Retires a checkpoint whose `root_hash` **is** `digest('mainline-demo/ledger/root/' \|\| tree_size)` and appears in no `ledger_node`. Measured on the **live URL** today: `GET /v1/ledger` serves three checkpoints, and the one at `tree_size = 1` has root `74f0845f11c5992b…`, which is **exactly** `sha256("mainline-demo/ledger/root/1")`. The row is a fiction and this removes it. | **Removal of an invention, not an invention** |
| `demo_world.sql` §8.5 — `encode(n.hash,'hex')` → `encode(n.hash,'base64')` | `spec/wire/checkpoint.md` (v1.0, frozen 2026-08-07) line 86 fixes note line 3 as *"base64 of the 32-byte RFC 6962 Merkle Tree Hash"*. The seed wrote hex, which base64-decodes to **48 bytes**. Same `n.hash`, re-encoded — no digest typed. | **Correct against the frozen spec** |
| `checkpoint.json` — `no-blank-line` reclassified `malformed` → `unsigned` | `spec/wire/checkpoint.md` §10 item 6 lists **exactly four** required refusals and this is none of them. `ledger.ts` orders `failed` → `malformed` → `unsigned`, so a bad signature and an unparseable note both still fail **before** `unsigned` is reachable. `unsigned` maps to **SKIP, never PASS**. | **Not a relaxation** |

The seed still computes every hash in the database; no hex literal was introduced. `GRANTS.yaml`
grew by documenting roles and memberships that **already exist on the live cluster** (the
`trappoint` USAGE grant was hand-granted 2026-08-14 and recorded in `evidence/deploy/LIVE.md`);
it declares no privilege the deployment does not hold.

### 12.2 · THE SCREENS — eight render real seeded data, two declare themselves unbuilt

The addressing repair is real and it is the right one: `GET /v1/demo/subjects` makes the
**kernel name its own subjects out of its own tables**, and `src/data/demo-subjects.ts` carries
no fallback literal. Against the local kernel the index answers `absent: []` — every subject
the console addresses exists.

| Screen | Before (founder, 2026-08-14) | Now, read off the page |
|---|---|---|
| **Overview** | did not exist | **Renders.** Three use cases in plain English, each linking to a seeded subject; states *"The identifiers behind the links were read from `GET /v1/demo/subjects` just now — none of them is written into this console."* |
| **Gate** | *"NO SUBJECT ADDRESSED"* | **Renders `DEMO-PTW-0001` with no query string**, and says which of three origins named it. §12.3 |
| **Diff** | `HTTP 404` on an invented clause | **Renders** clause `dec0de00-0004-…` at the seeded head commit |
| **Custody** | `HTTP 404` — no rows for `BLK-07` | **Renders** the seeded site. `BLK-07` — a string that had leaked out of a test vector — is gone. §12.4 |
| **Evidence** | *"Failed to construct 'URL': Invalid base URL"* | **Renders.** Says *"no capture was consulted, that fact in words rather than a blank"* |
| **Audit** | every aggregate *"No rows"* | **Renders** — `views carried 14`, `views that returned rows 6 of 14` |
| **Propagation** | — | **Renders** with a `STAGED` badge stating the three governing tables do not exist in any migration |
| **Silence** | — | **Renders** with `STAGED`, the conservation identity and the PER limit |
| **Ancestry**, **Disposition** | — | **`NOT BUILT YET — K3 owes it` / `K5 owes it`** in the sidebar. Declared, not faked. |

All twelve read routes answer `200` against the local kernel. `POST /v1/demo/gate-run` answers
**`PROVEN`** with the four beats `00000 → 23514 → P0001 → 00000`.

### 12.3 · THE GATE ON ARRIVAL — yes

With no query string the Gate opens on the seeded permit and prints, on screen:

> *"The console asked this deployment which permit it seeded, at GET /v1/demo/subjects, and
> this is the identifier that read returned."*

There is no default and no literal: `SubjectOrigin` is `address | index | demo-run`, an address
always wins, and a run's subject can only fill a slot the other two left empty. The plain band
opens *"A permit is a written authorisation for one specific piece of work"* and the precise
machinery — constraint names, SQLSTATEs, `db:column` provenance chips — is one disclosure away.

### 12.4 · THE BLOCKER — a correct repair that cannot reach the deployment

**The hex→base64 fix in `demo_world.sql` §8.5 is unreachable on any database that already
holds those checkpoint rows.** Every insert in §8 is guarded by `WHERE NOT EXISTS`; there is no
`ON CONFLICT DO UPDATE` and **no statement anywhere in the tree updates
`mainline.ledger_checkpoint.body`** (the only three matches are nemesis attack fixtures).
`scripts/deploy/reconcile_demo_checkpoints.sql` deletes the self-naming row and, by its own
statement, touches nothing else.

**Measured, not reasoned:**

| Database | Action | `body` line 3 |
|---|---|---|
| live `mainline_demo` (Function URL, today) | — | 64 hex chars → decodes to **48 bytes** |
| local `mainline_demo` (same state) | **re-ran `seed_demo.py` — `OK, attempts=1`** | still 64 hex chars → **48 bytes** |
| fresh scratch database | first seed | `v13D5bJFio5XjbmEHJaQJ7uz…` → **32 bytes** |

So on the deployed database the custody screen reads, verbatim:

> **the custody ledger: verification FAILED.** … *check 4 `log_signature`* — *"the root line
> decodes to 48 bytes; spec §3 requires exactly 32 bytes"* … *check 10
> `canonicaliser_identity`* — *"carries a note that will not parse"*

`7 / 2 / 6`, and the honesty strip's **SEAL** reads **`VERIFICATION FAILED`** in red. On a
correctly seeded database the same build reads **`NOT VERIFIED`**, `0` failed, and the strip
says *"every check that ran passed, but 8 were NOT RUN … A report containing a SKIP is not a
clean report."* The whole difference is whether the deployment is recreated or reconciled.

**Nothing in the repository would catch this.** `verify_demo_checkpoints.py` computes
`root_line_is_hex_of_root` and `root_line_decodes_to_bytes` and **reports** them; nothing
asserts either. It is the founder's pattern exactly — a defect that only exists in what is
served. The `unsigned` verdict added this wave is, against the deployed data, dead code: the
note never parses, so `malformed` wins first.

### 12.5 · THE HONESTY STRIP — five of the founder's five chips answered

| Chip | 2026-08-14 | Now |
|---|---|---|
| BUNDLE | `unknown` | **`none consulted`** + a paragraph distinguishing it from a digest that could not be recomputed |
| SEAL | `NOT VERIFIED` | a **measured verdict** — `VERIFICATION FAILED` (hex data) or `NOT VERIFIED` (correct data) |
| CORPUS ROOT | `unknown` | the real root, chipped `db:column` |
| CLOCK SKEW | `unknown` | `−657 ms`, chipped `recomputed` |
| SIGNATURE PATH | `unknown` | **`none compiled`** + why (no GT-15 attestation at build time) |

Three chips still carry the `unset` marker, and **each now states its reason in a sentence**
rather than showing a bare `unknown`. The `unset` provenance is unchanged, which is correct:
nothing was established either way. One residual — `CORPUS ROOT` and `CLOCK SKEW` read
`unknown` when Custody is opened as the **first** screen, because they are published by
surfaces the reader has not visited yet. Order-dependent, honest, worth closing.

### 12.6 · THE PRIVILEGE CONFORMANCE TEST — one direction is falsifiable, one is not

`scripts/qa/privilege_conformance.py` exists and is serious. Baseline: **120/120 granted pairs
reachable, 256/256 ungranted pairs refused with `42501`, 0 differences.**

* **Negative direction — FALSIFIABLE.** Granting `SELECT ON mainline_qa.v_my_record` to
  `mainline_api` (a pair the matrix does not name) turns it red with a precise finding:
  *"the matrix does NOT grant this and the cluster allowed it — expected 42501, observed
  00000"* → **`VERDICT PRIVILEGE CONFORMANCE FAILED`**. This is the direction that matters for
  an `authorization_type = NONE` endpoint, and it works.
* **Positive direction — NOT FALSIFIABLE AS RUN.** `REVOKE SELECT ON mainline.permit FROM
  mainline_api`, then re-probe: **`PRIVILEGE CONFORMANCE HOLDS`, 120/120, exit 0** — and the
  grant was back afterwards. `main()` calls `apply_matrix()` unconditionally before probing,
  in `--database` (borrowed) mode too, so the probe **repairs the defect it is meant to
  detect**. There is no `--no-apply`. A missing grant cannot make it red.

### 12.7 · THE SUITE, THE PROOF, AND ONE NEW RED

* **Lane (`demo-api` + `tests/deploy`), `--crdb=reuse`, from `--junitxml`:
  983 collected / 981 passed / 1 FAILED / 0 errors / 1 skipped.** Baseline was
  911/910/0/0/1 — 72 tests added, and **one is red**. **Identical in both orders**
  (randomised default, and `-p no:randomly`): same single failure, 196 s each.
* **A caution about scope, recorded so nobody repeats it.** A first run of bare
  `pytest --crdb=reuse` at the repo root collects **10,594** tests across every package in one
  interpreter and reports 184 failed / 111 errors. That is **not** a regression signal — it is
  the wrong shape. `qa/test-state.json` runs each distribution in its **own pytest
  subprocess**; a single-process monorepo run collides on imports. The lane above is the
  comparable measurement.
* The red is **new and honest**:
  `test_privilege_census.py::test_every_routine_the_demo_api_calls_holds_execute_from_some_authority_here`.
  It finds that `trappoint.explain_refusal` (called at `refusal.py:141`) holds `EXECUTE` from
  **no authority this repository declares**, and says so at length: *"on an
  `authorization_type = NONE` endpoint an undeclared privilege is the defect whether or not it
  is currently held."* It is a control that went red on first contact. **It is not registered
  in `qa/cluster-known-red.json` or any skip census** — no banned exemption was added.
* **Gate proof: `VERDICT PROVEN`, caveats `(none)`.** `PROJECTION 10/10 held`;
  `REFUSAL REFUSED [23514] gate_closed_when_issued (reported)`;
  `DRIFT REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)`; `ADMISSION ADMITTED [00000]`.
* **Console vitest: 103 files / 1937 tests / all passed.**

### 12.8 · READING LEVEL — an on-ramp, and no claim went vaguer

The tracked before/after on Custody's standards sentence is a **strengthening**. Before, one
flat list implied all four checks ran. After, it is inside a disclosure with the fourth
separated: *"The ECDSA P-256 signature over the checkpoint note is checked too — whenever a
checkpoint carries one and this reader holds a key."* The wave's own comment is right that the
old sentence *"was crediting this browser with work it had not done"*. **Not one precise term
was removed** — `RFC 8785`, `RFC 6962`, `ECDSA P-256` all survive verbatim, one control away.

### 12.9 · A SIZE RISK, NOT YET A BLOCKER

The entry chunk is **138,156 B gzipped against the 139,264 B (`136 * 1024`) response
ceiling — 1,108 bytes of headroom.** `budgets.json` bounds the entry *closure* at 220 KB and
**nothing bounds a single asset against the wire ceiling**. A served asset over the ceiling is
a `413`, and a `413` on the entry chunk is the *"MAINLINE CONSOLE — NOT YET BOOTED"* screen —
observed on this machine before the gzip siblings were generated. The ceiling itself is
**unmoved at `136 * 1024`**.

### 12.9a · WHAT THIS VERIFICATION DISTURBED, DECLARED

Three things, none of them tracked and none of them a claim on this page:

* **`verticals/mainline/apps/console/dist/` WAS REBUILT** (twice) and had 70 `.gz` siblings
  written into it by hand, because a browser walk needs a served artefact and `vite build`
  alone does not emit the pre-compressed siblings `build_lambda.sh` produces. `dist/` is
  `.gitignore`d (line 10) and the zip in the deploy path was **not** touched — but **§4.2's
  "`console/dist` undisturbed and byte-identical to the zip" is no longer true of this working
  tree**, and the orchestrator should rebuild through `build_lambda.sh` rather than pack what
  is there now.
* **Local databases `mainline_demo` and one scratch database were seeded**, to measure the
  before/after in §12.4. Local only; the deployed cluster was **read** and never written.
* **One grant was revoked and one granted on a scratch database** for §12.6, and both were
  restored — re-verified afterwards: `mainline.permit` holds `SELECT, UPDATE` again and
  `mainline_qa.v_my_record` holds nothing.

No commit was made, nothing was deployed, no AWS call was issued, no SSM parameter was
written, and no DSN or credential appears anywhere in this page.

### 12.10 · WHAT A JUDGE SEES, CLICKING THE SIDEBAR TOP TO BOTTOM

Ten entries. This is the walk after the orchestrator redeploys, **and it forks at Custody**
depending on whether the deployed `mainline_demo` is recreated or only reconciled.

1. **Overview — what this refuses, and why.** Opens *"The answer this system is built to give
   is 'no'."* Three cases in plain English, each ending in a link addressed to a seeded
   identifier. This is the fix for *"present a couple of exceptional use cases"*, and cases 1
   and 2 are backed by real rows. Case 3 (Silence) carries a `STAGED` badge before its numbers.
2. **Gate — the refusal.** Opens on `DEMO-PTW-0001` **with no query string**, says the kernel
   named it, and offers four controls. `RUN ALL` returns `PROVEN`: read `00000`, merge
   **REFUSED `23514 gate_closed_when_issued`**, forged-counter **REFUSED `P0001
   mainline.fn_permit_merge_gate`**, signed disposition **ADMITTED `00000`**. This is the
   demo, and it works.
3. **Diff — what "weakened" meant.** Clause `7.3.2(b)` at the seeded commit, with the CAT
   comparison recomputed in the browser.
4. **Custody — the chain.** **Fork.** If the database was recreated: `NOT VERIFIED`, **0
   failed**, 8 not run, each named. If it was only reconciled — which is what
   `reconcile_demo_checkpoints.sql` alone does — **`verification FAILED`, 2 red checks**, both
   for the 48-byte root line, and the SEAL chip is red across every screen in the console.
   **This is the one thing standing between the walk and a clean read.**
5. **Evidence — the bundle.** No longer a URL exception; states that no capture was consulted.
6. **Audit — the MCP surface.** 14 views carried, 6 returning rows.
7. **Propagation — where the lesson travelled.** `STAGED`, with an unusually candid note that
   the three governing tables exist in no migration.
8. **Silence — what was not surfaced.** `STAGED`, conservation identity recomputed in-browser.
9. **Ancestry** and 10. **Disposition** — **`NOT BUILT YET`**, each naming the worker that owes
   it. A judge sees an honest gap, not a broken screen.

**The honesty strip rides above all ten** and is now readable: transport `LIVE`, and every
`unset` chip carrying a sentence for why.

---

## 1 · The verdict

**Superseded by §12 where the two disagree.** The rows below were measured by the ninth
verification and are retained unedited; §12 is today's.

| # | Condition | Status | Where measured |
|---|---|---|---|
| 1 | No shortcut in the wave's diff | **MET** | §2 |
| 2 | `DEFAULT_MAX_RESPONSE_BYTES` unmoved at `136 * 1024` | **MET** | §2.1, §8 |
| 3 | The straddle holds and **exactly one** identity object is refused | **MET** | §8 |
| 4 | The re-recorded constants match the zip that ships | **MET** | §4 |
| 5 | The artefact starts **LIVE** | **MET** | §4 |
| 6 | `console/dist` undisturbed and byte-identical to the zip | **MET** | §4.2 |
| 7 | Suite green in both orders, no regression | **MET** — 580/579/0/0/1 | §3 |
| 8 | The ruff **LINT** ratchet holds | **MET** — 0 regressions, 1 improvement | §2.4 |
| 9 | Gate proof PROVEN, caveat-free | **MET** | §7 |
| 10 | The documents quoting these figures say true things | **NOT MET** — one block in one file | §6 |
| 11 | The origin serves the fixed console | **NOT MET** | §9 |

**Three things remain, in the order they have to be cleared:**

1. **§6 — `evidence/deploy/APPLIED.md` lines 145 and 166–181 describe a deploy path that has
   moved.** It states that the zip on disk is the 2026-08-14 REPLAY artefact and that *"No
   package was rebuilt into the deploy path"*. Both were true when written and both are now
   false. **This is the orchestrator's document and this verification does not edit it.**
2. **§9 — the redeploy.** The orchestrator's step. Nothing here may perform it.
3. **The SSM parameter.** The founder's step, and nobody else's. Until it lands the origin
   answers `dsn_unset`, which is the **correct** answer of a reachable route and is reported
   as such throughout this page.

---

## 2 · NO SHORTCUTS — the first check, and the one this wave had to survive

The wave re-recorded a family of constants that ratchets are built on. Every one of them was
re-read from the artefact here, and the question asked of each was not *"is it green?"* but
*"was it allowed to move, and did anything move with it that was not allowed to?"*

### 2.1 · The ceiling did not move, and nothing was weakened to let the tree past it

```
verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py:279
    DEFAULT_MAX_RESPONSE_BYTES: Final = 136 * 1024

git diff HEAD -- .../static_site.py   ->  no output; the file is byte-identical to HEAD
imported and evaluated              ->  139264,  == 136 * 1024,  == 139_264
```

**The module that owns the bound is not in the wave's diff at all.** The only change to
demo-api production source in the entire wave is **one line** — `envelope.py` gaining
`"demo_gate_run": f"{CONTRACT_BASE}gate-run.schema.json"`. Everything else the wave touched is
tests, documents, evidence, console TypeScript and the two deploy scripts.

### 2.2 · What moved, why it was allowed to, and the ruling that says so

The re-recorded constants are `_LARGEST_WEB_OBJECT{,_BYTES}`, `_LARGEST_SERVED_OBJECT{,_CODING,_BYTES}`,
`_WIDEST_SERVED_IDENTITY{,_BYTES}`, `_REFUSED_BY_THE_CEILING`, the three `web/` totals, and
`test_static_site.py`'s `_LARGEST_SERVED_WIRE_BYTES` / `_LARGEST_IDENTITY_BYTES`. Under
**R1** these are *measurements of a build*, and under **R5** they are the derived side. Their
subject moved — the console source grew when `demo_gate_run` and its 23,138 B contract were
declared — so re-recording them **to** the artefact is a ratchet following its subject, which
is R9, and is the opposite of moving a floor.

**Ruling R10** (`docs/leads/reconcile-constants-plan.md` §1, restated in
`docs/decisions/response-ceiling-authoritative-tree.md` §10) is the decision that made this
wave possible, and this verification endorses it as correctly reasoned and correctly bounded:

> `DEFAULT_MAX_RESPONSE_BYTES` remains `136 * 1024 == 139_264`. The live law is interface
> **I3**, the **straddle**, and **exactly one** identity object refused. The derivation
> `ceil(floor(1.10·g)/8192)·8192` is demoted to **dated provenance** — it records how 139,264
> was *chosen*, over the tree it was chosen from, and is no longer asserted against a tree it
> did not choose from.

It is answer **(a)** of the two available, it names its authority (R5's enumeration of the
authoritative facts, which never included the formula; R4, which reserved this decision to a
lead; R1's reproducibility gate; the founder's condition that bounds exist in code), and it
closes with the two facts that cut against it stated out loud. **147,456 was not taken**, and
the code makes taking it impossible: `assert ceiling <= derived` fails the moment anybody
raises the ceiling to meet the arithmetic.

**The shape in code is the part a reviewer should check, and it holds.** Two constants, two
roles, distinguishable at a glance:

* `_CEILING_PROVENANCE_G = 124_177` — **frozen**, never re-measured, and
  `test_the_ceiling_still_equals_the_number_its_derivation_chose` derives 139,264 from it and
  asserts equality with `DEFAULT_MAX_RESPONSE_BYTES`. **The ceiling can never be re-chosen
  silently**, because any edit to it breaks this equality.
* `_LARGEST_SERVED_WIRE_BYTES = 129_400` — today's measurement, and
  `test_the_live_law_holds_over_the_tree_that_ships_today` asserts I3 and the straddle over it.

### 2.3 · Nothing was deleted, skipped, xfailed or exempted — proven by node id, not by reading

`git diff HEAD` over `tests/` and `verticals/` introduces **no** `pytest.mark.skip`, no
`pytest.mark.xfail`, no `pytest.skip(...)`, no `continue-on-error` and no `|| true`. Four test
functions disappear by name and fifteen appear. The junit `<testcase>` sets settle what that
means, element by element against the wave's own baseline `qa/lint-after.xml`
(579 / 570 / **8 failed** / 0 / 1):

```
removed from the baseline : test_the_ceiling_is_the_derivation_and_not_a_number_somebody_liked   (1)
added                     : test_the_ceiling_still_equals_the_number_its_derivation_chose        (2)
                            test_the_live_law_holds_over_the_tree_that_ships_today
every other node id       : IDENTICAL
```

**One test was split into two. Nothing else left the suite.** The other three renames are
counts inside test names moving with their subject (`289_312 → 295_724`, `sixteen → seventeen`
resources, and the route-table pair test), and each replacement asserts *more* than the one it
replaced — `declared == routed` with **no permitted exception** where the old case allowed
`routed - declared == {DEMO_ROUTE}`.

**And all eight baseline failures now pass under their original node ids**, which is the only
form of "the failures are fixed" that cannot be faked by renaming:

```
PASS  test_response_contract::test_the_ceiling_refuses_something_it_governs
PASS  test_response_contract::test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses
PASS  test_response_contract::test_the_built_web_tree_has_not_outgrown_its_declaration
PASS  test_response_contract::test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal
PASS  test_response_contract::test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal
PASS  test_response_contract::test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed
PASS  test_static_site::test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from
PASS  test_static_site::test_serving_the_deployed_package_derives_the_ceiling_end_to_end
```

**Two apertures were WIDENED and none narrowed.** `SWEPT_DOCS` in `test_docs_are_true.py` now
covers `evidence/deploy/APPLIED.md` and `docs/ci/cluster-lane-package.md` on top of
`LIVE_DOCS`, pinned by a named ratchet; `docs/CI-STATE.md` is **+276 lines, 0 deletions**;
`docs/HONESTY.md` is untouched; every file in `qa/` that holds a ratchet baseline is
**unmodified** — the only new thing in that directory is a junit XML.

### 2.4 · THE RATCHET — the LINT half is clean, and the FORMAT half is a CRLF artefact, proven

`python scripts/qa/ruff_ratchet.py`, ruff 0.16.1, the version `qa/ruff-ratchet.json` records:

```
ruff 0.16.1  |  lint findings 656  |  unformatted files 223

  LINT improved     rule=E501  tree=scripts/  baseline=1  measured=0  (-1)

  LINT REGRESSIONS: none.

  FORMAT REGRESSION  rule=unformatted  tree=<repo>                 0 -> 223
  FORMAT REGRESSION  rule=unformatted  tree=other/                 0 -> 3
  FORMAT REGRESSION  rule=unformatted  tree=packages/mainline-*    0 -> 5
  FORMAT REGRESSION  rule=unformatted  tree=packages/trappoint-*   0 -> 50
  FORMAT REGRESSION  rule=unformatted  tree=scripts/               0 -> 8
  FORMAT REGRESSION  rule=unformatted  tree=tests/                 0 -> 106
  FORMAT REGRESSION  rule=unformatted  tree=verticals/             0 -> 51
```

**All eight LINT regressions the eighth verification reported are gone, and one rule improved.**
The script still exits 1, on the FORMAT half alone.

**The FORMAT half was not accepted on assertion; it was measured.** Every one of the 223
flagged paths was read, and its worktree bytes compared with `git show HEAD:<path>` after
normalising `\r\n` to `\n`:

```
flagged paths                                       223
containing CRLF                                     222
byte-identical to HEAD after newline normalisation  222
genuinely different from HEAD                         1  -> docs/leads/reconcile-constants-plan.md
                                                          (new, untracked; a Markdown lead plan
                                                           whose embedded Python blocks ruff reads)
```

**222 of 223 are this Windows checkout's line endings and nothing else.** `ruff format` across
the repo would rewrite 222 files it has no business touching, so it was **not run**, per the
standing instruction. The one remainder is a new lead document, not code, and it lands in the
`other/` bucket that the CRLF noise already occupies.

**A consequence worth naming, because it bears on §4.3.** Twenty of the 59 modified paths are
console sources that differ from `HEAD` **only** in line endings, and one of them is a CSS
module (`src/design/primitives/instrument.module.css`). CSS-module class names hash the file's
bytes. A console rebuilt from this worktree may therefore emit a chunk under a *different*
content hash at the same length — the documented `index-BKZMI9SJ.js` hazard. It does not
affect what ships, because `dist/` and the zip already hold the same bytes (§4.2); it is the
reason the constants in the tests name the artefact **by digest**.

---

## 3 · THE SUITE — 580/579/0/0/1, and a correction to the previous reading

`.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api --crdb=reuse -q
-p no:cacheprovider --junitxml=<path>`. Every number read from the `<testsuite>` root element
and cross-checked against the terminal summary.

| reading | collected | passed | failed | errors | skipped | wall |
|---|---:|---:|---:|---:|---:|---:|
| baseline this wave was handed (`qa/lint-after.xml`) | 579 | 570 | **8** | 0 | 1 | — |
| **default order** | **580** | **579** | **0** | **0** | **1** | 162.5 s |
| **`--random-order`, genuinely shuffled** | **580** | **579** | **0** | **0** | **1** | 153.8 s |
| `tests/deploy` | **331** | **331** | **0** | **0** | 0 | 41.9 s |
| console vitest (80 files) | **1,489** | **1,489** | **0** | **0** | 0 | 72.8 s |

The one skip is the standing declared one —
`test_gate_run.py::test_payload_validates_against_the_json_schema`, *"jsonschema is not a
workspace dependency"* — unchanged and untouched. The eight failures are gone, and §2.3 shows
they are gone **as themselves**.

**TWO CORRECTIONS TO THE EIGHTH VERIFICATION'S §3, both found here.**

* **The collection is 580, not 579.** The lead's target of `579/578/0/0/1` was computed before
  one test was split into two. Nothing is missing; the delta is `+2 − 1` and §2.3 enumerates
  it. The earlier `579/578` is preserved above so the arithmetic can be followed.
* **The "randomised order" run in verification 8 was not randomised.** `pytest-randomly` is
  **not installed** in this environment, so `-p no:randomly` is a documented no-op and its
  absence changes nothing: two invocations differing only in that flag execute in **identical
  order**. Confirmed here by comparing the `<testcase>` sequences of the two runs — byte-for-
  byte the same list. This repository ships **`pytest-random-order`**, which is inert until
  `--random-order` is passed (`pyproject.toml` says so at length, and it is right). The row
  above was therefore re-taken with `--random-order`: the sequence differs from the default
  run, the node-id **set** is identical, and the result is unchanged.

**A green in one order is not a green.** Until today this page had never reported one taken in
two.

---

## 4 · THE ARTEFACT — read from the archive, not from the source tree

### 4.1 · The constants against the zip's own central directory

`zipfile` over `out/lambda/mainline-demo-api-arm64.zip`, `sha256 6802872f…`. Left column is
what the tests now declare; right column is what the archive holds.

| | declared | measured in the zip | |
|---|---:|---:|:--|
| `web/` entries | 114 | **114** | ✓ |
| `web/` bytes | 1,308,536 | **1,308,536** | ✓ |
| identity objects | 57 / 1,012,812 B | **57 / 1,012,812 B** | ✓ |
| `.gz` siblings | 57 / 295,724 B | **57 / 295,724 B** | ✓ |
| largest identity | `assets/index-BH5dfAvF.js` 457,123 B | **`assets/index-BH5dfAvF.js` 457,123 B** | ✓ |
| largest sibling — `g` | `…BH5dfAvF.js.gz` 129,400 B | **`…BH5dfAvF.js.gz` 129,400 B** | ✓ |
| second identity | `assets/surface-0lG8KzXw.js` 51,266 B | **`assets/surface-0lG8KzXw.js` 51,266 B** | ✓ |
| refused by the ceiling | `("assets/index-BH5dfAvF.js",)` | **exactly that one, 1 of 57** | ✓ |
| `.gz` siblings over the ceiling | — | **0** | ✓ (interface I1) |
| entry chunk digest | `sha256 e30bd39b…` | **`e30bd39b395bad681f19bd11119e68dcd24e8ea971b22664350dc7cd9d159aae`** | ✓ |

**Every declared figure matches the archive. None was read from `dist/`, and none was quoted
from a document.**

### 4.2 · `console/dist` is undisturbed, and it is the zip's own source

The brief's fifth condition, checked as a whole-tree comparison rather than on one file:

```
zip web/ entries 114   |   dist entries 49   |   common paths 31
common paths whose sha256 DIFFER : 0
in the zip, not in dist          : 83   = 57 .gz siblings + 26 web/bundle/ files
in dist, not in the zip          : 18   = every one a .js.map, stripped by the packer by construction
entry chunk   dist  457,123 B  sha256 e30bd39b395bad681f19bd11119e68dcd24e8ea971b22664350dc7cd9d159aae
              zip   457,123 B  sha256 e30bd39b395bad681f19bd11119e68dcd24e8ea971b22664350dc7cd9d159aae
```

**Thirty-one files in common, zero mismatches.** `dist/` was not rebuilt by this verification
and its mtimes predate this session. `console_repro.py` was **not** run against the worktree
console; the safe form (`--source rev:HEAD`, which exports to a scratch directory) was not
needed because nothing here required a rebuild.

### 4.3 · Does the artefact start LIVE? The packer's own gate, run against the zip

The embedded packer was extracted from `scripts/deploy/build_lambda.sh` (61,485 B,
`sha256 773de524274915554c6038e2d33d3c16d4e46000b75bd400858c95c93b236825`, the same digest
`build_lambda.ps1` carries) and run in `--mode consolecheck`, which reads a finished zip and
takes no rebuild:

```
package   mainline-demo-api-arm64.zip
sha256    6802872f805740dd1a7de891eca7a8d1cf6c11f5eb5b639aec5677f5d78ae13b
console   declared  --console-transport live
console   effective live, replay  (selectSource would start it LIVE, switchable true)
console   literals  VITE_MAINLINE_API_BASE=/; VITE_MAINLINE_BUNDLE_URL=./bundle/; VITE_MAINLINE_LOG_VKEY=(empty)
console   buildId   3933b97, unknown
console   ACCEPTED: this artefact starts LIVE, as declared          exit 0
```

The sidecar agrees independently: `out/lambda/mainline-demo-api-arm64.zip.json` records
`console.packaged.literals.VITE_MAINLINE_API_BASE = "/"` and `console.transport_declared = "live"`.

**And the headline beat is in the shipping bytes.** `demo_gate_run`, `/v1/demo/gate-run` and
`gate-run.schema.json` all appear in `web/assets/index-BH5dfAvF.js` and
`web/assets/DemoDriver-CEGGCtyu.js`. The false `404s` sentence appears in **no** shipped
asset. `web/index.html` is 4,655 B and references `./assets/index-BH5dfAvF.js`.

`scripts/deploy/deploy.sh` and `deploy.ps1` now pass `--console-transport live` as a
hard-wired argument rather than a flag, so the REPLAY package cannot be re-shipped by omission.

---

## 5 · THE BEAT, DRIVEN AGAINST A REAL DATABASE

`scripts/proof/gate_refusal.py` against the local v26.2.5 node, throwaway database, run today:

```
cluster       CockroachDB CCL v26.2.5
database      w_qr_gate_refusal_proof
chain         271/271 applied, 0 failed, 90.375s
reached 0115  True
unproduced    (none) - every relation this tree references has a producer
PROJECTION    10/10 held - open_blocking 0->1 - gate_epoch 0->1 - outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) - nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
evidence      evidence/gate-refusal/proof-20260814T180258Z.json
```

Beat 1 is the `00000` read, so the chain is `00000 → 23514 → P0001 → 00000`. The same four
through the HTTP endpoint against CockroachDB Cloud are in
`evidence/deploy/cloud-acceptance.json`, two independent `gate_runs`, each `verdict PROVEN`.

**What cannot be driven is the deployed URL**, and for the honest reason: the SSM parameter is
unset, so `POST /v1/demo/gate-run` answers `503 dsn_unset`. That is the correct behaviour of a
reachable route and it is not dressed up anywhere on this page.

---

## 6 · THE DOCUMENTS — true, except one block in one file

`tests/deploy` is 331/331, which includes every doc-truth sweep: the route-table checker that
reads `app.py:229` at run time and refuses any live document claiming the demo route is
unrouted or 404s, the judge-walk checkers that refuse a named console asset the origin does not
serve or a transport claim the wire denies, and the widened `SWEPT_DOCS`. The pages that carry
the moved figures — `COST-BOUND.md`, `LATENCY.md`, `RUNBOOK.md`, `console-build.md`,
`docs/ci/cluster-lane-package.md`, `docs/decisions/response-ceiling-authoritative-tree.md`,
`docs/CI-STATE.md` — all now carry the **two-package framing**: the package on the origin
(`12fcba7a…`, `index-DzVoV1YM.js`, REPLAY, 433,564 / 124,177) and the package of record
(`6802872f…`, `index-BH5dfAvF.js`, LIVE, 457,123 / 129,400), never mixed. R4's derivation
window `119,158 ≤ g ≤ 126,604` is explicitly retired in every page that held it and replaced
by the live warning: **9,864 gzipped bytes of headroom remain**.

**THE ONE FAILURE.** `evidence/deploy/APPLIED.md` — the document a reader opens *first* to find
out what is deployed, and the document `SWEPT_DOCS` was widened to cover — was updated in three
places and left stale in a fourth. No checker reads it, because every checker points at the
origin and these sentences point at the local deploy path:

| line | what it says | status |
|---|---|---|
| 145 | *"The two wire figures are the ones three test modules declare (`124,177` / `433,564`)"* | **false** — the three modules declare `129,400` / `457,123` |
| 168–170 | *"`out/lambda/mainline-demo-api-arm64.zip` on disk is dated 2026-08-14 and its packer sidecar still records `console.configured.VITE_MAINLINE_API_BASE` as the empty string — it is the artefact that is serving"* | **false on all three counts** — the zip is dated 2026-08-15, its sidecar records `"/"`, and it is not on any origin |
| 171–181 | *"**No package was rebuilt into the deploy path**"*, and *"all three declaring test files still carry the deployed package's numbers"* | **false** — the LIVE package is in the deploy path, and the three files carry the package of record's numbers |
| 155–160 | the ceiling block ending *"OUTSIDE the window `119,158 ≤ g ≤ 126,604`"*, with no pointer to R10 | **stale framing** — that window is retired |

*"No redeploy happened"* and *"The SSM parameter is untouched"* in the same block remain **true**
and must survive whatever correction is made. **This verification does not edit that file.** It
is the orchestrator's evidence record, its own convention is *annotate in place, never replace*,
and a worker rewriting another's record is the failure mode this repository spends its budget
on. The correction is one dated annotation and it is the last thing between this tree and a
redeploy.

---

## 7 · THE INVARIANT — measured, not quoted

```
CEILING  DEFAULT_MAX_RESPONSE_BYTES = 139,264 = 136 * 1024        <- UNMOVED, file untouched
g        largest served, gzipped    = 129,400   assets/index-BH5dfAvF.js.gz
I        largest identity           = 457,123   assets/index-BH5dfAvF.js

STRADDLE   0 < 129,400 < 139,264 < 457,123                              HOLDS
I3 lower   129,400 <= 139,264        (the origin can serve its own site) HOLDS
I3 upper   139,264 < 1.20 x 129,400 = 155,280                            HOLDS
EXACTLY 1  identity objects at or over 139,264 : 1 of 57                 HOLDS
I1         .gz siblings at or over 139,264     : 0 of 57                 HOLDS

ratio      139,264 / 129,400 = 1.076      (was 1.121)
headroom   139,264 - 129,400 = 9,864 B    (was 15,087 B)   <- THE NUMBER WITH TEETH
DERIVATION floor(1.10 x 129,400) = 142,340 -> 18 x 8,192 = 147,456 != 139,264
```

**The ceiling still bites.** It still refuses the identity form of the entry chunk and still
serves the gzipped one; the same one object, at the same path, 413 or 200 depending on a single
request header. What went stale is the **derivation record**, not the bound — and R10 says so in
the direction that costs something rather than the direction that is convenient: `ceiling <=
derived` is asserted, so the ceiling may be **tighter** than the formula would choose and may
**never** be loosened to meet it. `139,264` is not available to be raised, and the test that
would catch an attempt is `test_the_live_law_holds_over_the_tree_that_ships_today`.

**Read the direction of the ratio carefully.** 1.121 → 1.076 means the ceiling now sits
**closer** to what the origin emits, not further. The `_RATCHET = 1.20` guard exists to catch a
ratio climbing toward a ceiling that floats above everything and refuses nothing; falling toward
1.0 is the safe direction. The cost of moving this way is the headroom, and that is where the
risk now lives: **a console growth adding more than 9,864 gzipped bytes puts `g` over `C` and
this origin 413s its own entry bundle to every browser.** That is a real outage and it is caught
by I3's lower half, red, at build time.

**One honest caveat, recorded by the lead and endorsed here.** R1's gate — *a content-hashed
filename is a legitimate constant only if the build is reproducible* — is satisfied for the
**class**: the console build is deterministic, 3/3 byte-identical at two different sources. It
is **not** proven for the shipping filename `index-BH5dfAvF.js`, because the console source it
was built from is not committed. That is why every re-recorded constant names the artefact by
**digest** rather than resting on a content hash. It becomes provable the moment the
orchestrator commits the console work, and it should be re-measured then.

---

## 8 · THE LIVE URL — what a judge sees right now

`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`. **Nothing was
deployed to take these readings and no credential was used.** The origin is unchanged since the
eighth verification measured it, because nothing has been applied since.

| request | answer |
|---|---|
| `GET /` | **`200`**, 4,655 B — the console shell serves |
| `GET /v1/health` | **`503`**, `ok=false`, `reason="dsn_unset"` |
| `POST /v1/demo/gate-run` | **`503`**, `kind="dsn_unset"` — **the route exists; it does not 404** |
| `GET /assets/index-DzVoV1YM.js` | **`200`** gzipped, 124,177 B — the **REPLAY** entry chunk |

Both API bodies name the cause exactly: SSM `GetParameter /mainline/demo/cockroach_dsn` in
`ap-southeast-1` answered HTTP 400 `{"__type":"ParameterNotFound"}`.

**A judge opening the URL at this moment still sees what the founder saw:** a console whose own
honesty chrome reads `TRANSPORT REPLAY (staged)` / `BUILD dev`, every byte on screen a recorded
EvidenceBundle rather than the kernel the page is sitting on, no control for the headline beat
because `demo_gate_run` is not in the artefact at all, and — if they reach the driver's gap
panel — a sentence telling them `app.py` has no demo route, which is false.

**Everything in §2–§7 is true of a tree that is not on that origin.**

---

## 9 · WHAT A JUDGE WOULD SEE AFTER THE ORCHESTRATOR REDEPLOYS

Stated from the bytes in the package of record, so this is a prediction with an artefact behind
it rather than a hope:

* **`GET /`** → `200`, the 4,655 B shell, referencing `./assets/index-BH5dfAvF.js`.
* **The console starts LIVE.** `VITE_MAINLINE_API_BASE` compiles to `"/"`, so `selectSource`
  starts it on the origin's own API with `switchable` true — the honesty chrome reads
  **`TRANSPORT LIVE`**, and **`BUILD 3933b97`** instead of `dev`. A judge can name the build a
  screenshot came from.
* **The headline button exists and is pressable.** `demo_gate_run`, `/v1/demo/gate-run` and
  `gate-run.schema.json` are all in the shipped chunks; `DemoDriver` mounts a real `<button>`,
  and `DeclarationGapPanel` is unreachable because `RESOURCES.has('demo_gate_run')` is true.
* **The false `404` sentence is gone from the screen** — it appears in no shipped asset.
* **`GET /assets/index-BH5dfAvF.js`** → `200` at **129,400 B** to any browser (all send
  `Accept-Encoding: gzip`), and **`413 response_too_large`** to a client that refuses
  compression, e.g. `curl` without `--compressed`. That refusal is the cost bound working, it is
  named in the docs, and it is not a defect.
* **AND THEN THE BUTTON ANSWERS `503 dsn_unset`, AND IT WILL KEEP DOING SO UNTIL THE FOUNDER
  WRITES THE SSM SECRET.** `GET /v1/health` will read `ok=false reason="dsn_unset"` and the
  gate-run POST will read `kind="dsn_unset"`, both naming
  `GetParameter /mainline/demo/cockroach_dsn → ParameterNotFound`. **This is CORRECT behaviour
  and this page will not dress it up.** It is a reachable route refusing for a named reason —
  the opposite of a 404, and the opposite of a page that pretends. A console that reads LIVE,
  names its build, and renders the kernel's own refusal verbatim is *proving* it is talking to
  the real kernel. **It is not the demo.** The demo is one founder-owned step away.
* **After the founder writes `/mainline/demo/cockroach_dsn` with the `mainline_api` DSN** —
  never the `.env` DSN, which holds ALL on 417 objects while the Function URL is
  `authorization_type = NONE` — the same button returns the four beats,
  `00000 → 23514 → P0001 → 00000`, verdict **PROVEN**, rendered from the kernel's own SQLSTATEs.

---

## 10 · WHAT CLOSES THIS, IN ORDER

1. **Correct `evidence/deploy/APPLIED.md`** — one dated annotation over lines 145 and 166–181,
   in that file's own *annotate, never replace* style. The orchestrator's document. (§6)
2. **Commit and push the 86 paths.** No lane has ever executed this tree, and committing the
   console source is also what turns §7's caveat into a proof.
3. **The redeploy.** The ORCHESTRATOR's step, and nobody else's. The package is already built,
   already `--console-transport live`, already verified to start LIVE from its own bytes.
4. **The SSM parameter `/mainline/demo/cockroach_dsn`, holding the `mainline_api` DSN.** The
   FOUNDER's step, and nobody else's.

**Between 3 and 4** a judge gets a console that reads LIVE, names its build, carries a working
button for the headline beat, and answers that button with `503 dsn_unset` rendered honestly on
screen. **That is a good demo beat, not a failure.** After 4, the same button returns the four
beats.

---

## 11 · Verdict

**NO-GO.** Ninth verification, 2026-08-15, tree `3933b97` plus 86 uncommitted paths.

The wave this page was asked to verify **succeeded, and it succeeded honestly.** The eight
failures are fixed as themselves, proven by node id. The response ceiling did not move by a
single byte and the module that owns it is not in the diff. The straddle holds, exactly one
identity object is refused, and the ruling that keeps `139,264` where it is chose the option
that costs something over the option that would have made the arithmetic agree. The re-recorded
constants match the archive exactly. The artefact starts LIVE and carries the headline beat in
its bytes. `dist` is byte-identical to the zip. The suite is 580/579/0/0/1 in two genuinely
different orders — the first time this page has been able to say that truthfully — `tests/deploy`
is 331/331, vitest is 1,489/1,489, the LINT ratchet has zero regressions and one improvement,
and the gate proof is `PROVEN` with no caveats.

**And none of it is on the origin.** The URL still serves a REPLAY console with no
`demo_gate_run` in its bytes; one evidence document still describes a deploy path that has moved
under it; and the secret that turns the button green is the founder's to write. **A judge
opening the URL right now still sees what the founder saw.** That is the whole verdict, and it
will stay the verdict until step 3 of §10 happens.
