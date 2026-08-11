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

Measured over the paste blocks only: **15 blocks, 3,415 words**, elevator pitch **163
characters** (cap is 200), one sentence. Re-derive all three with:

```bash
python -c "import re;t=open('docs/submission/DEVPOST.md',encoding='utf-8').read();b=re.findall(r'<!-- PASTE -->\n(.*?)(?=\n---\n)',t,re.S);print(len(b),sum(len(x.split()) for x in b),len(b[0].strip()))"
```

That total sits above the 1,400-word drafting guide and is recorded rather than rounded.
**The five criterion blocks are the ones that must not be cut**: the rules weight the five
judging criteria equally and each block is the only place one of them is answered directly.
If the total must come down, cut *Challenges* and *How we built it* first — the artefact
detail they carry is duplicated at greater length in
[`JUDGING-AXES.md`](JUDGING-AXES.md) and [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md). Do not
cut *Limitations*.

> **Two URLs are unresolved as this file is written**, and the checklist below carries the
> literal string `UNRESOLVED` where each belongs. Do not invent them. The repository URL
> **is** resolved — `https://github.com/Shaugato/mainline`, which is the address whatever
> its visibility — and the root `LICENSE` is now tracked (`git ls-files LICENSE` answers;
> it was untracked on `2026-08-10` and this note said so). What is still true on
> `2026-08-11` is that the repository is `PRIVATE`: `gh repo view Shaugato/mainline --json
> visibility,licenseInfo` → `{"visibility":"PRIVATE","licenseInfo":{"key":"apache-2.0"}}`,
> so a judge opening that URL today gets a 404. Clearing that gate is the founder runbook's
> work, not this document's, and `python scripts/submission/check_submission_ready.py`
> reports it as its own row until it is done.

---

## Elevator pitch

<!-- PASTE -->

Every permit system gates on the present; MAINLINE gates on ancestry — the database refuses the merge until someone signs against the incident that wrote the rule.

---

## Inspiration

<!-- PASTE -->

An engineer raises a compressor alarm setpoint from `135` back to the manufacturer's `150` — a routine change, technically correct, and every permit-to-work system on the market would approve it. MAINLINE runs `blame` on the clause instead, and finds it was lowered on `2013-06-12` after a seal fire, by an author who left the company in `2017`, with the message *"Lowered 150 to 135 after seal fire INC-2013-044 — two contractors burned."* The permit merge is then **mechanically refused by the database** — not flagged, refused — until a named competent person signs a disposition against a thirteen-year-old death.

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

---

## How we built it

<!-- PASTE -->

The database is not a datastore under this system — it is the system. `docs/TOOL-USAGE.md` documents **4 CockroachDB tools**, inside which **10 engine features** are separately accounted (counting a feature as a tool to clear a bar is the arithmetic this repository exists to refuse), and **12 AWS services**, each carrying a verdict of EXERCISED, DESIGNED or NOT-AVAILABLE plus a file-and-line anchor.

**CockroachDB `v26.2.5`.** The four tools are the database itself, CockroachDB Cloud with the `ccloud` CLI, the Managed MCP Server, and two authored Agent Skills. The gate needs `SERIALIZABLE` — it reads before it writes, and anything weaker is a write-skew hole — plus PL/pgSQL triggers, named `CHECK` constraints whose *name* is the deliverable, and `SHOW CREATE` with `pg_get_triggerdef()` chained into a schema attestation, so nobody quietly weakens the gate that prevents quietly weakening controls. The rest: C-SPANN vector indexes inline at `CREATE TABLE` for recall, `AS OF SYSTEM TIME` and follower reads for the fixity patrol, row-level security with `FORCE`, `crdb_internal` for the HLC ordering the ledger, and CHANGEFEED, which is DESIGNED.

**AWS, and the two halves are not the same claim.** Bedrock for Claude inference and Titan embeddings in `ap-southeast-2`, the model id resolved at start-up from `ListInferenceProfiles` and pinned into the run record, so a residency violation fails loudly rather than silently reaching another region. **That half is EXERCISED.** `invoke_model` on `amazon.titan-embed-text-v2:0` and `converse` on `au.anthropic.claude-haiku-4-5-20251001-v1:0` return HTTP `200` with AWS request ids (`evidence/aws/probe/bedrock-probe.json`); the `1024`-dimension vectors those calls produced sit in a CockroachDB Cloud table and are searched through the C-SPANN index by a plan that names `clause_embedding@ce_ann` with both prefix columns bound (`evidence/aws/ann/ann-proof.json`, `evidence/aws/ann/explain-hinted.txt`); and AWS's own `AWS/Bedrock` CloudWatch counters record the invocations from outside this repository, which is the only piece of evidence here that we did not write about ourselves.

