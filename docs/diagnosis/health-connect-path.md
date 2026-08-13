<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The ten seconds in `/v1/health` — the connect, not the query, and not only the unhealthy case

**Analyst:** `w5-connect-path` · **Measured 2026-08-14 on TRAPPOINT**, HEAD `e944407` (working
tree dirty), local CockroachDB v26.2.5, psycopg 3.3.4, Python 3.13.14 ·
**Verdict: two defects, both in `db.py`, neither in `health.py`. `health.py` is byte-identical.**

---

## 0 · The one-line summary, and the sentence the brief got half right

`/v1/health` did take 10.1 s. The brief attributed it to the 503 test's unreachable address.
That is where the suite *saw* it, and it is not where it lives: **the healthy path took 10 s
too**, on any DSN spelled `localhost`, against a database that answered `200`.

Decomposed by timing the two halves separately against a healthy database:

| | seconds |
|---|---:|
| `db.connection()` | **10.102** |
| `HEALTH_STATEMENT` | 0.003 |

The whole of it is the connect. It is not the statement, not the `40001` retry loop
(`READ_RETRY_ATTEMPTS` retries `40001` only; every other SQLSTATE propagates on first
occurrence and a connect failure is not `40001`), and nothing in `health.py`.

---

## 1 · Mechanism (a) — a dead address family, paid for in full

```
socket.getaddrinfo('localhost', 26257)
    -> [ (AF_INET6, ('::1', 26257)), (AF_INET, ('127.0.0.1', 26257)) ]

raw socket connect  ::1:26257        -> TimeoutError after 12.003 s (settimeout(12))
raw socket connect  127.0.0.1:26257  -> connected in 0.0005 s
```

The pinned container publishes IPv4 only and `::1` black-holes rather than refusing, so the
IPv6 attempt waits out whatever budget it is given.

**The budget is applied per address, and in psycopg 3.3 that is psycopg's own doing, not
libpq's.** `psycopg/_conninfo_attempts.py::_resolve_hostnames` calls `socket.getaddrinfo`
itself and returns **one attempt per answer**; `Connection.connect` then loops over the
attempts applying `timeout_from_conninfo(params)` to each — its own comment says *"Because the
libpq async function doesn't honour the timeout, we need to reimplement the repeated
attempts."* So with `CONNECT_TIMEOUT_SECONDS = 10` and two addresses, a cold connect to
`localhost` cost 10 s + 0.5 ms, and a cold connect to a host with *n* dead addresses cost
`n × 10 s`.

### 1.1 The correction to the record: 130.1 s is psycopg's default, not the OS's

The repository-root `conftest.py` recorded **130.1 s** on 2026-08-10 and attributed it to "a
black-holed address" waiting out the operating system's TCP timeout. Measured here:

```python
>>> psycopg.conninfo._DEFAULT_CONNECT_TIMEOUT
130
```

130.1 s is `130` — psycopg's own default connect timeout — spent on the one dead address,
plus the 0.1 s the live one then took. **The kernel never gave up; psycopg did.** The
attribution matters because it changes what the number is a property of: it is not a fixed
cost of black-holed addresses, it moves the moment a DSN or `$PGCONNECT_TIMEOUT` says
something, and it is therefore *n* × whatever the budget is rather than a constant.
`conftest.py`'s remedy (`PGCONNECT_TIMEOUT=5`) is still correct and is not touched here — and
it is now honoured by `db._open` rather than overruled by it, which is mechanism (b).
**`conftest.py:16` and `conftest.py:116` still carry the incomplete attribution.** That file is
not this worker's to edit; the correction is recorded here and in `db.py`'s docstring, and
whoever owns the repository-root conftest should fold it in. The remedy is right either way,
so nothing is broken by the delay — only the reasoning printed beside it.

`scripts/deploy/measure_beats.py:118-125` records the same mechanism accurately and reaches
the same conclusion; `docs/ci/demo-suite-order.md §5.1` and `docs/diagnosis/refusal-that-writes.md §5`
both measured it before this wave. What none of them had was §3 below.

---

## 2 · Mechanism (b) — `_open` silently outranked the caller

```python
def _open(dsn: str) -> psycopg.Connection[Any]:
    return psycopg.connect(dsn, autocommit=True,
                           connect_timeout=CONNECT_TIMEOUT_SECONDS, ...)
```

A **keyword argument** outranks both the DSN's query string and `$PGCONNECT_TIMEOUT`. Two
consequences, both measured:

* `test_health_is_503_when_the_database_does_not_answer` asks for `connect_timeout=2` in its
  DSN and waited **10.055 s**. That single test was the slowest node in a 50.9 s suite.
