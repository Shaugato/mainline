<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The reference ledger — thirty seconds, no credential, no cooperation from us

```console
$ uvx trappoint-verify verify --bundle evidence/reference-ledger/bundle.json
```

That is the whole ask. No account, no network, no database, nothing installed but Python
and `cryptography`. `bundle.json` is one self-describing file; you can email it.

**What it prints today**, verbatim, against `trappoint-verify 0.1.0`:

```text
16 checks | 9 passed | 0 failed | 7 not checked
exit 2: everything that ran held, and 7 check(s) did not run. This is NOT a clean verification.
```

Nine checks passed and **none failed**. The seven that did not run are the ones whose
modules have not landed yet — signature, RFC 3161, beacon, witness, archive, attestation,
WebAuthn — and the tool refuses to call that a clean verification, which is correct.
`checkpoint chain OK · inclusion OK · consistency OK (n=73) · 0 findings` is what it will
print when all sixteen are bound; quoting that line today would be reporting a plan as a
result, which is the exact failure this whole directory exists to refuse.

> **This key is public by design — the reference bundle proves the verifier works, not
> that MAINLINE's production log is honest.**

Everything else on this page is the small print behind that sentence, and it is here
because a fixture that quietly implies production custody is exactly the overclaim this
domain exists to refuse.

---

## What this bundle is, and what it is not

`bundle.json` is a complete, conforming instance of
[`spec/wire/evidence-bundle.md`](../../spec/wire/evidence-bundle.md) v1.0: 73 leaves across
eight entry kinds, eight signed checkpoints, a consistency proof for **every** consecutive
checkpoint pair, an inclusion proof for **every** leaf, 16 Signed Disposition Receipts, three
schema attestations carrying `pg_get_triggerdef()` text, 16 closure-generation rows, one
re-verifiable WebAuthn assertion, RFC 3161 timestamp tokens, and recorded S3 Object Lock
metadata.

