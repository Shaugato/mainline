<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# MEMORY-VISIBLE — the plan

**Lead:** memory-visibility · **Date:** 2026-08-15 · **Repo:** `D:/CoackroachDBxAWS/mainline`, HEAD `4af05e1`
**Research followed:** `docs/demo/research/r2-memory.md` (primary), with cross-checks against `r1-judging`,
`r3-operator`, `r4-story`.
**Live URL read during planning (GET only, no POST, no write, no deploy):**
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

---

## 0 · The one thing this plan builds

A page at **`/memory.html`** on the deployed origin — a framework-free, self-contained client of the
real kernel — that renders the store → retrieve → act loop as three columns of real rows, fills the
third column from one real `POST /v1/demo/gate-run`, and is legible in under 20 seconds.

It exists because the Devpost brief says, verbatim, *"Show the CockroachDB memory in action visibly…
a screen showing your agent store, retrieve and act on memory. Don't just narrate."* — and because the
Official Rules make *"footage showing the CockroachDB memory layer at work"* a **mandatory element of
the video**, not advice (`r1-judging`, `r4-story`). We currently imply the loop. Nothing in the tree
films it.

`r1-judging` established that the criteria tie-break is **lexicographic and Agentic Memory Design is
first**. This page is the axis-1 exhibit. It is the highest-leverage screen in the submission.

---

## 1 · What I measured before ruling (so that nothing below is assumed)

Five reads against the live Function URL on **2026-08-15T10:50Z**, plus one local recomputation.
Everything the loop needs is already live. **I re-derived, not re-read, `r2`'s claims.**

| # | Read | Result |
|---|---|---|
| 1 | `GET /v1/permits/dec0de00-0006-…/blocking-checks` | 200. `severity 4`, `virulence blood_major`, `closure_gen 0`, `origin blame_ancestry`, `open true`, `materialised_at 2026-08-02T03:00:10Z`, and the **`precursor` object inline** (`DEMO-INC-0001`, `occurred_at 2019-03-14T06:20:00Z`, `severity_gate 4`, `severity_basis human_rated`, `source_sha256 1f84f023…`). One request carries the STORE fact and the RETRIEVE result. |
| 2 | `GET /v1/clauses/dec0de00-0004-…/ancestry` | 200. `closure` = `{closure_gen 0, ancestor_count 1, max_severity 4, virulence blood_major, depth 1, truncated false, computed_by …demo_world.sql, projector_ver demo-1, computed_at 2026-08-10T02:57:43.852434Z}`; `blame_edges[0]` = `{basis asserted_document, state active, evidence_quote_sha256 f83044c9…}`. |
| 3 | `GET /v1/recall-runs/dec0de00-0009-…` | 200, 2,223 B. `started_at 2026-08-02T03:00:00Z`, `n_candidates 1 / n_blocking 1 / n_advisory 0 / n_silenced 0 / n_deduped 0`, `policy_version demo-recall-1.0`, `index_generation g1`, `index_plan_digest d98e50a8…`, `latency_ms null`. **Seventeen `db:column` chips, no others.** |
| 4 | `GET /v1/ledger` | 200, 9,505 B. Four leaves. **Leaf 2 is `precursor_event_ingested`, leaf 3 is `blame_closure_computed`** — the two memory writes, sequenced and Merkle-committed, each carrying `canon_bytes_b64`, `leaf_hash_hex`, `prev_link_hash_hex` and an inclusion proof. |
| 5 | *(local)* RFC 6962 recomputation of all four leaves | `sha256(0x00 ‖ canon_bytes)` **matched `leaf_hash_hex` 4/4.** The STORE is verifiable in a browser with `crypto.subtle`, from bytes the server returned. |
| 6 | `statement_refs` on reads 2 and 3 | **The server returns the actual SQL.** `ancestry.statement_refs[0]` = `{kind:"view", object:"mainline.clause_blame_current", text:"SELECT closure_gen, ancestor_events, ancestor_count, max_severity, virulence::text AS virulence, depth, truncated, computed_by, projector_ver, computed_at, site_id, encode(as_of_commit,'hex') AS as_of_commit FROM mainline.clause_blame_current WHERE clause_uuid = %s AND as_of_commit = decode(%s,'hex')"}` — **the sole legal read path (DM-9), verbatim, from the wire.** `recall-runs` likewise carries its full `mainline_meas.recall_run` statement. |
| 7 | `statement_refs` on read 1 | **Uneven.** Five refs; only `mainline.disposition` carries `text` (143 B). The other four are `{kind, object, text: null}`. This is the one honest gap in the query-path surface and R-M6 rules on it. |

