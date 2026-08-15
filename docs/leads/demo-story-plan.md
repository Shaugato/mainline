<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# DEMO-STORY PLAN — the three minutes a stranger spends with MAINLINE

**Lead:** demo-story lead · **Date:** 2026-08-15 · **Baseline:** `master` @ `e88b8b6`
**Target:** <https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws>
**Workers:** exactly 6, disjoint paths, enumerated in §7.

---

## 0 · WHAT I MEASURED, AND WHERE THE BRIEF IS WRONG

I opened the live URL and walked every screen before decomposing. Everything below is a
reading, not a restatement of the brief. Where a reading contradicts the brief, the reading
wins and I say so.

### 0.1 The kernel

| probe | result |
|---|---|
| `GET /v1/health` | `ok=true`, `mainline_demo`, `CockroachDB CCL v26.2.5`, `deploy_chain 271/271`, `schema_fingerprint ec9b1ce7…`, warm `0.70 s` |
| `POST /v1/demo/gate-run` | `verdict PROVEN`, `persisted false`, `single_transaction true`, `elapsed_ms 1658.5`, `failures []`, all four `matched_expectation true` |

The four beats, verbatim from the payload:

| # | name | outcome | SQLSTATE | constraint | source | elapsed |
|---|---|---|---|---|---|---|
| 1 | `read` | `read` | `00000` | — | — | 0.013 ms |
| 2 | `merge` | **REFUSED** | `23514` | `gate_closed_when_issued` | **reported** | 513.15 ms |
| 3 | `projection_drift_attack` | **REFUSED** | `P0001` | `mainline.fn_permit_merge_gate` | *parsed* | 532.16 ms |
| 4 | `admit` | `admitted` | `00000` | — | — | 437.01 ms |

Beat 2 carries a full `refusal` object: `mus` = one obligation
(`dec0de00-0007-4000-8000-000000000001`, severity 4, `blood_major`, origin `blame_ancestry`,
detail *"open at gate_epoch 1; no live disposition"*) and `naa` =
`dispose_obligations`, cardinality 1, *"1 obligation(s) remain open on this subject;
disposing of exactly those restores admissibility"*, with five legal disposition kinds.
**None of that reaches the screen today.** That is finding §1.3.

### 0.2 Every seeded subject resolves. The console addresses almost none of them.

| resource | address that works | live status |
|---|---|---|
| permit `DEMO-PTW-0001` | `/v1/permits/dec0de00-0006-4000-8000-000000000001` | 200, 5691 B |
| blocking checks | `/v1/permits/…0006…/blocking-checks` | 200, 2408 B |
| disposition lattice | `/v1/checks/dec0de00-0007-4000-8000-000000000001/disposition` | 200, 3805 B |
| exposure receipt | `/v1/receipts/dec0de00-0008-4000-8000-000000000001` | 200, 1817 B |
| recall run | `/v1/recall-runs/dec0de00-0009-4000-8000-000000000001` | 200, 2223 B |
| silence | `/v1/permits/…0006…/silence` | 200, 2386 B |
| clause version | `/v1/clauses/dec0de00-0004-4000-8000-000000000001/versions/9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39` | 200, 3230 B |
| clause ancestry | `/v1/clauses/…0004…/ancestry` | 200, 3744 B |
| ledger / custody | `/v1/ledger?site_code=dec0de00-0001-4000-8000-000000000001` | 200, 10751 B |
| change request `DEMO-MOC-0001` | `/v1/change-requests/dec0de00-000c-4000-8000-000000000001` | 200, 3295 B |
| propagation (STAGED) | `/v1/lessons/dec0de00-0005-4000-8000-000000000001/propagation` | 200, 4041 B |
| audit | `/v1/audit` | 200, 19439 B |
| evidence bundle | `/bundle/manifest.json` | **200, 8435 B** |

**Not one 404 in the list.** The demo world is complete and reachable. Every broken screen
is a screen asking for something else.

The invented identifiers, located exactly:

