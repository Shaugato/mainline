// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE VERDICT — where "not measured" refuses to become "pass".
 *
 * This is a twelve-line piece of arithmetic carrying the one idea that makes it worth
 * having its own file.
 *
 * The naive implementation of a budget check is `value <= limit`. It has a hole the
 * shape of a missing measurement: when `value` is absent, the comparison is skipped, the
 * budget is not reported as failing, and a summary that counts failures reports zero. A
 * console with no instrumentation at all passes every budget it has.
 *
 * That is the same defect as a gate counter that reads zero because nothing computed it,
 * and this product exists to refuse exactly that. So:
 *
 *   • a measurement that did not happen produces `'not-measured'`, never `'pass'`;
 *   • a REQUIRED budget that is `'not-measured'` makes the whole summary FAIL;
 *   • an empty verdict list FAILS, because a gate that did not run has not passed; and
 *   • every `'not-measured'` carries the sentence saying why, and the summary prints it.
 *
 * A budget marked `required: false` (the lazy 3D chunk, which the cut ladder is allowed
 * to delete) is the one case where absence is legal — and it is legal because somebody
 * wrote `required: false` in `budgets.ts`, which is a decision with an author, not a
 * silence.
 */

import { type Budget, BUDGETS, budgetById, formatLimit } from './budgets';

export const VERDICT_STATUSES = ['pass', 'fail', 'not-measured', 'absent'] as const;

export type VerdictStatus = (typeof VERDICT_STATUSES)[number];

/** What a measurer hands in. `value === null` means it could not measure, not zero. */
export interface Measurement {
  readonly budgetId: string;
  readonly value: number | null;
  /** Why `value` is null. REQUIRED when it is null — an unexplained absence is refused. */
  readonly unmeasuredBecause?: string;
  /** For percentile budgets: how many samples the value came from. */
  readonly samples?: number;
  /** `true` when the thing being measured legitimately does not exist in this build. */
  readonly absent?: boolean;
}

export interface Verdict {
  readonly budgetId: string;
  readonly status: VerdictStatus;
  readonly value: number | null;
  readonly limit: number;
  /** `limit - value`, or `null` when unmeasured. Negative means over budget. */
  readonly headroom: number | null;
  /** One sentence, safe to render verbatim on the honesty chrome. */
  readonly message: string;
  /** Whether this verdict is allowed to sink the summary. */
  readonly required: boolean;
}

function unmeasured(budget: Budget, reason: string): Verdict {
  return {
    budgetId: budget.id,
    status: 'not-measured',
    value: null,
    limit: budget.limit,
    headroom: null,
    required: budget.required,
    message: `${budget.title}: NOT MEASURED — ${reason}`,
  };
}

/**
 * Grades one measurement against one budget.
 *
 * Throws only for a measurement naming a budget that does not exist. Everything else is
 * a verdict, because a measurer that crashes the report is a measurer that gets removed
 * from the report.
 */
