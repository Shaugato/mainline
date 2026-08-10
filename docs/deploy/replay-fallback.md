<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# REPLAY — what the badge means, what these bytes prove, and what they do not

**For the judge reading the demo, and for anyone who has to decide whether to believe it.**

**Owner:** `deploy / w9-evidence-bundle`.
**The bundle:** `verticals/mainline/apps/console/fixtures/bundles/demo-cloud/`.
**The capture:** `scripts/deploy/capture_demo_bundle.py`, driven by
[`verticals/mainline/apps/console/capture-plan.demo.json`](../../verticals/mainline/apps/console/capture-plan.demo.json).
**The evidence:** [`evidence/deploy/bundle-capture.json`](../../evidence/deploy/bundle-capture.json)
— every number in this document comes from that file and is reproduced here for reading,
not for citation. Where the two disagree, the evidence file is right and this page is stale.

---

## 1. The one-paragraph version

The demo screen you are looking at is fed by an **EvidenceBundle**: a directory of
request/response pairs captured from a live CockroachDB Cloud cluster in Singapore, plus
the verbatim SQL round trips behind them, plus a manifest listing every file's SHA-256.
Your browser downloads the manifest, **recomputes the digest of every listed file before
any screen is painted**, and refuses to render a single frame if one disagrees. The badge
in the chrome says `REPLAY`, permanently, and the seal beside it shows the manifest digest
your browser computed — not one the page was told.

Nothing on that screen was written by a person. The SQLSTATEs, the constraint names, the
projected counters, the clearance digest and the refusal messages are CockroachDB's own,
taken off the driver's diagnostics during the capture.

---

## 2. What `REPLAY` means, precisely

| | `LIVE` | `REPLAY` |
|---|---|---|
| Where bytes come from | an HTTP call to the read API, now | a signed, content-addressed directory captured earlier |
| What is checked | the response against its JSON-Schema contract | the same contract, **plus** SHA-256 over every file, in your browser |
| What fails closed | a contract violation | a contract violation **or** one wrong byte anywhere in the bundle |
| Code path | `HttpTransport` | `BundleTransport` |
| Surfaces, components, rendering | identical | identical |

`LIVE` and `REPLAY` differ in **one line of composition and one badge**, never in a
rendering path (`src/app/composition.tsx`). That is what makes the badge a fact rather
than a label somebody maintains: the same `MainlineTransport` interface, the same
`finishExchange()` post-conditions, the same screens.

The one property worth stating as a mechanism rather than a promise, from
`src/data/bundle.ts`:

> `BundleTransport` cannot serve a single frame before manifest verification has RESOLVED,
> and it has no verifier of its own. There is no default verifier and no
> `?skip_verification`.

A tampered bundle produces a **failure panel, not a screen**. This was exercised
accidentally and usefully during development: a static host that could not serve two
long-named frames produced

```
VERIFICATION FAILED — NO FRAME WAS SERVED
  … file-read: the manifest lists this file but it could not be read … HTTP 404
```

and every surface below it rendered its own honest absence rather than a default. The
failure path is not theoretical; it is the path the console took the first time the bundle
was served incorrectly.

---

## 3. What was captured, and from where

Measured on **2026-08-10** against `mainline-dev`, CockroachDB Cloud **Basic**,
`aws-ap-southeast-1` (Singapore), database `mainline_demo`, connected as the `mainline-sql`
SQL user.

| | |
|---|---|
| Cluster fingerprint | `source: observed` · CockroachDB CCL **v26.2.5** · cluster version `26.2` · region `aws-ap-southeast-1` |
| How the region was established | `SELECT locality FROM crdb_internal.gossip_nodes` — read, not declared |
| Schema | chain **271/271 applied, 0 failed**, `tree_fingerprint fe27b6208d228192…`, from `trappoint.deploy_chain` |
| Frames | **18** (10 read context, 3 gate beats, 5 twin reads) |
| Files in the bundle | **24** — 18 frames + 6 SQL round trips |
| Total bytes | **173 954** |
| Manifest digest | `7772131bf9424359140540254167c40e37d458cb212df0f1b78ffff359076614` |
| Wall clock | **56.1 s**, one transaction, **zero** `40001` retries needed on this run |
| Rows written to the database | **none** (§6) |

The manifest digest changes on every capture, because `captured_at` is part of the
manifest. The current one is in `evidence/deploy/bundle-capture.json` and on the screen.

### The three beats, as the cluster reported them

