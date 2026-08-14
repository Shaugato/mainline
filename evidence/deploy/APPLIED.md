<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The apply, as it actually happened — 2026-08-14

**Applied by the orchestrator, with the founder's authorisation, against account `<account>`
in `ap-southeast-1`.** Nothing below is predicted; every line was read back from the account
or from a live HTTP request.

## What exists now

    terraform apply    24 created, 0 changed, 0 destroyed
    terraform state    37 resources
    demo_url           https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws

Eleven resources are the demo API; thirteen are the cost guard — three alarms on three
timescales feeding one SNS topic into a responder that calls
`PutFunctionConcurrency(ReservedConcurrentExecutions=0)`, plus the budget. The guard was
instantiated in this apply, which is why the plan is 24 and not the 22 an earlier review saw.

Preceding it, and the first mutating action of the whole deploy: the state bucket
`mainline-demo-tfstate-<account>` — versioned, public access blocked on all four settings,
SSE-S3, tagged, noncurrent versions expiring at 30 days.

## First light, measured

> **THIS BLOCK IS HISTORY AND IT STAYS. ANNOTATED 2026-08-15, NOT REPLACED.** Every reading
> below was true when it was taken, on 2026-08-14, minutes after the apply, and **all three
> have since been re-measured by an independent program and reproduce** — status, body size
> and reason string, on all three rows. The only quantity that moved is the elapsed time,
> which is a latency and not a constant. §*What the apply actually put on that origin* records
> what those three readings did **not** say, which is the finding of the wave that followed.
> A claim deleted is not a claim corrected — `docs/deploy/COST-BOUND.md`'s own preservation
> rule — so nothing here is edited to match a later measurement.

    GET  /                     200, 4,655 B, 1.63 s   (static console, served)
    GET  /v1/health            ok=false, reason="dsn_unset"
    POST /v1/demo/gate-run     503,        kind="dsn_unset"

Both API answers name the cause exactly: *SSM GetParameter '/mainline/demo/cockroach_dsn'
in ap-southeast-1 answered HTTP 400: {"__type":"ParameterNotFound"}*.

**That is the predicted state, not a defect.** `PRE-APPLY.md` G3 records the asymmetry in
advance: Terraform CONSTRUCTS the parameter ARN and never reads it, so an apply with no
parameter in Parameter Store succeeds, creates all twenty-four resources, and produces a
demo whose first request cannot reach a database. The origin is up; the secret is the one
remaining step.

**Re-measured 2026-08-14 by `scripts/deploy/judge_walk.py --base-url <the demo URL>`**, a
program that takes a URL and nothing else and writes
[`evidence/deploy/judge-walk.json`](judge-walk.json). It opened a socket for every reading —
the document stamps `"source": "live"` — and it reproduces all three rows above: `GET /`
**200, 4,655 B**; `/v1/health` **503 `ok=false reason="dsn_unset"`**; and `POST
/v1/demo/gate-run` **503 `kind="dsn_unset"`**, its step saying in full *"THE ROUTE EXISTS (a
404 would mean it did not)"*. Both API answers carry that same `ParameterNotFound` detail
verbatim. The elapsed time it recorded for `GET /` was **1,617.4 ms** against the 1.63 s
above; a cold Lambda's first byte is not a constant and neither figure supersedes the other.
**23 steps: 2 satisfied, 20 refused for the one named reason `dsn_unset`, 1 FAILED** — and
that one failure is the section below.

## What the apply actually put on that origin — recorded 2026-08-15

**Nothing in this section was deployed, applied, or redeployed. The Function URL is serving
the same bytes it was serving on 2026-08-14**, and the rebuild and the redeploy are the
orchestrator's step, not this record's. What follows is what the wave *measured about* those
bytes, plus what changed in the tree they will next be built from.

### The console artefact that was applied is a REPLAY build

The three readings above are all about the **API**. None of them looks at the JavaScript, and
the defect was in the JavaScript. The founder opened the URL and read `TRANSPORT REPLAY
(staged)` / `BUILD dev` off the page — he found it, we did not.

