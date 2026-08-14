<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# LATENCY — how long each demo beat actually takes, and what that does to the bill

**Owner:** W1 (cost-bound) · **Measured:** 2026-08-13, this workstation
**Harness:** `scripts/deploy/measure_beats.py` · **Evidence:** `evidence/deploy/cost/latency-baseline.json`

> **ANNOTATED 2026-08-14** by W2 (latency-truth) of the docs-and-deploy wave, at HEAD
> `eefae1c`. **No measurement in this document was changed and none was deleted.** Every digit
> below is the one the harness produced on 2026-08-13, to the precision
> `latency-baseline.json` carries it. What moved is **tense, tree and sourcing**: several rows
> describe the packer's **input** tree, which no longer deploys, while reading as though they
> described the shipping origin.
>
> Those rows are annotated in place, in the idiom `docs/deploy/COST-BOUND.md` already uses —
> **a claim deleted is not a claim corrected**, and the correction is only checkable against
> the claim it corrects. Deleting them would also orphan a live consumer:
> `COST-BOUND.md` §0.1 row **L1** is built on **14.106 ms**, which is exactly this document's
> `asset_map` local p50, and that row carries the largest honesty finding in the cost
> documentation.
>
> **Annotated sections: §0.1 (new), §0, §1.1, §1.2, §5.1, §5.2, §6.1, §6.2, §6.3, §7.**
> One statement was **corrected** rather than annotated — the fourth sentence of headline 2,
> which was false against `evidence/deploy/terraform-plan-furl.txt:315`. It is struck through
> with the artefact quoted beside it.

Nothing here was applied. No `terraform` command was run to produce it and no mutating AWS
call was made. The only writes anywhere near this page are the gate run's own, and the gate
run rolls its transaction back — `persisted: false` in 200 of 200 samples.

---

> ## The four sentences that matter
>
> 1. **A warm four-beat gate run takes about 1.3 seconds, not 100 ms.** Measured 1,340 ms p50
>    against the local container and 11,256 ms p50 against CockroachDB Cloud in
>    `ap-southeast-1` from a workstation 223 ms away, which corrects to **3,729 ms p99** for a
>    Lambda in the same region as the cluster.
> 2. **The founder's requested `timeout = 3 s` is not honest.** It is 0.80× the corrected warm
>    p99 (3,000 / 3,729 = 0.804) and 0.46× the modelled cold start at 256 MB
>    (3,000 / 6,511 = 0.461). It would truncate the headline beat on a warm invocation, never
>    mind a cold one. The measured floor is **14 s**, ~~which is one second below where the
>    plan already sits~~.
>
>    > **CORRECTED 2026-08-14 against the artefact. The plan does not sit one second above the
>    > floor. It sits ON it.** `evidence/deploy/terraform-plan-furl.txt:315` reads
>    > `+ timeout = 14`, and `infra/envs/demo/terraform.tfvars.example:105` reads
>    > `api_timeout_seconds = 14`. **Authority:** `docs/deploy/terraform-plan.md` §0.1 — *"the
>    > committed plan artefact is authoritative and this prose is derived"* — enforced by
>    > `tests/deploy/test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence`,
>    > whose own message ends *"Do NOT edit the evidence file to match the documents."* The
>    > artefact was not touched; this sentence was.
>    >
>    > **The margin this sentence claimed does not exist**, and that is the material change.
>    > Against §5.1's binding case of **13,022.9 ms**: a 15 s plan cleared it by
>    > **1.152×** (15,000 / 13,022.9), a 14 s plan clears it by **1.075×** (14,000 / 13,022.9).
>    > The spare second was **7.5 points of headroom**, and it is gone. §5.1 already called
>    > 1.07× *"very little margin"*; it is now the whole of it. **That is a reason to hold 14 s,
>    > not to lower it** — and per §5.1 `timeout` is a **RELIABILITY** bound, not a spend bound:
>    > Lambda bills actual duration, so a 100 ms invocation costs the same under 14 s as under
>    > 3 s. Raising `timeout` to give an alarm room is forbidden in terms by
>    > `infra/modules/demo-api/main.tf:752` — *"do not raise timeout to make an alarm fit."*
> 3. **`memory_size` 512 → 256 MB costs the headline beat almost nothing**, because the gate
>    run is database-bound: 1,245 ms of its 1,337 ms server-reported time — **93 %** — is
>    CockroachDB executing three statements, not Lambda computing.
> 4. **The byte levers are worth far less than their byte ratios suggest.** A response costs a
>    fixed **1.6 ms** plus **8.2 ns per byte**, so shrinking an object shrinks its duration
>    less than proportionally, the request rate rises, and most of the saving is handed back.
>    ~~Stripping~~ **Stripping the source maps REMOVED** — it landed on 2026-08-13 and the
>    deployed package holds **zero** maps (§0.1) — **72 % of the bytes** and **22 % of the
>    worst-case bill**. §6 is the arithmetic, and it disagrees with the plan's prediction by
>    about 3×. **The percentages are unchanged; only the tense is.**

---

## 0 · What was run

`scripts/deploy/measure_beats.py` starts `scripts/deploy/local_furl.py` as a subprocess and
drives it over a real TCP socket. `local_furl` is this repository's existing in-process
Function URL emulator: the real `mainline_demo_api.app.handler`, the real payload-format-2.0
encode and decode. **No emulator was written for this measurement.** What the harness adds is a
clock, an ordering discipline and a percentile.

Five beats, against two database targets:

| Beat | Request | Why this one |
|---|---|---|
| `index` | `GET /` | the document a judge's browser asks for first |
| `asset_js` | `GET /assets/index-BjAGxrVJ.js` | largest **non-map** object in the served tree — M5, 433,396 B. **This is the beat that still names a URL the deployed origin answers** — §0.1 |
| `asset_map` † | `GET /assets/index-BjAGxrVJ.js.map` | largest **emittable** object — M4, 1,554,168 B. **† ANNOTATED: emittable by the tree this harness served, which is the packer's INPUT tree. The DEPLOYED origin answers 404 to this path** — §0.1 |
| `health` | `GET /v1/health` | the cheapest database beat |
| `gate_run` | `POST /v1/demo/gate-run` | the headline four-beat gate run — the beat that decides the timeout |

| Target | Cluster | Database | Seed |
|---|---|---|---|
| `local` | `trappoint-crdb`, CockroachDB v26.2.5, one node | `w_w1_cost` | the proof seeder |
| `cloud` | CockroachDB Cloud **Basic**, `aws-ap-southeast-1` | `mainline_demo` | `demo_world.sql` |

### 0.1 · ANNOTATED 2026-08-14 · which tree these beats were served from, and which of them the deployed origin still answers

**This is a correction of tense, tree and sourcing. No number in this document moved and none
was removed.**

