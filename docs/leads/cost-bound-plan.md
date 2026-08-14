<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# COST-BOUND — the plan that puts the bound in code

**Lead:** cost-bound · **Date:** 2026-08-13 · **Workers:** 8
**Posture:** the founder's, already chosen, not re-litigated — `authorization_type = NONE`
stays, no authentication is added, no URL is gated behind a secret. The bound is a
mechanism in this repository or it does not exist.

**Nothing in this plan applies anything.** `terraform init/validate/plan/show` and
read-only AWS calls only.

---

## 0 · What I measured before decomposing

Every row below is a command I ran today on this workstation, not a figure inherited from
`docs/deploy/COST-BOUND.md` or from a board.

| # | Measurement | Value | How |
|---|---|---|---|
| M1 | ~~Served tree in the deployed package~~ **Served tree in what is now the packer's INPUT tree** | **75 files, 3,571,990 B** under `web/` | ~~`zipfile` over `out/lambda/mainline-demo-api-arm64.zip`~~ → `evidence/deploy/cost/package-shape.json` `architectures[].before.web` |
| M2 | …of which source maps | **18 files, 2,586,960 B** (72.42 %) | ~~same~~ → `…before.web.source_maps` (**deployed today: 0 files, 0 B**) |
| M3 | …non-map | **57 files, 985,030 B** | ~~same~~ → `…before` non-map, and `…after.web.identity` — **the same 57 / 985,030** |
| M4 | ~~Largest emittable object~~ **Largest object in the INPUT tree** | **1,554,168 B** `web/assets/index-BjAGxrVJ.js.map` | ~~same~~ → `…before.web.largest_identity_object` (**deployed today: 433,396 B identity, 124,127 B gz — the map is not in the package**) |
| M5 | Largest non-map object | **433,396 B** `web/assets/index-BjAGxrVJ.js` | ~~same~~ → `…after.web.largest_identity_object`, unchanged across both trees |
| M6 | **gzip −9 of the whole non-map tree** | **289,312 B** (0.294 of M3) | `gzip.compress(level=9)` per entry |
| M7 | **Largest gzipped object** | **124,127 B** — and it is the only object above 64 KiB compressed | same; 56 of 57 are ≤ 65,536 B gz |
| M8 | Response ceiling in force | `DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024` (`static_site.py:170`) — **refuses 0 of 75**; M4/ceiling = 0.741 | read |
| M9 | Compression in the handler | **none.** No `gzip`, no `Content-Encoding`, no `accept-encoding` anywhere in `static_site.py` or `app.py` | `grep` |
| M10 | Budget resources in `infra/` | **zero.** `grep -rn 'aws_budgets_budget' infra/` returns two prose comments and no resource | `grep` |
| M11 | Alarm actions | `var.alarm_actions` default `[]` — **all four alarms are actionless** | `variables.tf:628` |
| M12 | Plan shape today | `Plan: 11 to add, 0 to change, 0 to destroy` | `evidence/deploy/terraform-plan-furl.txt` |
| M13 | Terraform | v1.14.8, windows_amd64 | `terraform version` |
| M14 | Warm handler time, this workstation, in-process | `index.html` **0.72 ms** p50 · largest non-map **2.55 ms** · largest map **5.39 ms** | 40 iterations of `static_site.serve` |
| M15 | `json.dumps` of the finished payload | +**2.03 ms** (non-map) · +**7.36 ms** (map) | 30 iterations |
| M16 | Request-time gzip cost | **17.8 ms** (level 6) / **25.9 ms** (level 9) for the 433 KB asset | timed |
| M17 | `testpaths` | already includes `verticals/*/apps/demo-api/tests` (`pyproject.toml:129-134`) | read |

