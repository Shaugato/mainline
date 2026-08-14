<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `POST /v1/demo/gate-run` answered NOT PROVEN about a transaction that persisted nothing

**Worker:** W2, cloud-hardening wave · **Measured 2026-08-14 on TRAPPOINT**, repo
`D:/CoackroachDBxAWS/mainline`, working tree at HEAD `d098721` plus the ci-green wave's
uncommitted work, `.venv/Scripts/python.exe` (Python 3.13, pytest 9.1.1, psycopg 3.3.4),
CockroachDB CCL **v26.2.5** on `127.0.0.1:26257`.

Dispatched under `docs/leads/cloud-hardening-final.md` **W2**, whose ruling **R2** says the
question is *what wrote the row* and forbids narrowing the check to make the red go away.
This document answers that question with a reproduction rather than a hypothesis, and it
records one prediction of the plan that the measurement **falsified**.

---

## 0 · The answer in five lines

1. The writer is **any other session that COMMITS a row into any of the ten tables**
   `_FINGERPRINT_SQL` counts, between the run's two readings.
2. On this workstation those writers are named and countable: `test_transitions.py`'s own
   `fresh_history` and `bare_permit` fixtures, which have committed **677 `PTW-W4-*`** and
   **102 `PTW-BARE-*`** permits into the shared scratch database, at up to **4 per second**.
3. They land inside a gate run's window only when **two pytest sessions share one scratch
   database**. Reproduced deliberately: **5 failed** in `test_gate_run.py`, the lead's exact
   failure string.
4. **Two judges pressing the button at once does NOT do it.** The plan named that as the
   cause; it is measured here and it is not. Two gate runs persist nothing, so neither can
   move the other's fingerprint.
5. So this is R2's **third** outcome — *a concurrent CALLER can write it, and the contract
   has a gap* — and it is closed by adding run-scoped evidence beside the ten counts, never
   by narrowing them.

---

## 1 · What the check claimed, and what it actually measured

`gate_run.py` takes a fingerprint before the beats' transaction opens and again after it is
rolled back:

```
before = _fingerprint(conn, opening.permit_id)     # ten unscoped count(*) + the permit row
   … four beats, one SERIALIZABLE transaction, rolled back …
after  = _fingerprint(conn, resolved.permit_id)
identical = before == after
```

and, when `identical` was false, appended

```
the affected tables are NOT byte-identical before and after the run;
the transaction was supposed to persist nothing
```

to `failures`, which flipped `verdict` to `NOT PROVEN`.

**The two readings are separated in time and unscoped in space.** They therefore measure
*"the ten tables did not change"*, which is a strictly stronger statement than *"this run
changed nothing"* — and the stronger statement is false whenever anybody else commits. The
payload then reported somebody else's row as its own failure, in a sentence that accuses
the run of a write it had not made.

---

## 2 · Falsifying the plan's prediction first

`docs/leads/cloud-hardening-final.md` §0.1.1: *"Two judges pressing the button at the same
moment is precisely this interaction."* Constructed and run — two `gate_run`s on two
connections from `db._open`, released together by a `threading.Barrier`:

```
ARM1 a: verdict=PROVEN identical=True failures=[]
ARM1 b: verdict=PROVEN identical=True failures=[]
```

**It is not the interaction.** A gate run persists nothing, so a second one cannot move the
first one's counts. This matters practically: had it been true, the plausible repair would
have been to serialise the endpoint — and serialising it would have destroyed the one
property that lets fifty judges share one seeded history.

Pinned as an assertion, so the prediction cannot quietly come back:
`test_gate_run.py::test_two_judges_pressing_the_button_at_once_do_not_move_the_fingerprint`.

---

## 3 · The writer, constructed

Same run, one change: a **committing** caller lands between the two readings — one row into
`mainline.permit`, on a separate autocommit connection, which is precisely what
`bare_permit` does.

