<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# TWO-AUDIENCE LEAD — the console a stranger can read and an engineer can audit

**Domain:** `verticals/mainline/apps/console` (its own pnpm workspace) plus exactly one
new read on `verticals/mainline/apps/demo-api`.
**Authority for this plan:** the founder's two requests of 2026-08-15, quoted in §0;
`docs/leads/ui.md` §1.1 (the three registers), D5, D7, D13, D16, D18; `docs/HONESTY.md`
(untouched by this plan); `verticals/mainline/db/seeds/demo/demo_world.sql` §preamble
(the synthetic disclosure).
**Date measured:** 2026-08-15, against the live URL and the tree at `e88b8b6`.

---

## 0. What the founder asked for, and what I measured before deciding anything

Two requests, both verbatim:

> *"the way it's written, it's kind of hard to read… someone might not have technical
> abilities but still uses this software, they should be able to understand. And someone
> has technical ability… they should be able to look into more detail."*

> *"the demo is all about showing what we are doing… we need to present a couple of
> exceptional use cases that we are solving with this platform and show those examples."*

I did not work from the brief's description. I fetched the live kernel and read the
shipped source. **The measurements below are the ground truth this plan is built on and
every one of them was taken today.**

### 0.1 The kernel is not the problem — measured

| probe | result |
|---|---|
| `GET /v1/health` | `ok=true`, `mainline_demo`, CockroachDB CCL v26.2.5, deploy chain **271/271**, `0.0146 s` |
| `POST /v1/demo/gate-run` | `outcome: completed`, `failures: []`, `persisted: false`, four beats all `matched_expectation: true`, `1689 ms` |
| beat 1 `read` | `00000`, `open_blocking_projected 1` = `open_blocking_derived 1` |
| beat 2 `merge` | **REFUSED** `23514` `gate_closed_when_issued`, `constraint_source: reported` |
| beat 3 `projection_drift_attack` | **REFUSED** `P0001` `mainline.fn_permit_merge_gate`, `constraint_source: parsed` |
| beat 4 `admit` | `00000`, `merged_commit 4fbbd371…`, `permit_open_blocking 0` |
| `GET /v1/permits/dec0de00-0006-…-01` | 200 — seven CHECK constraints with their predicates and counters |
| `GET /v1/clauses/dec0de00-0004-…-01/ancestry` | 200 — closure, blame edge, commit chain |
| `GET /v1/clauses/dec0de00-0004-…-01/versions/9f12114d…` | 200 |
| `GET /v1/ledger` (no `site_code`) | 200 — checkpoints at `tree_size` 1, 2, 4 |
| `GET /v1/lessons/dec0de00-0002-…-01/propagation` | 200 — conflicts present |
| `GET /v1/permits/dec0de00-0006-…-01/silence` | 200 — `entries: []` **and a PER receipt** |
| `GET /v1/audit` | 200 — every `v_*` view present, `rows: []`, one `unreachable` entry with its own reason |
| `GET /bundle/manifest.json` | **200** |

Every screen the founder saw fail has a live, 200-answering subject behind it. **Nothing
in this plan requires a new row, a new seed, or a softened claim.**

### 0.2 The five failures, diagnosed to the line

I found the cause of every one, and I found two the founder had not walked yet.

