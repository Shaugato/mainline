<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SUBMISSION-COMPLETENESS PLAN — every field filled, the optional ones too, and the rare things put where a judge will meet them

**Submission-completeness lead · 2026-08-17 · repo `D:/CoackroachDBxAWS/mainline`, master at
`9e91467` · live origin
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`**

**This file replaces the extra-credit plan dated 2026-08-16, which was executed.** That wave's
output is in the tree — the axis-1 paragraphs are in `DEVPOST.md`, the six live GETs are in
`README.md`, `evidence/mcp/` exists, and its claim ledger is preserved at
`docs/submission/EXTRA-CREDIT-CLAIMS.md`. **Nothing that wave wrote is undone here.** Its eight
rulings (R1–R8) still bind; where this page rules on the same question it says so.

Every measurement below was taken today by this lead, not copied from another document.

---

## 0 · WHAT I MEASURED TODAY, AND THE THREE THINGS IT CHANGES

**Measurement 1 — the origin answers from outside our network.** Fetched
`GET /v1/health` from a host that is not ours and holds no credential of ours, `2026-08-17`:

```json
{"ok":true,"database":"mainline_demo",
 "cluster_version":"CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 …)",
 "deploy_chain_applied":271,"deploy_chain_files":271,
 "schema_fingerprint":"ec9b1ce7…","server_date":"2026-08-17T15:08:16.662624Z"}
```

That is the R2 mechanical requirement discharged from the judge's side of the wire rather than
from ours. **It is not permission to stop checking it** — see W4.

**Measurement 2 — the submission requirements, re-read from the source today, are seven items
and two of them are optional.** Fetched from `https://cockroachdb-ai.devpost.com/`, verbatim:

> 6. *"Optional: Include an architectural diagram showing how CockroachDB, AWS services, and
>    your agent interact."*
> 7. *"Optional: Provide feedback on the CockroachDB AI tools or features."*

**Both are unmet in substance, and the repository does not know it.** `RULES-MATRIX.md` §1.2
marks the diagram row *"present"* — but the only architecture diagram in the tree is
`README.md:365`, three ASCII boxes reading *product → substrate → CockroachDB*. **It contains no
AWS service and no agent**, which are two of the three things the requirement names. And the
feedback row reads *"worth doing"*; `docs/upstream/` holds one Agent-Skill proposal and nothing
else. There is no document anywhere in this repository that collects what we learned about the
platform. The founder asked for exactly that, in his own words, and the contest asks for it too.
**Two asks converge on one missing file. That is the highest-value hour on this board.**

**Measurement 3 — the rarest things we own are invisible where a judge lands.**
`grep -ci "anti-vacuity\|has_function_privilege\|naa_reason\|Wilson"` over the two documents a
judge actually opens first:

| document | hits |
|---|---:|
| `docs/submission/JUDGE-START.md` | **0** |
| `docs/submission/FIRST-FIVE-MINUTES.md` | **0** |
| `README.md` | **0** |

All four artefacts are real, committed and verified today: `docs/ci/anti-vacuity.md:55` reads
*"Seven lanes have a standing negative control after this wave, against three before it"*;
`docs/regression/GUARD.md:370` is headed *"`has_function_privilege` is a stub on CockroachDB
v26.2.5"* and quotes the behavioural truth at `:378`,
`CALL as probe: REFUSED 42501 user w_rg_probe does not have EXECUTE privilege on procedure
merge_permit`. They reached `DEVPOST.md` in the last wave. **They did not reach the pages a judge
opens before `DEVPOST.md`.**

---

## 1 · THE READABILITY BAR — and the single ruling that makes it safe

The founder read our own briefing and said: *"Even after going through your briefing, I'm finding
a very hard time to understand."* **That is the bar. We are failing it, and the failure is not
imprecision — it is that a first-time reader meets layer 3 first.**

**RULING A — LAYERING IS ADDITIVE. NO WORKER IN THIS WAVE DELETES OR REWRITES AN EXISTING
PRECISE CLAIM.** Layer 1 goes *in front of* layer 2 and layer 3, never *instead of* them. A
worker who cannot make a sentence both true and simple writes two sentences and keeps both.
**Authority:** the founder's own instruction — *"the fix is layering, not simplifying"* and
*"never weaken a claim to make it readable"* — plus the plain risk that a wave which rewrites
`DEVPOST.md` at T-1 day breaks a page that already passes `check_submission_prose.py` at zero
violations. This ruling is also what makes six workers safe to run concurrently: an insert
cannot collide with another insert the way two rewrites of one paragraph can.

