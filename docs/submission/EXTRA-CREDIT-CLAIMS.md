<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# EXTRA-CREDIT CLAIM LEDGER — every new sentence traced to an artefact

**W6 · the control on the extra-credit wave · 2026-08-16 · repo `D:/CoackroachDBxAWS/mainline`,
`HEAD` `c951558`, working tree uncommitted · live origin
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`**

This page writes no marketing prose and makes no claim of its own about the product. It does one
thing: it takes every new or changed claim that workers W1 through W5 put on a submission
surface, finds the artefact or live route that produces it, **re-derives the value first-hand**,
and records the one command a sceptic runs to prove the sentence wrong. A claim with no such
command is not softened here — it is listed in §3 REFUSED and handed back to the worker who
wrote it.

**One contradiction survived the sweep and is reported rather than fixed** (§7.1), and the contradiction ruling R3 names is reported in §8 — where the finding is that the file's own owner had already corrected it in the working tree, so the ledger records the correction instead of re-proposing it. W6 owns
`docs/submission/EXTRA-CREDIT-CLAIMS.md` and nothing else; it edited no other file, ran no
deploy, wrote no `SSM` parameter, widened no grant, and narrowed no rule.

**How to falsify this page.** Every row below carries its own command. Run any of them. If a
value in the *observed* column does not come back, this page is wrong and the row is the proof.
The live rows need no clone, no account and no credential; the artefact rows need the repository
and nothing else.

---

## 0 · THE METHOD, AND WHAT WOULD MAKE IT DISHONEST

1. **A worker's word is not evidence.** No number below was copied from the page that claims it.
   Each was read out of the artefact or off the origin by W6, in this sitting, with the command
   printed beside it.
2. **A claim with no falsifying command does not get a row.** It gets a REFUSED entry naming the
   worker and the sentence.
3. **A red is recorded, never bought.** No rule was narrowed, scoped, skipped or disabled to turn
   a red green. Where the repository's own controls report something, the verdict is copied with
   its exit code, including the parts that are not flattering.
4. **A disagreement is named with both readings.** Where the copy and an artefact differ, §7 and
   §8 print both and name the artefact that decides it. W6 never silently prefers one.
5. **Digits inside `code spans` are names, not measurements** — the repository's own convention,
   and this page keeps it.

**The one measurement W6 did not take.** The suite was run, and it is red for a cause that is not
this wave's — §5.1. W6 did not repair it, because both available repairs (dropping accumulated
scratch databases, or raising a cluster setting) are changes made to turn a red green, and the
second is exactly the move this repository exists to refuse.

---

## 1 · THE SWEEP ENVELOPE — what existed when, so a later reader can date every row

Six workers were in flight concurrently — **W1, W3, W4 and W5 all wrote while this sweep was
running.** W6 therefore snapshotted the owned files three times and records all three, so no row
is attributed to the wrong state of the tree.

| file | sha256 (first 16) `12:08:50Z` | `12:23:28Z` | `12:31:57Z` (final) |
|---|---|---|---|
| `docs/submission/DEVPOST.md` (W1) | `2105b57b8c24a270` | `5614b3855848078b` | `877982d1b5f1a50a` |
| `README.md` (W2) | `e0a5fdc68cbf264a` | `95d2ab3a074597bb` | `95d2ab3a074597bb` (settled) |
| `docs/submission/JUDGING-AXES.md` (W3) | `8ddcd16889da461f` | `cf48bda278eca5f0` | `8325437f30c0bc4d` |
| `docs/TOOL-USAGE.md` (W4) | `94dd0c422a75fc4a` | `c3541df069457634` | `c3541df069457634` (settled) |
| `evidence/demo/live-semantics.json` (W5) | did not exist | `8eedb08881cd09cb` | `4ff2792826f439b3` |
| `docs/demo/LIVE-SEMANTICS.md` (W5) | did not exist | `de6a9b77e670397b` | present |
| `evidence/mcp/session-extract.json` (W4) | did not exist | `ac860a69b14cb112` | present |

Re-derive any row:

```
.venv/Scripts/python.exe -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('README.md').read_bytes()).hexdigest()[:16])"
```

**Line numbers in §2 are as of the final snapshot, `2026-08-16T12:31:57Z`, and every one was
re-resolved at that timestamp** rather than left at the value it had when the row was written —
five citations in §2.1 and four in §2.3 moved between the second and third snapshots and were
corrected. **A file that moves after `12:31:57Z` moves its line numbers with it; the sentence,
not the line, is the identifier — grep for it.**

---

## 2 · THE CLAIM LEDGER

Every row: the sentence as it stands, where it lives, what produces it, what W6 observed, and
the command that falsifies it. `$B` is the demo origin. `$P` is
`dec0de00-0006-4000-8000-000000000001`. `PY` is `.venv/Scripts/python.exe`.

### 2.1 · W1 — `docs/submission/DEVPOST.md`, axis one

| # | the claim | at | produced by | W6 observed | falsify it with |
|---|---|---|---|---|---|
| W1-1 | *"STORE → RETRIEVE → ACT runs against the deployed origin and writes `evidence/demo/memory-loop.json`"* — verdict PROVEN, 23 of 23 assertions held, 0 failed | `DEVPOST.md:308` | `evidence/demo/memory-loop.json` | `verdict` `PROVEN`; `assertions_total` 23; `assertions_held` 23; `assertions_failed` `[]` | `PY -c "import json;d=json.load(open('evidence/demo/memory-loop.json'));print(d['verdict'],d['assertions_total'],d['assertions_held'],d['assertions_failed'])"` |
| W1-2 | the transcript ran against the **deployed** origin, not a local emulator | `DEVPOST.md:308` | same file, `#base_url` | `base_url` is the live Function URL, character-for-character the origin in `SUBMISSION.json` `demo_url` | `PY -c "import json;print(json.load(open('evidence/demo/memory-loop.json'))['base_url'])"` |
| W1-3 | *"ten seconds"* is a **subtraction of two columns off two live routes**, `stated_anywhere_in_this_program: false` | `DEVPOST.md:308` | same file, `#gap` | `gap.seconds` 10.0; `gap.stated_anywhere_in_this_program` `false`; `gap` also carries `from`, `to`, `how`, `computed_here`, `corroboration` | `PY -c "import json;print(json.load(open('evidence/demo/memory-loop.json'))['gap'])"` |
| W1-4 | the proof script audits itself — 79 values audited, 0 found in the source, 0 UUID literals | `DEVPOST.md:308` | same file, `#self_audit` | `values_audited` 79; `values_found_in_the_source` `[]`; `uuid_literals_in_the_source` 0 | `PY -c "import json;print(json.load(open('evidence/demo/memory-loop.json'))['self_audit'])"` |
| W1-5 | *"No endpoint was added to make any of this filmable"* — the artefact's own ruling `R7` | `DEVPOST.md:308` | same file, `#ruling` | the string *"the loop needs no new endpoint"* is present in the artefact | `PY -c "import json;print('the loop needs no new endpoint' in json.dumps(json.load(open('evidence/demo/memory-loop.json'))))"` |
| W1-6 | the blocked merge returns a `mus` — `origin: blame_ancestry`, `severity: 4`, `virulence: blood_major`, `detail: "open at gate_epoch 1; no live disposition"` | `DEVPOST.md:310` | **live** `POST $B/v1/demo/gate-run`, beat 2 | all four fields returned verbatim today, `sqlstate` `23514`, constraint `gate_closed_when_issued` | `curl -s -XPOST $B/v1/demo/gate-run -H "content-type: application/json" -d "{}" \| PY -c "import json,sys;print(json.load(sys.stdin)['data']['beats'][1]['refusal']['mus'])"` |
| W1-7 | an `naa` of `cardinality 1` with five legal dispositions (`applied`, `mitigated`, `mechanism_absent`, `escalated`, `emergency_override`) | `DEVPOST.md:310` | same live POST | `kind` `dispose_obligations`, `cardinality` 1, `legal_kinds` exactly those five, in that order | same command, `…['refusal']['naa']` |
| W1-8 | on beat 3, the attack, the payload degrades honestly: `naa: null`, `naa_reason: "not_computable"`, `mus[0].kind: "capability_gap"` | `DEVPOST.md:310` | same live POST, beat 3 | `sqlstate` `P0001`, constraint `mainline.fn_permit_merge_gate`, `naa` `null`, `naa_reason` `not_computable`, `mus[0].kind` `capability_gap` | same command, `…['beats'][2]['refusal']` |
| W1-9 | *"Both halves are committed as well as live"* — the `mus`/`naa` in `evidence/deploy/live-gate-run.json`, the degraded beat in `evidence/demo/live-beats.json` § `beat_three_diagnosis`, whose note calls it *"a Product-Readiness point, not an embarrassment"* | `DEVPOST.md:310` | those two artefacts | `live-gate-run.json` carries `data.beats[1].refusal.mus/naa` and `data.beats[2].refusal.naa_reason` `not_computable`; `live-beats.json` carries `beat_three_diagnosis` and that exact phrase | `PY -c "import json;print(json.dumps(json.load(open('evidence/deploy/live-gate-run.json'))['data']['beats'][2]['refusal'])[:200])"` and `PY -c "import json;print('Product-Readiness point, not an embarrassment' in json.dumps(json.load(open('evidence/demo/live-beats.json'))))"` |
| W1-10 | the memory layer is `SERIALIZABLE`, a named `CHECK`, a composite FK with `ON UPDATE RESTRICT`, a counter no client may write, `FORCE` row-level security, and a chain applied 271 of 271 against managed CockroachDB Cloud (`evidence/deploy/cloud-chain.json`) | `DEVPOST.md:314` | four migration files + `evidence/deploy/cloud-chain.json` | `gate_closed_when_issued` at `0050_permit.sql:114`; `ON UPDATE RESTRICT` at `0071a_epoch_pin_permit.sql:39`; `FORCE ROW LEVEL SECURITY` at `0181a_permit_rls_force.sql:5` and `:54`; `cloud-chain.json` `files` 271 · `applied` 271 · `failed` 0 | `grep -n gate_closed_when_issued verticals/mainline/db/migrations/0050_permit.sql` and `PY -c "import json;d=json.load(open('evidence/deploy/cloud-chain.json'));print(json.dumps(d)[:400])"` |
| W1-11 | axis 4's concession is the custody store, not the memory layer: 7 of 16 cryptographic custody checks unwritten (`qa/test-state.json`) | `DEVPOST.md:314` | `qa/test-state.json#external_checks.custody_bundle_verification` | `counts` = `failed` 0 · `not_checked` 7 · `passed` 9 · `total` 16; `exit_code` 2; the seven are named — `log_signature`, `rfc3161_upper_bound`, `beacon_lower_bound`, `witness_quorum`, `archive_object_lock`, `gate_self_attestation`, `webauthn_reverification` | `PY -c "import json;print(json.load(open('qa/test-state.json'))['external_checks']['custody_bundle_verification']['counts'])"` |
| W1-12 | **OPEN THIS TO CHECK IT** — `curl -s <demo_url>/v1/permits/dec0de00-…-000000000001/blocking-checks`; the deciding field `precursor.severity_gate` reads 4 with `severity_basis: "human_rated"` and `origin: "blame_ancestry"` | `DEVPOST.md:316` | **live** `GET $B/v1/permits/$P/blocking-checks` | `data.checks[0].precursor.severity_gate` 4; `precursor.severity_basis` `human_rated`; `data.checks[0].origin` `blame_ancestry` | `curl -s $B/v1/permits/$P/blocking-checks \| PY -c "import json,sys;c=json.load(sys.stdin)['data']['checks'][0];print(c['precursor']['severity_gate'],c['precursor']['severity_basis'],c['origin'])"` |
| W1-13 | the client supplied 0 and a trigger projected 4 — `evidence/gate-refusal/proof-20260810T054407Z.json#projection`, 10 of 10 assertions holding | `DEVPOST.md:316` | that artefact | `projection.assertions_total` 10; `projection.assertions_held` 10 | `PY -c "import json;p=json.load(open('evidence/gate-refusal/proof-20260810T054407Z.json'))['projection'];print(p['assertions_total'],p['assertions_held'])"` |
| W1-14 | clause text is embedded into C-SPANN indexes declared inline at `CREATE TABLE`, with `CONSTRAINT embed_model_stated` forcing each row to record its model; the plan naming `clause_embedding@ce_ann` is at `evidence/aws/ann/ann-proof.json` | `DEVPOST.md:306` | `0031_clause_embedding.sql` + `evidence/aws/ann/ann-proof.json` | `embed_model_stated` at `0031_clause_embedding.sql:21` and `:147`; the artefact contains `clause_embedding@ce_ann` and an `EXPLAIN` | `grep -n embed_model_stated verticals/mainline/db/migrations/0031_clause_embedding.sql` and `PY -c "import json;print('clause_embedding@ce_ann' in json.dumps(json.load(open('evidence/aws/ann/ann-proof.json'))))"` |

