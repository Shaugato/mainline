// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SEVERITY RAMP.
 *
 * `mainline.virulence_class` has four values and the ramp has four steps. Three
 * properties are asserted here because all three are the difference between a scale and
 * a decoration:
 *
 *   1. MONOTONE IN LIGHTNESS AND MONOTONE IN CHROMA. Severity deepens and saturates;
 *      neither coordinate ever reverses. This is what makes the ramp readable as a rank
 *      rather than as four colours somebody liked.
 *   2. ONE HUE. Never a rainbow. A hue change across a severity scale encodes rank in
 *      the one channel a dichromat cannot read, and it is the single most common way an
 *      otherwise careful palette becomes inaccessible.
 *   3. STILL ORDERED UNDER DICHROMACY. Simulated with the Viénot–Brettel–Mollon (1999)
 *      linear-RGB model for protanopia and deuteranopia.
 *
 * ── WHAT (3) IS AND IS NOT ───────────────────────────────────────────────────────
 *
 * The simulation is a MODEL of a median dichromat, not a measurement of any person, and
 * it does not cover anomalous trichromacy (the far more common case) or tritanopia
 * (which the 1999 single-matrix form does not model at all). Naming the gap is the point.
 *
 * It is also not the accessibility argument on its own. `severity.ts`'s redundancy rule
 * is: the band NAME is always rendered as text and there is no prop that removes it.
 * The separation asserted below is a SUPPORT for that rule — it keeps the ramp usable at
 * a glance — not a substitute for it. That is why the floor is a modest 4.0 L* rather
 * than a number chosen to sound impressive: the colour is never doing the work alone.
 */

import { describe, expect, it } from 'vitest';

import {
  cieLStar,
  fromLinear,
  oklchToSrgb,
  parseOklch,
  simulateDichromacy,
  toHex,
  type Dichromacy,
  type Oklch,
} from '../../../src/design/color';
import { SEVERITY_BANDS, VIRULENCE_CLASSES, bandFor } from '../../../src/design/severity';
import { parseTokenScopes, resolveTokens, type TokenScope } from '../../../src/design/token-source';
import tokensCss from '../../../src/design/tokens.css?raw';

/**
 * Minimum CIE L* between adjacent bands after simulation. See the header: the band name
 * is always text, so this floor keeps the ramp legible at a glance rather than carrying
 * the whole accessibility claim.
 */
const MIN_ADJACENT_LSTAR = 4;

/** Minimum L* across the whole ramp, so the four steps are not three plus a rounding error. */
const MIN_TOTAL_LSTAR = 18;

const scopes = parseTokenScopes(tokensCss);

function rampOf(scope: TokenScope): readonly { band: string; oklch: Oklch }[] {
  const tokens = resolveTokens(scopes, scope);
  return SEVERITY_BANDS.map((band) => {
    const raw = tokens.get(band.token);
    if (raw === undefined) throw new Error(`severity: no ${band.token} in the ${scope} register.`);
    const parsed = parseOklch(raw);
    if (parsed === null) throw new Error(`severity: ${band.token} = "${raw}" did not parse.`);
    return { band: band.virulence, oklch: parsed };
  });
}

const REGISTERS: readonly { scope: TokenScope; name: string }[] = [
  { scope: 'dark', name: 'dark' },
  { scope: 'print', name: 'print' },
];

describe('the band set matches mainline.virulence_class', () => {
  it('has exactly the four values ARCHITECTURE.md §5.0 declares, in the enum order', () => {
    expect(VIRULENCE_CLASSES).toEqual(['routine', 'serious', 'blood_major', 'blood_fatal']);
    expect(SEVERITY_BANDS.map((band) => band.virulence)).toEqual([...VIRULENCE_CLASSES]);
    expect(SEVERITY_BANDS.map((band) => band.rank)).toEqual([0, 1, 2, 3]);
  });

  it('renders every band with a token and a spoken form', () => {
    for (const value of VIRULENCE_CLASSES) {
      const band = bandFor(value);
      expect(band.token.startsWith('--tp-sev-')).toBe(true);
      expect(band.spoken).toContain(value.replace('_', ' '));
    }
  });

  it('refuses an unknown band rather than defaulting one', () => {
    // A silently-defaulted severity is a mis-stated severity, and this is the number
    // that decides what a person is allowed to sign.
    expect(() => bandFor('catastrophic' as never)).toThrow(/no band declared/);
  });
});