**The three layers, and who owes which:**

| layer | reader | test it must pass | owed by |
|---|---|---|---|
| **1** | a non-technical person, sixty seconds | a person, a situation, a consequence — no term used before it is defined | W1, W3, W5, W6 |
| **2** | a technical reader | the constraint, the trigger, the SQLSTATE, why it cannot be bypassed | W1, W2, W5 |
| **3** | a reviewer checking a claim | the file, the line, the transcript — **already exists and is not weakened by anybody** | all |

**Terms that may not appear without a plain-language gloss at first use**, taken from the
founder's list and extended by what I found in the tree: `projection`, `blame ancestry`,
`defeater`, `epoch`, `disposition`, `obligation`, `canonicalisation`, `MUS`, `NAA`, `diachronic`,
`synchronic`, `negative control`, `anti-vacuity`, `Wilson lower bound`, `SQLSTATE`, `C-SPANN`,
`projected counter`, `precursor`. A worker who cannot gloss one in a clause does not use it in
layer 1.

---

## 2 · RULINGS — what the brief left open, decided, with authority named

**R-A · Layering is additive.** Above. Binds every worker.

**R-B · `DEVPOST.md` is this wave's, and it is worked insert-only.** **Authority:** my scope is
*"fill every field the Devpost form asks for, including the optional ones, and produce the copy"*
— that copy lives in exactly one file. W1 owns it. **Under R-A, W1 inserts new blocks and edits
exactly one existing structure: the *Field-by-field checklist for the person pasting* table at
the foot, which is the completeness lead's own instrument.** No existing `<!-- PASTE -->` block is
rewritten, shortened, or re-ordered by this wave.

**R-C · The two optional requirements are DONE, not advised.** **Authority:** the founder —
*"anything they say optional, we should go for it"* — and the verbatim requirement text in §0.
W5 draws the diagram; W2 writes the feedback; W1 turns each into a paste block. **A pointer to a
README section is not a diagram, and a promise to write feedback is not feedback.**

**R-D · Every CockroachDB finding is re-verified before it is published, and one that cannot be
reproduced is published as unreproduced rather than dropped.** **Authority:** the founder's
*"verify every one before publishing it; do not publish one you cannot reproduce"*, and the
harder reason: this document is the one a CockroachDB engineer will read most carefully, and a
finding they cannot reproduce costs us more credibility than the other six earn. **The register
is a bug report from a grateful user, not a complaint.** Each finding states what we expected,
what we measured, the command, what it cost, and what would have been better. **Any finding W2
cannot stand behind goes into a section headed *"Reported, not reproduced on this machine"* with
the reason. That section existing is worth more than seven clean findings.**

**R-E · No new measurement against AWS, no redeploy, no credential, no grant.** **Authority:**
the founder's absolute prohibitions. Read-only HTTPS `GET` against the public origin is the only
network access this wave takes, and `POST /v1/demo/gate-run` is permitted only because it ends in
`ROLLBACK` and persists nothing (`persisted false`, measured). **Nobody runs `terraform`, writes
an SSM parameter, prints a credential, or commits.**

**R-F · The two criterion-name spellings that came back from two contest pages are NOT
reconciled by this wave.** **Authority:** `docs/submission/compliance-plan.md` Ruling 3 read the
`/rules` page verbatim on `2026-08-16` and got *"Technological Implementation"* and *"Product
Readiness"*; my fetch of the overview page today came back through a summarising model and
rendered them *"Technical Implementation"* and *"Production Readiness"*. **A summariser's output
is not verbatim text and I will not overturn a verbatim reading with it.** The existing spellings
stand everywhere. No worker changes an axis name, and W4 records the discrepancy as a
*question for the founder*, not a defect.

**R-G · `evidence/**`, `qa/**`, `infra/**`, `.github/**`, `spec/**`, `packages/**`, `tests/**`,
`verticals/**`, `docs/HONESTY.md`, `docs/CI-STATE.md`, `docs/submission/SUBMISSION.json`,
`docs/submission/MUST-NOT-CLAIM.md`, `docs/submission/RULES-MATRIX.md`,
`docs/submission/JUDGING-AXES.md`, `docs/TOOL-USAGE.md`, `docs/submission/EXTRA-CREDIT-CLAIMS.md`
and `README.md` are untouched by every worker in this wave.** **Authority:** each is another
domain's single write point, several are under the founder's explicit prohibition, and `README.md`
is the file most likely to be owned by a sibling lead this wave. **Where a worker finds a defect
in one of them it REPORTS it with the exact replacement text and hands it to the orchestrator.**
That is W4's standing job and any worker may add to its list.

