<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# VERDICT — the stranger's read

**Reviewer:** THE STRANGER. Three minutes, no prior reading of this repository, scoring against
Agentic Memory Design, Technical Implementation, Real-World Impact, Production Readiness and
Creativity.
**Date:** 2026-08-16 · **Tree:** `D:/CoackroachDBxAWS/mainline`, HEAD `4af05e1` (+ uncommitted demo wave)
**Origin under test:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

---

## VERDICT: **NOT READY**

Narrowly, and for **one** reason, and that reason is a **packaging step, not a rebuild**.

Everything the founder set out to build exists, is honest, and is measurably real. The
operator systems UI — the permit-to-work app and the change-request screen, with MAINLINE
refusing *inside* them — **is not on the deployed origin.** It is built, correct, and sitting
in `dist/`. It has never been packed into the Lambda web root.

> `GET /operator.html` and `GET /memory.html` are **byte-identical to `GET /`**
> (md5 `fb2bc293700ac32112b9679eeb97343a`) and title themselves `MAINLINE console`.
> The deployed archive carries `html_entries: 1`.

The repository already knows this and refuses to stage around it —
`docs/demo/film/FALLBACKS.md` **W6-1** and `docs/demo/film/CLICKS.md` **D-6** file it against
themselves and escalate it to the orchestrator. That is to the team's credit. It is still the
thing standing between this submission and the film the founder described.

**This is not a "broken demo" finding.** The URL works. See §9.

---

## 1 · NOTHING IS FAKED — **PASS**, emphatically

This was checked first and hardest, because a faked refusal sinks the submission on inspection.
I found none, and I looked for it the way someone trying to catch you would.

| probe | result |
|---|---|
| Hard-coded SQLSTATEs in `src/operator/**`, `public/*.js`, `operator.html` | **none.** The single literal in the tree is `'40001'` in `kernel/gate-run.ts:127`, used in a **comparison**, never rendered |
| Hard-coded constraint names / CHECK text (`gate_closed_when_issued`, `fn_permit_merge_gate`, `failed to satisfy CHECK`) in runtime code | **zero occurrences** |
| Mocked fetch, stubbed transport, canned refusal strings | **none** |
| Simulated latency | **one** `setTimeout` in the entire demo surface — see below |

**The one timer, and why it is honest.** `public/memory-loop.js:1146` staggers the painting of
the four beats. It is lexically inside the scope that already holds the parsed response, it
gates no request, and every figure it reveals arrived in a single body. The page **says so on
screen** — *"Four beats, one response"* — and offers `?reveal=off` to fill all four the instant
the response lands. W7's capture measured click→DOM at **30 ms** and **33 ms** and proved
**exactly one** `POST /v1/demo/gate-run` across the whole interaction. This is ordering, not
latency, and it discloses itself. It clears.

**The adversarial check I did not have to write.** `evidence/demo/operator-capture.json` models
**eight** SQLSTATEs and asserts *none of them appears on screen without being in the 10,446
bytes the server returned*. Every SQLSTATE rendered — `00000`, `23514`, `P0001`, `00000` — is a
beat's own. That is the check a sceptic would ask for.

**The 404 on screen is a real 404.** `GET /v1/change-requests/{cr_id}/blocking-checks` → 404,
693 bytes, rendered verbatim. The screen shows an absence as an absence rather than as a
placeholder. This is the opposite of faking.

---

## 2 · THE LIVE KERNEL — **PASS** (measured by me, this sitting)

```
GET  /v1/health        ok=true  deploy_chain 271/271  database=mainline_demo
                       CockroachDB CCL v26.2.5  schema ec9b1ce7…
POST /v1/demo/gate-run 200 · 10,499 bytes · 2.91 s · verdict PROVEN
                       staged=false · staged_note=null · failures=[]

  1 read                      00000              open_blocking_derived=1  counters_agree=true
  2 merge                     23514  REFUSED     gate_closed_when_issued   (constraint_source "reported")
  3 projection_drift_attack   P0001  REFUSED     mainline.fn_permit_merge_gate ("parsed")
  4 admit                     00000  ADMITTED

  transaction  SERIALIZABLE · 3 savepoints · disposition rolled_back
  persisted    false · row counts identical over 10 tables
```

