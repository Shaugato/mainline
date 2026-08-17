<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE MECHANICAL SWEEP — the requirements nobody checks until it is too late

## What a mechanical sweep is, and why a true submission can still lose on one

A contest entry has two completely different ways to fail.

The first is the one everybody worries about: you claimed something that is not true. Somebody
checks, it does not hold, and you deserve to lose.

The second has nothing to do with truth. Every claim holds, every number is real, every command
runs — and the entry still fails, because a video was uploaded with the wrong privacy setting, or
a link in the README points at a file that was renamed last week, or the demo server that answered
all week goes quiet in the middle of the judging period. **Nobody lied. The submission still
loses.** These are mechanical failures: small, boring, entirely preventable, and invisible from
the inside, because the person who made the mistake is the one person who cannot see it. An
uploaded video looks fine to the account that uploaded it whatever its privacy setting. A broken
link looks exactly like a working one until it is clicked.

**A mechanical sweep is somebody going through those failures one at a time and measuring each,
rather than assuming.** This page is that sweep. Six checks, each with the literal command, the
literal result, and — where a check found something wrong — the exact text that fixes it.

**Three ground rules govern every line below.**

1. **A check that was not run is written `NOTRUN`, and `NOTRUN` is never a pass.** A question
   nobody asked is an open question, not a good answer.
2. **This page measures; it does not repair other people's files.** Where the fix belongs in a
   document this sweep does not own, the exact replacement text is printed here and handed to the
   person who owns that file. Nothing is edited behind an owner's back.
3. **Nothing here was deployed, re-deployed, or written to a cloud account.** The only network
   traffic this sweep produced was ordinary read requests that anybody on the internet can make,
   with no password or key of ours attached.

**About the dates.** Every measurement below was taken by this sweep, none copied from another
document. The machine's clock runs ten hours ahead of UTC, so it reads `2026-08-18` locally while
UTC reads `2026-08-17`. **Every timestamp on this page is the UTC one** that the server or the
tool printed for itself — `python -c "import datetime; print(datetime.datetime.now(datetime.timezone.utc))"`
answered `2026-08-17T17:29:45+00:00` while the same machine's local clock read
`2026-08-18T03:29:45`.

---

## The scoreboard

| # | check | verdict |
|---|---|---|
| 1 | the licence is detectable by GitHub and shows in the repository's About panel | **PASS** |
| 2 | the video upload instruction says Unlisted, forbids Private, and demands a logged-out test | **PASS in the kit · GAP in three other places — replacement text below** |
| 3 | every link on the judge-facing pages resolves to a file that exists | **PASS — 140 links, 0 broken; now a standing check, with a self-test** |
| 4 | the demo URL answers from outside, with no credential | **PASS — and the obligation runs four weeks past the deadline** |
| 5 | every evidence file cited on the judge-facing pages exists on disk | **PASS — 226 citations, 0 broken, 1 absence declared on purpose** |
| 6 | the expected `STALE`, and one question only the founder can answer | **RECORDED — no defect** |

**Five questions are `NOTRUN` and are named as such rather than left to look like passes** — §7.
**Five defects were found in files this sweep does not own, with the exact fix for each** — §8.
One of them, `D4`, is a build lane that is red right now and needs an owner before the tree is
pushed.

---

## 1 · THE LICENCE — and the clause most entrants miss

**The rule.** The contest requires a public repository carrying an open-source licence. There is
a second half that is easy to skip: the licence must be *detectable and visible at the top of the
repository page (in the About section)*. GitHub renders a licence name in the **About** panel on
the right of a repository's front page — but only when its own licence detector recognises the
`LICENSE` file. A repository can hold a perfectly valid Apache-2.0 file and still show nothing in
that panel, and then a judge checking the requirement sees a blank where the licence should be.

**Why there was a real reason to doubt it here.** This repository does not use one licence. It
uses three, mapped file-by-file through a `REUSE.toml` file and a `LICENSES/` directory
(`Apache-2.0.txt`, `CC-BY-4.0.txt`, `FSL-1.1-ALv2.txt`, `LicenseRef-FSL-1.1-ALv2.txt`). A
detector meeting a tree like that can reasonably come back undecided. `compliance-plan.md`
Ruling 7 recorded the detector answering `Apache-2.0` on `2026-08-16`; this sweep re-asked today
rather than trusting that.

**Command, and the answer it gave:**

```
$ gh repo view Shaugato/mainline --json visibility,licenseInfo
{"licenseInfo":{"key":"apache-2.0","name":"Apache License 2.0","nickname":""},"visibility":"PUBLIC"}

$ gh api repos/Shaugato/mainline --jq '{visibility:.visibility, private:.private, spdx:.license.spdx_id, default_branch:.default_branch}'
{"default_branch":"master","private":false,"spdx":"Apache-2.0","visibility":"public"}
```

**And one measurement neither of those makes, because both go through an authenticated tool.**
`gh` sends this account's credential. A judge sends nothing. So the public page was also fetched
the way a stranger fetches it — plain `curl`, no key, no header, no account:

```
$ curl -sSL -w "%{http_code}\n" https://github.com/Shaugato/mainline -o page.html
200
```

