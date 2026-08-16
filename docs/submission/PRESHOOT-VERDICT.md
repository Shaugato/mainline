<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PRE-SHOOT VERDICT — the judge with ten minutes, run against the tree and the live origin

**Reader:** an adversarial judge holding the closing card, the repository and no patience ·
**Date:** 2026-08-17 · **HEAD:** `7e609cc` plus the uncommitted working tree ·
**Nothing was committed, applied, deployed, granted, revoked or dropped by this pass.**

Every number below was measured by this pass — against the local node at
`postgresql://root@localhost:26257/mainline_demo`, against the live origin over anonymous HTTP,
or against the committed artefacts. Nothing is quoted from a document that asserts it.

## VERDICT: **NOT READY**

**The three fixes the audit demanded all landed and all hold.** FIX 1 is solved outright: a judge
can now answer the eligibility question from the frame. FIX 2's three contradictions are closed and
each published command produces its published output when run verbatim. FIX 3's shooting documents
now tell one story and the click sheets agree on the press.

**NOT READY is about four things the fixes did not touch**, and the first is the one that matters:

1. **`k3`'s rail carries a false safety claim** — *"persisted: false — this endpoint cannot write"* —
   which this pass falsified against the live endpoint in one request. Two words fix it, the
   replacement is already sanctioned and the same length, and it is **cheap before the take and
   expensive after**.
2. **`k3`'s rail states `256/256` at a scope `k2`'s own half does not** — the two halves of the same
   22 seconds disagree about one number.
3. **No-regression cannot be certified today.** The local node is at its schema-object cap; SUITES
   and KERNEL are unmeasurable, not failing.
4. **The second use case does not drive against the live origin.** `POST /v1/demo/cr-gate-run`
   answers `404`. `B9`/`B10` are a documented NO-GO and the film he can honestly shoot today is the
   **152 s** variant, not the 172 s one.

Items 1 and 2 are pre-shoot text edits. Item 4 is a shoot-day decision that changes which film gets
made. Item 3 is an environment blocker nobody should clear by moving the environment.

---

## 1 · THE ELIGIBILITY QUESTION, ANSWERED FROM THE FRAME — FIX 1 IS SOLVED

**Yes. I can answer it, from `k3` alone, without pausing on anything else.** The panel
`k3.overlay.tools` reads, at 99 characters across and 7 lines tall:

```
------------------------------------------------------------------------------------------------
COCKROACHDB  ·  THE FOUR CONTEST TOOLS.  THE RULES REQUIRE TWO.   three EXERCISED, one DESIGNED

Distributed Vector Indexing (C-SPANN)  EXERCISED  3 cspann, 4 VECTOR, 42809    evidence/aws/ann/
Managed MCP Server                     EXERCISED  15 of 16, DIVERGED, published   evidence/mcp/
CockroachDB Cloud + ccloud CLI         EXERCISED  cluster list -o json, parsed   evidence/ccloud/
CockroachDB Agent Skills               DESIGNED   shipped, validated;  NO RUN IS COMMITTED  skills/
```

**The heading prints the floor beside the count**, which converts a boast into a check: a judge
reads *"the rules require two"* and *"three EXERCISED"* in the same line and is done.

**And it cost no second of film.** Measured, not assumed:

| what | measured | source |
|---|---|---|
| panel geometry | **99 ch × 7 lines** — `wc -L` semantics over the block itself | `VO-CLOSE.md:1107-1115` |
| `k3` overlay as committed | **89 ch × 24 lines** | `VO-CLOSE.md` §5.2 fence |
| composed `k3` | `max(89,99) = 99` ch · `24 + 1 + 7 = 32` lines — **exactly** §5.6.1's stated budget | this pass |
| the two `k2` overlay strings | **untouched.** `git diff --numstat` → **339 insertions, 0 deletions**; every hunk falls outside §3.1, §4.1 and §3.5 | this pass |
| film total | **172 s** — `BEATS.yaml` `dur` sums to `172` across `b0…b10 · k1 · k2 · k3 · end` | this pass |
| the close | **22 s** — `k1` 6 · `k2` 10 · `k3` 6 | `BEATS.yaml` |
| word budgets | `322` = `budget.film_words`; close `36`, of which **34 are spoken** | this pass |

