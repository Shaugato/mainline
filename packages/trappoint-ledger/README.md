<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-ledger` — the tree that proves, the chain that explains

**Apache-2.0 · Python ≥ 3.13 · one runtime dependency (`trappoint-jcs`), and the proof
algorithms have none at all.**

This package is the tamper-evidence log of the TRAPPOINT substrate: an
[RFC 6962](https://www.rfc-editor.org/rfc/rfc6962) Merkle tree, its inclusion and
consistency proofs, [C2SP `tlog-tiles`](https://c2sp.org/tlog-tiles) addressing for the
static verification surface, and the `link_hash` chain that a person can read aloud.

It does no IO. It opens no socket, reads no clock, and touches no database. Everything
here is a pure function of bytes you hand it — which is what makes it usable
simultaneously by the sequencer (which writes), by `trappoint-verify` (which checks a
bundle emailed to a stranger), and by a witness (which cosigns).

## What is here

| Module | What it is |
|---|---|
| `merkle.tree` | `MTH`, leaf and node hashing, and a tree whose `append` returns **exactly the `ledger_node` rows that came into existence** |
| `merkle.proof` | `PATH` and `PROOF` generation, and the stateless `verify_inclusion` / `verify_consistency` a third party runs |
| `merkle.tiles` | `tlog-tiles` geometry and path grammar; which tiles a verifier must fetch for a given proof |
| `chain` | `link_hash`, chain recomputation, `seq` density, and the CU-1 genesis convention |

`note`, `checkpoint`, `signer`, `beacon` and `receipt` are added alongside these by the
signing worker; this README covers the tree, the proofs, the tiles and the chain.

## The one implementation detail worth reading twice

RFC 6962 splits a list of `n` leaves at **the largest power of two strictly less than
`n`**. The obvious expression, `1 << (n.bit_length() - 1)`, is wrong for exactly the
values of `n` that are powers of two — where it returns `n` itself — and right
everywhere else. The bug therefore survives casual testing and then produces a tree that
no other Certificate-Transparency implementation will ever agree with.

By the time that is noticed, the wrong roots have been signed by KMS, timestamped by an
RFC 3161 authority and written to an S3 bucket under Object Lock COMPLIANCE, where they
cannot be deleted by anyone including the account root. `largest_power_of_two_below` is
written once, tested against brute force, and used everywhere.

## Two structures, and the honest division of labour

The Merkle tree is what *proves* things; the chain is what *explains* them.

A chain gives a courtroom the sentence "entry 41 209 names entry 41 208", which is worth
a great deal in front of a jury and nothing at all against an adversary with `UPDATE`.
Delete leaf *k*, renumber `k+1..n`, recompute every `link_hash` in a single
`UPDATE … FROM generate_series`, and the chain recomputes perfectly. Only a root that
left our control before the rewrite catches it, and catching it is a **consistency
proof**, not a chain walk.

`tests/test_chain.py` contains that demonstration as a passing test rather than as a
caveat in prose: the rewritten chain verifies, and the consistency proof against the
earlier published root fails.

## What this package does not claim

- **It is not evidence by itself.** A hash chain inside a table the adversary owns is a
  checksum. The evidence is the commitment that left our reach — the signed checkpoint,
  the timestamp, the Object Lock object version, the witness cosignature — and those
  live in the modules and the infrastructure around this one.
- **Tiles do not defeat a split view on their own.** Serving proofs as static objects
  removes our application code from the verification path, which is necessary. It is not
  sufficient: split-view resistance requires an *adverse* witness quorum, which today we
  do not have. `spec/custody/checks.yaml` records check 7 as
  `implemented_but_not_adverse`, and that is the honest word for it.

## Conformance

- RFC 6962 §2.1 (`MTH`), §2.1.1 (`PATH`), §2.1.2 (`PROOF`/`SUBPROOF`) — generation.
- RFC 6962-bis §2.1.3.2, §2.1.4.2 — the stateless verification algorithms.
- C2SP `tlog-tiles` — tile geometry (height 8, 256 hashes, 8192 bytes when full) and the
  `tile/<L>/<N>[.p/<W>]` path grammar with `x`-prefixed three-digit index groups.

Tested against the Certificate Transparency reference implementation's known-answer
vectors (eight leaves; all nine roots, five inclusion proofs, four consistency proofs),
against a second, independent transcription of the RFC's recursive definitions, and
against Hypothesis property tests over every tree size up to 512.
