<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
This file quotes every forbidden sentence verbatim, beside the true one. It therefore
carries the `prose-hygiene: register` marker above, and
`scripts/submission/check_submission_prose.py` does not scan it — and PRINTS that it did
not, on every run, so "not scanned" is never mistaken for "passed". The marker is visible
in the diff, which is the whole reason it is a comment in the file rather than a path in
the scanner.
-->

# MUST NOT CLAIM — the sentences, and what to say instead

This page exists because the founder is going to be on camera, in a Devpost form, and in
front of judges, saying sentences out loud, and roughly nine of them are *plausible*,
*flattering* and *false*. Every one of those nine has a true version that is very nearly as
good — often better, because a project that volunteers its own limits is the only kind a
safety engineer believes.

**How to use this page.** Read the left column once. If a sentence like it is about to leave
your mouth, say the right column instead. Do not paraphrase the right column into something
stronger; the wording is chosen to be defensible under a question.

**How it is enforced.** `scripts/submission/check_submission_prose.py` invokes
`scripts/demo/claim_hygiene.py` for the architecture-level must-not-claim table and then adds
the nine submission-specific families below, scanning `README.md`, `docs/submission/*.md` and
`docs/TOOL-USAGE.md`. It has a `--self-test` that plants one violation per family and requires
the scanner to fire on each, because a check that has never been red asserts nothing.

The prose checker cannot hear you. It reads files. **The video and the Devpost answers are
where this page has to be obeyed by a human**, which is why it is written as sentences rather
than as regexes.

---

## The register

### 1 · Data residency

| | |
|---|---|
| **MUST NOT SAY** | "Everything runs in Australia." · "Australian data residency." · "Your safety records never leave the country." |
| **TRUE INSTEAD** | "Inference runs in Sydney, `ap-southeast-2`. The database is in Singapore, `aws-ap-southeast-1`, because `ap-southeast-2` is Advanced-tier only on CockroachDB Cloud. There is no end-to-end Australian residency and we say so on the honesty card." |
| **WHY** | `docs/adr/0002-g1-platform-ground-truth.md` F5; `docs/HONESTY.md` § GEOGRAPHY AND LATENCY. The split is a *tier* constraint, not an oversight, and naming it is a stronger answer than hiding it — it shows you read the region list. |
| **CAUGHT BY** | `claim_hygiene.py` MNC-02; `check_submission_prose.py` SUB-01 |

`verticals/mainline/demo/script/CAMERA-STRINGS.yaml` already lists "end-to-end Australian data
residency" under `forbidden_on_camera`. Shot `s23`'s voice-over is the compliant sentence:
database in Singapore, inference in Sydney.

### 2 · Timings

| | |
|---|---|
| **MUST NOT SAY** | "It refuses in milliseconds in production." · "Sub-second gate latency." · Any number from the demo presented as a product characteristic. |
| **TRUE INSTEAD** | "Every timing you see is a single-node CockroachDB in Docker on this laptop. The managed cluster is in another region and this repository contains no p50, no p99 and no load profile for that hop." |
| **WHY** | `docs/HONESTY.md` § "Every timing in the demo is a LOCAL timing". The local/Cloud gap is measured and large, and the Cloud figure recorded there is a **floor** (`>`), transcribed rather than re-measured. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-02 |

If a judge asks "how fast is it", the correct answer is the honest one plus the reason: the
recall path crosses a region boundary on every embedding call, and nobody has measured it
under load. Anyone who quotes you a production latency for this system is guessing.

### 3 · The corpus, the incident, the site, the fatality