`measure_beats.py` starts `local_furl.py` as a subprocess, and `local_furl.DEFAULT_WEB_ROOT`
(`scripts/deploy/local_furl.py:101`) is
`verticals/mainline/apps/console/dist` — **the packer's INPUT tree**. Counted on this machine
today, that directory holds **18** source maps, `index-BjAGxrVJ.js.map` among them at
**1,554,168 B**. That is why `asset_map` answered `200` in 200 of 200 samples on both targets,
and why the evidence records `status_ok: true` and `cold_status: 200` for it. **The
measurement is real and it was taken correctly.**

**The tree that deploys is a different tree.** `scripts/deploy/build_lambda.{sh,ps1}` strips
`web/**/*.map` **by default** — `build_lambda.ps1:219`, *"Stripping is the default as of
2026-08-13"*; `build_lambda.sh:121`, *"`--strip-source-maps` accepted, and already the
default"*. Read out of the built artefacts today with `zipfile` over the central directory:

| | `web/` entries | bytes | source maps | largest identity | largest `.gz` |
|---|---:|---:|---:|---:|---:|
| the packer's **input** tree — what this harness served | 75 | 3,571,990 | **18 / 2,586,960 B** | **1,554,168 B** `index-BjAGxrVJ.js.map` | none |
| the **deployed** package — `out/lambda/mainline-demo-api-{arm64,x86_64}.zip` | 114 | 1,274,342 | **0 / 0 B** | **433,396 B** `index-BjAGxrVJ.js` | **124,127 B** `index-BjAGxrVJ.js.gz` |

Both architectures are byte-for-byte identical on that row, and **neither zip contains an entry
named `index-BjAGxrVJ.js.map`.** `static_site.py` answers a miss under `/assets/` with a
**404 `asset_not_found`** (`static_site.py:940-941`) rather than the SPA fallback, because those
are file prefixes and not routes. Therefore:

> **`GET /assets/index-BjAGxrVJ.js.map` against the shipping origin is a 404.** The `asset_map`
> rows in §1.1, §1.2, §6.1, §6.2 and §6.3 are **true measurements of a tree that no longer
> deploys.** They are not measurements of the deployed origin and must not be read as any.

#### What a request actually gets today — measured on this machine, 2026-08-14

Not modelled. The `web/` tree was extracted from `mainline-demo-api-arm64.zip` and
`static_site.serve()` was called against it with the ceiling in force
(`DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024 = 139,264`):

| Request | `Accept-Encoding` | Status | Bytes on the wire | `content-encoding` |
|---|---|---:|---:|---|
| `GET /` | — | **200** | **4,655** | — |
| `GET /assets/index-BjAGxrVJ.js` | `gzip` | **200** | **124,127** | `gzip` |
| `GET /assets/index-BjAGxrVJ.js` | — | **413** `response_too_large` | 693 (the refusal) | — |
| `GET /assets/index-BjAGxrVJ.js.map` | `gzip` or — | **404** `asset_not_found` | 288 (the refusal) | — |
| `GET /assets/index-BjAGxrVJ.js.gz` | `gzip` | **404** `asset_not_found` | 468 (the refusal) | — |

Three things follow, and the second is stronger than the defect this annotation was opened for:

1. **`asset_js` is the beat that describes a URL a request can reach today.** Its measured
   figures stand as taken: **5.66 ms p50 local / 11.45 ms p50 cloud**, over **433,396 B**
   identity.
2. **But 433,396 B is not a body this origin emits.** On the identity path the ceiling refuses
   that object with a **413**, deliberately and in writing — `static_site.py:257-267` names
   this as *"exactly one object of the 57"* and says so out loud rather than dodging it. **The
   largest body the deployed origin actually puts on the wire is the 124,127 B gzip sibling**,
   which is what every browser receives, because every browser sends `Accept-Encoding: gzip`.
   A figure of 433,396 B is an *on-disk* size, not a wire size.
3. **The `.gz` sibling has no URL of its own.** It is served under the identity URL when
   `Accept-Encoding` permits gzip (`static_site.py:70-74`, `:526-532`); asking for the `.gz`
   path directly is itself a 404. So there is no "gzip beat" to point at — there is one URL
   with two answers.

#### Which side is authoritative, and why not one digit here moved

**Authority:** `docs/decisions/response-ceiling-authoritative-tree.md` **§1** — *"**Ruling: the
deployed tree.** Cost is incurred by bytes leaving the deployed origin, so an object that never
reaches the deployed package cannot be evidence about a cost control."* That ruling governs the
**label and the tense**, not the arithmetic. The measurements stay, for three reasons that are
checkable rather than sentimental:

1. **`COST-BOUND.md` §0.1 row L1 consumes `14.106 ms`** — this document's `asset_map` local
   p50, to the digit `latency-baseline.json` carries. That row is the largest honesty finding
   in the cost documentation (a published headline understated **×6.91**, $33,251.87 →
   $229,804.98). Delete the beat and the honest "before" is orphaned.
2. **A claim deleted is not a claim corrected** — `COST-BOUND.md`'s own preservation rule.
3. **The pre-strip beat is the denominator.** §6.2's ratios are ratios *of* it: remove the
   1.000× row and the 0.777× and 0.439× rows below it lose the thing they are a share of.

**UNRESOLVED — the 124,127 B path has a measured size and no measured duration.** No beat in
`latency-baseline.json` sent `Accept-Encoding: gzip`; all five were identity requests. §6.2
*fits* the sibling at **2.60 ms**, which is a least-squares extrapolation off three identity
beats, not an observation. **What would settle it:** re-run §9 with a sixth beat —
`GET /assets/index-BjAGxrVJ.js` with `Accept-Encoding: gzip`, asserting
`content-encoding: gzip` and 124,127 response bytes — against a web root extracted from
`out/lambda/mainline-demo-api-arm64.zip` rather than `console/dist`. Until that runs, no
duration for the object the origin actually ships is a measurement, and none is written here.

**Both targets ran all four beats and returned `PROVEN` in 100 of 100 samples**, with
`admit` on SQLSTATE `00000`. On the cloud that is new: BLOCKER 1's
`23503 disposition_signer_credential_id_fkey` reproduced here at 05:55 UTC and another wave
fixed it before this run started. §8 records both observations.

**One emulator process per beat.** `transitions._prepare` (`transitions.py:293-294`) and
`_demo_gate_run` (`:1032-1033`) set `conn.autocommit = False` on the module-scope connection
that `db.py:306` opened with `autocommit=True`, and never restore it. A harness that
interleaved beats in one process would measure that defect instead of the beat. §8 records what
happens when you deliberately do interleave them.

> **ANNOTATED 2026-08-14 — all three line citations in that paragraph are now stale, and so is
> its present tense.** `transitions.py` and `db.py` are two of the six modules whose digests
> moved (§7). Today: the only `conn.autocommit = False` in `transitions.py` is at **`:336`**,
> inside a `_borrowed` context manager (`:303-358`) that saves the flag and restores it in a
> `finally`; `_prepare` (**`:361`**) now *refuses* a connection handed to it in autocommit
> (**`:381-383`**); and `db._open` opens with `autocommit=True` at **`db.py:581`**, not
> `:306`. The line numbers are corrected here; **whether the defect itself still reproduces is
> UNRESOLVED and is dealt with in §8's annotation, not asserted here.** The methodological
> point — one emulator process per beat — is unaffected either way and remains the right way
> to run this harness.

