<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I11 — Evidence typing

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the signature and ancestry layers
- **MAINLINE schema invariants that instantiate it:** `MI13`, `MI14`, `MI20`
- **Conformance cases:** 6 (2 on the reference profile)

---

## NORMATIVE STATEMENT

**A prior approval is not evidence. A gist match may not clear. A clearance MUST cite a re-verifiable
verbatim anchor.**

- Evidence MUST be **typed**, and the type MUST be enforced at the point of use:
  - an **inference** may accuse; it MUST NOT arm a gate;
  - a **model-produced rating** MUST NOT arm a gate;
  - a **gist or similarity match** may raise an obligation; it MUST NOT clear one;
  - only a **verbatim anchor** — an object reference plus a byte range plus a span digest — may
    support a clearing verdict.
- The number of verbatim anchors a clearing verdict requires MUST be **projected**, not chosen by the
  signer, and MAY rise where the surrounding material is known to induce false recognition.
- A **prior approval MUST NOT be admissible** as evidence for a weakening that crosses a risk frontier.
  Evidence cited for such a weakening MUST post-date the frontier move.
- A citation typed verbatim MUST carry its anchor. A citation without an anchor MUST be refused, not
  downgraded.

---

## MECHANISM

| Role | SQL object |
|---|---|
| inference cannot arm | `inference_never_blocks` — `CHECK` on the edge's evidential basis and state |
| models cannot arm | `model_cannot_arm` — `CHECK` on the rating's provenance |
| only verbatim acquits | `verbatim_floor` — `CHECK (kind NOT IN (clearing kinds) OR verbatim_anchor_count >= required_anchors)`, both counts **projected** |
| anchors are real | `verbatim_needs_anchor` — a verbatim citation must carry an object key and a span digest |
| no prior approvals | `frontier_evidence` plus `fn_frontier_guard()` — refuse a weakening whose cited evidence does not post-date the frontier move |
| substance | a minimum rationale length, as a vertical policy the customer signs |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| an inferred edge marked active | `23514` | `inference_never_blocks` |
| a model-rated severity arming the gate | `23514` | `model_cannot_arm` |
| a clearing verdict citing only gist evidence | `23514` | `verbatim_floor` |
| a verbatim citation with no object key or span digest | `23514` | `verbatim_needs_anchor` |
| a weakening citing evidence that predates the frontier move | `23514` | `frontier_evidence` |
| a rationale below the substantive floor | `23514` | `substantive` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-24`](../conformance/manifest.toml) | Disposition with a rationale shorter than the substantive floor | `23514` | `substantive` | mainline | 1 |
| [`CF-36`](../conformance/manifest.toml) | mechanism_absent disposition citing only gist evidence | `23514` | `verbatim_floor` | both | 1 |
| [`CF-37`](../conformance/manifest.toml) | Verbatim citation with no object key and no span digest | `23514` | `verbatim_needs_anchor` | both | 1 |
| [`CF-54`](../conformance/manifest.toml) | A semantically inferred blame edge marked active | `23514` | `inference_never_blocks` | mainline | 1 |
| [`CF-55`](../conformance/manifest.toml) | A model-rated severity used to arm the gate | `23514` | `model_cannot_arm` | mainline | 1 |
| [`CF-61`](../conformance/manifest.toml) | A weakening below the risk frontier citing evidence that predates the frontier move | `23514` | `frontier_evidence` | mainline | 2 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the citation is apposite.** A verbatim anchor proves the text exists and was
  quoted; it does not prove it supports the conclusion. That is a human judgement with a signature on
  it, which is the point.
- **It does not claim gist retrieval is unreliable.** Gist accuses well; the asymmetry is deliberate
  and is about *evidentiary force*, not about model quality.
- **It does not claim to detect a fabricated citation.** It makes fabrication *checkable*: the anchor
  is re-verifiable against an immutable object, so a citation to an incident that does not exist
  fails a check somebody can run.
- **It does not claim the anchor requirement is calibrated.** The required count is projected from a
  policy; whether the policy is well calibrated is measured, not asserted.