| | |
|---|---|
| **MUST NOT SAY** | "This is a real incident." · "A real operator's procedures." · "Two contractors were burned at this site." (spoken as fact) · "Kestrel Resources" spoken as a customer. |
| **TRUE INSTEAD** | "Every clause, procedure, incident, permit, operator and site in this demo was written for this repository. Kestrel Resources is fictional, Marrindal is fictional, `INC-2013-044` never happened. The mechanism is real; the inputs are authored." |
| **WHY** | `docs/HONESTY.md` § SYNTHETIC. The film carries the watermark `SYNTHETIC CORPUS · KESTREL RESOURCES IS FICTIONAL` for exactly this reason (`SHOT-LIST.yaml: watermark`), and `CAMERA-STRINGS.yaml` forbids a real person, a real incident or a real operator on camera. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-03 |

The narration in `VO.md` is written in the present tense of a story and that is fine — a
narrative frame is not a claim of fact when the watermark is burned into the frame and the
honesty card names the column. What is *not* fine is answering "did that happen?" with
anything other than "no, it is authored".

### 4 · Model behaviour

| | |
|---|---|
| **MUST NOT SAY** | "The agent tests prove the model behaves this way." · "We tested this against Claude and it works." |
| **TRUE INSTEAD** | "Agent tests replay recorded request/response cassettes. A green test proves our code handles that recorded exchange; it proves nothing about a live model's behaviour today. Where a live call is genuinely required, the test skips and the skip reason is in the census." |
| **WHY** | `docs/HONESTY.md` § SYNTHETIC, second bullet. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-04 |

### 5 · The conformance suite

| | |
|---|---|
| **MUST NOT SAY** | "The conformance suite passes." · "N conformance cases pass." · "We are conformance-tested." |
| **TRUE INSTEAD** | "The conformance suite has never been demonstrated. Against a bare node the cases *error* rather than skip, because `cases/_world.py` refuses to call an unbuilt world a refusal. The case bodies exist and the manifest enumerates them, but until a census runs against a migrated cluster that list is a plan, not a result." |
| **WHY** | `docs/HONESTY.md` § "The conformance suite has not been demonstrated" — the document calls this "the single largest gap between what this repository contains and what it has shown". |
| **CAUGHT BY** | `check_submission_prose.py` SUB-05 |

Two conformance cases *are* demonstrated, and they are demonstrated by a different program:
`scripts/proof/gate_refusal.py` captures CF-01 and CF-03 directly. Say that. It is a smaller
claim and it is true.

### 6 · The migration chain

| | |
|---|---|
| **MUST NOT SAY** | "The whole schema applies cleanly." · "All the migrations pass." · **Any migration count quoted from memory, including 246 of 261.** |
| **TRUE INSTEAD** | "Re-derive it, don't quote it. The committed evidence file records the count for the tree it ran against; run `scripts/proof/gate_refusal.py` or `scripts/submission/seed_demo_state.py` and read the number that run produced." |
| **WHY** | The number moves. `evidence/gate-refusal/proof-20260810T004200Z.json` records `chain.files = 261`, `applied_count = 246`, `failed_count = 15`, every failure attributed to one of five tables with no producer migration. On this working tree at `2026-08-10T05:12Z`, `scripts/submission/seed_demo_state.py` measured **271 of 271 applied, 0 failed, 0 unexplained** — five producer migrations (`0049d`, `0089`, `0089b`, `0090`, `0099`) have since appeared on disk and are, at the time of writing, still untracked by git. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-06 |

This is the clearest illustration on the page of why the rule is *re-derive, never quote*. A
document that hard-coded "246 of 261" on 2026-08-09 was already wrong by 2026-08-10, and it
was wrong in the direction that makes the project look *worse* than it is — which is the only
direction of error this repository can afford, but it is still an error.

The same rule governs the counter caveat that rides with it. `seed_demo_state.py` prints the
question — *who wrote `mainline.permit.open_blocking`?* — on every run and answers it from the
catalogue, because the answer changed when `0099_outbox.sql` landed. **Do not say "the
projection trigger closed the counter" unless the script you just ran said the trigger is
installed.**

### 7 · The reference-ledger keys