The page that came back is 436,567 bytes and carries GitHub's own rendering payload for the About
panel, verbatim:

```
"visibilityLabel":"Public","license":{"spdxId":"Apache-2.0","name":"Apache License 2.0"}
```

**That is the field the About panel draws.** It is present, it is `Apache-2.0`, and it came back
to a request carrying no credential of ours.

**The file itself, unchanged and untouched by this sweep:**

```
$ git ls-files -s LICENSE
100644 261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64 0	LICENSE
$ wc -c LICENSE
11357 LICENSE
```

Tracked, `11 357` bytes, opening `Apache License / Version 2.0, January 2004`. The submission gate
agrees from its own side: `PASS  root LICENSE  11357 bytes, reads as Apache-2.0`
(`python scripts/submission/check_submission_ready.py`, run today).

> **VERDICT — PASS.** Public, Apache-2.0, detected, and visible in the About panel to an
> anonymous visitor. The three-licence tree did not confuse the detector. **No licence file was
> changed by this sweep**, which was the instruction.

---

## 2 · THE VIDEO PRIVACY SETTING — the single most expensive one-click mistake available

**The rule, verbatim from the Official Rules**, as transcribed in `compliance-plan.md` §1.3: the
video *"must be uploaded to and made publicly visible on YouTube or Vimeo and a link to the video
must be provided on the submission form"*.

**"Publicly visible" is not the same as the setting called Public**, and this is where entries
die. YouTube offers three settings. **Public** is listed and searchable. **Unlisted** means anyone
holding the link can watch with no sign-in — that satisfies the rule and is the normal hackathon
choice. **Private** means only named Google accounts can open it, and a judge sees *"Video
unavailable"*. Vimeo behaves the same way, and a password-protected Vimeo video is a Private video
with extra steps.

**Here is why this is a trap and not merely a setting.** To the person who uploaded the file —
signed in, on the account that owns the video — **Private, Unlisted and Public look identical.**
The video plays. Nothing warns anybody. And the failure is indistinguishable from a second,
completely different mistake: a link typed or pasted wrong. Both produce a judge staring at an
error page, and **neither produces any message back to the entrant.** There is exactly one way to
tell the difference from the inside, and it costs thirty seconds: open the link in a browser you
are not signed in to.

### 2a · What the video kit says — measured, not assumed

`docs/submission/VIDEO-KIT.md` is not this sweep's file to edit. It was read, and it is **correct
and complete on all three points:**

| what the instruction must do | where it does it | quoted |
|---|---|---|
| say **Unlisted** satisfies the rule | `VIDEO-KIT.md:98`, `:163` | *"Unlisted is enough; **Private is not**"* — and the settings table marks Unlisted *"yes — and this is the conventional hackathon choice"* |
| **explicitly forbid Private** | `VIDEO-KIT.md:79`, `:164` | *"A perfect capture uploaded Private is a disqualified entry"*; the table row reads *"**NO — this disqualifies the video**"* |
| require a **logged-out** check before the link is pasted | `VIDEO-KIT.md:175`–`:189` | *"Open a **private / incognito window**, or a browser you are not signed into"*, then *"**Confirm you are logged out** — the account avatar must be absent"* |

It goes further than the brief asked, and the extra step is the one that matters most: it says to
copy the URL **from the submission form field itself**, not from the YouTube tab and not from the
clipboard, *"The value that matters is the one that will be submitted"* (`VIDEO-KIT.md:177`–`179`).
That closes the mistyped-link half of the trap, which no privacy setting can.

> **VERDICT for the kit — PASS.** No change needed and none made.

### 2b · Three other places carry the instruction, and none of them carries the test

The founder will not necessarily have the kit open at the moment of upload. **Three other files
tell somebody to upload the video**, and this sweep read all three against the tree as it stands
right now. One of them names the Unlisted-versus-Private distinction; the other two say only
*"unlisted"* and stop. **Not one of the three tells anybody to open the link in a logged-out
browser** — and that is the step that converts knowing the rule into knowing whether you broke it.

Each of the three is owned by another domain, so the fix is **reported here with exact replacement
text and not made.**

**GAP 1 — `docs/submission/DEVPOST.md`, the *Field-by-field checklist for the person pasting*,
row *Video demo link* (`:658`). HALF CLOSED WHILE THIS SWEEP WAS RUNNING, AND THE HALF THAT IS
LEFT IS THE ONE THAT DOES THE WORK.** This is the highest-value of the three, because it is the
table somebody has open at the exact moment they paste the link into the form. When this sweep
first read it, the cell said only *"Kit is in `VIDEO-KIT.md`; the founder records it"*. It was
re-read after that file's owner edited it, and it now carries the distinction:

> *"**The rules require it publicly visible on YouTube or Vimeo — an *unlisted* upload is public
> enough and a *private* one is not**, and that distinction has ended more hackathon entries than
> any missing feature."*

**That is the warning, and it is good. What is still missing is the test.** Knowing that Private
fails does not tell anybody whether *their* upload is Private — the two settings are
indistinguishable from the account that owns them. **Exact text to append to that cell**, additive,
nothing removed:

