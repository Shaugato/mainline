// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE QUALITY LADDER.
 *
 *   > Measure the first 30 frames and drop instancing detail or hand back to the ribbon
 *   > if the frame budget is missed — never let a mine-site laptop stutter through a
 *   > fatality.
 *
 * Three tiers, one direction, and a measurement that has to be taken before it is
 * allowed to have an opinion. `docs/dimensionality-charter.md` §6.
 *
 * ── WHY p95 AND NOT THE MEAN ─────────────────────────────────────────────────────
 *
 * The thing this rule protects against is a STUTTER, and a mean is exactly the statistic
 * that hides one: twenty-nine 8 ms frames and one 180 ms frame average to 13.7 ms and
 * look healthy, while the reader saw the screen freeze. p95 over a 30-frame window
 * reports the second-worst frame, which is the frame the reader remembers.
 *
 * ── WHY IT IS INERT UNDER CINEMA MODE ────────────────────────────────────────────
 *
 * A capture runs under ANGLE/SwiftShader, a software rasteriser that misses every frame
 * budget by construction. If the ladder ran during a capture, the scene would degrade
 * partway through and the screenshot would become a function of how fast the CI runner
 * happened to be — which is precisely the property D12 exists to remove.
 */

/** How many frames a grade needs. Fewer than this is not a measurement. */
export const QUALITY_SAMPLE_FRAMES = 30;

/** 60 fps. A frame at or under this is `full`. */
export const FULL_TIER_P95_MS = 16.7;

/** ~36 fps. Above this the walk is handed back to the ribbon. */
export const REDUCED_TIER_P95_MS = 28;

export type DetailTier = 'full' | 'reduced' | 'handback';

/** Ordered worst-last, so a descent is a comparison rather than a lookup table. */
export const DETAIL_TIERS: readonly DetailTier[] = ['full', 'reduced', 'handback'];

export type QualityReason =
  | 'insufficient-sample'
  | 'within-budget'
  | 'missed-full-budget'
  | 'missed-reduced-budget'
  | 'reduced-window-still-missed'
  | 'inert-under-cinema';

export interface QualityGrade {
  readonly tier: DetailTier;
  readonly reason: QualityReason;
  /** The measured p95, or `null` when no measurement was taken. */
  readonly p95Ms: number | null;
  /** One sentence, safe to render verbatim to a reader who wonders why it looks simpler. */
  readonly explanation: string;
}

/**
 * The p95 of a sample, by the nearest-rank method on a sorted copy.
 *
 * Nearest-rank rather than linear interpolation: an interpolated percentile invents a
 * frame time that no frame took, and every other number this console renders is one the
 * machine actually produced.
 */
export function p95(samples: readonly number[]): number | null {
  const finite = samples.filter((value) => Number.isFinite(value) && value >= 0);
  if (finite.length === 0) return null;
  const sorted = finite.slice().sort((a, b) => a - b);
  const rank = Math.ceil(0.95 * sorted.length);
  const index = Math.min(sorted.length - 1, Math.max(0, rank - 1));
  return sorted[index] ?? null;
}

/**
 * Grades one 30-frame window.
 *
 * `previousTier` makes the ladder monotone: a session's tier only ever descends. A tier
 * that could climb back would make the scene oscillate between detail levels on a
 * machine sitting near the threshold, and an oscillating scene is a scene whose
 * screenshot means nothing.
 */
