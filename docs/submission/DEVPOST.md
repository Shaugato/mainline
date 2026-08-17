<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DEVPOST — the text the founder pastes into the form

**Everything between a `<!-- PASTE -->` marker and the next horizontal rule goes into the
Devpost field named in the heading above it.** Nothing else on this page is submitted: this
preamble, the blockquote notes and the checklist at the foot are for the person filling in
the form.

**Every number in the paste blocks names the artefact that produced it**, in the style of
[`docs/HONESTY.md`](../HONESTY.md). Digits inside `code spans` are *names* — `v26.2.5`,
SQLSTATE `23514`, a setpoint of `150` — not measurements. A bare number is a measurement and
carries its file. If you edit a number, re-derive it first; the discipline is the product.

Measured over the paste blocks only on `2026-08-17`: **20 blocks, 13,450 words**, elevator
pitch **163 characters** against a cap of 200, one sentence. *It read **16 blocks, 11,194
words** on `2026-08-16`, and the `2,256` words between the two readings are four new blocks
and no edit to any old one* — a sixty-second opener that goes above *Inspiration* and replaces
nothing under it, the architecture caption that answers optional requirement 6, the CockroachDB
feedback that answers optional requirement 7, and the testing instructions the rules' access
clause asks for, which this page had never carried as pasteable copy. **Not one of the sixteen
earlier blocks was rewritten, shortened or re-ordered**, which is why the elevator-pitch
character count below is unchanged and why the five criterion blocks still stand where they
stood. *The `11,194` figure read `10,575` earlier on `2026-08-16` and was re-derived with the
command below rather than left standing. The `619`
words between those two readings are almost all in the axis-1 block: the live STORE → RETRIEVE
→ ACT loop with its committed transcript, the refusal's MUS and NAA including the third beat's
`naa_reason: "not_computable"`, a paragraph scoping the criterion's own words "production-grade
role as the agent's memory layer" to the memory layer, and a replaced `OPEN THIS TO CHECK IT`
line that is now an anonymous `curl` — plus one sentence in "Accomplishments" naming a stub the
regression guard's plant caught. Axis 4 was not touched in that pass and not one word of its
concession was softened; the axis-1 scoping paragraph says so in the block itself.*
**The sixteenth block is new and
it is the close block, *What actually ran*** — the two censuses read out row by row with the
verdict each carries, which is where the `2,922` words of the pass before this one went. *That figure was
written as `10,436` an hour earlier in this same pass and was re-derived rather than left,
after the CockroachDB section grew a paragraph separating the hackathon's four named tools
from the census's four tool rows — a distinction whose absence would have read as a
double-count. The stale figure is named here for the same reason every other one on this page
is.* It exists because
"we used AWS and CockroachDB" is a claim a judge cannot check and "these `6` AWS rows and
these `12` CockroachDB rows carry `EXERCISED`, and these `7` carry `DESIGNED`, and here is
the file that says so" is a claim a judge can check in a minute. The same pass took nine tags
out of *Built With* and one false one — `opentofu` — off the page entirely.
It read **7,653** earlier on `2026-08-16` and **7,234** on
`2026-08-15`; the `419` words between those two are the Managed-MCP correction in *Product
Readiness*, where this page had written that over MCP *"the read path contains none of our
code"* — a claim `evidence/mcp/auditor-live.json` refuses in the very field it was drawn
from, because the client that sends the request is ours. The corrected sentence is longer
than the wrong one, which is the usual direction here. That figure read **6,583** on
`2026-08-14`; those `651` words are the corrections in *How we built it*, *Limitations* items
(6) and (7), *Technological Implementation* and *Product Readiness*, each of which now
carries both the reading it used to give and the one the artefact gives today — this page
grows when a claim is corrected rather than shrinking when one is deleted, and the direction
is deliberate. Three earlier versions of this
line said 3,415, then 4,837, then 5,718 words. **The 4,837 had already drifted before it was
replaced** — the same command below returned 4,873 against this file on the morning of
2026-08-14, so somebody had edited a paste block and not re-derived the line that counts
them. It is named rather than quietly overwritten, because a page whose *first* number is
stale has taught a reader nothing about the rest. **The 5,718 was accurate when written and
was re-derived, not re-typed, when *Limitations* took six more gaps** — `demo_url` and
`video_url`, the acceptance run's HTTP target, the conformance suite, the reference vertical,
the console lane, and the owed Cloud run. The *Limitations* block and the five axis
blocks are what grew, which is the direction this page is allowed to grow in. Re-derive all
three with:

```bash
python -c "import re;t=open('docs/submission/DEVPOST.md',encoding='utf-8').read();b=re.findall(r'<!-- PASTE -->\n(.*?)(?=\n---\n)',t,re.S);print(len(b),sum(len(x.split()) for x in b),len(b[0].strip()))"
```

That total sits above the 1,400-word drafting guide and is recorded rather than rounded.
**The five criterion blocks are the ones that must not be cut**: the rules weight the five
judging criteria equally, each block is the only place one of them is answered directly, and
each is written to be read *alone* — a judge scoring axis 3 should never have to read axes 1,
2, 4 and 5 to find it. Every axis block ends with a line beginning `OPEN THIS TO CHECK IT`
naming the one committed path a sceptic would open to falsify it.
If the total must come down, cut *Challenges* and *How we built it* first — the artefact
detail they carry is duplicated at greater length in
[`JUDGING-AXES.md`](JUDGING-AXES.md) and [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md). **Do not
cut *Limitations*, do not cut the five axis blocks, and do not cut *What actually ran*.** A
submission that surfaces its own gaps outscores one where a judge finds them — and the close
block is the only place the two censuses are read out with their verdicts attached, which is
the difference between naming a service and evidencing one. **If *What actually ran* must be
shortened, shorten the bases and never the verdict labels**: a row that loses its `DESIGNED`
is a promotion, and a promotion is the one edit this page forbids outright.

> **THE FUNCTIONALITY RULE MAKES EVERY SENTENCE BELOW A PROMISE.** The Official Rules say the
> Project *"must function as depicted in the video and/or expressed in the text description"*,
> so a judge may treat any observable claim on this page as a test to run, and one aspirational
> line discredits the rest. Every observable claim was therefore classified on `2026-08-16`
> into one of three kinds, and the kind is stated in the text wherever it is not obvious:
>
> 1. **Reachable on the deployed origin, with no credential.** Measured with `curl` on
>    `2026-08-16` against the Function URL that [`SUBMISSION.json`](SUBMISSION.json) names —
>    not read out of an artefact. `GET /v1/health` answered `ok true`, `database
>    mainline_demo`, `cluster_version CockroachDB CCL v26.2.5`, `deploy_chain_applied 271` of
>    `deploy_chain_files 271`. `POST /v1/demo/gate-run` answered four beats — `00000`, then
>    `23514 gate_closed_when_issued`, then `P0001 mainline.fn_permit_merge_gate` against a
>    counter forced to zero, then `00000` — at `verdict PROVEN` with `failures []`,
>    `transaction.isolation SERIALIZABLE`, `single_transaction true`, `disposition
>    rolled_back`, `persisted false` and `self_persisted false`. `GET /v1/demo/subjects`,
>    `GET /v1/ledger`, `GET /v1/audit` and the console at `/console` each answered `200`.
> 2. **Real in this repository, measured, and not in the demo's request path.** True and
>    committed, but reproduced by *running something* rather than by opening the origin. This
>    page says so in those words wherever it applies. It is the construction the repository
>    already uses for Bedrock (`docs/demo/film/VO-CLOSE.md`, `docs/deploy/JUDGE-PACK.md`), and
>    it is a statement of scope, not a hedge: naming the boundary is what makes the claim
>    inside it worth anything.
> 3. **Not demonstrable.** Deleted, or restated as the smaller thing that is.
>
> **The two route instructions a reader can get wrong in under a minute.**
> `/v1/demo/gate-run` is **POST-only** — send `curl -X POST`. A `GET` to it comes back `405`,
> and a `405` is that route declining a method, which only a route that exists can do; it is
> not the path being absent. And the origin serves the console's document shell for any path
> it does not recognise, so a `200` from a path invented on the spot is that shell rather than
> an endpoint — **read the body, not the status code.** No instruction on this page sends a
> reader to a `GET` the origin answers differently.

> **ONE URL is unresolved as this line is re-derived, and it was two until `2026-08-16`.**
> Read on `2026-08-16`, `SUBMISSION.json` carries a resolved `demo_url` — the Lambda Function
> URL, which answered `200` to the probes recorded above — and still carries the literal
> `UNRESOLVED` in `video_url`, because the film has not been recorded. **The superseded
> reading is named rather than overwritten**: every earlier version of this note said *two*
> URLs were unresolved and that the checklist carried the literal string where each belongs,
> and that was true every day it was written. Do not invent the one that is still open, and
> **do not take either status from this note** — it is a snapshot of another worker's file
> taken at a moment, `SUBMISSION.json` is the single write point, and
> `python scripts/submission/check_submission_ready.py` is the measurement. The third URL is
> resolved: **the repository is public** at `https://github.com/Shaugato/mainline`, and it
> opens for a stranger with no account of ours. Re-derive it —
> `gh repo view Shaugato/mainline --json visibility,licenseInfo` answers
> `{"visibility":"PUBLIC","licenseInfo":{"key":"apache-2.0"}}`, measured `2026-08-12` — and
> the root `LICENSE` is tracked, `11357` bytes, reading as Apache-2.0. Earlier versions of
> this note said the repository was `PRIVATE` and that a judge opening the URL would get a
> `404`. That was true when it was written and it is not true now.
> **Do not take the resolved/unresolved status from this note.** It is a snapshot;
> `python scripts/submission/check_submission_ready.py` is a measurement, prints one row per
> requirement with the literal command that resolves it, and exits non-zero while any row is
> outstanding. [`SUBMISSION.json`](SUBMISSION.json) is the single write point, and its owner
> is the only thing that changes a URL's value.

---

## The twelve words this page cannot avoid

**This section is not pasted anywhere.** It is here so the person filling in the form — and
anyone reading this file cold — can check a word without leaving the page. Every paste block
below either glosses these words in the same sentence it uses them, or does not use them. The
fuller vocabulary, twenty-four terms each with the table or route that makes it a real thing,
is [`docs/architecture/GLOSSARY.md`](../architecture/GLOSSARY.md); no gloss here may
contradict one there.

| Word | In one clause |
|---|---|
| **obligation** | Something that has to be settled before a permit may be issued — usually a past incident this job resembles, attached to the permit as a row. Table `mainline.blocking_check`. |
| **disposition** | The signed answer to exactly one obligation: a named competent person recording what they did about it. It is the only way an obligation closes. Table `mainline.disposition`. |
| **precursor** | The earlier event an obligation points back at — the incident this job resembles. It is what carries the severity that arms the refusal. |
| **blame ancestry** | The chain of earlier versions and earlier incidents a rule descends from, walked as a graph at the moment the question is asked. `git blame`, for a safety rule. |
| **projection** | A value the database writes onto a row *by itself*, derived from other rows, overwriting whatever the writer supplied. The count of open obligations on a permit is one. |
| **epoch** | A counter on the permit (`gate_epoch`) that goes up every time a new obligation arrives, so an obligation that turns up after a permit was issued cannot be quietly attached to it. |
| **SQLSTATE** | The five-character code a SQL database returns to say what it did — `00000` accepted, `23514` a `CHECK` rule refused it, `P0001` a stored procedure refused it. The code comes from the database; an English message could come from anywhere. |
| **synchronic** | Judged on how the world is **now**: isolation in place, gas test in date, signature present. That is every permit system shipping today. |
| **diachronic** | Judged on how it **got here**: why does this rule say 135, and who paid for that number. |
| **MUS** | Minimal unsatisfiable subset — the shortest set of facts that together force the refusal. Drop any one of them and the write would have gone through. |
| **NAA** | Nearest admissible alternative — the closest version of the request the database **would** have accepted. Where it cannot be computed the answer is `null` with a reason attached, never a guess. |
| **C-SPANN** | CockroachDB's vector index type, used here to find the past incidents a new job resembles. |

---

## Elevator pitch

<!-- PASTE -->

Every permit system gates on the present; MAINLINE gates on ancestry — the database refuses the merge until someone signs against the incident that wrote the rule.

---

## Read this first — the sixty-second version

> **THIS BLOCK GOES AT THE VERY TOP OF THE *About the project* BODY, ABOVE *Inspiration*.**
> It is the only block on this page written for a reader who has never seen the project and
> does not work with databases. It uses no term it has not just defined, and every fact in it
> carries the file it was transcribed from. **It replaces nothing** — *Inspiration* and
> everything after it stay exactly as they are, underneath it.

<!-- PASTE -->

**Read this knowing the story is invented.** Kestrel Resources is fictional and `INC-2013-044` never happened. The mechanism is real; the inputs were written by us (`docs/HONESTY.md` § SYNTHETIC).

In 2011 a gas plant sets the high-temperature alarm on a compressor seal to 150 °C. On `2013-06-12` that seal catches fire and two contractors are burned; nobody dies. On `2013-08-04` an engineer lowers the alarm to 135 °C, saving one line with the change: *"Lowered 150 → 135 after seal fire INC-2013-044 — two contractors burned."* Then ordinary things happen to that rule: in 2016 it is renumbered from 7.3 to 5.2.1, in 2019 it moves into another standard and becomes 9.2.1, and in 2021 the engineer leaves the company.

Today somebody proposes putting the alarm back to 150 °C. They are not careless: the manufacturer specifies 150, and 135 trips alarms on hot afternoons that people have started ignoring. The rule on their screen says *"shall be set at 135 °C"* and gives no reason.

**Every permit-to-work system we surveyed approves that change** — six commercial products, read against the thirteen essential elements of a permit form that the UK Health and Safety Executive's HSG250 lists (`docs/demo/research/r3-operator.md` §1–§2; we could not obtain screenshots, so this is what their documentation states). A permit to work is the written authorisation without which nobody starts a dangerous job, and all of them ask one question: *is the world all right at this moment?* Isolations in place, gas test in date, ticket valid. Every one of those checks passes, because nothing about the plant today is wrong. None of them can answer *why is this limit here.*

