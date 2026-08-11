<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Observability — one heartbeat, four alarms, and what a judge sees when it breaks

**What watches this demo, by what, at what interval, what each signal means, what a judge
sees when the database is unreachable, and what it costs.**

Owner: `w8-acceptance-and-video` for this document and
[`.github/workflows/demo-health.yml`](../../.github/workflows/demo-health.yml). The alarms
and dashboard are declared by [`infra/modules/demo-api`](../../infra/modules/demo-api);
every threshold below is read from that module's HCL rather than remembered.

**Nothing on this page is created yet.** `terraform apply` has not been run — the plan is
committed and the founder reviews it before any apply
([`docs/leads/ship-final.md`](../leads/ship-final.md) §2.2). So §3 and §4 describe
declarations, not resources, and say so in their own words. §2 is live today and is red
today, on purpose.

---

## 1. What is watched, by what, at what interval

| Subject | Watcher | Interval | Where the signal appears |
|---|---|---|---|
| `GET /` — the console is served | `demo-health.yml` | hourly | red X on the Actions tab |
| `GET /v1/health` — live, fresh, `ok: true` | `demo-health.yml` | hourly | red X + the body in the log |
| `POST /v1/demo/gate-run` — the four beats by SQLSTATE | `demo-health.yml` | hourly | red X + which beat moved |
| latency of all three | `demo-health.yml` | hourly | job summary table, every run |
| Lambda errors / throttles / p99 / concurrency | four CloudWatch alarms (declared) | 5-minute periods | CloudWatch console; **notifies nobody** |
| the whole claim, end to end, from outside | `scripts/deploy/demo_acceptance.py` | at deploy time, and on demand | [`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json) |
| CockroachDB Cloud cluster metrics | **nothing** | — | see §6 |

Two watchers, deliberately. The cron answers *is it up and does it still refuse?*; the
alarms answer *is the function itself unhealthy?*. Neither can answer the other's
question, and a page that implied one of them covered both would be the most misleading
document here.

---

## 2. The heartbeat — `.github/workflows/demo-health.yml`

Hourly on the hour, and on demand via `workflow_dispatch`.

```
resolve the URL from docs/submission/SUBMISSION.json:demo_url
  (a workflow input or vars.DEMO_URL overrides it, for a staging host)

GET  /                     assert 200 and an HTML document
GET  /v1/health            assert 200, body.ok, server_date within 900s
POST /v1/demo/gate-run     assert 200 and the four beats:
                             1 read                     00000
                             2 merge                     23514  gate_closed_when_issued
                             3 projection_drift_attack   P0001  mainline.fn_permit_merge_gate
                             4 admit                     00000
                           assert persisted is false and verdict is PROVEN
record the latency of all three into the job summary
```

### It is red right now, and the red says which red it is

`docs/submission/SUBMISSION.json` holds `"demo_url": "UNRESOLVED"`, so the first step
fails with:

> no demo URL is published; this lane is red because the demo is not deployed, not
> because it is broken

That is the whole design of this lane. Before 2026-08-11 it failed in six to thirteen
seconds with a curl connection error against an unset repository variable — the same red
for a completely different reason, which is how a monitor teaches its readers to ignore
it. **A monitor whose red cannot distinguish "not deployed" from "deployed and down" is
not a monitor.**

**It goes green on its own the moment the URL exists.** W10 writes `demo_url` after the
apply; the next scheduled run reads the file out of the checkout, finds a URL and starts
asserting. No repository variable, no secret, no edit to the workflow. The submission file
is the single place a demo URL is recorded, so it is the single place this job reads.

### Why the freshness assertion earns the job

A cached 200 is the classic false green: an edge object serves a valid health body for
hours after the database behind it has gone. `server_date` comes from `now()` **inside the
health statement**, so a body older than the window proves nothing has spoken to
CockroachDB recently, whatever the status line says. The endpoint is served `no-store`;
this check is what verifies that it actually is.

The window is 900 seconds and deliberately generous. It is a staleness detector, not a
clock-skew detector — a GitHub runner and a CockroachDB node in Singapore have no
guaranteed relationship between their clocks. A `server_date` in the *future* is reported
as a **warning** naming clock skew, not as a staleness failure, because sending whoever is
on call to look for the wrong thing is its own failure mode.

### Why it now drives the gate, when the previous version refused to

The previous version of this workflow argued that calling `gate-run` on a schedule was
hundreds of needless `SERIALIZABLE` transactions against a Basic cluster with a spend cap,
to re-establish something that does not silently change. Two facts moved:

* **It does silently change.**
  [`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json) recorded the
  demo's headline endpoint answering **404 for days** while every other surface was green,
  because the route was missing from `app._routes()`. A liveness check that never touched
  it could not have seen that, and did not.
