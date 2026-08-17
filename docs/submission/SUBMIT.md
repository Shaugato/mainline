<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SUBMIT — the last hour, in order

**This is the only page you need open after the red light goes off.** It assumes you have the
exported video file and nothing else in your head. Every block of text the form asks for
already exists in this repository; **no wording is retyped on this page**, because a second
copy is a second thing that can drift. Each row below names the file and the section to copy
from.

**Deadline: `2026-08-18 17:00 EDT` = `2026-08-18T21:00:00Z`** — the values
[`SUBMISSION.json`](SUBMISSION.json) carries in `deadline_local` and `deadline_utc`.

**Two things were measured while this page was written, and both are yours to close.**

* **`video_url` in [`SUBMISSION.json`](SUBMISSION.json) still holds the literal token
  `UNRESOLVED`.** That token is written at birth by design and is not a placeholder somebody
  forgot; it is there because the film did not exist. Step 5 closes it.
* **The repository is at least one commit ahead of `origin/master` and has not been pushed.**
  Measured read-only on `2026-08-18`: `git rev-list --left-right --count origin/master...HEAD`
  answered `0	1`, with `HEAD` at `d9c4090` and `origin/master` at `9e91467`. **The layered
  README a judge will read is not on GitHub yet.** Step 7 closes it. Two caveats on that
  reading: it came from the local remote-tracking ref with no fetch, so `git fetch` first if
  you want it re-derived; and it was taken before this same wave's edits landed, so expect
  uncommitted paths in `git status` as well as the unpushed commit. Step 7 covers both.

---

## 1 · Before you start — three things that must be true

Do not open the form until all three hold.

| # | must be true | how you know | if it does not hold |
|---:|---|---|---|
| A | **The exported video file is under 3:00** | Read the duration **off the exported file**, not off any plan or shot list. A plan sums *intended* durations; the rule applies to the file you upload | Do not upload it. The pre-committed cut ladder is `verticals/mainline/demo/film/SPINE.md` §5 and `BEATS.yaml`'s `cut_ladder`, executed top-down and never reordered on the day. `B3` — the memory loop — is floored and may never be cut, because it is what satisfies a rules requirement in its own right |
| B | **The video will be uploaded Unlisted, never Private** | Unlisted satisfies *"publicly visible"*; Private does not, and to you — signed in, on the account that owns it — **Private, Unlisted and Public look identical**. [`VIDEO-KIT.md`](VIDEO-KIT.md) §00.2 is the whole trap written out | Step 4 is the check that catches it. Do not skip step 4 |
| C | **The repository is pushed** | See the measurement above: it was **not**, at the time this page was written | Step 7. Nothing else on this list matters if a judge clones a tree that is a commit behind the one you are describing |

---

## 2 · The ordered steps

One action each, in the order they must happen. Run every command from the repository root,
`D:\CoackroachDBxAWS\mainline`.

### The film

**1 · Read the duration off the exported file.** Where: your file manager or editor, on the
export itself. It must be under `3:00`. If it is at or over, go back to the cut ladder in
condition A above — an overrun does not merely risk disqualification, it silently truncates
whatever you put last, and the end card is last.

**2 · Upload it to YouTube or Vimeo, visibility Unlisted.** The rules name those two hosts and
[`check_submission_ready.py`](../../scripts/submission/check_submission_ready.py) enforces the
host as well as the URL, so a link on any other service fails the gate before a judge ever
sees it.

**3 · Copy the watch URL from the upload page.** Copy it once, into the terminal or editor you
will use in step 5. Do not retype it from memory later.

**4 · Open a private window, confirm you are logged out, and confirm the video *plays*.**
`Ctrl+Shift+N` in Chrome or Edge, `Ctrl+Shift+P` in Firefox. **The account avatar must be
absent** — an incognito window that inherited a session proves nothing. Not "the page loads":
it must play, with the right title and the duration you exported. [`VIDEO-KIT.md`](VIDEO-KIT.md)
§00.2 has this as a five-line checklist.

### The repository