**Percentiles are nearest-rank**, never interpolated: every p95 and p99 below is an observation
that actually happened, the ⌈q·N⌉-th smallest. At N = 100 the p99 is the 99th smallest and not
the maximum; the evidence sets `p99_is_max` wherever N < 100, which is only the cold probes at
N = 5.

**Every gate-run sample is counted, not just the last one.** The evidence carries
`verdict_counts`, `outcome_counts` and per-beat `sqlstate` counts over all 100 samples, plus an
`one_regime` flag. That is not decoration: an earlier run of this harness recorded one sample's
verdict and reported `PROVEN` for a set of samples that had straddled the BLOCKER 1 fix.

---

## 1 · The measurement

Wall time at the socket: request sent, to response body fully read. Five warm-up requests per
beat, discarded. Every sample on both targets answered `200`.

### 1.1 · `local` — `trappoint-crdb`, database `w_w1_cost`

| Beat | N | p50 | p95 | p99 | max | first (cold) | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| `index` | 200 | **1.23** | 1.50 | 1.71 | 1.83 | 9.1 | 4,655 |
| `asset_js` | 200 | **5.66** | 8.45 | 20.05 | 26.77 | 14.8 | 433,396 |
| `asset_map` † | 200 | **14.11** | 23.41 | 32.59 | 35.68 | 32.8 | 1,554,168 |
| `health` | 100 | **8.21** | 10.38 | 11.09 | 13.07 | 19.0 | 388–389 |
| `gate_run` | 100 | **1,339.61** | 2,705.15 | 2,974.73 | 3,130.84 | 1,432.0 | 9,362–9,368 |

### 1.2 · `cloud` — CockroachDB Cloud Basic, `ap-southeast-1`, database `mainline_demo`

| Beat | N | p50 | p95 | p99 | max | first (cold) | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| `index` | 200 | **3.65** | 5.59 | 7.32 | 7.37 | 25.2 | 4,655 |
| `asset_js` | 200 | **11.45** | 25.06 | 34.31 | 35.98 | 30.3 | 433,396 |
| `asset_map` † | 200 | **30.75** | 51.86 | 58.02 | 60.86 | 28.0 | 1,554,168 |
| `health` | 100 | **450.35** | 469.03 | 687.90 | 689.01 | 2,120.9 | 408–410 |
| `gate_run` | 100 | **11,256.07** | 11,465.98 | 11,687.74 | 12,453.22 | 12,588.1 | 9,369–9,372 |

All milliseconds.

> **† ANNOTATED 2026-08-14 — `asset_map` measures the packer's input tree, not the deployed
> origin.** See §0.1. The deployed package holds **zero** source maps and answers **404
> `asset_not_found`** to `/assets/index-BjAGxrVJ.js.map`. **Every digit in these two rows
> stands exactly as measured** — 14.11 ms p50 local is `14.106` in the evidence and is the
> input `COST-BOUND.md` §0.1 row L1 is built on. What is corrected is only what they are
> evidence *about*: the tree, and the tense.
>
> **`asset_js` — 5.66 ms local / 11.45 ms cloud — is the row that names a URL the deployed
> origin still answers.** Its 433,396 B is that object's size *on disk*; on the wire the
> ceiling in force refuses it with a **413** to any caller that does not send
> `Accept-Encoding: gzip`, and answers **200 with 124,127 B** to any caller that does. The
> `index` row needs no annotation: `GET /` returns **4,655 B** out of the deployed tree today,
> the same figure measured here.

**The static beats are this harness's own control, and they set its noise floor.** `index`,
`asset_js` and `asset_map` never touch a database, so their two rows are the same code measured
twice, minutes apart, under different machine load. They differ by **2.4 ms, 5.8 ms and
16.6 ms** at p50 — up to **2.2×** on the largest object. **That factor is the honest error bar
on every static-beat figure in this document**, and it is why §6 quotes ratios (which cancel it)
rather than absolute durations wherever it can.

**`health` makes about two round trips.** 450.35 − 8.21 = 442.1 ms of difference across a
223.1 ms hop: the liveness `SELECT 1` and the fingerprint read.

**The gate run is database work, not handler work.** On the local target the four beats
reported 0.009 + 431.795 + 417.837 + 395.256 = **1,244.9 ms** of a **1,336.6 ms**
server-reported run — 93 %. The handler's own share is under 100 ms, and the socket adds
3.0 ms on top of the server's own timer.

**A cold `health` against the cloud costs 2.1 s and a cold gate run costs 12.6 s.** Those are
the `first (cold)` column: the first request a fresh process serves, which pays the module
import and the first connection. §2 takes them apart.

---

## 2 · The cold cost, in a fresh interpreter every time

Five samples per target, each a brand-new Python process. An in-process loop would have
measured a warm import cache and reported a cold start no execution environment ever pays.

| | `import psycopg` | first connection | `SELECT 1` round trip |
|---|---:|---:|---:|
| local, p50 | 353.9 | 7.8 | 0.816 |
| local, p99 | 365.6 | 8.1 | 1.880 |
| cloud, p50 | 736.4 | 1,700.3 | 223.077 |
| cloud, p99 | 922.3 | 2,562.4 | 446.368 |

RTT is over N = 250 (50 per sample); the other two are N = 5, so their p99 **is** their maximum
and the evidence says so.

**`import psycopg` is essentially the whole cold import.** Importing `mainline_demo_api.app` —
the entire handler, not just the driver — measured 368.1, 383.9, 389.4, 401.4 and 411.9 ms in
five fresh interpreters. The driver is nearly all of it, so the psycopg figure is a faithful
stand-in for the Lambda's module-load cost.

**The two `import psycopg` samples disagree by 2.1×** (354 ms against 736 ms at p50) for the
same operation. The difference is machine load. The model in §5 takes the **smaller**, because
it then multiplies by a fractional-core penalty, and taking the larger would count one slowdown
twice.

**The first connection to the cloud is round trips, not work.** 1,700 ms at p50 over a 223 ms
hop is about 7.6 RTT — a TCP handshake, a TLS handshake with certificate verification, and the
pgwire startup exchange. In region those round trips nearly vanish; the CPU of verifying a
certificate does not, which is why §5 floors the corrected figure rather than scaling it to
nothing.

### 2.1 · A ten-second trap that is a property of this workstation and of nothing else

`db.py` sets `CONNECT_TIMEOUT_SECONDS = 10`. Measured today:

| DSN host | `connect_timeout` | psycopg connect |
|---|---:|---:|
| `127.0.0.1` | 10 | **8.7 ms** |
| `localhost` | 10 | **10,078 ms** |
| `localhost` | 30 | **30,075 ms** |

