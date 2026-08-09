<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0043 — CU-3: the log signature is ECDSA P-256, C2SP note type `0x02`, DER as KMS returns it

**Status:** Accepted · **Date:** 2026-08-04 · **Decider:** custody lead · **Milestone:** K2
**Supersedes:** nothing · **Implements:** `docs/leads/custody.md` §2 decision **CU-3**
**Depends on:** ADR 0041 (checkpoint wire format), ADR 0040 (custody red before green)
**Implemented by:** `packages/trappoint-ledger/src/trappoint_ledger/note/`,
`checkpoint.py`, `signer.py`

## Context

A checkpoint is the only object in the custody design that leaves our trust boundary. Its
signature is what a witness cosigns alongside, what an RFC 3161 authority timestamps a
copy of, and what an opposing expert's own verifier must be able to check without asking
us anything. The algorithm and — more importantly — the *encoding* are therefore not an
implementation detail. They are the interface.

Three facts constrain the choice.

**AWS KMS cannot produce Ed25519.** C2SP note type `0x01` is Ed25519 and it is what the
public witness ecosystem prefers. KMS offers RSA, ECC NIST P-256/384/521 and ECC secp256k1,
and no Edwards curve. The only way to sign Ed25519 notes is a software key, which means a
private key living in the memory of a Lambda or a container.

**A software key destroys the argument the ledger exists to make.** The whole rogue-DBA
case is that a T1 adversary holding arbitrary SQL — including `DROP TRIGGER`, including
`DELETE FROM ledger_leaf` — still has no path to `kms:Sign`, because signing lives in a
different account behind a key policy they do not control. A key in process memory is a key
reachable from a process compromise, and the separation collapses.

**C2SP registers `0x02` for ECDSA P-256, but does not pin its encoding in prose.** It
defines the type as "ECDSA signatures as implemented by `github.com/transparency-dev/witness`".
That implementation verifies with Go's `ecdsa.VerifyASN1` over `SHA-256(note text)`, which
is ASN.1 DER `SEQUENCE { r INTEGER, s INTEGER }`. A reader who assumes the JOSE/COSE
convention — fixed-width `r‖s`, exactly 64 bytes for P-256 — writes a verifier that rejects
every checkpoint we ever signed, and finds out at the worst possible moment.

## Decision

**1. The log signature is C2SP signed-note type `0x02`: ECDSA over NIST P-256 with SHA-256.**
The key is an AWS KMS `ECC_NIST_P256` / `SIGN_VERIFY` key in an account separate from both
the database and the archive.

**2. The signature bytes are the ASN.1 DER encoding exactly as `kms:Sign` returns them.**
There is no re-encoding step anywhere in this repository. `KmsSigner.sign` returns the
`Signature` field verbatim; `build_signature_line` base64s `key ID ‖ those bytes`. The
choice is normative in `spec/wire/checkpoint.md` §5.1 with a worked verification vector,
because C2SP leaves it to a reference implementation and an opposing expert must not have
to guess.

**3. The call is `Sign(MessageType='RAW', SigningAlgorithm='ECDSA_SHA_256')` over the note
text.** Both values are module constants, not parameters. `MessageType='DIGEST'` would have
KMS treat our 446-byte note text as if it were a SHA-256 digest; the resulting signature
verifies against nothing computable.

**4. The `0x02` key ID is `SHA-256(DER SPKI)[:4]` — no name, no algorithm byte** — and it
is *derived*, never accepted. `note.keyid.PublicKey` has no `key_id` field; it recomputes
one from the key material at construction, so a key whose ID disagrees with its bytes is
unrepresentable. `parse_vkey` compares the recomputed value against the vkey's field and
raises `KeyIdMismatch` rather than trusting it, per §5.2.

**5. Adding Ed25519 later is additive and costs nothing.** The note format ignores signature
lines whose key it does not know, so a `0x01` line can be added to every future checkpoint
without a format version bump and without invalidating a single existing one. If a witness
network we care about demands Ed25519, we add a second line; we do not move the log key out
of KMS.

**6. `cryptography` is not a dependency of `trappoint-ledger`.** The signature primitive is
injected as a callable (`SignatureVerifier`), and `signer.py` imports `cryptography` lazily
inside the two functions that need it, raising `SigningBackendUnavailable` with the install
line if it is absent. `trappoint_ledger.note`, `.checkpoint`, `.beacon` and `.merkle`
therefore import and function on the same floor `trappoint-verify` promises a stranger, and
`test_signer.py::test_the_ledger_still_imports_and_verifies_structure_without_cryptography`
proves it in a subprocess with the module blocked.

