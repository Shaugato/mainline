<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Can `claims`, `boundary` and `submission` say no?

**W8, 2026-08-12, base commit `1d41442` on `master`.** Forty-five CI runs — 3 controls,
36 plants, 3 revert controls, and 3 dispatches superseded before they meant anything (§5) —
every one of them created and read in the same sitting, because GitHub expires this
repository's logs within hours. Every row below carries a run id you can open.

Method, for each distinct promise a lane makes: plant one violation that should break
exactly that promise, push it to a throwaway branch, dispatch the lane on that branch,
read the log, and require the lane to go red **naming the thing that was planted**. A lane
that goes red for a different reason has not been falsified. Then revert and require green
again.

**No plant was ever pushed to `master`.** Every plant lived on a `w8-p-*` branch cut from
`1d41442`; all branches were deleted when the last log was read. The repository's own
`aws-evidence` lane is the reason the control comes first: it reported
`FAMILY red-for-the-wrong-reason` because an unmutated copy of `evidence/` already failed,
which would have made every plant beneath it meaningless.

---

## 0. The control, and a correction for `docs/CI-STATE.md`

`docs/CI-STATE.md` records all three of these lanes as **RED**. That document was measured
at `47f8aa2`. **All three are GREEN at `1d41442`,** and green again on an unmutated
throwaway branch cut from it. W10 should record the correction.

