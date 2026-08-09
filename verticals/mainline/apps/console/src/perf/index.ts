// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The performance package (`docs/leads/ui.md` D13).
 *
 * Register-NEUTRAL and dependency-free, like `src/a11y/`. It imports no React and no
 * animation library, so an EVIDENCE surface can measure itself without reaching a
 * package its register may not see.
 *
 *   `budgets.ts`      the five numbers, with the conditions each is only true under
 *   `marks.ts`        the fixed instant vocabulary, the spans, and an injected clock
 *   `interaction.ts`  nearest-rank percentiles with a stated sample floor
 *   `verdict.ts`      the grading, where a missing measurement is never a pass
 *
 * The one idea worth carrying out of here: `'not-measured'` is a status, it is not
 * `'pass'`, and a required budget in that state fails the summary.
 */

export {
  BUDGETS,
  BUDGET_KINDS,
  BUDGET_STATUSES,
  BYTE_BUDGET_IDS,
  RUNTIME_BUDGET_IDS,
  budgetById,
  formatLimit,
  type Budget,
  type BudgetKind,
  type BudgetStatus,
} from './budgets';

export {
  MARKS,
  SPANS,
  createRecorder,
  frozenClock,
  scriptedClock,
  spanById,
  systemClock,
  type Clock,
  type MarkName,
  type Recorder,
  type Span,
  type SpanReading,
} from './marks';

export {
  DEFAULT_MINIMUM_SAMPLES,
  createInteractionSampler,
  observeInteractions,
  percentile,
  type InteractionSample,
  type InteractionSampler,
  type ObservationHandle,
  type PercentileResult,
  type SamplerOptions,
} from './interaction';

export {
  VERDICT_STATUSES,
  evaluate,
  formatSummary,
  summarise,
  type Measurement,
  type Summary,
  type Verdict,
  type VerdictStatus,
} from './verdict';
