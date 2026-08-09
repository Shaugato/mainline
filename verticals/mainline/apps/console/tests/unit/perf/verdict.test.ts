// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ONE ASSERTION THIS PACKAGE EXISTS FOR.
 *
 * The naive budget check is `value <= limit`, and it has a hole the shape of a missing
 * measurement: when the value is absent the comparison is skipped, the budget is not
 * reported as failing, and a summary that counts failures reports zero. **A console with
 * no instrumentation at all passes every budget it has.**
 *
 * That is the same defect as a gate counter reading zero because nothing computed it, and
 * it is the defect this product exists to refuse. So:
 *
 *   · a measurement that did not happen is `'not-measured'`, never `'pass'`;
 *   · a REQUIRED budget in that state fails the summary;
 *   · a required budget nobody handed a measurement in for fails the summary;
 *   · an empty verdict list fails, because a gate that did not run has not passed.
 *
 * Each of those is a separate `it` below, and each one would be green under the naive
 * implementation, which is why they are written as four rather than as one.
 */

import { describe, expect, it } from 'vitest';

import { BUDGETS, budgetById } from '../../../src/perf/budgets';
import { evaluate, formatSummary, summarise, type Measurement } from '../../../src/perf/verdict';

const REQUIRED = BUDGETS.filter((budget) => budget.required);

/** A measurement comfortably inside every budget, so a summary can be made to pass. */
function within(budgetId: string): Measurement {
  const budget = budgetById(budgetId);
  if (budget === null) throw new Error(budgetId);
  const base: Measurement = { budgetId, value: Math.floor(budget.limit / 2) };
  return budget.minimumSamples === undefined ? base : { ...base, samples: budget.minimumSamples };
}

const ALL_WITHIN: readonly Measurement[] = BUDGETS.map((budget) => within(budget.id));

describe('grading one budget', () => {
  it('passes at the limit and fails one unit over it', () => {
    expect(evaluate({ budgetId: 'gate-interactive', value: 1000 }).status).toBe('pass');
    expect(evaluate({ budgetId: 'gate-interactive', value: 1001 }).status).toBe('fail');
  });

  it('reports headroom, and reports it negative when over', () => {
    expect(evaluate({ budgetId: 'first-refusal-paint', value: 300 }).headroom).toBe(100);
    expect(evaluate({ budgetId: 'first-refusal-paint', value: 500 }).headroom).toBe(-100);
  });

  it('states the conditions in the message, so nobody quotes the number bare', () => {
    const verdict = evaluate({ budgetId: 'gate-interactive', value: 400 });
    expect(verdict.message).toContain('4× CPU throttle');
  });

  it('refuses a measurement naming a budget nobody declared', () => {
    expect(() => evaluate({ budgetId: 'invented', value: 1 })).toThrow(/no budget "invented"/);
  });
});

describe('a measurement that did not happen', () => {
  it('is NOT-MEASURED, and not a pass', () => {
    const verdict = evaluate({
      budgetId: 'gate-interactive',
      value: null,
      unmeasuredBecause: 'no browser tier ran.',
    });
    expect(verdict.status).toBe('not-measured');
    expect(verdict.status).not.toBe('pass');
    expect(verdict.message).toContain('NOT MEASURED');
    expect(verdict.message).toContain('no browser tier ran.');
  });

  it('is NOT-MEASURED even when the measurer gave no reason — and says so', () => {
    const verdict = evaluate({ budgetId: 'gate-interactive', value: null });
    expect(verdict.status).toBe('not-measured');
    expect(verdict.message).toContain('unexplained absence');
  });

  it('is NOT-MEASURED when a percentile came from too few samples', () => {
    const budget = budgetById('interaction-p95');
    const minimum = budget?.minimumSamples ?? 0;
    expect(minimum).toBeGreaterThan(1);

    const verdict = evaluate({ budgetId: 'interaction-p95', value: 40, samples: minimum - 1 });
    expect(
      verdict.status,
      'a p95 over four clicks is the maximum of four clicks. Grading it as a pass is how a demo ' +
        'ships a latency claim built on three interactions.',
    ).toBe('not-measured');

    expect(evaluate({ budgetId: 'interaction-p95', value: 40, samples: minimum }).status).toBe('pass');
  });

  it('is NOT-MEASURED when the reported value is not a number a clock could produce', () => {
    expect(evaluate({ budgetId: 'gate-interactive', value: Number.NaN }).status).toBe('not-measured');
    expect(evaluate({ budgetId: 'gate-interactive', value: -1 }).status).toBe('not-measured');
  });
});