| lane | control at `1d41442` on `master` | control on branch `w8-control` (tree identical) | revert control (plant, then `git revert`) |
|---|---|---|---|
| `claims` | [31596451954](https://github.com/Shaugato/mainline/actions/runs/31596451954) success | [31604450388](https://github.com/Shaugato/mainline/actions/runs/31604450388) **success** | [31607037059](https://github.com/Shaugato/mainline/actions/runs/31607037059) **success** |
| `boundary` | [31596449113](https://github.com/Shaugato/mainline/actions/runs/31596449113) success | [31604455314](https://github.com/Shaugato/mainline/actions/runs/31604455314) **success** | [31607033539](https://github.com/Shaugato/mainline/actions/runs/31607033539) **success** |
| `submission` | [31596458067](https://github.com/Shaugato/mainline/actions/runs/31596458067) success | [31604458802](https://github.com/Shaugato/mainline/actions/runs/31604458802) **success** | [31607040186](https://github.com/Shaugato/mainline/actions/runs/31607040186) **success** |

The revert controls are two-commit branches — the plant, then `git revert` of the plant —
whose tree is byte-identical to `1d41442` (`git diff --quiet 1d41442 HEAD` passes). They
exist so that "green again after revert" is a measurement and not an inference.

**The unmutated control is clean for all three lanes. Every plant below is therefore
trustworthy.**

---

## 1. `boundary` — the lane the brief called highest-risk

The brief said `boundary.yml` carries the fewest red-proof constructs of any green lane and
should get the most effort. It got fourteen experiments. **The finding is the opposite of
the worry: `boundary` is the hardest of the three lanes to fool.** Several plants were
caught by two or three independent jobs at once, and one plant was caught by the Rego
policy re-stating in a different language what the Python checker had already refused.

### 1.1 E1 — no model IAM

**Promise:** the `mainline-kernel` task role carries an unconditional `Deny` on
`bedrock:*`, `bedrock-runtime:*` and `bedrock-agentcore:*`, asserted over the committed
plan.

**Plant** (`w8-p-b-e1`): renamed `bedrock-agentcore:*` to `bedrock-agentcore-TYPO:*` in
`tests/boundary/fixtures/plan.json` — the shape of a real regression, one action quietly
dropping out of a deny list.

**Run [31605107711](https://github.com/Shaugato/mainline/actions/runs/31605107711) —
failure.** Named the plant, four times over:

```
E1 job, "Assert the kernel task role cannot reach Bedrock"
  FAILED test_kernel_boundary_denies_the_model_plane
  FAILED test_each_denied_action_is_covered_unconditionally
  FAILED test_e1_targets_the_kernel_not_every_role
  AssertionError: no unconditional Deny with Resource '*' covers bedrock-agentcore:*;
  a conditional or resource-scoped Deny is a Deny somebody can argue with

E1 job, "Report"                     — also failed (the `|| true` removal is load-bearing)
E2 job, test_rego_agrees_with_python — E1-DENY-MISSING … covering bedrock-agentcore:*
Boundary summary                     — failed
```

**Verdict: FALSIFIED, for the planted reason.** The `Report` step failing is worth naming
separately: `boundary.yml` says `|| true` was removed there on 2026-08-10 so that the CLI's
exit codes mean something. This run is the receipt.

### 1.2 E2 — no model network path

**Promise:** no Bedrock endpoint is reachable from the kernel security group.

**Plant** (`w8-p-b-e2`): in the plan's `configuration` block, repointed
`aws_vpc_security_group_egress_rule.kernel_endpoints_https` from
`aws_security_group.endpoint_kernel` to `aws_security_group.endpoint_cognition` — the group
that fronts `aws_vpc_endpoint.bedrock_runtime_cog`.

**Run [31605111824](https://github.com/Shaugato/mainline/actions/runs/31605111824) —
failure**, four E2 tests plus the unit-test job:

```
[E2/E2-BEDROCK-ENDPOINT-KERNEL-REACHABLE] aws_vpc_endpoint.bedrock_runtime_cog via
  aws_security_group.endpoint_cognition: the kernel security group is permitted to reach
  the security group attached to a bedrock endpoint; the endpoint being in another subnet
  does not help if the packet can get there
[E2/E2-ENDPOINT-SERVES-MISMATCH] aws_vpc_security_group_egress_rule.kernel_endpoints_https
  tcp/443 -> sg:aws_security_group.endpoint_cognition … tagged Serves='cognition'
```

**Verdict: FALSIFIED, for the planted reason.**

### 1.3 E2's second opinion — `conftest test`, unmediated

**Promise:** the Rego policy is a second opinion that does not depend on our test harness.

This step sits **after** the E2 pytest step in the same job, so on every plant above it was
never reached — pytest failed first. To observe it refusing, `w8-p-b-rego` carries the E1
plant **and** disables the E2 pytest step above it.

**Run [31607324400](https://github.com/Shaugato/mainline/actions/runs/31607324400) —
failure** at `Rego, directly — the second opinion, unmediated by our test harness`:

```
E1-DENY-MISSING: boundary aws_iam_policy.kernel_boundary on role aws_iam_role.kernel_task
does not carry an unconditional Deny with Resource "*" covering bedrock-agentcore:*
```

**Verdict: FALSIFIED, for the planted reason — but only after removing the step above it.**
See §4.1: this step is *redundant*, not vacuous.

### 1.4 E3 — no model code path

**Promise:** no kernel-plane package can reach a model SDK.

**Plant** (`w8-p-b-e3`): `import langchain` at the top of
`packages/trappoint-core/src/trappoint_core/gate.py`.

**Run [31605115674](https://github.com/Shaugato/mainline/actions/runs/31605115674) —
failure**, and the reachability analysis named the import path:

```
[E3/E3-IMPORT] packages/trappoint-core/src/trappoint_core/gate.py:31:
  kernel-plane source imports 'langchain'
[E3/E3-IMPORT-REACHABLE] trappoint_core.gate:31: module reachable from the kernel imports
  'langchain'; import path: mainline_gate_svc.service -> trappoint_core.gate
```

**Verdict: FALSIFIED, for the planted reason.**

### 1.5 E3's vacuity guard — "examined nothing" is not "passed"

**Promise:** `boundary.yml` states that removing `|| true` from `Surface the skips` is what
makes exit 3 (VACUOUS — scanned nothing) distinguishable from exit 0.

**Plant** (`w8-p-b-e3vac`): repointed `DEFAULT_KERNEL_ROOTS` at
`packages/w8-no-such-root-*`, so the AST scan has nothing to walk.

**Run [31606962773](https://github.com/Shaugato/mainline/actions/runs/31606962773) —
failure**, at *both* steps, with `examined=0 violations=0 skips=2 exemptions=0`. The scan
that examined nothing failed instead of passing.

**Verdict: FALSIFIED, for the planted reason.**

### 1.6 E4 — no model prompt path (the plan half)

**Promise:** the kernel speaks exactly pgwire plus in-VPC HTTPS.

**Plant** (`w8-p-b-e4`): added `aws_vpc_security_group_egress_rule.kernel_dns_udp`, udp/53
to `10.60.0.0/16`, from the kernel security group, written into all three plan sections.

**Run [31605119482](https://github.com/Shaugato/mainline/actions/runs/31605119482) —
failure**, with four distinct findings, all naming the planted address:

```
E4-PROTOCOL-NOT-TCP        … kernel_dns_udp uses ip_protocol "udp"
E4-PORT-NOT-PERMITTED      … permits kernel egress to 53, outside the closed set {443, 26257}
E4-DESTINATION-NOT-ENUMERATED / E4-DESTINATION-UNRESOLVED … targets a raw IPv4 CIDR
```

**Verdict: FALSIFIED, for the planted reason.**

### 1.7 E4 — the FIS blackhole record

**Promise:** the unrun FIS game-day may not claim it was verified without a committed
attestation.

**Plant** (`w8-p-b-fis`): `verified: false` → `true` in
`mainline_boundary/data/fis-blackhole.yaml`.

**Run [31605123202](https://github.com/Shaugato/mainline/actions/runs/31605123202) —
failure** at `test_fis_record_is_marked_unverified`:

> the FIS blackhole record claims to be verified. GT-16 is unanswered and AWS credentials
> are not valid on the build machine; if this genuinely ran, commit the attestation at
> `evidence/fis/FIS-KERNEL-EGRESS-BLACKHOLE-01.attestation.json` and this test will accept it.

The workflow's own inline `Restate the FIS blackhole status` step was **skipped**, because
the pytest step above it had already failed. `w8-p-b-fisstep` repeats the plant with that
pytest step disabled: **run
[31607357953](https://github.com/Shaugato/mainline/actions/runs/31607357953) — failure**,
`AssertionError: flip this only with a committed attestation`, `verified=True`.

**Verdict: FALSIFIED, for the planted reason, in both places.**

### 1.8 The fleet capability matrix

**Promise:** every agent's declared capabilities satisfy the §8.2/§8.4 matrix.

**Plant** (`w8-p-b-fleet`): gave the first T1 Cognition agent a tool —
`tools: ["mcp:insert_rows"]`.

**Run [31606959141](https://github.com/Shaugato/mainline/actions/runs/31606959141) —
failure**:

```
[FLEET-COGNITION-HOLDS-TOOLS] archivist: a T1 Cognition agent declares tools
['mcp:insert_rows']; the components that read hostile text hold no tools
```

**Verdict: FALSIFIED, for the planted reason — with a caveat that belongs in §4.2:**
`spec/agents/fleet.yaml` **does not exist in this repository**, so the matrix is asserted
against `packages/mainline-boundary/tests/fixtures/fleet_reference.yaml`, and
`test_shipped_fleet_register_exists` **skips on every run** (visible in the control,
31604455314).

### 1.9 CI greps — the A6 sampling ban, on the real tree

**Promise:** no request builder in the fleet sets a sampling parameter.

**Plant** (`w8-p-b-grep`): `temperature=0.0` on the real
`self._client().invoke_model(...)` call in
`packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py`.

**Run [31605529174](https://github.com/Shaugato/mainline/actions/runs/31605529174) —
failure** in two jobs:

```
[GREP/GREP-SAMPLING-PARAM] packages/trappoint-recall/src/trappoint_recall/eval/
bedrock_backend.py:585: a model request builder sets 'temperature' — keyword argument on
self._client.invoke_model(), which is a model transport.
```

**Verdict: FALSIFIED, for the planted reason.**

### 1.10 CI greps — the narrowing that must not become a deletion

**Promise:** the standing step `RED — the narrowed A6 rule still fires on a real request
builder` fails if the 2026-08-10 narrowing has quietly become a deletion.

**Plant** (`w8-p-b-a6`): dropped `"temperature"` from `SAMPLING_KEYS` — exactly the silent
deletion the step exists to catch.

**Run [31605126806](https://github.com/Shaugato/mainline/actions/runs/31605126806) —
failure.** The lane refused, but **not at the step that advertises the property**: the
`test_ci_greps.py` step above it failed first (three assertions), and
`test_greps_still_refuse_a_planted_sampling_parameter` in the unit-test job failed too.

`w8-p-b-a6red` repeats the plant with that pytest step disabled, so the advertised step is
reached. **Run [31605577907](https://github.com/Shaugato/mainline/actions/runs/31605577907)
— failure** at `RED — the narrowed A6 rule still fires on a real request builder`:

```
AssertionError: expected the builder at {7}, got set()
```

**Verdict: the PROPERTY is FALSIFIED twice over. The STEP fires only when it is reached,
and in normal operation it is not** — see §4.1.

### 1.11 `mainline-boundary unit tests` — ruff and mypy

| promise | plant | run | log |
|---|---|---|---|
| `ruff check packages/mainline-boundary tests/boundary` is enforcing | unused `import os` in `mainline_boundary/errors.py` | [31605532101](https://github.com/Shaugato/mainline/actions/runs/31605532101) **failure** | `F401 \`os\` imported but unused → errors.py:14:8`, `Found 1 error.` |
| `mypy --strict` is enforcing | a function annotated `-> str` that returns an `int` | [31605535929](https://github.com/Shaugato/mainline/actions/runs/31605535929) **failure** | `errors.py:42:12: error:` (strict return-type) |

**Verdict: both FALSIFIED, for the planted reason.**

### 1.12 The summary job

**Promise:** `Boundary summary` fails if any enforcement lane did not pass.

Not planted separately: it went red in **every one of the fourteen** boundary plant runs
above and green in both controls. That is a stronger demonstration than a single plant.

**Verdict: FALSIFIED, repeatedly.**

---

## 2. `claims`

Twelve experiments, ten promises, three of the lane's five jobs falsified at every step
they own.

### 2.1 `claim hygiene (red half, then green half)`

| # | promise | plant | run | what the log said |
|---|---|---|---|---|
| 1 | `--self-test` fires on every planted family | deleted the `upstream` sentence from `SELF_TEST_FIXTURE` (`w8-p-c2`) | [31605710899](https://github.com/Shaugato/mainline/actions/runs/31605710899) **failure** | `SELF-TEST FAILED — the scanner did not fire on: MNC-15-upstream-merge` |
| 2 | the committed non-compliant fixture is refused | removed every planted claim from `claim-hygiene-red.md` (`w8-p-c3`) | [31605714385](https://github.com/Shaugato/mainline/actions/runs/31605714385) **failure** | `claim_hygiene passed a file that is deliberately non-compliant. The scanner is broken, or TARGET_GLOBS no longer reaches the rules.` |
| 3 | the published surface carries no forbidden claim | one MNC-01 sentence appended to `README.md` (`w8-p-c1`) | [31605707995](https://github.com/Shaugato/mainline/actions/runs/31605707995) **failure** | `[MNC-01-rls-vs-rogue-admin] README.md:298` |

**All three FALSIFIED, for the planted reason.**

### 2.2 `the red half is red for the reason it claims`

This is the lane's own anti-vacuity job, and it makes four separable promises. All four
were falsified, each by a plant designed to trip that one and nothing else.

| # | promise | plant | run | what the log said |
|---|---|---|---|---|
| 4 | every declared rule is reached by a planted violation | added `MNC-99-w8-unplanted`, pattern `zzq-w8-unmatchable-sentinel`, planted nowhere (`w8-p-c1`) | [31605707995](https://github.com/Shaugato/mainline/actions/runs/31605707995) **failure** | `UNPLANTED FAMILY MNC-99-w8-unplanted` |
| 5 | each fixture sentence is refused **alone** | appended `The weather in Sydney was mild that afternoon.` to the fixture (`w8-p-c2`) | [31605710899](https://github.com/Shaugato/mainline/actions/runs/31605710899) **failure** | `FAMILY sentence-not-refused: this fixture sentence is refused only in company and never on its own, so it plants nothing: The weather in Sydney was mild that afternoon` |
| 6 | the fixture's non-zero exit is caused by its plants | added rule `MNC-98-w8-wrongreason` matching `plants removed`, which is text the job's own stripped control contains — and covered it with a fixture sentence so promise 4 stayed green (`w8-p-c4`) | [31605718203](https://github.com/Shaugato/mainline/actions/runs/31605718203) **failure** | `FAMILY red-for-the-wrong-reason: a copy of the fixture with every planted claim removed STILL exits 1, so the red half's non-zero exit is not caused by its planted violations` |
| 7 | the job never mutates the tracked tree | made `claim_hygiene.main()` append to the tracked `NOTICE` (`w8-p-c5`) | [31606420807](https://github.com/Shaugato/mainline/actions/runs/31606420807) **failure** | `::error::this job mutated the checkout. Every plant belongs in a scratch copy.` followed by ` M NOTICE` |

Promise 6 is the interesting one: the job that exists to detect "red for the wrong reason"
was itself made red for the wrong reason, and it said so in those words.

**All four FALSIFIED, for the planted reason.**

### 2.3 `shot lists, budget and voice-over`

| # | promise | plant | run | what the log said |
|---|---|---|---|---|
| 8 | the shot lists sum inside the 174 s envelope | last shot `dur: 6` → `dur: 26` (`w8-p-c2`) | [31605710899](https://github.com/Shaugato/mainline/actions/runs/31605710899) **failure** | `declares budget.total_s=171 but its shots sum to 191` |
| 9 | the scope-cut ladder cannot reach a `never_cut` shot | ladder step 1 repointed from `s07-beat1-identity-survival` to `s08-beat2-merge-refused` (`w8-p-c10`) | [31606976893](https://github.com/Shaugato/mainline/actions/runs/31606976893) **failure** | `… which is on the never_cut list. The bypass beat is never cut for time` |
| 10 | the 20 % voice-over cut is a real diff and it is current | a cued line added to `VO-DRAFT.md` (`w8-p-c6`) | [31606493821](https://github.com/Shaugato/mainline/actions/runs/31606493821) **failure** | `VO-CUT.diff is stale — run make_cut_diff.py` |

**All three FALSIFIED, for the planted reason.** Promise 10 took two attempts, and the
first attempt is worth recording rather than hiding: run
[31605725000](https://github.com/Shaugato/mainline/actions/runs/31605725000) was **green**
with an uncued sentence added to `VO-DRAFT.md`. That is not a hole. `make_cut_diff.py`
measures only `[m:ss]`-cued spoken lines, so an uncued sentence is genuinely not part of
the voice-over and the checker was right to ignore it. **My plant was wrong, not the lane.**

### 2.4 `honesty card`

| # | promise | plant | run | what the log said |
|---|---|---|---|---|
| 11 | the card regenerates from its inputs and matches what is committed | one HTML comment appended to `card.html` by hand (`w8-p-c1`) | [31605707995](https://github.com/Shaugato/mainline/actions/runs/31605707995) **failure** | `::error::honesty card is stale or its inputs are broken` |
| 12 | every value on the card is traceable to a named path, and there are at least 30 | truncated the ledger to five entries **in the `--json` branch only**, so promise 11 stayed green (`w8-p-c8`) | [31607214104](https://github.com/Shaugato/mainline/actions/runs/31607214104) **failure** | `only 5 traced values on the card; expected the full set` |
| 13 | the generated card itself passes claim hygiene | put an MNC-01 sentence in the card **template** and regenerated `card.html`, so promise 11 stayed green (`w8-p-c9`) | [31606973527](https://github.com/Shaugato/mainline/actions/runs/31606973527) **failure** | `[MNC-01-rls-vs-rogue-admin] … card.html:135`, at the step `The generated card itself passes claim hygiene` |

**All three FALSIFIED, for the planted reason.** Promises 12 and 13 both needed a plant
that left the earlier step in the same job green; without that they would have been masked.

### 2.5 `refusal strings agree with the kernel and the spec`

**Promise:** every on-camera SQLSTATE, exhibit and `RAISE` message is real.

**Plant** (`w8-p-c7`): one `sqlstate: "23514"` → `"42P01"` in `REFUSAL-STRINGS.yaml`.

**Run [31605728051](https://github.com/Shaugato/mainline/actions/runs/31605728051) —
failure**:

```
FAIL  R1-GATE-CLOSED: names SQLSTATE '42P01', which is outside the closed set in
spec/errors.md §1.
```

**Verdict: FALSIFIED, for the planted reason.**

---

## 3. `submission`

Nine experiments; every job and every blocking step falsified.

### 3.1 `the submission gate can say no`

Five sequential steps, five separate branches, because a failure at step *n* hides steps
*n+1…*.

| # | promise | plant | run | what the log said |
|---|---|---|---|---|
| 14 | the gate imports and parses with nothing installed | `import jsonschema` at module top (`w8-p-s1`) | [31606023333](https://github.com/Shaugato/mainline/actions/runs/31606023333) **failure** | `ModuleNotFoundError: No module named 'jsonschema'` at `The gate imports and parses with nothing installed` |
| 15 | `--self-test` fires on every planted failure family | deleted the `github-token` entry from `CREDENTIAL_SHAPES` (`w8-p-s2`) | [31606026336](https://github.com/Shaugato/mainline/actions/runs/31606026336) **failure** | `FAIL credential family github-token fires` |
| 16 | an empty tree is refused, not waved through | `main()` returns `EXIT_READY` unconditionally (`w8-p-s3`) | [31606030157](https://github.com/Shaugato/mainline/actions/runs/31606030157) **failure** | `::error::the gate returned 0 for a directory containing nothing at all` |
| 17 | the path-length ratchet fires on its planted cases | `parse_ls_files_z` made to split on newline as well as NUL (`w8-p-s4`) | [31606033508](https://github.com/Shaugato/mainline/actions/runs/31606033508) **failure** | `FAIL parse_ls_files_z splits on NUL only — ['a/b.txt', 'c/d', 'e.txt']` |
| 18 | the REUSE checker refuses a synthetic uncovered tree | `Report.uncovered` silently drops paths under `stray/` — the exact prefix the self-test's uncovered scenario uses (`w8-p-s5`) | [31606036630](https://github.com/Shaugato/mainline/actions/runs/31606036630) **failure** | `FAILED   the file nobody licensed` |

**All five FALSIFIED, for the planted reason, each at the step that owns it.**

### 3.2 `submission readiness (report-only until D-3)`

| # | promise | plant | run | what the log said |
|---|---|---|---|---|
| 19 | after D-3 a push that leaves a row unresolved **fails** | on `w8-p-s6`, added the branch to the `push` filter and moved `BLOCKING_FROM` to `2026-01-01T00:00:00Z`; the gate itself untouched. Triggered by the push, not by dispatch | [31606160119](https://github.com/Shaugato/mainline/actions/runs/31606160119) **failure**, `event: push` | `mode: BLOCKING (2026-01-01T00:00:00Z or later)` / `gate status: 1` / `::error::the submission gate exited 1 inside the blocking window.` |
| 20 | a table that records no exit code is an error, not a pass | deleted `echo "gate_status=…" >> $GITHUB_OUTPUT` (`w8-p-s7`) | [31606039803](https://github.com/Shaugato/mainline/actions/runs/31606039803) **failure** | `::error::the readiness table recorded no exit code, so nothing is asserted` |

**Both FALSIFIED, for the planted reason.** Promise 19 matters most: it is the only proof
that the D-3 cutover is real machinery and not a comment. The gate's own exit code was `1`
against the real repository — `SUBMISSION.json` still holds `UNRESOLVED` — so the blocking
branch had something genuine to refuse.

### 3.3 `a stranger can clone it, and every file names a licence`

| # | promise | plant | run | what the log said |
|---|---|---|---|---|
| 21 | no tracked path may grow past the Windows clone budget | a 189-character tracked path added through the index (`w8-p-s9`) | [31606043449](https://github.com/Shaugato/mainline/actions/runs/31606043449) **failure** | `longest tracked path (chars): 189 > budget 141 — RISE REFUSED` |
| 22 | every tracked file names a licence whose text is in the tree | `stray/w8-orphan.txt`, no header, no sidecar, no annotation (`w8-p-s10`) | [31606046829](https://github.com/Shaugato/mainline/actions/runs/31606046829) **failure** | `REFUSED [UNCOVERED] 1 tracked file(s) resolve no licence …` and `REFUSED [RATCHET] metric=uncovered_total baseline=0 measured=1 [HARD GATE: baseline is 0]` |

**Both FALSIFIED, for the planted reason.**

---

## 4. What I could NOT falsify, and why

This section is the point of the exercise. Nothing below is a lane that lies; each is a
place where a green tick asserts less than its name suggests, and W10 should record it.

### 4.1 Three advertised red-proof steps are unreachable behind a stronger step

`boundary` carries three steps whose whole purpose is to be seen refusing. **In normal
operation none of them can be observed refusing,** because a `pytest` step earlier in the
same job asserts a strict superset of the same property and fails first. Each was proven
able to refuse only by disabling the step above it on a throwaway branch:

| step | masked by | proven only with the mask removed |
|---|---|---|
| `RED — the narrowed A6 rule still fires on a real request builder` | `tests/boundary/test_ci_greps.py::test_a_planted_temperature_on_a_real_request_builder_is_still_caught`, which plants the same module shape plus two more sites | [31605577907](https://github.com/Shaugato/mainline/actions/runs/31605577907) |
| `Rego, directly — the second opinion, unmediated by our test harness` | `test_rego_agrees_with_python`, which runs the same `conftest` invocation inside pytest | [31607324400](https://github.com/Shaugato/mainline/actions/runs/31607324400) |
| `Restate the FIS blackhole status in the log` (no `if: always()`) | `test_fis_record_is_marked_unverified` | [31607357953](https://github.com/Shaugato/mainline/actions/runs/31607357953) |

**This is redundancy, not vacuity — the properties are all enforced.** But a reader of the
Actions tab who sees `RED — …` green and concludes "that step watched something refuse
today" is wrong: the step ran and passed on a plant of its own making, and the thing that
would actually catch a regression is the step above it. If the intent is a step that is
observed refusing, it needs to run *before* its superset, or with `if: always()`.

### 4.2 `boundary`'s fleet matrix has no shipped subject

`spec/agents/fleet.yaml` **does not exist**, so on every run — including the control,
[31604455314](https://github.com/Shaugato/mainline/actions/runs/31604455314) —
`test_shipped_fleet_register_exists` **skips**, and the matrix is asserted against
`packages/mainline-boundary/tests/fixtures/fleet_reference.yaml`. The skip says so loudly
and the fixture is an honest transcription of §8.4, so this is a *declared* gap rather than
a hidden one — but `boundary.yml`'s `paths:` filter names `spec/agents/fleet.yaml` as a
trigger for a file that has never existed. **Green here means "a reference register
satisfies the matrix", not "the fleet we ship satisfies the matrix".**

### 4.3 Two more legs of `boundary` skip on every run

Both are declared, both are visible in the control log, neither is a pass:

* `E3-SBOM-CURRENT-ABSENT` — no SBOM is committed for the current kernel image, so the
  image-contents leg does not stand. Only the AST scan does.
* E1's two live `iam simulate-principal-policy` tests skip because
  `MAINLINE_BOUNDARY_LIVE_AWS` is deliberately unset. The plan-time assertion is the one
  that runs.

### 4.4 `submission` contains four steps that cannot fail the lane — and the repo bans that

`docs/leads/ci-green-plan2.md` §6.2 and the standing discipline say `continue-on-error` and
`|| true` are banned. `.github/workflows/submission.yml` carries **three**
`continue-on-error: true` steps and **one** `|| true`:

| step | construct | consequence |
|---|---|---|
| `Make the remote-tracking ref the gate compares against` | `continue-on-error: true` | documented as best-effort on forks; the gate reports NOT CHECKED rather than guessing |
| `The table` | `continue-on-error: true` | deliberate — it hands its exit code to the decision step, which §3.2 promise 20 proves is enforcing |
| `The machine record` | `continue-on-error: true` **and** `\|\| true` on the same command | **cannot fail the lane under any input.** Not falsifiable |
| `Report-only until D-3, blocking after` | — | enforcing; proven by promises 19 and 20 |

Only `The machine record` is unfalsifiable-by-construction. The other two are load-bearing
in a way promise 20 makes safe: if `The table` dies without writing `gate_status`, the
decision step errors. **`The machine record` should either drop its suppression or be
merged into the step that already asserts something.**

### 4.5 `claims`' honesty card is checked against a fixture corpus

The `card` job accepts exit `3` — "built from at least one fixture" — as a warning, which
is the right call while `corpus.lock.json` is unfrozen, and `just demo:preflight` refuses
it. Measured on this tree: `gen_card.py` prints `BUILT FROM A FIXTURE — not for camera`.
So promise 11 (`the card regenerates from its inputs`) is falsifiable and was falsified,
but what it asserts today is *"the card matches what the fixture corpus produces"*. The
real-corpus version of that promise cannot be tested until the corpus is frozen. **Not
falsified as a claim about the real corpus.**

### 4.6 `submission`'s report-only window is a declared non-promise

Before `2026-08-15T21:00:00Z`, and on any event that is not a `push`, the readiness job is
**designed** not to fail. There is no promise to falsify in that mode; the only falsifiable
promise is the cutover itself, which is §3.2 promise 19. Worth stating plainly because
between now and D-3 a green `submission` tick does **not** mean the submission is ready —
`SUBMISSION.json` still holds `UNRESOLVED` for `demo_url`, `judge_access` and `video_url`,
and the gate exits `1` saying so, as run 31606160119 shows.

---

## 5. Two plants of mine that were wrong, recorded so nobody re-derives them

Honesty about method, not only about results:

1. **`w8-p-c5`, first attempt** — run
   [31605721913](https://github.com/Shaugato/mainline/actions/runs/31605721913) went red
   with a `SyntaxError` in `claim_hygiene.py`. That is red for the wrong reason: my plant
   was malformed. Re-run clean as 31606420807.
2. **`w8-p-c8`, first attempt** — run
   [31606970086](https://github.com/Shaugato/mainline/actions/runs/31606970086) failed at
   the *previous* step with a `SyntaxError`, again my fault. Re-run clean as 31607214104.
3. **`w8-p-c6`, first attempt** — run 31605725000 was **green**, and correctly so (§2.3).

4. **The three revert controls were dispatched twice.** `git revert -q` is not a valid
   flag, so the first `w8-rev-*` branches carried the plant with no revert on top. Runs
   31606966181, 31606980193 and 31606983436 were dispatched against those branches and
   are **not** evidence of anything — the branches were rebuilt correctly (`git diff
   --quiet 1d41442 HEAD` passing on a two-commit branch) and re-dispatched as
   31607033539 / 31607037059 / 31607040186, which are the runs cited in §0.

A red that is not the red you planted proves nothing. All of these were redone.

---

## 6. Scoreboard

| lane | distinct promises | falsified for the planted reason | not falsifiable, and why |
|---|---|---|---|
| `claims` | 13 | **13** | — (§4.5 narrows what promise 11 asserts) |
| `boundary` | 14 | **14** | 3 advertised steps only when unmasked (§4.1); fleet matrix has no shipped subject (§4.2); 2 legs skip (§4.3) |
| `submission` | 9 | **9** | 1 step cannot fail by construction (§4.4) |

**Thirty-six promises, thirty-six falsified, three controls green, three revert controls
green.** None of these three lanes is a green that cannot fail. The caveats in §4 are about
*what* the green asserts, not about *whether* it can go red.

---

## 7. Hygiene

Every branch used here — `w8-control`, `w8-p-b-{e1,e2,e3,e3vac,e4,fis,fisstep,a6,a6red,grep,fleet,ruff,mypy,rego}`,
`w8-p-c{1..10}`, `w8-p-s{1,2,3,4,5,6,7,9,10}`, `w8-rev-{claims,boundary,submission}` — was
deleted from the remote after its log was read. Plants were authored in a detached
worktree, never in the repository's own working tree, and **nothing planted here has ever
been on `master`**. No workflow, test or source file was modified on `master` by W8; the
only file W8 writes is this one.
