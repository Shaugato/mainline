<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `cat_key` v1 — normative encoding specification

**Status:** normative. **Version tag:** `cat1`. **Owner:** algorithms domain, worker W3 (`cat-seal`).
**Conformance fixture:** `tests/fixtures/domain/cat/golden-vectors.json`.
**Reference implementation:** `mainline_domain.cat.preimage`.

This document defines, completely and without reference to any source file, how a
**Control Assertion Tuple (CAT)** is serialised to a byte string (the *preimage*)
and how that preimage becomes `mainline.clause_version.cat_key`.

It is written so that an opposing expert with a hex editor and a SHA-256
implementation can re-derive every `cat_key` this system has ever stored, and
disagree with us in public if we got one wrong. Everything needed to do that is
in this file. The golden vectors are the conformance suite; an implementation
that reproduces all of them byte-for-byte is conformant.

---

## 1. Why this is not JSON

`cat_key` is identity axis 2: the thing that survives a rewrite in which every
word of a clause changes. Two obligations with the same `cat_key` are the same
obligation, and blame attaches through that equality. An encoding that admits
*any* ambiguity therefore admits a way to make one obligation look like another,
or to make one obligation look like two.

JSON is the wrong tool for that job, for three specific reasons and not as a
matter of taste:

1. **Number formatting is unspecified in practice.** `50`, `50.0`, `5.0e1` and
   `50.00` are the same JSON number and different JSON texts. A canonicalisation
   profile (RFC 8785) fixes this, but only by mandating IEEE-754 double
   serialisation — and a safety setpoint is a `Decimal`, not a double.
2. **A second canonicaliser is a second liability.** This repository already
   vendors one digest discipline (`canon_sha256`, see
   `mainline_domain.canon.digest`). Vendoring an RFC 8785 implementation would
   add a large, subtle, security-relevant dependency whose bugs would be
   *our* bugs, silently, in the identity axis.
3. **Object key ordering, string escaping and Unicode escapes** each admit more
   than one correct answer. Every one of those is a place two conformant
   encoders could disagree.

The encoding below has none of those degrees of freedom. Every field is
length-prefixed, so concatenation is unambiguous; every field is type-tagged, so
*absent* and *empty* are different byte strings; and the one numeric type has a
single canonical spelling defined in §4.

---

## 2. The tuple

A CAT has exactly **thirteen** fields, in exactly this order. The order is
normative and is never sorted, reordered or omitted.

| # | Field | Type | Notes |
|---|---|---|---|
| 1 | `actor` | TEXT | who is bound |
| 2 | `deontic` | TEXT | `MUST`, `MUST_NOT`, `SHOULD`, `SHOULD_NOT`, `MAY`, `ABSENT` |
| 3 | `action` | TEXT | canonical action key |
| 4 | `object_class` | TEXT | what the action is performed on |
| 5 | `hazard_energy` | TEXT | the energy the control stands between |
| 6 | `parameter` | TEXT | `safe_direction` registry key, or `""` |
| 7 | `comparator` | TEXT | `<=`, `>=`, `<`, `>`, `=`, `~`, `+/-`, `range`, `""` |
| 8 | `value` | QUANTITY \| ABSENT | the setpoint |
| 9 | `conditions` | LIST of TEXT | when the obligation applies |
| 10 | `exceptions` | LIST of TEXT | when it does not — **hedges live here** |
| 11 | `verification` | LIST of TEXT | independent checks, hold points, signatures |
| 12 | `frequency` | QUANTITY \| ABSENT | test/inspection interval |
| 13 | `coverage_quantifier` | TEXT | `all`, `any`, `selected`, `typical`, `unspecified` |

A field of TEXT type is **never** absent: a missing text slot is the empty
string. Only `value` and `frequency` may be ABSENT, and for those two, ABSENT
and "empty" are distinct encodings that produce distinct `cat_key`s.

Fields 9–11 are ordered lists. **The encoder does not sort them.** Ordering is a
normalisation decision, made before encoding, and specified in §7. This is
deliberate: an encoder that silently sorted would hide a normaliser that did not.

---

## 3. Field encoding

Every field is encoded as exactly three parts, concatenated:

```
  <type_byte : 1 byte> <length : uint32, big-endian> <payload : `length` bytes>
```

`length` is the length of `payload` **in bytes**, not in characters. There is no
alignment, no padding and no terminator.

### 3.1 Type bytes

| Byte | Name | Payload |
|---|---|---|
| `0x00` | ABSENT | empty; `length` is `0x00000000` |
| `0x01` | TEXT | the field's UTF-8 bytes |
| `0x02` | LIST | the concatenation of each element encoded as a **TEXT field** |
| `0x03` | QUANTITY | four **TEXT fields** concatenated: value, unit, dimension, reference |

No other type byte is defined in `cat1`. An encoder that emits one is not
conformant; a decoder that accepts one is not conformant.

### 3.2 TEXT