| # | Screen | Outcome | SQLSTATE | Exhibit | How the exhibit was obtained |
|---|---|---|---|---|---|
| 2 | `#/gate?permit=dec0de00-0006-4000-8000-000000000001` | REFUSED | `23514` | `gate_closed_when_issued` | **reported** by the driver |
| 3 | `#/gate?permit=98832832-cb53-54ce-a709-d0af8c0c7f8b` | REFUSED | `P0001` | `mainline.fn_permit_merge_gate` | **parsed** from the message |
| 4 | `#/gate?permit=f4976f47-599a-52ac-b7aa-379c80e6e849` | ADMITTED | `00000` | `clearance_digest 3b2c35b4…` | server-computed |

Beat 3 is the one to look at twice. `mainline.permit.open_blocking` is forced to zero
**out of band** — exactly what a disarmed projector or a careless `UPDATE` leaves behind —
so the `gate_closed_when_issued` CHECK is now satisfied and would admit the merge. The
merge is refused anyway, because `mainline.fn_permit_merge_gate` **re-derives** the open
count from `blocking_check LEFT JOIN disposition` instead of trusting the column. On that
screen the console shows the drift directly: the weld reads `open_blocking = 0`,
`CLEAR — WITNESSED`, and the precursor list beside it still carries an open obligation.

Beat 4 is not decoration. **A gate that always refuses is broken, not safe.** One signed
disposition closes the counter through the projection trigger and the same merge succeeds,
with a `mainline.merge_record` row and a clearance digest the *server* computed over the
sorted `(check_id, disposition_id)` set.

---

## 4. The staged frames — read this before quoting anything

Eight of the eighteen frames carry `staged: true` and a note. The bundle-level flag is
therefore true as well, and the honesty chrome says `STAGED` on those screens. Here is
exactly what that flag means here, because it does **not** mean "made up".

**Beats 3 and 4 run against two TRANSIENT subjects.** Permits `DEMO-PTW-0002` and
`DEMO-PTW-0003` were built *inside the capture transaction*, as row-for-row
`INSERT … SELECT` copies of the seeded permit `DEMO-PTW-0001`'s whole history — permit,
cited clause, boundary certificate, recall run, silence receipt, blocking check, exposure
receipt and line, and both hash-chained permit events — driven through the same triggers,
and then rolled back with everything else. **Those rows are not in the database now**, and
the live API answers 404 for them. The construction is filed verbatim in the bundle at
`sql/twin-construction.txt`.

They exist for a reason that is structural rather than convenient. The drift beat needs a
subject whose projected counter reads zero; the admission beat needs a subject carrying a
signed disposition; the seeded permit is in neither state, and cannot be in three states
at once. The console addresses a gate screen by permit id and a bundle frame is keyed by
method and path, so **three worlds need three permit ids** — there is no way to file two
answers under one name.

What is **not** staged about them is the part that carries the claim: the SQLSTATE, the
constraint name, the message, the projected counters and the clearance digest are the
cluster's own, taken off psycopg's `Diagnostic` object and its result rows during the
capture. Nothing in any frame was composed by hand.

One further staged frame is not ours: `GET /v1/permits/…/silence` is emitted by the read
API with its own `staged` flag and its own note, and the capture carries that through
untouched rather than overriding it.

---

## 5. What this bundle can and cannot support

**It can support these claims.**

1. On 2026-08-10, a CockroachDB Cloud Basic cluster running v26.2.5 in `aws-ap-southeast-1`
   held the seeded permit `DEMO-PTW-0001` in state `dispositioned` with `open_blocking = 1`
   and no disposition rows.
2. `CALL mainline.merge_permit(…)` against that permit was refused with SQLSTATE `23514`
   and constraint `gate_closed_when_issued`, reported by the driver.
3. Against a copy of the same history whose `open_blocking` had been forced to zero out of
   band, the same call was refused with SQLSTATE `P0001` naming
   `mainline.fn_permit_merge_gate`, because the gate re-derives the count.
4. Against a copy carrying one signed disposition, the same call was ADMITTED with a
   `merge_record` row and a server-computed clearance digest.
5. All of that happened in **one** `SERIALIZABLE` transaction — witnessed by
   `cluster_logical_timestamp()` being identical at both ends — and the transaction was
   rolled back.
6. The screen you are looking at was produced from these bytes and no others.

**It cannot support these claims, and no screen fed by it may imply them.**