**MAINLINE makes that answer a condition of the write.** Every rule carries a pointer to the event that caused it to be written. Issuing a permit is handled the way a change to source code is handled — as a merge — and before it lands, the database looks up what wrote each rule the job leans on. Any earlier event nobody has answered for becomes an **obligation**: one open question attached to that permit. While it is open, **the database refuses to record the permit as issued.**

*Refuses* is the load-bearing word. Not a banner beside an Approve button, which a tired person dismisses at 04:00; not a check in our application, which a migration script would go around. It is a rule inside CockroachDB, applied to every writer including us — switch our screens off and the permit still will not issue. A named competent person must first sign what they intend to do about the 2013 fire; that signed answer is a **disposition**, and once it exists the same merge goes through.

An old lesson a new job cannot get around, enforced by the database rather than remembered by a person. **Check it in a minute, with no account of ours:** `POST /v1/demo/gate-run` on the demo URL replays that argument in four steps and ends in `ROLLBACK`, so `persisted` comes back `false` and your visit leaves nothing behind.

*Dates, setpoints and the quoted line are transcribed from `spine.json` and `CAMERA-STRINGS.yaml` under `verticals/mainline/` (`commit_message_2013`, asserted byte-equal across four files). The refusal is `23514 gate_closed_when_issued` [src: `evidence/gate-refusal/proof-20260810T054407Z.json`]. The invented incident is severity `4` — two contractors, partial-thickness burns.*

---

## Inspiration

<!-- PASTE -->

*(The scenario is invented — Kestrel Resources and Marrindal are fictional and `INC-2013-044` never happened. The mechanism is real; the inputs are authored.)*

An engineer raises a compressor alarm setpoint from `135` back to the manufacturer's `150` — a routine change, technically correct, and every permit-to-work system we surveyed would approve it. MAINLINE runs `blame` on the clause instead. A seal fire burned two contractors on `2013-06-12`; the alarm was lowered because of it on `2013-08-04`, with the message *"Lowered 150 → 135 after seal fire INC-2013-044 — two contractors burned."*; and that author left the company on `2021-07-16`. The permit merge is then **mechanically refused by the database** — not flagged, refused — until a named competent person signs a disposition against a thirteen-year-old fire.

Every shipping permit system is **synchronic**: it gates on the current state of the world — isolation in place, gas test valid, signature present. None can express *why* a rule says what it says, so the memory of an incident decays to nothing the day its author resigns. MAINLINE is **diachronic**: it gates on **ancestry**. Recall is therefore not a panel beside the decision but a **precondition of the state transition**, enforced under `SERIALIZABLE`. A document shown next to an "Approve" button is a UI nag, and a UI nag gets dismissed. An invariant does not.

---

## What it does

<!-- PASTE -->

MAINLINE holds institutional safety memory as a version-controlled repository whose commits are written by incidents. Every clause carries a blame pointer to the event that wrote it, the permit-to-work is a protected branch, and one rule is enforced as a **database refusal**: a permit may not reach `merged` while a recalled precursor carries an obligation nobody has signed. Being a refusal rather than application logic, it holds against psql and a back-office correction alike.

The mechanism is three steps, specified normatively in `spec/TRAPPOINT-SPEC.md` §2 and shipped as a CockroachDB Agent Skill:

- **PROJECT** — a trigger writes the cross-row fact onto a *scalar column of the subject row*, derived from an authoritative relation, **never from the inserter**.
- **PIN** — a completed transition takes a composite foreign key onto `(subject_id, gate_epoch)`; any new obligation increments the epoch, and `ON UPDATE RESTRICT` makes attaching one to a completed transition *physically impossible*.
- **REFUSE** — a plain-column `CHECK` over that scalar refuses the write, for every writer, forever.

`just prove` applies the chain and attempts the merge three times. Reproduced in a scratch database while writing this:

```
chain       271/271 applied, 0 failed, 51.498s
REFUSAL     REFUSED [23514] gate_closed_when_issued (reported)
DRIFT       REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION   ADMITTED [00000]
VERDICT     PROVEN
```

The middle beat is the claim **under attack**: the projected counter was forced to zero out of band, and the gate refused anyway, because it *re-derives* the count instead of trusting the column handed to it. The third matters as much — the same history is admitted once a disposition is signed, because a gate that always refuses is broken, not safe (`evidence/gate-refusal/proof-20260810T054407Z.json`).

**That transcript is `just prove` on a laptop: real, measured, and not in the demo's request path** — it wants a clone and a local node, and it is worth running for exactly that reason, because it needs no account of ours. **The same beats also come back over HTTP from the deployed origin, and that half needs neither.** `POST /v1/demo/gate-run` answers `00000` → `23514 gate_closed_when_issued` → `P0001 mainline.fn_permit_merge_gate` → `00000` at `verdict PROVEN`, inside one `SERIALIZABLE` transaction ending in `ROLLBACK`, so `persisted` comes back `false` and asking the question leaves nothing behind. Send it as a `POST`; the route declines a `GET` with `405`.

---

## How we built it

<!-- PASTE -->

The database is not a datastore under this system — it is the system. `docs/TOOL-USAGE.md` documents **4 CockroachDB tools**, inside which **10 engine features** are separately accounted (counting a feature as a tool to clear a bar is the arithmetic this repository exists to refuse), and **12 AWS services**, each carrying a verdict of EXERCISED, DESIGNED or NOT-AVAILABLE plus a file-and-line anchor.

**CockroachDB `v26.2.5`, and the four tools identified in the order the criterion enumerates them.** The Technological Implementation criterion names three — *"distributed vector index, MCP Server, ccloud CLI"* — and the submission requirement separately names a fourth, Agent Skills. So they are identified in the criterion's order, and the fourth is identified as the extra it is. **Three are EXERCISED against a floor of two; the fourth is DESIGNED and is labelled DESIGNED rather than rounded up.** Every verdict below is read out of `evidence/tool-usage/crdb-features.json`, which carries one per row with the basis that earned it — not out of this paragraph.

- **Distributed Vector Indexing — `EXERCISED`.** C-SPANN vector indexes declared inline at `CREATE TABLE` and searched under a bound prefix. The plan that proves the index is actually *chosen* names `clause_embedding@ce_ann` with both prefix columns bound, with the `EXPLAIN` committed beside it (`evidence/aws/ann/ann-proof.json`, `evidence/aws/ann/explain-hinted.txt`). The census files this as a feature row rather than a tool row; the verdict is the same either way. Real, measured, **and not in the demo's request path** — the deployed origin's four beats are pure SQL and call no index and no model.
- **Managed MCP Server — `EXERCISED`.** Two sessions against `https://cockroachlabs.cloud/mcp`, protocol `2025-06-18`, `tools/list` returning `12` tools, running as the server's own SQL identity `managed-mcp` against live Basic cluster `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`. Both put the same `16`-question pack and both reach **`15` of `16` PASS at verdict `DIVERGED — KNOWN GAP`** — `evidence/deploy/judge-run.json` on `2026-08-11` and `evidence/mcp/pack-run.json` on `2026-08-16`, five days and one deployment apart. **The one FAIL is `N01` and it is preserved rather than rounded off**: the `managed-mcp` identity can read `mainline_qa.v_disposition_profile`, which the pack asserted it could not. `15` of `16` is not `16` of `16` and this page will not print it as one. Real, measured, and not in the demo's request path — the credential that opens that endpoint is account-level and unpublishable, which is why it is not the judge access route.
- **`ccloud` CLI — `EXERCISED`.** `evidence/ccloud/cluster-list.txt` is a captured `ccloud auth whoami` + `ccloud cluster list -o json` transcript against `mainline-dev`. Real, measured, and not in the demo's request path; `ccloud` `0.6.12` has no headless authentication, which is why it is a committed transcript rather than a lane.
- **Agent Skills — `DESIGNED`, and the census says so rather than us.** Two skills are on disk, each shipping an executable assertion script that fails when its guarantee stops holding. **No run of either script is captured under `evidence/`**, so the row reads `DESIGNED` in the census's own words — *"they are shipped and not evidenced"*. The skills are real files a judge can read and run; what is missing is a captured run, and the verdict column says exactly that. This is the fourth tool beyond a floor of two, and it is not promoted to make a list look longer.

The gate needs `SERIALIZABLE` — it reads before it writes, and anything weaker is a write-skew hole — plus PL/pgSQL triggers, named `CHECK` constraints whose *name* is the deliverable, and `SHOW CREATE` with `pg_get_triggerdef()` chained into a schema attestation, so nobody quietly weakens the gate that prevents quietly weakening controls. The rest: C-SPANN vector indexes inline at `CREATE TABLE` for recall, `AS OF SYSTEM TIME` and follower reads for the fixity patrol, row-level security with `FORCE`, `crdb_internal` for the HLC ordering the ledger, and CHANGEFEED, which is DESIGNED.

**AWS, and the two halves are not the same claim.** Bedrock for Claude inference and Titan embeddings in `ap-southeast-2`, the model id resolved at start-up from `ListInferenceProfiles` and pinned into the run record, so a residency violation fails loudly rather than silently reaching another region. **That half is EXERCISED.** `invoke_model` on `amazon.titan-embed-text-v2:0` and `converse` on `au.anthropic.claude-haiku-4-5-20251001-v1:0` return HTTP `200` with AWS request ids (`evidence/aws/probe/bedrock-probe.json`); the `1024`-dimension vectors those calls produced sit in a CockroachDB Cloud table and are searched through the C-SPANN index by a plan that names `clause_embedding@ce_ann` with both prefix columns bound (`evidence/aws/ann/ann-proof.json`, `evidence/aws/ann/explain-hinted.txt`); and AWS's own `AWS/Bedrock` CloudWatch counters record the invocations from outside this repository, which is the only piece of evidence here that we did not write about ourselves. **And the scope, stated plainly rather than left to be discovered: Bedrock is exercised in this repository and it is _not_ in the demo's request path.** The four beats the deployed origin answers are SQL against CockroachDB and nothing else — no model is called while a judge is looking. Both halves of that sentence are true and neither is separable from the other.

**The other half splits, and the split is the honest part.** Of the `12` service rows in `evidence/tool-usage/aws-services.json`, `6` are EXERCISED, `5` are DESIGNED, and `1` — Bedrock Rerank — is NOT-AVAILABLE in `ap-southeast-2` and is listed as such rather than dropped. Three of the six are the calls above; the other three are the **demo stack, applied on `2026-08-14`**: `evidence/deploy/APPLIED.md` records `terraform apply` returning *"24 created, 0 changed, 0 destroyed"*, and the Lambda Function URL it produced answers `GET /v1/health` with `ok true` and `deploy_chain 271/271` (`evidence/deploy/live-health.json`) and `POST /v1/demo/gate-run` with the four beats and verdict `PROVEN` (`evidence/deploy/live-gate-run.json`). **Those two are the reachable class**, and both were re-measured against the origin on `2026-08-16` rather than quoted from the artefacts that first recorded them — the health body still reads `ok true`, `database mainline_demo`, `deploy_chain_applied 271` of `271`, and the gate run still reads `verdict PROVEN` with `failures []` and `persisted false`. **The five that are still DESIGNED are the custody half, and it is the half that matters most**: S3 with Object Lock in COMPLIANCE mode, KMS for `ECC_NIST_P256` checkpoint signatures, CloudTrail for a digest chain we could not have forged, EventBridge for the steward's schedule — and CloudFront, which **cannot** be applied on this account at all. There is no MAINLINE evidence bucket, no signing key, no trail and no distribution. Re-derive the split with `python scripts/submission/capture_tool_evidence.py --check`, which reads no network and no credential and exits non-zero when a count **or a citation** in that census has gone stale. On `2026-08-14` it exited `2`: two AWS rows cited a line in `infra/modules/demo-api/main.tf` that no longer held the thing they cited it for, and the generator refuses to write while an anchor has drifted off its subject. Both anchors were re-pointed **in the generator**, which is the authoritative side, and both censuses regenerated from it; nothing under `infra/` was edited to make a citation true. Read the per-service verdicts from the census rather than from this paragraph.

---

## Challenges we ran into

<!-- PASTE -->

**A defect census built from error messages measures what the error messages can express.** Seven tables had consumers — triggers, views, RLS policies — and no producer migration. Classified by SQLSTATE the count read **five**, and it was wrong: CockroachDB names only the *first* absent relation in a statement, so one table sat shadowed behind another in both views that joined them and never appeared in an error string anywhere. The durable fix is not the seven files but the lint that now differences every schema-qualified reference against every relation the tree creates, so the eighth instance fails at lint time instead of deployment time.

**The measurement everyone quoted was not the measurement a deployment performs.** The chain figure published for days came from a *continue-on-error census*; the forward-only runner a deployment actually uses halts on the first refusal, and it halted early, leaving the version dirty. Both now complete: `271` of `271` files, `0` failed, nothing dirty, attestation head ordinal `271` at grade `strong` (`evidence/chain/chain-20260810T062542Z.json`), up from `246` of `261` with `15` failing. That earlier artefact stays in the tree rather than being deleted.

**Platform facts, published rather than smoothed over.** `P0001` carries no `diag.constraint_name`, so the raising object is recovered from message text — the proof records whether an exhibit was `reported` or `parsed`, the difference between a diagnosis and a guess. `ccloud` `0.6.12` has no headless authentication and Cloud audit-log endpoints `404` on Basic, so "custody of the custodian" is documented as unavailable rather than shipped as an unbacked claim.

---

## Accomplishments that we're proud of

<!-- PASTE -->

