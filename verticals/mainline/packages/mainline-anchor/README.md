<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-anchor`

**The per-checkpoint fanout that moves a commitment to the log head outside our reach.**

A hash chain inside a table the adversary owns is a checksum, not evidence. This package
is what makes the difference: for every checkpoint, it quotes two public randomness
beacons, signs the note with a KMS key whose private half has never existed outside an
HSM, writes those bytes into an S3 bucket under **Object Lock COMPLIANCE in a second AWS
account**, obtains RFC 3161 timestamps from **two independent authorities**, publishes the
tiles a stranger needs to fetch proofs, and pushes the signed note to external witnesses.

Six steps, and **the order is the product.**

```
beacon ─► sign ─► object lock ─► timestamp ─► publish tiles ─► push to witnesses
   │        │          │              │              │                  │
   │        │          │              │              │                  └─ a witness asked to
   │        │          │              │              │                     cosign a root whose
   │        │          │              │              │                     tiles are not fetchable
   │        │          │              │              │                     cannot check the
   │        │          │              │              │                     consistency proof it
   │        │          │              │              │                     exists to check
   │        │          │              │              └─ serving proofs against a root with no
   │        │          │              │                 upper time bound invites reliance on an
   │        │          │              │                 unbounded claim
   │        │          │              └─ a timestamp over bytes we have not committed to keep
   │        │          │                 proves the bytes existed, not that we kept them
   │        │          └─ §7.3 step 3 locks the NOTE; archiving an unsigned root archives
   │        │             nothing anyone can attribute to us
   │        └─ the beacon lines are INSIDE the body, so a body signed first is a different body
   └─ unpredictable-before-issue ⇒ the root cannot have been fabricated earlier
