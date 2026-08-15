<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
This file quotes forbidden sentences beside the true ones, in the same three-column form
docs/submission/MUST-NOT-CLAIM.md and docs/demo/research/r6-honesty.md use, because a fallback
document that did not name the wrong sentence would be teaching only half the lesson at 02:00.
It therefore carries the `prose-hygiene: register` marker, and every quoted prohibition sits on
a line that also carries an explicit negation, which claim_hygiene.py's documented negation
exemption reads as STATING the rule. If this path is ever added to a prose scanner's sweep
list, the scanner must PRINT that it skipped this file, so "not scanned" is never read as
"passed".
-->

# FALLBACKS — what the founder says when a beat misbehaves, and the pre-flight before the red light

**Worker W6** · story-and-script wave · written 2026-08-15, measurements re-read 2026-08-16
**Binding on this file:** `docs/demo/story-and-script-plan.md` §4 — **R-N above all**, and
R-C, R-E, R-F, R-I, R-J, R-K, R-L. **Research:** `r6-honesty` Parts C and D (and A4.4, A10,
A13.2, A13.5, A17), `r5-craft` §§0.1 and 9.
**Live origin:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
**Siblings this file must not contradict:** `BEATS.yaml`, `SPINE.md`, `VO-DEMO.md`,
`VO-CLOSE.md`, `CLICKS.md`, `ONSCREEN-TEXT.yaml`.

**`claim_hygiene.py --check` verdict**, run this session on this file and pasted verbatim:

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/FALLBACKS.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
                                                                          (exit 0)
