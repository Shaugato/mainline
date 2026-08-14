<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI state — what GitHub actually says

> ## THE MEASURED BOARD — 2026-08-14, public tip `7535670`
>
> **Re-measured live by W6 (ci-green) on 2026-08-14 and confirmed row for row against §1.0.
> Read §1.0 first; everything below §1.A is the preserved record of earlier boards.**
>
> ```
> 20 workflows        8 GREEN        12 RED        0 never-run
>
> decomposed by JOB, which is the unit a lane-level bit hides:
>                     17 green jobs  ·  20 red jobs
>
> 12 RED ├─ 4 RED ON PURPOSE, and turning them green is FORBIDDEN   §1.0.6
>        │    schema · db · custody-chain · demo-health   (+ ci's PL-2 job)
>        └─ 8 red on a defect, of which FIVE are already repaired in
>             this working directory and NONE has a run id
>
> SKIPS, counted and named — never summed into passes:              §1.0.5
>        cluster-tests    1 skip   against a ceiling of 1   (10 → 1; the ceiling
>                                  was never touched, and nine former skips now
>                                  EXECUTE — eight of them fail, visibly)
>        ci (hermetic)    1,104 skips of 10,250 collected = 10.8 %
>
> demo-api suite, --crdb=reuse, from --junitxml:                     §1.0.7
>        at 7535670   570 / 567 passed / 2 failed / 1 skipped / 0 errors
>                     — NOT the circulated 570/569/0/0, which was never
>                       reproducible. NOTHING closed that gap.
>        at d098721   576 / 573 passed / 2 failed / 1 skipped / 0 errors
>                     then 576 / 575 passed / 0 failed / 1 skipped / 0 errors
>                     on the SAME tree an hour later. The 40001 -> 503 defect
>                     is INTERMITTENT, not fixed. Hold to the run that SHOWS
>                     it; a green run of an intermittent defect is not a
>                     green tree.
> ```
>
> **THE LOAD-BEARING CAVEAT: no lane in this repository has ever run at local HEAD.** The
> public tip is `7535670`; `5e6932e`, `f68abb7`, `c9a7253` and `d098721` exist only in this
> working directory, alongside 40 modified and 14 untracked paths. **Every fix this wave made
> — W1's, W2's, W5's and W6's own — is a PLAN on this board, and is counted red.** *A repair
> without a run id is a plan.*

**Measured 2026-08-13 by W5 of the CI-RUNS-THE-CLUSTER wave, at commit `2dc5c86` on
`master`, on a repository that is PUBLIC.** All eighteen workflows were **dispatched in this
sitting**, between `12:20:13Z` and `12:20:52Z`, against the public tip, and every log below
was read **warm**, in the same sitting, with `gh run view <id> --log-failed` or — where a
run-level bundle had not been assembled — `gh api …/actions/jobs/<id>/logs`. Every run id
opens without an account.

**No row on this page is inherited, projected, or measured on a branch.** The revision this
replaces was a board at `53197f5`; that commit is now **nine commits behind local HEAD and
seven behind the public tip**, so its central sentence — *"this board is `53197f5`, the
public tip"* — had become false. Every row here was re-created rather than re-read, and §7
lists the five claims that did not survive the re-measurement.

---

## THE BOARD, STATED PLAINLY

```
18 workflows        11 GREEN        7 RED
                                    ├─ 5 RED ON PURPOSE   schema · db · demo-health ·
                                    │                     custody-chain · db-schema
                                    └─ 2 RED ON A DEFECT  ci · nightly-differential

2 things that ASSERT NOTHING, named here rather than counted as passes:
    ci                   the PL-2 job, on a dispatch — push-gated; it did not run (§1.1)
    nightly-differential the gate/oracle comparison  — the harness dies before the
                                                       comparison is made, on a FOURTH
                                                       commit now (§3.2)

1 thing this board can see that no lane in this repository measures at all:
    the demo API's 187 cluster-backed tests — collected, counted, never executed (§6)
```