**The honesty mechanism is executable, and we can show it going red and then going green for the right reason.** `tests/release/test_honesty_is_checkable.py` fails the build when a number in `docs/HONESTY.md` and its cited source disagree, when a cited file is gone, or when a number carries no reference at all. One rule runs the other way: it fails when evidence *appears* that the prose has not absorbed. On `2026-08-10` it gave `1 failed, 33 passed`, naming the two artefacts that had landed within the hour — the completed forward-only chain run, and the first conformance census — because a document that lags its own evidence is a document that will eventually overstate. Re-run on `2026-08-12` it gives `34 passed`, `0 failed`: the prose absorbed both. A red build is the correct response to evidence a document has not caught up with, and the green that follows is only worth something because the red was real. That is why the central claim above is worth believing: verdict `PROVEN`, three beats, zero caveats, reproducible with no credential of ours. **And the same discipline caught a defect in our own checking before the regression guard it belongs to had ever run in anger:** `has_function_privilege` is a stub on CockroachDB `v26.2.5` — it answered `true` after a real `REVOKE`, for that role and for `root` and for `admin` and for `public`, while the behavioural truth of the same call was `REFUSED 42501`, so a check built on it cannot fail and a check that cannot fail is decoration; it was found by a planted violation rather than by a failure in production, and replaced with `SHOW GRANTS` plus explicit role-membership expansion, which *can* go red (`docs/regression/GUARD.md` § *Two things this guard found on its first run*).

---

## What we learned

<!-- PASTE -->

**A truthful red beats a fabricated green, and it is cheaper to defend.** Every quality number here is a *ratchet*: `671` `ruff` findings and `0` files `ruff format` would rewrite (`qa/ruff-ratchet.json`, keys `lint.total` and `format.unformatted_files`; an earlier version of this page said `847` and `245`, and both fell), `0` `mypy` errors over `660` checked source files (`qa/mypy-ratchet.json`) — and that zero is worth nothing without the count beside it, because a checker that ran nothing also prints zero. Frozen, published, free to fall but not rise, and gated per rule so a change cannot buy its way past with a headline total.

**A skill whose advice cannot be falsified is a blog post.** Both CockroachDB Agent Skills ship an executable assertion: one replays an illegal history and fails unless the expected SQLSTATE *and* constraint name are raised; the other fails unless the query plan actually chooses the vector index. **And the verdict on that tool is `DESIGNED`, not `EXERCISED`, because shipping an assertion is not the same as capturing its run** — `evidence/tool-usage/crdb-features.json` records *"they are shipped and not evidenced"* and this page does not upgrade it. The scripts are in the tree and a judge can run either one; what nobody can do is open a committed transcript of us having done so, and that is the whole distance between the two verdicts.

**Absence of evidence refuses; it never admits.** Where the authority source holds no row for a subject, the trigger must refuse — never default, infer or pass. That rule separates a safety gate from a workflow step.

---

## What's next for MAINLINE

<!-- PASTE -->

**Demonstrate the conformance suite, which has never been demonstrated.** What exists is a census, not a run: `qa/conformance-census.json` records `10` passed, `6` failed and `55` cannot-run over `71` selected cases, each cannot-run naming the object it lacked. Against a bare node the cases error rather than skip, which is why the cannot-run column is the tall one, and `docs/HONESTY.md` calls this the single largest gap between what this repository contains and what it has shown. Two of the declared cases — CF-01 and CF-03 — are exercised elsewhere, by `scripts/proof/gate_refusal.py`; that is a smaller claim than a suite run and it is the true one. `46` of the cannot-runs share one cause, a setup statement the database refused because a column does not exist, so one repair moves most of them.

**Land the cryptographic half of custody.** Offline bundle verification exits `2` on purpose: of `16` checks, `9` ran and held, `0` failed, and `7` did not run at all (`qa/test-state.json`, `external_checks.custody_bundle_verification`). The seven are the signature half — `log_signature`, `rfc3161_upper_bound`, `beacon_lower_bound`, `witness_quorum`, `archive_object_lock`, `gate_self_attestation`, `webauthn_reverification`. Exit `2` is the tool refusing to let nine passes be read as a verified ledger.

<!-- no-bare-point-estimates: allow - both numbers are DDL wall-clock seconds from evidence/deploy/, not retrieval metrics; the sentence exists to say the hop is UNMEASURED for retrieval, and the checker matches on the word it uses to deny the claim -->
**Deploy, and measure the hop.** The one cross-region cost measured so far is DDL, not recall: `359.1` seconds for the chain against Singapore versus `46.35` locally for the same files (`evidence/deploy/`). Neither is a retrieval measurement, and this repository publishes no interval for that hop because nobody has taken one.

---

## Limitations — read this before you believe any of it

<!-- PASTE -->

**`docs/HONESTY.md` publishes what is broken, counted, with the command that re-derives each number.** It is the first thing we would want a judge to open; burying it would contradict the entire pitch. What follows is not a footnote — it is the part of this submission we would most want scored, because a judge who finds a gap we did not name should discount everything we did.

**Five gaps, each with the artefact that measures it.** (1) **Custody is half-built.** Offline bundle verification exits `2`, not `0`: of `16` checks, `9` ran and held, `0` failed, and `7` did not run at all — `log_signature`, `rfc3161_upper_bound`, `beacon_lower_bound`, `witness_quorum`, `archive_object_lock`, `gate_self_attestation`, `webauthn_reverification`, which is the entire cryptographic half (`qa/test-state.json`, `external_checks.custody_bundle_verification`). What is verified is the Merkle structure, never the signatures over it. (2) **The MI invariant ratchet measures `21` of `30` pending, and `9` enforced** — re-derived by running `python scripts/mi_ratchet.py`, whose last line reads `21 pending / 9 enforced`. The intentional-red message in `.github/workflows/ci.yml` said `28 of 30` for as long as it took nine invariants to be promoted underneath it; that string has been corrected to `21` at `ci.yml:702` and other documents in the tree are still being brought to the measured figure. Quote neither number from memory: run the script. (3) **CloudFront cannot be created on this AWS account at all.** A real apply on `2026-08-10` reached the distribution and AWS refused with `AccessDenied: Your account must be verified before you can add new CloudFront resources.` — verbatim, `RequestID` intact, in `docs/deploy/RUNBOOK.md` Appendix A, reproduced from a bare `aws cloudfront create-distribution` with no Terraform involved, by an identity holding `AdministratorAccess`. Only AWS Support can lift it, so the demo origin is a Lambda Function URL and the runbook is written as though the hold never clears. (4) **Master carries more red than a comfortable submission would.** `docs/CI-STATE.md` is the board and it names every workflow with its run id and a quoted log line; read on `2026-08-14` it states `18 workflows · 11 GREEN · 7 RED`, of which `5` are RED ON PURPOSE (`schema`, `db`, `demo-health`, `custody-chain`, `db-schema`) and `2` are red on a defect (`ci`, `nightly-differential`). Re-derived live on `2026-08-14` with `gh run list --branch master --limit 300`, taking the latest run of each: **`20` workflows, `8` success and `12` failure.** The two counts differ by the lanes CI-STATE says it does not credit — `cluster-tests` and `cluster-lane-bites`, both added since that board was taken — and that page states in its own words that nothing on it credits work still in the working tree. Neither figure was moved to agree with the other. **This bullet has carried three readings of the same command and keeps all three**: `8`/`10` over `18` workflows at commit `1d41442` on `2026-08-12`; `11`/`9` over `20` earlier on `2026-08-14`; and `8`/`12` over `20` after the `04:29Z` push on the same day. The board got worse between two runs of one command in one morning, which is the reason this bullet prints the command rather than a remembered number. (5) **The lane that finally runs our tests against a real database skips ten of them, against a ceiling of one.** Until `2026-08-13` every one of this repository's workflows passed `--crdb=none`, so each cluster-backed test in the product skipped and the suite that proves the central claim had never executed in CI at all — four separate NO-GO verdicts were reached on that basis. `.github/workflows/cluster-tests.yml` now starts a pinned `cockroachdb/cockroach:v26.2.5` container and runs the demo-api suite at `--crdb=reuse`; GitHub Actions run `31735341117` at `headSha eefae1c` measured `528` collected, `518` executed, `10` skipped, `1` failed, `0` errored — `1 failed, 517 passed, 10 skipped in 154.21s`. **That run's conclusion is `failure` and it should be.** The ceiling in `qa/cluster-known-red.json` is `max_skipped: 1` beside `min_executed: 440`, and the lane refuses ten in its own words: *a skip here means the suite could not reach the cluster this job started, and a skip is indistinguishable from a green tick on a dashboard.* The ten are the tree-reading halves of `test_response_contract.py` and `test_static_site.py`, which read `out/lambda/mainline-demo-api-arm64.zip` — a `.gitignore`'d build output the lane never builds — and their own skip text refuses the shortcut: *the packer's input tree is deliberately NOT accepted as a stand-in.* The answer is to build the package in the lane. It is not to raise the ceiling, and the ceiling has not been raised.

**Six more, named here rather than left for a judge to find.** (6) **This bullet said "the two URLs this submission needs are still `UNRESOLVED` in the file that governs them", and on `2026-08-16` that became a one-URL bullet.** Read that day, `docs/submission/SUBMISSION.json` carries a resolved `demo_url` — the Lambda Function URL — and still holds the literal `UNRESOLVED` in `video_url`. **The superseded reading is kept rather than overwritten, which is this page's rule for every number on it.** For `video_url` the reason is unchanged: the film has not been recorded, and no worker on this submission can record it. **For `demo_url` it is no longer true that there is no origin** — `terraform apply` ran on `2026-08-14`, `24 created`, and the Lambda Function URL it produced answers `ok true` (`evidence/deploy/APPLIED.md`, `evidence/deploy/live-health.json`). What is unresolved is the *submitted value*, not the deployment, and that is a distinction this page is required to keep: `SUBMISSION.json` is the single write point, it is not this page's to write, and a URL is submitted when its owner writes it there and not when a paragraph asserts it. `python scripts/submission/check_submission_ready.py` is the measurement, and **it has now printed three different readings and this bullet keeps all three**: on `2026-08-12` and again on `2026-08-14`, `NOT READY`, `3` unresolved rows of `10`, `0` NOT CHECKED — `demo_url`, `video_url` and `remote_sync`; on `2026-08-16`, **`NOT READY`, `2` unresolved rows, `0` NOT CHECKED, exit `1`** — `demo URL` now reads `PASS` naming the Function URL, `video URL` reads `FAIL`, and `remote is in sync` reads `WARN` on uncommitted paths, which is a working tree ahead of the server and clears on a push. **Take the reading from the program on the day you say it, never from this sentence.** Writing a hostname into that file before an origin exists is the single failure that file exists to prevent; taking one from this paragraph instead of from that file is the second. (7) **The acceptance harness has never met its contract against anything but a local emulator, and this bullet keeps all three of its readings.** It read: *"the four-beat run has never met its contract over HTTP — `evidence/deploy/acceptance.json` reads `"verdict": "NOT PROVEN"` at `generated_at 2026-08-13T01:47:58Z` with `10` named failures, and the target it reached was `http://127.0.0.1:8764` with `target_is_local_emulator: true`"*. **The committed file today says something different and the caveat survives intact**: `verdict` is `PROVEN` at `generated_at 2026-08-14T08:16:49Z` with `0` failures — **and `url` is `http://127.0.0.1:8792` with `target_is_local_emulator: true`**, so it is still a statement about a local emulator serving the unmodified handler and not about a deployed URL. `evidence/deploy/cloud-acceptance.json` is the same shape at `127.0.0.1:8791`. **What did land against the deployment is a different program's artefact and is named as such:** `evidence/deploy/live-gate-run.json`, the four beats answered by the public Function URL, verdict `PROVEN`, one `SERIALIZABLE` transaction ending in `ROLLBACK` — see the annotation under item (11). *Read the verdict the file carries when you open it, not the one quoted here — that pointer has now been wrong twice, in both directions.* (8) **The conformance suite has never been demonstrated end to end.** What exists is a census: `qa/conformance-census.json` records `10` passed, `6` failed and `55` cannot-run over `71` selected, because against a bare node the cases error rather than skip. Exactly two declared cases have been exercised anywhere — CF-01 and CF-03 — and by `scripts/proof/gate_refusal.py` rather than by the suite. (9) **The forkable half does not apply, and it is the same defect class as the seven tables that had no producer migration.** `trappoint_ref.clause` and `trappoint_ref.event` are referenced by the rendered SQL and created by no file in it, so `trappoint migrate up --tree trappoint-ref` refuses at `0058_blocking_check` with `42P01` — `docs/HONESTY.md` § *The reference vertical cannot be applied*, and red in the `schema` workflow. The seven unproduced tables were themselves invisible to a SQLSTATE census, because CockroachDB names only the first absent relation per statement; the count read five and the truth was seven. (10) **The console lane has never been observed running against the tree a judge would clone.** Its only green is GitHub Actions run `31699574592`, conclusion `success`, at `headSha 2dc5c86` — five commits behind the tip — dispatched `2026-08-13T12:20:40Z`, and `docs/CI-STATE.md` marks that row *"NO — five commits behind"* in its own is-this-the-tip column and lists `console` among the greens not audited for vacuity. **A green about a tree nobody is running is not evidence about this tree.** Re-derive with `gh run list --branch master --limit 300`; the row is cited by run id rather than by line number because that board is being revised as this is written. (11) **CockroachDB Cloud carries the world, and the Cloud run through the HTTP handler is owed.** The paragraph below is carried verbatim, in the same words, by `docs/STATE-OF-THE-BUILD.md`, `docs/HONESTY.md`, `docs/CI-STATE.md` and `docs/submission/JUDGING-AXES.md`, so that five documents cannot drift apart on one owed measurement:

> **CockroachDB Cloud carries the demo world, and the gate refuses there.** The migration chain is `APPLIED` and the seeded world is `SEEDED AND REFUSABLE` against `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`, database `mainline_demo`, CockroachDB CCL v26.2.5 — the refusal observed on Cloud is `23514` `gate_closed_when_issued`, with `nothing_persisted: true` [src: `evidence/deploy/cloud-chain.json#outcome`, `evidence/deploy/cloud-seed.json#verdict`, `#verification`].
>
> **The four-beat run through the HTTP handler has NOT been recorded against Cloud.** The operator reports it in the body of commit `7535670`; that commit's diff carries no such artefact, and `evidence/` holds none. **OWED:** re-run `scripts/deploy/…` against Cloud with `--out evidence/deploy/cloud-gate-run.json`, and only then may a Cloud `PROVEN` appear on this page. Until it exists, the only `PROVEN` this repository holds is `evidence/gate-refusal/proof-20260814T032418Z.json`, and it is **local** (`cluster.database = w_qr_gate_refusal_proof`).