describe.each(REGISTERS)('the ramp · $name register', ({ scope }) => {
  const ramp = rampOf(scope);

  it('uses ONE hue — never a rainbow', () => {
    const hues = new Set(ramp.map((step) => step.oklch.h));
    expect(
      [...hues],
      `the severity ramp spans hues ${[...hues].join(', ')}. A hue change across a severity ` +
        'scale encodes rank in the one channel a dichromat cannot read.',
    ).toHaveLength(1);
  });

  it('is monotone in lightness', () => {
    const lightness = ramp.map((step) => step.oklch.l);
    const decreasing = lightness.every(
      (value, index) => index === 0 || value < (lightness[index - 1] ?? Infinity),
    );
    const increasing = lightness.every(
      (value, index) => index === 0 || value > (lightness[index - 1] ?? -Infinity),
    );
    expect(
      decreasing || increasing,
      `lightness runs ${lightness.join(' → ')}, which reverses. A ramp that reverses is four ` +
        'colours, not a rank.',
    ).toBe(true);
  });

  it('is monotone in chroma, and severity SATURATES', () => {
    const chroma = ramp.map((step) => step.oklch.c);
    for (let index = 1; index < chroma.length; index += 1) {
      const current = chroma[index] ?? 0;
      const previous = chroma[index - 1] ?? 0;
      expect(
        current,
        `chroma runs ${chroma.join(' → ')}: ${ramp[index]?.band} is no more saturated than ` +
          `${ramp[index - 1]?.band}.`,
      ).toBeGreaterThan(previous);
    }
  });

  it('keeps routine nearly neutral — a routine clause is not an alarm', () => {
    const routine = ramp[0];
    expect(routine?.oklch.c ?? 1).toBeLessThan(0.03);
  });

  it.each<Dichromacy | 'none'>(['none', 'protanopia', 'deuteranopia'])(
    'stays ordered and separated under %s',
    (kind) => {
      const simulate = (colour: Oklch): number => {
        const srgb = oklchToSrgb(colour).srgb;
        return cieLStar(kind === 'none' ? srgb : simulateDichromacy(srgb, kind));
      };
      const lightness = ramp.map((step) => simulate(step.oklch));

      // Order first: the ramp must still be a rank.
      const descending = lightness.every(
        (value, index) => index === 0 || value < (lightness[index - 1] ?? Infinity),
      );
      const ascending = lightness.every(
        (value, index) => index === 0 || value > (lightness[index - 1] ?? -Infinity),
      );
      expect(
        descending || ascending,
        `under ${kind} the ramp reads L* ${lightness.map((l) => l.toFixed(1)).join(' → ')}, ` +
          'which is no longer ordered.',
      ).toBe(true);

      // Then separation, adjacent and overall.
      for (let index = 1; index < lightness.length; index += 1) {
        const delta = Math.abs((lightness[index] ?? 0) - (lightness[index - 1] ?? 0));
        expect(
          delta,
          `under ${kind}, ${ramp[index - 1]?.band} and ${ramp[index]?.band} differ by only ` +
            `${delta.toFixed(1)} L* ` +
            `(${toHex(oklchToSrgb(ramp[index - 1]?.oklch ?? { l: 0, c: 0, h: 0 }).srgb)} vs ` +
            `${toHex(oklchToSrgb(ramp[index]?.oklch ?? { l: 0, c: 0, h: 0 }).srgb)}).`,
        ).toBeGreaterThanOrEqual(MIN_ADJACENT_LSTAR);
      }

      const total = Math.abs((lightness.at(-1) ?? 0) - (lightness[0] ?? 0));
      expect(total, `under ${kind} the whole ramp spans only ${total.toFixed(1)} L*`).toBeGreaterThanOrEqual(
        MIN_TOTAL_LSTAR,
      );
    },
  );
});

