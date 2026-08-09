<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# Performance budgets — the numbers, and which of them anything actually measures

**`docs/leads/ui.md` D13.**

> *"Sub-second on a mine-site laptop" is a number or it is marketing.*

Generated from `src/perf/budgets.ts` and `src/perf/marks.ts`;
`tests/unit/perf/doc-generated.test.ts` asserts the tables are byte-identical to what those
files render.

---

## 0. The idea that makes this more than a table

The naive budget check is `value <= limit`. It has a hole exactly the shape of a missing
measurement: when the value is absent the comparison is skipped, the budget is not counted
as failing, and a summary that counts failures reports zero.

**A console with no instrumentation at all passes every budget it has.**

That is the same defect as a gate counter reading zero because nothing computed it — the
defect this product exists to refuse — so `src/perf/verdict.ts` refuses it here too:

| Situation | Status | Effect on the summary |
|---|---|---|
| measured, within limit | `pass` | — |
| measured, over limit | `fail` | fails |
| **not measured** | `not-measured` | **fails, if the budget is required** |
| never reported at all | counted in `missing` | **fails, if the budget is required** |
| no budgets graded at all | — | **fails** — a gate that did not run has not passed |
| legitimately absent from the build (`required: false`) | `absent` | — |

`'absent'` is the one case where nothing happens, and it is legal because somebody wrote
`required: false` in `budgets.ts` against it. That is a decision with an author, not a
silence. Today the only such budget is the lazy 3D chunk, which is `BUILD_PLAN` §10.2's
first scope cut: `rm -r src/features/ancestry/render3d/` costs texture, not a fact.

---

## 1. The budgets

<!-- GENERATED:budgets — rendered from src/perf/budgets.ts + src/perf/marks.ts. Do not edit by hand. -->

| Budget | What it bounds | Limit | Only true under | Required | Status |
|---|---|---|---|---|---|
| `evidentiary-shell` | Evidentiary shell — entry chunk plus its static import closure and CSS | 220 KB | gzip of the transferred JavaScript and CSS closure, not raw bytes | required | measured by `scripts/check-budgets.ts` |
| `memory-register-walk` | Lazy 3D chunk — the MEMORY-register ancestry walk | 600 KB | gzip of the lazy chunk closure, minus anything already in the entry | optional | measured by `scripts/check-budgets.ts` |
| `gate-interactive` | Gate surface interactive | 1000 ms | 4× CPU throttle, cold cache, replay transport, 1920×1080 | required | **NOT YET MEASURABLE** — `tests/browser/budgets.spec.ts` has not landed |
| `first-refusal-paint` | First refusal paint, from a verified bundle | 400 ms | from bundle verification resolving to the refusal bar being in the DOM | required | **NOT YET MEASURABLE** — `tests/browser/budgets.spec.ts` has not landed |
| `interaction-p95` | Interaction latency, 95th percentile | 100 ms | 4× CPU throttle; event-timing durations over a session of at least 20 interactions | required | **NOT YET MEASURABLE** — `tests/browser/budgets.spec.ts (samples from src/perf/interaction.ts)` has not landed |

<!-- /GENERATED:budgets -->

`budgets.json` is authoritative for the two byte budgets — it is what
`scripts/check-budgets.ts` reads after a build — and `src/perf/budgets.ts` mirrors them so
the console can state its whole performance contract in one place.
`tests/unit/perf/budgets.test.ts` asserts the two files agree. If they ever disagree, that
test fails rather than one of them quietly winning: a performance contract with two answers
is a performance contract with none.

### Status, honestly

Two of the five are enforced today, by `scripts/check-budgets.ts` over the real Vite
manifest. **The three runtime budgets are NOT YET MEASURABLE.** They need a browser with 4×
CPU throttling, and `playwright.config.ts` plus `tests/browser/budgets.spec.ts` belong to
the `cinema-conformance-harness` worker, which had not landed when this package was
written.

Marking them `measurable` before that would be a claim about a gate that does not exist.
Because they are marked `not-yet-measurable` and are `required`, any summary produced today
comes back **`fail`** — which is the correct answer and the one that gets them wired up.

---

## 2. The spans

A budget is only as good as the two instants it is measured between, and the classic way a
latency number becomes fiction is that the ends drift: somebody moves the "interactive"
mark earlier, and nobody can tell, because the mark was a string literal in one file.

So the instants are a frozen tuple (`MARKS`), a typo is a type error, and every span
declares the budget it feeds. `tests/unit/perf/marks.test.ts` asserts the bijection: a
duration budget with no span is a number nothing can produce, and a span claiming a budget
that does not exist is a measurement nobody grades.