Read out of the served bytes rather than off a screen, by two independent programs:

    VITE_MAINLINE_API_BASE:""              <- compiled EMPTY
    VITE_MAINLINE_BUNDLE_URL:"./bundle/"   <- compiled SET
    VITE_MAINLINE_LOG_VKEY:""
    MODE:"demo"      buildId:"dev"      signaturePath:"unknown"

`verticals/mainline/apps/console/src/app/source-select.ts` trims each variable and treats the
empty string as **unset**, so exactly one source was configured, `switchable` was false, and
every byte a judge saw was a recording played over an origin that has a real kernel behind
it. The defect is a **missing build input**, not a bug in the selector: `.env.demo` leaves
`VITE_MAINLINE_API_BASE=` empty on purpose and says so in its own header, and the deploy ran
the bare `pnpm exec vite build --mode demo` that file alone produces.

| where it was read | artefact | what it says |
|---|---|---|
| off the wire, from the deployed origin | [`judge-walk.json`](judge-walk.json) → `context.transport_mode` | **`REPLAY`**, with `compiled_sources.live` **`null`** |
| out of the zip's central directory, over `web/assets/*.js` | [`console-mode.json`](console-mode.json) → `readings[]` | the same three literals, and `exit_code: 2` |

The second row is the packaging guard this wave added, run against the artefact that
shipped: `--console-transport live` **refuses** it. `console-mode.json` records that the
reading cost no rebuild — *"No package was rebuilt to produce this record … the bytes a judge
met on 2026-08-14 are still on disk and are still the thing that was measured."*

`buildId:"dev"` is a second defect in the same artefact: `MAINLINE_BUILD_ID` never reached
the build, so the honesty chrome could not name the artefact a screenshot came from, which is
the entire reason that field exists.

### The headline beat was not addressable from the console, and now is — in the tree

`POST /v1/demo/gate-run` **has never 404'd on this deployment.** The route is declared at
`verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:229` —
`Route("POST", "/v1/demo/gate-run", "demo_gate_run")` — and the live URL answers **503
`kind="dsn_unset"`**, which is a reachable route refusing for a named reason. The block above
recorded that on the day of the apply and it is still true.

What was missing was on the **console** side: the resource was not declared, so no control
existed, and `DemoDriver` refused to reach the endpoint with a bare `fetch` because that
would skip envelope and contract validation and would have no REPLAY counterpart. In the
tree today `src/data/resources.ts` declares **17** resources — `RESOURCE_KEYS` lists
`demo_gate_run` at line 243 — and `src/data/contracts.ts` registers `gate-run.schema.json`
as a verbatim copy of the demo-api's. **That is a change to the source, not to the origin.**
The deployed artefact still contains zero occurrences of `gate-run`.

### CONFIRMED INDEPENDENTLY, 2026-08-15, by the judge-eye verifier

Every claim in the two sections above was re-taken from the wire and from the served bytes by
a worker who wrote none of them, on 2026-08-15. **Nothing was deployed, applied, redeployed or
written to AWS to produce this paragraph, and no DSN was read or printed.** The readings
reproduce:

| request | 2026-08-14 record | 2026-08-15 re-measurement |
|---|---|---|
| `GET /` | `200`, 4,655 B | **`200`, 4,655 B**, 1.58 s |
| `GET /v1/health` | `503` `ok=false reason="dsn_unset"` | **identical**, same `ParameterNotFound` detail |
| `POST /v1/demo/gate-run` | `503` `kind="dsn_unset"` | **identical** — the route exists; it does not 404 |

The console assertion was settled the same way, by fetching the asset `GET /` names and
reading the compiled literals out of the response body rather than off a screen:

    GET /                       -> references ./assets/index-DzVoV1YM.js
    GET /assets/index-DzVoV1YM.js
      Content-Encoding gzip     124,177 B on the wire, 433,564 B identity
      VITE_MAINLINE_API_BASE:""          <- EMPTY: selectSource starts REPLAY
      VITE_MAINLINE_BUNDLE_URL:"./bundle/"
      buildId:"dev"
      "demo_gate_run"     ABSENT
      "/v1/demo/gate-run" ABSENT

**The two wire figures are the ones three test modules declare** (`124,177` / `433,564`), so
the re-recording done this wave describes the tree that is actually serving. **The last two
lines are the finding**: the artefact on the URL cannot address the headline beat at all — the
key does not appear in it — which is why the founder had no button to press.