* **The transaction is rolled back and nothing accumulates.** The four beats share one
  transaction that ends in `ROLLBACK`. The acceptance prover establishes that from
  *outside* by re-reading `GET /v1/permits/{id}` after each run and comparing
  `open_blocking`, `state`, `gate_epoch` and `head_seq` — see §5. There is no state for
  two runs to collide over and nothing to clean up.

The cadence is therefore **hourly, not half-hourly**: 24 gate runs a day, ~200 across the
whole judging window, against a cluster whose monthly allowance is 100 M RU.

### It opens nothing when it passes

No issue, no comment, no notification, no artefact. A monitor that produces output on a
healthy system trains its readers to ignore its output. The only signal is the red X on a
scheduled run — which is what a maintainer already watches for, and which, on a public
repository, is visible to the judges too.

### No `continue-on-error`, no `|| true`, no `set +e`

[`docs/HONESTY.md`](../HONESTY.md) bans them and this workflow contains none. The previous
version carried one `|| true` on the curl that fetched the health body; it is gone. curl's
exit status is now allowed to fail the step under `set -euo pipefail`, and the HTTP status
is captured with `--write-out` and asserted separately, so a **transport failure** and a
**500** stay different reds. A step that cannot fail asserts nothing.

The one `if: always()` in the file is on the step that writes the latency table. It
reports; it does not suppress. The job's conclusion is still whatever the assertions
decided, and a red run carries its timings — a 200 that took nine seconds is the shape of
a problem that has not become an outage yet.

---

## 3. The four CloudWatch alarms (declared, not created)

Declared by `infra/modules/demo-api`. All four are 5-minute periods, 1 evaluation period,
named `${function_name}-<suffix>`.

| Alarm | Metric | Statistic | Threshold | What it means |
|---|---|---|---|---|
| `-errors` | `Errors` | `Sum` | `> 0` | The Lambda raised. In this handler that should be impossible — `handler()` is written never to raise and turns every failure into a JSON body — so a single error is a real defect, not load. |
| `-throttles` | `Throttles` | `Sum` | `> 0` | Concurrency was refused. At demo volume this means the account's concurrency ceiling was hit by *something*, quite possibly not this function. |
| `-duration-p99` | `Duration` | `p99` | `> 20 000 ms` | The slow tail. The gate run is a dozen statements to Singapore; a p99 past 20 s means cold starts stacking, a struggling Basic cluster, or a `40001` retry storm. |
| `-concurrency` | `ConcurrentExecutions` | `Maximum` | `> 20` | **An abuse tripwire, not a capacity signal.** A judging session is a handful of browsers making four requests each. Twenty concurrent executions is not reachable by legitimate use of this demo. |

### The alarms notify nobody, and that is deliberate

`alarm_actions` defaults to `[]`. There is no SNS topic, no email, no pager. **The alarms
exist to be read** — by the dashboard, by `aws cloudwatch describe-alarms`, and by whoever
is looking after a deploy. Wiring a notification channel for an eight-day demo means
creating a topic, confirming a subscription, and remembering to tear both down; the cron
in §2 is what actually tells a human something is wrong.

If you want to be paged, set `alarm_actions` to an SNS topic ARN and add it to the
teardown checklist in §7. It is a one-variable change, and it is off by default rather
than absent.

**The first ten CloudWatch alarms are free.** Four alarms cost $0.00.

---

## 4. The dashboard and the logs

**Dashboard** — one, named for the function, declared by the same module: invocations,
errors, duration with the p99 threshold drawn on it as an annotation, concurrent
executions with the abuse tripwire drawn on it, and the four alarm widgets. Drawing the
thresholds as annotations is the point: a duration graph without its alarm line requires
the reader to remember the number.

**Logs** — CloudWatch Logs, `retention_in_days = 7`.