> **ANNOTATED 2026-08-14 — M1–M5 NAME THE WRONG TREE, AND THE DIGITS ARE NOT THE DEFECT.**
> This table is a **dated record of 2026-08-13**, before this plan's own W2 made
> `--strip-source-maps` the build default. On that date `out/lambda/mainline-demo-api-arm64.zip`
> really did hold 75 `web/` entries, 3,571,990 B and 18 source maps, so **every value in
> M1–M7 was measured correctly and none of them is retyped here.** What has since become
> false is the *label and the sourcing*: M1 says *"in the deployed package"* and M4 says
> *"largest **emittable** object"*, both sourced to a zip that a reader can open today and
> find **zero source maps** in. That tree is now the packer's **input**, and the sourcing is
> corrected to the artefact that carries both:
> [`evidence/deploy/cost/package-shape.json`](../../evidence/deploy/cost/package-shape.json).
>
> | | files | bytes | source maps | `.gz` siblings | largest object |
> |---|---:|---:|---:|---:|---:|
> | `architectures[].before` — the packer's **input** tree (what M1–M7 measured) | 75 | 3,571,990 | 18 / 2,586,960 B | 0 | **1,554,168 B** `index-BjAGxrVJ.js.map` |
> | `architectures[].after` — the **deployed** package, today | 114 | 1,274,342 | **0 / 0 B** | 57 / 289,312 B | 433,396 B identity / **124,127 B** gz |
>
> **The digits stay because they are load-bearing.** `1,554,168 B` is the input from which
> `docs/deploy/COST-BOUND.md` §2.2's **$33,251.87** is re-derived by
> `scripts/deploy/cost_model.py`, under a build gate
> (`tests/deploy/test_cost_model.py::test_the_model_reproduces_every_published_headline`), and
> it is the byte count the **×6.91** correction in that document's §0.1 row L1 rests on.
> Retyping them would silently break a reproduction and delete a finding. **A figure that does
> not name its tree is wrong, whichever tree it came from** — so both are named, here and in
> §4 below.
>
> **M6/M7 need no re-sourcing and are called out so nobody "fixes" them**: 289,312 B and
> 124,127 B were computed by gzipping the non-map tree, and those are exactly the `.gz` figures
> the **deployed** package now carries (`…after.web.gz`, `…after.web.largest_gz_object`).
> M6/M7 are true of *both* trees.
>
> **M8, M11 and M12 are superseded by date, not corrected here**, because this is a record of
> what was true when the plan was written and the whole point of keeping it is to show what
> moved: the ceiling M8 read at `2 * 1024 * 1024` is now **139,264 B**; M11's actionless
> `var.alarm_actions = []` is now `local.guard_stop_topic_actions`; and M12's plan count of
> **11 to add** is now **24** per `evidence/deploy/terraform-plan-furl.txt:843`. The live
> statements of all three are in `docs/deploy/COST-BOUND.md` §0.2 and §5.1, which is where a
> reader should take a current number from. **Nothing in this dated table should be quoted as
> current.**

### 0.1 · The one number the existing model never measured, and it is the load-bearing one

`docs/deploy/COST-BOUND.md` §2.1 assumes an invocation duration of **100–300 ms** and says
so honestly (§9: "100 ms is an estimate"). Under a sustained flood at the account
concurrency ceiling, three of the four cost terms depend on that estimate, and they do not
depend on it the way people expect:

```
rate      = concurrency / duration                      ∝ 1/duration
egress    = rate × bytes × window                       ∝ 1/duration
requests  = rate × window                               ∝ 1/duration
compute   = concurrency × memory_GB × window × rate_per_GBs   INDEPENDENT of duration
```

Compute under flood is `10 × 0.5 GB × 2,592,000 s × $0.0000133334 = $172.80` at any
duration whatsoever — which is exactly the figure §2.2 prints, arrived at from the other
direction. **Egress and request charges are inversely proportional to duration, and
duration has never been measured.** M14+M15 put the handler's own share of a
largest-object response at **≈ 12.8 ms** on this workstation. A warm arm64 Lambda at
512 MB is slower than this machine, but not 8× slower. If the true figure is 25 ms rather
than 100 ms, **the headline USD 33,250 is understated 4×.**

I am not going to headline a number I have not measured, and neither should this
repository. **W1 measures it end-to-end through `scripts/deploy/local_furl.py`** — which is
the same handler, the same payload encode/decode, and a real socket — and W7 recomputes the
model with a stated sensitivity band. Until W1 lands, treat $33,250 as a **floor**, not a
worst case.