```

## What is fatal and what becomes debt

| step | on failure | why |
|---|---|---|
| beacon | **abort** | A checkpoint whose body shape varies with beacon reachability produces two classes of checkpoint, and an opposing expert gets to ask which class this one is. One shape, always. |
| sign | **abort** | Nothing downstream means anything over an unsigned root. |
| object lock | **abort** | Until this completes there is no commitment outside our control. Aborting costs a retry; continuing advertises a commitment that does not exist. |
| timestamp | `AnchorDebt` | By now the object is indelible. Raising would pretend an event that physically happened did not. |
| publish tiles | `AnchorDebt` | Same. The bundle carries proofs regardless; tiles are a fetchability convenience. |
| push to witnesses | `AnchorDebt` | ARCHITECTURE.md §7.3 step 5 exactly: permits still merge, the debt row is what makes the next checkpoint inadmissible. **Going dark stays possible and self-reports.** |

Nothing here retries and nothing logs-and-continues. `.importlinter` contract 4 forbids
`tenacity`/`backoff` repository-wide, and a decorator that retried "on exception" could
not tell a TSA timeout from a bucket that is not holding our object.

## The Object Lock refusal, in one paragraph

`PutObject` **succeeds against a bucket with no Object Lock configuration.** The lock
parameters are accepted, ignored, and you get an ordinary deletable object and a 200.
Asking is therefore not evidence of anything. `S3ObjectLockArchive.put_checkpoint` reads
the object's lock metadata back with `HeadObject`, and `ArchivedObject.assert_indelible()`
refuses — naming the field — unless S3 itself reports `ObjectLockMode='COMPLIANCE'`, a
legal hold that is `ON`, a `VersionId` (Object Lock requires versioning), and a
`RetainUntilDate` at least seven years out. That refusal is `ObjectLockNotEnforced`, it is
deliberately *not* wrapped in `AnchorAborted`, and it is a Class E evidentiary-integrity
incident rather than a retry.

## Why every external system is a `typing.Protocol`

**AWS credentials are not valid on the machine this package was written on.** Risk 3 in
`docs/leads/custody.md` §6 is that an unexercised path is a broken path. The mitigation is
that the fakes in `tests/fakes.py` assert the *exact call shape*, so the first invocation
that does have credentials fails loudly instead of silently succeeding wrong:

- `FakeKmsClient` refuses anything but `SigningAlgorithm='ECDSA_SHA_256'` and
  `MessageType='RAW'` — under `DIGEST`, KMS would treat several hundred bytes of note text
  as if it were a SHA-256 digest and emit a signature no verifier on earth accepts.
- `FakeS3Client` refuses anything but `ObjectLockMode='COMPLIANCE'`,
  `ObjectLockLegalHoldStatus='ON'` and a timezone-aware `RetainUntilDate` seven years out
  — and, constructed with `object_lock_enabled=False`, it behaves the way S3 actually
  behaves, which is what makes the read-back test real.
- The port fakes refuse to run before their predecessor in `STEP_ORDER` has run, so the
  ordering assertion is made by the *collaborators* and not only by the code under test.

Every expected value in `tests/test_call_shapes.py` is a **literal**, never an import from
the code under test: asserting against `ports.OBJECT_LOCK_MODE` would pass after somebody
changed that constant to `"GOVERNANCE"`, which is precisely the change that must fail.

**Deliberately not `moto`** (ruling CU-10). Its Object Lock enforcement is incomplete, and
a green test against a mock that does not enforce the control is worse than no test —
it converts an unproven property into a believed one. The control itself is proven over
the OpenTofu plan JSON by `scripts/custody/check_evidence_plan.py`.

Proof that the ordering test bites: swap two lines in `AnchorFanout.anchor` and eleven
tests fail, several with `FakeCallRefused: timestamp was called before object_lock`.

## Dependencies

One: `trappoint-ledger`, for the checkpoint body, the C2SP signed note and the beacon
types. Not `boto3` (the client is injected), not `requests` (`UrllibTransport` is thirty
lines of stdlib behind `HttpTransport`), and not `cryptography` — this package never
verifies a signature and never holds a key, so the whole suite runs on a floor install.

## What this package does **not** do

- **It does not verify an RFC 3161 token.** Ruling CU-8 puts CMS `SignedData` verification
  in `trappoint-verify` (check 5), hand-rolled over its own minimal DER reader, because
  `cryptography` has no CMS verification API and `asn1crypto` would cost the
  one-dependency floor. What is checked *here* is the boundary condition: the response's
  `PKIStatus` is granted, the imprint algorithm is SHA-256, the `hashedMessage` is **our**
  digest and not somebody else's, and the nonce we sent came back.
- **It does not compute a Merkle tree.** The root and the tiles arrive from
  `trappoint_ledger.merkle` via the sequencer.
- **It does not claim split-view resistance.** A witness in our own account is not a
  witness. `Cosignature.adverse` carries the claim so verifier check 7 can refuse to infer
  it, and until an insurer, an HSR or a regulator runs the cosigner the quorum is q = 1
  over our own infrastructure. A pass with no witness reports `fully_anchored is False`.

## Unverified on this machine, and said so here rather than discovered later

- **No live AWS call has been made.** Every call shape is asserted against a fake.
- **The beacon endpoint paths are configuration, not constants.** The defaults
  (`https://api.drand.sh/{chain_hash}/public/latest`, `https://beacon.nist.gov/beacon/2.0/pulse/last`)
  are the documented public paths, but nothing here has contacted either service. Both are
  constructor arguments so a wrong default is a deployment fix, not a code change.
- **No real TSA token has been parsed.** The DER walk is tested against a hand-built,
  structurally-valid token. Real FreeTSA and Sigstore fixtures land with
  `scripts/custody/fetch_tsa_fixtures.py` for `trappoint-verify`'s check 5, and
  `spec/custody/checks.yaml` marks that interop lane `unverified` until it is green in CI.

## Running the tests

```sh
cd verticals/mainline/packages/mainline-anchor
pytest tests -q          # 59 tests, no network, no credentials, no cryptography
```
