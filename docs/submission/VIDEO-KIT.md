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

**Everything below was re-measured on 2026-08-12** against the pinned local node. Where a
command was executed while writing this page it is marked **RAN 2026-08-12**; where it was
only confirmed to exist it is marked **declared, not run here**. The distinction is the
document's own honesty rule applied to itself: a command nobody has run is a plan.

---

## 0 · Authority, and how every number below is re-derived

| Question | The file that answers it |
|---|---|
| How long is a shot? What is the running time? | `verticals/mainline/demo/script/SHOT-LIST.yaml` (`t`, `dur`, `budget`) |
| What is spoken? | `verticals/mainline/demo/script/VO.md`, and `vo`/`word_count` per shot in `SHOT-LIST.yaml` |
| What prose appears on screen? | `verticals/mainline/demo/script/CAMERA-STRINGS.yaml` |
| What does the *database* print? | `verticals/mainline/demo/REFUSAL-STRINGS.yaml` |
| What may the founder not say? | [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) — twelve families — and §0.3 below for the four that are specific to the film |

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

**RAN 2026-08-12.** It printed `25 shots  171s (2:51)  304 words  1.78 w/s` and
`ceiling 180s  CI hard fail 176s  headroom 9s` — the same figures the 2026-08-11 run
produced. Everything in §0.1 and §0.2 is that output, formatted.

The validator agrees, and it is the gate that matters:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe verticals/mainline/demo/script/validate_shotlist.py
```

**RAN 2026-08-12** — `submission.total_s 171`, `submission.shots 25`,
`submission.vo_words 304`, `submission.headroom_s 9`, `mws.total_s 158`, and
`shot lists OK`. It also prints one NOTE, which is not a pass and says so: the authored
corpus fixture root does not exist yet, so the camera string was not checked against it.
That NOTE is the same fact that decides beat 1 in §C.

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

## 0.3 · MUST NOT CLAIM — the four the camera will tempt you into

[`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) is the register and it is **twelve** families long.
Read it the morning of the shoot. **These four are specific to the film, and each one is a
number somebody will ask you about.**

### 1 · Do NOT say "thirty of thirty invariants", or "all the invariants are enforced"

| | |
|---|---|
| **MUST NOT SAY** | "All thirty machine invariants are enforced." · "30/30." · "The invariant catalogue is complete." |
| **TRUE INSTEAD** | "The catalogue names thirty invariants. Nine are enforced in the database today and twenty-one are pending. The ratchet is what keeps that number honest — it fails the build if a pending invariant is quietly described as enforced." |
| **MEASURED** | `.venv/Scripts/python.exe scripts/mi_ratchet.py report` → **`21 pending / 9 enforced`**. RAN 2026-08-12. |
| **THE NUMBER YOU MAY HAVE HEARD** | **28 of 30.** It was true when it was written and nine invariants have been promoted since. `.github/workflows/ci.yml:690` now quotes that string *in order to correct it*, and the survivors are in superseded planning documents under `docs/leads/`. So a grep of the tree returns the stale number and its correction together and you can carry away either. Run the command; quote neither figure from memory. Register family 11. |

The ratchet being red is not a defect to hide. It is the top-level incompleteness counter, and
an honest 9-of-30 with a machine that refuses to let it be overstated scores better under
*Technological Implementation* than a silent 30/30 nobody believes.

### 2 · Do NOT say the custody chain has been verified end to end

| | |
|---|---|
| **MUST NOT SAY** | "The custody chain is verified end to end." · "Every custody check passes." |
| **TRUE INSTEAD** | "Sixteen custody checks are specified. Nine pass. **Seven of the sixteen are unimplemented** — the cryptographic verifier checks are not written — and the CI lane is red for exactly that reason, by name, per check." |
| **MEASURED** | `.github/workflows/custody-chain.yml:740` names the summary line `16 checks \| 9 passed \| 0 failed \| 7 not checked`; `docs/CI-STATE.md` §3.1 records the lane as an intentional red for exactly that reason. Both citations re-checked 2026-08-12, because line numbers move and a stale pointer is a claim nobody can follow. |

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
| **MEASURED** | `evidence/deploy/aws-live.json`. Everything else in the AWS column — Lambda, SSM, CloudWatch — is **declared in Terraform and not applied**, and `evidence/deploy/acceptance.json` says so on its own face. |