`BEATS.yaml`'s `k3.on_screen` names the panel as the card's **fourth** element and says *"three
EXERCISED, one DESIGNED"* in its own words. `SPINE.md:194` carries it in the `K3` row.
`ONSCREEN-TEXT.yaml`'s copy is **byte-identical** to `VO-CLOSE.md`'s, line for line — checked, not
asserted.

**The single caution.** `k3` composed is at **32 of 32 lines** — zero height headroom, by its own
stated budget. §5.6.1's remedy ladder exists and touches no word, no row and no state. That is the
right design; it just means a thirty-third line is not available to anyone on the day.

---

## 2 · EVERY LINE ON THE CARDS, CHECKED

**Verified: 34 claim-bearing lines.** **Unverifiable in this pass: 3.** **Stated better than the
evidence supports: 2** — both on `k3`'s criterion rail, both already logged as open REWORDs in this
project's own clearance file.

### 2.1 Verified — measured by this pass

**`k1` — the loop.** All six relation names resolve on the cluster with the right `table_type`
(`mainline.event`, `mainline.blame_edge`, `mainline.clause_blame_closure`, `mainline.permit`,
`mainline_meas.recall_run` base tables; `mainline.clause_blame_current` a **VIEW**). The three
timestamps are real rows: `occurred_at` **`2019-03-14 06:20:00+00`**, `started_at`
**`2026-08-02 03:00:00+00`**, `materialised_at` **`2026-08-02 03:00:10+00`** — the card's *"ten
seconds"* is the subtraction. `-> 23514` and `-> P0001` are what the live endpoint returns.

**`k2` — the AWS half.** `url_authorization_type` defaults to `NONE` and `infra/envs/demo/main.tf:460`
resolves to `NONE`; `architecture` is wired from `var.lambda_architecture`; the SSM name
`/mainline/demo/cockroach_dsn` is the declared default; one execution role
(`${function_name}-exec`) and one inline policy (`${function_name}-dsn-read`). `APPLIED.md` reads
**`24 created, 0 changed, 0 destroyed`**, the state bucket **versioned · public access blocked ·
SSE-S3**, and *"three alarms on three timescales feeding one SNS topic into a responder that calls
`PutFunctionConcurrency(ReservedConcurrentExecutions=0)`, plus the budget"* — the card's sentence,
in the apply record's own words.

**`k2` — the CockroachDB half.** `GET /v1/health`, anonymous, returned live:
`ok true`, `CockroachDB CCL v26.2.5`, `database mainline_demo`, `deploy_chain_applied 271` of `271`,
`schema_fingerprint ec9b1ce7…`. `POST /v1/demo/gate-run`, anonymous, returned
`transaction.isolation SERIALIZABLE`, `single_transaction true`, **three** savepoints
(`gate_run_beat_2/3/4`), `disposition rolled_back` — the card's *"one transaction, three savepoints,
rolled back"*, exactly. On the cluster: `gate_closed_when_issued` is a CHECK reading
`((state != 'merged'::mainline.subject_state) OR (open_blocking = 0))`; `mainline.subject_state` is
a user-defined enum; **19** multi-column foreign keys; `WITH RECURSIVE` is at
`verticals/mainline/db/queries/closure_write.sql:**152**`, the line the card cites.

**`k3` — the tools panel, row by row.** `3` cspann indexes and `4` VECTOR columns, counted live on
`mainline_demo`; `42809` occurs 3× in `evidence/aws/ann/explain-unhinted.txt` with 2 explicit
`REFUSED BY THE SERVER` lines. `evidence/mcp/pack-run.json` → **`15 / 16 · DIVERGED — KNOWN GAP ·
exit 1`**. `evidence/ccloud/cluster-list.txt` parses as JSON to `('mainline-dev', 'v26.2.5', 'AWS')`.
`skills/validate-spec.py skills/ --strict` → **`3 skill(s), 0 error(s), 0 warning(s)`**, and
`ls evidence/ | grep -i skill` returns **nothing, exit 1** — which is the whole of
`NO RUN IS COMMITTED`. The census agrees with the panel and was not edited to: `crdb_vector_index
EXERCISED · crdb_managed_mcp EXERCISED · crdb_cloud_ccloud EXERCISED · crdb_agent_skills
**DESIGNED**`.

