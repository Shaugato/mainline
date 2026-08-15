<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# operator-systems-plan — the software the people in the story actually use

**Lead:** operator-systems · **Date:** 2026-08-15 · **Repo HEAD:** `4af05e1`
**Status:** DECISIONS. Everything under §2 is a ruling, not a suggestion. Workers implement §4.

---

## 0 · The one paragraph

We are building **two operator screens** — a permit-to-work screen a site supervisor works
in, and a management-of-change screen a safety engineer works in — as a **second entry point
in the console's Vite build**, written in **vanilla TypeScript with no framework and no
import from the existing console**, served from **the same origin as the API**, so that every
action is a real same-origin HTTP request and every SQLSTATE on screen is one the database
produced. MAINLINE is not branded anywhere on these screens. You see MAINLINE by seeing what
it stops.

---

## 1 · WHAT WAS MEASURED BEFORE ANY OF THIS WAS DECIDED

Read the bytes, not the summary. Each of these changed a decision.

| # | measurement | file / source | consequence |
|---|---|---|---|
| M1 | **There is deliberately no CORS block on the Function URL** | `infra/modules/demo-api/main.tf:434-447` | A page not served by that origin **cannot read** its answers. The operator app must be served BY the origin. Settles the whole architecture. |
| M2 | Entry chunk **138,156 B gzipped** against a **139,264 B** wire ceiling; **1,108 B** headroom; `_MINIMUM_HEADROOM_BYTES = 1024` fails CI | `docs/STATE-OF-THE-BUILD.md:230-235`, r2-memory §4.6 | The operator surface may add **zero bytes** to the existing entry closure. Separate entry, no shared imports. |
| M3 | `budgets.json` `evidentiary-shell` uses `root: "entry"`, which seeds **every** `isEntry` chunk | `verticals/mainline/apps/console/budgets.json:9`, `scripts/check-budgets.ts:113-122` | A second entry silently joins the 220 KB shell budget. Must be split (see R6). |
| M4 | The lazy-boundary check separately re-seeds from `'entry'` and bans `three` / `@react-three` | `scripts/check-budgets.ts:246-281` | That ban **automatically extends** to the operator entry. Keep it; do not narrow it. |
| M5 | `static_site` serves any file under `web/`; misses under `assets/` are 404, everything else falls back to `index.html` | `static_site.py:1004-1019`, `ASSET_PREFIXES` | `dist/operator.html` → `web/operator.html` → served at `/operator.html`. No handler change needed. `/operator` (no extension) would serve the **console**, so the URL is the one with the extension. |
| M6 | The packer copies the whole `dist/` to `web/`, requires `web/index.html`, and scans **every** `assets/*.js` for `VITE_*` literals | `scripts/deploy/build_lambda.sh:477-505, 761-830, 1328-1334` | No packer change needed. But its `STALE CONSOLE` asset-reference check reads **only `index.html`** — a gap we close console-side (R7). |
| M7 | `claim_hygiene.py` already globs `verticals/mainline/demo/operator/*.md`, and the directory **does not exist** | `scripts/demo/claim_hygiene.py:60` | The intended home for operator copy is already declared and currently reported ABSENT. W8 fills it, which puts every sentence we intend to speak under the existing scanner. |
| M8 | `POST /v1/permits/{id}/merge` on the seeded subject → **423 Locked**, `use_instead: POST /v1/demo/gate-run` | `docs/deploy/gate-run-contract.md` §7, r3 §5.5, r4 | The ISSUE button calls `/v1/demo/gate-run`. A 423 is the demo protecting itself, not a gate refusal. |
| M9 | `GET /v1/demo/subjects` returns `site_id, site_code, permit_id, cr_id, check_id, receipt_id, clause_uuid, commit_id, run_id, lesson_id` + `subjects{}` + `absent[]` | `subjects.py:489-500`, `contracts/subjects.schema.json` | Nothing is hardcoded. The screens address what the kernel tells them to address. |
| M10 | **No route lists a change request's blocking checks.** `GET /v1/change-requests/{cr_id}/blocking-checks` and `POST /v1/change-requests/{cr_id}/merge` are both absent from `ROUTES` | `app.py:229-252` | Screen two cannot reach its obligation from any read, and cannot drive a merge. Ruled at R11. |
| M11 | `gate-run` payload carries per-beat `sqlstate`, `constraint`, `constraint_source`, `message`, `matched_expectation`, `elapsed_ms`, `statement`, `refusal`, `observed`; run carries `verdict`, `persisted`, `persistence_check`, `transaction.single_transaction` | `contracts/gate-run.schema.json` `$defs` | Every number on screen has a field name. No number is composed by the client. |
| M12 | Node 24.14.0 and pnpm 11.5.3 are on PATH; CockroachDB is listening on `localhost:26257`; `scripts/deploy/local_furl.py` runs the **real handler** in-process and stamps `X-Mainline-Emulator: local_furl` on every response | measured this session; `local_furl.py:26-44` | We can build, run and film-rehearse a same-origin operator page against a real kernel **without touching AWS**, and a local capture can never be mistaken for the deployed one. |

