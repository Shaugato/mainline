<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# RUNBOOK.md — how to bring the two operator screens up, rehearse them, and film them

**Worker:** W8 · **Date:** 2026-08-15 · **Verified end to end this session** on Windows 11,
node 24.14.0, pnpm 11.5.3, CockroachDB v26.2.5 at `localhost:26257`.

Every command below was run. Where a step failed the first time, the failure and its fix are
written down, because the two that bit here will bite the next person in exactly the same way.

---

## 0 · The one rule that outranks the rest

**A local capture is identifiable by the `X-Mainline-Emulator` header rendered on screen, and
must never be presented as the deployed run.**

`scripts/deploy/local_furl.py` stamps `X-Mainline-Emulator: local_furl` on **every** response,
including the static ones, and the origin strip at the bottom of both screens renders it. If
that strip says `local_furl`, the capture is a rehearsal. The deployed origin sends no such
header and the strip reads `absent — the last response declared no emulator`.

This is not a caption discipline that a person has to remember. It is on screen in every frame,
which is why the header exists. Do not crop it out, and do not film over it.

---

## 1 · Pre-flight — five checks, about ninety seconds

```bash
# 1. the toolchain
node --version                     # expect v24.14.0
pnpm --version                     # expect 11.5.3

# 2. the database is up and reachable
.venv/Scripts/python.exe -c "import psycopg; \
  print(psycopg.connect('postgresql://root@localhost:26257/defaultdb?sslmode=disable').execute('select 1').fetchone())"

# 3. the seeded world exists — it is NOT in defaultdb (see §2, trap 1)
#    expect 'mainline_demo' in the list
.venv/Scripts/python.exe -c "import psycopg; \
  print([r[0] for r in psycopg.connect('postgresql://root@localhost:26257/defaultdb?sslmode=disable').execute('show databases')])"

# 4. build the site — this is what gets served
cd verticals/mainline/apps/console && rm -rf dist && npx vite build && cd -

# 5. confirm BOTH documents landed
ls verticals/mainline/apps/console/dist/index.html \
   verticals/mainline/apps/console/dist/operator.html
```

If step 5 shows only `index.html`, the operator entry is not in
`vite.config.ts`'s `build.rollupOptions.input` and nothing below will work.

---

## 2 · Start the emulator — and the two traps

**The command that works:**

```bash
.venv/Scripts/python.exe scripts/deploy/local_furl.py \
  --port 8791 \
  --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable" \
  --database mainline_demo \
  --permit-id "dec0de00-0006-4000-8000-000000000001" \
  --require-web-root \
  --ready-file /tmp/furl-ready.txt
```

The web root defaults to `verticals/mainline/apps/console/dist`, which is what you just built,
so it does not need to be passed. `--require-web-root` makes a missing build exit 3 instead of
starting a server that serves nothing.

### Trap 1 — the seed is in `mainline_demo`, not `defaultdb`

Without `--database mainline_demo`:

```
GET /v1/demo/subjects -> 500
{"error":{"detail":"[42P01] relation \"mainline.site\" does not exist", ...}}
```

The permit screen then renders its absence block — correctly, and it is a good demonstration of
the screen's honesty, but it is not what you want to film.

### Trap 2 — the gate run needs the permit id passed explicitly

Without `--permit-id`, `/v1/demo/gate-run` answers **422**:

```
{"detail":"no mainline.permit with permit_id 077a6fdd-… in this database.
 The demo history is seeded by w2-cloud-database; override the identifier
 with MAINLINE_DEMO_PERMIT_ID if this deployment seeded a different one.",
 "error":"demo_history_not_seeded"}
```

The reads all succeed, so the screen looks perfect right up until somebody presses ISSUE. **Press
ISSUE during rehearsal, every time, before you start recording.**

Both traps are properties of the local emulator only. The deployed origin has both values
configured.

---

## 3 · THE URL — and the one that looks right and is wrong

| URL | what it serves |
|---|---|
| **`http://127.0.0.1:8791/operator.html`** | ✅ **CONTROL OF WORK.** This is the one you film. |
| `http://127.0.0.1:8791/operator` | ❌ **the MAINLINE console** |
| `http://127.0.0.1:8791/` | the MAINLINE console |

**Measured this session, and this is worth understanding rather than memorising:**

```
GET /operator.html  -> 200   5,097 B   (the operator document)
GET /operator       -> 200   4,749 B   (byte-identical to GET /)
GET /               -> 200   4,749 B
```

`static_site.py` serves any file that exists under `web/`, 404s a miss under `assets/`, and
**falls back to `index.html` for everything else**. `operator` (no extension) is not a file, so
it falls through the SPA fallback to the console. There is no error and nothing looks broken —
you simply get the wrong product, which is the worst possible failure mode for a demonstration
whose whole point is that this is *not* the console.

Fixing it means editing `static_site.py`, which this wave forbids. **The URL we film and publish
is the one with the extension.**

Within the page, the two modules are hash routes: `#/permit` (default) and `#/change`.

---

