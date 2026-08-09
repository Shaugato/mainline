// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The marks, the spans, and the clock that cinema mode freezes.
 *
 * The assertion worth the file is the frozen-clock one. D12 freezes `performance.now` so
 * that a capture is reproducible; a recorder that read the clock directly would record
 * every span as 0 ms and report a console that renders instantaneously — the one number
 * in the capture that is not reproducible would be the one about speed, and it would be
 * flattering. Here a frozen clock yields NOT MEASURED, with the reason attached.
 */

import { describe, expect, it } from 'vitest';

import { BUDGETS } from '../../../src/perf/budgets';
import {
  MARKS,
  SPANS,
  createRecorder,
  frozenClock,
  scriptedClock,
  spanById,
  systemClock,
} from '../../../src/perf/marks';

describe('the vocabulary', () => {
  it('has unique marks and unique spans', () => {
    expect(new Set(MARKS).size).toBe(MARKS.length);
    const ids = SPANS.map((span) => span.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('builds every span out of declared marks', () => {
    for (const span of SPANS) {
      expect(MARKS, `${span.id}.from`).toContain(span.from);
      expect(MARKS, `${span.id}.to`).toContain(span.to);
      expect(span.why.length, `${span.id} does not say why it is measured there`).toBeGreaterThan(40);
    }
  });

  it('is in bijection with the duration budgets', () => {
    const budgeted = SPANS.filter((span) => span.budget !== null).map((span) => span.budget);
    // Only `duration-ms` budgets are measured between two marks. The percentile budget is
    // fed by src/perf/interaction.ts from Event Timing entries, which are intervals the
    // platform reports rather than instants this console marks — asserting a span for it
    // would require inventing marks nothing could ever set.
    const durations = BUDGETS.filter((budget) => budget.kind === 'duration-ms').map((b) => b.id);
    expect(durations.length).toBeGreaterThan(1);

    for (const budget of durations) {
      // A budget with no span is a number nothing in the console can produce.
      expect(budgeted, `no span feeds the "${budget}" budget`).toContain(budget);
    }
    for (const budget of budgeted) {
      // A span claiming a budget that does not exist is a measurement nobody grades.
      expect(BUDGETS.map((b) => b.id)).toContain(budget);
    }
    expect(new Set(budgeted).size).toBe(budgeted.length);
  });

  it('leaves the percentile budget to the sampler, and says so where it is declared', () => {
    const p95 = BUDGETS.find((budget) => budget.kind === 'percentile-ms');
    expect(p95?.measuredBy).toContain('src/perf/interaction.ts');
    expect(SPANS.some((span) => span.budget === p95?.id)).toBe(false);
  });

  it('resolves a span by id and refuses one it does not have', () => {
    expect(spanById('gate-interactive')?.to).toBe('gate:interactive');
    expect(spanById('a-span-nobody-declared')).toBeNull();
  });
});

describe('the recorder', () => {
  it('measures a span between two marks', () => {
    const recorder = createRecorder(scriptedClock([100, 480]));
    recorder.mark('bundle:verify-resolved');
    recorder.mark('refusal:painted');
    const reading = recorder.read('first-refusal-paint');
    expect(reading.durationMs).toBe(380);
    expect(reading.unmeasuredBecause).toBeNull();
  });

  it('keeps the FIRST mark, not the last', () => {
    // React 19 mounts effects twice in development. A last-write-wins recorder would
    // report the second, warm mount as the cold one — a console that gets faster the
    // more times you measure it.
    const recorder = createRecorder(scriptedClock([100, 500]));
    recorder.mark('shell:script-start');
    recorder.mark('shell:script-start'); // must not read the clock at all
    recorder.mark('shell:react-mounted');

    expect(
      recorder.at('shell:script-start'),
      'the second mark overwrote the first. Under last-write-wins the start instant would be 500 ' +
        'here, and the cold boot would be reported as the warm remount.',
    ).toBe(100);
    expect(recorder.at('shell:react-mounted')).toBe(500);
    expect(recorder.read('shell-mount').durationMs).toBe(400);
  });

  it('reports an unmarked end as NOT MEASURED, naming the mark', () => {
    const recorder = createRecorder(scriptedClock([100]));
    recorder.mark('shell:script-start');
    const reading = recorder.read('gate-interactive');
    expect(reading.durationMs).toBeNull();
    expect(reading.unmeasuredBecause).toContain('gate:interactive');
  });

  it('refuses a span whose end precedes its start', () => {
    const recorder = createRecorder(scriptedClock([500, 100]));
    recorder.mark('bundle:verify-resolved');
    recorder.mark('refusal:painted');
    expect(recorder.read('first-refusal-paint').durationMs).toBeNull();
    expect(recorder.read('first-refusal-paint').unmeasuredBecause).toContain('not a duration');
  });

  it('refuses a span id nobody declared', () => {
    const recorder = createRecorder(scriptedClock([1, 2]));
    expect(recorder.read('invented').unmeasuredBecause).toContain('not a declared span');
  });

  it('reads every declared span at once, and resets', () => {
    const recorder = createRecorder(scriptedClock([0, 10, 20, 30]));
    for (const mark of MARKS) recorder.mark(mark);
    expect(recorder.readAll()).toHaveLength(SPANS.length);
    recorder.reset();
    expect(recorder.at('shell:script-start')).toBeNull();
  });
});

describe('the frozen clock (cinema mode)', () => {
  it('produces NOT MEASURED, not 0 ms', () => {
    const recorder = createRecorder(frozenClock(1_000));
    recorder.mark('bundle:verify-resolved');
    recorder.mark('refusal:painted');
    const reading = recorder.read('first-refusal-paint');
    expect(
      reading.durationMs,
      'a frozen clock makes every span 0 ms. Reporting that as a measurement would make the one ' +
        'number in a reproducible capture that is NOT reproducible also the most flattering.',
    ).toBeNull();
    expect(reading.unmeasuredBecause).toContain('frozen');
    expect(frozenClock(1_000).monotonic).toBe(false);
  });

  it('still records the instants, so a capture can assert the ordering', () => {
    const recorder = createRecorder(frozenClock(1_000));
    recorder.mark('refusal:painted');
    expect(recorder.at('refusal:painted')).toBe(1_000);
  });
});

describe('the system clock', () => {
  it('is monotonic and returns a finite number', () => {
    const clock = systemClock();
    expect(clock.monotonic).toBe(true);
    expect(Number.isFinite(clock.now())).toBe(true);
  });
});