- **Not a custody proof.** `manifest.checkpoint` is `null`, and the verifier records
  `skip:checkpoint-absent` as a finding for exactly that reason: *the frames are
  byte-checked against the manifest and the manifest is checked against nothing.* No log
  signing key exists in this deployment, so no C2SP signed note is carried and no ledger
  inclusion proof is anchored. A manifest naming a note that is not in the bundle would
  fail the verifier's own parse; inventing one would be worse.
- **Not a liveness claim.** REPLAY says a cluster answered this way *once*, at
  `captured_at`. It says nothing about whether the cluster is up while you read.
- **Not a latency or throughput measurement.** `duration_ms` on each frame is the time the
  capture spent in the database, from Australia, with no HTTP hop. It is not a measurement
  of the deployed API.
- **Not an end-to-end Australian residency claim.** Residency is split: the database is in
  `aws-ap-southeast-1` (Singapore), Bedrock inference is in `ap-southeast-2` (Sydney). The
  fingerprint's `evidence_ref` says so, and no screen may round that off.
- **Not a claim about real events.** No real incident, no real site, no real fatality.
  Every row behind these frames is synthetic and corresponds to nobody
  (`verticals/mainline/demo/DEMO-HONESTY.md`).
- **Not an observed HTTP exchange.** No read API was deployed when this was captured. The
  payloads were produced by calling the *same functions the Lambda serves* —
  `mainline_demo_api.reads` and `mainline_demo_api.transitions`' envelope builders — so
  the bytes are the bytes the live API returns for the same request, minus the network
  hop. Every frame records `via: python-call` in `evidence/deploy/bundle-capture.json`.

---

## 6. The capture mutated nothing, and here is the check

Row counts over every table the beats can write, plus `mainline.permit`'s own column
values, were taken on a **separate autocommit connection** before the transaction opened
and again after it was rolled back. Column values as well as counts, because the drift beat
mutates a column without changing a count. They were identical:
`persistence_check.identical: true`, and the round trip is in the bundle at
`sql/persistence-check.txt`.

Verified independently after the run, on a fresh connection to the Cloud database:

```
mainline.permit                    1     mainline.disposition           0
mainline.merge_record              0     mainline.blocking_check        1
mainline.permit_event              2     mainline_ops.outbox            1
DEMO-PTW-0001  dispositioned  open_blocking=1  gate_epoch=1  head_seq=2
twin 98832832 rows: 0
twin f4976f47 rows: 0
```

This is the same property the live demo relies on: because the transition beats roll back,
**the demo needs no per-visitor state, no reset button, no session table, no cleanup
sweeper and no lock.** The fiftieth judge sees what the first did.

---

## 7. Re-derive the manifest yourself

You do not have to take the seal's word for it. Everything is a static file.

```sh
# 1. fetch the bundle from the demo URL
curl -sO https://<demo-host>/bundle/manifest.json

# 2. the digest the chrome shows is just this
sha256sum manifest.json

# 3. every listed file, checked against its own entry
python - <<'PY'
import hashlib, json, urllib.request
base = "https://<demo-host>/bundle/"
m = json.load(urllib.request.urlopen(base + "manifest.json"))
bad = 0
for f in m["files"]:
    body = urllib.request.urlopen(base + urllib.parse.quote(f["path"])).read()
    ok = len(body) == f["bytes"] and hashlib.sha256(body).hexdigest() == f["sha256"]
    bad += not ok
    print(("ok  " if ok else "BAD "), f["path"])
print(m["bundle_id"], len(m["files"]), "files,", bad, "disagreements")
PY
```

From a checkout, the producer's own checker says the same thing:

```sh
cd verticals/mainline/apps/console
node scripts/capture-bundle.ts check --dir fixtures/bundles/demo-cloud
#   capture-bundle check: fixtures/bundles/demo-cloud — 24 file(s) agree.
```

and the capture script runs `check` itself and **fails the run** if it disagrees, plus a
second, independent digest pass in Python (`independent_digest_check` in the evidence),
because a producer that only trusts its own checker has one implementation, not a check.

The SQL round trips are plain text and are part of the verified set. Read them:

```
sql/beat-2-merge-refused-23514.txt     sql/cluster-fingerprint.txt
sql/beat-3-merge-refused-p0001.txt     sql/twin-construction.txt
sql/beat-4-merge-admitted-00000.txt    sql/persistence-check.txt
```

---

## 8. Regenerating the bundle

