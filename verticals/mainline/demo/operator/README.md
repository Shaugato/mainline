<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `verticals/mainline/demo/operator/` — the paperwork for the two operator screens

**Worker:** W8 · **Date:** 2026-08-15 · **Scope:** `docs/demo/operator-systems-plan.md`

---

## What this directory is for

`CONTROL OF WORK` is the surface a judge actually watches: a permit-to-work screen a site
supervisor works in, and a management-of-change screen a safety engineer works in, served from
the same origin as the API so that every refusal on screen came back over HTTP in that page
load. The code for it lives in `verticals/mainline/apps/console/src/operator/**` and belongs to
workers W1–W7.

**This directory holds no code.** It holds the four documents that decide what those screens
are allowed to *say*, prove that nothing on them was invented, tell the orchestrator what
shipping them costs, and tell a camera operator how to film them.

The directory path is not chosen. `scripts/demo/claim_hygiene.py` line 60 already globs
`verticals/mainline/demo/operator/*.md`, and until these files existed it reported:

```
ABSENT  verticals/mainline/demo/operator/*.md matched no file — not scanned, and therefore not passed
```

That sentence is the reason this directory exists at this path. "Nothing was scanned" is not
"it passed", and every sentence we intend to put on screen or speak over the top of it now sits
under the same scanner that governs the README, `VERIFY.md` and `docs/HONESTY.md`.

---

## The four documents

| file | what it settles | who reads it |
|---|---|---|
| [`COPY.md`](COPY.md) | Every string that appears on either screen, each with its source: a column, a verbatim standard citation, an editorial line, a client-side computation, or an operator-typed placeholder. Carries the language rulings and the banned phrases. | whoever writes the script, whoever records the voice-over, W3–W6 |
| [`FIELD-LEDGER.md`](FIELD-LEDGER.md) | Every field on both screens reconciled against HSG250 Figure 1 and OSHA 1910.119(l)(2), classified REAL / TYPED / LABELLED-ABSENT / OMITTED. Nothing is unclassified. | anybody asking "where did that number come from" |
| [`PACKAGING.md`](PACKAGING.md) | Measured build impact: the two index-chunk digests, the operator closure gzip, the `dist/` census, the deploy-lane result, and the `--console-transport` decision handed to the orchestrator. | the orchestrator, before the next package |
| [`RUNBOOK.md`](RUNBOOK.md) | How to bring the screens up over the local CockroachDB node and film them, including the exact URL and the rule that separates a local capture from the deployed one. | whoever rehearses, whoever films |

---

## The three rules that bind all four

1. **Nothing on these screens is faked.** No refusal, no latency, no SQLSTATE, no row and no
   seal is composed by the client, and no document here contains a sentence asserting one. A
   refusal string that did not come back over HTTP in that page load is the one defect that
   would make the whole surface worthless.
2. **A local capture is never presented as the deployed run.** Every response the emulator
   serves carries `X-Mainline-Emulator: local_furl`, the page renders it, and `RUNBOOK.md` §5
   makes that the identifying mark.
3. **These documents record measurements, not estimates.** Where a number appears in
   `PACKAGING.md` it was measured in this session and the command that produced it is written
   beside it. Where something could not be measured, it says so instead of guessing.

---

## Where the authority comes from

* `docs/demo/operator-systems-plan.md` — the rulings R1–R18. Binding.
* `docs/demo/research/r3-operator.md` — the field-by-field honesty ledger these screens
  implement. §5.3 is the source of the typed-field rule.
* `docs/demo/research/r6-honesty.md` — A5, A5.1 and A17.2, the memory-loop language and the
  synthetic-watermark rules.
* `docs/HONESTY.md` and `docs/CI-STATE.md` — unchanged by this wave, and not available to be
  weakened by it.
