<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The script — what each file is for, and which one wins

Six files, one schedule. The division exists because three of the four failure modes that end
a hackathon entry are *silent*, and a silent failure has to be turned into arithmetic before it
can be caught.

| File | Holds | Generated? |
|---|---|---|
| `SHOT-LIST.yaml` | the submission cut: 25 shots, 2:51, each tagged to the milestone that must be complete for it to exist, each with a fallback | no |
| `SHOT-LIST-MWS.yaml` | the Minimum Winnable Submission: 22 shots, 2:38, four beats | no |
| `VO.md` | the locked voice-over, and nothing else | no |
| `VO-DRAFT.md` | the pre-cut draft, kept so the cut is visible | no |
| `VO-CUT.diff` | the cut itself, with the **measured** reduction in its header | **yes** — `make_cut_diff.py` |
| `CAMERA-STRINGS.yaml` | every on-camera prose string, written down once | no |

The refusal strings — constraint names, SQLSTATEs, `RAISE` messages — are **not** here. They live
in [`../REFUSAL-STRINGS.yaml`](../REFUSAL-STRINGS.yaml), one directory up, because they belong to
the database rather than to the film, and `../check_refusal_strings.py` verifies each one against
the migration that defines it.

## The two numbers that decide eligibility

```
sum(dur)  = 171 s  = 2:51        target, BUILD_PLAN §5.5
headroom  =   9 s                margin below the 180 s disqualifier
```

`validate_shotlist.py` asserts both, plus: the `t` column is the running sum of `dur` (so the
timecodes cannot drift from the durations); every row carries `requires_milestone` and
`fallback`; every `word_count` equals the words actually in its `vo`; every `vo` line appears
verbatim in `VO.md`; and **the scope-cut ladder cannot reach a `never_cut` shot**. That last one
is not defensive programming. A ladder that *can* reach the bypass beat eventually *will*, at
02:00, when judgement is at its worst and the cut is ninety seconds long.

## Two bans, both mechanical

**No commit SHA is ever written or spoken.** `commit_id` is a `sha256` over the JCS envelope; it
cannot be chosen in advance, so a SHA in a script is a promise the commit DAG has not made. The
validator fails on any seven-character hexadecimal literal in a shot's `on_screen` or `vo`.

**No invariant number is ever spoken.** The film cites constraint names, which are unambiguous to
anyone who can read the schema. A bare invariant number is not: it is a pointer into a document
the viewer does not have, and it is ambiguous between two catalogues. The validator fails on any
such literal in `VO.md` or in a shot's `vo`.

## How to check the whole set

```bash
python verticals/mainline/demo/script/validate_shotlist.py     # budget, fallbacks, VO alignment
python verticals/mainline/demo/script/make_cut_diff.py --check # the cut is real and current
python verticals/mainline/demo/check_refusal_strings.py        # the strings match the schema
python scripts/demo/claim_hygiene.py                           # nothing forbidden is said
```

`.github/workflows/claims.yml` runs all four, so drift is a red build rather than a discovery in
the edit suite.

## Capture day

Shoot **worst-first**, three takes each; `capture_order` on every row is the running order, and
it starts at the bypass beat while the operator is fresh and the cluster is quiet. Beat 2 is
never cut for time — if the custodian patrol is not wired, its third statement is dropped and the
beat ends at the append-only refusal. If preflight is not green, switch lists rather than
improvise: `SHOT-LIST-MWS.yaml` was written on D-7 for exactly that reason.