> **Agent Skills reads `DESIGNED` on the card, in the same capitals and the same column as
> `EXERCISED`, and no run was captured to promote it.** That is the row that makes the other three
> believable, and it survived the wave intact.

### 2.2 Could not verify — 3, and each is named rather than waved through

1. **`42501` on `256/256` ungranted pairs.** `privilege_conformance.py --database mainline_demo`
   **refuses to run** — *"this database holds 0 applied migration(s) against 271 file(s) on disk"* —
   and a fresh probe database **cannot be created**, because the node is at its schema-object cap
   (§4). The number is inherited from `STATE-OF-THE-BUILD.md` §12.6 and was not re-measured here.
2. **The Bedrock box's `au.*` inference profiles and Titan v2 in `ap-southeast-2`.** Evidenced in the
   repository; confirming it needs an AWS call, which this pass is forbidden to make.
3. **`k1`'s `refused at <THIS RUN>`** — a capture-time placeholder by design, not a claim.

### 2.3 Stated better than the evidence supports — **2**, both on `k3`, both fixable in words

**R1 — `-> persisted: false — this endpoint cannot write`. This is false as written, and I falsified
it in one anonymous request.** `POST /v1/demo/gate-run` beat 4 returned
`observed.disposition_id **ef1e9dba-c7aa-4e07-b702-732bb0f9ad99**` and a `merge_record` with a
`clearance_digest` — **the endpoint wrote** — and `persistence_check.after.row_counts` then reads
`mainline.disposition: **0**`, because the transaction was rolled back. The true claim is *the
writes do not survive*, which is stronger and is what `persisted: false` actually means.

This is not a new discovery; it is **`CLAIMS-CLEARANCE.md` §7.4**, still open, and its own words are
the indictment: the film's `B8` says the endpoint writes **out loud at 1:50**, and
`ONSCREEN-TEXT.yaml` `b8.footer.persisted` **forbids the short form by name** — *never say "nothing
was written."* The card then carries that forbidden sentence in three words for the film's last six
seconds. `CLAIMS-CLEARANCE.md` row **O27** records the condition explicitly and notes that the
recompression moved it from the last eight seconds to the last six: *"fewer seconds is not a fix."*

> **Sanctioned replacement, already written, same length on screen** (§7.4):
> `-> persisted: false — this call is non-mutating by construction`
> or `-> persisted: false — nothing it writes survives the transaction`.

**R2 — `-> the refusal itself; 42501 on 256/256 ungranted pairs; a ledger that publishes what did
not run`.** `CLAIMS-CLEARANCE.md` **§7.10** requires the scope words *"in privilege conformance"*,
because the figure is `privilege_conformance.py`'s baseline against
`postgresql://root@localhost:26257/defaultdb` and **no artefact attributes it to `mainline_demo` on
CockroachDB Cloud** — under a card heading that establishes one. The proof that this is a real
inconsistency and not a preference: **`k2`'s CockroachDB half already carries the qualifier**
(`VO-CLOSE.md:862`, *"256/256 ungranted pairs refused in privilege conformance"*) while `k3`'s rail
at `:990` does not. **Two halves of the same 22 seconds state one number at two scopes.** Two words
close it, and §4 explains why I could not re-measure the number itself.

---

## 3 · THE THREE CONTRADICTIONS — ALL THREE CLOSED, AND EACH COMMAND RUN VERBATIM

**S1 · the role predicate — FIXED, and the claim was not weakened to match the broken check.**
`close-block.md:262` and `feature-census.md:286` now publish the explicit nine-name `IN` list.
Run verbatim by this pass against the pinned local node:

```
rolname,rolcanlogin
agent_gate,f · agent_projector,f · agent_recaller,f · auditor_ro,f · mainline_auditor,f
mainline_migrator,f · mainline_owner,f · quality_assurance,f · svc_disposition,f
```

**Nine rows, `rolcanlogin` false on all nine** — the published check now produces the published
answer. `feature-census.md:296-300` goes further and bans the `LIKE` form by name, printing what it
returns (five rows, two able to log in) so it cannot be pasted back by accident.

