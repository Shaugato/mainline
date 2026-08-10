<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Observability — four alarms, one dashboard, a cron, and a teardown checklist

**What watches this demo, what each signal means, what it costs, and how to take it all down.**

Owner: `w10-judge-and-acceptance` for this document and
[`.github/workflows/demo-health.yml`](../../.github/workflows/demo-health.yml).
The alarms and dashboard are created by `w6-tf-api` in
[`infra/modules/demo-api`](../../infra/modules/demo-api); every threshold below is read from
that module's HCL rather than remembered.

---

## 1. The decision that shapes this page

A demo that runs for eight days in front of judges needs to answer one question reliably —
**is it up?** — and it needs to answer it for approximately nothing.

The obvious AWS answer is a CloudWatch Synthetics canary. Priced:

| | |
|---|---|
| Canary at 5-minute intervals | 8 640 runs/month |
| Rate | $0.0012 per run |
| **Monthly** | **$10.37** |
| Everything else in this stack | ~$0.03 |

**A canary would cost roughly thirty times the entire rest of the deployment, to check one URL.**
It is refused. `deploy-plan.md` §2.3 made that call and this document implements it.

The replacement is a GitHub Actions cron that runs every 30 minutes, costs nothing on a public
repository, and — this is the part a canary does not give you — **fails in public, in the
repository the judges are already reading**. A red X on a scheduled workflow is a more useful
signal for this project than an alarm state only the account owner can see.

---

## 2. The heartbeat — `.github/workflows/demo-health.yml`

Every 30 minutes, and on demand via `workflow_dispatch`.

```
GET ${DEMO_URL}/v1/health
  assert HTTP 200
  assert body.ok is true
  assert body.server_date is within 900s of the runner's clock
```

**The freshness assertion is the one that earns the job.** A cached 200 is the classic false
green: a CDN or a stale edge object will serve a perfectly valid health body for hours after the
database behind it has gone. `server_date` comes from `now()` *inside the health statement*, so a
body older than the window proves nothing spoke to CockroachDB recently, whatever the status line
says. The endpoint is served `no-store`; this check is what verifies that it actually is.

The window is deliberately generous. It is a staleness detector, not a clock-skew detector — a
GitHub runner and a CockroachDB node in Singapore have no guaranteed relationship between their
clocks. A `server_date` in the *future* is reported as a **warning** naming clock skew, not as a
staleness failure, because sending whoever is on call to look for the wrong thing is its own
failure mode.

### It opens nothing when it passes

No issue, no comment, no notification, no artefact. A monitor that produces output on a healthy
system trains its readers to ignore its output. The only signal is a red X.

### It fails when `DEMO_URL` is unset

Not skips — **fails**, with a message naming the fix. An unconfigured monitor that reports success
is worse than no monitor: the green tick reads as "the demo is up" when it means "nobody told me
where the demo is". That is the exact failure this job exists to prevent, so it must not be the
job's own default behaviour.

### What it deliberately does not do

It does not call `POST /v1/demo/gate-run`. That endpoint opens a `SERIALIZABLE` transaction and
drives four beats through the kernel; running it every thirty minutes for eight days is ~380
needless transactions against a Basic cluster with a spend cap, to re-establish something that
does not silently change. **This job answers "is the demo up", not "is the demo correct."** The
gate is proven at deploy time by `scripts/deploy/demo_acceptance.py`.

### Verified, not merely written

The assertion logic was extracted from the workflow and exercised against real health bodies from
the running API on 2026-08-10 — including its red paths, which is the half that matters:

| Input | Result |
|---|---|
| fresh body, `ok: true` | **exit 0**, one line of log |
| `server_date` 28 hours old | **exit 1**, `health body is stale` |
| `server_date` absent | **exit 1**, `no server_date` — freshness cannot be established |
| `ok: false` | **exit 1**, names `reason` and `detail` |
| `server_date` in the future | **exit 0** with a `clock skew` warning |

Configuration: repository variable `DEMO_URL`. A variable, not a secret — it is the URL printed in
the submission form, and masking a public URL in the logs of a public repository would only make
failures harder to read.

---

## 3. The four CloudWatch alarms

Created by `infra/modules/demo-api`. All four are 5-minute periods, 1 evaluation period, named
`${function_name}-<suffix>`.

| Alarm | Metric | Statistic | Threshold | What it means |
|---|---|---|---|---|
| `-errors` | `Errors` | `Sum` | `> 0` | The Lambda raised. In this handler that should be impossible — `handler()` is written never to raise and turns every failure into a JSON body — so a single error is a real defect, not load. |
| `-throttles` | `Throttles` | `Sum` | `> 0` | Concurrency was refused. At demo volume this means the account's concurrency ceiling was hit by *something*, quite possibly not this function. |
| `-duration-p99` | `Duration` | `p99` | `> 20 000 ms` | The slow tail. The gate run is six statements to Singapore; a p99 past 20 s means cold starts stacking, a struggling Basic cluster, or a `40001` retry storm. Sits below CloudFront's 30-second origin timeout so the alarm fires before a judge sees a 504. |
| `-concurrency` | `ConcurrentExecutions` | `Maximum` | `> 20` | **An abuse tripwire, not a capacity signal.** A judging session is a handful of browsers making four requests each. Twenty concurrent executions is not reachable by legitimate use of this demo. |