**5 · Write the URL into [`SUBMISSION.json`](SUBMISSION.json).** Open the file, find
`"video_url": "UNRESOLVED"`, and replace the token with the URL from step 3. **Change nothing
else in that file.** It is the single write point for every URL in this submission; every
other document reads from it rather than carrying its own copy.

**6 · Run the gate, with the network flag.**

```bash
python scripts/submission/check_submission_ready.py --check-urls
```

It prints one row per requirement and a numbered remedy under each row that is not `PASS`.
`--check-urls` **fetches** rather than trusts, so it will catch a mistyped video URL. It will
not catch a Private one reliably — a private video's page can still answer `200` — which is
why step 4 exists and is not optional.

**7 · Commit and push.** This carries both the commit that was already outstanding and your
`SUBMISSION.json` edit. Until this lands, `origin/master` does not hold the tree the form
describes.

**8 · Re-run the gate.** Same command as step 6. The `remote_sync` row clears only after the
push, so this run is the one that tells you the tree and the form agree. Exit `0` means every
blocking row is `PASS`; exit `1` prints which are not, each with a literal command. **`NOTRUN`
means NOT CHECKED and is never a pass.**

**9 · Generate the judge credential and leave that terminal open.**

```bash
python scripts/deploy/judge_access.py provision --rotate --show-password
```

The `mainline_judge` password is printed **once** to that terminal and written to no file in
this repository, no evidence artefact and no environment variable. **Do not paste it into any
file here, including this one.** It goes into one place: the form's credentials field, in
step 18.

### The form

**10 · Open the Devpost submission form** for the hackathon and start a new submission.

**11 · Project title →** `MAINLINE`. The repository name, and the name every document uses.

**12 · Elevator pitch →** [`DEVPOST.md`](DEVPOST.md) § *Elevator pitch*, the single line under
its `<!-- PASTE -->` marker. It is `163` characters against a `200`-character cap.

**13 · *About the project* body →** the **eighteen blocks**, in the order given by
[`DEVPOST.md`](DEVPOST.md) § *Field-by-field checklist for the person pasting* → **table A**.
Paste them in that order. Two rules from that table survive unchanged: the five *Judged on*
blocks go in axis order `1`–`5`, and *What actually ran* is **always last**. If the form's
length limit forces a cut, cut *Challenges we ran into* and *How we built it* first — table A
says why, and says which blocks may never be cut.

**14 · Built With →** [`DEVPOST.md`](DEVPOST.md) § *Built With*, the tag list under its
`<!-- PASTE -->` marker. **Do not add tags back.** That list holds only rows the two censuses
mark `EXERCISED`; a tag field cannot carry a verdict, so a `DESIGNED` row put back here would
read as a claim the evidence does not support. The nine that were removed are each named, with
their verdict, in the *What actually ran* block you pasted in step 13.

**15 · Try it out — repository link →** [`SUBMISSION.json`](SUBMISSION.json) → `repo_url`.
Copy the value from the file, not from any prose that quotes it.

**16 · Try it out — demo link →** [`SUBMISSION.json`](SUBMISSION.json) → `demo_url`. Same rule.

**17 · Video demo link →** [`SUBMISSION.json`](SUBMISSION.json) → `video_url`, the value you
wrote in step 5. Reading it back out of the file rather than out of your clipboard is the
cheapest way to confirm the file and the form carry the same string.

**18 · Testing instructions →** [`DEVPOST.md`](DEVPOST.md) § *Testing instructions — how a
judge reaches this, and what each route costs them*, the block under its `<!-- PASTE -->`
marker. **If the form has no such field, this block goes into the *About the project* body**
as block 17 of the eighteen — table A already places it there. Then put the password from
step 9 into the form's own credentials field, and nowhere else.

**19 · Images →** upload [`diagrams/architecture.svg`](diagrams/architecture.svg) **as the
thumbnail**; it carries the request-path boundary on its own face.
[`diagrams/story.svg`](diagrams/story.svg) is the second image. **If the field declines `.svg`,
export a raster copy rather than redrawing.** A screenshot of `/console` on the live demo URL
is a legitimate third image.

**20 · Stop. Do not press submit yet.** Go to §4 below.