* `src/features/custody/CustodyScreen.tsx:48` — `export const DEFAULT_SITE_CODE = 'BLK-07';`
  The seeded `site_code` is `dec0de00-0001-4000-8000-000000000001` (it equals `site_id::STRING`
  by `fn_recall_policy_anchored`, and `demo_world.sql:56-60` says so).
* `src/features/diff/ClauseDiffScreen.tsx:55-56` — `018f3a30-2200-7d10-9f31-0c9a4e77bb02` and
  `5f916282a2a3e576…`. Neither exists in any seed.
* `src/app/router.ts:36` — `DEFAULT_PATH = '/gate'`. A judge who opens the bare URL lands on
  the one screen that, correctly and by design, refuses to choose a subject.
* **The navigation itself is unaddressed.** Measured hrefs: `#/gate`, `#/ancestry`,
  `#/disposition`, `#/custody`, `#/audit`, `#/propagation`, `#/silence`, `#/diff`,
  `#/evidence` — nine bare paths, no query string on any of them. Five of the nine cannot
  render without one.

### 0.3 Four corrections to the brief

**(a) Audit is NOT empty.** Measured on the live page: *"views carried **14**"*, observed at
`2026-08-14T22:31:43Z`. Six of the fourteen carry rows — `v_blame_coverage` (1),
`v_cbm_ledger` (1), `v_disposition_coverage` (1), `v_ledger_health` (1),
`v_open_gate_summary` (1), `v_recall_conservation` (1). The other eight are genuinely empty
and honestly so. The screenshot caught one of two things: the load state, which literally
prints *"views carried 0"* for ~2 s, or the **first** view in alphabetical order,
`mainline_audit.v_agent_actions`, which is empty because no MCP agent has called this
deployment. **Nobody invents an agent-call row.** The fix is ordering and a lead line, and
it is small. This is the cheapest of the seven screens and must not be over-invested in.

**(b) Gate, Custody, Diff, Silence, Propagation are not broken — they are unaddressed.**
`#/gate?permit=dec0de00-0006-4000-8000-000000000001` renders in full today: the permit row,
seven projected counters each welded to the CHECK that reads it, the obligation with its
severity-4 `blood_major` band, the 2019 precursor `DEMO-INC-0001`, the clause text, the
canon SHA-256, the anchor set, the CAT comparison. It is a strong screen behind a missing
query string.

**(c) CORPUS ROOT and CLOCK SKEW are not unset.** With the permit addressed the strip reads
`CORPUS ROOT 49b22526023f4932c8dbd8cd2df1bc22e612cf8ddf40768d84b9e07d09498983` (`db:column`)
and `CLOCK SKEW +11 ms` (`recomputed`). They were blank in the screenshot *because the screen
had no subject*. Fixing addressing fixes two of the five strip slots for free.