> **Knowing the rule does not tell you which setting you used** — to the account that uploaded it,
> Private and Unlisted look identical, and both play. **The check that tells them apart takes
> thirty seconds:** copy the URL out of the submission form field itself, open a browser you are
> not signed in to, paste it, and watch the video **play** — not merely load a page. It is also
> the only check that catches a mistyped link, which fails in exactly the same way and is just as
> invisible from here. [`VIDEO-KIT.md`](VIDEO-KIT.md) §00.2.

**GAP 2 — `docs/submission/SUBMISSION.json`, `notes.video_url`.** Reads today: *"the founder
records it, uploads it unlisted to YouTube or Vimeo, and the URL it is given is the value that
belongs in video_url."* That file is the single place a submission address may be written and is
nobody else's to edit. **Exact replacement sentence:**

> the founder records it, uploads it **Unlisted — never Private, which disqualifies the video** —
> to YouTube or Vimeo, **confirms the link plays in a browser he is not signed in to**, and the
> URL it is given is the value that belongs in video_url.

**GAP 3 — `scripts/submission/check_submission_ready.py`, the remedy text printed for the failing
`video URL` row.** Today it prints:

```
     Record it, upload it UNLISTED to YouTube or Vimeo, and paste the URL it is given:
         edit docs/submission/SUBMISSION.json: "video_url": "https://youtu.be/<id>"
         python scripts/submission/check_submission_ready.py --check-urls
```

This is the last message anybody sees before the row goes green, which makes it the last chance to
catch the mistake. **Exact replacement for that block:**

```
     Record it, upload it UNLISTED to YouTube or Vimeo, and paste the URL it is given.
     UNLISTED, not PRIVATE: Private disqualifies the video and a judge sees
     "Video unavailable". Both settings look identical to the account that uploaded it.
         open the URL in a browser you are NOT signed in to; it must PLAY, not just load
         edit docs/submission/SUBMISSION.json: "video_url": "https://youtu.be/<id>"
         python scripts/submission/check_submission_ready.py --check-urls
```

> **VERDICT — PASS in the video kit, which states the rule, forbids Private, and demands the
> logged-out test. GAP in the three places most likely to be read at the moment of upload: none of
> them carries the logged-out test, and two of them do not carry the Private warning either.**
> Three exact replacements are above; none was applied, because none of those files belongs to
> this sweep.
>
> **And the row itself is still open, which no document can close.** `check_submission_ready.py`
> run today: `FAIL  video URL  video_url is UNRESOLVED`. The film has not been recorded. Only the
> founder can close it.

---

## 3 · EVERY LINK RESOLVING — and a checker that can prove it is able to fail

**The problem.** Six documents carry the whole judge-facing surface, and they are dense with
pointers: `140` relative Markdown links and `226` bare evidence-file paths quoted in the prose.
Every one of them breaks silently. Rename a file, move a directory, fix a typo in a filename, and
the pointer goes on reading exactly as convincing as before. **The first person to find out is a
judge who clicks it.** Nothing in this repository checked them before this sweep.

**Read the counts as a reading at an instant, not as a constant.** Those six documents are being
written by other people as this page is written. This sweep's first run over them, an hour
earlier, counted `112` links and `213` citations; the run quoted below counted `140` and `226`.
**Both runs found zero broken pointers, and that is the durable part.** The counts move; the
verdict is re-derived in one command, printed below, by anybody, at any time.

**What was built:** `scripts/submission/check_doc_links.py`. It walks the six named documents,
extracts every pointer, resolves each relative path against the directory of the document that
wrote it, and exits non-zero naming anything that is not on disk.

**Two passes, because there are two kinds of pointer.** The **link pass** reads Markdown link
syntax — `[text](target)` and the reference form `[label]: target`. It skips links inside fenced
code blocks, because those are printed examples of syntax rather than live pointers, and treating
them as live would make the tool cry wolf. The **citation pass** reads bare `evidence/…` and `qa/…`
paths anywhere in the file, code blocks included, because that is exactly where they live: inside
`[src: …]` notes and inside commands a judge is told to run. **A path a document offers as its
evidence is a promise about the disk whether or not anybody made it clickable.**

**What it deliberately does not check, counted and printed rather than dropped.** Web addresses
are not fetched — a documentation check that needs the internet gives a different answer on a
plane, and this one is meant to give the same answer everywhere. The `#section` half of a link is
stripped before the file is looked up: the tool answers *does the file exist*, not *does the
heading exist*. Filename patterns such as `evidence/gate-refusal/proof-<UTC>.json` and bare
directories such as `evidence/deploy/` are skipped by name and counted, because neither is a claim
that one particular file exists.

**The run, today:**

```
$ D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_doc_links.py --verbose
check_doc_links: 6 judge-facing file(s) under D:\CoackroachDBxAWS\mainline
  links     140 relative resolved-or-reported, 1 external not fetched, 0 same-page fragment(s) skipped
  citations 226 evidence/qa path(s) checked, 33 template-or-directory skipped
  DECLARED ABSENT (cited): evidence/deploy/cloud-gate-run.json
OK: every relative link and every cited evidence path resolves.
  → exit 0
```

