<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# VIDEO KIT — the capture runbook

The script is finished. `verticals/mainline/demo/script/` holds a locked voice-over
(`VO.md`), the submission cut (`SHOT-LIST.yaml`), a minimum-winnable cut
(`SHOT-LIST-MWS.yaml`), the camera strings, the generated cut diff and a validator that
`.github/workflows/claims.yml` runs, so a drifted shot list is a red build.

This document is the gap between a locked script and a founder holding a microphone: the
machine, the pre-flight, the literal keystrokes, the string each one should produce, and
the pre-committed fallback for every shot whose milestone might not be finished on the day.

**Everything below was re-measured on 2026-08-14** against the pinned local node, and this
revision supersedes the 2026-08-12 one. Where a command was executed while writing this page
it is marked **RAN 2026-08-14**; where it was only confirmed to exist it is marked
**declared, not run here**. The distinction is the document's own honesty rule applied to
itself: a command nobody has run is a plan.

> **Why this page was re-derived rather than re-read.** The signature path started working
> during the completion wave — `mainline.defeater_option` is seeded, the demo API resolves the
> vocabulary digest and the signing credentials out of the database instead of deriving them,
> and the four-beat gate-run now reaches its **admission**. A capture runbook written before
> that is wrong about which beats have a surface. Two of its worked examples were also simply
> stale: §B.4 printed a receipt deadline that is now two days in the past, and §B.1 pasted the
> names of two containers that are no longer the ones running. Both are re-derived below from
> commands re-run on 2026-08-14, not re-typed.
>
> **This page does not produce the video, and nothing in this wave recorded anything.** It
> puts a founder in a position to.

---

## 0 · Authority, and how every number below is re-derived

| Question | The file that answers it |
|---|---|
| How long is a shot? What is the running time? | `verticals/mainline/demo/script/SHOT-LIST.yaml` (`t`, `dur`, `budget`) |
| What is spoken? | `verticals/mainline/demo/script/VO.md`, and `vo`/`word_count` per shot in `SHOT-LIST.yaml` |
| What prose appears on screen? | `verticals/mainline/demo/script/CAMERA-STRINGS.yaml` |
| What does the *database* print? | `verticals/mainline/demo/REFUSAL-STRINGS.yaml` |
| What may the founder not say? | [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) — **fourteen** families as of 2026-08-14 — and §0.3 below for the ones that are specific to the film |

**Those files are authoritative.** `.github/workflows/claims.yml` runs
`script/validate_shotlist.py` over the YAML, so a drifted shot list is a red build.

Sections §0.1 and §0.2 carry the timings and the word counts anyway, because a founder cannot
film from a promise that the numbers exist somewhere. They are **derived, not transcribed**:
one command regenerates both tables, and if it disagrees with what is printed here, the
command is right and this page is stale.

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe - <<'PY'
import yaml, pathlib
d = yaml.safe_load(pathlib.Path("verticals/mainline/demo/script/SHOT-LIST.yaml").read_text(encoding="utf-8"))
b, s = d["budget"], d["shots"]
total, words = sum(x["dur"] for x in s), sum(x.get("word_count") or 0 for x in s)
for x in s:
    print(f"{x['t']//60}:{x['t']%60:02d}  {x['dur']:>2}s  {x['shot_id']:<34} "
          f"{x.get('word_count') or 0:>3}w  {(x.get('word_count') or 0)/x['dur']:.2f} w/s")
print(f"\n{len(s)} shots  {total}s ({total//60}:{total%60:02d})  {words} words  "
      f"{words/total:.2f} w/s")
print(f"ceiling {b['hard_ceiling_s']}s  CI hard fail {b['ci_hard_fail_s']}s  "
      f"headroom {b['hard_ceiling_s'] - total}s")
PY
```

**RAN 2026-08-14.** It printed `25 shots  171s (2:51)  304 words  1.78 w/s` and
`ceiling 180s  CI hard fail 176s  headroom 9s` — the same figures the 2026-08-12 and
2026-08-11 runs produced. Everything in §0.1 and §0.2 is that output, formatted.

The validator agrees, and it is the gate that matters:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe verticals/mainline/demo/script/validate_shotlist.py
```

**RAN 2026-08-14**, exit **0**, printing verbatim:

```
  camera.commit_message_chars 71
  mws.headroom_s           22
  mws.shots                22
  mws.total_s              158
  mws.vo_words             273
  submission.headroom_s    9
  submission.shots         25
  submission.total_s       171
  submission.vo_words      304
  vo_md.words              356
  NOTE  fixtures/corpus/authored/ does not exist yet (owner: corpus-spine-authored), so the authored fixture was not checked. This is not a pass — it enforces once the directory lands
  shot lists OK
```

**The timings did not move, and that is the finding, not the absence of one.** Nothing in
this wave added or removed a shot: the working signature path changed which beats have a
*surface*, not how long the film is. A revision that quietly grew the cut to show off a new
mechanism would have spent the nine seconds of headroom on the least examined part of the
submission. **Beat 3 gained a terminal-checkable surface and gained zero seconds** — §C.4.

The NOTE is not a pass and says so: the authored corpus fixture root does not exist yet, so
the camera string was not checked against it. That NOTE is the same fact that decides beat 1
in §C.2, and it is still the fact.

---

## 0.1 · THE SHOT LIST, TIMED — 2:51 against a 3:00 ceiling

**Total 171 s = 2 minutes 51 seconds.** The rule is under three minutes; the hard ceiling in
the budget is 180 s and CI fails the cut at 176 s, so there are **9 seconds of margin to the
rule and 5 seconds to the build**. That margin is the whole reason the scope-cut ladder in §E
exists and is pre-committed: an over-length cut is disqualified, and nobody discovers it at
02:00 on the deadline.

| in | dur | shot_id | beat | VO words | w/s | never cut | needs |
|---|---|---|---|---|---|---|---|
| `0:00` | 6 s | `s01-cold-open` | — | 14 | 2.33 |  | K3 |
| `0:06` | 7 s | `s02-the-change` | — | 12 | 1.71 |  | K3 |
| `0:13` | 5 s | `s03-title` | — | 10 | 2.00 |  | K0 |
| `0:18` | 5 s | `s04-architecture` | — | 14 | 2.80 |  | K0 |
| `0:23` | 10 s | `s05-beat1-blame-walk` | 1 | 9 | 0.90 |  | K3 |
| `0:33` | 11 s | `s06-beat1-commit-message` | 1 | 19 | 1.73 |  | K3 |
| `0:44` | 7 s | `s07-beat1-identity-survival` | 1 | 13 | 1.86 |  | K3 |
| `0:51` | 7 s | `s08-beat2-merge-refused` | 2 | 10 | 1.43 | **yes** | K1 |
| `0:58` | 7 s | `s09-beat2-constraint` | 2 | 11 | 1.57 | **yes** | K1 |
| `1:05` | 8 s | `s10-beat2-bypass-admin-update` | 2 | 12 | 1.50 | **yes** | K1 |
| `1:13` | 5 s | `s11-beat2-bypass-append-only` | 2 | 8 | 1.60 | **yes** | K1 |
| `1:18` | 10 s | `s12-beat2-bypass-drop-constraint` | 2 | 14 | 1.40 | **yes** | K6 |
| `1:28` | 9 s | `s13-beat3-lattice-refusal` | 3 | 17 | 1.89 | **yes** | K5 |
| `1:37` | 8 s | `s14-beat3-disposition-signed` | 3 | 16 | 2.00 |  | K5 |
| `1:45` | 5 s | `s15-beat3-merge-succeeds` | 3 | 11 | 2.20 |  | K5 |
| `1:50` | 5 s | `s16-beat4-register-gains-activity` | 4 | 11 | 2.20 |  | K6 |
| `1:55` | 6 s | `s17-beat4-lease-revoked` | 4 | 9 | 1.50 | **yes** | K5 |
| `2:01` | 4 s | `s18-beat4-suspend-and-fork` | 4 | 8 | 2.00 |  | K5 |
| `2:05` | 8 s | `s19-beat5-mcp-connect` | 5 | 13 | 1.62 |  | K6 |
| `2:13` | 8 s | `s20-beat5-explain` | 5 | 15 | 1.88 |  | K4 |
| `2:21` | 6 s | `s21-beat5-silence` | 5 | 12 | 2.00 |  | K4 |
| `2:27` | 5 s | `s22-readiness-strip` | — | 11 | 2.20 |  | K6 |
| `2:32` | 8 s | `s23-honesty-card` | — | 12 | 1.50 |  | K0 |
| `2:40` | 5 s | `s24-rubber-stamp` | — | 16 | 3.20 |  | K0 |
| `2:45` | 6 s | `s25-end-card` | — | 7 | 1.17 |  | K0 |
| | **171 s** | **25 shots** | | **304** | **1.78** | | |

`2:45 + 6 = 2:51`. Export at 30 fps: **5 130 frames.**

---

## 0.2 · THE VOICE-OVER, WITH WORD COUNTS — so the timing is checkable

304 words over 171 seconds is **1.78 words per second — 107 words per minute**, which is a
deliberate, unhurried read. It is *slow* for narration on purpose: every sentence in this film
is load-bearing and several of them contain a SQLSTATE.

**Two lines are faster than the rest, and you will feel it.** Read them first, with a
stopwatch, before you commit to the take:

| shot | words | dur | w/s | what to do |
|---|---|---|---|---|
| `s24-rubber-stamp` | 16 | 5 s | **3.20** | The fastest line in the film, 80 % above the average. It is also the most important one to land — it is the honesty beat. Read it at the average rate and it takes **9 s**, i.e. 4 s over. Take those 4 s out of the 9 s of headroom, or split the line across `s23`'s tail. **Do not rush it.** |
| `s04-architecture` | 14 | 5 s | **2.80** | Comfortable if the card is static and you start on the cut. The scope-cut ladder deletes this shot first, and the line with it. |

Everything else sits between 0.90 and 2.33 w/s and needs no decision.

**A stopwatch pass, before any recording:** read each line aloud from the table below, time
it, and write the time next to it. A line whose read time exceeds its `dur` is a line that
will be cut off or a shot that will run long, and it is cheaper to find that out on the sofa
than in the edit.

| shot | VO | words | dur | w/s |
|---|---|---|---|---|
| `s01-cold-open` | One number in a maintenance procedure. Nobody at this site knows why it's 135. | 14 | 6 s | 2.33 |
| `s02-the-change` | An engineer raised it to 150 — the manufacturer's number. Defensible. Approved. | 12 | 7 s | 1.71 |
| `s03-title` | MAINLINE: institutional safety memory as a version-controlled repository, on CockroachDB. | 10 | 5 s | 2.00 |
| `s04-architecture` | Commits are written by incidents. Every clause points at the event that wrote it. | 14 | 5 s | 2.80 |
| `s05-beat1-blame-walk` | So we ask the clause where it came from. | 9 | 10 s | 0.90 |
| `s06-beat1-commit-message` | 2013. A gland seal fire. Two contractors burned. The alarm gave ninety seconds; 135 would have given six minutes. | 19 | 11 s | 1.73 |
| `s07-beat1-identity-survival` | Retypeset 2016. Split 2019. The clause kept its identity, so the blame survived. | 13 | 7 s | 1.86 |
| `s08-beat2-merge-refused` | Today's permit relies on that clause. The supervisor clicks merge. | 10 | 7 s | 1.43 |
| `s09-beat2-constraint` | Refused — not by a warning. By a CHECK constraint: gate_closed_when_issued. | 11 | 7 s | 1.57 |
| `s10-beat2-bypass-admin-update` | Cluster admin. Raw SQL. Our application bypassed entirely. The database still refuses. | 12 | 8 s | 1.50 |
| `s11-beat2-bypass-append-only` | The obligation is append-only. It cannot be deleted. | 8 | 5 s | 1.60 |
| `s12-beat2-bypass-drop-constraint` | An admin can drop the constraint. What they cannot do is drop it unobserved. | 14 | 10 s | 1.40 |
| `s13-beat3-lattice-refusal` | Accept the residual risk? There's no such verdict — no row, and a foreign key says so. | 17 | 9 s | 1.89 |
| `s14-beat3-disposition-signed` | Severity four forces a compensating control and a second signature. We measure deliberation. We never accuse. | 16 | 8 s | 2.00 |
| `s15-beat3-merge-succeeds` | Now it merges, carrying a signed record of who overrode what. | 11 | 5 s | 2.20 |
| `s16-beat4-register-gains-activity` | Then the site register gains an activity. Nobody touches the screen. | 11 | 5 s | 2.20 |
| `s17-beat4-lease-revoked` | He signed it away only while this stayed true. | 9 | 6 s | 1.50 |
| `s18-beat4-suspend-and-fork` | The permit suspends itself and forks a child. | 8 | 4 s | 2.00 |
| `s19-beat5-mcp-connect` | Hand it to an auditor. CockroachDB's own managed MCP — read-only, not ours. | 13 | 8 s | 1.62 |
| `s20-beat5-explain` | Because everyone asks whether the vector search is real — C-SPANN, on the named index. | 15 | 8 s | 1.88 |
| `s21-beat5-silence` | Then the question nobody else answers: what did you not tell me? | 12 | 6 s | 2.00 |
| `s22-readiness-strip` | Single tenant. Row-level security. CockroachDB's audit log hashed into our ledger. | 11 | 5 s | 2.20 |
| `s23-honesty-card` | Live: database in Singapore, inference in Sydney. Operator and incidents are synthetic. | 12 | 8 s | 1.50 |
| `s24-rubber-stamp` | The honest limit: nothing separates a considered disposition from a rubber stamp. We log our silence. | 16 | 5 s | 3.20 |
| `s25-end-card` | Repo, demo, read-only endpoint. Verify it yourself. | 7 | 6 s | 1.17 |

