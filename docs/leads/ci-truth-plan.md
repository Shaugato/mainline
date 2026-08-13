<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI-TRUTH — the plan, and the measurements it rests on

**Lead: CI-TRUTH. Written 2026-08-13 at `86b25bd` on `master`.** Every number below was taken
by this lead, in this sitting, either from a warm `gh run view --log-failed` or from a command
run against the tree. Nothing is carried forward from a recorded board.

**One methodological note governs three of the nine tasks.** This checkout is a Windows tree
whose files were written under `core.autocrlf=true` at some point; `.gitattributes` does not
exist. Any byte-sensitive measurement taken on the working tree is therefore wrong. Every such
measurement here was taken instead on a **fresh LF export** —

```
git archive HEAD | tar -x -C <scratch>/lfcheck
```

— which is byte-for-byte what the runner checks out. Where the two disagree, the LF number is
the real one and the Windows number is named as the artefact it is.

---

## 0 · The measured board

At `f50efde` (the last commit that touched code) plus `86b25bd` (docs-only; four lanes
re-triggered), **18 workflows exist, 14 have a run at one of those two commits, 8 green and
6 red**:

| lane | run | verdict | cause, from the log |
|---|---|---|---|
| `submission` | 31625358434 | green | — |
| `cloud-verify` | 31625120663 | green | — |
| `boundary` | 31624369240 | green | — |
| `skills` | 31624369173 | green | — |
| `judge-pack` | 31624369172 | green | — one step of it is unfalsifiable (§8) |
| `release-proof` | 31624369165 | green | — |
| `claims` | 31624369135 | green | — |
| `supply-chain` | 31624369091 | green | — |
| `ci` | 31624369123 | RED | 5 jobs: PL-2, mypy, ruff, pytest, summary |
| `aws-evidence` | 31624369242 | RED | 3 jobs, ONE cause: `SEC-ACCOUNT-ID` (§2) |
| `custody-chain` | 31624369124 | RED | canonicaliser drift (§1) + 7/16 by design |
| `db-schema` | 31624369174 | RED | DM-9 violation (§6) |
| `db` | 31624369169 | RED | `restated literal rose from 19 to 20` (§4) |
| `schema` | 31625358541 | RED **by design** | 2 objects with no producer (§9) |

`demo-health` and `nightly-differential` last ran at `1d41442` (both red); `console` last ran
at `1d41442` (green); `mutation-ratchet` was in flight at `86b25bd` when this was written.
**W9 re-measures all four and every row above before rewriting `docs/CI-STATE.md`.**

---

## 1 · The canonicaliser drift — cause found, and it is not what it looks like

The brief asked which side is correct. **The registry is correct and the module is the
deviation, and the deviation is semantically empty.** Proof, three commands:

```
git show 998c526 --stat -- packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py
    → 4 ++++            (and 4 more in the vendored twin)
git show 998c526 -- …/canon_v1.py
    → @@ -121,6 +121,7 @@   +<blank line>   … ×4, PEP8 two-blank-lines before a top-level def
git show 998c526^:…/canon_v1.py | sha256
    → 260ed37ddc610f1fb94ddce98998fe4ae5ce883698ad5c7033839cd258dcd659
```

That is the registry pin, exactly. The commit that moved it is **`998c526 "style(ruff): the
tree is formatted"`** — a machine-generated formatting sweep that swept up a file whose own
docstring says *"Frozen by construction … Removing or modifying a shipped `canon_v*` is a
breaking change to evidence, not to code, and CI refuses it."* CI did refuse it. It took four
blank lines to invalidate every checkpoint signature in the reference bundle.

**So: do not re-pin.** Re-pinning would admit a canonicaliser the registry never accepted and
would re-sign the bundle against it — which is precisely what `custody-chain`'s own notice
warns about. Restore the pinned bytes, and then stop the formatter from being able to do this
again, because a revert that the next `ruff format .` undoes is not a fix.

This one cause is behind `custody-chain`'s check 10 (`canon-source-mismatch`), at least three
named `ci` pytest failures (`test_canonicaliser_registry_is_pinned_and_retained`,
`test_canon_line_names_the_canonicaliser_this_build_is_running`, and the reference-bundle
structural check), and the 12-JSON-path bundle diff.