Seven days is chosen, not defaulted. It covers the whole judging window with room to
spare, keeps ingest far inside the 5 GB free tier, and — the part that matters for a
public demo — means nothing a judge's browser generated is retained a week after they
generated it. `never expire` is the AWS default and would quietly keep a request log
forever for a demo that exists for eight days.

**The handler logs no DSN, no password, and no query string that could carry one.**
`scripts/deploy/cloud_chain.redact` is the single chokepoint for anything that could, and
`scripts/deploy/__init__.py` states the rule for the whole package.
`scripts/deploy/local_furl.py` prints the DSN through `redact_dsn()` for the same reason,
and it is the one line of that banner most likely to be on a screen share.

---

## 5. What a judge sees when the database is unreachable

**Never a blank screen, and never a lie.** What they actually see depends on what the
console build carried, and the three cases are enumerated in
`verticals/mainline/apps/console/src/app/source-select.ts`:

| The build carries | What loads | Badge |
|---|---|---|
| a live API **and** a bundle | LIVE, with a control that switches to REPLAY | `LIVE` → `REPLAY` when switched |
| a bundle only | the signed EvidenceBundle, no backend in the request path | `REPLAY` |
| a live API only | the live surfaces; a database failure renders as a named transport failure on each one | `LIVE` |
| neither | every surface renders its own **NO SOURCE** panel | — |

The badge is read off `transport.describe().mode`, on the object that actually holds the
bytes (`src/app/HonestyChrome.tsx:58`), not off the selection — so it cannot say `LIVE`
about bytes that came from a bundle.

### There is no automatic failover, and that is the honest design

A console that silently switched to the bundle when the API failed would be showing a
judge **yesterday's data under a live badge**. `source-select.ts` therefore makes the
choice from the build and from `?source=`, which can only select between sources the build
already carries. When the database is unreachable, a LIVE build shows the failure — the
API answers `503 database_unreachable` with the SQLSTATE in the body, and
`src/data/transport.ts` classifies a non-2xx with no parseable envelope as a `status`
transport failure and shows it. The judge then switches to REPLAY themselves, with the
control or with `#/gate?source=replay`, and the badge changes because the transport did.

### Measured today, and it is a gap the deploy must close

The `dist/` committed at `verticals/mainline/apps/console/dist` was **not** built with
`--mode demo`: `grep -o 'bundle/' dist/assets/index-*.js` finds nothing, while
`grep -o 'NO SOURCE'` finds the panel. A console built with neither source shows that panel
on every surface — the honest rendering, and not the one a judge should get. The build that
ships must be the one `docs/deploy/console-build.md` §1 specifies:

```bash
VITE_MAINLINE_API_BASE=/ pnpm exec vite build --mode demo
```

`.env.demo` already supplies `VITE_MAINLINE_BUNDLE_URL=./bundle/`, so that command
produces the first row of the table above: LIVE by default, REPLAY one click away, both on
one origin. **This is a cross-domain note, not a change this page can make** — the console
build belongs to `w2-lambda-bundle`.

`scripts/deploy/local_furl.py --bundle-dir …` stages the bundle under `/bundle/` in a
temporary copy of the web root so the REPLAY surface can be exercised locally before that
artefact exists.

---

## 6. What is NOT observed, and should be said

* **CockroachDB Cloud metrics are not scraped.** Basic exposes a metrics endpoint; nothing
  here reads it. The demo's database health is inferred from `/v1/health` answering, which
  is a weaker statement than "the cluster is healthy" and is written here so nobody reads
  more into a green cron than it carries.
* **The spend cap is the real backstop.** `spend_limit` on the cluster is a hard ceiling:
  the cluster stops before the bill grows. That is a cost control, not an alarm, and there
  is no alert on approaching it.
* **There is no CloudFront to watch.** DECISION D1 removed it: this account is under an AWS
  verification hold that refuses new distributions (`ship-final.md` §1.4), and the demo URL
  is a Lambda Function URL. A previous version of this page described CloudFront 4xx/5xx
  rates; there is no distribution and that paragraph is gone.
* **No alarm can tell you the gate stopped refusing.** No CloudWatch metric expresses "a
  `CHECK` constraint is still attached". Only the four-beat assertion can, which is why §2
  now makes it hourly and why `demo_acceptance.py` makes it a deploy gate. That is the one
  claim in the submission, and it is the one thing metrics cannot see.