`VO.md` carries two `·hold` marks — `s06` and `s20` — where the line lands early and the
frame is held in silence. **The silence is part of the shot.** Do not fill it.

Export: **1920 × 1080, 30 fps, −16 LUFS, true peak −1 dBTP, captions burned in**
(`SHOT-LIST.yaml: budget.export`). Judges watch muted; a film whose SQLSTATEs are only in the
audio is a film with no evidence in it.

---

## 0.3 · MUST NOT CLAIM — the four the camera will tempt you into, and five more

[`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) is the register and it is **fourteen** families long
as of 2026-08-14. Read it the morning of the shoot. **These four are specific to the film, and
each one is a number somebody will ask you about.**

### 1 · Do NOT say "thirty of thirty invariants", or "all the invariants are enforced"

| | |
|---|---|
| **MUST NOT SAY** | "All thirty machine invariants are enforced." · "30/30." · "The invariant catalogue is complete." |
| **TRUE INSTEAD** | "The catalogue names thirty invariants. Nine are enforced in the database today and twenty-one are pending. The ratchet is what keeps that number honest — it fails the build if a pending invariant is quietly described as enforced." |
| **MEASURED** | `.venv/Scripts/python.exe scripts/mi_ratchet.py report` → **`21 pending / 9 enforced`**. RAN 2026-08-14 (and the same two numbers on 2026-08-12). |
| **THE NUMBER YOU MAY HAVE HEARD** | **28 of 30.** It was true when it was written and nine invariants have been promoted since. `.github/workflows/ci.yml:690` now quotes that string *in order to correct it*, and the survivors are in superseded planning documents under `docs/leads/`. So a grep of the tree returns the stale number and its correction together and you can carry away either. Run the command; quote neither figure from memory. Register family 11. |

The ratchet being red is not a defect to hide. It is the top-level incompleteness counter, and
an honest 9-of-30 with a machine that refuses to let it be overstated scores better under
*Technological Implementation* than a silent 30/30 nobody believes.

### 2 · Do NOT say the custody chain has been verified end to end

| | |
|---|---|
| **MUST NOT SAY** | "The custody chain is verified end to end." · "Every custody check passes." |
| **TRUE INSTEAD** | "Sixteen custody checks are specified. Nine pass. **Seven of the sixteen are unimplemented** — the cryptographic verifier checks are not written — and the CI lane is red for exactly that reason, by name, per check." |
| **MEASURED** | `.github/workflows/custody-chain.yml:740` names the summary line `16 checks \| 9 passed \| 0 failed \| 7 not checked`; `qa/test-state.json#external_checks.custody_bundle_verification` reads `passed 9, failed 0, not_checked 7, total 16, exit_code 2`, and names all seven — `log_signature`, `rfc3161_upper_bound`, `beacon_lower_bound`, `witness_quorum`, `archive_object_lock`, `gate_self_attestation`, `webauthn_reverification`. **Both re-read 2026-08-14, unchanged**, and the line number re-checked because line numbers move and a stale pointer is a claim nobody can follow. |

`s12`'s claim survives this intact: the drop of the constraint becomes an attested leaf. What
is *not* yet built is the cryptographic verification of the chain those leaves sit in. Those
are different sentences and only the first one is filmed.

### 3 · Do NOT say CloudFront, a CDN, or "edge"

| | |
|---|---|
| **MUST NOT SAY** | "Served through CloudFront." · "Behind a CDN." · "At the edge." |
| **TRUE INSTEAD** | "One AWS Lambda Function URL serves the console and the API from a single origin — HTTPS on an AWS-issued certificate, no CDN, no bucket in the request path, and therefore no CORS anywhere." |
| **WHY** | `docs/leads/ship-final.md` §1.4: this AWS account is under a verification hold and a real `terraform apply` was refused with `AccessDenied: Your account must be verified before you can add new CloudFront resources`. DECISION D1 removed CloudFront from the critical path; `var.enable_cloudfront` defaults `false` and **no distribution exists**. |

`s22-readiness-strip`'s fourth tile is *"CloudWatch alarm on gate-bypass attempts"*. Those
alarms are **declared in Terraform and not created**, because the apply has not been run. The
shot's own fallback says to drop that tile if AWS is unreachable — drop it, or film the HCL
that declares it and say "declared". Do not film a CloudWatch console showing an alarm that
belongs to a different project's stack.

### 4 · Do NOT name an AWS service the committed evidence does not show executing

| | |
|---|---|
| **MUST NOT SAY** | Any AWS service as part of the running system unless a committed artefact shows it returning bytes. |
| **TRUE INSTEAD** | "Amazon Bedrock executes: Titan embeddings and Claude Haiku, in `ap-southeast-2`, with the transcript committed." |
| **MEASURED** | `evidence/deploy/aws-live.json`. Everything else in the AWS column — Lambda, SSM, CloudWatch — is **declared in Terraform and not applied**. `check_submission_ready.py`, RAN 2026-08-14, prints `4 CockroachDB tools, 10 AWS services; 2 AWS service(s) marked as having run (Amazon Bedrock, Amazon CloudWatch); 24 of 24 cited artefacts present on disk`. **Two of ten**, named. Say those two. |

### And the five the register carries that a camera makes worse

Families 10 to 14 of [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md). **Four of the five have no
scanner rule at all** — a human is the only control. In one line each:

* **Never say the conformance suite has been demonstrated.** It has not been. Two cases are
  captured instead by `scripts/proof/gate_refusal.py`. (Family 10; `SUB-05` catches the word
  in a file and hears nothing you say.)
* **Never quote the MI ratchet as 28 of 30.** It measures 21 pending / 9 enforced. (Family 11;
  caught by nothing — run the command.)
* **Never say "the deployed demo is proven", and never say "the demo is live".** This one
  **inverted on 2026-08-14 and got harder, not easier.** `evidence/deploy/acceptance.json` now
  reads `verdict PROVEN` — and `target_is_local_emulator: true`, `url http://127.0.0.1:8792`,
  `database_under_test.host localhost:26257`, `is_cockroachdb_cloud: false`. Its sibling
  `cloud-acceptance.json` reads `PROVEN` against the **Cloud** database `mainline_demo` — over
  the **same local emulator socket**, `http://127.0.0.1:8791`. **There is no public origin.**
  The file's own `mode_description` field says *"against CockroachDB Cloud"* and is false for
  the local run; quote `target_provenance`, never `mode_description`. (Family 12; caught by
  nothing — read the file, both files, on the day.)
* **Never say a signature in this project has always pinned the declined alternatives.** Until
  2026-08-14 both signing paths bound `sha256(b"defeater-vocab")`. It is fixed now and the
  captured Cloud bundle still carries the old value. (Family 13; caught by nothing.)
* **Never say the database refuses a defeater code that was never offered.** `mainline.
  disposition` has no foreign key onto `mainline.defeater_option`; that refusal is the
  application's. (Family 14; caught by nothing — and this is the one a founder three minutes
  into saying *"the database refuses"* will say once too often.)

### The demo URL, on `s25`

`s25-end-card` shows the repository, the demo URL and the MCP one-liner. RAN 2026-08-14:
`docs/submission/SUBMISSION.json` holds `"demo_url": "UNRESOLVED"` and
`"video_url": "UNRESOLVED"`; `"repo_url"` reads `https://github.com/Shaugato/mainline`, and
`check_submission_ready.py` confirms the repository itself is `PUBLIC`, asked live.
**Film `s25` last, and do not put a URL on the card that is not in that file.** If it still
reads `UNRESOLVED` on the day, the card carries the repository and the MCP line only, and the
voice-over drops the word "demo" — "*Repo, read-only endpoint. Verify it yourself*" is seven
words minus one and fits the same 6 seconds.

**This prohibition is not softened by the two `PROVEN` acceptance artefacts.** Both were taken
over `scripts/deploy/local_furl.py`, a local emulator of a Lambda Function URL, and both say
so in their own `target_is_local_emulator` field. A green acceptance run against a socket on
your own laptop is not a demo URL, and putting one on the end card would be the single
checkable falsehood in the film.

### And the one that is easiest to get wrong because it sounds modest

The database does **not** stop a cluster admin from dropping the gate. `s12` films the drop
succeeding. The claim is tamper-*evidence* — the drop becomes an attested leaf — and
`REFUSAL-STRINGS.yaml` R3 says so in the file the camera reads from.

---

## A · THE MACHINE

### A.1 One window. Nothing else.

`CAMERA-STRINGS.yaml` lists "browser chrome, an OS taskbar, a cloud console" under
`forbidden_on_camera`. So:

* **One terminal, full screen, no tabs, no split panes, no title bar text that names a
  directory on your disk.** The evidence JSON already leaks `D:\CoackroachDBxAWS\…`; the
  film does not have to.
* **Auto-hide the taskbar** before the first take, not between takes.
* **Notifications off.** Focus Assist / Do Not Disturb on.
* **No browser anywhere in frame**, including for the console shots — those are the
  console's own window, and if that is impossible, the fallbacks in section C put the same
  content in the terminal.

### A.2 Geometry, and how to check it rather than trust it

The camera-facing output of `scripts/submission/seed_demo_state.py --camera` is
**hard-wrapped at 96 columns by the program** (`CAMERA_WIDTH`), precisely so a soft wrap
cannot re-flow the frame on a different machine. Set the terminal to **100 columns × 32
rows** and it will never wrap.