describe('absence', () => {
  it('is legal for a budget somebody wrote `required: false` against', () => {
    const verdict = evaluate({ budgetId: 'memory-register-walk', value: null, absent: true });
    expect(verdict.status).toBe('absent');
    expect(verdict.message).toContain('texture, not a fact');
  });

  it('is a FAILURE for a required budget', () => {
    const verdict = evaluate({ budgetId: 'evidentiary-shell', value: null, absent: true });
    expect(verdict.status).toBe('fail');
    expect(verdict.message).toContain('failure rather than a saving');
  });
});

describe('the summary', () => {
  it('passes only when every budget was measured and is within limit', () => {
    const summary = summarise(ALL_WITHIN);
    expect(summary.status, formatSummary(summary)).toBe('pass');
    expect(summary.failed).toEqual([]);
    expect(summary.notMeasured).toEqual([]);
    expect(summary.missing).toEqual([]);
  });

  it('FAILS when a required budget was not measured — the whole point', () => {
    const measurements = ALL_WITHIN.map((measurement) =>
      measurement.budgetId === 'interaction-p95'
        ? { budgetId: 'interaction-p95', value: null, unmeasuredBecause: 'no observer.' }
        : measurement,
    );
    const summary = summarise(measurements);
    expect(
      summary.status,
      'a required budget nobody could measure graded as a pass. That is the naive `value <= limit` ' +
        'implementation, and under it a console with no instrumentation at all passes every ' +
        'budget it has.',
    ).toBe('fail');
    expect(summary.message).toContain('NOT MEASURED');
  });

  it('FAILS when a required budget was never reported at all', () => {
    const summary = summarise(ALL_WITHIN.filter((m) => m.budgetId !== 'gate-interactive'));
    expect(summary.status).toBe('fail');
    expect(summary.missing).toEqual(['gate-interactive']);
    expect(summary.message).toContain('never reported');
  });

  it('FAILS on an empty run, because a gate that did not run has not passed', () => {
    const summary = summarise([]);
    expect(summary.status).toBe('fail');
    expect(summary.message).toContain('no budget was graded at all');
  });

  it('does NOT fail when only an optional budget is absent', () => {
    const measurements = ALL_WITHIN.map((measurement) =>
      measurement.budgetId === 'memory-register-walk'
        ? { budgetId: 'memory-register-walk', value: null, absent: true }
        : measurement,
    );
    // BUILD_PLAN §10.2 cut 1 deletes render3d/. That absence is a decision with an
    // author (`required: false` in budgets.ts), not a silence.
    expect(summarise(measurements).status).toBe('pass');
  });

  it('renders every verdict, and marks the unmeasured ones distinctly from the passes', () => {
    const summary = summarise([
      within('evidentiary-shell'),
      { budgetId: 'gate-interactive', value: null, unmeasuredBecause: 'no browser tier ran.' },
    ]);
    const text = formatSummary(summary);
    expect(text).toContain('ok  ');
    expect(text).toContain('????');
    expect(text).toContain('first-refusal-paint');
  });
});

describe('the required set is not empty', () => {
  it('has required budgets at all, so every assertion above is not vacuous', () => {
    expect(REQUIRED.length).toBeGreaterThan(2);
  });
});