* The repository-root `conftest.py` exports `PGCONNECT_TIMEOUT=5` for the express purpose
  that *no fixture can hang*, and was overruled by a module that had never heard of it.

No caller — not a test, not an operator, not the Lambda — could choose a connect budget
shorter than this module's.

---

## 3 · Is this production, or is it a workstation artefact? **Measured, not assumed.**

`measure_beats.py` says *"That is a workstation artefact, not a Lambda property"*. That claim
had never been checked against the deployed hostname's DNS. It has now been.

**Read-only DNS, 2026-08-14.** The hostname is the one the deploy programs' own transcripts
name as the cluster they applied the 271-file chain and the demo seed to
(`evidence/deploy/cloud-chain.json`, `evidence/deploy/cloud-seed.json`,
`evidence/deploy/judge-access.json`, `docs/deploy/cloud-database.md`,
`evidence/ccloud/cluster-list.txt`). It is identified below by the first 12 hex of its
SHA-256 so this page can be re-checked without publishing the cluster id inside it.

| name | AAAA answers | A answers | CNAMEs traversed |
|---|---:|---:|---:|
| **deployed cluster, `host#d390361c910f`** | **0** | **3** | 2 |
| control `dns.google` | 2 | 2 | 0 |
| control `cloudflare.com` | 2 | 2 | 0 |
| control `example.com` | 2 | 2 | 0 |
| control `aws.amazon.com` | 8 | 4 | 2 |

**The deployed hostname publishes no AAAA record. It is A-only, behind two CNAMEs, with three
A records.**

The controls are not decoration, and the first attempt at this measurement was wrong without
them. `socket.getaddrinfo(host, AF_INET6)` answered `WSANO_DATA` for **`dns.google`**, which
certainly has AAAA — this workstation has no global IPv6 and the Windows resolver suppresses
AAAA answers it cannot use. A run that had asked `getaddrinfo` alone would have reported "no
AAAA" about every name on the internet and called it a finding. The table above is
`Resolve-DnsName`, which issues the query and reports the RRset, and the four controls are
what make its zero readable. `aws.amazon.com` is there specifically because the deployed name
sits behind two CNAMEs and a query path that stopped at a CNAME would report 0 for everything
that has one.

### 3.1 What follows, stated precisely

1. **There is no AAAA-first cold-start tax on the deployed function today.** Mechanism (a) as
   observed locally is a workstation artefact, and `measure_beats.py`'s sentence is correct —
   now measured rather than asserted. This is **not** a production latency finding, and it
   does **not** bear on the p99 alarm or on the cold-start bill as things stand. `LATENCY.md`'s
   measured 14 s is not superseded and is not touched.
2. **The deployed name resolves to THREE addresses, and mechanism (a) was never about IPv6.**
   It is about a budget applied per address. Under the old code a single unhealthy address
   among those three cost 10 s of a cold start, and all three cost **30 s** — past the
   function's own timeout, which converts "the database is unreachable" into "the function
   timed out", the precise failure `CONNECT_TIMEOUT_SECONDS` exists to prevent. Cloud rotates
   these addresses; nobody chose "three" and nobody is notified when it changes.
3. **The absence of AAAA is a fact about Cockroach Labs' DNS today, not a property of this
   code.** A dual-stack name — a cluster recreated, a Cloud change, a different region —
   silently restores the full 10 s per cold start under the old connect path and nothing in
   the repository would notice. The fix removes the exposure rather than the symptom.

---

## 4 · The fix, and what was deliberately NOT done

Two changes, both in `db.py`, both in the connect path.

**(a) `_address_that_answers` / `_race`.** The addresses psycopg is about to walk are taken
from psycopg's own `conninfo_attempts(params)` — not resolved a second time, so the set raced
is by construction the set the driver would otherwise walk one timeout at a time. One
non-blocking socket is opened to each **at once** and a single `selectors` wait takes the
first that answers; its address is handed back as `hostaddr`, which collapses psycopg's
attempt list to one. A dead address costs nothing rather than one full timeout, and the
budget now bounds the **whole** connect instead of each attempt separately.

No thread and no retry. `EVENT_WRITE` is the correct mask on both platforms because
`selectors.SelectSelector` merges the exception set into the write set on Windows
(`r, w, x = select.select(r, w, w, timeout); return r, w + x`), and `SO_ERROR` separates
*connected* from *failed* — being woken is not the same as having arrived.

Three boundaries are deliberate:

* **One address gets no probe at all.** The probe costs one TCP round trip, and the deployed
  DSN would pay it on every cold start if it were levied unconditionally. Where there is one
  address the budget already bounds the whole connect, so there is nothing to buy. (Today's
  deployed name has three, so it does race; a single-A cluster pays nothing.)
* **A comma-separated `host` list is left alone.** That is a caller naming specific hosts in a
  specific order, possibly with `target_session_attrs` or `load_balance_hosts`. Racing them
  would silently re-decide a decision the caller made.
* **The host NAME is kept beside the address.** `hostaddr` is added, never substituted, because
  `sslmode=verify-full` matches the certificate against `host` and SCRAM salts with it. An
  address that replaced the name would silently disable the Cloud DSN's verification. Asserted
  in `test_a_dead_address_is_not_paid_for_one_whole_timeout`.

**(b) `_supplied_connect_timeout`.** `CONNECT_TIMEOUT_SECONDS` is now supplied when neither the
DSN nor `$PGCONNECT_TIMEOUT` states a budget, and imposed on nobody. That is libpq's own
precedence order. The bound the module docstring promises is still absolute — something always
states a budget, and where nothing else does it is still 10 s.

### 4.1 An earlier draft, and why the failure path raises instead of falling through

The first version fell through to psycopg when the race found nobody home, on the reasoning
that psycopg's own error message is the authentic one. Measured: `localhost:1` then cost
**22.1 s** — 2.1 s to establish that both loopback addresses were dead, then 20 s for psycopg
to establish it again, ten seconds per address. **Worse than the 20.1 s defect it was meant to
fix.** The budget is a total or it is nothing, so that case now raises here, naming every
address and what each did. Nothing is lost: everything psycopg says that this cannot — the
sslmode, the auth method, the server's own complaint — is said *after* a TCP connection
exists, and an address that gets that far wins the race and is handed over.

### 4.2 Explicitly not done

* **The test's DSN was not rewritten to `127.0.0.1`.** That greens the suite and leaves the
  deployed function exposed; it is the class of green this repository has been burned by.
* **`CONNECT_TIMEOUT_SECONDS` was not lowered.** Lowering it shortens a wasted wait and breaks
  genuinely slow cold connects. It is unchanged at 10.
* **No retry and no thread** was added to paper over the wait.
* **No ceiling, threshold or assertion was weakened.** `test_reads.py`'s `body["seconds"] < 5.0`
  is untouched and now passes with three orders of magnitude of headroom. `timeout` remains a
  reliability bound and did not move. `health.py` is byte-identical —
  `0b9f26e986217895738640fa0cc4430bd3bd6b91f57af6db1e72bb2c8a4145de` before and after.

---

## 5 · The four-way measurement

`health.health(dsn=…)`, each cell in a **fresh interpreter** (one genuine cold connect per
cell), healthy database `w3_demo_api_885e1182f4e6`, unreachable address `:1`.

| DSN spelling | path | before, cold | after, cold | before, warm | after, warm |
|---|---|---:|---:|---:|---:|
| `localhost:26257` | healthy → 200 | **10.124 s** | **0.030 s** | 0.009 s | 0.007 s |
| `127.0.0.1:26257` | healthy → 200 | 0.017 s | 0.014 s | 0.008 s | 0.007 s |
| `localhost:1` | unreachable → 503 | **20.081 s** | **2.035 s** | 20.099 s | 2.022 s |
| `127.0.0.1:1` | unreachable → 503 | 10.063 s | 10.060 s | 10.022 s | 10.042 s |
| `127.0.0.1:1` + `connect_timeout=2` | unreachable → 503 | **10.055 s** | **2.021 s** | 10.036 s | 2.021 s |

Both spellings on the healthy path are now under the 5 s ceiling by a factor of ~100. The
`127.0.0.1:1` row is unchanged **by design**: an address literal resolves to one attempt, there
is nothing to race, and psycopg's own budget governs it. (Its raw socket refuses in ~2 s under
the Windows loopback stack while psycopg waits the full 10; that is psycopg's business and
buying it back would mean levying the probe on every single-address connect, including the
deployed one.)

The unreachable rows do not get warmer because `health.py` calls `db.close()` on the error
path, so every unreachable call is a cold connect. That is correct and was not changed.

---

## 6 · Falsification — each mechanism, independently

Both mechanisms were reverted separately in the working tree and the controls re-run. `db.py`
was restored from a byte copy afterwards and the SHA-256 compared back (`restored: True`).

