<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# RUNBOOK — D-day, in order, with the expected output of every command

**Deadline: 2026-08-18 17:00 EDT (`2026-08-18T21:00:00Z`).**

This is the founder's list. Every step is a literal command and the output it should
produce. Nothing on this page is automated by the build fleet: steps 1 to 3 in particular
are the founder's alone, because one of them is irreversible and two of them publish a
repository.

Run every command from the repository root, `D:/CoackroachDBxAWS/mainline`.

Two rules for the whole page:

* **Do not skip a verification.** Each step's verification is the precondition of the
  next one. The order exists because the failure modes overlap.
* **If a verification prints something other than what is written here, stop.** The
  runbook has no branch for "close enough".

---

## Before you start — read the board, change nothing

```bash
python scripts/submission/check_submission_ready.py
```

Read-only. It writes no file, starts no container and needs no credential. It prints a
table and, under it, a numbered remedy for every unresolved row. On 2026-08-10 it printed
five unresolved rows and exited **1**:

```
STATUS  CHECK                  OBSERVED
------  ---------------------  --------------------------------------------------------
PASS    root LICENSE           11357 bytes, reads as Apache-2.0
FAIL    remote is in sync      2 commits ahead of origin/master, 98 file(s) on this disk and on no server
FAIL    repository is public   visibility is PRIVATE [gh repo view --json visibility]
FAIL    demo URL               demo_url is UNRESOLVED
FAIL    video URL              video_url is UNRESOLVED
PASS    Devpost description    docs/submission/DEVPOST.md: 14637 bytes, 111 non-blank lines
PASS    tool usage documented  4 CockroachDB tools, 10 AWS services named
FAIL    judge access           3 unresolved: judge_access.required, judge_access.how, judge_access.credentials_location
PASS    provenance disclosure  docs/submission/DISCLOSURE.md present (20445 bytes); 16 commits, all inside the window
PASS    time remaining         8d 13h to 2026-08-18 17:00 EDT (2026-08-18T21:00:00Z)
```

Every step below turns exactly one of those rows green. The last step is running this
same command again and requiring exit **0**.

> The byte counts and the clock in that transcript move as the documents and the day do.
> The **statuses** are the part to read, and the program is always the authority — this
> page is a record of one run, not a substitute for running it.

### The same command, RAN 2026-08-14 — **four of those five rows are now green**

The 2026-08-10 transcript is kept above as the dated record it is. Here is today's, so a
founder opening this page knows which steps are already behind them:

```
PASS    root LICENSE           11357 bytes, reads as Apache-2.0
FAIL    remote is in sync      4 commits ahead of origin/master, 22 file(s) on this disk and on no server
PASS    repository is public   PUBLIC [gh repo view Shaugato/mainline --json visibility, asked live], repo_url https://github.com/Shaugato/mainline
FAIL    demo URL               demo_url is UNRESOLVED
FAIL    video URL              video_url is UNRESOLVED
PASS    Devpost description    docs/submission/DEVPOST.md: 53343 bytes, 219 non-blank lines
PASS    tool usage documented  4 CockroachDB tools, 10 AWS services; 2 AWS service(s) marked as having run (Amazon Bedrock, Amazon CloudWatch); 24 of 24 cited artefacts present on disk
PASS    judge access           resolved - credential required; how 463 chars, credentials_location 373 chars, and no credential value in the file
PASS    provenance disclosure  docs/submission/DISCLOSURE.md present (20445 bytes); 86 commits, all inside the window
PASS    time remaining         4d 11h to 2026-08-18 17:00 EDT (2026-08-18T21:00:00Z)

NOT READY - 3 unresolved rows.
```

**Steps 2, 3, 4 and 6 of this page are DONE.** The repository is public, the licence is
detected, `repo_url` is written and `judge_access` is resolved with no credential value in
the file. What remains is **step 1** (the push, red only because a documents wave is sitting
uncommitted on this disk), **step 5** (the demo URL, which needs an apply) and **step 7**
(the film).

**Do not read `NOT READY - 3` as worse than `NOT READY - 5`.** Two of the three are the
sentinels this project put there on purpose — `demo_url` and `video_url` are `UNRESOLVED`
because the facts they would assert are not true — and the third clears with a `git push`.

---

## Step 1 — push

```bash
git status --porcelain          # expect: no output, or commit what it lists first
git push origin master
```

**Expected output**, shape rather than literal — the hashes will be whatever they are:

```
Enumerating objects: ..., done.
...
To https://github.com/Shaugato/mainline.git
   <old>..<new>  master -> master
```

**Verify:**

```bash
git rev-list --left-right --count origin/master...HEAD
```