### The alarms notify nobody, and that is deliberate

`alarm_actions` defaults to `[]`. There is no SNS topic, no email, no pager. **The alarms exist to
be read** — by the CloudWatch dashboard, by `aws cloudwatch describe-alarms`, and by whoever is
looking after a deploy. Wiring a notification channel for an eight-day demo means creating a
topic, confirming a subscription, and remembering to tear both down; the cron in §2 is what
actually tells a human something is wrong.

If you want to be paged, set `alarm_actions` to an SNS topic ARN and add it to the teardown
checklist in §5. It is a one-variable change, and it is off by default rather than absent.

**The first ten CloudWatch alarms are free.** Four alarms cost $0.00.

---

## 4. The dashboard and the logs

**Dashboard** — one, named for the function, created by the same module. It carries invocations,
errors, duration with the p99 threshold drawn on it as an annotation, concurrent executions with
the abuse tripwire drawn on it, and the four alarm widgets. Drawing the thresholds as annotations
is the point: a duration graph without its alarm line requires the reader to remember the number.

**Logs** — CloudWatch Logs, `retention_in_days = 7`.

Seven days is chosen, not defaulted. It covers the whole judging window with room to spare, keeps
ingest far inside the 5 GB free tier, and — the part that matters for a public demo — means
nothing a judge's browser generated is retained a week after they generated it. `never expire` is
the AWS default and would quietly keep a request log forever for a demo that exists for eight
days.

**The handler logs no DSN, no password, and no query string that could carry one.**
`scripts/deploy/cloud_chain.redact` is the single chokepoint for anything that could, and
`scripts/deploy/__init__.py` states the rule for the whole package.

---

## 5. Teardown checklist

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

- [ ] **Unset the `DEMO_URL` repository variable**, so the health cron stops failing against a URL
      that no longer exists. A permanently red scheduled workflow is noise that trains people to
      ignore a red scheduled workflow.
- [ ] **Rotate `CC_API_KEY`** — the Cloud service-account key. §4 of
      [`JUDGE-PACK.md`](JUDGE-PACK.md) records that this key can `create_database` on the cluster;
      it was used for measurement during the build and should not outlive it.
- [ ] **Drop the `mainline_demo` database**, or delete the cluster, once the evidence files are
      archived. Everything in it is synthetic, so this is housekeeping rather than a data
      obligation.
- [ ] **Confirm the CloudWatch log group is gone.** `teardown.sh` removes it; a log group that
      outlives its function is the most commonly orphaned resource in an AWS teardown, and it
      keeps costing.
- [ ] If `alarm_actions` was wired to SNS, **delete the topic and its subscriptions.**

### What teardown will not touch

The AWS account holds four unrelated projects. Everything this deployment creates carries the
`mainline-demo-` name prefix and the tag `project=mainline`, and `teardown.sh` filters on the tag
and **refuses to proceed** if the filter returns resources it did not expect. Step 5 above is the
independent confirmation of that, run after the fact rather than trusted in advance.

---

## 6. What is not observed, and should be said

* **CockroachDB Cloud metrics are not scraped.** Basic exposes a metrics endpoint; nothing here
  reads it. The demo's database health is inferred from `/v1/health` answering, which is a weaker
  statement than "the cluster is healthy" and is written here so nobody reads more into a green
  cron than it carries.
* **The spend cap is the real backstop.** `spend_limit` on the cluster is a hard ceiling: the
  cluster stops before the bill grows. That is a cost control, not an alarm, and there is no
  alert on approaching it.
* **CloudFront metrics have no alarms.** The distribution's 4xx/5xx rates appear in the console
  and nothing watches them. The health cron traverses CloudFront on every run, so a broken
  distribution shows up there — one hop later than a dedicated alarm would catch it, at zero cost
  and zero configuration.
* **There is no alarm on the thing that matters most.** No CloudWatch metric can tell you the gate
  stopped refusing. Only `demo_acceptance.py` can, and it runs at deploy time rather than
  continuously — see [`JUDGE-PACK.md`](JUDGE-PACK.md) §6. A monitoring page that implied otherwise
  would be the most misleading document in this repository.

---

## 7. Cost, itemised

| Line | Basis | USD/month |
|---|---|---|
| CloudWatch alarms | 4; first 10 free | 0.00 |
| CloudWatch dashboard | first 3 free | 0.00 |
| CloudWatch Logs | 7-day retention, far inside the 5 GB free ingest | 0.00 |
| GitHub Actions cron | public repository | 0.00 |
| CloudWatch Synthetics canary | **refused** — see §1 | ~~10.37~~ |
| **Total observability** | | **0.00** |

The whole stack, for context, is estimated at **≈ $0.03/month, worst case under $1.00**
(`deploy-plan.md` §2.3). Observability is free within it, and the single line that would not have
been is the one that is not there.
