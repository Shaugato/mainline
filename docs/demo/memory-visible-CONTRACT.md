<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MEMORY-VISIBLE — the cell-to-pointer contract

**Worker:** `w1-contract` · **Plan:** `docs/demo/memory-visible-plan.md` · **Date measured:** 2026-08-15
**Origin read:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
**Captured by:** `python scripts/demo/capture_memory_loop.py --with-post`
**Recordings:** `verticals/mainline/apps/console/fixtures/memory-loop/`
**Replayed offline by:** `tests/demo/test_memory_loop_contract.py`

This file is the factual spine of the memory-visible plan. Every row below was resolved out of
a response body the deployed API actually sent, and every one of those bodies is on disk, byte
for byte, in the fixture directory. **Nothing here was typed from memory, inferred from a
schema, or copied out of the plan.** Where the plan's §3 sketch shows a value the API does not
return, §5 says so and escalates rather than quietly substituting a near neighbour.

---

## 0 · What was measured, and the bytes it came back in

Six exchanges — five GETs and exactly one POST — on 2026-08-15, in one run of the capture tool.
Addressing came from `GET /v1/demo/subjects` and from nowhere else (R-M8); the tool holds no
UUID literal, and neither does this document.

| capture | method · path | status | bytes | `sha256` of the body | received (client clock) |
|---|---|---|---|---|---|
| `subjects` | `GET /v1/demo/subjects` | 200 | 8,941 | `2678dcd2bcf381bd48ab3f32e20aca0307fe92e6154171f703c4ac5330328535` | `2026-08-15T11:57:16.056943Z` |
| `blocking-checks` | `GET /v1/permits/{permit_id}/blocking-checks` | 200 | 2,408 | `7825a6b6e42f67d69487e6752697cbb3b939145ffbdf4bba34b14e594f271f42` | `2026-08-15T11:57:16.767855Z` |
| `ancestry` | `GET /v1/clauses/{clause_uuid}/ancestry` | 200 | 3,744 | `0342ffa41df99dd5fc562b53ff646e605484b66e156a3616a18ac7981a6d53ac` | `2026-08-15T11:57:17.572136Z` |
| `recall-run` | `GET /v1/recall-runs/{run_id}` | 200 | 2,223 | `c8199c14ebf8d10965a6d332b2693e53e90deee74663031550e55c5cec973a62` | `2026-08-15T11:57:18.262174Z` |
| `ledger` | `GET /v1/ledger` | 200 | 9,505 | `418a4c61a7ef3f62eba4ce777fb731de1f4713d2e48913943ddc7e6c3427d001` | `2026-08-15T11:57:18.984555Z` |
| `gate-run` | `POST /v1/demo/gate-run` | 200 | 10,499 | `65a417dc1d3f61d516ebfe34b5aeed139c4c0bc38cba133261b013b78fa0caac` | `2026-08-15T11:57:21.734183Z` |

The permit, clause and run ids in the middle three paths are the ones `/v1/demo/subjects`
returned; the literal paths are recorded in `fixtures/memory-loop/manifest.json`, which is a
recording and is therefore exempt from R-M8's ban on identifiers in source.

**One POST, and one only.** `--with-post` is off by default in the capture tool. The gate-run
recording above is the only POST this worker fired at the deployment.

---

## 1 · How to read the table

### 1.1 Two pointer spaces, and they are not the same one

The plan's §4 addresses the **whole envelope** — `/data/checks/0/severity`. The envelope's own
`provenance[]` addresses **`data` alone** — `/checks/0/severity`. This is not an inconsistency
to be tidied away; it is how `envelope.py` builds the list (`_POINTER` refuses anything that is
not "an RFC 6901 pointer into data"). The consequence is structural and W3 must design for it:

> **Every field outside `/data` carries no chip and can carry none.** `statement_refs`,
> `observed_at`, `server_date`, `schema_id`, `resource`, `staged` are all outside the space
> `provenance[]` can address. The two SQL cells are in this category. Their chip column reads
> *none claimed*, and that is a property of the envelope's design, not a gap in the payload.

So: to find the chip for an envelope pointer, strip the leading `/data` and look the remainder
up in `provenance[]`. A pointer that does not begin `/data` has no chip.

### 1.2 Chip resolution is the console's own algorithm, not a new one

`verticals/mainline/apps/console/src/features/gate/provenance.ts::lookupProvenance` already
answers this question for the React console, and its answer is the one this contract uses:

1. **exact** — an entry whose `pointer` equals the pointer asked for.
2. **inherited** — otherwise, the *longest* entry that contains it, where "contains" means
   `pointer === ancestor || pointer.startsWith(ancestor + '/')`. That module's own comment:
   *"The ancestor rule is not a loophole… The UI shows WHICH pointer carried the claim, so an
   ancestor-derived chip is visibly weaker than an exact one."*
3. **none claimed** — otherwise. Never a default, never a substitute (R-M3).

`envelope.py`'s `Provenance` docstring is the emitter's half of the same rule: *"A pointer is
claimed once. The first chip for a pointer wins, so a caller can add the precise claim
(`derived` for `/checks/3/open`) before the sweeping one (`db:column` for `/checks/3`) and get
the precise one."* Sweeping claims are therefore deliberate, and honouring them is correct.

**The chip column names which of the three happened.** `` `db:column` inherited from `/checks/0` ``
is a weaker claim than `` `db:column` exact `` and must be rendered as weaker.

### 1.3 The `[key=value]` selector

Plan §4 requires the two ledger leaves be *"found by `entry_kind`, never by array index"*, and
the two SQL statements be found by `object`. Neither is expressible in bare RFC 6901, so this
contract uses one extension — **four distinct selectors, used by fourteen rows** and nowhere
else:

```
/data/leaves/[entry_kind=precursor_event_ingested]/leaf_hash_hex
```

`[key=value]` selects the **single** element of the array whose `key` equals `value`, and is an
error if it matches zero elements or more than one. On 2026-08-15 the selectors resolved to:

| selector | resolved to |
|---|---|
| `/data/leaves/[entry_kind=precursor_event_ingested]` | `/data/leaves/2` |
| `/data/leaves/[entry_kind=blame_closure_computed]` | `/data/leaves/3` |
| `ancestry /statement_refs/[object=mainline.clause_blame_current]` | `/statement_refs/0` |
| `recall-run /statement_refs/[object=mainline_meas.recall_run]` | `/statement_refs/0` |

Chips are resolved against the **resolved** pointer, because that is the pointer `provenance[]`
was written about.

### 1.4 The value column's four forms

| form | meaning | how the test checks it |
|---|---|---|
| `` `<json>` `` | the JSON value, exactly | equality against the fixture |
| `` `sha256(utf8)=<hex>, <n> B` `` | a value too long for a table cell | digest and byte length of the UTF-8 encoding |
| ``volatile `<json>` `` | recorded from this run; a different run yields a different one | JSON **type** only |
| `(…)` in parentheses | not a value at all — a client-side fact | declared, not resolved |

**`volatile` is a confession, not a licence.** The four beat timings, the run's own
`elapsed_ms` and `generated_at` change every time the POST is made. The numbers below are the
ones this capture produced and are true of it. Any page that shows one must show the one its own
response carried (R-M7.2) — never the one printed here.

---

## 2 · The table

**Eighty rows** — 76 pointer rows, 3 equality markers, 1 client-clock row. Every `data-cell` id
in plan §4, expanded to one row per rendered value. `tests/demo/test_memory_loop_contract.py`
asserts these three counts, so a row cannot be added or removed without this sentence moving.

<!-- CONTRACT-TABLE-BEGIN -->