Check it, do not eyeball it — print a ruler and confirm it occupies exactly one line:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "print(''.join(str(i%10) for i in range(1,101)))"
```

If that string wraps, the terminal is narrower than 100 columns and every long refusal
message will break in a place you did not choose.

**Font size follows from the geometry, not from taste.** At a 1920-pixel-wide capture and
100 columns, each character cell is 19 pixels wide, which for a typical monospace face
(advance width about 0.6 em) means roughly a **24 pt / 32 px** font. Set the size, then run
the ruler again: if it still fits on one line and the window is full-screen at 1080p, the
size is right. `23514 gate_closed_when_issued` is 27 characters — at that cell size it
occupies about a quarter of the frame width, which survives the downscale a judge's browser
applies to an embedded player.

**The verification table is wider — about 135 columns, mostly UUIDs — and is deliberately
not wrapped.** It is a diagnostic you read *before* recording. Do not film it.

### A.3 Colour

Every line these scripts print is **plain ASCII with no ANSI colour codes**, so the terminal
theme is doing all of the contrast work:

* Near-black background, near-white foreground. Windows Terminal's default Campbell scheme
  is fine. Anything with grey-on-grey "comment" colours is not.
* **Cursor blink off.** A blinking cursor in a held frame reads as a stall.
* **No transparency, no acrylic, no background image.** Compression artefacts land on
  exactly the small text you need legible.

### A.4 `just` and `uv` are NOT on `PATH` on this machine

This is measured, and re-measured on **2026-08-14**, by `scripts/qa/doctor.py`, which reports
two blocking rows:

```
FAIL    uv (python workspace)   not on PATH
FAIL    just (command surface)  not on PATH
```

**Be precise about `uv`, because the tree contains a trap.** `.venv/Scripts/uv.exe` **does
exist** — `ls .venv/Scripts/*.exe`, RAN 2026-08-14, lists `uv.exe`, `uvw.exe` and `uvx.exe`
beside `python.exe`. The doctor is still right: the row is *"not on PATH"*, and a bare `uv`
typed at a prompt on this machine fails. Do not "correct" the doctor because you found the
binary, and do not type `uv` on camera on the strength of having found it. **`uv: command not
found` is not a suite result and it is not a take.**

`QUICKSTART.md` and `docs/HONESTY.md` both describe the workflow as `just prove`, `just up`,
`just migrate`. **Do not type any of those on camera.** They will error, the take is gone,
and the recovery is worse than the original shot. Every command in this kit is the plain
`python` form against the workspace interpreter:

```
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe
```

Use the absolute path. A bare `python` on this machine may resolve to a different
interpreter, and `psycopg` will not be in it. Where a command is a console script rather
than a module, it is spelled the same way — `D:/CoackroachDBxAWS/mainline/.venv/Scripts/`
plus the executable name, which is how `trappoint-migrate` appears in §B.10.

Neither FAIL blocks the proof. `doctor.py` says so itself, and section B.2 pastes the
output that proves it.

---

## B · THE PRE-FLIGHT

Run these in order. Each step gives the command, then the output it produced on
**2026-08-14**, pasted below it. If your output differs materially, stop and fix it —
that is the point of pasting it.

**B.4 is a hard gate and it is the quietest way this shoot fails.** Everything before it can
be checked by looking at the screen. B.4 cannot: it is a deadline, it is invisible once it
passes, and the failure it causes looks exactly like the product working. **The worked example
in B.4 is re-derived live on every revision of this page, never re-typed** — a runbook that
ships a blown deadline as its example has taught the reader to ignore the example.

### B.1 The node is up and it is the pinned image

```bash
docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"
```

**RAN 2026-08-14:**

```
trappoint-crdb	cockroachdb/cockroach:v26.2.5	Up 34 hours (healthy)
```

The image must be `cockroachdb/cockroach:v26.2.5`. A different tag is a different product
and a different set of error strings.

**The container name changed and the 2026-08-12 revision of this page is wrong about it.**
That revision pasted two containers, `trappoint-testkit-crdb` and `mainline-crdb`, and told
you only `mainline-crdb` answers on `26257`. **Neither name exists on this machine today.**
One container answers, it is called `trappoint-crdb`, and it is on `26257`. So: **do not match
on the name.** The pre-flight in B.2 confirms which *socket* answered, and the socket is the
thing every command in this kit actually uses. If your `docker ps` shows a different name
again, that is fine; if it shows a different *image tag*, stop.

### B.2 The doctor, and its two known FAIL rows

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/qa/doctor.py
```

**RAN 2026-08-14**, verbatim:

```
MAINLINE preflight - Windows-11-10.0.26200-SP0 - 2026-08-14T09:34:03+00:00

STATUS  CHECK                   OBSERVED
------  ----------------------  ------------------------------------------------
OK      python >= 3.13          3.13.14 at D:\CoackroachDBxAWS\mainline\.venv\Scripts\python.exe
OK      docker (client)         Docker version 29.3.1, build c2be9cc
OK      docker engine (API)     server 29.3.1 (linux)
FAIL    uv (python workspace)   not on PATH
FAIL    just (command surface)  not on PATH
OK      psycopg 3 (importable)  psycopg 3.3.4
OK      workspace installed     .venv/ present
OK      node >=24.0.0           v24.14.0
OK      pnpm >=11.0.0           11.5.3
OK      compose.yaml image pin  cockroachdb/cockroach:v26.2.5  (parsed by trappoint_testkit.image)
OK      pinned image present    cockroachdb/cockroach:v26.2.5 -> sha256:771325a0586b
OK      migration tree          271 .sql files in verticals/mainline/db/migrations
OK      proof script            scripts/proof/gate_refusal.py
OK      pgwire 127.0.0.1:26257  a socket accepted the connection [the local single-node default]
OK      cockroachdb version     CockroachDB CCL v26.2.5
OK      node clock vs host      -0.024s (node - host, round trip removed)
OK      gc.ttlseconds == 4500   4500 - aligned with CockroachDB Cloud
------  ----------------------  ------------------------------------------------

NOT READY - 2 blocking checks. In order: ...
```

It exits **NOT READY - 2 blocking checks**, and that is expected.

* **`just` not on PATH** — `just` is a command *surface*, a set of one-line bash recipes.
  Nothing in this kit uses it. It blocks the doctor's own readiness verdict, not the proof.
* **`uv` not on PATH** — `uv` resolves the 27-distribution workspace from the lockfile. The
  workspace is *already installed* in `.venv/`, which the doctor confirms on the line
  `OK  workspace installed`. `uv` would be needed to rebuild it, not to run it.
* **`gc.ttlseconds` is now an OK row, not a WARN.** On 2026-08-10 the local node reported the
  permissive 14400 default and the doctor warned about the fidelity gap; today it reads
  **4500**, which is what Cloud enforces. `seed_demo_state.py` pins 4500 on the database it
  creates regardless, so this changes nothing about the shoot — but if your run shows the
  WARN again, that is the node's zone configuration and not a fault.
* **`node clock vs host`** is worth a glance: every deadline in B.4 is the *server's* clock,
  and this row is how far it is from yours. It read `-0.024s` on 2026-08-14 and `+0.050s` on
  2026-08-12 — tens of milliseconds either way, which is why B.4's two-hour window can be
  treated as two hours and not as an estimate.

### B.3 Seed the state, in one command

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --database w_D6_video_kit
```

This drops and rebuilds the database, applies the whole migration chain, seeds the smallest
history in which the claim is decidable, and then **proves it did** — by executing the three
refusals for real and rolling each one back. It takes about a minute, most of it the chain.

**RAN 2026-08-14** (against `w_D6_video_kit`, a scratch database built by exactly this
command, so that another worker's `w_s08_demo_state` was not disturbed), verbatim:

```
MAINLINE demo state - w_D6_video_kit - build

CHECK                      STATUS  SHOTS    OBSERVED
-------------------------  ------  -------  --------------------------------------------
cluster                    INFO             CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
gc.ttlseconds              INFO             4500 on w_D6_video_kit (Cloud enforces 4500)
migration chain            OK      all      271/271 applied, 0 failed, 0 unexplained, 96.8s
reached 0115 merge gate    OK      s08 s09  0115_fn_permit_merge_gate applied
seed history               OK      all      permit_id=d5397043-… check_id=63495c7d-…
gate objects               OK      s08-s12  8/8 present
permit row                 OK      s08      1 permit(s) with external_ref='PTW-PROOF-1'; permit_id=d5397043-…
permit state               OK      s08      state='dispositioned' (the client's claim that every obligation is disposed of)
open obligation            OK      s08 s09  permit.open_blocking=1
obligation row             OK      s11      blocking_check check_id=63495c7d-…
no disposition yet         OK      s08 s13  0 live disposition(s) against the obligation
exposure receipt live      OK      s13 s14  receipt_id=2bed3dd4-… LIVE until 2026-08-14T11:22:40Z
gate constraint attached   OK      s09 s12  mainline.permit CONSTRAINT gate_closed_when_issued
append-only weld           OK      s11      TRIGGER append_only ON mainline.blocking_check
explain_refusal installed  OK      s10      trappoint.explain_refusal(kind, id, constraint, attempt)
merge REFUSES              OK      s08 s09  REFUSED [23514] gate_closed_when_issued (reported)
raw UPDATE REFUSES         OK      s10      [23514] failed to satisfy CHECK constraint ((state != 'merged':::mainlin
DELETE REFUSES             OK      s11      [P0001] MAINLINE: this table is append-only; write a new row
state intact after probes  OK      s08-s12  state='dispositioned' open_blocking=1 dispositions=0
open_blocking written by   INFO    s08      trigger check_materialised (0121) — the database's own projection
-------------------------  ------  -------  --------------------------------------------

VERDICT  READY - 20 checks, 0 failed. Roll camera.
```

**The chain took 96.8 s on this run against 54.3 s on 2026-08-12, over the same 271 files.**
Same tree, same node, a factor of nearly two. Nothing is wrong; the machine was busy. Budget
the slower figure and never quote either one from memory — the row prints the number.

**Exit 0 or do not record.** Exit 1 means the state is wrong and every failing row is named.
Exit 2 means there was no cluster — a different problem, kept separate on purpose.

**The count on the `migration chain` row is that run's, not this page's.** It moves: the
committed `evidence/gate-refusal/proof-20260810T004200Z.json` records a smaller chain and
fifteen failures, all attributed to five tables that then gained producer migrations. Read
the number off the run you just did, say that number, and if a judge asks where it came from,
name `scripts/submission/seed_demo_state.py` and re-derive it in front of them. Never carry a
migration count in your head onto camera, and never describe the chain with a word like
"cleanly" — the artefact says how many applied and how many failed, and those two numbers are
the whole answer.

**The seeded database does not survive a Docker restart or a machine reboot**, and nothing
recreates it. A `--verify-only` run against a clean machine answers:

```
database  FAIL    all    <the database you named> does not exist on this cluster - run without --verify-only to build it
VERDICT  NOT READY - 1 check failed
```

So the full command above is not a one-off setup step you did last week; it is the first
thing you type on capture day.

The identifiers are minted fresh on every rebuild. The 2026-08-14 run printed:

```
  database        w_D6_video_kit
  permit_id       d5397043-c919-42a1-a715-f72609e14ab1
  check_id        63495c7d-742a-44d7-ba6a-9a9b933eb13d
  site_id         f5db39eb-cca6-4abd-9e72-83c81b54ec0c
```

Not one of those four values matches the 2026-08-12 run's. That is the block working.

**Those exact values will not be yours.** Copy from *your* run's ON-CAMERA SUBSTITUTIONS
block, never from this page — that is the entire reason the block exists. It prints the
`permit_id`, `check_id` and `site_id` this run minted, and the SQL statements with those
values already substituted. **Never retype a UUID on camera** — a mistyped UUID is a take,
and it is a take you will not notice until the error message is the wrong error message.

### B.4 THE RECEIPT DEADLINE — a hard gate, and the quietest way this shoot fails

`seed_demo_state.py` prints this block on **every** run, in both modes, immediately under the
caveat. **RAN 2026-08-14**, against a freshly seeded state, verbatim:

```
BEAT 4   SKIPS AFTER 2026-08-14T11:22:40Z  (1h 59m from now, server clock)
         After this instant a local gate-run SKIPS beat 4 (the admission) and reports NOT
         PROVEN, while beats 1-3 keep refusing exactly as they do now — so the failure does not
         look like a failure on camera. scenario._RECEIPT_SQL selects the exposure receipt only
         while expires_at > now(); seed_history issues it with a two-hour window.
         Receipt 2bed3dd4-8256-4d76-a296-2c6113245360 is LIVE. Finish the take before that
         instant, or re-run: python scripts/submission/seed_demo_state.py --database
         w_D6_video_kit
```

> **That instant, `2026-08-14T11:22:40Z`, was in the future by 1 h 59 m when this page was
> written and is in the past now.** That is not a defect in the example — it is the example.
> **This block is the only paste on this page that is guaranteed stale by the time you read
> it**, and a revision of this page that leaves an old one standing is showing a founder a
> blown gate as the model of a healthy one. The 2026-08-12 revision printed
> `2026-08-12T18:37:01Z` and shipped it for two days. Re-derive; never re-type.

**Write your own instant on a sticky note before you touch the camera.** Not the one above —
yours. It is roughly two hours after your seed and it is the only number on the screen that
becomes false while you are looking at it.

**The mechanism, so you can trust the gate rather than obey it.** Every line reference here
was re-checked on **2026-08-14**, because `gate_run.py` moved in the completion wave and a
stale pointer is a claim nobody can follow. `scenario._RECEIPT_SQL` (`scenario.py:297`)
selects the exposure receipt with
`WHERE r.permit_id = %s AND l.check_id = %s AND r.expires_at > now()` (`scenario.py:301`).
With no live receipt, `resolve()` returns `receipt_id = None`; **`gate_run.py:734`** tests
exactly that — `if resolved.check_id is None or resolved.receipt_id is None:` — and
**`gate_run.py:735`** sets `beats[3]["outcome"] = "skipped"`. *(The 2026-08-12 revision cited
`:552` and `:553`; those line numbers are wrong on today's tree and are corrected here rather
than carried.)* A skipped beat 4 makes the verdict
`NOT PROVEN`. Beats 1 to 3 are unaffected — the projection still holds, the gate still
refuses with `23514 gate_closed_when_issued`, the drift probe still raises `P0001`. **Every
refusal on camera still refuses.** That is why this is dangerous: there is no error message,
no red row, and nothing on the frame changes. The demo's whole point is that the gate refuses
*and then admits*; without beat 4 it is a gate that only ever says no, which `gate_run.py`
itself calls broken.

It also reaches beat 3 of the *film*. A disposition's foreign key
(`0066_disposition.sql:160`, `fk_exposure`) lands on the pair `(receipt_id, check_id)`, so a
signature that cannot cite a live receipt is a signature the database will not accept — which
is `s13`, `s14` and `s15`.

**THE GATE, in three rules:**

1. **Past the instant → re-seed.** Run B.3 in full. The receipt window cannot be extended in
   place: `mainline.exposure_receipt` is append-only, so a new receipt has to be issued.
2. **Within twenty minutes of the instant → re-seed before you roll.** Three takes of a shot
   plus a rebuild does not fit into twenty minutes, and the rebuild is a minute you can spend
   now instead of a beat you lose later.
3. **After any re-seed, re-verify** (B.6) **and copy the new UUIDs.** They are minted fresh
   every time and the substitutions block on your screen is now stale.

**And the rule about which database this gate governs.** B.4 is about **STATE A only**. The
demo world (STATE B, §B.10) carries a receipt seeded to expire `2027-01-01`, measured on
2026-08-14 by reading `mainline.exposure_receipt` on a freshly built world. **Nothing filmed
from STATE B has a two-hour clock, and nothing filmed from STATE A does not.** §B.9 states the
split and why neither expiry may be changed to make the other's problem go away.

**The one-line check to run between takes.** It asks the database the same question
`scenario._RECEIPT_SQL` asks, and answers in one line. Substitute **your** database for
`w_D6_video_kit`:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg,datetime as dt;r=psycopg.connect('postgresql://root@localhost:26257/w_D6_video_kit?sslmode=disable&connect_timeout=10').execute('SELECT r.expires_at, r.expires_at > now() FROM mainline.exposure_receipt r JOIN mainline.exposure_line l ON l.receipt_id = r.receipt_id JOIN mainline.blocking_check b ON b.check_id = l.check_id AND b.permit_id = r.permit_id JOIN mainline.permit p ON p.permit_id = r.permit_id AND p.external_ref = %s ORDER BY r.issued_at DESC LIMIT 1', ('PTW-PROOF-1',)).fetchone();print('BEAT 4', ('LIVE until ' if r and r[1] else 'DEAD since ') + r[0].astimezone(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ') if r else 'BEAT 4 NO RECEIPT - re-seed')"
```

**RAN 2026-08-14** in PowerShell against the freshly seeded scratch database, and it printed,
verbatim and on one line:

```
BEAT 4 LIVE until 2026-08-14T11:22:40Z
```

It agrees with the block B.3 printed, to the second, which is the point of running both: the
tripwire and the seeder ask the same question of the same rows and are written separately.
If it says `DEAD since` or `NO RECEIPT`, stop and run B.3. It is a tripwire, not an authority
— `--verify-only` is the authority, and it names the row `exposure receipt live`.

**Why an expired receipt used to be survivable and is not.** `seed_demo_state.py` records, in
the comment above the row itself, that it once printed `VERDICT READY` against a database
whose receipt had died thirty-two hours earlier — the row was INFO, and an INFO row cannot
stop a shoot. Read back on 2026-08-14 at `scripts/submission/seed_demo_state.py:694`
(`table.add("exposure receipt live", bool(live), observed, shots="s13 s14")`), the row is a
**required** check, so a dead receipt now fails the table and stops the shoot instead of
quietly costing it a beat.

### B.5 The caveat you must read before you speak

`seed_demo_state.py` prints this on **every** run, in both modes, whether or not anything is
wrong:

```
CAVEAT   WHO WROTE mainline.permit.open_blocking? The gate's own projection trigger
         (check_materialised, migration 0121) depends on mainline_ops.outbox. Where that table
         has no producer migration the trigger cannot install, and the seeded history writes the
         counter itself — to the value the gate independently re-derives from
         mainline.blocking_check LEFT JOIN mainline.disposition. The refusal on camera is the
         database's either way; the COUNTER that provoked it may not be.
         MEASURED ON THIS RUN: the trigger IS installed, so the counter is the database's own
         projection. You may say the projection closed the counter.
```

The second paragraph is the one to read. It is measured from the catalogue on that run, not
copied from a document, **because the answer has already changed once**: the committed
`evidence/gate-refusal/proof-20260810T004200Z.json` recorded the trigger as absent, and the
tree has since gained producer migrations for the five tables that were unproduced. If a
future run says `the trigger is ABSENT`, then the sentence "the projection closed the counter"
is not available to you and the sentence "the gate re-derived the count and refused" is.

### B.6 Re-verify without rebuilding

Between takes, and after anything destructive:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --verify-only --database w_D6_video_kit
```

Seconds, not a minute. It exits 1 and names the broken rows if the state has moved. Measured
after typing shot `s12`'s `ALTER TABLE … DROP CONSTRAINT` by hand:

```
gate constraint attached   FAIL    s09 s12  … is ABSENT — s12 has nothing to drop
merge REFUSES              FAIL    s08 s09  ADMITTED [00000] — the gate let it through …
raw UPDATE REFUSES         FAIL    s10      [00000] the statement SUCCEEDED and was rolled back
VERDICT  NOT READY - 4 check(s) failed
```

That is the tool working. **After `s12`, rebuild** (B.3) before any further take. It also
re-prints the B.4 deadline, which is the cheapest way to see it.

### B.7 The dry pass of the beat-2 commands

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --camera --database w_D6_video_kit
```

Verifies first, refuses to print the block if the table is not green, then prints beat 2 at
a fixed 96 columns. **RAN 2026-08-14** against `w_D6_video_kit`, verbatim (UUIDs are this
run's, and this mode's verdict line reads `READY - 16 checks, 0 failed` because
`--verify-only` does not re-run the four build-time rows):

```
==============================================================================
BEAT 2 · THE REFUSAL AND THE BYPASS
SQLSTATE, message and constraint are the SERVER'S. The layout is this script's.
Every statement below is rolled back; the database is unchanged.
==============================================================================

s09 · OUR CLIENT · CALL mainline.merge_permit(...)
    outcome     REFUSED
    SQLSTATE: 23514
    constraint: gate_closed_when_issued
    source:     diag.constraint_name (reported)

s10 · RAW SQL AS CLUSTER ADMIN · the application bypassed entirely
    UPDATE mainline.permit SET state = 'merged'
      WHERE permit_id = 'd5397043-c919-42a1-a715-f72609e14ab1';
    ERROR: failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR
           (open_blocking = 0:::INT8))
    SQLSTATE: 23514
    constraint: gate_closed_when_issued   <- from diag.constraint_name
    SELECT trappoint.explain_refusal(
      'permit', 'd5397043-c919-42a1-a715-f72609e14ab1', 'gate_closed_when_issued');
    class:      gate
    constraint: gate_closed_when_issued
    mus:        1 obligation(s)
    naa:        dispose_obligations
                1 obligation(s) remain open on this subject; disposing of exactly those restores
                admissibility

s11 · RAW SQL AS CLUSTER ADMIN · the obligation is append-only
    DELETE FROM mainline.blocking_check
      WHERE permit_id = 'd5397043-c919-42a1-a715-f72609e14ab1';
    ERROR: MAINLINE: this table is append-only; write a new row
    SQLSTATE: P0001

s12 · NOT RUN HERE. It is destructive and it is meant to be:
    ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued;
    Type it on camera. Then rebuild this database before the next take.
==============================================================================
```

**The banner is not decoration and must stay in frame.** It says the SQLSTATE, message and
constraint are the server's and the layout is the script's. That sentence is the difference
between a demonstration and a mock-up, and a judge who sees it stops wondering.

### B.8 The whole proof, if you want the headline in one command

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable
```

Prints `REFUSAL … REFUSED [23514] gate_closed_when_issued (reported)`, then the forged-counter
refusal, then the admission, then `VERDICT PROVEN`. It builds and drops its own throwaway
database (`w_qr_gate_refusal_proof`), so it does **not** disturb `w_D6_video_kit` — but it
takes about a minute and it is a different frame from beat 2. Use it as the fallback for
`s09` if the console is unavailable, not as the main path. Declared here, not re-run while
this page was written; §B.3 exercises the same imported primitives, and the **committed
transcript of its most recent run is on disk** and was read back on 2026-08-14:

```
evidence/gate-refusal/proof-20260814T032418Z.json
  generated_at_utc  2026-08-14T03:24:18Z
  cluster           CockroachDB CCL v26.2.5 · database w_qr_gate_refusal_proof · gc.ttlseconds 4500
  chain             271 files, 271 applied, 0 failed, 71.797s
  PROJECTION        10 of 10 assertions held · open_blocking 0->1 · gate_epoch 0->1
                    · severity 4 projected where the client supplied 0
  REFUSAL           REFUSED [23514] gate_closed_when_issued        (constraint_source: reported)
  DRIFT             REFUSED [P0001] mainline.fn_permit_merge_gate  (constraint_source: parsed)
  DISPOSITION       signed=true · kind=applied · countersigned_count_after=1
  ADMISSION         ADMITTED [00000]
  caveats           []          failures  []
  VERDICT           PROVEN
```

**That is the four-beat signature the whole film is about — `00000 → 23514 → P0001 → 00000`
— and it is `PROVEN`, caveat-free, on a LOCAL database.** `cluster.database` reads
`w_qr_gate_refusal_proof`; it is not Cloud and this page does not say it is.

### B.9 THE TWO RECEIPTS — two databases, two expiries, and the split is on purpose

**Read this before B.10, because it is the sentence that explains why B.4's deadline does not
apply to half the shots on this page.** There are two exposure receipts in this project, they
expire eighteen months apart, and **that is a design, not a drift**.

| | the FILM path | the DEMO-API / JUDGE path |
|---|---|---|
| **database** | `w_D6_video_kit` (STATE A), built by `scripts/submission/seed_demo_state.py` | `w_demo_world` / Cloud `mainline_demo` (STATE B), built by `scripts/deploy/seed_demo.py` |
| **receipt written by** | `scripts/proof/gate_refusal.py::seed_history` — `gate_refusal.py:1243` issues `now() + INTERVAL '2 hours'` | `verticals/mainline/db/seeds/demo/demo_permit.sql:416` — a literal `TIMESTAMPTZ '2027-01-01 00:00:00+00'` |
| **expires** | **two hours after you seed** | **2027-01-01**, and it has not moved |
| **who it serves** | the founder, in one shooting session | every judge, for the whole judging period |
| **what B.4's deadline governs** | this one, and only this one | nothing — the judge path has no shoot clock |

**Neither expiry was changed by this page and neither may be.** `demo_permit.sql:398-403`
declares the long one on its own face, in the file, in terms:

> ⚠ STAGED, AND SAY SO. In the product a receipt's TTL is hours — `mainline.exposure_receipt`
> constrains only `expires_at > issued_at`, and the application picks the window. This seeded
> receipt expires on 2027-01-01 so that the admission beat keeps working for every judge for
> the whole judging period, rather than for two hours after somebody ran the deploy. That is a
> demonstration convenience, it belongs in DEMO-HONESTY.md's STAGED column, and it is written
> down here so nobody reads the long window as the product's default.

**The seed is authoritative; this page is checked against it.** The temptation this section
exists to kill is the obvious one: B.4 is a nuisance, the judge path proves a two-hour window
is not required, so why not give the film the 2027 receipt too? Because the two-hour window is
the *product's* behaviour and the long one is the *demonstration's*, and the film is the
artefact a stranger will believe. **A shoot that films the 2027 receipt is filming the staged
element and calling it the mechanism.** If the deadline is inconvenient, re-seed — that is
what rule 1 in B.4 is for.

**On camera, if asked:** *"There are two seeded worlds. The one on screen issues a two-hour
receipt, which is the product's shape. The judge-facing one is deliberately given until 2027
so the admission beat still answers next month, and the seed file says so in a comment above
the row."* That is the whole answer and it costs eight seconds.

### B.10 The SECOND database — and why it cannot be the first one

Beat 2 films the **proof** history: permit `PTW-PROOF-1`, seeded by B.3. The console shots —
the merge click, the disposition ladder, the site register — want the **demo
world**: `verticals/mainline/db/seeds/demo/demo_world.sql` and `demo_permit.sql`, the same
pair `scripts/deploy/seed_demo.py` writes into the Cloud database.

**They cannot share a database, and this was measured rather than assumed.** Seeding the demo
world into the B.3 database succeeded and then failed its own verdict:

```
  seed         demo_world.sql       OK                 0.10s attempts=1
  seed         demo_permit.sql      OK                 0.17s attempts=1
permits       2 in mainline.permit, 1 is the demo permit
MERGE         REFUSED [23514] gate_closed_when_issued (reported)
rollback      nothing_persisted=True
  ! 2 permits stand in mainline.permit, expected exactly 1 — the demo database has accumulated
    state that is not the seed
VERDICT       WRONG STATE
```

**RAN 2026-08-12**, and deliberately **not repeated** on 2026-08-14 — the whole point of this
section is that you do not do this. Both seed files applied in under a third of a second and
the demo permit's merge was refused by the database with the same SQLSTATE and the same
constraint — so the mechanism is fine. `seed_demo.py` requires **exactly one** permit, and
B.3's proof permit is the second one. Seeding the demo world on top of the shot-ready database
therefore turns a green pre-flight into `WRONG STATE` minutes before a take.

So build it separately, into its own empty database. **All four commands were RE-RUN on
2026-08-14, in this order, and the sequence finished green.** Note the `--out` on the last
line: it is not optional and §G item 13 explains why.

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg;psycopg.connect('postgresql://root@localhost:26257/defaultdb?sslmode=disable',autocommit=True).execute('CREATE DATABASE IF NOT EXISTS w_d6_demo_world')"
D:/CoackroachDBxAWS/mainline/.venv/Scripts/trappoint-migrate.exe bootstrap --dsn postgresql://root@localhost:26257/w_d6_demo_world?sslmode=disable
D:/CoackroachDBxAWS/mainline/.venv/Scripts/trappoint-migrate.exe up --dsn postgresql://root@localhost:26257/w_d6_demo_world?sslmode=disable --migrations verticals/mainline/db/migrations
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/deploy/seed_demo.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable --database w_d6_demo_world --out out/qa/demo-world-seed.json
```

> **⚠ USE A LOWERCASE DATABASE NAME.** The first attempt at this on 2026-08-14 used
> `w_D6_demo_world`. `CREATE DATABASE` folds the unquoted identifier to lower case, but the
> DSN's path segment is passed through verbatim, so `trappoint-migrate bootstrap` answered:
>
> ```
> trappoint migrate: the database refused [3D000]: database "\"w_D6_demo_world\"" does not exist
> ```
>
> The message is correct and the diagnosis is not obvious at 02:00. `seed_demo_state.py` is
> unaffected because it creates *and* selects the database itself.

`bootstrap` answers `bootstrapped: schema, schema_migration, schema_lock, schema_attestation,
genesis attestation`; `up` refuses with a named message if you skip it, and on 2026-08-14 it
ended `fingerprint 5a84e08d… (grade strong, attestation ordinal 271)`; and `seed_demo.py`
ended, verbatim:

```
  connected    w_d6_demo_world as root (SELECT current_database(); the DSN's path segment said 'defaultdb' and was overridden)
  seed         demo_world.sql       OK                 0.32s attempts=1
  seed         demo_permit.sql      OK                 0.18s attempts=1

cluster       localhost:26257/defaultdb
database      w_d6_demo_world  (as root; confirmed by SELECT current_database(), DSN path segment 'defaultdb')
permits       1 in mainline.permit, 1 is the demo permit
permit        dec0de00-0006-4000-8000-000000000001
check         dec0de00-0007-4000-8000-000000000001
state         dispositioned  open_blocking=1  gate_epoch=1  head_seq=2
obligation    severity=4 virulence=blood_major (projected)
dispositions  0
MERGE         REFUSED [23514] gate_closed_when_issued (reported)
rollback      nothing_persisted=True
VERDICT       SEEDED AND REFUSABLE
```

Exit **0**. That is STATE B: the demo permit, one open obligation, and the same refusal beat 2
films, executed and rolled back.

**What is actually in it, read back from the database on 2026-08-14** — because a verdict line
is a claim about a database and this is the database:

```
permits                    [('DEMO-PTW-0001', 'dispositioned', open_blocking=1)]
defeater_option rows       6   across TWO generations (2 distinct vocab_sha256, 3 rows each)
                             2ccb08a3…  ENERGY_SOURCE_ABSENT · MECHANISM_PRESENT_AND_VERIFIED
                                        · WORK_NOT_INTRUSIVE
                             d9c837c2…  CONTROL_PRESERVED_BY_EDIT · EDIT_OUTSIDE_BLAMED_ANCHOR
                                        · PRECURSOR_ANSWERED_ELSEWHERE
ledger_leaf                4
ledger_node                3
exposure_receipt expiries  [('dec0de00-0008-…', '2027-01-01 00:00:00+00')]
```

Three things worth pulling out of that block:

* **The permit reference is `DEMO-PTW-0001`, not `WO-88213`** — §G item 9, re-confirmed on a
  freshly built world. Frame the banner and the state, never the caption.
* **`2ccb08a3…` is the same digest STATE A holds** for the same check kind. Two independently
  seeded databases, one vocabulary generation, one digest — which is what
  `0064_defeater_option.sql` says the value means, and it now means it.
* **The receipt expires `2027-01-01`, exactly as `demo_permit.sql:416` seeds it.** That is
  §B.9's split, measured rather than read off the file: STATE B has no two-hour clock, and
  **B.4's deadline does not apply to anything filmed from this database.**

**Read the `connected` line.** The DSN's path segment says `defaultdb`; the tool overrides it
by name and then confirms with `SELECT current_database()`. That is deliberate — the committed
Cloud DSN also carries `defaultdb` in its path while the demo lives in another database, so
anything that trusts the path segment and then counts `mainline.*` gets zero and concludes the
deployment is empty. **`seed_demo.py` refuses to trust it and says so on its own face.**

**Budget real time for `up`, and do it the day before rather than on capture day.** It appends
an attestation per file by default, and that is not free. **Measured end to end on 2026-08-14:
2 297 seconds — 38 minutes 17 seconds — for 271 files**, against **96.8 s** for the proof's own
chain application inside `scripts/submission/seed_demo_state.py` over the same tree, which does
not attest per file. (The 2026-08-12 run measured "about half an hour" and 54.3 s for the same
two things; both pairs are that run's.) **Re-derive rather than plan against any of them, and
do not start this on capture day.** `--attest final` is the documented alternative if the clock
matters more than the per-file chain.

---

## C · THE BEAT-BY-BEAT TABLE

For every shot: the exact command, the seeded state it assumes, the shot itself, the one
sentence of voice-over, and the pre-committed fallback. Durations are in `SHOT-LIST.yaml`;
`capture_order` is section D.

### C.0 The four states, named once

Every row below says which one it needs. Build them in this order.

| | what it is | how it is built | **measured 2026-08-14** |
|---|---|---|---|
| **STATE A** | the proof history: permit `PTW-PROOF-1`, one open obligation, one **live** exposure receipt, the gate constraint attached, **the defeater vocabulary and the two signing credentials** | §B.3, into a database you name | **green**, `READY - 20 checks, 0 failed` |
| **STATE B** | the demo world: the demo permit `DEMO-PTW-0001`, the severity-4 precursor, the blame edge, **6 defeater options over 2 generations**, a 4-leaf ledger, and a receipt good to 2027 | §B.10, **a different database from A** | **green** — built from empty on 2026-08-14, `VERDICT SEEDED AND REFUSABLE`, 1 permit, merge refused `23514`, `nothing_persisted=True` |
| **STATE C** | the authored corpus — four labelled clause generations, `verticals/mainline/fixtures/corpus/authored/` | owner `corpus-spine-authored` | **STILL ABSENT.** `Test-Path` on that directory returns `False`; `validate_shotlist.py` reports it as not checked, which is not a pass |
| **STATE D** | nothing — a static card | authored artwork | `verticals/mainline/demo/script/cards/` **still does not exist on this tree** |

**Schema presence is not a shot.** Every table and view the beats read is present in STATE A —
check it yourself in one command, which **RAN 2026-08-14** against `w_D6_video_kit` and
printed `present` **eight** times, including the two the signature path needs:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg;c=psycopg.connect('postgresql://root@localhost:26257/w_D6_video_kit?sslmode=disable&connect_timeout=10');[print(f'{s}.{t}:','present' if c.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s',(s,t)).fetchone()[0] else 'ABSENT') for s,t in [('mainline_audit','v_disposition_coverage'),('mainline_audit','v_silence_summary'),('mainline','event_cue_embedding'),('mainline','ledger_leaf'),('mainline_ops','site_register_signal'),('mainline','patrol_run'),('mainline','defeater_option'),('mainline','signing_credential')]]"
```

```
mainline_audit.v_disposition_coverage: present
mainline_audit.v_silence_summary: present
mainline.event_cue_embedding: present
mainline.ledger_leaf: present
mainline_ops.site_register_signal: present
mainline.patrol_run: present
mainline.defeater_option: present
mainline.signing_credential: present
```

**The last two rows are new to this revision and they are the reason beat 3 changed.** A
table being present is still not a shot; what matters is whether it holds rows. On the
2026-08-14 STATE A build it does:

```
defeater_option rows: 3          — all three for the one obligation, all sharing ONE vocab_sha256
signing_credential rows: 2       — the signer and the countersigner
clearance_legal rows: 21
(blood_major, accept_residual): 0
```

The console, the custodian patrol, the changefeed and the MCP endpoint are applications on
top of that schema, and whether each is wired is what decides between a row's main path and
its fallback.

### C.1 Cold open and titles

**`s01-cold-open`** — K3 · 6 s · capture #14 · **STATE C**

* **Command** — none. This frame is the clause view; on this tree the authored fixture root is
  absent, so nothing on this machine renders it.
* **Shot** — clause, mono, on warm paper. Select `135` with the mouse; the red left-rule fades
  in. No typing. Must appear: `The seal-face high-temperature alarm shall be set at 135 °C.`
  (`CAMERA-STRINGS.yaml: clause_text_2013_onwards`; the `°` is U+00B0 — check the font).
* **VO** — "One number in a maintenance procedure. Nobody at this site knows why it's 135."
* **Fallback** — a static PNG of the same clause, typeset from `CAMERA-STRINGS.yaml`, no
  cursor move. **On this tree the fallback is the main path.**

**`s02-the-change`** — K3 · 7 s · capture #15 · **STATE C**

* **Command** — none, as above.
* **Shot** — permit branch view showing the MOC. No typing. Must appear: `MOC-2026-0413`,
  `135 → 150`, `control_delta: weaken` (`moc_ref`, `moc_diff_line`, `moc_delta_badge`). The
  arrow is U+2192, not `->`.
* **VO** — "An engineer raised it to 150 — the manufacturer's number. Defensible. Approved."
* **Fallback** — the same diff typeset as a card from the three camera strings above.

**`s03-title`** — K0 · 5 s · capture #22 · **STATE D**

* **Command** — none. `SHOT-LIST.yaml` names `script/cards/title.svg` as the artefact and
  **that directory does not exist**, so the card is a capture-day asset somebody has to author
  before the shoot.
* **Shot** — static card, no motion, no typing. Must appear:
  `MAINLINE — institutional safety memory as a version-controlled repository` (`title_card`;
  the em dash is U+2014).
* **VO** — "MAINLINE: institutional safety memory as a version-controlled repository, on CockroachDB."
* **Fallback** — none needed once the card exists; it has no runtime dependency.

**`s04-architecture`** — K0 · 5 s · capture #23 · **STATE D**

* **Command** — none; same missing directory as `s03`.
* **Shot** — static card, five elements, no animation.
* **VO** — "Commits are written by incidents. Every clause points at the event that wrote it."
* **Fallback** — **scope-cut ladder step 2 removes this shot entirely.** `s03` carries the
  thesis, and if the card is not authored in time this is the shot to lose.

### C.2 Beat 1 — the clause remembers · **RE-MEASURED 2026-08-14, AND IT STILL HAS NO SURFACE**

**This section was written before the signature path worked, so it was re-measured rather than
re-read. The answer did not change, and it is the one finding on this page that a reader
should be sorriest about.** The working signature path is beat 3's; it gave beat 1 nothing.

Four commands, all run on 2026-08-14, all against this tree:

```bash
# 1 — is there a `mainline` executable?
ls D:/CoackroachDBxAWS/mainline/.venv/Scripts/*.exe
```

The console scripts installed there are `mainline-boundary`, `mainline-gate`,
`mainline-mutation`, `mainline-steward`, the `trappoint-*` family, and the ordinary tool
binaries. **There is no `mainline` executable.** `mainline blame STD-ISO-006 --clause 9.2.1`
is a string in `CAMERA-STRINGS.yaml`, not a program, and typing it on camera produces a
shell error.

```bash
# 2 — is the authored corpus there?          -> False
Test-Path verticals/mainline/fixtures/corpus/authored
# 3 — is there a tape to replay instead?     -> ABSENT (no evidence/demo-run-* exists)
Get-ChildItem evidence -Filter "demo-run-*"
# 4 — does a blame surface exist anywhere?   -> no match
Get-ChildItem -Recurse -Filter "*.py" scripts | Select-String "def .*blame|blame_walk"
```

`verticals/mainline/fixtures/corpus/` exists and holds `answer-key/`, `cache/`,
`moc-stream/`, `reflow/`, `rendered/` and `templates/` — **and no `authored/`**. That is the
directory the four-generation spine lives in.

> **BEAT 1 HAS NEITHER A MAIN PATH NOR ITS WRITTEN FALLBACK, AND THAT IS STILL TRUE TWO
> WAVES LATER.** Every `s01`, `s02`, `s05`, `s06` and `s07` frame below is a *typeset card*
> built by hand from `CAMERA-STRINGS.yaml`. Four of those five rows already say so in their
> `fallback` field in `SHOT-LIST.yaml`; that field is now the main path, not the contingency.
> **Schedule the typesetting as work.** It is roughly a third of the film's running time —
> 39 s of 171 s — and nobody has started it. Owners: `corpus-spine-authored`, and whoever
> owns K3's surface.

The one consolation is that the claim survives the medium. `s06`'s payload is a *string*, and
the string is asserted byte-equal across four files by `validate_shotlist.py` — so a typeset
card carrying `Lowered 150 → 135 after seal fire INC-2013-044 — two contractors burned` is
carrying exactly what a rendered UI would have carried. What is lost is the *walk*, and the
voice-over never claims one.

**`s05-beat1-blame-walk`** — K3 · 10 s · capture #4 · **STATE C**

* **Command** — none on this machine, and **do not type the string**. The on-screen text is
  `mainline blame STD-ISO-006 --clause 9.2.1` (`CAMERA-STRINGS.yaml: blame_command`, verbatim),
  shown at a `mainline_demo=>` prompt — but there is no `mainline` executable (§C.2), so a
  live keystroke produces a shell error, not a walk. Typeset the prompt and the command as
  part of the card.
* **Shot** — four nodes walking `2011 → 2013 → 2016 → 2019`, one per line.
* **VO** — "So we ask the clause where it came from."
* **Fallback — THIS IS THE MAIN PATH** — a typeset replay of the four nodes from
  `CAMERA-STRINGS.yaml: spine.labels` and `spine.dates`, with the VO unchanged. The *written*
  fallback (a tape from `evidence/demo-run-<ts>/`) requires an artefact that does not exist —
  re-checked 2026-08-14.

**`s06-beat1-commit-message`** — K3 · 11 s · capture #5 · **STATE C**

* **Command** — none. Nothing is typed in this shot.
* **Shot** — zoom on the 2013 node, then hold in silence. Must appear:
  `Lowered 150 → 135 after seal fire INC-2013-044 — two contractors burned`
  (`commit_message_2013`, asserted **byte-equal** across four files; U+2192 and U+2014 are
  load-bearing), plus `D. Okonjo` and `2013-08-04`. **No commit SHA is shown or spoken, ever.**
* **VO** — "2013. A gland seal fire. Two contractors burned. The alarm gave ninety seconds; 135 would have given six minutes." · `·hold`
* **Fallback** — a still frame of the same node typeset from the camera strings; **keep the
  silence**.

**`s07-beat1-identity-survival`** — K3 · 7 s · capture #16 · **STATE C**

* **Command** — none.
* **Shot** — blame ribbon; the 2016 and 2019 nodes light. Must appear:
  `7.3 → 5.2.1 → 9.2.1 · doc move` (`ribbon_caption`), with one `clause_uuid` under all three
  labels.
* **VO** — "Retypeset 2016. Split 2019. The clause kept its identity, so the blame survived."
* **Fallback** — **scope-cut ladder step 1 removes this shot.** `s06`'s VO absorbs the claim.

### C.3 Beat 2 — the refusal and the bypass · NEVER CUT

Every row here is `never_cut: true`. Section E says what that forbids. **This is the only
footage in the film a skeptic cannot explain away as an application behaving itself**, and it
is the beat with the most verified commands.

**`s08-beat2-merge-refused`** — K1 · 7 s · capture #3 · **STATE B** (console) or **STATE A**
(terminal)

* **Command** — console: the merge button on permit `WO-88213`. Terminal equivalent, verify
  only, nothing persisted:

  ```bash
  D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/deploy/seed_demo.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable --database w_demo_world --check
  ```

  **RAN 2026-08-12** against the scratch database, printing
  `MERGE  REFUSED [23514] gate_closed_when_issued (reported)` and
  `rollback  nothing_persisted=True`. That run also answered `VERDICT WRONG STATE`, because
  the scratch database held two permits — see §B.10. The refusal line is the frame; the verdict
  line is the pre-flight, and on a database built the §B.10 way only one permit stands.
* **Shot** — the permit, hot work on P-4104. Click **merge** once. Must appear:
  `MERGE BLOCKED · 1 undispositioned precursor · gate_closed_when_issued`
  (`CAMERA-STRINGS.yaml: banners.merge_blocked`).
* **The permit reference on screen will not be `WO-88213`.** Measured 2026-08-12: the seeded
  demo world holds exactly one permit and its `external_ref` reads **`DEMO-PTW-0001`**.
  `WO-88213` is a `CAMERA-STRINGS.yaml` string belonging to the authored corpus, which has not
  landed. Frame the banner and the state, not the reference — or wait for the corpus. Do not
  retype the reference to match the script; a caption that disagrees with the database is the
  one thing this film cannot afford.
* **VO** — "Today's permit relies on that clause. The supervisor clicks merge."
* **Fallback** — run the same transition from the terminal; the red bar becomes the SQLSTATE
  line — `seed_demo_state.py --camera`, block `s09`.

**`s09-beat2-constraint`** — K1 · 7 s · capture #2 · **STATE A**

* **Command** — `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --camera --database <your database>`, then frame the `s09` block. **RAN 2026-08-14** against `w_D6_video_kit`.
* **Assumes** — B.3 green, including the `exposure receipt live` row; the command re-verifies
  and refuses to print if it is not.
* **Shot** — terminal, full screen, the four labelled lines of the `s09` block. Must appear:
  `SQLSTATE: 23514` and `gate_closed_when_issued` (`REFUSAL-STRINGS.yaml` R1 `terminal_match`
  and `exhibit`). **See the note below this beat about `client_render`.**
* **VO** — "Refused — not by a warning. By a CHECK constraint: gate_closed_when_issued."
* **Fallback** — **none. If this cannot be filmed there is no submission; K1 carries no
  reduction.**

**`s10-beat2-bypass-admin-update`** — K1 · 8 s · capture #1 · **STATE A**

* **Command** — paste from *your* ON-CAMERA SUBSTITUTIONS block, in a `psql`-style shell
  against your STATE A database as root: the `UPDATE mainline.permit SET state = 'merged' WHERE
  permit_id = '…';` and then the `SELECT trappoint.explain_refusal('permit', '…',
  'gate_closed_when_issued');`. Both statements **RAN 2026-08-14** inside `--camera`, each
  rolled back.
* **Assumes** — STATE A, untouched by `s12`.
* **Shot** — one terminal, cluster admin, the application nowhere in the path. Must appear:
  `ERROR: failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR
  (open_blocking = 0:::INT8))`, then `SQLSTATE: 23514`, then `constraint:
  gate_closed_when_issued` from `explain_refusal`.
* **VO** — "Cluster admin. Raw SQL. Our application bypassed entirely. The database still refuses."
* **Fallback** — **none. This is the most valuable footage in the video.**

**`s11-beat2-bypass-append-only`** — K1 · 5 s · capture #6 · **STATE A**

* **Command** — paste `DELETE FROM mainline.blocking_check WHERE permit_id = '…';` from the
  substitutions block. **RAN 2026-08-14** inside `--camera`, rolled back.
* **Shot** — same admin session, one statement. Must appear:
  `MAINLINE: this table is append-only; write a new row` and `SQLSTATE: P0001`
  (`REFUSAL-STRINGS.yaml` R2 `message`).
* **VO** — "The obligation is append-only. It cannot be deleted."
* **Fallback** — **none. Two of the three bypass statements are the floor for this beat.**

**`s12-beat2-bypass-drop-constraint`** — K6 · 10 s · capture #7 · **STATE A, and it ends it**

* **Command** — type `ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued;` on
  camera. **This succeeds, and that is the shot.** Deliberately **not run** while this page was
  written: `seed_demo_state.py` verifies the constraint by asking the catalogue, never by
  dropping it.
* **Assumes** — STATE A, and it destroys it. The custodian patrol (K6) must be wired for the
  second half.
* **Shot** — the `ALTER TABLE` acknowledgement (R3 `outcome`), then the patrol's attested leaf
  `gate_definition_changed` with the prior triggerdef digest (R3b `terminal_match`), shown at
  4× as an inset.
* **VO** — "An admin can drop the constraint. What they cannot do is drop it unobserved."
* **Fallback** — **if the K6 custodian patrol is not wired, drop this statement and end the
  beat at `s11`.** The beat is never cut; only its third statement is.
* **After the take** — run B.3 in full. Do not re-add the constraint by hand: a hand-made
  constraint is not the migration's constraint, and the next take would film a different
  object. `--verify-only` will show four failed rows until you rebuild.

**Two things about this beat that are measured, and that you must know before rolling.**

*The `client_render` string in `REFUSAL-STRINGS.yaml` is not what the shipped client prints.*
The file records `GateRefused(constraint='gate_closed_when_issued', sqlstate='23514')`. The
client actually renders `GateRefused("23514 gate_closed_when_issued: failed to satisfy CHECK
constraint (…)")` — re-measured 2026-08-14 by constructing one and printing it (§G item 5 carries the transcript),
whose constructor calls `super().__init__(f"{sqlstate} {constraint}: {message}")`. Both carry
the SQLSTATE and the constraint name, so the voice-over is true either way.
`seed_demo_state.py --camera` sidesteps the divergence by printing the fields on their own
labelled lines, which is also what makes them legible. **Do not compose a shot around the
`client_render` string in the YAML.** Neither file is this kit's to edit; the divergence is
raised to the demo owner in §G.

*Beat 2 is filmed from STATE A, and STATE A is the database B.4 is about.* The refusals do not
care whether the receipt is alive. `s13` onwards does.

### C.4 Beat 3 — the disposition ladder · **THE BEAT THE COMPLETION WAVE CHANGED**

**Read this before you schedule beat 3. It moved, and it moved in the good direction.**

Until 2026-08-14 the sentence *"a judge chooses a defeater and signs"* described a screen
nobody could reach: `mainline.defeater_option` held no rows, so there was nothing to choose
from, and both signing paths in the demo API bound `sha256(b"defeater-vocab")` — a constant —
instead of the digest of the option set. **Both are fixed.** Measured on 2026-08-14 against a
freshly seeded STATE A:

```
defeater_option rows: 3
  63495c7d-…  ENERGY_SOURCE_ABSENT             "Which stored-energy source was surveyed and found
                                                absent within this permit's boundary, and by whom?"
  63495c7d-…  MECHANISM_PRESENT_AND_VERIFIED   "Which isolation point was locked, and who verified
                                                it at zero?"
  63495c7d-…  WORK_NOT_INTRUSIVE               "Which task in this permit's scope was assessed as
                                                non-intrusive, and against which method statement?"
  — all three rows share ONE vocab_sha256, which is what the digest is supposed to mean
signing_credential rows: 2       — the signer and the countersigner, resolved not derived
```

`mainline.defeater_option` is seeded in three places, each aggregating the digest from its own
rows rather than binding a literal: `demo_permit.sql`, `demo_world.sql` and
`scripts/proof/gate_refusal.py`. The four-beat proof reaches its **admission** because of it —
`evidence/gate-refusal/proof-20260814T032418Z.json` records `disposition.signed: true`,
`countersigned_count_after: 1`, then `ADMISSION ADMITTED [00000]` (§B.8).

**What that buys the film, and what it does not.** It buys a *terminal-checkable* beat 3: the
vocabulary, the digest and the admission are all readable with `psycopg` on a database you
built a minute ago, so `s13`–`s15` are no longer console-only. It does **not** buy a console.
The modal, the greyed lattice cells and the countersigner field appearing unprompted are still
UI that has to exist on the day.

**And it creates one sentence that must not be said** — MUST-NOT-CLAIM family 14. The database
will accept a `defeater_code` that was never offered: `0066_disposition.sql` carries only
`CHECK (defeater_code <> '')` and **no foreign key onto `mainline.defeater_option`**. The
refusal lives in `mainline_demo_api.defeaters.resolve_defeater_vocabulary`, which raises rather
than falling back. *"The database refuses a defeater that was never offered"* is false. *"The
vocabulary and its digest are the database's, and the application refuses to sign without
them"* is true and is the sentence to use.

**`s13-beat3-lattice-refusal`** — K5 · 9 s · capture #8 · **STATE A or B, receipt LIVE**

* **Command** — the disposition modal (console). The lattice inset's claim is checkable from
  the terminal in one line, which **RAN 2026-08-14** against `w_D6_video_kit` and printed
  `clearance_legal rows: 21` then `(blood_major, accept_residual): 0`:

  ```bash
  D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg;c=psycopg.connect('postgresql://root@localhost:26257/w_D6_video_kit?sslmode=disable&connect_timeout=10');print('clearance_legal rows:', c.execute('SELECT count(*) FROM mainline.clearance_legal').fetchone()[0]);print('(blood_major, accept_residual):', c.execute('SELECT count(*) FROM mainline.clearance_legal WHERE virulence = %s AND kind = %s', ('blood_major','accept_residual')).fetchone()[0])"
  ```

* **Assumes** — a live exposure receipt (B.4). Without one the signature has no `(receipt_id,
  check_id)` pair to cite and the modal cannot reach the lattice at all.
* **Shot** — signer picks `accept_residual` against a `blood_major` ancestry, submits. Must
  appear: `SQLSTATE: 23503`, constraint `fk_clearance` (R4). The lattice inset shows the three
  deliberately absent cells greyed with their reasons.
* **VO** — "Accept the residual risk? There's no such verdict — no row, and a foreign key says so."
* **Fallback** — **none. This is the entry's single best thirty seconds and is never cut.**

`mainline.clearance_legal` holds **21** rows and the pair `(blood_major, accept_residual)` is
**absent** — both re-measured 2026-08-14 by the command above, and both unchanged from
2026-08-12. That absence is what `s13` films. It is not a stricter row; it is no row.

**`s14-beat3-disposition-signed`** — K5 · 8 s · capture #9 · **STATE A or B, receipt LIVE**

* **Command** — console: switch the kind to `mitigated`; the countersigner field **appears by
  itself** because `req_second_signer` is projected true. Fill the rationale past 120
  characters. Sign, then countersign. Declared, not run here — this path needs the console and
  an enrolled authenticator.
* **Assumes** — a live exposure receipt; `0066_disposition.sql:160` binds the signature to the
  pair `(receipt_id, check_id)`. **And, new on 2026-08-14, a non-empty
  `mainline.defeater_option` for that check** — the resolver raises rather than defaulting, so
  an unseeded vocabulary now fails loudly instead of signing a constant. `--verify-only` does
  not yet carry a row for it; §B.3's build does, implicitly, because the seed writes it.
* **Shot** — the countersigner field appearing unprompted, then
  `deliberation 00:47 · measured, never thresholded` (`banners.deliberation`). R5's
  `needs_second_signer` is the constraint doing the work.
* **VO** — "Severity four forces a compensating control and a second signature. We measure deliberation. We never accuse."
* **Fallback — and this one is newly available** — if the console is not ready, the *substance*
  of `s14` is now filmable from the terminal: show the three `defeater_option` rows and their
  single shared `vocab_sha256`, then the proof's `disposition` block (`signed: true`,
  `countersigned_count_after: 1`) from `evidence/gate-refusal/proof-20260814T032418Z.json`.
  That is a weaker frame and a true one. If WebAuthn is not enrolled, the console path degrades
  to the OIDC + signed-envelope route, and the honesty card says so in its NOT-BUILT-YET column.

**`s15-beat3-merge-succeeds`** — K5 · 5 s · capture #10 · **STATE A or B, after `s14`**

* **Command** — console: click merge again. It goes through. Declared, not run here.
* **Assumes** — a signed disposition exists, so `open_blocking` has fallen to 0. **This
  consumes the state**: a merged permit cannot be refused again, so budget a rebuild (B.3) per
  attempt.
* **Shot** — a `merge_record` row with its `clearance_digest`.
* **VO** — "Now it merges, carrying a signed record of who overrode what."
* **Fallback** — terminal rendering of the same `merge_record` row.

### C.5 Beat 4 — the diachronic flip

**`s16-beat4-register-gains-activity`** — K6 · 5 s · capture #11 · **STATE B**

* **Command** — none typed on camera; the register write arrives from the changefeed. Declared,
  not run here.
* **Shot** — split screen. Left: the site activity register gains one row. Right: the permit,
  untouched, cursor parked. **Nobody types.**
* **VO** — "Then the site register gains an activity. Nobody touches the screen."
* **Fallback** — insert the register row into `mainline_ops.site_register_signal` from the
  terminal in the same shot; the point survives.

**`s17-beat4-lease-revoked`** — K5 · 6 s · capture #12 · **STATE B**

* **Command** — none typed. The retro-block attempts to attach to the issued permit and the
  database refuses. Declared, not run here.
* **Shot** — `DEFEATER LEASE REVOKED · predicate falsified by site register`
  (`banners.lease_revoked`), then `MAINLINE: precursor arrived after issue — use the post-issue
  recall path` and `SQLSTATE: P0001`, raised by `mainline.fn_check_materialised` (R6).
  **`23503` is NOT filmed here** — see ADR 0030; on this path it cannot occur, and filming a
  SQLSTATE that cannot occur is the exact overclaim this project punishes in others.
* **VO** — "He signed it away only while this stayed true."
* **Fallback** — if the changefeed is not wired, fire the register write in the same
  transaction and film the identical `P0001`. The mechanism is unchanged.

**`s18-beat4-suspend-and-fork`** — K5 · 4 s · capture #13 · **STATE B**

* **Command** — none typed. The route behind it is `POST /v1/permits/{permit_id}/suspend`,
  confirmed present again on 2026-08-14 among the API's 17 routes — `grep -c 'Route("' verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py` returns `17`, and `POST /v1/permits/{permit_id}/suspend -> suspend_permit` is one of them.
* **Shot** — `PERMIT SUSPENDED · child forked` (`banners.permit_suspended`) and the child
  permit's id.
* **VO** — "The permit suspends itself and forks a child."
* **Fallback** — terminal rendering of the parent/child permit rows.

### C.6 Beat 5 — hand it to an auditor

**`s19-beat5-mcp-connect`** — K6 · 8 s · capture #17 · **Cloud, not local**

* **Command** — in Claude Code: `/mcp`, then prompt 1. The connection details are in
  `verticals/mainline/demo/judge/MCP-CONFIG.md`. Declared, not run here.
* **Shot** — `cockroachdb-cloud: connected`, then a `select_query` against
  `mainline_audit.v_disposition_coverage` showing surfaced / dispositioned / orphans with
  `ancestry_complete`.
* **VO** — "Hand it to an auditor. CockroachDB's own managed MCP — read-only, not ours."
* **Fallback** — if publishing a key is forbidden, record the MCP session against the
  throwaway `mainline-verify` cluster plus our own read-only endpoints, and `VERIFY.md` states
  exactly why.

**`s20-beat5-explain`** — K4 · 8 s · capture #18 · **STATE A (the local fallback is verified)**

* **Command** — prompt 2 → `explain_query` over MCP. The identical `EXPLAIN` runs locally, and **RAN 2026-08-14** against `w_D6_video_kit`. A 1024-float literal cannot be typed, so build it:

  ```bash
  PYTHONIOENCODING=utf-8 D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe - <<'PY'
  import psycopg
  vec = "[" + ",".join(["0.01"] * 1024) + "]"
  conn = psycopg.connect("postgresql://root@localhost:26257/w_D6_video_kit?sslmode=disable&connect_timeout=10")
  plan = conn.execute(
      "EXPLAIN SELECT cue_id FROM mainline.event_cue_embedding@cue_scoped_idx "
      "WHERE site_id = '00000000-0000-0000-0000-000000000001'::UUID "
      "AND scope_id = '00000000-0000-0000-0000-000000000002'::UUID "
      "AND facet = 'lesson' "
      "ORDER BY emb <=> '" + vec + "'::VECTOR LIMIT 5"
  ).fetchall()
  print("\n".join(r[0] for r in plan))
  PY
  ```

  On 2026-08-14 it printed the plan tree ending, verbatim:

  ```
  └── • lookup join
      │ table: event_cue_embedding@event_cue_embedding_pk
      │ equality: (cue_id) = (cue_id)
      │ equality cols are key
      │
      └── • vector search
            table: event_cue_embedding@cue_scoped_idx
            target count: 5
            prefix spans: [/'00000000-0000-0000-0000-000000000001'/'00000000-0000-0000-0000-000000000002'/'lesson' - /'00000000-0000-0000-0000-000000000001'/'00000000-0000-0000-0000-000000000002'/'lesson']
  ```

  **Three things about that command are not decoration.** The index hint `@cue_scoped_idx` is
  mandatory — the index is `cue_scoped_idx (site_id, scope_id, facet, emb vector_cosine_ops)`
  and at demo scale the optimizer does not choose it unhinted. Every prefix column takes a
  **single value**, which is what produces a non-empty `prefix spans`. And
  `PYTHONIOENCODING=utf-8` is required: the plan tree is drawn with box characters, and
  without it Python raised `UnicodeEncodeError: 'charmap' codec can't encode character
  '\u2502'` on this console. **Run this one in Git Bash or the SQL shell** — PowerShell parses
  the `<=>` operator itself and refuses the line.
* **Shot** — hold on the **unedited** fragment containing `vector search` and a non-empty
  `prefix spans` (`REFUSAL-STRINGS.yaml: explain_fragment`).
* **VO** — "Because everyone asks whether the vector search is real — C-SPANN, on the named index." · `·hold`
* **Fallback** — run that `EXPLAIN` in the SQL shell; the fragment is identical, and it is the
  one printed above.

**`s21-beat5-silence`** — K4 · 6 s · capture #19 · **a database with a recall run in it**

* **Command** — prompt 3, *what did you decline to surface?* The view exists locally and
  **RAN 2026-08-14**, unchanged: `SELECT count(*) FROM mainline_audit.v_silence_summary`
  answered **0** on a freshly seeded STATE A, because nothing has run a recall against it.
  **A shot of an empty view is not this shot** — film it against a database that has a recall
  run, or the Cloud demo.
* **Shot** — `mainline_audit.v_silence_summary`: candidates by reason with mean score, mean
  threshold and nearest miss.
* **VO** — "Then the question nobody else answers: what did you not tell me?"
* **Fallback** — the same view over the SQL shell if the MCP key is withheld — with the same
  caveat about rows.

### C.7 Close

**`s22-readiness-strip`** — K6 · 5 s · capture #20 · **STATE D**

* **Command** — none; four static tiles.
* **Shot** — an RLS policy denying a cross-site read; the single-tenant boundary;
  `ccloud audit list -o json` hashed into the ledger; the CloudWatch alarm on gate-bypass
  attempts.
* **VO** — "Single tenant. Row-level security. CockroachDB's audit log hashed into our ledger."
* **Fallback** — **drop the CloudWatch tile.** The alarms are declared in Terraform and have
  not been created, so unless the apply has happened before your shoot there is nothing to
  film; the remaining three tiles stand alone. §0.3 item 3 has the wording.

**`s23-honesty-card`** — K0 · 8 s · capture #21 · **STATE D, and it is blocked today**

* **Command** — `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe verticals/mainline/demo/honesty/gen_card.py --check`. **RAN 2026-08-14**, exit **2**, and it **refused again**:
  `gen_card: verticals/mainline/fixtures/corpus/corpus.lock.json does not exist. It is produced
  by the corpus-freeze-load worker (corpusgen freeze).`
* **Assumes** — a frozen corpus lock and a real probe attestation. Neither is on this tree.
  The committed `verticals/mainline/demo/honesty/card.html` therefore carries its own
  full-width banner: **`NOT FOR CAMERA — built from a fixture (corpus lock). Regenerate against
  the frozen corpus and a real probe run before capture.`** That banner is driven by a marker
  *inside the data*, so a rehearsal build cannot be smuggled onto camera by leaving a flag off.
* **Shot** — the four columns — REAL / SYNTHETIC / STAGED / NOT BUILT YET — with M14 SHEPARD
  named in the fourth.
* **VO** — "Live: database in Singapore, inference in Sydney. Operator and incidents are synthetic."
* **Fallback** — **the card ships in every cut, so this shot cannot be dropped.** Until the
  lock lands, typeset the four columns from `verticals/mainline/demo/DEMO-HONESTY.md`, which
  holds every *sentence* and — by design — **no numbers at all**. A card with the sentences and
  without the counts is honest; the fixture-built card is not, and it says so itself.

**`s24-rubber-stamp`** — K0 · 5 s · capture #24 · **STATE D**

* **Command** — none. Same generator, same blocker as `s23`; the limit is a sentence, not a
  count, so it can be typeset directly.
* **Shot** — the limit card, one sentence, full screen.
* **VO** — "The honest limit: nothing separates a considered disposition from a rubber stamp. We log our silence."
* **Fallback** — **none. Naming the limit is the cheapest credibility in the film**, and at
  3.20 w/s it is also the line to rehearse first (§0.2).

**`s25-end-card`** — K0 · 6 s · capture #25 · **STATE D**

* **Command** — read the URLs out of `docs/submission/SUBMISSION.json`. **RAN 2026-08-14**: `repo_url = https://github.com/Shaugato/mainline`, `demo_url = UNRESOLVED`, `video_url = UNRESOLVED`. `check_submission_ready.py`, same day, confirms `repository is public PUBLIC [gh repo view Shaugato/mainline --json visibility, asked live]` and still lists `demo URL` and `video URL` as unresolved rows.
* **Shot** — repository, demo URL, the `claude mcp add` one-liner, and the licence triple
  (Apache-2.0 · FSL-1.1-ALv2 · CC-BY-4.0).
* **VO** — "Repo, demo, read-only endpoint. Verify it yourself."
* **Fallback** — **film it last.** If `demo_url` still reads `UNRESOLVED`, the card carries the
  repository and the MCP line only and the VO drops one word (§0.3).

**The watermark is on every frame:** `SYNTHETIC CORPUS · KESTREL RESOURCES IS FICTIONAL`
(`SHOT-LIST.yaml: watermark`). Captions are burned in — judges watch muted.

---

## D · CAPTURE ORDER — worst first, three takes each

Shoot in `capture_order`, not in story order. The list is in `SHOT-LIST.yaml`; the reason it
starts where it does is that the hardest, most valuable and least recoverable shot is the
raw-SQL bypass, and discovering a problem with it at the end of a shooting day is how a
submission misses a deadline.

The first six, in order: `s10-beat2-bypass-admin-update`, `s09-beat2-constraint`,
`s08-beat2-merge-refused`, `s05-beat1-blame-walk`, `s06-beat1-commit-message`,
`s11-beat2-bypass-append-only`. The order after that is in the YAML.

**Three takes of every shot, always, even when the first one is clean.** Not perfectionism:
an editor with one take has no cut point, and beat 2's value is in the pacing between the
refusal and the bypass.

**Between takes** run `--verify-only` (B.6) or the one-liner in B.4. **After `s12`** run the
full rebuild (B.3).

Two shots need a fresh database rather than a fresh take: `s12` (it drops the constraint) and
`s15` (it merges the permit, and a merged permit cannot be refused again). Budget a rebuild
minute for each attempt at those two — and remember that every rebuild **resets the B.4
deadline**, which is the one good thing about it.

**A shooting day fits inside one receipt window only if you plan it that way.** The window is
two hours; beat 2 alone is five shots at three takes. Seed, shoot beats 2 and 3, re-seed, then
shoot the rest.

---

## E · THE SCOPE-CUT LADDER, AND THE ONE THING IT MAY NOT REACH

The ladder is pre-committed in `SHOT-LIST.yaml` under `scope_cut_ladder`, executed top-down,
so that it is never a 02:00 judgement call:

1. Cut `s07-beat1-identity-survival` — the reflow claim moves to `s06`'s VO and to the
   repository.
2. Cut `s04-architecture` — the thesis survives in `s03`.
3. Trim `s01-cold-open` — the hold on the setpoint shortens; the hook still lands.
4. Switch to `SHOT-LIST-MWS.yaml` — the Minimum Winnable Submission, four beats, written on
   D-7 and not on D-1. It sums to **158 s** over **22 shots** and **273** spoken words,
   re-derived 2026-08-14 by `validate_shotlist.py` (`mws.total_s 158`, `mws.shots 22`,
   `mws.vo_words 273`, `mws.headroom_s 22`).

**One thing the ladder must NOT be used for on this tree.** Beat 1 has no surface (§C.2), so
its shots are typeset cards somebody has to author. It is tempting to reach for ladder steps 1
and 3 — both of which cut beat 1 shots — as a way of not doing that work. **Steps 1 and 3
recover 10 seconds of a 9-second headroom problem you do not have.** The cut is at 171 s
against a 180 s rule; there is nothing to recover. Use the ladder for *time*, and schedule the
typesetting as *work*.

**Beat 2 — `s08` through `s12` — is never cut for time.** Every row carries
`never_cut: true`, and the validator asserts that the ladder cannot reach a `never_cut`
shot. If beat 2 has to shrink, it shrinks by dropping the *third statement* (`s12`'s
`DROP CONSTRAINT`) and ending at `s11`, which is a smaller shot and not a smaller beat.
`s13-beat3-lattice-refusal` and `s17-beat4-lease-revoked` are also `never_cut`.

The reason is not sentimental. Beat 2 is the only footage in the film that a skeptic cannot
explain away as an application behaving itself: it runs as cluster admin, in raw SQL, with
the application bypassed entirely, and the database still refuses. Everything else in the
video is a claim about a product. That beat is a claim about a *database*, and it is the one
the repository can prove.

---

## F · Before you speak

Read [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) once, the morning of the shoot. **Fourteen**
families as of 2026-08-14, each beside the true sentence. The seven most likely to slip out on
camera:

* Not "everything runs in Australia" — inference is in Sydney, the database is in Singapore. <!-- prose-hygiene: quoting -->
* Not "it refuses in milliseconds" — every timing here is local Docker on one laptop. <!-- prose-hygiene: quoting -->
* Not "a real incident" — the corpus, the operator, the site and the incident are authored.
* Not "the conformance suite passes", and not that it has ever been demonstrated — it has not;
  two cases are demonstrated instead by `scripts/proof/gate_refusal.py`.
* Not "the deployed demo is proven" and not "the demo is live" — **both acceptance artefacts
  read `PROVEN` as of 2026-08-14 and both were taken over a local emulator socket**, with
  `target_is_local_emulator: true`. There is no public origin; `demo_url` is `UNRESOLVED`.
  Read the files on the day, and read `target_provenance`, not `mode_description`.
* Not "every signature pins the alternatives the signer declined" as a claim about the past —
  until 2026-08-14 both signing paths bound `sha256(b"defeater-vocab")`, and the captured
  Cloud bundle still carries that value.
* Not "the database refuses a defeater code that was never offered" — there is no foreign key;
  the application refuses.

And the one that is easiest to get wrong because it sounds modest: the database does **not**
stop a cluster admin from dropping the gate. `s12` films the drop succeeding. The claim is
tamper-*evidence* — the drop becomes an attested leaf — and `REFUSAL-STRINGS.yaml` R3 says so
in the file the camera reads from.

---

## G · What this kit found while it was being written

Recorded rather than repaired: none of these files belongs to this kit. **Every item below was
re-measured on 2026-08-14 on the pinned local node**, and the verdict is noted against each —
because a findings list nobody re-runs is a findings list that quietly becomes fiction.

1. **STILL OPEN · `verticals/mainline/demo/honesty/card.html` is marked NOT FOR CAMERA and
   cannot be regenerated on this tree.** `gen_card.py --check`, RAN 2026-08-14, exits **2**:
   `gen_card: verticals/mainline/fixtures/corpus/corpus.lock.json does not exist. It is
   produced by the corpus-freeze-load worker (corpusgen freeze). Pass --allow-fixtures for a
   clearly-marked stand-in card, or point --lock at the real artefact.` Owner:
   `corpus-freeze-load`. Until it lands, `s23` and `s24` have no generated card, and the
   fallback in §C.7 is the only honest frame.
2. **STILL OPEN · `verticals/mainline/demo/script/cards/` does not exist** — `Test-Path`
   returns `False` on 2026-08-14 — so the three static cards (`title.svg`,
   `architecture.svg`, `end.svg`) named as evidence artefacts in `SHOT-LIST.yaml` are
   unauthored. They are capture-day assets with a lead time.
3. **STILL OPEN, AND THE MOST EXPENSIVE ONE · beat 1 has no surface.** Re-measured
   2026-08-14, four ways (§C.2): there is no `mainline` executable in `.venv/Scripts/`; the
   authored corpus root `verticals/mainline/fixtures/corpus/authored/` is absent (the shot-list
   validator reports it as unchecked, which it prints as *not a pass*); no
   `evidence/demo-run-*` tape exists; and no blame surface exists anywhere under `scripts/`.
   **This did not move when the signature path started working** — that wave gave beat 3 a
   surface and beat 1 nothing. It is 39 s of a 171 s film. Owners: `corpus-spine-authored` and
   whoever owns K3's surface.
4. **`seed_demo.py` and `seed_demo_state.py` cannot seed the same database.** Measured:
   applying the demo world on top of the proof history produces
   `VERDICT WRONG STATE — 2 permits stand in mainline.permit, expected exactly 1`, even though
   both seed files applied and the demo permit's merge was refused correctly. §B.10 is the
   two-database procedure. This is a note for the demo owner, not a defect in either script.
5. **STILL OPEN · `REFUSAL-STRINGS.yaml` R1 `client_render` does not match the shipped
   client.** Re-measured 2026-08-14 by constructing one and printing it. The YAML records
   `GateRefused(constraint='gate_closed_when_issued', sqlstate='23514')`. The class actually
   renders:

   ```
   repr : GateRefused("23514 gate_closed_when_issued: failed to satisfy CHECK constraint
          ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))")
   ```

   because `TrappointError.__init__` receives `f"{sqlstate} {constraint}: {message}"`. Both
   carry the SQLSTATE and the constraint name, so the voice-over is true either way, and
   `seed_demo_state.py --camera` sidesteps the divergence by printing the fields on labelled
   lines. **`SHOT-LIST.yaml:s09` still quotes the YAML's string in its `on_screen` field**, and
   that field is documentation of intent rather than a tape-match target — but the note in §C.3
   is the operative instruction: do not compose a shot around it. Either the YAML or the client
   should move; neither is this document's to change.
6. **`REFUSAL-STRINGS.yaml` R1 `server_expression_rendering.verified: false` can be set true.**
   The exact rendering is
   `failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))`,
   printed again today on CockroachDB CCL v26.2.5. It should still never be a tape match
   target — a type annotation is a platform detail — but it is no longer unmeasured.
7. **STILL OPEN · `mainline_audit.v_silence_summary` is empty on a freshly seeded local
   database** — 0 rows again on 2026-08-14, because no recall run has touched it. `s21` needs a
   database that has one.
8. **STILL OPEN, AND NOW TIMED END TO END · `trappoint migrate up` is far slower than the
   proof's own chain application.** Re-measured 2026-08-14 over the same 271 files, on the
   same node, in the same hour: **`trappoint-migrate up` took 2 297 s (38 m 17 s)** with the
   default per-file attestation, ending `fingerprint 5a84e08d… (grade strong, attestation
   ordinal 271)`; **`seed_demo_state.py` took 96.8 s** because it does not attest per file.
   A ratio of about **24×**. (The 2026-08-12 pair was "about half an hour" and 54.3 s.) Not a
   defect — they do different work, and the attestation chain is the point of the slower one —
   but it is a scheduling fact for §B.10 and it belongs to the migration runner's owner.
9. **STILL OPEN · the film's permit reference does not exist in any database on this project.**
   `CAMERA-STRINGS.yaml:90 permit_ref` is `WO-88213`; the demo world seeded by
   `scripts/deploy/seed_demo.py` — the same pair of seed files behind the Cloud database —
   mints one permit whose `external_ref` reads `DEMO-PTW-0001`. A note already sits beside
   `permit_ref` at `CAMERA-STRINGS.yaml:85` recording exactly this. Either the corpus mints the
   scripted reference when `corpus-spine-authored` lands, or the string moves. The decision
   belongs to the corpus and demo-seed owners, not to this kit.
10. **NEW, 2026-08-14 · the container this kit told you to look for does not exist.** The
    2026-08-12 revision pasted `trappoint-testkit-crdb` and `mainline-crdb` and said only the
    second answers on `26257`. `docker ps` today lists one container, `trappoint-crdb`. Nothing
    is broken — the socket is what matters and B.2 confirms it — but **B.1 was a worked example
    that would have sent a founder looking for a container that is not there**, and the same
    stale name is still in `docs/submission/RUNBOOK.md` §7's `docker ps` expectation, which is
    a document this kit does not own. Raised to the runbook's owner, and corrected here.
11. **NEW, 2026-08-14 · `mainline.disposition` has no foreign key onto
    `mainline.defeater_option`.** `grep -n defeater verticals/mainline/db/migrations/
    0066_disposition.sql` returns `:108 defeater_code STRING NOT NULL`, `:109
    defeater_vocab_sha256 BYTES NOT NULL`, `:211 CHECK (defeater_code <> '')` and `:216 CHECK
    (length(defeater_vocab_sha256) = 32)` — and no `REFERENCES`. The gap is closed in
    `mainline_demo_api.defeaters`, which raises rather than defaulting, and that module records
    why the constraint was not added four days from a deadline. **It is a film problem as much
    as a schema one**, because the whole voice-over is "the database refuses". MUST-NOT-CLAIM
    family 14 carries the sentence. Owner: the demo-api and migrations owners.
12. **NEW, 2026-08-14 · the committed Cloud bundle fixture carries a vocabulary digest that
    digests nothing.** Base64-decode `response.body_b64` in `verticals/mainline/apps/console/
    fixtures/bundles/demo-cloud/frames/GET-f116fc2724f1b968.json` and `signed.
    defeater_vocab_sha256` reads
    `7ad8d49c2edd93f0a8fd3cd6b2a5d6cd225810805527a1a3f2f497aec819db3f`, which is exactly
    `sha256(b"defeater-vocab")`. The code that produced it is fixed; **the fixture is a
    recording and is not edited to agree with the fix**. If any frame of the film shows that
    bundle, it is showing the pre-fix value. Owner: the console-fixtures owner, whose choice is
    to re-record or to annotate — not to re-type the digit.
13. **NEW, 2026-08-14, AND THIS ONE BIT WHILE THIS PAGE WAS BEING WRITTEN ·
    `scripts/deploy/seed_demo.py` OVERWRITES A COMMITTED CLOUD ARTEFACT BY DEFAULT.** Its
    `--out` defaults to `evidence/deploy/cloud-seed.json` — the file that records the
    **CockroachDB Cloud** seed, `SEEDED AND REFUSABLE` at `2026-08-14T04:27:30Z` against
    `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257`, database
    `mainline_demo`. Running the §B.10 sequence against a **local** scratch database rewrote
    that file with `cluster: localhost:26257/defaultdb`, `database: w_d6_demo_world`,
    `connected_as: root`. It was reverted with `git checkout --` on the spot and the Cloud
    values are restored byte-for-byte.

    **The failure mode is silent and it is exactly the one this project sells against:** the
    run is green, the verdict is `SEEDED AND REFUSABLE` either way, and the only difference is
    that a transcript claiming to be Cloud is now a transcript of a laptop. Nothing in the
    output warns you; the `evidence` line at the foot of the run is the only clue and it reads
    like a courtesy.

    **Always pass `--out` to a path outside `evidence/`** when you are seeding a scratch
    database — `--out out/qa/demo-world-seed.json` — and check `git status evidence/` after
    any run of it. The durable repair belongs to the deploy domain: default `--out` to
    something that is not a committed artefact, or refuse to write a Cloud-named file from a
    `localhost` DSN. Either would have made this impossible; neither is this kit's to write.

---

## H · THE PROVENANCE OF THIS REVISION — every command, and whether it was RUN

This page's own honesty rule, applied to this page: **a command nobody has run is a plan.**
Here is the ledger for the 2026-08-14 revision, so a reader can check the claim rather than
accept it. Everything marked RAN was executed on this machine, on 2026-08-14, against the
pinned local node; everything marked READ was read back from a committed file.

| § | command or file | verdict |
|---|---|---|
| 0 | `validate_shotlist.py` | **RAN** · exit 0 · `submission.total_s 171`, `shots 25`, `vo_words 304`, `headroom_s 9`, `mws.total_s 158` |
| A.4 | `ls .venv/Scripts/*.exe` | **RAN** · no bare `mainline`; `uv.exe` present but not on `PATH` |
| B.1 | `docker ps` | **RAN** · one container, `trappoint-crdb`, `cockroachdb/cockroach:v26.2.5` |
| B.2 | `scripts/qa/doctor.py` | **RAN** · `NOT READY - 2 blocking checks` (`uv`, `just`) |
| B.3 | `seed_demo_state.py --database w_D6_video_kit` | **RAN** · `READY - 20 checks, 0 failed` · chain 271/271 in 96.8 s |
| **B.4** | the seeder's `BEAT 4 SKIPS AFTER` block | **RAN** · `2026-08-14T11:22:40Z (1h 59m from now)` |
| **B.4** | the one-line receipt tripwire | **RAN** · `BEAT 4 LIVE until 2026-08-14T11:22:40Z` |
| B.7 | `seed_demo_state.py --camera` | **RAN** · `READY - 16 checks, 0 failed`; the s09/s10/s11 block pasted verbatim |
| B.8 | `evidence/gate-refusal/proof-20260814T032418Z.json` | **READ** · `PROVEN`, `caveats []`, 271/271, 10/10, `23514` → `P0001` → `00000` |
| B.9 | `demo_permit.sql:400,416` · `gate_refusal.py:1243` | **READ** · `2027-01-01` and `now() + INTERVAL '2 hours'` — **neither changed** |
| B.9 | `mainline.exposure_receipt` on STATE B | **RAN** · one receipt, `2027-01-01 00:00:00+00` |
| B.10 | `CREATE DATABASE` → `bootstrap` → `up` → `seed_demo.py --out …` | **RAN**, all four, from empty · `SEEDED AND REFUSABLE`, exit 0 · `up` took 2 297 s |
| C.0 | the eight-relation presence one-liner | **RAN** · `present` ×8 |
| C.0 | `defeater_option` / `signing_credential` / `clearance_legal` counts | **RAN** · STATE A: 3 / 2 / 21, `(blood_major, accept_residual)` = 0 |
| C.2 | four beat-1 surface probes | **RAN** · all four ABSENT — the finding stands |
| C.3 | `trappoint_core.errors.GateRefused` rendering | **RAN** · diverges from `REFUSAL-STRINGS.yaml`, as recorded in §G item 5 |
| C.6 | the vector-search `EXPLAIN` | **RAN** · `vector search` on `@cue_scoped_idx`, non-empty `prefix spans` |
| C.6 | `mainline_audit.v_silence_summary` | **RAN** · 0 rows — still not this shot |
| C.7 | `gen_card.py --check` | **RAN** · exit 2, refuses; corpus lock absent |
| C.7 | `SUBMISSION.json` | **READ** · `demo_url UNRESOLVED`, `video_url UNRESOLVED`, repo public |
| 0.3 | `scripts/mi_ratchet.py report` | **RAN** · `21 pending / 9 enforced` |
| 0.3 | `evidence/deploy/acceptance.json`, `cloud-acceptance.json` | **READ** · both `PROVEN`, both `target_is_local_emulator: true` |
| G | `0066_disposition.sql`, the demo-cloud bundle frame | **READ** · no FK onto `defeater_option`; the digest is `sha256(b"defeater-vocab")` |

**Not run, and named as such:** `s12`'s `DROP CONSTRAINT` (destructive by design; the seeder
verifies the constraint from the catalogue instead), every console path, the MCP session, the
changefeed, and the custodian patrol. Each is marked *declared, not run here* where it appears.

**And the thing this page did not do: it did not record a video.** No footage exists. The kit
is the preparation; the film is the founder's.