> **SUPERSEDED ON ONE LINE, 2026-08-14.** The last line of that block — *"collected,
> counted, never executed"* — **is no longer true**, and the block is kept exactly as it
> was written rather than corrected in place, because it is the `2dc5c86` board and a
> board edited after the fact is not a board. CI run
> [31735341117](https://github.com/Shaugato/mainline/actions/runs/31735341117)
> (`cluster-tests`, push, `eefae1c`, 2026-08-13T19:20:30Z) **executed 518 cluster-backed
> demo-api tests against a real CockroachDB**: `1 failed, 517 passed, 10 skipped in
> 154.21s`, from `528 collected`. §6 is rewritten around that run and carries the
> before/after in full. Nothing else on the `2dc5c86` board is corrected by this note.

**What a judge scanning the Actions tab needs first.** Five of the seven reds are lanes
refusing to certify something this repository has not built yet, and **each one states so in
the first clause of the message GitHub renders**. The other two are defects: `ci` on one
lane-level defect (a stale cassette index) plus five by-design custody rows and two
newly-visible demo-api test defects (§3.1), and `nightly-differential` on its own test harness
(§3.2).

**Two things moved since the previous board and they moved in opposite directions.**
`aws-evidence` was red on a scanner false-positive that switched off an entire anti-vacuity
family; it is now **green, with that family executing on a runner for the first time** (§4.1).
And `schema` grew a **fourth** red job that the previous board recorded as green — a stale
generated document, a defect rather than a design (§2.1.1).

Nothing here was made green by being quieter. Measured across the whole of
`.github/workflows/` at `2dc5c86`:

```
$ git grep -nE "^\s*continue-on-error:" 2dc5c86 -- .github/workflows/   → no matches
$ git grep -n "|| true"                 2dc5c86 -- .github/workflows/   → THREE live lines:
      db.yml:564                     docker rm -f trappoint-crdb || true
      nightly-differential.yml:170   grep -cve … counterexamples.jsonl || true
      nightly-differential.yml:217   grep -cve … counterexamples.jsonl || true
```

**The previous revision of this page said "one live line" and that was wrong when it was
written** — the two `nightly-differential` lines are present at `53197f5` as well. Corrected
in §7.1 rather than quietly fixed here. Every other textual hit in those files is a comment
recording where a suppression used to be.

---

## 0. Method, and the caveat that governs this page

### 0.1 Re-check every number here yourself

```bash
# every workflow's real conclusion on the default branch
gh run list --branch master --limit 200 \
  --json databaseId,workflowName,conclusion,createdAt,event \
  --jq 'group_by(.workflowName)[] | max_by(.createdAt) | "\(.workflowName)|\(.conclusion)|\(.databaseId)"'

# one workflow's conclusion, job by job
gh run view <run-id> --json jobs --jq '.jobs[] | "\(.conclusion) :: \(.name)"'

# the precise cause of a red — the command every claim below rests on
gh run view <run-id> --log-failed

# a job whose run-level bundle is not assembled yet, or whose text --log-failed drops
gh api "repos/Shaugato/mainline/actions/runs/<run-id>/jobs?per_page=100" --jq '.jobs[].id'
gh api "repos/Shaugato/mainline/actions/jobs/<job-id>/logs"
```

Every workflow in this repository declares `workflow_dispatch`, so every row here was
**created** rather than found: `gh workflow run <name>.yml --ref master`, eighteen times, then
the logs read before they went anywhere. **Logs expire, and a recorded board is not
evidence** — that is why the board was re-created rather than re-read. A run id is a claim
that something happened; only a log somebody opened is a claim about *what*.

**One methodological warning, carried forward because it was earned on this page.** An
earlier draft of §2.5 reported that `db-schema`'s `mi-red` had narrowed from five refusals to
two. It had not. The "two" was an artefact of a `tail -25` on that author's own `gh run view`
pipeline, which cut the first three lines off a five-line list. It was caught by re-running
the same grep without the tail against three different runs, which agreed on five. **A quoted
cause is only as good as the command that produced it, and the command belongs in the note.**
This board re-measured that set for a fourth time and it is still five (§2.5).

### 0.2 The caveat that governs this page, stated once

**This board is `2dc5c86` — the public tip — and it is the whole of what a stranger can
check.** Verified after the dispatch, not before:

```
$ git ls-remote --heads origin
2dc5c86d59922837ce2e770561e3b2523543cc71   refs/heads/master
```

At the moment of measurement the working tree also carried work no reader can check. Measured
at the close of the sitting, with the command beside the number, because it grew while the
page was being written:

```
$ git rev-list --count 2dc5c86..HEAD            → 2      (531001c, 073dfea)
$ git status --porcelain -uno    | wc -l        → 32     tracked files modified
$ git status --porcelain | grep -c '^??'        → 31     untracked paths
```

Five other waves are running in parallel in this directory, including the two cluster-lane
workers of this one. **Nothing on this page credits any of it.** Two consequences are large
enough to name:

* **`.github/workflows/cluster-tests.yml` — the first lane in this repository's history that
  points a real CockroachDB at the demo-api suite — exists in the working tree, is untracked,
  is absent from the remote, and has never been dispatched.** It has no run id, so it has no
  row. §6 states what it would prove and what number to check when it lands. **A repair
  without a run id is a plan, and this page counts plans as red.**
* **`ci`'s cassette failure (§3.1) is repaired in local commit `073dfea` and unrepaired on the
  board**, for the same reason.

**This page's section numbers move between revisions and two workflows cite them.**
`.github/workflows/custody-chain.yml:693` cites "`docs/CI-STATE.md` 3.1" for the
seven-unimplemented-checks finding, which was §2.4 on the previous board and is §2.4 here;
`ci.yml:1059` cites this page *by section name* — "the reds that are red on purpose" — which
is the durable form and is why that heading is unchanged. The old §6, §7 and §8 are §7, §8
and §9 here, because §6 is new.

---

## 1. Every workflow, with its real conclusion

### 1.0 RE-MEASURED LIVE, 2026-08-14 — the board as GitHub answers it today

**Measured by D3 of the DOCS-TRUE wave on 2026-08-14, from the public repository, with
§0.1's own first command and nothing else.** Not one conclusion below is inherited from the
`2dc5c86` table that follows it, from the orchestrator's board, or from a commit message.
Where a row's newest run predates the public tip, the row says so in its own cells rather
than in a footnote, because *a green taken at `eefae1c` is not a statement about `7535670`*.

```bash
$ gh run list --branch master --limit 200 \
    --json databaseId,workflowName,conclusion,createdAt,event,headSha \
    --jq 'group_by(.workflowName)[] | max_by(.createdAt)
          | "\(.workflowName)|\(.conclusion)|\(.databaseId)|\(.headSha[0:7])|\(.createdAt)|\(.event)"'

$ git ls-remote --heads origin | grep refs/heads/master
7535670bf5b71808a74e11a1d550051ede8e5203   refs/heads/master
```

**The public tip is `7535670`.** Four further commits — `5e6932e`, `f68abb7`, `c9a7253`,
`d098721` — exist only in this working directory, are absent from the remote, and **have
produced no run id**. §0.2's rule applies to them without exception: *a repair without a run
id is a plan, and this page counts plans as red.* Nothing below credits any of them.

| workflow | conclusion | run | head | created (UTC) | event | at the tip? | § |
|---|---|---|---|---|---|---|---|
| `aws-evidence` | **failure** | [31770005783](https://github.com/Shaugato/mainline/actions/runs/31770005783) | `7535670` | 2026-08-14T04:29:07Z | push | **yes** | §1.0.2 |
| `boundary` | success | [31770242329](https://github.com/Shaugato/mainline/actions/runs/31770242329) | `7535670` | 2026-08-14T04:33:40Z | dispatch | **yes** | §4 |
| `ci` | failure | [31770005791](https://github.com/Shaugato/mainline/actions/runs/31770005791) | `7535670` | 2026-08-14T04:29:07Z | push | **yes** | §1.0.2 |
| `claims` | **failure** | [31735341024](https://github.com/Shaugato/mainline/actions/runs/31735341024) | `eefae1c` | 2026-08-13T19:20:30Z | push | **NO — two commits behind the tip** | §1.0.2 |
| `cloud-verify` | success | [31728207470](https://github.com/Shaugato/mainline/actions/runs/31728207470) | `1a6e10a` | 2026-08-13T17:56:15Z | schedule | **NO — predates `eefae1c`** | §4.3 |
| `cluster-lane-bites` | failure | [31770005766](https://github.com/Shaugato/mainline/actions/runs/31770005766) | `7535670` | 2026-08-14T04:29:07Z | push | **yes** | §1.0.3 |
| `cluster-tests` | failure | [31770005759](https://github.com/Shaugato/mainline/actions/runs/31770005759) | `7535670` | 2026-08-14T04:29:07Z | push | **yes** | §6.8 |
| `console` | success | [31699574592](https://github.com/Shaugato/mainline/actions/runs/31699574592) | `2dc5c86` | 2026-08-13T12:20:40Z | dispatch | **NO — five commits behind** | §4 |
| `custody-chain` | failure | [31770245613](https://github.com/Shaugato/mainline/actions/runs/31770245613) | `7535670` | 2026-08-14T04:33:44Z | dispatch | **yes** | §2.4 |
| `db` | failure | [31770238265](https://github.com/Shaugato/mainline/actions/runs/31770238265) | `7535670` | 2026-08-14T04:33:35Z | dispatch | **yes** | §2.2 |
| `db-schema` | failure | [31770240275](https://github.com/Shaugato/mainline/actions/runs/31770240275) | `7535670` | 2026-08-14T04:33:37Z | dispatch | **yes** | §2.5 |
| `demo-health` | failure | [31785827676](https://github.com/Shaugato/mainline/actions/runs/31785827676) | `7535670` | 2026-08-14T08:54:06Z | schedule | **yes** | §2.3 |
| `judge-pack` | success | [31699580021](https://github.com/Shaugato/mainline/actions/runs/31699580021) | `2dc5c86` | 2026-08-13T12:20:44Z | dispatch | **NO — five commits behind** | §5.2 |
| `mutation-ratchet` | success | [31729443279](https://github.com/Shaugato/mainline/actions/runs/31729443279) | `1a6e10a` | 2026-08-13T18:10:51Z | schedule | **NO** | §4 |
| `nightly-differential` | failure | [31720904696](https://github.com/Shaugato/mainline/actions/runs/31720904696) | `e944407` | 2026-08-13T16:29:08Z | schedule | **NO** | §3.2 |
| `release-proof` | success | [31770243984](https://github.com/Shaugato/mainline/actions/runs/31770243984) | `7535670` | 2026-08-14T04:33:42Z | dispatch | **yes** | §4 |
| `schema` | failure | [31770005764](https://github.com/Shaugato/mainline/actions/runs/31770005764) | `7535670` | 2026-08-14T04:29:07Z | push | **yes** | §2.1 |
| `skills` | success | [31699588327](https://github.com/Shaugato/mainline/actions/runs/31699588327) | `2dc5c86` | 2026-08-13T12:20:50Z | dispatch | **NO — five commits behind** | §4 |
| `submission` | **failure** | [31770005810](https://github.com/Shaugato/mainline/actions/runs/31770005810) | `7535670` | 2026-08-14T04:29:07Z | push | **yes** | §1.0.2 |
| `supply-chain` | success | [31735341020](https://github.com/Shaugato/mainline/actions/runs/31735341020) | `eefae1c` | 2026-08-13T19:20:30Z | push | **NO — two commits behind** | §4 |

**Score at 2026-08-14: 20 workflows · 8 green · 12 red · 0 never-run.** The `2dc5c86` board
below counted eighteen; the two new lanes are `cluster-tests` and `cluster-lane-bites`, which
that board could not count because neither existed on the remote (§0.2, §6.4).

**EIGHT of the twenty greens and reds describe a tree that is no longer the tip**, and twelve
are at it. `console`, `judge-pack` and `skills` are still reporting `2dc5c86`; `cloud-verify`
and `mutation-ratchet` report `1a6e10a`; `claims` and `supply-chain` report `eefae1c`;
`nightly-differential` reports `e944407`. **A green whose head is five commits old is a claim
about a tree nobody is running.** This is §10.4's finding, unrepaired: it has re-formed around
a different set rather than closing. The cure is a dispatch, not a sentence on this page.

> **This sentence said "seven" in its first draft, and the list under it named eight.** The
> error was caught by counting the rows of the table above with a script instead of by eye,
> and it is recorded rather than silently fixed, because the whole argument of this page is
> that a number nobody re-derived is a number nobody checked — and that applies hardest to
> the numbers this page writes about itself. The count is **8 not at the tip, 12 at it**;
> `8 + 12 = 20`, which is the row count of the table and of `ls .github/workflows/*.yml`.

#### 1.0.1 What moved since the `2dc5c86` board, in the direction nobody wanted

Three lanes that the table below records as **green** are now **red**, each at a head this
page can name:

| workflow | `2dc5c86` | now | the failing job, from `gh run view <id> --json jobs` |
|---|---|---|---|
| `aws-evidence` | success (§4.1) | **failure** at `7535670` | all three jobs red |
| `claims` | success | **failure** at `eefae1c` | *claim hygiene (red half, then green half)* — the other four jobs green |
| `submission` | success (§4.2) | **failure** at `7535670` | *a stranger can clone it, and every file names a licence* — the other two jobs green |

**§4.1 and §4.2 are NOT rewritten to match.** They are true of run `31699560021` and run
`31699563085`, they name those runs in their first line, and a page that re-types a dated
reading to agree with today has stopped being a board. §1.0.2 carries the new causes; §7.9
and §7.10 record which sentences did not survive.

#### 1.0.2 The three new reds, each with the cause read out of its own log

**`aws-evidence` [31770005783](https://github.com/Shaugato/mainline/actions/runs/31770005783),
`7535670` — a citation retargeted, and it took the mutation family down with it.** Two
`[CEN-ANCHORS]` errors, quoted from the runner:

```
[CEN-ANCHORS] evidence/tool-usage/aws-services.json#rows.aws_lambda: anchor
infra/modules/demo-api/main.tf:333 quotes 'authorization_type = var.url_authorization_type'
but that line now reads 'handler       = "mainline_demo_api.app.handler"'; the citation has
silently retargeted
[CEN-ANCHORS] … #rows.aws_ssm_parameter_store: anchor infra/modules/demo-api/main.tf:215
quotes 'actions = ["ssm:GetParameter"]' but that line now reads '#'; the citation has
silently retargeted
```

And then the expensive consequence, which §4.1 recorded as **repaired** and is now back:

```
FAMILY red-for-the-wrong-reason: an unmutated copy of evidence/ already fails, so every
plant below would be red for a reason that is not its plant
```

**§5.3 called this family *"the strongest anti-vacuity statement on this board"*. At `7535670`
it asserts nothing again**, for the same structural reason as before and a different proximate
one. The cure is to re-anchor the two citations in `evidence/tool-usage/aws-services.json`
against `infra/modules/demo-api/main.tf` as it now stands — **the tree is authoritative and the
citation is derived** — and it is nobody's in this documents wave: no worker here owns
`evidence/` or `infra/`. Recorded, owned by the AWS-evidence lead, not fixed.

**`claims` [31735341024](https://github.com/Shaugato/mainline/actions/runs/31735341024),
`eefae1c` — three `HYG-sha-literal` reds in `docs/HONESTY.md`, and the red half is healthy.**
The job's red half passed in full (`self-test OK — the scanner goes red on every planted
family`, then `21 claim-hygiene violation(s)` against the deliberate fixture, then
`fixture refused with status 1, as required`). The green half is what failed:

```
scanned 16 file(s) against 21 rules
ABSENT  docs/MECHANISMS.md matched no file — not scanned, and therefore not passed
ABSENT  verticals/mainline/demo/operator/*.md   … not scanned, and therefore not passed
ABSENT  docs/deck/**/*.md    · docs/deck/**/*.html · docs/deck/**/*.txt   … not passed
FAIL  docs/HONESTY.md:724: [HYG-sha-literal] 2dc5c86
FAIL  docs/HONESTY.md:746: [HYG-sha-literal] 2dc5c86
FAIL  docs/HONESTY.md:749: [HYG-sha-literal] 2dc5c86
3 claim-hygiene violation(s)
```

**Note the ABSENT count, because a summary of it has been wrong in this wave.** The checker
prints **five** ABSENT lines, not three: `docs/deck/**/*.{md,html,txt}` is one glob in the
scope list and three globs in the output. The three-versus-five distinction changes nothing
about the finding and everything about whether a reader trusts the person quoting it.
`docs/HONESTY.md` is D2's under this wave's RULING 5 and is not touched here.

**`submission` [31770005810](https://github.com/Shaugato/mainline/actions/runs/31770005810),
`7535670` — one untracked file with no licence, and a hard gate whose baseline is zero.**
Two of three jobs green. The licence job:

```
UNCOVERED — resolve a licence or annotate (1):
    collected.txt
REFUSED [UNCOVERED] 1 tracked file(s) resolve no licence by header, by sidecar or by REUSE.toml
REFUSED [RATCHET] metric=uncovered_by_top_level_directory.<root> baseline=0 measured=1 [HARD GATE: baseline is 0]
REFUSED [RATCHET] metric=uncovered_total baseline=0 measured=1 [HARD GATE: baseline is 0]
```

A stray `collected.txt` at the repository root was committed without a licence. **The lane is
right and its baseline of 0 does not move**; the same run reports one metric *improved*
(`reuse_toml_patterns_matching_nothing` 5 → 1), so the ratchet is working in both directions.
The cure is to delete or licence that file, in the tree, by whoever put it there. **Not by
adding a path to a scope list.** This page has no opinion on which, and no authority to do
either.

#### 1.0.3 `cluster-lane-bites` is red, and every cell of its 2×2 passed

Run [31770005766](https://github.com/Shaugato/mainline/actions/runs/31770005766), `7535670`,
push. Read with `gh run view 31770005766 --json jobs --jq '.jobs[].steps[]'`, which numbers
the steps itself rather than leaving the count to whoever is describing them: **steps 1–18
all passed — including all four cells of the falsifiability 2×2 and the
inventory-cannot-suppress control. Step 19 failed. Step 20 was skipped. Step 21 passed.**

The single failing step is **19, *The frozen-seed guard is GREEN again***, which runs **after**
the plant has been reverted and the tree proved byte-for-byte clean — so it discriminates
nothing about the plant, and its cause is a stale freeze baseline left by commit `898ad55`.

Because the summary step carries no `if: always()`, *The 2×2, as one table* was **skipped**, so
the lane's own table has still never been published by a run. The four cells were read out of
the job log step by step instead. **The full account, with the load-bearing comparison stated
so it cannot be misread, is [`docs/ci/cluster-lane-falsifiability.md`](ci/cluster-lane-falsifiability.md) §Z.**

#### 1.0.4 The Cloud gate-run, recorded as OWED

> **CockroachDB Cloud carries the demo world, and the gate refuses there.** The migration chain
> is `APPLIED` and the seeded world is `SEEDED AND REFUSABLE` against
> `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`, database `mainline_demo`,
> CockroachDB CCL v26.2.5 — the refusal observed on Cloud is `23514`
> `gate_closed_when_issued`, with `nothing_persisted: true`
> [src: `evidence/deploy/cloud-chain.json#outcome`, `evidence/deploy/cloud-seed.json#verdict`,
> `#verification`].
>
> **The four-beat run through the HTTP handler has NOT been recorded against Cloud.** The
> operator reports it in the body of commit `7535670`; that commit's diff carries no such
> artefact, and `evidence/` holds none. **OWED:** re-run `scripts/deploy/…` against Cloud with
> `--out evidence/deploy/cloud-gate-run.json`, and only then may a Cloud `PROVEN` appear on
> this page. Until it exists, the only `PROVEN` this repository holds is
> `evidence/gate-refusal/proof-20260814T032418Z.json`, and it is **local**
> (`cluster.database = w_qr_gate_refusal_proof`).

That paragraph is this wave's RULING 1, reproduced verbatim and worded identically in
`docs/STATE-OF-THE-BUILD.md` and `docs/HONESTY.md`, so that three documents cannot drift into
three different accounts of the same absent artefact. **It belongs on the CI board for a
reason that is specific to this page: no lane produced either Cloud artefact.** Both were made
by hand on a workstation. §4.3's sentence therefore survives untouched — see §4.3.

#### 1.0.5 INDEPENDENTLY RE-MEASURED, 2026-08-14 by W6 (ci-green) — §1.0 confirmed row for row, and the job-level split it did not carry

**§1.0's table was re-created, not re-read.** The same `gh run list` query was run again from
this workstation and returned **the same twenty rows, the same twenty run ids, the same twenty
conclusions and the same twenty heads.** `git ls-remote` still answers `7535670`. Nothing in
§1.0 was corrected, because nothing in it was wrong.

**The four unpushed commits are still unpushed, and the count has not changed.** `5e6932e`,
`f68abb7`, `c9a7253`, `d098721` — the whole of W1–W5's work in this wave — remain absent from
the remote, alongside **40 modified tracked files and 14 untracked paths**. *A repair without a
run id is a plan, and this page counts plans as red.* **Every fix this wave made is therefore
a plan on this board, including W6's own** (§1.0.6, `aws-evidence`).

##### The job-level split, which a lane-level conclusion hides

A workflow's conclusion is one bit. It is the wrong unit for a board, because a lane with
seven green jobs and two red ones renders identically to a lane with two green and seven red.
Read from `gh run view <id> --json jobs`, at `7535670`:

| lane | run | jobs | **green** | **red** | the red jobs, named |
|---|---|---:|---:|---:|---|
| `ci` | 31770005791 | 12 | **7** | **5** | `PL-2` · `pytest --crdb=none` · `REUSE` · `ruff format · the counted lint ratchet` · `CI summary` (aggregate) |
| `custody-chain` | 31770245613 | 7 | **5** | **2** | *a stranger verifies the bundle…* · *fifteen attacks · the matrix is generated from the run* |
| `schema` | 31770005764 | 4 | **0** | **4** | all four — two of them **COLLATERAL**, having never reached their own subject (§2.1) |
| `aws-evidence` | 31770005783 | 3 | **0** | **3** | all three — **one root cause**, and the third says so itself (§1.0.6) |
| `submission` | 31770005810 | 3 | **2** | **1** | *a stranger can clone it, and every file names a licence* |
| `db-schema` | 31770240275 | 3 | **2** | **1** | `mi-red and mi-green` |
| `db` | 31770238265 | 2 | **1** | **1** | *migrate + conform…* |
| `cluster-tests` | 31770005759 | 1 | **0** | **1** | the lane's single job |
| `cluster-lane-bites` | 31770005766 | 1 | **0** | **1** | *…and every cell of its 2×2 passed* (§1.0.3) |
| `demo-health` | 31785827676 | 1 | **0** | **1** | no URL exists (§2.3) |
| `boundary` | 31770242329 | — | **all** | 0 | — |
| `release-proof` | 31770243984 | — | **all** | 0 | — |

**Twelve red lanes decompose into 20 red jobs against 17 green ones.** That is a materially
different picture from "12 of 20 lanes are red", and it is the one a reader needs.

##### The pass/skip split — skips are COUNTED AND NAMED, never summed into passes

**A skip is indistinguishable from a green tick on a dashboard.** These are read out of the
run's own pytest summary line at `7535670`, one commit fresher than §10.15's `eefae1c` census:

| lane | run | failed | **passed** | **skipped** | deselected | collected |
|---|---|---:|---:|---:|---:|---:|
| `cluster-tests` | 31770005759 | **8** | 561 | **1** | 0 | **570** |
| `ci` — hermetic `pytest --crdb=none` | 31770005791 | **7** | 9,124 | **1,104** | 15 | **10,250** |

**`cluster-tests`: 1 skip against a ceiling of 1, and the ceiling was never touched.** This is
the single largest improvement on the board and it must not be undone. The lane now runs
`./.github/actions/build-demo-package` before the suite, so the deployed zip exists in the lane
and the nine tree-reading assertions that used to **skip** now **execute**. Eight of them fail.
**The lane converted nine invisible skips into eight visible defects**, which is a lane working
exactly as designed. `COLLECTED_FLOOR: 445` held against 570 collected.

The one surviving skip is **named**, not summed: `test_gate_run.py::
test_payload_validates_against_the_json_schema` — *"jsonschema is not a workspace dependency;
the structural check above is what runs today and this turns green the day it is added."*

**`ci`'s 1,104 skips are the largest unexamined quantity on this board.** They are `1,104` of
`10,250` — **10.8 % of the suite** — and the lane is `--crdb=none` **on purpose**, so most of
them are cluster tests skipping with a written reason rather than dialling a node the session
declined to obtain. That is correct behaviour and it is still 1,104 assertions this lane does
not make. §6 and §10.17 are about exactly which ones. **They are recorded here as skips, on the
same line as the passes and in a different column, because adding them together is the one
arithmetic this page exists to refuse.**

#### 1.0.6 FIXED versus RED ON PURPOSE at this HEAD — and for each deliberate red, what turns it green and what does NOT

**These are two different kinds of red and a board that does not separate them is useless.**
Per RULING R7 of [`docs/leads/ci-green-final.md`](leads/ci-green-final.md).

##### RED ON PURPOSE — turning these green is FORBIDDEN; sharpening them is required

| lane / job | owner | what turns it green | what does **NOT** |
|---|---|---|---|
| **`schema`** and **`db`** | **KERNEL domain**, [`docs/leads/kernel.md`](leads/kernel.md) 1.1 | a `CREATE TABLE` migration for **`trappoint_ref.clause`** and one for **`trappoint_ref.event`**, at `packages/trappoint-sql/refvertical/sql/<nnnn>_<table>.sql`. Both are referenced by that vertical and created by no file in it; `trappoint migrate` refuses at `0058_blocking_check` with `42P01` | narrowing the matrix · skipping a job · dropping the foreign key. **Each closes the lane by deleting the question** |
| **`ci` / `PL-2`** | the `ci` lane | **nothing available today.** It asks for the URL of a `db` run in which **`CONFORMANCE` itself** went red. `CONFORMANCE` has **never executed**, because `db` stops one step earlier on the same missing producers. The field stays **`UNRECORDED`** | recording **any other** red `db` run. That is the laundering the field exists to prevent — a URL in a field that asks for a different observation |
| **`custody-chain`** | **`verify-crypto`** | the seven missing runners under `packages/trappoint-verify/src/trappoint_verify/checks/` — checks **4, 5, 6, 7, 8, 11, 12** have no runner bound. The lane's own census: **`16 checks │ 9 passed │ 0 failed │ 7 not checked`** | marking a not-checked check as passed. **`0 failed` and `7 not checked` are different findings and the census keeps them apart** |
| **`demo-health`** | the founder / the orchestrator | `docs/submission/SUBMISSION.json` → `demo_url` holding an `https` URL. **No URL exists**; `terraform apply` has not been run and the founder re-authorises before any apply | any workflow edit. The lane can already be proved sound with `gh workflow run demo-health -f url=…` (§2.3) |

**`0 failed │ 7 not checked` deserves its own sentence.** Nine of sixteen custody checks pass
and **none fails** — which reads like a clean bill of health and is not one. Seven checks have
no implementation to run. A dashboard showing `custody-chain` as one red bit loses that
distinction entirely; so would a summary that reported "9 of 9 passing".

##### FIXED IN THE TREE — and every one of them is a PLAN on this board, because none has a run id

| what | who | status |
|---|---|---|
| `cluster-tests` builds the package in-lane; skips **10 → 1** against a ceiling of 1 | landed before `7535670` | **the only fix on this page with a run id.** Measured green in run 31770005759's own numbers |
| the eight `cluster-tests` byte-constant failures — re-recorded from a build **proven to reproduce byte for byte** | W1, `f68abb7` | **unpushed. No run id. Counted red here** |
| the two frozen-seed baselines, re-measured after the four-part negative control | W2, `5e6932e` | **unpushed. No run id. Counted red here** |
| `collected.txt` deleted (clears `submission`'s licence job **and** `ci`'s REUSE job — one file, two lanes); 11 lint regressions cleared; the wave's files formatted | W5, `c9a7253` + `d098721` | **unpushed. No run id. Counted red here** |
| **`aws-evidence`'s two `CEN-ANCHORS` citations re-anchored** — `main.tf:333 → :432` and `:215 → :280`, to the lines that genuinely carry the quoted text, with `infra/modules/demo-api/main.tf` **unedited** | **W6, this wave** | **uncommitted. No run id. Counted red here** — see below |

**W6's own fix is held to the same rule, and this is the row that proves the rule is not
ceremonial.** All three `aws-evidence` jobs were run locally against the repaired file — the
verifier passes `1016 assertions across 40 of 40 declared invariants`, `--self-test` reports
*"the red half is red, and red for the reason it claims"*, and the anti-vacuity **control**
returns `0 failure(s)`, which is the specific thing that was broken (the third job's own
message was *"an unmutated copy of `evidence/` already fails, so every plant below would be
red for a reason that is not its plant"* — one root cause, three red jobs, and the collateral
job says so itself). **A local pass is not a run id.** This row stays red until a push produces
one, exactly like the four above it. Recorded, not credited.

#### 1.0.7 The demo-api suite's baseline was 570 / 567 / 2 / 1 / 0 — NOT the circulated 570 / 569 / 0 / 0 — and nothing "closed the gap", because the gap was never real

**The handover circulated `570 tests / 569 passed / 0 failed / 1 skipped / 0 errors`, in
DEFAULT and RANDOMISED order.** Measured at `7535670` by the CI-BOARD lead with the same
command, `--crdb=reuse`, from `--junitxml`:

| | tests | passed | failed | skipped | errors |
|---|---:|---:|---:|---:|---:|
| handover claimed | 570 | 569 | 0 | 1 | 0 |
| **MEASURED at `7535670`** | **570** | **567** | **2** | **1** | **0** |

**What closed the gap: nothing. The 569 was never reproducible, and saying "a fix closed it"
would be the false green this page exists to refuse.** The two failures are not new work
arriving; they are two pre-existing conditions that a lucky run composition had hidden:

1. **`test_reads.py::test_health_reads_the_deploy_chain_marker_when_the_database_has_one`** —
   `psycopg.errors.InvalidCatalogName: database "w5_deploy_chain_marker…" does not exist`. It
   is **state-ordered**: it needs a database some *earlier* test creates, so it passes or fails
   on **the composition of the run**, not on the code. A suite that reorders — which the
   RANDOMISED order does by design — moves it.
2. **`test_transitions.py`** — a CockroachDB **`40001`
   `TransactionRetryWithProtoRefreshError`** escaping the retry wrapper and being rendered to
   the caller as **`503 database_unreachable`**. **The node id moves; the defect does not.**

**Re-measured again by W6 at local HEAD `d098721`** (four commits past `7535670`, working tree
dirty), `--crdb=reuse`, from `--junitxml`:

```
576 tests · 573 passed · 2 failed · 1 skipped · 0 errors · 269.743s
```

**The suite grew from 570 to 576** — W1–W5 added six tests, all passing. **Both failure shapes
survive**, and the second one moved node id again exactly as predicted: it is now
`test_transitions.py::test_a_run_that_really_persists_is_caught`, `SerializationFailure`,
`restart transaction: TransactionRetryWithProtoRefreshError` — a **different** node id from the
lead's `test_sign_disposition_then_merge_commits`, same shape.

**That is the confirmation, not a coincidence.** Three measurements, three different node ids,
one defect. It is neither a flake nor a deterministic per-node-id failure, and it may not be
filed under `unstable` where no ceiling polices it (RULING R3). **The 40001 → 503 gap is OPEN
at this HEAD.** Owner: the retry wrapper, `verticals/mainline/apps/demo-api/src/
mainline_demo_api/retry.py`. A prior lead measured **40001 six times out of six** by racing two
connections against the LOCAL single node, so *"untestable without Cloud"* is false and may not
be claimed.

##### A FOURTH measurement, in which BOTH failures vanished — and why that is evidence FOR the defect, not against it

W6 re-ran the identical command after making its documentation edits:

```
576 tests · 575 passed · 0 failed · 1 skipped · 0 errors · 144.637s
```

**This is not a fix and must never be quoted as one.** W6 changed **five files: four Markdown
documents and one JSON citation.** No Python, no SQL, no product code, no test — the diff
cannot reach the suite. Between the 573-passing run and the 575-passing run **nothing the suite
executes was different.**

So the honest reading is the opposite of the flattering one: **the same tree produced 573 and
then 575 passes an hour apart**, which is the sharpest available demonstration that

* `test_health_reads_the_deploy_chain_marker_when_the_database_has_one` is **state-ordered**,
  and passes or fails on run composition; and
* the `test_transitions.py` **40001 → 503** is a **real, intermittent product defect** that
  neither reproduces on demand nor stays fixed.

**A green run of an intermittent defect is not a green tree.** Four measurements now exist —
567, 567, 573, 575 passed — and the correct baseline to hold a worker to is the one that
**shows** the defect, not the one that happened to miss it. **`570 / 567 / 2 / 1 / 0` at
`7535670` stands as the recorded baseline, and `576 / 575 / 0 / 1 / 0` is recorded beside it as
the run in which the defect did not fire.** Quoting only the second would recreate the exact
error the circulated `570/569/0/0` made.

The single skip is the same one in every run and is **named**: `test_gate_run.py::
test_payload_validates_against_the_json_schema`, *"jsonschema is not a workspace dependency"*.

---

### 1.A The `2dc5c86` board — *kept as the BEFORE, and not corrected in place*

The table below was measured on 2026-08-13 against the then-public tip. **Its conclusions are
true of the run ids in its own cells and of nothing else**, and it is kept whole rather than
edited because a board edited after the fact is not a board — the same rule §6.0 applies to
its own superseded heading. Where a row moved, §1.0.1 says so and §7 records the sentence.

| workflow | conclusion | run | kind | § |
|---|---|---|---|---|
| `aws-evidence` | success | [31699560021](https://github.com/Shaugato/mainline/actions/runs/31699560021) | — **was red; the mutation family now executes** | §4.1 |
| `boundary` | success | [31699565343](https://github.com/Shaugato/mainline/actions/runs/31699565343) | — | §4 |
| `claims` | success | [31699568088](https://github.com/Shaugato/mainline/actions/runs/31699568088) | — | §4 |
| `cloud-verify` | success | [31699571546](https://github.com/Shaugato/mainline/actions/runs/31699571546) | — smaller claim than its name | §4.3 |
| `console` | success | [31699574592](https://github.com/Shaugato/mainline/actions/runs/31699574592) | — | §4 |
| `judge-pack` | success | [31699580021](https://github.com/Shaugato/mainline/actions/runs/31699580021) | — **five jobs; the envelope teeth still bite** | §5.2 |
| `mutation-ratchet` | success | [31699583092](https://github.com/Shaugato/mainline/actions/runs/31699583092) | — | §4 |
| `release-proof` | success | [31699585931](https://github.com/Shaugato/mainline/actions/runs/31699585931) | — | §4 |
| `skills` | success | [31699588327](https://github.com/Shaugato/mainline/actions/runs/31699588327) | — | §4 |
| `submission` | success | [31699563085](https://github.com/Shaugato/mainline/actions/runs/31699563085) | — | §4.2 |
| `supply-chain` | success | [31699590999](https://github.com/Shaugato/mainline/actions/runs/31699590999) | — | §4 |
| `schema` | failure | [31699557229](https://github.com/Shaugato/mainline/actions/runs/31699557229) | **RED ON PURPOSE — and one job that is not** | §2.1 |
| `db` | failure | [31699554580](https://github.com/Shaugato/mainline/actions/runs/31699554580) | **RED ON PURPOSE** — same cause | §2.2 |
| `demo-health` | failure | [31699577433](https://github.com/Shaugato/mainline/actions/runs/31699577433) | **RED ON PURPOSE** | §2.3 |
| `custody-chain` | failure | [31699551218](https://github.com/Shaugato/mainline/actions/runs/31699551218) | **RED ON PURPOSE** — two causes | §2.4 |
| `db-schema` | failure | [31699548569](https://github.com/Shaugato/mainline/actions/runs/31699548569) | **RED ON PURPOSE** — five promotions owed | §2.5 |
| `ci` | failure | [31699545661](https://github.com/Shaugato/mainline/actions/runs/31699545661) | defect — 10 of 12 jobs green | §3.1 |
| `nightly-differential` | failure | [31699542934](https://github.com/Shaugato/mainline/actions/runs/31699542934) | defect — **asserts nothing**, fourth commit running | §3.2 |

**Score: 11 green, 7 red, 0 never-run.** (A nineteenth entry, `Dependabot Updates`, is
GitHub's own managed workflow, not this repository's lane.)

> **That score is `2dc5c86`'s and is superseded by §1.0, which reads 20 workflows · 8 green ·
> 12 red on 2026-08-14.** The digits above are not re-typed: they were correct when measured,
> the run ids beside them still open, and re-typing them would destroy the only evidence that
> the board moved.

**One row on this page was written green before it was observed, and then corrected.**
`nightly-differential` was still `in_progress` when the rest of the board was drafted; its two
differential jobs run for thirty minutes each. The draft carried it as a success — a
prediction, which is exactly what this page's method forbids — and it was replaced when the
run concluded `failure` at `12:51:39Z`. Recorded here rather than silently fixed, because the
only reason the error did not survive is that the conclusion was waited for.

### 1.1 One red cannot be produced by a dispatch, and this page says which

`ci`'s **PL-2** job is gated on `github.event_name == 'push' && github.ref ==
'refs/heads/master'`. On dispatched run `31699545661` it reported **success**, because on any
other event it emits a `::warning` instead of failing. **That green asserts nothing.** The
by-design red it exists to raise is recorded in §8, and this page will not launder a dispatch
green into a claim that PL-2 held.

---

## 2. The five reds that are red on purpose

Every lane here **must stay red**, and every one states in the first clause of the annotation
GitHub renders that it is deliberate, plus the artefact that would end it. One job inside
`schema` is the exception, and §2.1.1 separates it out rather than letting it shelter under
the lane's by-design heading.

### 2.1 `schema` — two objects the reference vertical references and nothing creates

Run [31699557229](https://github.com/Shaugato/mainline/actions/runs/31699557229). **All four
jobs red**, on **two** causes. Three of them share one, quoted verbatim from the log:

```
##[error]RED BY DESIGN, NOT A CI DEFECT: 2 object(s) referenced by
packages/trappoint-sql/refvertical/sql and created by no file in it: trappoint_ref.clause,
trappoint_ref.event. This lane refuses to be closed by narrowing the matrix, skipping a job
or dropping the foreign key -- only a CREATE TABLE migration for each object named above
turns it green, because two bindings that both render is the substrate claim and one
binding is a template engine with an audience of one.
```

Each missing producer names its owner and its already-existing twin:

```
##[error]MISSING PRODUCER: trappoint_ref.clause -- consumed by 0066_disposition (FOREIGN KEY
target) -- expected: a CREATE TABLE migration in packages/trappoint-sql/refvertical/sql/ --
MAINLINE twin that already exists: verticals/mainline/db/migrations/0028_clause.sql --
owner: KERNEL domain, docs/leads/kernel.md 1.1
##[error]MISSING PRODUCER: trappoint_ref.event  -- consumed by 0058_blocking_check … --
MAINLINE twin that already exists: verticals/mainline/db/migrations/0033_event.sql
```

**What turns it green:** a `CREATE TABLE` migration for `trappoint_ref.event` and one for
`trappoint_ref.clause`, at `packages/trappoint-sql/refvertical/sql/<nnnn>_<table>.sql`.
Owner: KERNEL domain, `docs/leads/kernel.md` 1.1.

**This is the model red of the repository, because it refuses the cheap fixes.** Narrowing
the matrix, skipping the job or dropping the foreign key would each close the lane by
deleting the question, and the message says so in one sentence so that nobody tries.

The census line the job prints before it refuses, read from job `94445138416` on this run —
quoted from the runner rather than re-derived here, because a number this page did not
personally re-run is a number it must attribute:

```
reference vertical: 22 tables created, 12 referenced, 2 with no producer
```

Two of the four red jobs — *unwelding matrix* and *the self-attesting gate* — are
**COLLATERAL**: they never reached their own subjects. Their annotations carry the word
**UNPROVEN**, because "did not run" and "ran and failed" are different findings:

```
##[error]RED BY DESIGN, NOT A CI DEFECT. 2 object(s) are referenced by … CockroachDB
refused at 0058_blocking_check on trappoint_ref.event, the first of them. … This job did
NOT fail on its own subject -- the unwelding matrix did not execute, so it is UNPROVEN by
this run rather than failing. WHAT TURNS IT GREEN: a CREATE TABLE migration for each object
named above. WHAT DOES NOT: narrowing the matrix, skipping this job, or dropping the
foreign key -- each of those closes the lane by deleting the question.
```

#### 2.1.1 The fourth job is NOT by design, and the previous board had it green

*anomaly coverage and manifest totality (hermetic)* was green on run `31662337715` and is red
here, on a cause that has nothing to do with the missing producers:

```
##[error]ANOMALY_COVERAGE.md is stale. Regenerate and commit it.
diff --git a/packages/trappoint-conformance/ANOMALY_COVERAGE.md …
-# `ANOMALY_COVERAGE.md` — A1-A14, and the case that covers each
+# `ANOMALY_COVERAGE.md` — A1-A14, and the case that covers each
```

**The two sides of that diff are the same characters.** The job regenerates the document with
`tests/test_anomaly_coverage.py` and then asserts `git diff --quiet` on it, so a byte-level
difference in line endings shows as every line changed and no line different. Diagnosed on
this workstation:

```
$ git show HEAD:packages/trappoint-conformance/ANOMALY_COVERAGE.md   → CRLF 42, bare LF 0
$ ls .gitattributes                                                  → No such file
```

**The committed blob is CRLF; the generator on a Linux runner writes LF; the repository has no
root `.gitattributes` to reconcile them.** This is the same defect class as the `ruff format`
line-ending artefact in §3.1 and the CRLF commit that `802e7b7` had to undo — the third
occurrence. **What turns it green:** the file committed with the line endings its generator
produces, or a root `.gitattributes` that normalises them. **What does not:** relaxing the
`git diff --quiet`, which is the only thing making the generated document a checked claim
rather than a decoration. Owner: the conformance package.

### 2.2 `db` — the same finding, a second lane

Run [31699554580](https://github.com/Shaugato/mainline/actions/runs/31699554580). Census job
green, migrate job red on the identical cause, quoted from the log:

```
one version constant, and it lives in compose.yaml ............ success
migrate + conform, on a node pinned to Cloud's gc.ttlseconds ... failure
    trappoint migrate: REFUSED: 0058_blocking_check: [42P01]
    relation "trappoint_ref.event" does not exist
```

**`db`'s older recorded cause remains paid, and the margin that paid it has been spent.** The
image census, read from job `94445127812` on this run:

```
floating tag: 0 (ceiling 0)
restated literal: 19 (ceiling 19)
```

The `restated literal rose from 19 to 20` red that earlier boards carried is still gone, and
`floating tag` is at zero against a ceiling of zero. **But the previous board recorded
`restated literal: 18 (ceiling 19)` with the lane's own `::notice` asking for the ceiling to
come down to 18, and that slack is gone**: a restated image literal came back between
`53197f5` and `2dc5c86`, the census is now exactly at its ceiling, and the job prints no
notice because there is nothing left to lower. **One more restated `cockroachdb/cockroach:…`
literal in any file this census scans turns `db`'s green job red.** Corrected in §7.2.

This page records the ceiling rather than moving it: lowering a ceiling changes an assertion,
and changing an assertion is not a documentation task.

**What turns `db` green:** the two producers of §2.1, after which `db`'s `CONFORMANCE` step
executes for the first time in this repository's history.

**What `db` still does not do:** say *red by design* in its own message. That was true on the
previous board and is true here; a reader of the Actions tab still has to come to this page
for `db`. Named, not hidden.

### 2.3 `demo-health` — no demo is deployed, and the red names its cure

Run [31699577433](https://github.com/Shaugato/mainline/actions/runs/31699577433), one job,
verbatim:

```
##[error]no demo URL is published; this lane is red because the demo is not deployed, not
because it is broken.
```

The annotation continues, on the run summary page as well as in the log, with **the
assertions it did not get to make** — `GET /` returning an HTML document, `GET /v1/health`
returning `ok:true` with a `server_date` inside the freshness window, and the four beats of
`POST /v1/demo/gate-run` with their SQLSTATEs (`00000`; `23514 gate_closed_when_issued`;
`P0001 mainline.fn_permit_merge_gate`; `00000`), plus `persisted:false` and the server's own
`PROVEN`. **A reader therefore learns the size of the hole, not only its name.**

**What turns it green:** `docs/submission/SUBMISSION.json` → `demo_url` holding an `https`
URL. No repository variable, no secret, no workflow edit. `terraform apply` has not been run;
the plan is committed and the founder re-authorises before any apply.

**And the lane can be proved sound today, with no deployment at all** — the red prints the
command itself:

```
gh workflow run demo-health -f url=https://<a host that answers>
```

The dispatch input outranks the file, so such a run exercises every assertion above and never
reaches the failing step. **An intentional red nobody can falsify is indistinguishable from a
lane that has quietly stopped working**, which is why that command is in the error rather than
in a comment.

### 2.4 `custody-chain` — 7 of 16 checks have no implementation, and three K2 artefacts do not exist

Run [31699551218](https://github.com/Shaugato/mainline/actions/runs/31699551218). **Five jobs
green, two red, two independent by-design causes** — unchanged from the previous board and
re-read here rather than carried forward.

**Cause 1 — 7/16.** Verbatim:

```
##[error]Checks 4, 5, 6, 7, 8, 11, 12 did not run. Owner: verify-crypto. This lane is
RED ON PURPOSE and stays red until the modules named in the annotations below exist.
Nothing is skipped, excused or ratcheted to conceal it.
```

Each of the seven carries its own annotation naming the module, the test, and what it *would*
have proved — log signature, RFC-3161 bracket, beacon, witness quorum, S3 object-lock, gate
self-attestation, WebAuthn re-verification. For example:

```
##[error]NEEDS packages/trappoint-verify/src/trappoint_verify/checks/witness.py … and
packages/trappoint-verify/tests/crypto/test_witness_quorum.py. Registry says status=deferred,
target=implemented_but_not_adverse, owner=verify-crypto. It would have proved: At least q
cosignatures over the SAME (size, root), across distinct trust domains, at least one adverse.
```

**What turns it green:** those seven runners under
`packages/trappoint-verify/src/trappoint_verify/checks/`.

**Cause 2 — the K2 exit criteria**, `3 failed, 10 passed, 2 skipped`:

```
K2.4 NOT MET — MISSING ARTEFACT: evidence/k2-checkpoint-cadence.json
K2.5 NOT MET — MISSING ENTRY: spec/CHANGELOG.md carries no line naming
               `wire/checkpoint.md` at v1.0.
K2.6 NOT MET — MISSING ARTEFACT: evidence/k2-migration-attestation.json
```

Each names its owner and its cure — for K2.4, *"a file at that path carrying keys 'samples'
(>= 30), 'p50_seconds', 'p95_seconds', 'max_seconds' and 'measured_at', written by observing
consecutive checkpoint publications against a running sequencer"* — and each says why it is
not faked: *"the ~60 s window of undetectable mutation is the single honest number the whole
custody argument turns on. A number this test invented would be a number nobody measured."*

**The canonicaliser drift earlier boards recorded here is still gone**, and its absence is
measured: check 10 `PASS`, and on this workstation
`python scripts/custody/check_vendored_canon.py` → `canonicaliser registry: 3 passed, 0
failed, 0 skipped`.

### 2.5 `db-schema` — the catalogue is green; `mi-red` refuses five promotions

Run [31699548569](https://github.com/Shaugato/mainline/actions/runs/31699548569). Two of three
jobs green — *the catalogue is committed, current and well-formed* and *the version comparison
bites* — and `mi-red` red:

```
5 HELD (the red law refuses on these — see REFUSED below) · 2 RED (an owning test fails; the
law holds) · 14 UNWITNESSED (no owning test resolves at all).
REFUSED: MI06 is pending but its tests pass — promote it in mi_catalogue.yaml
REFUSED: MI10 …   REFUSED: MI21 …   REFUSED: MI22 …   REFUSED: MI27 …
```

with, for MI10 specifically:

```
MISSING:  a FAILING owning test — all 2 of its owning tests pass, so not one of them has
been observed to make 23503 happen.
```

This is a **red-before-green integrity law doing its job**: an invariant marked `pending`
whose owning tests all pass is either already enforced (and the catalogue is stale) or its
tests witness nothing. The lane refuses to guess, and states its own falsifiability:

> *"promote only if one of the tests above makes an object above REFUSE. A test that would
> still pass with that object dropped witnesses nothing, and an `enforced` row recorded on it
> is the false green PL-2 exists to forbid."*

**What turns it green:** for each of MI06, MI10, MI21, MI22 and MI27, either a promotion in
`mi_catalogue.yaml` backed by a test observed to make the enforcing object refuse, or an
owning test that actually fails.

**This set has not moved across four runs on four commits** — 31657335542 at `06f41f8`,
31660091618 at `9221d0c`, 31662330242 at `53197f5`, and 31699548569 at `2dc5c86`. It is the
same five names each time.

### 2.6 `ci`'s PL-2 job — by design, and it only fires on a push

PL-2 asks for the URL of a `db` run in which the **`CONFORMANCE` step itself** went red. No
such run exists, because `CONFORMANCE` has never executed (§2.2). Recording any other red `db`
run would put a URL in a field that asks for a different observation. The annotation carries
all of that where a reader sees it; it is quoted in full in §8, from a push run at this
board's own commit.

---

## 3. The two reds that are defects

### 3.1 `ci` — 10 of 12 jobs green; one stale cassette index, five by-design custody rows, two newly-visible demo-api defects

Run [31699545661](https://github.com/Shaugato/mainline/actions/runs/31699545661).

| job | verdict |
|---|---|
| every checker this lane invokes exists | success |
| **actionlint** | **success** — all eighteen workflows, `shellcheck` over every `run:` |
| PL-2 — the red run is recorded | success — **push-gated, asserts nothing here** (§1.1) |
| import-linter contracts · and no package outside them | success |
| REUSE — every file names its licence | success |
| the lockfile is authoritative · workspace membership | success |
| **mypy · and the target list is complete** | **success** |
| **ruff format · the counted lint ratchet** | **success** |
| the sequence ban, repository-wide | success |
| RED BY DESIGN, and it must stay red | success — every declared red is still red |
| pytest --crdb=none | **failure** |
| CI summary | **failure** (aggregate) |

**`pytest --crdb=none`**, read out of the job's own log:

```
8 failed, 8629 passed, 1003 skipped, 13 deselected, 2 warnings in 339.20s (0:05:39)
##[notice]13 test(s) deselected here and run by the 'red-by-design' job
```

`8 + 8629 + 1003 + 13 = 9653`. The eight, named and classified:

| test | cause | classification |
|---|---|---|
| `test_k2_1_tamper_is_caught_by_a_consistency_proof` | the attack matrix does not record A1 as detected by check 3 | by design (§2.4) |
| `test_k2_2_closure_rewrite_is_caught_by_check_14` | the matrix does not record A10 as detected by check 14 | by design (§2.4) |
| `test_k2_4_checkpoint_cadence_measured_and_deadman_defined` | K2.4 missing artefact | by design (§2.4) |
| `test_k2_5_checkpoint_wire_format_tagged_v1_0_with_changelog_entry` | K2.5 missing entry | by design (§2.4) |
| `test_k2_6_migration_attestation_chained_with_a_stable_fingerprint` | K2.6 missing artefact | by design (§2.4) |
| `test_every_recorded_body_hashes_to_its_index_row` | `assert '11d32dd3a13f…' == '136eec3462c2…'` | **defect** |
| `test_no_web_framework_or_aws_sdk_is_imported` | `the deployment package pulled in ['boto3', 'botocore', 'httpx', 'pydantic']` | **defect, in the test** |
| `test_the_one_unmeasured_response_is_bounded_by_construction` | `OSError: [Errno 36] File name too long` | **defect, in the test** |

**Three things about that table are new since the previous board and each is worth a
sentence.**

**The K2 rows went from three to five.** K2.1 and K2.2 assert that the recorded attack matrix
names a specific check as the detector. They are the same by-design family as K2.4-K2.6 and
they are red for the same reason: the artefact that would satisfy them does not exist yet.

**The cassette defect is unchanged on the board and repaired off it.**
`packages/mainline-agentkit/tests/test_live_cassettes.py` asserts that every recorded cassette
body hashes to its index row, and one does not. A recorded body that disagrees with its own
index is either an edited transcript or a stale index. **It must not be closed by rewriting
the index to match the body** — that makes the check tautological and destroys the only thing
it was measuring. Local commit `073dfea` carries a repair. **`073dfea` is not on the public
tip, so this board counts the defect as live** (§0.2).

**The last two rows exist because the demo-api suite is now collected.** Until 2026-08-13
`testpaths` did not reach `verticals/mainline/apps/demo-api/tests`; the `839 skipped` of the
previous board is `1003 skipped` here, and the difference is that suite arriving. Both
failures are defects in the tests rather than in the product — a process-wide `sys.modules`
read that only a shared session exposes, and a long-filename probe that only a Linux runner
rejects — and both belong to the demo-api domain. **They are the first evidence in this
repository's history that a case under that directory can turn a CI lane red.** What they are
*not* is the thing §6 is about.

**`ruff` and `mypy` are green, for the second board running.** Confirmed independently on this
workstation against a fresh LF export (`git archive HEAD | tar -x`), which is byte-for-byte
what the runner checks out:

```
$ ruff format --check .        # ruff 0.16.1, on an LF export
1443 files already formatted
```

**The same sweep on the Windows working tree reports hundreds of files.** That number is a
line-ending artefact — this checkout has no root `.gitattributes`, which is also the cause of
§2.1.1 — and appears here only so that nobody takes it for a fact about the code. **There must
be no `ruff format .` sweep on this tree.**

### 3.2 `nightly-differential` — red on its own harness, so it says nothing about the gate

Run [31699542934](https://github.com/Shaugato/mainline/actions/runs/31699542934). One job
green (*64 parallel merges of one subject*), **both differential jobs red**, on the same pair
of harness errors the previous three boards recorded:

```
E  psycopg.OperationalError: sending prepared query failed: another command is already in
   progress
   .venv/lib/python3.13/site-packages/psycopg/cursor.py:117: OperationalError
E  hypothesis.errors.FlakyStrategyDefinition: Inconsistent data generation! Data generation
   behaved differently between test cases. Is your data generation depending on external
   state?
FAILED packages/trappoint-model/tests/test_read_committed.py::
       test_gate_agrees_with_the_oracle_at_read_committed      (1 failed, 1 passed in 1813.37s)
FAILED packages/trappoint-model/tests/test_differential.py::
       test_gate_agrees_with_the_oracle_at_serializable        (1 failed in 1803.25s)
```

**This is the worst red on the board and the count does not show it.** The lane's subject is
*the database gate agrees with the reference oracle, at two isolation levels*. It never got
there: a Hypothesis strategy is reading external state, and a psycopg cursor is being reused
while a command is in flight. **The comparison between gate and oracle was not made, at either
isolation level.**

**Not a flake — a defect that reproduces, now across FOUR commits.** The identical pair of
errors was recorded at `06f41f8` (run 31657318276), `9221d0c` (run 31660134173), `53197f5`
(run 31662319746) and here at `2dc5c86`. Each of the four runs spent about thirty-one minutes
reaching the same place.

**What turns it green:** a fix at the cause — a strategy that does not depend on external
state, one cursor per in-flight command. **What must not:** a retry, an `xfail`, or a narrowed
example budget. Each would leave the gate/oracle comparison exactly as unmeasured as it is
now, while painting the lane green.

---

## 4. The eleven greens, and what each green does and does not mean

`aws-evidence`, `boundary`, `claims`, `cloud-verify`, `console`, `judge-pack`,
`mutation-ratchet`, `release-proof`, `skills`, `submission`, `supply-chain`.

A green is worth exactly what its lane can refuse; §5 audits that. Three greens need a
sentence here first.

### 4.1 `aws-evidence` is green, the false positive is gone, and a whole anti-vacuity family came back on

Run [31699560021](https://github.com/Shaugato/mainline/actions/runs/31699560021), three jobs
green: *the red half is red for the reason it claims*, *no third-party import, no credential,
no ~/.aws*, *evidence/aws is internally coherent and leaks nothing*.

The previous board recorded this lane red on one literal — `322122547200`, which is Lambda's
300 GiB code-storage quota in bytes and was being read as an AWS account id by
`SEC-ACCOUNT-ID` — and recorded the **expensive consequence**: the third job aborted with
*"FAMILY red-for-the-wrong-reason: an unmutated copy of evidence/ already fails"*, so **not one
plant was being tested**. A repair existed uncommitted and the board would not credit it.

It is committed and it works. From job `94445145344`, read warm:

```
control (unmutated copy): 0 failure(s)
40 declared invariants · 24 reached by a plant · 16 named exemptions
26 plants · 24 distinct expected ids · 15 fire their own invariant and nothing else ·
   11 additionally fire declared siblings
every plant fired exactly the invariants it declares
```

**That is the strongest anti-vacuity statement on this board**, and note what it is: not "the
plants fired" but "every plant fired *exactly* the set it declares", with a blast-radius
declaration keyed per plant and a duplicate-label guard. A plant that got blunter — firing
more than it declares — fails the job just as a plant that went silent does.

**Two limits survive and are not swept up in the good news.** Sixteen of the forty invariants
have **no plant at all** and are carried on a written exemption list; a named exemption is
still an unexercised check. And the blast-radius declaration is a *measurement* of what each
plant fires today, not a derivation of what it should fire.

### 4.2 `submission` is green, and the last suppression pair in the repository was in it

Run [31699563085](https://github.com/Shaugato/mainline/actions/runs/31699563085), three jobs
green: *the submission gate can say no*, *submission readiness (report-only until D-3)*, *a
stranger can clone it, and every file names a licence*.

The step called *The machine record* used to carry `continue-on-error: true` **and** a
`|| true` on the command inside it — two independent reasons it could not fail, which means it
asserted nothing about the machine record. **Both are gone.** The repository-wide measurement
is at the top of this page, and it corrects the previous board's count (§7.1).

### 4.3 `cloud-verify` is green, and it has never touched CockroachDB Cloud in CI

Run [31699571546](https://github.com/Shaugato/mainline/actions/runs/31699571546): success.
The name invites a reading the lane does not support. **Nothing in this repository has ever run
against CockroachDB Cloud in CI.** The lane verifies the artefacts and configuration a Cloud
run would need, against the local pinned node. A useful claim, and a smaller one than the name
suggests.

#### 4.3.1 RE-VERIFIED 2026-08-14, because two Cloud artefacts now exist and the sentence above still holds

This is the sentence on this page most likely to have been overtaken by the last two days'
work, so D3 re-measured it rather than carrying it forward. **It survives, and the reason it
survives is exact: the two Cloud artefacts were produced by hand, and a hand-run is not a
lane.**

The newest `cloud-verify` on `master` is
[31728207470](https://github.com/Shaugato/mainline/actions/runs/31728207470), head `1a6e10a`,
`schedule`, 2026-08-13T17:56:15Z — **which predates the public tip `7535670`**. Its four jobs,
read with `gh run view 31728207470 --json jobs`:

| conclusion | job |
|---|---|
| success | the version comparison bites — a neighbouring tag must fail it |
| success | is there a Cloud cluster to verify against? (and can it say no?) |
| success | a real 40001 `RETRY_SERIALIZABLE`, and the loop that must not swallow it |
| success | **SKIPPED — no Cloud cluster secret** |

**The fourth job's name is the finding.** There is no *verify against Cloud* job in the run at
all; what ran is the declared complement — the step *Say what was not verified, and name the
thing that is missing*. The gate is `secrets.CRDB_CLOUD_DSN`, which is not set on this
repository, and the third job's `40001` was constructed against **the local pinned single-node
container**, not against Cloud.

`evidence/deploy/cloud-chain.json` and `evidence/deploy/cloud-seed.json` are real and are
cited in §1.0.4. Neither has a run id. **A lane is a thing a stranger can re-run from the
Actions tab; a workstation transcript is a thing a stranger must take on trust.** The two are
not interchangeable and this page will not average them. What would end this section is one
`cloud-verify` run in which the Cloud job's conclusion is `success` rather than absent — and
that requires a repository secret, which is a decision for the founder and not a documentation
task.

---

## 5. Anti-vacuity — which greens are load-bearing, which are not

A green means *"this lane can say no, and today it said yes"* only if the lane has been seen
saying no. This section carries the anti-vacuity verdicts forward, **each re-measured on the
runs above rather than quoted from a worker's summary**, and names what is still not
falsifiable. The long form is [`docs/ci/anti-vacuity.md`](ci/anti-vacuity.md).

### 5.1 PROVEN — the image pin is a claim about the running server

Earlier audits found that `custody-chain.yml`, `db-schema.yml` and `db.yml` read the pin out
of `compose.yaml`, `docker run` it, then poll `SELECT 1`. **Nothing ever asked the running
server what version it was**, so the assertion could catch a pin that failed to arrive but not
a pin that was wrong when it was requested.

Closed, with its own negative control. From `db-schema` run 31699548569, job *the version
comparison bites — a neighbouring tag must fail it*, read warm from job `94445107893`:

```
pin-truth:   tag v26.2.5 -> server said 'CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu,
             built 2026/07/28 18:56:00, go1.25.5)' -> MATCHES the pin v26.2.5
pin-control: tag v26.2.4 -> server said 'CockroachDB CCL v26.2.4 (x86_64-pc-linux-gnu,
             built 2026/07/14 16:50:57, go1.25.5)' -> does not match the pin v26.2.5
the comparison bites: v26.2.5 accepted and v26.2.4 rejected by the same pattern, in the
same step, against two nodes that both answered SQL
```

**Two nodes, one comparison, opposite verdicts, in one step.** That is a claim, not a poll.
The same job is green in `custody-chain` run 31699551218.

### 5.2 PROVEN — `judge-pack`'s envelope step has teeth

From run 31699580021, job `94445212032`, read warm:

```
unmutated copy: exit 0
  plant: envelope.py REQUEST_TIMEOUT_SECONDS 20 -> 25   -> exit 1, names
         request_timeout_seconds/DISAGREES: True
  plant: envelope.py MAX_RESPONSE_BYTES 10240 -> 10241  -> exit 1, names
         MAX_RESPONSE_BYTES/DISAGREEMENT: True
  plant: QUESTIONS.yaml Q10 EXPLAIN padded past the 16384 cap -> exit 1, names
         Q10/DOES NOT FIT: True
  plant: QUESTIONS.yaml select_page_rows 25 -> 50       -> exit 1, names
         select_page_rows/DISAGREES: True
  plant: both judge-side files move to 10241 together   -> exit 1, names
         MAX_RESPONSE_BYTES/DISAGREEMENT: True

5 plants: an unmutated copy is green, every plant is red, and every red names the row its
plant targets.
working tree clean — every plant lived in a temporary copy
```

**Two limits, kept from the audit that produced it and re-checked here.** The lane's `green`
job still invokes `cli.py envelope` **without** `--require-cross-check`
(`.github/workflows/judge-pack.yml:449`); only the teeth job passes the flag (`:249`, `:256`).
And `validate --strict` still tolerates an absent cross-check — it prints `NOT RUN` and adds no
warning. So **every `judge-pack` green recorded on this repository before the teeth landed
carries `cross-check: NOT RUN`**, and any claim that the judge pack's limits were confirmed
against a second implementation *in CI* is false for all of them.

### 5.3 PROVEN, and it was BLOCKED one board ago — the `aws-evidence` mutation family

The previous board recorded this as **BLOCKED**: the family aborted before it planted anything,
had been exercised only against a clean export carrying an uncommitted fix, and *"the
blast-radius step has never executed on a runner"*. **It has now.** The transcript is in §4.1.
The sixteen named exemptions and the measurement-not-derivation caveat are carried forward
unchanged, because those were separate findings and neither was repaired.

### 5.4 UNPROVEN — `nightly-differential`'s gate/oracle comparison

Recorded here as well as in §3.2, because colour and vacuity have different answers. The lane
is **red**, so no reader is misled by a green. But its subject — *the gate agrees with the
oracle* — **was not measured at either isolation level**, and has not been across four
commits now. A red lane and an unmeasured claim are different findings; this page keeps them
apart.

### 5.5 Greens whose refusal capability was checked, and how far

| lane | the standing job whose subject is "this lane can say no" | run | how far this page checked |
|---|---|---|---|
| `db-schema` | *the version comparison bites — a neighbouring tag must fail it* | 31699548569 | **log read** (§5.1) |
| `judge-pack` | *the envelope step goes red for each row it prints* | 31699580021 | **log read** (§5.2) |
| `aws-evidence` | *the red half is red for the reason it claims* | 31699560021 | **log read** (§4.1, §5.3) |
| `custody-chain` | *the version comparison bites — a neighbouring tag must fail it* | 31699551218 | conclusion only |
| `judge-pack` | *the validator fires on every planted violation*; *a run with no cluster exits 3, never 0* | 31699580021 | conclusion only |
| `submission` | *the submission gate can say no* | 31699563085 | conclusion only |
| `ci` | *RED BY DESIGN, and it must stay red* — an inverted job that fails if a declared red goes green | 31699545661 | conclusion only |
| `cluster-lane-bites` | *the cluster lane bites, and the hermetic lane cannot* — a 2×2 over {plant, no plant} × {`--crdb=none`, `--crdb=reuse`} | 31735341050 | **log read**, 2026-08-14 (§5.7) |
| `cluster-tests` | `COLLECTED_FLOOR` + skip ceiling, asserted from the lane's own JUnit XML | 31735341117 | **log read**, 2026-08-14 (§6.5) |
| `release-proof` | *a bare pytest run exits 0 on an all-skipped suite, and the gate refuses it by name* | 31699585931 | **log read**, 2026-08-14 (§5.7) |
| `ci` | `RED_FLOOR: 15` — the same job, now read rather than inferred | 31735341191 | **log read**, 2026-08-14 (§10.14) |

**The last column is not decoration.** Three rows were checked by reading what the job printed;
four by reading the conclusion of a job whose *name* claims a refusal. The four are weaker
evidence and are labelled rather than promoted.

**Four rows added 2026-08-14 by W6 of the lane-honest wave**, each from a run at `eefae1c` or
later and each read out of the log rather than out of a conclusion. The `ci` row appears twice
on purpose: the 2026-08-13 reading of it was conclusion-only, the 2026-08-14 one is a log read,
and replacing the weaker row with the stronger one would hide that the weaker one was ever
accepted.

### 5.6 What this section does not claim

It does not claim the remaining greens are vacuous. It claims they were **not audited on this
board** — a different sentence, and the honest one. `boundary`, `claims`, `cloud-verify`,
`console`, `mutation-ratchet`, `release-proof`, `skills` and `supply-chain` each passed;
whether each can be made to fail was not re-established here.

### 5.7 PROVEN, 2026-08-14 — two controls that were watched refusing, one of them the most expensive in the repository

**Added by W6 of the lane-honest wave. Both were read out of a run log, not out of a summary.**

**`cluster-lane-bites`, run
[31735341050](https://github.com/Shaugato/mainline/actions/runs/31735341050)** (push,
`eefae1c`, 2026-08-13T19:20:30Z). The lane plants a defect that only a real database can see,
then runs the same subset four ways. Every cell's pytest summary line, verbatim:

| | plant ABSENT | plant PRESENT |
|---|---|---|
| `--crdb=none` | `7 passed, 71 skipped in 0.32s` → 7 executed, floor 7 | `7 passed, 71 skipped in 0.30s` → 7 executed, and **7 == 7** |
| `--crdb=reuse` | `77 passed, 1 skipped in 109.21s` → 77 executed, floor 77 | `3 failed, 74 passed, 1 skipped in 76.12s` → **RED** |

**The load-bearing cell is the top-right one, and it is the one people misread.** It is not a
green to be celebrated; it is the proof that *the hermetic lane cannot tell the planted tree
from the clean one* — same count, same duration, same colour. If the plant were visible
hermetically, the cluster lane would be redundant for it and the answer would be a different
plant, **never a relaxed assertion**. The bottom-right cell then shows the cluster lane
catching what the hermetic lane could not. Two more assertions in the same run passed: the
known-red inventory could not suppress the planted failure, and the frozen-seed guard went red
against the plant. The lane's overall conclusion is **failure**, on a stale freeze baseline
that ruling R2 governs — the 2×2 itself is intact and green.

The 142 `conftest.py:294` skips in the hermetic cells carry the reason the fixture wrote:
*"the session obtained no CockroachDB, so this cluster-backed test is skipped rather than
allowed to reach a node the session declined to obtain."* **That is what the whole 2×2 is
about: those 142 are the tests the hermetic lane cannot speak for, and the cluster lane is the
only place they become evidence.**

**`release-proof`, run
[31699585931](https://github.com/Shaugato/mainline/actions/runs/31699585931)**, job *the
database refuses the merge*, two pytest summary lines in one job:

```
15 skipped in 0.24s     ← the bare run, --crdb=none against a closed port. pytest exits 0.
15 passed  in 44.49s    ← the same suite against a real node.
```

**Both halves of the defect are asserted in one step**: that `pytest` reports success on an
all-skipped run, and that the gate refuses that run by name. This is the control §6.4 cites,
and it is the reason `cluster-tests.yml` has a `COLLECTED_FLOOR` at all. It is the strongest
anti-vacuity statement on this page after `aws-evidence`'s plant family (§4.1), and unlike that
one it needs no plants: it exhibits the failure mode live and then refuses it.

### 5.8 UNPROVEN, 2026-08-14 — `schema`'s unwelding matrix has never reached its own pytest step

`schema.yml:483` runs `pytest packages/trappoint-conformance/unweld -m schema` against a
disposable node. In run
[31735341105](https://github.com/Shaugato/mainline/actions/runs/31735341105) the job
*unwelding matrix (serial, disposable cluster)* died **before** that step, at
`trappoint migrate up`:

```
##[error]RED BY DESIGN, NOT A CI DEFECT. 2 object(s) are referenced by
packages/trappoint-sql/refvertical/sql and created by no file in it:
trappoint_ref.clause, trappoint_ref.…
```

**Nobody is misled — the lane is red, and the red says so in its first clause.** But the
matrix's four cases (`--collect-only` on that directory: **4 tests**) have not executed, so
`REFUSAL_DEPTH.md`'s currency check at `schema.yml:487` is comparing a committed artefact
against a matrix that did not run. This is §5.4's shape exactly — *a red lane and an unmeasured
claim are different findings* — and it is recorded here so the second one is not absorbed into
the first when the migration is fixed. **Activation:** the two missing producers land, the
migration succeeds, and the four cases execute for the first time.

---

## 6. The cluster line: a lane in this repository HAS now executed cluster-backed demo-api tests — 518 of them, in CI, against a real CockroachDB

**Rewritten 2026-08-14 by W6 of the lane-honest wave, under ruling R9 of
[`docs/leads/lane-honest-plan.md`](leads/lane-honest-plan.md).**

### 6.0 The sentence this section used to carry, and the run that ended it

This section was titled, through every revision until this one:

> **6. The cluster line: no lane in this repository has ever executed a cluster-backed
> demo-api test**
>
> *This is the finding this board exists to publish, and no previous revision of this page
> carried it in any form.*

**That sentence is now FALSE, and the heading above is the correction.** Its two lines are
quoted here in full — heading and standfirst — so that the version this page shipped for a day
is readable beside the version that replaced it. §6.4 — written
before the lane existed — already asked *"what would end it, and the number to check when
it lands"*. This is that landing, and §6.4 is answered in §6.5 rather than deleted.

The run, named once so every number below can be checked against it:

| | |
|---|---|
| workflow | `cluster-tests` |
| run | [31735341117](https://github.com/Shaugato/mainline/actions/runs/31735341117) |
| event · head · started | push · `eefae1c` · 2026-08-13T19:20:30Z |
| job | *the demo-api suite against a real CockroachDB* |
| **pytest's own summary line** | **`1 failed, 517 passed, 10 skipped in 154.21s`** |
| collected · executed · skipped · failed · errored | **528 · 518 · 10 · 1 · 0** |
| conclusion | **failure** — and correctly so; §6.5 names the one failure |

Read with `gh run view 31735341117 --log`, 1,023 log lines, parsed for every
`SKIPPED [n] …` line rather than for a rollup — a skip census quoted from a summary is not
a census. **The lane is RED, which is the state §6.4 predicted it would arrive in, and a
red lane that executed 518 assertions is worth more than the green nothing it replaced.**

**§§6.1–6.3 below are kept exactly as they were written.** They are the measurements that
made the old sentence true, they are now the BEFORE, and a page that deletes its own
superseded numbers stops being evidence. Their 2026-08-13 figures are not restated to
match this run and this run is not restated to match them.

### 6.1 The sentence, and the two measurements that make it — *kept as the BEFORE*

```
$ git grep -n "demo-api" 2dc5c86 -- .github/workflows/ ; echo "exit=$?"
exit=1                                  # no match, in any of the eighteen files

$ git grep -c 'docker run -d' 2dc5c86 -- .github/workflows/
cloud-verify.yml:1   custody-chain.yml:3   db-schema.yml:1   db.yml:1
mutation-ratchet.yml:1   nightly-differential.yml:2   release-proof.yml:2   schema.yml:2
                                        # 8 files, 13 stand-ups
```

**Eight of the eighteen workflows start a pinned CockroachDB. Not one of them names the demo
API's test directory.** The only lane that runs the whole-repo `testpaths` collection is
`ci`'s `hermetic-tests`, and it runs `--crdb=none` on purpose — which is correct, because that
is what makes a cluster test skip with a written reason instead of dialling a node the session
declined to obtain.

> **The lane that reaches that directory has no cluster. Every lane that has a cluster is
> pointed somewhere else.**

### 6.2 What it costs, measured on this workstation in this sitting — *kept as the BEFORE*

```
$ pytest verticals/mainline/apps/demo-api/tests --collect-only -q
445 tests collected in 0.66s

$ pytest verticals/mainline/apps/demo-api/tests --crdb=none  -q
258 passed, 187 skipped in 13.60s

$ pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q
4 failed, 376 passed, 1 skipped, 64 errors in 52.15s
```

**187 of 445 cases covering the product's headline path execute in no CI lane anywhere.** They
are collected — they are inside `ci`'s `1003 skipped` in §3.1 — and each carries the reason its
own fixture wrote, which is enormously better than a suite nobody walked. It is still not a
test that ran. The one skip that survives a cluster is `jsonschema is not a workspace
dependency`, so the executable population under a real node is **444**.

**And the right-hand column is where the defects are.** `4 failed … 64 errors` are real
findings owned by other leads in this wave; they are invisible to every lane on this board.

**Those totals moved twice more before this section was finished, and the drift is published
rather than smoothed.** Re-run at the close of the same sitting, with nothing changed by this
worker except three markdown files, the suite went 445 → 499 → 502 collected: another worker
landed 836 lines across `static_site.py` and `test_response_contract.py` while this page was
being written, and five of the new cases fail with no database at all. **The number that did
not move across any of the three runs is the one this section is about: 187 skipped, every
time, in a directory no workflow points a cluster at.**
[`docs/ci/test-collection.md`](ci/test-collection.md) carries all three pairs with the
commands that produced them.

### 6.3 The same shape at repository scale — *kept as the BEFORE*

The exact argv `ci.yml`'s `hermetic-tests` job runs, plus `-ra`, on the local tree:

```
$ pytest --crdb=none -q -m "not (g4alpha or pl2_red)" -ra
4 failed, 8832 passed, 988 skipped, 15 deselected, 2 warnings in 606.03s (0:10:06)

974 of those 988 skips name a CockroachDB, a DSN or a cluster.  46 distinct reason strings.
```

`4 + 8832 + 988 + 15 = 9839`.

**The same lane, measured independently by another worker on this wave, and the two agree
where it matters.** [`qa/ci-skip-census.json`](../qa/ci-skip-census.json), schema
`mainline.qa.ci-skip-census/1`, written by `scripts/qa/ci_skip_census.py` at `12:04:05Z`,
carries one entry per skipped test rather than a rollup by reason — because a rollup cannot be
attributed to a lane. Cited by key:

| key | value |
|---|---|
| `#collected` | 9839 |
| `#skipped` | 988 |
| `#distinct_reasons` | 46 |
| `#roots["verticals/mainline/apps/demo-api"].cluster_skipped` | 187 |
| `#passed` | 8829 — where this sitting measured 8832, three tests apart on a moving tree |
| `#skips` | one object per skipped test: `{nodeid, file, line, root, reason, cluster_shaped}` |

**Two independent runs of one argv, one afternoon apart, agreeing on `collected`, `skipped` and
`distinct_reasons` and differing by three on `passed`.** That is the shape of a tree five
workers are editing, and it is why §6.2's ratio rather than its absolute totals is the claim.

The per-root breakdown, the workflow census and the full account of the drift are in
[`docs/ci/test-collection.md`](ci/test-collection.md), whose closing section states the
sentence this board turns on: **collection is not execution.**

### 6.4 What would end it, and the number to check when it lands — *kept as the BEFORE; answered in §6.5*

`.github/workflows/cluster-tests.yml` exists in the working tree and is **untracked, absent
from the remote, and never dispatched** (§0.2). It has no row on this board and will not get
one until it has a run id.

When it lands, the number that matters is not its colour — **it will be red on the day it
arrives, and that is correct**, because the `4 failed … 64 errors` above are real. The number
to check is its executed floor: **`tests − skipped ≥ 440`**, asserted from its own JUnit XML.
`release-proof.yml:219-320` records the defect that floor exists for — *"pytest exits 0 when
every test skips"* — live in this repository. **A lane that runs zero tests and exits 0 is
worse than no lane at all**, and a cluster lane that quietly passes without a cluster converts
*"we do not know"* into *"we checked"*.

### 6.5 §6.4 ANSWERED — the floor it named, checked against the run that landed

§6.4 asked for one number: **`tests − skipped ≥ 440`**, asserted from the lane's own JUnit
XML. Run 31735341117 reports `528 − 10 = 518`. **518 ≥ 440. The floor §6.4 wrote is met, by
78.**

The lane also carries `COLLECTED_FLOOR: "445"` (`cluster-tests.yml:111`) and collected 528,
so the anti-vacuity guard §6.4 was really about — *a lane that runs zero tests and exits
0* — is armed and did not fire. Its error message forbids the obvious escape in writing:

> *"A collection error here is a real defect in the checked-out tree … answered by landing
> what is missing. It is never answered by lowering `COLLECTED_FLOOR`, by `-k`, by
> `--deselect`, or by stubbing the import."*

**The one failure, named rather than counted.**
`test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`
asserts `set() == {'MECHANISM_PRESENT_AND_VERIFIED', 'SCOPE_EXCLUDES_HAZARD'}` at
`test_reads.py:414`, because `mainline.defeater_option` holds **zero rows**. A judge cannot
choose a defeater and therefore cannot sign — the last beat of the demo. **The assertion was
not weakened to match the seed**; the seed owes the rows. Owner: the demo-seed lead, out of
scope for this wave by ruling R10.

**The ten skips, every one of them, read out of the run's own `SKIPPED [n]` lines:**

| source | skips | reason, in the test's own words |
|---|---|---|
| `test_response_contract.py:893` | 3 | *"the deployed package is not built, so the tree-reading half of the ratchet did NOT run in this session"* |
| `test_static_site.py:930` | 3 | *"the deployed package … is not built, so the ceiling's derivation was NOT checked"* |
| `test_envelope.py:1016` | 1 | *"no deployment package has been built in this tree, so there are no bytes to read"* |
| `test_response_contract.py:1144` | 1 | same cause |
| `test_response_contract.py:1210` | 1 | same cause |
| `test_gate_run.py:945` | 1 | *"jsonschema is not a workspace dependency"* — **nothing to do with the database** |
| | **10** | **against the lane's ceiling of 1** |

**Nine of the ten are one cause: `out/lambda/mainline-demo-api-arm64.zip` is a gitignored
build output and CI never builds it.** The tenth is unrelated. The lane's own message for
this state is the standard the rest of the repository is now measured against:

> *"10 test(s) skipped, ceiling 1. A skip here means the suite could not reach the cluster
> this job started, and a skip is indistinguishable from a green tick on a dashboard."*

**The ceiling of 1 is correct and does not move** (ruling R4). Building the package in-lane
takes 10 → 1, landing exactly on it. Corroborated locally: with the package present on this
workstation the same suite skips exactly one test, and it is the `jsonschema` one.

### 6.6 What is in flight, has no run id, and is therefore not credited here

This page's own rule, from §0.2: **a repair without a run id is a plan, and this page counts
plans as red.** Three repairs to this lane exist in the working tree at the moment of
writing, are uncommitted, are absent from the remote, and have produced no run:

| change | owner | the number to check when it lands |
|---|---|---|
| `cluster-tests.yml` builds the deployment package in-lane (`./.github/actions/build-demo-package`, present at `cluster-tests.yml:281`, untracked) | W1 | the lane's JUnit reports **≤ 1 skipped** against the unchanged ceiling of 1, and **executed rises 518 → 527**; and the **nine** package-dependent assertions that have never run in CI get an outcome, pass or fail, named |
| `qa/cluster-known-red.json` falls to **one** group of **one** id — the `defeater_option` failure above — with `floor.min_executed` **440 → 518** and `max_skipped` unchanged at **1** | W3 | the lane goes green on 63 of the 64 ids the inventory used to carry, and red on exactly one, by name |
| `cluster-lane-bites.yml`'s falsifiability 2×2, re-run against a re-baselined frozen-seed guard | W2 | all four cells and all six assertions green end to end |

**The floor rises to the CI number, 518, and not to this workstation's 527.** The file says
why in its own words, and it is the right call: CI legitimately skips nine package-dependent
assertions that run here, so a floor of 527 would trip the lane **for a cause it does not
name**, and a floor that fires for the wrong reason teaches a reader to disable it.
`min_executed` becomes 527 in the commit that PROVES 527 in CI — which is W1's, not W3's.

### 6.7 What the cluster line still does not cover, stated before somebody reads it as more than it is

* **Every green here is from a SINGLE-NODE CockroachDB.** `cluster-tests.yml` stands up one
  pinned container; this workstation runs one local node. The demo deploys to CockroachDB
  **Cloud**, which is multi-node and returns `40001 RETRY_SERIALIZABLE` under contention.
  **Nothing in this lane exercises the retry loop.** `_seed_permit` at
  `test_transitions.py:224` commits ~29 statements with no retry, and `test_gate_run.py:143`
  names its scratch database with a fixed string — a measurement hazard that has already
  corrupted one published "unstable" list. Owner: the Cloud lead (R10); recorded, not fixed.
* **`cloud-verify` still has never touched CockroachDB Cloud in CI** (§4.3, §10.5). "Cluster"
  in this section means the pinned local container, every time it appears.
* **One run is not a distribution.** `qa/cluster-known-red.json` carries four `unstable`
  entries in `test_transitions.py` with measured `runs_observed`/`runs_failed` — 19/2, 22/1,
  19/1, 19/1 — precisely because three consecutive passes do not refute a flake. A single
  green run of this lane would not either.

### 6.8 §6.6 ANSWERED — the three in-flight repairs landed, and the lane is red on something else

**Measured 2026-08-14 by D3, from run
[31770005759](https://github.com/Shaugato/mainline/actions/runs/31770005759)** — `cluster-tests`,
push, head `7535670`, the public tip. §6.6 named three repairs that had no run id and wrote the
number to check for each. All three now have one. **§6.6 is answered here and left standing
above rather than deleted, because a prediction that is edited after the outcome is not a
prediction.**

The lane's own verdict line, quoted from the runner:

```
cluster lane: 570 collected, 569 executed, 1 skipped, 8 failed, 0 errored
8 failed, 561 passed, 1 skipped in 224.11s (0:03:44)
```

| §6.6 said to check | measured at `7535670` | verdict |
|---|---|---|
| *"the lane's JUnit reports **≤ 1 skipped** against the unchanged ceiling of 1"* | **1 skipped** | **MET, exactly** |
| *"and **executed rises 518 → 527**"* | **569 executed**, from **570 collected** | **exceeded, and for a reason §6.6 could not have known: the suite itself grew from 528 to 570 collected between `eefae1c` and `7535670`. 527 was the right prediction for a 528-case suite and is the wrong number to check against a 570-case one. The floor that matters is unchanged and is met.** |
| *"the **nine** package-dependent assertions that have never run in CI get an outcome, pass or fail, named"* | **they got one, and eight of them are RED** — named in §6.8.2 | **MET, and the outcome is bad news, which is what an outcome is for** |
| *"`qa/cluster-known-red.json` falls to **one** group of **one** id"* | it did; and that one id **PASSED** — the lane printed `FIXED [disposition-defeater-vocabulary-is-not-seeded]` | **MET; the inventory is now stale in the other direction (§6.8.3)** |
| *"`cluster-lane-bites`'s 2×2 … all four cells and all six assertions green end to end"* | **all four cells green; the run is still red on a later step** | **partially met — see §1.0.3** |

#### 6.8.1 The skip ceiling was satisfied by building the package, and it was never raised

This is the finding on this page most at risk of being read backwards, so it is stated in the
direction the evidence runs.

**At `eefae1c`, run 31735341117: 10 skipped against a ceiling of 1, and the lane errored on
it.** Nine of the ten had one cause — `out/lambda/mainline-demo-api-arm64.zip` is a
`.gitignore`'d build output and CI never built it. §6.5 records all ten by line number.

**At `7535670`, run 31770005759: 1 skipped against the same ceiling of 1.** The lane now
builds the package before the suite, via `./.github/actions/build-demo-package`
(`cluster-tests.yml:281`), and the surviving skip is the `jsonschema` one — the skip the
ceiling of 1 was sized for.

**The ceiling did not move.** It lives in `qa/cluster-known-red.json` under `floor.max_skipped`
and reads `1` at `eefae1c` and `1` at `7535670`. The lane's own comment says why, and it is
quoted rather than paraphrased because the temptation it refuses is the one this whole
repository is about:

> *"THIS STEP DOES NOT WEAKEN THE SKIP CEILING; IT REMOVES THE REASON FOR THE SKIPS."*
> — `.github/workflows/cluster-tests.yml:275`

**The cure was to build the package in the lane. It was never to raise the ceiling, and no
document in this repository may suggest otherwise.** A ceiling raised to admit ten skips would
have converted *"nine assertions did not run"* into *"nine assertions are fine"*, and the two
are the same colour on a dashboard. The lane was right to error and the repair paid for
itself in one run: eight defects that had never been visible in CI became visible in CI.

#### 6.8.2 The nine got their outcome, and eight of them are red on a build that reproduces differently

Eight `NEW` failures, all in the package-dependent set, all one family. Named individually
because §6.6 asked for them to be:

```
test_response_contract.py::test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal
test_response_contract.py::test_the_built_web_tree_has_not_outgrown_its_declaration
test_response_contract.py::test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed
test_response_contract.py::test_the_ceiling_refuses_something_it_governs
test_response_contract.py::test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal
test_response_contract.py::test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses
test_static_site.py::test_serving_the_deployed_package_derives_the_ceiling_end_to_end
test_static_site.py::test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from
```

One cause, quoted from the runner:

```
AssertionError: the deployed package refuses ['assets/index-DzVoV1YM.js [identity]'].
  Exactly one object, on the identity path, is the declared consequence of the derived
  ceiling; anything else is an asset nobody decided to stop serving, or a ceiling that
  stopped biting.
    - 'assets/index-BjAGxrVJ.js [identity]': 413      ← what the test declares
    + 'assets/index-DzVoV1YM.js [identity]': 413      ← what CI built
```

```
AssertionError: assets/index-DzVoV1YM.js is 433564 B … at or above the 139264 B ceiling,
  and this file does not name it as refused. … Strip it, declare it in
  _REFUSED_BY_THE_CEILING, or raise the ceiling deliberately — do not raise it to make
  this pass.
```

**Read what did NOT move.** The ceiling is `139264` B in both the test and the run — that is
`136 * 1024`, and it is unchanged. The failure is not that the bound slipped; it is that the
**content-hashed filename and byte count recorded in the test describe a different build of
the console** than the one the lane produced (`index-BjAGxrVJ.js` at 433,396 B declared,
`index-DzVoV1YM.js` at 433,564 B built). Exactly one object is over the ceiling in both, and
it is the same object under two names.

**Which side is authoritative is a question this page does not get to answer by preference.**
The deployed tree is authoritative for what the origin emits — that is
`docs/decisions/response-ceiling-authoritative-tree.md` §1, and it is why the assertion is
written against a built artefact at all. So the constants are the derived side and they are
what must move, **but only after a build that reproduces has been shown to produce them**, and
the assertion's own message forbids the shortcut in writing: *"do not raise it to make this
pass"*. That work is not this documents wave's; `docs/ci/cluster-lane-package.md` §5 records
why W1 deliberately did **not** re-record them, and that reasoning is what a reader should
check before anybody re-records them now.

#### 6.8.3 The inventory is now stale in the direction nobody polices

The same run printed:

```
inventory: 1 known, 0 still failing, 1 now passing, 4 declared unstable, 8 NEW
FIXED  [disposition-defeater-vocabulary-is-not-seeded]
       test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements
##[notice] 4 declared-unstable test(s) passed this run. If the cross-test contamination
           behind them has been fixed, delete them from qa/cluster-known-red.json — an
           exemption nobody is reminded of becomes permanent.
```

**The one `groups` entry names a cause that is fixed, and all four `unstable` entries passed.**
`qa/cluster-known-red.json` is not this page's file and is not edited by this wave. What this
wave owes is saying so precisely enough that its owner cannot claim nobody said it, and that
is [`docs/ci/cluster-known-red-staleness.md`](ci/cluster-known-red-staleness.md) — four entries
by node id, the contradiction quoted from the file's own `policy` block, and the one category
no ceiling polices named as such.

---

## 7. Claims on earlier boards that did not survive re-measurement

Each was true when written, or believed when written, and is false at `2dc5c86`.

### 7.1 "`|| true` survives on exactly one live line" → **three**

The top of this page carries the measurement. `db.yml:564` is the container-cleanup line the
earlier board named; `nightly-differential.yml:170` and `:217` are two `grep -c` invocations
inside printing lines, each with a written justification at `:166` — *"`grep -c -v` exits 1 on
a zero count, and under `set -e` an empty corpus would abort the step before the test could
report it as the failure it is"*.

**The earlier board did not miss a change; it undercounted.** Both lines are present at
`53197f5`:

```
$ git grep -n "|| true" 53197f5 -- .github/workflows/   → the same three live lines
```

**This page does not remove them.** The justification is real, the test that owns the claim
asserts non-emptiness separately, and deleting a suppression is a change to a workflow file
this worker does not own. Named, counted, and left for the owning lane.

### 7.2 "`db`'s restated-literal census reads 18 against a ceiling of 19" → **19 against 19**

Measured on job `94445127812` of run 31699548569's sibling, `db` run 31699554580 (§2.2). The
previous board recorded a one-literal margin and the lane's own `::notice` asking for the
ceiling to be lowered. **The margin is gone**: the count rose back to the ceiling between
`53197f5` and `2dc5c86`, the notice is no longer printed, and the next restated literal makes
that job red. This is the ratchet doing exactly what it is for — the number moved and the
page that failed to re-measure it would have said the opposite.

### 7.3 "`aws-evidence` is red on `SEC-ACCOUNT-ID`, and its mutation family asserts nothing" → **both paid** (§4.1, §5.3)

### 7.4 "`schema`: three jobs red, one green, one cause" → **four red, two causes** (§2.1.1)

The fourth is a defect, not a design, and it is a line-ending difference in a generated
document.

### 7.5 "`ci`'s pytest is 4 failures, three of them by-design custody rows" → **8 failures, five by-design custody rows** (§3.1)

Two of the three new ones are demo-api tests that had never been collected. The third K2 pair
was always red and was not in the previous board's four.

### 7.6 Claims that survived, and are listed because they were expected to move

* **`db-schema`'s `mi-red` refuses the same five promotions.** Fourth run, fourth commit (§2.5).
* **`db` and `schema` are red on the two missing reference-vertical producers.** Unchanged.
* **`demo-health` is red because no demo URL is published.** Unchanged.
* **`custody-chain` is 7/16 with three K2 artefacts missing.** Unchanged.
* **No lane's Cloud half has ever run in CI** (§4.3). Unchanged.

### 7.7 A claim this page made about itself, and then caught

An earlier draft of §2.5 said `mi-red` had narrowed from five refusals to two. **False**, and
the cause was that author's own `tail -25` truncating a five-line list. Corrected against three
runs then, and re-measured as five a fourth time here. Recorded because the mechanism that
caught it — re-running the command instead of trusting the note — is the only mechanism this
page has.

### 7.8 "§6: no lane in this repository has ever executed a cluster-backed demo-api test" → **518 executed** (§6.0)

**Added 2026-08-14 by W6 of the lane-honest wave.** This was §6's own headline and the finding
the `2dc5c86` board existed to publish. It was true when written, on the tree it was written
about, and it is false at `eefae1c`: run 31735341117 executed **518 of 528** demo-api tests
against a real CockroachDB. It is filed here — in the section for claims that did not survive
re-measurement — rather than only in §6, because a page that corrects itself quietly and a page
that never made the claim look identical to a stranger.

**Note which direction this one moved.** §§7.1–7.5 are claims that were too kind to the
repository. This one was too harsh: the hole was real, somebody filled it, and the page had to be
edited to stop understating the tree. **Both directions belong in this section**, and a list that
only ever collected the flattering corrections would be the more comfortable document and the less
useful one.

### 7.9 "`aws-evidence` is green … a whole anti-vacuity family came back on" (§4.1) → **red again at `7535670`, and the family is off again**

**Added 2026-08-14 by D3.** §4.1 is true of run `31699560021` at `2dc5c86` and it names that
run in its first line, so it is not corrected in place. It is false as a statement about the
tip: run [31770005783](https://github.com/Shaugato/mainline/actions/runs/31770005783) at
`7535670` is red on all three jobs, and the third aborts with the same
`FAMILY red-for-the-wrong-reason` §4.1 celebrated the end of. The proximate cause is different
(two `[CEN-ANCHORS]` citations that silently retargeted, §1.0.2) and the structural lesson is
the one §5.3 already drew: **an anti-vacuity family that depends on an unmutated control being
green is only as strong as the weakest assertion anywhere in that control.**

### 7.10 "`submission` is green" (§4.2) and "`claims` — success" (§1) → **both red**

**Added 2026-08-14 by D3.** `submission` at `7535670` is red on one unlicensed file
(`collected.txt`) against a hard gate whose baseline is 0; `claims` at `eefae1c` is red on the
three `HYG-sha-literal` lines in `docs/HONESTY.md`. Neither is a lane defect and neither is
answered by a scope list. Causes and quoted logs in §1.0.2.

### 7.11 "the demo API's 187 cluster-backed tests — collected, counted, never executed" → superseded twice, and the SECOND correction is the one that matters

**Added 2026-08-14 by D3.** The board's opening block was already annotated once, on
2026-08-13, when run 31735341117 executed 518. **It has now been overtaken again**: at
`7535670` the lane executes **569 of 570** with **one** skip, because the deployment package
is built in the lane (§6.8.1). The figure `187` was never wrong about the tree it described,
and the two corrections are stacked rather than merged so that the rate of change is legible.
**A claim corrected twice in twenty-four hours is a claim about a moving tree, and the right
response is to date every reading, not to stop publishing them.**

### 7.12 A claim this page could not check, and says so

`cluster-tests`'s failure output was reported by an orchestrator as *drowned by CockroachDB's
own event log*, such that the single failing assertion had to be found with `grep`. **That was
measured at run 31735341117 and it was true there** —
[`docs/ci/cluster-lane-diagnosis.md`](ci/cluster-lane-diagnosis.md) §1 carries the line
geometry. At `7535670` the four-part fix has landed and a one-screen digest is printed. **It
is a mitigation and not a closure**, and the residual is measured rather than assumed:
`docs/ci/cluster-lane-diagnosis.md` §8, added today, gives the current run's geometry line by
line. What this page cannot check is whether a reader lands on the rendered step summary or on
the raw log, because GitHub's API does not expose which one an account opened.

---

## 8. The row a dispatch cannot produce: `ci`'s PL-2 red on a push

PL-2 is push-gated (§1.1, §2.6), so this row cannot come from the eighteen dispatches above.
**It also cannot come from this sitting**, because this worker pushed nothing: the local tree
is two commits and sixty-three paths ahead of the public tip and none of that is this worker's
to publish (§0.2). So this row is the push run **at this board's own commit**, created by the push
that produced `2dc5c86`, and read warm here.

* **run:** [31669424091](https://github.com/Shaugato/mainline/actions/runs/31669424091) — `ci`,
  event `push`, ref `refs/heads/master`, head `2dc5c86` — **the same SHA as every other row on
  this page**, which is why it is admissible where a run at a different commit would not be
* **created:** `2026-08-13T05:10:28Z`, by somebody else's push, **not by this sitting**
* **job:** `PL-2 — the red run is recorded` (job `94350801637`) — **failure**
* **cause, quoted from the job log, read warm via `gh api …/actions/jobs/94350801637/logs`:**

```
##[error]RED BY DESIGN, NOT A CI DEFECT. This job asks for the URL of a db run in which the
CONFORMANCE step itself went red. No such run exists, because CONFORMANCE has never
executed: db.yml stops one step earlier, at 0058_blocking_check on the missing
trappoint_ref.event. Recording any other red db run would put a URL in a field that asks
for a different observation, which is the precise laundering the field was created to
prevent, so it stays UNRECORDED and this job stays red. WHAT TURNS IT GREEN: the producer
for trappoint_ref.event lands, the next db push-run on master reaches CONFORMANCE, that
step is red, and THAT run's URL replaces the word UNRECORDED in
docs/adr/0005-red-before-green.md. WHAT DOES NOT: any other red db run, deleting the line,
or relaxing this check.
```

**The rest of that push run agrees with the dispatched board**: `actionlint`, `ruff format`,
`mypy`, `import-linter`, `REUSE`, the lockfile, the sequence ban, *every checker this lane
invokes exists* and *RED BY DESIGN, and it must stay red* all green; `pytest --crdb=none` and
`CI summary` red, the same two as run 31699545661 in §3.1. **PL-2 is the one job the dispatch
could not reach**, and on a push it is red, by design, with the reason in the annotation — so
`ci` is red on a push for **three** jobs rather than two, and the third is deliberate.

**Consequence for the board.** `ci` is red on a push for one more reason than on a dispatch,
and that reason is by design. It does not change §1: `ci` is red either way.

---

## 9. What this page did not achieve

* **The cluster lane has no row.** `.github/workflows/cluster-tests.yml` is written and
  untracked; `cluster-lane-bites.yml`, `scripts/qa/skip_ratchet.py` and
  `scripts/qa/check_pytest_lanes.py` — the falsifiability job, the skip ratchet and the
  per-lane declaration checker this wave planned — **do not exist in the tree at all**. §6 is
  therefore a measurement without a mechanism: it states the hole and nothing yet stops it
  reopening.
  **DISCHARGED 2026-08-14, and kept above rather than deleted so the gap is dateable.** All four
  exist and all four have run: `cluster-tests` (run 31735341117, §6.0), `cluster-lane-bites` (run
  31735341050, §5.7), and both checkers landed with the sweep in §10.0. §6 now has a mechanism —
  `COLLECTED_FLOOR: 445`, a skip ceiling of 1, and `qa/cluster-known-red.json`'s
  `floor.min_executed` — and each of the three refuses in a direction that a lowered number cannot
  satisfy quietly.
* **`qa/ci-skip-census.json` landed and `docs/HONESTY.md` cannot cite it.** That file is a new
  evidence family, and `tests/release/test_honesty_is_checkable.py`'s `FAMILIES` tuple does not
  declare it — so a citation into it is rejected as *"an artefact family nobody declared"*, and
  the `families_landed_but_uncited` rule that fires when new evidence appears **cannot see it
  either**. The census is cited on this page and in `docs/ci/test-collection.md` instead. The
  registration is one entry in a file this worker does not own.
* **`db.yml`'s red does not say "by design" in its own message.** Unchanged from the previous
  board; its reader still has to come here.
* **`db`'s restated-literal census no longer has any slack, and this page only reports it.**
  The previous board recorded `18 (ceiling 19)` and the lane's own request to lower the
  ceiling; it now reads `19 (ceiling 19)` (§2.2, §7.2). The margin was spent by somebody
  restating an image literal, nobody noticed, and the next one turns a green job red. Moving a
  ceiling — in either direction — changes an assertion, and changing an assertion is not a
  documentation task, so this page names the condition and leaves the number alone.
* **The three suppression lines are named, not removed** (§7.1).
* **`nightly-differential` has not compared the gate to the oracle across FOUR commits**
  (§3.2, §5.4). It is red, so nobody is misled — but the claim the lane exists to make is
  unmeasured, and no worker in this wave owned it.
* **A new defect was found and not fixed:** `ANOMALY_COVERAGE.md` is committed CRLF and
  regenerated LF, with no root `.gitattributes` to reconcile them (§2.1.1). Recorded with the
  byte counts and left to the owning package, because the fix is a re-commit of a generated
  file and a repository-wide line-ending policy, neither of which is a documentation change.
* **Eight greens were not audited for vacuity** (§5.6).
* **ADDED 2026-08-14 by D3 — eight of twenty rows describe a tree that is not the tip, and
  this page did not fix it.** `console`, `judge-pack` and `skills` are still reporting
  `2dc5c86`; `cloud-verify` and `mutation-ratchet` report `1a6e10a`; `claims` and
  `supply-chain` report `eefae1c`; `nightly-differential` reports `e944407`. Every one of
  those is a green or a red about a tree nobody is running. **The cure is a dispatch, and a
  dispatch is an action on the repository rather than an edit to a document**, so this
  revision names the eight and stops there. §10.4 recorded the same defect at a count of ten
  and it has not closed; it has re-formed around different lanes.
* **ADDED 2026-08-14 by D3 — three lanes went from green to red and no worker in this wave
  owns any of the three causes.** `evidence/tool-usage/aws-services.json` needs two citations
  re-anchored, a root `collected.txt` needs a licence or a deletion, and `docs/HONESTY.md`'s
  three SHA literals are D2's under RULING 5. This page reports all three with the log text
  and touches none of them (§1.0.2, §7.9, §7.10).
* **ADDED 2026-08-14 by D3 — the 2×2's own table has still never been published by a run.**
  All four cells passed at `7535670`, and the summary step was skipped because it carries no
  `if: always()` and a later step failed. **A falsifiability argument whose conclusion is only
  reachable by reading nineteen step names one at a time is a falsifiability argument most
  people will not read.** The reconstruction is in
  [`docs/ci/cluster-lane-falsifiability.md`](ci/cluster-lane-falsifiability.md) §Z; the fix is
  one `if: always()` in a workflow this wave does not own.
* **ADDED 2026-08-14 by D3 — `qa/cluster-known-red.json` is stale in both directions and this
  wave may not touch it.** Its single `groups` entry names a cause that is fixed; all four of
  its `unstable` entries passed in the same run; and the file's own `policy` block says the
  `unstable` label does not describe them. Named in full, with the file's own words quoted, in
  [`docs/ci/cluster-known-red-staleness.md`](ci/cluster-known-red-staleness.md). **Documenting
  a stale exemption is not the same as removing it, and this page does not pretend otherwise.**
* **`custody-chain.yml:693`'s cross-reference into this page is still stale** and still belongs
  to another owner. It cites "`docs/CI-STATE.md` 3.1" for a finding that is §2.4. The
  equivalent reference in `ci.yml` was rewritten to cite the owning **domain document** and a
  **section name** instead of a number, which is the durable form: this page is re-derived from
  a fresh measurement every time the board moves, so a section number embedded in a workflow is
  a cross-reference that rots silently. Reported, not edited.

---

## 10. Greens that cannot fail — the vacuity sweep, and the two checkers that did not exist

**Measured 2026-08-14** by the lane-controls lane, worker W6. Local tree `D:/CoackroachDBxAWS/mainline`,
`HEAD 538193b`, `origin/master 1a6e10a`. Every number below is from a command named beside it;
nothing here is inherited from a worker's summary, or from §§1–9 above, without re-running it.

The rule this section is written under: **a green means "this lane can say no, and today it said
yes" only if the lane has been seen saying no.** Everything on the list is a place where the first
half is currently unproven. Each entry carries **the condition that would activate it** — the
specific thing that has to become true before the green means anything — because a list of soft
spots with no activation condition is itself a document that cannot fail.

> **§§10.14–10.19 are a SECOND sweep, added 2026-08-14 at HEAD `eefae1c` by W6 of the
> LANE-HONEST wave** — a different worker from the one who wrote §§10.0–10.13, who was W6 of the
> lane-controls wave at HEAD `538193b`. Two waves numbered their workers the same way and this
> page would otherwise read as one person contradicting themselves. **The earlier entries are not
> re-measured and not edited**, except where a later measurement is appended inside one and says
> so in bold (§10.6). Where the second sweep contradicts the first, it says which entry and why.

### 10.0 `ci`'s checker registry was RIGHT, and it is the reason this section exists

Run [31728043860](https://github.com/Shaugato/mainline/actions/runs/31728043860), job *every checker
this lane invokes exists*, read with `gh run view … --log-failed`:

```
  ok      scripts/qa/check_workspace_members.py      every pyproject.toml on disk is a uv.lock member
  ok      scripts/qa/ruff_ratchet.py                 no ruff rule count may rise
  ok      scripts/qa/mypy_targets.py                 every distribution has a mypy.ini section
  ok      scripts/qa/check_import_registry.py        no distribution is linted by zero contracts
  ok      scripts/qa/check_reuse.py                  every file carries an SPDX identifier or a sidecar
  MISSING scripts/qa/skip_ratchet.py                 every cluster-shaped skip is executed by a named lane or enumerated
  MISSING scripts/qa/check_pytest_lanes.py           every pytest step in this directory declares which side of the cluster line it is on
2 checker(s) absent. ci.yml asserts what these programs assert and nothing else, so a missing
one is a claim this lane silently stopped making.
```

That job is an anti-vacuity control and it worked. `skip_ratchet.py` was on disk and untracked;
`check_pytest_lanes.py` had never been written. Both now land, and all seven paths resolve against
the index — verified by replaying the registry's own loop over `git ls-files`.

Both run on the runner's **bare** `python3`: gate zero has no `uv` and no virtualenv, and both were
executed here against a clean CPython 3.14.3 carrying none of the project's dependencies.

**`scripts/qa/skip_ratchet.py`**, run at this tree:

```
cluster-shaped skips 974  ->  244 executed by 9 lane(s)  ·  730 unlanded  ·  0 unattributed
unlanded total 730 against a ceiling of 730
skip_ratchet: OK — every cluster-shaped skip is attributed.
```

Ceiling 730, measured 730: **zero slack**, which is the state a ratchet is supposed to land in.

**`scripts/qa/check_pytest_lanes.py`** is new, and its numbers were measured before its ceiling was
written, not after:

```
pytest invocations 38  ->  12 declared · 26 undeclared  (ceiling 26, floor 38)
    declared   3  cluster
    declared   9  hermetic
```

* The ceiling is **per lane** (`file.yml#job`), not one total of 26. A bare total would let somebody
  delete a marker from `ci.yml` and add one in `schema.yml` for no net change; a per-lane count
  refuses that. Twenty lanes carry a non-zero entry, and each equals its measured value exactly.
* Both this checker and `skip_ratchet.py` answer *"what is a pytest invocation?"* from **one**
  definition — `check_pytest_lanes.py` imports `skip_ratchet.scan_workflows`. Two programs in the
  same registry disagreeing about that is how one of them goes quietly blind.
* That shared scanner was cross-checked against a dumb raw grep before any floor was drawn under it:
  **130 lines** in `.github/workflows/` contain the word `pytest`, and every non-comment line the
  scanner did **not** claim is prose, an `echo`, a `pip install`, or a backslash continuation of a
  block it had already claimed (`mutation-ratchet.yml:388`, `nightly-differential.yml:341`). No
  blind spot on this tree.
* **It was watched refusing, on the real tree.** A step named *"TEMPORARY NEGATIVE CONTROL — an
  undeclared pytest step, added to be refused"* was added to `boundary.yml`'s `ci-greps` job,
  immediately after *"No retry helper, no sampling parameter, no per-signer label, no forbidden
  claim"*, running `python -m pytest tests/boundary/test_e1_iam.py -q --no-header`:

  ```
  boundary.yml#ci-greps: 2 pytest invocation(s) declare no lane, against a ceiling of 1.   [exit 1]
  ```

  The same step was then given `# trappoint:pytest-lane=hermetic` **without** changing its command —
  the obvious way to silence a checker that only counts markers:

  ```
  boundary.yml:292: declared `hermetic` at boundary.yml:291 but the command passes no `--crdb`
  mode, so it runs at the testkit default `auto`. The declaration and the command disagree; the
  command wins at runtime.                                                                 [exit 1]
  ```

  The step was then removed with `git checkout -- .github/workflows/boundary.yml`, and the file
  verified byte-clean with `git status --porcelain`.
* **Its negative control runs on every invocation, not behind a flag.** `ci.yml` invokes the program
  bare, so a control that had to be asked for with `--prove` would be a control nobody runs — the
  same shape of nothing this section exists to find. Each pass builds two synthetic workflow
  directories under `tempfile` and requires **exactly one** finding for each of five planted defects
  (undeclared step; marker contradicting its own `--crdb`; undefined marker value; `unlanded` with
  no `reason=`; orphan marker) **and zero** findings for a well-formed one. A program hard-wired to
  `return 1` fails that control, which is the direction nothing else in this repository tests.

**Activation condition for the checker itself:** it is a ratchet at zero slack, so it activates on
the next pytest step anybody adds. It can only go vacuous if a future invocation is written in a
shape `skip_ratchet._is_invocation` does not match — see §10.11.

### 10.1 The inert list, at a glance

| # | lane / control | why its green cannot fail today | what activates it |
|---|---|---|---|
| 10.2 | the digest assertion, in **four** workflows | `vars.CRDB_IMAGE_DIGEST` is unset | somebody records a hash they observed |
| 10.3 | `cluster-lane-bites`, 2026-08-13 | the file did not PARSE, so the lane was on nobody's red list | fixed; the standing guard is `actionlint` |
| 10.4 | the push→lane `paths:` filters | ten workflows' newest verdict predates `origin/master` by five commits | a push touching their filters, or a dispatch at `HEAD` |
| 10.5 | `cloud-verify`'s Cloud job | behind `if: needs.preflight.outputs.has-cluster == 'true'`, never true | a Cloud cluster secret exists |
| 10.6 | `ci`'s hermetic pytest job | no floor on the ~9,884 tests it collects | a `COLLECTED_FLOOR` on that job, as `cluster-tests` has |
| 10.7 | `db-schema`'s one-way MI ratchet | `if: github.event_name == 'pull_request'`, and this repo lands by push | changes arrive via PR, or the check also runs on push |
| 10.8 | `check_reuse.py`'s dead-glob metric | ceiling 5, measured 1 — four units of slack | the ceiling is lowered to 1 |
| 10.9 | `qa/ci-skip-census.json` | lands **without** its producer; nothing in CI can re-derive it | `ci_skip_census.py` is tracked and `--check` runs in a lane |
| 10.10 | `qa/skip-ratchet.json`'s licence | its in-band SPDX and `REUSE.toml` disagree, and no tool can see it | a ruling on which side is authoritative |
| 10.11 | the shared pytest-invocation scanner | its no-blind-spot proof was taken by hand today, not in CI | the raw-grep cross-check lands as a test |
| 10.14 | sixteen of the twenty workflows' pytest steps | **no `--crdb` flag at all** — each runs at the testkit default, so what it says about a database depends on the environment | a `--crdb` on every invocation, as `check_pytest_lanes.py` already demands a marker |
| 10.17a | `custody-chain` vs `test_custodian_attestation.py` | 19 tests, 3 of them cluster-backed, and **no step in the lane names the file** | the lane runs the directory, not three files out of four |
| 10.17b | `custody-chain`'s `test_k2_exit.py` step | 2 cluster-backed cases skip **inside a lane that has a node up**, because that step's job exports no DSN | the step moves into the job that stands the node up |
| 10.17c | the conformance `db` tier, 181 cases | **180 skipped in `ci`**, and no lane runs them under pytest at all | a lane points those tests at a DSN, or the tier is declared `unlanded` with a reason |
| 10.18 | four lanes' newest green | earned five commits behind the tip — down from §10.4's seven, not closed | a dispatch at `HEAD`, or a `paths:`-touching push |
| §5.8 | `schema`'s unwelding matrix | the job dies at `trappoint migrate up`, so its 4-case pytest step is never reached | the two missing producers land |

### 10.2 The image-digest assertion is inert in FOUR workflows, not two

`gh variable list` for `Shaugato/mainline` returns **nothing**: `CRDB_IMAGE_DIGEST` is unset. Every
lane that stands a node up resolves the digest and then asserts it only `if [ -n "${EXPECTED}" ]`:

```
cluster-tests.yml:145        EXPECTED: ${{ vars.CRDB_IMAGE_DIGEST }}
cluster-lane-bites.yml:195   EXPECTED: ${{ vars.CRDB_IMAGE_DIGEST }}
db.yml:381                   EXPECTED: ${{ vars.CRDB_IMAGE_DIGEST }}
db-schema.yml:346            expected="${{ vars.CRDB_IMAGE_DIGEST }}"
```

All four then print `::notice::CRDB_IMAGE_DIGEST is unset; the digest is recorded but not asserted`.

**This is declared, not hidden, and the design is right** — asserting the moment somebody records the
real hash beats committing a fabricated one today. It is on this list anyway, and the two entries
belonging to this lane's own workflows are listed first: naming your own lane's soft spot is the
price of naming everybody else's. The lane plan (ruling R8) named two; the sweep found four.

Note what is **not** inert: the *version* comparison. `db-schema` run 31699548569 shows two nodes,
one comparison, opposite verdicts (§5.1). The pin's TAG is proven. Only its DIGEST is unasserted.

**Activation:** `gh variable set CRDB_IMAGE_DIGEST --body sha256:…` with a hash somebody actually
observed — not a hash copied from this page.

### 10.3 A lane that fails to PARSE is on nobody's red list — a category this page had not written down

`cluster-lane-bites.yml` was committed at `e944407`, and run
[31720234309](https://github.com/Shaugato/mainline/actions/runs/31720234309) lasted **0 s and created
zero jobs**, titled by its file path rather than by its `name:` key — GitHub's signature for a
workflow it refused to parse. For a full day the lane appeared on no red list, because a workflow
that never starts produces no failing job to list.

**An absence and a pass are the same colour of nothing on the Actions tab, and this is the second
distinct way to obtain one.** §6 records the first — a suite that skips everything and exits 0. This
is a lane that never reaches a suite at all, and it is worse, because the first at least consumes a
runner and prints a count.

Fixed by W1. Run [31728043749](https://github.com/Shaugato/mainline/actions/runs/31728043749) is a
real 40-second run with a real job and **21 real steps**, and its verdict is FAILURE at
*"Cell 1/4 - plant ABSENT, cluster: the subset is GREEN today"* — the lane's first measurement in the
project's history, and worth more red than it was worth green.

**Standing guard:** `actionlint` in `ci.yml` is what catches this class, and it is green at
`1a6e10a`. The residual is not technical — see §10.4a.

### 10.4 Ten workflows' newest verdict describes a tree that is five commits old

Measured with `gh run list --workflow <name>.yml --limit 1 --json createdAt,conclusion,event` over all
twenty workflows:

| last event | workflow | conclusion | head |
|---|---|---|---|
| push 17:54Z | `ci`, `schema`, `cluster-tests`, `cluster-lane-bites` | failure | `1a6e10a` |
| push 17:54Z | `aws-evidence`, `submission` | success | `1a6e10a` |
| **dispatch 12:20Z** | `boundary`, `claims`, `console`, `judge-pack`, `release-proof`, `skills`, `supply-chain` | **success** | **`2dc5c86`** |
| **dispatch 12:20Z** | `custody-chain`, `db-schema`, `db` | failure | **`2dc5c86`** |
| schedule | `cloud-verify` success · `demo-health` failure · `nightly-differential` failure · `mutation-ratchet` in flight | — | — |

`git log --oneline 2dc5c86..origin/master | wc -l` → **5**. So **seven green ticks on the Actions tab
were earned against bytes five pushed commits behind `origin/master`**, and six behind the local
tree. Those lanes' `on: push: paths:` filters did not match the 17:54Z push, so they did not run;
nothing on the board says so, because a lane that did not run keeps showing its previous conclusion.

This is §10.3's category at repository scale, and it is the more dangerous form: §10.3's lane was at
least visibly odd (0 s, no jobs, named by path). **A stale green looks exactly like a fresh one.**

**Activation:** a push that touches each lane's `paths:` filter, or `gh workflow run <name>` at
`HEAD`. **What would end the class:** a board that prints each lane's `headSha` beside its
conclusion, so *green* and *green, five commits ago* stop rendering identically. Recorded, not built
— that summary belongs to `ci.yml`, which this worker does not own.

#### 10.4a A PROCESS finding, not a control finding — `actionlint` said so, and the file was pushed

`actionlint` reported at `e944407`, on the very run that produced §10.3's zero-second lane:

```
.github/workflows/cluster-lane-bites.yml:95:16: context "runner" is not allowed here.
  available contexts are "github", "inputs", "matrix", "needs", "secrets", "strategy", "vars"
```

**The control was correct, it fired, it named the file, the line, the column and the cure — and the
commit landed anyway.** Nothing in the tooling failed. What failed is the step between a red gate and
a push, and no assertion added to a workflow file can repair that. That is exactly why it is recorded
here as a PROCESS finding rather than added to the inert list above: the inert list is a backlog of
controls to strengthen, and filing this one there would produce another control nobody reads.

**Activation:** branch protection requiring `actionlint` on `master`, or a pre-push hook. Both are
repository settings, not repository code.

### 10.5 `cloud-verify` is green, and its Cloud job has never run

Run [31728207470](https://github.com/Shaugato/mainline/actions/runs/31728207470), jobs as reported by
`gh run view … --json jobs`:

```
success   the version comparison bites — a neighbouring tag must fail it
success   is there a Cloud cluster to verify against? (and can it say no?)
success   a real 40001 RETRY_SERIALIZABLE, and the loop that must not swallow it
success   SKIPPED — no Cloud cluster secret
skipped   conformance + fingerprint attestation, against Cloud
```

The last job is the one the workflow is named for, and it sits behind
`cloud-verify.yml:250  if: needs.preflight.outputs.has-cluster == 'true'`. Its complement at line 433
(`!= 'true'`) is the job that actually runs, and it succeeds. **The workflow's green is the green of
its own else-branch.** §4.3 already states the conclusion; this is the job-level measurement behind
it, taken fresh.

Two things in the design deserve credit and change nothing about the verdict: the else-branch job is
*named* `SKIPPED — no Cloud cluster secret`, so the skip is visible on the board rather than inferred;
and `cloud-verify.yml:221` greps its own file to assert that both `if:` clauses still exist, which is
a control against deleting the branch instead of satisfying it.

**Activation:** a CockroachDB Cloud cluster secret in the repository. Until then the honest reading of
this lane's green is *"the preflight can tell that there is no cluster"* — which is what its own job
name says.

### 10.6 `ci`'s hermetic job has no floor on the tests it collects

`grep -n "collected\|COLLECTED\|FLOOR" .github/workflows/ci.yml`: every hit is a comment recording a
tally (lines 124–135), the `red-by-design` job's `RED_FLOOR: "15"`, or the refusal at line 723 for a
RED selector that matched nothing. Line 647 states the policy in the file's own words — *"A floor on
FAILURES, never on collected tests"* — and that is correct **for that job**.

But the `hermetic-tests` job, the one that runs the whole suite, asserts only that nothing fails. Its
`--collect-only` step (*"Collection must cost a second, not a container"*, `ci.yml:529`) catches a
collection **error**, because a broken collection exits non-zero. It does not catch a collection
**collapse**. If a `conftest`, a `rootdir` change or a `pyproject` edit reduced the hermetic suite
from ~9,884 tests to 200, that job would be green.

The floor is not missing from the repository — it is missing from this lane. `cluster-tests.yml`
carries `COLLECTED_FLOOR` (445, deliberately not raised from a dirty-tree measurement). And one
indirect floor does exist here: `RED_FLOOR: 15` requires fifteen declared reds to still be collected
**and** failing in `red-by-design`, so a total collapse would be caught. **Fifteen of ~9,884 is the
whole of the protection.**

**Activation:** a `COLLECTED_FLOOR` on `hermetic-tests`, of the shape `cluster-tests.yml` already
uses. Recorded, not written: `ci.yml` is not this worker's file, and adding an assertion to another
lane's workflow inside a sweep commit is how a sweep becomes a merge conflict.

**STILL OPEN, re-measured 2026-08-14 at `eefae1c`, and the ratio has got worse.** Run 31735341191's
`hermetic-tests` printed `collected 10150 items` and `5 failed, 9052 passed, 1078 skipped, 15
deselected` — the four halves add to 10,150, which is how the parse was checked. So the sentence
above now reads **fifteen of 10,150**, not fifteen of ~9,884, and the unprotected population grew by
311 tests while the protection stayed at fifteen. `ci.yml` **is** this worker's file in the
lane-honest wave, and the floor was still not added: `COLLECTED_FLOOR` on `hermetic-tests` is a new
assertion on a lane that is currently red for other reasons, and landing it inside a
documentation-and-comments commit would make one commit that both records a state and changes what
CI asserts. The number it should be drawn under, measured on a runner rather than a workstation, is
**10,150**, and this paragraph exists so the commit that adds it does not have to re-derive it.

### 10.7 The one-way MI ratchet only runs on pull requests, and this repository does not use them

`db-schema.yml:753`, the step *"The ratchet is one-way"*, is guarded by
`if: github.event_name == 'pull_request'`. It is the check that an `enforced → pending` demotion in
`mi_catalogue.yaml` carries an `ADR-NNNN` in the commit body — *"a mechanism that stops being enforced
is a decision about what this system no longer promises"*. It needs
`github.event.pull_request.base.sha` to diff against, which is why it is PR-only.

Measured over the 200 most recent runs (`gh run list --limit 200 --json event`):

```
Counter({'workflow_dispatch': 99, 'push': 85, 'schedule': 16})     # pull_request: 0
```

`gh run list --event pull_request` finds runs only on **2026-08-10** and **2026-08-11**, and both sets
come from one dependabot branch (`dependabot/github_actions/actions-e016cff95b`, *"ci: bump the
actions group"*). **No human change has ever reached `master` through a pull request.** Every commit
in `git log` since is a direct push. So the demote-check has never examined a hand-written commit,
and a demotion landed by push today would go unchecked.

This is the sharpest instance in the tree of *an assertion behind an `if:` that is never true*,
because unlike §10.5 it has no else-branch announcing itself on the board — it simply does not appear.

**Activation:** changes land through PRs, **or** the step gains a push path that diffs against
`github.event.before` instead of `base.sha`. Recorded and handed to the `db-schema` owner: changing
the guard changes what the assertion asserts, which is not a documentation edit.

### 10.8 `check_reuse.py` has four units of ceiling slack, and reports it as an improvement

`python scripts/qa/check_reuse.py` at this tree ends:

```
REUSE.toml globs matching no TRACKED file (1) — counted, may not rise:
    #4:packages/**/*.jsonl  <- matches nothing on disk either
  improved   metric=reuse_toml_patterns_matching_nothing baseline=5 measured=1
OK — 7471 tracked files, 0 uncovered, 4 licence texts, no counted number rose.
```

Measured **1**, ceiling **5**, exit **0**. Four dead licence globs could be added to `REUSE.toml`
today without this checker saying a word — and a dead glob is precisely a licence declaration
covering nothing, which is the defect the metric exists to count. The word `improved` is doing the
work a red would do elsewhere.

This is the general shape the sweep was asked to find — *a ratchet whose ceiling sits above its
measured value* — and it is the only live instance in `qa/`. `qa/skip-ratchet.json` is at 730/730 and
`check_pytest_lanes.py` at 26/26, both zero-slack. (`qa/ruff-ratchet.json` is a different condition:
it is currently **red** against the working tree on sixteen counters, all in files other workers in
this wave are still editing. Red is not vacuous, so it is not on this list. `ruff check` and
`ruff format --check` are both clean on the two files this worker landed.)

**Activation:** lower `reuse_toml_patterns_matching_nothing` to 1 in the baseline `check_reuse.py`
reads. Not done here: the baseline belongs to that checker's owner, and a ceiling is an assertion.

### 10.9 The census lands without its producer — this lane's own soft spot, in its own words

`qa/ci-skip-census.json` (580 KB, `generated_utc: 2026-08-13T12:04:05Z`, 512 s of wall clock to
produce) is committed by this worker. Its producer, `scripts/qa/ci_skip_census.py`, is **on disk and
untracked**, and is not on this worker's owned-path list, so it is reported rather than reached for.

`qa/skip-ratchet.json` states the consequence itself, in its own `caveats` block:

> *"THIS RATCHET IS ONLY AS FRESH AS THE CENSUS IT READS… a cluster-backed test added AFTER the census
> was taken is invisible to this checker until the census is re-taken. `scripts/qa/ci_skip_census.py
> --check` is the guard against that, and it is a separate claim owned by a separate file. The two
> together are the whole assertion; either alone is half of it."*

**After this commit the tree carries exactly one half.** The ratchet reads a frozen snapshot, nothing
in CI can re-derive it, and a stranger cannot reproduce it. That is the same shape as
`qa/cluster-known-red.json` describing a `cr_id` cause on a tree whose real cause had already moved to
`commit_v2` — a record going stale against its own tree, which this wave has had to repair once
already.

The file's second caveat measures the drift rate directly: *"At 12:33 UTC the collection was 9839;
forty minutes later it was 9894, because other workers landed test files."* **55 tests in 40 minutes.**

**Activation:** track `scripts/qa/ci_skip_census.py` and run `--check` in a lane. Landing the census
half alone is still net positive — 974 cluster-shaped skips now carry a published, non-raisable
attribution where before they carried none — but the claim reads as twice what it is, and this page is
where that gets said out loud.

### 10.10 `qa/skip-ratchet.json` declares one licence and `REUSE.toml` resolves another

`qa/skip-ratchet.json` carries, in band:

```json
"SPDX-License-Identifier": "CC-BY-4.0",
```

`REUSE.toml`'s block for `qa/*-ratchet.json` assigns **`Apache-2.0`**, and its own comment explains
why that block exists: `qa/mypy-ratchet.json` and `qa/test-state.json` declare Apache-2.0 as ordinary
JSON keys, and *"REUSE reads comment headers, not JSON keys, so a checker sees those two files as bare
and this file would otherwise hand them CC-BY-4.0 and contradict their own text."*

`qa/skip-ratchet.json` matches that glob and declares the opposite licence, so the block written to
prevent a contradiction now produces one. **No tool can see it:** `check_reuse.py` reads comment
headers, so the in-band key is invisible to it and the run is green (7,471 tracked files, 0
uncovered).

**Left alone, deliberately.** Both candidate edits — changing the JSON's key, or narrowing
`REUSE.toml`'s glob — move a declaration to match a derived one, and which side is authoritative is a
licensing decision rather than a mechanical one. `REUSE.toml` is not this worker's file either.
`qa/ci-skip-census.json` is unaffected: it matches the `qa/*.json` block, which is CC-BY-4.0, and
agrees with itself.

**Activation:** a ruling on the licence for QA ratchet artefacts, applied to whichever side is wrong,
in a commit that says which.

### 10.11 What this checker cannot see, stated before somebody else has to find it

* **One scanner, two checkers.** A pytest invocation written in a shape
  `skip_ratchet._is_invocation` does not match is invisible to **both** registry checkers at once.
  Today that set is empty — proven by the 130-line raw-grep cross-check in §10.0 — but **that proof
  was taken by hand and is not in CI**, so it decays. *Activation: land the cross-check as a test.*
* **`MARKER_REACH = 40`.** The furthest a real marker legitimately sits above its invocation is 33
  lines (`cluster-tests.yml:258` governing the pytest at line 291, in the comment block above the
  step's `- name:`, which Contract A permits). A marker further than 40 lines from any invocation is
  refused as an ORPHAN, which fails closed; but a marker 40 lines above an unrelated later pytest
  step would bind to it. *Activation: a control that plants a marker above a non-pytest step
  followed by a pytest step.*
* **`unlanded` has its own ceiling, at 0.** Contract A's escape hatch is honest — declared, with a
  reason — and it is still a pytest step nobody executes, so it may not be used to empty
  `UNDECLARED_CEILING`. Nothing uses it today. *Activation: it is at zero slack; the first use
  refuses.*
* **Renaming a job resets its lane key**, so a rename is refused twice over: the new key exceeds an
  implicit ceiling of 0, and the old key's ceiling now shows slack. Fails closed in both directions,
  by construction.

### 10.12 Three hypotheses these sweeps tested and REFUTED — recorded so nobody re-runs them

* **"Lanes triggered only by `schedule` that have never actually fired."** There are exactly two
  schedule-only workflows — `cloud-verify` and `demo-health` — and both have fired: `cloud-verify`
  run 31728207470 (`event: schedule`, success, 2026-08-13T17:56Z) and `demo-health` run 31727356338
  (`event: schedule`, failure, 17:46Z, with 72+ runs behind it). Five more (`boundary`,
  `mutation-ratchet`, `nightly-differential`, `schema`, `supply-chain`) carry a `schedule` trigger
  alongside `push`. **No never-fired schedule lane exists.** The real defect in this neighbourhood is
  §10.4, and it is about `push` filters, not about `schedule`.
* **"`on: pull_request` has never fired anywhere."** False — see §10.7. It has fired, on two days, for
  one dependabot branch. The precise finding is narrower and stronger than the hypothesis, and
  stating the narrow version is the point: *no human change has ever reached `master` through a PR*,
  which is what makes `db-schema.yml:753` inert without making sixteen `on: pull_request` triggers
  dead.
* **ADDED 2026-08-14 — "every pytest lane without a `--crdb` flag silently skips its cluster
  tests."** **Refuted for five of seven lanes and confirmed narrowly in three places**; the full
  measurement, the collection counts that support it and the three places are in **§10.16 and
  §10.17**. It is listed here as well as there because this bullet list is where a reader goes to
  find out which plausible-sounding claims have already been tested, and the third one has the
  same shape as the first two: *the blanket version is false, the narrow version is the finding.*

### 10.13 Adjacent, measured, and owned by somebody else

* **`qa/cluster-known-red.json` was still untracked when this was measured**, while
  `cluster-tests.yml` and `cluster-lane-bites.yml` both read it. `scripts/ci/cluster_lane_report.py`,
  `scripts/ci/plant_cluster_defect.py` and `tests/ci/test_demo_seed_is_frozen.py` had landed with W2;
  the inventory belongs to W5. Until it lands, both cluster lanes fail at a clean checkout on a
  missing file — the same defect one level down that ruling R3 named. Recorded, not committed: it is
  not this worker's path.
* **The demo-api suite moved under this worker twice inside one hour, and not because of this
  worker.** All three readings are from `--junitxml`, never from a terminal scroll, on
  `pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q -p no:cacheprovider`:

  | reading | collected | executed | skipped | failed | errors | passed | wall |
  |---|---|---|---|---|---|---|---|
  | lane lead's baseline | 524 | 523 | 1 | 6 | **63** | 454 | 46.2 s |
  | this worker, 04:13 | 528 | 527 | 1 | 7 | 0 | 520 | 41.6 s |
  | this worker, 04:40 | 528 | 527 | 1 | **1** | 0 | **526** | 44.1 s |

  The 63 `commit_v2` setup errors disappeared before this worker's first reading, and six of the
  seven `test_reads.py` failures disappeared between the two — both from the suite-green lead's work
  landing in the same working tree. **Neither movement is attributable to this worker's change**,
  which adds two programs under `scripts/qa/`, two JSON files under `qa/`, and this section: nothing
  the demo-api suite imports or reads. The residual single failure is
  `test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`.

  Recorded in this shape because §10.9's own caveat is about exactly this: a number measured while
  six workers write to one tree describes a tree that no longer exists by the time anybody reads it,
  and a single "after" figure would have implied a causation that the timestamps refute.

### 10.14 The `--crdb` census: sixteen of twenty workflows run pytest without ever saying which side of the cluster line they are on

**Measured 2026-08-14 by W6 of the lane-honest wave, at HEAD `eefae1c`.** The census is taken
against `git show eefae1c:<file>` rather than against the working tree, deliberately: five other
workers are writing to this directory and a lane that exists only on disk has no run id, so it
cannot appear on a board (§0.2).

```
$ for f in $(git ls-files .github/workflows/); do
    echo "$(basename $f)  none=$(git show eefae1c:$f | grep -c -- --crdb=none)"\
         " reuse=$(git show eefae1c:$f | grep -c -- --crdb=reuse)"
  done
```

**Exactly four of the twenty pass a `--crdb` flag at all:**

| workflow | `--crdb=none` | `--crdb=reuse` |
|---|---|---|
| `ci.yml` | 20 | 0 |
| `cluster-lane-bites.yml` | 13 | 10 |
| `cluster-tests.yml` | 4 | 3 |
| `release-proof.yml` | 4 | 0 |

Every other pytest-running lane — `boundary`, `custody-chain`, `db-schema`, `mutation-ratchet`,
`nightly-differential`, `schema`, `supply-chain` — runs pytest with **no `--crdb` mode**, so it
runs at the testkit default and a cluster-backed test there skips on whatever the environment
happens to hold. `check_pytest_lanes.py` (§10.0) already refuses a step that declares a lane its
command contradicts; **it does not yet require a step to pass a mode at all**, and that is the
gap this row names.

**Two corrections to the census this sweep was handed, both measured rather than argued:**

* **`db.yml` runs no pytest whatsoever.** Its only occurrence of the word is `".pytest_cache"`
  inside a directory-exclusion list at `db.yml:282`. It runs the conformance suite through the
  `trappoint-conform` CLI (`db.yml:525`, `:530`) — a different program over a different input —
  so it belongs on no list of pytest lanes, and putting it on one would have made a green look
  like a pytest green that it never was.
* **A fifth `--crdb` lane is arriving and has no run id.** In the working tree at the time of
  writing, `cloud-verify.yml` carries `3 × --crdb=none` and `4 × --crdb=reuse` and eleven pytest
  lines; at `eefae1c` it carries **zero of each**. Uncommitted, absent from the remote, never
  dispatched. Named here so the next census does not read it as drift, and **not credited**: a
  repair without a run id is a plan.

### 10.15 Every pytest-running lane, with the pass/skip split read out of its own newest run

**A skip census is only evidence if you read it out of the run.** Each row below is the pytest
summary line the job actually printed, recovered with `gh run view <id> --log` and parsed for
`SKIPPED [n] …` lines rather than for a rollup. Where a lane runs several pytest steps, every
step is listed, because a lane-level total hides which step was the empty one.

| lane | newest run | head | conclusion | measured pytest outcome, per step |
|---|---|---|---|---|
| `ci` | [31735341191](https://github.com/Shaugato/mainline/actions/runs/31735341191) | `eefae1c` | failure | hermetic: **5 failed, 9052 passed, 1078 skipped, 15 deselected** in 349.02s, from `collected 10150 items` · red-by-design: **15 failed, 10135 deselected** in 20.43s |
| `cluster-tests` | [31735341117](https://github.com/Shaugato/mainline/actions/runs/31735341117) | `eefae1c` | failure | **1 failed, 517 passed, 10 skipped** in 154.21s (§6.5) |
| `cluster-lane-bites` | [31735341050](https://github.com/Shaugato/mainline/actions/runs/31735341050) | `eefae1c` | failure | `7p/71s` · `7p/71s` · `77p/1s` · `3f/74p/1s` · control `3f` · freeze `2f/1p` (§5.7) |
| `release-proof` | [31699585931](https://github.com/Shaugato/mainline/actions/runs/31699585931) | `2dc5c86` | success | **15 skipped** in 0.24s (the control), then **15 passed** in 44.49s (§5.7) |
| `boundary` | [31738665393](https://github.com/Shaugato/mainline/actions/runs/31738665393) | `eefae1c` | success | 7 steps: `11p/2s` · `12p` · `14p/1s` · `16p` · `32p/1s` · `38p` · `56p` = **179 passed, 4 skipped** |
| `custody-chain` | [31735341212](https://github.com/Shaugato/mainline/actions/runs/31735341212) | `eefae1c` | failure | `82p` · `285p` · `95p` · `11p` · `1p` · `17p` in 28.82s · `2f/11p/2s` = **502 passed, 2 failed, 2 skipped** |
| `db-schema` | [31735341076](https://github.com/Shaugato/mainline/actions/runs/31735341076) | `eefae1c` | failure | mi-red: **7 failed, 460 passed** in 102.06s · catalogue: **299 passed, 1 skipped** · **1 passed** |
| `schema` | [31735341105](https://github.com/Shaugato/mainline/actions/runs/31735341105) | `eefae1c` | failure | **23 passed, 2 deselected** in 0.70s — and the `-m schema` step **never reached** (§5.8) |
| `supply-chain` | [31735341020](https://github.com/Shaugato/mainline/actions/runs/31735341020) | `eefae1c` | success | **61 passed, 0 skipped** in 1.42s |
| `mutation-ratchet` | [31729443279](https://github.com/Shaugato/mainline/actions/runs/31729443279) | `1a6e10a` | success | **1072 passed, 0 skipped** in 32.56s |
| `nightly-differential` | [31720904696](https://github.com/Shaugato/mainline/actions/runs/31720904696) | `e944407` | failure | `11p` · **1 failed** in 1803.15s · `11p` in 18.94s · `11p` · **1 failed, 1 passed** in 1813.04s — **0 skipped** |
| `db` | [31735341068](https://github.com/Shaugato/mainline/actions/runs/31735341068) | `eefae1c` | failure | **no pytest step exists in this lane** (§10.14) |

**Four of these totals are exact against a local collection, which is how the parse was checked
rather than trusted.** `mutation-ratchet`'s 1072 equals `tests/e2e/mutation` (967) +
`tests/unit/domain/novelty` (105) collected here; `boundary`'s 179 + 4 equals `tests/boundary`
(127) + `packages/mainline-boundary/tests` (56) = 183; `supply-chain`'s 61 equals
`test_no_model_in_closure.py` (61); `db-schema`'s 299 + 1 equals `packages/trappoint-migrate/tests`
(300). A parser that agreed with none of them would be reporting its own bugs as findings.

### 10.16 The hypothesis this sweep was given, and what the measurement did to it

**The hypothesis:** *"every pytest lane without a `--crdb` flag silently skips its
`requires_cluster` tests, so its green says nothing about the database."*

**REFUTED for five of the seven lanes, and for a reason that is better news than the hypothesis.**
Counted with `pytest --crdb=none <lane's own target paths> -m requires_cluster --collect-only -q`
on the pinned interpreter:

| lane's target paths | tests collected | of which `requires_cluster` |
|---|---|---|
| `tests/boundary` + `packages/mainline-boundary/tests` | 183 | **0** |
| `packages/trappoint-jcs` + `-ledger` + `-verify` | 462 | **0** |
| `tests/e2e/mutation` + `tests/unit/domain/novelty` | 1072 | **0** |
| `verticals/…/mainline-gate-svc/tests/test_no_model_in_closure.py` | 61 | **0** |
| `packages/trappoint-migrate/tests` | 300 | **0** |
| `packages/trappoint-conformance/unweld` | 4 | **0** |
| `tests/integration/custody` | 62 | **12** |
| `packages/trappoint-model/tests` | 33 | **14** |
| `tests/concurrency/test_single_merge.py` | 4 | **4** |
| `tests/concurrency/test_retry_taxonomy_spy.py` | 7 | **1** |

**A lane cannot silently skip a cluster test it never collects.** `boundary`, `supply-chain`,
`mutation-ratchet` and `db-schema` point pytest at directories that hold **zero** cluster-backed
cases, and their four measured skips (`boundary` 4, `db-schema` 1) are all environment or
artefact skips carrying written reasons — a live-IAM simulation, a missing kernel SBOM, an
unshipped fleet register, an uninstalled `trappoint-sql`. **Not one is cluster-shaped.**

**And the two lanes that DO collect cluster-backed cases both stand a node up and execute them.**
`custody-chain` ran `tests/integration/custody/nemesis` as **17 passed in 28.82s** against a
pinned container; `nightly-differential` ran `tests/concurrency/test_single_merge.py` +
`test_retry_taxonomy_spy.py` as **11 passed in 18.94s**, and its `trappoint-model` differential
arms for 1803 s and 1813 s each. **Neither lane reports a single skip.** The hypothesis predicted
silence and the runs show execution.

**CONFIRMED, narrowly, in exactly two places — and both are named in the next two entries.** The
narrow version is the finding: *stating that no non-`--crdb` lane skips a cluster test would have
been as wrong as the blanket hypothesis*, and §10.12 already established that the narrow form of a
refuted hypothesis is usually the real one.

### 10.17 Three cluster-backed assertion sets that no lane executes, named individually

**(a) `tests/integration/custody/test_custodian_attestation.py` — 19 tests, 3 of them
`requires_cluster` — is run by NO `custody-chain` step.** The lane runs
`tests/integration/custody/test_ledger_append.py` (11), `…/nemesis` (17) and `…/test_k2_exit.py`
(15) — 43 of the directory's 62 — and never names the fourth file. `custody-chain` stands a
CockroachDB up for the nemesis job, so the node exists and those 3 assertions do not reach it.
They are collected by `ci`'s hermetic lane instead, where they skip. **Activation:** the lane runs
the directory rather than three files out of four, or the omission is enumerated with a reason.

**(b) `custody-chain`'s `test_k2_exit.py` step skips 2 cluster-backed cases INSIDE a lane that has
a node up**, because the step lives in a job that exports no DSN. From the run's own output:

```
SKIPPED [1] tests/integration/custody/test_k2_exit.py:607: SKIP(no-cluster): requires a
disposable single-node CockroachDB. Green from K2 onward via …/nemesis/test_gate_attacks.py.
SKIPPED [1] tests/integration/custody/test_k2_exit.py:615: SKIP(no-cluster): reads the live
schema for row-level TTL on any ledger_* table.
```

**Credit where it is owed: the first skip names the file that covers it instead**, which is the
only form of skip that is not a hole. The second names no substitute. **Activation:** the step
moves into the job that stands the node up, or the second skip gains a cover-note or an entry in
`qa/skip-ratchet.json`.

**(c) The conformance `db` tier — 181 cases in `packages/trappoint-conformance/tests/
test_conformance_cases.py` — is executed by no lane under pytest.** `ci`'s hermetic run skipped
**180** of them, in four groups of 45, each printing:

> *"SKIP WITH REASON: no `TRAPPOINT_DSN` or `LOCAL_DSN`. These assertions are about what a
> database does; without one there is nothing to assert…"*

`schema`'s conformance job runs a different 25 (`23 passed, 2 deselected`). `db.yml` exercises the
conformance CASES through the `trappoint-conform` CLI against a live node — a real check, and a
different program over a different input, so it is not this pytest tier. **180 skipped in CI
against 181 collected here: the one-case difference is not smoothed**, it is what a moving tree
looks like, and both numbers carry the command that produced them. **Activation:** a lane points
`packages/trappoint-conformance/tests` at a DSN, or the tier is declared `unlanded` with a reason
under Contract A.

### 10.18 The board, re-swept — every workflow's newest run with its head, which is what §10.4 asked for

§10.4 named the class *"a stale green looks exactly like a fresh one"* and said what would end it:
**a board that prints each lane's `headSha` beside its conclusion.** Measured 2026-08-14 with
`gh run list --limit 60 --json workflowName,conclusion,event,databaseId,headSha`:

| head | workflows whose newest run is there | conclusion |
|---|---|---|
| `eefae1c` (local HEAD, public tip) | `boundary` · `supply-chain` | **success** |
| `eefae1c` | `ci` · `cluster-tests` · `cluster-lane-bites` · `custody-chain` · `schema` · `db` · `db-schema` · `aws-evidence` · `claims` · `submission` · `demo-health` | failure |
| `1a6e10a` (1 commit behind) | `cloud-verify` · `mutation-ratchet` | success |
| `e944407` (2 behind) | `nightly-differential` | failure |
| **`2dc5c86` (5 behind)** | **`console` · `judge-pack` · `release-proof` · `skills`** | **success** |

**Four green ticks on the Actions tab were earned against bytes five pushed commits old.** That is
down from §10.4's seven — `boundary` and `supply-chain` have since run at `eefae1c` — so the class
has narrowed rather than closed, and the four that remain are named.

**Three lanes turned red at `eefae1c` that the `2dc5c86` board recorded green**, and they are
listed by their own job names so nobody has to guess which half moved:

```
claims       31735341024   4 jobs success · FAILURE :: claim hygiene (red half, then green half)
submission   31735341080   2 jobs success · FAILURE :: a stranger can clone it, and every file names a licence
aws-evidence 31735341177   FAILURE :: all three jobs, including "the red half is red for the reason it claims"
```

`aws-evidence` is the one that matters most: §4.1 and §5.3 record its plant family as the
strongest anti-vacuity statement on this board, and **all three of its jobs are now red at
`eefae1c`**, so that claim is currently unverified at the tip. §4.1's measurement is not deleted —
it was true at `2dc5c86` — but it may not be quoted as a statement about `eefae1c`. Owner: the AWS
evidence lead. Recorded, not fixed.

### 10.19 This worker's own numbers, and the tree that moved under them

Both readings are from `--junitxml`, from the `<testsuite>` element's attributes, never from a
terminal scroll, on
`pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q -p no:cacheprovider`:

| reading | collected | executed | skipped | failed | errors | passed | wall |
|---|---|---|---|---|---|---|---|
| lane-honest lead's §1.1 baseline, 2026-08-14 early | 528 | 527 | 1 | 1 | 0 | 526 | 170.5 s |
| **W6 BEFORE**, 2026-08-14T12:08:59+10:00 | **570** | **570** | **0** | **30** | **13** | **527** | 158.8 s |
| **W6 AFTER**, 2026-08-14T12:28:37+10:00 | **570** | **570** | **0** | **30** | **13** | **527** | 128.7 s |

**Every column is identical, and so is the set behind it.** The two JUnit reports were compared
node id by node id, not count by count: **43 `<testcase>` elements carry a `<failure>` or an
`<error>` in each, and the two sets of 43 are equal — nothing only-before, nothing only-after.**
Equal totals over different sets is the failure mode that a totals-only comparison cannot see, and
it is worth the six lines of parsing to exclude it. The 30 s of wall clock is a warm page cache.

**The BEFORE this worker was handed was 528/527/1/1/0 and the BEFORE this worker MEASURED was
570/570/0/30/13.** The gap is not a regression and it is not this worker's: between the two
readings the judge-can-sign lead landed `test_defeaters.py` (29 cases) and `test_judge_can_sign.py`
(13) into the working tree, untracked, and modified `test_transitions.py`,
`test_row_factory_contract.py` and `test_gate_run.py`. `qa/cluster-known-red.json` calls that tree
**"epoch-2"** in its own words and says of four `test_transitions.py` ids: *"On the UNCOMMITTED
epoch-2 tree this id fails 17 of 17 runs, in every arm, order and database W4 measured. A failure
present in every run is not instability, this exemption does not describe it."* **The handed-down
BEFORE is preserved above rather than replaced**, because a worker who quietly adopts a
better-looking baseline has deleted the evidence that the tree moved.

**This worker's change cannot touch either number.** It edits `docs/CI-STATE.md` and appends
comment lines to `.github/workflows/ci.yml`; the demo-api suite imports neither. The AFTER is
reported for the arithmetic, not as a claim of causation — the same shape §10.13 used, and for the
same reason.

**One number this worker did move, and the direction it moved in.** `ci.yml` gains a third dated
collection reading — **15 / 10135 / 10150 at `eefae1c`**, taken from CI run 31735341191's own
output rather than from a workstation — appended beside the two readings already there. The
`13 / 9240 / 9253` block is untouched, `RED_FLOOR` is still **15**, and the diff is
**60 insertions, 0 deletions**. The collection moved **9839 → 10150, which is +311**; a figure of
+430 was in circulation and came from comparing the live number against a dirty tree. A local
re-run on this working tree gives **15 / 10196 / 10211**, and the 61-test difference is accounted
for by name: four untracked test files collect exactly 61 (`test_txn.py` 17,
`test_seed_permit_needs_retry.py` 2, `test_defeaters.py` 29, `test_judge_can_sign.py` 13).
**Four collections, four different trees, one `RED_FLOOR`.**