| | |
|---|---|
| **MUST NOT SAY** | "We committed keys by mistake." · Nothing at all — silence here reads as a leak the moment a judge greps the tree. |
| **TRUE INSTEAD** | "Every file under `evidence/reference-ledger/keys/` is a private key committed on purpose and named `NOT-SECRET` in its own filename, so a stranger can verify the offline custody bundle without asking anyone for a credential. They are worthless and must never be reused for anything that matters." |
| **WHY** | `docs/HONESTY.md` § SYNTHETIC, third bullet. Five key files, each with a `.license` sidecar, each carrying `NOT-SECRET` in the name. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-07 |

### 8 · The custody bundle

| | |
|---|---|
| **MUST NOT SAY** | "The custody bundle verifies." · "Cryptographically verified ledger." · "All checks pass." |
| **TRUE INSTEAD** | "`trappoint-verify` exits 2, and 2 is the honest code: nine of sixteen checks ran and every one of them held, and seven did not run at all. The seven are the cryptographic half — log signature, RFC-3161 bracket, beacon, witness quorum, S3 object-lock, gate self-attestation, WebAuthn re-verification. What is verified is the Merkle structure, not the signatures over it." |
| **WHY** | `qa/test-state.json#external_checks.custody_bundle_verification` — `passed 9, failed 0, not_checked 7, total 16, exit_code 2`. Read back today. `docs/HONESTY.md` says in terms: *do not read the nine passes as a verified ledger.* |
| **CAUGHT BY** | `check_submission_prose.py` SUB-08 |

### 9 · CockroachDB Cloud

| | |
|---|---|
| **MUST NOT SAY** | "It runs on CockroachDB Cloud in CI." · "Tested against the managed cluster." · "The nightly truth check runs against Cloud." |
| **TRUE INSTEAD** | "Nothing has ever run against CockroachDB Cloud in CI. The nightly truth check is designed, not scheduled. The cluster exists — `mainline-dev`, Basic tier, `aws-ap-southeast-1` — and there is a captured `ccloud` transcript against it under `evidence/ccloud/`, but no automated lane has ever pointed at it." |
| **WHY** | `docs/HONESTY.md` § "Other things this document will not pretend about", first bullet. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-09 |

---

## Three more that are already enforced elsewhere, repeated because they are said out loud

These live in `ARCHITECTURE.md` §11.7 and are checked by `scripts/demo/claim_hygiene.py`,
which `check_submission_prose.py` invokes rather than reimplements. They appear here because
the failure mode for all three is *speech*, not a file.

**Row-level security against a rogue admin.** RLS is evaluated by the same server a cluster
admin owns. Say: "RLS is tenancy and least privilege — it stops a confused query, not the
administrator. Against the administrator the claim is tamper-*evidence*: shot `s12` films an
admin dropping the constraint successfully, and then films the attested leaf that records it."
(`claim_hygiene.py` MNC-01; `REFUSAL-STRINGS.yaml` R3 `must_not_claim` says the same thing in
the file the camera reads from.)

**Rubber-stamping.** Nothing in this data model distinguishes a considered disposition from a
rubber stamp. Say: "we make the question unavoidable and the record precise; we measure
deliberation and we never accuse." That is shot `s24`, and it is in the film on purpose.
(`claim_hygiene.py` MNC-06.)

**ANN replay.** An approximate-nearest-neighbour result is not bit-identically replayable. Say
"replayable arithmetic and a disclosed boundary". (`claim_hygiene.py` MNC-10; and
`REFUSAL-STRINGS.yaml explain_fragment.must_not_claim`.)

---

## What to say when you do not know

The strongest sentence available to this project, and the one that costs nothing:

> "I don't know, and here is the file that would tell us."

`docs/HONESTY.md` is 349 lines of exactly that, every number carrying the artefact that
produced it, and a test that fails the build when a number and its source disagree. Link it.
It is the best thing in the repository.
