// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The percentile, and the sample floor beneath it.
 *
 * "p95 < 100 ms" is not a number until somebody says which definition produced it. This
 * package uses NEAREST RANK — the element at 1-based index `ceil(p × n)` of the ascending
 * sample — and the first block pins that definition against a hand-computed table, so a
 * change to linear interpolation cannot happen silently.
 *
 * The second block is the honest one: below the floor, `percentile()` returns `null`
 * rather than the maximum. With four samples, `ceil(0.95 × 4) = 4` — the "95th
 * percentile" IS the maximum, and quoting it as a p95 is a category error, not a small
 * one.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_MINIMUM_SAMPLES,
  createInteractionSampler,
  observeInteractions,
  percentile,
} from '../../../src/perf/interaction';

/** 1..20, so `ceil(p × 20)` is readable by eye. */
const TWENTY = Array.from({ length: 20 }, (_, index) => index + 1);

describe('nearest rank, stated and pinned', () => {
  it.each([
    [0.95, 19],
    [0.5, 10],
    [0.9, 18],
    [1, 20],
    [0.05, 1],
  ])('p%f of 1..20 is %i', (p, expected) => {
    expect(percentile(TWENTY, p).value).toBe(expected);
  });

  it('never invents a value the system did not exhibit', () => {
    // Linear interpolation would answer 19.05 here. Every percentile this returns is a
    // latency that actually happened, which is the property a claim about a safety
    // console should have.
    const result = percentile(TWENTY, 0.95);
    expect(TWENTY).toContain(result.value);
    expect(result.method).toBe('nearest-rank');
  });

  it('sorts before ranking, and ignores a negative or non-finite sample', () => {
    const scrambled = [...TWENTY].reverse();
    expect(percentile(scrambled, 0.95).value).toBe(19);
    expect(percentile([...TWENTY, -5, Number.NaN], 0.95).samples).toBe(20);
  });

  it('refuses a fraction that is not one', () => {
    expect(() => percentile(TWENTY, 0)).toThrow(/not a percentile/);
    expect(() => percentile(TWENTY, 1.5)).toThrow(/not a percentile/);
  });
});

describe('the sample floor', () => {
  it('returns null below the floor, and says why', () => {
    const result = percentile([10, 20, 30, 400], 0.95);
    expect(
      result.value,
      'with four samples the "p95" is the maximum. Returning it would let a demo ship a latency ' +
        'claim built on three clicks.',
    ).toBeNull();
    expect(result.unmeasuredBecause).toContain('below the floor');
    expect(result.samples).toBe(4);
  });

  it('returns a value at exactly the floor', () => {
    expect(percentile(TWENTY, 0.95, 20).value).toBe(19);
    expect(percentile(TWENTY.slice(0, 19), 0.95, 20).value).toBeNull();
  });

  it('defaults the floor to 20, which is what D13’s p95 is honest at', () => {
    expect(DEFAULT_MINIMUM_SAMPLES).toBe(20);
  });
});

describe('the sampler', () => {
  it('collects, reports its count, and finds the worst interaction', () => {
    const sampler = createInteractionSampler();
    sampler.record({ kind: 'pointerdown', durationMs: 12 });
    sampler.record({ kind: 'keydown', durationMs: 140 });
    sampler.record({ kind: 'click', durationMs: 30 });
    expect(sampler.count()).toBe(3);
    expect(sampler.worst()).toEqual({ kind: 'keydown', durationMs: 140 });
    expect(sampler.p(0.95).value).toBeNull();
  });

  it('drops the OLDEST sample at capacity, so the window is the console as it is now', () => {
    const sampler = createInteractionSampler({ capacity: 3, minimumSamples: 1 });
    for (const durationMs of [1, 2, 3, 4]) sampler.record({ kind: 'click', durationMs });
    expect(sampler.durations()).toEqual([2, 3, 4]);
  });

  it('ignores a nonsense duration rather than folding it into the percentile', () => {
    const sampler = createInteractionSampler({ minimumSamples: 1 });
    sampler.record({ kind: 'click', durationMs: -1 });
    sampler.record({ kind: 'click', durationMs: Number.POSITIVE_INFINITY });
    expect(sampler.count()).toBe(0);
  });

  it('resets', () => {
    const sampler = createInteractionSampler({ minimumSamples: 1 });
    sampler.record({ kind: 'click', durationMs: 5 });
    sampler.reset();
    expect(sampler.count()).toBe(0);
    expect(sampler.worst()).toBeNull();
  });
});

describe('the platform hook', () => {
  it('reports that it is NOT observing when the platform has no Event Timing', () => {
    // jsdom has no PerformanceObserver. The handle must say so rather than quietly
    // observing nothing — a sampler that stays empty and a sampler that was never
    // attached produce the same p95 and mean opposite things.
    const sampler = createInteractionSampler();
    const handle = observeInteractions(sampler);
    expect(handle.observing).toBe(false);
    expect(handle.unavailableBecause).toContain('NOT being assumed to be within budget');
    handle.stop();
  });

  it('does not fall back to a hand-rolled timer', () => {
    // A number produced by a different method than the budget was written for is worse
    // than no number, because it grades as a pass.
    const sampler = createInteractionSampler();
    observeInteractions(sampler);
    expect(sampler.count()).toBe(0);
  });

  it('reports the refusal when observe() itself is rejected', () => {
    class Rejecting {
      static readonly supportedEntryTypes: readonly string[] = ['event'];
      observe(): never {
        throw new Error('entry type not supported by this build');
      }
      disconnect(): void {
        /* nothing to disconnect */
      }
      takeRecords(): readonly [] {
        return [];
      }
    }
    vi.stubGlobal('PerformanceObserver', Rejecting);

    const handle = observeInteractions(createInteractionSampler());
    expect(handle.observing).toBe(false);
    expect(handle.unavailableBecause).toContain('entry type not supported by this build');
  });
});