## 4 · Rehearsal — verify the world before the camera runs

```bash
# every subject resolves, and `absent` is empty
curl -s http://127.0.0.1:8791/v1/demo/subjects | head -c 400
```

Expect `permit_id`, `cr_id`, `check_id`, `receipt_id`, `clause_uuid`, `commit_id`, `run_id`,
`site_code` all populated and `"absent": []`.

**Then open `/operator.html` and confirm, on screen:**

| # | check | expected |
|---|---|---|
| 1 | status chip | **`dispositioned`**, verbatim, beside the seven-value alphabet |
| 2 | reference | `DEMO-PTW-0001` |
| 3 | hazard card | `DEMO-INC-0001`, **14 March 2019 06:20 UTC**, severity gate 4 |
| 4 | the three loop rows | `RECALLED` / `SHOWN TO` / `STATUS`, with `STATUS` showing **OPEN** |
| 5 | clause | the `SYNTHETIC —` stored-energy sentence, verbatim, anchors `LOTO` `ZERO_ENERGY` |
| 6 | signature block | element 10 signed by `demo.signer` as **Acceptor**; 9, 12, 13 **unsigned**; 11 **omitted** |
| 7 | PPE | `not carried by this deployment` |
| 8 | action bar | `1 obligation outstanding` |
| 9 | origin strip | the origin, and `local_furl` |

**Press ISSUE once** and confirm all four beats:

```
[1] read                     00000
[2] merge                    23514  REFUSED  gate_closed_when_issued
[3] projection_drift_attack  P0001  REFUSED  mainline.fn_permit_merge_gate
[4] admit                    00000  ADMITTED
VERDICT PROVEN · rolled_back · self_persisted false
```

Measured server-side elapsed on this machine: 0.011 / 524 / 330 / 291 ms; one round trip,
1.27 s wall. **Times vary and that is fine — they are measured, not scripted.**

Then switch to `#/change` and confirm state **`checks_materialised`**, reference
`DEMO-MOC-0001`, `open_blocking` **1**, the five OSHA headings, the IChemE ribbon, and the
disabled `Approve change` control with the **404 route table** printed beside it as the reason.

---

## 5 · Filming

1. **Devtools open, Network tab visible, at least once.** The single most valuable ten seconds
   available: press ISSUE with the network panel showing **one** `POST /v1/demo/gate-run` and
   four beats coming back in that one response. A judge who sees that stops wondering.
2. **Do not crop the origin strip.** §0.
3. **Show beat 4.** A gate that always refuses is broken, not safe. The film does not end on a
   refusal.
4. **Beat 3 is the strongest thing here.** Somebody forces the counter to zero out of band and
   the gate refuses anyway, because it re-derives from the obligations instead of trusting the
   number. Give it room.
5. **Type into the typed fields on camera.** Elements 1, 3, 5 and the change screen's proposed
   wording are empty by design. Typing them on camera is what proves they were never data.
6. **The language rulings in `COPY.md` §1 apply to the voice-over, not only to the screen.**
   Past tense for the recall; `dispositioned` and `checks_materialised` spoken as spelled; the
   incident is 2019 and nobody was hurt in it; "this run wrote nothing" rather than "the
   database is unchanged".

---

## 6 · Shutdown

```bash
# stop local_furl with Ctrl-C, or kill the background task that owns port 8791
```

`local_furl` writes nothing to the tree. The gate run writes nothing to the database: it opens
one `SERIALIZABLE` transaction and rolls it back, and `self_persisted false` is the payload's
own reading of that. You may run it as many times as you like during rehearsal.

---

## 7 · If something is wrong

| symptom | cause | fix |
|---|---|---|
| screen shows `no permit subject to address` | subjects did not resolve | §2 trap 1 — `--database mainline_demo` |
| reads fine, ISSUE returns a problem panel | gate run has no permit | §2 trap 2 — `--permit-id` |
| the MAINLINE console appears instead | wrong URL | §3 — use `/operator.html` |
| `Module not in this build` | screen module missing from the bundle | rebuild; check `dist/operator.html` exists |
| boot notice never disappears | the bundle threw at import | browser console; check `assets/` deployed beside `operator.html` |
| origin strip says `absent` locally | you are not on the emulator | you may be on the deployed origin — **stop and check before filming** |

**Do not "fix" any of these by editing a value into the page.** Every one of them is a real
condition with a real cause, and the screens are built to say so.

---

## 8 · Verification status of this runbook

**Followed end to end by its author (W8) on 2026-08-15**, from a clean `dist/`, reaching a
working `/operator.html` against the local emulator with all four beats and `VERDICT PROVEN`.
The two traps in §2 were found by hitting them.

**Outstanding, and it is a real gap:** the completion bar for this document is that it be
followed end to end **by someone other than its author**. That has not happened. Nothing in it
is unverified, but a runbook is also a test of whether its instructions are legible to somebody
who did not already know the answer, and that test has not been run. **Recommended: W7 or the
orchestrator walks §1–§4 cold and reports back.**