| screen | what a judge sees | the actual cause, at the line |
|---|---|---|
| **Gate** | "no subject addressed" | `features/gate/GateSurfaceRoot.tsx:83` — `params.get('permit')`, no default, by design |
| **Propagation** | *(same, not yet walked)* | `features/propagation/PropagationSurfaceRoot.tsx:85` — same shape |
| **Silence** | *(same, not yet walked)* | `features/silence/SilenceSurfaceRoot.tsx:82` — same shape |
| **Custody** | `404 … no rows for site_code 'BLK-07'` | `features/custody/CustodyScreen.tsx:48` — `DEFAULT_SITE_CODE = 'BLK-07'`. The seed's `site_code` is `dec0de00-0001-4000-8000-000000000001`. `BLK-07` is a **literal nobody seeded**. |
| **Diff** | `404 … no clause_version row` | `features/diff/ClauseDiffScreen.tsx:55-56` — `DEMO_CLAUSE = '018f3a30-…'`, `DEMO_COMMIT = '5f916282…'`. Both **invented**. The seed carries `dec0de00-0004-…-01` at `9f12114d…`. |
| **Evidence** | `Failed to construct 'URL': Invalid base URL` | `data/bundle.ts:161` — `new URL(path, './bundle/')`. A **relative** base is not a legal `URL` base. `app/composition.tsx:174` already resolves against `document.baseURI` for the transport; the evidence surface reaches `bundleSourceFor()` directly and skips that step. The bundle itself is served and answers 200. |
| **Audit** | every aggregate "No rows" | **TRUE.** The demo API connects as `mainline_api`, not the Managed-MCP service account, and no agent call has been logged. The payload already carries the `unreachable` entry that says exactly this — the screen does not render it. |
| honesty strip | five cells `unknown` / `NOT VERIFIED` | `app/honesty.ts` — every slot is filled by the surface that can establish it, and only `GateSurfaceRoot` publishes any of them. On a screen the reader lands on cold, nothing has published, so `unknown` is the **honest** rendering of a check that never ran. The seal is `NOT VERIFIED` because the verifier is never started outside the bundle path. |

### 0.3 The finding that changes the shape of the fix

`demo-api/src/mainline_demo_api/scenario.py:118` derives the demo identifiers by
`uuid5` and writes them out as `EXPECTED` — `permit = 077a6fdd-2167-559c-…`. **The live
deployment does not use them.** `POST /v1/demo/gate-run` answers with
`subject_id: dec0de00-0006-4000-8000-000000000001`, which is what `demo_world.sql` seeds
and what `MAINLINE_DEMO_PERMIT_ID` overrides the derivation to.

So there are now **three** candidate literals for "the demo permit" — the `uuid5`
derivation, the seed's `dec0de00-…` family, and whatever a future deployment overrides
them to — and **the console has no way to know which one it is pointed at.** Any literal
compiled into the console is a fourth. That is precisely how `BLK-07` and
`018f3a30-…` got there.

**This is not a copy problem and it cannot be fixed with copy.** It is settled in
Ruling R1.

### 0.4 The copy, read before it is judged

The founder is right and the brief is right that the writing is not bad. It is exact.
`GateScreen.tsx` calls its sections *"Irreducible reason set"*, *"The weld"*,
*"The precursors"*; the one control on the headline screen is labelled
`POST /v1/permits/{id}/merge`; the honesty strip's first cell is `transport`. Every one
of those is defensible and none of them is a first sentence.

I counted the terms a first-time reader meets **before anything defines them**, on the
screens as they ship today: *projection*, *projected counter*, *canonicalisation*,
*inclusion proof*, *consistency proof*, *epoch* / *gate epoch*, *blame ancestry*,
*defeater*, *closure generation*, *virulence*, *minimal unsatisfiable subset*, *nearest
admissible alternative*, *the weld*, *register*, *provenance chip*, *staged*,
*SQLSTATE*, *transport*, *seal*, *corpus root*, *clock skew*. **Twenty-one.** None is
wrong. All twenty-one stay. What changes is what a reader meets *first*.

### 0.5 Baseline, so a regression is attributable

- Console unit suite, measured today, `pnpm exec vitest run`: **1489 tests, 1481 passed,
  8 failed across 3 files**, 159 s. The failures are **pre-existing at `e88b8b6` and are
  not this plan's work**: `tests/unit/silence/screen.test.tsx` (2 — the conservation
  identity), and two files whose failures are 5000 ms `testTimeout` expiries on this
  machine (`tests/unit/verify/custody-screen.test.tsx` among them; the run reported
  913 s of environment time). **No worker may "fix" these by weakening an assertion or
  raising a timeout ceiling. Record them before and after; if your count moves, say so.**