> **Any field the form asks for that is not in the map in §3** — a prize category, an opt-in,
> a team field — is not guessed at anywhere in this repository. See §5.

---

## 3 · The Devpost field map

**Where a field's exact name on the form cannot be verified without logging in, the row says
so rather than inventing one.** The copy is ready either way; a field this repository prepared
text for and the form turns out not to have costs nothing, and the reverse costs the
submission.

| Devpost field | Where the text lives | Length limit | Required? |
|---|---|---|---|
| Project title *(field name unverified)* | `MAINLINE` — nothing to copy | unknown | **required** |
| Elevator pitch | [`DEVPOST.md`](DEVPOST.md) § *Elevator pitch* | **200 characters**; the block is `163` | **required** |
| *About the project* — the body | [`DEVPOST.md`](DEVPOST.md) § *Field-by-field checklist* → table A, eighteen blocks in that order | unknown; see table A for the cut order if one is imposed | **required** |
| Built With | [`DEVPOST.md`](DEVPOST.md) § *Built With* | unknown | **required** |
| Try it out — repository link | [`SUBMISSION.json`](SUBMISSION.json) → `repo_url` | n/a | **required** |
| Try it out — demo link | [`SUBMISSION.json`](SUBMISSION.json) → `demo_url` | n/a | **required** |
| Video demo link | [`SUBMISSION.json`](SUBMISSION.json) → `video_url` | n/a — but the **file** must be under 3:00 and on YouTube or Vimeo | **required** |
| Testing instructions / judge access *(field name unverified — the form may not have a separate field)* | [`DEVPOST.md`](DEVPOST.md) § *Testing instructions* | unknown | **required** if the field exists; otherwise it is block 17 of the body |
| Judge credentials *(field name unverified)* | **Nowhere in this repository, by design.** Generated by `python scripts/deploy/judge_access.py provision --rotate --show-password` and printed once to that terminal | n/a | **required** — a judge needs it for the read-only ledger route |
| Image gallery / thumbnail *(field name unverified)* | [`diagrams/architecture.svg`](diagrams/architecture.svg) as thumbnail, [`diagrams/story.svg`](diagrams/story.svg) second | unknown | **strongly recommended** — with no other pictures in the entry, these are what a judge sees first |
| Team members / collaborators *(field name unverified)* | **not prepared** — yours to fill | unknown | unknown |
| Prize categories, opt-ins, organiser-defined fields | **none prepared, and deliberately not guessed at** | unknown | unknown |

**The two optional contest requirements are already answered inside the body you paste in step
13**, so there is nothing extra to attach for either: requirement 6 (an architectural diagram)
by § *Architecture — the diagram, and a caption that works without it* plus the SVG in step 19,
and requirement 7 (feedback on the CockroachDB AI tools) by § *Feedback for CockroachDB — the
optional requirement, actually answered*. Requirement 7 in particular is a judged deliverable
in its own right — six published findings, one struck — so do not let it fall out of the body
if the length is cut.

---

## 4 · The last check before you press submit

Fresh eyes, five items, in this order. Every one of them is a thing that looks fine from the
chair you have been sitting in.

- [ ] **1 · The demo URL, in a private window.** Copy it **from the form field itself**, open
      an incognito window, and load it. You should get the console, not an error. Also try
      `/judge`. Measured read-only on `2026-08-18`, `/`, `/judge` and `/console` each answered
      `200` and `GET /v1/health` answered `ok: true` — but that was from this machine, and the
      point of this check is that it is not.
- [ ] **2 · The video URL, in a private window, from the form field.** Not from your clipboard,
      not from the YouTube tab, not from [`SUBMISSION.json`](SUBMISSION.json). Confirm the
      avatar is absent, then confirm it **plays**. If it does not, the cause is one of exactly
      two things — visibility is Private, or the URL is wrong — and both are a one-minute fix.
- [ ] **3 · The repository URL, in the same private window.** It must open without a login and
      show the README you approved. If the README you see is missing the layering, step 7 did
      not land.
