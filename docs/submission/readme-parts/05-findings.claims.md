# CLAIM LEDGER — section F (`05-findings.md`), worker W5

**Fragment:** `docs/submission/readme-parts/05-findings.md` · **40 lines** (budget 40) ·
5 307 bytes · rendered heading `## How we got here, and what we found out about CockroachDB`.

**How this fragment was built.** Read-only, from committed documents and artefacts in this tree at
HEAD `9e91467`. **No database connection was opened, no proof script was run, no HTTP request was
issued, no AWS call was made, no credential was read or printed, and no file outside the two paths
this worker owns was edited.** Nothing was committed. Every finding below was verified by opening
the cited file and reading the measurement, not by re-measuring.

---

## 1 · The nine candidate findings, and what happened to each

`PUBLISHED` — in the README table. `DROPPED` — not in the README table, with the reason. Nine
candidates, five published, four dropped. **Two** (`e`, `f`) were dropped because five was the cap
*and* because their briefed wording overstates what the source actually says. **Two** (`d`, `g`)
were dropped because the claim as briefed is **not what our own tree measured**. Those last two are
the important rows in this table.

| # | candidate (as briefed) | disposition | why |
|---|---|---|---|
| a | `has_function_privilege()` is a stub on v26.2.5 | **PUBLISHED** | Verified at `docs/regression/GUARD.md:370-393`: scratch database `w_regression_guard_priv`, `EXECUTE` revoked, behavioural truth `42501 … does not have EXECUTE privilege on procedure merge_permit`, function still `true` for the probe login, `root`, `admin` and `public`; `has_table_privilege` through the identical control tracked behaviour. Measured 2026-08-15 on the local single node. **Published as "cannot answer `false`", not as "is a stub"** — the second is a statement about the implementation we did not read. See §2 for the counter-reading we checked it against. |
| b | `SHOW GRANTS` full signature vs `information_schema.routines` bare name | **PUBLISHED** | Verified at `docs/regression/GUARD.md:238` and `:250-251` (plants P2 and P3, `routine_signature_normalised`). Published as **ours** — a naive comparison is our bug — which is what the row says. |
| c | vector index not chosen by the optimizer at 5 200 rows | **PUBLISHED** | Verified at `docs/adr/0002-g1-platform-ground-truth.md` GT-06 / GT-06b, live Basic cluster, 2026-08-07; corroborated `docs/HONESTY.md` (*"only when the index is named in the query"*) and `evidence/aws/ann/explain-unhinted.txt` / `explain-hinted.txt`. Published as **limit**, explicitly *correct behaviour that broke our assumption*, never as a defect. |
| h | the 10 240-byte MCP response cap truncates rather than raising | **PUBLISHED** | Verified at `packages/mainline-mcp/src/mainline_mcp/limits.py:60` (`MAX_RESPONSE_BYTES = 10_240`, docstring *"At or above this the answer may have been TRUNCATED."*) and `docs/TOOL-USAGE.md` §*Feedback on the CockroachDB AI tools* item 1, which quotes `evidence/mcp/tools-schema.json`. Published as **limit** — documented, with a silent failure mode. |
| i | `ccloud` 0.6.12 has no headless service-account authentication | **PUBLISHED** | Verified verbatim at `evidence/ccloud/README.md:37`: `login` / `logout` / `whoami` only, browser-based login, `CC_API_KEY` ignored, `0.7.0`–`1.0.0` all `404`. Published as **limit** — a missing capability, stated with the workaround we actually use. |
| d | `crdb_internal` and `system` are restricted **on Basic tier** | **DROPPED as briefed; the correction is published in one sentence** | The tier framing is **wrong** and our own tree says so. `evidence/tool-usage/crdb-features.json` (`verdict_basis`, re-measured 2026-08-12) records the refusal **on the pinned local single node**, with `SET allow_unsafe_internals = true` unlocking it; `docs/deploy/JUDGE-PACK.md:536-550` and `evidence/deploy/judge-run.json:368` record the same `42501` and the same hint on Cloud. It is a **version default, not a tier constraint**. Publishing it as a tier constraint would have been the overclaim this section exists to avoid, so the fragment publishes the correction instead. |
| g | `gc.ttlseconds` **defaults** to 4500 on Basic | **DROPPED — cannot be sustained** | `docs/deploy/cloud-database.md:41` records *"requested 4500, **accepted**, read back as 4500"* — that is **our** `CONFIGURE ZONE` value, not a read of a database nobody configured. `docs/HONESTY.md` records the local node reading `14400` and says the census *"does not reconfigure the machine it is measuring"*. `docs/deploy/CLOUD-40001.md:75` and `docs/adr/0002-…` GT-07 both state `4500` for Basic, but neither establishes it as the **default**. No committed artefact reads `gc.ttlseconds` on an unconfigured Basic database, so *"defaults to 4500"* is not publishable. **Flagged, not fixed:** `README.md:191` currently says 4500 is *"the value CockroachDB Cloud Basic enforces"* — that line is in W6's section and this worker did not touch it. |
| e | the 20 000 schema-object cap surfaces as unrelated failures | **DROPPED for space; named in the closing line with its citation** | Verifiable: `docs/submission/EXTRA-CREDIT-CLAIMS.md:358-367` quotes `ConfigurationLimitExceeded: cannot create new schema object(s): would exceed approximate maximum (20000); current count: 20161` with the `HINT` naming `sql.schema.approx_max_object_count`, and `docs/submission/PRESHOOT-VERDICT.md:289` reproduces it. **The briefed wording overstates it**: the error *is* a clear quota error and names its own setting; what cost time is that it arrives as thirteen unrelated-looking fixture errors, on a node **our own** scratch databases filled. Had it been published it would have been labelled `ours`. |
| f | `convert_from()` untyped `<string>`, and a local/Cloud divergence | **DROPPED for space; named in the closing line with its citation** | The typing half is verified at `verticals/mainline/db/seeds/demo/demo_world.sql:844-846`, which quotes `42883 split_part(): unknown signature: convert_from(string, string)`. **The divergence half is not supported by that source**: the comment attributes the contrast to a scratch table whose column was `bytea` where the product's is `text` — a schema difference of ours, not a single-node-versus-Cloud engine difference. Publishing *"resolved locally, failed on Cloud"* would have been unsourced. |