`scripts/demo/demo_ready.py --check` against the deployment: **8 of 8 facts PASS, 0 failed —
"Roll camera."**

Beat 3 is the strongest thing this project owns and the payload carries it in the same single
response as the rest: the counter the gate reads is forced to zero out of band, and the gate
refuses **anyway**, because it re-derives from ancestry. W7 proved the on-screen reveal of that
beat issues no second request. It is a reveal, not a re-enactment.

---

## 3 · THE MEMORY LOOP — **PASS**, and it is the best thing here

The hackathon's named theme, and the brief's explicit demand. I walked it live:

| step | what the database actually holds | route |
|---|---|---|
| **STORE** | `mainline.event` `DEMO-INC-0001`, severity-4, `occurred_at 2019-03-14T06:20:00Z`, reaching the clause by `origin blame_ancestry` | `/v1/permits/{id}/blocking-checks` → 200, **2,408 B** |
| **RETRIEVE** | `mainline_meas.recall_run` `started_at 2026-08-02T03:00:00Z` · `n_candidates 1` · `n_blocking 1` · `index g1` · `policy demo-recall-1.0` | `/v1/recall-runs/{id}` → 200, **2,223 B** |
| **ACT** | obligation `materialised_at 2026-08-02T03:00:10Z` — **ten seconds later** — and the gate refuses `23514` citing it | `/v1/demo/gate-run` |

Every one of those values is a column, not a caption, and I read them off the live origin.

**The detail that makes it unfakeable.** The seed writes `0, 'routine'`
(`verticals/mainline/db/seeds/demo/demo_permit.sql:318`). The deployment serves **severity 4 /
`blood_major`**. The difference is `fn_check_project` overwriting both out of the clause's own
blame closure. *"Nobody typed that four"* is literally true, and a judge can check it in two
places. A counter a client writes is an opinion; a counter a trigger writes on a row the client
never touched is the database's.

Budgeted at **18 s** in B3, rendered as three labelled panels **inside the permit screen the
supervisor is already looking at** — not on a separate dashboard, which is the right call.
W7's capture confirms the labels the built screen actually produces are **`STORED` ·
`RECALLED` · `ACTED`** (past tense — correct, and see §10.6), with `DEMO-INC-0001`,
`2019-03-14`, `blame_ancestry`, `blood_major` and `03:00:10` all present in the captured DOM.

A judge can point at the screen and say "there is the memory". **Requirement met — on the
picture. Not yet reachable at the URL** (§9).

---

## 4 · THE FIRST 30 SECONDS — **PASS** on the plan

| t | what a judge sees |
|---|---|
| `0:00` | Live product — the supervisor's permit form. No title card, no logo, no architecture diagram |
| `0:00–0:07` | Written lower third carrying the problem **and** the audience, costing zero seconds of VO |
| `0:12` | A real click, a genuine in-flight request |
| `0:22` | **First refusal, inside the supervisor's own app** — `23514 · gate_closed_when_issued` |

Well inside the organiser's 20–30 s window, with eight seconds to spare. Spending the *written*
line on "problem and audience" and the *spoken* opener on the promise satisfies both Devpost
instructions without a title card. That is a genuinely good call.

---

## 5 · THE THREE MINUTES — **PASS**

**Measured total: `172 s` = `2:52`.** Hard stop `174 s`; ceiling `180 s`.

`120 s` demo + `50 s` close + `2 s` end card. **213 spoken words across the demo at 1.90 w/s**,
~82 more across the close; every single beat at or under a self-imposed **1.95 w/s** ceiling —
a deliberate, unhurried read rather than a rushed one. A pre-committed cut ladder recovers
**19 s** in a fixed order down to a `153 s` floor, so an overrun on the day has an answer that
nobody has to invent at 2am.

