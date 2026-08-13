<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# COST-FINISH — closing the bound the last wave built and did not connect

**Lead:** cost-bound (finish) · **Date:** 2026-08-13 · **Workers:** 6 · **HEAD:** `073dfea`
**Posture:** the founder's, unchanged and not re-litigated — `authorization_type = NONE`,
no auth on the URL, real limits in code.
**Nothing in this plan applies anything.** `terraform init/validate/plan/show` and
read-only AWS calls only.

---

## 0 · What I measured today, before decomposing anything

Every row is a command I ran on this workstation on 2026-08-13. Nothing here is inherited
from `docs/deploy/COST-BOUND.md`, from `docs/leads/cost-bound-plan.md`, or from a board.

### 0.1 · The suite, both lanes, run by me

```
pytest verticals/mainline/apps/demo-api/tests --crdb=reuse
    ->  3 failed, 377 passed, 1 skipped, 63 errors in 47.28s

pytest tests/deploy \
       verticals/.../tests/test_ratelimit.py test_logbudget.py test_response_contract.py \
       --crdb=none
    ->  180 passed in 6.93s
```

The 3 + 63 are **not this wave's**. They are the demo-truth lead's four findings: the
`payloads` fixture that refuses to invent a subject (63 errors, one cause),
`test_refusal_row_factory` ×2, and the undeclared-query-parameter refusal. **They are the
before number and they must be the after number.** No worker in this wave touches
`test_reads.py`, `test_refusal_row_factory.py`, `conftest.py`, or any seed.

One correction to the orchestrator's brief, measured rather than assumed:
`test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503` **passes in suite at
`073dfea`**. It is not in my failure list. Finding 4 of that brief is closed or dormant; it
is not open.

### 0.2 · The package as actually built (`out/lambda/mainline-demo-api-arm64.zip`, 15:54 today)

| # | Measurement | Value |
|---|---|---|
| M1 | zip on disk | 7,646,264 B, 246 entries |
| M2 | `web/` entries | **114 files, 1,274,342 B** |
| M3 | …source maps | **0 files, 0 B** — the strip is already the default |
| M4 | …`.gz` siblings | **57 files, 289,312 B** |
| M5 | …identity | **57 files, 985,030 B**, median 5,467 B |
| M6 | largest identity object | **433,396 B** `web/assets/index-BjAGxrVJ.js` |
| M7 | largest `.gz` object | **124,127 B**, and it is the **only** one above 64 KiB |
| M8 | ceiling in force | `DEFAULT_MAX_RESPONSE_BYTES = 512 * 1024` (`static_site.py:206`) |

### 0.3 · Two findings that change what this wave is

**F1 — scope item (a) is already done, and I will not re-do it.**
`--strip-source-maps` is the default in **both** builders
(`build_lambda.sh:142`, `build_lambda.ps1:219-223`), `--keep-source-maps` /
`-KeepSourceMaps` is the opt-out, the sidecar records `source_maps: stripped`, and M3
confirms it on the artefact: **zero maps ship**. The brief's "flip the default" is
complete. Saying so and moving on is worth more than re-flipping a flipped switch.

**F2 — the `.gz` siblings are BUILT AND NEVER SERVED, and the ceiling has gone slack.**
These are one finding, because the same wave caused both.

```
grep -n 'accept.encoding|content.encoding|gzip'  static_site.py   ->  no match
grep -n 'accept.encoding|content.encoding|gzip'  app.py           ->  no match
```

`scripts/deploy/bundle_manifest.py` implements interface **I1** completely — it writes the
siblings, records `largest_gz_object`, and ships the two regression checks
(`compressible_without_sibling`, `gz_without_identity`). The **serving half was never
written.** So today the function carries 289,312 B of compressed objects it has no code
path to emit, `Accept-Encoding: gzip` is ignored, and — worse — a direct request for
`/assets/index-BjAGxrVJ.js.gz` is not refused, so one set of bytes has two names, which I1
forbids in as many words.

And the ceiling, measured against the tree that actually deploys:

| Ceiling | refuses, identity tree | refuses, all `web/` |
|---|---:|---:|
| 2 MiB (the old value) | 0 / 57 | 0 / 114 |
| 1 MiB | 0 / 57 | 0 / 114 |
| **512 KiB (in force today)** | **0 / 57** | **0 / 114** |
| 256 KiB | 1 / 57 | 1 / 114 |
| 139,264 B | 1 / 57 | 1 / 114 |

`static_site.py:178` says of the 512 KiB constant: *"and it binds"*. **It does not.** The
docstring's own arithmetic — "75 files … 74 answer 200 and one answers 413" — was measured
against the **pre-strip input tree**, and the strip landed in the same wave, removing the
one object the ceiling refused. The claim was true when written and false by the end of the
same day. This is the exact defect the previous verifier named about 2 MiB: *a ceiling
above everything it governs is a decoration.* It is now a decoration again, one octave
down, and the docstring asserts otherwise.

**I am not lowering the ceiling to whatever number makes a test green.** The authority here
is the deployed tree: `max(served wire bytes) <= CEILING < k · max(served wire bytes)` for a
stated small `k`, asserted against the real package at test time, so it can never again
drift above everything. See W1.

### 0.4 · The stop mechanism exists and **nothing calls it**

`infra/modules/cost-guard/` is complete and valid — SNS topic + policy, responder Lambda +
role + `lambda:PutFunctionConcurrency` grant scoped to one ARN + an explicit Deny on
`DeleteFunctionConcurrency`, `aws_budgets_budget`, and all three alarms
(`invocations_burst`, `invocations_hourly`, `log_ingestion`).
`tests/deploy/test_cost_guard_responder.py` is 30,272 B of Stubber tests **including two
mandatory falsification checks with anchor guards**. `terraform validate` passes on the
module standalone. All of that is real work and it is good work.

```
grep -n 'module "' infra/envs/demo/main.tf   ->  module "site"   (line 255)
                                                 module "api"    (line 280)
```

**There is no `module "guard"`.** The module is never instantiated, `var.alarm_actions`
is still `[]` (`variables.tf:761`), and every alarm on the demo function is actionless.
`evidence/deploy/terraform-plan-furl.txt` still reads `Plan: 11 to add`.

So the finding that produced the previous wave — *the bound is documented and not
implemented* — **has reproduced one level up**. It is now *coded and not instantiated*,
which on a plan output is identical. That is this wave's centre of gravity and it belongs
to W5.

Also unpassed from `infra/envs/demo/main.tf`, so the module defaults stand:
`timeout` = 15 s, `memory_size` = **512 MB**, `duration_p99_threshold_ms` = 12,000,
`log_level` = **INFO**, and none of `MAINLINE_MAX_RESPONSE_BYTES`,
`MAINLINE_RATE_*`, `MAINLINE_LOG_BUDGET_BYTES` is published — so every code default is
in force and **unreadable from `get-function-configuration`**.

### 0.5 · The number the founder was given is a floor, and I have now measured how far

`docs/deploy/LATENCY.md` (W1 of the last wave) measured every beat. The static beats are
the flood beats, and they are nothing like the modelled 100 ms:

| beat | local p50 | cloud p50 | bytes |
|---|---:|---:|---:|
| `asset_js` | **5.66 ms** | 11.45 ms | 433,396 |
| `asset_map` | **14.11 ms** | 30.75 ms | 1,554,168 |
| `gate_run` | 1,339.61 ms | **11,256.07 ms** | ~9,370 |

The prior lead's insight — `egress, requests ∝ 1/duration; compute ⊥ duration` — is
correct, and I have now put the measured duration into it rather than predicting the
effect. Decimal GB, ap-southeast-1 tariff, concurrency 10, 30 days, arm64:

| model | duration | wire bytes | egress | requests | compute | **total / 30 d** |
|---|---:|---:|---:|---:|---:|---:|
| the audited headline (reproduced) | 100 ms | 1,554,168 | $33,046 | $52 | $173 | **$33,271** |
| the same at the **measured** map duration | 14.11 ms | 1,554,168 | $229,219 | $367 | $173 | **$229,759** |
| after the strip (already shipped) | 5.66 ms | 433,396 | $159,598 | $916 | $173 | **$160,687** |
| + `.gz` on the wire | 5.66 ms | **124,127** | $46,294 | $916 | $173 | **$47,383** |
| + `memory_size` 512 → 256 MB | 5.66 ms | 124,127 | $46,294 | $916 | **$86** | **$47,297** |
| + the rate bound (fleet 100 rps served, rest 429) | 5.66 ms | 124,127 | $3,203 | $916 | $86 | **$4,205** |
| **+ the stop, 5 min** | 5.66 ms | 124,127 | $7.90 | $0.11 | $0.01 | **$8.01** |
| the stop at 1 h (the hourly alarm) | | | | | | **$96** |
| the Budgets backstop at a 24 h lag | | | | | | **$2,002** |

Read that column downward and the argument of this wave is not arguable:

1. **USD 33,250 is understated about 7×** once duration is measured instead of assumed.
   $229,759 is the honest "today", and even that is a *model bound*, not a prediction —
   it assumes AWS sustains 708 rps × 1.55 MB = 1.1 GB/s of egress from ten 512 MB
   execution environments, which nobody has observed. W6 must publish it labelled as a
   bound with that assumption named, not as a forecast.
2. **The byte levers give back most of what they take.** The strip cut bytes 3.59× and cut
   the bill only 1.43×, because a smaller object is faster to serve and the rate rose 2.5×.
   The `.gz` lever is the good one (3.39×) and `memory_size` is worth $86 — 0.2 % — and is
   worth taking only because it is duration-independent, not because it is large.
3. **Every byte lever multiplied together leaves a five-figure bill.** $229,759 → $47,297.
4. **The rate bound is the first order-of-magnitude**, and it is already in code
   (`ratelimit.py`, wired at `app.py:441` as the first statement of the handler) — and
   it is **unpublished by Terraform**, so it runs on code defaults nobody chose.
5. **The stop is the whole answer.** $47,297 → $8 per episode. It is built. It is not
   connected.

**The residual to argue about is row 9, not row 8.** A caller who paces under both
`Invocations` alarms is caught only by Budgets at an 8–24 h Cost Explorer lag. W6 must
compute that residual at the **hourly alarm threshold**, not at flood rate — a caller under
the alarm is by definition not at flood rate, and quoting $2,002 there would be dishonest
in the direction that flatters nobody.

**And the residual includes this, in the table and not in a footnote: this converts a cost
attack into an availability attack.** Anyone at all can reach this URL by the founder's
explicit choice, so anyone at all can trip the burst alarm and stop the demo. It stays
stopped until a human runs `scripts/deploy/kill_switch.{sh,ps1} --restore`. That is the
right trade against an unbounded bill — an outage is recoverable by one command and a bill
is not — but it is a trade, and it goes in the residual column.

### 0.6 · `timeout` is a reliability bound and this plan does not sell it as one

`LATENCY.md` §5.1 recommends **14 s** against a warm in-region `gate_run` p99 corrected to
**3,729 ms**, an `import psycopg` p99 of 2,526 ms at 0.145 vCPU, and the cloud gate-run p99
**as measured** of 11,688 ms. The founder's requested 3 s is **0.80× the corrected warm
p99** and would truncate the headline beat. Lambda bills actual duration, so a 5.66 ms
invocation costs the same under a 14 s timeout as under a 3 s one: **the timeout moves the
bill by nothing.** W5 sets 14 s because it is a reliability bound, records it as one, and
must also move `duration_p99_threshold_ms` below it — that `lifecycle.precondition` is
working as intended and **must be satisfied, never relaxed.**

---

## 1 · The rule that governs this wave

**Read this before touching anything, and it is repeated in all six briefs.**

A previous worker on this repository hit `23503` on beat 4 and "fixed" it by editing
`demo_world.sql` to enrol the constant the code derived — making the *seed* match the
*code*. Three negative controls caught it; one said *"the seed has been reshaped to match
an application constant."* It was reverted.