---

## 2 · `SEC-ACCOUNT-ID` — one literal, three red jobs, and a poisoned mutation family

`evidence/deploy/verify/aws-quota-and-cost.json:30` reads

```json
"AccountLimit.TotalCodeSize": 322122547200,
```

which is Lambda's 300 GiB code-storage quota in bytes — 300 × 1024³ = 322 122 547 200 — and is
twelve digits long. `_ACCOUNT_ID` at `scripts/aws/verify_evidence.py:292` fires on it. It takes
down `no third-party import…`, `evidence/aws is internally coherent…`, and — the expensive one
— `the red half is red for the reason it claims`, which now aborts with **`FAMILY
red-for-the-wrong-reason: an unmutated copy of evidence/ already fails, so every plant below
would be red for a reason that is not its plant`**. A false positive has therefore switched off
a whole anti-vacuity family.

**The evidence file must not be touched.** It is a recorded measurement; editing it to please a
scanner is forging evidence. Fix the scanner, and fix it without blinding it — an allow-list of
one literal is the wrong answer for the same reason the deploy transcript's header already
gives: *"a scanner carrying an exception for one such literal would carry it for any."*

---

## 3 · ruff and mypy — and a correction to the brief

The brief says `ruff format` is already clean and the local count is pure CRLF. **Half right,
and the half that is wrong is the half that matters.**

| measured on | files ruff would reformat |
|---|---|
| this Windows working tree | 244 |
| a fresh LF export of `HEAD` | **10** |
| CI, run 31624369123 | **10** |

So 234 of the 244 are the CRLF artefact and 10 are real. There must be **no `ruff format .`
sweep** — that would rewrite 244 files and, per §1, would re-break the canonicaliser. Exactly
ten named files get formatted; nine belong to W3 and one to W4.

The ratchet's 9 regressions, from the CI log verbatim: `D102 +12`, `D105 +2`, `D107 +1`,
`D401 +6` on `packages/trappoint-*`, and five `unformatted` rows. This lead located the lint
half: of the three `packages/trappoint-*` files changed since the baseline commit `998c526`,
**`bedrock_backend.py` carries 22 of the 23 D-family findings** — the same file as all four
mypy errors. One file, two red jobs.

`mypy` at `bedrock_backend.py:1152,1153,1171,1172`: `channel=CHANNEL` and `origin=ORIGIN` are
`str` where `ScoredCandidate` wants a `Literal[…]`. The module constants need narrowing at the
definition, not a `cast` at the call site.

The Unicode half of the brief's `noqa` instruction is **already done** — see `already_true`.

---

## 4 · The image census — the ceiling that rose, and the twenty files under it

Reproduced `db.yml`'s census logic exactly, against the LF export:

```
FLOATING   34 occurrences across 20 files   ceiling 34   held
RESTATED   20 occurrences across 12 files   ceiling 19   ROSE  ← the red
```

The riser is a single line in a file this wave added:
`skills/designing-diachronic-gates/scripts/assert_gate_refuses.py:67`. Bringing it back to 19
turns `db` green. That is a two-line change and it is not the point.

The point is the 34 floating uses. Each one is `os.environ.get("MAINLINE_CRDB_IMAGE",
"cockroachdb/cockroach:latest-v26.2")` or a docstring restating it, and `latest-v26.2` is a tag
that moves. The lane the census sits in exists to make "one version constant, and it lives in
compose.yaml" true. Convert them to the shared testkit fixture and **lower the ceiling in the
same commit** — the step's own comment asks for exactly that.

---

## 5 · The lockfile, and the suppression

`trappoint migrate lock` reports 10 migrations whose manifest hash disagrees with the tree —
identical on the Windows tree and on the LF export, so it is real content drift, not line
endings. `--write` is a two-second command; **it is not the task.** The manifest is the thing
that would notice a migration edited after review, so regenerating it without first explaining
each of the ten is the exact laundering the lockfile exists to prevent.

`submission.yml` lines 171–176 carry `continue-on-error: true` on the step *and* `|| true` on
the command inside it. The step is "The machine record". It cannot fail, in two independent
ways, which means it asserts nothing about the machine record.