The six documents it guards are named literally in the source, not matched by a wildcard, so the
guarded set cannot silently grow or shrink when the tree moves: `README.md`, `VERIFY.md`,
`docs/submission/JUDGE-START.md`, `docs/submission/FIRST-FIVE-MINUTES.md`,
`docs/submission/DEVPOST.md`, `docs/deploy/JUDGE-PACK.md`. If one of those files is itself moved
or renamed, the tool reports it as the loudest possible finding — *the guarded set has moved* —
rather than quietly guarding five.

### 3a · Why the self-test checks the reason and not only the exit code

**A self-test that plants a defect and asserts only "the program exited non-zero" passes when the
program fails to start.** It passes when the program crashes on a missing import, when it rejects
its own arguments, when the interpreter is not there. Every one of those is a checker that is
checking nothing, wearing a green. That failure mode is the one this repository already writes
down as its own rule, in `docs/ci/anti-vacuity.md`: *an assertion that a program failed, without
checking why, passes when the program fails to start.*

So `--self-test` runs **two phases and asserts four things**, and the first assertion is the one
people leave out:

```
$ D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_doc_links.py --self-test

--- phase 1: control, a fixture whose every pointer resolves
  OK: every relative link and every cited evidence path resolves.

--- phase 2: planted, one broken link and one broken citation added
  MISSING link  docs/x/FIXTURE.md:16  nope/PLANTED-MISSING-DOC.md
  MISSING cite  docs/x/FIXTURE.md:17  evidence/nope/PLANTED-MISSING-EVIDENCE.json
  FAIL: 2 unresolved pointer(s).

--- verdict
  PASS  A1 control exits 0 (got 0). A checker that refuses a clean tree makes the planted red meaningless.
  PASS  A2 planted exits non-zero (got 1)
  PASS  A3 output names the planted LINK target literally: nope/PLANTED-MISSING-DOC.md
  PASS  A4 output names the planted CITATION target literally: evidence/nope/PLANTED-MISSING-EVIDENCE.json

self-test OK: the checker goes green on a clean tree and red on a planted defect, naming it.
  → exit 0
```

**A1 is the control.** If the checker refuses a clean tree, then its red on the planted defect
says nothing about the planted defect. **A3 and A4 are the reason.** They require the planted
target's own literal name in the output, so a red for any other cause fails the self-test. The
fixture is built in a temporary directory, the checker is re-invoked as a separate process, and
nothing in this repository is touched.

### 3b · The one suppression in the tool, and why it can bite back

One citation on the judge-facing surface points at a file that is not on disk **on purpose**.
`docs/submission/DEVPOST.md:263` names `evidence/deploy/cloud-gate-run.json` in the same sentence
that says it does not exist: *"The four-beat run through the HTTP handler has NOT been recorded
against Cloud … `evidence/` holds none. **OWED:** …"* That is a declaration of an absence, not a
broken pointer, and failing the run on it would be wrong.

It is therefore listed in the tool's `DECLARED_ABSENT` table, printed on every run so the
suppression is never invisible — **and the entry is an assertion in both directions.** While the
path is absent, the finding is suppressed. **The moment the file appears, the entry becomes a
false statement about the tree, and the tool reports `STALE` and exits non-zero**, because the
paragraph that declared the absence has silently become untrue. Proven, not asserted — the
condition was forced in a scratch directory:

```
$ ... --root <temp root where evidence/deploy/cloud-gate-run.json was created> --check docs/x/T.md
MISSING stale DECLARED_ABSENT  evidence/deploy/cloud-gate-run.json
        this path EXISTS now, so the entry is false. Rewrite the sentence that declared it
        absent, then delete the entry.
FAIL: 1 unresolved pointer(s).
  → exit 1
```

**An allow-list that can only ever silence things is how a green gets bought. This one can go
red.**

### 3c · It is wired into no automated build, and that is a decision

Ruling R-H of `docs/submission/extra-credit-plan.md`. The test baseline is **1070 collected /
1069 passed / 0 failed / 0 errors**, and adding an automated lane the day before a deadline is the
cheapest available way to break it. This is a standalone tool, run by hand. Verified rather than
asserted:

```
$ grep -rn "check_doc_links" .github/
  (no matches)
$ grep -rl "check_doc_links" . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules
  ./docs/submission/extra-credit-plan.md      ← the ruling that says not to wire it in
  ./scripts/submission/check_doc_links.py     ← the file itself
```

There are `20` workflow files under `.github/workflows/` and this script appears in none of them.

### 3d · The checker cried wolf once, at this page, and was corrected

**This page was run through the checker too, and it found two things.** One was a real defect in
the checker and is fixed. The other is not a defect at all and is worth recording.

**The defect.** §3 above explains link syntax by printing an example of it inside backticks. The
checker read that printed example as a live pointer and reported it missing. **It was wrong, and
for a checkable reason: Markdown does not render a link inside code — it prints the characters.**
A link in backticks is an illustration, not something a reader can click. The checker already
skipped fenced code blocks for exactly that reason and did not skip inline ones. It now skips
both, and **the fix cost no coverage: the count over the six judge-facing documents was `140`
before the change and `140` after**, which says no real link in any of them was ever hiding inside
backticks.