- Demo-api + tests/deploy: 911 collected / 910 passed / 0 failed / 1 skipped (given).
- `budgets.json`: evidentiary shell **225 280 gzip bytes**, `required: true`. Lazy 3D
  chunk 614 400, `required: false`.

---

## 1. The shape of the answer

> **Every screen opens with three sentences a site supervisor can read, and every exact
> thing that was already on it is one deliberate, permanent click away.**

Not a summary layer *instead of* the mechanism. A **band above** it. The refusal payload,
the SQLSTATE, the constraint name, the predicate, the provenance chip and the mono face
are untouched — they move down, never away, and four of them never even collapse.

Two readers, one screen, one set of bytes.

---

## 2. RULINGS — where the brief left a choice, I make it here and name my authority

Each ruling is binding on every worker. Where I overrule a thing that ships today, I say
what ships today and why it changes.

### R1 — No identifier a screen addresses may be a literal the console invented. The console **asks the kernel** which subjects exist.

*Authority: the brief's own rule — "seed the subject the console addresses, or address
the subject the seed carries" — plus §0.3, which proves the seeded subject is a
deployment-time fact the console cannot derive.*

`DEFAULT_SITE_CODE = 'BLK-07'`, `DEMO_CLAUSE`, `DEMO_COMMIT` are **deleted, not
corrected.** Replacing `'BLK-07'` with `'dec0de00-0001-…'` would produce the identical
defect against the next deployment, and would be the console asserting a fact about rows
it did not write.

The mechanism is one new read: **`GET /v1/demo/subjects`**. It answers with the
identifiers `mainline_demo_api.scenario.resolve()` — and the discovery SQL already
committed in `demo-api/tests/conftest.py:485-572` — **reads back out of the database**:
permit, site code, clause uuid, that clause's commit, the open obligation, the exposure
receipt, the recall run, the lesson. Every field is `null` when the row is absent, and
the whole read answers `404` carrying `ScenarioNotSeeded.detail` verbatim when the permit
is not there. **It asserts nothing it did not find.** That is `scenario.py`'s own stated
split, quoted in its docstring: *"a derived identifier the API pinned would be the API
asserting a fact about rows it did not write."*

**Three consequences, all binding:**

1. **The console degrades, it does not crash.** If `/v1/demo/subjects` answers `404` or
   `405` — an older kernel, a bundle replay, a deployment the orchestrator has not
   redeployed — every surface keeps the "no subject addressed" panel it has today,
   rewritten per R6. **It never guesses.** This plan must land useful even if the Lambda
   is never redeployed.
2. **The gate has a second, zero-backend path.** `POST /v1/demo/gate-run` already returns
   `subject_id`, `blocking_check_id` and the clause in `refusal.mus[].clause_id`. The
   moment a reader presses the demo driver, the gate knows its permit. Wire it. This
   makes the headline screen self-addressing **with no deploy at all**.
3. **`demo_world.sql`, `demo_permit.sql` and every migration are OFF LIMITS to every
   worker on this plan.** A worker was once caught reshaping the seed to match a code
   constant and it was reverted. The direction of fit is: **code follows seed, always.**

### R2 — The evidence surface's bundle base is resolved against `document.baseURI`, and that is a defect fix, not a claim change.

*Authority: `app/composition.tsx:174` already does exactly this and documents why;
`.env.demo` states `VITE_MAINLINE_BUNDLE_URL=./bundle/` is relative **on purpose** so the
console runs from a sub-path and from `file://`.*

`data/bundle.ts:161` calls `new URL(path, './bundle/')`. A relative base is not a legal
`URL` base in any browser. The bundle is served — I measured `/bundle/manifest.json` →
**200**. Resolve the base once, where `FetchBundleSource` is constructed, exactly as the
composition root does. **The `refuseRelativePath` guard in `features/evidence/source.ts`
is not weakened by one character** — a `?bundle=` parameter still may not name an origin,
and the resolution happens *after* that refusal, never instead of it.

