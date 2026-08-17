## Check us — clone it and reproduce the refusal

```bash
git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git
```

**The flag is not decoration.** Windows refuses a file path over 260 characters, the longest path this repository tracks
is 141, and that leaves 117 characters for the directory you clone into [src: qa/judge-dry-run.json#path_lengths]. Three
real clones bracket it: 111 characters cloned cleanly, 122 failed with `Filename too long`, and with the flag that same
122 cloned clean while a plain `open()` on the longest file still raised. **The flag fixes `git` and nothing else**, so
clone somewhere short, such as `D:\m`. On macOS and Linux it does nothing.

Then four commands, needing Docker, a Python interpreter, and no account of ours. Both columns are first-class, and the plain column is the one that actually ran: `just` and `uv` are not installed on the machine every number here was measured on [src: qa/judge-dry-run.json#host.tools_on_path].

| The recipe | The same thing, plain |
|---|---|
| `just doctor` | `python scripts/qa/doctor.py` |
| `just setup` | `python -m pip install -e packages/trappoint-migrate` |
| `just up` | `docker compose -f compose.yaml up -d --wait`<br>then `docker compose -f compose.yaml run --rm crdb-align` |
| `just prove` | `python scripts/proof/gate_refusal.py --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable"` |

* **`python scripts/qa/doctor.py` exits 1 on this machine, and it is right to.** The only rows it fails are `uv` and `just`. It prints a numbered remedy under each, and it does not block the proof.
* **The install step is not optional.** This page once said the proof needed nothing but the interpreter, and a recorded dry run falsified that [src: qa/judge-dry-run.json#runs]. Without the install, the script stops at `ModuleNotFoundError: No module named 'psycopg'`.
* **`crdb-align` pins the local node's `gc.ttlseconds` to 4500** — the value CockroachDB Cloud Basic enforces — so a time-travel assumption that is legal on your laptop is not one that fails in the cloud.

`just prove` builds a throwaway database, applies the migration chain, and attempts the same merge three times: refused,
refused again with the counter forged, then admitted. This is the committed run, in [`evidence/gate-refusal/`](evidence/gate-refusal/):

```
chain         271/271 applied, 0 failed, 63.094s
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 · outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       PROVEN
```

* **Tier 2 of [`VERIFY.md`](VERIFY.md) is the four commands above.** That page orders three ways of checking us by how much you have to take on faith. This one asks for nothing: no credential, no model call, 106 s, exit 0, `VERDICT PROVEN`.
* **Tier 1 is an offline bundle check**, also with no credential and no network, and `VERIFY.md` records what it returns today: `16 checks · 8 passed · 1 failed · 7 not checked`, **exit 1**. Seven cryptographic checks are unimplemented. One more is red on real drift: the bundle carries a hash of the program that puts each record into one fixed byte form, and that program has since changed. It is a genuine offline verification of the Merkle structure, the tree of hashes over the ledger, and it is **not** a verified ledger. An older census records the same tool at `9 passed · 0 failed · 7 not checked`, exit 2 [src: qa/test-state.json#external_checks.custody_bundle_verification]; that reading is from 2026-08-09 and the failing check is newer.
* **Tier 3 points your own agent** at CockroachDB's managed endpoint, with none of our code in the path. It was **not run** for this revision, because no scoped key was held.

Two artefacts repay opening on their own.

* [`evidence/gate-refusal/`](evidence/gate-refusal/) — a transcript of what one cluster did at one instant: the SQLSTATE, which is the database's own error code, the constraint name, the counter the database wrote for itself either side of a single insert, and the caveats the run could not honestly avoid. Earlier runs are kept beside the current one on purpose, because a document whose credibility rests on showing its own movement may not quietly delete where it moved from.
* [`qa/test-state.json`](qa/test-state.json) — passed, failed, errored and skipped per package, with every skip's reason string, taken twice: once with no database available and once against a live node. Rendered as [`docs/release/test-state.md`](docs/release/test-state.md). That census predates the producer migrations and has not been retaken, so it describes a tree that no longer exists.

## What we are not claiming

Two files hold the full account. [`docs/HONESTY.md`](docs/HONESTY.md) is what is proven, what is authored and what is
not built, with every number carrying the artefact that produced it — and `tests/release/test_honesty_is_checkable.py`
fails the build when a number and its source disagree. [`docs/submission/MUST-NOT-CLAIM.md`](docs/submission/MUST-NOT-CLAIM.md)
prints the flattering sentence we may not say beside the true one, family by family. **The six lines below summarise
those two pages and do not replace them.**

* **The conformance suite has never been demonstrated.** Of 71 declared cases, a first census records 55 that could not run at all, 6 red and 10 that held [src: qa/conformance-census.json#totals]. A modest first result is not a passing suite.
* **The corpus is authored, and the model transcripts are recorded cassettes** — saved request-and-response pairs replayed offline. A green agent test shows that our code handles that recorded exchange; it shows nothing about a live model today.
* **The reference-ledger keys are named `NOT-SECRET` because they are.** They are published on purpose, so that a stranger can verify the offline bundle without asking anyone for a credential.
* **Lint and types are counted, not clean** — frozen ratchets that may fall and may not rise, at 671 `ruff check` findings [src: qa/ruff-ratchet.json#lint.total] and 0 `mypy` errors [src: qa/mypy-ratchet.json#total_errors] over the 660 files mypy actually checks [src: qa/mypy-ratchet.json#source_files_checked]. The lint half of the ruff ratchet is red today.
* **Every timing in the demo is a local timing** — a single-node CockroachDB in Docker on one laptop. Inference runs on Bedrock in Sydney while the database is in Singapore: end-to-end Australian residency is false here, and the hop between the two is unmeasured under load.
* **Nothing has ever run against CockroachDB Cloud in CI.** The cluster exists, and a captured human session is under `evidence/ccloud/`. No automated lane has ever pointed at it.

## Repository, licence, status, corrections

| Path | Contents | Licence |
|---|---|---|
| `spec/` | TRAPPOINT specification, invariants, SQLSTATE contract, wire formats | Apache-2.0 |
| `packages/trappoint-*` | Substrate: SQL templates, gate runtime, offline verifier, recall prefix builder, Model Context Protocol surface, conformance suite | Apache-2.0 |
| `skills/` | CockroachDB Agent Skills, upstream-PR-shaped | Apache-2.0 |
| `scripts/` | The proof, the doctor, the censuses, the ratchets | Apache-2.0 |
| `verticals/mainline/` | The product: domain lattice, gate service, recall agent, custody relay, console | LicenseRef-FSL-1.1-ALv2 |
| `infra/` | OpenTofu modules and environments | LicenseRef-FSL-1.1-ALv2 |
| `evidence/` | Transcripts, captured tool evidence, and a reference ledger whose structure a stranger can check offline | CC-BY-4.0 |
| `qa/` | The counted ratchets and the censuses — every number, and the command that re-derives it | CC-BY-4.0 prose, Apache-2.0 ratchets |
| `docs/` | Architecture decision records, honesty, submission | CC-BY-4.0 |

That layer boundary is also the licence boundary, enforced by `import-linter` in CI: contract 1 of `.importlinter` refuses the build when an Apache-2.0 distribution imports a Functional Source License one, so the substrate stays forkable.

**Status.** Pre-alpha. The Actions tab is red in places, and one of those reds means nothing at all. Read
[`docs/CI-STATE.md`](docs/CI-STATE.md) before drawing a conclusion from a colour: some reds report a true
incompleteness — seven of sixteen custody checks unwritten — and others are jobs that died in the runner's network.

**Licence.** The root [`LICENSE`](LICENSE) is Apache-2.0 — the substrate, which anyone may fork — and GitHub detects it,
so the repository page shows that badge without a judge opening a file. The badge is true and it is not the whole tree:
the tree is multi-licensed by directory, as the table above sets out. [`LICENSES/`](LICENSES) holds every licence text
and [`REUSE.toml`](REUSE.toml) annotates the files that cannot carry a header.
[`docs/submission/LICENSING.md`](docs/submission/LICENSING.md) is the full account, and
[`TRADEMARKS.md`](TRADEMARKS.md) governs the names.

**Corrections.** One row per claim this page used to make and no longer does — collected here rather than deleted.

| This page used to say | What is true | Evidence |
|---|---|---|
| the longest tracked path is 214 characters, and a plain clone first fails at a 45-character destination | those console replay frames were renamed to content-addressed names, so that path no longer exists; the longest tracked path is 141 and the safe clone prefix is 117. That 117 is arithmetic over the tracked paths — the clone probe itself has not been re-run | `qa/judge-dry-run.json#superseded_observations` |
| Bedrock genuinely executes, and nothing else on AWS does | a Lambda Function URL now serves the demo, and the apply that created it has run: eleven requests answered over the internet, `target_is_local_emulator: false`. Which AWS row is exercised is the census's to say and not this page's | `evidence/deploy/aws-live.json`, `evidence/demo/live-beats.json`, `evidence/tool-usage/aws-services.json` |
| the proof needs nothing but the interpreter | it needs one editable install as well. A recorded dry run falsified the claim, and re-running it into a fresh virtual environment falsifies it again, one import earlier | `qa/judge-dry-run.json#runs` |
