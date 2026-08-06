<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0001 — G0 (counsel gate): pre-committed default executed

**Status:** Accepted · **Date:** 2026-08-06 · **Decider:** Shaugato (founder)

## Context

`BUILD_PLAN.md` §2 (K0 CLEARANCE) defines gate **G0**: a paid one-hour consultation with an Australian resources-sector WHS/safety lawyer, putting four questions:

1. Can a retrospective MOC Ancestry Audit be structured under **legal professional privilege** in Queensland, and does that privilege survive the transition to a running production system designed to be produced in court?
2. Does a signed, named `mechanism_absent` disposition against a fatality-linked precursor, made 48 hours before an incident, **help or hurt the defence** relative to no record existing at all — and does the answer change if the system also logs every precursor it declined to surface, with its arithmetic?
3. Would you introduce this to a client GC?
4. Does per-approver dwell timing constitute computer surveillance requiring notice under the NSW Workplace Surveillance Act 2005 or its analogues?

The gate exists because the adversarial audit (`research/04-final/audit.md`) identified the disposition record as the project's single largest unvalidated assumption, in both a prospective form (a signed `mechanism_absent` preceding a fatality is a conscious-disregard exhibit) and a retrospective one (the paid audit's own deliverable is a dated, named-author catalogue of un-reviewed weakenings, presumptively discoverable).

## Decision

**G0 is not sought at this time. The pre-committed default is executed**, per `BUILD_PLAN.md` §2 exit criterion 1 and §2.1.

Rationale: the counsel hour is necessary for the **commercial wedge** and for freezing the **final legal shape** of the disposition record. It is *not* necessary to build the platform, to satisfy any hackathon requirement, or to demonstrate the gate. Idling the build on a lawyer's diary would be a self-inflicted schedule wound for no engineering gain.

## Consequences

**The build proceeds in full.** All migrations, the kernel, recall, custody, the agent fleet, the corpus, the demo and the console are built to completion. The gate refuses exactly as designed.

**The five counsel-sensitive DDL files ship behind the vertical's `disposition_ext` extension point, under the conservative reading:**

| File | Conservative reading applied |
|---|---|
| `0066 disposition` | No `mechanism_absent` disposition kind permitted over fatal (severity ≥ 4) ancestry |
| `0067 disposition_citation` | `evidence_opened` is recorded; citation is mandatory, not optional |
| `0068 override_ledger` | Ships; override remains site- and signer-scoped and monotone |
| `0069 carried_disposition` | Ships with the bounded-window TTL constraint |
| `0086 silence_ledger` | Ships **unprivileged** — treated as discoverable by default |

The shape is therefore **configuration, not DDL**: when G0 is later answered, the change is a policy value, not a migration.

**Two things are withheld until G0 clears:**

1. **No public claim about the paid MOC Ancestry Audit product.** Not in the README, not in the submission, not in the video, not on any site.
2. **The `mainline-audit` policy package** (thresholds, the FSL side of the measurement family) is not published.

**Per-approver dwell timing** (question 4) defaults to **off**. Deliberation is derived from server-side `exposure_receipt.issued_at`, which is a record of what the system did, not a measurement of a worker. Any per-person measurement family remains opt-in behind `person_measure_policy` and is not enabled in the demo or in any default configuration.

## Revisit trigger

G0 must be answered **before** any of the following:

- the first commercial conversation about the paid audit;
- publishing the `mainline-audit` package;
- enabling any per-person measurement in a customer tenant;
- freezing the disposition kind vocabulary as a SemVer-stable public API.

## References

- `BUILD_PLAN.md` §2, §2.1, §2.2
- `ARCHITECTURE.md` §11 (security, RBAC, and the legal-aware record)
- `research/04-final/audit.md` — "biggest build risk" and its first action