### 2.2 · W2 — `README.md`, the six live GETs

| # | the claim | at | produced by | W6 observed | falsify it with |
|---|---|---|---|---|---|
| W2-1 | *"its answer is already committed: verdict PROVEN, 23 of 23 assertions held, 0 failed"* | `README.md:81` | `evidence/demo/memory-loop.json` | identical to W1-1 | as W1-1 |
| W2-2 | *"79 values audited, 0 of them found in the source"* | `README.md:96` | same file `#self_audit` | identical to W1-4 | as W1-4 |
| W2-3 | **provenance** — `curl $B/v1/clauses/dec0de00-0004-…/ancestry` returns a `blame_edge` with `basis: asserted_document` and an `evidence_quote_sha256` | `README.md:330` | **live** ancestry route | `data.blame_edges[0].basis` `asserted_document`; `evidence_quote_sha256` = a lowercase 64-hex digest beginning `f83044c9` | `curl -s $B/v1/clauses/dec0de00-0004-4000-8000-000000000001/ancestry \| PY -c "import json,sys;e=json.load(sys.stdin)['data']['blame_edges'][0];print(e['basis'],len(e['evidence_quote_sha256']))"` |
| W2-4 | **ancestry** — `commit_chain` with `control_delta: introduce`, closure of `depth 1`, `ancestor_count 1` | `README.md:331` | same live route | `data.commit_chain[0].control_delta` `introduce`; `data.closure.depth` 1; `data.closure.ancestor_count` 1 | same command, `…['data']['commit_chain'][0]['control_delta']`, `…['data']['closure']` |
| W2-5 | **severity floors** — `severity_gate: 4`, `severity_basis: human_rated`, `origin: blame_ancestry` | `README.md:332` | **live** blocking-checks route | identical to W1-12 | as W1-12 |
| W2-6 | **logged silence** — a Merkle receipt: `corpus_root`, `candidate_root`, `theta 0.35`, `s 1`, `n 1`, a boundary proof | `README.md:333` | **live** `GET $B/v1/permits/$P/silence` | `data.receipt.corpus_root` 64-hex beginning `91e35cc5`; `candidate_root` beginning `f23c0569`; `theta` 0.35; `s` 1; `n` 1; `boundary_proof.leaf_s.leaf_hash_hex` present; `policy_version` `demo-recall-1.0` | `curl -s $B/v1/permits/$P/silence \| PY -c "import json,sys;r=json.load(sys.stdin)['data']['receipt'];print(r['theta'],r['s'],r['n'],r['policy_version'])"` |
| W2-7 | **retrieval accounting** — `n_candidates 1 · n_blocking 1 · n_advisory 0 · n_silenced 0 · n_deduped 0`, plus the `index_plan_digest` | `README.md:334` | **live** `GET $B/v1/recall-runs/dec0de00-0009-…` | all five counts exactly as printed; `index_plan_digest` 64-hex beginning `d98e50a8`; `started_at` `2026-08-02T03:00:00Z` | `curl -s $B/v1/recall-runs/dec0de00-0009-4000-8000-000000000001 \| PY -c "import json,sys;d=json.load(sys.stdin)['data'];print(d['counts'],d['index_plan_digest'][:8])"` |
| W2-8 | **the act** — `curl -XPOST $B/v1/demo/gate-run` returns the refusal's `mus` and `naa` | `README.md:335` | **live** gate-run | `verdict` `PROVEN`, 4 beats, sqlstates in order `00000` · `23514` · `P0001` · `00000`, beats 2 and 3 carrying `refusal` | as W1-6 |
| W2-9 | **R4 read honestly** — *"the receipt is complete and `entries` is empty — `n_silenced: 0`, nothing was withheld"* | `README.md:340` | **live**, two different responses | `data.entries` is `[]` on the silence route **and** `data.counts.n_silenced` is 0 on the recall-run route — two responses agreeing | `curl -s $B/v1/permits/$P/silence \| PY -c "import json,sys;print(json.load(sys.stdin)['data']['entries'])"` |
| W2-10 | *"the receipt says which of its own fields no column produced: `staged: true`, with a `staged_note` naming `receipt.bound.statement`"* | `README.md:340` | **live** silence route | envelope `staged` `true`; `staged_note` opens *"receipt.bound.statement is the only value in this payload that no column produced"*; the `provenance` array carries `{"chip": "staged", "pointer": "/receipt/bound/statement"}` | `curl -s $B/v1/permits/$P/silence \| PY -c "import json,sys;e=json.load(sys.stdin);print(e['staged']);print([p for p in e['provenance'] if p['chip']=='staged'])"` |
| W2-11 | *"Every one of those responses carries a `provenance` array of per-field chips — `db:column`, `derived`, `staged`"* | `README.md:340` | **live**, all four GETs | ancestry 11 chips (`db:column` 8, `db:constraint` 1, `derived` 2); blocking-checks 6 (`db:column` 3, `derived` 3); silence 6 (`db:column` 4, `derived` 1, `staged` 1); recall-run `db:column` 17 | `curl -s $B/v1/permits/$P/blocking-checks \| PY -c "import json,sys;print(json.load(sys.stdin)['provenance'])"` |
| W2-12 | **the two dropped semantics** — archival bonds and fixity are design, and their live accounting reads zero: `n_bonded_sev5: 0`, `n_bonded_sev5_blocking: 0`, and `GET /v1/audit` returns `mainline_audit.v_fixity_coverage` with an empty `rows` array | `README.md:350` | **live** recall-run + audit routes | `counts.n_bonded_sev5` 0; `counts.n_bonded_sev5_blocking` 0; the audit response's `v_fixity_coverage` view declares 9 columns and `rows` of length 0 | `curl -s $B/v1/audit \| PY -c "import json,sys;v=[x for x in json.load(sys.stdin)['data']['views'] if 'fixity' in x['view']][0];print(v['view'],len(v['rows']))"` |
| W2-13 | the `bonded_fatalities_all_blocking` arm is governed by `spec/invariants/I13-silence-logged.md` | `README.md:350` | that spec file | the file exists and names `bonded_fatalities_all_blocking` 3 times | `grep -c bonded_fatalities_all_blocking spec/invariants/I13-silence-logged.md` |