**S2 · JUDGE-START Stop 5 — FIXED, and it now agrees with the other four documents.** Stop 5 reads
*"There is exactly ONE published route to MAINLINE's ledger, and it is a SQL login."* The MCP
sub-heading is *"available, working, and deliberately not published"*, taken word for word from
`JUDGE-PACK.md` §4, and it states the account-level key's `create_database` / `create_table` /
`insert_rows` verbs and prints the one command that reads back `credential_publishable: False`.
**The string "two published routes" now appears in exactly one file in the repository — `AUDIT.md`,
quoting the error it struck.**

**S5 · "all four exercised" — FIXED.** `close-block.md` §3 opens *"Three of the four are exercised
in this repository with a committed transcript… The fourth, Agent Skills, is `DESIGNED`."* §7.3's
written cut says the same in prose and the header now carries the counted length (`239 words`)
rather than the length it wished it were.

**S6 · the EventBridge grep — FIXED, and its published output is the output it prints.** Run
verbatim: `grep -rn --include=*.tf "aws_cloudwatch_event\|aws_scheduler" infra` → **no output,
exit 1**. §8's row now carries the reason the filter is load-bearing.

**S8 · the two documents prescribing the same 22 seconds — FIXED by deference, in both directions.**
`close-block.md` §7.1 now names `VO-CLOSE.md` §§2–5 and `ONSCREEN-TEXT.yaml` `k1`/`k2`/`k3` as the
sole authority and re-labels its own block a press-kit fallback; `VO-CLOSE.md` §5.6's AUTHORITY note
(R-C8) says the same from the other side. Its line 5 is corrected regardless of use.

---

## 4 · ONE STORY ACROSS THE SHOOTING DOCUMENTS — YES, WITH FOUR RESIDUAL NITS

**The beat count and the timings agree everywhere.** `SPINE.md:197`, `BEATS.yaml`, `VO-CLOSE.md`
§0.1, `VO-DEMO-CR.md:95` and `VIDEO-KIT.md`'s V1 row all carry `148 + 22 + 2 = 172 s = 2:52`, hard
stop `174`, ceiling `180`. `BEATS.yaml`'s durations sum to `172` when added, which is the only test
that matters.

