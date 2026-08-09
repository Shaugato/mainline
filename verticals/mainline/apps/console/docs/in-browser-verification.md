<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# In-browser verification

**What `src/verify/` is, what it proves, what it refuses to claim, and the contract it
holds with `packages/trappoint-verify`.**

---

## 1. The premise this exists to remove

`BUILD_PLAN.md` §3/K5 contains the sharpest sentence anyone has written about this console:

> the terminal carries claims about the database and the UI carries claims about a human
> decision — an engineer can authenticate a SQLSTATE on screen; nobody can authenticate a
> React component.

That is true **because a React component is normally a rendering of an assertion somebody
else made**. So the console stops being a rendering.

> **The console re-derives, in the browser, from signed bytes, every claim it displays —
> and shows the derivation.**

RFC 8785 canonicalisation, RFC 6962 leaf / node / inclusion / consistency hashing, the
ECDSA-P256 checkpoint signature and the PER silence-root boundary proof are recomputed in a
Web Worker from the same bytes `trappoint-verify` consumes, against committed cross-verifier
vectors. What the custody screen shows is not *the database's word*; it is *our arithmetic
over the database's signature*, and a stranger can run the same arithmetic in Python.

---

## 2. The modules

| File | What it does | Specification |
|---|---|---|
| `jcs.ts` | RFC 8785 canonicalisation and a strict JSON parser that refuses duplicate member names | RFC 8785 |
| `sha256.ts` | WebCrypto SHA-256, plus a software FIPS 180-4 implementation for insecure origins | FIPS 180-4 |
| `bytes.ts` | hex / base64 / UTF-8, each refusing malformed input rather than guessing | RFC 4648 §4 |
| `rfc6962.ts` | leaf and node hashing, `MTH`, inclusion and consistency proofs, the link chain | RFC 6962 §2.1, §2.1.1, §2.1.2 |
| `checkpoint.ts` | C2SP signed-note parsing, vkey parsing, DER→raw, ECDSA P-256 verification, extension lines | `spec/wire/checkpoint.md` v1.0 |
| `silenceroot.ts` | the Proof of Exhausted Recall boundary pair | ARCHITECTURE.md §5.7 |
| `ledger.ts` | the check suite over a whole `ledger` payload, and the honest-limit constants | `spec/custody/checks.yaml` |
| `config.ts` | where the trust anchor came from — build, URL, operator, or nowhere | — |
| `worker.ts` | the message protocol and the Web Worker entry point | — |
| `client.ts` | `WorkerVerifier` and `InlineVerifier` over one handler | — |
| `bundle-verifier.ts` | the `BundleVerifier` that gates `BundleTransport` | `docs/evidence-bundle.md` |
| `useVerification.ts` | the verifier as React state, five states, no partial result | — |

The arithmetic is dependency-free: `jcs.ts`, `sha256.ts`, `bytes.ts`, `rfc6962.ts`,
`checkpoint.ts`, `silenceroot.ts`, `ledger.ts`, `config.ts`, `worker.ts` and `client.ts`
import **nothing at all** — not React, not a crypto library, not each other's siblings
outside this directory. Exactly two files reach outside it, and both are adapters rather
than arithmetic: `bundle-verifier.ts` imports the `BundleVerifier` TYPES from
`src/data/bundle`, and `useVerification.ts` imports React. The check suite can therefore be
lifted into any JavaScript host — a Node script, a Deno one-liner, a different UI — without
carrying the console with it.

---

## 3. The cross-verifier contract

`tests/vectors/` is the contract between this TypeScript implementation and
`packages/trappoint-verify` (Python, offline, dependency floor `cryptography`).

> **Both implementations must agree on every case byte for byte, or CI fails on whichever
> side moved. A vector is never edited to make an implementation pass.**

| File | Cases | What a divergence would mean |
|---|---|---|
| `jcs.json` | 8 canonicalisation cases, 5 refusals | Two verifiers hashing different bytes for the same record — every leaf hash in the ledger becomes unreproducible |
| `rfc6962.json` | 5 leaves, 6 roots, 5 inclusion proofs, 4 consistency proofs, 5 negatives | A proof one side accepts and the other refuses |
| `checkpoint.json` | 13 note cases, 3 vkey cases | A signature one side calls valid |
| `silence-boundary.json` | 6 boundary cases | A silence receipt one side reads as exhaustive |
| `ledger-payload.json` | one complete, cryptographically real `ledger` envelope | The suite has no green path that is not a mock |

**The `jcs.json` values were captured from the Python reference, not from this
implementation.** `packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py` is the module
vendored byte-for-byte into `trappoint-verify` and whose SHA-256 is written into every
checkpoint as `canon_src_sha256`; the generator ran it and recorded its output. A vector
file produced by the implementation it checks would assert only that the implementation
equals itself.

