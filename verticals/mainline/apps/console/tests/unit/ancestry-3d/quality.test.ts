// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE QUALITY LADDER — `docs/dimensionality-charter.md` §6.
 *
 *   > Never let a mine-site laptop stutter through a fatality.
 *
 * The interesting assertions here are the ones about what the ladder REFUSES to do:
 * grade on too few frames, grade on a mean, climb back up, or run at all during a
 * capture.
 */

import { describe, expect, it } from 'vitest';

import {
  DETAIL_TIERS,
  FULL_TIER_P95_MS,
  QUALITY_SAMPLE_FRAMES,
  REDUCED_TIER_P95_MS,
  createFrameSampler,
  detailBudgetFor,
  gradeWindow,
  p95,
} from '../../../src/features/ancestry/render3d/quality';

const window = (value: number, count = QUALITY_SAMPLE_FRAMES): number[] =>
  Array.from({ length: count }, () => value);

describe('p95, not the mean', () => {
  it('reports the frame the reader remembers, not the average frame', () => {
    // Twenty-eight healthy frames and two freezes. The mean is 15.7 ms and looks
    // perfectly healthy; the reader saw the screen stop twice.
    const samples = [...window(4, 28), 180, 180];
    const mean = samples.reduce((sum, value) => sum + value, 0) / samples.length;
    expect(mean).toBeLessThan(FULL_TIER_P95_MS);
    expect(p95(samples)).toBeGreaterThan(REDUCED_TIER_P95_MS);
    expect(gradeWindow(samples, 'full').tier).toBe('handback');
  });

  it('does not fire on ONE slow frame in thirty, and that is deliberate', () => {
    // Nearest-rank p95 over a 30-frame window reports the second-worst frame. A single
    // dropped frame — a garbage collection, a tab regaining focus — is not a stutter,
    // and a ladder that degraded the scene for one is a ladder nobody would leave on.
    const samples = [...window(4, 29), 400];
    expect(p95(samples)).toBe(4);
    expect(gradeWindow(samples, 'full').tier).toBe('full');
  });

  it('invents no frame time — nearest rank, never interpolation', () => {
    const samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    expect(samples).toContain(p95(samples));
  });

  it('ignores nonsense samples rather than propagating a NaN', () => {
    expect(p95([Number.NaN, -1, 12, 14])).toBe(14);
    expect(p95([])).toBeNull();
  });
});

describe('a measurement that has not been taken is not evidence', () => {
  it('grades a short window as insufficient and leaves the tier alone', () => {
    const grade = gradeWindow(window(500, QUALITY_SAMPLE_FRAMES - 1), 'full');
    expect(grade.reason).toBe('insufficient-sample');
    expect(grade.tier).toBe('full');
    expect(grade.p95Ms).toBeNull();
  });

  it('holds a already-descended tier through a short window rather than resetting it', () => {
    const grade = gradeWindow(window(4, 3), 'reduced');
    expect(grade.tier).toBe('reduced');
  });
});

describe('the three rungs', () => {
  it('stays full inside the budget', () => {
    const grade = gradeWindow(window(9), 'full');
    expect(grade.tier).toBe('full');
    expect(grade.reason).toBe('within-budget');
    expect(grade.p95Ms).toBeCloseTo(9, 6);
  });

  it('drops to reduced on the first missed window', () => {
    const grade = gradeWindow(window(22), 'full');
    expect(grade.tier).toBe('reduced');
    expect(grade.reason).toBe('missed-full-budget');
  });

  it('hands back when a reduced window still misses', () => {
    const grade = gradeWindow(window(22), 'reduced');
    expect(grade.tier).toBe('handback');
    expect(grade.reason).toBe('reduced-window-still-missed');
  });

  it('hands back immediately when the frame time is past the hand-back threshold', () => {
    const grade = gradeWindow(window(45), 'full');
    expect(grade.tier).toBe('handback');
    expect(grade.reason).toBe('missed-reduced-budget');
    expect(grade.explanation).toContain('the ribbon carries every node');
  });

  it('is monotone — a session’s tier only ever descends', () => {
    for (const previous of DETAIL_TIERS) {
      const recovered = gradeWindow(window(4), previous);
      expect(DETAIL_TIERS.indexOf(recovered.tier)).toBeGreaterThanOrEqual(
        DETAIL_TIERS.indexOf(previous),
      );
    }
    expect(gradeWindow(window(4), 'handback').tier).toBe('handback');
    expect(gradeWindow(window(4), 'reduced').tier).toBe('reduced');
  });
});

describe('the ladder is inert during a capture', () => {
  it('grades full and says why, whatever the frame times were', () => {
    const grade = gradeWindow(window(900), 'full', { cinema: true });
    expect(grade.tier).toBe('full');
    expect(grade.reason).toBe('inert-under-cinema');
    expect(grade.explanation).toContain('software rasteriser');
  });

  it('will not degrade a scene that has already descended, either', () => {
    expect(gradeWindow(window(900), 'reduced', { cinema: true }).tier).toBe('full');
  });
});

describe('what each rung actually turns off', () => {
  it('drops decoration before it drops a fact', () => {
    const full = detailBudgetFor('full');
    const reduced = detailBudgetFor('reduced');
    expect(full.showLaneRails).toBe(true);
    expect(reduced.showLaneRails).toBe(false);
    expect(reduced.labelStride).toBeGreaterThan(full.labelStride);
    // The canvas still renders every node and every edge at the reduced tier: the only
    // thing dropped is the geometry that carries no fact.
    expect(reduced.renderCanvas).toBe(true);
  });

  it('stops rendering the canvas at all on hand-back', () => {
    expect(detailBudgetFor('handback').renderCanvas).toBe(false);
  });
});

describe('the frame sampler', () => {
  it('is a fixed-capacity ring, not a growing array', () => {
    const sampler = createFrameSampler(5);
    for (let index = 0; index < 100; index += 1) sampler.push(index);
    expect(sampler.samples()).toHaveLength(5);
    expect(sampler.samples()).toEqual([95, 96, 97, 98, 99]);
    expect(sampler.full()).toBe(true);
  });

  it('refuses nonsense samples', () => {
    const sampler = createFrameSampler(4);
    sampler.push(Number.NaN);
    sampler.push(-3);
    sampler.push(12);
    expect(sampler.samples()).toEqual([12]);
  });

  it('resets cleanly when a tier changes', () => {
    const sampler = createFrameSampler(3);
    sampler.push(1);
    sampler.reset();
    expect(sampler.samples()).toEqual([]);
    expect(sampler.full()).toBe(false);
  });
});