Two structural measurements that decide *where* the page lives:

- `verticals/mainline/apps/console/vite.config.ts` does **not** set `publicDir`, so Vite's default
  (`public/`) applies. That directory **does not exist yet.** Files placed there are copied to
  `dist/` verbatim: not transformed, not hashed, **not written into `dist/.vite/manifest.json`**.
- `budgets.json` has exactly two budget roots — `root: "entry"` and
  `root: "glob:src/features/ancestry/render3d/**"` — and `scripts/check-budgets.ts` reads the Vite
  manifest. A file that never enters the manifest is outside both roots **by construction.**

---

## 2 · RULINGS

Every ruling below is made on my authority as memory-visibility lead, over questions `r2` left open
or that no researcher reached. Each names its evidence. **A worker who believes a ruling is wrong
escalates to me; a worker who silently works around one has committed the failure this repository
already reverted somebody for.**

### R-M1 — No new endpoint is required. Authority: my own measurement, §1 rows 1–7.

My scope said *"if showing a step needs an endpoint we lack, build the endpoint rather than faking
the step."* I checked, and we lack none. STORE is covered by `/v1/ledger` leaves 2–3 plus
`/v1/clauses/{}/ancestry`. RETRIEVE is covered by `/v1/clauses/{}/ancestry` (closure + the literal
view SQL), `/v1/recall-runs/{}` (counts, policy, index generation, `started_at`) and
`/v1/permits/{}/blocking-checks` (the armed `severity` / `virulence` / `closure_gen`). ACT is covered
by `POST /v1/demo/gate-run`.

**Therefore: no worker on this plan may touch `reads.py`, `gate_run.py`, `app.py`, `envelope.py`, any
migration, or any seed.** The baseline is 988 collected / 987 passed / 0 failed; the deployed API is
the thing every other lead is filming; and an endpoint change is a redeploy, which is prohibited.

**Escalation, and it is a real path, not a formality:** if W1's measurement finds a field the panel
needs and no endpoint returns, W1 **stops and reports it to me with the exact JSON pointer and the
exact endpoint**. I will then either redesign the cell or authorise an additive read-only endpoint as
a separate decision. **No worker invents the value, and no worker quietly drops the cell.**

### R-M2 — The page is a framework-free static file in `console/public/`, served at `/memory.html`.

`r2` warning 5 is the binding constraint: `static_site.DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024`, the
shipped entry chunk's `.gz` sibling is 138,177 B, headroom is **1,087 B**, and
`tests/test_static_site.py::_MINIMUM_HEADROOM_BYTES = 1024` turns CI red at **63 more gzipped bytes**.
Crossing it serves 413 for the console's own JavaScript — a blank page while health reports OK.

A `public/` file adds **zero bytes to the entry closure** because it never enters the module graph and
never enters the manifest. This is stronger than "we measured it and it fit": it cannot fail that way.
W5 measures anyway, because a ruling that is only an argument is not a test.

Consequences, all binding:

- **`vite.config.ts` is not edited.** No `rollupOptions.input`, no `publicDir` override, no second
  HTML entry through the bundler. The default already does what we need, and that config file is
  guarded by `tests/deploy/test_console_repro.py` over `BUILD_INPUT_NAMES`.