**The other half is DESIGNED, not EXERCISED, and nothing is deployed.** S3 with Object Lock in COMPLIANCE mode, KMS for `ECC_NIST_P256` checkpoint signatures, CloudTrail for a digest chain we could not have forged, and Lambda, CloudFront with OAC, CloudWatch as provisioned infrastructure, IAM, SSM Parameter Store and EventBridge for the demo stack. `terraform apply` has never been run, there is no MAINLINE bucket and no MAINLINE distribution in the account, and no judge can visit any of it. Read the per-service verdicts from `evidence/tool-usage/aws-services.json` rather than from this paragraph.

---

## Challenges we ran into

<!-- PASTE -->

**A defect census built from error messages measures what the error messages can express.** Seven tables had consumers — triggers, views, RLS policies — and no producer migration. Classified by SQLSTATE the count read **five**, and it was wrong: CockroachDB names only the *first* absent relation in a statement, so one table sat shadowed behind another in both views that joined them and never appeared in an error string anywhere. The durable fix is not the seven files but the lint that now differences every schema-qualified reference against every relation the tree creates, so the eighth instance fails at lint time instead of deployment time.

**The measurement everyone quoted was not the measurement a deployment performs.** The chain figure published for days came from a *continue-on-error census*; the forward-only runner a deployment actually uses halts on the first refusal, and it halted early, leaving the version dirty. Both now complete: `271` of `271` files, `0` failed, nothing dirty, attestation head ordinal `271` at grade `strong` (`evidence/chain/chain-20260810T062542Z.json`), up from `246` of `261` with `15` failing. That earlier artefact stays in the tree rather than being deleted.

**Platform facts, published rather than smoothed over.** `P0001` carries no `diag.constraint_name`, so the raising object is recovered from message text — the proof records whether an exhibit was `reported` or `parsed`, the difference between a diagnosis and a guess. `ccloud` `0.6.12` has no headless authentication and Cloud audit-log endpoints `404` on Basic, so "custody of the custodian" is documented as unavailable rather than shipped as an unbacked claim.

---

## Accomplishments that we're proud of

<!-- PASTE -->

**The honesty mechanism is executable, and it is red right now — because good news arrived.** `tests/release/test_honesty_is_checkable.py` fails the build when a number in `docs/HONESTY.md` and its cited source disagree, when a cited file is gone, or when a number carries no reference at all. One rule runs the other way: it fails when evidence *appears* that the prose has not absorbed. Running it while writing this gave `1 failed, 33 passed`, naming the two artefacts that had landed within the hour — the completed forward-only chain run, and the first conformance census. A red build is the correct response to evidence a document has not caught up with. That is the feature, and it is why the central claim above is worth believing: verdict `PROVEN`, three beats, zero caveats, reproducible with no credential of ours.

---

## What we learned

<!-- PASTE -->

**A truthful red beats a fabricated green, and it is cheaper to defend.** Every quality number here is a *ratchet*: `847` `ruff` findings and `245` files `ruff format` would rewrite (`qa/ruff-ratchet.json`), `0` `mypy` errors over `660` checked source files (`qa/mypy-ratchet.json`) — and that zero is worth nothing without the count beside it, because a checker that ran nothing also prints zero. Frozen, published, free to fall but not rise, and gated per rule so a change cannot buy its way past with a headline total.

**A skill whose advice cannot be falsified is a blog post.** Both CockroachDB Agent Skills ship an executable assertion: one replays an illegal history and fails unless the expected SQLSTATE *and* constraint name are raised; the other fails unless the query plan actually chooses the vector index.

**Absence of evidence refuses; it never admits.** Where the authority source holds no row for a subject, the trigger must refuse — never default, infer or pass. That rule separates a safety gate from a workflow step.

---

## What's next for MAINLINE

<!-- PASTE -->

**Raise the conformance suite off its floor.** A census has for the first time produced a result for every declared case instead of erroring out, and it is red: `qa/conformance-census.json` records `10` passed, `6` failed and `55` cannot-run across `71` declared cases, each cannot-run naming the object it lacked. `46` share one cause — a setup statement the database refused because a column does not exist — so a single repair moves most of them.

**Land the cryptographic half of custody.** Offline bundle verification exits `2` on purpose: `9` checks ran and held, `0` failed, `7` did not run at all (`qa/test-state.json`). Exit `2` is the tool refusing to let nine passes be read as a verified ledger.

