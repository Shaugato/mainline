<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I09 — Exposure binding

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the signature layer
- **MAINLINE schema invariants that instantiate it:** `MI08`, `MI12`
- **Conformance cases:** 5 (5 on the reference profile)

---

## NORMATIVE STATEMENT

**A disposition MAY exist only against a precursor materialised to *that* actor in *that*
transaction.**

- The disposition MUST hold a composite foreign key onto the exact `(exposure receipt, obligation)`
  pair the substrate rendered to the signing actor. Not to the obligation alone; to the pair.
- The exposure receipt MUST record what was rendered — the digest of the exact payload, its size, the
  corpus state at the read, and the policy version — and MUST be issued by the **server clock**.
- The receipt MUST be bounded: a disposition against an expired receipt MUST be refused, and expiry
  MUST be evaluated at write time, since no `CHECK` can hold a time comparison.
- Deliberation time MUST be derived from the server-issued receipt timestamp, never supplied by the
  client.
- The signature MUST cover the receipt: a countersignature MUST be a **different credential**.

---

## MECHANISM

| Role | SQL object |
|---|---|
| the binding | `fk_exposure` — `FOREIGN KEY (receipt_id, check_id)` onto the exposure line |
| the receipt | an append-only exposure receipt with a per-line payload digest and token count |
| expiry | `fn_disposition_project()` refuses against an absent or expired receipt; a sweeper marks expiry by writing a **new** row, never by updating the receipt |
| derived deliberation | `fn_disposition_project()` computes elapsed time from the server-issued receipt timestamp |
| the reading floor | a computed, positive-polarity flag projecting a subject counter, offset by a countersignature counter — breaching it **prices** a second signer rather than raising |
| distinct credentials | `distinct_credential`, `uv_required` |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| dispose against a `(receipt, obligation)` pair never materialised to that actor | `23503` | `fk_exposure` |
| dispose against an expired or absent receipt | `P0001` | `mainline.fn_disposition_project` |
| two live dispositions against one obligation | `23505` | `one_live_disposition` |
| record a disposition without user verification | `23514` | `uv_required` |
| countersign with the signer's own credential | `23514` | `distinct_credential` |
| complete with an unmet reading floor and no countersignature | `23514` | `reading_floor_when_issued` |

*"It never showed me"* and *"I signed without looking"* are both violations of one foreign key.

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-12`](../conformance/manifest.toml) | Two live dispositions against one blocking check | `23505` | `one_live_disposition` | both | 1 |
| [`CF-18`](../conformance/manifest.toml) | Disposition against a (receipt, check) pair that was never materialised to the signing actor | `23503` | `fk_exposure` | both | 1 |
| [`CF-21`](../conformance/manifest.toml) | Disposition against an exposure receipt that has already expired | `P0001` | `mainline.fn_disposition_project` | both | 1 |
| [`CF-25`](../conformance/manifest.toml) | Disposition recorded with user_verified = false | `23514` | `uv_required` | both | 1 |
| [`CF-26`](../conformance/manifest.toml) | Countersignature made with the signer's own credential | `23514` | `distinct_credential` | both | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the human read it.** It claims the system rendered it, to that person, in that
  transaction, and that the signature covers the digest of what was rendered. Whether they read it is
  not knowable and this specification declines to pretend otherwise.
- **It does not claim a disposition can be distinguished from a rubber stamp.** It cannot, and no
  document produced from this system may say it can. The reading floor *measures* and *prices*; it
  does not adjudicate.
- **It does not identity-proof anyone.** It binds a credential and a verified user presence. Who
  holds the credential is an enrolment question outside this substrate.
- **It does not survive offline signing, and offline signing is therefore forbidden.** A queue-and-sync
  design manufactures dispositions with reconstructed timestamps, which is the single worst
  evidentiary artefact this system could produce.