### And the three the register gained on 2026-08-12

They are families 10, 11 and 12 of [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md), and two of them
have **no scanner rule at all** — a human is the only control. In one line each:

* **Never say the conformance suite has been demonstrated.** It has not been. Two cases are
  captured instead by `scripts/proof/gate_refusal.py`. (Family 10; `SUB-05` catches the word
  in a file and hears nothing you say.)
* **Never quote the MI ratchet as 28 of 30.** It measures 21 pending / 9 enforced. (Family 11;
  caught by nothing — run the command.)
* **Never say the acceptance run passes** unless `evidence/deploy/acceptance.json` reads
  `PROVEN` **on the day of the shoot**. RAN 2026-08-12: that file's `verdict` field read
  **`NOT PROVEN`**, generated `2026-08-12T16:17:12Z`. (Family 12; caught by nothing — read
  the file.)

### The demo URL, on `s25`

`s25-end-card` shows the repository, the demo URL and the MCP one-liner. RAN 2026-08-12:
`docs/submission/SUBMISSION.json` holds `"demo_url": "UNRESOLVED"` and
`"video_url": "UNRESOLVED"`; `"repo_url"` reads `https://github.com/Shaugato/mainline`.
**Film `s25` last, and do not put a URL on the card that is not in that file.** If it still
reads `UNRESOLVED` on the day, the card carries the repository and the MCP line only, and the
voice-over drops the word "demo" — "*Repo, read-only endpoint. Verify it yourself*" is seven
words minus one and fits the same 6 seconds.

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

### A.4 `just` and `uv` are NOT installed on this machine

This is measured, and re-measured today, by `scripts/qa/doctor.py`, which reports two
blocking rows:

```
FAIL    uv (python workspace)   not on PATH
FAIL    just (command surface)  not on PATH
```

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
plus the executable name, which is how `trappoint-migrate` appears in §B.9.

Neither FAIL blocks the proof. `doctor.py` says so itself, and section B.2 pastes the
output that proves it.

---

## B · THE PRE-FLIGHT

Run these in order. Each step gives the command, then the output it produced on
**2026-08-12**, pasted below it. If your output differs materially, stop and fix it —
that is the point of pasting it.

**B.4 is a hard gate and it is new.** Everything before it can be checked by looking at the
screen. B.4 cannot: it is a deadline, it is invisible once it passes, and the failure it
causes looks exactly like the product working.

### B.1 The node is up and it is the pinned image

```bash
docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"
```

**RAN 2026-08-12:**

```
trappoint-testkit-crdb	cockroachdb/cockroach:v26.2.5	Up 43 hours
mainline-crdb	cockroachdb/cockroach:v26.2.5	Up 43 hours
```

The image must be `cockroachdb/cockroach:v26.2.5`. A different tag is a different product
and a different set of error strings. **Two containers answer on this machine** — the test
kit's and the demo's. Only `mainline-crdb` is on `26257`, which is the port every command in
this kit uses; the pre-flight in B.2 confirms which socket answered.

### B.2 The doctor, and its two known FAIL rows

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/qa/doctor.py
```

**RAN 2026-08-12.** The rows that matter:

```
OK      python >= 3.13          3.13.14 at D:\CoackroachDBxAWS\mainline\.venv\Scripts\python.exe
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
OK      pgwire 127.0.0.1:26257  a socket accepted the connection [the local single-node default]
OK      cockroachdb version     CockroachDB CCL v26.2.5
OK      node clock vs host      +0.050s (node - host, round trip removed)
OK      gc.ttlseconds == 4500   4500 - aligned with CockroachDB Cloud
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
  and this row is how far it is from yours.