- **`budgets.json` is not edited.**
- **Nothing under `console/src/**` is edited by any worker on this plan.**
- No framework, no bundler, no npm dependency, no external origin. `index.html` already declares the
  offline/`file://` requirement; `/memory.html` inherits it. One `<link>` to a sibling CSS file and
  two `<script type="module">` to sibling JS files, all relative.

### R-M3 — The provenance vocabulary is the API's five chips, not the console's four.

A real discrepancy, found while planning, recorded so nobody "fixes" it:

- `console/src/design/provenance.ts:26` — `['db:column', 'db:constraint', 'recomputed', 'staged']`,
  and its docstring says *"There is no `computed`, no `derived` and no `estimated`."*
- `demo-api/…/envelope.py:93,96` — `{'db:column', 'db:constraint', 'recomputed', 'staged', 'derived'}`,
  where `derived` means *"computed by this read API from columns it names in `statement_refs`."*

**Ruling: `/memory.html` uses the envelope's five, because it renders envelope payloads verbatim and
the envelope is the authority for what each value it shipped actually is.** The page never assigns a
chip itself — **it renders the chip the response supplied, resolved by RFC 6901 pointer.** A value
whose pointer carries no chip in `provenance[]` is rendered with **no chip and no substitute**, per
`envelope.py`'s own line: *"unclaimed provenance is better than a comfortable default."*

**No sixth chip may be invented.** Neither file is modified. The discrepancy goes in
`memory-visible-CONTRACT.md` as a recorded fact, not a bug.

### R-M4 — A number computed in the browser gets NO chip, and may appear only as visible arithmetic.

`r2` §4.3 asks for *"2,555 days before this permit existed"* and says to label it `derived`. **That is
not available.** `derived` is reserved by `envelope.py:37` for the read API; `recomputed` is reserved
by `provenance.ts` and D6 for re-derivation from **signed bytes**. Browser arithmetic over two
rendered columns is neither.

**Ruling: banned as a bare chipped number. Permitted only in this form** — both operands on screen,
adjacent, each with its own `db:column` chip, and the gap rendered in a visually distinct *annotation*
register (smaller, unboxed, no chip) that reads as commentary on the two values above it, e.g.

```
occurred_at   2019-03-14T06:20:00Z   [db:column]
materialised_at 2026-08-02T03:00:10Z [db:column]
                  ↳ 2,697 days apart — arithmetic over the two columns above; not a stored value
```

The same rule governs `r4-story`'s ten-second beat (`recall_run.started_at 2026-08-02T03:00:00Z` →
`blocking_check.materialised_at 2026-08-02T03:00:10Z`): both are columns, both go on screen, the "ten
seconds" is annotation. **W3 computes no day-count until W1 has confirmed both operand pointers; the
number above is illustrative and must be recomputed from the live payload, not copied from this doc.**

### R-M5 — The overwritten "before" value is a source citation, never a rendered datum.

`r2` §2.2 calls the `0 / 'routine' / 0` → `4 / blood_major / 0` delta "the money shot." It is. But the
`0 / 'routine'` half **was overwritten by `fn_check_project()` and is recoverable by no read.** If it
appears in the same register as a column value, we have put a fabricated exhibit in front of a judge —
the exact class of act this repository reverted a worker for.

**Ruling, two halves:**

1. **The unrecoverable half is a citation.** Rendered in a distinct `source:` register — monospace,
   prefixed with the literal file and line
   (`verticals/mainline/db/seeds/demo/demo_permit.sql:318`), **no provenance chip**, visually
   unmistakable from a chipped value, and introduced by the words *"the seed supplied"* in the past
   tense. It is a quotation of this repository, and it is true as a quotation.
