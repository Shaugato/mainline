<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# What is on the demo address today, and what we do not claim over it

`README.md` says the demo refuses live. This page is the audit trail behind that sentence: which
beats each use case plays, which it declines to play and why, and which readings of our own
committed artefacts we have superseded. It exists because the README's first sixty seconds
should not be spent on forensics, and because the forensics should not therefore disappear.

The address is
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`.

---

## 1 · Use case two is short two beats, and names both rather than filling them in

**`admission_beat: null`.** Nothing is signed off in this run. Signing needs a receipt proving
this obligation was actually shown to somebody; no such row exists for this change request, and
the demo's database login may read `mainline.exposure_receipt` but may not write to it.

**`kernel_procedure_beat: null`.** The database's own merge procedure,
`CALL mainline.merge_change_request(…)`, is not played. Under that same login it answers
`42501`, a privilege error, before the gate is ever reached — and a privilege error shown as a
gate refusal would be a fabricated exhibit.

Both reasons are quoted from the payload's own fields:
`qa/live2.json#data.admission_absent_reason`, `#data.admission_absent_grants`,
`#data.kernel_procedure_absent_reason`, `#data.kernel_procedure_absent_sqlstate` = `42501`.
The grant rows those fields cite are `db/GRANTS.yaml:644`, `:647` and `:761`.

**Use case one does have the admission beat, and it answers `00000`.** A gate that always
refuses is broken, not safe, so that beat is not optional — it is missing from *this run*, not
from the demo.

---

## 2 · Is use case two live on that address? Both readings, with their dates

The committed artefacts disagreed, so both are here.

| when | artefact | what it recorded |
|---|---|---|
| **2026-08-16T04:41Z** | [`evidence/deploy/cr-gate-live.json`](../../evidence/deploy/cr-gate-live.json), [`qa/cr-gate-live.json`](../../qa/cr-gate-live.json) | `POST /v1/demo/cr-gate-run` answered **404** on this origin; `verdict: UNANSWERABLE` |
| **2026-08-16T21:11:57Z** | [`qa/live2.json`](../../qa/live2.json) | `verdict: PROVEN`, with beats `00000` · `23514 cr_gate_closed_when_merged` · `P0001 mainline.fn_cr_merge_gate` |

A route that was never deployed is not a gate that failed to refuse, and the 04:41Z files draw
that distinction themselves, in a field named `this_is_not_a_gate_that_failed_to_refuse`. The
newer file reads `PROVEN` — but the origin's hostname appears nowhere in it, so on its own it
does not say **where** it ran.

**So we checked, read-only, on 2026-08-17, and sent no `POST`.** A `GET` of
`/v1/demo/cr-gate-run` answered **`405`**, `{"allow": ["POST"], "detail": "/v1/demo/cr-gate-run
exists but not for GET"}`, and `GET /v1/health` answered `200` with `ok: true` at
`server_date 2026-08-17T15:16:05Z`.

**The route is deployed today, and the 404 reading is superseded.** We have not driven a `POST`
through the public origin ourselves, so **we do not claim use case two beat-for-beat over that
address**. Use case one we do claim over it, because its artefact names the address it ran
against.

---

## 3 · The two operator screens are on the origin now

This is a correction. Measured **2026-08-15**, `GET /operator.html` returned the console shell
byte-for-byte identical to `GET /` — which is what a not-yet-deployed second entry point looks
like — and the README said so.

Re-checked read-only on **2026-08-17**: the two documents now differ, and `/operator.html` is
byte-for-byte identical to `verticals/mainline/apps/console/dist/operator.html` in this tree —
the same content hash, `a7a685e8…`. A **content hash** is a fingerprint of a file's bytes; two
files with the same one hold the same bytes. Its script and its stylesheet answer `200` as well.

**What we checked is that the entry point is served. We did not drive the screens.**

---

## 4 · What each use case does claim

| | **1 · Permit to work** | **2 · Management of change** |
|---|---|---|
| beats | read `00000` · merge refused `23514 gate_closed_when_issued` · forged count refused `P0001 mainline.fn_permit_merge_gate` · admit `00000` | read `00000` · merge refused `23514 cr_gate_closed_when_merged` · forged count refused `P0001 mainline.fn_cr_merge_gate` |
| left the world unchanged | `persisted: false` | `persisted: false` |
| artefact | [`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json) — `verdict PROVEN`, `2026-08-15T14:11:35Z`, `base_url` is the address above, `target_is_local_emulator false`, no credential used | [`qa/live2.json`](../../qa/live2.json) — `verdict PROVEN`, `generated_at 2026-08-16T21:11:57Z` |
| claimed over the public address | **yes** — the artefact names the address | **no** — see §2 |

`persisted: false` means the whole run rolls back and leaves the world as it found it. Use case
two's payload proves that twice over: the counter its attack beat forces to zero is a value only
that run wrote, and it is read back at `1` after the savepoint rollback and again at `1` after
the transaction rollback [`qa/live2.json#data.persistence_check.self_evidence`].