### R3 — An empty result must say **why** it is empty, in a sentence, and must never be filled.

*Authority: `docs/HONESTY.md`; the existing precedent in `app/honesty.ts` — "a slot
nobody filled must look like a slot nobody filled — never like a reassuring green tick".*

The audit aggregates are empty because the demo API connects as the demo's own read
role, not as the Managed-MCP service account. **The payload already says so** — the
`unreachable[0].probe` field carries that sentence, and the screen throws it away.
Render it. Add nothing.

"No rows" becomes "No rows — *and here is the reason there are none, which is a fact
about this deployment and not about any record*". The row count stays zero.

### R4 — A cell in the honesty strip changes from `unknown` **only** by the check actually running. Never by a default, never by a screen assuming.

*Authority: `app/honesty.ts` docstring, D16.*

Four of the five `unknown`s are unknown because the work that would fill them is only
started by `GateSurfaceRoot`. Start it from the shell so it runs on every screen: the
transport knows its own mode and clock skew the instant it is built; the bundle digest
and the seal come from the verifier this console already ships and already tests.

Where a check genuinely **cannot** run, the cell says which nothing it is:
`.env.demo` ships `VITE_MAINLINE_LOG_VKEY` empty, so the checkpoint **signature** check
is a named SKIP and the seal is amber. It must read **`SKIPPED — this build carries no
log key`**, never `unknown`, and never green. `signature path: unknown` is a true fact
about the build (no GT-15 attestation exists) and **stays exactly as it is**; it gains a
plain gloss and nothing else.

**If a worker cannot make a cell true, the cell stays `unknown`. That is a pass, not a
failure.** Fabricating a filled cell is the one unforgivable move in this repository.

### R5 — The demo world is SYNTHETIC and every plain-language sentence drawn from it must carry that word.

*Authority: `demo_world.sql:13-28` — "Every row below is synthetic and corresponds to
nobody… free text opens with `SYNTHETIC —` … every JSONB payload carries
`"synthetic": true`". The live ancestry payload I fetched today returns
`attribution: "SYNTHETIC — the investigation names this clause as the control that
failed."`*

**This overrules the example sentence in my own brief.** The brief offers, as the model
plain-language opener:

> *"A worker was injured in 2024 because a control was missing…"*

Written that way it is an **unqualified claim about a real injury**, and the database it
is drawn from says in its own bytes that it corresponds to nobody. A console whose entire
argument is that it does not overstate cannot open with a fabricated casualty.

The admissible form keeps every ounce of the force and adds four words:

> **"This is a synthetic demonstration record.** In it, an isolation was signed off
> without being verified at zero, and stored energy was released during intrusive work.
> The rule written afterwards is the rule this permit relies on. The permit has one
> obligation still open against it, and the database refused to merge it."

