<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I12 — No decay without evidence

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the signature and propagation layers
- **MAINLINE schema invariants that instantiate it:** `MI02`, `MI11`, `MI23`, `MI28`
- **Conformance cases:** 6 (4 on the reference profile)

---

## NORMATIVE STATEMENT

**No elevated control state MUST de-escalate by timeout. De-escalation requires a positive evidence
row.**

- The passage of time MUST NOT clear an obligation, downgrade a classification, or convert a bounded
  disposition into an unbounded one. Expiry MUST **re-block**, never release.
- Every bounded window MUST be **bounded, not merely present**: an expiry column that is non-null but
  unconstrained is non-conformant. The window MUST be constrained against its declared maximum by
  `CHECK`.
- A disposition resting on an asserted absence MUST bind a **machine-checkable predicate** over the
  operator's own registers, with a stated probability and a bounded horizon. An unquantified,
  unfalsifiable or unbounded reason MUST NOT be a representable state.
- When such a predicate is falsified, the disposition MUST be revoked automatically, the obligation
  MUST re-open, and the subject's epoch MUST bump — with the revocation timestamped **before whatever
  happens next**.
- Only **tightenings** may propagate automatically across a fleet. A weakening MUST NOT travel.

---

## MECHANISM

| Role | SQL object |
|---|---|
| bounded means bounded | `ttl_enforced` on the disposition; `carried_bounded` on a carried disposition; `predicate_bounded` on the predicate itself |
| expiry re-blocks | the completion trigger's anti-join counts only dispositions that are live **and** unexpired; expiry is evaluated at write time because `now()` is not immutable |
| falsifiable absence | a compiled predicate over named registers, with a stated probability strictly between 0 and 1 and a non-trivial term count |
| automatic revocation | a changefeed watching the named registers; on falsification the revocation is written, the obligation re-opens, the epoch bumps |
| propagation direction | `only_tightenings_travel` |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| complete a subject whose only disposition has expired | `P0001` | `mainline.fn_permit_merge_gate` |
| a disposition whose expiry exceeds its clearance's maximum window | `23514` | `ttl_enforced` |
| a carried disposition whose expiry exceeds its declared window | `23514` | `carried_bounded` |
| an absence-based verdict with no bounded predicate | `23514` | `needs_predicate` |
| propagate a weakening across the fleet | `23514` | `only_tightenings_travel` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-02`](../conformance/manifest.toml) | Merge a permit whose only disposition expired before the merge | `P0001` | `mainline.fn_permit_merge_gate` | both | 2 |
| [`CF-30`](../conformance/manifest.toml) | mechanism_absent disposition with no bounded machine-checkable predicate | `23514` | `needs_predicate` | both | 1 |
| [`CF-32`](../conformance/manifest.toml) | Clearance kind requiring reassertion, supplied with no reassert_by | `23514` | `needs_reassert` | both | 1 |
| [`CF-33`](../conformance/manifest.toml) | Disposition whose expires_at exceeds signed_at plus the clearance's max_ttl_hours | `23514` | `ttl_enforced` | both | 1 |
| [`CF-64`](../conformance/manifest.toml) | Propagate a weakening across the fleet | `23514` | `only_tightenings_travel` | mainline | 1 |
| [`CF-66`](../conformance/manifest.toml) | A carried disposition whose expiry exceeds its declared window | `23514` | `carried_bounded` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not close the window between expiry and the sweep.** A disposition that expires at 04:00
  is refused at the next gate evaluation, not at 04:00:00. The sweep is an operational latency and is
  reported as one.
- **It does not claim the stated probability is calibrated.** It claims it exists, is bounded away
  from certainty, and is attributable — which is what makes it falsifiable rather than rhetorical.
- **It does not claim automatic revocation is instantaneous.** It claims it is *automatic and
  timestamped*, so the record reads *"the firm called the lease at 04:12, before anything happened"*
  rather than *"he signed it away and a man died"*.
- **It does not claim the register watch is complete.** A predicate can only be falsified by a
  register somebody named; naming too few is a modelling failure the substrate cannot detect.