**R-H · The new script W4 writes is not wired into CI.** **Authority:** the no-regression rule.
Baseline is `1070` collected / `1069` passed / `0` failed / `0` errors and a new lane is the
cheapest way to break it at T-1 day. W4's checker is a standalone tool with its own `--self-test`
that plants a broken link and asserts the checker refuses. It is added to no workflow.

**R-I · `capture_tool_evidence.py --check` will report `STALE` on `files_scanned` after this
wave, and that is expected.** **Authority:** `DEVPOST.md`'s own words — *"a `STALE` naming only
`files_scanned` is a tree that grew, not a verdict that moved"*. Every worker adds files.
**Nobody regenerates `evidence/tool-usage/` to make it green** — that file is another domain's
and regenerating it is how a green gets bought. W4 records the expectation so a later reader does
not meet it as new breakage.

**R-J · Nothing is promoted.** Agent Skills stays `DESIGNED`. Bedrock stays *real in this
repository and not in the demo's request path*. The change request stays *no admission beat*.
Managed MCP stays `15` of `16` at `DIVERGED — KNOWN GAP`. **A verdict that moves in this wave is
a defect in this wave.**

---

## 3 · THE COMPLETENESS TABLE — every field, and its state today

Requirements 1–7 are the contest's own, verbatim from §0. The rest are Devpost's standard form.
**Where a form field's exact name cannot be verified without logging in, it is marked so and the
copy is written anyway** — a field we prepared for and did not need costs nothing; the reverse
costs the submission.

| # | field | state today | owed |
|---|---|---|---|
| 1 | public repo URL, README, deps, setup | **MET** — public, Apache-2.0, `LICENSE` tracked, 11 357 bytes | W4 re-verifies |
| 2 | functional demo URL | **MET** — answered from outside our network today (§0) | W4 re-verifies |
| 3 | video < 3 min, publicly visible on YouTube/Vimeo | **NOT DONE** — `video_url` is `UNRESOLVED`; only the founder can close it | W4 makes the **Unlisted-not-Private** instruction unmissable |
| 4 | which CockroachDB tools, and how | **MET** — `docs/TOOL-USAGE.md` | — |
| 5 | which AWS services, and how | **MET** — same | — |
| 6 | **optional** — architectural diagram: CockroachDB × AWS × the agent | **UNMET IN SUBSTANCE** — the only diagram has no AWS and no agent | **W5** |
| 7 | **optional** — feedback on the CockroachDB AI tools | **ABSENT** — no such document exists | **W2** |
| — | elevator pitch (200 char cap) | MET — `163` characters | — |
| — | About the project — the seven standard headings | MET, and **unreadable cold** | **W1** adds layer 1 in front |
| — | Built With | MET — `27` tags, `EXERCISED` rows only | — |
| — | Try it out links | MET — repo + demo | W1 enumerates |
| — | Testing instructions / judge credentials | resolved in `SUBMISSION.json`; **no paste block exists** | **W1** |
| — | image gallery / thumbnail (*field name unverified*) | **EMPTY** — and with no film yet, it is the only visual a judge gets | **W5** |
| — | the story of how we got here | **ABSENT** — founder ask #2 | **W6** |

---

## 4 · THE UNDER-SOLD RARITIES — what W3 places, and the one test each had to pass

Each is real, committed, verified today, and **absent from the two pages a judge opens first.**
They are placed by quotation of an existing artefact. **No new run is authorised for any of them.**

1. **A CI lane that plants a defect and proves the hermetic lane could not have seen it.**
   `docs/ci/anti-vacuity.md` — one row per workflow, asking whether the lane can prove it is
   *able to fail*. `7` of `18` workflows carry a standing negative control after that wave,
   against `3` before it, **and the table names the `8` that still have none.** The rare clause
   is the last one: *an assertion that a program failed, without checking why, passes when the
   program fails to start.*
2. **A regression guard that caught a stub in the database's own privilege function.**
   `docs/regression/GUARD.md` §*Two things this guard found on its first run*. Plant P2 was built
   to make `has_function_privilege` answer `false` after a real `REVOKE`. It answered `true` —
   for that role, for `root`, for `admin`, for `public` — while the behavioural truth of the same
   call was `REFUSED 42501`. **Found by a planted violation before the guard had ever run in
   anger**, and replaced with `SHOW GRANTS` plus explicit role-membership expansion, which can go
   red.
3. **Honesty documents that name what is not built.** `docs/HONESTY.md`, `docs/CI-STATE.md`, and
   `DEVPOST.md`'s *Limitations* — eleven gaps, each with the command that re-derives it.
   **Untouched by this wave; quoted, never softened.**