2. **The live half is an equality across two independent responses.**
   `blocking-checks → /data/checks/0/severity` **equals** `ancestry → /data/closure/max_severity`;
   likewise `virulence` and `closure_gen` ↔ `closure_gen`. **Both are `db:column`. They come from two
   separate HTTP requests a judge can see in devtools.** The check's severity is not an independent
   value — it *is* the closure's value, and the page shows that by putting them side by side and
   marking the match. That is the retrieval made visible with nothing unrecoverable in it.

The sentence the panel carries as text — *"The agent could not choose this"* (`r2` §4.5) — is earned
by 2, footnoted by 1, and by the `fn_check_project` source quoted with its `file:line`.

### R-M6 — The query path is rendered from `statement_refs[].text`, verbatim, and the gaps are stated.

My scope demands *"the actual query path."* Measured (§1 rows 6–7): the server already returns it for
the retrieval read — `mainline.clause_blame_current`, the DM-9 sole legal read path, as literal SQL
with `%s` placeholders — and for the recall run. On `blocking-checks` four of five refs have
`text: null`.

**Ruling:**

- The page renders `statement_refs[].text` **byte-for-byte as returned**, in a disclosure that is
  collapsed by default and expanded for the film. Never retyped, never reformatted, never
  syntax-highlighted in a way that changes characters.
- Where `text` is `null`, the page renders `kind` and `object` and the literal words
  **"statement text not returned by this endpoint."**
- **It is forbidden to paste SQL from a migration or seed into that gap.** A query path we assert is
  worth less than one the server hands us, and the difference is the whole product.

This single disclosure is, as far as I can find, the thing no competing entry will have: not a claim
that the database was consulted, but the statement it was consulted with.

### R-M7 — One POST, four beats, progressive reveal, and the page confesses the shape.

`r4-story` measured that `POST /v1/permits/{id}/merge` on the seeded subject answers **423
`demo_subject_write_protected`** with `use_instead: POST /v1/demo/gate-run`, and `r3-operator`
independently flagged that rendering a 423 in a refusal banner is a fabricated exhibit. So the ACT
column is filled from **one** `POST /v1/demo/gate-run` whose four beats already happened inside one
`SERIALIZABLE` transaction. Splitting it into three POSTs would destroy `transaction.single_transaction`.

**Ruling — the reveal is allowed, and it is fenced by four requirements, all mandatory:**

1. A **persistent disclosure line**, on screen the whole time, not a tooltip:
   `one request · four beats · one SERIALIZABLE transaction · response received <HH:MM:SS.mmm>`,
   filled from the client's own receipt time and the payload's `generated_at`.
2. Each beat renders **its own `elapsed_ms` from the payload**. The reveal delay is never displayed as
   a duration and never labelled as latency.
3. **No `setTimeout`, `requestAnimationFrame` loop, or `await sleep()` may run before the response has
   resolved, and none may gate a `fetch`.** The reveal timer is constructed inside the `.then`/`await`
   that already holds the parsed body, and W6's browser spec asserts this against the source.
4. **`?reveal=off` renders all four beats instantly.** A judge with devtools open can prove in one
   keystroke that every value was already in the response. This is cheap and it disarms the only
   suspicion the reveal can raise.