**ANNOTATION TO ITEM (11), `2026-08-15` — written beside the block above and deliberately not inside it.** That owed measurement **has since been taken**, under a different filename than the OWED line names: `evidence/deploy/live-gate-run.json` is the four-beat run answered by the public Lambda Function URL over CockroachDB Cloud — `data.verdict` `PROVEN`, four beats `00000` / `23514 gate_closed_when_issued` / `P0001 mainline.fn_permit_merge_gate` / `00000`, `isolation SERIALIZABLE`, `single_transaction true`, `disposition rolled_back`, `persisted false` — with `evidence/deploy/LIVE.md` as its narrative. **The block is left word-for-word on purpose.** It is carried verbatim by four other documents so that five cannot drift apart on one owed measurement; none of those four is this page's to edit, and correcting one copy alone would break the only mechanism holding them equal. **The correction is owed on all five together**, and it is filed as owed in `docs/demo/ON-SCREEN-CLAIMS.md` § *Discrepancies filed, not smoothed*. Read the artefact, not either paragraph.

**And the boundaries that were always here.** The corpus is **authored** — the compressor-setpoint story is a designed worked example, no real incident, no real site, no real fatality. The agent suite still replays **recorded cassettes**, and a green run there says our code handles that recorded exchange — it is not a statement about a model today. Separately, and it is a different claim: Bedrock was genuinely invoked while this was written, and the transcripts are committed under `evidence/aws/probe/`. The reference-ledger keys are named `NOT-SECRET` because they are. **The custody half of the AWS surface is still not deployed** — no MAINLINE evidence bucket, no Object Lock, no KMS signing key, no trail, no MAINLINE distribution — so of the `12` AWS service rows in `evidence/tool-usage/aws-services.json`, `5` are still DESIGNED (`6` EXERCISED, `1` NOT-AVAILABLE); the demo stack was applied on `2026-08-14` and the evidence store was not, which is why the cryptographic custody checks in gap (1) still cannot run. **Nothing has ever run against CockroachDB *Cloud* in CI** — the cluster lane in gap (5) starts a pinned CockroachDB *container* on the runner, which is a real database and is not the managed one, and the difference matters because a single node never returns `40001 RETRY_SERIALIZABLE` and a multi-node Cloud cluster does. Inference is in Sydney and the database in Singapore, so **any claim of end-to-end Australian data residency would be false**, and the cross-region hop is unmeasured under load. Every timing in the demo is a local timing against Docker on a laptop. The test census reports `9290` tests with no cluster — `8323` passed, `44` failed, `923` skipped, every skip carrying the reason its own fixture wrote (`qa/test-state.json`, `totals.none`, generated `2026-08-09T22:44:59Z`) — and it predates the seven producer migrations and has not been retaken. **Those four numbers read `8845` / `8065` / `44` / `736` in every earlier version of this page**, which was the census before the demo API's own rows were merged into it; `docs/HONESTY.md` was re-derived against the artefact and this page was not, so for two days the two disagreed and the artefact was right both times. **`docs/submission/JUDGING-AXES.md` printed the same stale quartet until `2026-08-14` and now carries the artefact's figures with the superseded four named beside them.** `docs/submission/JUDGE-START.md` still prints them; it is not this file's to edit and is reported rather than reached into.

---

# The five judging criteria, one block each

**These five blocks are pasted into the *About the project* body, after *Limitations*, in
this order.** The rules weight the five criteria equally, so **each axis gets its own heading
and answers only itself**: a judge scoring axis 3 can read the axis 3 block alone and never
open axes 1, 2, 4 or 5. The axis names are the register's, taken verbatim from
[`JUDGING-AXES.md`](JUDGING-AXES.md), which carries the same five in the same order with the
honest counterweight for each.

**Every block ends with a line beginning `OPEN THIS TO CHECK IT`, naming one committed path.**
That is the artefact a sceptic opens to falsify the block above it. If the artefact does not
say what the block says, the block is wrong and the axis should be marked down — that is what
the artefacts are for.

Where a number in this repository moved after a document quoted it, the number below is the
one the artefact carries **today** and the stale one is named. That is the whole method.

| # | Axis | Block below | The one artefact |
|---|---|---|---|
| 1 | Agentic Memory Design | *Judged on — Agentic Memory Design* | `spec/TRAPPOINT-SPEC.md` §2 + `evidence/gate-refusal/` |
| 2 | Technological Implementation | *Judged on — Technological Implementation* | `scripts/proof/gate_refusal.py` |
| 3 | Real-World Impact | *Judged on — Real-World Impact* | `VERIFY.md` |
| 4 | Product Readiness | *Judged on — Product Readiness* | `docs/submission/SUBMISSION.json` |
| 5 | Creativity & Originality | *Judged on — Creativity & Originality* | `skills/designing-diachronic-gates/` |

---

## Judged on — Agentic Memory Design

<!-- PASTE -->

**JUDGING AXIS 1 OF 5 — AGENTIC MEMORY DESIGN.** This block answers that axis and no other; the four that follow answer theirs.