Every clause of that is a field I can point at: `demo_world.sql:275-276` (the precursor
narrative, verbatim from the seed's own `SYNTHETIC —` prefix), the live ancestry
`blame_edges[0].attribution`, and `open_blocking: 1` off the permit read. **Rule: any
narrative sentence sourced from the demo seed opens with, or sits under, a persistent
SYNTHETIC marker.** Where the seed's own text already starts `SYNTHETIC —`, render it
verbatim and do not re-word it.

### R6 — PLAIN and FULL DETAIL are one shell control, carried in the address, and FULL is never the only place a fact lives.

*Authority: D7 and `app/router.ts` — this console is hash-routed so a screenshot is
reproducible from a link; `features/evidence/source.ts` — "a surface that shows nothing
must say which of the several possible nothings it is".*

- One control in the shell: **PLAIN** (default on arrival) / **FULL DETAIL**.
- State lives in the address as `?detail=full`, propagated across every nav link.
  **No `localStorage`** — the console must run from `file://`, and a screenshot must
  reproduce from its URL.
- **PLAIN never hides:** the refusal bar, the SQLSTATE, the constraint name, a provenance
  chip, a STAGED badge, a SYNTHETIC marker, or the honesty strip. Those are visible in
  both modes, always.
- **PLAIN collapses** (into a labelled, keyboard-reachable disclosure, never removes):
  predicates, digests, JSON pointers, SQL statements, byte/row caps, hash tables,
  witness tables, canonicalisation detail, the RFC citations.
- **FULL DETAIL is exactly today's screen** plus the plain band still at the top. A
  worker who cannot produce FULL DETAIL byte-identical in *substance* to what ships
  today has removed something and must put it back.
- Every disclosure summary names what is inside it in the reader's words —
  *"Show the exact check the database ran"* — never *"Details"*.

### R7 — Vocabulary. These are the words. One sentence each. Used identically on every screen.

*Authority: mine, as two-audience lead; the brief instructs me to rule on it.*
*Placement: `src/design/glossary.ts` is the single source; `docs/console/vocabulary.md`
is generated from it, the way `registers.doc.ts` and `contract.doc.ts` already work.*

**The product's own words** — these are what the console says in prose:

| word | the one sentence | the exact thing it names |
|---|---|---|
| **permit** | A written authorisation for one specific piece of work. | `mainline.permit` |
| **obligation** | Something that must be answered before the permit is allowed to take effect. | `mainline.blocking_check` |
| **refusal** | The database declining to make the change, and printing its own named reason for it. | a `23514`/`P0001` error |
| **signature** | One named person recording, under their own credential, how an obligation was answered. | `mainline.disposition` |
| **ancestry** | The trail from this rule back through the earlier events and edits it came from. | `clause_blame_closure` + `commit_chain` |
| **custody** | Proof that a record has not been altered since it was written down. | the ledger + checkpoint |
| **silence** | Everything the search looked at and decided not to show you — and the arithmetic for why. | `/v1/permits/{id}/silence` |
| **propagation** | Where else the same lesson was applied, and where it was not. | `/v1/lessons/{id}/propagation` |
| **synthetic** | Made up for this demonstration; corresponds to no real person, site or event. | the seed's own marker |

**Terms that stay and gain a first-use definition** — never replaced, always glossed:

| term | first-use gloss |
|---|---|
| `projection` / projected counter | A running total the database keeps in a column so a check can be instant instead of re-counting. |
| projection drift | When that running total stops matching what the rows actually say — by accident, or on purpose. |
| SQLSTATE | The five-character code the database prints to name what it refused. `23514` means a CHECK constraint was not satisfied. |
| constraint | A rule written into the table itself, so no query can get around it. |
| gate epoch | A version number for the set of obligations; it moves when they change, so an old signature cannot be reused across the change. |
| canonicalisation | Writing a record in one exact byte-for-byte form, so two different computers hashing it get the same answer. (RFC 8785) |
| inclusion proof | A short list of hashes that proves one entry really is in the log, without re-reading the log. (RFC 6962) |
| consistency proof | A short list of hashes that proves the log only ever grew, and no earlier entry was rewritten. |
| corpus root | The exact commit of the rule-book that this page's ancestry was worked out against. |
| clock skew | The server's clock minus this browser's. A screenshot's timestamp means nothing without it. |
| minimal unsatisfiable subset | The smallest set of reasons that is on its own enough to cause the refusal — take any one away and it would not refuse. |
| nearest admissible alternative | The smallest thing you could actually do that would make this allowed. |
| defeater | The named reason a person is permitted to give for an obligation. The list is fixed per obligation; there is deliberately no general "not applicable". |
| virulence / severity | How bad the underlying failure was, on the scale the record itself carries. |
| provenance chip | The little marker saying how the console came to believe the value beside it — read from a column, recomputed here, or never established. |
| STAGED | This value came from a fixture, not from the live database, and the badge is there so you never have to wonder. |
| transport | Where these bytes came from: LIVE (a database, just now) or REPLAY (a signed bundle, verified in this browser first). |
| seal | Whether this browser re-did the arithmetic over the signed bytes and got the same answer. |

**Two console-composed headings are overruled** because they are console jargon, not
kernel vocabulary, and nothing verbatim is lost:

- *"The weld"* → **"What the database checks before it will merge"**. The word "weld"
  survives in FULL DETAIL as the section's subtitle and in the source comments.
- *"Irreducible reason set"* → **"Why it refused — the smallest set of reasons"**, with
  `minimal unsatisfiable subset` glossed beside it. `mus` in the payload is untouched.

**Forbidden in any sentence a worker writes:** *seamless, powerful, robust, enterprise,
revolutionary, unlock, empower, leverage, effortless, trust us, simply, just*. The test
for every added sentence is: **can I point at the field it came from?** If not, delete it.

### R8 — The exact strings the kernel emits are never touched.

*Authority: D18, and the brief.*

Refusal `message`, `constraint`, `sqlstate`, `detail`, `naa.description`, `mus[].detail`,
`unreachable[].probe`, `attribution`, `statement`, `predicate` — every one is rendered
**verbatim**, in the mono face, through `Sqlstate.tsx` / `ConstraintName.tsx` /
`Mono.tsx` as it is today. A gloss goes **beside** it, never instead of it, never
inside the same element, and is visually distinguishable as console prose. No worker
adds a branch that picks a sentence based on a code — that is the exact discipline
`DemoDriver.tsx` documents about itself and it is not relaxed here.

`docs/HONESTY.md` and `docs/CI-STATE.md` are **not edited by anybody on this plan.**

### R9 — The two exceptional use cases, and where they live.

*Authority: the founder's second request. Choice of which two: mine.*

The founder asked for "a couple of exceptional use cases… and show those examples". The
two I select are the two this platform can *demonstrate live, against a real database,
in front of a judge*, and neither needs a word of invention:

1. **"The obvious tamper does not work."** — the gate. A permit with one open obligation
   is refused. Then the projected counter is forced to zero out of band, which is exactly
   what a disarmed projector or a careless `UPDATE` leaves behind, so the CHECK
   constraint is now satisfied and *would* admit the merge. **It is refused anyway**,
   because the function re-derives the count instead of trusting the column. Then one
   signature is recorded and it merges. Four beats, one `SERIALIZABLE` transaction,
   rolled back, `persisted: false` — measured today at 1689 ms. Owner: **W3**.
2. **"The system tells you what it did *not* tell you."** — silence and propagation.
   Every precursor the recall declined to surface, with its score, its threshold and the
   universe it was drawn from; and whether exhaustion could be certified at all. Beside
   it, which sibling sites took the control change and which did not. This is the case
   no competitor demonstrates, because it requires the product to volunteer its own
   negative space. Owner: **W6**.

Each is a plain-language walkthrough at the top of its screen, driven by the **real**
endpoint, degrading to a named absence if the endpoint does not answer. Neither is a
video, an animation, or a script. Both must be reproducible from a link.

### R10 — Budgets are a ceiling and this plan does not raise one.

*Authority: the brief's absolute prohibition; `budgets.json` `evidentiary-shell`
`max_gzip_bytes: 225280`, `required: true`.*

Copy costs bytes and this plan adds a lot of copy. **No worker edits `budgets.json`.**
The glossary and the two walkthroughs go in **lazy** chunks, not the evidentiary shell.
`DEFAULT_MAX_RESPONSE_BYTES` stays `136 * 1024`. `continue-on-error` and `|| true` stay
banned. Every worker runs `pnpm exec tsc --noEmit`, `pnpm exec eslint . --max-warnings 0`
and `pnpm exec vitest run` and reports the numbers against §0.5.

### R11 — Nobody deploys.

**NEVER `terraform apply`. Never redeploy. Never update the Lambda. Never touch AWS.
Never write the SSM parameter. Never print a DSN, a password or any credential. Do not
commit.** Build and verify locally against
`postgresql://root@localhost:26257/defaultdb?sslmode=disable`; the orchestrator deploys
and the orchestrator commits. This is repeated in all six worker briefs because it is the
rule most likely to be broken by a worker who has just made something work.

---

## 3. The six workers

Paths are literally enumerated and **disjoint**. No two workers write the same file.

**Ordering:** W1 lands first (everyone imports its kit). W2 lands second (W3–W6 read its
subject context). W3–W6 are then fully parallel. A worker blocked on a predecessor builds
against the interface named in its brief and does not reach into the predecessor's files.

| id | title | owns |
|---|---|---|
| **W1** | The plain-language kit | glossary, `PlainBand`, `Disclosure`, `Gloss`, detail-mode |
| **W2** | Subject discovery, end to end | `GET /v1/demo/subjects`, the console's subject context, the shell |
| **W3** | Gate — the headline, and use case 1 | `features/gate/**` |
| **W4** | Custody and Audit | `features/custody/**`, `features/audit/**` |
| **W5** | Diff and Evidence, and the bundle base URL | `features/diff/**`, `features/evidence/**`, `data/bundle.ts` |
| **W6** | Propagation, Silence, and the honesty strip — use case 2 | `features/propagation/**`, `features/silence/**`, `app/HonestyChrome.tsx` |

Full briefs are in the structured output that accompanies this plan; the path lists there
are normative.

---

## 4. Definition of done, for the plan as a whole

1. `#/gate`, `#/custody`, `#/diff`, `#/evidence`, `#/audit`, `#/propagation`, `#/silence`
   each render **content, not an error**, on cold arrival with no query string, against
   the live kernel — or a **named, plain-language absence** that says which nothing it is.
   No 404. No `Invalid base URL`. No bare "no subject addressed".
2. Every one of those seven opens with at most three sentences containing **none** of the
   twenty-one terms from §0.4 undefined, and every one of the twenty-one is reachable in
   one click and still exact.
3. Every SQLSTATE and constraint name on screen is verbatim **and** carries a gloss beside
   it, from `glossary.ts`.
4. The honesty strip's cells are either filled **by a check that ran**, or say which
   nothing they are. Zero cells changed by assumption.
5. Both use cases (R9) run from the live URL and are reproducible from a link.
6. No literal subject identifier remains anywhere under `apps/console/src/`. Grep is the
   test: `BLK-07`, `018f3a30`, `5f916282` return nothing outside history.
7. `tsc --noEmit` clean, `eslint --max-warnings 0` clean, vitest **no worse than §0.5**,
   demo-api suite no worse than 910 passed, budgets pass unchanged.
8. `docs/HONESTY.md`, `docs/CI-STATE.md`, `budgets.json`, `demo_world.sql`,
   `demo_permit.sql` and every migration are **unmodified**. `git status` proves it.

---

## 5. What I am explicitly NOT doing, and why

- **Not removing the `ancestry` and `disposition` nav links.** They are `declared-missing`
  and render a NOT-BUILT-YET card naming the milestone that owes them. That is the
  console keeping a promise visible rather than quietly dropping it, and it is a better
  answer to a judge than a shorter menu. W6 gives the card a plain first sentence; nobody
  deletes the promise.
- **Not touching `demo_world.sql` to make `BLK-07` exist.** §0.2, R1. The direction of fit
  is code-follows-seed.
- **Not filling the audit tables.** R3. The zero is true.
- **Not making the seal green.** R4. `VITE_MAINLINE_LOG_VKEY` is empty in this build and
  the honest word for that is SKIPPED.
- **Not writing marketing.** R7. Every sentence points at a field or it does not ship.
