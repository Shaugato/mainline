<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# ROADMAP

**Who this is for.** Anyone outside the project who wants to know what MAINLINE does not do
yet, what stands in its place today, and what we intend to build next.

**What this is not.** It is not the honesty register. [`docs/HONESTY.md`](docs/HONESTY.md) is
that, and it governs wherever the two disagree. This page reorders what that page already
records. It withdraws nothing and it softens no number.

Every quantity below names the committed file it came from. No dates are promised here. The
work that comes first is called *next* and the work behind it is called *after that*, because a
date we cannot keep is a claim like any other.

## Where this is today

MAINLINE is **pre-alpha**. One mechanism is finished, and a stranger can reproduce it on a
laptop in four commands.

A **`CHECK` constraint** is a rule the database applies to every write, from every client. Ours
refuses to merge a permit to work while an **obligation** is open — an obligation being a lesson
from a past incident that this job has not answered yet. The committed proof run applies 271
migration files, fails 0, and records verdict `PROVEN` with an empty caveat list
[src: evidence/gate-refusal/proof-20260816T151248Z.json]. A **SQLSTATE** is the five-character
code the database itself returns for a step. That run refuses the merge with SQLSTATE `23514` on
the constraint `gate_closed_when_issued`. It then refuses a second time with `P0001`, once the
counter it reads has been forced to zero out of band.

What is not finished is most of what surrounds that mechanism: the suite that would test it
broadly, the cryptographic half of the evidence bundle, and the greater part of the deployment
surface. Those are the sections below, in that order.

## What is next

Every entry below has the same three parts, on purpose: **what is not there**, what stands in its
place *today*, and what happens *next*. The middle part is the one most roadmaps leave out, and it
is usually the one worth reading. A gap with something working in front of it is a different
situation from a gap with nothing in front of it.

Items come off this list by being built, not by being reworded.

### Proving the substrate more widely

**The conformance suite has never been demonstrated.** Two cases — CF-01 and CF-03 — are demonstrated instead by `scripts/proof/gate_refusal.py`, which is a smaller claim and a true one.