```
ARM2 verdict=NOT PROVEN identical=False
     failure: the affected tables are NOT byte-identical before and after the run;
              the transaction was supposed to persist nothing
     moved: {'mainline.permit': (780, 781)}
     permit_row identical: True          <- the run's own subject never moved
```

One row, from anybody, is enough. `permit_row identical: True` is the whole finding: the
subject this run drove was untouched, and the run still called itself a failure.

---

## 4 · The writer, identified in the suite — by its own rows

Not inferred. `mainline.permit` in the shared scratch database
`w_w4_api_transitions_dd0a1855b3aa`, grouped by the `external_ref` its minter writes:

| rows | `external_ref` family | who writes it |
|---:|---|---|
| **677** | `PTW-W4-…` | `test_transitions.py::_seed_permit`, via the `fresh_history` fixture |
| **102** | `PTW-BARE-…` | `test_transitions.py::bare_permit` |
| 1 | `PTW-PROOF-1` | `scripts/proof/gate_refusal.py::seed_history` — the demo subject |

Each `fresh_history` also commits a `blocking_check`, an `exposure_receipt`, its
`exposure_line`s, two `permit_event`s and a `mainline_ops.outbox` signal — **six of the ten
tables the fingerprint counts.** Measured arrival density: up to **4 permits committed per
second**.

Within one pytest session these are sequential and can never land inside a single gate run's
window. They land inside it when **two sessions share the database**, which is the state
`docs/ci/demo-suite-order.md` records (`w_w4_api_transitions` growing across runs to 834
permits) and which the fingerprinted database name reduced but did not remove: two sessions
at the same tree compute the same fingerprint and therefore the same name.

### 4.1 The reproduction

`test_transitions.py` in one process; three seconds later `test_gate_run.py` in another,
both `--crdb=reuse`, both on `w_w4_api_transitions_dd0a1855b3aa`:

```
FAILED test_gate_run.py::test_gate_run_verdict_is_proven
FAILED test_gate_run.py::test_every_table_row_count_is_identical_across_a_gate_run
FAILED test_gate_run.py::test_the_payload_proves_its_own_persistence_claim
FAILED test_gate_run.py::test_two_consecutive_runs_see_the_same_subject
FAILED test_gate_run.py::test_concurrent_runs_do_not_collide
5 failed, 22 passed, 1 skipped in 10.07s
```

— four of the five node ids the plan named, verbatim, carrying the identical assertion
string. An instrumented reading of the two fingerprints, taken **0.95 s apart** inside one
`gate_run` call, shows exactly which rows arrived and whose they are:

```
moved: mainline.permit 803→804, permit_event 1742→1746, merge_record 243→244,
       disposition 345→346, ledger_intake 244→245, blocking_check 698→699,
       exposure_receipt 752→753, exposure_line 752→753, outbox 698→699
newest mainline.permit      : PTW-W4-88bd28810188   permit 88bd2881-0188-…
newest mainline.permit_event: permit 88bd2881-0188-…  merged → suspended
newest mainline.disposition : permit 4ca0496c-a6f5-…
```

**Every appeared row belongs to a permit that is not this run's subject.** That is the
attribution, and it is the fact the repair is built on.

---

## 5 · Which of R2's three outcomes

