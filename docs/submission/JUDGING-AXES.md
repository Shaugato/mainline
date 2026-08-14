<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# JUDGING AXES — which artefact earns which score

Five axes, equally weighted: **Agentic Memory Design · Technological Implementation ·
Real-World Impact · Product Readiness · Creativity & Originality.**

This page is written for someone filling in a score sheet, not for someone deciding whether
to keep reading — that is [`DEVPOST.md`](DEVPOST.md). Each section gives the one sentence to
take away, the two or three artefacts that earn it with their exact paths, and **the honest
counterweight for that same axis**, drawn from [`docs/HONESTY.md`](../HONESTY.md).

The counterweights are the point. A submission that argues five axes and concedes nothing is
asking to be disbelieved on all five. Every limitation below is one we published before a
judge could find it, and each is a number with a file behind it.

**Every relative path on this page was re-resolved against the working tree on `2026-08-14`,
after this revision's edits: `60` links, `0` broken** — the same walk over
[`DEVPOST.md`](DEVPOST.md) returned `11` and `0`, over
[`RULES-MATRIX.md`](RULES-MATRIX.md) `12` and `0`, and over
[`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) `40` and `0`.
*(The same sentence read `2026-08-12` and gave no link count; a claim of "none broken" with no
denominator is unfalsifiable, so the denominator is now printed.)* Every number carries the
artefact that produced it. Digits inside `code spans` are
names (`v26.2.5`, SQLSTATE `23514`), not measurements. Where a figure below moved after an
earlier version of this page quoted it, the stale figure is named rather than deleted.

**Each of the five sections below is written to be scored alone.** A judge marking axis 3
reads §3 and nothing else: the take-away, the artefacts with their paths, the honest
counterweight, and — since `2026-08-14` — the **one path to open** that falsifies the section
if it does not say what the section says. The five axes are equally weighted by the rules, so
none of them is allowed to depend on another being read first.

**Fastest possible check — two minutes, no account, no credential:**

```bash
git clone -c core.longpaths=true <repo> && cd mainline
just up && just prove          # or: python scripts/proof/gate_refusal.py --dsn …
```

Expected last line: `VERDICT PROVEN`. If it says anything else, the central claim is
falsified and every axis below should be marked down. That is the intended failure mode.

---

## 1 · Agentic Memory Design

> **Take away:** memory here is not retrieval shown beside a decision — it is a
> **precondition of the state transition**, enforced by the database, so it cannot be
> dismissed, skipped, or routed around by a writer who did not use the application.

| Artefact | What it earns |
|---|---|
| [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2 | The memory model is a **normative specification**, not an implementation detail: PROJECT · PIN · REFUSE, with rules `P-1`–`P-5` and `N-1`–`N-4`. `P-2` forbids deriving a gate value from the inserting row; `P-3` says absence of evidence **refuses, never admits**; `N-3` forbids `CASCADE` in both positions, because a cascade rewrites history. |
| [`verticals/mainline/db/migrations/0120_trg_check_project.sql`](../../verticals/mainline/db/migrations/0120_trg_check_project.sql) + [`0115_fn_permit_merge_gate.sql`](../../verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql) + [`0050_permit.sql`](../../verticals/mainline/db/migrations/0050_permit.sql) | The three steps as shipped SQL: the trigger that projects a cross-row fact onto a scalar of the subject row, the gate function that **re-derives** rather than trusts it, and the plain-column `CHECK` that refuses for every writer forever. |
| [`evidence/gate-refusal/proof-20260810T054407Z.json`](../../evidence/gate-refusal/proof-20260810T054407Z.json) | The design is not asserted, it is **executed**. `projection.severity`: the client supplied `0`, the trigger projected `4` onto a row the client never touched. A counter a client writes is a client's opinion; a counter a trigger writes is the database's. `10` projection assertions, all holding. |

**Why the memory has semantics rather than being a document store:** provenance (clause → the
incident that wrote it), ancestry (a commit DAG that is walked, not a "related documents"
list), severity floors (a fatality's relevance never decays), archival bonds (recall keyed to
an activity taxonomy, not keywords), fixity (as-documented reconciled against as-operated),
and **logged silence** — every precursor the system *declined* to surface is recorded with
its arithmetic. The last one is the unusual commitment: a recall system that cannot be
audited on what it withheld is not auditable at all.

**Honest counterweight.** The corpus is **authored** — the compressor-setpoint story is a
designed worked example, no real incident, no real site, no real fatality
([`docs/HONESTY.md`](../HONESTY.md) § SYNTHETIC). The agent layer's model transcripts are
**recorded cassettes**; a green agent test proves the code handles that recorded exchange and
proves nothing about a live model today. An earlier version of this line went on to say that
no live Bedrock inference transcript was committed, and on `2026-08-11` that stopped being
true: [`evidence/deploy/aws-live.json`](../../evidence/deploy/aws-live.json) records four
calls in `ap-southeast-2`, each with an AWS request id, and a Titan v2 embedding of dimension
`1024` at L2 norm `1.0`. The cassettes remain what the *test suite* replays; the transcript is
a separate and narrower claim. And the recall path crosses a region boundary on every
embedding call with **no p50, no p99 and no load profile anywhere in the repository** — anyone
quoting MAINLINE's recall latency is guessing.

**OPEN THIS TO CHECK IT — [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2**, then
any file in [`evidence/gate-refusal/`](../../evidence/gate-refusal/). The single field that
decides this axis is `projection.severity`: the client supplied `0` and the trigger projected
`4` onto a row the client never touched, with `10` of `10` projection assertions holding
(`evidence/gate-refusal/proof-20260810T054407Z.json#projection`). If that field shows the
client's own number, memory here is a cache and this axis is falsified.

---

## 2 · Technological Implementation

> **Take away:** the refusal lives in CockroachDB — constraints, triggers, `SERIALIZABLE` —
> so it holds against `psql`, a migration script and a back-office correction alike, and the
> repository proves that by attacking it rather than by demonstrating it.

| Artefact | What it earns |
|---|---|
| [`scripts/proof/gate_refusal.py`](../../scripts/proof/gate_refusal.py) → [`evidence/gate-refusal/proof-20260810T054407Z.json`](../../evidence/gate-refusal/proof-20260810T054407Z.json) | Three beats, one command. `23514` `gate_closed_when_issued` (source `reported`); then **the same permit refused again at `P0001` `mainline.fn_permit_merge_gate` after the projected counter was forged to zero out of band** (source `parsed`); then `00000` ADMITTED after one signed disposition. Verdict `PROVEN`, `0` caveats. |
| [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) + [`evidence/tool-usage/`](../../evidence/tool-usage/) | The rules ask which CockroachDB and AWS services were used **and how**. `4` CockroachDB tools, `10` engine features accounted separately, `12` AWS services — each with a verdict of EXERCISED / DESIGNED / NOT-AVAILABLE and a file-and-line anchor. `python scripts/submission/capture_tool_evidence.py --check` exits 1 if any count is stale. |
| [`packages/trappoint-migrate/src/trappoint_migrate/attest.py`](../../packages/trappoint-migrate/src/trappoint_migrate/attest.py) | The gate is **self-attesting**: `pg_get_triggerdef()` and `pg_get_functiondef()` are hashed into a chained schema attestation, so the gate's own source text is inside the record. Nobody quietly weakens the gate that prevents quietly weakening controls. A fallback records `attestation_grade="weak"` instead of pretending equivalence. |

**The detail worth a second look.** The middle beat is the whole architecture under attack. A
"materialised conflict" design is only as good as its resistance to a forged projection, so
the proof forges one. The gate re-derives the obligation count and refuses anyway: **P2
projections are enforced, never trusted.** The third beat matters equally — a gate that
always refuses is broken, not safe.

**Honest counterweight.** An earlier version of this page said the AWS half had **nothing** in
the EXERCISED column. That was true when it was written and is not true now, and the honest
correction is small rather than flattering: the census at
[`evidence/tool-usage/aws-services.json`](../../evidence/tool-usage/aws-services.json) carries
`12` service rows and only `3` of them are EXERCISED — the two Bedrock rows and CloudWatch.
`8` are DESIGNED and `1` is NOT-AVAILABLE, every Terraform module is unapplied, and Bedrock
Rerank is absent in `ap-southeast-2` and listed as such rather than dropped. Re-derive it with
`python scripts/submission/capture_tool_evidence.py --check`, which exits non-zero when any
count in that file has gone stale — on `2026-08-14` it exits **`2`**, refusing before any count
is computed because two of its declared source anchors have drifted off their subject, and
`docs/TOOL-USAGE.md` names that regeneration as owed rather than hiding it.
*If you also run `python scripts/submission/check_submission_ready.py` you will read
`10 AWS services` there against the `12` here: the gate holds a fixed table of ten service
names and asks which this repository mentions, while the census emits one row per distinct
use and Bedrock appears three times. Neither number was moved to match the other; the
arithmetic is in `docs/TOOL-USAGE.md` Part 2 and in `RULES-MATRIX.md` §1.*
`ccloud` `0.6.12` has no headless service-account authentication,
and Cloud audit-log endpoints `404` on the Basic tier, so the control-plane half of "custody
of the custodian" has **no input source on this tier**.
Nothing has ever run against CockroachDB Cloud in CI.

**What CockroachDB Cloud does and does not carry, in the same words this repository uses
everywhere else.** The paragraph below is the ruling text, reproduced verbatim so that this
page, `docs/STATE-OF-THE-BUILD.md`, `docs/HONESTY.md` and `docs/CI-STATE.md` cannot drift
apart on it:

> **CockroachDB Cloud carries the demo world, and the gate refuses there.** The migration chain
> is `APPLIED` and the seeded world is `SEEDED AND REFUSABLE` against
> `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`, database `mainline_demo`,
> CockroachDB CCL v26.2.5 — the refusal observed on Cloud is `23514`
> `gate_closed_when_issued`, with `nothing_persisted: true`
> [src: `evidence/deploy/cloud-chain.json#outcome`, `evidence/deploy/cloud-seed.json#verdict`,
> `#verification`].
>
> **The four-beat run through the HTTP handler has NOT been recorded against Cloud.** The
> operator reports it in the body of commit `7535670`; that commit's diff carries no such
> artefact, and `evidence/` holds none. **OWED:** re-run `scripts/deploy/…` against Cloud with
> `--out evidence/deploy/cloud-gate-run.json`, and only then may a Cloud `PROVEN` appear on
> this page. Until it exists, the only `PROVEN` this repository holds is
> `evidence/gate-refusal/proof-20260814T032418Z.json`, and it is **local**
> (`cluster.database = w_qr_gate_refusal_proof`).

**OPEN THIS TO CHECK IT — [`scripts/proof/gate_refusal.py`](../../scripts/proof/gate_refusal.py).**
Run it against a bare local node and read the last line. The committed transcript it writes is
[`evidence/gate-refusal/proof-20260814T032418Z.json`](../../evidence/gate-refusal/proof-20260814T032418Z.json):
verdict `PROVEN`, `caveats: []`, chain `271/271`, `PROJECTION 10/10`,
`REFUSAL [23514]`, `DRIFT [P0001]`, `ADMISSION [00000]`. If that last word is anything but
`PROVEN`, this axis is falsified and should be scored as such.

---

## 3 · Real-World Impact

> **Take away:** the failure this addresses is not a missing document — it is a *defensible*
> change approved by people doing their jobs correctly, because the reason behind the rule
> left with the person who wrote it.

| Artefact | What it earns |
|---|---|
| [`docs/HONESTY.md`](../HONESTY.md) | The impact claim is bounded by the same document that bounds everything else. A safety-critical system whose vendor publishes its own failing counts is the only kind a regulated operator can adopt without doing the audit themselves. |
| [`VERIFY.md`](../../VERIFY.md) | Three tiers ordered by how much you must take on faith. **Tier 1** verifies a signed ledger offline with no credential, no network and no cluster. **Tier 2** — clone, `just up`, `just prove` — reproduces the refusal on a stranger's laptop with no account of ours and no model call. A safety claim a buyer cannot re-run is marketing. |
| [`evidence/deploy/cloud-chain.json`](../../evidence/deploy/cloud-chain.json) + [`evidence/deploy/chain-261.json`](../../evidence/deploy/chain-261.json) | The design has met a managed cluster, not only a laptop: the same `271` files applied against CockroachDB Cloud Basic in Singapore, `0` failed, `0` retries needed, `359.1` seconds (`#chain_seconds`; `#total_seconds` is `388.9` and includes bootstrap — open the file and you meet the larger number first, so both are named here) against `46.35` locally (`chain-261.json#wall_clock_seconds`). That ratio is the most useful number here for anyone budgeting a deployment, and it is measured rather than modelled. **It is a DDL measurement and not a retrieval one**, and this repository publishes no interval for the recall hop because nobody has taken one. |

**Cost, stated plainly.** The cluster's configured `spend_limit` is `2500` — US$25.00/month,
a ceiling and not a spend ([`evidence/ccloud/cluster-list.txt`](../../evidence/ccloud/cluster-list.txt)).
The arrangement that satisfies *"functional demo URL, free and unrestricted for judges"* is a
single Lambda Function URL with `authorization_type = NONE` serving both the console and
`/v1/*`, estimated at roughly **US$0.02/month** and planned at
`Plan: 24 to add, 0 to change, 0 to destroy.` — line `843` of
[`evidence/deploy/terraform-plan-furl.txt`](../../evidence/deploy/terraform-plan-furl.txt),
which is **`11` resources in `module.api[0]` and `13` in `module.guard[0]`**, the cost guard
`infra/envs/demo/main.tf:631` instantiates.
*This paragraph said `11 to add` until 2026-08-14. The `11` was never wrong and is still
there — it is the API module alone — but it stopped being the plan's total the moment the
guard was wired in, and nothing re-read the plan afterwards. The artefact was regenerated and
this sentence was corrected against it; the artefact was not touched.*
An earlier version of this paragraph costed a static console build with replay fixtures at
US$0/month; that shape was abandoned because the console alone does not exercise the gate, and
because CloudFront cannot be created on this account at all — see §4. The estimate is an
estimate: **no bill has been observed, because nothing has been applied.**

**Honest counterweight.** No real operator has used this, and no real data is in it. The
domain corpus was authored for this repository. **Inference is in Sydney and the database is
in Singapore, so any claim of end-to-end Australian data residency is false** for this
deployment — stated here, in `VERIFY.md`, in the README and in `docs/TOOL-USAGE.md`, and
nowhere rounded off. Every timing in the demo is a local timing against Docker on a laptop.
The AWS evidence store is **described, not exercised under load**: no bucket has been
applied, and the check that would compare object-lock modes against live object versions is
one of the seven cryptographic checks that did not run.

**OPEN THIS TO CHECK IT — [`VERIFY.md`](../../VERIFY.md).** Tier 2 is the one that decides
this axis: clone, `just up`, `just prove`, and the refusal reproduces on a stranger's laptop
with no account of ours and no model call. A safety claim a buyer cannot re-run is marketing.
The managed-cluster half is
[`evidence/deploy/cloud-chain.json`](../../evidence/deploy/cloud-chain.json) —
`files 271 · applied 271 · failed 0` against CockroachDB Cloud Basic in `aws-ap-southeast-1`.

---

## 4 · Product Readiness — **the weakest axis, and we are saying so first**

> **Take away:** score this axis down. The engineering discipline here is real and the
> shipping readiness is not, and a submission that pretended otherwise would contradict the
> one thing it is actually selling.

**The measured reasons, each with its artefact.** Every row below was re-derived on
`2026-08-14` **from the artefact its own Source column names**, one row at a time and never
from the row above it — which is how four of them were found to have drifted. Where a figure
moved, the superseded one is named in the same cell.

| Finding | Measurement | Source |
|---|---|---|
| **Nothing is deployed.** `terraform apply` has not been run | `demo_url` holds the literal `UNRESOLVED` | [`docs/submission/SUBMISSION.json`](SUBMISSION.json); `python scripts/submission/check_submission_ready.py` |
| The plan that would deploy it is written and unapplied | `Plan: 24 to add, 0 to change, 0 to destroy.` — `11` in `module.api[0]`, `13` in `module.guard[0]`, the cost guard `infra/envs/demo/main.tf:631` instantiates. *This cell said `11 to add` and cited `terraform-plan-furl.txt:339` until 2026-08-14. Both digits were stale, and the correction went one way only: the document was re-read against the artefact, and the artefact was not touched.* | [`evidence/deploy/terraform-plan-furl.txt`](../../evidence/deploy/terraform-plan-furl.txt) line `843` |
| The end-to-end acceptance run does not reach its contract | `"verdict": "NOT PROVEN"` at `generated_at 2026-08-13T01:47:58Z`, with `10` named failures — both runs reach beat `4` and are refused `23503 disposition_signer_credential_id_fkey`, with no `clearance_digest` on the admission beat. *This cell said `2026-08-11T05:43:54Z` with `4` failures, which was two regenerations behind; the count went UP and is published as it stands* | [`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json) |
| The conformance suite has never been demonstrated | `10` passed, `6` failed, `55` cannot-run, `0` errored, over `71` selected | [`qa/conformance-census.json`](../../qa/conformance-census.json) `totals`, `selected` |
| Lint is a published number, not a clean one | `671` `ruff` findings — down from the `847` an earlier version of this row carried — and `0` files `ruff format` would rewrite | [`qa/ruff-ratchet.json`](../../qa/ruff-ratchet.json) `lint.total`, `format.unformatted_files` |
| Types likewise, and this one is now a zero with its denominator | `0` `mypy` errors over `660` checked source files; the row used to read `12` over `477` | [`qa/mypy-ratchet.json`](../../qa/mypy-ratchet.json) `total_errors`, `source_files_checked` |
| The test suite is not green | `9290` tests with no cluster: `8323` passed, `44` failed, `923` skipped, generated `2026-08-09T22:44:59Z`. *This cell read `8845` / `8065` / `44` / `736` until 2026-08-14 — the census taken before the demo API's own rows were merged into it. `docs/HONESTY.md` and `DEVPOST.md` were re-derived against the artefact days before this page was, and for those days the two disagreed; the artefact was right both times* | [`qa/test-state.json`](../../qa/test-state.json) `totals.none` |
| One target cannot be measured at all | `tests/integration` under `--crdb=reuse` was killed at `2400.02` seconds having written no JUnit XML, so `tests: 0` there is *unmeasured*, not *none* | [`qa/test-state.json`](../../qa/test-state.json) `packages."tests/integration".runs.cluster` |
| Custody verification is deliberately **not** a pass | exit `2`: `9` checks held, `0` failed, `7` never ran, of `16` | [`qa/test-state.json`](../../qa/test-state.json) `external_checks.custody_bundle_verification.counts` |
| Master is more red than green, and got redder today | Latest run of each workflow: **`20` workflows, `8` success, `12` failure**. *The two figures this row has carried are both kept: `18` workflows at `8`/`10`, re-derived `2026-08-12T14:58Z` at `1d41442`; and `20` workflows at `11`/`9`, re-derived earlier on `2026-08-14`. The board moved against us between two runs of the same command on the same day, which is the reason this row prints the command and not a remembered number* | `gh run list --branch master --limit 300`, re-derived `2026-08-14` after the `04:29Z` push. `gh` lists `21` names because `cluster-lane-bites` appears twice, once under its file path; collapsed, `20` |

**Two rows that were on this list are off it, and the removal is recorded rather than
silent.** The repository was `PRIVATE` when this page was first written and is now `PUBLIC` —
`gh repo view Shaugato/mainline --json visibility,licenseInfo` answers
`{"visibility":"PUBLIC","licenseInfo":{"key":"apache-2.0"}}` — and the root `LICENSE`, which
was untracked, is tracked and reads as Apache-2.0 at `11357` bytes. Neither is an achievement;
they were table stakes, and the only reason to mention them is that a document which quietly
drops its own failing rows cannot be trusted with the ones it keeps.

**And one constraint that is not ours to fix.** The demo origin is a Lambda Function URL
rather than CloudFront because AWS will not create new CloudFront distributions on this
account. That is not a Terraform problem, an IAM problem or a module problem: a real apply on
`2026-08-10` reached the distribution and was refused, and the same refusal comes back from a
bare `aws cloudfront create-distribution` with a three-field config and no Terraform anywhere.
AWS's words, quoted verbatim and kept verbatim in
[`docs/deploy/RUNBOOK.md`](../deploy/RUNBOOK.md) Appendix A with the `RequestID` intact:

<!-- prose-hygiene: quoting -->
> `AccessDenied: Your account must be verified before you can add new CloudFront resources.`
> `To verify your account, please contact AWS Support and include this error message.`

Only AWS Support can lift it, the runbook is written as though it never clears, and the
identity that was refused holds `AdministratorAccess`.

**Now the part that should recover some of the mark: those numbers are falsifiable and
monotone.** Each is a **ratchet** — a frozen figure in a committed JSON file that may fall
and may not rise. `scripts/qa/ruff_ratchet.py` gates **per rule and per tree**, not on a
headline sum, so a change that removes twenty findings in one directory and adds five
hard-gate violations in another cannot buy its way past with the total.
[`scripts/qa/check_reuse.py`](../../scripts/qa/check_reuse.py) does the same for licence
headers against [`qa/reuse-ratchet.json`](../../qa/reuse-ratchet.json), separating *gated*
counts from *recorded* ones so numbers that legitimately move in both directions are not
pretended to be gates. Re-baselining is the only way a number rises, and it leaves a diff.

**And the discipline is enforced against the prose, not just the code.**
[`tests/release/test_honesty_is_checkable.py`](../../tests/release/test_honesty_is_checkable.py)
reads [`docs/HONESTY.md`](../HONESTY.md), extracts every number, follows every reference, and
fails when a number and its source disagree, when a citation points outside `qa/` or
`evidence/`, when a cited file is gone, or when a number carries no reference at all. It also
plants one of every violation family into a synthetic document and requires the checker to
fire on each — because a lint that has never been red asserts nothing.

**One rule runs the other way, and it is red as this page is written.**
`test_the_document_does_not_lag_a_family_that_landed` fails when evidence *appears* that the
prose has not absorbed. Run on `2026-08-10`:

```
1 failed, 33 passed
AssertionError: docs/HONESTY.md is behind its own evidence:
  family 'chain-run' has 1 file(s) on disk (evidence/chain/chain-20260810T062542Z.json) …
  family 'conformance-census' has 1 file(s) on disk (qa/conformance-census.json) …
```

One of those artefacts is **good news**: the forward-only deployment runner completed —
`271` of `271` files, `0` failed, nothing dirty, attestation head ordinal `271` at grade
`strong`, in `evidence/chain/chain-20260810T062542Z.json`.

The other is a census, and it is **not** a demonstration. The conformance suite has never been
demonstrated end to end: run against a bare node its cases error rather than skip, which is
why `qa/conformance-census.json` reports `55` of `71` as cannot-run with the missing object
named on each. Exactly two of the declared cases have been exercised anywhere in this
repository — CF-01 and CF-03 — and they were exercised by `scripts/proof/gate_refusal.py`
rather than by the suite. That is a smaller claim than "the suite ran", and it is the one this
page will make. An earlier version of this paragraph said the suite had been demonstrated end
to end for the first time; `scripts/submission/check_submission_prose.py` rule
`SUB-05-conformance-passes` caught the sentence in our own document and this is the
replacement it asked for.

The build went red on both artefacts anyway, because the document had not caught up. **A
repository that breaks its own build when its documentation lags its evidence is the readiness
signal here** — not the pass rate.

**Honest counterweight to the counterweight.** Do not over-credit that. *This paragraph said
`docs/HONESTY.md` "is stale right now, and the same section that predicted this breakage also
still says `qa/conformance-census.json` does not exist". Re-read on `2026-08-14`, that is no
longer true of the tree: `docs/HONESTY.md:837` now quotes its own superseded sentence and
absorbs the census in a table at `:846-853`, with `[src: qa/conformance-census.json#…]` on
every figure. The lag was real and it closed; the sentence is corrected rather than deleted,
because the correction is only checkable against the claim it corrects.* What has **not**
closed is the census itself — `55` of `71` still cannot run. Separately, an earlier version of
this paragraph said **no GitHub Actions run of the pipeline was recorded in this
repository**. That has since been fixed and the fix is not
flattering: [`docs/CI-STATE.md`](../CI-STATE.md) now names every workflow with its run id, and
what those run ids show is a board that is more red than green. Re-derived on `2026-08-14`
with `gh run list --branch master --limit 300`, taking the latest run of each: **`20`
workflows, `8` success, `12` failure.** *Two earlier readings of the same command are kept
beside it — `18` workflows at `8`/`10` on `2026-08-12` at commit `1d41442`, and `20` at
`11`/`9` earlier on `2026-08-14`.* Several of the reds report a true incompleteness and are
meant to stay red; `docs/CI-STATE.md` is the page that says which, and it is not this page's
to write. The observation problem is solved; the lanes are not.

**OPEN THIS TO CHECK IT — [`docs/submission/SUBMISSION.json`](SUBMISSION.json), then
`python scripts/submission/check_submission_ready.py`.** The checker prints one row per
requirement with the literal command that resolves it and refuses to call the submission ready
while any row is unresolved. Run on `2026-08-14` against this working tree it printed
**`NOT READY`, `3` unresolved rows of `10`, `0` NOT CHECKED**: `demo_url` and `video_url`,
which are the two this page has always said are open, plus `remote_sync`, which is `4` commits
ahead of `origin/master` with uncommitted paths and clears on a push. A `FAIL` row on that
output is this axis, stated by a program rather than by us.

---

## 5 · Creativity & Originality

> **Take away:** the original move is a *category* distinction with a mechanism behind it —
> every shipping permit system gates on the present state of the world, and this one gates on
> **ancestry** — and the mechanism is three ordinary SQL features composed into something
> none of them does alone.

| Artefact | What it earns |
|---|---|
| [`skills/designing-diachronic-gates/`](../../skills/designing-diachronic-gates/) | The idiom is generalised out of the product into a **CockroachDB Agent Skill**, and it ships a program that falsifies it: [`scripts/assert_gate_refuses.py`](../../skills/designing-diachronic-gates/scripts/assert_gate_refuses.py) spins a throwaway node, replays an illegal history, and fails unless the expected SQLSTATE **and** constraint name are raised. A skill whose advice cannot be falsified is a blog post. |
| [`skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py`](../../skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py) | The second skill encodes a platform fact discovered the hard way — a prefix-constrained ANN query uses the C-SPANN index **only when the index is named in the query** — and fails when the plan stops choosing it. An ANN query that quietly fell back to a scan is otherwise indistinguishable from one that did not. |
| [`evidence/producers/producer-census-before.json`](../../evidence/producers/producer-census-before.json) | The most original *finding* in the build, and it is a negative result: **a defect census built from error messages measures only what the error messages can express.** CockroachDB names one absent relation per statement, so a table shadowed behind another in every view that joined them was invisible to a SQLSTATE census — permanently. The count read five; the truth was seven. |

**Three smaller ideas that are unusual on their own.** *Refusal is structurally redundant* —
an unwelding harness disables the trigger and drops the constraint, one at a time, and the
write still fails. *The ledger is gap-free by compare-and-swap, not by sequence* —
`CREATE SEQUENCE` is banned repo-wide because sequence updates are not rolled back, so a gap
**means** tampering. *Every refusal emits a minimal unsatisfiable subset* and, where
computable, the nearest admissible alternative — because a gate that only says "no" gets
routed around, and an invariant that is routed around is not an invariant.

**Honest counterweight.** The idea is the strong part and the demonstration is narrower than
the idea. `AS OF SYSTEM TIME` is deliberately **not** sold as "prove the state at time T" —
[`packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py`](../../packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py)
exists to show it cannot, and long-horizon reconstruction is an application-level commit DAG
instead. Six conformance capability tokens name relations this repository has **deliberately
not authored** — `propagation`, `observed_assertion`, `merge_conflict`, `frontier_move`,
`discordance_warrant`, `coverage_certificate` — so those cases cannot pass and report
cannot-run with the object named. The novel algorithms described in the design notes
(ORIGINDIFF and the salami defence among them) are **specified, not demonstrated**; no
committed artefact exercises them end to end.

**OPEN THIS TO CHECK IT — [`skills/designing-diachronic-gates/`](../../skills/designing-diachronic-gates/).**
Its `scripts/assert_gate_refuses.py` spins a throwaway node, replays an illegal history, and
fails unless the expected SQLSTATE **and** the expected constraint name are raised. If the
skill's own assertion cannot be made to go red, the idiom it teaches is unfalsifiable and this
axis is worth less than it claims.

---

## What a judge should do with all of this

1. **Run `just prove`.** Two minutes. If `VERDICT` is not `PROVEN`, mark the project down on
   axes 1 and 2 — that is what the artefact is for. The most recent committed transcript is
   [`evidence/gate-refusal/proof-20260814T032418Z.json`](../../evidence/gate-refusal/proof-20260814T032418Z.json),
   `2026-08-14`, verdict `PROVEN` with `caveats: []`, in a throwaway database on the pinned
   local node (`cluster.database = w_qr_gate_refusal_proof`): `chain 271/271 applied, 0 failed`,
   `PROJECTION 10/10 held`, `REFUSAL REFUSED [23514] gate_closed_when_issued (reported)`,
   `DRIFT REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)`,
   `ADMISSION ADMITTED [00000]`. **That `PROVEN` is local.** The equivalent four-beat run
   through the HTTP handler against CockroachDB Cloud is **OWED** and is quoted in full in §2.
2. **Open [`docs/HONESTY.md`](../HONESTY.md) before the README.** It is the shortest route to
   an accurate picture, and it was written to be used against us.
3. **Score Product Readiness low.** It is the weakest axis, the reasons are counted above,
   and we would rather be marked accurately than believed generously. The single sharpest
   check is `python scripts/submission/check_submission_ready.py`: re-run on `2026-08-14` it
   printed `3` unresolved rows of `10` with `0` NOT CHECKED and exited `1` — `demo_url`,
   `video_url` and `remote_sync`. It printed the same three on `2026-08-12`. Two of them are
   the founder's, and the third is a dirty working tree that clears on a push.
4. **Check one number at random.** Every figure on this page and in
   [`DEVPOST.md`](DEVPOST.md) resolves to a file under `qa/` or `evidence/`, or to a command
   printed beside it. If one does not, that is a defect — and
   [`docs/HONESTY.md`](../HONESTY.md) says to report it.
5. **Notice which claims on this page are written as "was X, is now Y", and which way each
   moved.** Toward us: the repository's visibility, the tracked `LICENSE`, `ruff` `847`→`671`
   with `245`→`0` unformatted, `mypy` `12`/`477`→`0`/`660`, the AWS EXERCISED column going
   from empty to `3` of `12`, a committed live Bedrock transcript where there was none, and
   recorded GitHub Actions runs where there were none. Away from us: the conformance suite,
   which this page previously said had been demonstrated end to end and which has in fact
   never been demonstrated; the demo's cost, which was written as US$0/month for a static
   console that was abandoned because it does not exercise the gate; the shipping plan, which
   this page quoted as `11 to add` while the committed artefact reads
   `Plan: 24 to add, 0 to change, 0 to destroy.`;
   the acceptance run, whose named failures went from `4` to `10`; and the no-cluster test
   census, which this page read as `8845`/`8065`/`44`/`736` while the artefact said
   `9290`/`8323`/`44`/`923`. Those recorded runs also showed a board that moved from `8` green
   / `10` red on `2026-08-12` to `8` green / `12` red on `2026-08-14`. A page that keeps only
   the flattering half of its own drift is not a register, it is an advertisement.

Related: [`DEVPOST.md`](DEVPOST.md) — the submission text.
[`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) — which CockroachDB and AWS services, and how.
[`FIRST-FIVE-MINUTES.md`](FIRST-FIVE-MINUTES.md) — the judge's first five minutes, measured
on a fresh clone. [`VERIFY.md`](../../VERIFY.md) — three ways to check the claim without
trusting us.