<!-- no-bare-point-estimates: allow - both numbers are DDL wall-clock seconds from evidence/deploy/, not retrieval metrics; the sentence exists to say the hop is UNMEASURED for retrieval, and the checker matches on the word it uses to deny the claim -->
**Deploy, and measure the hop.** The one cross-region cost measured so far is DDL, not recall: `359.1` seconds for the chain against Singapore versus `46.35` locally for the same files (`evidence/deploy/`). Neither is a retrieval measurement, and this repository publishes no interval for that hop because nobody has taken one.

---

## Limitations — read this before you believe any of it

<!-- PASTE -->

**`docs/HONESTY.md` publishes what is broken, counted, with the command that re-derives each number.** It is the first thing we would want a judge to open; burying it would contradict the entire pitch. The corpus is **authored** — the compressor-setpoint story is a designed worked example, no real incident, no real site, no real fatality. The agent suite still replays **recorded cassettes**, and a green run there says our code handles that recorded exchange — it is not a statement about a model today. Separately, and it is a different claim: Bedrock was genuinely invoked while this was written, and the transcripts are committed under `evidence/aws/probe/`. The reference-ledger keys are named `NOT-SECRET` because they are. **Nothing is deployed** — no MAINLINE bucket, no MAINLINE distribution, no applied Terraform — so every AWS row except Bedrock is DESIGNED, and nothing has ever run against CockroachDB Cloud in CI. Inference is in Sydney and the database in Singapore, so **any claim of end-to-end Australian data residency would be false**, and the cross-region hop is unmeasured under load. Every timing in the demo is a local timing against Docker on a laptop. The test census reports `8845` tests with no cluster — `8065` passed, `44` failed, `736` skipped, every skip carrying the reason its own fixture wrote (`qa/test-state.json`) — and it predates the seven producer migrations and has not been retaken.

---

# The five judging criteria, one section each

**These five blocks are pasted into the *About the project* body, after *Limitations*, in
this order.** The rules weight the five criteria equally, so each gets its own heading and
each one cites a **committed artefact** rather than an adjective. A judge who disbelieves a
sentence here can open the file named in it without asking us for anything.

Where a number in this repository moved after a document quoted it, the number below is the
one the artefact carries **today** and the stale one is named. That is the whole method.

---

## Judged on — Agentic Memory Design

<!-- PASTE -->