---

## 2 · RULINGS — every open question, decided, with the authority named

**R1 — The operator app is a SECOND VITE ENTRY POINT, vanilla TypeScript, zero framework.**
`operator.html` beside `index.html`; `src/operator/**` imports **no** React, **no** module from
`src/app`, `src/design`, `src/features`, `src/verify`, and **no** runtime value from `src/data`.
Type-only imports from `src/data/types.generated.ts` are permitted because types erase to zero
bytes. *Authority:* M2 (the 1,108-byte headroom is the hardest constraint in the repository
right now), r2-memory §4.6 which recommends exactly this, and the founder's point that this is a
**different product's** UI — sharing the MAINLINE design system would defeat the demo.

**R2 — The invariant that proves R1 held: `dist/assets/index-*.js` must be byte-identical
before and after.** W1 builds twice and compares sha256. If the index chunk moves by one byte,
the work stops and the orchestrator is told. *Authority:* M2; `.env.demo` records that a
one-byte move is a thing this repo measures and cares about.

**R3 — The screens are served from the origin, and they name that origin on screen.**
No absolute URL is compiled in. Every request is `new URL('/v1/...', location.origin)`. The
page renders the origin it was actually loaded from, plus `X-Mainline-Emulator` when present,
in a persistent strip. *Authority:* M1 (no CORS makes any other shape non-functional), M12
(the emulator header exists precisely so a local capture cannot be passed off as the deployed
one). **Consequence recorded for the orchestrator:** the operator surface is *always* a live
client of its origin, so a package built `--console-transport replay` would ship a live page
beside a replay console. W8 writes this up; the orchestrator decides.

**R4 — The ISSUE button calls `POST /v1/demo/gate-run`. It never calls
`POST /v1/permits/{id}/merge`.** This sentence goes in the source file as a comment.
*Authority:* M8, r3 §5.5 ("the single most likely wrong turn available to a builder").

**R5 — One press, progressive disclosure — WITH the disclosure line, which is not optional.**
One real POST returns all four beats. The screen reveals them in order under operator
controls, and carries a permanent line: `one request · four beats · POST /v1/demo/gate-run ·
run_id <id> · response received <ISO> · <n> bytes`. Every per-beat duration rendered is the
payload's own `elapsed_ms`. There is **no `setTimeout`, no artificial delay, no skeleton that
pretends to be work.** The pending state is driven by the real promise and shows a real
elapsed clock. *Authority:* r3 §6.4 recommendation (a) + mandatory mitigation; r4's ruling that
without that sentence the reveal is faked latency; r5-craft §5.3.

**R6 — `budgets.json` is SPLIT, never widened.** `evidentiary-shell` changes `root: "entry"` →
`root: "index.html"` (the manifest key), and a new **required** budget `operator-surface` is
added with `root: "operator.html"`, `follow: "static"`, `subtract` unset. The lazy-boundary
check at `check-budgets.ts:246` continues to seed from `'entry'` and therefore still bans
`three` / `@react-three` from **both** entries. Net effect: two gates where there was one, each
addressable, and nothing is exempted. *Authority:* M3, M4. A budget that silently covers a new
subject is a budget that fails for a reason nobody chose; splitting it is the non-weakening
move and it is recorded here so no reviewer reads it as a narrowing.

**R7 — A new console-side gate, `scripts/check-entrypoints.ts`, runs in `pnpm run ci`.**
It asserts that every `dist/*.html` exists, that every `./assets/...` reference inside each of
them resolves to a real file, and that the operator entry's sourcemap `sources` contains no
`node_modules/react` module. This closes M6's gap **without touching `scripts/deploy/**`.**
*Authority:* M6; the existing `modulesInChunk()` technique in `check-budgets.ts:168-180` is the
idiom being reused.