**The thing that is not a defect.** §3a above quotes the self-test transcript, which contains the
literal path `evidence/nope/PLANTED-MISSING-EVIDENCE.json` — a file that is supposed not to exist.
Run against this page, the checker reports it, twice, correctly. **That is the tool working**: this
page really does print an `evidence/` path that is not on disk. It is why
`docs/submission/MECHANICAL-SWEEP.md` is **not** in the guarded set — a page whose subject matter
is deliberately-broken pointers cannot be guarded by a checker for broken pointers without one of
them being wrong. Recorded here rather than solved by an exception, so that a later maintainer who
adds this page to the set and gets a red knows in ten seconds why.

> **VERDICT — PASS.** `140` links and `226` citations resolve; `0` broken, on two runs an hour
> apart over a tree that grew between them. The check is now repeatable by anyone in one command,
> and the checker has proved it is able to fail for the right reason.

---

## 4 · THE DEMO URL, ANSWERED FROM OUTSIDE

**The rule.** The submission needs a working demo anybody can open. The important word is
*anybody*: an origin that answers when we ask it, using our own credentials, has not been tested
the way a judge will test it.

**How this was measured.** Plain `curl` from a shell holding no key, no token and no signed
request for that account. `curl` sends nothing unless told to, and it was told nothing. **All four
requests in the table below are ordinary reads**, the same kind a browser makes when somebody types
the address. There was one further request that is not a read, and it is described and justified on
its own at the end of this section.

Origin: `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

| request | HTTP | bytes | what came back |
|---|---:|---:|---|
| `GET /v1/health` | `200` | 410 | the health payload, quoted below |
| `GET /` | `200` | 4 749 | the console page |
| `GET /judge` | `200` | 4 749 | the same page (the app routes in the browser) |
| `GET /console` | `200` | 4 749 | the same page |

```
$ curl -sS https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health
{
 "applied_by": "scripts/deploy/cloud_chain.py",
 "cluster_version": "CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)",
 "database": "mainline_demo",
 "deploy_chain_applied": 271,
 "deploy_chain_files": 271,
 "migrations_applied": 0,
 "ok": true,
 "schema_fingerprint": "ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339",
 "seconds": 0.0132,
 "server_date": "2026-08-17T17:18:26.338553Z"
}
```

**Every field of that reading matches the one the lead recorded earlier today** — `ok true`,
`mainline_demo`, `CockroachDB CCL v26.2.5`, `271` of `271`, same `schema_fingerprint` — with the
clock advanced. `deploy_chain_applied 271 of deploy_chain_files 271` is the database saying that
every one of the `271` schema files this project ships has been applied to it.

**The three page requests all return the same `4 749` bytes.** That is not a fault; it is how a
browser-side application works — one page is served for every address and the browser decides what
to draw. It is also why `README.md` already publishes the related gap honestly: the operator
screens are not on this origin, and `GET /operator.html` returns that same page rather than a
different one. **This sweep did not deploy anything to change that, and was not permitted to.**

**The one `POST`, and why it is allowed.** `POST /v1/demo/gate-run` runs the demonstration's four
steps against the live database inside a single transaction that ends in `ROLLBACK` — the database
command that discards everything the transaction did. It writes nothing that survives. The
response says so about itself, in a field the server computes by re-reading the rows afterwards:

```
$ curl -sS -X POST -H 'content-type: application/json' -d '{}' \
    https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/demo/gate-run
  → HTTP 200, 10 500 bytes
```

| field | value |
|---|---|
| `data.verdict` | `PROVEN` |
| `data.persisted` | `false` |
| `data.outcome` | `completed` |
| `data.failures` | `[]` |
| `data.transaction.isolation` | `SERIALIZABLE` |
| `data.transaction.disposition` | `rolled_back` |
| `data.run_id` | `a9b6b505-712d-4541-b604-2c11fe5ab680` |
| `data.generated_at` | `2026-08-17T17:18:39Z` |
| `data.elapsed_ms` | `1620.492` |

The four steps, with the code the database returned for each. Three words first, so the table needs
no decoding. A **`SQLSTATE`** is the five-character code a SQL database returns to say what
happened: `00000` means the statement succeeded, and anything else names a specific refusal. A
**permit** here is a work authorisation — a document saying a job may go ahead. An **obligation**
is a question left unanswered on that permit, which somebody competent still has to answer.

| step | `SQLSTATE` | what the database did |
|---|---|---|
| `read` | `00000` | succeeded — read the permit, and the one question still unanswered on it |
| `merge` | `23514` | **refused** to let the job proceed, by the rule named `gate_closed_when_issued` |
| `projection_drift_attack` | `P0001` | **refused again.** This step is an attack: it edits the database's own summary counter to zero, so the count of unanswered questions *looks* clear. `mainline.fn_permit_merge_gate` does not believe the counter — it recounts the underlying rows and refuses |
| `admit` | `00000` | succeeded — but only after a competent person had signed a real answer to the real question |

**That is the same four-step result the front page publishes**, reproduced today, by an
unauthenticated caller, on a public server, ending in a rollback.

### 4a · The obligation runs to 2026-09-15 — four weeks past the deadline

The rules require the project to stay available free of charge **until the Judging Period ends**.
The judging period is `2026-08-19` → **`2026-09-15`** (`docs/submission/JUDGE-START.md:44`–`:45`;
`compliance-plan.md` Ruling 5; `SUBMISSION.json#notes.demo_url` states the same obligation in the
file that owns the URL). **So the origin answering today is necessary and not sufficient.**