**The `rfc6962.json` and `checkpoint.json` values were asserted against
`spec/wire/checkpoint.md` §7 at generation time.** That worked example is frozen, is signed
by a key published in the specification precisely so anyone can reproduce it, and the
generator refuses to emit a vector that disagrees with it.

### 3.1 Running the same arithmetic in Python

```console
$ pipx run trappoint-verify --vectors verticals/mainline/apps/console/tests/vectors/
```

Every case in the directory is expected to produce the same bytes and the same verdicts.

---

## 4. What is checked in the browser, and what is not

`spec/custody/checks.yaml` is the normative registry of sixteen checks. The browser
implements the subset that requires **no access to our database and no cooperation from
us**, and reports the rest as SKIP with a named reason.

| # | Check | In the browser | Why |
|---|---|---|---|
| 1 | `leaf_hash_recomputation` | **yes** | SHA-256 over the carried `canon_bytes` |
| 2 | `inclusion_proof` | **yes** | RFC 6962 §2.1.1 |
| 3 | `consistency_proof_every_pair` | **yes** | RFC 6962 §2.1.2, for every consecutive pair |
| 4 | `log_signature` | **yes**, when a key is configured | WebCrypto ECDSA P-256 over the note text |
| 5 | `rfc3161_upper_bound` | no | ASN.1 and X.509 chain building; not implemented dependency-free |
| 6 | `beacon_lower_bound` | no | NIST is RSA/X.509, drand is BLS12-381 — no browser primitive verifies either |
| 7 | `witness_quorum` | **yes**, bounded | The SET is checked; the cosignature BYTES are not |
| 8 | `archive_object_lock` | no | Requires an AWS call |
| 9 | `link_chain_and_density` | **yes** | Recomputed, and `seq` asserted dense from 0 |
| 10 | `canonicaliser_identity` | **yes**, when a pin is configured | Compares the signed `canon:` line against `spec/custody/canon-registry.yaml` |
| 11 | `gate_self_attestation` | no | `schema_attestation` is not in the ledger read contract |
| 12 | `webauthn_reverification` | no | Needs the enrolled COSE key and the exposure receipt |
| 13 | `no_sandbox_leaf` | **yes** | Structural |
| 14 | `closure_generation_monotone` | no | Lives in `clause_blame_current`, not the custody ledger |
| — | `payload_vs_canon_bytes` | **yes** | Not a registry check: a DISCREPANCY report (attack A3) |

**A SKIP is printed as loudly as a FAIL, and a report containing one is never clean.**
`CheckReport.overall` is `pass` only when every implemented check passed *and* nothing was
skipped; otherwise it is `bounded` or `fail`, and the custody screen's overall seal is amber
or red accordingly. `spec/custody/checks.yaml` states the reason in its own header: *a
verifier that quietly passes because it did not look is the single worst artefact this
domain could ship.*

---

## 5. Where the trust anchor comes from

A public key is not a secret. The rule that matters is different, and
`contracts/ledger.schema.json` states it:

> A bundle that carries its own trust anchor proves nothing.

So the anchor arrives out of band, and **where it arrived from travels to the screen**:

| `source` | Meaning | Rendered as |
|---|---|---|
| `build` | Compiled in via `VITE_MAINLINE_LOG_VKEY` | "did not arrive with the bundle, and a link cannot override it" |
| `url` | `?log_vkey=` on this page | "chosen by whoever sent you this link — out of band with respect to the BUNDLE, not with respect to the LINK" |
| `operator` | Typed in by the reader | "its provenance is whatever the reader knows it to be" |
| `none` | Nothing configured | Check 4 SKIPS. The seal is amber — never green, and never red |

Build wins over URL, deliberately: a deployment that pinned a key has made a decision, and
a link someone sends must not be able to override it.

---

## 6. The honest limits, stated once

These sentences are exported as constants from `src/verify/ledger.ts`, rendered literally on
the custody surface, and asserted by `tests/browser/custody.spec.ts`. Softening one breaks a
spec rather than passing review.

> **Until an adverse witness runs the cosigning service the quorum is q=1 and split-view
> resistance is NOT claimed.**

> **ANN retrieval is approximate: a Proof of Exhausted Recall proves exhaustion of the
> retrieval that ran, not of the corpus.**

Four more, stated on the screen rather than in a constant:

- Not that a disposition was sincere. Non-repudiation is cryptographic, not moral.
- Not that the narrative in an ingested document is true. Content authenticity is out of
  scope; provenance is in scope.