| `data-cell` | fixture | RFC 6901 pointer | measured value, 2026-08-15 | chip the envelope claimed |
|---|---|---|---|---|
| `store.event.ref` | `blocking-checks` | `/data/checks/0/precursor/external_ref` | `"DEMO-INC-0001"` | `db:column` inherited from `/checks/0` |
| `store.event.kind` | `blocking-checks` | `/data/checks/0/precursor/kind` | `"incident"` | `db:column` inherited from `/checks/0` |
| `store.event.occurred_at` | `blocking-checks` | `/data/checks/0/precursor/occurred_at` | `"2019-03-14T06:20:00Z"` | `db:column` inherited from `/checks/0` |
| `store.event.severity_gate` | `blocking-checks` | `/data/checks/0/precursor/severity_gate` | `4` | `db:column` inherited from `/checks/0` |
| `store.event.severity_basis` | `blocking-checks` | `/data/checks/0/precursor/severity_basis` | `"human_rated"` | `db:column` inherited from `/checks/0` |
| `store.event.title` | `blocking-checks` | `/data/checks/0/precursor/title` | `"SYNTHETIC — Stored energy release during intrusive work"` | `db:column` inherited from `/checks/0` |
| `store.event.source_sha256` | `blocking-checks` | `/data/checks/0/precursor/source_sha256` | `"1f84f023f5f891fadab55ef7e9f16f08285b3803f65c509f514476ea6770ba46"` | `db:column` inherited from `/checks/0` |
| `store.edge.basis` | `ancestry` | `/data/blame_edges/0/basis` | `"asserted_document"` | `db:column` inherited from `/blame_edges/0` |
| `store.edge.state` | `ancestry` | `/data/blame_edges/0/state` | `"active"` | `db:column` inherited from `/blame_edges/0` |
| `store.edge.attribution` | `ancestry` | `/data/blame_edges/0/attribution` | `"SYNTHETIC — the investigation names this clause as the control that failed."` | `db:column` inherited from `/blame_edges/0` |
| `store.closure.gen` | `ancestry` | `/data/closure/closure_gen` | `0` | `db:column` inherited from `/closure` |
| `store.closure.ancestors` | `ancestry` | `/data/closure/ancestor_count` | `1` | `db:column` inherited from `/closure` |
| `store.closure.max_severity` | `ancestry` | `/data/closure/max_severity` | `4` | `db:column` inherited from `/closure` |
| `store.closure.virulence` | `ancestry` | `/data/closure/virulence` | `"blood_major"` | `db:column` inherited from `/closure` |
| `store.closure.depth` | `ancestry` | `/data/closure/depth` | `1` | `db:column` inherited from `/closure` |
| `store.closure.truncated` | `ancestry` | `/data/closure/truncated` | `false` | `db:column` inherited from `/closure` |
| `store.closure.computed_by` | `ancestry` | `/data/closure/computed_by` | `"verticals/mainline/db/seeds/demo/demo_world.sql"` | `db:column` inherited from `/closure` |
| `store.closure.projector_ver` | `ancestry` | `/data/closure/projector_ver` | `"demo-1"` | `db:column` inherited from `/closure` |
| `store.leaf.ingested.seq` | `ledger` | `/data/leaves/[entry_kind=precursor_event_ingested]/seq` | `2` | `db:column` inherited from `/leaves/2` |
| `store.leaf.ingested.entry_kind` | `ledger` | `/data/leaves/[entry_kind=precursor_event_ingested]/entry_kind` | `"precursor_event_ingested"` | `db:column` inherited from `/leaves/2` |
| `store.leaf.ingested.recorded_at` | `ledger` | `/data/leaves/[entry_kind=precursor_event_ingested]/recorded_at` | `"2026-08-01T00:30:00Z"` | `db:column` inherited from `/leaves/2` |
| `store.leaf.ingested.leaf_hash_hex` | `ledger` | `/data/leaves/[entry_kind=precursor_event_ingested]/leaf_hash_hex` | `"6ca2bb9afa88bc988277b51c3b3ce4e5dd02708b14d8af0a32546802e4b0e107"` | `db:column` inherited from `/leaves/2` |
| `store.leaf.ingested.prev_link_hash_hex` | `ledger` | `/data/leaves/[entry_kind=precursor_event_ingested]/prev_link_hash_hex` | `"afe3289347af801fea3b87552b0d2bc06ecaa250c17144bbc3ff400a9afc8e71"` | `db:column` inherited from `/leaves/2` |
| `store.leaf.ingested.canon_bytes_b64` | `ledger` | `/data/leaves/[entry_kind=precursor_event_ingested]/canon_bytes_b64` | `sha256(utf8)=92f4d4fac73fbad9e7d76b6941b423b8f8f3e41ecca224825dd55e03f395218b, 292 B` | `db:column` inherited from `/leaves/2` |
| `store.leaf.closure.seq` | `ledger` | `/data/leaves/[entry_kind=blame_closure_computed]/seq` | `3` | `db:column` inherited from `/leaves/3` |
| `store.leaf.closure.entry_kind` | `ledger` | `/data/leaves/[entry_kind=blame_closure_computed]/entry_kind` | `"blame_closure_computed"` | `db:column` inherited from `/leaves/3` |
| `store.leaf.closure.recorded_at` | `ledger` | `/data/leaves/[entry_kind=blame_closure_computed]/recorded_at` | `"2026-08-01T00:40:00Z"` | `db:column` inherited from `/leaves/3` |
| `store.leaf.closure.leaf_hash_hex` | `ledger` | `/data/leaves/[entry_kind=blame_closure_computed]/leaf_hash_hex` | `"6e3fb05782687e1d924a5f192f3636301eb5f0f8f056f02d13237184658ded59"` | `db:column` inherited from `/leaves/3` |
| `store.leaf.closure.prev_link_hash_hex` | `ledger` | `/data/leaves/[entry_kind=blame_closure_computed]/prev_link_hash_hex` | `"a19884a1493dc4cc7ebcc0dce175e12893a63fabc6db7f930afb3b722aaf8263"` | `db:column` inherited from `/leaves/3` |
| `store.leaf.closure.canon_bytes_b64` | `ledger` | `/data/leaves/[entry_kind=blame_closure_computed]/canon_bytes_b64` | `sha256(utf8)=d46a0d59a143a384cc5f5a7f8d5721b2473731732e07eb66b25f02bd0ef61717, 316 B` | `db:column` inherited from `/leaves/3` |
| `retrieve.sql.view` | `ancestry` | `/statement_refs/[object=mainline.clause_blame_current]/text` | `sha256(utf8)=87d9d8557bbe1e6cbde993c355519289e8c08971020aad4403920ee87316211b, 349 B` | none claimed |
| `retrieve.sql.recall` | `recall-run` | `/statement_refs/[object=mainline_meas.recall_run]/text` | `sha256(utf8)=ef9b744974e8a0b37b47832d93d142d830854f702c786a360fc30b862d965580, 420 B` | none claimed |
| `retrieve.armed.severity` | `blocking-checks` | `/data/checks/0/severity` | `4` | `db:column` inherited from `/checks/0` |
| `retrieve.armed.virulence` | `blocking-checks` | `/data/checks/0/virulence` | `"blood_major"` | `db:column` inherited from `/checks/0` |
| `retrieve.armed.closure_gen` | `blocking-checks` | `/data/checks/0/closure_gen` | `0` | `db:column` inherited from `/checks/0` |
| `retrieve.armed.origin` | `blocking-checks` | `/data/checks/0/origin` | `"blame_ancestry"` | `db:column` inherited from `/checks/0` |
| `retrieve.armed.materialised_at` | `blocking-checks` | `/data/checks/0/materialised_at` | `"2026-08-02T03:00:10Z"` | `db:column` inherited from `/checks/0` |
| `retrieve.recall.started_at` | `recall-run` | `/data/started_at` | `"2026-08-02T03:00:00Z"` | `db:column` exact |
| `retrieve.recall.policy` | `recall-run` | `/data/policy_version` | `"demo-recall-1.0"` | `db:column` exact |
| `retrieve.recall.index_generation` | `recall-run` | `/data/index_generation` | `"g1"` | `db:column` exact |
| `retrieve.recall.index_plan_digest` | `recall-run` | `/data/index_plan_digest` | `"d98e50a8f7f84354b022ed0a86de9c8f49fbdf37f1fe6641012af3b63171439b"` | `db:column` exact |
| `retrieve.recall.n_candidates` | `recall-run` | `/data/counts/n_candidates` | `1` | `db:column` exact |
| `retrieve.recall.n_blocking` | `recall-run` | `/data/counts/n_blocking` | `1` | `db:column` exact |
| `retrieve.recall.n_advisory` | `recall-run` | `/data/counts/n_advisory` | `0` | `db:column` exact |
| `retrieve.recall.n_silenced` | `recall-run` | `/data/counts/n_silenced` | `0` | `db:column` exact |
| `retrieve.recall.n_deduped` | `recall-run` | `/data/counts/n_deduped` | `0` | `db:column` exact |
| `retrieve.match.severity` | `blocking-checks` + `ancestry` | `/data/checks/0/severity` == `/data/closure/max_severity` | `"match"` | none claimed |
| `retrieve.match.virulence` | `blocking-checks` + `ancestry` | `/data/checks/0/virulence` == `/data/closure/virulence` | `"match"` | none claimed |
| `retrieve.match.closure_gen` | `blocking-checks` + `ancestry` | `/data/checks/0/closure_gen` == `/data/closure/closure_gen` | `"match"` | none claimed |
| `act.beat1.name` | `gate-run` | `/data/beats/0/name` | `"read"` | none claimed |
| `act.beat1.outcome` | `gate-run` | `/data/beats/0/outcome` | `"read"` | none claimed |
| `act.beat1.sqlstate` | `gate-run` | `/data/beats/0/sqlstate` | `"00000"` | none claimed |
| `act.beat1.constraint` | `gate-run` | `/data/beats/0/constraint` | `null` | none claimed |
| `act.beat1.constraint_source` | `gate-run` | `/data/beats/0/constraint_source` | `null` | none claimed |
| `act.beat1.elapsed_ms` | `gate-run` | `/data/beats/0/elapsed_ms` | volatile `0.013` | none claimed |
| `act.beat2.name` | `gate-run` | `/data/beats/1/name` | `"merge"` | none claimed |
| `act.beat2.outcome` | `gate-run` | `/data/beats/1/outcome` | `"refused"` | none claimed |
| `act.beat2.sqlstate` | `gate-run` | `/data/beats/1/sqlstate` | `"23514"` | `db:constraint` exact |
| `act.beat2.constraint` | `gate-run` | `/data/beats/1/constraint` | `"gate_closed_when_issued"` | `db:constraint` exact |
| `act.beat2.constraint_source` | `gate-run` | `/data/beats/1/constraint_source` | `"reported"` | none claimed |
| `act.beat2.elapsed_ms` | `gate-run` | `/data/beats/1/elapsed_ms` | volatile `613.317` | none claimed |
| `act.beat3.name` | `gate-run` | `/data/beats/2/name` | `"projection_drift_attack"` | none claimed |
| `act.beat3.outcome` | `gate-run` | `/data/beats/2/outcome` | `"refused"` | none claimed |
| `act.beat3.sqlstate` | `gate-run` | `/data/beats/2/sqlstate` | `"P0001"` | `db:constraint` exact |
| `act.beat3.constraint` | `gate-run` | `/data/beats/2/constraint` | `"mainline.fn_permit_merge_gate"` | `db:constraint` exact |
| `act.beat3.constraint_source` | `gate-run` | `/data/beats/2/constraint_source` | `"parsed"` | none claimed |
| `act.beat3.elapsed_ms` | `gate-run` | `/data/beats/2/elapsed_ms` | volatile `528.144` | none claimed |
| `act.beat4.name` | `gate-run` | `/data/beats/3/name` | `"admit"` | none claimed |
| `act.beat4.outcome` | `gate-run` | `/data/beats/3/outcome` | `"admitted"` | none claimed |
| `act.beat4.sqlstate` | `gate-run` | `/data/beats/3/sqlstate` | `"00000"` | none claimed |
| `act.beat4.constraint` | `gate-run` | `/data/beats/3/constraint` | `null` | none claimed |
| `act.beat4.constraint_source` | `gate-run` | `/data/beats/3/constraint_source` | `null` | none claimed |
| `act.beat4.elapsed_ms` | `gate-run` | `/data/beats/3/elapsed_ms` | volatile `499.759` | none claimed |
| `act.verdict` | `gate-run` | `/data/verdict` | `"PROVEN"` | `derived` exact |
| `act.failures` | `gate-run` | `/data/failures` | `[]` | none claimed |
| `act.self_persisted` | `gate-run` | `/data/persistence_check/self_persisted` | `false` | `recomputed` exact |
| `act.single_transaction` | `gate-run` | `/data/transaction/single_transaction` | `true` | none claimed |
| `meta.generated_at` | `gate-run` | `/data/generated_at` | volatile `"2026-08-15T11:57:20Z"` | none claimed |
| `meta.elapsed_ms` | `gate-run` | `/data/elapsed_ms` | volatile `1895.12` | none claimed |
| `meta.received_at` | (none) | (client clock) | (the browser's own time when the body finished arriving) | none claimed |

<!-- CONTRACT-TABLE-END -->

### 2.1 Notes on four rows a reader will stop at

**`retrieve.match.*` has no chip, and must not borrow one.** The match marker is a comparison
the client performs between two independently fetched responses (R-M5.2). Both operands are
chipped `db:column`; the *verdict of the comparison* is the page's own arithmetic, and R-M4
forbids dressing browser arithmetic in a chip. Render it as a marker, not as a value.

**`act.beat1` and `act.beat4` carry no chip at all — including their `"00000"` SQLSTATEs.**
`transitions.py` claims `db:constraint` for `/beats/1/sqlstate` and `/beats/2/sqlstate` only.
The refusals are chipped; the successes are not. The page shows two chipped SQLSTATEs and two
unchipped ones, and that asymmetry is the truth about what the emitter claimed. Adding a chip
to the other two is an endpoint change, which R-M1 forbids.

**`act.failures` is `[]` on a `PROVEN` run.** R-M10 requires every string in it be printed when
it is non-empty; on this capture there are none. A page that has never rendered a non-empty
`failures` has not been tested against R-M10.

**`meta.received_at` is the only cell in this contract that no response contains.** It is the
client's own receipt time, required by R-M7.1's persistent disclosure line. It is listed so that
nobody mistakes it for a payload field and goes looking for a pointer.

---

## 3 · The two SQL statements, verbatim from the wire

R-M6: rendered byte-for-byte as returned, never retyped, never reformatted. Reproduced here so
the contract is checkable by eye; the authoritative bytes are the fixtures, and the digests in
the table are what `tests/demo/test_memory_loop_contract.py` checks.

**`retrieve.sql.view`** — `ancestry` · `/statement_refs/[object=mainline.clause_blame_current]/text`
· `kind: "view"` · 349 B · `sha256 87d9d8557bbe1e6cbde993c355519289e8c08971020aad4403920ee87316211b`

```sql
SELECT closure_gen, ancestor_events, ancestor_count, max_severity,
       virulence::text                  AS virulence,
       depth, truncated, computed_by, projector_ver, computed_at, site_id,
       encode(as_of_commit, 'hex')      AS as_of_commit
  FROM mainline.clause_blame_current
 WHERE clause_uuid = %s AND as_of_commit = decode(%s, 'hex')
```

**`retrieve.sql.recall`** — `recall-run` · `/statement_refs/[object=mainline_meas.recall_run]/text`
· `kind: "table"` · 420 B · `sha256 ef9b744974e8a0b37b47832d93d142d830854f702c786a360fc30b862d965580`

```sql
SELECT run_id, permit_id, site_id,
       encode(corpus_commit, 'hex')         AS corpus_commit,
       policy_version,
       encode(index_plan_digest, 'hex')     AS index_plan_digest,
       index_generation,
       n_candidates, n_blocking, n_advisory, n_silenced, n_deduped,
       n_bonded_sev5, n_bonded_sev5_blocking,
       arms_degraded, started_at, latency_ms
  FROM mainline_meas.recall_run
 WHERE run_id = %s
```

### 3.1 Where `text` is `null`, and what must go there instead

R-M6 requires the gaps be stated rather than filled. Measured across the four fixtures that
carry `statement_refs`:

| fixture | refs | carry `text` | carry `text: null` |
|---|---|---|---|
| `blocking-checks` | 5 | 1 — `mainline.disposition` | 4 — `mainline.blocking_check`, `mainline.clause_version`, `mainline.event`, `mainline.permit` |
| `ancestry` | 9 | 2 — `mainline.clause_blame_current`, `pg_catalog.pg_constraint` | 7 |
| `recall-run` | 1 | 1 — `mainline_meas.recall_run` | 0 |
| `ledger` | 7 | 1 — the RFC 6962 note, which is prose and **not SQL** | 6 |
| `gate-run` | 5 | 0 | 5 |

For every `null`, the page renders `kind` and `object` and the literal words **"statement text
not returned by this endpoint."** Pasting SQL from a migration or a seed into that gap is
forbidden by R-M6 and would be the exact substitution this repository has already reverted
somebody for.

---

## 4 · Recorded facts about the provenance vocabulary — NOT bugs, and NOT to be fixed

R-M3 instructs that the discrepancy be recorded here rather than repaired. Three things are
true at once, all measured on this tree at HEAD `4af05e1`:

### 4.1 Five chips on the wire, four in the console's design package

| file · line | declares | text |
|---|---|---|
| `verticals/mainline/apps/demo-api/src/mainline_demo_api/envelope.py:93` | **five** | `Chip = Literal["db:column", "db:constraint", "recomputed", "staged", "derived"]` |
| `verticals/mainline/apps/console/src/design/provenance.ts:26` | **four** | `export const PROVENANCE_KINDS = ['db:column', 'db:constraint', 'recomputed', 'staged'] as const;` |

`envelope.py:96` repeats the five as a `frozenset`; `provenance.ts`'s docstring states the
absence deliberately: *"There is no `computed`, no `derived` and no `estimated`."*

**Neither file is modified by this plan.** R-M3 rules that `/memory.html` uses the envelope's
five, because it renders envelope payloads verbatim. This is not a hypothetical: **`derived` is
the chip the deployed API attached to `/verdict`** — the single most important value in the ACT
column — and **five of the six** captures carry at least one `derived` entry (twenty in total).
A page built on the console's four-chip vocabulary would have to drop that chip or lie about it.

### 4.2 The gate-run driver emits `recomputed`, and the read envelope says it never does

`envelope.py`'s module docstring, describing the chip table:

> `recomputed` — the CONSOLE re-derived it from signed bytes in a Worker (D6). **This API never
> emits it:** we are the emitter, and an emitter cannot vouch for a recomputation the reader has
> not performed.

And `transitions.py:1328,1338,1341` — the gate-run envelope's hard-coded provenance list:

```
{"pointer": "/subject/open_blocking_derived", "chip": "recomputed"},
{"pointer": "/persistence_check/identical",   "chip": "recomputed"},
{"pointer": "/persistence_check/self_persisted", "chip": "recomputed"},
```

Both sentences are true of their own scope: `POST /v1/demo/gate-run` does not go through
`envelope.read_envelope` — it is built by `transitions._envelope` and stamped with
`gate_run.GATE_RUN_SCHEMA_ID`. The docstring is a statement about the **read** API. **Recorded
as a fact. Neither file is modified.** The consequence for W3 is only this: `act.self_persisted`
renders `recomputed` because the response claimed it, and the page does not additionally claim
to have recomputed anything it has not.

### 4.3 `derived` in the wild, so nobody thinks it is theoretical

| fixture | pointers claimed `derived` |
|---|---|
| `subjects` | the eight `…/count` pointers |
| `blocking-checks` | `/subject_kind`, `/checks/0/open`, `/checks/0/disposition_id` |
| `ancestry` | `/truncation/ancestry_complete`, `/truncation/spilled_count` |
| `ledger` | `/checkpoints/*/log_key`, `/cosignatures/*/witness_key`, `/inclusion_proofs`, `/consistency_proofs` |
| `gate-run` | `/verdict` |

`recall-run` is the one fixture whose seventeen chips are **all** `db:column`.

---

## 5 · ESCALATIONS to the memory-visibility lead

R-M1 makes escalation a duty, not a formality. **Every `data-cell` id in plan §4 resolved.**
Nothing in §4 is missing, so no cell was invented, substituted or dropped. The four items below
are raised against plan §3's *sketch* and against a collision between two rulings; all four need
a lead's decision, and none of them is a thing I may decide by choosing a nearby field.

### E-1 — `tau_applied 0 · θ 0.35` appears in the §3 panel sketch and **exists in no response**

**Status: blocking for whoever renders that line. No `data-cell` id was assigned to it in §4.**

Searched all six captured bodies for `tau`, `theta` and `0.35`: **zero occurrences.** The
`recall-run` payload's `data` has eleven members — `run_id`, `permit_id`, `site_id`,
`corpus_commit`, `policy_version`, `index_plan_digest`, `index_generation`, `arms_degraded`,
`started_at`, `latency_ms`, and `counts`, whose own seven are `n_candidates`, `n_blocking`,
`n_advisory`, `n_silenced`, `n_deduped`, `n_bonded_sev5`, `n_bonded_sev5_blocking`. There is no
threshold field on it, and none on `blocking-checks` either.

I did not substitute a similar field and I did not drop the line silently. Recommended
disposition, for the lead to accept or replace: **strike the line.** R-M9's own text asks only
for *"`origin: blame_ancestry` and the recall counts explicitly"*, and both of those are in the
table above with `db:column` chips. `demo_permit.sql:181-185` is cited in R-M9 as refusing to
let anyone claim a threshold — printing `θ 0.35` would be that claim.

### E-2 — `[recomputed]` under `ledger leaf 2` in the §3 sketch collides with R-M3

**Status: needs a ruling before W4 writes `memory-verify.js`.**

R-M3: *"The page never assigns a chip itself — it renders the chip the response supplied."* The
ledger's claim for `/leaves/2/leaf_hash_hex` is `db:column`, inherited from `/leaves/2`. So a
`[recomputed]` chip beside that value would be **assigned by the page**, which R-M3 forbids in
terms.

But R-M4 says `recomputed` is *"reserved by `provenance.ts` and D6 for re-derivation from
**signed bytes**"* — which is exactly and only what W4's `crypto.subtle` verification does, and
the plan's §1 row 5 records that the RFC 6962 recomputation matched 4 of 4. The two rulings
point opposite ways for this one cell.

Both readings are defensible and neither is mine to pick. A shape that satisfies both, offered
without prejudice: render the column value with its `db:column` chip, and render the browser's
verdict as a **separate** adjacent element in its own register (*"this browser recomputed
`sha256(0x00 ‖ canon_bytes)` and it matched"*), so that no single value carries two chips and
the page's own claim is visibly the page's own.

### E-3 — the ACT column is mostly unchipped, and this is the column judges look at hardest

**Status: a fact, not a blocker. Flagged because it will surprise W2 and W3 at layout time.**

Of the 28 `act.*` cells, **six carry a chip**: `/beats/1/sqlstate`, `/beats/1/constraint`,
`/beats/2/sqlstate`, `/beats/2/constraint` (all `db:constraint`), `/verdict` (`derived`) and
`/persistence_check/self_persisted` (`recomputed`). **The other twenty-two carry none**, because
`transitions.py:1325-1341` claims ten pointers and no ancestor sweep. Beat names, outcomes,
`constraint_source` and every `elapsed_ms` are unchipped.

R-M3 forbids inventing a chip for them, and R-M1 forbids changing the endpoint that would claim
one. So the ACT column is honestly sparse. If the lead wants the *design* to acknowledge that
rather than have it read as an oversight, one sentence of chrome — *"chips appear where the
response claimed one"* — costs nothing and is true of the whole page.

### E-4 — `/data/beats/3/observed/merge_record/clearance_digest` is chipped and has no cell id

**Status: minor. §3's sketch shows `clearance_digest …` under beat 4; §4 assigns it no id.**

It is present, it is `db:column` **exact** — one of only two exact `db:column` claims in the
gate-run payload — and its value on this capture is
`bd47ec6be8d2b37d850819e56d3b47d8e80f7e28e94e9eb819839f693bb1c1ce` (volatile: a fresh run mints
a fresh one). If the lead wants it on screen, it needs a `data-cell` id, and adding one requires
W2 and W3 to move together per §4's seam rule. It is deliberately **absent from the table above**
because the table is §4's cells and nothing else.

---

## 6 · Every cell that carries no chip, in one list

R-M3's instruction is that these render with **no chip and no substitute**. **Thirty cells** —
the count is asserted by the test — listed so nobody has to re-derive it from the table:

- both SQL cells — `retrieve.sql.view`, `retrieve.sql.recall` (structural: outside `/data`)
- all three `retrieve.match.*` markers (client-side comparison; R-M4)
- `act.beat1.{name,outcome,sqlstate,constraint,constraint_source,elapsed_ms}` — all six
- `act.beat2.{name,outcome,constraint_source,elapsed_ms}`
- `act.beat3.{name,outcome,constraint_source,elapsed_ms}`
- `act.beat4.{name,outcome,sqlstate,constraint,constraint_source,elapsed_ms}` — all six
- `act.failures`, `act.single_transaction`
- `meta.generated_at`, `meta.elapsed_ms`, `meta.received_at`

Everything else in the table carries a chip the envelope itself supplied.

---

## 7 · Re-measuring, and what will break if the world moves

```
python scripts/demo/capture_memory_loop.py              # five GETs, no POST
python scripts/demo/capture_memory_loop.py --with-post  # and one gate-run
python -m pytest tests/demo/test_memory_loop_contract.py -q
```

The test replays the fixtures **with the network unplugged** — it installs a `socket.socket`
that raises, so a test that reached for the wire fails rather than passing on live data. It
asserts, for every row above: the pointer resolves, the value matches (or the digest and byte
length match, or for a `volatile` row the JSON type matches), and the chip is the one the
envelope's `provenance[]` actually yields under §1.2's resolution.

**If the deployment is reseeded or redeployed, this document goes stale and the test goes red.**
That is the design. Re-run the capture, re-run the test, and let the diff show what moved — a
contract that survives a change in the world it describes is not a contract.

**What this document does not prove.** That the page renders any of it; that is W2, W3 and W6.
That the values are *correct* about the world; they are correct about what the API returned, and
the SYNTHETIC prefixes on `store.event.title` and `store.edge.attribution` are the payload's own
statement that the world is a seeded one (R-M13 — not stripped, not styled away).
