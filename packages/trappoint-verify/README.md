<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-verify`

**An evidence bundle is one JSON file. This is the program that checks it, on your
machine, with nothing of ours.**

```console
$ uvx trappoint-verify verify --bundle bundle.json
```

No credential. No account. No network. No cooperation from the people who produced the
bundle — which, if you are reading this, is probably the point.

A bundle records the preconditions the database enforced before work was permitted to
start. This tool re-derives, from first principles, whether the record is internally
consistent and whether it agrees with the commitments that left the log operator's control
at the time.

---

## The one thing to know before you read the output

A check here reports **`PASS`**, **`FAIL`** or **`SKIP(reason)`**, and

> **a `SKIP` is printed as loudly as a `FAIL`.**

Same colour weight. Same section. A `NOT CHECKED` banner at the **top** of the report
naming every check that did not run and why. And its own exit code, so a shell can tell
"we found nothing wrong" apart from "we did not look":

| exit | meaning |
|---|---|
| `0` | every selected check ran and held |
| `1` | at least one check ran and did not hold |
| `2` | **nothing failed, and something was not looked at** |
| `3` | the bundle could not be read, or the command line was wrong — a finding about the input, not about the log |

This is the whole design. A verifier that quietly passes because a section was missing, a
key was absent or a module had not been built is worse than no verifier at all: it
converts an unknown into a clean bill of health, and it does so silently. Everything else
in this package is arithmetic.

Today a default run over a complete bundle exits `2`, because seven of the sixteen check
modules have not landed yet. That is stated, in the report, per check, with the name of
the module that would have run and the sentence it would have proved.

---

## What it is allowed to depend on

**`cryptography`. That is the entire list.**

- No MAINLINE package. RFC 6962 inclusion and consistency proofs are reimplemented here on
  `hashlib` rather than lifted from `trappoint-ledger`, and the RFC 8785 canonicaliser is
  **vendored byte-for-byte** into `src/trappoint_verify/vendor/`.
- `tests/test_dependency_floor.py` walks the syntax tree of every shipped module and
  asserts the top-level import set is a subset of the standard library plus
  `cryptography` — and that no dynamic-import escape hatch (`__import__`,
  `importlib.import_module`, `eval`, `exec`) exists to step over the check.
- `tests/test_no_network.py` replaces `socket.socket` with a function that raises, proves
  the replacement bites, and then runs the entire suite and the CLI end to end.
- `scripts/custody/check_vendored_canon.py` asserts the vendored canonicaliser is
  byte-identical to the one the log used. A verifier whose canonicaliser has drifted from
  the log's agrees with nothing.

Each of those is a test, not a sentence. That is deliberate: every claim on this page that
could rot is wired to something that fails when it does.

---

## The checks

| # | name | proves | needs nothing from us |
|---|---|---|---|
| 1 | `leaf_hash_recomputation` | every leaf hash is `SHA-256(0x00 ‖ canon_bytes)`, dispatched on `payload_ver` | yes |
| 2 | `inclusion_proof` | leaf *i* is in the tree the checkpoint committed to | yes |
| 3 | `consistency_proof_every_pair` | the tree at size *m* is a prefix of the tree at size *n*, for **every** consecutive pair | yes |
| 4 | `log_signature` | the note was signed by the pinned log key | yes |
| 5 | `rfc3161_upper_bound` | a timestamp authority saw this root no later than `genTime` | yes |
| 6 | `beacon_lower_bound` | the checkpoint quotes a beacon value that did not exist earlier | yes |
| 7 | `witness_quorum` | *q* cosignatures over the same `(size, root)`, across distinct trust domains | yes |
| 8 | `archive_object_lock` | the archived object matches, under Object Lock COMPLIANCE | **no — needs `--s3`** |
| 9 | `link_chain_and_density` | the link chain recomputes and `seq` is dense `0..n−1` | yes |
| 10 | `canonicaliser_identity` | the code that produced the bytes is the code checking them | yes |
| 11 | `gate_self_attestation` | the trigger source that refused the merge is inside the ledger | yes |
| 12 | `webauthn_reverification` | the human signature verifies against the **enrolled** key, and the challenge reconstructs | yes |
| 13 | `no_sandbox_leaf` | no demo write is inside this tree | yes |
| 14 | `closure_generation_monotone` | blame-closure generations are dense and severity never fell | yes |
| 15 | `receipt_coverage` | every expired promise was kept | yes |
| 16 | `bundle_totality` | **the run looked at everything it says it looked at** | yes |

Fifteen of sixteen need nothing from us. That number is not typed into this table by hand —
it is computed from the `offline` column of `spec/custody/checks.yaml` and asserted by
`tests/test_checks_totality.py`.

`trappoint-verify explain-check <id>` prints any row above, on a machine that has never
seen this repository, along with whether **this build** actually has a runner bound to it.

---

## Commands

```console
$ trappoint-verify verify --bundle bundle.json        # every registered check
$ trappoint-verify receipt-audit --bundle bundle.json # checks 4 and 15 only
$ trappoint-verify explain-check 14                   # what does check 14 prove?
$ trappoint-verify verify --bundle bundle.json --json # the same report, machine-readable
```

`receipt-audit` is a narrowed run and says so: a `SELECTED RUN` banner names what was not
run, for the same reason `NOT CHECKED` exists.

### Options that could touch a network

All of them are off by default, and their absence downgrades a specific check to
`SKIP(offline)` rather than passing it quietly.

| flag | what it enables |
|---|---|
| `--s3` | compare the `archive` section against live object versions (check 8) |
| `--kms-pubkey` | fetch the log's public key from KMS instead of trusting a pin (check 4) |
| `--tile-url` | fetch static tiles rather than reading proofs out of the bundle |

`--log-key` takes a C2SP verifier key **out of band**. Without one, a bundle that carries
its own key proves nothing about the log, and the report says `PASS(self-asserted-key)` —
a distinct verdict, printed as such.

`--redact-webauthn` treats the WebAuthn section as redacted. Check 12 then reports
`SKIP(redacted)` instead of the section silently disappearing.

---

## What this does **not** prove

Said here, first, because the alternative is that you find it out later from someone else.

- **Not that a disposition was sincere.** Non-repudiation is cryptographic, not moral. A
  verified signature says a credential was used; it does not say the person meant it, or
  that they were not under pressure.
- **Not that an ingested document is true.** Provenance — who submitted it, when, its hash,
  its archived version — is in scope. Content authenticity is not.
- **Not that a search was exhaustive** over anything except the retrieval that actually
  ran.
- **Nothing about the state of the database at a past time.** The cluster's garbage
  collection window is short; long-horizon history is the application-level commit DAG, not
  time travel.
- **Not resistance to a split view.** Check 7 requires cosignatures from distinct trust
  domains with at least one adverse. Until an insurer, a union health-and-safety
  representative, a regulator or an external auditor actually runs the cosigner, the
  quorum is *q* = 1 over the log operator's own infrastructure, which is **not adverse in
  the legal sense**. The registry marks check 7 `implemented_but_not_adverse` and the
  report prints `PASS(not-adverse)` — a different verdict from `PASS`.
- **Not anything about the storage layer's operators.** A managed database vendor or a
  cloud provider with access below the SQL layer is outside what any check here can reach.
  Only external archival and adverse witnesses touch that, and both are stated limits
  rather than solved problems.
- **Nothing at all, about anything, for a check that reports `SKIP`.**

---

## Working on this package

```console
$ uv run pytest packages/trappoint-verify        # 88 tests, under two seconds
$ python scripts/custody/check_vendored_canon.py # the vendoring equality
```

Two rules for contributors, both mechanical:

1. **Never edit `src/trappoint_verify/vendor/canon_v1.py`.** It is a byte-identical copy.
   Change the original in `packages/trappoint-jcs` and re-copy, or CI fails with *"the
   verifier's one-dependency claim is false while this differs"*.
2. **Never add a dependency.** The floor is the product. If a check cannot be implemented
   inside it, the honest outcome is `SKIP(reason)` with the reason printed — which is a
   supported outcome here precisely so that nobody is ever tempted to trade the floor for a
   green tick.

New checks register through `trappoint_verify.checks.register`, are wired for import in
`checks/__init__.py`, and must appear in `spec/custody/checks.yaml`. The totality test
refuses a runner without a row, a row without a test, and a registry that has drifted from
the copy inside the wheel.

---

## References

- `spec/wire/evidence-bundle.md`, `spec/wire/checkpoint.md`, `spec/wire/receipt.md`
- `spec/custody/checks.yaml` — the normative check registry this tool mirrors
- `docs/adr/0046-verifier-skip-is-loud.md` — why a skip is printed like a failure
- RFC 6962 §2.1, RFC 8785, RFC 4648 §4, [c2sp.org/tlog-checkpoint](https://c2sp.org/tlog-checkpoint)