### B.3 Seed the state, in one command

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --database w_s08_demo_state
```

This drops and rebuilds the database, applies the whole migration chain, seeds the smallest
history in which the claim is decidable, and then **proves it did** — by executing the three
refusals for real and rolling each one back. It takes about a minute, most of it the chain.

**RAN 2026-08-12** (against `w_w9_video_kit`, a scratch database built by exactly this
command, so that another worker's `w_s08_demo_state` was not disturbed):

```
migration chain            OK      all      271/271 applied, 0 failed, 0 unexplained, 54.3s
reached 0115 merge gate    OK      s08 s09  0115_fn_permit_merge_gate applied
seed history               OK      all      permit_id=d09d0748-… check_id=d0575fd7-…
gate objects               OK      s08-s12  8/8 present
permit row                 OK      s08      1 permit(s) with external_ref='PTW-PROOF-1'
permit state               OK      s08      state='dispositioned'
open obligation            OK      s08 s09  permit.open_blocking=1
obligation row             OK      s11      blocking_check check_id=d0575fd7-…
no disposition yet         OK      s08 s13  0 live disposition(s) against the obligation
exposure receipt live      OK      s13 s14  receipt_id=c19e1269-… LIVE until 2026-08-12T18:37:01Z
gate constraint attached   OK      s09 s12  mainline.permit CONSTRAINT gate_closed_when_issued
append-only weld           OK      s11      TRIGGER append_only ON mainline.blocking_check
explain_refusal installed  OK      s10      trappoint.explain_refusal(kind, id, constraint, attempt)
merge REFUSES              OK      s08 s09  REFUSED [23514] gate_closed_when_issued (reported)
raw UPDATE REFUSES         OK      s10      [23514] failed to satisfy CHECK constraint ((state != 'merged'…
DELETE REFUSES             OK      s11      [P0001] MAINLINE: this table is append-only; write a new row
state intact after probes  OK      s08-s12  state='dispositioned' open_blocking=1 dispositions=0
open_blocking written by   INFO    s08      trigger check_materialised (0121) — the database's own projection

VERDICT  READY - 20 checks, 0 failed. Roll camera.
```

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
database  FAIL    all    w_s08_demo_state does not exist on this cluster - run without --verify-only to build it
VERDICT  NOT READY - 1 check failed
```

So the full command above is not a one-off setup step you did last week; it is the first
thing you type on capture day.

The identifiers are minted fresh on every rebuild. The 2026-08-12 run printed:

```
  database        w_w9_video_kit
  permit_id       d09d0748-3318-4e0e-aea6-ab61c2083e0a
  check_id        d0575fd7-ee07-4663-a078-ed11a821d8ff
  site_id         7f9b9907-1a77-46ea-ab96-4d7e2d941cf9
```

**Those exact values will not be yours.** Copy from *your* run's ON-CAMERA SUBSTITUTIONS
block, never from this page — that is the entire reason the block exists. It prints the
`permit_id`, `check_id` and `site_id` this run minted, and the SQL statements with those
values already substituted. **Never retype a UUID on camera** — a mistyped UUID is a take,
and it is a take you will not notice until the error message is the wrong error message.

### B.4 THE RECEIPT DEADLINE — a hard gate, and the quietest way this shoot fails

`seed_demo_state.py` prints this block on **every** run, in both modes, immediately under the
caveat. **RAN 2026-08-12:**

```
BEAT 4   SKIPS AFTER 2026-08-12T18:37:01Z  (1h 59m from now, server clock)
         After this instant a local gate-run SKIPS beat 4 (the admission) and reports NOT
         PROVEN, while beats 1-3 keep refusing exactly as they do now — so the failure does
         not look like a failure on camera. scenario._RECEIPT_SQL selects the exposure receipt
         only while expires_at > now(); seed_history issues it with a two-hour window.
         Receipt c19e1269-… is LIVE. Finish the take before that instant, or re-run: python
         scripts/submission/seed_demo_state.py --database w_w9_video_kit
```

**Write that instant on a sticky note before you touch the camera.** Not the one above —
yours. It is roughly two hours after your seed and it is the only number on the screen that
becomes false while you are looking at it.

**The mechanism, so you can trust the gate rather than obey it.**
`scenario._RECEIPT_SQL` (`scenario.py:297`) selects the exposure receipt with
`WHERE r.permit_id = %s AND l.check_id = %s AND r.expires_at > now()`. With no live receipt,
`resolve()` returns `receipt_id = None`; `gate_run.py:552` tests exactly that and
`gate_run.py:553` sets beat 4's outcome to `skipped`. A skipped beat 4 makes the verdict
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

**The one-line check to run between takes.** It asks the database the same question
`scenario._RECEIPT_SQL` asks, and answers in one line:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg,datetime as dt;r=psycopg.connect('postgresql://root@localhost:26257/w_s08_demo_state?sslmode=disable&connect_timeout=10').execute('SELECT r.expires_at, r.expires_at > now() FROM mainline.exposure_receipt r JOIN mainline.exposure_line l ON l.receipt_id = r.receipt_id JOIN mainline.blocking_check b ON b.check_id = l.check_id AND b.permit_id = r.permit_id JOIN mainline.permit p ON p.permit_id = r.permit_id AND p.external_ref = %s ORDER BY r.issued_at DESC LIMIT 1', ('PTW-PROOF-1',)).fetchone();print('BEAT 4', ('LIVE until ' if r and r[1] else 'DEAD since ') + r[0].astimezone(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ') if r else 'BEAT 4 NO RECEIPT - re-seed')"
```

**RAN 2026-08-12**, in both `bash` and PowerShell on this machine, against the scratch
database: `BEAT 4 LIVE until 2026-08-12T18:37:01Z`. If it says `DEAD since` or
`NO RECEIPT`, stop and run B.3. It is a tripwire, not an authority — `--verify-only` is the
authority, and it names the row `exposure receipt live`.

**Why an expired receipt used to be survivable and is not.** `seed_demo_state.py` records, in
the comment above the row itself, that it once printed `VERDICT READY` against a database
whose receipt had died thirty-two hours earlier — the row was INFO, and an INFO row cannot
stop a shoot. Read back today at `scripts/submission/seed_demo_state.py:615-641`, the row is a
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
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --verify-only --database w_s08_demo_state
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
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --camera --database w_s08_demo_state
```

Verifies first, refuses to print the block if the table is not green, then prints beat 2 at
a fixed 96 columns. **RAN 2026-08-12**, verbatim (UUIDs are this run's):

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
      WHERE permit_id = '<from the substitutions block>';
    ERROR: failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR
           (open_blocking = 0:::INT8))
    SQLSTATE: 23514
    constraint: gate_closed_when_issued   <- from diag.constraint_name
    SELECT trappoint.explain_refusal(
      'permit', '<from the substitutions block>', 'gate_closed_when_issued');
    class:      gate
    constraint: gate_closed_when_issued
    mus:        1 obligation(s)
    naa:        dispose_obligations
                1 obligation(s) remain open on this subject; disposing of exactly those restores
                admissibility

s11 · RAW SQL AS CLUSTER ADMIN · the obligation is append-only
    DELETE FROM mainline.blocking_check
      WHERE permit_id = '<from the substitutions block>';
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
database (`w_qr_gate_refusal_proof`), so it does **not** disturb `w_s08_demo_state` — but it
takes about a minute and it is a different frame from beat 2. Use it as the fallback for
`s09` if the console is unavailable, not as the main path. Declared here, not run while this
page was written; §B.3 exercises the same imported primitives.

### B.9 The SECOND database — and why it cannot be the first one

Beat 2 films the **proof** history: permit `PTW-PROOF-1`, seeded by B.3. The console shots —
the merge click on `WO-88213`, the disposition ladder, the site register — want the **demo
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

**RAN 2026-08-12.** Both seed files applied in under a third of a second and the demo
permit's merge was refused by the database with the same SQLSTATE and the same constraint —
so the mechanism is fine. `seed_demo.py` requires **exactly one** permit, and B.3's proof
permit is the second one. Seeding the demo world on top of the shot-ready database therefore
turns a green pre-flight into `WRONG STATE` minutes before a take.

So build it separately, into its own empty database:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg;psycopg.connect('postgresql://root@localhost:26257/defaultdb?sslmode=disable',autocommit=True).execute('CREATE DATABASE IF NOT EXISTS w_demo_world')"
D:/CoackroachDBxAWS/mainline/.venv/Scripts/trappoint-migrate.exe bootstrap --dsn postgresql://root@localhost:26257/w_demo_world?sslmode=disable
D:/CoackroachDBxAWS/mainline/.venv/Scripts/trappoint-migrate.exe up --dsn postgresql://root@localhost:26257/w_demo_world?sslmode=disable --migrations verticals/mainline/db/migrations
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/deploy/seed_demo.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable --database w_demo_world
```

**All four commands RAN 2026-08-12, in that order, and the sequence finished green.**
`bootstrap` answers `bootstrapped: schema, schema_migration, schema_lock, schema_attestation,
genesis attestation`; `up` refuses with a named message if you skip it; and `seed_demo.py`
ended:

```
  seed         demo_world.sql       OK                 0.11s attempts=1
  seed         demo_permit.sql      OK                 0.19s attempts=1
permits       1 in mainline.permit, 1 is the demo permit
state         dispositioned  open_blocking=1  gate_epoch=1  head_seq=2
obligation    severity=4 virulence=blood_major (projected)
MERGE         REFUSED [23514] gate_closed_when_issued (reported)
rollback      nothing_persisted=True
VERDICT       SEEDED AND REFUSABLE
```

That is STATE B: the demo permit, one open obligation, and the same refusal beat 2 films,
executed and rolled back.

**Budget real time for `up`, and do it the day before rather than on capture day.** It appends
an attestation per file by default, and that is not free. Measured on this machine:
`trappoint.schema_migration` held **230** rows about twenty-five minutes in, and the run
finished about half an hour after it started, ending
`fingerprint 4b54809a… (grade strong, attestation ordinal 271)`. The proof's own chain
application inside `scripts/submission/seed_demo_state.py` takes **54 seconds** over the same
tree, because it does not attest per file. Both figures are that run's; re-derive rather than
plan against them. `--attest final` is the documented alternative if the clock matters more
than the per-file chain.

---

## C · THE BEAT-BY-BEAT TABLE

For every shot: the exact command, the seeded state it assumes, the shot itself, the one
sentence of voice-over, and the pre-committed fallback. Durations are in `SHOT-LIST.yaml`;
`capture_order` is section D.

### C.0 The four states, named once

Every row below says which one it needs. Build them in this order.

| | what it is | how it is built | measured today |
|---|---|---|---|
| **STATE A** | `w_s08_demo_state` — the proof history: permit `PTW-PROOF-1`, one open obligation, one **live** exposure receipt, the gate constraint attached | §B.3 | **green**, 20 checks, 0 failed |
| **STATE B** | `w_demo_world` — the demo world: the demo permit, the severity-4 precursor, the blame edge | §B.9, **a different database from A** | **green** — `VERDICT SEEDED AND REFUSABLE`, 1 permit, merge refused `23514`, nothing persisted |
| **STATE C** | the authored corpus — four labelled clause generations, `verticals/mainline/fixtures/corpus/authored/` | owner `corpus-spine-authored` | **ABSENT.** `validate_shotlist.py` reports it as not checked, which is not a pass |
| **STATE D** | nothing — a static card | authored artwork | `verticals/mainline/demo/script/cards/` **does not exist on this tree** |

**Schema presence is not a shot.** Every table and view the beats read is present in STATE A —
check it yourself in one command, which **RAN 2026-08-12** in both `bash` and PowerShell and
printed `present` six times:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg;c=psycopg.connect('postgresql://root@localhost:26257/w_s08_demo_state?sslmode=disable&connect_timeout=10');[print(f'{s}.{t}:','present' if c.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s',(s,t)).fetchone()[0] else 'ABSENT') for s,t in [('mainline_audit','v_disposition_coverage'),('mainline_audit','v_silence_summary'),('mainline','event_cue_embedding'),('mainline','ledger_leaf'),('mainline_ops','site_register_signal'),('mainline','patrol_run')]]"
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

### C.2 Beat 1 — the clause remembers · **the beat with no surface on this tree**

Read this paragraph before you schedule a shooting day. `mainline blame STD-ISO-006 --clause
9.2.1` is a string in `CAMERA-STRINGS.yaml`, not a program: **there is no `mainline`
executable in `.venv/Scripts/`** — measured 2026-08-12, the console scripts installed there
are `mainline-boundary`, `mainline-gate`, `mainline-mutation`, `mainline-steward` and the
`trappoint-*` family. The four-generation spine those shots walk lives in the authored corpus
(STATE C), which is absent, and the shot list's fallback — a tape replayed from
`evidence/demo-run-<ts>/` — is also absent: no `evidence/demo-run-*` directory exists on this
tree. **Beat 1 has neither a main path nor its written fallback today**, and that is a
scheduling fact rather than a capture-day surprise.

**`s05-beat1-blame-walk`** — K3 · 10 s · capture #4 · **STATE C**

* **Command** — none on this machine. The on-screen string is
  `mainline blame STD-ISO-006 --clause 9.2.1` (`CAMERA-STRINGS.yaml: blame_command`, verbatim),
  typed at a `mainline_demo=>` prompt.
* **Shot** — four nodes walking `2011 → 2013 → 2016 → 2019`, one per line.
* **VO** — "So we ask the clause where it came from."
* **Fallback** — a typeset replay of the four nodes from `CAMERA-STRINGS.yaml: spine.labels`
  and `spine.dates`, with the VO unchanged. The written fallback (a tape from `evidence/`)
  requires an artefact that does not exist.

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
  the scratch database held two permits — see §B.9. The refusal line is the frame; the verdict
  line is the pre-flight, and on a database built the §B.9 way only one permit stands.
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

* **Command** — `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --camera --database w_s08_demo_state`, then frame the `s09` block. **RAN 2026-08-12.**
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
  against `w_s08_demo_state` as root: the `UPDATE mainline.permit SET state = 'merged' WHERE
  permit_id = '…';` and then the `SELECT trappoint.explain_refusal('permit', '…',
  'gate_closed_when_issued');`. Both statements **RAN 2026-08-12** inside `--camera`, each
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
  substitutions block. **RAN 2026-08-12** inside `--camera`, rolled back.
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
constraint (…)")` — re-measured 2026-08-12 by reading `trappoint_core.errors.GateRefused`,
whose constructor calls `super().__init__(f"{sqlstate} {constraint}: {message}")`. Both carry
the SQLSTATE and the constraint name, so the voice-over is true either way.
`seed_demo_state.py --camera` sidesteps the divergence by printing the fields on their own
labelled lines, which is also what makes them legible. **Do not compose a shot around the
`client_render` string in the YAML.** Neither file is this kit's to edit; the divergence is
raised to the demo owner in §G.

*Beat 2 is filmed from STATE A, and STATE A is the database B.4 is about.* The refusals do not
care whether the receipt is alive. `s13` onwards does.

### C.4 Beat 3 — the disposition ladder

**`s13-beat3-lattice-refusal`** — K5 · 9 s · capture #8 · **STATE A or B, receipt LIVE**

* **Command** — the disposition modal (console). The lattice inset's claim is checkable from
  the terminal in one line, which **RAN 2026-08-12** in both `bash` and PowerShell and printed
  `clearance_legal rows: 21` then `(blood_major, accept_residual): 0`:

  ```bash
  D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import psycopg;c=psycopg.connect('postgresql://root@localhost:26257/w_s08_demo_state?sslmode=disable&connect_timeout=10');print('clearance_legal rows:', c.execute('SELECT count(*) FROM mainline.clearance_legal').fetchone()[0]);print('(blood_major, accept_residual):', c.execute('SELECT count(*) FROM mainline.clearance_legal WHERE virulence = %s AND kind = %s', ('blood_major','accept_residual')).fetchone()[0])"
  ```

* **Assumes** — a live exposure receipt (B.4). Without one the signature has no `(receipt_id,
  check_id)` pair to cite and the modal cannot reach the lattice at all.
* **Shot** — signer picks `accept_residual` against a `blood_major` ancestry, submits. Must
  appear: `SQLSTATE: 23503`, constraint `fk_clearance` (R4). The lattice inset shows the three
  deliberately absent cells greyed with their reasons.
* **VO** — "Accept the residual risk? There's no such verdict — no row, and a foreign key says so."
* **Fallback** — **none. This is the entry's single best thirty seconds and is never cut.**

`mainline.clearance_legal` holds **21** rows and the pair `(blood_major, accept_residual)` is
**absent** — both re-measured 2026-08-12 by the command above. That absence is what `s13`
films. It is not a stricter row; it is no row.

**`s14-beat3-disposition-signed`** — K5 · 8 s · capture #9 · **STATE A or B, receipt LIVE**

* **Command** — console: switch the kind to `mitigated`; the countersigner field **appears by
  itself** because `req_second_signer` is projected true. Fill the rationale past 120
  characters. Sign, then countersign. Declared, not run here — this path needs the console and
  an enrolled authenticator.
* **Assumes** — a live exposure receipt; `0066_disposition.sql:160` binds the signature to the
  pair `(receipt_id, check_id)`.
* **Shot** — the countersigner field appearing unprompted, then
  `deliberation 00:47 · measured, never thresholded` (`banners.deliberation`). R5's
  `needs_second_signer` is the constraint doing the work.
* **VO** — "Severity four forces a compensating control and a second signature. We measure deliberation. We never accuse."
* **Fallback** — if WebAuthn is not enrolled, degrade to the OIDC + signed-envelope path, and
  the honesty card says so in its NOT-BUILT-YET column.

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
  confirmed present 2026-08-12 among the API's 17 routes.
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

* **Command** — prompt 2 → `explain_query` over MCP. The identical `EXPLAIN` runs locally, and
  **RAN 2026-08-12**. A 1024-float literal cannot be typed, so build it:

  ```bash
  PYTHONIOENCODING=utf-8 D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe - <<'PY'
  import psycopg
  vec = "[" + ",".join(["0.01"] * 1024) + "]"
  conn = psycopg.connect("postgresql://root@localhost:26257/w_s08_demo_state?sslmode=disable&connect_timeout=10")
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

  It printed the plan tree ending:

  ```
  └── • vector search
        table: event_cue_embedding@cue_scoped_idx
        target count: 5
        prefix spans: [/'00000000-0000-0000-0000-000000000001'/'00000000-0000-0000-0000-000000000002'/'lesson' - …]
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
  **RAN 2026-08-12**: `SELECT * FROM mainline_audit.v_silence_summary` answered with **0
  rows** on STATE A, because nothing has run a recall against it. **A shot of an empty view is
  not this shot** — film it against a database that has a recall run, or the Cloud demo.
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

* **Command** — `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe verticals/mainline/demo/honesty/gen_card.py --check`. **RAN 2026-08-12** and it **refused**:
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

* **Command** — read the URLs out of `docs/submission/SUBMISSION.json`. **RAN 2026-08-12**:
  `repo_url = https://github.com/Shaugato/mainline`, `demo_url = UNRESOLVED`,
  `video_url = UNRESOLVED`.
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
   D-7 and not on D-1. It sums to 158 s, re-derived 2026-08-12.

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

Read [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) once, the morning of the shoot. Twelve families,
each beside the true sentence. The five most likely to slip out on camera:

* Not "everything runs in Australia" — inference is in Sydney, the database is in Singapore. <!-- prose-hygiene: quoting -->
* Not "it refuses in milliseconds" — every timing here is local Docker on one laptop. <!-- prose-hygiene: quoting -->
* Not "a real incident" — the corpus, the operator, the site and the incident are authored.
* Not "the conformance suite passes", and not that it has ever been demonstrated — it has not;
  two cases are demonstrated instead by `scripts/proof/gate_refusal.py`.
* Not "the acceptance run passes" — read `evidence/deploy/acceptance.json` on the day. It read
  `NOT PROVEN` on 2026-08-12.

And the one that is easiest to get wrong because it sounds modest: the database does **not**
stop a cluster admin from dropping the gate. `s12` films the drop succeeding. The claim is
tamper-*evidence* — the drop becomes an attested leaf — and `REFUSAL-STRINGS.yaml` R3 says so
in the file the camera reads from.

---

## G · What this kit found while it was being written

Recorded rather than repaired: none of these files belongs to this kit. Everything here was
measured on 2026-08-12 on the pinned local node.

1. **`verticals/mainline/demo/honesty/card.html` is marked NOT FOR CAMERA and cannot be
   regenerated on this tree.** `gen_card.py --check` refuses because
   `verticals/mainline/fixtures/corpus/corpus.lock.json` does not exist. Owner:
   `corpus-freeze-load`. Until it lands, `s23` and `s24` have no generated card, and the
   fallback in §C.7 is the only honest frame.
2. **`verticals/mainline/demo/script/cards/` does not exist**, so the three static cards
   (`title.svg`, `architecture.svg`, `end.svg`) named as evidence artefacts in `SHOT-LIST.yaml`
   are unauthored. They are capture-day assets with a lead time.
3. **Beat 1 has no surface.** There is no `mainline` executable in `.venv/Scripts/`; the
   authored corpus root `verticals/mainline/fixtures/corpus/authored/` is absent (the shot-list
   validator reports it as unchecked, which it prints as *not a pass*); and the written
   fallback — a tape under `evidence/demo-run-<ts>/` — does not exist either. Owners:
   `corpus-spine-authored` and whoever owns K3's surface.
4. **`seed_demo.py` and `seed_demo_state.py` cannot seed the same database.** Measured:
   applying the demo world on top of the proof history produces
   `VERDICT WRONG STATE — 2 permits stand in mainline.permit, expected exactly 1`, even though
   both seed files applied and the demo permit's merge was refused correctly. §B.9 is the
   two-database procedure. This is a note for the demo owner, not a defect in either script.
5. **`REFUSAL-STRINGS.yaml` R1 `client_render` does not match the shipped client.** Re-measured
   against `trappoint_core.errors.GateRefused`, whose constructor renders
   `f"{sqlstate} {constraint}: {message}"`. Either the YAML or the client should move; the kit
   works around it and neither is this document's to change.
6. **`REFUSAL-STRINGS.yaml` R1 `server_expression_rendering.verified: false` can be set true.**
   The exact rendering is
   `failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))`,
   printed again today on CockroachDB CCL v26.2.5. It should still never be a tape match
   target — a type annotation is a platform detail — but it is no longer unmeasured.
7. **`mainline_audit.v_silence_summary` is empty on a freshly seeded local database** — 0 rows,
   because no recall run has touched it. `s21` needs a database that has one.
8. **`trappoint migrate up` is far slower than the proof's own chain application** — 54
   seconds inside `scripts/submission/seed_demo_state.py`, against about half an hour under
   `trappoint-migrate up` with the default per-file attestation over the same tree (230 rows
   in `trappoint.schema_migration` at the twenty-five-minute mark; it then exited 0 and printed
   `attestation ordinal 271`, fingerprint grade strong). Not a defect — they do different
   work, and the attestation chain is the point of the slower one — but it is a scheduling
   fact for §B.9 and it belongs to the migration runner's owner.
9. **The film's permit reference does not exist in any database on this project.**
   `CAMERA-STRINGS.yaml: permit_ref` is `WO-88213`; the demo world seeded by
   `scripts/deploy/seed_demo.py` — the same pair of seed files behind the Cloud database —
   mints one permit whose `external_ref` reads `DEMO-PTW-0001`. Either the corpus mints the
   scripted reference when `corpus-spine-authored` lands, or the string moves. A note now sits
   beside `permit_ref` recording the measurement; the decision belongs to the corpus and
   demo-seed owners, not to this kit.