The STOP in `docs/decisions/response-ceiling-authoritative-tree.md` §9 was also reproduced
first-hand rather than quoted. A LIVE console was built on 2026-08-15
(`$env:VITE_MAINLINE_API_BASE='/'`, PowerShell, so no MSYS path conversion is possible), its
entry chunk `assets/index-C8EWacrY.js` read back as carrying `VITE_MAINLINE_API_BASE:"/"`, and
the ceiling arithmetic re-derived over the whole tree:

    identity objects over 139,264 : 1   ('assets/index-C8EWacrY.js', 457,132)
    .gz siblings over 139,264     : 0
    largest gz sibling  g         = 129,404
    floor(1.10 x g) = 142,344  ->  smallest 8 KiB multiple >= that = 18 x 8,192 = 147,456
    147,456 != 139,264            -> OUTSIDE the window 119,158 <= g <= 126,604
    I3 bound  129,404 <= 139,264 < 155,284.8   HOLDS

`g = 129,404` agrees to the byte with §9's independently-taken figure. **`DEFAULT_MAX_RESPONSE_BYTES`
is still `136 * 1024` in `static_site.py:279` and was not touched.**

### What is NOT claimed here

* **No redeploy happened.** `out/lambda/mainline-demo-api-arm64.zip` on disk is dated
  2026-08-14 and its packer sidecar still records `console.configured.VITE_MAINLINE_API_BASE`
  as the empty string — it is the artefact that is serving, not a successor to it.
* **No package was rebuilt into the deploy path**, and the one measurement that would gate a
  rebuild is a **STOP, not a green.** A LIVE package *was* built — to a **scratch path**,
  `--console-transport both`, `MAINLINE_BUILD_ID=3933b97`, zip `sha256 56d6730b8b55…` — purely
  to measure it. With the seventeenth resource and the 23,138 B contract in place its entry
  chunk is **457,123 B** identity / **129,404 B** on the wire, against 433,564 / 124,177
  today. 129,404 B is **2,800 B outside** the window `119,158 ≤ g ≤ 126,604` inside which
  `DEFAULT_MAX_RESPONSE_BYTES == 139,264` re-derives, so re-recording from that build would
  mean raising the ceiling one 8 KiB step to make the arithmetic come out — raising a ceiling
  to pass a test. It was not done: the report is
  `docs/decisions/response-ceiling-authoritative-tree.md` §9, and all three declaring test
  files still carry the deployed package's numbers.
  ([`console-repro.json`](console-repro.json) → `runs["worktree-phase2"]` records the earlier,
  `dist`-level reading of the same growth — 457,037 / 129,371 — taken without a real
  `MAINLINE_BUILD_ID`; the packaged figure is the one that governs, because the origin serves
  the package.)
* **The SSM parameter is untouched**, by this wave and by this document. The section below is
  unchanged.

## The step that is deliberately not automated, and the reason

`/mainline/demo/cockroach_dsn` must hold the **`mainline_api`** DSN. Measured on the live
cluster, the three login-capable roles are not interchangeable:

| role | privileges held |
|---|---|
| `mainline-sql` — the DSN in `.env` | **ALL on 417 objects** |
| `mainline_api` | CONNECT 1 · USAGE 36 · SELECT 55 · UPDATE 3 · INSERT 8 · EXECUTE 29 |
| `mainline_judge` | CONNECT 1 · USAGE 21 · SELECT 14 · EXECUTE 28 — no INSERT, no UPDATE |

The Function URL carries `authorization_type = NONE` by the founder's explicit choice, so
whatever this parameter holds is what an anonymous caller's request runs as. Putting the
`.env` DSN here would give a public unauthenticated endpoint `ALL` on 417 objects. It is
`mainline_api` or it is a hole.

Entering a credential is the founder's action, not the orchestrator's, so the value is
placed by him. The mechanism keeps it out of every log either way: the payload goes in via
`--cli-input-json file://…` from a `0600` file so it never enters an argument vector, and it
is read back WITHOUT `--with-decryption`, so the check cannot print it even by accident.
Terraform is given the parameter NAME and never the value — `terraform show` cannot print a
password Terraform never held.