> *a concurrent **test** wrote it (then the suite's isolation is the defect); the **handler**
> wrote it (then the handler is the defect and the check just caught it); or a concurrent
> **caller** can write it (then the contract has a gap).*

* **The handler is not the defect.** Twenty gate runs across two full-suite orders on a
  quiet workstation produced **zero** in-flight deltas, and the whole-database sweep over
  ~89 tables passes. The four beats are savepoint-fenced and the transaction is rolled back;
  measured separately, replacing the final `rollback()` with a `commit()` persists
  **nothing**, because each beat has already been undone by its own savepoint.
* **A concurrent test wrote it** — true, and it is §4. The suite's isolation is *a* defect,
  and it belongs to the fixture owners; the reproduction and the readable failure message
  are handed to them rather than papered over.
* **A concurrent caller can write it** — true, and it is the one that reaches a judge. On
  Cloud the demo URL is bounded-but-open by the founder's choice, and the console exposes
  four **committing** transitions (`merge_permit`, `sign_disposition`, `materialise_checks`,
  `suspend_permit`). One judge signing a disposition while another presses gate-run moves
  `mainline.disposition`, and the second judge is told the demo persisted something.
  **That is the contract gap, and it is a property of the code, not of this workstation.**

---

## 6 · The repair, and what it deliberately is not

Made under R2's second half, with the schema, the document and the code moving together:
`contracts/gate-run.schema.json`, `docs/deploy/gate-run-contract.md` §3, `gate_run.py`.

**What did NOT change — check this first.** `_FINGERPRINT_SQL` is byte-for-byte the same ten
unscoped `count(*)`s. `_FINGERPRINT_TABLES` still holds all ten names. No `WHERE permit_id`
was added to either. No tolerance, no "allow a delta of one", no retry-until-equal, no
serialisation of the endpoint. `identical` is still computed, still over all ten tables plus
the permit row, and is still in the payload.

**What was ADDED, beside it.** A reading the run can be held to, because it is built from an
identifier no other writer holds:

* `self_evidence.minted_disposition_id` — the `uuid4` beat 4 mints for its disposition —
  and the count of rows carrying it **after** the rollback, which must be `0`. Beat 4 is the
  only beat the database ACCEPTS, and every other row it causes is written by
  `mainline.merge_permit` in the same transaction as that disposition; if this row is gone,
  that transaction did not commit and none of its rows are here either.
* `subject_row_counts` — `merge_record`, `permit_event` and `disposition` for **this permit**,
  taken in both fingerprints.
* `permit_row` — unchanged, and still where beat 3's out-of-band `UPDATE` shows up. This is
  the reading the schema keeps *"because the attack beat mutates a column without changing a
  count"*, and it is untouched.

`self_persisted` is the OR of those three. **The verdict now keys on `self_persisted`**, and
a count delta that is nobody's doing is reported as `concurrent_writes` — a fact about the
database this demo shares — instead of as this run's failure.

### 6.1 It can still fail, and it is made to

`test_transitions.py::test_a_run_that_really_persists_is_caught` swallows beat 4's
`ROLLBACK TO SAVEPOINT` and turns the closing rollback into a commit, against a throwaway
`fresh_history` permit, and requires `self_persisted is True`, the minted disposition present
in **1** row, the subject counts moved and the verdict `NOT PROVEN`. Written this way because
the first draft of the plant — swapping only the final rollback — **did not fire**, measured;
the savepoints had already undone everything. A control that could not fail would have been a
worse outcome than the red it replaced.

`test_gate_run.py::test_a_concurrent_committer_moves_the_counts_and_is_not_this_runs_failure`
asserts **both** halves: that the ten unscoped counts still SEE the foreign row — that
assertion goes red if anyone ever narrows `_FINGERPRINT_SQL`, which is R2's tripwire — and
that the verdict no longer blames the run for it.

---

## 7 · What is still red under a two-session collision, and why it is left red

Re-running §4.1's collision after the repair: **2 failed, 27 passed** where there were five.

`test_every_table_row_count_is_identical_across_a_gate_run` still fails, and that is correct.
It counts **every base table** in four schemas and requires all of them unchanged; its
premise is EXCLUSIVE ACCESS to the database, and under two sessions that premise is false.
It was not weakened. Its failure message now states the diagnosis in one line — that
`self_persisted` is `False`, that the red is therefore a second writer on a named database,
and where the reproduction is — because a lane whose diagnosis is unreadable will not be
read.

**The suite-isolation defect behind it is real and is not this worker's to fix**: two
sessions at one tree compute one fingerprint and therefore one database name. The honest
fixes are a per-session database or a lock, both of which belong to the fixture owners, and
both of which are recorded here rather than smuggled into a file this worker owns.
