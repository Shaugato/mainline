<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `/memory.html` — the shot direction

**Worker:** `w6-audit` · **Lead plan:** `docs/demo/memory-visible-plan.md` · **Date:** 2026-08-15
**Subject:** the store → retrieve → act panel, on camera, in **under 20 seconds of screen time.**

This is the panel that answers the Devpost brief's hardest line — *"Show the CockroachDB memory in
action visibly… a screen showing your agent store, retrieve and act on memory. Don't just
narrate."* — and the Official Rules' requirement of **footage showing the CockroachDB memory layer
at work**. `r1-judging` found the criteria tie-break is lexicographic with Agentic Memory Design
first. These twenty seconds are the axis-1 exhibit.

---

## 0 · The one rule that governs every word below

**The screen states the numbers. The founder states the meaning.**

Every figure in the frame arrived in one of five HTTP responses and will differ run to run — the
per-beat `elapsed_ms` certainly will. A voice-over that says a number the screen is about to
contradict is the only way to lose this panel, and it is avoidable by never saying one. There is
one exception and it is a name, not a measurement: the founder may say *"twenty-three five
fourteen"* if he chooses, because the SQLSTATE is the seeded world's stable answer — but the
screen says it anyway, so he gains nothing by it.

Corollary: **no number in this document may be read onto the soundtrack.** The numbers here exist
so the founder can rehearse the *shape* and time the cuts.

---

## 1 · Before the camera rolls — the checklist

Run in order. Any red stops the shoot; none of these is fixable in post.

| # | check | how |
|---|---|---|
| 1 | the page is deployed and the four reads answer | open the live URL at `/memory.html`, wait for column ② to fill; an em dash anywhere in ① or ② means a read did not answer |
| 2 | the verdict is `PROVEN` and `failures[]` is empty | press once, off camera, and read the verdict strip |
| 3 | `self persisted` reads `false` | it is the honest reading (`r2-memory` warning 8); `identical` is the wrong one and is not what the page shows |
| 4 | the two `SYNTHETIC —` prefixes are on screen and unstripped | column ①'s *title* and *attribution* (ruling R-M13) |
| 5 | the statement disclosures expand and carry real SQL | column ②'s two `<details>`; if either says *"statement text not returned by this endpoint"*, that is honest but it is not the shot — reframe to the one that carries text |
| 6 | the source audit is green | `python scripts/qa/check_memory_panel_honesty.py` |
| 7 | the browser tier is green | `pnpm run test:browser` (see §7 — the config must collect `memory-loop.spec.ts` first) |
| 8 | geometry | 1024 × 576 CSS at `deviceScaleFactor 2.5` → a 2560 × 1440 frame, the same geometry `playwright.config.ts` films and asserts legibility at |
| 9 | one browser window, no extensions, no bookmarks bar, no devtools *in this shot* | the network-panel shot belongs to the proof section, not to these twenty seconds |
| 10 | a **second tab** already loaded at `/memory.html?reveal=off`, unpressed | it is the last three seconds of this panel |

**Press once off camera before the take.** The run is idempotent — the transaction rolls back —
and a cold Lambda answering its first request in eight seconds is not a shot anyone wants.

---

## 2 · The reveal cadence, and why it is a parameter rather than a default

The ACT column is filled from **one** `POST /v1/demo/gate-run` whose four beats already happened
inside one `SERIALIZABLE` transaction. The page reveals them in order, and `?reveal=<ms>` sets the
step. The reveal is a display order over values that had all arrived; it is never labelled a
latency, and `?reveal=off` fills every beat instantly (ruling R-M7).

| cadence | press → beat 4 | what it buys | what it costs |
|---|---|---|---|
| `?reveal=off` | round trip only | the proof shot; nothing to suspect | no room to speak |
| default (no parameter) | round trip + ~2.0 s | a judge's own visit | too fast to narrate |
| `?reveal=2000` | round trip + 6.0 s | a tight cut | the peak has ~2 s |
| **`?reveal=3000`** | round trip + 9.0 s | **the peak breathes; beat 4 lands into the silence** | the panel spends 19.8 s |

