<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0046 — CU-7: a `SKIP` is printed as loudly as a `FAIL`, and it has its own exit code

**Status:** Accepted · **Date:** 2026-08-10 · **Decider:** custody lead · **Milestone:** K2
**Supersedes:** nothing · **Implements:** `docs/leads/custody.md` §1.2 and §2 decision **CU-7**
**Depends on:** ADR 0040 (custody red before green), ADR 0041 (checkpoint wire format)

## Context

`trappoint-verify` exists so that a stranger can check our log without our cooperation.
Everything about it is arranged around that: one dependency, no network on any default
path, a vendored canonicaliser, RFC 6962 reimplemented rather than shared. All of that is
about *capability* — whether the tool **can** check something.

There is a second question, and it is the one that decides whether the tool is worth
running: **did it?**

Sixteen checks are specified in `spec/custody/checks.yaml`. A real bundle will not always
support all sixteen. A bundle with one checkpoint has no consecutive pair, so check 3 has
nothing to prove. A bundle with no `witness_cosignatures` section cannot be asked about
split views. A bundle produced with `--redact-webauthn` deliberately withholds the personal
data check 12 needs. A build in which worker 7's modules have not landed has no RFC 3161
verifier at all. Each of those is a legitimate state, and in each of them the tool has an
obvious, comfortable option available: print fifteen green ticks and say nothing.

That is the failure mode. It is not hypothetical and it is not rare — it is the default
behaviour of almost every verification tool that has ever shipped, because a skipped check
looks like a passing check to everything downstream: to a CI exit code, to a screenshot, to
a person scanning a report at the end of a long day, and to a customer who was told the
bundle "verified".

The custody plan states it in one sentence: *a verifier that quietly passes because it did
not look is the single worst artefact this domain could ship*. This ADR is the mechanical
form of that sentence.

## Decision

**1. Three verdicts, and `SKIP` carries a mandatory reason.**

`PASS`, `FAIL`, `SKIP(reason)`. `trappoint_verify.report.skipped()` refuses to construct a
skip with an empty reason — it raises at construction time, not at rendering time, so a
reasonless skip cannot reach a report even by accident. A `PASS` may additionally carry a
**qualifier** (`PASS(not-adverse)`, `PASS(coarse)`, `PASS(self-asserted-key)`), which is a
distinct verdict from `PASS` and is printed as one.

**2. `FAIL` and `SKIP` render with the same style constant.**

Not "similar". The same one — bold red, from a single `_LOUD` constant. They are
distinguished only by the word. A reader cannot train their eye to skim past one of them
without also skimming past the other, and nobody can later "soften" the skip colour without
also softening the failure colour, in a diff that says exactly that.

**3. The `NOT CHECKED` banner is at the top, not the bottom.**

Any report containing a skip opens — before a single `PASS` is printed — with a banner
naming every skipped check, its reason, and the detail explaining what would have been
proved. Footnotes are read by nobody. If the run did not look at something, that is the
first thing the report says.

**4. A distinguishing exit code.**

| exit | meaning |
|---|---|
| `0` | every selected check ran and held |
| `1` | at least one check ran and did not hold |
| `2` | **nothing failed, and something was not looked at** |
| `3` | the bundle was unreadable, or the command line was wrong |

`2` is the load-bearing one. A CI lane that treats non-zero as failure cannot go green on a
run that skipped half its checks; a lane that wants to tolerate skips has to write that
tolerance down, where a reviewer can see it. `argparse` exits `2` on a usage error by
default, which would be indistinguishable from *"verified, but N checks did not run"* — so
the parser is subclassed to exit `3` instead. `3` also covers an unreadable bundle, because
"your file is malformed" and "your ledger is broken" are different findings and a shell must
not conflate them.

**5. A narrowed run is announced the same way.**

`receipt-audit` runs checks 4 and 15. The report therefore opens with a `SELECTED RUN`
banner naming the narrowing, for the same reason `NOT CHECKED` exists: a subset presented
without its boundary overstates itself.

**6. An unimplemented check is a `SKIP`, never an absence.**

A check with a registry row and no bound runner reports `SKIP(not-implemented)` and prints
the module that would have implemented it, its declared status, its owner, and the sentence
it would have proved. A check that is silently missing from the output is the exact defect
this ADR exists to prevent, so it is impossible: the run loop walks the registry's sixteen
ids, not the set of registered runners.

**7. An unknown `payload_ver` is a `FAIL`, never a `SKIP`.**