**(d) The honesty strip's remaining three slots are correct and read as failure.** `BUNDLE
unknown`, `SEAL NOT VERIFIED`, `SIGNATURE PATH unknown` are **true** under LIVE: no bundle is
being read, so nothing has been verified. This is the console's own doctrine —
*"a surface that shows nothing must say which of the several possible nothings it is"*
(`features/evidence/source.ts`) — applied to every slot except its own chrome.

### 0.4 Two defects I found that the brief does not mention

**(i) The refusal does not land where the screen promises it will.** I pressed MERGE on the
live console. The driver panel showed `beat 2 · merge · REFUSED · SQLSTATE 23514 ·
gate_closed_when_issued`. Simultaneously, further down the same page, the screen's own
refusal band still read **`NO ATTEMPT — NOTHING HAS BEEN REFUSED`** and the *Irreducible
reason set* read **`NO REASON SET`**. The product's entire argument had just happened and the
component built to display it said nothing had happened. This is the single highest-value fix
in this plan.

**(ii) Custody's four red checks have exactly two root causes, and one is a stale cloud row.**
Live custody at the seeded site reports `5 passed / 4 failed / 6 not run` and a headline
`verification FAILED`. Decomposed:

* `check 2 inclusion_proof` — **one** disagreeing row: `leaf 0 of 1`, 32 bytes, recomputes
  `032980be3a0d1fb7…`, payload carries `74f0845f11c5992b…`. Every size-2 and size-4 path
  **agrees**.
* `check 3 consistency_proof_every_pair` — `1→2` disagrees for the same reason; `2→4` agrees.
* `check 4 log_signature` — *"a checkpoint note has no empty line, so it has no signature
  section"*. The seeded note is `mainline/<site>\n<size>\n<root>\n` with no signature block.
* `check 10 canonicaliser_identity` — to be attributed by W6; not yet decomposed.

The tree_size-1 checkpoint is **superseded seed state still resident in the cloud**.
`demo_world.sql:392` says it in its own words: *"Until 2026-08-14 this section seeded ONE
checkpoint, `tree_size = 1`, with a `root_hash` of …"*. The current file seeds `tree_size = 2`
and `tree_size = 4` only, reading both roots back out of `mainline.ledger_node`. The seed is
`ON CONFLICT DO NOTHING` / `WHERE NOT EXISTS` throughout and **never deletes**, so the old row
and its cosignature survived the re-seed. `74f0845f…` appears nowhere in the current tree
except `docs/diagnosis/divergence-02-derived-digests.md:104`, which records it as the
superseded value. Checks 2 and 3 are the verifier working perfectly on a row that should not
be there.

---

## 1 · RULINGS

Each ruling names its authority. A worker who wants to depart from one escalates to me; a
worker who departs silently has their change reverted.

**R1 · The second use case is ADMITTED as data and REFUSED as a driven demo.**
`DEMO-MOC-0001` (`dec0de00-000c-4000-8000-000000000001`) is real: state
`checks_materialised`, `open_blocking = 1`, `gate_epoch 1`, four named CHECK constraints
including `cr_gate_closed_when_merged`, `cr_clause` foreign-keyed to the exact
`(clause_uuid, commit_id)` pair the permit relies on, and its own three-option defeater
vocabulary (`CONTROL_PRESERVED_BY_EDIT`, `EDIT_OUTSIDE_BLAMED_ANCHOR`,
`PRECURSOR_ANSWERED_ELSEWHERE`). **But `app.py:210-229` declares no
`POST /v1/change-requests/{id}/merge`.** It cannot be pressed. Use case 2 is therefore told
from the read payload and the seeded rows, and *the absence of a merge route is stated in the
use-case document as a limit*. Nobody stages a route. *Authority: measured route table +
measured 200 payload.*

**R2 · The default landing must be an addressed screen; the Gate keeps its rule.**
`router.ts:36` sends the first fifteen seconds to `NO SUBJECT ADDRESSED`. The fix is **not**
to give Gate a default permit — *"this surface renders the gate of ONE subject and does not
choose one for you"* is a correct rule and stays. A new `/start` surface becomes
`DEFAULT_PATH`, and every navigation link becomes an **addressed deep link**. *Authority: D8
in `docs/leads/ui.md:161` makes a new surface one file; the Gate's own doctrine makes the
alternative wrong.*

**R3 · Invented identifiers are replaced by seeded ones in ONE module, welded to the seed in
the safe direction.** A single `src/app/demo-subjects.ts` holds every id the console
addresses. Its test reads `verticals/mainline/db/seeds/demo/*.sql` and fails if any constant
is absent from the seed. **The direction is fixed and non-negotiable: the CONSTANT is checked
against the SEED. Never the reverse.** A worker who edits a seed file to make a constant agree
is reverted on sight — that exact act was caught and reverted in this repository once already.
*Authority: the brief's own prohibition; `demo_world.sql` §10's identical discipline.*

**R4 · Audit gets ordering and a lead line, and nothing else.** Views that carry rows lead;
the header states *n of 14 views carried rows*. `v_agent_actions` stays empty and stays
visible with its existing sentence. **No agent-call row is invented, no view is hidden.**
*Authority: measured — 14 carried, 6 populated.*

**R5 · Custody's red is real, is named, and is fixed at the row — never at the check.**
No verifier check is weakened, skipped, or exempted. No signature is forged. W6 reproduces
the tree_size-1 failure on the local cluster, writes `reconcile_demo_checkpoints.sql` that
**deletes the superseded checkpoint and its cosignature** (rows the current seed does not
produce), and writes a verifier script that proves 2 and 3 turn green. **W6 does not apply it
to AWS.** The orchestrator applies. Until it is applied, the Custody screen must name *which*
checkpoint failed and why, rather than showing a bare `verification FAILED`.
Check 4 (`log_signature`) is a true fact about a synthetic corpus and is **stated, not
fixed** — `DEMO-HONESTY.md` §3 STAGED is where it belongs. *Authority: `demo_world.sql:392`;
measured per-check details.*

**R6 · The honesty strip names which nothing, and never shows a tick with nothing behind it.**
Under LIVE, `BUNDLE` / `SEAL` / `SIGNATURE PATH` say that no bundle is being read and that
REPLAY is one control away — the fact, not a green tick and not a bare `unknown`. Separately,
`TRANSPORT LIVE` currently carries the provenance chip **`staged`**, which is a false label on
a true value; it must carry what actually establishes it. *Authority: measured strip;
`features/evidence/source.ts`'s own doctrine.*

**R7 · The refusal lands in the screen's refusal bar, with its MUS and its NAA.** After a
gate-run refusal, `RefusalBar` shows the constraint, the SQLSTATE and the
`constraint_source`; `ReasonSet` shows the payload's `mus`; and the `naa` — *"disposing of
exactly those restores admissibility"* — is rendered, because it is the answer to the only
question a judge has after a refusal. The un-pressed `NO ATTEMPT` state is preserved exactly
and must remain reachable. `constraint_source: 'parsed'` continues to render as a weakened
diagnosis; a parsed exhibit must never look like a reported one. *Authority: measured
disconnection; `DemoDriver.tsx` header, D18.*

**R8 · The evidence bundle URL is a real bug with a real bundle behind it.**
`FetchBundleSource` does `new URL(path, './bundle/')`, which throws
`Failed to construct 'URL': Invalid base URL`. `/bundle/manifest.json` returns 200 / 8435 B.
The relative location is resolved against `document.baseURI` **at both call sites** —
`features/evidence/source.ts` (W5) and `app/composition.tsx` (W6) — and `data/bundle.ts` is
not touched, because it is shared and neither worker owns it. *Authority: measured 200 on the
bundle; measured console error.*

**R9 · The on-ramp is ADDITIVE. Nothing precise is deleted or softened.** Every screen gains a
lead — one short paragraph in plain language, above the fold — and every existing sentence
stays, below it. The RFC 8785 / RFC 6962 / ECDSA paragraph does not move away, it moves
*down*. **If a rewrite makes a claim vaguer, weaker, or less checkable, it is wrong and is
reverted.** The test: a reader who knows nothing understands the first paragraph; a reader who
knows everything finds nothing missing further down. *Authority: the founder's words in the
brief.*

**R10 · No invention, anywhere.** No fabricated row, no hard-coded tick, no faked seal, no
constant that merely looks like a hash. A screen with no subject says so and links to the
subjects that exist.

**R11 · The gate reveal is presentation over one completed transaction, and says so.**
The four beats arrive together in one already-rolled-back SERIALIZABLE transaction. Revealing
them in order is a *reading aid*, and the panel states that in one sentence. The per-beat
`elapsed_ms` shown is the **payload's own** number, never the reveal delay. *Authority: the
screen already states the constraint honestly; the brief says work with it.*

**R12 · The gate surface is the EVIDENCE register and the reveal must respect it.**
`docs/leads/ui.md:60`: mono for anything the database emitted, **no easing over 160 ms**, no
`motion`, no `@react-three/*`, *"nothing moves that a screenshot could not reproduce."*
Therefore: CSS-only reveal, each step ≤ 160 ms, `prefers-reduced-motion` renders all four beats
at once, and the resting state after the sequence is the complete panel — a screenshot taken
at any moment is a truthful screenshot. *Authority: `ui.md` §1.1, CI-enforced import boundary.*

---

## 2 · USE CASE ONE — the one the seed already tells

**Working title: "The permit that could not merge, because a 2019 incident is still unanswered."**

Every id below returned 200 from the live URL today.

A crew wants to do intrusive work. The permit is `DEMO-PTW-0001`
(`dec0de00-0006-4000-8000-000000000001`), ref `refs/permits/demo-0001`, state
`dispositioned`, `gate_epoch 1`. It relies on one clause: `DEMO-SOP-0001 §7.3.2(b)`
(`dec0de00-0004-4000-8000-000000000001` at commit `9f12114dc1a94f43…`), whose text is
*"Before any intrusive work, stored energy shall be isolated, locked and verified at zero by a
competent person."*

In March 2019 there was an incident: `DEMO-INC-0001`, *stored energy release during intrusive
work*, human-rated severity **4**, source document `demo/incident-0001.pdf`,
SHA-256 `1f84f023f5f891fa…`. The investigation named that clause as the control that failed.
That naming is a `blame_edge` row and a `clause_blame_closure` row — a foreign key, not a
sentence in a report.

So when this permit was opened, the closure armed an obligation against it:
`dec0de00-0007-4000-8000-000000000001`, origin `blame_ancestry`, severity **4**, virulence
`blood_major`, `closure_gen 0`. **Nobody chose those numbers** — `fn_check_project` projected
them from `clause_blame_current`.

Press **MERGE**. The database refuses: `23514`, `gate_closed_when_issued`,
`CHECK ((state != 'merged') OR (open_blocking = 0))`. The refusal is *reported* by the driver,
not parsed out of a message. The minimal unsatisfiable subset is one row: that obligation,
open at `gate_epoch 1`, no live disposition. And the payload says what would fix it:
*dispose exactly those obligations* — one of `applied`, `mitigated`, `mechanism_absent`,
`escalated`, `emergency_override`.

Now the part that is actually rare. Suppose somebody disarms the projector, or runs a careless
`UPDATE mainline.permit SET open_blocking = 0`. The CHECK constraint is now satisfied. Press
**FORGE THE COUNTER AND MERGE**. It is refused **anyway**: `P0001`,
`mainline.fn_permit_merge_gate` — *"re-derived open obligation count is 1 while the projected
counter reads zero."* The gate does not trust the column it is guarding. It recounts.

Finally, sign a disposition. The signer is shown three defeaters and must pick one; the
disposition pins the SHA-256 of the vocabulary they were shown, so *"nobody told me those were
my options"* is a checkable claim. **SIGN A DISPOSITION AND MERGE** → `00000`, admitted, with a
server-computed `clearance_digest 41b9249ac28ce0bb…` and a `merge_record`. A gate that always
refuses is broken, not safe.

Then the whole thing is rolled back, and the payload proves it rather than claiming it: the
minted `disposition_id` is a uuid4 no other writer holds, and it is gone; the permit row is
byte-identical; the subject's own row counts are unchanged.

**The one-sentence version, for the top of the screen:** *A 2019 fatality-class incident blamed
a clause. Today's permit relies on that clause. The database will not let it merge — and it
will not be talked out of it by editing the counter.*

## 3 · USE CASE TWO — the same blame, one subject over (R1)

**Working title: "The edit that inherits the same debt."**

`DEMO-MOC-0001` (`dec0de00-000c-4000-8000-000000000001`) is a management-of-change request
against `refs/heads/main`. It proposes to **edit the very clause version the permit relies
on** — `cr_clause` names `(dec0de00-0004-…, 9f12114d…)` with relation `edits`, as a foreign
key. Because it touches the clause the 2019 incident reaches, *the same closure arms an
obligation against it*: `dec0de00-000d-4000-8000-000000000001`, projected to severity 4,
`blood_major`.

Live payload, measured: `state checks_materialised`, `open_blocking 1`, `open_conflicts 0`,
`open_residue 0`, and the constraint that would refuse it by name —
`cr_gate_closed_when_merged CHECK ((state != 'merged') OR (open_blocking = 0))`.

Its defeaters are **different from the permit's, and that is 0064 working**: a code is unique
within a check and meaningless outside it. The permit's obligation asks about a *job*
(`WORK_NOT_INTRUSIVE`). This one asks about an *edit*: does the proposed text still require the
control the precursor's blame reaches; does it touch the blamed anchor at all; is the
precursor's finding already answered by a different clause version.

**The point:** the obligation is not attached to a document workflow. It is attached to the
*clause*, and it follows the clause into every subject that touches it — a permit to do work,
and a proposal to change the rule. Two gated subjects, one repository, one debt.

**The honest limits, stated on the screen and in the document (R1):**
1. There is **no** `POST /v1/change-requests/{id}/merge`. This subject can be read and its gate
   inspected; it cannot be pressed. Nothing is staged to make it pressable.
2. The console has **no change-request surface**. Use case 2 is told through the Diff screen
   (the clause version it proposes to edit) and the read payload. That is a limit of the
   console, not of the kernel, and it is written down rather than hidden.

## 4 · WHAT IS NOT A USE CASE (say so, do not stage it)

* **Propagation.** `/v1/lessons/…/propagation` returns 200 with a lesson, a fleet response and
  an open conflict — but the identifiers are `_staged_uuid` / `_staged_digest` derivations and
  the envelope flags them. It is reachable, it is honestly badged STAGED, and it is **not** a
  use case. It may be *linked* from `/start` under a STAGED label. It may not be narrated.
* **The MCP agent surface.** `v_agent_actions` is empty and `mainline_qa` reports
  `not_probed`. No agent has called this deployment. This is a capability the platform has and
  the demo does not exercise. Say that; do not populate it.
* **Split-view resistance.** The custody screen already states the limit itself: *"Until an
  adverse witness runs the cosigning service the quorum is q=1 and split-view resistance is NOT
  claimed."* That sentence stays exactly as written.

## 5 · THE FIRST FIFTEEN SECONDS

What a judge sees on `https://…lambda-url…/` with no hash, after this plan lands:

1. **Second 0-3.** The `/start` screen. One headline: what this refuses and why that is hard.
   One line of orientation: *two gated subjects, one incident, one database that recounts.*
   The honesty strip above it already reads `TRANSPORT LIVE` and `BUILD b822fdc`.
2. **Second 3-6.** One primary control, unmissable: **RUN THE GATE** → `#/gate?permit=dec0de00-0006-4000-8000-000000000001`
   with the driver focused and RUN ALL primed.
3. **Second 6-15.** They press it. Four beats resolve in order. Beat 2 lands as a refusal —
   loud, in the screen's own refusal band, with `23514` and `gate_closed_when_issued` and the
   one obligation that caused it. Beat 3 lands as the *same* refusal after the counter was
   forged. Beat 4 admits.
4. **After.** Three addressed follow-on links, each one already known to return 200:
   *"where the blame comes from"* (Diff), *"what the log can prove"* (Custody),
   *"what the recall did not show you"* (Silence).

**What they press first:** RUN ALL. Not MERGE. RUN ALL tells the whole argument — refuse,
refuse under attack, admit on a signature — in one exchange, which is what the transaction
discipline already forces and therefore what the story should embrace.

## 6 · THE TWO READERS (R9)

Every screen carries two layers in one column, never a toggle that hides a claim:

* **The lead** — plain language, no acronym before it is earned, above the fold. *"The database
  refused this merge. Here is the one unanswered thing that caused it."*
* **The exhibit** — everything that is there today, verbatim, unmoved in meaning: SQLSTATE,
  constraint predicate, provenance chip, canon digest, the RFC citations, the recomputation
  tables.

A "SHOW THE ARITHMETIC" affordance may collapse an exhibit **only** if the collapsed state
still names what is inside it and the expanded state is the print/screenshot default. Nothing
that is currently visible may become unreachable.

---

## 7 · THE SIX WORKERS — disjoint paths

All paths relative to `D:/CoackroachDBxAWS/mainline/`. No path appears under two workers.

| id | title | owns |
|---|---|---|
| W1 | use-case authorship | `verticals/mainline/demo/USE-CASES.md`, `verticals/mainline/demo/FIRST-RUN.md`, `docs/decisions/demo-use-cases.md` |
| W2 | first run, routing, nav, subject registry | `src/app/router.ts`, `src/app/App.tsx`, `src/app/surfaces.ts`, `src/app/shell.module.css`, `src/app/demo-subjects.ts`, `src/features/start/**` + their tests |
| W3 | the gate run becomes watchable | `src/features/gate/DemoDriver.tsx`, `demo-driver.module.css`, `beats.ts`, `last-run.ts`, `GateSurfaceRoot.tsx` + their tests |
| W4 | the refusal lands in the refusal bar | `src/features/gate/GateScreen.tsx`, `RefusalBar.tsx`, `ReasonSet.tsx`, `gate.module.css`, `refusal-from-run.ts` + their tests |
| W5 | the four unaddressed screens | `src/features/custody/**`, `src/features/diff/**`, `src/features/evidence/**`, `src/features/silence/**`, `src/features/propagation/**` |
| W6 | trust indicators + the stale checkpoint | `src/app/HonestyChrome.tsx`, `chrome.module.css`, `honesty.ts`, `composition.tsx`, `src/features/audit/**`, `scripts/deploy/reconcile_demo_checkpoints.sql`, `scripts/deploy/verify_demo_checkpoints.py`, `docs/decisions/custody-stale-checkpoint.md` |

`src/…` above means `verticals/mainline/apps/console/src/…`.

### 7.1 The two cross-worker contracts I am fixing here, so nobody negotiates them

**Contract A — `src/app/demo-subjects.ts` (W2 writes it; W2/W3/W4/W5 import it).**

```ts
export const DEMO_SITE_CODE   = 'dec0de00-0001-4000-8000-000000000001';
export const DEMO_PERMIT_ID   = 'dec0de00-0006-4000-8000-000000000001';
export const DEMO_CHECK_ID    = 'dec0de00-0007-4000-8000-000000000001';
export const DEMO_RECEIPT_ID  = 'dec0de00-0008-4000-8000-000000000001';
export const DEMO_RECALL_RUN  = 'dec0de00-0009-4000-8000-000000000001';
export const DEMO_CLAUSE_UUID = 'dec0de00-0004-4000-8000-000000000001';
export const DEMO_COMMIT_HEX  = '9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39';
export const DEMO_LESSON_ID   = 'dec0de00-0005-4000-8000-000000000001';   // STAGED payload
export const DEMO_CR_ID       = 'dec0de00-000c-4000-8000-000000000001';   // read-only, no merge route
```

Nobody redeclares any of these. Nobody adds one without adding its seed assertion (R3).

**Contract B — `src/features/gate/last-run.ts` (W3 writes it; W4 consumes it).**
A React context publishing the last completed gate-run payload, or `null` before any press.
W3 publishes; W4 subscribes and adapts via its own `refusal-from-run.ts`. Neither worker edits
the other's file. `null` must keep W4's `NO ATTEMPT` state exactly as it renders today.

### 7.2 Rules repeated in every brief

Every worker brief repeats, verbatim: **no invention**, **no deploy**, **no seed edited to
match a constant**, **no floor lowered**, **no `|| true` / `continue-on-error`**, **no commit**.

---

## 8 · DONE

The demo is done when a stranger who has never heard of MAINLINE opens the bare URL, presses
one control within fifteen seconds, watches a database refuse a merge twice — once on ancestry,
once under a forged counter — admit it on a signature, and can then click through to the blame
that caused it and the log that can prove it, **without typing a UUID and without meeting a
404 or an unnamed red tick.** Every number they see is one the database emitted. Nothing on
the path was invented to make it work.
