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

**Every path on this page was checked to resolve on `2026-08-10`.** Every number carries the
artefact that produced it. Digits inside `code spans` are names (`v26.2.5`, SQLSTATE
`23514`), not measurements.

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
proves nothing about a live model today. No live Bedrock inference transcript is committed.
And the recall path crosses a region boundary on every embedding call with **no p50, no p99
and no load profile anywhere in the repository** — anyone quoting MAINLINE's recall latency
is guessing.

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

**Honest counterweight.** The AWS half has **nothing** in the EXERCISED column
([`docs/TOOL-USAGE.md`](../TOOL-USAGE.md)): the account is live and the models are enabled,
but every Terraform module is unapplied and every code path to a model is a cassette. Bedrock
Rerank is **not available** in `ap-southeast-2` and is listed as such rather than dropped.
`ccloud` `0.6.12` has no headless service-account authentication, and Cloud audit-log
endpoints `404` on the Basic tier, so the control-plane half of "custody of the custodian"
has **no input source on this tier**. Nothing has ever run against CockroachDB Cloud in CI.

---

## 3 · Real-World Impact

> **Take away:** the failure this addresses is not a missing document — it is a *defensible*
> change approved by people doing their jobs correctly, because the reason behind the rule
> left with the person who wrote it.

| Artefact | What it earns |
|---|---|
| [`docs/HONESTY.md`](../HONESTY.md) | The impact claim is bounded by the same document that bounds everything else. A safety-critical system whose vendor publishes its own failing counts is the only kind a regulated operator can adopt without doing the audit themselves. |
| [`VERIFY.md`](../../VERIFY.md) | Three tiers ordered by how much you must take on faith. **Tier 1** verifies a signed ledger offline with no credential, no network and no cluster. **Tier 2** — clone, `just up`, `just prove` — reproduces the refusal on a stranger's laptop with no account of ours and no model call. A safety claim a buyer cannot re-run is marketing. |
| [`evidence/deploy/cloud-chain.json`](../../evidence/deploy/cloud-chain.json) + [`evidence/deploy/chain-261.json`](../../evidence/deploy/chain-261.json) | The design has met a managed cluster, not only a laptop: the same `271` files applied against CockroachDB Cloud Basic in Singapore, `0` failed, `0` retries needed, `359.1` seconds against `46.35` locally. That ratio is the most useful number here for anyone budgeting a deployment, and it is measured rather than modelled. |

**Cost, stated plainly.** The cluster's configured `spend_limit` is `2500` — US$25.00/month,
a ceiling and not a spend ([`evidence/ccloud/cluster-list.txt`](../../evidence/ccloud/cluster-list.txt)).
The cheapest arrangement satisfying *"functional demo URL, free and unrestricted for judges"*
is a static console build with committed replay fixtures: no server, no credential, no
egress, **US$0/month**, against roughly US$5–8/month for the cheapest always-on container.

**Honest counterweight.** No real operator has used this, and no real data is in it. The
domain corpus was authored for this repository. **Inference is in Sydney and the database is
in Singapore, so any claim of end-to-end Australian data residency is false** for this
deployment — stated here, in `VERIFY.md`, in the README and in `docs/TOOL-USAGE.md`, and
nowhere rounded off. Every timing in the demo is a local timing against Docker on a laptop.
The AWS evidence store is **described, not exercised under load**: no bucket has been
applied, and the check that would compare object-lock modes against live object versions is
one of the seven cryptographic checks that did not run.

---

## 4 · Product Readiness — **the weakest axis, and we are saying so first**

> **Take away:** score this axis down. The engineering discipline here is real and the
> shipping readiness is not, and a submission that pretended otherwise would contradict the
> one thing it is actually selling.

**The measured reasons, each with its artefact:**

| Finding | Measurement | Source |
|---|---|---|
| The repository a judge would clone is **not public** | `visibility: PRIVATE`, `licenseInfo: null`, `homepageUrl: ""` | `gh repo view Shaugato/mainline`, run `2026-08-10` |
| The root licence exists on disk but is **untracked** | `?? LICENSE` | `git status --porcelain` |
| **Nothing is deployed** | no demo URL exists | [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) Part 4 |
| The conformance suite passes **10 of 71 declared cases** | `10` passed, `6` failed, `55` cannot-run, `0` errored | [`qa/conformance-census.json`](../../qa/conformance-census.json) |
| Lint is a published number, not a clean one | `847` `ruff` findings, `245` files `ruff format` would rewrite | [`qa/ruff-ratchet.json`](../../qa/ruff-ratchet.json) |
| Types likewise | `12` `mypy` errors over `477` checked source files | [`qa/mypy-ratchet.json`](../../qa/mypy-ratchet.json) |
| The test suite is not green | `8845` tests with no cluster: `8065` passed, `44` failed, `736` skipped | [`qa/test-state.json`](../../qa/test-state.json) |
| One target cannot be measured at all | `tests/integration` did not finish even with the ceiling raised to `2400` seconds | [`qa/test-state.json`](../../qa/test-state.json) |
| Custody verification is deliberately **not** a pass | exit `2`: `9` checks held, `0` failed, `7` never ran | [`qa/test-state.json`](../../qa/test-state.json) |

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

Both artefacts are **good news** — the forward-only deployment runner completed (`271` of
`271` files, `0` failed, nothing dirty, attestation head ordinal `271` at grade `strong`),
and the conformance suite was demonstrated end to end for the first time. The build went red
anyway, because the document had not caught up. **A repository that breaks its own build when
its documentation lags its evidence is the readiness signal here** — not the pass rate.

**Honest counterweight to the counterweight.** Do not over-credit that. `docs/HONESTY.md` is
stale right now, and the same section that predicted this breakage also still says
`qa/conformance-census.json` does not exist. The mechanism caught it; a human has not yet
fixed it. Separately, `.github/workflows/ci.yml` gates every substantive job behind a
`checkers` job — the program it named as missing has since landed, but **no GitHub Actions
run of the pipeline is recorded in this repository**, so every CI claim remains a claim about
a lane whose green nobody has observed.

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

---

## What a judge should do with all of this

1. **Run `just prove`.** Two minutes. If `VERDICT` is not `PROVEN`, mark the project down on
   axes 1 and 2 — that is what the artefact is for.
2. **Open [`docs/HONESTY.md`](../HONESTY.md) before the README.** It is the shortest route to
   an accurate picture, and it was written to be used against us.
3. **Score Product Readiness low.** It is the weakest axis, the reasons are counted above,
   and we would rather be marked accurately than believed generously.
4. **Check one number at random.** Every figure on this page and in
   [`DEVPOST.md`](DEVPOST.md) resolves to a file under `qa/` or `evidence/`. If one does not,
   that is a defect — and [`docs/HONESTY.md`](../HONESTY.md) says to report it.

Related: [`DEVPOST.md`](DEVPOST.md) — the submission text.
[`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) — which CockroachDB and AWS services, and how.
[`FIRST-FIVE-MINUTES.md`](FIRST-FIVE-MINUTES.md) — the judge's first five minutes, measured
on a fresh clone. [`VERIFY.md`](../../VERIFY.md) — three ways to check the claim without
trusting us.