**R8 — NO WORKER EDITS DEPLOY-OWNED OR KERNEL-OWNED FILES.** Off limits to all eight workers:
`scripts/deploy/**`, `infra/**`, `verticals/mainline/apps/demo-api/**`, `tests/deploy/**`,
`docs/HONESTY.md`, `docs/CI-STATE.md`, `docs/regression/**`, any ratchet or assertion, and
`DEFAULT_MAX_RESPONSE_BYTES`. If a measurement constant needs re-recording because `dist/` grew
(`_LARGEST_WEB_OBJECT`, the `web/` totals), W8 **measures it and writes the number down for the
orchestrator**; nobody edits it. *Authority:* the brief's absolute prohibitions; R10 in
`docs/STATE-OF-THE-BUILD.md` §2.2 on which side of a ratchet is allowed to follow which.

**R9 — Fields with no column are typed by a human on camera, or they are labelled empty.**
Figure 1 elements **1 (permit title), 3 (job location free text), 5 (description of work)** are
**visible `<input>`/`<textarea>` elements** with a caret, a placeholder, no provenance chip, and
they are never echoed back as server data. Element **8 (PPE)** renders greyed with the words
*"not carried by this deployment"*. Element **11 (extension)** is omitted. Elements **12–13**
render as **unsigned** rows. Hard-coding a plausible job description, plant name, crew or PPE
list is **forbidden** and is the same class of act as reshaping a seed to match a constant.
*Authority:* r3 §5.3, which is the honesty ledger and is binding.

**R10 — Do not translate the state enum, and do not paraphrase the seeded strings.**
The chip reads `dispositioned` verbatim (a real value of `mainline.subject_state`), with a
gloss available on demand. The clause text, the defeater prompts and the anchors render exactly
as the database returned them. *Authority:* r3 §4 and §6.2.