```sh
# against CockroachDB Cloud, using COCKROACH_DSN from the repo-root .env
.venv/Scripts/python.exe scripts/deploy/capture_demo_bundle.py --database mainline_demo

# rehearsal against a local node (chain + seed first; see scripts/deploy/)
.venv/Scripts/python.exe scripts/deploy/capture_demo_bundle.py \
  --dsn "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable" \
  --database w_w9_evidence_bundle
```

It captures, seals with `capture-bundle.ts seal`, checks with `capture-bundle.ts check`,
proves nothing persisted, and writes `evidence/deploy/bundle-capture.json`. Exit `0` only
when all of that holds; `1` when a beat did not match its expectation or the bundle does
not verify; `3` when the transaction stayed undecided on `40001` after six attempts — which
is **not** a refusal, and the program says so rather than pretending the gate spoke.

Two notes for whoever runs it.

* **`40001` is retried at the transaction level**, six attempts, exponential backoff with
  full jitter. A single-node Docker cluster never produces `RETRY_SERIALIZABLE`; a managed
  multi-node cluster does, and it killed the first Cloud run of 2026-08-10
  (`docs/leads/deploy-plan.md` §1.2). This run needed **zero** retries; the loop is
  insurance against a failure mode observed once, not a workaround for a constant.
* **`capture-bundle.ts capture` is deliberately not used.** Its SQL step spawns one
  `cockroach sql` process per statement, so each statement lands in its own session and its
  own implicit transaction, and a savepoint cannot span process boundaries — which makes
  the three-beats-in-one-rolled-back-transaction discipline impossible to express. `seal`
  and `check` are used unchanged. The plan file records the same reasoning.

### Serving it

The bundle is 24 static files, ~174 KB, and needs no backend. The console is built with
one variable:

```sh
VITE_MAINLINE_BUNDLE_URL=/bundle/ pnpm exec vite build
# then copy fixtures/bundles/demo-cloud/ to <site>/bundle/
```

One deployment-time gotcha, found the hard way: two frame file names are **143 and 151
characters** long (a request key is the file name, and a clause-version key carries a
64-hex commit id). Under a long parent path on Windows that exceeds `MAX_PATH` and a local
static server answers `404` for them — which the verifier correctly reports as a bundle it
will not serve. On S3 + CloudFront the limit is 1 024 bytes for a key and it is a
non-issue, but a local rehearsal should be run from a short path.

---

## 9. The cut line

From `docs/leads/deploy-plan.md` §4, stated here so it is in the document a judge reads:

> **If the live API is not green 72 hours before the deadline, this is the demo, and the
> submission says so.**

That is not a degradation quietly applied. It is a working demo URL showing the gate
refusing twice and admitting once, from bytes that are verified in the judge's own browser,
with no backend that can fail during judging — and a submission text that names it as the
replay path rather than implying a live one. **Nobody is allowed to let the live path hold
the URL hostage.**

When the live API *is* green, both remain reachable on the same URL. The badge flips to
`LIVE` for the surfaces the API serves, `REPLAY` stays available, and the same screen with
two sources and one badge that never lies about which one you are looking at is the story
— not the compromise.

---

## 10. Known gaps in this artefact

Published here rather than left for a reader to find, in the manner of `docs/HONESTY.md`.

1. **No custody anchor.** `manifest.checkpoint` is `null` (§5). The console renders that as
   an absence and the verifier records it as a SKIP finding, which is correct, but it means
   the manifest is checked against nothing outside itself. Closing this needs a C2SP signed
   note and a log verification key, both owned by the custody domain.
2. **`POST /v1/demo/gate-run` is not addressable from this console.** The console declares
   sixteen resources and `demo_gate_run` is not one of them, so the demo driver renders an
   honest panel naming the three files that would change. The three beats therefore reach
   the screen as three permit-addressed gate screens, which is why the twins exist (§4).
   This is a real seam between this bundle and the live gate-run endpoint, and it is W8's
   and the console owner's to close, not this capture's to route around.
3. **The `P0001` refusal's reason set is weaker than the `23514` one.** Beat 2's payload
   names the obligation, its origin, its clause, its severity and its virulence; beat 3's
   `mus` degrades to a single `capability_gap` element. That is the read API's own
   `explain_refusal` behaviour for a `RAISE`-sourced refusal, carried through unchanged, and
   the console labels it `WEAKENED DIAGNOSIS · constraint_source is parsed` on screen.
   Improving it belongs to the refusal builder, not to the capture.
4. **`tier` in the cluster fingerprint is `null`.** The Cloud tier is not readable over
   pgwire by this SQL user, and a value copied from a console screenshot would be
   `declared` inside a block whose whole point is that it is `observed`.