**Expected: `0` and `0`, tab-separated.** On 2026-08-10 this printed `0<TAB>2`.

### Why this is step 1 and not step 5

Two commits are on this disk and on no server. They carry **98 files**, and the list of
what is in them is the reason the order of this runbook is not negotiable:

| path | on `origin/master` before the push |
|---|---|
| `scripts/proof/gate_refusal.py` | no — **the proof this project is about** |
| `conftest.py` | no — without it `pytest` cannot collect |
| `LICENSES/` | no — the licence texts requirement 1 depends on |
| `docs/HONESTY.md` | no — the document the README links in its second section |
| `evidence/gate-refusal/proof-*.json` | no |

A judge who clones the repository as it stands on the server today gets a tree in which
the central artefact does not exist, `pytest` cannot run, and the README promises
commands that are not there. Publishing that tree is worse than publishing nothing,
because it is checkable and it fails.

The push is also a precondition of step 3 in the strict sense: `audit_public_readiness.py`
refuses while `HEAD` is ahead of the remote, and step 3 is gated on that audit.

---

## Step 2 — verify the licence, on the server and not only on this disk

```bash
ls -l LICENSE
python scripts/qa/check_reuse.py
```

**Expected:** `LICENSE` is present and non-empty — 11,357 bytes on 2026-08-10, reading as
Apache-2.0 — and `check_reuse.py` exits 0.

Then confirm GitHub itself can see it, which is what a judge's browser will do:

```bash
gh repo view Shaugato/mainline --json licenseInfo
```

**Expected after the push:** a non-null `licenseInfo`. On 2026-08-10, before the push,
this printed `{"licenseInfo":null}`.

> GitHub detects the licence from the root file. If `licenseInfo` is still null after a
> successful push, the file is present but not recognised — check that it is the
> unmodified licence text and not a wrapper around it.

---

## Step 3 — flip the repository to public · **IRREVERSIBLE** · **ALREADY DONE, 2026-08-11**

> **This step has been taken. It is kept in full because a runbook that deletes a completed
> irreversible step stops being a record of what was done.** `gh repo view Shaugato/mainline
> --json visibility` answers `{"visibility":"PUBLIC"}`, confirmed live by
> `check_submission_ready.py` on 2026-08-14. The act itself is recorded in
> [`PUBLIC-FLIP-CHECKLIST.md`](PUBLIC-FLIP-CHECKLIST.md); the disclosure consequences are the
> standing register in [`PUBLIC-READINESS.md`](PUBLIC-READINESS.md), which on 2026-08-14
> reports **160 undisposed findings** and exits 3.
>
> **The "sixteen commits" figure in 3b's warning below was true on 2026-08-10 and is now 86.**
> It is annotated rather than re-typed, because the warning it belongs to is about an act that
> has already happened: whatever number of commits was published, they are published.
> `git rev-list --count HEAD` = **86** on 2026-08-14, and every push since the flip has added
> to the public surface with no further decision point. **Read 3a before every push, not
> before every flip** — there is only ever one flip and it is behind you.

### 3a — the gate. Do not run 3b until this exits 0.

```bash
python scripts/submission/audit_public_readiness.py
echo $?
```

**Required: exit `0`.** On 2026-08-10 it exited **1** and ended:

```
BLOCKING PRECONDITIONS:
  - 2 commit(s) on HEAD are NOT on origin/master - flipping public would publish a tree that does not contain them

VERDICT: NOT READY - failing checks: secrets_history, absolute_paths, repo_state
```

`repo_state` is cleared by step 1. The other two are enumerated in
[`PUBLIC-READINESS.md`](PUBLIC-READINESS.md) with a disposition for each; read that
document before you accept them, because the audit lists findings it has deliberately
recorded rather than repaired, and accepting them is a decision, not a formality.

### 3b — the flip

```bash
gh repo edit Shaugato/mainline --visibility public --accept-visibility-change-consequences
```

**Expected:** no output, exit 0.

> **This step is irreversible in practice.** Turning the repository private again does not
> unpublish it: GitHub's fork network, the public event stream, archival mirrors and
> search-engine caches all outlive the revert. The flip publishes **all sixteen commits**,
> not only the tree at `HEAD` — a value masked at `HEAD` but present in an earlier commit
> is published anyway. That is the whole reason step 3a exists.

**Verify:**

```bash
gh repo view Shaugato/mainline --json visibility
```

**Expected: `{"visibility":"PUBLIC"}`.** On 2026-08-10 this printed
`{"visibility":"PRIVATE"}`.

---

## Step 4 — record the repository URL, and set the homepage

Write the URL into the one file that carries it:

```bash
# docs/submission/SUBMISSION.json
#   "repo_url": "https://github.com/Shaugato/mainline"
```

**Verify:**

```bash
python scripts/submission/check_submission_ready.py --json | grep -A2 '"repo_public"'
```

**Expected:** that row's `"status"` is `"PASS"`.

The homepage field is what a judge sees on the repository page, and it should point at
the demo rather than at the repository. Set it once the demo URL exists — step 5:

```bash
gh repo edit Shaugato/mainline --homepage "<the demo URL from step 5>"
gh repo view Shaugato/mainline --json homepageUrl
```

**Expected:** `homepageUrl` equals the demo URL. On 2026-08-10 it was `""`.

---

## Step 5 — the demo URL

The deployment is not this document's build; the binding is. When the demo is live,
write its URL into the single write point:

```bash
# docs/submission/SUBMISSION.json
#   "demo_url": "https://<the deployed console>"
```

**Verify — and verify by fetching, not by looking:**

```bash
python scripts/submission/check_submission_ready.py --check-urls
```

**Expected:** the `demo URL` row reads `PASS` with `-> GET 200` or `-> HEAD 200`. This is
the only mode of the gate that touches the network, and it exists because a URL that was
pasted with a trailing space looks perfect in a text editor.

> Do this from a machine, or at least a browser profile, that is not the one that
> deployed it. A demo that works only for the person holding the deployment credentials
> fails requirement 6, and it fails it silently.

---

## Step 6 — judge access

Answer all three members. `required` must be a real JSON boolean, not the string
`"false"` — the gate refuses the quoted form, because `"false"` is truthy in most
languages that will read this file.

```bash
# docs/submission/SUBMISSION.json
#   "judge_access": {
#     "required": false,
#     "how": "The demo is public and needs no sign-in.",
#     "credentials_location": "none - no credential is required"
#   }
```

If a credential *is* required, `credentials_location` says **where it lives** — never
what it is. This file becomes world-readable the moment step 3b runs, and the gate scans
every value in it for credential shapes and refuses the whole row if one appears.

**Verify:**

```bash
python scripts/submission/check_submission_ready.py --json | grep -A3 '"judge_access"'
```

**Expected:** `"status": "PASS"` and the observed string ending
`no credential value in the file`.

---

## Step 7 — the video

The script, the voice-over, the shot list, the seeded state and the sentences that may
not be said are in [`VIDEO-KIT.md`](VIDEO-KIT.md) and
`verticals/mainline/demo/script/`. The shot list is validated in CI, so the running time
is arithmetic rather than a hope.

1. Seed the state the shot list assumes, and confirm the refusal is live before recording.

   **`gate_refusal.py` takes no DSN from thin air.** With no `--dsn` and none of
   `MAINLINE_TEST_DSN` / `TRAPPOINT_DSN` / `COCKROACH_URL` / `CRDB_URL` / `LOCAL_DSN` in
   the environment it exits **2** and explains itself. `seed_demo_state.py` defaults to
   the local node; the proof does not. Pass it:

   ```bash
   docker ps --format "{{.Names}} {{.Image}} {{.Status}}"   # match the IMAGE, not the name
   python scripts/submission/seed_demo_state.py --database <your scratch database>
   python scripts/proof/gate_refusal.py \
     --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
   ```

   > **Corrected 2026-08-14: do not expect a container called `mainline-crdb`.** That name
   > does not exist on this machine any more. `docker ps` today lists one container,
   > `trappoint-crdb`, on the pinned image `cockroachdb/cockroach:v26.2.5`, and it answers on
   > `26257`. **The image tag is the thing to check; the name is not load-bearing** and
   > `python scripts/qa/doctor.py` confirms which socket actually answered. `VIDEO-KIT.md`
   > §B.1 carries the same correction.

   **Expected**, from the committed transcript of the most recent run —
   `evidence/gate-refusal/proof-20260814T032418Z.json`, read back on 2026-08-14 — the tail of
   the run, four beats and a verdict:

   ```
   cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
   database      w_qr_gate_refusal_proof
   chain         271/271 applied, 0 failed, 71.797s
   PROJECTION    10/10 held
   REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
   DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
   ADMISSION     ADMITTED [00000]
   caveats       (none)
   VERDICT       PROVEN
   evidence      evidence/gate-refusal/proof-<timestamp>.json
   ```

   Exit code **0**. Do not record until you have seen `VERDICT PROVEN` in this session —
   the `chain` and `caveats` lines move as the migration tree changes, and the film is
   about the beats, not about a number you remember. The chain figure was `57.196s` on
   2026-08-10 and `71.797s` on 2026-08-14 over the *same* 271 files; a slower machine is not
   a finding.

   **And check the receipt deadline before you roll.** `seed_demo_state.py` prints a
   `BEAT 4 SKIPS AFTER <instant>` block on every run. Past that instant the admission beat
   skips silently, the first three beats keep refusing, and nothing on the frame changes —
   `VIDEO-KIT.md` §B.4 calls it *"the quietest way this shoot fails"* and carries the
   one-line tripwire to run between takes.