**R11 — Screen two shows the change request it can actually read, and NAMES what it cannot.**
No route in `ROUTES` yields the change request's blocking-check id (M10), and taking that id
from a document would be a hardcoded literal of exactly the kind `subjects.py:24-27` argues
against. So screen two renders: the real `change_request` payload (`external_ref`, `ref_name →
target_ref`, `state`, `head_seq`, `gate_epoch`, `counters.open_blocking = 1`, `constraints[4]`
with their predicates), the IChemE ribbon with our enum in a chip beside it (never *as* it), the
OSHA five headings, and an **approve control rendered disabled with the obligation named as the
reason**. Beside it, the **404 route table** the deployment itself returns, as the evidence for
the absence. If, and only if, a check id is obtained from a live read, the three CR defeater
prompts render from `GET /v1/checks/{id}/disposition`. **A hardcoded `dec0de00-000d-…` is
forbidden.** *Authority:* M10, r3 §5.4/§7.4, `docs/decisions/demo-use-cases.md` §0 ("a
capability is named and never populated").

**R12 — No proposed clause text is fabricated.** `mainline.change_request` carries no proposed
text (r3 §5.4, DDL `0051_change_request.sql:59-102`). The engineer types it on camera into the
OSHA *"Modifications to operating procedures"* box; the diff is then computed client-side over
one real string and one typed string and is **labelled as such**. The console's existing
`features/diff/` is out of bounds (R1 forbids the import anyway).

**R13 — The product is called `CONTROL OF WORK`, with no vendor mark, and it carries a
permanent synthetic watermark.** "Control of work" is the industry's own generic name for the
software category, so it imitates nobody. No logo, no employer name, no form number, no
verbatim standard text presented as the product's own. A persistent strip reads
`SYNTHETIC DEMONSTRATION — no real site, no real permit, no real person`, matching the seed's
own `SYNTHETIC —` prefixes, which stay visible. *Authority:* r6-honesty A17.2 and A3.

**R14 — `demo.signer` is labelled the ACCEPTOR on the acceptance row, and is given no issuing
role.** The column is `exposure_receipt.actor_sub` and it means *who the obligation was shown
to* — HSG250 element 10. *Authority:* r3 §10, which flags its own §6.1 mapping as ambiguous;
between two readings of one column we take the one the column's name supports.

**R15 — The refusal is a BANNER over a locked action, never a modal, and it renders two
stacked registers**: the supervisor's sentence on top, the database's own words beneath
(`23514` · `gate_closed_when_issued` · the CHECK predicate · which table it came from).
*Authority:* r3 §2.5 (not one vendor source describes a modal) and §8.

**R16 — Beat 4 is shown. The film does not end on a refusal.** *"A gate that always refuses is
broken, not safe"* (`gate-run-contract.md` §1). *Authority:* r3 §8.

**R17 — Language discipline on the memory loop.** The card's three lines are labelled
**RECALLED / SHOWN TO / STATUS** in operator language, sourced from `recall_run`,
`exposure_receipt` and `blocking_check.open`. On-screen text uses the **past tense** for the
recall ("the recall run that armed this obligation", `started_at`) and the **present tense**
only for the re-derivation that happens on the button press. No "watch it remember", no
similarity score, no vector visualisation — there are no embeddings, cues or candidate rows in
this world. *Authority:* r6-honesty A5 and A5.1; r2-memory warning 4.

**R18 — Every screen carries a RAW PAYLOAD affordance and a REQUEST LOG.** One click shows the
verbatim JSON that produced what is on screen, with the request method, path, status, wire
bytes and `observed_at`. This is what makes the two registers believable and it is what a judge
in devtools will cross-check. *Authority:* the brief ("the raw payload available"); r5-craft §6.

---

## 3 · THE ARCHITECTURE, IN ONE PICTURE

```
browser
  └─ GET  <origin>/operator.html            served by static_site.py out of web/
       ├─ GET  /v1/demo/subjects            ← which subject, never a literal      (M9)
       ├─ GET  /v1/permits/{permit_id}
       ├─ GET  /v1/permits/{permit_id}/blocking-checks
       ├─ GET  /v1/clauses/{uuid}/versions/{commit}
       ├─ GET  /v1/recall-runs/{run_id}
       ├─ GET  /v1/receipts/{receipt_id}
       ├─ GET  /v1/change-requests/{cr_id}
       └─ POST /v1/demo/gate-run            ← the ISSUE button. One transaction.  (R4)
                                              Four beats. Rolled back. Persists nothing.
same origin ⇒ no CORS ⇒ response headers readable ⇒ X-Mainline-Emulator visible   (M1, M12)
```

**Two places it can run, and the page says which one it is in:**

* **rehearsal** — `scripts/deploy/local_furl.py` over the local CockroachDB node, web root
  pointed at `console/dist`. Real handler, real kernel, real SQLSTATEs, `X-Mainline-Emulator:
  local_furl` on every response, rendered on screen. This is how W1–W7 verify.
* **deployed** — the orchestrator's next `build_lambda` picks `dist/operator.html` up with no
  script change (M6) and serves it at `<demo-url>/operator.html`. **No worker deploys.**

---

## 4 · THE EIGHT WORKERS

Disjoint, literally enumerated paths. `CON` = `verticals/mainline/apps/console`.
Four files are **edited** rather than created and each has exactly one owner: `vite.config.ts`,
`budgets.json`, `eslint.config.js`, `package.json` — all W1's, nobody else's.

| id | title | owns |
|---|---|---|
| W1 | operator shell, build wiring and the two new gates | the entry, the chrome, `vite.config.ts`, `budgets.json`, `eslint.config.js`, `package.json`, `scripts/check-entrypoints.ts` |
| W2 | the kernel client — real HTTP, addressing, envelope, provenance, raw payload | `src/operator/kernel/**` |
| W3 | the permit form: header, Figure 1 body, typed fields, signature block, display copy | `src/operator/permit/**` |
| W4 | hazard identification = the STORE → RETRIEVE → ACT card | `src/operator/hazard/**` |
| W5 | the action bar, the four beats and the refusal experience | `src/operator/issue/**` |
| W6 | the management-of-change screen, and the absence it must name | `src/operator/change/**` |
| W7 | accessibility, legibility and the devtools-honesty capture proof | `CON/tests/browser/operator-*.spec.ts`, `CON/scripts/operator-capture.mjs` |
| W8 | the copy deck, the field honesty ledger, packaging impact, the runbook | `verticals/mainline/demo/operator/**` |

Full briefs are carried in the structured output that accompanies this document; each is
self-contained and repeats the no-faking and no-deploy rules.

### 4.1 Sequencing

W1 and W2 are the critical path and start immediately; W1 must land `operator.html` and the
route stub before W3–W6 can mount anything, and W2 must land `client.ts` + `addressing.ts`
before any screen has data. W3, W4, W5, W6 then run in parallel against W2's interfaces. W7
runs last against a built `dist/` and a running `local_furl`. W8 runs throughout and is the
only worker allowed to write prose that ships.

### 4.2 The interfaces W2 publishes, fixed here so four workers can build against them

```ts
// src/operator/kernel/client.ts
export interface Exchange<T> {
  readonly method: 'GET' | 'POST';
  readonly path: string;          // '/v1/permits/…' — always same-origin
  readonly status: number;
  readonly wireBytes: number;
  readonly receivedAt: string;    // ISO, from the client's clock, labelled as such
  readonly serverDate: string | null;
  readonly emulator: string | null;   // X-Mainline-Emulator, or null
  readonly envelope: Envelope | null; // null on a problem+json body
  readonly data: T | null;
  readonly raw: string;           // verbatim response text. Never re-serialised.
  readonly problem: Problem | null;
}
export function get<T>(path: string): Promise<Exchange<T>>;
export function post<T>(path: string, body?: unknown): Promise<Exchange<T>>;

// src/operator/kernel/envelope.ts
export interface Envelope {
  readonly resource: string; readonly schema_id: string;
  readonly observed_at: string | null; readonly staged: boolean;
  readonly staged_note: string | null;
  readonly provenance: readonly { readonly pointer: string; readonly kind: ProvChip; readonly note?: string }[];
}
export type ProvChip = 'db:column' | 'db:constraint' | 'recomputed' | 'staged' | 'derived';
export function chipFor(env: Envelope | null, jsonPointer: string): ProvChip | null;

// src/operator/kernel/addressing.ts
export interface Addressing { permitId: string|null; crId: string|null; checkId: string|null;
  receiptId: string|null; clauseUuid: string|null; commitId: string|null; runId: string|null;
  siteCode: string|null; absent: readonly {subject: string; relation: string; reason: string}[]; }
export function resolveAddressing(): Promise<Addressing>;   // GET /v1/demo/subjects, cached per page load

// src/operator/kernel/log.ts
export function record(x: Exchange<unknown>): void;
export function entries(): readonly Exchange<unknown>[];
export function onChange(fn: () => void): () => void;
```

Every screen renders **absence** rather than a placeholder when a field is `null`, and renders
the `absent[]` reason verbatim when addressing could not resolve a subject.

---

## 5 · THE FIDELITY CHECKLIST WE ARE SCORED AGAINST

From r3 §9, in the order an industry judge checks it. Each is cheap and each is a thing a fake
screen normally gets wrong. W3 owns 1–2 and 5–8, W4 owns 3, W6 owns 9–10, W8 audits all ten.

1. reference number (`external_ref`) and a status chip (`state`, verbatim)
2. an expiry / validity window (`opened_at → horizon_at`)
3. isolation treated as a first-class linked obligation, not a checkbox
4. HSG250 Table 1 role names — never "approver"
5. a signature block with dated-and-timed rows, **including an unsigned hand-back**
6. suspension present as a state distinct from closed
7. a display / print copy affordance
8. permit type identified and colour-coded — **cold work, blue-edged**, not red
9. the OSHA five headings and the IChemE five-step ribbon on screen two
10. an authorisation matrix scaled to risk (the disposition lattice)

---

## 6 · WHAT WOULD MAKE THIS WORK WORTHLESS

Stated plainly so no worker has to infer it.

* A refusal string that did not come back over HTTP in this page load.
* A SQLSTATE, constraint name, digest, count or timestamp typed into a `.ts` file.
* `setTimeout` used to make anything feel like work, anywhere, for any reason.
* A UUID literal in source. Addressing comes from `GET /v1/demo/subjects` (M9).
* A "proposed clause text" that no column carries (R12).
* A job description, plant name, crew or PPE list presented as data (R9).
* A `423 Locked` rendered as though it were a gate refusal (R4).
* One byte added to `dist/assets/index-*.js` (R2).
* Any AWS call, any `terraform` verb, any SSM write, any redeploy, any commit.

---

## 7 · WHAT THIS PLAN DOES NOT SETTLE

Recorded so it is not invented later.

* **Whether the deployed package should be built `--console-transport live` now that a
  permanently-live page ships beside a possibly-replay console.** R3 states the consequence;
  the packaging decision is the orchestrator's. W8 writes the memo.
* **Whether `/operator` (extensionless) should be routed.** It currently serves the console via
  the SPA fallback (M5). Fixing it means editing `static_site.py`, which R8 forbids this wave.
  The URL we film and publish is `/operator.html`.
* **The permit type.** No column carries one. "Cold work" is r3's inference from the clause's
  subject matter; it is therefore rendered as an operator-typed selection (R9), not as data.
* **Whether the progressive reveal reads as honest on a capture.** R5 makes the disclosure line
  mandatory; W7 must watch a real capture with devtools open and record the verdict before this
  shape is committed to. If it reads as staged, the fallback is three presses / three real
  round trips, which is unimpeachable and slower.