**And there is a real tension inside this repository that should be named rather than discovered
in September.** The deployment carries a cost guard: a budget alarm and a responder function that,
when spending spikes, sets the demo's capacity to zero until a human runs a restore command.
`docs/deploy/COST-BOUND.md` row **T** already states the trade in its own words — *"THE GUARD
CONVERTS A COST ATTACK INTO AN AVAILABILITY ATTACK … it stops the demo, for everyone, at reserved
concurrency 0, until a human runs `scripts/deploy/kill_switch.{sh,ps1} --restore`"*. The demo URL
requires no authorisation at all, by the founder's explicit choice, so **anyone at all** can trip
that alarm.

**The consequence, stated plainly: between `2026-08-19` and `2026-09-15`, a cost-guard stop is a
rules breach, not a saving.** A judge opening a dead URL does not know or care why it is dead. The
guard remains the right trade — an outage is recoverable by one command and an unbounded bill is
not — but **the restore is now time-critical in a way it was not before the submission.** This
sweep changes nothing about the guard and is not permitted to; it records the obligation, the
tension, and the one command that ends an outage.

> **VERDICT — PASS today, with a standing obligation to `2026-09-15` that no measurement taken
> today can discharge.** `NOTRUN`, and named so it is not read as a pass: nobody has checked
> whether anything schedules a teardown of this origin before `2026-09-15`. That question is in
> §7.

---

## 5 · EVERY CITED ARTEFACT EXISTS

**Why this is a separate check from §3.** A link is something a judge clicks. A **citation** is
something else: a bare file path quoted in the middle of a sentence as the evidence behind a
number — this repository's house style, and the thing that makes its claims checkable. Those paths
are not clickable, so no link checker sees them, and they break exactly as easily.

**Measured** by the citation pass of the same tool, over the same six documents:

```
citations 226 evidence/qa path(s) checked, 33 template-or-directory skipped
```

- **`226` paths checked, `0` missing.**
- **`33` skipped by name**, each because it is not a claim that one particular file exists:
  filename patterns such as `evidence/gate-refusal/proof-<UTC>.json`, and directories such as
  `evidence/deploy/`, `evidence/mcp/`, `evidence/aws/probe/`, `evidence/ccloud/`,
  `evidence/reference-ledger/keys/`, `qa/`.
- **`1` absence declared on purpose** — `evidence/deploy/cloud-gate-run.json`, §3b above.

**Corroborated by a second, independent program that this sweep did not write.**
`scripts/submission/check_submission_ready.py` runs its own citation audit over a different
document and reported today: `PASS  tool usage documented  …  35 of 35 cited artefacts present on
disk`. Two programs, two documents, two extraction methods, and no misses in either.

**Nothing was created to satisfy a citation, and that was the instruction.** Writing an empty file
to turn a pointer green is the exact failure this style of citation exists to prevent.

> **VERDICT — PASS.** `226` of `226` cited evidence files present, plus `35` of `35` from the
> second program, one declared absence, and no file created by this sweep.

---

## 6 · THE EXPECTED STALE, AND THE ONE QUESTION FOR THE FOUNDER

### 6a · Ruling R-I — `capture_tool_evidence.py --check` reports `STALE`, and that is expected

`scripts/submission/capture_tool_evidence.py` re-derives two inventory files —
`evidence/tool-usage/crdb-features.json` and `evidence/tool-usage/aws-services.json` — by walking
the whole tree and counting how many files mention each CockroachDB feature and each AWS service.
Among the things it records is `files_scanned`: **how many files the walk saw.**

**So adding any file at all makes it report `STALE`.** Every worker in this wave adds files. Run
today:

```
$ D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/capture_tool_evidence.py --check
tool-usage census is STALE:
  evidence/tool-usage/crdb-features.json: 31484 bytes on disk vs 31487 bytes fresh
  evidence/tool-usage/aws-services.json:  39632 bytes on disk vs 39633 bytes fresh
  run: python scripts/submission/capture_tool_evidence.py
  → exit 1
```

**`DEVPOST.md` already states the rule for reading that message:** *"a `STALE` naming only
`files_scanned` is a tree that grew, not a verdict that moved; a `STALE` naming a verdict, a total
or an anchor is the real thing and is what the tool exists to catch."* The message above prints
byte counts rather than field names, so **this sweep checked which fields actually moved**, using
the tool's own `--print` mode, which writes a fresh census to the screen and touches no file:

```
$ ... capture_tool_evidence.py --print > fresh.txt     # writes nothing to the tree
   then compare fresh.txt field-by-field against the two committed files
```