`getaddrinfo('localhost')` returns `::1` ahead of `127.0.0.1` here, the container publishes
`127.0.0.1:26257` only, and libpq waits the **whole** of `connect_timeout` on the AF_INET6
address before falling back. The cost is exactly `connect_timeout`, whatever it is set to.

This is a workstation artefact, not a Lambda property — the deployed function resolves a real
cloud hostname. It is recorded for two reasons: folding it into a baseline would have overstated
cold start by ten seconds, and **any local tool whose DSN names `localhost` is paying it
silently, once per process.** The harness names `127.0.0.1`.

---

## 3 · From "11.3 s over a 223 ms hop" to "what a Lambda in `ap-southeast-1` sees"

**Everything in this section is an EXTRAPOLATION and the evidence labels it one.**

The deployed Lambda and the cluster are both in `ap-southeast-1`; this workstation is 223.1 ms
(p50) away. The cloud gate run pays that distance once per client round trip and the Lambda
would not. Removing it needs the round-trip count, which was obtained twice, by methods that
share no term.

**Method A — derive it from the two targets.** Same handler, same code, two clusters at
different distances:

```
round_trips = (cloud_p50 - local_p50) / (cloud_rtt_p50 - local_rtt_p50)
            = (11,256.07 - 1,339.61) / (223.077 - 0.816)
            = 44.6
```

**Method B — count them from the cluster's own statistics.** Snapshot
`crdb_internal.node_statement_statistics` for `application_name = 'mainline-demo-api'` either
side of exactly one warm gate run on the local node. It attributed **79 executed statements** to
that run. Those are not 79 round trips: CockroachDB records what a UDF, trigger or stored
procedure executes *server-side*, and renders those database-qualified
(`w_w1_cost.mainline.permit`) while the statements the client actually wrote stay unqualified
(`mainline.permit`). Splitting the delta on that boundary gives **24 client statements**.
Transaction control does not appear in those statistics at all and every one of them is still a
round trip — `BEGIN`, three `SAVEPOINT`/`ROLLBACK TO`/`RELEASE` triplets, four `ROLLBACK`s:
**14 more**. Total **38** on a path where beat 4 is admitted, **36** where it refuses at the
foreign key and skips the merge `CALL` and the merge-record read. The constant carried in the
harness is **36**, and it is now the low side.

**The two methods agree to 24 %, and the disagreement is informative rather than noise.**
Method A comes out *higher* because it charges to the network everything that is not the local
run's duration — including the fact that CockroachDB Cloud **Basic** is a shared serverless tier
and executes the same gate run more slowly than a dedicated local container. Correcting with the
counted 36 leaves that residue visible where it belongs:

| | p50 | p99 |
|---|---:|---:|
| measured from this workstation | 11,256.1 | 11,687.7 |
| corrected with **method A**, 44.6 trips, 2 ms in-region RTT | 1,392.4 | 1,824.1 |
| corrected with **method B**, 36 trips, 2 ms in-region RTT | **3,297.0** | **3,729.0** |
| measured on the local container, for comparison | 1,339.6 | 2,974.7 |

Method A's corrected p50 (1,392 ms) lands within 4 % of the independently measured local p50
(1,340 ms) — exactly what you would see if Cloud Basic executed as fast as the local node. It
does not. **Method B is the conservative reading and it is the one carried forward: a warm
in-region gate run, p99 ≈ 3,729 ms.** At a pessimistic 5 ms in-region hop the figure moves by
108 ms, so the choice of in-region RTT is not worth arguing about; the choice of trip count is.

**The local p99 is deliberately NOT part of that maximum.** It is a measurement of a different
cluster and it is not a floor on what a same-region Lambda sees against CockroachDB Cloud. Its
role is the p50 cross-check above.

**What is NOT measured here:** nothing in this document ran inside `ap-southeast-1`. The 2 ms
same-region hop is an assumption, not an observation, and it is the input a reviewer should
attack first.

---

## 4 · What `memory_size` does, measured by proxy and labelled as a proxy

AWS allocates CPU to a Lambda in linear proportion to `memory_size`: **1,769 MB buys one vCPU**,
so 512 MB is 0.289 vCPU and 256 MB is 0.145 vCPU, delivered by time-slicing. That relationship
is AWS documentation, not a measurement of ours.

What *can* be measured here is whether wall time really is inversely proportional to the share
of a core a task receives. The harness reproduces a fractional core directly: the worker pins
itself to logical CPU 0, and *k* competitor processes pin themselves to the **same** core and
spin, so the worker receives 1/(k+1) of it. The operation is the handler's own hot CPU op —
`json.dumps` of the largest served object, M15 — 250 rounds per point.

| competitors | core share | ≈ Lambda memory | mean per op | slowdown | if perfectly proportional |
|---:|---:|---:|---:|---:|---:|
| 0 | 1.000 | 1,769 MB | 2.805 ms | 1.000× | 1× |
| 1 | 0.500 | 884 MB | 5.153 ms | **1.837×** | 2× |
| 2 | 0.333 | 590 MB | 8.675 ms | **3.093×** | 3× |
| 6 | 0.143 | 253 MB | 11.062 ms | **3.944×** | 7× |

**Proportionality holds at the halves and thirds and breaks down at the extreme point**, where
six spinners on one core failed to deliver their share of contention on an already-busy machine.
An earlier run of the same probe, on a quieter machine, measured 2.215× / 3.274× / 7.345× — the
1/7 point landing on 7.345× against an ideal 7×. **The probe is noisy at ±25 % and this document
says so rather than quoting the run that flatters it.**

Because of that noise the slope is **clamped at 1.0** before §5 uses it. Perfect proportionality
is AWS's documented relationship; the probe's job is to confirm it, and to make the bound
*larger* if this machine turns out worse than proportional. It is not allowed to make a safety
bound *smaller*, because a local scheduler artefact is not evidence that AWS will be generous.
The measured 0.838 is recorded beside the applied 1.0 in the evidence.

**The statistic is the mean, not the best**, and that matters. At a 0.143 share the
best-of-rounds figure was 2.127 ms — full-core speed — because some one round fitted inside a
single scheduler quantum without being preempted. A first version of this harness used the
minimum and reported a 1.08× slowdown where the truth was 7.35×.

**What this is not.** Nothing here measures an arm64 Graviton2 core, an AWS scheduler, or this
handler under a real Lambda. It establishes that *this* machine time-slices roughly
proportionally. Applying that to AWS is extrapolation and every downstream use of it is labelled
one. The Graviton2-versus-this-core ratio is unknown and is carried in §6 as a band of 1× to 2×.

---

## 5 · The recommendation

### 5.1 · `timeout` — **14 s**

The model, in three terms, each labelled:

| Term | ms | Kind |
|---|---:|---|
| warm in-region gate run, p99 | 3,729.0 | extrapolation (§3, method B) |
| `import psycopg` p99 at 0.145 vCPU | 2,526.2 | extrapolation (§4) from a measured 365.6 ms |
| first connection, in region | 256.2 | extrapolation — 10 % of the measured 2,562.4 ms, floored at 60 ms for the handshake's own CPU |
| **cold start at 256 MB** | **6,511.4** | |
| cold start at 512 MB | 5,248.3 | |
| **binding case: cold at 256 MB with a 2× worse tail** | **13,022.9** | |