### 0.2 · Why the founder's chosen levers are the right ones, and which one is doing the work

The founder chose: strip the maps, make the cap bind, cut the timeout and memory, add a
rate bound, add a budget action that can actually stop the function. Reconciled against the
arithmetic above:

* **Bytes-per-request levers (L2, L3) are real but self-limiting.** Making a response 11×
  smaller also makes it faster to build, which raises the rate, which gives some of the
  saving straight back. They are necessary and they are not sufficient.
* **`memory_size` is the one classical lever that is duration-independent.** Halving it
  halves the $172.80 compute term outright, and — post-rate-limit — compute is the majority
  of what is left. It is worth taking on those terms, and *only* on those terms.
* **`timeout` is not a spend bound under a flood and this plan will not sell it as one.**
  Lambda bills actual duration; a 100 ms invocation costs the same under a 15 s timeout as
  under a 3 s one. What a 3 s timeout bounds is the blast radius of a *hung* invocation —
  the pgwire stall, the INTRANS connection — which is a reliability property with a real
  cost tail, and it is worth having for that reason, at a value chosen from measurement and
  not from a round number. **A timeout that truncates the headline beat is a far worse
  defect than a larger bill**, so W1 measures the slowest gate-run against the cloud cluster
  with its 40001 retry loop before W6 touches the number.
* **The mechanism that actually bounds the bill is the one nobody has built: an automatic
  stop.** The worst case is `rate × bytes × time-until-something-stops-it`. Every existing
  control leaves the third factor at *30 days*. Bring it to *five minutes* and the same
  flood costs single-digit dollars. That is a bigger factor than every byte lever in the
  menu multiplied together, and it is the centre of this wave.

### 0.3 · Three timescales, because one tripwire is a tripwire an attacker walks under

An attacker who sits just below a burst threshold is not stopped by a burst threshold. So
the stop mechanism is deliberately **three alarms on three timescales, all firing the same
action**:

| Timescale | Sensor | Catches | Lets through |
|---|---|---|---|
| **minutes** | `Invocations` Sum over 60 s, above a threshold well clear of a judging session | the flood | a caller pacing just under it |
| **hours** | `Invocations` Sum over 3600 s, cumulative | the slow burn under the burst line | a caller under *both* |
| **days** | AWS Budgets → SNS → the same responder | anything the first two missed, and any cost this project did not model at all | the first 8–24 h (Cost Explorer lag) |

Each one bounds what the faster one lets through. **Named plainly: this converts a cost
attack into an availability attack** — the function stays at reserved concurrency 0 until a
human restores it. That is the trade the founder's posture implies, it is the right trade
against an unbounded bill, and it must appear in the residual column rather than in a
footnote.

### 0.4 · What has no mechanism available, stated so nobody looks for it later

* **There is no Function-URL-level rate control.** AWS WAF does not attach to Lambda
  Function URLs (only CloudFront, ALB, API Gateway, AppSync, Cognito). The only Function-URL
  knob is `authorization_type`, which the founder ruled out. W4 must state this in the
  module docstring rather than leave a reader wondering.
* **There is no Lambda budget action.** `aws_budgets_budget_action` supports
  `APPLY_IAM_POLICY`, `APPLY_SCP_POLICY` (Organizations only) and `RUN_SSM_DOCUMENTS`
  (EC2/RDS). None of them stops a Lambda. The path is Budgets **notification** → SNS →
  responder → `PutFunctionConcurrency(0)`, and W5 says so in the module header instead of
  implying a native action exists.