**Result — `87` fields differ, and every single one is a file count:**

| what differs | count |
|---|---:|
| fields differing in total | `87` |
| of those, fields that are **not** a `file_count`, a `files_by_category` bucket, or `scan.files_scanned` | **`0`** |
| **verdicts** that differ (`EXERCISED` / `DESIGNED` / `NOT-AVAILABLE`) | **`0`** |
| **totals** that differ | **`0`** |

`scan.files_scanned` moved from `7884` to `7973` — `89` more files in the tree. The largest single
category move is documentation: `423` → `481`. **Not one verdict changed. Not one total changed.**

> **RULING R-I, recorded here so a later reader does not meet it as new breakage.** After this wave
> `capture_tool_evidence.py --check` reports `STALE`, exit `1`. **It is expected, it is measured,
> and its shape has been checked: counts, not verdicts.** **NOBODY regenerates
> `evidence/tool-usage/` to make it green.** Those files belong to another domain, and
> regenerating somebody else's artefact to turn a red green is how a green gets bought rather than
> earned. This sweep did not regenerate them; it used `--print`, which writes nothing.

### 6b · Ruling R-F — one open question, for the founder, and it is a question and not a defect

Two contest pages returned **two different spellings of two judging-criterion names.**

| read from | on | spelling 1 | spelling 2 |
|---|---|---|---|
| the `/rules` page, **read verbatim, character-for-character** | `2026-08-16` | **Technological Implementation** | **Product Readiness** |
| the overview page, **read through a summarising model** | `2026-08-17` | Technical Implementation | Production Readiness |

**A verbatim reading is a transcription of what the page says. A summarising model's output is a
paraphrase of what a page says, and paraphrases silently normalise unusual word choices** —
"Technological" into the more common "Technical", "Product" into the more common "Production". So
the two readings are not two equal witnesses. `compliance-plan.md` Ruling 3 recorded the verbatim
reading and also recorded a check on it: `grep` finds zero occurrences of "Production Readiness"
anywhere in the repository's own transcription.

**The verbatim reading therefore stands, and no axis name is changed by anyone in this wave** —
that is Ruling R-F of the lead plan, and this sweep obeys it. The repository continues to say
*Technological Implementation* and *Product Readiness* everywhere.

> **THE ONE QUESTION FOR THE FOUNDER, and it is the only thing on this page that needs a human.**
> When you are next signed in to the contest site, please read the two criterion names off the
> official rules page with your own eyes and tell us which spelling it uses. **If it says
> Technological Implementation and Product Readiness, nothing needs to change** — that is what
> every document already says. **If it says something else, one word in each of two names needs
> updating, and it is a five-minute change.** This is recorded as an open question rather than as
> a defect, because on the evidence we have, the existing spellings are the better-supported ones.

---

## 7 · WHAT THIS SWEEP DID NOT CHECK — `NOTRUN`, and never a pass

A page that lists only what it verified is easy to mistake for a page that verified everything.
These are the questions this sweep did **not** answer.

| # | question | state | why, and who could answer it |
|---|---|---|---|
| N1 | Does anything scheduled — a cost-guard action, a budget rule, a calendar teardown — take the demo origin down before `2026-09-15`? | **NOTRUN** | Answering it means reading live cloud account state. This sweep is forbidden to touch the cloud account at all. It needs the deployment owner, reading the account, once. **§4a is why it matters.** |
| N2 | Does the full test suite still report `1070` collected / `1069` passed / `0` failed / `0` errors? | **NOTRUN** | Not re-run by this sweep. **The no-regression rule is met by construction rather than by measurement**, and the distinction is the point: this sweep added exactly two files — one Markdown page and one standalone script — edited no source file, added no automated lane, and touched nothing under test. The new script's filename does not begin with `test_`, so it is not collected. `DEFAULT_MAX_RESPONSE_BYTES` is still `136 * 1024` at `verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py:323`, verified by reading the line. **The three build lanes a new file *can* break were run and are green** — `ruff check`, `ruff format --check`, and `check_submission_prose.py`, all in §9. Re-running the suite is the orchestrator's to schedule. |
| N3 | Do the `#section` anchors inside links point at headings that exist? | **NOTRUN — out of scope by design** | `check_doc_links.py` answers *does the file exist*, not *does the heading exist*. Stated in the tool's own output and in §3. |
| N4 | Do the external web addresses on the judge-facing pages still resolve? | **NOTRUN — out of scope by design** | `1` external address across the six documents; not fetched, counted and printed instead. A documentation check that needs the internet gives different answers in different places. |
| N5 | Is the video under three minutes, and does it show what the rules require? | **NOTRUN — unanswerable** | There is no film. `video_url` is the literal token `UNRESOLVED`. `VIDEO-KIT.md` §00.1 carries the duration rule and the pre-committed plan for cutting to fit. |

---

## 8 · DEFECTS FOUND IN FILES THIS SWEEP DOES NOT OWN — reported, never edited

Ruling R-G of the lead plan: where a worker finds a defect in another domain's file, it reports the
exact replacement text and hands it over. **Everything in this section is a hand-off. Nothing in
this section was edited.**