The recommendation is the smallest whole second that clears the binding case: **14 s.** It is
not a round number picked first and justified afterwards; the arithmetic is in `recommend()` in
the harness, not in this prose. **It is robust to §4's noisiest input:** at perfect CPU
proportionality the binding case is 13,023 ms, and at the 1.083 slope the earlier probe measured
it is 13,442 ms. The answer is 14 s either way.

The 2× is carried *inside* the binding case rather than reported beside it, because the lead's
ranking is explicit — a timeout that truncates the headline beat is a worse defect than a larger
bill — and because **the timeout is not a spend bound at all**: Lambda bills actual duration, so
a 100 ms invocation costs the same under a 14 s timeout as under a 3 s one. What a timeout
bounds is the blast radius of a *hung* invocation: the pgwire stall, the connection stranded
INTRANS by §8's defect.

**Expressed as a multiple, which is what was asked for:**

| 14 s is … | of |
|---:|---|
| **1.20×** | the cloud gate-run p99 **as measured**, 11,688 ms |
| **3.75×** | that p99 **corrected to in-region**, 3,729 ms |
| **2.67×** | the modelled cold start at 512 MB |
| **2.15×** | the modelled cold start at 256 MB |

**What 14 s would truncate:** a warm in-region gate run whose tail is more than 3.75× the
corrected p99; a cold start at 256 MB whose CPU is more than 2.15× slower than modelled;
**nothing measured on either target today**, including the 12,588 ms cold cloud gate run in
§1.2. If the tail is 2× worse in Lambda than on this workstation, the binding case becomes
13,023 ms and 14 s clears it by **1.07×** — very little margin, and that is precisely why the
number is not smaller.

**What 3 s would truncate:**

* the warm in-region p99 itself, 3,729 ms — with no cold start and no retry at all;
* every cold-start gate run at 256 MB — modelled 6,511 ms, **2.17× of 3 s**;
* every cold-start gate run at 512 MB — modelled 5,248 ms, and 10,497 ms at a 2× tail;
* any warm run that takes one `40001` retry, which replays the whole beat set;
* **every** gate run driven by a caller as far from the cluster as this workstation — measured
  p99 11,688 ms — which is what a judge running `demo_acceptance.py` from outside
  `ap-southeast-1` is. That one is not an extrapolation; it is 100 of 100 samples.

**The instruction to W6 is a floor, not a digit.** ~~14 s and the plan's current 15 s differ by
less than this model's own uncertainty~~, and the model's dominant unknown — a Graviton2 core
against this one — is not measured at all. **Do not go below 14 s. Do not go near 3 s.** If
`timeout` moves, `duration_p99_threshold_ms` must still move below it; that plan-time
precondition is working as intended and must not be relaxed.

> **CORRECTED 2026-08-14 against the artefact.** The plan is no longer at 15 s.
> `evidence/deploy/terraform-plan-furl.txt:315` says `timeout = 14` and
> `infra/envs/demo/terraform.tfvars.example:105` says `api_timeout_seconds = 14`, so **the
> plan sits at this floor, not above it**, and there is no longer a gap for the model's
> uncertainty to be smaller than. The sentence's *conclusion* is unaffected and is if anything
> stronger: 14 s clears the 13,022.9 ms binding case by **1.07×** and by nothing else.
>
> The two neighbouring artefact values, reconciled while checking this one — both **already
> correct in the shipping configuration**, neither requiring an edit here:
>
> | Attribute | Artefact | Line |
> |---|---:|---:|
> | `timeout` | **14** s | `terraform-plan-furl.txt:315` |
> | `aws_cloudwatch_metric_alarm.duration_p99` `threshold` | **13,500** ms | `terraform-plan-furl.txt:124` |
> | `modelled_worst_legitimate_duration_ms` | **13,022** ms | `terraform-plan-furl.txt:868` |
> | `memory_size` | **256** MB | `terraform-plan-furl.txt:290` |
>
> That 13,500 ms sits inside the admissible band the module enforces —
> `modelled_worst_legitimate_duration_ms < duration_p99_threshold_ms < timeout * 1000`, i.e.
> 13,022 < 13,500 < 14,000 — by **two** plan-time preconditions
> (`infra/modules/demo-api/main.tf:691` and `:751`). **Both edges are live and neither is
> slack.** The band is 978 ms wide. `modelled_worst_legitimate_duration_ms = 13022` is §5.1's
> own binding case read back into the infrastructure, so this document's arithmetic is a
> load-bearing input to a plan-time control and **not a figure that may be rounded here.**
> **This document does not carry a 12,000 ms threshold anywhere**; a 12,000 ms figure appears
> in `infra/modules/demo-api/variables.tf:981` and `main.tf:721` only as the *planted negative
> control* that proved a conditional precondition did not fire, which is a different claim.

### 5.2 · `memory_size` — **256 MB**

**Why it is nearly free on the headline beat.** The gate run is database-bound, and that is
measured, not asserted: the four beats accounted for 1,244.9 ms of a 1,336.6 ms server-reported
run. **93 % of the gate run is CockroachDB executing**, and CockroachDB does not get slower when
Lambda gets less CPU. Halving memory roughly doubles the other 7 %.

**Why it is worth taking.** `memory_size` is the one classical lever that is
duration-independent: the compute term is `concurrency × memory_GB × window × price`, so halving
memory halves it outright. It *also* halves the flood rate, because the CPU-bound beats take
twice as long — and egress and request charges both scale as 1/duration. It is the only lever in
the menu that pushes every cost term the same way. §6.3 puts it at roughly half the worst case.

**What it costs, stated rather than buried.**

* **Cold start rises from a modelled 5,248 ms to 6,511 ms — and that lands on a judge's first
  click.** There is no mitigation that does not cost money (provisioned concurrency).
* The static-asset beats roughly double, because they are nearly pure CPU: `asset_map` at
  ≈ 49 ms becomes ≈ 99 ms on the fast-core assumption. **ANNOTATED 2026-08-14: `asset_map` is
  the pre-strip beat and the deployed origin 404s it (§0.1).** The doubling is unaffected —
  only *which object is the largest one being doubled* has changed. Post-strip the same
  doubling runs on `asset_js`, which §6.3 already prices at **≈ 17.7 ms → ≈ 35.4 ms**, and on
  its gzip sibling at **≈ 9.0 ms → ≈ 17.9 ms**. Both figures are read out of §6.3's existing
  scenario rows; **nothing was recomputed to write this note.**
* **There is no measurement of a 256 MB Lambda anywhere in this evidence, and there cannot be
  one without an apply.** §4 is the closest thing available, it is a proxy, and it is noisy.

---

## 6 · What this does to the cost model — the part W7 needs

Under a sustained flood at the account concurrency ceiling:

```
rate      = concurrency / duration                            proportional to 1/duration
egress    = rate x bytes x window                             proportional to 1/duration
requests  = rate x window                                     proportional to 1/duration
compute   = concurrency x memory_GB x window x price_per_GBs  INDEPENDENT of duration
```

**So the measured duration is what makes the worst-case dollar figure right or four times
wrong** — and `docs/deploy/COST-BOUND.md` §2.1 says honestly that its 100–300 ms is an estimate.
This is the measurement.

### 6.1 · The attacker's beat is not the gate run

| Beat | p50 on this workstation | bytes | bytes per millisecond |
|---|---:|---:|---:|
| `gate_run` | 1,339.61 ms | 9,366 | 7 |
| `index` | 1.23 ms | 4,655 | 3,785 |
| `asset_js` | 5.66 ms | 433,396 | 76,572 |
| `asset_map` † | 14.11 ms | 1,554,168 | **110,146** |

A flood maximises bytes per second, so it uses `asset_map` and nothing else. **A cost model that
applies the gate run's duration to a flood understates the bill by four orders of magnitude in
byte rate; one that applies the static beat's duration to the `timeout` truncates the demo.**
They are different numbers answering different questions and this document keeps them apart.

> **† ANNOTATED 2026-08-14 — which tree this flood is a flood of.** The sentence above
> describes the **PRE-STRIP flood**: it uses `asset_map`, and the deployed origin answers
> **404** to that path (§0.1). It is the correct flood for the tree this harness served and
> for §6.2's 1.000× denominator, and it stays.
>
> **The POST-STRIP flood uses `asset_js` and nothing else.** Against the tree that ships,
> `asset_js` is the maximum of this table's last column at **76,572 B/ms** — a figure already
> in the row above, not a new one. For any client sending `Accept-Encoding: gzip` the wire
> object is the **124,127 B** sibling under the same URL, and for any client that does not, the
> ceiling answers **413** (§0.1).
>
> **The model is NOT recomputed here and no number under it has been swapped.** §6.2 already
> carries the post-strip flood as its **0.777×** row and §6.3 already prices it in the "after
> the strip" column; this note names which tree each flood describes and changes neither. **A
> beat silently swapped underneath an unchanged number would be the defect this annotation
> exists to correct, one layer down.**

### 6.2 · Duration is affine in bytes, and the intercept is the whole story

Least squares over the three static beats, each an N = 200 p50:

```
local   duration_ms = 1.584 +  8.156e-6 x bytes     R2 = 0.99452
cloud   duration_ms = 3.705 + 17.435e-6 x bytes     R2 = 0.99985
```

Residuals: −0.39, +0.54, −0.15 ms (local) and −0.14, +0.19, −0.05 ms (cloud). The two fits
differ because the machine was busier during the second; §1.3 bounds that at 2.2×. **A response
costs 1.6 ms before it costs anything per byte** — and on the busier reading, 3.7 ms.

That intercept is why the byte levers are self-limiting, and it turns a byte ratio into a much
smaller cost ratio. Egress is proportional to *bytes ÷ duration*, and the CPU extrapolation
factor cancels out of that ratio entirely — so the last column below is **independent of every
unknown in §4**, and the two fits agree on it to within 2 percentage points:

| Object | bytes | fitted duration | bytes/ms | share of ~~today's~~ **the PRE-STRIP** flood rate |
|---|---:|---:|---:|---:|
| ~~today~~ — largest source map · **PRE-STRIP baseline; 404 on the deployed origin** | 1,554,168 | 14.26 ms | 108,989 | **1.000×** |
| ~~after W2 strips the maps~~ — largest `.js` · **THE STRIP HAS LANDED; this row is today** | 433,396 | 5.12 ms | 84,672 | **0.777×** (cloud fit: 0.763×) |
| at the I2 wire ceiling, 136 KiB · **in force today**, `DEFAULT_MAX_RESPONSE_BYTES` | 139,264 | 2.72 ms | 51,209 | **0.470×** (cloud fit: 0.450×) |
| ~~after W3 serves `.gz`~~ — largest gzipped object · **THE SIBLINGS HAVE LANDED; 57 ship** | 124,127 | 2.60 ms | 47,813 | **0.439×** (cloud fit: 0.419×) |