When a test and the code disagree, **ask which side is authoritative** and move the other
one. **Never change a seed, fixture, ceiling, threshold, or expected value to obtain a
green.** Doing so converts a real defect into a permanent invisible one. If you believe a
fixture is genuinely wrong, say so in `still_broken` with your evidence **and leave it
alone.**

In this wave the trap has a specific shape, and it is the one that already fired once:
**`DEFAULT_MAX_RESPONSE_BYTES` is a ceiling.** Lowering it until a test passes, or raising
it until an asset fits, is precisely the prohibited move. The authoritative side is the
**measured deployed tree**. The ceiling is derived from it by a stated rule, and W1 ships
the assertion that keeps it derived.

Second trap: `evidence/deploy/cost/*.json`, `evidence/deploy/terraform-plan-furl.*` and
`docs/HONESTY.md` / `docs/CI-STATE.md` are **recorded evidence**. If a checker goes red
against them, fix the checker or regenerate the evidence from a real run — never hand-edit
the record.

---

## 2 · Interfaces, fixed here so six workers do not negotiate them

**I1 — the sibling contract** (already implemented by the packer; W1 implements the
serving half unchanged). `<name>.gz` sits beside every compressible `web/**` entry, gzip
level 9, `mtime=0`, no filename field. The server emits it with
`content-encoding: gzip` and the media type **of `<name>`** when the request's
`Accept-Encoding` contains `gzip`. **A direct request for a path ending `.gz` is a 404.**

**I2 — the ceiling is measured on WIRE bytes.** The billed quantity is what leaves Lambda
after it decodes base64, not the base64 string. `static_site._refuse_too_large` already
separates `wire` from `on_disk`; W1 keeps that separation and W2 proves it end-to-end.
**gzip bytes are not valid UTF-8, so a `.gz` body must set `isBase64Encoded: true` and the
base64 form is 33 % larger than the wire form** — a ceiling applied to the encoded string
would over-refuse by exactly that. This is the subtlest hazard in the wave.

**I3 — the ceiling stays binding.** W1 asserts, over the real package:
`largest_served_wire_bytes <= MAX_RESPONSE_BYTES < 1.20 × largest_served_wire_bytes`.
The test reads the tree, not a constant. An asset that grows past it fails the test rather
than the demo.

**I4 — the stop contract** (already shipped; nobody re-writes it). Responder takes an SNS
message, calls `PutFunctionConcurrency(ReservedConcurrentExecutions=0)`, idempotent, never
`DeleteFunctionConcurrency`. Restore is `scripts/deploy/kill_switch.{sh,ps1} --restore`.
`cost-guard` exports `sns_topic_arn`; W5 feeds it to `var.alarm_actions`.