- Not anything about state at a past time via `AS OF SYSTEM TIME`: the cluster's
  garbage-collection window is 75 minutes (`gc.ttlseconds = 4500`, measured 2026-08-07), so
  long-horizon versioning is the application-level commit DAG.
- The `drand:` line's round TIME is arithmetic and is checked; the round's own BLS12-381
  signature is not, so that line alone is not a lower bound this page established.

---

## 7. Limits of this implementation, as against the Python one

Three, all of them consequences of the language rather than of effort, and all recorded as
data in `tests/vectors/jcs.json` under `enforced_by` so the asymmetry cannot drift silently.

1. **No CU-5 evidentiary profile.** The Python canonicaliser refuses any IEEE-754 float in a
   ledger payload. JavaScript has one number type and cannot distinguish `1` from `1.0`, so
   the browser cannot make that refusal. CU-5 is enforced on the WRITING side, in Python,
   where the distinction exists.
2. **No safe-integer refusal.** Python refuses an integer outside ±(2⁵³−1) because an
   exact-integer implementation and an ECMAScript one would emit different digits. By the
   time such a literal reaches JavaScript it is already a double and the offending digits
   are already gone.
3. **No ECDSA without WebCrypto.** SHA-256 has a software fallback and works on an insecure
   origin; the signature check does not. On a page served over plain `http://`, check 4
   reports SKIP with the reason, and no seal on the checkpoint is green.

---

## 8. Why a Web Worker

Not for speed — a bundle is a few hundred kilobytes and SHA-256 over it is milliseconds.

1. **The main thread must not be able to lie about a result it computed itself.**
   Verification lives behind a message boundary with a typed protocol and no shared state.
   That is a weak guarantee against a hostile author and a strong one against an ordinary
   refactor, and ordinary refactors are what erode a claim over a year.
2. **A 40 000-leaf tree must not freeze the refusal screen.** The demo corpus is small; the
   product's ledgers are not, and a verifier that has to be re-architected the first time it
   meets a real log is a verifier that will be turned off instead.

`InlineVerifier` exists for environments with no `Worker` constructor — jsdom, a sandboxed
iframe, a CSP without `worker-src`. It calls the **same handler**, so the two cannot drift,
and the reason it was used is carried to the screen in `describe().transportNote`. A silent
fallback would make "verified in a worker" a claim nobody could check.

---

## 9. How a bundle is gated

`src/data/bundle.ts` states the contract: `BundleTransport` computes no digest, verifies no
signature, has no default verifier and no skip option, and `exchange()` cannot return before
`verify()` has resolved with `verdict: 'verified'`.

`InBrowserBundleVerifier` is the other half. Its judgement is a split:

**FAIL — no frame is served at all:**

- a listed file whose SHA-256 does not match `manifest.files[].sha256`;
- a listed file that cannot be read;
- a checkpoint note that will not parse, or whose signed tree size or root disagrees with
  what `manifest.checkpoint` claims.

**SKIP — recorded as a finding, bundle still servable:**

- no log verification key is configured, so the checkpoint SIGNATURE was not checked;
- the manifest declares no checkpoint.

A digest mismatch means the bytes on the wire are not the bytes that were sealed, so nothing
downstream runs. An unconfigured trust anchor means *we* cannot check something; refusing to
render would punish the reader for our own missing configuration. Both outcomes are visible.

---

## 10. The staged demo fixture fails, and that is correct

`fixtures/bundles/blk-07/` is hand-authored. Its own `ledger/bundle.json` says so:

> Running `trappoint-verify` against it MUST fail, and that failure is the correct outcome.

The custody surface makes **no exception** for it. Fed the staged bundle, the screen renders
a red `leaf_hash_recomputation` seal and prints which leaves disagreed. A verifier with a
fixture allowlist is not a verifier.

The green path is `tests/vectors/ledger-payload.json`: cryptographically real — every leaf
hash, link hash, root, inclusion path, consistency proof and ECDSA signature is genuine and
reproducible from `spec/wire/checkpoint.md` §7 — and operationally staged, which its own
`staged_note` says at length. `tests/browser/custody.spec.ts` serves it, watches every seal
go green, then flips one byte and watches the frame get blocked.

---

## 11. Running the checks

```console
$ pnpm -C verticals/mainline/apps/console test        # the unit tier, including every vector
$ pnpm -C verticals/mainline/apps/console test:browser -- custody.spec.ts audit.spec.ts
```

The unit tier needs no network, no database, no cloud account and no model call. The browser
tier needs `playwright.config.ts` (owned by the `cinema-conformance-harness` worker) and a
shell that composes a transport; until both land it is red, and the reason is written at the
top of each spec rather than suppressed.
