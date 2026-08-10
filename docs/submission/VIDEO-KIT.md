<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# VIDEO KIT — the capture runbook

The script is finished. `verticals/mainline/demo/script/` holds a locked voice-over
(`VO.md`), the submission cut (`SHOT-LIST.yaml`), a minimum-winnable cut
(`SHOT-LIST-MWS.yaml`), the camera strings, the generated cut diff and a validator that
`.github/workflows/claims.yml` runs, so a drifted shot list is a red build. **None of that
is restated here and none of it is this document's to change.**

This document is the gap between a locked script and a founder holding a microphone: the
machine, the pre-flight, the literal keystrokes, the string each one should produce, and
the pre-committed fallback for every shot whose milestone might not be finished on the day.

---

## 0 · Authority, and the one rule about numbers

| Question | The file that answers it | Never answered here |
|---|---|---|
| How long is a shot? What is the running time? | `verticals/mainline/demo/script/SHOT-LIST.yaml` (`t`, `dur`, `budget`) | **yes — no duration appears in this document** |
| What is spoken? | `verticals/mainline/demo/script/VO.md` | |
| What prose appears on screen? | `verticals/mainline/demo/script/CAMERA-STRINGS.yaml` | |
| What does the *database* print? | `verticals/mainline/demo/REFUSAL-STRINGS.yaml` | |
| What may the founder not say? | [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) | |

**No duration, timecode or running total is written in this document.** A duration written
twice is a duration that can drift, the validator only guards the YAML, and the failure mode
is silent: a cut over three minutes is disqualified without anyone telling you. The schedule
is one file. Print it when you need it:

```bash
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c "import yaml,sys; d=yaml.safe_load(open('verticals/mainline/demo/script/SHOT-LIST.yaml',encoding='utf-8')); print(f\"budget {d['budget']}\"); [print(f\"{s['t']:>4}  {s['dur']:>3}  {s['shot_id']}\") for s in d['shots']]"
```

Everything else in this kit is keyed by `shot_id`, which does not drift.

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

This is measured, today, by `scripts/qa/doctor.py`, which reports two blocking rows:

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
interpreter, and `psycopg` will not be in it.

Neither FAIL blocks the proof. `doctor.py` says so itself, and section B.2 pastes the
output that proves it.

---

## B · THE PRE-FLIGHT

Run these in order. Each step gives the command, then the output it produced on
`2026-08-10`, pasted below it. If your output differs materially, stop and fix it —
that is the point of pasting it.

### B.1 The node is up and it is the pinned image

```bash
docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"
```

```
mainline-crdb	cockroachdb/cockroach:v26.2.5	Up 8 hours
```

The image must be `cockroachdb/cockroach:v26.2.5`. A different tag is a different product
and a different set of error strings.

### B.2 The doctor, and its two known FAIL rows

```bash
cd D:/CoackroachDBxAWS/mainline
.venv/Scripts/python.exe scripts/qa/doctor.py
```

The rows that matter:

```
OK      python >= 3.13          3.13.14 at D:\CoackroachDBxAWS\mainline\.venv\Scripts\python.exe
OK      docker engine (API)     server 29.3.1 (linux)
FAIL    uv (python workspace)   not on PATH
FAIL    just (command surface)  not on PATH
OK      psycopg 3 (importable)  psycopg 3.3.4
OK      compose.yaml image pin  cockroachdb/cockroach:v26.2.5  (parsed by trappoint_testkit.image)
OK      migration tree          271 .sql files in verticals/mainline/db/migrations
OK      pgwire 127.0.0.1:26257  a socket accepted the connection [the local single-node default]
OK      cockroachdb version     CockroachDB CCL v26.2.5
WARN    gc.ttlseconds == 4500   14400 (the permissive local default), Cloud enforces 4500
```

It exits **NOT READY - 2 blocking checks**, and that is expected.

* **`just` not on PATH** — `just` is a command *surface*, a set of one-line bash recipes.
  Nothing in this kit uses it. It blocks the doctor's own readiness verdict, not the proof.
