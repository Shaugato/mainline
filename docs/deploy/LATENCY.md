<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# LATENCY — how long each demo beat actually takes, and what that does to the bill

**Owner:** W1 (cost-bound) · **Measured:** 2026-08-13, this workstation
**Harness:** `scripts/deploy/measure_beats.py` · **Evidence:** `evidence/deploy/cost/latency-baseline.json`

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
>    p99 and 0.46× the modelled cold start at 256 MB. It would truncate the headline beat on a
>    warm invocation, never mind a cold one. The measured floor is **14 s**, which is one
>    second below where the plan already sits.
> 3. **`memory_size` 512 → 256 MB costs the headline beat almost nothing**, because the gate
>    run is database-bound: 1,245 ms of its 1,337 ms server-reported time — **93 %** — is
>    CockroachDB executing three statements, not Lambda computing.
> 4. **The byte levers are worth far less than their byte ratios suggest.** A response costs a
>    fixed **1.6 ms** plus **8.2 ns per byte**, so shrinking an object shrinks its duration
>    less than proportionally, the request rate rises, and most of the saving is handed back.
>    Stripping the source maps removes **72 % of the bytes** and **22 % of the worst-case
>    bill**. §6 is the arithmetic, and it disagrees with the plan's prediction by about 3×.

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
| `asset_js` | `GET /assets/index-BjAGxrVJ.js` | largest **non-map** object in the served tree — M5, 433,396 B |
| `asset_map` | `GET /assets/index-BjAGxrVJ.js.map` | largest **emittable** object — M4, 1,554,168 B |
| `health` | `GET /v1/health` | the cheapest database beat |
| `gate_run` | `POST /v1/demo/gate-run` | the headline four-beat gate run — the beat that decides the timeout |

| Target | Cluster | Database | Seed |
|---|---|---|---|
| `local` | `trappoint-crdb`, CockroachDB v26.2.5, one node | `w_w1_cost` | the proof seeder |
| `cloud` | CockroachDB Cloud **Basic**, `aws-ap-southeast-1` | `mainline_demo` | `demo_world.sql` |

**Both targets ran all four beats and returned `PROVEN` in 100 of 100 samples**, with
`admit` on SQLSTATE `00000`. On the cloud that is new: BLOCKER 1's
`23503 disposition_signer_credential_id_fkey` reproduced here at 05:55 UTC and another wave
fixed it before this run started. §8 records both observations.

**One emulator process per beat.** `transitions._prepare` (`transitions.py:293-294`) and
`_demo_gate_run` (`:1032-1033`) set `conn.autocommit = False` on the module-scope connection
that `db.py:306` opened with `autocommit=True`, and never restore it. A harness that
interleaved beats in one process would measure that defect instead of the beat. §8 records what
happens when you deliberately do interleave them.

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
| `asset_map` | 200 | **14.11** | 23.41 | 32.59 | 35.68 | 32.8 | 1,554,168 |
| `health` | 100 | **8.21** | 10.38 | 11.09 | 13.07 | 19.0 | 388–389 |
| `gate_run` | 100 | **1,339.61** | 2,705.15 | 2,974.73 | 3,130.84 | 1,432.0 | 9,362–9,368 |

### 1.2 · `cloud` — CockroachDB Cloud Basic, `ap-southeast-1`, database `mainline_demo`

| Beat | N | p50 | p95 | p99 | max | first (cold) | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| `index` | 200 | **3.65** | 5.59 | 7.32 | 7.37 | 25.2 | 4,655 |
| `asset_js` | 200 | **11.45** | 25.06 | 34.31 | 35.98 | 30.3 | 433,396 |
| `asset_map` | 200 | **30.75** | 51.86 | 58.02 | 60.86 | 28.0 | 1,554,168 |
| `health` | 100 | **450.35** | 469.03 | 687.90 | 689.01 | 2,120.9 | 408–410 |
| `gate_run` | 100 | **11,256.07** | 11,465.98 | 11,687.74 | 12,453.22 | 12,588.1 | 9,369–9,372 |

All milliseconds.

### 1.3 · Four readings that fall straight out of the two tables

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

**The instruction to W6 is a floor, not a digit.** 14 s and the plan's current 15 s differ by
less than this model's own uncertainty, and the model's dominant unknown — a Graviton2 core
against this one — is not measured at all. **Do not go below 14 s. Do not go near 3 s.** If
`timeout` moves, `duration_p99_threshold_ms` must still move below it; that plan-time
precondition is working as intended and must not be relaxed.

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
  ≈ 49 ms becomes ≈ 99 ms on the fast-core assumption.
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
| `asset_map` | 14.11 ms | 1,554,168 | **110,146** |

A flood maximises bytes per second, so it uses `asset_map` and nothing else. **A cost model that
applies the gate run's duration to a flood understates the bill by four orders of magnitude in
byte rate; one that applies the static beat's duration to the `timeout` truncates the demo.**
They are different numbers answering different questions and this document keeps them apart.

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

| Object | bytes | fitted duration | bytes/ms | share of today's flood rate |
|---|---:|---:|---:|---:|
| today — largest source map | 1,554,168 | 14.26 ms | 108,989 | **1.000×** |
| after W2 strips the maps — largest `.js` | 433,396 | 5.12 ms | 84,672 | **0.777×** (cloud fit: 0.763×) |
| at the I2 wire ceiling, 136 KiB | 139,264 | 2.72 ms | 51,209 | **0.470×** (cloud fit: 0.450×) |
| after W3 serves `.gz` — largest gzipped object | 124,127 | 2.60 ms | 47,813 | **0.439×** (cloud fit: 0.419×) |

**Stripping the source maps removes 72.4 % of the served bytes and 22.3 % of the worst-case
flood.** Adding pre-compression takes the pair to 56 % off. Both are real; neither is the
order-of-magnitude the byte counts imply.

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

| Scenario | today, the map | after W2 strip | after W3 gzip |
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

---

## 7 · Conditions, caveats and what is not measured

**Which bytes were measured.** `handler_source` in the evidence carries a SHA-256 prefix for
every module in `mainline_demo_api` as it stood at 07:05 UTC. **W2, W3 and W4 are changing that
package in this same wave** — the source-map strip, the wire ceiling and the gzip sibling, the
rate limiter — so these figures are a **before**. When `static_site.py` or `app.py` moves, the
static-beat rows here are stale and the digest says so without anybody having to trust a date.
Re-run §9 after those land.

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

**The model can be re-derived without re-measuring.** `--recompute-from <artefact>` reuses every
measurement and recomputes only `round_trip_model` and `recommendation`, stamping `recomputed`
and `measured_at` into the output so the provenance of each half is separable. A model that can
only be reproduced by re-running a thirty-minute measurement cannot be audited; this one can be
checked in a second. The committed artefact was produced that way, from the measurements of the
06:50 UTC run, after the CPU slope was clamped at 1.0 for the reason in §4.