* **Nothing watches the Bedrock path.** The recall agent's embedding calls are outside the
  demo's request path; `evidence/deploy/aws-live.json` records that they execute, and
  nothing monitors them continuously.

---

## 7. Cost, itemised, and the canary that is not here

The obvious AWS answer to "watch a URL" is a CloudWatch Synthetics canary. Priced:

| | |
|---|---|
| One canary at 5-minute intervals | 8 640 runs/month |
| Rate | $0.0012 per run |
| **Monthly** | **$10.37** |
| Everything else in this stack | ≈ $0.03 |

**A canary would cost roughly thirty times the entire rest of the deployment, to check one
URL.** It is refused, and the GitHub Actions cron replaces it at a lower sampling rate with
three properties a canary does not have: it asserts the four SQLSTATEs rather than a status
code; it fails **in public**, in the repository the judges are already reading; and it
costs nothing on a public repository.

| Line | Basis | USD/month |
|---|---|---|
| CloudWatch alarms | 4; first 10 free | 0.00 |
| CloudWatch dashboard | first 3 free | 0.00 |
| CloudWatch Logs | 7-day retention, far inside the 5 GB free ingest | 0.00 |
| GitHub Actions cron | public repository | 0.00 |
| CockroachDB RU for 24 gate runs/day | one rolled-back transaction each, inside the free allowance | 0.00 |
| CloudWatch Synthetics canary | **refused** — see above | ~~10.37~~ |
| **Total observability** | | **0.00** |

The whole stack is estimated at **≈ $0.02/month, worst case under $1.00**
(`ship-final.md` §2.1), against a founder ceiling of ~$5/month.

---

## 8. Teardown checklist

Run after judging closes. **Order matters**: the database credential is revoked before the
infrastructure that used it is destroyed, so nothing is left holding a live login.

```bash
# 1. Revoke the judge credential on the Cloud cluster
psql "$COCKROACH_DSN" -c 'DROP USER mainline_judge'

# 2. Revoke the API credential
psql "$COCKROACH_DSN" -c 'DROP USER mainline_api'

# 3. Destroy the AWS stack (filters on the project tag and refuses otherwise)
bash scripts/deploy/teardown.sh

# 4. Delete the SSM parameter holding the DSN
aws ssm delete-parameter --name /mainline-demo/dsn --profile mainline-dev

# 5. Confirm nothing survives that carries the prefix
aws resourcegroupstaggingapi get-resources \
    --tag-filters Key=project,Values=mainline \
    --profile mainline-dev --region ap-southeast-1
```

Then, by hand, because each is a deliberate decision rather than a script's:

- [ ] **Set `demo_url` back to `UNRESOLVED`** in `docs/submission/SUBMISSION.json`, so the
      health cron reverts to the "not deployed" red rather than failing against a URL that
      no longer exists. A permanently red scheduled workflow trains people to ignore a red
      scheduled workflow.
- [ ] **Unset the `DEMO_URL` repository variable** if one was ever set as an override.
- [ ] **Rotate `CC_API_KEY`** — the Cloud service-account key. §4 of
      [`JUDGE-PACK.md`](JUDGE-PACK.md) records that this key can `create_database` on the
      cluster; it was used for measurement during the build and should not outlive it.
- [ ] **Drop the `mainline_demo` database**, or delete the cluster, once the evidence files
      are archived. Everything in it is synthetic, so this is housekeeping rather than a
      data obligation.
- [ ] **Confirm the CloudWatch log group is gone.** `teardown.sh` removes it; a log group
      that outlives its function is the most commonly orphaned resource in an AWS teardown,
      and it keeps costing.
- [ ] If `alarm_actions` was wired to SNS, **delete the topic and its subscriptions.**

### What teardown will not touch

The AWS account holds four unrelated projects — including a CloudFront distribution
`E2FCXK8NILPNWF` belonging to none of them (`ship-final.md` §1.4). Everything this
deployment creates carries the `mainline-demo-` name prefix and the tag `project=mainline`,
and `teardown.sh` filters on the tag and **refuses to proceed** if the filter returns
resources it did not expect. Step 5 above is the independent confirmation of that, run
after the fact rather than trusted in advance.
