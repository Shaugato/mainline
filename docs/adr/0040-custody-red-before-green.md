<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0040 — The K2 exit criteria are committed as a failing test

**Status:** Accepted · **Date:** 2026-08-07 · **Decider:** custody lead · **Milestone:** K2
**Implements:** `docs/leads/custody.md` §1.2 · **Discipline:** PL-2 (red before green)

## Context

MAINLINE's deliverable is a **refusal**. The gate refuses a merge; the ledger refuses a
fork; the canonicaliser refuses a float; the verifier refuses to agree that a tampered
bundle is intact.

For a product of that shape, a green test suite is not evidence. A suite that has never
been red is equally consistent with two states of the world:

- the mechanism works, or
- the mechanism was never wired up, and the test asserts nothing.

The second state is not hypothetical. It is the ordinary outcome of writing a test after
the code, against the code, by the person who wrote the code — and it is exactly the defect
an opposing expert is hired to find. *"Your test suite passes"* is worth nothing if the
answer to *"did it ever fail?"* is *"we never checked."*

The same reasoning applies to the milestone itself. K2's six exit criteria (BUILD_PLAN.md
§3) are a definition of done written before the work. If they are turned into assertions
only once the work is finished, they are a description of what was built rather than a
specification of what had to be.

## Decision

**`tests/integration/custody/test_k2_exit.py` is committed containing exactly the six K2
exit criteria as executable assertions, before a single line of ledger, verifier or
sequencer code exists. The failing run is the deliverable of custody worker 1.**

Three rules bind it:

1. **Six failures, one per criterion, each with a distinct message naming the missing
   artefact.** Not one failure that covers everything, and not a `pytest.fail("todo")` — a
   criterion whose failure message does not tell you what to build has not been specified.
2. **The file is made green by building artefacts, never by editing assertions.** A commit
   that weakens an assertion without an accompanying ADR removed a criterion; it did not
   meet one.
3. **Auxiliary tests in the same file skip loudly rather than fail.** Exactly six failures
   is itself part of the deliverable, so anything that is not an exit criterion —
   `test_gate_depends_on_ledger`, `test_no_ttl_on_ledger`, `test_verifier_determinism` —
   reports `SKIP(no-cluster)` with the reason printed.

## The red run

Recorded here because the run is the proof artefact, and a claim about a run that nobody
can locate is the class of claim this whole domain exists to eliminate.

```console
$ cd D:/CoackroachDBxAWS/mainline
$ python -m pytest tests/integration/custody/test_k2_exit.py -q
...
FAILED tests/integration/custody/test_k2_exit.py::test_k2_1_tamper_is_caught_by_a_consistency_proof
FAILED tests/integration/custody/test_k2_exit.py::test_k2_2_closure_rewrite_is_caught_by_check_14
FAILED tests/integration/custody/test_k2_exit.py::test_k2_3_bundle_verifies_with_no_cluster_and_no_credential
FAILED tests/integration/custody/test_k2_exit.py::test_k2_4_checkpoint_cadence_measured_and_deadman_defined
FAILED tests/integration/custody/test_k2_exit.py::test_k2_5_checkpoint_wire_format_tagged_v1_0_with_changelog_entry
FAILED tests/integration/custody/test_k2_exit.py::test_k2_6_migration_attestation_chained_with_a_stable_fingerprint
6 failed, 6 passed, 3 skipped in 0.82s
```

| | |
|---|---|
| Date | 2026-08-07 |
| Repository | `github.com/Shaugato/mainline`, branch `master` |
| Parent commit | `2dc7b45` |
| Python | 3.14.3 |
| pytest | 9.0.3 |
| `sha256` of the captured run output | `5c0670ac89dcd5d6fc5304861e623d1b0b9eaf62b6117ab8ddc3f6a76400aec0` |

> **The CI run URL is not yet available, and this ADR does not pretend otherwise.**
> `.github/workflows/custody-chain.yml` does not exist at the time of writing — it is
> custody worker 10's deliverable — so there is no hosted run to link. The local run above
> is recorded with its exact environment and the digest of its output so that it is
> checkable rather than merely asserted. **The URL of the first CI run of this job is
> appended to this table, in a commit that changes nothing else, the day the workflow
> lands.** Recording a placeholder that looks like a link would be the small dishonesty
> that makes every other claim in the domain worth less.

## What each failure is telling the fleet to build

| Criterion | Failing because | Owner |
|---|---|---|
| **K2.1** tamper caught by a consistency proof | no nemesis harness, no `evidence/CUSTODY_ATTACK_MATRIX.md` | `reference-ledger-and-nemesis` |
| **K2.2** closure rewrite caught by check 14 | same, plus `checks.yaml` still records check 14 as `deferred` | `verify-core`, `reference-ledger-and-nemesis` |
| **K2.3** bundle verifies offline, no credential | no `trappoint_verify`, no reference bundle, no dependency-floor test | `verify-core`, `reference-ledger-and-nemesis` |
| **K2.4** cadence measured, deadman defined | no `evidence/k2-checkpoint-cadence.json`; `checkpoint_age_seconds` undefined | `sequencer`, cloud lead |
| **K2.5** wire format tagged v1.0 with a CHANGELOG entry | `spec/wire/checkpoint.md` **is** frozen at v1.0; `spec/CHANGELOG.md` carries no entry | kernel lead (owns `spec/CHANGELOG.md`) |
| **K2.6** migration attestation chained, fingerprint stable | no `mainline_custody_patrol`, no attestation artefact | `witness-and-custodian` |

K2.5 is the interesting row. Half of it is already green — the wire format is frozen — and
the half that is red is owned by a different domain. That is exactly what a cross-domain
dependency should look like: visible, attributable, and failing in someone's build rather
than living in a spreadsheet.

## Consequences

**The build is red on purpose, and everyone can see why.** Nobody has to ask what K2 means;
they can run one command and read six sentences telling them what does not exist yet.

**The criteria cannot quietly soften.** Rule 2 means the only way to change what K2 requires
is to write down that you changed it.

**The same discipline binds the verifier.** `SKIP` is printed as loudly as `FAIL`, any
report containing one carries a `NOT CHECKED` banner, and `spec/custody/checks.yaml` records
a build-time `status` per check with a totality rule (a check marked `implemented` must name
a module and a test that both exist). A verifier that quietly passes because it did not look
is the single worst artefact this domain could ship, and it is the same failure this ADR is
about, one layer down.

**A cost, accepted.** Six red tests sit in the repository for the length of K2, and anyone
running the full suite sees them. The alternative — a `@pytest.mark.xfail` or a skipped
file — hides the milestone's state, which is the opposite of what the artefact is for.

## Revisit trigger

None. When all six pass, K2 is done, and this ADR becomes a record of how it was known to
be done. If a criterion is ever removed or weakened, that is a new ADR superseding this one,
naming the criterion and the reason.

## References

- `BUILD_PLAN.md` §3 K2 (contents, exit criteria, "fails how")
- `docs/leads/custody.md` §1.2, §1.4
- `spec/custody/checks.yaml` (the totality rules), `spec/custody/attacks.yaml`
- `docs/adr/0041-checkpoint-wire-format.md`
