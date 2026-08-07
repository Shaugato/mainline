<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0041 — The checkpoint wire format is frozen at v1.0 before the first leaf

**Status:** Accepted · **Date:** 2026-08-07 · **Decider:** custody lead · **Milestone:** K2
**Freezes:** `spec/wire/checkpoint.md`, `spec/wire/evidence-bundle.md`, `spec/wire/receipt.md`
**Related:** ADR 0040 (red before green), ADR 0043 (log signature), ADR 0044 (two beacons)

## Context

The checkpoint is the only object in the custody design that **leaves our trust boundary**.
Everything else — the ledger tables, the Merkle nodes, the link chain — lives inside a
database the future defendant owns, and is therefore a checksum rather than evidence. The
checkpoint is what an RFC 3161 authority timestamps, what S3 Object Lock holds, and what a
witness in an adverse trust domain cosigns.

Its wire format is consequently not an implementation detail. It is **the interface a third
party implements against**, and the third party we should design for is not a friendly
integrator. It is an opposing expert writing their own verifier — plausibly in Rust,
plausibly paid to find a discrepancy — who will read the specification, implement it, and
report whatever their implementation says.

Changing that format after a million rows is not a data migration. **It is a migration of
evidence**: every checkpoint signed under the old shape becomes an object that has to be
explained rather than verified, and "we changed the format in 2027, here is a compatibility
shim" is a sentence that costs more in a deposition than every engineering hour it saved.

The ordering constraint follows directly. **Canonical bytes before hashes** — a hash of
bytes nobody can reproduce is not evidence. **Tree before signature** — signing a root you
cannot prove inclusion into is theatre. **Signature before anchor** — anchoring an unsigned
root anchors nothing. **Format before content.**

## Decision

**`spec/wire/checkpoint.md`, `spec/wire/evidence-bundle.md` and `spec/wire/receipt.md` are
frozen at `v1.0` on 2026-08-07, before a single real leaf is written**, each carrying a
complete worked test vector inside a fenced block, and each accompanied by a conformance
list that an independent implementer can work through.

Five rulings inside the freeze:

### 1. The checkpoint is a C2SP signed note, unmodified

Origin, decimal tree size with no leading zeroes, base64 RFC 6962 root, optional extension
lines; text ends in U+000A; blank line; then `— ` + key name + ` ` + base64(4-byte
big-endian key ID ‖ signature). We add nothing to the framing. Using the ecosystem's format
means the witness software that already exists works against us without a fork, and it
means a reader can check our document against `c2sp.org/tlog-checkpoint` rather than
against our good intentions.

### 2. Signature type `0x02`, ECDSA P-256, **DER** — and it is not our choice to make

C2SP defines `0x02` as "ECDSA signatures as implemented by
`github.com/transparency-dev/witness`", and leaves the encoding unstated in prose. It is not
actually ambiguous once you read the reference: that verifier calls Go's
`ecdsa.VerifyASN1` over `SHA-256(note text)`, which is ASN.1 DER. AWS KMS returns DER for
`ECDSA_SHA_256`. The two agree, so MAINLINE stores KMS's bytes verbatim and adds no
re-encoding step.

`spec/wire/checkpoint.md` §5.1 states this **normatively, with a worked vector**, because an
implementer who assumed the fixed-width `r‖s` form (the JOSE/COSE convention) will fail
verification and will not immediately know why. Ten seconds of reading a spec beats a week
of mutual accusation.

The `0x02` **key ID** rule is likewise stated explicitly, because it differs from the
Ed25519 one: `SHA-256(DER SPKI)[:4]`, with no key name and no algorithm byte in the input.
Deriving it the Ed25519 way produces a key ID mismatch and a note that "verifies" against
nothing.

### 3. Three extension lines — `canon:`, `drand:`, `nist:` — and the honest cost

C2SP says extension lines are NOT RECOMMENDED. We use three anyway, and §4.4 of the wire
spec states the cost in the specification itself rather than in a blog post:

> The `0x02` log signature covers the whole note text including extensions. A cosignature of
> type `0x04` or `0x06` does **not**. Therefore the beacon lower bound is exactly as strong
> as the log signature and no stronger, and against a T4 adversary it is not a bound at all.

That paragraph is the reason this ADR exists rather than a wiki page. It means no MAINLINE
deck, README or report can claim a beacon-backed lower bound against a colluding signer
without contradicting a normative document in its own repository.