* **`uv` not on PATH** — `uv` resolves the 27-distribution workspace from the lockfile. The
  workspace is *already installed* in `.venv/`, which the doctor confirms on the line
  `OK  workspace installed`. `uv` would be needed to rebuild it, not to run it.
* The `gc.ttlseconds` WARN is advisory and the doctor says so in its own words: *"The proof
  itself pins its own throwaway database, so this is fidelity, not a blocker."*
  `seed_demo_state.py` pins **4500** on the database it creates.

### B.3 Seed the state, in one command

```bash
cd D:/CoackroachDBxAWS/mainline
.venv/Scripts/python.exe scripts/submission/seed_demo_state.py
```

This drops and rebuilds `w_s08_demo_state`, applies the whole migration chain, seeds the
smallest history in which the claim is decidable, and then **proves it did** — by executing
the three refusals for real and rolling each one back. It takes about a minute, most of it
the chain. Measured on `2026-08-10`:

```
migration chain            OK      all      271/271 applied, 0 failed, 0 unexplained, 57.2s
reached 0115 merge gate    OK      s08 s09  0115_fn_permit_merge_gate applied
gate objects               OK      s08-s12  8/8 present
permit row                 OK      s08      1 permit(s) with external_ref='PTW-PROOF-1'
permit state               OK      s08      state='dispositioned'
open obligation            OK      s08 s09  permit.open_blocking=1
no disposition yet         OK      s08 s13  0 live disposition(s) against the obligation
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

The command then prints an **ON-CAMERA SUBSTITUTIONS** block with the `permit_id`, `check_id`
and `site_id` this run minted, and the SQL statements with those values already substituted.
**Copy-paste from that block. Never retype a UUID on camera** — a mistyped UUID is a take,
and it is a take you will not notice until the error message is the wrong error message.

### B.4 The caveat you must read before you speak

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
copied from a document, **because the answer has already changed once**:
`evidence/gate-refusal/proof-20260810T004200Z.json` recorded the trigger as absent and the
chain at 246 of 261; the tree measured 271 of 271 a day later once producer migrations for
the five unproduced tables appeared. If a future run says `the trigger is ABSENT`, then the
sentence "the projection closed the counter" is not available to you and the sentence "the
gate re-derived the count and refused" is.

### B.5 Re-verify without rebuilding

Between takes, and after anything destructive:

```bash
.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --verify-only
```

Seconds, not a minute. It exits 1 and names the broken rows if the state has moved. Measured
after typing shot `s12`'s `ALTER TABLE … DROP CONSTRAINT` by hand:

```
gate constraint attached   FAIL    s09 s12  … is ABSENT — s12 has nothing to drop
merge REFUSES              FAIL    s08 s09  ADMITTED [00000] — the gate let it through …
raw UPDATE REFUSES         FAIL    s10      [00000] the statement SUCCEEDED and was rolled back
VERDICT  NOT READY - 4 check(s) failed
```

That is the tool working. **After `s12`, rebuild** (B.3) before any further take.

### B.6 The dry pass of the beat-2 commands

```bash
.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --camera
```

Verifies first, refuses to print the block if the table is not green, then prints beat 2 at
a fixed 96 columns. Measured output, verbatim, `2026-08-10`:

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

### B.7 The whole proof, if you want the headline in one command

```bash
.venv/Scripts/python.exe scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable
```

Prints `REFUSAL … REFUSED [23514] gate_closed_when_issued (reported)`, then the forged-counter
refusal, then the admission, then `VERDICT PROVEN`. It builds and drops its own throwaway
database (`w_qr_gate_refusal_proof`), so it does **not** disturb `w_s08_demo_state` — but it
takes about a minute and it is a different frame from beat 2. Use it as the fallback for
`s09` if the console is unavailable, not as the main path.

---

## C · THE BEAT-BY-BEAT TABLE

For every shot: what you physically do, the string that must appear, and the fallback if the
milestone is not finished. Durations are in `SHOT-LIST.yaml`; `capture_order` is section D.

**A milestone note before the table.** The *schema* for every beat exists on this tree —
`mainline_audit.v_disposition_coverage`, `mainline_audit.v_silence_summary`,
`mainline.event_cue_embedding` with `cue_scoped_idx`, `mainline.clearance_legal` (21 rows),
`mainline.ledger_leaf`, `mainline.custodian_attestation`, `mainline_ops.outbox`,
`mainline.patrol_run` and `mainline_ops.site_register_signal` are all present in
`w_s08_demo_state`, measured `2026-08-10`. **Schema presence is not a shot.** The console,
the custodian patrol, the changefeed and the MCP endpoint are applications on top of it, and
whether each is wired is what decides between a row's main path and its fallback. Check the
schema half yourself in one command:

```bash
.venv/Scripts/python.exe -c "import psycopg;c=psycopg.connect('postgresql://root@localhost:26257/w_s08_demo_state?sslmode=disable&connect_timeout=10');[print(f'{s}.{t}:','present' if c.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s',(s,t)).fetchone()[0] else 'ABSENT') for s,t in [('mainline_audit','v_disposition_coverage'),('mainline_audit','v_silence_summary'),('mainline','event_cue_embedding'),('mainline','ledger_leaf'),('mainline_ops','site_register_signal'),('mainline','patrol_run')]]"
```

### Cold open and titles

| shot_id | needs | What you do, literally | Must appear on screen | Fallback |
|---|---|---|---|---|
| `s01-cold-open` | K3 | Clause view, mono on warm paper. Select `135` with the mouse; the red left-rule fades in. No typing. | `The seal-face high-temperature alarm shall be set at 135 °C.` — `CAMERA-STRINGS.yaml: clause_text_2013_onwards`. The `°` is U+00B0; check the font renders it. | Static PNG of the same clause rendered from the authored fixture; no cursor move. |
| `s02-the-change` | K3 | Permit branch view showing the MOC. No typing. | `MOC-2026-0413` · `135 → 150` · `control_delta: weaken` — `moc_ref`, `moc_diff_line`, `moc_delta_badge`. The arrow is U+2192, not `->`. | The same diff rendered by the mock fixture server in `demo/browser/mock/`. |
| `s03-title` | K0 | Static card. No motion, no typing. | `MAINLINE — institutional safety memory as a version-controlled repository` — `title_card`. Em dash is U+2014. | None required — the card is a static export with no dependency. |
| `s04-architecture` | K0 | Static card, five elements, no animation. | The five-element architecture card, `script/cards/architecture.svg`. | **Scope-cut ladder step 2 removes this shot entirely.** `s03` carries the thesis. |

### Beat 1 — the clause remembers

| shot_id | needs | What you do, literally | Must appear on screen | Fallback |
|---|---|---|---|---|
| `s05-beat1-blame-walk` | K3 | Type at the `mainline_demo=>` prompt: `mainline blame STD-ISO-006 --clause 9.2.1` — `CAMERA-STRINGS.yaml: blame_command`, verbatim. | Four nodes walking `2011 → 2013 → 2016 → 2019`, one per line. | Pre-recorded tape output replayed from `evidence/`; the VO is unchanged. |
| `s06-beat1-commit-message` | K3 | Zoom on the 2013 node. Nothing typed. Hold in silence. | `Lowered 150 → 135 after seal fire INC-2013-044 — two contractors burned` — `commit_message_2013`, **byte-equal across four files**. U+2192 and U+2014 are load-bearing. Plus `D. Okonjo` and `2013-08-04`. **No commit SHA is shown or spoken, ever.** | Still frame of the same node from the authored fixture; the silence is kept. |
| `s07-beat1-identity-survival` | K3 | Blame ribbon; the 2016 and 2019 nodes light. | `7.3 → 5.2.1 → 9.2.1 · doc move` — `ribbon_caption`. One `clause_uuid` under all three labels. | **Scope-cut ladder step 1 removes this shot.** `s06`'s VO absorbs the claim. |

### Beat 2 — the refusal and the bypass · NEVER CUT

Every row here is `never_cut: true`. Section E says what that forbids.

| shot_id | needs | What you do, literally | Must appear on screen | Fallback |
|---|---|---|---|---|
| `s08-beat2-merge-refused` | K1 | Permit `WO-88213`, hot work on P-4104. Click **merge** once. | `MERGE BLOCKED · 1 undispositioned precursor · gate_closed_when_issued` — `CAMERA-STRINGS.yaml: banners.merge_blocked`. | Run the same transition from the terminal; the red bar becomes the SQLSTATE line — `seed_demo_state.py --camera`, block `s09`. |
| `s09-beat2-constraint` | K1 | `.venv/Scripts/python.exe scripts/submission/seed_demo_state.py --camera`, frame the `s09` block. | `SQLSTATE: 23514` and `gate_closed_when_issued` — `REFUSAL-STRINGS.yaml` R1 `terminal_match` and `exhibit`. **See the note below this table about `client_render`.** | **None. If this cannot be filmed there is no submission; K1 carries no reduction.** |
| `s10-beat2-bypass-admin-update` | K1 | Paste from the substitutions block: the `UPDATE … SET state='merged'`, then the `SELECT trappoint.explain_refusal(…)`. | `ERROR: failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))` then `SQLSTATE: 23514`; then `constraint: gate_closed_when_issued` from `explain_refusal`. | **None. This is the most valuable footage in the video.** |
| `s11-beat2-bypass-append-only` | K1 | Paste the `DELETE FROM mainline.blocking_check …`. | `MAINLINE: this table is append-only; write a new row` and `SQLSTATE: P0001` — `REFUSAL-STRINGS.yaml` R2 `message`; the tape matches on `MAINLINE: this table is append-only`. | **None. Two of the three bypass statements are the floor for this beat.** |
| `s12-beat2-bypass-drop-constraint` | K6 | Type `ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued;` **This succeeds, and that is the shot.** Then the custodian patrol writes its leaf; show at 4× as an inset. | `ALTER TABLE` — R3 `outcome`. Then `gate_definition_changed` — R3b `terminal_match`, with the prior triggerdef digest. | **If the K6 custodian patrol is not wired, drop this statement and end the beat at `s11`.** The beat is never cut; only its third statement is. |

**Two things about this beat that are measured, and that you must know before rolling.**

*The `client_render` string in `REFUSAL-STRINGS.yaml` is not what the shipped client
prints.* The file records
`GateRefused(constraint='gate_closed_when_issued', sqlstate='23514')`. The client actually
renders `GateRefused("23514 gate_closed_when_issued: failed to satisfy CHECK constraint
(…)")` — measured `2026-08-10` against `trappoint_core.errors`. Both carry the SQLSTATE and
the constraint name, so the voice-over ("*Refused — not by a warning. By a CHECK constraint:
gate_closed_when_issued*") is true either way. `seed_demo_state.py --camera` sidesteps the
divergence by printing the fields on their own labelled lines, which is also what makes them
legible. **Do not compose a shot around the `client_render` string in the YAML.** Neither
file is this kit's to edit; the divergence is raised to the demo owner.

*After `s12` the database is broken on purpose.* Re-run B.3 before any further take. Do not
try to re-add the constraint by hand — a hand-made constraint is not the migration's
constraint, and the next take would be filming a different object.

### Beat 3 — the disposition ladder

| shot_id | needs | What you do, literally | Must appear on screen | Fallback |
|---|---|---|---|---|
| `s13-beat3-lattice-refusal` | K5 | Disposition modal. Pick `accept_residual` against a `blood_major` ancestry. Submit. | `SQLSTATE: 23503`, constraint `fk_clearance` — R4. Lattice inset shows the three deliberately absent cells greyed with their reasons. | **None. This is the entry's single best thirty seconds and is never cut.** |
| `s14-beat3-disposition-signed` | K5 | Switch the kind to `mitigated`. The countersigner field **appears by itself** because `req_second_signer` is projected true. Fill the rationale past 120 characters. Sign, then countersign. | `deliberation 00:47 · measured, never thresholded` — `banners.deliberation`. R5's `needs_second_signer` is the constraint doing the work. | If WebAuthn is not enrolled, degrade to the OIDC + signed-envelope path and the honesty card says so in its NOT-BUILT-YET column. |
| `s15-beat3-merge-succeeds` | K5 | Click merge again. It goes through. | A `merge_record` row with its `clearance_digest`. | Terminal rendering of the same `merge_record` row. |

`mainline.clearance_legal` holds 21 rows in the seeded database and the pair
`(blood_major, accept_residual)` is **absent** — measured `2026-08-10`. That absence is what
`s13` films. It is not a stricter row; it is no row.

### Beat 4 — the diachronic flip

| shot_id | needs | What you do, literally | Must appear on screen | Fallback |
|---|---|---|---|---|
| `s16-beat4-register-gains-activity` | K6 | Split screen. Left: the site activity register gains a row. Right: the permit, untouched, cursor parked. **Nobody types.** | One new register row; the permit unchanged. | Insert the register row from the terminal in the same shot; the point survives. |
| `s17-beat4-lease-revoked` | K5 | Nothing typed. The retro-block attempts to attach to the issued permit and the database refuses. | `DEFEATER LEASE REVOKED · predicate falsified by site register` — `banners.lease_revoked`; then `MAINLINE: precursor arrived after issue — use the post-issue recall path` and `SQLSTATE: P0001`, raised by `mainline.fn_check_materialised` — R6. **`23503` is NOT filmed here** — see ADR 0030; on this path it cannot occur, and filming a SQLSTATE that cannot occur is the exact overclaim this project punishes in others. | If the changefeed is not wired, fire the register write in the same transaction and film the identical `P0001`. The mechanism is unchanged. |
| `s18-beat4-suspend-and-fork` | K5 | Nothing typed. | `PERMIT SUSPENDED · child forked` — `banners.permit_suspended`, and the child permit's id. | Terminal rendering of the parent/child permit rows. |

### Beat 5 — hand it to an auditor

| shot_id | needs | What you do, literally | Must appear on screen | Fallback |
|---|---|---|---|---|
| `s19-beat5-mcp-connect` | K6 | In Claude Code: `/mcp`, then prompt 1. | `cockroachdb-cloud: connected`, then a `select_query` against `mainline_audit.v_disposition_coverage` showing surfaced / dispositioned / orphans with `ancestry_complete`. | If publishing a key is forbidden, record the MCP session against the throwaway `mainline-verify` cluster plus our own read-only endpoints, and `VERIFY.md` states exactly why. |
| `s20-beat5-explain` | K4 | Prompt 2 → `explain_query`. Hold on the fragment. | The **unedited** plan fragment containing `vector search` and a non-empty `prefix spans` over `mainline.event_cue_embedding@cue_scoped_idx` — `REFUSAL-STRINGS.yaml: explain_fragment`. **The index hint is mandatory**: at demo scale the optimizer does not choose the vector index unhinted. | Run the same `EXPLAIN` in the SQL shell; the fragment is identical. |
| `s21-beat5-silence` | K4 | Prompt 3: *what did you decline to surface?* | `mainline_audit.v_silence_summary`: candidates by reason with mean score, mean threshold and nearest miss. | Same view over the SQL shell if the MCP key is withheld. |

### Close

| shot_id | needs | What you do, literally | Must appear on screen | Fallback |
|---|---|---|---|---|
| `s22-readiness-strip` | K6 | Four static tiles. | RLS policy denying a cross-site read; the single-tenant boundary; `ccloud audit list -o json` hashed into the ledger; the CloudWatch alarm on gate-bypass attempts. | Drop the CloudWatch tile if AWS is unreachable; the remaining three stand alone. |
| `s23-honesty-card` | K0 | Full-screen card generated by `honesty/gen_card.py`. | The four columns — REAL / SYNTHETIC / STAGED / NOT BUILT YET — with M14 SHEPARD named in the fourth. | **None. The card ships in every cut, including the MWS.** |
| `s24-rubber-stamp` | K0 | The limit card, one sentence, full screen. | The rubber-stamp limit, stated. | **None. Naming the limit is the cheapest credibility in the film.** |
| `s25-end-card` | K0 | End card. | Repository, demo URL, the `claude mcp add` one-liner, and the licence triple (Apache-2.0 · FSL-1.1-ALv2 · CC-BY-4.0). | **None.** The URLs come from `docs/submission/SUBMISSION.json`; do not paste one that still reads `UNRESOLVED`. |

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

**Between takes** run `--verify-only` (B.5). **After `s12`** run the full rebuild (B.3).

Two shots need a fresh database rather than a fresh take: `s12` (it drops the constraint) and
`s15` (it merges the permit, and a merged permit cannot be refused again). Budget a rebuild
minute for each attempt at those two.

---

## E · THE SCOPE-CUT LADDER, AND THE ONE THING IT MAY NOT REACH

The ladder is pre-committed in `SHOT-LIST.yaml` under `scope_cut_ladder`, executed top-down,
so that it is never a 02:00 judgement call:

1. Cut `s07-beat1-identity-survival` — the reflow claim moves to `s06`'s VO and to the
   repository.
2. Cut `s04-architecture` — the thesis survives in `s03`.
3. Trim `s01-cold-open` — the hold on the setpoint shortens; the hook still lands.
4. Switch to `SHOT-LIST-MWS.yaml` — the Minimum Winnable Submission, four beats, written on
   D-7 and not on D-1.

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

Read [`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) once, the morning of the shoot. Nine sentences,
each beside the true one. The four most likely to slip out on camera:

* Not "everything runs in Australia" — inference is in Sydney, the database is in Singapore. <!-- prose-hygiene: quoting -->
* Not "it refuses in milliseconds" — every timing here is local Docker on one laptop. <!-- prose-hygiene: quoting -->
* Not "a real incident" — the corpus, the operator, the site and the incident are authored.
* Not "the conformance suite passes" — it has never been demonstrated; two cases are
  demonstrated instead by `scripts/proof/gate_refusal.py`.

And the one that is easiest to get wrong because it sounds modest: the database does **not**
stop a cluster admin from dropping the gate. `s12` films the drop succeeding. The claim is
tamper-*evidence* — the drop becomes an attested leaf — and `REFUSAL-STRINGS.yaml` R3 says so
in the file the camera reads from.

---

## G · What this kit found while it was being written

Recorded rather than repaired: none of these files belongs to this kit.

1. **`REFUSAL-STRINGS.yaml` R1 `client_render` does not match the shipped client.** Measured
   above in section C. Either the YAML or `trappoint_core.errors` should move; the kit works
   around it and neither is this document's to change.
2. **`REFUSAL-STRINGS.yaml` R1 `server_expression_rendering.verified: false` can now be set
   true.** The exact rendering is
   `failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))`,
   measured `2026-08-10` on CockroachDB CCL v26.2.5. It should still never be a tape match
   target — a type annotation is a platform detail — but it is no longer unmeasured.
3. **`README.md:55` carries a migration count that this tree no longer produces.** Re-derived
   by `scripts/submission/seed_demo_state.py` on `2026-08-10`, the chain applies every file
   in the tree. `scripts/submission/check_submission_prose.py` reports the README line as
   `SUB-06-migration-count`, whose remedy is to re-derive the number rather than quote one.
4. **The migration tree has 271 files, not the 261 both committed proof runs recorded.** Ten
   arrived after the last proof. Re-run the proof before the submission so the evidence and
   the tree agree.