**I5 — the log budget.** `logbudget.DEFAULT_BUDGET_BYTES = 4096` per invocation, override
`MAINLINE_LOG_BUDGET_BYTES`. W3 measures what the **runtime** adds on top (START/END/REPORT
are not the handler's bytes and no code can suppress them) and hands W4 a
`log_incoming_bytes_threshold` derived from `measured_bytes_per_invocation ×
burst_threshold`, not from a round number.

**I6 — no cycle in Terraform.** `cost-guard` takes `guarded_function_name` as a **string**
and builds the ARN itself from `aws_caller_identity`/`aws_region`/`aws_partition`
(`main.tf:147`). So W5 must hoist the name into `local.api_function_name = "${var.name_prefix}-api"`
and pass **the local** to both modules. Passing `module.api.function_name` into
`module.guard` while passing `module.guard.sns_topic_arn` into `module.api` is a
module-level cycle and Terraform will refuse it.

---

## 3 · The six workers

| # | Worker | Owns | Depends on |
|---|---|---|---|
| W1 | serve the gzip, make the ceiling bind | `static_site.py`, `test_static_site.py` | — |
| W2 | the envelope and the socket | `app.py`, `test_response_contract.py`, `local_furl.py`, new e2e test | W1 |
| W3 | bound log ingestion, measured | `logbudget.py`, `test_logbudget.py`, new probe + evidence | — |
| W4 | cost-guard thresholds, re-derived and falsified | `infra/modules/cost-guard/**`, responder + its test | W3 |
| W5 | instantiate the guard; regenerate the plan | `infra/modules/demo-api/**`, `infra/envs/demo/**`, plan evidence | W4 |
| W6 | the model as a program; the one honest table | `cost_model.py` + test, 6 live docs | W1,W3,W5 |

Full briefs travel in the structured output. The paragraphs below carry only what a
reviewer of *this* document needs.

**W1** writes the serving half of I1 and derives the ceiling from M6/M7 by I3's rule. The
number it lands on is a *consequence* of the tree, not an input. If the honest derivation
says the ceiling should be 139,264 B (1.122 × M7) it says so and the largest identity
object then 413s on the identity path — which is correct, because every browser that will
ever fetch it sends `Accept-Encoding: gzip`, and a client that refuses compression asking
for a 433 KB bundle is exactly what a wire ceiling is for. W1 must state that consequence
loudly rather than quietly choosing a looser number to avoid it, and must fix the
`static_site.py:178` docstring sentence *"and it binds"*, which is currently false.

**W2** owns the one hazard nobody has hit yet: a gzip body through the Function-URL
envelope must be base64, and base64 is 33 % larger. W2 proves through a real socket
(`local_furl.py`) that a browser-shaped request gets 124,127 wire bytes with
`content-encoding: gzip`, that an identity request gets identity or a 413, and that
`/…​.gz` is a 404.

**W3** bounds ingestion (scope item (e)) by measurement rather than by assertion. The
handler's 4,096 B is a code bound and it is real; what nobody has measured is the total,
including the runtime's own lines and the 429 path under flood. W3 measures and hands W4 a
derived threshold.

**W4** re-derives every cost-guard threshold against W3's measurement and my §0.5 model,
and — the part that matters — **runs the falsification**, not merely ships it. An
untriggered action is indistinguishable from no action and no `apply` is permitted, so the
Stubber test with its anchor-guarded mutation is the only proof available and it must be
observed going red.

**W5** is the load-bearing worker: `module "guard"` in the env root, `alarm_actions` wired,
`timeout` 14 s, `memory_size` 256 MB, `duration_p99_threshold_ms` under the timeout,
`log_level` WARN, and all six `MAINLINE_*` values published so the bounds in force are
readable from `get-function-configuration`. Then `init/validate/plan` and the regenerated
evidence. **The plan will no longer be 11 to add.** W5 produces the new count and the exact
list.

**W6** turns the model into `scripts/deploy/cost_model.py`, and its test must reproduce the
**existing** $33,252 / $11,701 from the existing inputs before it is allowed to publish new
ones — a model that cannot reproduce the old answer has no standing to produce a new one.
Then the one table, and the six live documents whose claims this wave falsified.

---

## 4 · Hazards

1. **The 3 failed / 63 errors are another lead's.** Before = after. A worker who "fixes"
   `test_reads.py` in this wave has crossed into a wave that is choosing on the merits.
2. **`infra/modules/demo-api/main.tf` and `infra/envs/demo/main.tf` are one hand only (W5).**
   The blocker-1 signer-subject change already landed there in the working tree; W5 must
   rebase on it, not revert it.
3. **The Terraform module cycle (I6) is a real error, not a warning.** W5 hoists the local.
4. **The concurrency alarm's `lifecycle.precondition` at 8 against the measured account
   ceiling of 10, and `reserved_concurrent_executions = -1`, are correct.** Satisfy them.
   Never relax them.
5. **`--crdb=reuse` or `--crdb=none`, always.** An unqualified full-suite run started
   thirteen containers on 2026-08-10 and took the node down (`justfile:258-266`).
6. **Nobody applies anything, and no worker may make a mutating AWS call** — including
   `put-function-concurrency`, including "just to prove the responder works."
7. **Historical `docs/leads/*` records are dated findings and are not edited.** Only the six
   live `docs/deploy` + `docs/STATE-OF-THE-BUILD.md` claims move.