export function evaluate(measurement: Measurement): Verdict {
  const budget = budgetById(measurement.budgetId);
  if (budget === null) {
    throw new Error(
      `perf/verdict: no budget "${measurement.budgetId}" is declared in src/perf/budgets.ts. A ` +
        'measurement nobody can grade is a number in a log file.',
    );
  }

  if (measurement.absent === true) {
    if (budget.required) {
      return {
        budgetId: budget.id,
        status: 'fail',
        value: null,
        limit: budget.limit,
        headroom: null,
        required: true,
        message:
          `${budget.title}: ABSENT, and this budget is required. The thing being measured is not ` +
          'in this build, which is a failure rather than a saving.',
      };
    }
    return {
      budgetId: budget.id,
      status: 'absent',
      value: null,
      limit: budget.limit,
      headroom: null,
      required: false,
      message:
        `${budget.title}: absent from this build, which budgets.ts permits (required: false). ` +
        'The console loses texture, not a fact.',
    };
  }

  if (measurement.value === null) {
    const reason =
      measurement.unmeasuredBecause ??
      'the measurer gave no reason, which is itself the finding: an unexplained absence cannot be ' +
        'told apart from an absent measurer.';
    return unmeasured(budget, reason);
  }

  if (!Number.isFinite(measurement.value) || measurement.value < 0) {
    return unmeasured(budget, `the reported value ${measurement.value} is not a measurement.`);
  }

  const minimum = budget.minimumSamples;
  if (minimum !== undefined) {
    const samples = measurement.samples ?? 0;
    if (samples < minimum) {
      return unmeasured(
        budget,
        `${samples} sample(s) is below the floor of ${minimum} this percentile is honest at.`,
      );
    }
  }

  const headroom = budget.limit - measurement.value;
  const unit = budget.unit === 'ms' ? 'ms' : 'bytes';
  const pass = measurement.value <= budget.limit;

  return {
    budgetId: budget.id,
    status: pass ? 'pass' : 'fail',
    value: measurement.value,
    limit: budget.limit,
    headroom,
    required: budget.required,
    message: pass
      ? `${budget.title}: ${measurement.value} ${unit} against ${formatLimit(budget)} — ${headroom} ${unit} of headroom (${budget.conditions}).`
      : `${budget.title}: ${measurement.value} ${unit} EXCEEDS ${formatLimit(budget)} by ${-headroom} ${unit} (${budget.conditions}).`,
  };
}

export interface Summary {
  readonly status: 'pass' | 'fail';
  readonly verdicts: readonly Verdict[];
  readonly failed: readonly Verdict[];
  readonly notMeasured: readonly Verdict[];
  /** Required budgets no measurement was handed in for at all. */
  readonly missing: readonly string[];
  readonly message: string;
}

/**
 * The whole gate.
 *
 * Every budget in `BUDGETS` must be accounted for: a measurement that was never handed
 * in is `missing`, and a missing REQUIRED budget fails. That is deliberately harsher
 * than iterating the measurements — iterating what you were given can only ever grade
 * what somebody remembered to measure.
 */
export function summarise(measurements: readonly Measurement[]): Summary {
  const verdicts = measurements.map(evaluate);
  const graded = new Set(verdicts.map((verdict) => verdict.budgetId));

  const missing = BUDGETS.filter(
    (budget) => budget.required && !graded.has(budget.id),
  ).map((budget) => budget.id);

  const failed = verdicts.filter((verdict) => verdict.status === 'fail');
  const notMeasured = verdicts.filter((verdict) => verdict.status === 'not-measured');
  const blockingUnmeasured = notMeasured.filter((verdict) => verdict.required);

  const status: 'pass' | 'fail' =
    verdicts.length === 0 ||
    failed.length > 0 ||
    blockingUnmeasured.length > 0 ||
    missing.length > 0
      ? 'fail'
      : 'pass';

  const parts: string[] = [];
  if (verdicts.length === 0) parts.push('no budget was graded at all — a gate that did not run has not passed');
  if (failed.length > 0) parts.push(`${failed.length} over budget`);
  if (blockingUnmeasured.length > 0) {
    parts.push(`${blockingUnmeasured.length} required budget(s) NOT MEASURED`);
  }
  if (missing.length > 0) parts.push(`${missing.length} required budget(s) never reported: ${missing.join(', ')}`);

  return {
    status,
    verdicts,
    failed,
    notMeasured,
    missing,
    message:
      status === 'pass'
        ? `All ${verdicts.length} performance budgets were measured and are within limit.`
        : `Performance budgets FAILED — ${parts.join('; ')}.`,
  };
}

/** The summary rendered for a terminal or for the honesty chrome. */
export function formatSummary(summary: Summary): string {
  const lines = [summary.message, ''];
  for (const verdict of summary.verdicts) {
    const flag =
      verdict.status === 'pass'
        ? 'ok  '
        : verdict.status === 'absent'
          ? 'none'
          : verdict.status === 'not-measured'
            ? '????'
            : 'FAIL';
    lines.push(`  ${flag}  ${verdict.message}`);
  }
  for (const budgetId of summary.missing) {
    lines.push(`  ????  ${budgetId}: required, and no measurement was handed in.`);
  }
  return lines.join('\n');
}