Payload is the string encoded as UTF-8, no BOM, shortest form, unnormalised at
this layer — Unicode normalisation is §7's job, not the encoder's. The empty
string is `01 00000000` and is **not** the same as ABSENT (`00 00000000`).

### 3.3 LIST

Payload is the concatenation of `n` complete TEXT fields, one per element, in
list order. `length` is the total byte length of that concatenation, so the
outer length prefix and the inner ones are both present and both mandatory.

An empty list is `02 00000000`. A one-element list containing the empty string
is `02 00000005 01 00000000` — five payload bytes. These are different byte
strings and therefore different `cat_key`s, which is the intended behaviour: "no
exceptions" and "one exception, unnamed" are not the same obligation.

### 3.4 QUANTITY

Payload is exactly four TEXT fields, concatenated, in this order:

1. **value** — the canonical decimal string of §4
2. **unit** — the unit token, as a string, verbatim
3. **dimension** — the dimension name, as a string, verbatim
4. **reference** — one of `absolute`, `gauge`, `delta`, `none`

`length` is the total byte length of those four fields.

`reference` is load-bearing and is never inferred at this layer. `50 psig` and
`50 psia` differ in the fourth sub-field and therefore in the `cat_key`. That is
the whole point of the field: a gauge reading silently treated as absolute flips
a `safe_direction` comparison, so a weakening reads as a strengthening. The
encoding refuses to let the two collide.

---

## 4. Canonical decimal string

A setpoint is a `Decimal`, never a float. `Decimal` carries *significance*:
`Decimal("50")` and `Decimal("50.0")` are equal in value and different in
representation. Identity must follow value, so the encoding defines one spelling
per value:

1. If the decimal is not finite (`NaN`, `sNaN`, `Infinity`, `-Infinity`), the
   encoder **raises**. There is no canonical spelling for a non-finite setpoint
   and there is no safe default.
2. Render the exact value in **plain positional notation**, with no exponent, no
   thousands separator, no leading `+`, and no leading zeros other than the
   single `0` before a decimal point.
3. If a decimal point is present, strip trailing zeros from the fractional part,
   then strip a trailing decimal point.
4. If the result is `-0`, `-` or empty, the result is `0`. Negative zero has no
   distinct canonical form.

Worked examples:

| Input | Canonical |
|---|---|
| `Decimal("50")` | `50` |
| `Decimal("50.0")` | `50` |
| `Decimal("50.000")` | `50` |
| `Decimal("5E+1")` | `50` |
| `Decimal("0.500")` | `0.5` |
| `Decimal("-0.0")` | `0` |
| `Decimal("-12.340")` | `-12.34` |
| `Decimal("1E-7")` | `0.0000001` |
| `Decimal("0")` | `0` |

Consequence, stated so nobody is surprised by it later: two CATs that compare
equal under Python's `Decimal` equality produce **the same** `cat_key`, because
`Decimal("50") == Decimal("50.0")`. That is the intended invariant, and it is
tested.

---

## 5. The preimage

```
  preimage := DOMAIN || 0x1F || F1 || F2 || F3 || ... || F13
```

where

* `DOMAIN` is the 15 ASCII bytes `mainline/cat/v1`
  (hex `6d 61 69 6e 6c 69 6e 65 2f 63 61 74 2f 76 31`),
* `0x1F` is the ASCII unit separator, and
* `F1 … F13` are the thirteen fields of §2, each encoded per §3, in order.

The domain prefix carries the version. A future `cat2` changes the prefix, which
changes every preimage, which is the intended cost: `cat_key` is stored on
`clause_version` rows that blame edges point at, so re-keying history is a
migration, never a config flag — exactly as `canon_version` is.

The `0x1F` separator is redundant given the fixed prefix length, and is kept
anyway so a preimage is visibly self-describing in a hex dump.

---

## 6. `cat_key`

```
  cat_key := "cat1:" || lowercase_hex( SHA-256( preimage ) )
```