No hard fail. **8 seconds of margin against the 3:00 wall.**

---

## 6 · THE TECHNICAL MINUTE — **PASS**, and unusually honest

Nothing aspirational reaches the screen. The AWS block is **grouped**, and the grouping is the
honesty: `IN THIS REQUEST` (Lambda arm64, Function URL `authorization_type = NONE`, SSM
Parameter Store, IAM) versus `IN THE APPLY THAT CREATED IT` (S3 state bucket, CloudWatch alarms
+ SNS + Budgets — 24 created / 0 changed / 0 destroyed). **Bedrock gets its own labelled
exception** — exercised in the repository, *not* in this request path — and the film says the
line out loud. The Singapore-database / Sydney-inference residency split is stated rather than
blurred.

The CockroachDB block names SERIALIZABLE, the `CHECK` constraint, the PL/pgSQL trigger function,
a user-defined enum visible inside the refusal message, and composite foreign keys — and
repeats **"It did not run in this request."** three times for the things that did not. It
concedes *"one cluster, one region, and no scale claim"* in the founder's own voice.

I checked the forbidden list against the census. It holds: CHANGEFEED is `DESIGNED`
(`kv.rangefeed.enabled` reads false), CloudFront is `DESIGNED and unapplyable` with the
`AccessDenied` request-id recorded, KMS / CloudTrail / EventBridge / S3 Object Lock / Agent
Skills all `DESIGNED`. **No aspirational claim reaches the overlay.**

---

## 7 · HONESTY — **PASS**

`scripts/demo/claim_hygiene.py` over the seven files that carry spoken or on-screen text
(`VO-DEMO`, `VO-CLOSE`, `ONSCREEN-TEXT.yaml`, `BEATS.yaml`, `SPINE`, `CLICKS`, `FALLBACKS`):

```
scanned 7 file(s) against 21 rules
claim hygiene OK
```

The scanner self-tests red on four planted families, so a green run means something.

**One cosmetic trap.** Scanning all of `docs/demo/film/` reports **6 violations, all at
`CLAIMS-CLEARANCE.md:816-819`** — they are the scanner's own `--self-test` transcript pasted
into a fenced block. False positives, but a reviewer who runs the scanner over the directory
sees red. Worth a fence-aware exemption or a note at the call site.

Three underclaiming discrepancies are **filed rather than smoothed** in
`ON-SCREEN-CLAIMS.md §"Discrepancies filed, not smoothed"`. Filing them is the right call.

---

## 8 · NO REGRESSION

**Console bundle headroom — PASS, and it improved.**

| | entry chunk (gz) | headroom to the 139,264 B ceiling |
|---|---|---|
| deployed (`index-LoN3Sn_L.js`) | 138,177 B | 1,087 B |
| this tree (`index-Dif0ht5g.js`) | **137,887 B** | **1,377 B** |

The operator landed as a **separate second entry** exactly as instructed —
`operator-D24tzVGh.js` at **29,906 B gz**, outside the console's import closure. `public/`
files are copied verbatim and never enter the module graph: `memory.html` 7,990 B gz,
`memory-loop.js` 16,023 B gz. **Nothing was added to the constrained chunk.** Sourcemaps are
not deployed (404, not 413), so devtools stays quiet.

`DEFAULT_MAX_RESPONSE_BYTES` is unmoved at `136 * 1024`. No `continue-on-error`, no `|| true`
introduced. Nothing committed; the tree is left for the orchestrator.

**Suite — PASS. Measured by me, on the documented lane:**

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests tests/deploy \
    --crdb=reuse -q -p no:cacheprovider --timeout=900 --junitxml=…