**Film at `?reveal=3000`.** Three defences make the cadence unmistakably a cadence:

1. the persistent disclosure line — *one request · four beats · one SERIALIZABLE transaction* — is
   on screen for every frame of the take;
2. each beat prints **its own** `elapsed_ms` from the payload, and those figures run from a small
   fraction of a millisecond (the read) to a few hundred (the three writes) while the cadence is
   three thousand. **The numbers on screen disagree with the cadence, on purpose.** A viewer who
   suspects the reveal is latency is refuted by the frame he is suspecting;
3. the last three seconds of this panel are the same run at `?reveal=off`.

Round-trip figures measured, so the cut can be timed: **1,895 ms** against the deployed Function
URL (`fixtures/memory-loop/manifest.json`, captured 2026-08-15T11:57:21Z) and **888 ms** against
the local emulator (this worker's run, same day). Budget **~2.1 s** for the wait and re-time on the
day — the page prints `round trip ms` in the verdict strip.

---

## 3 · The shot sheet

`t` is screen time from the panel's first frame. **VO** is what the founder says; a `—` means he
says nothing, and the silences are as directed as the words.

At **t = 0 columns ① and ② are already filled.** They are facts, not results: the four reads ran
when the page loaded, before the camera. The ACT column is em dashes, which is the page saying it
has been handed nothing rather than showing a zero.

| t | on screen | VO | direction |
|---|---|---|---|
| `0.0` | the whole panel: ① STORED, ② RETRIEVED filled; ③ ACTED ON empty | *"This is what the system remembers about one clause — and it did not learn it from a document. It learned it from an incident."* | steady wide on the three columns; no zoom |
| `1.4` | eye lands on ② — severity, virulence, and the `═` marker | *"Same severity, arriving in two different responses. Nothing here chose it."* | let the `same value, two responses` marker carry it; do not read the values aloud |
| `2.2` | **PRESS** | *"One request."* | the cursor is already on the button at t=0; the click is visible |
| `2.2 – 4.3` | ③ goes to `awaiting response`; ① and ② unchanged | *"Four beats, one transaction."* | this is real latency and it is the most honest two seconds in the film — do not cut it out |
| `4.3` | **beat 1 · read · `00000`** | — | half a beat of quiet; the eye reads `00000` unaided |
| `4.8 – 6.9` | beat 1 holds | *"It reads first. The permit, and the obligation still open on it."* | — |
| `7.3` | **beat 2 · merge · REFUSED · `23514` · `gate_closed_when_issued`** | *"Now it tries the merge. Refused — by a check constraint, by its name."* | **CALM.** Beat 2 is table stakes; every database can enforce a CHECK. Filming it as the climax leaves beat 3 nowhere to go (`r4-story` §4.2) |
| `9.3 – 10.3` | beat 2 holds | — | one second of nothing. This is the run-up |
| `10.3` | **beat 3 · projection_drift_attack · REFUSED · `P0001` · `mainline.fn_permit_merge_gate`** | *"Before that beat, the counter this gate reads was set to zero. Out of band. It refuses anyway."* | **THE PEAK.** Slow push-in permitted, one step only, ending before the line |
| `11.9` | beat 3 holds; the claim line under it reads *An attacker who owns the counter does not own the gate* | *"An attacker who owns the counter does not own the gate."* | say it once, flat, no lift at the end |
| `13.0 – 13.3` | unchanged | — | **silence.** Do not fill it |
| `13.3` | **beat 4 · admit · ADMITTED · `00000`** lands into the silence | — | hold the silence over it. The admission is deliberately undersold: the memory does not veto |
| `14.5 – 16.2` | beat 4 holds | *"One disposition is signed against the obligation, and the same merge is admitted. Same gate. Same transaction."* | — |
| `16.2 – 17.0` | the verdict strip: `PROVEN` · `self persisted false` · `single transaction true` | *"One transaction, and nothing this run wrote survived it."* | the strip is small; a brief scale-up is allowed, a re-render is not |
| `17.0` | **hard cut** to the second tab, `?reveal=off`, and press | *"Reveal off —"* | no dissolve. A cut is honest; a dissolve looks like an edit over the interesting part |
| `17.3 – 19.8` | all four beats fill at once | *"— every figure was already in that one response."* | end frame: the full ACT column and the disclosure line legible |

**Total 19.8 s.**

### If it has to be shorter

Cut in this order, and never past the third: `1.4` (the equality marker) → `4.8` (beat 1's line) →
`16.2` (the verdict line). **Never cut the `17.0` reveal-off shot** — it is the cheapest credibility
in the film — and never cut beat 3.

### If a take goes wrong

Retake **the whole press-to-verdict window**. A cut inside the ACT column is the one edit that
would let a viewer wonder whether the values were swapped between beats, and no gain in tidiness is
worth handing him that question.

---

## 4 · The two sentences the panel carries in text, and who says them

The page already prints both. The founder should **not** read them aloud — a viewer reading a
sentence while hearing it is a viewer processing neither.

- **"Nothing here was deleted."** — column ①, under the closure. It is earned by the append-only
  trigger, cited on the page with its file and line.
- **"The agent could not choose this."** — column ②, under the equality marker. Earned by
  `fn_check_project`, which assigns severity, virulence and generation from the closure
  unconditionally. The page footnotes it with the seed's own pre-projection values, quoted as a
  **citation of this repository in the past tense** — never as a database value, because that half
  was overwritten and is recoverable by no read (ruling R-M5).

---

## 5 · The surfaces this loop actually exercises

For the naming section (`story-and-script-plan.md` C2/C3) or a text overlay. **Everything below is
exercised by the twenty seconds above** — nothing in this list is in the account but off this path.

### CockroachDB

| feature | where it is in this loop | visible on this panel |
|---|---|---|
| `SERIALIZABLE` isolation | the four beats run inside one transaction | yes — the disclosure line and `single transaction true` |
| one transaction, three `SAVEPOINT`s (`gate_run_beat_2/3/4`) with rollback between beats | how four beats survive two refusals without four transactions | in the payload's `transaction.savepoints` |
| `cluster_logical_timestamp()` (HLC) | the transaction's opened and closed logical timestamps | in the payload |
| `CHECK` constraint `gate_closed_when_issued` → SQLSTATE `23514` | beat 2's refusal | yes — beat 2 |
| PL/pgSQL `mainline.fn_permit_merge_gate`, `RAISE` → SQLSTATE `P0001` | beat 3: re-derives the open-obligation count from base tables and refuses when the projected counter disagrees | yes — beat 3 |
| `SELECT DISTINCT ON (clause_uuid, as_of_commit) … ORDER BY … closure_gen DESC`, view `mainline.clause_blame_current` | the retrieval read — generation-versioned, so a superseded closure is still readable | yes — the statement disclosure shows the view's own text, as the API returned it |
| `BEFORE UPDATE OR DELETE` trigger `append_only` on `mainline.clause_blame_closure` | why "nothing here was deleted" is a weld and not a convention | cited on the page with file and line |
| user-defined enum `mainline.virulence_class` | `virulence::text AS virulence` in the disclosed statement | yes — inside the statement |
| `BYTES` columns with `encode(…,'hex')` / `decode(…,'hex')` | commit ids, digests, and the ledger's canonical bytes | yes — the digests in ① and ② |
| the append-only ledger rows the browser re-derives | two leaf hashes, recomputed in the browser from the bytes the same response carried | yes — the two *verified here* rows in ① |

### AWS

| service | what it does in this loop | visible |
|---|---|---|
| **AWS Lambda** (`python3.13`, arm64) | ran the handler that answered all five requests | in the URL |
| **Lambda Function URL** (`authorization_type = NONE`, `invoke_mode = BUFFERED`) | the same origin serves this page **and** `/v1/*` — which is why the page is framework-free and lives inside the response-size ceiling | in the URL |
| **SSM Parameter Store** (SecureString, KMS-decrypted at cold start) | the only place the database credential lives; the function reads exactly one parameter | no — and say so |
| **CloudWatch Logs** | one log group; the invocation behind this take is in it | no |
| **IAM execution role** | reads that one parameter, writes that one log group, and nothing else | no |

**Not on this path, and worth saying out loud:** CloudFront and S3 (they serve other artefacts),
CloudTrail, and **Amazon Bedrock — exercised in this repository, not in this request path.** Naming
a service the loop does not touch is the kind of small overclaim a judge with the repo open will
find, and it costs more than the service was worth.

---

## 6 · Forbidden on this panel

Each of these has a true alternative beside it. The prohibitions are the lead plan's rulings and
the repository's law; the alternatives are what to say instead.

| never | why | say / show instead |
|---|---|---|
| *"vector search"*, *"embeddings"*, *"similarity"*, a threshold | those tables are **empty** in this world and `tau_applied` is 0 (R-M9). A similarity visual would be a fabricated exhibit | *"recall reached it through blame ancestry"* — the page prints `origin blame_ancestry` and the counts |
| the year **2024**, or `INC-2024-0117` | the incident is **2019-03-14**; `INC-2024-0117` lives inside a STAGED payload (R-M11) | the date the page prints |
| *"Kestrel Resources"*, `WO-88213` | stale nouns from `DEMO-HONESTY.md`; they name nothing in this world | `DEMO-INC-0001`, as printed |
| citing `ARCHITECTURE.md` | it does not exist in this tree (R-M11) | `docs/demo/memory-visible-plan.md` |
| reading a stored severity of `0 / routine` as a value | that half was overwritten and no read recovers it (R-M5) | the page's own citation register: *"the seed supplied…"*, past tense, with file and line |
| re-recording the ACT column separately, or compositing beats | it would be a staged refusal — a Devpost **Functionality** violation, judged by people with this public repository open | one unbroken take from press to verdict |
| saying *"agentic memory"* | it says the hackathon's word back to the hackathon (`r4-story`) | show the loop; the label is the judges' job |
| a number from this document | every figure is per-run | let the screen say it |

---

## 7 · Hand-offs

1. **`playwright.config.ts`** collects `/operator-.*\.spec\.ts$/` and therefore does **not** collect
   `tests/browser/memory-loop.spec.ts`. One character class collects both suites —
   `testMatch: /(operator|memory)-.*\.spec\.ts$/` — and the file is not this worker's to edit. Until
   it lands, run the spec with an explicit config or `MAINLINE_MEMORY_BASE_URL`.
2. **The network-panel shot** — devtools open, five requests, one POST — belongs to the proof
   section, not to these twenty seconds. It is the natural companion to the `?reveal=off` cut and
   makes the same point with different evidence.
3. **The operator screens** may host this loop by importing `mount()` from `memory-loop.js`; that
   integration costs one script tag and changes nothing in this direction.

---

## 8 · Where every number in this document came from

| number | source |
|---|---|
| round trip 1,895 ms (deployed) | `verticals/mainline/apps/console/fixtures/memory-loop/gate-run.json` → `data.elapsed_ms`, captured 2026-08-15T11:57:21Z by `scripts/demo/capture_memory_loop.py` |
| round trip 888 ms (local) | one run of `scripts/deploy/local_furl.py` against the local CockroachDB node, 2026-08-15, this worker |
| beats: `read 00000` · `merge refused 23514` · `projection_drift_attack refused P0001` · `admit admitted 00000` | both of the above, agreeing |
| four reads + one addressing GET + one POST | asserted every run by `tests/browser/memory-loop.spec.ts` |
| reveal cadence arithmetic | `memory-loop.js` — `DEFAULT_REVEAL_MS 650`, `MAX_REVEAL_MS 4000`, one step per gap between beats |
| 2560 × 1440 filming geometry | `playwright.config.ts`, which films and asserts legibility at 1024 × 576 CSS × 2.5 |

**Every one of them is per-run except the last two. Re-measure on the day; script the shape, not
the figures.**
