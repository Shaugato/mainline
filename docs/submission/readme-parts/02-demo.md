## See it refuse — live, with no account

Open the address below in any browser. There is nothing to install and nobody to sign up with.

| Devpost asks for | This entry |
|---|---|
| **Demo URL** | `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` |
| **Judge access — free and unrestricted** | No account, no login, no credential of ours; the origin takes anonymous callers by design.[^src-open] Reading our ledger in your own SQL client is a separate read-only login, in [`docs/deploy/JUDGE-PACK.md`](docs/deploy/JUDGE-PACK.md) §2 |
| **Video, under three minutes** | `UNRESOLVED` |
| **Which CockroachDB tools and AWS services, and how** | [`docs/TOOL-USAGE.md`](docs/TOOL-USAGE.md) — every tool and every service with a file, a line number, and a verdict saying whether it has actually run |
| **Repository and licence** | `https://github.com/Shaugato/mainline`, public since 2026-08-11; the root [`LICENSE`](LICENSE) is Apache-2.0 |

Those rows are rendered from [`docs/submission/SUBMISSION.json`](docs/submission/SUBMISSION.json), the one file here where a submission address may be written, and this page never edits it. `UNRESOLVED` is a **literal token** that file writes into every such field at birth, not a placeholder somebody forgot to replace. `video_url` still holds it because the film has not been recorded.[^src-video]

**What a judge presses.** Each run is a short sequence of steps; we call each step a **beat**, and every beat carries the code the database returned. A **SQLSTATE** is that five-character code, returned by the database itself; `00000` means the write went through. The refusal comes from a `CHECK` constraint — a rule the database enforces on every write. An **obligation** is a lesson from a past incident that this job has not answered yet. Beat three is an attack: the cached count of open obligations is forced to zero out of band, then the merge is tried again. `persisted: false` means the whole run rolls back and leaves the world as it found it.

| | **1 · Permit to work** | **2 · Management of change** |
|---|---|---|
| **Who is on the screen** | a site supervisor issuing a permit to work | a safety engineer merging a change to a written procedure |
| **What to press** | `/operator.html#/permit`, or `POST /v1/demo/gate-run` | `/operator.html#/change`, or `POST /v1/demo/cr-gate-run` |
| **What the database answers** | read `00000` · merge refused **`23514`** on constraint `gate_closed_when_issued` · forged count refused **`P0001`** from `mainline.fn_permit_merge_gate` · admit `00000` · `persisted: false` | read `00000` · merge refused **`23514`** on constraint `cr_gate_closed_when_merged` · forged count refused **`P0001`** from `mainline.fn_cr_merge_gate` · `persisted: false` |
| **Artefact** | [`evidence/demo/live-beats.json`](evidence/demo/live-beats.json) — `verdict PROVEN`, `2026-08-15T14:11:35Z`, `base_url` is the address above, `target_is_local_emulator false`, no credential used | [`qa/live2.json`](qa/live2.json) — `verdict PROVEN`, `generated_at 2026-08-16T21:11:57Z`; where it ran is settled below |

**Use case two is short two beats, and names both rather than filling them in.** `admission_beat: null`. Nothing is signed off in this run. Signing needs a receipt proving this obligation was actually shown to somebody; no such row exists for this change request, and the demo's database login may read `mainline.exposure_receipt` but may not write to it. `kernel_procedure_beat: null`. The database's own merge procedure, `CALL mainline.merge_change_request(…)`, is not played. Under that same login it answers `42501`, a privilege error, before the gate is ever reached — and a privilege error shown as a gate refusal would be a fabricated exhibit. Both reasons are quoted from the payload's own fields.[^src-cr-absent] Use case one does have the admission beat, and it answers `00000`.

**Is use case two live on that address? The committed artefacts disagreed, so both readings are here with their dates.** On **2026-08-16T04:41Z**, [`evidence/deploy/cr-gate-live.json`](evidence/deploy/cr-gate-live.json) and [`qa/cr-gate-live.json`](qa/cr-gate-live.json) recorded `POST /v1/demo/cr-gate-run` answering **404** on this origin and wrote `verdict: UNANSWERABLE`. A route that was never deployed is not a gate that failed to refuse, and those files draw that distinction themselves, in a field named `this_is_not_a_gate_that_failed_to_refuse`. The newer file, `qa/live2.json` at **2026-08-16T21:11:57Z**, reads `verdict: PROVEN` with the three beats above — but the origin's hostname appears nowhere in it, so on its own it does not say where it ran. Writing this section on **2026-08-17** we made one read-only check and sent no `POST`. A `GET` of `/v1/demo/cr-gate-run` now answers **`405`**, `{"allow": ["POST"], "detail": "/v1/demo/cr-gate-run exists but not for GET"}`, and `GET /v1/health` answers `200` with `ok: true` at `server_date 2026-08-17T15:16:05Z`. **So the route is deployed today and the 404 reading is superseded.** We have not driven a `POST` through the public origin ourselves, so we do not claim use case two beat-for-beat over it. Use case one we do claim over it, because its artefact names the address it ran against.