**Struck for lack of a verifiable source: 0.** Every candidate had a committed source. Two (`d`,
`g`) had a source that **contradicted the briefed wording**, and both are recorded above rather
than quietly reworded.

---

## 2 · The counter-reading we checked finding (a) against

`docs/demo/cr-gate-measurements.md:56-69` reads a `true` from `has_function_privilege()` as
*"CockroachDB's platform default for `PUBLIC` on a routine with a `NULL` ACL"* — correct behaviour,
and our misreading. That measurement was taken on a routine with **no explicit access-control list
at all**, so `true` is the right answer there. `docs/regression/GUARD.md:370-393` measures a
**different state**: `EXECUTE` explicitly revoked, and a `CALL` in that same state refused `42501`.
The two do not contradict each other, and the finding rests only on the second. The fragment
therefore claims exactly the narrow thing the second measurement supports.

---

## 3 · Claims from the current `README.md` that touch this section

| claim in `README.md` today | disposition | note |
|---|---|---|
| `:321` *"every one of them is **synchronic** — it gates on the current state of the world. MAINLINE is **diachronic**"* | **MOVED** | Present in `docs/submission/readme-parts/03-mechanism.md:6-7` — `grep -n "synchronic\|diachronic"` returns lines 6 and 7 of that file. Section F states the same fact in plain words (*"every one of those checks is about the present"*) without the two terms, because plan R4 allows each of them exactly once and W3 has spent both. |
| `:191` `crdb-align` pins `gc.ttlseconds` to 4500, *"the value CockroachDB Cloud Basic enforces"* | **KEPT** (not this worker's file) | W6 owns that section. See row `g` above: *enforces* is stronger than any artefact in the tree supports. Raised for W6/W7, not edited. |
| `:10` blame pointer / protected branch / refusal | **KEPT** | W1 and W3 carry it. |

No claim, number or citation from the current `README.md` was deleted by this fragment.

---

## 4 · Register and readability checks run on the fragment

* **Nothing implied about upstream reporting.** The fragment states plainly that none of the five
  has been reported to Cockroach Labs, and that the only thing staged upstream is an unrelated
  skill contribution, drafted and not filed [`docs/upstream/proposal-issue.md`]. No committed
  artefact shows any of these findings being filed, and none is claimed.
* **Every finding labelled.** `defect` (1), `limit` (3), `ours` (1), plus one candidate publicly
  corrected from *tier constraint* to *version default*. No finding is called a bug where the
  measurement shows a documented limit.
* **One positive, present.** *"What we would keep unchanged"* — `CHECK` constraints and PL/pgSQL
  triggers under `SERIALIZABLE`, and a refusal that names the constraint that raised it
  [`docs/deploy/cloud-database.md:48`, `docs/adr/0002-…` GT-08].
* **Glossed at first use, twelve words or fewer:** `SERIALIZABLE` (*concurrent writes behave as if
  run one after another*). `CHECK` constraint, trigger, SQLSTATE, obligation, projection and vector
  index are glossed earlier by W1/W3/W4; this fragment does not redefine them. `psql` is glossed
  in place as *the database's own command line*. The words `role`, `privilege`, `catalogue entry`,
  `optimizer`, `envelope` and `unhinted plan` were **removed** in favour of *login*, *permission
  check*, *catalogues*, *cost-based planner*, *nothing on the response says it was cut* and *unless
  the index is named in the statement*, so no new term needs a gloss.
* **Banned words:** none of `revolutionary`, `seamless`, `unprecedented`, `cutting-edge`,
  `game-changing`, `powerful`, `robust`, `effortlessly`, `blazing`, `canonicalisation`, `defeater`,
  `archival bond`, `fixity`, `C-SPANN` appears. `diachronic` and `synchronic` do not appear.
* **Sentence length:** longest sentence in the fragment, prose and table cells alike, is 35 words
  or fewer (checked mechanically over the file with `[src: …]` spans removed).
* **Every path cited exists at HEAD `9e91467`** — the **fourteen** distinct paths named in the
  fragment were each stat-checked and all fourteen are present. The table's fourth column is
  clickable: **seven** markdown links, each re-checked with `os.path.exists` against the repository
  root, **zero unresolved**. Everything else is an inline `[src: …]` span, which plan R11 keeps as
  the layer-2 convention and which cannot break a link check.