> **ANNOTATED 2026-08-14 — the future tense in three of these labels has expired; the numbers
> have not.** "W2" and "W3" here are the **cost-bound wave's** workers, not this wave's, and
> both landed on 2026-08-13. Measured over `out/lambda/mainline-demo-api-arm64.zip` today: **0**
> source maps, **57** `.gz` siblings, largest identity **433,396 B**, largest sibling
> **124,127 B**. So rows 2 and 4 describe the shipping tree and row 1 describes the tree that
> was replaced. **Not one fitted duration, byte count or ratio in this table moved** — the
> least-squares fit in §6.2 is over the three identity beats as measured, and re-labelling a
> row does not re-fit it. Row 3's ceiling is likewise unchanged and correct: `136 * 1024 =
> 139,264`, live in `static_site.py` today, and by construction it is the *only* row here that
> was never a prediction. **The 1.000× row is the denominator the other three are shares of;
> that is the second reason it cannot be deleted** (§0.1).
>
> One reading this table does **not** support, stated so nobody infers it: row 2 is not a
> claim that the origin emits 433,396 B. On the identity path it refuses that object with a
> **413**; the largest body it actually puts on the wire is row 4's **124,127 B** (§0.1).

~~**Stripping the source maps removes 72.4 % of the served bytes and 22.3 % of the worst-case
flood.**~~ **CORRECTED TENSE 2026-08-14: stripping the source maps REMOVED 72.4 % of the served
bytes and 22.3 % of the worst-case flood — it is done, and the percentages are unchanged.**
~~Adding pre-compression takes~~ **Pre-compression took** the pair to 56 % off. Both are real;
neither is the order-of-magnitude the byte counts imply.

**This disagrees with the plan, and the plan asked for the disagreement to be visible.**
`docs/leads/cost-bound-plan.md` §4 records an indicative table — explicitly "a prediction,
recorded so that a disagreement with W7's measured output is visible rather than absorbed" —
predicting $33,252 → ≈ $9,900 after the strip and ≈ $3,600 after the ceiling and gzip. Those rows
assume cost falls with bytes. It falls with bytes ÷ duration, and the measured ratios are 0.78
and 0.44. **The prediction is optimistic by roughly 3×.** Nothing about the stop mechanism — the
three alarms and the responder — is affected, and as the plan's §0.2 says, that is the lever that
does the real work. This measurement strengthens that argument rather than weakening it.

### 6.3 · Indicative dollars, so the shape is visible

Reproduced from `COST-BOUND.md` §2.2's tariff and window: concurrency 10, 30 days, decimal-GB
tiers. **The model reproduces the committed $33,252 and $11,701 headlines exactly from the
committed 100 ms and 300 ms inputs**, which is what gives it standing to produce new ones.
**W7 owns the executable model; this table is indicative and is here to show the shape.**

Durations are the local fit scaled by the vCPU share and a Graviton2-versus-this-core band of
1× to 2×.

| Scenario | ~~today,~~ the map · **PRE-STRIP; 404 today** | ~~after W2 strip~~ **the `.js` · SHIPPING** | ~~after W3 gzip~~ **the `.gz` · SHIPPING** |
|---|---:|---:|---:|
| 512 MB, Graviton2 == this core (49.3 / 17.7 / 9.0 ms) | **$66,489** | $52,080 | $30,243 |
| 512 MB, Graviton2 2× slower (98.5 / 35.4 / 17.9 ms) | $33,731 | $26,526 | $15,608 |
| 256 MB, Graviton2 == this core (98.5 / 35.4 / 17.9 ms) | $33,645 | $26,440 | $15,521 |
| 256 MB, Graviton2 2× slower (197.1 / 70.7 / 35.9 ms) | $17,265 | $13,663 | $8,083 |

**The committed $33,252 is not a worst case; it is the middle of this band.** At the fast end the
worst case is $66,489 — **2.0× the headline** — and the ratios across each row hold at 0.78 and
0.45 in every scenario, exactly as §6.2 predicts, because the extrapolation factor cancels.

**Three inputs W7 should take from here rather than assume:**

| Input | Value | Kind |
|---|---|---|
| flood-beat duration, 512 MB | **49–99 ms** | extrapolated from a measured 14.26 ms |
| flood-beat duration, 256 MB | **99–197 ms** | same, one more factor of two |
| duration ratio after each byte lever | **0.78 / 0.47 / 0.44** | measured; independent of every CPU unknown |

> **ANNOTATED 2026-08-14 — the first two rows are the PRE-STRIP flood beat.** Their 14.26 ms
> is `asset_map`'s fitted duration, and the deployed origin 404s that path (§0.1), so those
> two rows describe the tree that was replaced. **They are the right inputs for reproducing
> §2.2's committed headline and the wrong ones for pricing the tree that ships.** For the
> shipping tree the flood beat is `asset_js` at a fitted **5.12 ms** and W7 should take the
> row of §6.3 it wants directly rather than scaling these two; the ratio row is unaffected,
> because a ratio of two fitted durations cancels every CPU unknown and every tree label with
> it. **No value in this table was changed** — `scripts/deploy/cost_model.py` re-derives
> §2.2's committed headlines from them, and `tests/deploy/test_cost_model.py::test_the_model_reproduces_every_published_headline`
> fails the build if they move.

---

## 7 · Conditions, caveats and what is not measured

**Which bytes were measured.** `handler_source` in the evidence carries a SHA-256 prefix for
every module in `mainline_demo_api` as it stood at 07:05 UTC. **W2, W3 and W4 are changing that
package in this same wave** — the source-map strip, the wire ceiling and the gzip sibling, the
rate limiter — so these figures are a **before**. When `static_site.py` or `app.py` moves, the
static-beat rows here are stale and the digest says so without anybody having to trust a date.
Re-run §9 after those land.

> **ANNOTATED 2026-08-14 — THAT DIGEST HAS NOW FIRED, and this is the check working, not
> failing.** Re-computed on this machine today over
> `verticals/mainline/apps/demo-api/src/mainline_demo_api`, the root the evidence names:
>
> | Module | `handler_source` digest | today | |
> |---|---|---|---|
> | `static_site.py` | `976e383af3c11bbc` | `a1f2662c9759ea97` | **MOVED** |
> | `app.py` | `26e382ba9c885e52` | `6d5e6b9953cb77cf` | **MOVED** |
> | `db.py` | `3566805eee193428` | `e648a295ea31bef0` | **MOVED** |
> | `gate_run.py` | `f2db0b7c2752a93e` | `968e7b38e2b1c92b` | **MOVED** |
> | `reads.py` | `80e7ffa102a454e2` | `c1672f43c56f81a1` | **MOVED** |
> | `transitions.py` | `904628f31b595d55` | `3f24d379a00f7122` | **MOVED** |
> | `__init__.py`, `credentials.py`, `envelope.py`, `health.py`, `refusal.py`, `scenario.py` | — | unchanged | 6 of 12 |
>
> **`static_site.py` and `app.py` are both among the six that moved**, so by this paragraph's
> own rule **every static-beat figure in this document is now a `before`** — including the two
> the annotations above lean on, `asset_js` at 5.66 ms and `index` at 1.23 ms. They are the
> best figures available and they are not current ones. **The tree changed under them exactly
> as this paragraph predicted, and it was detectable without trusting a date — which is the
> whole point of committing the digest.**
>
> **UNRESOLVED, and not guessed at here: what the static beats measure on today's
> `static_site.py`.** §9 is a ~30-minute run of which ~19 minutes is 100 cloud gate runs
> against a CockroachDB Cloud cluster, and it was not re-run for this annotation. **What would
> settle it:** `measure_beats.py --targets local --web-root <the `web/` tree extracted from
> `out/lambda/mainline-demo-api-arm64.zip`>` with the gzip beat of §0.1 added — static beats
> only, no cloud target, minutes rather than half an hour, and it would answer §0.1's
> UNRESOLVED in the same run.

**Conditions.** The workstation was shared with seven other workers of the same wave. The local
container sat at 162–280 % CPU throughout, most of that this harness's own 100 back-to-back gate
runs; the node's session table was checked at 06:40 UTC and the only open transaction was this
harness's. An **earlier** run of the same harness overlapped another worker's `trappoint-migrate`
DDL sweep over database `w_w6`, and its local `gate_run` p99 came out at 6,755 ms against 2,975 ms
here — that run's tail was a busy shared node, not the demo, and it is not the run this document
reports.

**Not measured, and nobody should read this page as if it were:**

* anything running in `ap-southeast-1`. The 2 ms same-region RTT is an assumption.
* anything running on arm64. This is an x86_64 workstation; the target is Graviton2, and the
  ratio between them is the model's dominant unknown.
* any Lambda at any memory size. §4 is a proxy on a different architecture, and a noisy one.
* the AWS execution environment's own cold start — runtime bootstrap, INIT phase, VPC attach.
  Only the Python-side import and connect are here.
* concurrency. `local_furl` serialises handler calls to emulate one warm container, which is the
  right emulation and is not a load test.
* TLS between caller and function. AWS terminates that ahead of the function, so a local TLS hop
  would have measured something the Lambda never pays.
* a `40001` retry. None occurred in 200 gate runs across both targets, so its cost is modelled
  (one more beat set) and not observed.

**Credentials.** The cloud DSN never appears on a command line, in stdout, or in the evidence.
It reaches the emulator through `--env-file`, which `local_furl` reads itself; everything the
harness captures from a child passes through a redactor before it can be printed. Verified after
the fact: the values of `COCKROACH_DSN`, `CC_API_KEY` and `CC_SERVICE_ACCOUNT` do not appear in
`latency-baseline.json`, and it contains no `scheme://userinfo@` substring at all. The cluster
hostname is recorded, as it already is in five other files under `evidence/deploy/`.