```

Recorded per plan R-B: `docs/demo/film/` is outside every `TARGET_GLOBS` entry, so this scan is
invoked by hand and its result is pasted here rather than assumed. It is a reading of **this
file and of nothing else**, and it is not a CI result. Re-run it after any edit — *not scanned*
and *passed* are different results.

---

## 0 · THE TWO RULES THAT GENERATE EVERY LINE BELOW

**Rule one — R-N.** *If it goes wrong on the day, it goes on camera or the shoot moves.* A cold
press is waited out. A `40001` is pressed again on camera. If the live origin is down the film
is **not** made against a mock: it is postponed, or filmed against the local node **and said to
be local, on screen**. The authority is not only honesty — the hackathon's Functionality rule
requires the Project to *"function as depicted in the video"*, so a staged refusal is a **rules
violation**, not merely a dishonesty.

**Rule two — the one this whole document was written to make impossible.** **Not one fallback
in this file is "show a recorded refusal as if it were live."** There is no such fallback. If
the only way to finish the take is to play something back, the take does not get finished that
day. A demo that fakes the one thing the product does is worth less than no demo.

**Everything below therefore has the same shape:** what it looks like on screen, what the
founder **says** (verbatim, in his own words, on camera), what he **does**, and what he
**never** does. Each spoken line is written to be read cold at 02:00 without a decision left in
it.

**One habit that makes half of these unnecessary.** *Say it before a judge finds it.* Every
awkward thing in this film — the single request, the skipped checks, the change request that
cannot be driven, the field with no column — is stronger disclosed than discovered. The product
already discloses each of them on its own screens; the founder's job is to get there first.

---

## 1 · WHAT I RAN, AND WHAT I ONLY TRANSCRIBED

A command nobody has run is a plan. This table is the honest split for **this file**; §4 marks
it again per command, in the pre-flight block itself.

| # | what | status | result |
|---|---|---|---|
| **M1** | `GET <origin>/v1/health` | **RAN** (read-only) | `HTTP 200 · 410 B · 0.711 s` · `ok:true` · `deploy_chain_applied 271 / deploy_chain_files 271` · `database mainline_demo` · `cluster_version CockroachDB CCL v26.2.5` · `server_date 2026-08-15T13:59:42.544802Z` |
| **M2** | `GET <origin>/` and `GET <origin>/operator.html` | **RAN** (read-only) | Both `HTTP 200 · 4,655 B`. **The two documents are byte-identical**, and both carry `<title>MAINLINE console</title>`. See F-9 — this is the measurement that makes the operator-UI fallback a live question rather than a hypothetical. |
| **M3** | `GET <origin>/v1/ledger` | **RAN** (read-only) | `HTTP 200 · 9,505 B`. Read to confirm the surface answers; the SEAL verdict is computed **in the browser** and is **not** in this response. F-6 says read the chip with your own eyes. |
| **M4** | `.venv/Scripts/python.exe scripts/demo/claim_hygiene.py` (full sweep) | **RAN** | `scanned 23 file(s) against 21 rules` · `claim hygiene OK` · exit 0 — **and four `ABSENT` lines**, each naming a glob that matched no file and printing *"not scanned, and therefore not passed."* |
| **M5** | `.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --self-test` | **RAN** | `planted 4 violation families, scanner fired on 4` · `self-test OK` · exit 0 |
| **M6** | `.venv/Scripts/python.exe scripts/mi_ratchet.py report` | **RAN** | `21 pending / 9 enforced`, exit 0. **The figure is never quoted on camera** (R-K, r6 A14); it is run so a drift is seen before a judge sees it. |
| **M7** | `.venv/Scripts/python.exe verticals/mainline/demo/honesty/gen_card.py --check` | **RAN** | **exit 2**, and the reason is named: `corpus.lock.json does not exist. It is produced by the corpus-freeze-load worker.` With `--allow-fixtures` it prints `card.html is current (53 traced values)` and **exit 3** — the documented code for a clearly-marked stand-in card reading `NOT FOR CAMERA`. **Both are expected on this tree.** See §4 note (c). |
| **M8** | `.venv/Scripts/python.exe scripts/qa/regression_guard.py` | **RAN — and it is RED** | `VERDICT  REGRESSION - 3 of 31 checks FAILED in PRIVILEGES, SUITES (28 PASS, 0 SKIP)` · **exit 1**. It runs for well over five minutes; start it early. The three, verbatim: `SUITES collected` **expected 911, observed 997**; `SUITES passed` **expected 910, observed 996**; `PRIVILEGES relations` **2 shortfall(s) — `mainline.exposure_line INSERT; mainline.exposure_receipt INSERT`**. See §4 note (d) and W6-2 — **this is not mine to fix and I did not touch the ratchet.** |
| **M9** | `POST <origin>/v1/demo/gate-run`, **by hand** | **NOT RUN — forbidden to me** | I issued no `POST` by hand. Every payload field quoted in this file is read out of `evidence/deploy/live-gate-run.json`, `evidence/demo/operator-capture.json`, or the handler's own source. **The verdict on the day is the founder's own run, and nothing on this page substitutes for it.** |
| **M11** | `POST <origin>/v1/demo/gate-run`, **by the pre-flight tool** | **HAPPENED — disclosed, not hidden** | `regression_guard.py` **posts to the live gate-run itself**, by design, as its `LIVE` family. Running the command r6 Part D prescribes therefore drove the live endpoint from this session. Its four `LIVE` checks all **PASS**: `health_ok ok=True`, `deploy_chain_applied 271`, **`gate_run_verdict` expected `PROVEN`, observed `PROVEN`**, `gate_run_beats` **4 beats, 0 mismatch(es)**. The endpoint is non-mutating by construction and the guard's own `SEED` family re-counted the rows afterwards — `core_counts`, `defeater_option 6`, `ledger_leaf 4`, `ledger_node 3` all matched. Nothing was written. **Said out loud because a worker who let a `POST` happen and did not mention it would be the small version of the thing this whole file is against.** |
| **M10** | source read for exact strings | **READ, not run** | `mainline_demo_api/transitions.py` (the `423` body, verbatim), `gate_run.py` (beat-4 skip conditions and the `verdict` rule, verbatim), `retry.py` and `refusal.py` (`40001`), `contracts/gate-run.schema.json` (`outcome` enum), `operator/issue/pending.ts` (the pending clock), `scripts/deploy/local_furl.py` (the two headers), `features/custody/CustodyScreen.tsx` (the tally label), `infra/envs/demo/terraform.tfvars.example` (`api_timeout_seconds = 14`). |

**No AWS surface was touched, no SSM parameter was written, no credential was printed, no
`terraform` command was run, and nothing was committed.** The only file this worker authored is
this one. Two side effects of running the prescribed pre-flight are disclosed rather than
tidied away: the `POST` in **M11**, and `qa/regression-guard-suites.xml`, which
`regression_guard.py` writes as its own `--junitxml` and which my run therefore produced. No
ratchet, floor, ceiling, assertion or expectation was moved to make anything pass.

---

## 2 · THE FAILURE MODES

### F-1 · A COLD PRESS — seven to nine seconds of wait

**What it looks like.** The `ISSUE` press lands, the pending state comes up, the Network row
appears with no `Status` yet, and the page's own elapsed clock keeps counting well past the two
and a half seconds a warm press costs. Nothing is broken. The function has not been called
recently, so the platform is building a container and the handler is opening its first
connection before it can ask the database anything at all.

> **SAY, over the wait, calmly, without a number in it:**
>
> **"That's a cold start. Nothing has called this function for a while, so it's building its
> container and opening its first connection to the database before it can even ask the
> question. This is the real thing waking up — I'd rather show you that than cut it."**

**DO.**
- **Do not cut. Not once.** The unbroken press-to-answer take is the single most load-bearing
  editorial rule in the film (`r5-craft` §6).
- Do not press again. A second press is a second `POST` row, and a second `POST` row kills the
  take (F-11).
- Keep the pending clock and the single in-flight Network row in the same frame. The clock is
  driven by `requestAnimationFrame` sampling `performance.now()` against the real promise —
  there is no `setTimeout` behind it and no skeleton — and the page labels it as **this
  browser's** measurement, beside the per-beat durations the **server** measured.
- If the wait passes about twelve seconds, stop expecting a `200`: `api_timeout_seconds = 14`
  in the demo environment's own variables, so beyond that the platform cuts the call and the
  screen will show a transport failure rather than a refusal. That is F-13, not this one.

**NEVER.** Never speed the wait up. Never fill it with a cut. Never say how long it "usually"
takes, and never offer any of it as a product latency — the only honest answer to that question
is the one in §3. And **never warm the function from the tab you are about to film**: a warming
press in the filmed tab reveals the beats and burns the take (`CLICKS.md` §1.5, step 1).

**Why this is a shot and not a defect.** A judge who watches a real container start has watched
something no screenshot and no `setTimeout` can produce. `r5-craft` §0.1 is unambiguous: *the
button takes about two and a half seconds warm and up to about nine cold, and that is not a
defect to hide — it is the shot.*

---

### F-2 · `40001` — the retry that is a legal answer

**What it looks like.** Two surfaces, and they are different:

| surface | what you see |
|---|---|
| **`200` with `outcome: "retry"`** | The payload's `outcome` enum admits exactly two values, `completed` and `retry`, and the contract's own words for the second are: *"`retry` = SQLSTATE `40001` aborted the run; the transaction was UNDECIDED, which is not a refusal, and this driver does not re-send on the caller's behalf."* `verdict` reads `NOT PROVEN`, `failures[0]` opens *"the transaction was UNDECIDED (40001)"*, and the beats completed so far are still in the body. |
| **`503 transaction_undecided`** | The same `40001`, arriving as an exception no transition turned into an envelope. The envelope carries `sqlstate: "40001"`. |

Either way it is **not** a refusal. The gate never got to say anything.

> **SAY, on camera, and then press again on camera:**
>
> **"Four-oh-oh-oh-one. That's a serialization failure — the database aborted the whole
> transaction rather than let two writers interleave under SERIALIZABLE. Nothing was written,
> nothing was decided, and it does not re-send a merge on my behalf. So I press it again."**

**DO.**
- **Press it again, in the same unbroken take, with DevTools still in frame.** A `40001` shown
  and re-pressed is *more* credible than a demo that never sees one — that is `r5-craft` §0.1's
  third consequence and plan R-N's ruling, and both are right. Two `POST` rows are legitimate
  here **because the first one is on screen failing**; F-11's rule is about a second row nobody
  saw a reason for.
- Read the `failures` line off the screen if it is legible. The payload says it better than any
  script can.
- Note for the record, not for the microphone: the handler already re-runs the **whole**
  function under a bounded retry one level up (`transitions._demo_gate_run` →
  `retry.run_transaction`), which is safe precisely because this run persists nothing. So a
  `40001` that reaches the browser is one that outlived that budget. Do not say this on camera;
  it is four sentences of plumbing in the middle of the film's tensest beat.

**NEVER.** Never call it a refusal and never let it sit beside a SQLSTATE the gate produced as
though they were the same kind of event. Never cut to a cleaner take and never re-record audio
over this picture. Never say the system "retried" — **it did not**, at this layer, and the
contract says so in its own description field.

---

### F-3 · `423 demo_subject_write_protected` — the demo protecting itself, and it is not a gate refusal

**What it looks like.** `HTTP 423`, about 582 bytes, and a body that is not a refusal envelope
at all:

```
{"error":"demo_subject_write_protected",
 "use_instead":"POST /v1/demo/gate-run",
 "detail":"This is the seeded demo subject, and it is a single shared copy that a hundred
           judges read. Every transition on this path is irreversible on it — a permit is
           never un-merged — so one caller must not be able to brick the demo for the next.
           Drive the gate through POST /v1/demo/gate-run, which plays the same four beats in
           one transaction and rolls all of it back. Set MAINLINE_DEMO_ALLOW_MUTATION=1 in a
           deployment you own to lift this."}
```

**If this appears during the take, the `ISSUE` button posted to the merge route, and the take is
dead.** The button calls `POST /v1/demo/gate-run` and it never calls
`POST /v1/permits/{id}/merge`; `CLICKS.md` §2 boxes that warning and W7's capture assertion
`never-the-merge-route` held over the whole page load.

> **SAY — only if it is already on screen and cannot be avoided, e.g. a judge drove it live:**
>
> **"That four-two-three is not the gate refusing. That is the demonstration protecting itself.
> This permit is one shared copy that every judge reads, and a merge on it is irreversible — a
> permit is never un-merged — so the deployment locks the transition and points at the route
> that plays the same four beats in one transaction and rolls all of it back."**

**DO.** Stop the take. Restart from pre-roll step 2 (`CLICKS.md` §1.5). If a second attempt
produces it again, the button is wired to the wrong route: **escalate, and do not film.** If a
judge asks about it out of camera, the spoken line above is the whole answer and it is a good
one.

**NEVER — and this is the sharpest "never" in this document.** **This must never be rendered
in a refusal banner.** It carries no SQLSTATE, no constraint and no obligation; its message is
about a lock, not about a debt. A `423` dressed as a refusal is a **fabricated exhibit** — a
refusal that looks like the product's and came from the demo's own guard rail — and it is the
single most likely wrong turn available to anyone touching this surface. Never narrate a
SQLSTATE over it. Never say "the database refused" over it.

---

### F-4 · BEAT 4 SKIPS, AND THE VERDICT IS NOT `PROVEN`

**What it looks like.** Beat 4's `outcome` reads `skipped`, `matched_expectation` is `false`,
the run's `verdict` reads **`NOT PROVEN`**, and `failures` names the beat and quotes what was
expected against what was observed. The first three beats look **exactly** as correct as ever —
that is precisely why this one is dangerous. `verdict` is `PROVEN` only when `failures` is
empty; nothing rounds it up.

The handler skips beat 4 for exactly two reasons, and it says which in the beat's own `note`:

1. **No open obligation with a live exposure receipt on this permit** — *"there is nothing to
   sign a disposition against. A disposition's composite foreign key lands on
   `(check_id, receipt_id)`; the API does not fabricate either."*
2. **The obligation moved between the opening read and the beats' transaction**, so the
   defeater vocabulary resolved belongs to a different check — *"A disposition pins the digest
   of the option set its own check offered, so this run will not sign one it cannot pin.
   Re-run; this demo persists nothing, so nothing is left half-done."*

> **SAY, reading the payload's own words off the screen rather than paraphrasing them:**
>
> **"Beat four skipped, so this run is NOT PROVEN — and it says so itself, there, with the
> reason in its own words. I'll run it again. This endpoint persists nothing, so nothing is
> left half-done."**

**DO.**
- Read `failures` aloud, off the screen. The array exists so that silence about a red is
  impossible.
- Press again on camera. The second skip condition is a race and clears on a re-run; the
  payload's own note tells you to re-run.
- If it skips **twice**, the film has no admission beat that day. That is a shoot-moves case
  under R-N: B7's entire content came out of beat 4, and there is no honest way to film B7
  without it. Stop, and hand it to whoever owns the seed — this is not a founder's fix at 02:00.
- **On the local node this is the likely one, not the unlikely one.** The judge-path receipt on
  the deployed world expires `2027-01-01`; the film's own local database uses a different
  receipt expiring **two hours after issue**, and `scripts/submission/seed_demo_state.py` prints
  that deadline on **every** run for exactly this reason. If you are filming locally (F-10),
  re-seed before the take and read the deadline it prints.

**NEVER.** **Never narrate `PROVEN` over a run that did not produce it.** Never crop the
verdict out of frame to keep the shot clean. Never say "we proved it in CI" — nothing in CI has
ever asserted this URL, the `demo-health` lane is red on every schedule and it is red for the
right reason. Never re-record audio over this picture: if the take failed, re-record the take.

---

### F-5 · A JUDGE IN DEVTOOLS — "why is there one request and three transitions?"

**What it looks like.** A judge counts the Network rows, counts the beats, and the arithmetic
does not obviously agree. **This is the best question anyone can ask, and the film should have
already answered it before it is asked.**

> **SAY — the disclosure line, out loud, and say it flat, as a fact about the panel he is
> looking at rather than as a defence:**
>
> **"One request, four beats. They arrived in one already-rolled-back SERIALIZABLE transaction
> — they cannot arrive any other way, because they share one transaction fenced by savepoints.
> The panel reveals them in order as a reading aid, and every timing on it is the server's, not
> mine. That sentence is on the screen the whole time, and you can't dismiss it."**

**DO.**
- Point at the page's own disclosure strip, which composes itself from the payload and carries a
  live byte count: `one request · 4 beats · POST /v1/demo/gate-run · run_id … · response
  received … · … bytes`. W7's capture asserted its shape, asserted the byte count was the real
  body size, and asserted **zero** controls inside the strip — it is not dismissible.
- **Click a reveal with the Network panel in frame.** No new row appears. W7 measured the two
  reveals at **30 ms** and **33 ms** from click to DOM — orders below anything that could be
  mistaken for a round trip, and nothing like a fabricated delay.
- Offer the second press. `run_id`, `generated_at` and the transaction's opened logical
  timestamp all change between two runs; a recording cannot do that.

**NEVER.** Never let a judge discover the single request rather than be told it. Never describe
the reveal as anything but a reading aid over a completed exchange. And never remove the strip
to tidy the frame — without it the reveal is indistinguishable from faked sequencing, which is
plan R-C's exact words.

---

### F-6 · THE CUSTODY SEAL CHIP — `NOT VERIFIED` is not `VERIFIED`

**What it looks like.** The Custody screen computes its seals **in the browser** and prints a
tally under the label `checks passed / failed / not run`. The verdict at its very best reads
**`NOT VERIFIED`** with **zero failed and eight not run** — and `NOT VERIFIED` is a different
word from `VERIFIED`, on purpose.

> **SAY:**
>
> **"That says NOT VERIFIED, and NOT VERIFIED is not VERIFIED. Every check that ran passed —
> and eight did not run at all. They're the cryptographic half, and the screen names each one
> and says in words why it did not run rather than going quiet or going red. A report
> containing a SKIP is not a clean report, and we would rather show you the skip."**

**DO.**
- **Open the screen and read the chip with your own eyes before you film it.** The researcher
  who wrote the honesty register marked this as the one item he had **not** opened — he measured
  the data, not the chip — and flagged it as speculation. Read the tally off the screen; do not
  carry the numbers from this page onto camera.
- If any check reads **FAILED**, this is a different sentence and this screen does not get
  filmed that day. Escalate.
- Keep the CLI figure separate from the chip figure. `trappoint-verify` on the offline bundle
  reports **16 checks · 9 passed · 0 failed · 7 not checked, exit 2** — a different subject and
  a different count. Mixing the two on camera would be quoting a number about the wrong thing.

**NEVER.** Never say the custody bundle verifies, never say the ledger is cryptographically
verified, and never say all checks pass — none of those is true. Never say **tamper-proof**:
the claim is **tamper-evident**, never tamper-proofing. Never say **split-view resistant** in
any form, on any screen, in any caption — there is **one** witness, it is ours, `q = 1`, and
split-view resistance is not claimed and never has been.

---

### F-7 · "WHAT ABOUT THE SILENCE RECEIPT?"

**What it looks like.** The silence screen is a linked surface and is deliberately **out of the
120 seconds** (plan R-J). One field on it, `receipt.bound.statement`, is reproduced verbatim
from spec and is produced by no column.

> **SAY — one sentence, and do not shorten it, because the short version overstates it in one
> direction and undersells it in the other:**
>
> **"One field on that screen has no column behind it — `bound.statement`, the bounding sentence
> the contract requires on every exhibit, copied verbatim from spec. Everything else is a
> column: `corpus_root`, `candidate_root`, `theta`, `s`, `n`, `boundary_proof`,
> `policy_version`, and the index generation and plan digest out of `mainline_meas.recall_run`.
> The envelope names the one field rather than badging the whole screen. And the bound is on
> the retrieval that ran — never on the corpus."**

**DO.** Open it if asked, point at the one field, and let the envelope's own `staged` marker do
the work. It names the field, which is a stronger act than badging a screen.

**NEVER.** Never say the screen is staged — that under-sells it by an order of magnitude and it
is not accurate. Never say it is *"every warning the system decided not to give, computed
live"* — that over-sells it in the other direction. Never claim exhaustion of the corpus;
exhaustion is of the retrieval that ran.

---

### F-8 · "SHOW ME THE CHANGE REQUEST BLOCKING TOO"

**What it looks like.** `DEMO-MOC-0001` appears once, read-only, in B8, with `open_blocking 1`
and its own defeater codes, and the approve control **rendered disabled with the obligation
named as the reason**. There is no merge route for it — a `POST` to one measures `404`, and the
`404` body declares the whole route table — and `mainline.change_request` carries no title, no
description, no proposed text, no requester and no target clause.

> **SAY:**
>
> **"There's a second subject carrying the same clause's debt — a change request that proposes
> to edit the clause. `open_blocking` is one, it has its own gate constraints and its own
> defeater vocabulary, and all of that is columns we measured. There is no merge route for it
> yet, so I'm telling you about it rather than driving it."**

**DO.** Show it once, read-only, and move on. It is the film's cheapest scope cut if time runs
long — plan §2.2 puts B8's second half first on the ladder for exactly this reason.

**NEVER.** **MUST NOT SAY:** *"watch the same debt block the change request"* — nothing is
watched, because no merge route exists. Never render a "proposed" clause string: the table
carries none, so a plausible one would be hard-coded, and hard-coding a plausible string is the
same class of act as reshaping a seed to match a constant. Never say the clause **was**
rewritten — **somebody has proposed** to rewrite it, and the date on screen is `2019-03-14`.

---

### F-9 · THE OPERATOR UI DOES NOT LAND

**This is not hypothetical. It is the state I measured.**

`GET <origin>/operator.html` answers `200` with **4,655 bytes that are byte-identical to
`GET <origin>/`**, and both carry `<title>MAINLINE console</title>`. The built operator entry
point exists in this tree — `verticals/mainline/apps/console/dist/operator.html`, a different
document with `<title>Control of Work</title>` — and it is **not on the deployed origin.**
`CLICKS.md` D-6 flags the same gap and assigns it to the orchestrator; my `GET` is the
confirmation, and I am forbidden to deploy it. **The founder must re-check on the day** — the
one-line check is in §4.

> **SAY, if it is still true when the light goes on — on camera, at the top, not as an
> apology:**
>
> **"What you're looking at is the MAINLINE console and a terminal. The operator screens — the
> permit-to-work form and the disposition screen — exist in the tree and are not on this origin
> yet, so I'm going to show you the kernel directly instead of the software that sits on top of
> it. Every refusal you see is still the deployed API answering, with the SQLSTATE the database
> produced."**

**DO.** Film the console surface and a terminal, and **say on camera that that is what you are
doing.** The refusals are unchanged: they still come back over HTTP from the deployed API, and
they still carry the real SQLSTATEs. What is lost is the framing — the refusal landing inside
the software the story's people use — and the honest move is to name the loss rather than
simulate the frame.

**NEVER.** Never build a static operator page for the camera. Never dress a screenshot of the
built local page as the deployed one. Never point a URL bar at something and let the frame imply
it came from the origin it did not come from. A mockup here would fake the exact thing plan
§0 exists to deliver, and it would be a rules violation as well as a lie.

---

### F-10 · THE LIVE ORIGIN IS DOWN

**What it looks like.** `GET /v1/health` does not answer, or answers `ok:false`, or the origin
answers a `502`/`503` that is the platform's rather than the product's. Note the one honest
near-miss: `dsn_unset` naming `GetParameter … → ParameterNotFound` is the system refusing for a
**named** reason rather than pretending, and it is not the same event as an origin that is dark.

**There are exactly two answers, and neither of them is a mock.**

**Answer one — postpone.** Say nothing on camera, because there is no camera. This is the
default and it costs less than it feels like it costs.

**Answer two — film against the local node, and say so on screen.**

> **SAY, in the first fifteen seconds, before anything else:**
>
> **"One thing before I start: this is running against a CockroachDB node on this machine, not
> against the deployed URL — that origin is down right now. The strip at the bottom of the page
> says so, and it says so because the server stamps its own header on every response. The
> database, the migrations, the constraint and the trigger are the same ones; the hop is
> local."**

**DO.**
- Serve it with `scripts/deploy/local_furl.py`. It translates HTTP into the same payload-format
  2.0 event and calls the same handler, imported unmodified — **nothing between the arrows is
  stubbed, wrapped, patched or re-implemented** — and it stamps two headers on every response:
  `X-Mainline-Emulator: local_furl` and `X-Mainline-Not-The-Demo-Url` carrying its own path. It
  also prints a banner on start that refuses the title "the demo".
- The operator page's own **origin strip** renders `X-Mainline-Emulator` when it is present, so
  the disclosure happens in the page's own words rather than in an overlay somebody could have
  written. Keep it in frame. Have W5 burn a strap as well, so the disclosure survives a scroll.
- Re-seed first, and read the receipt deadline the seeder prints (F-4).

**NEVER.** Never crop the origin strip, never suppress either header, and never let a local take
be described anywhere — video, description, submission — as the deployed one. Never use a mock,
a fixture server, or a recorded payload replayed as if live: `TRANSPORT REPLAY` in the header is
a stop condition, not a fallback.

---

### F-11 · A SECOND `POST` ROW APPEARS THAT NOBODY SAW A REASON FOR

**What it looks like.** Two `gate-run` rows in the Network panel, or one `gate-run` and one
anything-else, with no visible failure between them.

**SAY:** nothing. **DO:** stop the take, and start again from pre-roll step 2. There is exactly
one mutating request in the entire film. The exception is F-2, where the first row is on screen
failing and the second press is the honest answer.

**NEVER** narrate over it, and never trim the extra row out in the edit — that is editing the
thing being claimed.

---

### F-12 · THE WATERMARK OR THE DISCLOSURE STRIP SCROLLS OUT OF FRAME

**What it looks like.** Both strips are normal flow elements with no sticky positioning, so they
leave frame after B0 and at B3/B6 respectively (`CLICKS.md` D-1, D-2).

**DO.** W5's burned-in strap carries the identical sentence for the beats that are scrolled away
from the top. For the disclosure strap specifically, the burned version carries **no run-varying
value**: a generic sentence cannot be wrong about a run, whereas a burned `run_id` typed by hand
can be — and would be, at 02:00.

**NEVER** crop the watermark to make a frame prettier, and never drop the `SYNTHETIC` prefix
from the incident narrative. A judge who sees the system labelling its own demo data trusts
everything else on the frame **more**, not less.

---

### F-13 · THE REQUEST DOES NOT COMPLETE AT ALL

**What it looks like.** The page's own runtime check renders `THE REQUEST DID NOT COMPLETE` and
names the path. Or the wait passes fourteen seconds and the platform cuts the call. Or a `413
response_too_large` comes back to a client that refuses compression.

> **SAY, if it is a `413`:** **"That's the response ceiling refusing rather than truncating. It
> would rather tell you it cannot serve the whole answer than serve you most of one and let you
> think it was all of it."**
>
> **SAY, if it is a transport failure:** **"That didn't complete. I'm not going to narrate a
> refusal over a request that never got an answer — let me press it again."**

**DO.** Press again on camera, once. If it fails twice, the shoot moves (R-N).

**NEVER** describe a transport failure as a refusal. A refusal has a SQLSTATE, a constraint and
a reason set; a failed request has none of the three, and putting a refusal's clothes on it is
the fabricated-exhibit move again.

---

### F-14 · THE PERMIT SCREEN DOES NOT TURN FROM BLOCKED TO ISSUED

**What it looks like.** Beat 4 comes back `ADMITTED · 00000`, and the permit header **does not
change**: the action-bar lock note still reads that the trigger refused this write, `ISSUE ▸`
is still disabled, the state chip still reads `dispositioned`, and `open_blocking` still reads
`1`. W7 measured exactly this across the admission stage.

**That is correct behaviour, not a defect.** The admission happened inside a transaction that
was rolled back, the page holds no re-read, and a screen that flipped to "issued" would be
asserting a state the database does not hold. The sentence *"the form turns from blocked to
issued"* lives in three sibling files and the software does not do it — `CLICKS.md` §7.1 has
escalated it.

> **SAY the true thing instead, which is in the same frame and is stronger:**
>
> **"Admitted — zero zero zero zero zero. The disposition applied, open obligations after the
> signature: zero, permit state merged, and there's the merge record. And three rows below
> that: this run persisted anything — false. The gate admitted, and the lock is still on the
> screen beside it, because none of this was allowed to happen."**

**NEVER** fake the render, and never re-cut picture under re-recorded audio to make the old
sentence land. The only way to make that sentence true on camera is to fake the render, which
is the one act this wave exists to prevent.

---

### F-15 · THE DISPOSITION PANEL IS NOT ON THE PERMIT SCREEN

**What it looks like.** B6 as written in the beat sheet has no pixels on the permit side: the
three defeater prompts and the cost lattice render on the **change** screen only, and the permit
screen issues no `GET` for a disposition (`CLICKS.md` D-5).

**DO.** Take Path B and trim B6 to the beat sheet's shorter form, or show the read-only panel on
the change screen and say which screen it is. **NEVER** stub a screen for the film, and never
present the change screen's panel as the permit's.

---

### F-16 · A JUDGE ASKS SOMETHING NOBODY REHEARSED

See §3, answer four. It is the strongest sentence in this document and it costs nothing.

---

## 3 · THE FOUR HARD-QUESTION ANSWERS — VERBATIM, REHEARSED, NOT PARAPHRASED

These are `r6-honesty` Part C, reproduced word for word. Each is the honest answer and each is
**stronger than the evasion**. Rehearse them until they are one breath each.

**1 · "How fast is it in production?"**

> **"I don't know, and nobody who tells you does. Every timing here is a laptop or one Singapore
> round trip. The recall path crosses a region boundary and we have no p50 for it."**

**2 · "Can an admin get round it?"**

> **"Yes, and we film them doing it. A cluster admin drops the constraint and it succeeds. What
> they cannot do is drop it unobserved. The claim is tamper-evidence, never tamper-proofing."**

**3 · "Does it stop people rubber-stamping?"**

> **"No. Nothing in this data model separates a considered disposition from a rubber stamp. It
> makes the question unavoidable, the record precise, and the worst stamp non-representable. It
> measures deliberation and never accuses."**

**4 · Anything you do not know.**

> **"I don't know, and here is the file that would tell us."**

Then link `docs/HONESTY.md`. It is the best thing in the repository and it is a document whose
numbers fail the build when they drift.

**The delivery note that makes all four work.** Say them at the same speed and in the same
register as the rest of the film. An honest limit delivered apologetically reads as a weakness;
delivered flatly it reads as a control. Answer three in particular is a **feature of the
pitch** — it is the sentence that tells a judge the rest of the numbers can be trusted.

---

## 4 · THE PRE-FLIGHT — RUN ON THE DAY YOU RECORD

`r6-honesty` Part D, plus the two additions this wave earned: the warm-up from `r5-craft` §0.1,
and the operator-surface check from F-9. **The RAN/TRANSCRIBED column is per command and is the
point of the block** — a command nobody has run is a plan.

```bash
cd D:/CoackroachDBxAWS/mainline
PY=D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe
URL=https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws

# ── the live system ────────────────────────────────────────────────────────────────────────
curl -sS "$URL/v1/health"                                        # ok:true, 271/271, fresh server_date
curl -sS -X POST -H 'content-type: application/json' -d '{}' \
     "$URL/v1/demo/gate-run" | grep -o '"verdict": *"[A-Z ]*"'   # must be PROVEN, all four beats

# ── the surface you are about to film (F-9) ────────────────────────────────────────────────
curl -sS "$URL/operator.html" | grep -o '<title>[^<]*</title>'   # must read Control of Work

# ── the repository's own checkers ──────────────────────────────────────────────────────────
$PY scripts/mi_ratchet.py report | tail -1                       # the invariant figure, never quoted
$PY scripts/demo/claim_hygiene.py                                # no forbidden claim in any file
$PY scripts/demo/claim_hygiene.py --self-test                    # and the checker can still go red
$PY scripts/qa/regression_guard.py                               # a SKIP forbids the word GREEN
$PY verticals/mainline/demo/honesty/gen_card.py --check          # the card matches its inputs

# ── the last sixty seconds ─────────────────────────────────────────────────────────────────
# WARM THE FUNCTION 30-60 s BEFORE THE TAKE, FROM A DIFFERENT TAB OR BROWSER.
```

| command | RAN by W6 / TRANSCRIBED | what to expect, and what to do about it |
|---|---|---|
| `curl … /v1/health` | **RAN** (M1) | `ok:true`, `271 / 271`, and a `server_date` from today. I read `0.711 s` from this workstation, which is the ~232 ms round trip to `ap-southeast-1` plus the handler. |
| `curl -X POST … /v1/demo/gate-run` | **TRANSCRIBED — I issued no `POST` by hand.** The guard did, as its own `LIVE` family (M11), and it read **`PROVEN`, 4 beats, 0 mismatch(es)** this session. | Must read `PROVEN`, with four beats and `failures: []`. **A reading from this session is not a reading from the day of the shoot — run it yourself and read your own output.** If it reads `NOT PROVEN`, go to F-4 before you go anywhere near a camera. |
| `curl … /operator.html \| grep title` | **RAN** (M2) | **Today it reads `<title>MAINLINE console</title>`, which means the operator surface is NOT on the origin.** It must read `Control of Work`. If it does not, the shoot follows F-9. |
| `mi_ratchet.py report` | **RAN** (M6) | `21 pending / 9 enforced`, exit 0. Run it to see drift; **never quote the figure on camera** (R-K). |
| `claim_hygiene.py` | **RAN** (M4) | `claim hygiene OK`, exit 0 — **and read the `ABSENT` lines.** Four globs matched no file and the tool prints *"not scanned, and therefore not passed"* for each. That is the tool refusing to let absence read as success; do not skim past it. |
| `claim_hygiene.py --self-test` | **RAN** (M5) | `planted 4 violation families, scanner fired on 4`, exit 0. **This is the one that matters.** A hygiene check that has never fired asserts nothing about a repository whose whole pitch is that it refuses to overclaim. |
| `regression_guard.py` | **RAN — RED, exit 1** (M8) | **Expect `REGRESSION - 3 of 31 checks FAILED`, and read note (d) before you react to it.** It takes well over five minutes; start it first. Its `LIVE` family **posts to the gate-run itself** (M11) and read `PROVEN`, four beats, zero mismatches. A `SKIP` in it forbids the word GREEN; today there are **0 SKIP** and **3 FAIL**. |
| `gen_card.py --check` | **RAN** (M7) | **Expect exit 2 on this tree**, with a named reason: the corpus lock artefact does not exist. With `--allow-fixtures` it prints `card.html is current (53 traced values)` and **exit 3**, the documented code for a stand-in card that labels itself `NOT FOR CAMERA`. **Neither is a failure to fix at 02:00 — but a founder who has not read this row will think it is.** Do not film the card. |
| **warm the function 30–60 s before the take** | **TRANSCRIBED** (`r5-craft` §0.1, §9) | One `POST /v1/demo/gate-run` — or a `GET /v1/health`, which also opens the pool — **from a different tab or a different browser**. A press in the filmed tab reveals the beats and burns the take. Note the wall-clock duration; if it exceeds about four seconds, warm again. |

### 4.1 · The four notes without which this block reads as four failures

**(a) A non-zero exit is not automatically a red.** Three of the commands above exit non-zero on
this tree **for named, understood reasons**, and a founder who has not read this section will
read them as the shoot being off. Read the reason, not the code.

**(b) `claim_hygiene.py` prints `ABSENT` lines and they are not noise.** Four globs matched no
file, and for each the tool prints *"not scanned, and therefore not passed."* That is the
checker refusing to let an absence read as a success. If a new `ABSENT` line appears that is not
one of the four, something moved — find out what before you film.

**(c) `gen_card.py --check` exits 2 on this tree, and 3 with `--allow-fixtures`.** The reason is
named in the output: the corpus lock artefact does not exist, and it is produced by a different
worker. With `--allow-fixtures` the card renders from shipped stand-ins, labels itself
`NOT FOR CAMERA`, and exits 3 to say so. **Neither exit is a thing to fix at 02:00, and neither
card gets filmed.** r6's Part D block does not carry this row; that is why this file does.

**(d) `regression_guard.py` is RED on this tree — `3 of 31 FAILED, 28 PASS, 0 SKIP`, exit 1 —
and here is exactly what the three are.**

| check | expected | observed | what it is |
|---|---|---|---|
| `SUITES collected` | `911` | `997` | The pinned figure is **older than this tree** and the collection has **grown**. The guard's own message says what it is defending: *"a shrinking collection is a deleted test, not a faster suite."* |
| `SUITES passed` | `910` | `996` | Same ratchet, same direction. `failed 0`, `errors 0`, `skipped 1` all **PASS**. |
| `PRIVILEGES relations` | every relation the code reaches | **2 shortfall(s): `mainline.exposure_line INSERT; mainline.exposure_receipt INSERT`** | A real privilege shortfall, named per object. Handed on, not interpreted here. |

**What a founder does with that.** Nothing, on the day, except know it. **Do not move the
ratchet to make the guard green** — moving a ratchet to fit an observation is the act this
repository exists to refuse, it is banned by every brief in this wave, and it is not a
founder's decision at 02:00. **And do not cite the guard on camera at all**: its number is not
in the film, and *"our CI is green"* is on the never-said list in §5 for reasons that are older
than this run.

**Two things that must not be conflated with it.** The guard's `SUITES` family scopes
`verticals/mainline/apps/demo-api/tests tests/deploy` and read `997 / 996 / 0 / 0 / 1` from its
own `--junitxml` root element. The wave's baseline of `988 / 987 / 0 / 0` is a **different
scope of a different run**. Two true readings of two different things; neither is quoted as the
other, and neither is spoken on camera.

**Then open the Custody screen in a browser and read the SEAL chip with your own eyes** (F-6).
The one blocker of the last verification lived only in what was served, and no test in this
repository would have caught it.

**And the three from `r5-craft` §9 that are not commands but are stop conditions.**
`TRANSPORT LIVE` in the header — if it reads `REPLAY`, stop, the deployed bundle is the wrong
one. The `build` cell in the honesty chrome must not read `dev`. The 480 test must pass on the
SQLSTATE frame, on the reason set and on the red refusal treatment — the capture measured that
at 200 % browser zoom all three **fail** it, so shoot at the geometry the capture fixed.

**One camera rule that belongs in the pre-flight because it is easiest to break there.** **No
camera is pointed at `docs/submission/SUBMISSION.json`** while its `demo_url` reads
`UNRESOLVED` (plan R-M). The URL itself is fine to film; that file is not.

---

## 5 · THE SENTENCES THAT ARE NEVER SAID, WHATEVER GOES WRONG

The full register is `r6-honesty` Part A and `docs/submission/MUST-NOT-CLAIM.md`. These are the
six a founder reaches for when a take is going badly, which is exactly when the reaching happens.

| **MUST NOT SAY**, however the day is going | **TRUE INSTEAD** |
|---|---|
| *"It's PROVEN"* over a run that did not produce it | Read the verdict off the screen. `PROVEN` only when `failures` is empty; the payload never rounds it up and neither do we. |
| *"Watch it remember."* · anything present-tense about the retrieval | The recall already ran — you are looking at its record, every field a column. What runs **now** is the third step: the database re-derives the obligation from blame ancestry and refuses the merge. |
| *"Our agent decided to block it."* | The decision is a `CHECK` constraint and a PL/pgSQL trigger. No model is in this path. |
| *"Tamper-proof."* · *"split-view resistant"* in any form | Tamper-**evident**, never tamper-proof. One witness, ours, `q = 1`, and split-view resistance is **not** claimed. |
| *"It refuses in milliseconds in production."* · any product latency | §3 answer one, verbatim. This repository contains no p50, no p99 and no load profile. |
| *"It catches rubber-stamping."* | §3 answer three, verbatim. Nothing in this data model separates a considered disposition from a rubber stamp. |

**And the one that is not a sentence but an act:** never show a recorded refusal as if it were
live. There is no fallback in this document that does it, and if one is ever added, it is wrong.

---

## 6 · WHAT THIS FILE COULD NOT SETTLE, AND WHO OWNS IT

Written down rather than glossed, in the same form the siblings use.

| # | open item | evidence | owner |
|---|---|---|---|
| **W6-1** | **The operator surface is not on the deployed origin.** `GET /operator.html` is byte-identical to `GET /` and titles itself `MAINLINE console`. F-9 is therefore live, not hypothetical. I am forbidden to deploy and did not. | M2, this file; `CLICKS.md` D-6 | orchestrator |
| **W6-2** | **`regression_guard.py` is RED: `3 of 31 FAILED, 28 PASS, 0 SKIP`, exit 1.** Two are the `SUITES` ratchet pinned at `911 / 910` against an observed `997 / 996`; one is a named privilege shortfall — `mainline.exposure_line INSERT; mainline.exposure_receipt INSERT`. **I did not move the ratchet and did not touch the privileges.** Whether the ratchet is re-pinned, and by whom, is not this file's call. | M8, §4 note (d) | QA / privileges owner |
| **W6-2b** | **Running the prescribed pre-flight drove the live endpoint.** `regression_guard.py`'s `LIVE` family posts to `/v1/demo/gate-run` itself. It read `PROVEN`, four beats, zero mismatches, and the guard's own `SEED` row counts matched afterwards, so nothing was written — but the brief said `GET` only, and this is on the record rather than in a footnote. | M11 | orchestrator, for awareness |
| **W6-3** | **`gen_card.py --check` exits 2 on this tree** for a named missing input, and 3 with `--allow-fixtures`. The r6 Part D block does not say so, and a founder reading that block cold will read a non-zero exit as a failure. This file's §4 note is the correction; whether the corpus lock ever lands is not mine. | M7 | corpus-freeze-load worker |
| **W6-4** | **The SEAL chip's tally was not read by any worker**, including me — the honesty researcher flagged the same gap and marked it speculation. F-6 says read it on the day, and that is the only control there is. | `r6-honesty` speculation item 1 | founder, before the take |
| **W6-5** | **No worker has run `POST /v1/demo/gate-run` in this wave**, by design. Every payload string quoted across the film's files is from committed evidence or from the handler's source. The day's verdict is the founder's own run and nothing substitutes for it. | M9 | founder |

---

**Last line, and it is the one to read if only one line gets read.** Every failure in this
document has an honest answer that is shorter than the dishonest one, and in every single case
the honest answer is the more interesting thing to watch. The cold start is a container waking
up. The `40001` is `SERIALIZABLE` doing its job. The `423` is the demo refusing to let one
caller brick it for the next. The `NOT VERIFIED` is eight checks declining to pretend. **A
product whose failure modes are all worth filming does not need a demo that lies.**