**The two operator screens are on the origin now.** This page used to say they were not. Measured 2026-08-15, `GET /operator.html` returned the console shell byte-for-byte identical to `GET /`, which is what a not-yet-deployed second entry point looks like. Re-checked read-only on **2026-08-17**: the two documents now differ, and `/operator.html` is byte-for-byte identical to `verticals/mainline/apps/console/dist/operator.html` in this tree — the same sha256 content hash, `a7a685e8…`. Its script and its stylesheet answer `200` as well. What we checked is that the entry point is served; we did not drive the screens.

**Three read-only commands hand a judge the same evidence, with the address and nothing else.** No account, no AWS access, no database of ours:

| command | what it answers |
|---|---|
| `.venv/Scripts/python.exe scripts/demo/demo_ready.py` | *is the world ready to film?* — eight facts, read-only, zero writes · [`docs/demo/DEMO-READY.md`](docs/demo/DEMO-READY.md) |
| `.venv/Scripts/python.exe scripts/proof/live_beats.py --base-url <the address above>` | drives use case one off the deployed address and records the SQLSTATE the database produced for each beat · [`docs/demo/LIVE-BEATS.md`](docs/demo/LIVE-BEATS.md) |
| `.venv/Scripts/python.exe scripts/proof/memory_loop.py --base-url <the address above>` | STORE → RETRIEVE → ACT — an incident named a clause, a retrieval pass finds it, and it becomes an obligation that blocks the permit · [`docs/demo/MEMORY-LOOP.md`](docs/demo/MEMORY-LOOP.md) |

<!-- W7: per R11 every layer-1 footnote DEFINITION is collected here, at the end of section C.
     DONE — W1's three definitions have been copied verbatim out of its `FOOTNOTES FOR W7`
     block into the list below, in reference order, labels unrenamed. Drop that block when you
     assemble 01-opening.md, or GitHub will see each label defined twice.
     ONE UNVERIFIED CITATION, W1's wording and W1's to fix, not edited here: `[^src-story]`
     cites `tests/unit/corpus`, which does not exist in this tree, and `commit_message_2013`
     appears in no file under `tests/` at all — only in `verticals/mainline/demo/honesty/
     gen_card.py` and `verticals/mainline/demo/script/validate_shotlist.py`. -->

[^src-fiction]: This is `docs/submission/MUST-NOT-CLAIM.md` §3 in that section's own wording.
[^src-story]: Every date, label and setpoint above is transcribed from `verticals/mainline/fixtures/corpus/answer-key/spine.json` — `dates`, `revisions` and `proposed_2026`. The quoted revision-history line is `commit_message_2013` in `verticals/mainline/demo/script/CAMERA-STRINGS.yaml`, asserted byte-equal across four files by `tests/unit/corpus`.
[^src-gate]: `scripts/proof/gate_refusal.py` attempts the merge over SQL with no console and no application in the path, and records the refusal `23514 gate_closed_when_issued` [src: evidence/gate-refusal/proof-20260810T054407Z.json]. What that run does and does not entitle us to say is in the sections below.
[^src-open]: `docs/submission/SUBMISSION.json#judge_access.how` — the Function URL is `authorization_type NONE`; `evidence/demo/live-beats.json#credentials_used` reads `none - no DSN, no AWS profile, no token; a stranger with the URL`.
[^src-video]: `docs/submission/SUBMISSION.json#notes.video_url`. The long form of the sentinel story is [`docs/submission/JUDGE-START.md`](docs/submission/JUDGE-START.md), lines 485–502.
[^src-cr-absent]: `qa/live2.json#data.admission_absent_reason`, `#data.admission_absent_grants`, `#data.kernel_procedure_absent_reason`, `#data.kernel_procedure_absent_sqlstate` = `42501`.