This is the one deliberate exception to "if we could not look, say skip", and the
distinction matters. A skip means *"this was not checked, and it could have been"*. A
bundle written under a canonicaliser we do not hold is one whose bytes we **cannot**
reproduce at all; reporting that as a skip would imply a capability we do not have. It
fails, in checks 1 and 16, and the report names the versions it holds.

**8. A check that raises becomes a `FAIL`, not a traceback.**

Every byte a check reads may have been chosen by an adversary. A crash is a denial of
service against the person holding the bundle — and it is also, in practice, read as "the
tool is broken" rather than "the bundle is". The run loop converts an escaping exception
into `FAIL(check-raised)` naming the exception type. This is the single place in the
repository where a blanket `except Exception` is correct, and it carries that justification
inline.

## Alternatives considered and rejected

**Print skips in yellow, under the summary.** The conventional choice, and it is what
produces the artefact this project must not ship. Yellow-under-the-fold is a colour scheme
that means *"proceed"*.

**Treat a skip as a failure — exit `1`.** Tempting, and wrong in a way that would corrode
the whole scheme. A single-checkpoint bundle genuinely has no consecutive pair; failing it
would teach users that failures are noise, which is the fastest known route to a real
failure being ignored. `2` keeps the fact loud and keeps `1` meaning something.

**Let `--strict` upgrade skips to failures, defaulting to lenient.** Rejected because
defaults are what actually run. A flag that has to be remembered is a property the tool does
not have.

**Suppress the `not-implemented` skips until worker 7 lands.** This would have made today's
run exit `0` and look finished. It would also have made the verifier's first published
behaviour a lie about its own completeness, in the exact register the tool exists to detect.
The seven unimplemented checks are printed, by name, with their owner.

## Consequences

**Good.** The honest state is the *default* state and requires no discipline from anyone: a
run over the committed reference bundle today exits `2` and says, at the top, that seven
checks did not run and which ones. When worker 7 lands the cryptographic modules, the same
command starts exiting `0` with no change to any test's expectations — `EXIT_OK` is already
observed as reachable by
`tests/test_checks_totality.py::test_the_registry_hook_admits_a_new_runner_and_exit_zero_becomes_reachable`,
which binds stub runners for the seven and watches the banner disappear.

**Costs, accepted.** A report is longer and noisier than the one-line summary a demo would
prefer, and the headline number a viewer sees today is `9 passed · 0 failed · 7 not checked`
rather than a clean tick. That trade is the correct way round: the tick is worth exactly what
it costs to obtain, and a tick obtainable by not looking is worth nothing.

**A second-order consequence, and it is the useful one.** Because a skip is expensive to
read and impossible to hide, the cheapest way to make a report look good is to make the
bundle better — carry the extra checkpoint, include the witness section, land the module.
The design pushes in the direction of more evidence rather than less reporting.

## Verification

Measured 2026-08-10 on CPython 3.14.3, `cryptography` 48.0.0, offline:

* `trappoint-verify verify --bundle evidence/reference-ledger/bundle.json` over worker 10's
  committed reference ledger — 8 checkpoints, 72 leaves, 16 receipts — exits **2**: nine
  structural checks PASS (72 leaf hashes, 72 inclusion proofs, all 7 consecutive consistency
  pairs, dense `seq` `0..71`, canonicaliser identity, no sandbox leaf, 16 monotone closure
  generations, 16 covered receipts, totality) and seven report `SKIP(not-implemented)` under
  a `NOT CHECKED` banner.
* Two consecutive `--json` runs are byte-identical.
* `socket.socket`, `socket.create_connection` and `socket.getaddrinfo` patched to raise: the
  full suite and all three subcommands complete.
* Every check has a passing positive test **and** a failing negative test asserting a stable
  machine code; neutering `verify_inclusion`, `verify_consistency` or the payload
  cross-check individually turns the corresponding negative test red, so the assertions are
  wired to the mechanisms rather than to the outcome.
* `Outcome(verdict=SKIP, reason="")` raises `ValueError` at construction.

## A note on vocabulary, recorded here because it is enforced in the same files

Every report opens with *"this bundle records the preconditions the database enforced before
work was permitted to start"* (CU-12). The three banned phrases — the ones enumerated
normatively in `spec/wire/evidence-bundle.md` §14, which describe a ledger as an artefact of
a proceeding rather than as a business record — appear nowhere in this package, in its
tests, or in anything it prints. Evidence Act 1995 (Cth) s.69(3) and s.147(3) exclude
representations prepared in contemplation of a proceeding: a ledger built to be one is not a
business record, and describing it that way damages the thing it is boasting about. The
operational sentence is both the accurate one and the safe one.

(This ADR does not quote the banned phrases, so that a repository-wide grep for them needs
no exemption for the document explaining why they are banned.)
