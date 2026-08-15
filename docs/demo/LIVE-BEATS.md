<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# LIVE BEATS — the four beats, taken off the deployed URL in one sitting

**Artefact:** [`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json)
**Producer:** [`scripts/proof/live_beats.py`](../../scripts/proof/live_beats.py)
**Owner:** proof-and-polish worker **P2**. Ruling **R4** of
[`docs/demo/proof-and-polish-plan.md`](proof-and-polish-plan.md) binds it.

The film shows a refusal landing inside an operator screen. A judge who believes the screen is
believing a pixel. This is the receipt behind the pixel: eleven HTTP requests to the deployed
demo, in order, in one sitting, with the SQLSTATE the database produced against every beat and a
byte count and two different clocks against every line.

---

## The command, and the date

```bash
.venv/Scripts/python.exe scripts/proof/live_beats.py \
  --base-url https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

| | |
|---|---|
| **taken** | **2026-08-15T14:11:35Z** (UTC; 2026-08-16 00:11 local, UTC+10) |
| exit code | **0** |
| verdict | **PROVEN**, `failures: []`, `transport_failures: []` |
| requests | **11** — 9 `GET`, 1 `POST /v1/demo/gate-run`, 1 documented `423` trap |
| bytes back | 55,099 over the eleven |
| credentials | **none.** No DSN, no AWS profile, no token, no knowledge of the seed |
| target | `ok: true` · `mainline_demo` · deploy chain **271 of 271** · `migrations_applied: 0` |
| cluster | `CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)` |
| schema fingerprint | `ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339` |

Every identifier in the run was **discovered**, not typed: `GET /v1/demo/subjects` is the only
source of the permit id, the change-request id and the obligation id, and
`mainline_demo_api.subjects` answers it entirely out of `SELECT`s. Point the same command at a
differently-seeded deployment and you get a transcript of *that* deployment rather than a
mismatch against this one.

---

## The four beats, as they came back

One `POST /v1/demo/gate-run`. One SERIALIZABLE transaction. Three savepoints. `ROLLBACK` at the
end, beat 4 included.

| # | beat | SQLSTATE | outcome | exhibit | `constraint_source` | server ms |
|---|---|---|---|---|---|---|
| 1 | `read` | `00000` | READ | — | — | 0.011 |
| 2 | `merge` | `23514` | **REFUSED** | `gate_closed_when_issued` | **`reported`** | 445.753 |
| 3 | `projection_drift_attack` | `P0001` | **REFUSED** | `mainline.fn_permit_merge_gate` | **`parsed`** | 449.649 |
| 4 | `admit` | `00000` | **ADMITTED** | `clearance_digest` (below) | — | 376.922 |

```
84a2fb4a213ac58de9114b3fb31a73cdcb6c4209dd3a4ee2800818966eed6aac
```

That digest is **observed, not asserted**. The server computes it over the sorted
`(check_id, disposition_id)` set and the disposition is minted fresh inside every run, so the
next run produces a different one; what the transcript asserts is that an admission arrives with
a server-computed exhibit of the right shape. An `ADMITTED` with no exhibit is an assertion, not
evidence.

**Beat 3 is the one to read twice.** `mainline.permit.open_blocking` is forced to zero out of band
— exactly what a disarmed projector or a careless `UPDATE` leaves behind — so beat 2's CHECK is
now satisfied and *would* admit the merge. It is refused anyway, because
`mainline.fn_permit_merge_gate` re-derives the open count from
`blocking_check LEFT JOIN disposition` instead of trusting the column. The kernel's own words,
recorded verbatim in the transcript:

> MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is
> 1 while the projected counter reads zero

**Beat 4 is not decoration either.** A gate that always refuses is broken, not safe. One signed
disposition closes the counter through the projection trigger and the same merge succeeds.

The transaction the four beats shared, from the payload:
`isolation: SERIALIZABLE`, `single_transaction: true` (the opened and closed
`cluster_logical_timestamp()` are equal — a read-only witness, not a claim the driver makes about
itself), `savepoints: [gate_run_beat_2, gate_run_beat_3, gate_run_beat_4]`,
`disposition: rolled_back`, `retry_sqlstate: null`. And `persisted: false` with
`persistence_check.self_persisted: false`, `minted_disposition_rows_after_rollback: 0`,
`permit_row_identical: true`.

---

## One request — four beats

```
one request — four beats — response received 2026-08-15T14:11:33Z
```

* **request id** `be1d350a-262c-42d3-9990-6cf27ed41963` — the `x-amzn-requestid` the AWS Lambda
  Function URL stamped on the response
* **run id** `0c5eb410-e56b-470d-b28a-2b457e581b8b` — the payload's own `run_id`, minted by the
  handler; distinct from the request id, which is AWS's
* **response** 10,499 bytes, `beat_count: 4`

This line exists for the operator screens. They reveal the beats one at a time, and that is
defensible **only** because all four arrived in one response body, under one request id, at one
timestamp — the reveal is a rendering choice, not four requests wearing a costume. The transcript
asserts that exactly one gate-run request was sent, so the claim cannot quietly stop being true.

The corollary binds the screens: **any delay a viewer sees between beats belongs to the screen and
must never be narrated as database latency.**

---

## Two clocks, and why they are never added together

Every recorded request carries **`wall_ms`** — this machine's monotonic clock around the round
trip: DNS, TLS, the trip to `ap-southeast-1` and back, any cold start, JSON parsing — and
**`payload_elapsed_ms`**, which is what the *server* said about itself, taken from a JSON pointer
recorded beside the number. They measure different things, and conflating them is how a demo ends
up narrating its own reveal delay as database latency.

| # | request | status | bytes | `wall_ms` | `payload_elapsed_ms` | pointer |
|---|---|---|---|---|---|---|
| 1 | `GET /v1/demo/subjects` | 200 | 8,941 | 778.9 | — | — |
| 2 | `GET /v1/health` | 200 | 410 | 699.6 | 12.5 | `/seconds` (× 1000) |
| 3 | `GET /v1/permits/{permit_id}` | 200 | 5,691 | 826.8 | — | — |
| 4 | `GET /v1/permits/{permit_id}/blocking-checks` | 200 | 2,408 | 705.8 | — | — |
| 5 | `GET /v1/permits/{permit_id}/silence` | 200 | 2,386 | 731.4 | — | — |
| 6 | `GET /v1/change-requests/{cr_id}` | 200 | 3,295 | 797.5 | — | — |
| 7 | `GET /v1/ledger` | 200 | 9,505 | 726.1 | — | — |
| 8 | **`POST /v1/demo/gate-run`** | 200 | 10,499 | **2,111.0** | **1,414.96** | `/data/elapsed_ms` |
| 9 | `GET /v1/permits/{permit_id}` (after the run) | 200 | 5,691 | 795.4 | — | — |
| 10 | **`POST /v1/permits/{permit_id}/merge`** — TRAP | **423** | 582 | 679.3 | — | — |
| 11 | `GET /v1/permits/{permit_id}` (after the trap) | 200 | 5,691 | 802.7 | — | — |

**A dash is not a zero.** A read envelope on this API carries `observed_at` and `server_date` and
**no duration at all**, so `payload_elapsed_ms` is `null` there and the pointer is `null` too. An
absent measurement is written down as absent, never as the wall clock wearing a server's name.

Three levels on the gate run, and the transcript keeps them apart:

```
wall_ms                 2111.0     this client, around the round trip
payload_run_elapsed_ms  1414.96    the server, about the whole run
beat_elapsed_ms_sum     1272.335   the server, about the four statements
network_and_cold_start  696.04     wall − payload, and nothing more is claimed about it
```

---

## The `423` is a DOCUMENTED TRAP, not a refusal — ruling R4

`POST /v1/permits/{permit_id}/merge` against the seeded subject answers:

```
423 Locked
{ "error": "demo_subject_write_protected",
  "use_instead": "POST /v1/demo/gate-run",
  "subject_id": "dec0de00-0006-4000-8000-000000000001",
  "detail": "This is the seeded demo subject, and it is a single shared copy that a hundred
             judges read. Every transition on this path is irreversible on it … Drive the gate
             through POST /v1/demo/gate-run …" }
```

It is a **write protection on a shared public row**, not the gate refusing. It carries no
SQLSTATE, no constraint and no MUS. It is recorded in the transcript **once**, under
`documented_traps`, labelled `"DOCUMENTED TRAP — NOT A REFUSAL"`, with its `use_instead` — and the
reason it is there at all is so that **no operator screen ever wires an ISSUE button to it.** A
`423` rendered in a refusal banner is a fabricated exhibit in front of a judge.

Authority: [`docs/deploy/gate-run-contract.md`](../deploy/gate-run-contract.md) §7.

That is the only non-`GET` this program sends besides the gate run. No `DELETE`, no `PUT`, no
second `POST` of any kind — and the transcript asserts that about **its own request list**
(`request_discipline`: `{"GET": 9, "POST": 2}`, `gate_run_count: 1`, `trap_count: 1`) before it
prints a verdict.

---

## The rollback, proven from outside

`persisted: false` is the server's word about itself. So the permit is re-read on a **different
endpoint, a different code path and a different transaction** — after the gate run, and again
after the trap — and the four fields that must not move are compared:

| field | before | after gate run | after trap |
|---|---|---|---|
| `state` | `dispositioned` | `dispositioned` | `dispositioned` |
| `open_blocking` | `1` | `1` | `1` |
| `gate_epoch` | `1` | `1` | `1` |
| `head_seq` | `2` | `2` | `2` |

`open_blocking` is the one that carries the argument. Beat 4 signs a disposition, which closes the
obligation and takes the counter to zero; if that survived the rollback, the next judge would see
a permit that merges with no refusal at all and the demo would silently stop demonstrating
anything.

---

## The world the transcript read, before it drove anything

| surface | what came back |
|---|---|
| permit | `DEMO-PTW-0001`, state `dispositioned`, `open_blocking 1`, `open_blocking_derived 1`, `gate_epoch 1`, `head_seq 2` |
| obligation | one, `open: true`, origin `blame_ancestry`, clause `7.3.2(b)`, **severity `4`**, **virulence `blood_major`** |
| precursor | `DEMO-INC-0001`, occurred **2019-03-14T06:20:00Z**, `severity_gate 4` |
| silence | PER `n 1`, `s 1`, `theta 0.35`, issued `2026-08-02T03:00:05Z`, corpus root and candidate root both present |
| change request | `DEMO-MOC-0001`, state `checks_materialised`, `merged_commit: null` — it **proposes** an edit and is unmerged |
| ledger | 4 leaves, 3 nodes, 2 checkpoints, 2 cosignatures, 6 inclusion proofs, 1 consistency proof, `unwitnessed_debt: []` |

**Where the `4` came from, because a `4` with no provenance is a number somebody could have
typed.** The seed supplies `0` / `routine`; `mainline.fn_check_project` overwrites both from
`mainline.clause_blame_current` under invariant MI25
([`docs/deploy/cloud-database.md:808`](../deploy/cloud-database.md)). Reading `4` / `blood_major`
back over HTTP is how you know the projection ran. Nobody typed the four.

The obligation's own `evidence_summary` begins `SYNTHETIC —`, and the transcript records it that
way. The history is synthetic; the refusal is not.

---

## What this transcript does **NOT** prove

Written down here as well as in the JSON, because an aperture a reader has to infer from what is
absent is not an aperture.

1. **Nothing about the console or the operator screens.** No browser ran; this is an HTTP client.
   That a screen renders these bytes is a separate claim with separate evidence.
2. **Not that the seeded history is true of the world.** It is SYNTHETIC and the payload says so
   in its own `evidence_summary`. What is proven is that the gate re-derives from it.
3. **Not that the store is CockroachDB Cloud** rather than any PostgreSQL-wire server. What is
   recorded is the `cluster_version` string the deployment reported about itself.
4. **Not that beat 4's signature was verified by an authenticator.** The WebAuthn assertion is
   synthesised and the envelope declares `staged`; only the projected columns are real
   (`gate-run-contract.md` §7).
5. **Not a latency figure for a judge's network.** `wall_ms` is one machine's path to one region
   at one hour with an unknown warm/cold state — a measurement, not a service level.
6. **Not that the endpoint behaves this way for every subject.** One seeded subject was driven,
   once, and the transcript names it.
7. **Not that nothing will ever persist.** The permit is re-read twice and compared field by
   field, which proves this rollback happened — not that every future one will.
8. **Not that the `423` trap is unreachable from a user interface.** It proves the API refuses it.
   Keeping it off an ISSUE button is the screen's job, and this transcript is the reason why.

It also proves nothing about the *suite*: 988 / 987 / 0 / 0 / 1 is worker **P4**'s bracket, not
this file's.

---

## How to falsify it

A guard nobody has driven red is decoration, so this one can be driven red offline, with no
network and no evidence file written:

```bash
.venv/Scripts/python.exe scripts/proof/live_beats.py --self-test
```

Eight cases. The first changes nothing and **must stay silent** — a checker that fails on
everything is as useless as one that fails on nothing. The other seven each move exactly one
thing away from the contract and must produce a failure line: beat 3's SQLSTATE moved
`P0001 → 23514`; beat 2's constraint renamed; beat 3 claiming `reported` provenance the platform
cannot supply; beat 3 growing a nearest-admissible answer it cannot compute; beat 3's MUS
emptied; beat 4 admitting with no clearance digest; beat 4's digest not a SHA-256. Measured
2026-08-15: `SELF-TEST PASSED - 8 cases, and the assertions can go red`.

The payloads that self-test mutates are **synthetic negative controls**. They are never written to
`evidence/`, never printed as an outcome, and are reachable only from `--self-test`.

### Exit codes

| code | meaning |
|---|---|
| `0` | `VERDICT PROVEN` |
| `1` | `VERDICT NOT PROVEN` — a beat, an exhibit, a trap or an invariant differs |
| `2` | usage |
| `3` | the target could not be reached at all (transport, before any status came back) |

**The SQLSTATEs are asserted here, not read off the server's own verdict.** A different SQLSTATE
is a regression even when a verdict still says `PROVEN`, and that is exactly the case a run that
trusted the server's self-assessment would miss.

---

## Beat 3's diagnosis is recorded weak, on purpose

On its strongest refusal the system reports that it **cannot compute a nearest admissible
answer**, and the transcript records every part of that verbatim rather than tidying it away:

```json
"constraint_source": "parsed",
"diagnosis": "none",
"naa": null,
"naa_reason": "not_computable",
"mus": [{ "kind": "capability_gap", "capability": "mainline.fn_permit_merge_gate" }],
"probe_calls": 0,
"spec_version": "1.0.0-rc.1",
"profile": "mainline"
```

The single MUS atom's `detail`, verbatim: *"outside the declarative decomposition; the general
algorithm is QuickXplain over savepoint probes, in a separate transaction and never on the
completion path"*.

`trappoint.explain_refusal` has no declarative decomposition for `mainline.fn_permit_merge_gate`,
so it says so instead of shipping a plausible superset labelled `declarative` — the failure
invariant **I14** exists to prevent exactly that. And `parsed` rather than `reported` is not
pedantry: CockroachDB populates no PL/pgSQL context stack, so `diag.constraint_name` and
`diag.context` are both `None` on a `RAISE`, and the object's name is recovered from the kernel's
own *"refused by `<schema>.<object>`"* clause. **A run whose exhibits were inferred must never
look like a run whose exhibits were reported.**

A system that names where its own explanation engine stops is making a Product-Readiness claim.
All four values above are asserted, so the day `naa` starts arriving non-null, this transcript
goes red and somebody has to say why.

---

## Reproducing it, as a stranger

Python 3.13 and the URL. No credential, no database, no AWS access, no local node.

```bash
.venv/Scripts/python.exe scripts/proof/live_beats.py \
  --base-url https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

Expect exit `0`, `VERDICT PROVEN`, and a transcript at
`D:/CoackroachDBxAWS/mainline/evidence/demo/live-beats.json` — with **different** timings, a
**different** `x-amzn-requestid`, a **different** `run_id` and a **different** `clearance_digest`.
Those four moving is the correct outcome. The SQLSTATEs, the constraint names, the two
`constraint_source` values and the permit's four invariant fields are what must not move.

### What this file does not duplicate

* [`scripts/deploy/demo_acceptance.py --phase2`](../../scripts/deploy/demo_acceptance.py) drives
  the gate **twice** and compares the two stable projections. `live_beats.py` imports its
  `EXPECTED_BEATS` table, its `check_beats`, its `fetch` and its permit-snapshot helpers rather
  than restating them — a second copy of the beat table would be a second place for it to be
  wrong.
* [`scripts/deploy/judge_walk.py`](../../scripts/deploy/judge_walk.py) walks every request the
  console artefact declares. `live_beats.py` imports its `mask` and `say`, so every string that
  reaches stdout and the **whole** evidence document are masked for DSNs, URL credentials,
  password/token pairs and 12-digit account ids — and then the four SQLSTATEs and the clearance
  digest are re-checked *after* masking, because a masker that quietly rewrote a measured value
  would be worse than no masker at all.

What neither produces, and this one does, is the **composed transcript of a single sitting**: the
world read, the gate driven, the rollback re-read, the trap labelled, eleven requests in one
ordered list with a byte count and two clocks against every line.
