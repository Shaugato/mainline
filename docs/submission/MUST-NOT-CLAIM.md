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
front of judges, saying sentences out loud, and roughly a dozen of them are *plausible*,
*flattering* and *false*. Every one of them has a true version that is very nearly as
good — often better, because a project that volunteers its own limits is the only kind a
safety engineer believes.

**How to use this page.** Read the left column once. If a sentence like it is about to leave
your mouth, say the right column instead. Do not paraphrase the right column into something
stronger; the wording is chosen to be defensible under a question.

**How it is enforced, and where it is not.** `scripts/submission/check_submission_prose.py`
invokes `scripts/demo/claim_hygiene.py` for the architecture-level must-not-claim table and
then adds nine submission-specific rules — `SUB-01` to `SUB-09` — scanning `README.md`,
`docs/submission/*.md` and `docs/TOOL-USAGE.md`. It has a `--self-test` that plants one
violation per family and requires the scanner to fire on each, because a check that has never
been red asserts nothing.

**The register is fourteen families and the scanner is nine rules, so the arithmetic does not
close, and the gap is written down rather than hidden.** Families 1 to 9 each carry a
`CAUGHT BY` line naming its rule. Family 10 is caught by `SUB-05`, which already fires on the
word *demonstrated*. **Families 11, 12, 13 and 14 have no rule at all** — one is a number that
lives in a workflow comment, one is a verdict inside a JSON artefact, and two are digests and
absent foreign keys inside a database, and none of them is a sentence a line-scanner can
recognise. Their `CAUGHT BY` line says so in those words. A family listed here without a rule
is a family a human is the only control for, and pretending otherwise would be the same class
of error this page exists to prevent.

**Two families were added on 2026-08-14 and neither replaces anything.** Families 13 and 14
exist because the *signature path started working* during the completion wave, and a working
mechanism creates flattering sentences that a broken one never could. Nothing on this page was
softened to make room for them; §12 in particular got **stricter**, not looser, on the day its
artefact turned green.

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
| **WHY** | The number moves. `evidence/gate-refusal/proof-20260810T004200Z.json` records `chain.files = 261`, `applied_count = 246`, `failed_count = 15`, every failure attributed to one of five tables with no producer migration. On this working tree at `2026-08-10T05:12Z`, `scripts/submission/seed_demo_state.py` measured **271 of 271 applied, 0 failed, 0 unexplained** — five producer migrations (`0049d`, `0089`, `0089b`, `0090`, `0099`) had by then appeared on disk. **Re-checked 2026-08-12: all five are now tracked** — `git ls-files verticals/mainline/db/migrations/` lists each one — so the sentence "untracked at the time of writing", which this row carried until today, is itself an example of the rule. |
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
| **TRUE INSTEAD** | "Nothing has ever run against CockroachDB Cloud in CI. The nightly truth check is designed, not scheduled. The cluster exists — `mainline-dev`, Basic tier, `aws-ap-southeast-1` — and there are captured transcripts against it under `evidence/ccloud/` and `evidence/deploy/`, but no automated lane has ever pointed at it." |
| **WHY** | `docs/HONESTY.md` § "Other things this document will not pretend about", first bullet. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-09 |

**Re-checked 2026-08-14, and the by-hand column grew while the CI column did not.** There are now several Cloud artefacts — `evidence/deploy/cloud-chain.json` (`APPLIED`), `cloud-seed.json` (`SEEDED AND REFUSABLE`), and, untracked at the time of writing, `cloud-acceptance.json` and `cloud-contention.json`. **Every one of them was driven by hand.** The prohibition is unchanged and is if anything easier to trip now: "we run against Cloud" is a sentence a reader will hear as *in CI*, and the correct sentence is "we have driven Cloud by hand and committed the transcripts; no lane points at it."

### 10 · "Demonstrated" is not a weaker word than "passes"

| | |
|---|---|
| **MUST NOT SAY** | "The conformance suite has been demonstrated." · "We demonstrated conformance end to end." · "There is a captured conformance run." |
| **TRUE INSTEAD** | "The conformance suite has never been demonstrated. Two cases — CF-01 and CF-03 — are captured instead by `scripts/proof/gate_refusal.py`, which is a smaller claim and a true one." |
| **WHY** | This is family 5 said with a different verb, and the different verb is the one that slips out, because it *sounds* like a hedge. It is not a hedge: "demonstrated" is the exact word `docs/HONESTY.md` uses for the thing that has not happened. A judge who hears "demonstrated" will look for the transcript, and there is not one. |
| **CAUGHT BY** | `check_submission_prose.py` SUB-05 — its pattern lists `demonstrated` beside `pass`, `green` and `verified`. It fires on a *file*. In the film it is on you. |

