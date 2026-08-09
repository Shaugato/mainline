<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0044 — CU-4: two beacons, and only one of them is load-bearing offline

**Status:** Accepted · **Date:** 2026-08-04 · **Decider:** custody lead · **Milestone:** K2
**Supersedes:** nothing · **Implements:** `docs/leads/custody.md` §2 decision **CU-4**
**Depends on:** ADR 0041 (checkpoint wire format), ADR 0043 (log signature)
**Implemented by:** `packages/trappoint-ledger/src/trappoint_ledger/beacon.py`

## Context

A checkpoint has to be bounded in time from **both** sides, because the two accusations are
different and each defeats a different one:

- *"You wrote this later and backdated it."* Defeated from above by an RFC 3161 timestamp:
  the root existed **no later than** `genTime`, attested by a party with no relationship
  to us.
- *"You wrote this earlier and held it."* Defeated from below by a public randomness beacon:
  a value that could not be known before it was issued means the checkpoint **cannot have
  been constructed before** that round's time.

ARCHITECTURE.md §7.3 specifies one beacon — a drand round embedded in the checkpoint body.
Implementing it exposes a problem that the architecture does not state.

**drand's signature is not verifiable under our dependency floor.** The `quicknet` chain is
`bls-unchained-g1-rfc9380`: BLS12-381 signatures on G1. `cryptography` implements no
pairing-friendly curve and no BLS scheme. `trappoint-verify`'s entire claim to a stranger
is *"one dependency, `cryptography`, and nothing else"* — that claim is what makes the
verifier something an opposing expert will actually run. Adding `py_ecc` or `blst` bindings
to verify a beacon would cost the claim.

What a verifier *can* do with a drand line under the floor is arithmetic:
`round_time = genesis + (round − 1) × period`. That catches a checkpoint quoting a round
that had not yet been issued when its RFC 3161 token was minted (attack **A9**). It does
not establish that the quoted round is a real drand round at all. **A drand line alone is
not a lower bound a stranger can check**, and a document that implied otherwise would be
claiming a property nobody verified.

## Decision

**1. The checkpoint body carries two beacon extension lines, not one.**

```
drand: <64 hex chain hash> <round decimal> <64 hex randomness>
nist: 2.0 <chainIndex>.<pulseIndex> <128 hex outputValue>
```

**2. drand `quicknet` is the fast beacon.** Chain hash
`52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971`, genesis `1692803367`,
period 3 s. A 3-second cadence matters: our checkpoint cadence is 60 s, and a beacon whose
rounds are minutes apart would widen the lower edge of the bracket by more than the window
we are trying to bound. Its round-to-time mapping is verified arithmetically (check 6b);
its BLS signature is reported `SKIP(optional-extra)` unless `trappoint-verify[beacon]` is
installed.

**3. The NIST Interoperable Randomness Beacon 2.0 pulse is the verifiable beacon.** Its
pulses are signed RSA PKCS#1 v1.5 over SHA-512 with an X.509 certificate — every primitive
of which `cryptography` implements. It is fully verified by check 6a, under the floor, with
no extra. Its 60-second cadence is coarser than drand's, which is why it is the second
beacon and not the only one.

**4. Two independent issuers, and the weaker one is labelled.** `spec/wire/checkpoint.md`
§4.2 states in the normative document that the drand line alone is not offline-checkable.
`spec/custody/checks.yaml` records check 6b's `SKIP` status. No MAINLINE deck, report or
README may describe the drand line as a verified lower bound without contradicting a
frozen specification, which is the point of writing it there rather than here.

**5. `trappoint_ledger.beacon` parses and does arithmetic; it verifies nothing.** The log
is the party whose honesty is in question, so a module inside the log that could pronounce
its own beacons valid would be producing a verdict nobody should accept. Verification lives
in `trappoint_verify.checks.beacon`. Two internal-consistency helpers are the only
exceptions, and both are documented as consistency rather than verification:

- `DrandRound.randomness_binds_signature()` — drand defines `randomness = SHA-256(signature)`
  for every scheme, so this is checkable with `hashlib`. It proves the two fields belong
  together. Anyone can mint a self-consistent pair; it establishes nothing about the League
  of Entropy.
- `NistPulse.output_binds_signature()` — **marked UNVERIFIED in the source**. NIST 2.0
  defines `outputValue` as a SHA-512 derived from `signatureValue`, and published
  descriptions differ over whether the preimage is the signature bytes alone or the signing
  input concatenated with them. No MAINLINE build has been run against `beacon.nist.gov` to
  settle it. The method implements the signature-bytes-alone reading, **nothing in this
  repository gates on its result**, and the authoritative check is 6a.

## The honest cost, stated once so it cannot be quietly dropped

The `0x02` log signature covers the entire note text, extension lines included. A witness
cosignature of type `0x04`/`0x06` (`c2sp.org/tlog-cosignature`) covers `(origin, size, root)`
and **does not cover extension lines**.

> **The beacon lower bound is exactly as strong as the log signature, and no stronger.** A
> T4 adversary — the cloud admin colluding with the signer — can mint a checkpoint with any
> beacon lines they like, and every witness will still cosign it.

What survives T4 is the RFC 3161 token over the note text plus each witness's own record of
when it first saw tree size *n*. That paragraph is in `spec/wire/checkpoint.md` §4.4, in
`spec/custody/threat-model.md`, and here.

## Consequences

- A stranger with `cryptography` and no network gets one fully verified lower bound (NIST)
  and one arithmetic consistency check (drand). Neither is silently assumed.
- The checkpoint body is ~200 bytes longer. `ledger_checkpoint.beacon JSONB` carries both
  parsed values in the shape `mainline_sequencer.append` writes, so the column and the
  signed note cannot disagree about which round was quoted — `beacon_column()` and
  `parse_beacon_column()` are the one implementation of that shape in the substrate.
- Anchoring needs two outbound fetches per checkpoint instead of one, both on the
  best-effort fanout path. Neither is in the transaction that records the checkpoint: an
  unreachable beacon must never be a reason not to record a commitment.
- `beacon.py` contains no HTTP client. `mainline_anchor` fetches; this parses. A parser that
  could also fetch is a parser that can be pointed at a URL by whatever it just parsed.

## References

- drand: `quicknet` chain `52db9ba7…e971`, scheme `bls-unchained-g1-rfc9380`, period 3 s,
  genesis `1692803367`; randomness is `SHA-256(signature)` for every scheme
- NIST Interoperable Randomness Beacon 2.0 (`beacon.nist.gov`), NISTIR 8213
- `spec/wire/checkpoint.md` §4.2–§4.4, §7.3, §10 point 8
- `spec/custody/checks.yaml` checks 6a and 6b · `spec/custody/attacks.yaml` A9
- `docs/leads/custody.md` §2 CU-4 · ARCHITECTURE.md §7.3