It exists so that a verifier can be tested against a non-trivial input by someone who has
never touched our cluster, before they ever look at a MAINLINE deployment. That is
**Tier 1** of `ARCHITECTURE.md` §7.5 — the tier that needs nothing from anyone. Tier 2
(`git clone && just up`, the merge refusal reproducing on a stranger's laptop) is the tier
the project README leads with, and it is a different, larger claim.

Four things in this bundle are **fixtures**, are labelled as such inside the JSON, and must
never be read as anything else:

| Element | What it actually is |
|---|---|
| the log key | committed in `keys/`, published deliberately; see the sentence above |
| `drand:` / `nist:` beacon lines | synthetic values, chosen so the round→time arithmetic is consistent with the timestamps. **No beacon was consulted.** They exercise check 6's arithmetic, not a beacon issuer |
| `tsa_tokens[]` | RFC 3161 tokens from a timestamp authority `generate.py` mints, from committed RSA keys, on every run. A real bundle carries tokens from ≥ 2 authorities with no MAINLINE relationship |
| `archive.objects[]` | recorded Object Lock **shapes**, never a live S3 response. Check 8 needs `--s3`; without it it reports `SKIP(offline)` and the report labels this section a claim by us about our own archive |

**T3 is not defeated by anything here, or anywhere.** A managed-service operator with
storage-path access — Cockroach Labs, or AWS — is outside the reach of every mechanism in
the database. Only S3 Object Lock in a separate account and external witnesses touch that
adversary at all, and neither is a complete answer. Saying it first is the only version of
that sentence that helps anybody.

**Split-view resistance is not claimed.** The witness cosignature in this bundle carries
`trust_domain: operator` and `adverse: false`, because it is ours. A conforming verifier
reports `PASS(not-adverse)` — a distinct verdict, printed as such — and that is the honest
state until an insurer, a union HSR or a regulator runs the 200-line cosigner themselves.

---

## The named subset — where to look first

Every leaf carries an inclusion proof, because check 16 refuses a bundle where any leaf
does not. If you are reading the file by hand rather than by verifier, these four are the
argument in miniature:

| `seq` | Entry | Why it is the interesting one |
|---|---|---|
| `0` | `schema` | the merge gate's own `CREATE TRIGGER` text, hashed into the tree **before** anything it later refused. The gate is self-attesting (check 11) |
| `1` · `2` | `schema` | the closure's append-only trigger and the `permit_event` chain trigger — the two mechanisms attacks A10 and A11 have to disable first |
| `4` | `check_open` | the first blocking check — a precursor the ancestry walk found |
| `8` | `disposition` | the signed clearance of that check, and the leaf the WebAuthn assertion re-verifies (check 12) |
| `10` | `merge` | the merge the database permitted **afterwards**. This ordering is the product: recall is a precondition of the state transition, not a report about it |

A record of the preconditions the database enforced before work was permitted to start.

---

## Regenerating it

```console
$ python evidence/reference-ledger/generate.py
$ python scripts/custody/regen_reference_ledger.py --check     # zero-diff, as CI runs it
```

Regeneration is **byte-deterministic** and CI asserts it produces no diff, mirroring
`trappoint render`. Every source of variation is pinned: one fixed instant, `uuid5`
identities under a fixed namespace, committed keys, **RFC 6979** deterministic ECDSA nonces
(cross-examined against OpenSSL's own deterministic signer on every run that has one),
PKCS#1 v1.5 for the RSA side, RFC 8785 member ordering, and LF-normalised hashing.

This is not tidiness. Evidence Act 1995 (Cth) ss.146–147 grant a presumption that a device
or process which *ordinarily* produces an outcome did so on the occasion in question. A
generator whose output varies run to run has no "ordinarily" to appeal to.

`bundle.json` is stored as its own RFC 8785 canonical bytes — one line, no indentation —
because §13 of the wire format requires the generated bytes to be the JCS bytes. To read it:

```console
$ python -m json.tool evidence/reference-ledger/bundle.json | less
```

`MANIFEST.sha256` is `sha256sum` format over LF-normalised bytes and covers this file,
`generate.py`, `bundle.json` and every key.

---

## What a verifier finds, check by check

Two columns, because they are two different facts and collapsing them would overstate one.
**Today** is what `trappoint-verify 0.1.0` actually printed when it was run against this
file. **Once the runner lands** is what this bundle carries the material for; a `SKIP` in
the first column is a statement about the verifier's build, never about the bundle.

| Check | Today | Once the runner lands | Why |
|---|---|---|---|
| 1 leaf hashes | **PASS** | PASS | 73 leaf hashes recomputed from the carried `canon_bytes` |
| 2 inclusion | **PASS** | PASS | 73 of 73 |
| 3 consistency | **PASS** | PASS | 7 consecutive pairs, including `0 → 1` (the empty tree is a prefix of every tree) |
| 4 log signature | `SKIP(not-implemented)` | `PASS(self-asserted-key)` unless you pass `--log-key` | the bundle carries its own vkey; a bundle that supplies its own trust anchor proves nothing, and the verdict says so |
| 5 RFC 3161 | `SKIP(not-implemented)` | PASS against the bundled TSA chain | locally minted; interop against FreeTSA / Sigstore is a separate, `unverified` lane |
| 6a NIST pulse | `SKIP(not-implemented)` | `SKIP(offline)` | the note carries the pulse's `outputValue`, not the pulse. Fetching it is an online check |
| 6b drand round | `SKIP(not-implemented)` | PASS on the arithmetic, `SKIP(optional-extra)` on the BLS signature | `cryptography` has no BLS12-381; that is why there are two beacons |
| 7 witness quorum | `SKIP(not-implemented)` | `PASS(not-adverse)` | q = 1, `trust_domain: operator` |
| 8 archive | `SKIP(not-implemented)` | `SKIP(offline)` | needs `--s3` |
| 9 link chain + density | **PASS** | PASS | dense `0..72`, genesis 32 zero bytes |
| 10 canonicaliser identity | **PASS** | PASS | `canon_src_sha256` = `260ed37d…d659` |
| 11 gate self-attestation | `SKIP(not-implemented)` | PASS | **not** `PASS(coarse)` — see below |
| 12 WebAuthn | `SKIP(not-implemented)` | PASS | verifies against the enrolled COSE key **and** the challenge reconstructs |
| 13 sandbox containment | **PASS** | PASS | no leaf carries `is_sandbox: true` |
| 14 closure monotonicity | **PASS** | PASS | 16 rows over 8 `(clause, commit)` pairs, dense from 1, `max_severity` non-decreasing |
| 15 receipt coverage | **PASS** | PASS | 16 receipts, 16 leaves present |
| 16 totality | **PASS** | PASS | every leaf proved, every pair proved, every absent section named |

Nine passed, none failed, seven did not run, and the tool exits **2** — *"everything that ran
held, and 7 checks did not run. This is NOT a clean verification."* That exit code is
correct and it is the point: a verifier that returned 0 here would be reporting the absence
of a module as the absence of a problem.

**GT-05 is answered, and the answer is yes.** `pg_get_triggerdef()` was probed against
CockroachDB CCL **v26.2.5** on 2026-08-10 and returns a fully-qualified, type-annotated
`CREATE TRIGGER` statement. Check 11 therefore keeps per-trigger granularity and does not
fall back to `SHOW CREATE TABLE`; the `PASS(coarse)` path in the specification stays
written down, and stays unused. Two properties of the returned text a third-party
implementer should expect: object names are qualified with the **database** as well as the
schema, and literals carry CockroachDB's `:::TYPE` annotations. An attestation is therefore
compared against the text captured at migration time — never against the migration file.

---

## Related

- [`spec/wire/evidence-bundle.md`](../../spec/wire/evidence-bundle.md) · [`checkpoint.md`](../../spec/wire/checkpoint.md) · [`receipt.md`](../../spec/wire/receipt.md)
- [`spec/custody/checks.yaml`](../../spec/custody/checks.yaml) — the sixteen checks and their status
- [`evidence/CUSTODY_ATTACK_MATRIX.md`](../CUSTODY_ATTACK_MATRIX.md) — what happens when someone attacks a copy of this bundle, generated from [`evidence/custody-nemesis-run.json`](../custody-nemesis-run.json)
- [`keys/README.md`](keys/README.md) — every key in this directory, and why publishing it is safe