**Memory here is not a retrieval layer bolted beside a workflow; it is the thing the write path is blocked on.** Every clause carries a blame pointer to the incident that wrote it, so recall is *diachronic* — it answers "why does this rule say this?", which none of the permit-to-work products we surveyed can express — and the answer is required **before** a state transition, not displayed beside it. The mechanism is normative in [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2 and is three steps: **PROJECT** (a trigger writes the cross-row fact onto a scalar column of the subject row, derived from an authoritative relation and never from the inserter), **PIN** (a completed transition takes a composite foreign key onto `(subject_id, gate_epoch)`, and `ON UPDATE RESTRICT` makes attaching a new obligation to a completed transition physically impossible), **REFUSE** (a plain-column `CHECK` over that scalar, which every writer meets, forever).

Two design rules fall out of it and both are enforced rather than asserted. **Absence of evidence refuses; it never admits** — where the authority relation holds no row for a subject, the trigger raises rather than defaulting, and that is what separates a safety gate from a workflow step. And **memory that cannot be searched is a filing cabinet**: clause text is embedded by Amazon Titan v2 into CockroachDB C-SPANN vector indexes declared inline at `CREATE TABLE`, and every embedding row is forced to record its own `embed_model` and `index_gen` by `CONSTRAINT embed_model_stated` in `verticals/mainline/db/migrations/0031_clause_embedding.sql`, because a vector whose model is unknown cannot honestly be compared with anything. The plan that proves the index is actually chosen — `clause_embedding@ce_ann`, both prefix columns bound — is committed at `evidence/aws/ann/ann-proof.json` with the `EXPLAIN` beside it.

**The loop is not a diagram; it is three live GETs and a committed transcript.** STORE → RETRIEVE → ACT runs against the deployed origin and writes `evidence/demo/memory-loop.json`: `verdict PROVEN`, `23` of `23` assertions held, `0` failed. An incident dated `2019-03-14` names a clause; seven years later a permit relies on that clause; the retrieval pass finds the incident and **ten seconds** later the finding is an obligation the database will not let the permit be issued around. Those ten seconds are a **subtraction of two columns off two live routes** — `mainline_meas.recall_run.started_at` from `GET /v1/recall-runs/{run_id}`, and `mainline.blocking_check.materialised_at` from `GET /v1/permits/{permit_id}/blocking-checks` — with `stated_anywhere_in_this_program: false` in the artefact that computes it. The program that writes that file audits **itself**: `values_audited: 79`, `values_found_in_the_source: []`, `uuid_literals_in_the_source: 0`. A proof script that could have hard-coded its own answer, and demonstrably did not. **No endpoint was added to make any of this filmable** — the artefact's own ruling `R7` says the loop needed none.

**The refusal is not a "no"; it is a minimal unsatisfiable set and the nearest admissible alternative.** `POST /v1/demo/gate-run` returns, for the blocked merge, a `mus` naming the one obligation — `origin: blame_ancestry`, `severity: 4`, `virulence: blood_major`, `detail: "open at gate_epoch 1; no live disposition"` — and an `naa` of `cardinality 1` describing the exact smallest repair, with the five dispositions the law of this system permits (`applied`, `mitigated`, `mechanism_absent`, `escalated`, `emergency_override`). A gate that only says "no" gets routed around, and an invariant that is routed around is not an invariant. **On the third beat — the attack — the payload degrades honestly rather than guessing:** `naa: null`, `naa_reason: "not_computable"`, `mus[0].kind: "capability_gap"`. A refusal that tells you it cannot compute the alternative is worth more than one that invents it. Both halves are committed as well as live: the blocked merge's `mus` and `naa` in `evidence/deploy/live-gate-run.json`, which is the public Function URL's own answer, and the degraded third beat in `evidence/demo/live-beats.json` § `beat_three_diagnosis`, whose own note calls it *"a Product-Readiness point, not an embarrassment"*.

The recall corpus is **authored for this repository**. There is no real incident, site, operator or fatality behind it (`docs/HONESTY.md` § SYNTHETIC). The mechanism is real; the inputs were written by us.

**On the criterion's own words — *"a meaningful, production-grade role as the agent's memory layer"* — the scope of that adjective is the memory layer, and this submission is careful about which half it is claiming.** The memory layer is `SERIALIZABLE`, a named `CHECK` whose name is the deliverable, a composite foreign key onto `(subject_id, gate_epoch)` with `ON UPDATE RESTRICT`, a counter no client may write, row-level security with `FORCE`, and a `271`-file migration chain applied `271` of `271` against managed CockroachDB Cloud (`evidence/deploy/cloud-chain.json`, `files 271 · applied 271 · failed 0`). **What axis 4 concedes — and it concedes it loudly — is the custody store and the operator surface around that layer: `7` of `16` cryptographic custody checks unwritten, no p50, no p99, no load profile** (`qa/test-state.json`, `external_checks.custody_bundle_verification`). Those are two different sentences about two different things, and this page will not merge them in either direction.

**OPEN THIS TO CHECK IT — no clone, no account, no credential, one command:** `curl -s <demo_url>/v1/permits/dec0de00-0006-4000-8000-000000000001/blocking-checks`, where `<demo_url>` is the origin `docs/submission/SUBMISSION.json` carries in `demo_url`. The field that decides this axis is `precursor.severity_gate`. It reads `4` with `severity_basis: "human_rated"` and `origin: "blame_ancestry"` — a value the client never supplied and a trigger projected onto a row the client never touched (`evidence/gate-refusal/proof-20260810T054407Z.json#projection`, `10` of `10` assertions holding). **If that number is the client's own, memory here is a cache and this axis is falsified.** Then `spec/TRAPPOINT-SPEC.md` §2 for the normative `PROJECT · PIN · REFUSE` rules the projection obeys.

---

## Judged on — Technological Implementation

<!-- PASTE -->

**JUDGING AXIS 2 OF 5 — TECHNOLOGICAL IMPLEMENTATION.** This block answers that axis alone.

**The claim worth judging is one beat long: force the projected counter to zero out of band, attempt the merge, and the database still refuses** — `P0001 mainline.fn_permit_merge_gate` — because the gate **re-derives** the blocking count from the authority relation instead of trusting the column it was handed. A gate that trusts its own projection is a cache with a `CHECK` on it. Re-derived while writing this, in a throwaway database on a pinned single node: `271` of `271` migration files applied, `0` failed (`evidence/gate-refusal/`), all `10` projection assertions held, `REFUSED [23514] gate_closed_when_issued` reported, `REFUSED [P0001] mainline.fn_permit_merge_gate` parsed, `ADMITTED [00000]` once a disposition is signed — verdict `PROVEN`, `caveats (none)`. The third beat matters as much as the first: a gate that always refuses is broken, not safe.

The same chain runs on **CockroachDB Cloud**, not only on a laptop: `evidence/deploy/cloud-chain.json` records `files 271 · applied 271 · failed 0` against a Basic cluster in `aws-ap-southeast-1`, with the tree fingerprint that produced it. **Amazon Bedrock executes** — `evidence/deploy/aws-live.json` is a four-call transcript in `ap-southeast-2` with AWS request ids: Titan v2 returned a `1024`-dimension embedding at L2 norm `1.0`, and Claude Haiku 4.5 returned `MAINLINE gate online` for `16` input and `8` output tokens. **And the same four beats now come back over HTTP from a deployed AWS Lambda**: `evidence/deploy/live-gate-run.json` is the answer the public Function URL gave — `23514 gate_closed_when_issued`, then `P0001 mainline.fn_permit_merge_gate` against a falsified counter, then `00000` — in one `SERIALIZABLE` transaction that ends in `ROLLBACK`, so the demo leaves no state behind it. Of the AWS rows that need a `terraform apply`, the demo stack's three have had one and the custody store's have not; `docs/TOOL-USAGE.md` says which is which, per service, with the file and line that does the work and the evidence path beside it.

**The suite that proves all of that now runs against a real CockroachDB in CI, and that is new.** Every one of this repository's workflows passed `--crdb=none` until `2026-08-13`, which meant each cluster-backed test skipped and the product's own suite had never executed in a lane. `.github/workflows/cluster-tests.yml` starts a pinned `cockroachdb/cockroach:v26.2.5` container and runs the demo-api suite at `--crdb=reuse`; run `31735341117` at `headSha eefae1c` measured `528` collected, `518` executed, `10` skipped, `1` failed, `0` errored — `1 failed, 517 passed, 10 skipped in 154.21s`. **Read the residual with the result.** The lane's conclusion is `failure`, because `10` skips stand against a ceiling of `1` (`qa/cluster-known-red.json`, `floor.max_skipped`), and the skips are the two files that read `out/lambda/mainline-demo-api-arm64.zip`, a `.gitignore`'d build output the lane never builds. **A lane that skips is indistinguishable from a green tick on a dashboard**, which is the lane's own sentence and the reason it refuses rather than reports.

**The honest numbers, because they are the argument.** [`docs/CI-STATE.md`](../CI-STATE.md) is the board and it names every workflow with its run id and a quoted log line; read on `2026-08-14` it states `18 workflows · 11 GREEN · 7 RED`. Re-derived live on `2026-08-14` with `gh run list --branch master --limit 300`, taking the latest run of each: **`20` workflows, `8` success, `12` failure, `0` never-run.** *The same command earlier the same day returned `11` success and `9` failure, and both readings are kept: three lanes went red after a push at `04:29Z`.* The gap against the board is the two cluster lanes added after that board was taken, and the board says on its own face that it credits nothing still in the working tree. Several of the reds report a true incompleteness and are *meant* to stay red. The MI invariant ratchet stands at **`21` of `30` pending, `9` enforced** — the last line `python scripts/mi_ratchet.py` prints — where the intentional-red message in `ci.yml` said `28 of 30` until nine invariants were promoted underneath it and the string was corrected. The custody chain has **`7` of `16` checks unimplemented**, the whole cryptographic half, and offline bundle verification exits `2` rather than letting nine passes read as a verified ledger. **And a one-grep claim this page used to overstate, corrected by running the grep.** It said *"`continue-on-error` and `|| true` appear nowhere in this repository's lanes"*, and half of that survives measurement while half does not. `grep -rn '^\s*continue-on-error\s*:' .github/workflows/` returns **`0`** — the directive is in no lane, and every textual mention of it is prose saying it is banned. `grep -rn '|| true' .github/workflows/` returns **`39`** lines, of which **`3`** are executable shell and the rest are that same prose. The three are named here rather than left for a judge to find: `.github/workflows/db.yml:790` is `docker rm -f trappoint-crdb || true` inside an `if: always()` teardown, and `.github/workflows/nightly-differential.yml:170` and `:217` wrap a `grep -c` that exits `1` on a zero count and would abort the step under `set -eu` before the test could report that emptiness as the failure it is — the second of those carries a comment in the lane saying so. **Neither masks a result, and neither is the reason the sentence changed.** The sentence changed because a stranger could falsify it in one grep, and a page that asks to be checked has to survive being checked.

**OPEN THIS TO CHECK IT — `scripts/proof/gate_refusal.py`.** Run it against a bare local node and read the last line. The transcript it writes is committed: `evidence/gate-refusal/proof-20260814T032418Z.json`, `2026-08-14`, verdict `PROVEN` with `caveats: []`, in a throwaway database of its own — `chain 271/271 applied, 0 failed` · `PROJECTION 10/10 held` · `REFUSAL REFUSED [23514] gate_closed_when_issued (reported)` · `DRIFT REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)` · `ADMISSION ADMITTED [00000]`. **That `PROVEN` is local** — `cluster.database` is `w_qr_gate_refusal_proof` — and the equivalent run against CockroachDB Cloud is owed, which *Limitations* item (11) states in the ruling's own words. If that last word is anything but `PROVEN`, this axis is falsified and should be scored as such.

---

## Judged on — Real-World Impact

<!-- PASTE -->

**JUDGING AXIS 3 OF 5 — REAL-WORLD IMPACT.** This block answers that axis alone.

**The failure this addresses is not hypothetical and not rare: a control is relaxed after an incident, the people who understood why leave, and years later somebody restores the "correct" value.** The worked example is a compressor alarm setpoint raised from `135` back to the manufacturer's `150` — technically correct, and approved by every permit-to-work system we surveyed, because each is **synchronic**: they gate on the current state of the world (isolation in place, gas test valid, signature present) and hold no representation of *why* a limit is where it is. The institutional memory of an incident decays to nothing on the day its author resigns. MAINLINE makes that memory a precondition of the merge, and a named competent person must sign a disposition against the original event before the permit can proceed.

**What makes it deployable rather than a demo is where the rule lives.** The refusal is a database constraint under `SERIALIZABLE`, so it holds against the console, against `psql`, and against a back-office correction made by somebody with credentials and a deadline — which is how controls actually get bypassed. The blast radius of "our app forgot to check" is zero, because the app is not what checks.

**And the honest boundary.** The corpus, the site, the operator and the incident are **authored for this repository** (`docs/HONESTY.md` § SYNTHETIC); Kestrel Resources is fictional and the film says so on screen. What has been demonstrated is the mechanism, on a real distributed database, with a real refusal — not an outcome at a real operator. Nobody's safety has been improved by this yet, and a submission that implied otherwise would be doing the exact thing this project exists to refuse.

**OPEN THIS TO CHECK IT — `VERIFY.md`.** It orders three tiers by how much you must take on faith, and Tier 2 is the one that matters for impact: clone, `just up`, `just prove`, and the refusal reproduces on a stranger's laptop with no account of ours and no model call. A safety claim a buyer cannot re-run is marketing. The managed-cluster half is `evidence/deploy/cloud-chain.json` — `files 271 · applied 271 · failed 0` against CockroachDB Cloud Basic in `aws-ap-southeast-1`, `359.1` seconds there — that is `#chain_seconds`; the file's `#total_seconds` is `388.9` and includes bootstrap, so both are named rather than the flattering one — against `46.35` locally (`evidence/deploy/chain-261.json#wall_clock_seconds`), which is the most useful ratio here for anyone budgeting a deployment. It is a DDL measurement and not a retrieval one.

---

## Judged on — Product Readiness

<!-- PASTE -->

**JUDGING AXIS 4 OF 5 — PRODUCT READINESS. Score this one down; the reasons are counted below and we would rather be marked accurately than believed generously.**

**What a judge can do today, and what each route actually costs them — because one of the four is not anonymous, and this block names which rather than letting it be discovered.** *Needing nothing from us at all —* clone the repository and run `python scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable`, which applies the chain into a throwaway database and prints the three beats and a verdict; or verify the signed evidence bundle offline with no credential at all; or — ***and this is the one route on the list that is not anonymous*** — read the **live** CockroachDB Cloud ledger through the read-only `mainline_judge` login, whose password goes in the Devpost form's credentials field and appears nowhere in this repository, so it is free of charge to a judge and reachable by nobody who is not one; on `2026-08-11` it read 14 of 14 `mainline_audit` views and was refused on all 11 of the 11 forbidden statements put to it — base tables, an `INSERT`, a `CREATE TABLE`, a `DROP VIEW`, a forbidden schema and `crdb_internal` — each refusal recorded with its SQLSTATE in `evidence/deploy/judge-access.json`; or point **their own** MCP client at the CockroachDB Managed MCP Server — **against their own cluster, with their own Cloud key** — using the configuration in `verticals/mainline/demo/judge/MCP-CONFIG.md` §1, which reproduces the *mechanism* and reaches none of our data, because the credential that opens `https://cockroachlabs.cloud/mcp` is an account-level service-account key carrying `create_database`, `create_table` and `insert_rows`, and is therefore one we will not publish (`evidence/deploy/judge-access.json` → `mcp_channel.credential_publishable: false`); the sessions **we** drove over that endpoint are committed instead, and there are two of them. `evidence/deploy/judge-run.json` is the first, `2026-08-11`: 15 of 16 pack questions PASS against the live Basic cluster, the verdict left at `DIVERGED — KNOWN GAP` and the one FAIL (`N01`) preserved rather than rounded off. `evidence/mcp/` is the second, captured `2026-08-16` — `pack-run.json` puts the same sixteen questions through the pack's **own** runner, with its envelope validator and its truncation guard, and reaches the same 15 of 16 and the same `DIVERGED — KNOWN GAP` five days and one deployment later, so nobody closed the gap by revoking a grant; `auditor-live.json` records a general-counsel persona putting `10` free-text questions to that server, `9` routing deterministically onto contracted `mainline_audit` views and the tenth onto a pinned `explain_query`, every answer arriving with its completeness stated and an unroutable question refused rather than guessed at; `budget-live.json` measures `13` of those views on the wire, `0` breaching the server's `10240`-byte cap — read with that file's own warning that `8` of the `13` returned zero rows, so part of that green is emptiness rather than headroom. **That is the part worth checking, and the precise claim is the artefact's own**: we generate the statement and we dial the HTTP, and everything that turns that statement into an answer — parse, authorise, plan, execute, encode, cap — is CockroachDB's own managed server, running as its own SQL identity `managed-mcp` on a surface we did not write. The stronger-sounding *"none of our code is in the read path"* **would not be true**, because the client that sent the request is ours, and `auditor-live.json` says exactly that in the same field rather than letting us round it up; or — *back in the needing-nothing-from-us class* — open the deployed origin, whose Lambda Function URL is named in `evidence/deploy/LIVE.md` and whose submitted value is `SUBMISSION.json`'s to write: `GET /v1/health` answers `ok true` and `POST /v1/demo/gate-run` returns the four beats and a verdict, changing nothing, because that transaction ends in `ROLLBACK`. **Both were re-measured against the origin on `2026-08-16`, not read back out of the artefacts** — `ok true`, `database mainline_demo`, `deploy_chain_applied 271` of `271`; and `verdict PROVEN`, `failures []`, `persisted false`, `self_persisted false`, `transaction.isolation SERIALIZABLE`. Send the second one as a `POST`: that route declines a `GET` with `405`, which is a route refusing a method rather than a path that is not there. `docs/submission/RULES-MATRIX.md` prints a generated status table for every rule, and `python scripts/submission/check_submission_ready.py` re-derives it and exits non-zero while anything is unresolved.

**One row that used to be here is gone, and its removal is recorded rather than quiet.** Earlier versions of this block said the repository was private and that a judge opening its URL would get a `404`. **The repository is public**: `gh repo view Shaugato/mainline --json visibility,licenseInfo` answers `{"visibility":"PUBLIC","licenseInfo":{"key":"apache-2.0"}}`, measured `2026-08-12`, and the root `LICENSE` is tracked at `11357` bytes. That was table stakes, not an achievement; it is named only because a page that quietly drops its own failing rows cannot be trusted with the ones it keeps.

**What is not ready, stated here rather than discovered during judging.** This paragraph said **"there is no deployed demo URL — `terraform apply` has never been run, so no origin exists to name"**, and it was true until `2026-08-14`. **The apply then ran.** `evidence/deploy/APPLIED.md` records `24 created, 0 changed, 0 destroyed` with `37` resources in state, against the plan still committed at `evidence/deploy/terraform-plan-furl.txt:843` reading `Plan: 24 to add, 0 to change, 0 to destroy.` — 11 resources in `module.api[0]` and 13 in `module.guard[0]`, the cost guard that `infra/envs/demo/main.tf:631` now instantiates, which an earlier version of this paragraph quoted as `11` because the guard was written and never wired in, and which `docs/submission/RULES-MATRIX.md` row R2 was still quoting as `11` until `2026-08-14`. **An origin exists and it answers**: `ok true`, `deploy_chain 271/271` (`evidence/deploy/live-health.json`), and the four beats at verdict `PROVEN` (`evidence/deploy/live-gate-run.json`). **What is still not ready is everything downstream of that.** This paragraph said `docs/submission/SUBMISSION.json` *"still holds the literal `UNRESOLVED` in `demo_url` and `video_url`"*, and on `2026-08-16` that halved: `demo_url` is resolved to the Function URL and `video_url` still reads the literal `UNRESOLVED`, because the film has not been recorded. That file is the **single write point** for both and is not this page's to write, so **do not read either URL's status from this paragraph — read it from that file, and from `python scripts/submission/check_submission_ready.py`**, which prints one row per requirement and exits non-zero while any is outstanding. The first thing the deployed origin was measured doing wrong is recorded rather than buried: its first health readings were `ok=false reason="dsn_unset"`, and the console artefact it served on `2026-08-15` was a **REPLAY** build with `demo_gate_run` absent from it (`evidence/deploy/APPLIED.md` § *What the apply actually put on that origin*). A deployed URL is not a finished demo, and this block will not merge the two.

**The end-to-end acceptance run has only ever met its contract against a local emulator, and this paragraph keeps every reading it has carried.** It said: *"`evidence/deploy/acceptance.json` carries `"verdict": "NOT PROVEN"` at `generated_at 2026-08-13T01:47:58Z`, with `10` named failures … both runs now get all the way to beat `4` and are refused there: `outcome` is `refused` where the contract requires `admitted`, SQLSTATE `23503` where it requires `00000`, constraint `disposition_signer_credential_id_fkey`, the server's own `matched_expectation` is `false`, and the admission beat carries no `clearance_digest` — an `ADMITTED` with no server-computed exhibit is an assertion, not evidence."* Two symptoms before that were the `404` on `POST /v1/demo/gate-run` recorded `2026-08-10` and the `500` on `[22P02] could not parse "check_id" as type uuid` recorded `2026-08-11` with `4` failures, a row-factory mismatch. **The committed artefact today reads `"verdict": "PROVEN"` at `generated_at 2026-08-14T08:16:49Z` with `0` failures**, so the credential-identifier defect named above is fixed. **And read the target as well as the verdict, because that caveat has not moved:** `url` is `http://127.0.0.1:8792` with `target_is_local_emulator: true`, so this `PROVEN` is a statement about a local emulator serving the unmodified handler and **not** about the deployed URL; `evidence/deploy/cloud-acceptance.json` is the same shape at `127.0.0.1:8791`. The run that *did* go through the public Function URL is a different program's artefact, `evidence/deploy/live-gate-run.json`, and it is named rather than folded into this one. Read the verdict the file carries when you open it, not the one quoted here — the artefact is the claim, this sentence is a pointer to it, and that pointer has now been wrong twice in opposite directions. Alongside that: `7` of `16` custody checks are unwritten, and the AWS account carries a verification hold on new CloudFront resources — `AccessDenied: Your account must be verified before you can add new CloudFront resources.`, quoted verbatim with its `RequestID` in `docs/deploy/RUNBOOK.md` Appendix A — which is why the demo origin is a Lambda Function URL instead.

**The readiness claim is therefore narrow and true: the mechanism is reproducible by a stranger, an origin is deployed and answering, and the submission is not finished.** Three different sentences, and this page will not merge them. *This block said "the deployment is not done" until `2026-08-14`; the apply changed the middle sentence and changed neither of the others.*

**OPEN THIS TO CHECK IT — `docs/submission/SUBMISSION.json`**, then `python scripts/submission/check_submission_ready.py`. The checker asks every requirement, prints `PASS`, `WARN` or `FAIL` per row with the literal command that resolves it, and refuses to call the submission ready while any row is unresolved. A `FAIL` row on that output is this axis, stated by a program rather than by us.

---

## Judged on — Creativity & Originality

<!-- PASTE -->

**JUDGING AXIS 5 OF 5 — CREATIVITY & ORIGINALITY.** This block answers that axis alone.

**The original move is inverting where recall sits.** Every retrieval-augmented system in this space puts memory *beside* the decision — a panel, a summary, a citation list — and leaves a human to weigh it. A panel beside an "Approve" button is a nag, and nags get dismissed at 3 a.m. by somebody who has seen it forty times. Making recall a **precondition of the state transition**, enforced by the storage engine rather than by the application, is not a better nag; it is a different category of object. The gate that re-derives its own input rather than trusting the projected column is the sharp end of it: the system is built to survive its own bookkeeping being wrong, including when the bookkeeping is wrong *on purpose*.

**The second unusual choice is that this submission publishes its own red lanes.** `docs/CI-STATE.md` names every failing workflow with the run id and the quoted log line; `docs/HONESTY.md` counts what is broken with the command that re-derives each number; `docs/submission/MUST-NOT-CLAIM.md` is a list of sentences we are forbidden to say, and `scripts/submission/check_submission_prose.py` fails the build when one of them appears in our own marketing prose — run on `2026-08-12` it reported `2` violations in this repository's own submission documents, quoting the offending line, the rule that caught it and the truer sentence to write instead, and one of the two was in this page's sibling `JUDGING-AXES.md`. Re-run on `2026-08-14` it reported `submission prose OK` across the `14` files it scans and **still exited `1`**, on `3` claim-hygiene violations in `docs/HONESTY.md` at lines `724`, `746` and `749` — the honesty ledger quoting a git SHA in a transcript, caught by a rule about SHAs in the film and the deck. **Re-run on `2026-08-15` it exits `0`, and the reason is the one that is allowed:** the honesty ledger's own owner removed those three SHAs. *Re-run again on `2026-08-16` — `submission prose OK` over `18` files, `claim hygiene OK` over `23`, exit `0`.* **The gate was not narrowed to make that happen** — its one scoping decision, `HYG-sha-literal is not re-applied here`, has been in `check_submission_prose.py` since `2026-08-10`, predates the red, and is printed on every run as a `SCOPED` line rather than applied silently. Both readings stay on this page, because a green whose red is unrecorded is a green nobody can weigh. Quality numbers are **ratchets**: frozen, published, free to fall and not to rise, gated per rule so no change can buy its way past with a headline total. The `UNRESOLVED` literal in `docs/submission/SUBMISSION.json` is a feature and the submission gate refuses while it is there, which is why the open rows are still red on this page instead of being quietly filled in. *That count was `2` for as long as this page has existed and read `1` on `2026-08-16`, when `demo_url` was resolved by the owner of that file rather than by a paragraph here; `video_url` is the one still open, and the gate still exits `1` on it.*

**A red that reports a true incompleteness is more informative than a green that reports nothing.** Building the apparatus that makes that survivable — and then submitting with it switched on — is the creative claim.

**OPEN THIS TO CHECK IT — `skills/designing-diachronic-gates/`.** The idiom is generalised out of the product into a CockroachDB Agent Skill, and it ships a program that falsifies it: `skills/designing-diachronic-gates/scripts/assert_gate_refuses.py` spins a throwaway node, replays an illegal history, and fails unless the expected SQLSTATE **and** the expected constraint name are raised. Its sibling `skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` fails when the query plan stops choosing the vector index, because an ANN query that quietly fell back to a scan is otherwise indistinguishable from one that did not. A skill whose advice cannot be falsified is a blog post. **Read the verdict with the claim: `evidence/tool-usage/crdb-features.json` marks this tool `DESIGNED`, not `EXERCISED`, because no run of either script is captured under `evidence/`** — *"shipped and not evidenced"*, in the census's words. That is the honest shape of an `OPEN THIS TO CHECK IT` line here: the falsification is a program in the tree that **you** run, and the thing we are not claiming is a transcript of us having run it.

---

## Built With

> **A tag is read as "we used this", and a tag field cannot carry a verdict.** So this list
> holds only rows the two censuses mark `EXERCISED`. Nine tags were removed on `2026-08-16`
> rather than kept and quietly qualified — `changefeed`, `amazon-s3`, `s3-object-lock`,
> `aws-kms`, `aws-cloudtrail`, `amazon-cloudfront`, `amazon-eventbridge` and
> `cockroachdb-agent-skills`, each of which carries `DESIGNED`; and `opentofu`, which is
> worse than `DESIGNED` and is the reason this pass was worth doing. **`infra/envs/demo/README.md`
> says in its own words that Terraform `v1.14.8` is what is installed on the build machine,
> that OpenTofu is not, and that "Terraform is what the claims on this page were measured
> with".** The tree is written to stay inside the common subset so `tofu apply` should work;
> nobody has run it, so the tag claimed a tool that never executed. It is now `terraform`.
> **None of the removed nine is hidden — every one of them is named, with its verdict, in the
> block below**, which is where a label can actually be attached to a name.

<!-- PASTE -->

cockroachdb, cockroachdb-cloud, ccloud-cli, cockroachdb-mcp-server, model-context-protocol, sql, plpgsql, c-spann-vector-index, serializable, row-level-security, as-of-system-time, follower-reads, aws-lambda, aws-lambda-function-url, amazon-bedrock, claude, amazon-titan-embeddings, amazon-cloudwatch, aws-iam, aws-ssm-parameter-store, python, typescript, react, terraform, rego, docker, pytest

---

## What actually ran — the two censuses, verdict by verdict

> **This is the close block, and the load-bearing word in it is "actually".** Every row below
> is read out of `evidence/tool-usage/aws-services.json` and
> `evidence/tool-usage/crdb-features.json`, which carry a per-row verdict — `EXERCISED`,
> `DESIGNED` or `NOT-AVAILABLE` — and a `verdict_basis` string naming what earned it. **No
> verdict is promoted here, and the two `DESIGNED` rows a submission would most want to
> round up are labelled rather than dropped.** Re-derive the whole thing with
> `python scripts/submission/capture_tool_evidence.py --check`, which opens no socket, reads
> no credential, and exits non-zero when a count **or a citation** in either census has gone
> stale.

<!-- PASTE -->

**Every AWS service and CockroachDB feature below is labelled with the verdict its own census carries.** `EXERCISED` means it ran and a committed artefact records the result. `DESIGNED` means the code is complete and on disk and nothing recorded has run it end to end. `NOT-AVAILABLE` means it was checked on this platform and is absent. The censuses are `evidence/tool-usage/aws-services.json` and `evidence/tool-usage/crdb-features.json`; `python scripts/submission/capture_tool_evidence.py --check` re-derives both without a network or a credential, and exits non-zero when a count **or a citation** has drifted off its subject. **Read what it names when it does.** That checker also re-counts `files_scanned` — the number of files in the tree it walked — so adding any file at all makes it report `STALE` on that field until the censuses are regenerated. A `STALE` naming only `files_scanned` is a tree that grew, not a verdict that moved; a `STALE` naming a verdict, a total or an anchor is the real thing and is what the tool exists to catch.

**AWS — `12` service rows: `6` EXERCISED, `5` DESIGNED, `1` NOT-AVAILABLE.** The six exercised rows are five distinct services, because Bedrock is counted twice — inference and embeddings are separate rows with separate transcripts.

- **AWS Lambda, and the Lambda Function URL — `EXERCISED`.** The `/v1/*` demo API, `arm64`, `authorization_type = NONE`, so it needs no credential and no AWS account of the reader's. This is the one AWS surface that is in the demo's request path: it is what answers `GET /v1/health` and `POST /v1/demo/gate-run`.
- **AWS Systems Manager Parameter Store — `EXERCISED`, and it was promoted on a refusal.** With the parameter absent, the origin answered `ok=false reason="dsn_unset"` and `503 kind="dsn_unset"`, naming `ParameterNotFound` exactly; with it present, `ok true`. The committed plan sets `MAINLINE_DSN_PARAM` and sets no `MAINLINE_DSN`, so the function has no other configured route to a database and an `ok true` health body **is** a signed, role-authorised `ssm:GetParameter`. No artefact records that parameter's value, and none ever will.
- **AWS IAM — `EXERCISED`, and narrower than the row's own title.** What ran is the demo stack's least-privilege half: a role created, assumed, and its one non-managed grant used. **The deny-first policy documents this row is named for are still unapplied** — no bucket policy denying `s3:DeleteObjectVersion` exists in the account, and the Rego suite asserts those denials against plan fixtures offline and nothing else. An applied allow is not an applied deny, and the verdict covers only the first.
- **Amazon CloudWatch — `EXERCISED`, as a reader rather than as a writer.** `110` read-only `GetMetricStatistics` calls against the `AWS/Bedrock` namespace in `ap-southeast-2`, each `Sum` taken at `Period` `300` **and** `3600` and required to agree, because a `Sum` is resolution-invariant and a disagreement would mean a clipped bucket. The log group, four demo-api alarms and the dashboard now **exist**, created in the apply — and they are **unexercised**: nothing in this repository records an alarm transitioning to `ALARM`, and an alarm that has never fired has demonstrated its existence and nothing about its threshold.
- **Amazon Bedrock — `EXERCISED` on two rows, and _not in the demo's request path_.** Claude inference on `au.anthropic.claude-haiku-4-5-20251001-v1:0` and Titan v2 embeddings on `amazon.titan-embed-text-v2:0`, both in `ap-southeast-2`, both returning HTTP `200` with **AWS request ids** — strings AWS minted that this repository could not have. Those calls are real and they are not what a judge triggers by opening the origin; the four beats are SQL against CockroachDB and call no model. Both halves of that are true and neither is separable from the other.
- **`DESIGNED` — `5`, named rather than omitted.** Amazon S3 with Object Lock in `COMPLIANCE` mode, AWS KMS with an `ECC_NIST_P256` `SIGN_VERIFY` key, AWS CloudTrail, Amazon EventBridge, and Amazon CloudFront. There is no MAINLINE evidence bucket, no signing key, no trail, no `aws_cloudwatch_event_*` resource anywhere under `infra/`, and no distribution. **This is the custody half, and it is the half that matters most** — it is why the seven cryptographic checks in *Limitations* item (1) cannot run.
- **`NOT-AVAILABLE` — `1`.** Amazon Bedrock Rerank is not offered in `ap-southeast-2`. It is listed as absent rather than dropped, and it cost nothing because listwise reranking was designed onto the Claude profile before availability was checked.
- **One of the five `DESIGNED` rows will not clear on any schedule.** A real apply reached the CloudFront distribution and AWS refused, verbatim: `AccessDenied: Your account must be verified before you can add new CloudFront resources.` It reproduces from a bare `aws cloudfront create-distribution` with no Terraform involved, under an identity holding `AdministratorAccess`. Only AWS Support can lift it, which is why the demo origin is a Lambda Function URL.

**CockroachDB — `14` rows: `12` EXERCISED, `2` DESIGNED, `0` NOT-AVAILABLE.** **Two taxonomies are in play here, and conflating them is exactly how tool counts get inflated, so both are stated.** *The hackathon's* four named tools come first, in the order the Technological Implementation criterion enumerates its three — *"distributed vector index, MCP Server, ccloud CLI"* — with Agent Skills fourth, because it is named in the submission requirements and **not** in that criterion. *The census's own* `kind` column divides the same `14` rows differently: `4` are tools (the database itself, Cloud with `ccloud`, the Managed MCP Server, Agent Skills) and `10` are engine features. **So Distributed Vector Indexing appears below as one of the hackathon's four tools and is filed by the census as one of its ten features. That is one thing counted under two schemes, not two things**, and it is said out loud so that nobody adds the lists together.

- **Distributed Vector Indexing — `EXERCISED`.** C-SPANN vector indexes declared inline at `CREATE TABLE`, searched under a bound prefix, with the plan that proves the index is chosen — `clause_embedding@ce_ann`, both prefix columns bound — committed with its `EXPLAIN`. The measured detail worth having: the same query **without** the hint does not choose the index, and `<->` against a `vector_cosine_ops` index raises `42809`.
- **Managed MCP Server — `EXERCISED`, at `15` of `16` and a verdict of `DIVERGED — KNOWN GAP`.** Two recorded sessions against `https://cockroachlabs.cloud/mcp`, protocol `2025-06-18`, `tools/list` returning `12` tools, running as the server's own SQL identity `managed-mcp` against live Basic cluster `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`: `evidence/deploy/judge-run.json` on `2026-08-11` and `evidence/mcp/pack-run.json` on `2026-08-16`, the second through the pack's own runner with its envelope validator and truncation guard. Both reach the same `15` of `16` and the same `DIVERGED — KNOWN GAP`, so nobody closed the gap by revoking a grant. **The one FAIL is `N01`** — the `managed-mcp` identity can read `mainline_qa.v_disposition_profile`, which the pack asserted it could not. **A `15` of `16` printed as `16` of `16` would be the rounding this whole page exists to refuse.**
- **`ccloud` CLI — `EXERCISED`.** A captured `ccloud auth whoami` + `ccloud cluster list -o json` transcript against `mainline-dev`. `ccloud` `0.6.12` has no headless authentication, so it is a committed transcript rather than a lane, and that limitation is published rather than smoothed over.
- **Agent Skills — `DESIGNED`.** Two authored skills are on disk, each shipping an executable assertion script — one replays an illegal history and fails unless the expected SQLSTATE **and** constraint name are raised, the other fails unless the plan actually chooses the vector index. **No run of either is captured under `evidence/`**, so the census reads *"they are shipped and not evidenced"* and this block reads the same. It is a fourth tool beyond a floor of two, and it is not promoted to lengthen a list.
- **The nine engine features that are `EXERCISED`, and the measurement that earned each.** `SERIALIZABLE` — not merely reported but observed refusing, a write-skew pair rejected at commit with `40001`. PL/pgSQL triggers and functions. Named `CHECK` constraints, where the constraint **name** is the deliverable and travels intact from a Cloud node through the handler into JSON a browser can read. C-SPANN vector indexing. `AS OF SYSTEM TIME`, including **its refusal** — a `90`-day read rejected with `XXUUU` naming the replica GC threshold, which is the half that shows the bound is real. Follower reads via `follower_read_timestamp()`. Row-level security with `ENABLE` **and** `FORCE`. `SHOW CREATE` and `pg_get_functiondef` chained into a schema self-attestation, so nobody quietly weakens the gate that prevents quietly weakening controls. And `crdb_internal`, which on `v26.2.5` is restricted by default — `42501` until `allow_unsafe_internals` is set — used by us and forbidden to the audit identity.
- **`DESIGNED` — `1`.** `CHANGEFEED`. `SHOW CHANGEFEED JOBS` answers and reports `0` jobs, because no changefeed has ever been created on any cluster in this project; and `kv.rangefeed.enabled` reads **false** on the pinned node, so CDC here is not merely unstarted, it is not currently startable without flipping a cluster setting first. That is the honest shape of a `DESIGNED` verdict and it is what a reader would find on their own node.

**The arithmetic, so nobody has to trust the prose: `6` + `5` + `1` = `12` AWS rows; `12` + `2` + `0` = `14` CockroachDB rows, which the census's `kind` column splits `4` tools to `10` engine features; and of those ten features, `9` are EXERCISED and `1` — `CHANGEFEED` — is not.** Counting a feature as a tool to clear a bar is the arithmetic this repository exists to refuse, which is why the two are separated everywhere they are counted, including above, where the hackathon's four named tools and the census's four tool rows are deliberately **not** the same four.

---

## Architecture — the diagram, and a caption that works without it

> **THIS ANSWERS SUBMISSION REQUIREMENT 6, WHICH IS OPTIONAL.** Verbatim, as the
> completeness lead fetched it from `https://cockroachdb-ai.devpost.com/` on `2026-08-17`
> and recorded at [`extra-credit-plan.md`](extra-credit-plan.md) §0: *"Optional: Include an
> architectural diagram showing how CockroachDB, AWS services, and your agent interact."*
>
> **There are three drawings and they agree with each other.** Checked `2026-08-17`, all
> three present:
> **(a) the image** — [`docs/submission/diagrams/architecture.svg`](diagrams/architecture.svg),
> self-contained, no external font, no script, no logo or trademark, and its own footer states
> the boundary this caption states: *"Everything above the dashed panel is on the live request
> path a judge can call today. The dashed panel is real in this repository and is not called
> while a judge is looking."* **This is the file to attach.**
> **(b) the request path in text** at
> [`docs/architecture/02-the-request-path.md`](../architecture/02-the-request-path.md) §2,
> every box a file, a URL or a database object at a stated path.
> **(c) the component map** at [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) §*The component
> map*, three layers with the licence boundary on it.
> **Attach (a), link (b) and (c), and paste the caption below into the body.** Keep the text
> pair as well as the image: a fenced diagram renders in GitHub's rendered view, in GitHub's
> raw view, in a terminal and in a printed PDF, which an image does not — and a judge reading
> on a phone or with a screen reader gets the caption instead of nothing.
> **And read [`DIAGRAMS.md`](DIAGRAMS.md) before you upload anything.** It is the drawings'
> own document: §1.3 lists every element with whether a judge's request touches it, §1.5 gives
> the source of each label's wording, §1.4 says what the diagram deliberately does not draw,
> and §3.3 covers what to do if a destination will not take `.svg`. *(That file had not landed
> when this note was first written and had by the time it was checked again; both readings are
> kept, which is this page's rule for every status on it.)*
> **Do not commission a prettier picture that claims an arrow none of the three has.**

<!-- PASTE -->

**Architecture — what talks to what when a judge presses the button.** The drawing is `docs/submission/diagrams/architecture.svg`, and the same picture is a text diagram at `docs/architecture/02-the-request-path.md` §2, with a wider one — the component map, three layers and the licence boundary — at `docs/ARCHITECTURE.md`. Every box in all three is a file, a URL or a database object that exists at a stated path. **This caption is written so that a reader who never sees the picture still knows what the arrows are**, which is also what a screen reader gets.

**In the demo's request path — five hops, and that is all of them.** **(1)** A judge, using `curl` or the console page in a browser tab, sends `POST /v1/demo/gate-run` over TLS with no API key, no cookie and an empty body. **(2)** An **AWS Lambda Function URL** in `ap-southeast-1` (Singapore) receives it. Its `authorization_type` is `NONE` — anyone at all may call it, by the founder's choice (`infra/envs/demo/variables.tf:105`). **(3)** **AWS Lambda** runs one Python handler, `arm64`, with no web framework in it: the deployment package's entire declared dependency list is `psycopg==3.3.4` and `psycopg-binary==3.3.4` (`verticals/mainline/apps/demo-api/pyproject.toml:47-50`). **(4)** That handler makes exactly one AWS API call — **AWS Systems Manager Parameter Store**, a single `GetParameter` for the SecureString holding the database connection string, signed by hand out of `hashlib` and `hmac` rather than through an SDK. **(5)** **CockroachDB `v26.2.5`, Cloud Basic tier, `aws-ap-southeast-1`**, database `mainline_demo`, where the refusal physically lives as three independent objects: a `CHECK` constraint, a trigger, and a function. The answer comes back out the same wire carrying the database's own five-character SQLSTATE and the constraint's own name, composed by nobody. **Amazon CloudWatch** takes the logs and holds the alarms for that function; it is not in the path of the answer.

**Not in the demo's request path — and the diagram says so on its own face rather than leaving it to be discovered.** **Amazon Bedrock** — Claude inference and Amazon Titan v2 embeddings, both in `ap-southeast-2` (Sydney) — **is real in this repository and is not called while a judge is looking.** Both halves of that sentence are true and neither is separable from the other: the calls happened, returned HTTP `200`, and carry AWS request ids this repository could not have minted (`evidence/aws/probe/bedrock-probe.json`); and the four beats the origin answers are SQL against CockroachDB and call no model at all. It is checkable rather than asserted — there is no `boto3` in the dependency list above, and `grep -rin bedrock verticals/mainline/apps/demo-api/src/` returns nothing. Also outside the request path, and on the drawing as such: the **CockroachDB Managed MCP Server**, which a judge reaches with their own cluster and their own key; **Amazon S3 with Object Lock, AWS KMS, AWS CloudTrail, Amazon EventBridge and Amazon CloudFront**, all five `DESIGNED` and none applied — there is no MAINLINE evidence bucket, no signing key, no trail and no distribution; and there is no CDN, no S3 bucket and no API Gateway in front of the origin, which is why one Function URL serves both the JSON API and the console page.

**Where the agent is on that drawing.** The half of the agent this demo exercises is its **memory** — what it stored, what it retrieved, and the write it was then blocked on. That loop is three read-only `GET`s against the same origin and it is recorded at `evidence/demo/memory-loop.json`: `verdict PROVEN`, `23` of `23` assertions holding. The half of the agent that calls a model is the half named in the paragraph above as not being in the request path. And the two CockroachDB Agent Skills that generalise the idiom out of the product are real files a judge can read and run, each shipping a script that fails when its guarantee stops holding — **the census marks that tool `DESIGNED`, not `EXERCISED`, because no run of either script is captured under `evidence/`**, and this caption does not upgrade it.

**Read the drawing with the verdicts beside it.** `docs/TOOL-USAGE.md` gives every CockroachDB tool and AWS service a verdict of `EXERCISED`, `DESIGNED` or `NOT-AVAILABLE` with the file and line that does the work, and *What actually ran*, above, reads both censuses out row by row. An arrow on a diagram is a drawing decision; a verdict in a census is a measurement.

---

## Feedback for CockroachDB — the optional requirement, actually answered

> **THIS ANSWERS SUBMISSION REQUIREMENT 7, WHICH IS OPTIONAL.** Verbatim, same source and
> same date as the block above: *"Optional: Provide feedback on the CockroachDB AI tools or
> features."*
>
> **The full answer is [`docs/upstream/COCKROACHDB-FINDINGS.md`](../upstream/COCKROACHDB-FINDINGS.md)**,
> the triage page written so one maintainer can read seven reports in a sitting, with
> [`COCKROACHDB-FIELD-NOTES.md`](../upstream/COCKROACHDB-FIELD-NOTES.md) as the
> plain-language front door beside it — six findings, one struck, three things that worked,
> each with a program that reproduces it. It was re-checked by a worker who wrote none of it
> ([`scripts/upstream/verify_field_notes.py`](../../scripts/upstream/verify_field_notes.py),
> output [`evidence/upstream/verification.json`](../../evidence/upstream/verification.json)),
> and that verification is the reason one finding was struck and six further sentences were
> withdrawn from inside the survivors. **Two things not to write anywhere:** that these have
> been sent to Cockroach Labs — they have not, and this document set is the thing we would
> send; and any finding without the label its own file carries, since one of the three below
> is `ARCHIVED-EVIDENCE` rather than reproduced today and says so in the copy.

<!-- PASTE -->

**Feedback for CockroachDB, and the first item is one we got wrong.** We built on CockroachDB `v26.2.5` for several weeks and kept a list of sharp edges. Before publishing we re-ran every item from a cold shell: **seven candidates, six published, one struck**, plus six sentences withdrawn from inside the survivors. The struck one was ours — we had published that the planner would not choose our vector index unless the statement named it; it chose it unasked, twice (`docs/upstream/STRIKE-LEDGER.md` §2).

**`has_function_privilege()` cannot answer `false` in the form a checking program has to use.** *Expected:* revoking `EXECUTE` on a stored procedure makes the role-named call answer `false`. *Measured:* with `EXECUTE` revoked from everyone and the engine itself refusing the call with `42501`, the role-named form still answered `true` — for that login and for `root`, `admin` and `public`. The self-asking form answered correctly, and `has_table_privilege` passed the identical control. Our guard was built on the blind form and could never have gone red; one documentation line would have saved us the afternoon. (`findings/F01`, `REPRODUCED-TODAY`.)

**Two catalogue surfaces spell one routine two different ways.** *Expected:* `SHOW GRANTS` and `information_schema.routines` agree on a routine's name. *Measured:* the first gives the full argument list, the second the bare name, neither carries the other's spelling, and comparing them as text produces false alarms forever. A stable object-id column on `SHOW GRANTS` would end the class. (`findings/F02`, `REPRODUCED-TODAY`.)

**The ceiling on schema objects arrives as unrelated test failures.** *Expected:* a warning on the way up to roughly 20,000 objects. *Measured:* thirteen broken tests and most of an hour blaming an innocent code change. The refusal at the ceiling is excellent; nothing counts down to it, and the count that would tell you where you stand lives in `crdb_internal`, closed by default. A `NOTICE` at 80 % would have cost minutes. The mess was ours — the shape of finding out is what we send. (`findings/F05`; its central refusal is filed under ***Reported, not reproduced on this machine*, label `ARCHIVED-EVIDENCE`** — not re-triggered here, since doing so means creating twenty thousand schema objects on purpose.)

**All six, each with a program that reproduces it: `docs/upstream/COCKROACHDB-FINDINGS.md`.** Read its opening section on what the platform got right before the complaints — three things that carried this product, measured the same way. **None of this has been sent to Cockroach Labs; it is the thing we would send.**

---

## Testing instructions — how a judge reaches this, and what each route costs them

> **THE CREDENTIAL IS FILLED IN BY THE FOUNDER AND NEVER FROM THIS REPOSITORY.** The
> `mainline_judge` password is generated by
> `python scripts/deploy/judge_access.py provision --rotate --show-password`, printed once to
> that run's terminal, and written to no file here, no evidence artefact and no environment
> variable ([`SUBMISSION.json`](SUBMISSION.json) → `judge_access.credentials_location`, in
> that field's own words: *"This key is a pointer; it must never hold the value it points
> at."*). **It does not appear on this page and must not be typed into it.** Paste the block
> below into the form's testing-instructions field if the form has one, and otherwise into
> the *About the project* body; put the password into the form's own credentials field.
>
> **The substance below is `SUBMISSION.json` → `judge_access`, which is that file's to write
> and not this page's.** If the two ever disagree, that file is right.

<!-- PASTE -->

**Testing instructions — four routes, and three of them need nothing from us at all.**

**1 · The deployed demo. No credential, no account, no sign-up, nothing to install.** The Lambda Function URL's `authorization_type` is `NONE`, and as of `2026-08-16` that is measured rather than planned: an unauthenticated fetch answered HTTP `200` on `/`, on `/judge` and on `/console`. Open the demo URL in a browser for the console, or:

```
curl -s        <demo_url>/v1/health
curl -s -X POST <demo_url>/v1/demo/gate-run
```

The first answers `ok true`, `database mainline_demo`, the cluster version, and `deploy_chain_applied 271` of `deploy_chain_files 271`. The second returns the argument in four beats — `00000`, then `23514 gate_closed_when_issued`, then `P0001 mainline.fn_permit_merge_gate` against a blocking count forged to zero out of band, then `00000` once a signed answer exists — at `verdict PROVEN`, inside one `SERIALIZABLE` transaction that ends in `ROLLBACK`. So `persisted` comes back `false`, nothing is saved, and there is no reset button and no per-visitor state: the next reader meets the same permit with the same open obligation, untouched. *(That is a statement about state, not about throughput — this repository publishes no load profile and no p50, and `Limitations` says so.)* **Two ways to get this wrong in under a minute.** `/v1/demo/gate-run` is `POST`-only and answers a `GET` with `405` — that is a route declining a method, which only a route that exists can do, and it is not the path being absent. And the origin serves the console's document shell for any path it does not recognise, so a `200` from a path invented on the spot is that shell rather than an endpoint: **read the body, not the status code.**

**2 · On your own laptop, with no account of ours and no model call.** Clone the repository, start a local CockroachDB, and run `python scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable`. It applies the migration chain into a throwaway database of its own, attempts the merge three times, and prints a verdict on the last line. `VERIFY.md` orders three tiers of checking by how much you have to take on faith, and this is Tier 2. This is the route we would most like a sceptic to take, because it needs nothing from us: a safety claim a buyer cannot re-run is marketing.

**3 · The read-only ledger login — the one route on this list that is not anonymous, and the only thing in this submission that needs a credential.** The `mainline_judge` login reads MAINLINE's live CockroachDB Cloud ledger in any SQL client, and its password is in this form's credentials field and appears nowhere in the repository. `docs/deploy/JUDGE-PACK.md` §2 is the instructions. Measured `2026-08-11`, that login read all `14` `mainline_audit` views and was refused on all `11` of the `11` forbidden statements put to it — base tables, an `INSERT`, a `CREATE TABLE`, a `DROP VIEW`, a forbidden schema and `crdb_internal` — each refusal recorded with its own SQLSTATE (`evidence/deploy/judge-access.json`).

**4 · The CockroachDB Managed MCP Server, against your own cluster with your own key.** `verticals/mainline/demo/judge/MCP-CONFIG.md` §1 is a copy-pasteable configuration that reproduces the *mechanism* and reaches none of our data. That is deliberate: the key which opens `https://cockroachlabs.cloud/mcp` is an account-level Cloud service-account key whose measured tool list carries `create_database`, `create_table` and `insert_rows`, so `evidence/deploy/judge-access.json` records `mcp_channel.credential_publishable: false` and we do not hand it out. The sessions we drove over that endpoint are committed instead — `evidence/deploy/judge-run.json` on `2026-08-11` and `evidence/mcp/pack-run.json` on `2026-08-16`, five days and one deployment apart, both reaching `15` of `16` pack questions at verdict `DIVERGED — KNOWN GAP`, with the one FAIL preserved rather than rounded off.

**Expect the asymmetry, because it is chosen rather than accidental: the demo is open to anyone with no credential of ours, and the ledger takes the read-only login above.** Nothing else in this submission asks a judge for anything.

---

## Field-by-field checklist for the person pasting

**This is a complete enumeration, and the fields that stay empty are enumerated too, each
with the reason.** A field this page prepared copy for and the form turns out not to have
costs nothing; the reverse costs the submission. **Where a form field's exact name cannot be
verified without logging in to Devpost, the row says `form-field name unverified` and the
copy is ready either way** — no field name below is asserted that has not been seen.

### A · The *About the project* body — eighteen blocks, in this order

Paste them in the order below. **Three rules survive from every earlier version of this
table and none of them is relaxed by the blocks added on `2026-08-17`:** the five *Judged on*
blocks go in axis order `1`–`5` because the rules weight the five criteria equally and each
block is the only place one of them is answered directly; *What actually ran* stays **last**,
because it is the close block and it is the one a judge can check against two committed JSON
files in a minute; and **nothing here is cut to make room.** If the total must come down, cut
*Challenges we ran into* and *How we built it* first — their artefact detail is duplicated at
greater length in [`JUDGING-AXES.md`](JUDGING-AXES.md) and
[`docs/TOOL-USAGE.md`](../TOOL-USAGE.md).

| # | Block on this page | Why it is in this position |
|---:|---|---|
| 1 | *Read this first — the sixty-second version* | **New on `2026-08-17`.** The only block written for a reader who has never met the project. It goes above *Inspiration* and replaces nothing under it |
| 2 | *Inspiration* | the synchronic/diachronic contrast, for a reader who now has the story — **read the defect note at the foot of this section before pasting this one** |
| 3 | *What it does* | the mechanism in three steps, and the transcript |
| 4 | *How we built it* | the two censuses, tool by tool, with verdicts |
| 5 | *Challenges we ran into* | first candidate for the knife if the total must fall |
| 6 | *Accomplishments that we're proud of* | second candidate |
| 7 | *What we learned* | — |
| 8 | *What's next for MAINLINE* | — |
| 9 | *Limitations — read this before you believe any of it* | **do not cut.** A submission that surfaces its own gaps outscores one where a judge finds them |
| 10–14 | the five *Judged on* blocks, axis `1` to axis `5` | **do not cut.** Each answers one criterion alone, so a judge scoring axis 3 never has to read axes 1, 2, 4 and 5 |
| 15 | *Architecture — the diagram, and a caption that works without it* | **New on `2026-08-17`.** Answers optional requirement 6; goes after the axis blocks so it reads as evidence rather than as an introduction |
| 16 | *Feedback for CockroachDB* | **New on `2026-08-17`.** Answers optional requirement 7 |
| 17 | *Testing instructions* | **New on `2026-08-17`.** Goes into the form's own testing-instructions field **if the form has one**; into the body here if it does not |
| 18 | *What actually ran — the two censuses, verdict by verdict* | **last, always.** And **if it must be shortened, shorten the bases and never the verdict labels**: a row that loses its `DESIGNED` is a promotion, and a promotion is the one edit this page forbids outright |

### B · Every other field on the form, including the ones left empty

| Devpost field | Copy on this page | State, and what is still needed |
|---|---|---|
| Project title (*form-field name unverified*) | — | **`MAINLINE`.** The repository name, the name every document on this page uses, and the name in `https://github.com/Shaugato/mainline`. Nothing further is owed |
| Elevator pitch, 200-character cap | *Elevator pitch* | **ready** — `163` characters, one sentence, re-derived by the command in this page's preamble on the day this line was written |
| About the project — the body | table A above | **ready** — eighteen blocks, in that order |
| Built With | *Built With* | **ready, and read the note above that block before editing it.** It holds only rows the two censuses mark `EXERCISED`; a tag field cannot carry a verdict, so a `DESIGNED` row put back here would be a promotion. The `DESIGNED` rows are named and labelled in *What actually ran* |
| Try it out — repo link | [`SUBMISSION.json`](SUBMISSION.json) → `repo_url` | **resolved and public** — `https://github.com/Shaugato/mainline` opens for a judge with no account. An earlier version of this row said it `404`s until a visibility flip; the flip has happened |
| Try it out — demo link | [`SUBMISSION.json`](SUBMISSION.json) → `demo_url` | **resolved on `2026-08-16`** to the Lambda Function URL, which answered `200` on `/`, `/console`, `GET /v1/health` and `POST /v1/demo/gate-run` the same day with no credential. This row said `UNRESOLVED` — *"nothing is applied"* — and that stopped being true when `terraform apply` ran on `2026-08-14`; the stale wording is named here rather than quietly swapped. **Take the current value from `SUBMISSION.json`, never from this row**; that file is the single write point and this row is a snapshot |
| Video demo link | [`SUBMISSION.json`](SUBMISSION.json) → `video_url` | **THE ONE OUTSTANDING BLOCKING ROW.** It still held the literal `UNRESOLVED` on `2026-08-16` — the film has not been recorded and no worker on this submission can record it. Kit is in [`VIDEO-KIT.md`](VIDEO-KIT.md); the founder records it. **The rules require it publicly visible on YouTube or Vimeo — an *unlisted* upload is public enough and a *private* one is not**, and that distinction has ended more hackathon entries than any missing feature. Same rule as every URL here: read the value from `SUBMISSION.json` |
| Testing instructions / judge access (*form-field name unverified*) | *Testing instructions* | **ready** — four routes, three of them anonymous. Substance is [`SUBMISSION.json`](SUBMISSION.json) → `judge_access`, which is that file's to write |
| Judge credentials (*form-field name unverified*) | **deliberately absent from this page** | **the founder fills this, from a terminal, not from this repository.** The `mainline_judge` password is generated by `python scripts/deploy/judge_access.py provision --rotate --show-password`, printed once, and written to no file, no artefact and no environment variable. **A credential value must never be typed into this page** |
| Image gallery / thumbnail (*form-field name unverified*) | [`diagrams/architecture.svg`](diagrams/architecture.svg) and [`diagrams/story.svg`](diagrams/story.svg) | **UPLOAD REQUIRED — and with the film unrecorded these are the only pictures a judge gets.** Both landed `2026-08-17` and both were absent when this table was first written; the earlier reading — *"there is no `.svg` and no `.png` anywhere in this tree"* — is named rather than quietly swapped. `architecture.svg` is the thumbnail: it carries the request-path boundary on its own face. **If the field declines `.svg`, export a raster copy rather than redrawing.** A screenshot of the console at `/console` on the live origin is a legitimate third image |
| Team members / collaborators (*form-field name unverified*) | **not this page's** | the founder's to fill. No copy is owed and none is prepared |
| Prize categories, opt-ins, and any organiser-defined field not enumerated above | **none prepared** | **unknown until the form is open**, and deliberately not guessed at. If one turns up asking for something this page has not written, the material is almost certainly already in [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md), [`RULES-MATRIX.md`](RULES-MATRIX.md) or [`docs/HONESTY.md`](../HONESTY.md) |

### C · The seven submission requirements, and where each one is answered

Requirements 1–7 are the contest's own, quoted verbatim by the completeness lead at
[`extra-credit-plan.md`](extra-credit-plan.md) §0 from a fetch of
`https://cockroachdb-ai.devpost.com/` on `2026-08-17`. **Two of the seven are marked optional
and both are answered rather than skipped.**

| # | Requirement | Where it is answered | State |
|---:|---|---|---|
| 1 | public repo with README, dependencies, setup | `repo_url`, and the README at that URL | **MET** — `PUBLIC`, Apache-2.0, `LICENSE` tracked at `11357` bytes |
| 2 | a functional demo URL | `demo_url`, and *Testing instructions* route 1 | **MET** — answered `200` unauthenticated on `2026-08-16`, and from outside our own network on `2026-08-17` |
| 3 | a video under three minutes, publicly visible | `video_url` | **NOT DONE** — the one outstanding blocking row, above |
| 4 | which CockroachDB tools, and how | *How we built it*, *What actually ran*, and [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) | **MET** — four named tools, three `EXERCISED`, Agent Skills `DESIGNED` and labelled so |
| 5 | which AWS services, and how | same three | **MET** — `12` service rows: `6` `EXERCISED`, `5` `DESIGNED`, `1` `NOT-AVAILABLE` |
| 6 | **optional** — an architectural diagram: CockroachDB × AWS × the agent | *Architecture — the diagram, and a caption that works without it* | **ANSWERED** — an image at [`diagrams/architecture.svg`](diagrams/architecture.svg), the same picture in text at two places, and a caption that stands with no picture at all |
| 7 | **optional** — feedback on the CockroachDB AI tools or features | *Feedback for CockroachDB* | **ANSWERED** — three findings in the block, six in [`docs/upstream/COCKROACHDB-FINDINGS.md`](../upstream/COCKROACHDB-FINDINGS.md), one struck and kept on the page |

### D · A defect in an existing block on this page, found and now corrected

**The *Inspiration* block carried four statements that the authored corpus contradicts.** The
wave that found them worked insert-only and reported them here rather than reaching into an
existing `<!-- PASTE -->` block. **They were applied on 2026-08-18**, so the block above and the
*sixty-second version* now agree, and the same four corrections went into `docs/ARCHITECTURE.md`
and `docs/story/ORIGIN.md`, which carried some of them too. The table stays because a page whose
method is *name the superseded reading* does not delete its own.

| The *Inspiration* block used to say | The corpus says | Where |
|---|---|---|
| the clause was lowered on `2013-06-12` | `2013-06-12` is the **incident** date. The clause was lowered on `2013-08-04` | `spine.json#dates` → `incident`, `strengthen_commit`; `anchors.yaml:68` → `{effective_on: 2013-08-04, driven_by_event: INC-2013-044}` |
| an author who left the company in `2017` | `2021-07-16`. `2017` matches no date in the corpus at all — `2016-11-21` is the retypeset and `2019-02-19` is the split | `spine.json#dates` → `author_separated` |
| a disposition against a *"thirteen-year-old death"* | **nobody dies.** Severity `4`, two contractors, partial-thickness burns — and the corpus comments that the potential is `4` and not `5` **deliberately** | `anchors.yaml:196`; `CAMERA-STRINGS.yaml:78` → `incident_summary_line`; `MUST-NOT-CLAIM.md` §3 forbids inventing a fatality |
| *"Lowered 150 to 135 …"* | *"Lowered 150 → 135 …"* — U+2192, asserted byte-equal across four files, with the corpus file's own header calling the punctuation load-bearing and saying *"Do not 'fix' the punctuation"* | `CAMERA-STRINGS.yaml:64-65` |

**What the *Inspiration* block reads now**, in place of those four:

> MAINLINE runs `blame` on the clause instead. A seal fire burned two contractors on
> `2013-06-12`; the alarm was lowered because of it on `2013-08-04`, with the message
> *"Lowered 150 → 135 after seal fire INC-2013-044 — two contractors burned."*; and that author
> left the company on `2021-07-16`. The permit merge is then **mechanically refused by the
> database** — not flagged, refused — until a named competent person signs a disposition against
> a thirteen-year-old fire.

**Paste block 1 and block 2 as they stand.** They agree with each other and with the corpus.

> **Do not paste a URL that is not resolved**, and do not read a URL's status out of the
> table above — it is a snapshot and it can drift.
> `python scripts/submission/check_submission_ready.py` prints one line per row with the
> literal command that resolves it and exits non-zero while any row is outstanding; run on
> `2026-08-14` it reported **`NOT READY`, `3` unresolved rows out of `10`, `0` NOT CHECKED** —
> `demo_url` and
> `video_url`, which are the two this page had always said were open, plus `remote_sync`,
> which on that run read `4` commits ahead of `origin/master` with `22` uncommitted paths and
> clears on a push. The same three rows, and the same count,
> as `2026-08-12`. **Re-run on `2026-08-16` it reports `NOT READY`, `2` unresolved rows,
> `0` NOT CHECKED, exit `1`** — `demo URL` has turned `PASS` and names the Function URL,
> `video URL` is `FAIL`, and `remote is in sync` is a `WARN` about uncommitted paths rather
> than an unresolved row. Three readings of one command are kept here; the third is not
> allowed to erase the first two. **`NOTRUN` means NOT CHECKED and is never a pass**, which is why the census
> of unasked questions is printed even when it is zero. The per-axis map a judge scores
> against is [`JUDGING-AXES.md`](JUDGING-AXES.md), which carries the same five axes in the
> same order with the honest counterweight for each; the rule-by-rule verdict is
> [`RULES-MATRIX.md`](RULES-MATRIX.md); which CockroachDB and AWS services were used, and
> how, is [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md).