| # | file | what is wrong | exact fix |
|---|---|---|---|
| **D1** | `docs/submission/DEVPOST.md`, *Video demo link* row (`:658`) | **half closed while this sweep ran.** That row now warns that an unlisted upload is public enough and a private one is not — good, and it was not there an hour earlier. It still does not tell the founder **how to find out which one he used**, and the two are indistinguishable from his own browser | one additive paragraph in **§2b GAP 1** — the logged-out test, appended to the cell, nothing removed |
| **D2** | `docs/submission/SUBMISSION.json`, `notes.video_url` | says *"uploads it unlisted"* with no warning that Private disqualifies and no logged-out check | replacement sentence in **§2b GAP 2** |
| **D3** | `scripts/submission/check_submission_ready.py`, remedy text for the `video URL` row | prints *"upload it UNLISTED"* and stops; this is the last message before the row goes green | replacement block in **§2b GAP 3** |
| **D4** | repository-wide, `scripts/qa/check_reuse.py` | **the licence-metadata check is RED, and it is not this sweep's doing.** It refuses on a ratchet — a frozen number that is allowed to fall and not to rise: `REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1345`. **`+132` above the frozen baseline** | **attribution measured, not assumed.** This sweep's two files were moved out of the tree, the check re-run, and both moved back: **the measurement was `1345` with them and `1345` without them — identical.** This sweep contributes exactly `0`. **This needs an owner before the tree is pushed**, because it is a lane that can fail the build, and it was already failing before this sweep touched anything |
| **D5** | repository root, `.w5-check.html` | **found and already gone.** An untracked `15 558`-byte scratch preview file was sitting in the root of a public repository, left by another worker in this wave, not covered by `.gitignore`. Harmless while untracked; a judge's first impression of the front page if it were ever committed | **nothing to do.** Its owner removed it fifteen minutes after this sweep found it. Recorded rather than deleted from the list, so that if a file of that shape reappears at the root before the push, somebody recognises it |

**Nothing else needed changing.** The licence files, the video kit's own instructions, and every
link and citation on all six judge-facing documents were checked and were correct as they stood.

**One hand-off that is not a defect but is time-critical.** The submission gate reports
`WARN  remote is in sync  …  28 path(s) are uncommitted and will not be published`. **Uncommitted
work is invisible to a judge.** Everything this wave produced — including this page and
`scripts/submission/check_doc_links.py` — is in that count. This sweep does not commit, by
instruction. **The orchestrator does.**

---

## 9 · REPRODUCE THIS PAGE

Every result above, in the order it appears. Nothing here needs a password, a key, or a cloud
account, and nothing here writes to one.

```bash
# 1 — the licence, detected and visible
gh repo view Shaugato/mainline --json visibility,licenseInfo
curl -sSL -o page.html https://github.com/Shaugato/mainline   # then look for "spdxId":"Apache-2.0"
git ls-files -s LICENSE && wc -c LICENSE

# 2 — the video instruction, where it is written in full
grep -n "Unlisted\|Private\|logged out\|incognito" docs/submission/VIDEO-KIT.md

# 3 and 5 — every link, and every cited evidence file
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_doc_links.py --verbose
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_doc_links.py --self-test
grep -rn "check_doc_links" .github/          # must print nothing — ruling R-H

# 4 — the origin, from outside, with no credential
U=https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
curl -sS "$U/v1/health"
for p in / /judge /console; do curl -sS -o /dev/null -w "$p %{http_code}\n" "$U$p"; done
curl -sS -X POST -H 'content-type: application/json' -d '{}' "$U/v1/demo/gate-run"   # ends in ROLLBACK

# 6a — the expected STALE, and the proof that only counts moved
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/capture_tool_evidence.py --check
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/capture_tool_evidence.py --print > fresh.txt

# the gates this page quotes but does not own
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_submission_ready.py
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_submission_prose.py
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_path_lengths.py
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/qa/check_reuse.py      # RED — see §8 D4
```

**The three checks the new script had to satisfy before it could be called finished**, because a
new file that breaks a build lane is a regression whatever else it proves. **The third one caught
this page**, on a first draft: a shell comment that quoted the linter's own success line, verbatim,
collided with `SUB-08` — the rule that forbids describing this project's cryptographic custody
verification as clean, because seven of its sixteen checks do not run at all. It was a false alarm
about a genuinely dangerous sentence. **The comment was rewritten; the rule was not narrowed to
let it through.**

```bash
# ruff check  -> reports no findings for this file
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m ruff check scripts/submission/check_doc_links.py
# ruff format -> "1 file already formatted"; CI runs `ruff format --check .` over the whole tree
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m ruff format --check scripts/submission/check_doc_links.py
# submission prose OK, exit 0, over the 30 files it scans
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/check_submission_prose.py
```

**What this sweep never did, and was never going to:** no `terraform apply`, no redeploy, no write
to any cloud account or parameter store, no credential printed anywhere, no automated lane added,
no commit, and no edit to any file outside the two it owns —
`docs/submission/MECHANICAL-SWEEP.md` and `scripts/submission/check_doc_links.py`.