## Consequences

- We are standards-compliant without a private-use type byte, and interoperable with the
  `transparency-dev` verifier that defines `0x02`.
- We give up the algorithm the public witness ecosystem prefers, and keep the property that
  makes the ledger worth having.
- The DER-versus-`r‖s` trap is now a ten-second discovery: `spec/wire/checkpoint.md` §7.4
  publishes a 71-byte DER signature and `test_signer.py` asserts its structure.
- `packages/trappoint-ledger/pyproject.toml` does **not** declare `cryptography`. The
  signing tests `importorskip` it and say so loudly. Declaring it as an optional extra is
  the outstanding item — see "Cross-domain note" below.

## Gaps found in `spec/wire/checkpoint.md` v1.0, and how each is resolved

The specification was frozen before any implementation existed, which is correct and is
also why implementing it surfaces under-specified corners. Each is recorded here rather
than resolved silently in code, per the instruction in the worker brief. None of them
changes a signed byte of the worked vector.

| # | Gap | Resolution in `trappoint-ledger` |
|---|---|---|
| **G1** | §4 says extension lines "MUST appear in the order given below" but defines only three names, and §4 also requires a verifier to ignore names it does not recognise. It cannot say where an *unrecognised* name sits relative to a recognised one. | The relative order of `canon`, `drand`, `nist` is enforced, and each may appear at most once. An unknown name is admitted at any position and preserved. Enforcing a total order would make §9's additive path impossible, which is the opposite of what §4 intends. |
| **G2** | §2 forbids ASCII control characters below U+0020 "in the whole note"; §6 step 2 forbids them "outside the signature lines". | The §2 reading is enforced — strictly stronger, and it cannot reject a conforming note, since a key name may not contain whitespace and base64's alphabet has no control characters. |
| **G3** | §2 says a verifier MUST accept **at least** 16 signature lines. No maximum is stated. | No maximum is imposed. Refusing a checkpoint for carrying "too many" cosignatures would turn a quorum success into a parse failure, which is the wrong failure. |
| **G4** | The format does not say whether two signature lines may share a `(name, key ID)` pair. | Duplicate lines are decoded and preserved; the *key set* handed to `verify_note` may not contain two keys with one lookup (that is a verifier misconfiguration and raises). A duplicated line from a known key simply verifies twice. |
| **G5** | §3 says line 3 is "base64 of the 32-byte hash" without saying whether a decoder must reject non-canonical padding bits. | Non-canonical base64 is rejected: the line must be byte-identical to the canonical encoding of the bytes it decodes to. Two spellings of one checkpoint would mean only one of them is the one that was signed. |
| **G6** | `spec/wire/receipt.md` §4 steps 4–5 compare against "the newest checkpoint's timestamp". A bundle may carry no checkpoint at all, in which case that quantity does not exist. | A fourth verdict, `SKIP(no-checkpoint)`, distinct from `SKIP(within-mmd)`. Returning `FAIL` would accuse the log operator on the strength of a bundle that was never assembled; returning `PASS` would be worse. Reported as loudly as a FAIL, per ADR 0046. |
| **G7** | Migration `0075_ledger_checkpoint.sql` cites "`spec/wire/checkpoint.md` §7.3" for the empty-tree checkpoint; §7.3 is the note text and §7.6 is the empty tree. | Cosmetic cross-reference drift in a file this worker does not own. Recorded, not edited. |

## Cross-domain note

`packages/trappoint-ledger/pyproject.toml` is owned by another worker and is unchanged by
this ADR. To make the signing tests run rather than skip under `uv sync`, it needs
`cryptography>=42` added as an **optional extra** (e.g. `[project.optional-dependencies] sign`)
and to the package's `dev` dependency group — never as a hard runtime dependency, which
would silently move the floor described in decision 6.

## References

- [c2sp.org/signed-note](https://c2sp.org/signed-note), [c2sp.org/tlog-checkpoint](https://c2sp.org/tlog-checkpoint)
- `github.com/transparency-dev/formats/note` — the `0x02` reference verifier
- AWS KMS `Sign` / `GetPublicKey` API reference (`SigningAlgorithm`, `MessageType`, `KeySpec`)
- `spec/wire/checkpoint.md` §5, §7, §10 · `spec/wire/receipt.md` §2.2
- `docs/leads/custody.md` §2 CU-3