<!-- GENERATED:spans — rendered from src/perf/budgets.ts + src/perf/marks.ts. Do not edit by hand. -->

| Span | Between | Budget | Why measured there |
|---|---|---|---|
| `first-refusal-paint` | `bundle:verify-resolved` → `refusal:painted` | `first-refusal-paint` | Starts at verification resolving rather than at fetch: the console REFUSES to render an unverified frame, so the time before that instant is honesty, not latency, and folding it in would create pressure to shorten the wrong thing. |
| `gate-interactive` | `shell:script-start` → `gate:interactive` | `gate-interactive` | The whole cold path a supervisor actually waits through, ending when the surface responds. |
| `shell-mount` | `shell:script-start` → `shell:react-mounted` | diagnostic only | Diagnostic: separates framework boot from surface work when gate-interactive regresses. |
| `bundle-verification` | `bundle:verify-start` → `bundle:verify-resolved` | diagnostic only | Diagnostic, and deliberately un-budgeted: the in-browser verifier is the product’s central claim (D6) and must never be under time pressure from a number in this file. |

<!-- /GENERATED:spans -->

The `interaction-p95` budget has no span, and that is not an omission: it is fed from Event
Timing entries, which are intervals the *platform* reports — the time from an input event
to the next paint — rather than instants this console marks. Measuring it with a
hand-rolled timer around a click handler would measure the handler, not the interaction,
and would report a console that is fast at exactly the moment it is dropping frames.

---

## 3. The percentile, stated

`p95 < 100 ms` is not a number until somebody says which definition produced it. Linear
interpolation and nearest rank disagree by a whole sample at small *n*, and at the sample
sizes a demo produces that difference is most of the answer.

**`src/perf/interaction.ts` uses NEAREST RANK** (ISO 16269-4): for a sorted ascending
sample of size *n*, the *p*-th percentile is the element at 1-based index `ceil(p × n)`. It
never invents a value the system did not exhibit — every percentile it returns is a latency
that actually happened, which is the property a claim about a safety console should have.

**Below 20 samples it returns `null`, not the maximum.** With four samples,
`ceil(0.95 × 4) = 4`: the "95th percentile" *is* the maximum. Quoting that as a p95 is a
category error, and it is how a demo ships a latency claim built on three clicks. `null`
becomes `not-measured`, which for a required budget fails.

---

## 4. Cinema mode and the frozen clock

D12 freezes `Date.now` and `performance.now` so a capture is reproducible. A recorder that
read the clock directly would record every span as 0 ms and report a console that renders
instantaneously — making the one number in a reproducible capture that is *not* reproducible
also the most flattering one.

So `createRecorder(clock)` takes its clock as an argument. Cinema mode passes
`frozenClock()`, whose `monotonic` flag is `false`, and every span reads back as **not
measured** with the reason attached. The marks are still recorded, so a capture can still
assert the *ordering* of events — just not their duration.

`src/perf/` imports nothing from `src/cinema/`: it declares the `Clock` interface and the
cinema worker supplies one.

---

## 5. Using the package

```ts
import { createRecorder, systemClock } from '../../src/perf';

const recorder = createRecorder(systemClock());
recorder.mark('shell:script-start');
// …
recorder.mark('gate:interactive');
recorder.read('gate-interactive');   // { durationMs, unmeasuredBecause }
```

```ts
import { createInteractionSampler, observeInteractions } from '../../src/perf';

const sampler = createInteractionSampler();
const handle = observeInteractions(sampler);
handle.observing;           // false on a platform without Event Timing
handle.unavailableBecause;  // …and it says so, verbatim, rather than reporting zero
```

```ts
import { formatSummary, summarise } from '../../src/perf';

const summary = summarise([
  { budgetId: 'evidentiary-shell', value: 201_432 },
  { budgetId: 'gate-interactive', value: null, unmeasuredBecause: 'no browser tier ran.' },
]);
summary.status;   // 'fail' — the second one was not measured, and it is required
console.log(formatSummary(summary));
```

---

## 6. What is deliberately un-budgeted

**In-browser verification** (`bundle:verify-start` → `bundle:verify-resolved`) is recorded
as a diagnostic and has no budget.

D6 — re-deriving every displayed claim from signed bytes — is the console's central claim,
and a number in this file that made it look slow would create pressure to check less. The
time a reader waits for verification is honesty, not latency. For the same reason
`first-refusal-paint` starts at verification *resolving*, not at fetch: the console refuses
to render an unverified frame, and folding that wait into the paint budget would put
pressure on exactly the wrong thing.
