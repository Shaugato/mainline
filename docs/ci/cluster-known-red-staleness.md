<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `qa/cluster-known-red.json` is stale in both directions — the four entries, by name

**Worker:** D3, DOCS-TRUE wave. **Date:** 2026-08-14.
**Subject:** `qa/cluster-known-red.json` **at the public tip `7535670`**, which is the copy CI
executed and the only copy a stranger can read.
**Measured from:** GitHub Actions run
[31770005759](https://github.com/Shaugato/mainline/actions/runs/31770005759) (`cluster-tests`,
push, head `7535670`, 2026-08-14T04:29:07Z) and `git show 7535670:qa/cluster-known-red.json`.

> **THIS DOCUMENT DOES NOT EDIT THAT FILE AND MUST NOT BE READ AS AUTHORISING AN EDIT TO IT.**
> `qa/` is outside this wave's ownership entirely. What is owed here is a written record
> precise enough that the file's owner cannot say nobody told them: the entries by node id, the
> contradiction in the file's own words, and the exact mechanism by which a stale entry becomes
> invisible. **A stale exemption that everybody has read about is still a stale exemption.**
> Naming it is not fixing it, and this page does not claim to have fixed anything.

---

## 0. The finding, in one sentence

> **At `7535670` the inventory carries one `groups` entry whose stated cause is fixed and four
> `unstable` entries that all passed in the same run — and `unstable` is the one category the
> lane's ceilings do not police, so four node ids sit in the only bucket where being wrong
> costs nothing.**

The lane itself said so, in a `::notice`, in that run:

```
##[notice] 4 declared-unstable test(s) passed this run. If the cross-test contamination
           behind them has been fixed, delete them from qa/cluster-known-red.json — an
           exemption nobody is reminded of becomes permanent.
```

**That notice is the mechanism working.** The file is not hiding; it asked to be pruned. What
follows is the audit it asked for.

---

## 1. The run this is measured against

```
cluster lane: 570 collected, 569 executed, 1 skipped, 8 failed, 0 errored
inventory: 1 known, 0 still failing, 1 now passing, 4 declared unstable, 8 NEW
```

Read out of run 31770005759's job log, job `94673769475`, with
`gh api "repos/Shaugato/mainline/actions/jobs/94673769475/logs"` — the whole job log rather
than `--log-failed`, because the inventory verdict is printed by the report step and a
`--log-failed` bundle can drop it.

---

## 2. THE STALE `groups` ENTRY — one entry, one node id, cause fixed

The `groups` list held exactly one entry at `7535670`. Its node id and its recorded cause:

| field | value |
|---|---|
| `nodeid` | `verticals/mainline/apps/demo-api/tests/test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements` |
| `cause` | *"`AssertionError: assert set() == {'MECHANISM_PRESENT_AND_VERIFIED', 'SCOPE_EXCLUDES_HAZARD'}` at `test_reads.py:414` — `{option['defeater_code'] for option in data['defeater_options']}` is EMPTY because `mainline.defeater_option` holds zero rows."* |
| `owner` | *"the demo-seed lead (blocker 1: `mainline.defeater_option` holds zero rows)"* |

**`mainline.defeater_option` no longer holds zero rows.** It is seeded in three places at
`7535670` — `demo_permit.sql` (check `0007`), `demo_world.sql` (check `000d`) and
`scripts/proof/gate_refusal.py` — each with a digest aggregated from its own rows. The lane
agreed, in the same run:

```
FIXED  [disposition-defeater-vocabulary-is-not-seeded]
       verticals/mainline/apps/demo-api/tests/test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements
```

and then made removal mandatory rather than optional, in an `::error`:

```
##[error] …test_the_disposition_carries_the_lattice_and_the_projected_requirements. Remove
them from qa/cluster-known-red.json in the commit that fixed them. This list is a ceiling
that must reach empty, and a ceiling nobody is made to lower is a ceiling that never falls.
```

**`groups` is policed.** A `groups` id that passes is a hard failure of the lane, which is why
this entry is loud. **The four below are not**, and that asymmetry is the whole of §3.

---

## 3. THE FOUR `unstable` ENTRIES, BY NAME — and the category no ceiling polices

All four are in `verticals/mainline/apps/demo-api/tests/test_transitions.py`. All four
**passed** in run 31770005759. Every figure in the table is read from the committed file at
`7535670`, not restated from a summary:

| # | node id (`test_transitions.py::…`) | `runs_observed` | `runs_failed` | added |
|---|---|---:|---:|---|
| 1 | `test_gate_run_is_reachable_through_handle_transition` | 19 | 2 | published earlier; counts folded 2026-08-14 |
| 2 | `test_the_request_after_a_gate_run_is_not_a_503` | 22 | 1 | **added 2026-08-14** by W3 on W4's measurement |
| 3 | `test_suspending_a_merged_permit_commits` | 19 | 1 | published earlier; counts folded 2026-08-14 |
| 4 | `test_the_request_after_a_sign_disposition_is_not_a_503` | 19 | 1 | published earlier; counts folded 2026-08-14 |

### 3.1 The contradiction, quoted from the file's own text

The file does not conceal this. It states it, in `policy`, under a key whose name is the
finding — and this is quoted verbatim rather than summarised, because a paraphrase of a
self-accusation is always kinder than the original:

> **`policy.an_unstable_label_is_not_a_verdict_on_a_deterministic_failure`:** *"READ THIS
> BEFORE TRUSTING AN `unstable` LABEL IN A LOG TAKEN AFTER 2026-08-14T23:24Z. All four
> `unstable` node ids are ALSO failing deterministically on the uncommitted epoch-2 tree
> described in `measured.re_measured[2]` — 17 runs of 17, in every arm, every order and every
> database W4 measured. That is not instability and this file does not claim it is."*

And on **each of the four entries**, under `not_covered_by_this_exemption`:

> *"On the UNCOMMITTED epoch-2 tree this id fails 17 of 17 runs, in every arm, order and
> database W4 measured. A failure present in every run is not instability, this exemption does
> not describe it, and it must be reported as a defect … rather than absorbed here."*

**So the file is right about itself and the entries are still a hazard.** The disclaimer lives
in a `policy` key and in a per-entry field; the **label** lives in the machine-readable
`unstable` list that `scripts/ci/cluster_lane_report.py` reads. A reader of the log sees
`(unstable, passed this run)`. A reader who wants the disclaimer has to open the JSON and
find a key called `an_unstable_label_is_not_a_verdict_on_a_deterministic_failure`. **A caveat
that is not on the same surface as the claim it qualifies is a caveat that will be missed.**

### 3.2 One internal inconsistency, reported and not corrected

`policy.an_unstable_label_is_not_a_verdict_on_a_deterministic_failure` dates the epoch
boundary **`2026-08-14T23:24Z`**. `how_the_unstable_counts_were_folded` dates the same
instant **`2026-08-13T23:24:25Z`** — *"at 2026-08-13T23:24:25Z, mid-battery, the judge-can-sign
lead's uncommitted rewrite … appeared"*. One of the two is a typo of the other. **This
document does not decide which**, because deciding would mean re-typing a digit inside
somebody else's dated record, and the wrong guess would make a false history look consistent.
`evidence/qa/transitions-stability.json` is the artefact that settles it and its owner is the
demo-suite lead.

### 3.3 Why `unstable` is the bucket where being wrong is free

Stated as a mechanism rather than an accusation, from the file's own `policy` block:

* **`groups` is a ceiling.** *"a node id there that PASSES is a hard failure telling whoever
  fixed it to delete the line."* Observed working in §2.
* **`unstable` is exempt from that ceiling**, and the file says so, immediately followed by
  the sentence that limits the exemption: *"`unstable` entries are exempt from the CEILING
  check and from nothing else — they still fail pytest, and pytest still fails the lane."*
* **The schema has two teeth and they are real.** An entry without `runs_observed`/`runs_failed`
  is refused, and so is an entry that *"failed every run it was seen in"*. Both fired
  correctly: the 2026-08-14 fold moved the four entries from 1/3, 1/3, 1/3 and unlisted to
  **2/19, 1/19, 1/19 and 1/22** — *further* from the schema edge, which the file argues is
  "the direction an honest fold should push a claim it did not reproduce."

**So nothing here is a suppression and nothing here is a green bought cheaply.** The exit
status is pytest's, unconditionally. The exposure is narrower and more specific: a
deterministic failure of an in-flight tree was described using a word — *unstable* — that
means something else, the file itself says so in prose, and no mechanism enforces the prose.
**Four node ids are therefore sitting under a label their own file disowns.**

---

## 4. What this document asks for, and who it asks

**Owner:** the demo-suite lead, named on every one of the four entries as `owner`.

1. **Delete the one `groups` entry**, in the commit that acknowledges the fix, exactly as the
   lane's `::error` instructs. Its cause is gone.
2. **Re-measure the four `unstable` entries against the tree that will actually ship**, and
   then either delete them (if the epoch-2 breakage is resolved and the flake does not
   reproduce) or **re-file them as defects with an owner** (if 17-of-17 still holds). The one
   thing `unstable` may not remain is a resting place for a deterministic failure — the file
   says this about itself in two separate keys.
3. **Do not delete an entry because it passed once.** The file's own R7 reasoning is right and
   is adopted here without qualification: an `unstable` entry is a claim about a
   **distribution**, and one green run does not refute it. Run 31770005759 is one run.
   `docs/CI-STATE.md` §6.7 makes the same point in the same words.

**And the thing that is NOT asked for, stated so it cannot be inferred from silence:** nobody
should raise `floor.max_skipped`, lower `floor.min_executed`, or add any of the eight `NEW`
failures of run 31770005759 to `groups`. Those eight are a real finding of a real build
(`docs/CI-STATE.md` §6.8.2), and the file's own rule for them already exists:

> **`policy.what_this_file_may_never_become`:** *"A place to put a test that started failing.
> Every entry below names a defect that existed before this lane did, is owned by a named
> lead, and is expected to be DELETED from here rather than to live here. A new failure is
> reported NEW."*

---

## 5. The state of the working tree, recorded because it is not the state of the repository

At the moment of writing, `qa/cluster-known-red.json` in this working directory has already
been pruned: `unstable` reads `[]`, `floor.min_executed` reads `518`, and two new keys —
`last_pruned_utc`, `last_pruned_by` — exist that are absent at `7535670`.

**That is a plan, not a result, and this document counts it as one.** It is uncommitted or
unpushed, it has no run id, and `docs/CI-STATE.md` §0.2's rule governs: *a repair without a run
id is a plan, and this page counts plans as red.* **Everything in §§2–4 above is written about
`7535670`, which is what a judge can fetch.** When the prune lands and a `cluster-tests` run
reports `0 declared unstable`, that run id belongs here and this section becomes the BEFORE.