4. **A refusal that returns a minimal unsatisfiable set and the nearest admissible alternative** —
   and returns `naa_reason: "not_computable"` rather than inventing one when it cannot compute it.
   Live and anonymous on `POST /v1/demo/gate-run`.
5. **A severity that a trigger derived from blame closure rather than a human typing it** — the
   client supplied `0`, the trigger projected `4` onto a row the client never touched.
   `evidence/gate-refusal/proof-20260810T054407Z.json#projection`, `10` of `10` assertions.

**The test every one of them had to pass to be on this list, and the two proposals that failed
it.** *Can it be finished and verified before the deadline without risking a working demo?*
**RECOMMENDED AGAINST:** deploying `operator.html` so the two screens exist on the origin (a
redeploy — prohibited, and `README.md` already publishes the gap); and re-running the mutation
ratchet or the regression guard for fresher numbers (a fresh red at T-1 day is a cost with no
upside, and both are standing measurements with committed artefacts).

---

## 5 · THE SIX WORKERS — disjoint, literally enumerated

No path appears twice. **Every brief carries the readability bar and the no-overclaim rule.**

| # | worker | owns, exactly |
|---|---|---|
| **W1** | The Devpost form, every field including the optional ones | `docs/submission/DEVPOST.md` |
| **W2** | The CockroachDB findings — the feedback requirement, actually answered | `docs/upstream/COCKROACHDB-FINDINGS.md` |
| **W3** | The five rarities, where a judge lands | `docs/submission/JUDGE-START.md`, `docs/submission/FIRST-FIVE-MINUTES.md` |
| **W4** | The mechanical sweep nobody runs until it is too late | `docs/submission/MECHANICAL-SWEEP.md`, `scripts/submission/check_doc_links.py` |
| **W5** | The architecture diagram, and the gallery a judge sees instead of a film | `docs/submission/DIAGRAMS.md`, `docs/submission/diagrams/architecture.svg`, `docs/submission/diagrams/story.svg` |
| **W6** | The story of how we got here, and the ledger that keeps it honest | `docs/submission/HOW-WE-GOT-HERE.md`, `docs/submission/COMPLETENESS-LEDGER.md` |

**Ordering.** W2 and W5 first — they are the two optional requirements and they are the only
items on this board that are *absent* rather than *unreadable*. W1 depends on both (it pastes
what they produce) and runs after them. W3, W4 and W6 are parallel; **W6 runs its ledger last**,
reads every other worker's output and edits none of it.

**Every new file carries an inline SPDX header** in the comment syntax of its format —
`<!-- … -->` for Markdown and SVG, `#` for Python — matching the tree's existing convention. **No
`.license` sidecars**; those are for JSON, which none of these are.

---

## 6 · THE FOUR RULES EVERY WORKER OBEYS

1. **THE READABILITY BAR.** A non-technical reader must understand the problem, why it matters,
   and what we built, in sixty seconds — concrete before abstract, a person and a situation and a
   consequence before any mechanism. **No term is used before it is defined** (the list is in §1).
   **No marketing voice** — "revolutionary", "seamless", "unprecedented" would destroy more
   credibility than any missing feature. **Layering is additive (R-A): you add layer 1 in front,
   you never delete a precise claim to make room for a friendly one.** If a sentence cannot be
   both true and simple, write two sentences.
2. **NO OVERCLAIM.** Never claim a service, feature, tool or number that did not actually run.
   Agent Skills is **DESIGNED**, not exercised. Bedrock runs **in this repository and not in the
   demo's request path** — both halves of that sentence, always. The change request has **no
   admission beat** and says so. Managed MCP is **`15` of `16`** at `DIVERGED — KNOWN GAP`. Every
   number carries the artefact that produced it, **even in layer 1** — moved to a footnote or a
   link, never dropped. Digits inside `code spans` are names, not measurements.
3. **NO REGRESSION.** Baseline **1070 collected / 1069 passed / 0 failed / 0 errors**. Gate proof
   stays `PROVEN`, caveats none. `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` does not move. Do not
   weaken `HONESTY.md`, `CI-STATE.md` or any ratchet. Do not widen a database grant. Do not add a
   CI lane. `continue-on-error` and `|| true` are banned.
4. **NO DEPLOY, NO COMMIT.** Never `terraform apply`, never redeploy, never touch AWS, never write
   an SSM parameter, never print a credential. Read-only HTTPS `GET` against the public origin is
   the only network access permitted. **Leave the tree for the orchestrator.**