### 2.3 · W3 — `docs/submission/JUDGING-AXES.md`, the score sheet

| # | the claim | at | produced by | W6 observed | falsify it with |
|---|---|---|---|---|---|
| W3-1 | the tie-break is lexicographic, quoted verbatim from Official Rules §6, so Agentic Memory Design decides every tie and Product Readiness is fourth | `JUDGING-AXES.md:25` | the contest's own Rules page, quoted; corroborated at `docs/demo/research/r1-judging.md` §1.2 | the quotation is marked `<!-- prose-hygiene: quoting -->` and reproduced without this repository's own emphasis; the corroborating file exists | `grep -n "Tie Breaking" docs/demo/research/r1-judging.md docs/submission/JUDGING-AXES.md` — and the Rules page itself, which is the authority |
| W3-2 | *"78 links, 0 broken"* on this page, re-resolved after this revision's edits | `JUDGING-AXES.md:48` | the page against the working tree | **reproduced exactly: 78 links, 0 broken**, by an independent implementation of the walk the page describes | see §2.6 for the script; `PY w6_links.py docs/submission/JUDGING-AXES.md` |
| W3-3 | over `RULES-MATRIX.md` the walk returns 12 and 0; over `DEVPOST.md` 12 and 0; over `docs/TOOL-USAGE.md` 77 and 0, with the 75 it read an hour earlier kept beside it | `JUDGING-AXES.md:60-64` | same walk | **12/0 and 12/0 reproduce exactly**, and `docs/TOOL-USAGE.md` reads 77 now and reproduced 75 **on the bytes that existed at the earlier reading** — see §7.2, which resolves it in W3's favour | `PY w6_links.py docs/submission/RULES-MATRIX.md docs/submission/DEVPOST.md` |
| W3-4 | the criterion's adjective *production-grade* governs the memory layer; §4's concession governs the custody store and the operator surface, and the page will not merge them | `JUDGING-AXES.md:112` | Official Rules §6 quotation + the artefacts in W1-10 and W1-11 | the two halves are backed by different artefacts and neither is overstated; `docs/HONESTY.md` and `docs/CI-STATE.md` are byte-identical to `HEAD` (§5.3) | `git diff --stat -- docs/HONESTY.md docs/CI-STATE.md` → empty |
| W3-5 | named `CHECK` at `0050_permit.sql:114`; composite FK at `0071a_epoch_pin_permit.sql:35-39`; `FORCE ROW LEVEL SECURITY` at `0181a_permit_rls_force.sql:54`; chain 271 of 271 (`evidence/deploy/cloud-chain.json`) | `JUDGING-AXES.md:112-124` | those files | line numbers verified exactly: 114, 39 (inside the cited 35-39 range), 54 | `grep -n "FORCE ROW LEVEL SECURITY" verticals/mainline/db/migrations/0181a_permit_rls_force.sql` |
| W3-6 | the three live routes, re-read `2026-08-16`, return `severity_gate 4` / the five counts + `index_plan_digest` / the receipt with `entries: []` | `JUDGING-AXES.md:136-143` | the three live GETs | all three re-read by W6 today; every field as printed | as W2-5, W2-7, W2-9 |
| W3-7 | *"Two of those three are among the **5** routes `evidence/demo/memory-loop.json` walks; `/silence` is not in that transcript at all"* | `JUDGING-AXES.md:147` | `evidence/demo/memory-loop.json#requests` | **the second clause holds** — the literal `/silence` does not appear in that artefact. **The first clause disagrees with the artefact: `requests` has 7 entries and 7 distinct routes, not 5.** Reported in §7.1, not fixed | `PY -c "import json;d=json.load(open('evidence/demo/memory-loop.json'));print(len(d['requests']),sorted({r['route'] for r in d['requests']}))"` |

### 2.4 · W4 — `docs/TOOL-USAGE.md` and `evidence/mcp/`