`cat_key` is therefore always 69 characters: five for `cat1:` plus sixty-four
hex digits, lowercase, no separators. It is stored in
`mainline.clause_version.cat_key STRING NULL`; `NULL` means *no CAT was
extracted*, which is a different fact from `cat_confidence='opaque'` (a CAT was
attempted and the clause's control is not machine-readable).

---

## 7. Normalisation — what happens *before* the encoder

The encoder is dumb on purpose. Everything judgemental happens first, in
`mainline_domain.cat.normalise`, and is specified here because a `cat_key` is
only reproducible if the normalisation is:

1. **Closed-vocabulary slots** (`actor`, `action`, `object_class`,
   `hazard_energy`, `parameter`, `comparator`, `coverage_quantifier`) are
   NFKC-normalised, `casefold()`ed, internal whitespace collapsed to single
   `U+0020`, and stripped. `deontic` is NFKC-normalised, whitespace-collapsed,
   stripped and **upper-cased** — it is the one closed slot that is not
   lower-cased, because the deontic-modality taxonomy labels are upper-case by
   convention and the lattice's R1 ordering table is written in them.
2. **Free-text lists** (`conditions`, `exceptions`, `verification`) have each
   element NFKC-normalised, `casefold()`ed, whitespace-collapsed, and stripped
   of trailing whitespace and trailing `.`, `;`, `,` — **unless stripping would
   empty the element**, in which case it is left as-is. Empty elements are
   dropped; duplicates are dropped, keeping the first occurrence.

   The stripping rule reads oddly and both halves are necessary. Removing one
   mark at a time is not idempotent (`a..` → `a.` → `a`), and a non-idempotent
   normaliser gives one CAT two canonical forms and therefore two `cat_key`s.
   Stripping unconditionally would turn an element consisting only of
   punctuation into the empty string, which is then dropped — silently deleting
   an exception, the one direction rule R4 must never be wrong in.
3. **List ordering** is then by the **UTF-8 bytes** of the element, ascending.
   Byte order, not locale order, not code-point order of the original — the
   normalised element's UTF-8 bytes compared as unsigned octets. A locale
   collation would make `cat_key` depend on the machine's environment.
4. **Quantities** are converted to SI **with the reference class preserved**.
   `50 psig` becomes `344.7...  kPa` with `reference='gauge'`; it never becomes
   `446 kPa` with `reference='absolute'`. A gauge↔absolute crossing raises and
   the error propagates; it is never caught, defaulted or logged-and-continued.
   A unit the converter does not know is left verbatim (its `cat_key` is then a
   function of the unit *as written*, which is honest and reproducible).

Steps 1–3 are self-contained and reproducible from this document. Step 4 depends
on the vendored unit definitions, which are themselves committed and versioned.

---

## 8. Confidence, and what it is not

`cat_confidence` is exactly one of `ok`, `low`, `opaque` — the three values the
`clause_version` `CHECK` permits. It is a property of the *extraction*, not of
the encoding, and it never changes a `cat_key`.

* **`ok`** — every slot the clause asserts was filled from a verifiable evidence
  span in `canon_text`.
* **`low`** — the extractor could not fill `parameter`, `comparator` or `value`
  with a verifiable span, or filled them in a form it knows is lossy (a
  `between X and Y` range keeps the lower bound only, and is always `low`).
* **`opaque`** — the clause's control is not in the prose: a table row, a figure
  or drawing reference standing in for the setpoint, or a bare cross-reference.
  This is a **product state**, not a retryable failure. Any edit to an `opaque`
  clause with severity ≥ 4 ancestry defaults to `weaken`, and the residue reason
  is `opaque_control`. The system deliberately over-blocks here, and says so.

---

## 9. Test vectors

`tests/fixtures/domain/cat/golden-vectors.json` is the conformance suite. Each
entry carries the CAT (with decimals as strings, never as JSON numbers), the
full `preimage_hex`, and the `cat_key`. The suite is chosen to pin every
degree of freedom this document removes:

| Vector | What it pins |
|---|---|
| V01 | a fully populated obligation; the baseline |
| V02 | `value` ABSENT vs present — different key |
| V03 | present-but-empty TEXT in `comparator` |
| V04 | empty LIST |
| V05 | LIST of one empty string — differs from V04 |
| V06 | non-ASCII payload; `length` is bytes, not characters |
| V07 | `Decimal("50.000")` — canonical decimal, equals V01's key |
| V08 | `Decimal("5E+1")` and a negative — exponent and sign handling |
| V09 | `reference='absolute'` vs V01's `gauge` — different key |
| V10 | list order is significant; the encoder does not sort |
| V11 | field-boundary ambiguity: `actor="ab", action="c"` |
| V12 | field-boundary ambiguity: `actor="a", action="bc"` — differs from V11 |
| V13 | `frequency` present with `value` ABSENT |
| V14 | prohibition with a hedge in `exceptions` and a long `verification` list |
| V15 | the zero CAT: every TEXT empty, every LIST empty, both quantities ABSENT |

V11 and V12 are the reason length prefixes exist. Without them both would encode
to the same bytes, and two different obligations would share one identity.

---

## 10. Known limitations of `cat1`

Stated here rather than discovered later:

* A `between X and Y` range keeps the lower bound and the comparator `range`.
  The upper bound is not in the tuple, so two clauses differing only in their
  upper bound share a `cat_key`. Extraction marks these `low`, which is the
  mitigation, not a fix. A `cat2` would add a second quantity slot.
* `frequency` uses the unit as written where the converter does not know it —
  `shift` is a site-defined interval, not an SI one, so `1 shift` normalises to
  itself. Two sites with different shift lengths therefore share a `cat_key` for
  the same written frequency. This is correct for identity (the clause says
  "each shift") and wrong for arithmetic (the lattice cannot compare `1 shift`
  to `12 h`); the lattice is required to treat an unconvertible frequency
  comparison as unknown, and unknown resolves to `weaken`.
* Nothing in this encoding distinguishes a considered CAT from a careless one.
  It makes the tuple exact; it does not make the extraction wise.