Beat 3 is the peak and must be given the room `r4-story` asked for: *"An attacker who owns the counter
does not own the gate."* And per `r2` warning 8, the page reads **`persistence_check.self_persisted:
false`**, never `identical`.

### R-M8 — Zero hardcoded identifiers. All addressing from `GET /v1/demo/subjects`.

`r2` warning 2: `scenario.EXPECTED` derives a `uuid5` permit id that is **not** the deployed
`dec0de00-0006-…`, so the Lambda is running with `MAINLINE_DEMO_*` overrides. `subjects.py:24-27`
already argues the rule. **No UUID literal, no `dec0de00`, no permit id, no clause id, no run id may
appear in `public/memory.html`, `public/memory-loop.js`, `public/memory-verify.js` or `public/memory.css`.**
The page calls `/v1/demo/subjects` first and addresses everything from the vector it returns.
W6's honesty script greps the four source files for `dec0de00` and for any UUID-shaped literal and
**fails on a hit.** Fixtures under `fixtures/memory-loop/` are captured payloads and are exempt.

### R-M9 — No vector, no embedding, no similarity, no spinning graph.

`r2` warning 4: `recall_candidate`, `event_cue`, `clause_embedding`, `lex_posting` are **empty in this
demo world**; the channel is `blame_ancestry` with `tau_applied = 0`, and `demo_permit.sql:181-185`
refuses to let anyone claim a threshold. A similarity visual would be a fabricated exhibit and would
also be the weaker story.

**Ruling: the page renders `origin: blame_ancestry` and the recall counts explicitly, so the absence is
stated rather than hidden.** Also banned, per `r2` §5.2: force-directed graphs, particle effects,
scrolling "agent thought" logs, embedding scatter plots, and any animation that implies a query which
did not run at that moment.

### R-M10 — Failure renders. It never blanks and it never reuses a stale value.

`r2` warning 7: beat 4 depends on an exposure receipt that expires 2027-01-01; if it lapses the beat is
`skipped` and the verdict is `NOT PROVEN`.

**Ruling:** `verdict: NOT PROVEN` renders as NOT PROVEN with every string in `failures[]` printed. A
failed GET renders the HTTP status and the endpoint path in the cell that needed it. **A cell may
never fall back to a previously fetched value, a fixture value, or a default.** *"A truthful red beats
a fabricated green"* is already this repository's law (`gate-run-contract.md`); this page obeys it.

### R-M11 — `ARCHITECTURE.md` is never cited on screen or in copy. It does not exist in this tree
(`r2` warning 1). Neither is `DEMO-HONESTY.md`'s *Kestrel Resources / WO-88213* world (`r2` warning 3);
its nouns are stale. Neither is a "lesson learned" panel (`r2` warning 6) — `mainline.lesson` and
`mainline.propagation` are produced by no migration. And the incident is **2019-03-14**, never 2024
(`r4-story`); `INC-2024-0117` lives inside a STAGED payload and is forbidden to narrate.

### R-M12 — Ownership boundary with the operator-screens lead, so neither of us blocks the other.

`r3-operator` recommends the loop render inside the permit screen's Hazard Identification section;
`r4-story` gives it beat B3. I own neither screen.

**Ruling:** I own `console/public/memory*.{html,css,js}` and the docs/tests enumerated in §4. I own
nothing under `console/src/**`. My deliverable is **complete and filmable standing alone** at
`/memory.html` — it never blocks on another lead. In addition, W3 exports
`mount(element, { base, subjects })` from `public/memory-loop.js` as a plain ES module, importable by
any page on this origin via `<script type="module">`. The operator lead may use it or ignore it; the
integration costs them one script tag and costs me nothing. **No worker of mine edits an operator
screen, and no worker of mine waits for one.**

### R-M13 — SYNTHETIC prefixes stay visible.

`evidence_summary`, `title` and `attribution` all arrive with a literal `SYNTHETIC — ` prefix. **It is
a column value. It is not stripped, not trimmed, not styled away.** `r4-story` is right that leaving it
visible makes everything beside it more credible, not less.

---

## 3 · The panel, specified

Three columns. One row of data each. A marker naming which column is live. No graph, no particles,
nothing that could have been prerecorded.

```
┌─ WHAT THIS SYSTEM REMEMBERS ──────── one request · four beats · one SERIALIZABLE transaction ─┐
│                                                                                               │
│  ① STORED                    ② RETRIEVED                   ③ ACTED ON                         │
│  ─────────                   ───────────                   ──────────                         │
│  DEMO-INC-0001               ledger leaf 3                 MERGE                              │
│  incident · 2019-03-14       blame_closure_computed        → REFUSED 23514                    │
│  severity_gate 4                                             gate_closed_when_issued          │
│  severity_basis human_rated  VIEW clause_blame_current                                        │
│                              [the literal SQL, from                counter forged to 0        │
│  ↓ blame_edge                 statement_refs[0].text]      → REFUSED P0001                    │
│    asserted_document                                         mainline.fn_permit_merge_gate    │
│    state active              closure_gen 0                                                    │
│                              ancestor_count 1              one disposition signed             │
│  ↓ clause_blame_closure      max_severity   4  ═╗          → ADMITTED 00000                   │
│    gen 0 · 1 ancestor        virulence blood_major ║          clearance_digest …              │
│    append-only,                                    ║                                          │
│    superseded never deleted  the obligation armed  ║                                          │
│                              severity        4  ═══╝  same value, two responses               │
│  ledger leaf 2               virulence blood_major                                            │
│  precursor_event_ingested    closure_gen     0                                                │
│  leaf_hash verified here     origin blame_ancestry                                            │
│  [recomputed]                tau_applied 0 · θ 0.35                                           │
│                              n_candidates 1 = 1 blocking + 0 advisory + 0 silenced            │
│  2019-03-14T06:20:00Z        started_at      2026-08-02T03:00:00Z                             │
│                              materialised_at 2026-08-02T03:00:10Z                             │
│    ↳ arithmetic over the two columns above; not a stored value                                │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
   verdict PROVEN · self_persisted false · SERIALIZABLE · single_transaction true
```

**The two sentences the page carries as prose** (`r2` §4.5), both earned above:

1. **"Nothing here was deleted."** `clause_blame_closure` is append-only and generation-versioned;
   `clause_blame_current` reads `DISTINCT ON … closure_gen DESC`; the append-only property is welded by
   a trigger, not by convention. This is the differentiator against every vector store.
2. **"The agent could not choose this."** `fn_check_project` overwrites `severity` and `virulence`
   unconditionally from the closure — an agent cannot write its own memory of how bad something is.

**The judge-facing line** (`r1-judging`): *most systems prove memory by recalling something; this one
proves memory by refusing something — and proves the memory is real by refusing again after the number
it reads was falsified.*

---

## 4 · The six workers — disjoint, literally enumerated paths

No path appears under two workers. No worker touches `console/src/**`, `vite.config.ts`,
`budgets.json`, `reads.py`, `gate_run.py`, `app.py`, `envelope.py`, any migration or any seed.

| # | id | owns |
|---|---|---|
| 1 | `w1-contract` | `docs/demo/memory-visible-CONTRACT.md` · `scripts/demo/capture_memory_loop.py` · `verticals/mainline/apps/console/fixtures/memory-loop/**` · `tests/demo/test_memory_loop_contract.py` |
| 2 | `w2-shell` | `verticals/mainline/apps/console/public/memory.html` · `verticals/mainline/apps/console/public/memory.css` |
| 3 | `w3-client` | `verticals/mainline/apps/console/public/memory-loop.js` |
| 4 | `w4-recompute` | `verticals/mainline/apps/console/public/memory-verify.js` · `verticals/mainline/apps/console/tests/unit/memory/verify.test.ts` · `verticals/mainline/apps/console/tests/unit/memory/chips.test.ts` |
| 5 | `w5-bytes` | `verticals/mainline/apps/console/scripts/check-memory-bytes.ts` · `tests/deploy/test_memory_page_is_served.py` · `docs/demo/memory-visible-BYTES.md` · `REUSE.toml` |
| 6 | `w6-audit` | `docs/demo/memory-visible-choreography.md` · `verticals/mainline/apps/console/tests/browser/memory-loop.spec.ts` · `scripts/qa/check_memory_panel_honesty.py` |

### The seam between W2 and W3 — the cell-id contract, fixed here

W2 owns the DOM skeleton and CSS; W3 owns the code that fills it. They meet on `data-cell` attributes
and nowhere else. W2 emits an empty element carrying `data-cell="<id>"`; W3 fills exactly the ids
below and **throws on an id it does not recognise and on an id it cannot fill**. Neither may add an id
without the other and without W1 confirming the pointer exists.

| `data-cell` | source | pointer |
|---|---|---|
| `store.event.ref` / `.kind` / `.occurred_at` / `.severity_gate` / `.severity_basis` / `.title` / `.source_sha256` | blocking-checks | `/data/checks/0/precursor/{external_ref,kind,occurred_at,severity_gate,severity_basis,title,source_sha256}` |
| `store.edge.basis` / `.state` / `.attribution` | ancestry | `/data/blame_edges/0/{basis,state,attribution}` |
| `store.closure.gen` / `.ancestors` / `.max_severity` / `.virulence` / `.depth` / `.truncated` / `.computed_by` / `.projector_ver` | ancestry | `/data/closure/*` |
| `store.leaf.ingested.*` / `store.leaf.closure.*` | ledger | the leaves whose `entry_kind` is `precursor_event_ingested` / `blame_closure_computed` — **found by `entry_kind`, never by array index** |
| `retrieve.sql.view` | ancestry | `/statement_refs` entry whose `object` is `mainline.clause_blame_current` → its `text` |
| `retrieve.sql.recall` | recall-run | `/statement_refs` entry whose `object` is `mainline_meas.recall_run` → its `text` |
| `retrieve.armed.severity` / `.virulence` / `.closure_gen` / `.origin` / `.materialised_at` | blocking-checks | `/data/checks/0/*` |
| `retrieve.recall.started_at` / `.policy` / `.index_generation` / `.index_plan_digest` / `.n_*` | recall-run | `/data/{started_at,policy_version,index_generation,index_plan_digest}`, `/data/counts/*` |
| `retrieve.match.severity` / `.virulence` / `.closure_gen` | **equality marker**, R-M5.2 | rendered `match` / `differs` from comparing the two responses; **no chip** |
| `act.beat<N>.name` / `.outcome` / `.sqlstate` / `.constraint` / `.constraint_source` / `.elapsed_ms` | gate-run | `/data/beats/<N-1>/*` |
| `act.verdict` / `act.failures` / `act.self_persisted` / `act.single_transaction` | gate-run | `/data/verdict`, `/data/failures`, `/data/persistence_check/self_persisted`, `/data/transaction/single_transaction` |
| `meta.received_at` / `meta.generated_at` / `meta.elapsed_ms` | gate-run + client clock | R-M7.1 |

---

## 5 · Definition of done for the panel as a whole

- `/memory.html` loads on the deployed origin, makes **four GETs and, on press, one POST**, and every
  value on screen is `Ctrl-F`-able in one of those five response bodies.
- `?reveal=off` fills the ACT column instantly.
- `pnpm run ci` in `console/` is green; `pytest` is still 988 collected / 987 passed / 0 failed / 0
  errors, or better, and **never worse**.
- Entry-chunk gzip is **byte-identical** before and after this plan lands, and W5 has the measurement
  written down.
- `scripts/qa/check_memory_panel_honesty.py` passes: no UUID literals in source, no `setTimeout`
  before a resolved response, no SQL literal in the page source, no `ARCHITECTURE.md` reference, no
  `2024`, no embedding/similarity vocabulary.
- Nothing is committed. The tree is left for the orchestrator.

## 6 · Prohibitions repeated, because they are the point

**Never fake a refusal, a latency, a SQLSTATE, a row, a count or a seal. Never `terraform apply`,
never redeploy, never touch AWS, never write an SSM parameter, never print a credential — the
orchestrator deploys. Never weaken `HONESTY.md`, `CI-STATE.md`, a ratchet or an assertion.
`continue-on-error` and `|| true` are banned. Do not commit.**

`r1-judging` supplies the citation that makes this a rules matter and not only a conscience matter:
the Official Rules require that the Project *"must function as depicted in the video"* — so a staged
refusal, a hard-coded SQLSTATE or a `setTimeout` faking latency is a **Functionality violation**,
judged by people with this public repository open.