| # | the claim | at | produced by | W6 observed | falsify it with |
|---|---|---|---|---|---|
| W4-1 | Managed MCP Server — **EXERCISED**: an MCP client dialled CockroachDB's own managed endpoint and drove the sixteen-question judge pack | `docs/TOOL-USAGE.md:633` | `evidence/mcp/pack-run.json`, `evidence/mcp/session.json` | `passed` 15 · `total` 16, `generated_at` `2026-08-16T07:33:46Z`; the session ran as `sql_identity` `managed-mcp` with HTTP `200`, `generated_at` `2026-08-16T07:33:26Z` | `PY -c "import json,re;p=json.dumps(json.load(open('evidence/mcp/pack-run.json')));print(re.findall(r'\"passed\": (\d+)',p)[:2],re.findall(r'\"total\": (\d+)',p)[:2])"` |
| W4-2 | protocol `2025-06-18`, `serverInfo cockroachdb-cloud 1.0.0`, and 12 tools with their full `inputSchema` | `docs/TOOL-USAGE.md:~660` | `evidence/mcp/session.json`, `evidence/mcp/tools-schema.json` | the tool count 12 appears in `tools-schema.json`; `session.json` carries `sql_identity` `managed-mcp` and `publishable` `false` | `PY -c "import json;print(sorted(json.load(open('evidence/mcp/tools-schema.json'))))"` |
| W4-3 | `evidence/mcp/session-extract.json` reproduces the `channels.mcp` and `managed_mcp_availability` blocks of `evidence/deploy/judge-run.json`, **copied, not re-run**, with that file's SHA-256 quoted | `docs/TOOL-USAGE.md:649` | both files | **byte-equality holds both ways**: `extract['channels.mcp'] == judge-run['channels']['mcp']` is `True`, and the availability block likewise; the digest W4 quotes matches the file's actual sha256 | `PY -c "import json;s=json.load(open('evidence/deploy/judge-run.json'));e=json.load(open('evidence/mcp/session-extract.json'));print(e['extract']['channels.mcp']==s['channels']['mcp'])"` |
| W4-4 | the underlying committed record: `channels.mcp` `ran true`, endpoint `https://cockroachlabs.cloud/mcp`, protocol `2025-06-18`, identity `managed-mcp`, 15 of 16 | `docs/TOOL-USAGE.md:1650` | `evidence/deploy/judge-run.json#channels.mcp` | every field verbatim, `generated_at` `2026-08-11T00:23:29Z` | `PY -c "import json;print(json.load(open('evidence/deploy/judge-run.json'))['channels']['mcp'])"` |
| W4-5 | **both caveats ride with it**: divergence `N01` — the `managed-mcp` identity *can* read `mainline_qa.v_disposition_profile` — and the credential is not publishable to anonymous judges, so MCP is demonstrated and is **not** the judge access path | `docs/TOOL-USAGE.md:950` and `:1650` | `evidence/mcp/pack-run.json#divergences`, `evidence/mcp/session.json` | `divergences` present; `publishable` `false` in the session record | `PY -c "import json;print(json.load(open('evidence/mcp/pack-run.json'))['divergences'])"` |
| W4-6 | the CockroachDB feature table's per-row file counts each carry a `[src: …]` pointer into `evidence/tool-usage/crdb-features.json` | `docs/TOOL-USAGE.md:~600` | that artefact | `totals` = 14 rows · `EXERCISED` 12 · `DESIGNED` 2 · `NOT-AVAILABLE` 0; `by_kind` tool 4 · feature 10 | `PY -c "import json;print(json.load(open('evidence/tool-usage/crdb-features.json'))['totals'])"` |
| W4-7 | the AWS side splits 6 EXERCISED / 5 DESIGNED / 1 NOT-AVAILABLE across 12 service rows | `docs/TOOL-USAGE.md` / `DEVPOST.md` close block | `evidence/tool-usage/aws-services.json` | `totals` = 12 rows · `EXERCISED` 6 · `DESIGNED` 5 · `NOT-AVAILABLE` 1 | `PY -c "import json;print(json.load(open('evidence/tool-usage/aws-services.json'))['totals'])"` |
| W4-8 | Agent Skills is **DESIGNED**, and *"nothing this repository records"* is stated plainly rather than dressed up | `docs/TOOL-USAGE.md:~590` | `evidence/tool-usage/crdb-features.json` | the artefact carries exactly 2 `DESIGNED` rows against 12 `EXERCISED` — the verdict is the artefact's, not the page's | as W4-6 |

### 2.5 · W5 — `evidence/demo/live-semantics.json`, `docs/demo/LIVE-SEMANTICS.md`, `scripts/proof/live_semantics.py`

| # | the claim | at | produced by | W6 observed | falsify it with |
|---|---|---|---|---|---|
| W5-1 | the six semantics are live on the deployed origin: verdict PROVEN, 45 of 45 assertions held, 0 failed | `evidence/demo/live-semantics.json` | the artefact itself, regenerated `2026-08-16T12:26:03Z` | `verdict` `PROVEN`; `assertions_total` 45; `assertions_held` 45; `assertions_failed` `[]`; `base_url` the live origin | `PY -c "import json;d=json.load(open('evidence/demo/live-semantics.json'));print(d['verdict'],d['assertions_total'],d['assertions_held'],d['assertions_failed'])"` |
| W5-2 | 26 individually named claims, each with route, JSON pointer, expected, observed and a provenance chip | same | `#claims` | 26 entries, **every one `holds: true`**; W6 re-read all 26 pointers off the origin independently and every observed value agrees — §6.4 | `PY -c "import json;c=json.load(open('evidence/demo/live-semantics.json'))['claims'];print(len(c),all(x['holds'] for x in c))"` |
| W5-3 | the silence ledger sentence per ruling R4: *"its entries list is EMPTY, which the recall run corroborates from a different response with `counts.n_silenced = 0`"* | same, `#silence_ledger` | two live responses | `entries_in_the_silence_payload` 0 and `n_silenced_in_the_recall_run` 0, each with the route it was read from — the corroboration is cross-response, which is the point | `PY -c "import json;print(json.load(open('evidence/demo/live-semantics.json'))['silence_ledger'])"` |
| W5-4 | the program's **source audit is the weaker of the two claims and says so**: no identifier and no origin originates in the source, but the *expected values* deliberately do | same, `#source_audit` | the artefact | `uuid_literals_in_the_source` 0; `origin_host_occurrences_in_the_source` 0; `source_sha256` recorded with `source_bytes` 57148; a `contrast` field names `scripts/proof/memory_loop.py` as making the stronger claim | `PY -c "import json;print(json.load(open('evidence/demo/live-semantics.json'))['source_audit'])"` |
| W5-5 | `not_proven_by_this_artefact` names what it does **not** prove — that the world is anyone's, and that the ACT half is covered (it sends no POST at all) | same | the artefact | the block is present and names the SYNTHETIC corpus and the absent POST explicitly | `PY -c "import json;print(json.load(open('evidence/demo/live-semantics.json'))['not_proven_by_this_artefact'])"` |
| W5-6 | each route records its own `http_status`, `response_bytes` and `response_sha256` | same, `#routes` | the artefact | present for each route; e.g. `/v1/demo/subjects` → HTTP `200`, 8941 bytes, a 64-hex response digest | `PY -c "import json;print(json.load(open('evidence/demo/live-semantics.json'))['routes']['subjects'])"` |

### 2.6 · The link-walk script W6 used, so W3-2 and W3-3 are reproducible by a stranger

The page describes the walk in prose; W6 implemented it independently rather than trusting the
number. Save as `w6_links.py` and run it:

```python
import pathlib, re, sys
LINK = re.compile(r"\]\(([^)\s]+)")
def strip_code(text):
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced; continue
        if fenced: continue
        out.append(re.sub(r"`[^`]*`", "``", line))
    return "\n".join(out)
for rel in sys.argv[1:]:
    p = pathlib.Path(rel); t = strip_code(p.read_text(encoding="utf-8"))
    tot, broken = 0, []
    for target in LINK.findall(t):
        if target.startswith(("http://", "https://", "mailto:", "#")): continue
        tot += 1
        bare = target.split("#", 1)[0]
        if bare and not (p.parent / bare).exists(): broken.append(target)
    print(f"{rel} links={tot} broken={len(broken)} {broken[:6]}")
```

Measured `2026-08-16T12:23Z`: `JUDGING-AXES.md` 78/0 · `RULES-MATRIX.md` 12/0 · `DEVPOST.md`
12/0 · `docs/TOOL-USAGE.md` 77/0 (75/0 on the `12:08:50Z` bytes) · `README.md` 32/0.

---

## 3 · REFUSED — claims with no falsifying command

**None.** Every new or changed claim W6 found on the five surfaces resolved to an artefact or a
live route with a command that would falsify it, and every one of those commands was run.

That is a finding about this wave, not a courtesy: the plan's §4 handed the workers copy that
already carried its artefact pointer on every number, and the workers kept the pointers. Two
claims came close enough to name here, and both survive **as written** for a stated reason:

| candidate | why it is not REFUSED |
|---|---|
| W3-1, the tie-break quotation from Official Rules §6 | the authority is a third-party page this repository does not control, so no command in this tree can falsify it. It stays because the page **quotes it verbatim, marks the quotation, and names the corroborating internal file** rather than paraphrasing — the strongest available handling of a claim whose source is outside the tree. The falsifier is the Rules page itself, and that is stated. |
| W1-9's phrase *"a Product-Readiness point, not an embarrassment"* | it is a value judgement, not a measurement — but it is **quoted from the artefact's own note** rather than authored by the page, and the quotation is checkable byte-for-byte. Row W1-9 falsifies the quotation, not the judgement. |

---

## 4 · THE REPOSITORY'S OWN CONTROLS — verdicts, with exit codes

Both were run after W1, W2 and W3 landed. **No rule was narrowed, scoped, skipped or disabled.**

### 4.1 · `python scripts/submission/check_submission_prose.py` — **exit 0, GREEN**

```
== claim_hygiene, over its own published surface (delegated, not reimplemented)
  scanned 23 file(s) against 21 rules
  ABSENT  docs/MECHANISMS.md matched no file - not scanned, and therefore not passed
  ABSENT  docs/deck/**/*.md  matched no file - not scanned, and therefore not passed
  ABSENT  docs/deck/**/*.html matched no file - not scanned, and therefore not passed
  ABSENT  docs/deck/**/*.txt matched no file - not scanned, and therefore not passed
  claim hygiene OK

== submission surface: 9 SUB rules + the claim_hygiene table
  scanned 19 file(s)
  SCOPED   HYG-sha-literal is not re-applied here
  DELEGATED README.md carries the claim_hygiene table above; SUB rules only here
  REGISTER docs/submission/MUST-NOT-CLAIM.md quotes prohibitions in full - not scanned, not passed
  submission prose OK
```

Run before the landings (`12:10Z`) and again after (`12:22Z`); **exit 0 both times**, same
scanned counts. The scanner's surface is `README.md`, `docs/submission/*.md` and
`docs/TOOL-USAGE.md` — exactly the set W1 through W4 touched — so all four surfaces passed the
nine SUB rules and the delegated claim-hygiene table with the wave's new prose in place.

The four `ABSENT` lines and the `SCOPED`, `DELEGATED` and `REGISTER` lines are the scanner's
own pre-existing disclosures, present identically in both runs and unchanged by anyone in this
wave. **They are reproduced here rather than summarised as "green" because a scanner that names
what it did not scan is the reason its green is worth anything.**

### 4.2 · `python scripts/demo/claim_hygiene.py --check <files>` — **exit 1, RED, on a rule the submission surface scopes out**

The brief's literal command is a usage error — `--check` requires file arguments and exits 2
with `usage:` — so W6 ran it over exactly the four files the wave touched:

```
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    README.md docs/TOOL-USAGE.md docs/submission/DEVPOST.md docs/submission/JUDGING-AXES.md
```

**exit 1 · scanned 4 file(s) against 21 rules · 5 claim-hygiene violation(s), all `HYG-sha-literal`:**

| where | the literal |
|---|---|
| `docs/TOOL-USAGE.md:208` | a 7-character commit id inside `headSha …` |
| `docs/submission/DEVPOST.md:256` | two 7-character commit ids in the gap census |
| `docs/submission/DEVPOST.md:258` | one 7-character commit id |
| `docs/submission/DEVPOST.md:329` | one 7-character commit id |

**The rule that fired, the truer sentence, and who owns it.** `HYG-sha-literal` exists because
`commit_id` is a sha256 over the JCS envelope and cannot be chosen in advance, so a SHA spoken
in the film or printed in the deck is a promise the DAG may not keep. **All five literals
pre-date this wave** — every one is present in the committed `HEAD` version of its file, which
is the discriminating test:

```python
import re, subprocess
PAT = r"(?<![0-9a-f])(?=[0-9a-f]{7}(?![0-9a-f]))(?=[a-f]*[0-9])[0-9a-f]{7}"
tokens = lambda text: set(re.findall(PAT, text))
for f in ("docs/submission/DEVPOST.md", "docs/TOOL-USAGE.md",
          "README.md", "docs/submission/JUDGING-AXES.md"):
    head = subprocess.run(["git", "show", "HEAD:" + f],
                          capture_output=True, text=True, encoding="utf-8").stdout
    work = open(f, encoding="utf-8").read()
    print(f, sorted(tokens(work) - tokens(head)))
```

It prints, per file, the seven-hex tokens the working tree has that the committed version does
not. **All four print the empty list.** No worker in this wave introduced a commit literal.

Two notes on that command, because a control that hides its own imprecision is not a control.
It **derives** the literals rather than spelling them out, so this page does not add five more
instances of the thing the rule bans. And the digit lookahead is load-bearing: without it the
same walk reports one new token in `docs/TOOL-USAGE.md` — the letters `feedbac`, which are
seven characters all drawn from the hex alphabet and are not a commit id at all. The
repository's own `HYG-sha-literal` does not report it either, which is the corroboration that
the refined pattern matches the rule's intent rather than merely producing the answer this page
wanted.

And the repository's own control over the submission surface **deliberately does not apply this
rule there**, printing its reason on every run: *"a provenance disclosure's job is to quote git
commits; the ban is on SHAs in the film and the deck, where `commit_id` cannot be chosen in
advance."* That scoping is pre-existing, authored by the control, and **W6 did not create it,
widen it or lean on it to buy a green** — §4.1's exit 0 is the surface's real verdict, and this
hand-scan is the stricter reading applied anyway, with its red printed in full.

**No action is assigned to any worker**, because no worker wrote these lines. If the founder
wants the film-and-deck ban extended over the submission surface, that is a scoping decision and
it is his to make, not W6's — and it would be a change to a control, not to a page.

### 4.3 · The same hand-scan, turned on this page — **exit 1, two hits, both this page's own**

A control that exempts itself is not a control. **This page was scanned by the same command and
it is not clean:**

```
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/submission/EXTRA-CREDIT-CLAIMS.md
```

**exit 1 · scanned 1 file(s) against 21 rules · 2 violations**, both `HYG-sha-literal`, both the
same seven-character commit id — at line 9, where this page dates its own sweep to the commit it
swept, and in §8.1, where it names the commit at which the false `SUBMISSION.json` sentence is
still live. **Both are kept, and here is the reasoning rather than an exemption.** The rule
exists because a `commit_id` cannot be chosen in advance, so a SHA *spoken in the film or printed
in the deck* is a promise the DAG may not keep. Neither of these is a promise: each names a
commit that already exists, so a reader can check out that exact tree and reproduce the reading.
That is the identical reason the repository's own submission-surface control gives for scoping
this rule out — *"a provenance disclosure's job is to quote git commits"* — and this page is a
provenance disclosure. **What W6 did not do is quietly rely on that scoping**: the hand-scan's
red is printed above with its line numbers; **the first draft of this page scanned at five hits,
and the three avoidable ones were rewritten out** — §4.2's command now derives the literals it
compares instead of spelling them — leaving the two that carry information a reader needs, which
are argued for above rather than hidden.

**The two scans add up, which is the arithmetic check on both.** Run over all five files at once
— the four the wave touched plus this one — the hand-scan reports `scanned 5 file(s) against 21
rules`, **exit 1, 7 claim-hygiene violation(s)**, every one `HYG-sha-literal`: the 5 of §4.2 that
pre-date the wave, plus the 2 of this section. **No other rule fired on any of the five files.**

This page's verdict on the repository's real control, with itself included, is in §4.1:
`submission prose OK`, **scanned 20 file(s)**, exit 0 — the twentieth file being this one.

---

## 5 · THE REGRESSION BASELINES

### 5.1 · The suite — **1070 collected, and it is RED for a cause outside this wave**

The canonical argv, taken from `scripts/qa/regression_guard.py:225-227`, not invented here:

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests tests/deploy \
    --crdb=reuse -q -p no:cacheprovider --timeout=900 --junitxml=<out>
```

Read from the `--junitxml` **root element**, never a terminal tail:

| reading | collected | passed | failed | errors | skipped | time |
|---|---|---|---|---|---|---|
| baseline `qa/film.xml`, `2026-08-16 16:43` local | **1070** | **1069** | 0 | 0 | 1 | 213.7 s |
| W6, `2026-08-16T12:20Z` | **1070** | 1056 | **1** | **12** | 1 | 126.0 s |

**Collection did not move. Nothing was deleted, nothing was added.** That is the number the
guard calls a regression when it falls, and it did not fall.

**All 13 reds share one cause, and it is not code.** Every one fails in fixture *setup* with the
identical message:

```
psycopg.errors.ConfigurationLimitExceeded: cannot create new schema object(s):
  would exceed approximate maximum (20000); current count: 20161
HINT: You can increase the limit by adjusting the cluster setting sql.schema.approx_max_object_count
```

The local single-node CockroachDB has **240 databases** and **20,161 schema objects** against an
approximate ceiling of 20,000 — accumulated scratch databases from many waves of workers, this
one included. The tests that fail are exactly the ones whose fixtures `CREATE` schema objects
(`test_judge_can_sign.py`, 12 errors; `test_reads.py::test_health_reads_the_deploy_chain_marker_when_the_database_has_one`,
1 failure).

**The attribution is checkable in one command.** Both suite paths are byte-identical to `HEAD`:

```
git status --porcelain -- verticals/mainline/apps/demo-api tests/deploy
```

→ empty. No worker in this wave touched a test, a fixture or a source file under either path;
the wave's changes are Markdown and JSON on documentation surfaces. The same 14 test cases are
green in the committed `qa/regression-guard-suites.xml`.

**W6 did not repair it, and that is deliberate.** The two available repairs are dropping other
workers' scratch databases — destructive, and they are in flight — or raising
`sql.schema.approx_max_object_count`, which is changing a cluster setting so that a red goes
green. Both are the founder's call. **This is recorded as an environment condition, not as a
pass.** Re-run the argv above after the local cluster is reclaimed and the row should read
1069 passed again.

### 5.2 · The ratchets — **neither rose**

| ratchet | command | exit | reading |
|---|---|---|---|
| **mypy** | `PY scripts/qa/mypy_targets.py --ratchet` | **0** | `OK: 0 error(s), none above the recorded count.` — `qa/mypy-ratchet.json` records `total_errors` 0 over 660 source files. **Unmoved.** |
| **ruff** | `PY scripts/qa/ruff_ratchet.py` | **1** | `ruff 0.16.1 \| lint findings 656 \| unformatted files 226`. **Lint IMPROVED by 1** (`E501` in `scripts/`, baseline 1 → measured 0). **Format is RED**: 226 unformatted files against a baseline of 0, in 6 trees. |

**The ruff red, honestly.** It is a formatting regression against a hard-gate baseline of 0, and
it is reported rather than absorbed. It is **not attributable to this wave**: 50 of the 226 are
under `packages/trappoint-*` and 107 under `tests/`, trees no extra-credit worker touched — the
whole wave's Python footprint is `scripts/proof/live_semantics.py` (W5). A repo-wide `226` with
a `0` baseline recorded on `2026-08-11` at the same `ruff 0.16.1` is a standing condition of the
tree, not a diff. **W6 did not run `ruff format`, did not run `--rebaseline`, and did not
narrow a tree**: the ratchet's own text says raising the number is allowed and raising it
silently is not, so it is raised here out loud and left for the owner of the trees involved.

**The direction rule held both ways:** lint fell by one and was not re-recorded upward; the
format count was not re-baselined to make the exit code 0.

### 5.3 · The two constants and the guard

| protected thing | command | reading |
|---|---|---|
| `DEFAULT_MAX_RESPONSE_BYTES` | `grep -n "DEFAULT_MAX_RESPONSE_BYTES: Final" verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py` | `323: DEFAULT_MAX_RESPONSE_BYTES: Final = 136 * 1024` — **the expression is intact**, and the file is unmodified in the working tree |
| console bundle headroom guard | `grep -n "_MINIMUM_HEADROOM_BYTES: Final" verticals/mainline/apps/demo-api/tests/test_static_site.py` | `342: _MINIMUM_HEADROOM_BYTES: Final = 1024` — **the floor is intact**; `qa/bundle-headroom.json` records the standing measurement 139,264 − 137,939 = 1,325 bytes of headroom, above the 1,024 floor. The guard lives inside `test_static_site.py`, which is inside the suite of §5.1, and it is **not** among the 13 reds |
| `docs/HONESTY.md`, `docs/CI-STATE.md`, `docs/submission/MUST-NOT-CLAIM.md` | `git status --porcelain -- docs/HONESTY.md docs/CI-STATE.md docs/submission/MUST-NOT-CLAIM.md` | **empty — all three byte-identical to `HEAD`.** No ratchet, honesty document or prohibition register was touched by anyone in this wave |
| database grants | `git status --porcelain -- verticals/mainline/db` | **empty.** The standing `materialise_checks` / `exposure_receipt` INSERT gap is exactly as open as it was |

---

## 6 · RECONCILIATION — W5's measurement against the copy W1, W2 and W3 wrote

W1 through W3 wrote from the plan's §2 and §4 measurements. W5 re-measured the same origin
independently — first at `2026-08-16T12:15:54Z`, then regenerated at `12:26:03Z`, both PROVEN at 45 of 45 — and wrote `evidence/demo/live-semantics.json`. **W6 then
re-read every value off the origin a third time.** Three independent readings.

| the value | the copy (W1/W2/W3) | W5's artefact | W6's own GET | verdict |
|---|---|---|---|---|
| `blame_edges[0].basis` | `asserted_document` | `asserted_document` | `asserted_document` | **AGREE** |
| `evidence_quote_sha256` | "an `evidence_quote_sha256`" | 64-hex, `f83044c9…` | 64-hex, `f83044c9…` | **AGREE** |
| `commit_chain[0].control_delta` | `introduce` | `introduce` | `introduce` | **AGREE** |
| `closure.depth` / `ancestor_count` | 1 / 1 | 1 / 1 | 1 / 1 | **AGREE** |
| `precursor.severity_gate` | 4 | 4 | 4 | **AGREE** |
| `precursor.severity_basis` | `human_rated` | `human_rated` | `human_rated` | **AGREE** |
| `origin` | `blame_ancestry` | `blame_ancestry` | `blame_ancestry` | **AGREE** |
| `receipt.theta` | 0.35 | 0.35 | 0.35 | **AGREE** |
| `receipt.s` / `receipt.n` | 1 / 1 | 1 / 1 | 1 / 1 | **AGREE** |
| `corpus_root` / `candidate_root` | present, Merkle | 64-hex `91e35cc5…` / `f23c0569…` | same two digests | **AGREE** |
| `boundary_proof.leaf_s.leaf_hash_hex` | present | 64-hex | 64-hex, equal to `candidate_root` | **AGREE** |
| `policy_version` | `demo-recall-1.0` | `demo-recall-1.0` | `demo-recall-1.0` | **AGREE** |
| the five counts | `1 · 1 · 0 · 0 · 0` | `1 · 1 · 0 · 0 · 0` | `1 · 1 · 0 · 0 · 0` | **AGREE** |
| `index_plan_digest` | present | 64-hex `d98e50a8…` | same digest | **AGREE** |
| `entries` on the silence payload | `[]` | 0 entries, read from `/data/entries` | `[]` | **AGREE** |
| `n_silenced` | 0 | 0, read from a *different* response | 0 | **AGREE** |
| `staged` / `staged_note` | `true`, naming `receipt.bound.statement` | recorded in `#provenance_and_staging` | `true`; the note names that pointer; the `staged` chip points at it | **AGREE** |

**Zero disagreements between W5's artefact and the copy.** The one number where the copy and an
artefact do disagree is not a live-semantics value at all — it is W3's route count against
`memory-loop.json`, and it is §7.1.

**One scope difference, named rather than smoothed.** W5's `#source_audit` makes a *weaker*
self-audit claim than `memory-loop.json` does, and says so in its own `contrast` field: the
expected values in `live_semantics.py` **are** authored in the source, deliberately, because a
checker that only records what it was told cannot go red. `memory-loop.json` claims no value
whatsoever originates in its program. **Both claims are true of their own program**, and the
copy uses the strong form only where it cites `memory-loop.json` (rows W1-4, W2-2). No page
attributes the strong claim to W5's artefact.

---

## 7 · NAMED DISAGREEMENTS — reported, not fixed

### 7.1 · CONTRADICTION · W3's route count against `evidence/demo/memory-loop.json`

**The sentence, verbatim**, `docs/submission/JUDGING-AXES.md:147`:

> Two of those three are among the `5` routes `evidence/demo/memory-loop.json` walks;
> **`/silence` is not in that transcript at all**, and is quoted here as a live route rather
> than as a line of it.

**The two readings.**

| reading | value | source |
|---|---|---|
| the page | **5** routes walked | `JUDGING-AXES.md:147` |
| the artefact | **7** requests, **7** distinct routes, each HTTP `200` | `evidence/demo/memory-loop.json#requests` |

**The artefact decides it, and here it is.** `#requests` holds seven entries:
`GET /v1/demo/subjects`, `GET /v1/health`, `GET /v1/clauses/{clause_uuid}/ancestry`,
`GET /v1/recall-runs/{run_id}`, `GET /v1/receipts/{receipt_id}`,
`GET /v1/permits/{permit_id}/blocking-checks`, `GET /v1/permits/{permit_id}`.

```
PY -c "import json;d=json.load(open('evidence/demo/memory-loop.json'));print(len(d['requests']),sorted({r['route'] for r in d['requests']}))"
```

**The reading under which 5 is right, stated so W3 is judged fairly.** Seven minus the two
discovery calls — `/v1/health` and `/v1/demo/subjects`, which establish that the origin answers
and supply the identifiers — is exactly **5** substantive routes. That is very likely what the
sentence means. **But the sentence as printed says "the 5 routes it walks", and the artefact
records 7 walked routes**, so a judge who runs the obvious command finds a number that does not
match. W6 does not choose between the readings and does not edit W3's file.

**Handed to W3.** Either re-derive to 7, or keep 5 and say which two are excluded and why — e.g.
*"among the 5 substantive routes the transcript walks, beyond the two discovery calls to
`/v1/health` and `/v1/demo/subjects`"*. Both are honest; the current phrasing is the only one
that is falsifiable-and-falsified.

**The second clause of that sentence holds exactly as written.** The literal `/silence` does not
occur anywhere in `memory-loop.json` — the word "silence" appears only inside the column name
`n_silenced`. So `/silence` genuinely is quoted as a live route rather than as a line of that
transcript, which is the honest construction the sentence was written to make.

```
PY -c "import json;print('/silence' in json.dumps(json.load(open('evidence/demo/memory-loop.json'))))"
```

→ `False`.

### 7.2 · RESOLVED IN W3's FAVOUR · the `docs/TOOL-USAGE.md` link count

Mid-sweep, `JUDGING-AXES.md` recorded the walk over `docs/TOOL-USAGE.md` as **75 and 0** while
W6's independent walk over that file returned **77 and 0**. That looked like a contradiction and
is not one, and the discriminating test is that W6 kept the earlier bytes:

| bytes | link count |
|---|---|
| `docs/TOOL-USAGE.md` as of `12:08:50Z` (sha256 `94dd0c422a75fc4a`) | **75** |
| `docs/TOOL-USAGE.md` as of `12:23:28Z` (sha256 `c3541df069457634`) | **77** |

W4 added two relative links between the two readings. **W3's number reproduces exactly on the
bytes W3 measured**, and W3's own sentence anticipates precisely this: *"both of those documents
are being revised while this one is, so their figures are readings with a timestamp rather than
properties of the repository."*

**And by the final snapshot W3 had caught the drift without being told.** `JUDGING-AXES.md:62`
now reads *"`77` and `0` where the same walk read `75` about an hour earlier in the same
session"*, keeping both readings, and adds *"a number that moved twice inside one hour is the
clearest possible demonstration of why the timestamp is printed with it."* **No action, and
nothing outstanding.**

**The page's other three counts — 78/0 on itself, 12/0 on `RULES-MATRIX.md`, 12/0 on
`DEVPOST.md` — reproduce exactly on current bytes**, which is also the evidence that W6's
independent implementation of the walk matches W3's rather than merely agreeing by luck.

### 7.3 · NOTED · `evidence/mcp/` is no longer the pointer directory ruling R2 designed

The plan's **R2** authorised `evidence/mcp/` as a *pointer directory only* — a README plus a
verbatim extract — because no new Managed-MCP capture was authorised for this wave. **The
directory now also contains live captures** (`session.json`, `pack-run.json`,
`tools-schema.json`, `auditor-live.json`, `budget-live.json`), timestamped
`2026-08-16T07:33Z`, **written by a different, concurrent wave** working from
`docs/submission/mcp-real-plan.md` — not by W4 and not under R2.

**This is recorded, not objected to.** The captures are real, they are dated, they carry
`publishable: false` and their divergences, and W4's page treats them as primary while keeping
the pointer discipline for the extract (row W4-3, which W6 verified byte-for-byte). **The only
thing that would be dishonest is a later reader believing R2's "no capture was made" applies to
this directory.** It does not. R2 governed *this* wave's workers, and this wave's workers made
no MCP call; the captures came from elsewhere in the same tree on the same day.

---

## 8 · RULING R3 — the contradiction in `docs/submission/SUBMISSION.json`, reported and handed over

**W6 DID NOT EDIT `docs/submission/SUBMISSION.json`. W6 DID NOT WRITE `demo_url` OR
`video_url`.** That file is the single write point and its owner is the only one who changes a
value in it. What follows is a report and a replacement text, for the orchestrator.

### 8.1 · The false sentence, quoted verbatim

At the committed `HEAD` (`c951558`), `docs/submission/SUBMISSION.json` `notes.demo_url` opens:

> Unresolved because `terraform apply` has not been run: no MAINLINE Lambda, no Function URL, no
> bucket exists in the account.

and the field it annotates reads `"demo_url": "UNRESOLVED"`. Re-read it yourself:

```
git show HEAD:docs/submission/SUBMISSION.json | PY -c "import json,sys;d=json.load(sys.stdin);print(d['demo_url']);print(d['notes']['demo_url'][:160])"
```

### 8.2 · The two artefacts that contradict it

**One — `evidence/deploy/APPLIED.md`**, whose opening section heads itself with the apply's date,
`2026-08-14`, and which records, at line 14:

> `terraform apply    24 created, 0 changed, 0 destroyed`

```
grep -n "24 created" evidence/deploy/APPLIED.md
```

**Two — the origin itself, fetched by W6 on 2026-08-16 over the public internet with no
credential.** `GET /v1/health` returned HTTP `200` with `ok` `true`, `deploy_chain_files` 271
and `deploy_chain_applied` 271 (`evidence/deploy/live-health.json` is the committed copy of the
same reading):

```
curl -s $B/v1/health | PY -c "import json,sys;d=json.load(sys.stdin);print(d['ok'],d['deploy_chain_applied'],d['deploy_chain_files'])"
```

→ `True 271 271`. A Lambda that does not exist does not answer, and a chain that was never
applied does not report itself applied.

### 8.3 · THE STATE OF THIS AS OF 2026-08-16T12:23Z — the plan's premise has been overtaken

**In the uncommitted working tree the sentence is no longer a live claim.** `SUBMISSION.json`
was edited at `2026-08-16 21:48` local by the worker who owns it. `demo_url` now carries the
Function URL, and the old sentence survives **only as an explicitly dated quotation of a
superseded claim**:

> RESOLVED 2026-08-16. […] TWO SUPERSEDED CLAIMS ARE PRESERVED HERE RATHER THAN DELETED, because
> each was true when it was written and the sequence is the record. (1) Until 2026-08-14 this
> note read: `Unresolved because terraform apply has not been run: no MAINLINE Lambda, no
> Function URL, no bucket exists in the account.` That described a world that ended when the
> apply landed.

**A dated quotation of a superseded claim is not a false claim** — it is the construction this
repository uses everywhere else, and it is stronger than deletion. Verify the current state:

```
PY -c "import json;d=json.load(open('docs/submission/SUBMISSION.json'));print(d['demo_url']);print(d['notes']['demo_url'][:120])"
```

```
git diff --unified=0 docs/submission/SUBMISSION.json
```

**So the correction R3 asks for has already been applied by the file's owner, and the ledger
records that rather than re-proposing it.** The residual risk is narrow and worth naming: **the
fix is uncommitted.** If the working tree is reverted, discarded, or if only some files are
committed, the false sentence returns as a live claim at `HEAD` with `demo_url` reading
`UNRESOLVED`.

### 8.4 · The exact replacement text, for the orchestrator, if it is ever needed again

**Do not apply this if `notes.demo_url` already opens `RESOLVED 2026-08-16` — it does as of
`12:23Z`, and the current text is longer and better than this.** This is the contingency text
for a tree where the `HEAD` sentence has come back. It replaces **only** the opening sentence of
`notes.demo_url` and touches no other field:

> RESOLVED 2026-08-14 by the apply, and re-confirmed live on 2026-08-16. The sentence this note
> opened with until 2026-08-14 — `Unresolved because terraform apply has not been run: no
> MAINLINE Lambda, no Function URL, no bucket exists in the account.` — is preserved here as a
> superseded claim rather than deleted, because it was true when it was written and the sequence
> is the record. It stopped being true when the apply landed: evidence/deploy/APPLIED.md records
> `terraform apply  24 created, 0 changed, 0 destroyed` on 2026-08-14, and on 2026-08-16 the
> origin answered GET /v1/health over the public internet with `ok true`,
> `deploy_chain_applied 271` of `deploy_chain_files 271`, and POST /v1/demo/gate-run with a
> four-beat array at verdict PROVEN. The artefacts are authoritative and this note is derived.

**Constraints on whoever applies it.** The note must not carry the URL — that would make it a
second write point in a file designed to have exactly one, which is the rule the current note
already states and obeys. `demo_url` and `video_url` are written by that file's owner alone.
**W6 wrote neither, and edited nothing.**

---

## 9 · WHAT THIS WAVE DELIBERATELY DID NOT DO

Drawn from the plan's DO NOT table and its rulings, recorded here so nobody re-proposes any of
it at 02:00 on the last night.

| not done | why, and where it was decided |
|---|---|
| **No new Managed-MCP capture by this wave.** No MCP call, no Cloud service-account key read, no network run | Ruling **R2**. A second capture could *disagree* with the committed one two days out with no time to reconcile. The MCP evidence this wave surfaces is quoted, and row W4-3 proves the quotation is byte-identical to its source. (Captures made by the concurrent `mcp-real` wave are a separate matter — §7.3) |
| **`operator.html` was not deployed**, so the two operator screens still do not exist separately on the origin | A redeploy, absolutely prohibited. `README.md` already publishes the gap — `GET /operator.html` returns the shell byte-for-byte identical to `GET /` — and a published gap outscores a rushed deploy that breaks a working demo |
| **The `materialise_checks` / `exposure_receipt` INSERT grant was not widened**, so the loop stays read-only | The founder's call, unmade. Widening the write surface of an unauthenticated endpoint is not a documentation wave's decision. `git status --porcelain -- verticals/mainline/db` is empty |
| **No sixth AWS service and no fifth CockroachDB tool** | Ruling **R7**. Under a lexicographic tie-break, breadth on axis 2 behind depth on axis 1 is the worst hour available. The census counts are unchanged: 12 AWS rows, 14 CockroachDB rows |
| **Axis 4 was not softened, re-scoped or rewritten** | Ruling **R6**. Its concession is the reason the other four axes are believed. The fix was a scoping sentence in axis **1** (rows W1-11, W3-4), and `docs/HONESTY.md` and `docs/CI-STATE.md` are byte-identical to `HEAD` |
| **No rule was narrowed, scoped or disabled to turn a red green** | §4.2's red is printed in full; §5.2's ruff red is printed in full; §5.1's suite red is printed in full with its cause. A green bought by scoping is the failure this repository exists to refuse |
| **The mutation ratchet and the regression guard were not re-run for fresher numbers** | Both are standing measurements with committed artefacts. A fresh red at T-2 days is a cost with no upside |
| **Nothing was deployed, applied, redeployed, or written to AWS.** No `terraform`, no SSM read or write, no credential read or printed, no account id anywhere on this page | The founder's absolute prohibition. The only network access W6 made was read-only `GET`s against the public origin plus one `POST /v1/demo/gate-run`, which is permitted because it ends in `ROLLBACK` — `persisted false`, `disposition rolled_back` |
| **No scratch database was created.** The brief offered `w_W6`; W6 did not take it | Every check W6 ran is a file read, a read-only HTTP request, or a `SELECT` over a catalog. Creating a database into a cluster that is already 161 objects over its ceiling (§5.1) would have made the very condition W6 was measuring worse |
| **Nothing was committed.** The tree is left for the orchestrator | The founder's rule. `git status --porcelain` reports 45 entries at `12:34Z`, one of which is this file, and `git rev-parse --short HEAD` still reads the commit this sweep opened against |

---

## 10 · WHAT THIS PAGE ITSELF DOES NOT CLAIM

- **It does not claim the suite is green.** It is not, at `12:20Z`, for the cause in §5.1, and
  the cause is named rather than hidden behind a collection count that did hold.
- **It does not claim the ruff ratchet is green.** It is not, and §5.2 prints the six trees.
- **It does not claim W1 through W5's pages are complete**, only that every claim W6 found on
  them at `12:23:28Z` traces to an artefact. Workers were still editing during the sweep; §1
  dates every reading, and a sentence added after that timestamp has not been through this
  control.
- **It does not fix anything.** Two disagreements (§7.1) and one contingency correction (§8.4)
  are handed to their owners with the text they need. W6 edited exactly one file:
  `docs/submission/EXTRA-CREDIT-CLAIMS.md`.