*Today.* The manifest declares 71 cases. One census, run to completion against a migrated
cluster, records 10 that held, 6 that answered wrongly and 55 that could not run at all
[src: qa/conformance-census.json#totals]. **A modest first result is not a passing suite.** Every
case that ended anywhere but passing names the object it wanted, and the census refuses to record
one that does not [src: qa/conformance-census.json#completeness].

*Next.* One setup defect is wearing 46 case identifiers: the legal world fails to build at
`clause_version` because the column `body_sha256` does not exist
[src: qa/conformance-census.json#systemic_causes.0.n]. That single column is the largest move
available. *After that:* the 6 cases that answered wrongly, each already quoted verbatim in the
artefact, and the 6 whose capability tokens name relations this repository has deliberately not
authored.

**Not there yet: the third tier of verification.**

*Today.* [`VERIFY.md`](VERIFY.md) orders three ways of checking us by how much you have to take
on faith, and records what each returns rather than what it should return. Tier 2 — the four
commands on your own laptop — returns exit 0 and `VERDICT PROVEN`. Tier 3 points your own agent
at CockroachDB's managed endpoint with none of our code in the path, and was not run for this
revision.

*Next.* Run Tier 3 with a scoped key and commit the transcript. With no key its suites skip with
a written reason and never pass, which is the behaviour we want and is not a result.

**Not there yet: a test that exercises a live model.**

*Today.* The corpus is authored, and the model transcripts are recorded cassettes — saved
request-and-response pairs replayed offline. A green agent test shows our code handles that
recorded exchange; it shows nothing about a live model today. Where a live call is genuinely
required, the test skips with a reason and the reason is in the census.

*Next.* A lane that makes a live call against a recorded contract, so that a model whose
behaviour has moved fails something. Until then the cassettes are what the agent tests are, and
we will not describe them as anything more.

### The custody bundle's cryptographic half

**Not there yet: signature verification over the evidence ledger.**

*Today.* The offline bundle check registers 16 checks and 7 of them have no runner bound
[src: qa/test-state.json#external_checks.custody_bundle_verification.counts]. Those 7 are the
cryptographic half: log signature, RFC-3161 bracket, beacon, witness quorum, S3 object-lock,
gate self-attestation and WebAuthn re-verification. What the tool verifies today is the Merkle
structure — the tree of hashes over the ledger — and not the signatures over it. It exits
non-zero and says so about itself; the exact counts and the exit code, with their measurement
dates, are in [`VERIFY.md`](VERIFY.md) Tier 1 and [`docs/HONESTY.md`](docs/HONESTY.md).

*Next.* The 7 runners under `packages/trappoint-verify/src/trappoint_verify/checks/`. Until they
exist the `custody-chain` lane stays red on purpose. Marking a check that did not run as passed
is the one repair that is forbidden, because *did not run* and *ran and held* are different
findings.

### CockroachDB Cloud, and what our automation has never touched

**Our automation has never pointed at the managed cluster.** Nothing has ever run against CockroachDB Cloud in CI. The cluster exists and there is a captured transcript; no automated lane has ever pointed at it.

*Today.* The whole migration chain has been driven against that cluster by hand: 271 files, 271
applied, 0 failed [src: evidence/deploy/cloud-chain.json]. Captured sessions sit under
`evidence/ccloud/` and `evidence/deploy/`, and every one of them was driven by hand.

*Next.* A lane that points at it. *After that:* the four-beat run through the HTTP handler
recorded against Cloud, which [`docs/CI-STATE.md`](docs/CI-STATE.md) §1.0.4 records as owed and
which no artefact holds today.

### The AWS surface

**Not there yet: 6 of the 12 AWS services in the design.**

*Today.* Of 12 services, 6 are EXERCISED, 5 are DESIGNED and 1 is NOT-AVAILABLE
[src: evidence/tool-usage/aws-services.json#totals.by_verdict]. DESIGNED means the code or
configuration is finished and on disk, and nothing we recorded has run it end to end. The 5 are
S3 with Object Lock, KMS, CloudTrail, CloudFront and EventBridge — no evidence bucket, no
signing key, no trail, no distribution, no schedule rule. Bedrock Rerank is the NOT-AVAILABLE
one: AWS does not offer it where our inference runs.

*Next.* CloudFront is not deferred by choice; it is blocked. A real apply returned
`AccessDenied: Your account must be verified before you can add new CloudFront resources.`, kept
verbatim with its request identifier in [`docs/deploy/RUNBOOK.md`](docs/deploy/RUNBOOK.md)
Appendix A. Only AWS Support can lift that hold, so the demo's origin is the Lambda Function URL
itself until they do. *After that:* the evidence store, which is what the S3, KMS and CloudTrail
rows are for.

**Not there yet: the deny-first policies on the evidence store.**

*Today.* The AWS IAM row is narrower than its title. What ran is the execution role's single
allow, and the deny-first evidence-store policies remain unapplied.

*Next.* Apply them in the same wave as the evidence store above, because a policy with nothing
to guard cannot be tested, and an untested deny is a comment.

**Not there yet: model inference inside the demo request path.**

*Today.* Bedrock executes in this repository and **not** in the demo request path. Inference
runs in `ap-southeast-2` while the database is in `aws-ap-southeast-1`, because
`ap-southeast-2` is Advanced-tier only on CockroachDB Cloud. What that split does and does not
entitle us to say is set out in [`docs/HONESTY.md`](docs/HONESTY.md).

*Next.* Either co-locate the two, which needs the Advanced tier, or measure the hop under load
and publish the measurement. Neither has been done, and until one is, the split stands as
written rather than as a plan we imply is closed.

### The live demo

**Not there yet: use case two driven beat by beat over the public address.**

*Today.* We have driven use case one over the public address but not use case two, so we claim
the first beat-for-beat over that address and not the second. A read-only check on 2026-08-17
found the route deployed and answering, and that reading is recorded with its date
[src: docs/submission/LIVE-STATUS.md §2].

*Next.* Drive a `POST` through the public origin and commit an artefact that names the address
it ran against. An artefact that does not name where it ran does not settle where it ran.

**Not there yet: two of use case two's beats.**

*Today.* Use case two plays three beats and declines two — `admission_beat: null` and
`kernel_procedure_beat: null` — each with the reason its own payload gives, because a beat
dressed to look passing would be a fabricated exhibit
[src: docs/submission/LIVE-STATUS.md §1].

*Next.* Build what each declined beat needs, then let it play. Filling them in ahead of that is
the one shortcut this project will not take.

### The permit screen does not show the question; the change screen does

**Not there yet: the permit screen showing its obligation's questions.** The change screen shows
its three, in full, with a citation box under each. The permit screen shows none of its own.

*Today.* The questions exist and the API serves them. A **disposition** is one named person's
signed answer to one obligation, and the route that offers its options answers `200` with three
of them for each demo obligation. The permit's three read:

> *Which isolation point was locked, and who verified it at zero?*
> *Which stored-energy source was surveyed and found absent within this permit's boundary, and by whom?*
> *Which task in this permit's scope was assessed as non-intrusive, and against which method statement?*

**The change screen calls that route and renders every word of it.** Three questions, a citation
box under each, and a note that there is no *not applicable* option, because the vocabulary does
not contain one. **The permit screen calls nothing of the sort**, so the same obligation is
answerable on one screen and silent on the other.

*Next.* Give the permit screen the panel the change screen already has. Until it does, the demo
film's permit beats say a person signs a reply and put no words in their mouth. A prompt spoken
over a frame that does not carry it is the kind of claim this project spends its credibility
refusing to make [src: docs/demo/film/CLAIMS-CLEARANCE.md D30].

### The gate itself

**Not there yet: a database-side check on the reason code.**

*Today.* One refusal in this demo is the application's, and we will not round it up. A signer
setting an obligation aside must give a reason code, and the database does not check that the
code was ever offered — Python closes that gap, not a constraint
[src: docs/submission/MUST-NOT-CLAIM.md §14].

*Next.* Move that check into the schema, so this refusal is the database's like the others.

**Not there yet: the drift path exercised by the suite.**

*Today.* Six gate properties were measured rather than assumed, and two came back weaker than we
hoped for. The case that would exercise the counter as a collision rather than an interleaving,
`CF-45`, is recorded `cannot_run`. And a harness that removes one mechanism at a time returned
nine of nine histories at refusal depth 1, meaning one mechanism refuses each. That file's own
verdict on a depth of one is *cut the mechanism, do not ship it*, and we have left the verdict
standing. Both results are in
[`docs/submission/GATE-PROPERTIES.md`](docs/submission/GATE-PROPERTIES.md).

*Next.* Build `CF-45`'s world so the drift path is exercised rather than argued. *After that:*
re-measure refusal depth with a second independent mechanism in place.

### The skills we authored, and the findings we owe upstream

**Not there yet: a recorded run of our Agent Skills.**

*Today.* Agent Skills is DESIGNED
[src: evidence/tool-usage/crdb-features.json#rows.crdb_agent_skills]. Nothing this repository
records has run them. Two authored skills and one staged upstream contribution are on disk, each
shipping a script that fails when its guarantee does not hold. No run of either is captured
under `evidence/`, and the row is not promoted to make the table look even.

*Next.* Run each skill end to end and commit the transcript, which is the same standard every
EXERCISED row on that table already met before it earned the word.

**Not there yet: the findings filed with Cockroach Labs.** This one is a contribution rather
than a shortcoming, and it is closer to done than anything else on this page.

*Today.* Seven things were measured on CockroachDB v26.2.5. One person who had written none of
them re-ran every one from a cold shell with the explicit job of striking things; six survived
and are published in
[`docs/upstream/COCKROACHDB-FINDINGS.md`](docs/upstream/COCKROACHDB-FINDINGS.md). The one that
did not survive, and six further claims narrowed inside the survivors, are in
[`docs/upstream/STRIKE-LEDGER.md`](docs/upstream/STRIKE-LEDGER.md). None of this has been
reported to Cockroach Labs yet; the one thing staged upstream is an unrelated skill contribution
[src: docs/upstream/proposal-issue.md].

*Next.* File the six with Cockroach Labs, and link each filing beside the finding it came from,
so a reader can follow one to the other in either direction.

### Smaller things, and what each one costs

* **`doctor.py` exits 1 on the machine every number here was measured on, and it is right to.**
  The only rows it fails are `uv` and `just`, neither of which is installed there
  [src: qa/judge-dry-run.json#host.tools_on_path]. It prints a numbered remedy under each and it
  does not block the proof. *Next:* nothing in the product. Install those two, or read the exit
  code and use the plain-python column, which is the column every number here came from.
* **Lint and types are counted, not clean.** There are 671 `ruff check` findings
  [src: qa/ruff-ratchet.json#lint.total] and 0 `mypy` errors [src: qa/mypy-ratchet.json#total_errors]
  over the 660 files mypy checks [src: qa/mypy-ratchet.json#source_files_checked]. These are
  frozen ratchets that may fall and may not rise, and the lint half is red today. *Next:* bring
  the lint number down. Re-freezing it upward is the one move a falling ratchet exists to forbid.
* **The test census describes a tree that no longer exists.** [`qa/test-state.json`](qa/test-state.json)
  was taken before the producer migrations landed, and it says so about itself. *Next:* retake
  it. It is cheap, and nobody has done it.
* **Every timing in the demo is a local timing** — one single-node CockroachDB in Docker, on one
  laptop. *Next:* a measurement under load against the managed cluster, once a lane points at
  it.

## The reds, and which ones mean something

The Actions tab is red in places, and the reds are not one kind. Read
[`docs/CI-STATE.md`](docs/CI-STATE.md) before drawing any conclusion from a colour.

The board recorded there on 2026-08-14, at public tip `7535670`, reads 20 workflows: 8 green and
12 red. Four of those reds are red on purpose and turning them green is forbidden — `schema`,
`db`, `custody-chain` and `demo-health`. Each refuses to certify something this repository has
not built, and each says so in the first clause of the message GitHub renders. Each also names
the artefact that would end it, and the shortcuts that would not: narrowing a matrix, skipping a
job, dropping a foreign key. Every one of those closes a lane by deleting its question.

The remaining reds are defects, and that page names the cause and the owner of each, read out of
its own log. That board is a reading at that tip on that date, not a statement about today's
tree. One rule on it governs everything else: a repair without a run identifier is a plan, and
that page counts plans as red.

**One more red belongs to neither kind, and it is this project's own writing gate.**
`scripts/submission/check_readme_readability.py` asks seven mechanical questions about whether a
stranger can read [`README.md`](README.md). Six are green. The seventh is a byte ceiling of
26,000, and that page is red against it at about 30,000. The ceiling is a number we set before
writing, and the page did not fit inside it without deleting claims that carry their evidence.
We left the ceiling where it was and the file over it, rather than move a number to make a red
go away or quietly drop a citation. The layer-1 budget, which is the one that governs the first
sixty seconds, is green. *Next:* shorten the page without dropping a claim or its citation.

## Where the full account lives

Nothing on this page replaces any of these. Where this page and one of them disagree, the other
one is right and this page is the error.

* [`docs/HONESTY.md`](docs/HONESTY.md) — what is proven, what is authored and what is not built,
  every number carrying the artefact that produced it.
* [`docs/submission/MUST-NOT-CLAIM.md`](docs/submission/MUST-NOT-CLAIM.md) — the flattering
  sentence this project is not entitled to say, printed beside the true one.
* [`VERIFY.md`](VERIFY.md) — three ways of checking us, ordered by how much you have to take on
  faith, each recording what it returns today rather than what it should return.
* [`docs/upstream/STRIKE-LEDGER.md`](docs/upstream/STRIKE-LEDGER.md) — one published finding
  struck and six claims narrowed, kept rather than deleted.
* [`docs/CI-STATE.md`](docs/CI-STATE.md) — the board, with the cause of every red read out of
  its own log.

We will keep this page moving as the work lands. Items come off it by being built, not by being
reworded.