**Memory here is not a retrieval layer bolted beside a workflow; it is the thing the write path is blocked on.** Every clause carries a blame pointer to the incident that wrote it, so recall is *diachronic* — it answers "why does this rule say this?", which no permit-to-work system on the market can express — and the answer is required **before** a state transition, not displayed beside it. The mechanism is normative in [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2 and is three steps: **PROJECT** (a trigger writes the cross-row fact onto a scalar column of the subject row, derived from an authoritative relation and never from the inserter), **PIN** (a completed transition takes a composite foreign key onto `(subject_id, gate_epoch)`, and `ON UPDATE RESTRICT` makes attaching a new obligation to a completed transition physically impossible), **REFUSE** (a plain-column `CHECK` over that scalar, which every writer meets, forever).

Two design rules fall out of it and both are enforced rather than asserted. **Absence of evidence refuses; it never admits** — where the authority relation holds no row for a subject, the trigger raises rather than defaulting, and that is what separates a safety gate from a workflow step. And **memory that cannot be searched is a filing cabinet**: clause text is embedded by Amazon Titan v2 into CockroachDB C-SPANN vector indexes declared inline at `CREATE TABLE`, and every embedding row is forced to record its own `embed_model` and `index_gen` by `CONSTRAINT embed_model_stated` in `verticals/mainline/db/migrations/0031_clause_embedding.sql`, because a vector whose model is unknown cannot honestly be compared with anything. The plan that proves the index is actually chosen — `clause_embedding@ce_ann`, both prefix columns bound — is committed at `evidence/aws/ann/ann-proof.json` with the `EXPLAIN` beside it.

The recall corpus is **authored for this repository**. There is no real incident, site, operator or fatality behind it (`docs/HONESTY.md` § SYNTHETIC). The mechanism is real; the inputs were written by us.

---

## Judged on — Technological Implementation

<!-- PASTE -->

**The claim worth judging is one beat long: force the projected counter to zero out of band, attempt the merge, and the database still refuses** — `P0001 mainline.fn_permit_merge_gate` — because the gate **re-derives** the blocking count from the authority relation instead of trusting the column it was handed. A gate that trusts its own projection is a cache with a `CHECK` on it. Re-derived while writing this, in a throwaway database on a pinned single node: `271` of `271` migration files applied, `0` failed (`evidence/gate-refusal/`), all `10` projection assertions held, `REFUSED [23514] gate_closed_when_issued` reported, `REFUSED [P0001] mainline.fn_permit_merge_gate` parsed, `ADMITTED [00000]` once a disposition is signed — verdict `PROVEN`, `caveats (none)`. The third beat matters as much as the first: a gate that always refuses is broken, not safe.

The same chain runs on **CockroachDB Cloud**, not only on a laptop: `evidence/deploy/cloud-chain.json` records `files 271 · applied 271 · failed 0` against a Basic cluster in `aws-ap-southeast-1`, with the tree fingerprint that produced it. **Amazon Bedrock executes** — `evidence/deploy/aws-live.json` is a four-call transcript in `ap-southeast-2` with AWS request ids: Titan v2 returned a `1024`-dimension embedding at L2 norm `1.0`, and Claude Haiku 4.5 returned `MAINLINE gate online` for `16` input and `8` output tokens. Every AWS row that would need `terraform apply` is still DESIGNED, and `docs/TOOL-USAGE.md` says which is which, per service, with the file and line that does the work.

**The honest numbers, because they are the argument.** [`docs/CI-STATE.md`](../CI-STATE.md) — re-measured `2026-08-11` at commit `47f8aa2` — is the board: **8 green, 9 red, 0 never-run**, and six of the nine reds report a true incompleteness and are *meant* to stay red. The MI invariant ratchet stands at **21 of 30 pending** (an earlier version of this page said 28 of 30; the registry string was seven invariants out of date and was corrected). The custody chain has **7 of 16 checks unimplemented** — the cryptographic half — and offline bundle verification exits `2` rather than letting nine passes read as a verified ledger. `continue-on-error` and `|| true` appear nowhere in this repository's lanes.

---

## Judged on — Real-World Impact

<!-- PASTE -->

**The failure this addresses is not hypothetical and not rare: a control is relaxed after an incident, the people who understood why leave, and years later somebody restores the "correct" value.** The worked example is a compressor alarm setpoint raised from `135` back to the manufacturer's `150` — technically correct, and approved by every permit-to-work system on the market, because they are all **synchronic**: they gate on the current state of the world (isolation in place, gas test valid, signature present) and hold no representation of *why* a limit is where it is. The institutional memory of an incident decays to nothing on the day its author resigns. MAINLINE makes that memory a precondition of the merge, and a named competent person must sign a disposition against the original event before the permit can proceed.

**What makes it deployable rather than a demo is where the rule lives.** The refusal is a database constraint under `SERIALIZABLE`, so it holds against the console, against `psql`, and against a back-office correction made by somebody with credentials and a deadline — which is how controls actually get bypassed. The blast radius of "our app forgot to check" is zero, because the app is not what checks.

**And the honest boundary.** The corpus, the site, the operator and the incident are **authored for this repository** (`docs/HONESTY.md` § SYNTHETIC); Kestrel Resources is fictional and the film says so on screen. What has been demonstrated is the mechanism, on a real distributed database, with a real refusal — not an outcome at a real operator. Nobody's safety has been improved by this yet, and a submission that implied otherwise would be doing the exact thing this project exists to refuse.

---

## Judged on — Product Readiness

<!-- PASTE -->

**What a judge can do today, without asking us for anything:** clone the repository and run `python scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable`, which applies the chain into a throwaway database and prints the three beats and a verdict; or verify the signed evidence bundle offline with no credential at all; or read the **live** CockroachDB Cloud ledger through the read-only `mainline_judge` login, which on `2026-08-11` read 14 of 14 `mainline_audit` views and was refused on 11 of 11 base tables and every write, each refusal recorded with its SQLSTATE in `evidence/deploy/judge-access.json`; or point their own MCP client at the CockroachDB Managed MCP Server with the configuration in `verticals/mainline/demo/judge/MCP-CONFIG.md`. `docs/submission/RULES-MATRIX.md` prints a generated status table for every rule, and `python scripts/submission/check_submission_ready.py` re-derives it and exits non-zero while anything is unresolved.

**What is not ready, stated here rather than discovered during judging.** There is **no deployed demo URL**: `demo_url` in `docs/submission/SUBMISSION.json` holds the literal `UNRESOLVED`, `terraform apply` has never been run, and the hourly health lane is red for exactly that reason and goes green on its own the moment a URL exists. The end-to-end acceptance run is `NOT PROVEN` — `evidence/deploy/acceptance.json` names two defects and the source lines that cause them rather than rounding them off. Seven custody checks are unwritten. The repository is private as this is written, and the AWS account carries a verification hold on new CloudFront resources, quoted verbatim in `docs/deploy/RUNBOOK.md`, which is why the demo origin is a Lambda Function URL instead.

**The readiness claim is therefore narrow and true: the mechanism is reproducible by a stranger, and the deployment is not done.** Those are different sentences and this page will not merge them.

---

## Judged on — Creativity

<!-- PASTE -->

**The original move is inverting where recall sits.** Every retrieval-augmented system in this space puts memory *beside* the decision — a panel, a summary, a citation list — and leaves a human to weigh it. A panel beside an "Approve" button is a nag, and nags get dismissed at 3 a.m. by somebody who has seen it forty times. Making recall a **precondition of the state transition**, enforced by the storage engine rather than by the application, is not a better nag; it is a different category of object. The gate that re-derives its own input rather than trusting the projected column is the sharp end of it: the system is built to survive its own bookkeeping being wrong, including when the bookkeeping is wrong *on purpose*.

**The second unusual choice is that this submission publishes its own red lanes.** `docs/CI-STATE.md` names every failing workflow with the run id and the quoted log line; `docs/HONESTY.md` counts what is broken with the command that re-derives each number; `docs/submission/MUST-NOT-CLAIM.md` is a list of sentences we are forbidden to say, and `scripts/submission/check_submission_prose.py` fails the build when one of them appears in our own marketing prose — it has caught us twice. Quality numbers are **ratchets**: frozen, published, free to fall and not to rise, gated per rule so no change can buy its way past with a headline total. The `UNRESOLVED` literal in `docs/submission/SUBMISSION.json` is a feature and the submission gate refuses while it is there, which is why two rows are still red on this page instead of being quietly filled in.

**A red that reports a true incompleteness is more informative than a green that reports nothing.** Building the apparatus that makes that survivable — and then submitting with it switched on — is the creative claim.

---

## Built With

<!-- PASTE -->

cockroachdb, cockroachdb-cloud, ccloud-cli, cockroachdb-mcp-server, cockroachdb-agent-skills, sql, plpgsql, c-spann-vector-index, serializable, row-level-security, changefeed, amazon-bedrock, claude, amazon-titan-embeddings, amazon-s3, s3-object-lock, aws-kms, aws-cloudtrail, aws-lambda, amazon-cloudfront, amazon-cloudwatch, aws-iam, aws-ssm-parameter-store, amazon-eventbridge, python, typescript, react, opentofu, rego, docker, pytest, model-context-protocol

---

## Field-by-field checklist for the person pasting

| Devpost field | Source above | Still needed |
|---|---|---|
| Elevator pitch | *Elevator pitch* | — |
| Inspiration | *Inspiration* | — |
| What it does | *What it does* | — |
| How we built it | *How we built it* | — |
| Challenges we ran into | *Challenges we ran into* | — |
| Accomplishments | *Accomplishments that we're proud of* | — |
| What we learned | *What we learned* | — |
| What's next | *What's next for MAINLINE*, then *Limitations*, then the five *Judged on* blocks | paste all seven, in that order |
| Built With | *Built With* | — |
| Try it out — repo link | `docs/submission/SUBMISSION.json` → `repo_url` | **resolved** — `https://github.com/Shaugato/mainline`. It 404s for a judge until the visibility flip, which is a separate row |
| Try it out — demo link | `docs/submission/SUBMISSION.json` → `demo_url` | `UNRESOLVED` — nothing is deployed; the apply is the deploy runbook's step 1 |
| Video demo link | `docs/submission/SUBMISSION.json` → `video_url` | `UNRESOLVED` — kit is in [`VIDEO-KIT.md`](VIDEO-KIT.md); the founder records it |
| Judge access / testing instructions | `docs/submission/SUBMISSION.json` → `judge_access` | **resolved** — both paths named; the `mainline_judge` password goes in the form's credentials field and **never** in this repository |

> **Do not paste a URL that is not resolved.** The demo link is a Stage One pass/fail gate
> and so is the repository's visibility. Every row above is re-derivable:
> `python scripts/submission/check_submission_ready.py` prints one line per row and the
> literal command that resolves it. The per-axis map a judge scores against is
> [`JUDGING-AXES.md`](JUDGING-AXES.md); the rule-by-rule verdict is
> [`RULES-MATRIX.md`](RULES-MATRIX.md); which CockroachDB and AWS services were used, and
> how, is [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md).