### 11 · The MI ratchet number, which has moved and will move again

| | |
|---|---|
| **MUST NOT SAY** | "28 of 30." · "Twenty-eight invariants are pending." · "Two of thirty are enforced." · Any ratchet figure recalled rather than run. |
| **TRUE INSTEAD** | "Run the ratchet and read its last line." |
| **MEASURED** | `.venv/Scripts/python.exe scripts/mi_ratchet.py report` printed `21 pending / 9 enforced` on **2026-08-12**, and printed the same two numbers again when it was re-run on **2026-08-14**. The ratchet stays red at that figure on purpose; it is the top-level incompleteness counter and it is what stops the number being overstated. Two runs agreeing is not a licence to quote it from memory on the third day — it is one more reason the command is four seconds long. |
| **WHY IT IS EASY TO GET WRONG** | `28 of 30` was true when it was written and nine invariants have been promoted since. The string survives in superseded planning documents under `docs/leads/`, and `.github/workflows/ci.yml:690` quotes it *in order to correct it* — so a reader who greps the tree finds the stale figure and its correction on adjacent lines, and can take away either one. |
| **CAUGHT BY** | **Nothing.** No rule in `check_submission_prose.py` or `claim_hygiene.py` reads a ratchet count. The command above is the only control, and it takes four seconds. |

### 12 · The acceptance run — which turned `PROVEN` on 2026-08-14, and got **harder** to talk about, not easier

| | |
|---|---|
| **MUST NOT SAY** | "The acceptance run passes" *(unqualified)*. · **"The deployed demo is proven."** · **"The demo is live."** · "Every beat answers 200 over HTTP **from the internet**." · "We proved it against CockroachDB Cloud over HTTP." |
| **TRUE INSTEAD** | "Two acceptance artefacts read `PROVEN` and **both were taken over a local socket**. `evidence/deploy/acceptance.json` ran the real handler against a **local** database; `evidence/deploy/cloud-acceptance.json` ran the same real handler against the **CockroachDB Cloud** database `mainline_demo`. In both, the HTTP hop is `scripts/deploy/local_furl.py`, an emulator of a Lambda Function URL, and both files set `target_is_local_emulator: true`. **No public demo origin exists**, and `SUBMISSION.json` holds `demo_url: UNRESOLVED` because of it." |
| **MEASURED, 2026-08-14** | `evidence/deploy/acceptance.json` — `verdict PROVEN`, `generated_at 2026-08-14T08:16:49Z`, `url http://127.0.0.1:8792`, `target_is_local_emulator true`, `target_provenance.database_under_test = {host: localhost:26257, reported_by_health: w_w3, is_cockroachdb_cloud: false}`, `failures []`. Both runs' four beats read `00000 → 23514 gate_closed_when_issued → P0001 mainline.fn_permit_merge_gate → 00000`. |
| **THE TRAP INSIDE THE GREEN FILE** | That artefact's own `mode_description` field reads *"the live stack: console, /v1/health, and two /v1/demo/gate-run calls against CockroachDB Cloud"* — and for **this** run that description is **false**: `database_under_test.host` is `localhost:26257`. A founder who greps for a quotable sentence will find `mode_description` before `target_provenance`. **Quote `target_provenance`, never `mode_description`.** The `advisories` block says the same thing in the file's own words. |
| **WHY THE PROHIBITION SURVIVED THE GREEN** | Until 2026-08-13 this row existed because the file said `NOT PROVEN` and somebody might say otherwise. It now exists for the opposite reason and it is a worse trap: the word `PROVEN` is sitting in the file, and the sentence it does **not** license — *the deployed demo works* — is the exact sentence a submission wants to say. A verdict is proof of what it measured; here that is a handler, a console bundle, a socket and a database. It is not proof of an origin. |
| **AND THE OLD READING IS STILL THE RULE** | The gate-run has four beats and the fourth one *skips silently* when the exposure receipt behind it has expired — the first three keep refusing, so the screen looks correct and the verdict does not. Read the file **on the day you say it**, both files, and read `verdict`, `generated_at` and `target_provenance` together. |
| **CAUGHT BY** | **Nothing.** No rule reads a JSON verdict. Read the file. |

**One artefact in that pair is not committed yet.** On 2026-08-14 `git status --porcelain evidence/deploy/` listed `evidence/deploy/cloud-acceptance.json` as `??` — untracked. Do not cite a file a judge cannot clone. Until it is committed, the Cloud reading above is a working-tree measurement and this row says so rather than rounding it up.

### 13 · The defeater vocabulary digest, which pinned a constant until 2026-08-14

