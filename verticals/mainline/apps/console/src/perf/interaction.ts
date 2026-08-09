// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * INTERACTION LATENCY — the p95 in D13, computed one stated way.
 *
 * "p95 < 100 ms" is not a number until somebody says which of the seven common
 * percentile definitions produced it. Linear interpolation and nearest-rank disagree by
 * a whole sample at small n, and at the sample sizes a demo produces (twenty or thirty
 * interactions) that difference is most of the answer.
 *
 * **This file uses NEAREST-RANK, as defined in ISO 16269-4:** for a sorted ascending
 * sample of size n, the p-th percentile is the element at 1-based index
 * `ceil(p × n)`. It is the definition that never invents a value the system did not
 * exhibit — every percentile this returns is a latency that actually happened, which is
 * the property a claim about a safety console should have.
 *
 * ── THE SAMPLE FLOOR, AND WHY IT RETURNS null RATHER THAN A NUMBER ───────────────
 *
 * With four samples, `ceil(0.95 × 4) = 4`: the "95th percentile" is the maximum. Quoting
 * that as a p95 is not a small error, it is a category error, and it is how a demo ships
 * a latency claim built on three clicks.
 *
 * So `percentile()` refuses below `minimumSamples` and returns `null`. `verdict.ts` then
 * grades that `null` as NOT MEASURED, which for a required budget is a FAILURE. The
 * alternative — returning the max and letting it pass — is the exact shape of dishonesty
 * this product exists to refuse in a different domain.
 */

/** The floor D13's p95 is honest at. Below this, there is no percentile, only a maximum. */
export const DEFAULT_MINIMUM_SAMPLES = 20;

export interface PercentileResult {
  /** The value, or `null` when the sample is too small to have one. */
  readonly value: number | null;
  readonly samples: number;
  /** `'nearest-rank'`, always. Recorded in the result so a report can state its method. */
  readonly method: 'nearest-rank';
  readonly percentile: number;
  /** Why the value is `null`, or `null` when it is a real result. Safe to render. */
  readonly unmeasuredBecause: string | null;
}

/**
 * The p-th percentile of `samples` by nearest rank.
 *
 * @param p                a fraction in (0, 1]
 * @param minimumSamples   below this the result is `null`, not a maximum
 */
export function percentile(
  samples: readonly number[],
  p: number,
  minimumSamples: number = DEFAULT_MINIMUM_SAMPLES,
): PercentileResult {
  if (p <= 0 || p > 1 || !Number.isFinite(p)) {
    throw new Error(`perf/interaction: ${p} is not a percentile fraction in (0, 1].`);
  }

  const finite = samples.filter((value) => Number.isFinite(value) && value >= 0);
  const base: Omit<PercentileResult, 'value' | 'unmeasuredBecause'> = {
    samples: finite.length,
    method: 'nearest-rank',
    percentile: p,
  };

  if (finite.length < minimumSamples) {
    return {
      ...base,
      value: null,
      unmeasuredBecause:
        `${finite.length} sample(s) is below the floor of ${minimumSamples}. At this size the ` +
        `"p${Math.round(p * 100)}" would be the maximum of the sample, which is a different claim.`,
    };
  }

  const sorted = [...finite].sort((a, b) => a - b);
  const rank = Math.ceil(p * sorted.length);
  const value = sorted[rank - 1];
  if (value === undefined) {
    // Unreachable while rank ∈ [1, n]; returned rather than thrown so that a percentile
    // can never take down a surface that was only trying to report on itself.
    return { ...base, value: null, unmeasuredBecause: 'rank fell outside the sorted sample.' };
  }
  return { ...base, value, unmeasuredBecause: null };
}

// ── The sampler ──────────────────────────────────────────────────────────────────

export interface InteractionSample {
  /** `pointerdown`, `keydown`, `click` — whatever the platform reported. */
  readonly kind: string;
  readonly durationMs: number;
}

export interface InteractionSampler {
  readonly record: (sample: InteractionSample) => void;
  readonly durations: () => readonly number[];
  readonly count: () => number;
  readonly p: (fraction: number) => PercentileResult;
  readonly worst: () => InteractionSample | null;
  readonly reset: () => void;
}