* **Log ingestion has no native ceiling.** A log group has retention, not a quota. The only
  bounds are *bytes emitted per invocation* (W4, deterministic) and *stop the thing emitting
  them* (W5's `IncomingBytes` alarm on the same responder).

---

## 1 · The design, as one picture

```
        ┌──────────────────────── one Lambda, one Function URL, auth NONE ───────────┐
        │                                                                            │
 caller │  ratelimit.py   ──429──►  (2 layers: global token bucket, per-IP bucket)   │
 ──────►│      │                                                                     │
        │      ▼                                                                     │
        │  static_site.serve  ──►  .gz sibling if the client accepts gzip            │
        │      │                   identity if it fits under the wire ceiling        │
        │      │                   406 if neither  ──────────────► bytes bounded     │
        │      ▼                                                                     │
        │  logbudget.py   ──►  bounded log bytes per invocation                      │
        └────────────────────────────────┬───────────────────────────────────────────┘
                                         │ metrics
                    ┌────────────────────┴────────────────────┐
                    ▼                    ▼                     ▼
        Invocations>T / 60s   Invocations>T' / 3600s    Logs IncomingBytes
                    └────────────────────┬────────────────────┘
                                         ▼
                              SNS topic (one)  ◄──── AWS Budgets notification
                                         ▼
                       cost-guard responder Lambda
                                         ▼
                    lambda:PutFunctionConcurrency(demo-api, 0)
```

Layer 1 (`ratelimit`, `.gz`, the wire ceiling) shapes and shrinks. Layer 2 (the three
alarms → one responder) terminates. Layer 3 (Budgets) is the backstop with an 8–24 h lag,
labelled as such.

---

## 2 · The interfaces, fixed here so eight workers do not negotiate them

These are contracts between workers. Nobody changes one without the plan changing.

**I1 — the pre-compressed sibling.** W2 writes `<name>.gz` beside every compressible
`web/**` entry: gzip level 9, `mtime=0`, no filename field in the header, so the zip stays
byte-reproducible. W3 serves `<name>.gz` with `content-encoding: gzip` and the media type of
`<name>` when the request's `accept-encoding` contains `gzip`. A direct request for a path
ending `.gz` is a **404** — one set of bytes must not have two names.

**I2 — the wire ceiling.** `static_site.MAINLINE_MAX_RESPONSE_BYTES` /
`DEFAULT_MAX_RESPONSE_BYTES` becomes **139,264 B (136 KiB)** — `1.122 ×` M7. W3 also ships
the anti-vacuity assertion that makes it *stay* binding (§3, W3). W6 publishes the same
number as `MAINLINE_MAX_RESPONSE_BYTES` in the function environment so the value in force is
readable from `get-function-configuration` without decoding a zip.

**I3 — the rate-limit environment.** W4 reads `MAINLINE_RATE_GLOBAL_RPS`,
`MAINLINE_RATE_GLOBAL_BURST`, `MAINLINE_RATE_IP_RPS`, `MAINLINE_RATE_IP_BURST`, each with a
code default that is safe if Terraform publishes nothing. W6 publishes all four.

**I4 — the stop contract.** W5's responder accepts an SNS message and calls
`lambda:PutFunctionConcurrency(FunctionName=<from env>, ReservedConcurrentExecutions=0)`.
It is idempotent, it never calls `DeleteFunctionConcurrency`, and restore is
`scripts/deploy/kill_switch.{sh,ps1} --restore`, which already exists. W5 exports
`sns_topic_arn`; W6 passes it into `var.alarm_actions`.

**I5 — the log budget.** W4 caps handler-emitted log bytes per invocation and collapses
repeated 429 lines to one line per bucket window. W6 sets `application_log_level = "WARN"`
and records what `system_log_level` does and does not suppress, from AWS documentation,
with the doc quoted.

---

## 3 · The eight workers

| # | Worker | Owns | Blocks |
|---|---|---|---|
| W1 | measure the beats | `scripts/deploy/measure_beats.py`, latency evidence, `docs/deploy/LATENCY.md` | W6, W7 |
| W2 | the package: strip + pre-compress | both builders, `bundle_manifest.py`, package-shape evidence | W3, W7 |
| W3 | serving + a ceiling that binds | `static_site.py` + its tests | W7 |
| W4 | the handler entry: rate bound + log budget | `app.py`, `ratelimit.py`, `logbudget.py` + tests | W6, W7 |
| W5 | the cost-guard: budget, SNS, responder, proof | `infra/modules/cost-guard/**`, responder + its test | W6 |
| W6 | Terraform integration and the regenerated plan | `demo-api` module, `envs/demo`, plan evidence | W8 |
| W7 | the cost model as an executable | `scripts/deploy/cost_model.py` + test + evidence | W8 |
| W8 | the honest table and the doc cascade | five `docs/deploy/*.md` | — |

Full briefs are carried in the structured output that accompanies this file; the paragraphs
below record only the things a reader of *this* document needs in order to review the shape.

### W1 — measure before anybody changes a number

The founder asked for a ~3 s timeout. Whether 3 s is honest is a measurement nobody has
taken. W1 runs every demo beat through `local_furl.py` (the real handler, real payload
translation, real socket), against **both** the local `trappoint-crdb` container and the
CockroachDB Cloud cluster in Singapore, and reports p50/p95/p99/max per beat plus the cold
import cost of `psycopg`. The cloud gate-run with its 40001 retry loop is the beat that
decides the number. W1 recommends `timeout` and `memory_size` with the headroom stated as a
multiple of the measured p99, and it re-measures at 256 MB by proxy (CPU-scaled) rather than
asserting the effect.

### W2 — strip the maps, ship the gzip

`--strip-source-maps` already exists in both builders and is off by default. W2 makes it the
default and adds pre-compression per I1. Measured effect on the served tree:
**3,571,990 → 985,030 B** raw, and the *largest emittable* object
**1,554,168 → 433,396 B** identity, **124,127 B** gzipped. Total `.gz` overhead added to the
package: 289,312 B, against 2,586,960 B removed.

### W3 — a ceiling that cannot go slack

Today's ceiling refuses 0 of 75 and sits at 1.35× the largest object — it is a number that
happens to be above everything, which is not a control. W3 lowers it to I2 and adds the
assertion that makes it stay a control:

```
largest_served_gz  <=  MAX_RESPONSE_BYTES  <  1.20 × largest_served_gz
```

measured over the real package at test time. A ceiling can never again drift into being
above everything, and an asset that grows past it fails the test rather than the demo.
W3 also fixes a false sentence in `_within_ceiling`'s docstring: base64 length is **not**
what AWS bills egress on — Lambda decodes it before the response leaves — so the current
measurement over-counts encoded bodies by 33 %. It is conservative and it is wrong, and both
halves get said.

### W4 — the rate bound, and what it does not bound

Two buckets, both per execution environment: a **global** token bucket (bounds this
instance's aggregate rate; with the account ceiling of 10 the fleet bound is `10 × R`, and
unlike a per-IP bucket it bounds a *distributed* flood) and a **per-IP** bucket (bounds one
caller). Stated plainly in the module docstring, because each is useless against the other's
threat and a reader must not have to derive that: per-IP does nothing against a botnet;
global does nothing about *who* is refused. **Neither bounds the invocation charge** — Lambda
bills a 429 like any other invocation — which is why W5 exists.

W4 also owns the per-invocation log budget (I5) and the 429 body, which must be small and
must not echo caller-controlled bytes.

### W5 — the stop, and proof that it is wired

A new module: one SNS topic, one responder Lambda with an execution role holding exactly
`lambda:PutFunctionConcurrency` on exactly the demo function's ARN, one
`aws_budgets_budget` with a notification to the topic, and the two `Invocations` alarms of
§0.3 plus the `IncomingBytes` alarm.

**An untriggered action is indistinguishable from no action**, and no `apply` is permitted,
so the proof is a test, not a hope: `tests/deploy/test_cost_guard_responder.py` feeds the
responder the **real** AWS Budgets SNS envelope and the **real** CloudWatch-alarm SNS
envelope and asserts, through `botocore.stub.Stubber`, that exactly one
`PutFunctionConcurrency` call is made with `ReservedConcurrentExecutions=0` and the right
function name — and that a malformed or foreign message makes **none**. A falsification
check is mandatory: delete the stop call and the test must go red.

`count = 0` is **not** the default here. The whole finding of the previous wave was that the
bound is documented and not implemented; a default-off stop is a documented stop.

### W6 — the Terraform surface, all of it, in one hand

`timeout`, `memory_size`, `duration_p99_threshold_ms` (which must move below the new
timeout or the plan-time precondition refuses it — that precondition is working as intended
and must not be relaxed), `application_log_level`, the four rate-limit variables, the wire
ceiling, `alarm_actions` wired to W5's topic, and the `module "guard"` block in the env root.
Then `terraform init/validate/plan` and the regenerated evidence.

**The plan will no longer be 11 resources.** That number is quoted in five `docs/deploy`
files and in four historical `docs/leads` records. W6 produces the new count and the exact
list; W8 corrects the five live documents. The historical lead records are dated findings and
are **not** edited — rewriting a record to match a later state is the defect this repository
refuses.

### W7 — the model, as a program

`docs/deploy/COST-BOUND.md`'s arithmetic is correct and it is prose. W7 turns it into
`scripts/deploy/cost_model.py`: measured inputs in, per-layer before/after out, both GB
conventions, a duration sensitivity band from W1, and the three-timescale residual. Its test
reproduces the two figures the existing document headlines ($33,252 / $11,701) from the
existing inputs, which is what makes the *new* figures trustworthy — a model that cannot
reproduce the old answer has no standing to produce a new one.

### W8 — the table, and the claims this wave falsified

One table: worst case USD/30 d **before** and **after**, per layer, with the residual named
— and the residual includes the availability trade of §0.3 and the detection window, not
just the dollars. Plus the doc cascade: every live claim of `Plan: 11 to add`, of a 2 MiB
ceiling, of "18 source maps still shipping", and of "the only bound is the account quota" is
now false and must move in the same wave that falsified it.

---

## 4 · Indicative arithmetic — what the table is expected to say

**Not a result. A prediction, recorded so that a disagreement with W7's measured output is
visible rather than absorbed.**

> **ANNOTATED 2026-08-14 — the `1,554,168` in the "today" row is the packer's INPUT tree**
> (`evidence/deploy/cost/package-shape.json` `architectures[].before.web.largest_identity_object`),
> **not what the deployed origin can emit.** The deployed package's largest object is
> **433,396 B** identity / **124,127 B** gz, and the response ceiling in force refuses the
> identity form. The digit stays because the whole value of this table is that a *prediction*
> can be compared with what W7 measured — and the comparison is only meaningful against the
> input it was predicted from. The measured ladder that replaced it is
> `docs/deploy/COST-BOUND.md` §0.1, which is the one table anyone should quote.

| Stage | Bytes/request | Time-to-stop | Worst case |
|---|---|---|---|
| today | 1,554,168 | 30 d | **$33,252** (at the unmeasured 100 ms; a floor) |
| + L2 strip | 433,396 | 30 d | ≈ $9,900 |
| + L3 ceiling & gzip | 139,264 | 30 d | ≈ $3,600 |
| + memory 512→256 MB | 139,264 | 30 d | ≈ $3,500 (compute term halves) |
| **+ the stop, 5 min** | 139,264 | **300 s** | **≈ $3 per episode** |
| slow burn under the fast alarm | 139,264 | 1 h alarm | bounded by the hourly threshold — W7 computes it |
| below both alarms | 139,264 | Budgets, 8–24 h | the real residual, and the number to argue about |

If W1 finds the true invocation duration is 25 ms rather than 100 ms, every row above the
"stop" line multiplies by ≈ 4 and the row below it does not move at all. **That asymmetry is
the argument for this wave.**

---

## 5 · Hazards for the orchestrator

1. **`infra/modules/demo-api/main.tf` is contested.** The blocker-1 lead needs
   `MAINLINE_DEMO_SIGNER_SUB` and `COUNTERSIGNER_SUB` published from the same `locals
   .environment` block W6 owns. One file, two waves. Route that change through W6 or
   sequence the waves; do not let two workers hold it.
2. **`docs/STATE-OF-THE-BUILD.md:55,297` and the board** assert `11 to add`. I have not
   claimed the board. It becomes false the moment W6 lands.
3. **Tests must run with `--crdb=reuse` or `--crdb=none`.** An unqualified full-suite run
   started thirteen containers on 2026-08-10 and took the node down (justfile:258-266).
4. **Nobody applies anything**, and no worker may run a mutating AWS call — including
   `put-function-concurrency`, including "just to prove the responder works". The proof is
   the stubbed test.