junit ROOT ELEMENT: tests=998  failures=0  errors=0  skipped=1  time=177.6 s
terminal:           997 passed, 1 skipped in 178.49s   ·   exit 0
```

Baseline `988 / 987 / 0 / 0` → **`998 / 997 / 0 / 0`, 1 skipped.** The wave **added ten tests
and broke none.** The single skip is declared (`jsonschema` is not a workspace dependency).
This reproduces `qa/wave-after.xml` exactly.

> **A note on scope, so nobody repeats my mistake.** I first ran a bare `pytest --crdb=reuse`
> from the root, which collects the **whole monorepo — 10,849 tests** — and is *not* the
> baseline lane. `scripts/qa/regression_guard.py` says so in its own docstring: tests collected
> by a bare `pytest` "are deliberately NOT in these counts." The 988/998 figures are
> `demo-api/tests` + `tests/deploy` only. Judge the ratchet on the lane it was recorded from.

**One real red, pre-existing at HEAD and outside this lane — worth fixing before submission.**

```
tests/ci/test_demo_seed_is_frozen.py::test_the_deployed_seed_files_have_not_changed[demo_world.sql]
  demo_world.sql hashes fb1dd071…1c1020b; the test records 78158939…54bf55156
```

`f0ba767` ("fix(seed): make the checkpoint repair reach a database that was already seeded")
changed the seed **without re-baselining the hash in the same commit**, which is precisely the
discipline that test exists to enforce. The demo wave did not cause it — both files are
committed and the wave never touched the seed. The test's own instructions apply: run the
**four-part negative control** in its docstring *before* touching the constant, and if any part
comes back unclean, revert the seed instead of re-baselining. This is a ratchet currently
sitting red; it should not be left that way into judging.

---

## 9 · THE BLOCKER, STATED PRECISELY

**What is true:** the deployed URL is **not broken and not dishonest.** It boots, it declares
`LIVE`, it compiled `VITE_MAINLINE_API_BASE` as `/`, and I watched it issue
`GET /v1/demo/subjects → 200` and render subject ids it had just read. It is a real client of
the real kernel with a careful, honest onramp.

**What is missing:** it is **the console** — a tour of the MAINLINE console, which is the exact
thing the founder said this demo is *not*. The permit-to-work app, the change-request screen and
the `STORE → RETRIEVE → ACT` panel — the entire "MAINLINE refusing inside the software people
actually use" premise — exist only on `127.0.0.1`.

**Why this is small:** `dist/` already contains `operator.html`, `memory.html`, `memory-loop.js`,
`memory-verify.js` and `memory.css`, all built, all far under the wire ceiling. The gap is that
`build_lambda`'s packer reads asset references out of `index.html` **only**, so a second HTML
entry never reaches `web/`. `scripts/check-entrypoints.ts` was written to close exactly this
gap console-side and calls it out in its own header.

**Consequence if filmed as-is:** the take happens against `local_furl`, the origin strip
correctly prints `X-Mainline-Emulator: local_furl` on screen, and the URL bar reads `127.0.0.1`
— contradicting `SPINE.md §1.3`'s *"on the deployed origin, URL bar in frame"* and costing the
"live" reading of the first thirty seconds. The team has already ruled out the dishonest
alternative: *"Never point a URL bar at something and let the frame imply..."* (`FALLBACKS.md:408`).

---

## 10 · THE SINGLE HIGHEST-LEVERAGE FIX

> **Pack the existing `dist/` into the Lambda web root and apply, so `/operator.html` and
> `/memory.html` serve themselves instead of falling back to `index.html`.**

Nothing needs to be designed, written or measured. The bytes exist, they fit, they are honest,
and they are gated by checks that already pass. This one step converts a strong local
demonstration into the live demo the script was written against, and it is the difference
between a judge watching the founder's story and a judge watching a console tour.

**Then, in order:**

2. **Wire the raw-payload drawer.** The only failing assertion in the whole capture is
   `raw-payload-drawer-is-byte-identical` (**R18 UNMET**): `renderRawPayload()` and
   `renderRequestLog()` in `src/operator/kernel/raw.ts` are implemented **and called by nobody**.
   This is the one affordance that lets a judge see the 10,446 bytes on screen without opening
   devtools — cheap, and it lands squarely on Technical Implementation.
3. **Write `demo_url` into `docs/submission/SUBMISSION.json`.** It still reads `UNRESOLVED`, and
   its rationale still says *"Nothing is deployed"* — stale since the apply. Founder's to write;
   `check_submission_ready.py --check-urls` is what closes it. `video_url` follows the film.
4. **Clear the frozen-seed red** (§8) by running the four-part negative control and then
   re-baselining the hash — or reverting the seed, if the control says so.
5. Make `claim_hygiene.py` fence-aware so `CLAIMS-CLEARANCE.md` stops reporting six false reds.
6. **One-word continuity check.** `SPINE.md` §B3 writes the panel labels as
   `STORE → RETRIEVE → ACT`; the built permit screen renders them past-tense as
   **`STORED · RECALLED · ACTED`** — which is the *better* wording, because B3's own rule is
   that the recall is never narrated in the present tense. Make the overlay and the screen say
   the same three words so a judge is not reading two vocabularies at once.

---

## 11 · WHAT I WOULD TELL A JUDGE AFTER WATCHING THIS

MAINLINE puts the last word about a dangerous change **inside the database**, so that a lesson
learned from a past incident stops being a memo people are supposed to remember and becomes a
constraint that cannot be gone around. A site supervisor fills in an ordinary permit-to-work
form and asks to merge it; the merge comes back refused with `23514` and the name of the rule
that refused it, because a severity-4 stored-energy release from 2019 left blame on the clause
this permit relies on, a recall run found it, and ten seconds later an obligation existed on the
permit — and the severity on that obligation was written by a trigger out of the blame closure,
not typed by anyone. Then somebody does the thing people really do: they force the counter the
gate reads down to zero. **It refuses anyway**, `P0001`, because it re-derives the answer from
ancestry instead of trusting a number — and that is the moment the product stops being a
checkbox and becomes a control. Sign one honest disposition and it admits, `00000`, proving the
refusal was a rule and not a bug; and nothing persisted, because the whole demonstration ran and
rolled back inside one `SERIALIZABLE` transaction. **The story lands.** It is specific, it is
about real work, the memory loop is visible rather than narrated, and the close names only what
actually ran and says out loud what did not. The one thing that would stop a judge believing all
of it is clicking the submitted link and arriving somewhere other than the app they just
watched.

---

## APPENDIX · COMMANDS RUN FOR THIS VERDICT

```
curl  GET  /v1/health                                      → 200  ok=true  271/271
curl  POST /v1/demo/gate-run                               → 200  10,499 B  2.91 s  PROVEN
curl  GET  /v1/permits/{id}/blocking-checks                → 200  2,408 B
curl  GET  /v1/recall-runs/{id}                            → 200  2,223 B
curl  GET  /v1/clauses/{id}/ancestry                       → 200  3,744 B
curl  GET  /operator.html /memory.html                     → 200, byte-identical to GET /
python scripts/demo/demo_ready.py --check                  → READY, 8/8, exit 0
python scripts/demo/claim_hygiene.py --check <7 text files>→ claim hygiene OK
python scripts/demo/claim_hygiene.py --self-test           → red on 4/4 planted, exit 0
pytest demo-api/tests tests/deploy --crdb=reuse            → 998/997/0/0, 1 skipped, exit 0
pytest tests/ci/test_demo_seed_is_frozen.py                → 1 failed (pre-existing, §8)
grep  hard-coded SQLSTATE / constraint / refusal text      → zero in runtime code
gzip  measurement of dist/ against the 139,264 B ceiling   → entry 137,887 B, headroom 1,377 B
browser  live load of the deployed origin + network panel  → GET /v1/demo/subjects → 200
```