export interface SamplerOptions {
  /** Below this many samples, `p()` returns `null`. Defaults to `DEFAULT_MINIMUM_SAMPLES`. */
  readonly minimumSamples?: number;
  /**
   * A hard cap on retained samples, so a long-lived page cannot grow a list forever.
   * When exceeded, the OLDEST sample is dropped — a percentile over the most recent
   * window is a statement about the console as it is now.
   */
  readonly capacity?: number;
}

export function createInteractionSampler(options: SamplerOptions = {}): InteractionSampler {
  const minimumSamples = options.minimumSamples ?? DEFAULT_MINIMUM_SAMPLES;
  const capacity = options.capacity ?? 1000;
  const samples: InteractionSample[] = [];

  return {
    record: (sample: InteractionSample): void => {
      if (!Number.isFinite(sample.durationMs) || sample.durationMs < 0) return;
      samples.push(sample);
      if (samples.length > capacity) samples.shift();
    },
    durations: (): readonly number[] => samples.map((sample) => sample.durationMs),
    count: (): number => samples.length,
    p: (fraction: number): PercentileResult =>
      percentile(
        samples.map((sample) => sample.durationMs),
        fraction,
        minimumSamples,
      ),
    worst: (): InteractionSample | null =>
      samples.reduce<InteractionSample | null>(
        (worst, sample) =>
          worst === null || sample.durationMs > worst.durationMs ? sample : worst,
        null,
      ),
    reset: (): void => {
      samples.length = 0;
    },
  };
}

// ── The platform hook ────────────────────────────────────────────────────────────

export interface ObservationHandle {
  readonly stop: () => void;
  /** `false` when the platform does not report event timings. Never silently assumed. */
  readonly observing: boolean;
  /** Why observation is not running, or `null`. Rendered verbatim by the honesty chrome. */
  readonly unavailableBecause: string | null;
}

/**
 * Feeds a sampler from the platform's Event Timing entries.
 *
 * `PerformanceObserver` with `type: 'event'` is the only source of a real interaction
 * latency — the interval from the input event to the next paint. A hand-rolled
 * `Date.now()` around a click handler measures the handler, not the interaction, and
 * would report a console that is fast at exactly the moment it is dropping frames.
 *
 * When the platform does not support it (jsdom does not, and neither does every browser
 * this must run on), the handle says so in `unavailableBecause` and observes nothing.
 * It does NOT fall back to a hand-rolled timer: a number produced by a different method
 * than the budget was written for is worse than no number, because it grades as a pass.
 */
export function observeInteractions(
  sampler: InteractionSampler,
  options: { readonly durationThresholdMs?: number } = {},
): ObservationHandle {
  const unsupported = (reason: string): ObservationHandle => ({
    stop: (): void => undefined,
    observing: false,
    unavailableBecause: reason,
  });

  if (typeof PerformanceObserver === 'undefined') {
    return unsupported(
      'PerformanceObserver is not available in this environment, so interaction latency is not ' +
        'being measured. It is NOT being assumed to be within budget.',
    );
  }

  const supported: readonly string[] = PerformanceObserver.supportedEntryTypes ?? [];
  if (!supported.includes('event')) {
    return unsupported(
      'this browser does not report the "event" performance entry type, so interaction latency is ' +
        'not being measured. It is NOT being assumed to be within budget.',
    );
  }

  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      sampler.record({ kind: entry.name, durationMs: entry.duration });
    }
  });

  // `durationThreshold` is how the platform is told to report the small ones too. The
  // default is 104 ms, which would hide every interaction just under the 100 ms budget
  // and report a p95 built only from the failures. It is typed as an intersection rather
  // than asserted, because an assertion here would also silence a genuine lib mismatch.
  const init: PerformanceObserverInit & { durationThreshold?: number } = {
    type: 'event',
    buffered: true,
    durationThreshold: options.durationThresholdMs ?? 16,
  };

  try {
    observer.observe(init);
  } catch (error) {
    return unsupported(
      `PerformanceObserver.observe({ type: 'event' }) was refused (${
        error instanceof Error ? error.message : String(error)
      }), so interaction latency is not being measured.`,
    );
  }

  return {
    stop: (): void => {
      observer.disconnect();
    },
    observing: true,
    unavailableBecause: null,
  };
}