**The press is decided and every document implements it.** Click 6 lands at **`2:14.0`, `+10.0`
into `b9`**; `2:17` is **struck** — named as struck in `CLICKS.md` (§0, §5, §8's ledger row 8),
`CLICKS-CR.md:248`, `FALLBACKS.md` (three places), `VO-DEMO-CR.md:237`, `ONSCREEN-TEXT.yaml:2130`
and `CLAIMS-CLEARANCE.md:1500`. The reason is stated the right way round: under `2:17` the SQLSTATE
would reach the screen **after** `b10`'s first word *"Refused."* had already named it. **No
duration, word budget or spoken line moved to buy it.**

**FIX 3 · `VIDEO-KIT.md` is reconciled, and honestly.** Its first screen now reads *"THIS FILE IS A
CAPTURE RUNBOOK. IT IS NOT THE FILM AUTHORITY, AND AS OF 2026-08-16 IT NO LONGER DESCRIBES THE
FILM"*, with a table routing every film question to the file that owns it. The 25-shot table, the
`s19-beat5-mcp-connect` shot, the `171 s / 2:51` total and **§497's *"declared in Terraform and not
applied… two of ten, named"*** are struck with `SUPERSEDED 2026-08-16` blocks that name what
replaced them. **Nothing was deleted** — the struck content stays readable, which is the correct
choice: a claim removed is not a claim corrected.

### The four residual disagreements, quoted

1. **`ON-SCREEN-CLAIMS.md:195` misquotes the panel heading it is the registry for.** It prints
   `COCKROACHDB · THE FOUR CONTEST TOOLS. THE RULES REQUIRE TWO.` with single spaces; the string of
   record has **two** spaces around the `·` and after `TOOLS.`. The table above it is headed *"may
   appear as, exactly"*. Harmless to a viewer, wrong in the one document whose job is exact strings.
2. **`CLAIMS-CLEARANCE.md` §13.6 `D-W5` overstates its own blocker.** It calls the
   `HYG-sha-literal` hits **"OPEN — BLOCKING for CI"**. Measured: `claim_hygiene.py` with no
   arguments — the form `.github/workflows/claims.yml`'s GREEN step runs — **exits 0**, because
   `TARGET_GLOBS` does not reach `docs/submission/**`. Under explicit `--check` the violations are
   real (**4**: `feature-census.md:958/:1617/:1707`, new this wave; `VIDEO-KIT.md:1013`, a Docker
   build hash already present at `HEAD`). Worth fixing; not a red lane.
3. **`APPLIED.md` says "three alarms", `close-block.md` says "seven".** Both true at different
   scopes — 3 guard, 4 `module.api`. `AUDIT.md` §4.3 raised it; it is still unreconciled.
4. **`evidence/tool-usage/aws-services.json` carries no SNS and no AWS Budgets row**, while `k2`
   names both on screen. `AUDIT.md` §4.3's coverage gap, still open. The card is scoped correctly
   and cites `APPLIED.md`; the artefact a judge is pointed at simply does not list them.

---

## 5 · THE FILM STILL FITS — MEASURED

```
b0 12 · b0b 8 · b1 10 · b2 14 · b3 18 · b4 10 · b5 16 · b6 18 · b7 12 · b8 6 · b9 12 · b10 12  = 148
k1  6 · k2 10 · k3  6                                                                          =  22
end 2                                                                                          =   2
                                                                                        TOTAL  = 172
```

`172 ≤ 172` target · `< 174` hard stop · `8 s` under the 180 s rule. Close at **22 s**, three cards.
Nothing in this pass, and nothing in the tools-panel wave, added a second: `close_words` is still
`36`, the spoken close is still 34 words, and `VO-CLOSE.md` §0.4.1 prices the spoken alternative
(`k2` would run 19 words in a 10 s block with **zero** air, breaking §3.5's landing-4 alignment) and
**refuses it in writing**. The panel is text a judge pauses on. That is the correct answer to the
constraint.

---

## 6 · NO REGRESSION — **CANNOT BE CERTIFIED TODAY, AND NOT BECAUSE OF THE TREE**

`scripts/qa/regression_guard.py --suite-out qa/preshoot-suites.xml`, run by this pass:

| family | result |
|---|---|
| **SUITES** | `collected` **1070** — baseline exactly · `passed` **1056** · `failed` **1** · `errors` **12** · `skipped` 1 |
| **KERNEL** | **not measured** — the proof wrote no evidence, exit 2 |
| **BOUNDS** | **PASS** — `136 * 1024 == 139264` unmoved; straddle `137939 < 139264 < 490373`; exactly 1 identity refusal |
| **LIVE** | **PASS** — `ok=True`, `deploy_chain_applied 271`, `gate_run_verdict PROVEN`, 4 beats, 0 mismatches |
| **SEED** | **PASS** — 7 of 7 |
| **PRIVILEGES** | 4 PASS · **1 FAIL** — `mainline.exposure_line` / `mainline.exposure_receipt` INSERT, **the sanctioned standing gap** |

**All 13 non-passing tests and all 7 KERNEL rows share one cause, and it is the node:**

```
cannot create new schema object(s): would exceed approximate maximum (20000); current count: 19999
```

Measured read-only by this pass: **243 databases on the local node, 54 of them scratch-shaped**
(`w_w4stab_shared`, `w_w5_order_w1`, `w_cohere_bench`, …), accumulated across many waves. Fixtures
cannot create their schemas, so every test needing a fresh one errors before its body runs. This is
**`D-ENV`**, already raised by W6 in `CLAIMS-CLEARANCE.md` §13.6 and reproduced here independently.

**Why it is not attributable to the tree:** `collected` is `1070`, the baseline to the test; the
working tree's changes are markdown and YAML under `docs/`, which pytest does not collect; and not
one of the 13 records a wrong value — every one is `ConfigurationLimitExceeded` on `CREATE`.

> **REPORTED, NOT REPAIRED, for the second time and for the same reason.** The two remedies are
> raising `sql.schema.approx_max_object_count` and dropping the 54 scratch databases. **This pass
> did neither.** One moves a red to green by moving the environment; the other destroys data on the
> node the demo world lives on — and several of those databases are cited as evidence in
> `docs/ci/transitions-contamination.md`. **Whoever clears it must re-run `regression_guard.py` and
> read `1070 / 1069 / 0 / 0` off a `--junitxml` root element before the baseline may be called
> held.** Until then the honest statement is: **BOUNDS unmoved, LIVE `PROVEN`, SEED green, SUITES
> and KERNEL unmeasurable on a saturated node.**

**Nothing was widened and nothing was revoked.** `mainline_qa.v_disposition_profile` / `N01` stays
open at `15 / 16`, verdict `DIVERGED — KNOWN GAP`. The PRIVILEGES `FAIL` stays open. A negative
suite that has quietly gone green is the worst artefact in a repository, because it reads as the
strongest.

---

## 7 · THE SECOND USE CASE DOES NOT DRIVE AGAINST THE LIVE ORIGIN

This pass drove the origin anonymously:

* `POST /v1/demo/gate-run` → **`200`**, `verdict PROVEN`, `persisted false`, four beats
  `00000 · 23514 · P0001 · 00000`. **Use case one is live.**
* `POST /v1/demo/cr-gate-run` → **`404`**, and the body enumerates the **17** routes the deployment
  does declare. `/v1/demo/cr-gate-run` is not among them; neither is
  `/v1/change-requests/{cr_id}/blocking-checks`.

This reproduces `evidence/deploy/cr-gate-live.json` exactly — `status UNANSWERABLE`, `exit_code 2`,
`cr_blocking_checks_declared false`, `declared_path_count 17` — produced `2026-08-16T04:41Z`.

**The shooting documents are right about this and say so plainly**, which is to their credit:
`FALLBACKS.md` §4.2's **R-11** gate is a **NO-GO today**; `CLICKS-CR.md`'s `R-SD4b` box makes the
whole press ruling conditional on it; and under NO-GO *"there is no Click 6 at all"*, `b8` returns to
10 s and **the film is 152 s** (`SPINE.md` §5.1).

**But the premise this pass was handed — that both use cases still drive against the live origin —
is not what the origin says today.** The founder must walk to the shoot knowing which film he is
making. Deploying the route is his call and the orchestrator's; this pass is forbidden to make it
and did not.

---

## 8 · WHAT TO DO BEFORE THE RED LIGHT, RANKED

1. **Reword `k3`'s rail line 2** to `persisted: false — this call is non-mutating by construction`
   (`CLAIMS-CLEARANCE.md` §7.4's sanctioned string). **Minutes. Same length on screen. No timing
   moves.** It removes the only line on the closing card that the film's own `B8` contradicts, and
   it is the one defect here that a judge can catch by watching the film twice.
2. **Add two words to `k3`'s rail line 4** — `…on 256/256 ungranted pairs **in privilege
   conformance**;` (§7.10). It makes the two halves of the close agree about one number.
3. **Decide the R-11 gate before the call sheet is printed** — 172 s with `b9`/`b10`, or 152 s
   without. Both films are fully documented. Neither is a surprise unless it is discovered at 09:00.
4. **Clear the node, then re-run the guard** and read `1070 / 1069 / 0 / 0` off the JUnit root. Not
   by raising `sql.schema.approx_max_object_count`.
5. **The four nits in §4**, none of which is shoot-blocking: the misquoted heading in
   `ON-SCREEN-CLAIMS.md:195`, `D-W5`'s overstated CI blocker, the 3-vs-7 alarm scopes, and the
   missing SNS / Budgets census rows.

**Explicitly not recommended, again:** capturing an Agent Skills run to promote `DESIGNED`,
revoking the `mainline_qa` grant to turn `N01` green, or widening the `exposure_*` grants. All three
would move a number on submission eve at the cost of the thing that makes this submission credible.

---

*No `terraform` was run. No AWS API was called. No SSM parameter was written. No credential was
printed. No grant was widened or revoked. No database was created or dropped and no cluster setting
was written, on a node whose saturation is the subject of §6. No ratchet, floor, ceiling or honesty
document was touched. Nothing was committed.*