---

## 8 · Three things this measurement found that it did not go looking for

**1 · The `autocommit` defect, both of its faces, in one run.** The harness's connection-state
probe issues `gate-run`, then `health`, then `gate-run` again in one process:

| Target | statuses |
|---|---|
| `local` (`w_w1_cost`, no deploy-chain marker) | `[200, 503, 200]` |
| `cloud` (`mainline_demo`, marker present) | `[200, 200, 200]` |

`transitions._prepare` sets `conn.autocommit = False` on the shared module-scope connection and
never restores it; `db.py:306` opened it `autocommit=True` and `health.py:106` documents that
assumption. On the marker-less database the next non-gate-run request is a hard **503**. On the
marker-carrying cluster it answers 200 and leaves the warm connection stranded INTRANS — an
idle-in-transaction `40001` amplifier the health alarm cannot see. Both halves reproduce, on a
real socket, through the real handler, on every run of this harness. **This is not the cost-bound
wave's file and it is not fixed here.** It is recorded because it was measured here, and because
the probe is falsifiable: if a future run answers `[200, 200, 200]` on the local target, the
finding is gone and the evidence will say so on its own.

> **ANNOTATED 2026-08-14 — the code this finding names has been replaced, and the finding is
> therefore UNRESOLVED rather than confirmed or withdrawn.** Read directly today,
> `transitions.py` no longer leaves the flag off: `_borrowed` (`:303-358`) saves
> `conn.autocommit`, clears it, and restores it in a `finally` whose comment states *"THE ORDER
> IS LOAD-BEARING"*; `_prepare` (`:361`) refuses a connection handed to it in autocommit rather
> than clearing one (`:381-383`); and the module's own prose at `:315` describes the 2026-08-13
> defect in the past tense. Two tests now assert the fixed behaviour **by name** —
> `test_a_gate_run_hands_the_shared_connection_back_in_autocommit` and
> `test_the_request_after_a_gate_run_is_not_a_503` in
> `verticals/mainline/apps/demo-api/tests/test_transitions.py`.
>
> **They do not pass on this machine today, and not for this reason.** Both fail
> `assert 422 == 200` with `{'error': 'demo_history_not_seeded'}` — `mainline.defeater_option`
> holds no row for check `db736483-…`, which is a different, currently-open blocker. The gate
> run never reaches the point where autocommit would be handed back, so **the assertion that
> would settle this finding is not being evaluated.** The code shape says fixed; no green says
> fixed; **this document reports the second, because a fix nobody has watched execute is a
> claim and not a measurement.**
>
> **What would settle it:** seed `mainline.defeater_option` so those two tests execute, then
> re-run §9's connection-state probe and read `statuses` for the `local` target. A
> `[200, 200, 200]` there retires this finding on the evidence's own terms, as the paragraph
> above already provides for. **The paragraph is left standing until that happens** — it names
> the defect, the fix that appears to answer it, and the reason nobody can yet say so.

**2 · BLOCKER 1 reproduced through the Function URL path, and then stopped reproducing.** At
05:55 UTC, four consecutive cloud gate runs returned HTTP 200 with `verdict: NOT PROVEN` and
exactly one failure — `beat 4 (admit): expected admitted/00000, observed refused/23503
disposition_signer_credential_id_fkey`. At 06:06 and 06:07 UTC another wave landed the fix — a
new module, `credentials.py`, and a change to `gate_run.py` — and the 100-sample run this
document reports, taken at 07:05 UTC, returned `PROVEN` 100 times with `admit` on `00000`.
**The figures in §1.2 are therefore for the slower of the two regimes**: the admitting path does
the merge `CALL` and the merge-record read that the refusing path skipped. `handler_source` in
the evidence pins the exact bytes measured.

That transition also caught this harness in the act. An earlier 100-sample cloud run spanned the
period in which the fix landed, and the harness recorded only the *last* sample's verdict — so it
reported `PROVEN` for a set it had no way of showing was uniform. It is not that the summary was
known to be wrong; it is that **it could not have disagreed with itself**, which is the defect
class this repository keeps rediscovering. The harness now counts every sample —
`verdict_counts`, `outcome_counts`, per-beat `sqlstate` counts and a `one_regime` flag — and both
targets in the reported run come back `one_regime: true`.

**3 · `localhost` in a DSN costs `connect_timeout` seconds on this workstation.** §2.1. Ten
seconds, on the first connection, silently, once per process.

---

## 9 · Reproducing this

```bash
# the local target needs a migrated, proof-seeded scratch database; this creates one
MAINLINE_W4_DATABASE=w_w1_cost .venv/Scripts/python.exe -m pytest \
    verticals/mainline/apps/demo-api/tests/test_gate_run.py --crdb=reuse -q

# then measure. ~30 minutes, of which ~19 is 100 cloud gate runs.
.venv/Scripts/python.exe scripts/deploy/measure_beats.py \
    --targets local,cloud \
    --local-database w_w1_cost \
    --local-permit-id <the seeded permit> --local-site-id <the seeded site> \
    --local-signer-sub proof.signer --local-countersigner-sub proof.countersigner \
    --samples-static 200 --samples-health 100 \
    --samples-gate-local 100 --samples-gate-cloud 100 \
    --cold-samples 5 --rtt-samples 50 --cpu-rounds 250 --warmup 5 \
    --out evidence/deploy/cost/latency-baseline.json
```

The cloud DSN comes from `.env` through `--env-file` (the default) and is never typed on a
command line. `--crdb=reuse` is mandatory: an unqualified full-suite run started thirteen
containers on 2026-08-10.

> **ANNOTATED 2026-08-14 — that command re-measures the packer's INPUT tree.** It passes no
> `--web-root`, so `local_furl` falls back to `DEFAULT_WEB_ROOT`
> (`verticals/mainline/apps/console/dist`, `local_furl.py:101`), which still carries all 18
> source maps. **Run verbatim, it reproduces §1.1 and §1.2 including `asset_map` — which is
> correct if you are reproducing this document, and wrong if you want the shipping origin.**
> To measure what deploys, extract `web/` from `out/lambda/mainline-demo-api-arm64.zip` and
> pass `--web-root <that directory>`; `asset_map` then answers **404**, and
> `/assets/index-BjAGxrVJ.js` answers **413** without `Accept-Encoding: gzip` and **200 with
> 124,127 B** with it (§0.1). **Neither invocation is a correction of the other. They answer
> different questions and the flag is which question you asked.**

**The model can be re-derived without re-measuring.** `--recompute-from <artefact>` reuses every
measurement and recomputes only `round_trip_model` and `recommendation`, stamping `recomputed`
and `measured_at` into the output so the provenance of each half is separable. A model that can
only be reproduced by re-running a thirty-minute measurement cannot be audited; this one can be
checked in a second. The committed artefact was produced that way, from the measurements of the
06:50 UTC run, after the CPU slope was clamped at 1.0 for the reason in §4.