| control | fixed | R1 both reverted | R2 only (b) reverted | R3 only (a) reverted |
|---|---|---|---|---|
| `test_a_stated_connect_timeout_is_supplied_never_imposed` | PASS | FAIL | **FAIL** | PASS |
| `test_a_dead_address_is_not_paid_for_one_whole_timeout` | PASS | FAIL | PASS | **FAIL** |
| `test_one_address_is_left_alone_and_no_address_is_a_bounded_failure` | PASS | FAIL | PASS | **FAIL** |
| `test_health_is_503_when_the_database_does_not_answer` (timing) | PASS | FAIL | **FAIL** | PASS |

R2 restored the `connect_timeout` keyword and kept the address race; R3 dropped the `hostaddr`
choice and kept the supplied-not-imposed budget. Each mechanism has at least one control that
goes red **if and only if** that mechanism is reverted, which is what "independent" means here.
The 503 node took 10.75 s under R2 and 2.46 s fixed — the behavioural half.

Two notes on how far each control reaches, because a control that overstates itself is worse
than none:

* The **timing** assertion in the 503 test bites on a host where `127.0.0.1:1` does not answer
  promptly (this one). On a host that refuses instantly it passes without proving anything.
  The half that is deterministic everywhere is
  `test_a_stated_connect_timeout_is_supplied_never_imposed`, which reads the budget libpq will
  apply rather than timing it, and which pins **three different numbers** (DSN 2,
  `$PGCONNECT_TIMEOUT` 4, module default 10) so that neither "always 10" nor "nothing supplied,
  psycopg's 130" can pass.
* The **address** controls use a listening socket the test owns as the live address and the
  same port on the other family as the dead one, with the resolution planted at
  `socket.getaddrinfo` — which is where psycopg does its own lookup. They need no database, no
  container and no assumption about which family this host prefers, and the live address is
  planted **first in one case and second in the other**, which is what separates "chose the one
  that answers" from "always returns the second".

---

## 7 · Full-suite numbers, read from `--junitxml` and from nowhere else

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=reuse -q -p no:cacheprovider --junit-xml=<report>.xml
```

| | tests | passed | failed | skipped | errors | wall |
|---|---:|---:|---:|---:|---:|---:|
| before | 524 | 454 | 6 | 1 | 63 | 53.617 s |
| after | 528 | **464** | **0** | 1 | 63 | 46.644 s |

**Regression set, computed node id by node id from the two XMLs: EMPTY.** Five nodes were
repaired and one removed and two added by W1/W2/W3/W4 landing beside this work — the four
`test_response_contract` movements, the `[silence]` seed node and the undeclared-query-
parameter node are theirs, not this worker's, and are named here only so the +10 is
attributable. This worker's contribution to the table is three new nodes, all passing, and
the slowest node in the suite falling from **10.040 s to 2.033 s**. The 63 errors are
blocker 1 and are not this worker's to move.

### 7.1 A first AFTER run showed seven regressions. They were not real, and the check that said so

An earlier AFTER run reported 7 nodes moving passed → failed, all in `test_gate_run` and
`test_transitions`, all with *"the affected tables are NOT byte-identical before and after
the run"*. Two measurements settled it rather than one argument:

1. All seven passed when re-run in isolation on the same tree.
2. `Get-CimInstance Win32_Process` showed a **second** full-suite pytest process
   (`--random-order`, W6's) running concurrently against the same node.

`test_gate_run.py:143` names its scratch database `w_w4_api_transitions` — a **fixed** name,
not fingerprinted like `demo_database` — so two suites in flight share one mutable database
and a "nothing persisted" assertion sees the other process's writes. This is the same defect
`docs/diagnosis/refusal-that-writes.md` diagnosed on 2026-08-13 ("the row was minted by a
second pytest process"), and it is worth recording that it is still reachable: **any two
concurrent demo-api runs on one node will produce those failures, and they look exactly like
a regression.** The numbers in the table above are from a run taken after waiting for the
other process to exit. Nothing was changed to make them green.

---

## 8 · Which side was moved, and why it was the derived one

**The code was moved. Every test and every ceiling stayed where it was.**

`test_health_is_503_when_the_database_does_not_answer` had asked for `connect_timeout=2` since
it was written, and got 10. `test_reads.py`'s `body["seconds"] < 5.0` had been asserting a
ceiling the healthy path violated whenever the DSN said `localhost`. Both were right and both
were being overruled by `_open`. The derived side was the connect path: its ten seconds were a
consequence of two choices inside one function — a keyword that outranked its callers, and a
budget spent once per address instead of once per connect — and neither choice was ever
written down as a decision. Nothing in a seed, a fixture, a threshold or an expected value was
touched.