---

## 6 · DM-9 — the brief said one file; there are two, at three sites

```
WRITE  scripts/proof/gate_refusal.py:970          INSERT INTO mainline.clause_blame_closure (…
WRITE  verticals/mainline/db/seeds/demo/demo_world.sql:320   INSERT INTO mainline.clause_blame_closure (
READ   verticals/mainline/db/seeds/demo/demo_world.sql:334   SELECT 1 FROM mainline.clause_blame_closure
```

The READ at `demo_world.sql:334` is the dangerous one and the reason DM-9 exists: a reader that
skips `clause_blame_current` gets a real row from a superseded generation, with **less**
ancestry and therefore a **lower** `max_severity`, silently — the one error direction in this
product with physical consequences.

`scripts/proof/gate_refusal.py` produces the caveat-free gate proof (chain 271/271, PROJECTION
10/10, `23514 gate_closed_when_issued`). **That proof must still be caveat-free when this is
done**, and it must be re-run to say so.

---

## 7–9 · Anti-vacuity — the part that outranks the count

Three greens were named unfalsifiable by the audit. This lead confirmed two of them by reading
the source and running the third.

**The image-pin assertion.** `custody-chain.yml:1052`, `:1112`, `:1257` and `db-schema.yml:321`
all read the pin out of `compose.yaml`, `docker run` it, then poll `SELECT 1` until the node
answers. Nothing ever asks the running server what version it is. The assertion catches a pin
that failed to arrive; it cannot catch a pin that was wrong when it was requested. `SELECT
version()` compared to the pin, plus a negative control that starts a deliberately different
tag and asserts the comparison fires, converts it into a claim.

**`judge-pack`'s envelope step.** Ran it: `verticals/mainline/demo/judge/cli.py envelope`
prints eleven `ok`s, two `fits`, `cross-check: ran`, and **exits 0**. Whether any input can make
it exit non-zero is the open question, and it is answerable by mutating one constant in an
in-memory copy and looking at the exit code. If nothing can, the step is decoration and must
either grow teeth or be named unproven.

**The mutation family.** Blocked behind §2; it will not be believable until an unmutated
`evidence/` passes, and even then the family must be shown to fire *because of* each plant.

`schema` (2 objects with no producer), `custody-chain` (7/16), `ci`'s PL-2 job (`the db lane's
red conform run URL is still UNRECORDED`) and `demo-health` are **red by design and stay red**.
Each one earns a message that says so in its own error text, so a judge scanning the Actions tab
is not asked to remember which reds were deliberate.

---

## The nine workers

| # | task | owns |
|---|---|---|
| W1 | canonicaliser restored to its pin, and fenced from the formatter | 2 canon files, `ruff.toml`, the registry |
| W2 | `SEC-ACCOUNT-ID` learns bytes from account ids | `verify_evidence.py` + a new test |
| W3 | `bedrock_backend.py`, the ratchets, and 9 of the 10 unformatted files | 15 files |
| W4 | the image census: the riser, the 34 floating uses, the ceilings | `db.yml` + 21 files |
| W5 | the lockfile, explained then regenerated; the double suppression removed | 2 files |
| W6 | DM-9: two files, three sites, and the gate proof still caveat-free | 4 files |
| W7 | the image pin becomes a claim about the running server | 3 workflows |
| W8 | the envelope grows teeth; the mutation family is shown to fire | 4 workflows + cli + 2 docs |
| W9 | the intentional reds say why; `CI-STATE.md` rewritten to the measured board | 3 workflows + 2 docs |

Ownership is absolute and the sets above are disjoint. W3 and W1 both change what `ruff format
--check` reports, so W3 waits for W1. W8's mutation family waits for W2. W9 waits for everyone,
because it is the only worker whose output is a claim about all of them.

**No worker may add `continue-on-error`, `|| true`, an `xfail`, or a ratchet rebaseline that
raises a number without saying so in the commit message. No worker edits a recorded transcript
under `evidence/`. If a task cannot be closed honestly, it is written down as unproven in
`docs/CI-STATE.md` — that outcome is a success, not a failure.**