export function gradeWindow(
  samples: readonly number[],
  previousTier: DetailTier = 'full',
  options: { readonly cinema?: boolean } = {},
): QualityGrade {
  if (options.cinema === true) {
    return {
      tier: 'full',
      reason: 'inert-under-cinema',
      p95Ms: null,
      explanation:
        'Cinema mode: the quality ladder is inert. A capture runs under a software rasteriser ' +
        'that misses every frame budget by construction, and a scene that degraded mid-capture ' +
        'would make the screenshot a function of the runner rather than of the data.',
    };
  }

  if (samples.length < QUALITY_SAMPLE_FRAMES) {
    return {
      tier: previousTier,
      reason: 'insufficient-sample',
      p95Ms: null,
      explanation:
        `Fewer than ${QUALITY_SAMPLE_FRAMES} frames have been measured. A measurement that has ` +
        'not been taken is not evidence of a problem, so the tier is unchanged.',
    };
  }

  const measured = p95(samples);
  if (measured === null) {
    return {
      tier: previousTier,
      reason: 'insufficient-sample',
      p95Ms: null,
      explanation: 'No usable frame times in the window; the tier is unchanged.',
    };
  }

  const descend = (candidate: DetailTier): DetailTier => {
    const previousRank = DETAIL_TIERS.indexOf(previousTier);
    const candidateRank = DETAIL_TIERS.indexOf(candidate);
    return candidateRank > previousRank ? candidate : previousTier;
  };

  if (measured <= FULL_TIER_P95_MS) {
    return {
      tier: previousTier,
      reason: 'within-budget',
      p95Ms: measured,
      explanation: `p95 frame time ${measured.toFixed(1)} ms is within the ${FULL_TIER_P95_MS} ms budget.`,
    };
  }

  if (measured <= REDUCED_TIER_P95_MS) {
    // Missing the full budget once drops one rung. Missing it again while already
    // reduced is the second window in charter §6 and goes all the way to the ribbon.
    const tier = previousTier === 'full' ? descend('reduced') : descend('handback');
    return {
      tier,
      reason: previousTier === 'full' ? 'missed-full-budget' : 'reduced-window-still-missed',
      p95Ms: measured,
      explanation:
        `p95 frame time ${measured.toFixed(1)} ms exceeds the ${FULL_TIER_P95_MS} ms budget. ` +
        (tier === 'handback'
          ? 'The reduced scene still misses it, so the walk hands back to the ribbon, which ' +
            'carries every fact the walk does.'
          : 'Lane rails and most year labels are dropped; no node and no edge is dropped.'),
    };
  }

  return {
    tier: descend('handback'),
    reason: 'missed-reduced-budget',
    p95Ms: measured,
    explanation:
      `p95 frame time ${measured.toFixed(1)} ms exceeds the ${REDUCED_TIER_P95_MS} ms hand-back ` +
      'threshold. The walk is handed back to the ribbon rather than stuttering through a ' +
      'fatality; the ribbon carries every node and every edge the walk would have drawn.',
  };
}

/** What each tier actually turns off. Read by `WalkScene.tsx`; asserted by `quality.test.ts`. */
export interface DetailBudget {
  readonly showLaneRails: boolean;
  /** Render a year label only every Nth decade boundary. `1` means every label. */
  readonly labelStride: number;
  /** Whether inferred edges keep their own dashed draw call. */
  readonly dashedInferredEdges: boolean;
  readonly renderCanvas: boolean;
}

export function detailBudgetFor(tier: DetailTier): DetailBudget {
  if (tier === 'full') {
    return {
      showLaneRails: true,
      labelStride: 1,
      dashedInferredEdges: true,
      renderCanvas: true,
    };
  }
  if (tier === 'reduced') {
    return {
      showLaneRails: false,
      labelStride: 2,
      // The dash carries "this link is inferred". Dropping the draw call does not drop
      // the fact: the DOM legend states it, and the ribbon renders it distinctly. A
      // fact never leaves the console because a laptop is slow.
      dashedInferredEdges: false,
      renderCanvas: true,
    };
  }
  return {
    showLaneRails: false,
    labelStride: 4,
    dashedInferredEdges: false,
    renderCanvas: false,
  };
}

/**
 * A tiny fixed-capacity ring of frame times.
 *
 * Fixed capacity because an unbounded array in a per-frame path is a leak with a nice
 * name, and because the ladder only ever asks about the most recent window.
 */
export interface FrameSampler {
  readonly push: (frameMs: number) => void;
  readonly samples: () => readonly number[];
  readonly full: () => boolean;
  readonly reset: () => void;
}

export function createFrameSampler(capacity: number = QUALITY_SAMPLE_FRAMES): FrameSampler {
  const size = Math.max(1, Math.trunc(capacity));
  let buffer: number[] = [];
  return {
    push(frameMs) {
      if (!Number.isFinite(frameMs) || frameMs < 0) return;
      buffer.push(frameMs);
      if (buffer.length > size) buffer = buffer.slice(buffer.length - size);
    },
    samples() {
      return buffer.slice();
    },
    full() {
      return buffer.length >= size;
    },
    reset() {
      buffer = [];
    },
  };
}