- [ ] **4 · The gate, one last time.** `python scripts/submission/check_submission_ready.py
      --check-urls`. Read the exit code. A row you have not looked at since step 8 may have
      moved, because `remote_sync` re-reads the working tree every run and any late edit dirties it.
- [ ] **5 · The body you pasted still ends with *What actually ran*.** Form editors reorder and
      truncate. That block is the one a judge can check against two committed JSON files in a
      minute, and it is the close.

Then press submit.

**One obligation the submission creates rather than discharges.** The rules require the project
to stay available free of charge **until the judging period ends on `2026-09-15`** — four weeks
past today. The demo answering today is necessary and not sufficient, and a cost-guard action
that tears the origin down in September would be a rules breach rather than a saving.
[`JUDGE-START.md`](JUDGE-START.md) Stop 0 records that tension rather than resolving it.

---

## 5 · If something is wrong at the last minute

### Safe to change now

* **The value of `video_url`, `demo_url` or `repo_url` in
  [`SUBMISSION.json`](SUBMISSION.json)** — that file is the single write point and is meant to
  be edited. Re-run the gate afterwards.
* **The video's visibility setting** — flipping Private to Unlisted changes nothing else and
  needs no re-upload.
* **Re-uploading the video and pasting a new URL** — do steps 3, 4, 5 and 17 again in that
  order.
* **Which of the eighteen blocks you pasted, if a length limit bites** — cut from the top of
  the cut order named in step 13, never from the bottom.
* **Adding a third image** — a `/console` screenshot is legitimate.

### Not safe to change now

* **Do not paste any credential into any file in this repository**, including this one. The
  password from step 9 goes into the form's credentials field and nowhere else. That is not a
  style preference: this tree is public.
* **Do not add a `Built With` tag back**, and do not upgrade a `DESIGNED` verdict to
  `EXERCISED` anywhere in the pasted text to make a table look even. Those labels are what make
  the neighbouring rows believable, and
  [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) is the register of the sentences this project is not
  entitled to say.
* **Do not delete a scoping clause to save space.** The clauses that say what did *not* run —
  the `DESIGNED` rows, *"and NOT in the demo request path"*, *"nothing recorded has run them"* —
  are load-bearing where they sit. Removing one does not shorten a true page; it turns a scoped
  true page into an unscoped false one.
* **Do not re-run `terraform apply`, the proof scripts, or
  `scripts/submission/seed_demo_state.py` to "check" anything.** They write into `evidence/` and
  `qa/`, the numbers in the pasted text are read out of those files, and moving them an hour
  before the deadline means the form and the repository stop agreeing. The read-only checks —
  `check_submission_ready.py`, and a browser — are the ones to use now.
* **Do not try to fix a known red.** The README is over its own byte ceiling and says so about
  itself in its Status section; `docs/CI-STATE.md` sets out which reds mean something and which
  are the tooling being honest. A disclosed red is not a defect a judge will hold against you;
  an undisclosed rewrite at `16:45` is.

### If the video is not going to be ready

Submit anyway, with everything else in place. A submission missing one requirement is assessed
on what is there; a submission that was never filed is not. Then add the video link and save
again, and re-run step 6 so [`SUBMISSION.json`](SUBMISSION.json) still matches the form.
**Whether Devpost lets you edit a saved submission up to the deadline is not verified
anywhere in this repository** — check it on the form itself before you rely on it, because if
it does not, submitting early costs you the video.

---

## What checks this page

`docs/submission/*.md` is scanned by
[`check_submission_prose.py`](../../scripts/submission/check_submission_prose.py) and by
`tests/boundary/test_ci_greps.py::test_outward_facing_documents_make_no_forbidden_claim`, so
this page is held to the same register as every other outward-facing document here. Related
reading, none of it required in the next hour:
[`RULES-MATRIX.md`](RULES-MATRIX.md) for the rule-by-rule verdict,
[`VIDEO-KIT.md`](VIDEO-KIT.md) §00 for the five video sub-rules,
[`JUDGE-START.md`](JUDGE-START.md) for what a judge meets first, and
[`../HONESTY.md`](../HONESTY.md) for what is proven, what is authored and what is not built.