2. Record, keeping under three minutes. The rules cap it at three; the submission cut is
   built with headroom for exactly this reason.

3. Upload to YouTube as **Unlisted** (not Private — a private video is invisible to a
   judge and the gate cannot tell the difference from the outside; `--check-urls` can).

4. Write the URL:

   ```bash
   # docs/submission/SUBMISSION.json
   #   "video_url": "https://youtu.be/<id>"
   ```

**Verify:**

```bash
python scripts/submission/check_submission_ready.py --check-urls
```

**Expected:** the `video URL` row reads `PASS`. The gate checks the host as well as the
status: a URL that is not on YouTube or Vimeo fails, because the rules name those two.

---

## Step 8 — regenerate the rules matrix

The status column in [`RULES-MATRIX.md`](RULES-MATRIX.md) is generated. Regenerate it so
the document a judge may read agrees with the program:

```bash
python scripts/submission/check_submission_ready.py --markdown
```

Paste the output over the table in §1 of that document. Do not edit a cell by hand.

---

## Step 9 — the final gate. It must exit 0.

```bash
python scripts/submission/check_submission_ready.py --check-urls
echo $?
```

**Required: exit `0`,** and the table ends:

```
READY - every blocking row is resolved.
```

If it exits 1, the remedy list under the table names the command for every row that is
still red. There is no flag that makes a red row green, and there is no version of this
step that ends with "it is probably fine".

Run the prose check too, because the Devpost paste is prose and prose is where the
overclaims live:

```bash
python scripts/submission/check_submission_prose.py
```

---

## Step 10 — paste into Devpost, field by field

[`DEVPOST.md`](DEVPOST.md) is written in Devpost's field order so this step is a paste
and not a writing session. Work down the table:

| # | Devpost field | source |
|---|---|---|
| 1 | *Elevator pitch* | `DEVPOST.md` § Elevator pitch |
| 2 | *Inspiration* | § Inspiration |
| 3 | *What it does* | § What it does |
| 4 | *How we built it* | § How we built it |
| 5 | *Challenges we ran into* | § Challenges we ran into |
| 6 | *Accomplishments that we're proud of* | § Accomplishments |
| 7 | *What we learned* | § What we learned |
| 8 | *What's next for MAINLINE* | § What's next, **then** § Limitations, in that order |
| 9 | *Built With* | § Built With |
| 10 | *Try it out* — repository link | `SUBMISSION.json` → `repo_url` |
| 11 | *Try it out* — demo link | `SUBMISSION.json` → `demo_url` |
| 12 | Video demo link | `SUBMISSION.json` → `video_url` |

**Paste every URL from `SUBMISSION.json`, never from memory and never from a browser tab.**
The three URL fields are the ones the gate has verified; a tab is not evidence.

Two fields the rules ask for that are easy to miss:

* **Which CockroachDB and AWS services, and how** — link `docs/TOOL-USAGE.md`. Naming the
  services is not enough; the rules ask how each one is used, and that document answers
  it service by service.
* **Pre-existing code disclosure** — link `docs/submission/DISCLOSURE.md`.

---

## Step 11 — after submitting, be the judge for five minutes

```bash
git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git m
cd m
python scripts/qa/doctor.py
```

Clone into a **short** path. Windows `MAX_PATH` is 260 characters and this repository
contains tracked paths over 200 characters long, so a deep destination fails checkout
with `Filename too long` and leaves a half-populated tree. `-c core.longpaths=true` costs
one flag and is a no-op off Windows. The measured threshold and the reproduction are in
[`FIRST-FIVE-MINUTES.md`](FIRST-FIVE-MINUTES.md).

Then open, in this order, the three things a judge opens: the repository front page, the
demo URL, and the video. If any of the three does not answer, you have until 17:00 EDT.

---

## What this fleet did not do, and why

Steps 1, 3b and 7 are the founder's, and no program in this repository performs them.

* **The push** publishes work. That is a decision, not a build step.
* **The visibility flip** cannot be undone. A tool that could run it unattended would be
  a tool that could publish a repository by accident.
* **The video** requires a person, a microphone and a judgement about what to show. The
  kit removes everything else.

Everything else on this page is a command whose output is checked by a program that
refuses.