### 4. The evidence bundle is one self-describing JSON file, and absence is a value

Every optional section, when absent, downgrades a **named** check to `SKIP(reason)` and puts
`NOT CHECKED` at the top of the report. A bundle that omits witness cosignatures does not
quietly pass check 7. This is the same discipline as ADR 0040, applied to the artefact
rather than to the build.

### 5. The receipt's signature input is JCS, not a concatenation

ARCHITECTURE.md §7.2 writes the Signed Disposition Receipt as
`Sign_KMS(entry_id ‖ leaf_hash ‖ site ‖ issued_at ‖ MMD)`. A bare concatenation of
variable-length fields is **ambiguous** — different field values can produce identical byte
strings — and an ambiguous signature input is a canonicalisation attack waiting to be
written up by exactly the reader this format is designed for. `spec/wire/receipt.md` §2
fixes the framing as RFC 8785 JCS with a `typ` member for domain separation. The covered
fields are unchanged; only the framing is pinned. The deviation is recorded in the wire spec
in a block quote, not buried.

## Consequences

**Workers 3 through 10 build against a fixed target.** The Merkle package, the note codec,
the sequencer, the verifier, the witness and the reference bundle all consume these three
documents. None of them has to guess, and none of them can drift, because
`tests/integration/custody/test_k2_exit.py::test_wire_vector_round_trips_through_the_canonicaliser`
reads the canonical bytes out of the markdown fence and hashes them — the document and the
code cannot disagree without the build saying so.

**The worked vectors are verification vectors, not signing vectors.** ECDSA is randomised;
re-signing the same note text produces different bytes that also verify. Every conformance
list says so explicitly, because an implementer who expects byte-reproducible signatures
will conclude our specification is wrong when their own library is behaving correctly.

**A deliberately public key is published in the specification.** `d =
5ae1b3c0…99887`, marked NOT SECRET in three places. Anyone can reproduce every value in
§7 of the checkpoint spec. A test vector nobody can regenerate is a screenshot.

**Extension is cheap; change is not.** New signature lines, new extension names and new
`payload_ver` values are all additive and require no version bump of any consumer, because a
conforming verifier ignores what it does not recognise. Changing lines 1–3, the signature
type, the key-ID derivation or the `canon:` hashing rule is a new document version, and every
checkpoint already signed stays valid under `v1.0` forever.

**There is no mechanism for reissuing a checkpoint, and there never will be.** A checkpoint
found to be defective is answered by a **new** entry recording the defect. Repairing history
to make verification pass is precisely the behaviour this product exists to detect, and a
mechanism that permits it under a flag will eventually be used under that flag.

## Cross-domain dependency, stated because it is currently red

K2 exit criterion 5 requires a **CHANGELOG entry**. `spec/CHANGELOG.md` is owned by the
kernel lead; custody supplies the text, and until the entry lands,
`test_k2_5_checkpoint_wire_format_tagged_v1_0_with_changelog_entry` fails. Suggested entry:

```markdown
### Added — `wire/checkpoint.md`, `wire/evidence-bundle.md`, `wire/receipt.md` at v1.0

The custody wire formats are frozen before the first ledger leaf is written, each with a
worked test vector and a conformance list. C2SP `tlog-checkpoint` profile with note
signature type `0x02` (ECDSA P-256, DER, key ID = `SHA-256(DER SPKI)[:4]`); three extension
lines (`canon:`, `drand:`, `nist:`); the evidence bundle as one self-describing JCS-canonical
JSON file; the Signed Disposition Receipt with a JCS signature input. See ADR 0041.
```

## Revisit trigger

A published erratum to `c2sp.org/signed-note` or `c2sp.org/tlog-checkpoint` that contradicts
§2 or §5.1 of our profile. Anything else — a new algorithm, a new witness, a new beacon, a
new canonicaliser — is additive and is not a revisit.

## References

- [c2sp.org/tlog-checkpoint](https://c2sp.org/tlog-checkpoint), [c2sp.org/signed-note](https://c2sp.org/signed-note)
- `github.com/transparency-dev/formats/note` — the `0x02` reference verifier
- RFC 6962 §2.1, RFC 8785, RFC 3161, RFC 4648 §4
- `BUILD_PLAN.md` §3 K2 exit criterion 5; `docs/leads/custody.md` §1.3, §2 CU-3, CU-4