| | |
|---|---|
| **MUST NOT SAY** | "Every signature in this project pins the alternatives the signer declined." · "The Cloud demo's signed disposition records which vocabulary was offered." · Any past-tense claim that the vocabulary digest has always meant what the schema says it means. |
| **TRUE INSTEAD** | "A disposition's `defeater_vocab_sha256` is *designed* to digest the whole option set, so a signature pins the alternatives as well as the choice — and until 2026-08-14 both signing paths in the demo API bound `sha256(b'defeater-vocab')` instead, which digests an ASCII string and pins nothing. It is fixed: `mainline_demo_api.defeaters.resolve_defeater_vocabulary` now READS the digest out of `mainline.defeater_option` and **raises** when the table is empty rather than falling back. The captured Cloud bundle still carries the old value, and that is disclosed rather than re-recorded." |
| **MEASURED, 2026-08-14** | `sha256(b"defeater-vocab")` is `7ad8d49c2edd93f0a8fd3cd6b2a5d6cd225810805527a1a3f2f497aec819db3f`. Base64-decode `response.body_b64` in `verticals/mainline/apps/console/fixtures/bundles/demo-cloud/frames/GET-f116fc2724f1b968.json` and `signed.defeater_vocab_sha256` is that exact string. Meanwhile `mainline.defeater_option` on a freshly seeded state holds **3** rows for the obligation, all sharing **one** `vocab_sha256` — which is what the digest is supposed to be. |
| **WHY** | This is `mainline_demo_api.credentials` one column across, and the module says so: *"the database owns the value, the application RESOLVES it, nothing is recomputed and nothing is defaulted."* A digest the application computes agrees with whatever fixture shares the expression and with no deployed seed. |
| **CAUGHT BY** | **Nothing.** No rule decodes a base64 body inside a replay fixture. The command above is the only control. |

### 14 · Where the defeater refusal actually lives — the application, not the database

| | |
|---|---|
| **MUST NOT SAY** | "The database refuses a defeater code that was never offered." · "A foreign key stops a signer citing an option they were not shown." · "Every refusal in this demo is the database's." |
| **TRUE INSTEAD** | "`mainline.disposition` has **no foreign key onto `mainline.defeater_option`**. `0066_disposition.sql` carries `defeater_code STRING NOT NULL` and only `CONSTRAINT disposition_defeater_code_stated CHECK (defeater_code <> '')`, so the database will accept a code that was never offered. That gap is closed **in the application**, by `resolve_defeater_vocabulary` raising, and it is written down rather than papered over." |
| **MEASURED, 2026-08-14** | `grep -n defeater verticals/mainline/db/migrations/0066_disposition.sql` returns four lines: `:108 defeater_code STRING NOT NULL`, `:109 defeater_vocab_sha256 BYTES NOT NULL`, `:211` the non-empty CHECK, `:216` the 32-byte length CHECK. **No `REFERENCES mainline.defeater_option` anywhere.** |
| **WHY IT MATTERS MORE HERE THAN ANYWHERE ELSE** | The whole film is the sentence *"not by a warning — by a CHECK constraint"*, and beats 2 and 3 earn it. This one specific refusal is a different species, and a founder who has spent three minutes saying "the database refuses" will say it once too often. The honest version costs nothing: **`0064` and `0066` are the two migrations the claim rests on, and the second one deliberately does not add the constraint** — `defeaters.py` records why (a new constraint moves `migrations.lock.json`, the schema fingerprint and the dev/demo/prod parity gate four days from a deadline). |
| **CAUGHT BY** | **Nothing.** No rule reads a migration for an absent foreign key. |

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

`docs/HONESTY.md` is that sentence at length — every number carrying the artefact that produced
it, and a test that fails the build when a number and its source disagree. Link it. It is the
best thing in the repository.

Its length is itself a number, so it is re-derived rather than remembered: `wc -l
docs/HONESTY.md` printed **349** at one revision, **780** on 2026-08-12, and **1006** when it
was measured again on **2026-08-14**. Each figure was true when someone typed it and false
within days. Three readings of one command, kept side by side, are the smallest possible
demonstration of why every count on this page names the command that produced it — and of why
the rule is *re-derive*, not *update the number and move on*.

---

## The four families that changed on 2026-08-14, in one place

Because a register that grows quietly is a register nobody re-reads:

| family | what moved | direction |
|---|---|---|
| 11 · MI ratchet | re-run; still `21 pending / 9 enforced` | unchanged, re-measured |
| 12 · acceptance run | artefact turned `PROVEN`; **prohibition tightened** and two new forbidden sentences added | **stricter** |
| 13 · defeater vocabulary digest | **new** — the digest pinned a constant until this wave | new |
| 14 · defeater FK | **new** — the refusal is the application's, not the database's | new |

Nothing was removed, softened or merged. The one row whose evidence improved is the one row
that gained sentences it may not say.
