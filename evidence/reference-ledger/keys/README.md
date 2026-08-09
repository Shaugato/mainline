<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Keys in this directory are NOT SECRET, on purpose

> **This key is public by design — the reference bundle proves the verifier works, not
> that MAINLINE's production log is honest.**

Five private keys are committed here. Every one of them signs the reference fixture and
nothing else. None has ever been, and none will ever be, a MAINLINE log key, a MAINLINE
signing credential or a MAINLINE timestamp authority.

Publishing them is the point. CU-6: *a reference fixture a stranger cannot regenerate is a
screenshot.* If the key were secret, `generate.py` would be a script only we could run, the
zero-diff CI assertion would be a claim about our laptop, and the bundle would be an image
of evidence rather than the thing itself.

| File | Algorithm | Signs | Key ID |
|---|---|---|---|
| `reference-log.NOT-SECRET.key.pem` | P-256 | checkpoint notes (C2SP type `0x02`) and every Signed Disposition Receipt | `6994c9d3` |
| `reference-witness.NOT-SECRET.key.pem` | P-256 | the witness signature line on the last two checkpoints | `341df99f` |
| `reference-webauthn.NOT-SECRET.key.pem` | P-256 | the WebAuthn assertion, standing in for an enrolled authenticator | `79f72db9` |
| `reference-tsa-root.NOT-SECRET.key.pem` | RSA-2048 | the fixture timestamp authority's root certificate | — |
| `reference-tsa.NOT-SECRET.key.pem` | RSA-2048 | RFC 3161 `TimeStampToken`s over each checkpoint note | — |

The key ID rule for type `0x02` is `SHA-256(DER SPKI)[:4]`, **not** the Ed25519 rule
(`SHA-256(name ‖ 0x0A ‖ 0x01 ‖ pubkey)[:4]`). Deriving it the Ed25519 way produces a note
that "verifies" against nothing;
[`spec/wire/checkpoint.md`](../../../spec/wire/checkpoint.md) §5.1 rules on it.

## How they were produced, and why that matters

The three P-256 keys are **derived from fixed scalars written in this repository's history**
rather than sampled, so `keys/` is reproducible from first principles rather than merely
copied. The two RSA keys were generated once and committed, because RSA key generation is
not deterministic and a committed key is the only way to keep the timestamp authority
reproducible.

Neither RSA key needs to be reproducible from a scalar for the fixture to be honest: what
must be reproducible is the *token*, and RSASSA-PKCS#1 v1.5 is deterministic, the
certificates carry fixed serial numbers and a fixed validity window, and `genTime` is
derived from the pinned clock. Two runs of `generate.py` therefore emit byte-identical
tokens.

## What is deliberately absent

There is **no AWS KMS key here and there never will be**. In production the log signature
comes from `ECC_NIST_P256` / `ECDSA_SHA_256` in an account separate from both the database
and the archive, and the entire rogue-DBA argument rests on a T1 adversary with arbitrary
SQL having no path to `kms:Sign`. A software key in a file — this file — has no such
property, and that is precisely why it may only ever sign a fixture.

## Refusing to reuse them

`ecdsa_sign_rfc6979` in `generate.py` derives its nonce from the private key and the
message (RFC 6979), so signing the same bytes twice yields the same signature. That is a
determinism property for a published key and a **catastrophe** for a secret one used
carelessly across two schemes without domain separation — which is one more reason the
production path signs with KMS and never with anything in this directory.
