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

Measured over the paste blocks only: **1,645 words**, elevator pitch **163 characters**
(cap is 200), one sentence. Re-derive both with:

```bash
python -c "import re;t=open('docs/submission/DEVPOST.md',encoding='utf-8').read();b=re.findall(r'<!-- PASTE -->\n(.*?)(?=\n---\n)',t,re.S);print(sum(len(x.split()) for x in b),len(b[0].strip()))"
```

That total sits above the 1,400-word drafting guide and is recorded rather than rounded.
If it must come down, cut *Challenges* and *How we built it* first — the artefact detail
they carry is duplicated at greater length in [`JUDGING-AXES.md`](JUDGING-AXES.md) and
[`docs/TOOL-USAGE.md`](../TOOL-USAGE.md). Do not cut *Limitations*.

> **Three URLs are unresolved as this file is written**, and the checklist below carries the
> literal string `UNRESOLVED` where each belongs. Do not invent them. The repository is
> `PRIVATE` with no licence on GitHub (`gh repo view Shaugato/mainline --json
> visibility,licenseInfo,homepageUrl` → `{"visibility":"PRIVATE","licenseInfo":null,
> "homepageUrl":""}`, run `2026-08-10`), and the root `LICENSE` exists on disk but is
> **untracked** (`git status --porcelain` → `?? LICENSE`), so a push today would not publish
> it. Clearing those gates is the founder runbook's work, not this document's.

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

**AWS.** Bedrock for Claude inference and Titan embeddings in `ap-southeast-2`, the model id resolved at start-up from `ListInferenceProfiles` and pinned into the run record, so a residency violation fails loudly rather than silently reaching another region. Then S3 with Object Lock in COMPLIANCE mode, KMS for `ECC_NIST_P256` checkpoint signatures, CloudTrail for a digest chain we could not have forged, and Lambda, CloudFront with OAC, CloudWatch, IAM, SSM Parameter Store and EventBridge for the demo stack. That half is **DESIGNED, not EXERCISED**: nothing is deployed, and every model call is a recorded cassette.

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

**A truthful red beats a fabricated green, and it is cheaper to defend.** Every quality number here is a *ratchet*: `847` `ruff` findings and `245` files `ruff format` would rewrite (`qa/ruff-ratchet.json`), `12` `mypy` errors over `477` checked source files (`qa/mypy-ratchet.json`). Frozen, published, free to fall but not rise, and gated per rule so a change cannot buy its way past with a headline total.

**A skill whose advice cannot be falsified is a blog post.** Both CockroachDB Agent Skills ship an executable assertion: one replays an illegal history and fails unless the expected SQLSTATE *and* constraint name are raised; the other fails unless the query plan actually chooses the vector index.

**Absence of evidence refuses; it never admits.** Where the authority source holds no row for a subject, the trigger must refuse — never default, infer or pass. That rule separates a safety gate from a workflow step.

---

## What's next for MAINLINE

<!-- PASTE -->

**Raise the conformance suite off its floor.** It has now been demonstrated end to end for the first time: `qa/conformance-census.json` records `10` passed, `6` failed and `55` cannot-run across `71` declared cases, each cannot-run naming the object it lacked. `46` share one cause — a setup statement the database refused because a column does not exist — so a single repair moves most of them.

**Land the cryptographic half of custody.** Offline bundle verification exits `2` on purpose: `9` checks ran and held, `0` failed, `7` did not run at all (`qa/test-state.json`). Exit `2` is the tool refusing to let nine passes be read as a verified ledger.

**Deploy, and measure the hop.** The one cross-region cost measured so far is DDL, not recall: `359.1` seconds for the chain against Singapore versus `46.35` locally for the same files (`evidence/deploy/`).

---

## Limitations — read this before you believe any of it

<!-- PASTE -->

**`docs/HONESTY.md` publishes what is broken, counted, with the command that re-derives each number.** It is the first thing we would want a judge to open; burying it would contradict the entire pitch. The corpus is **authored** — the compressor-setpoint story is a designed worked example, no real incident, no real site, no real fatality. Model transcripts are **recorded cassettes**; no live Bedrock inference transcript is committed. The reference-ledger keys are named `NOT-SECRET` because they are. **Nothing is deployed**, so every AWS row except model access is DESIGNED, and nothing has ever run against CockroachDB Cloud in CI. Inference is in Sydney and the database in Singapore, so **any claim of end-to-end Australian data residency would be false**, and the cross-region hop is unmeasured under load. Every timing in the demo is a local timing against Docker on a laptop. The test census reports `8845` tests with no cluster — `8065` passed, `44` failed, `736` skipped, every skip carrying the reason its own fixture wrote (`qa/test-state.json`) — and it predates the seven producer migrations and has not been retaken.

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
| What's next | *What's next for MAINLINE*, then *Limitations* | paste both, in that order |
| Built With | *Built With* | — |
| Try it out — repo link | — | `UNRESOLVED` — repo `PRIVATE`, root `LICENSE` untracked |
| Try it out — demo link | — | `UNRESOLVED` — nothing deployed |
| Video demo link | — | `UNRESOLVED` — kit is in [`VIDEO-KIT.md`](VIDEO-KIT.md) |

> **Do not paste a URL that is not resolved.** Two of the three are Stage One pass/fail
> gates. The per-axis map a judge scores against is [`JUDGING-AXES.md`](JUDGING-AXES.md);
> which CockroachDB and AWS services were used, and how, is
> [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md).