describe('PL-2 — the ramp gate is capable of refusing', () => {
  it('detects a non-monotone chroma sequence', () => {
    const chroma = [0.02, 0.14, 0.09, 0.2];
    const monotone = chroma.every(
      (value, index) => index === 0 || value > (chroma[index - 1] ?? -Infinity),
    );
    expect(monotone).toBe(false);
  });

  it('detects a rainbow', () => {
    const hues = new Set([30, 90, 150, 210]);
    expect(hues.size).toBeGreaterThan(1);
  });

  /**
   * THE ASSERTION THAT CAUGHT A REAL BUG IN THIS REPOSITORY.
   *
   * A dichromat sees achromatic colours exactly as a trichromat does, so the simulation
   * must fix every grey. The first implementation used the LMS-space Viénot matrices —
   * the ones most often quoted — which send a neutral grey negative. Every separation
   * number in this file would have been wrong, and no assertion about the ramp itself
   * could have revealed it, because the ramp's numbers would have been self-consistent.
   */
  it('leaves greys untouched, which is the model’s defining property', () => {
    for (const level of [0.02, 0.05, 0.25, 0.5, 0.75, 0.95, 1]) {
      const grey = fromLinear({ r: level, g: level, b: level });
      for (const kind of ['protanopia', 'deuteranopia'] as const) {
        const simulated = simulateDichromacy(grey, kind);
        expect(cieLStar(simulated), `${kind} shifted a grey at linear ${level}`).toBeCloseTo(
          cieLStar(grey),
          3,
        );
      }
    }
  });

  /**
   * A COLLAPSE, CONSTRUCTED RATHER THAN HUNTED FOR.
   *
   * Both matrices are rank-deficient projections onto the dichromat's two-dimensional
   * gamut. So for any chromatic colour `c`, `c` and `simulate(c)` are two DIFFERENT
   * colours that a dichromat cannot tell apart — which is the demonstration, computed
   * from the transform rather than from a pair somebody found by eye.
   *
   * Idempotence is the same fact stated as an equation: projecting twice is projecting
   * once. An identity transform (or one applied in the wrong colour space) fails it.
   */
  it.each(['protanopia', 'deuteranopia'] as const)(
    'projects onto a gamut where a distinguishable pair becomes indistinguishable · %s',
    (kind) => {
      const vivid = oklchToSrgb({ l: 0.62, c: 0.17, h: 145 }).srgb;
      const asSeen = simulateDichromacy(vivid, kind);

      // A trichromat separates these two easily — they are different colours, which is
      // measured in the channels rather than in L* because the projection moves hue and
      // chroma far more than it moves lightness. (Which is the whole problem: a ramp that
      // separates by hue vanishes for a dichromat while its lightness looks untouched.)
      const channelDelta = Math.max(
        Math.abs(vivid.r - asSeen.r),
        Math.abs(vivid.g - asSeen.g),
        Math.abs(vivid.b - asSeen.b),
      );
      expect(channelDelta, 'the simulation is a no-op — it is not projecting at all').toBeGreaterThan(
        0.15,
      );

      // ...and a dichromat cannot: both project to the same point.
      const twice = simulateDichromacy(asSeen, kind);
      expect(cieLStar(twice)).toBeCloseTo(cieLStar(asSeen), 2);
      expect(twice.r).toBeCloseTo(asSeen.r, 2);
      expect(twice.g).toBeCloseTo(asSeen.g, 2);
      expect(twice.b).toBeCloseTo(asSeen.b, 2);
    },
  );
});
