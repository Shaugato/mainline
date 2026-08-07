// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Colour arithmetic — OKLCH → sRGB, WCAG 2.2, APCA, and dichromacy simulation.
 *
 * This module exists so that the console's contrast claims are COMPUTED rather than
 * asserted. `docs/leads/ui.md` D14 makes accessibility a gate, and a gate that reads
 * "we checked it in Figma" is not a gate. Every number the visual-language tests
 * enforce comes out of the functions below, applied to the literal text of
 * `tokens.css` — so a token edit that breaks contrast breaks the build, and nobody
 * has to remember to re-check.
 *
 * Zero imports on purpose: this file is pure arithmetic over numbers, it is imported
 * by the EVIDENCE register, and it must be trivially reviewable.
 *
 * PROVENANCE OF THE CONSTANTS — all four sets are published, and are reproduced here
 * rather than pulled from a dependency because a colour library is an audit surface:
 *
 *   • OKLab ⇄ linear-sRGB matrices — Björn Ottosson's 2020 OKLab definition.
 *   • WCAG 2.x relative luminance and the (L1+0.05)/(L2+0.05) ratio — WCAG 2.2, §1.4.3.
 *   • APCA — the APCA-W3 0.1.9 ("0.98G-4g") constant set, the version referenced by the
 *     WCAG 3 working draft. APCA is ADVISORY here, never the gate (see `pairs.ts`).
 *   • Dichromacy simulation — Viénot, Brettel & Mollon (1999), the linear-RGB
 *     single-matrix form. It is a MODEL of a median dichromat, not a measurement of any
 *     person; the tests state that limit in words where they use it.
 */

/** Non-linear sRGB, each channel in [0, 1]. */
export interface Srgb {
  readonly r: number;
  readonly g: number;
  readonly b: number;
}

/** OKLCH. `l` in [0, 1], `c` ≥ 0, `h` in degrees. */
export interface Oklch {
  readonly l: number;
  readonly c: number;
  readonly h: number;
}

const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);

/** sRGB transfer function, non-linear → linear. */
export function srgbToLinear(channel: number): number {
  const c = clamp01(channel);
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** sRGB transfer function, linear → non-linear. */
export function linearToSrgb(channel: number): number {
  const c = clamp01(channel);
  return c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
}

/**
 * OKLCH → sRGB.
 *
 * `inGamut` is returned separately from the clamped colour. A browser rendering
 * `oklch()` on an sRGB display performs its own gamut mapping, which is NOT simple
 * clipping — so a token that leaves sRGB would make every number this module produces
 * a claim about a colour the reader is not seeing. `tokens.test.ts` therefore refuses
 * any token that is out of gamut, and this flag is how it finds out.
 */
export function oklchToSrgb(colour: Oklch): { readonly srgb: Srgb; readonly inGamut: boolean } {
  const hRad = (colour.h * Math.PI) / 180;
  const a = colour.c * Math.cos(hRad);
  const b = colour.c * Math.sin(hRad);

  const lp = colour.l + 0.3963377774 * a + 0.2158037573 * b;
  const mp = colour.l - 0.1055613458 * a - 0.0638541728 * b;
  const sp = colour.l - 0.0894841775 * a - 1.291485548 * b;

  const l3 = lp * lp * lp;
  const m3 = mp * mp * mp;
  const s3 = sp * sp * sp;

  const rLin = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3;
  const gLin = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3;
  const bLin = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3;

  // A 1/1000 tolerance: floating-point round-trips put an in-gamut colour a hair
  // outside on occasion, and refusing those would be a false refusal.
  const tol = 0.001;
  const inGamut =
    rLin >= -tol && rLin <= 1 + tol && gLin >= -tol && gLin <= 1 + tol && bLin >= -tol && bLin <= 1 + tol;

  return {
    srgb: { r: linearToSrgb(rLin), g: linearToSrgb(gLin), b: linearToSrgb(bLin) },
    inGamut,
  };
}

/** sRGB → linear sRGB triple. */
export function toLinear(colour: Srgb): Srgb {
  return { r: srgbToLinear(colour.r), g: srgbToLinear(colour.g), b: srgbToLinear(colour.b) };
}

/** Linear sRGB → sRGB triple. */
export function fromLinear(colour: Srgb): Srgb {
  return { r: linearToSrgb(colour.r), g: linearToSrgb(colour.g), b: linearToSrgb(colour.b) };
}

/** `#rrggbb`, for a failure message a human can paste into a colour picker. */
export function toHex(colour: Srgb): string {
  const byte = (x: number): string =>
    Math.round(clamp01(x) * 255)
      .toString(16)
      .padStart(2, '0');
  return `#${byte(colour.r)}${byte(colour.g)}${byte(colour.b)}`;
}

/** WCAG 2.x relative luminance. */
export function relativeLuminance(colour: Srgb): number {
  const lin = toLinear(colour);
  return 0.2126 * lin.r + 0.7152 * lin.g + 0.0722 * lin.b;
}

/** WCAG 2.2 contrast ratio, in [1, 21]. Symmetric in its arguments, as the spec is. */
export function wcagContrast(a: Srgb, b: Srgb): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

// ── APCA-W3 0.1.9 ──────────────────────────────────────────────────────────────

const APCA_MAIN_TRC = 2.4;
const APCA_R = 0.2126729;
const APCA_G = 0.7151522;
const APCA_B = 0.072175;
const APCA_NORM_BG = 0.56;
const APCA_NORM_TXT = 0.57;
const APCA_REV_TXT = 0.62;
const APCA_REV_BG = 0.65;
const APCA_BLK_THRS = 0.022;
const APCA_BLK_CLMP = 1.414;
const APCA_LO_CLIP = 0.1;
const APCA_DELTA_Y_MIN = 0.0005;
const APCA_SCALE_BOW = 1.14;
const APCA_LO_BOW_OFFSET = 0.027;
const APCA_SCALE_WOB = 1.14;
const APCA_LO_WOB_OFFSET = 0.027;

function apcaY(colour: Srgb): number {
  const y =
    APCA_R * Math.pow(clamp01(colour.r), APCA_MAIN_TRC) +
    APCA_G * Math.pow(clamp01(colour.g), APCA_MAIN_TRC) +
    APCA_B * Math.pow(clamp01(colour.b), APCA_MAIN_TRC);
  // Soft black clamp: APCA models the flare floor of a real display rather than
  // pretending an emissive panel reaches zero luminance.
  return y > APCA_BLK_THRS ? y : y + Math.pow(APCA_BLK_THRS - y, APCA_BLK_CLMP);
}

/**
 * APCA lightness contrast `Lc`, SIGNED.
 *
 * Positive = dark text on a light background; negative = light text on a dark
 * background, which is this console's default polarity. Callers threshold on the
 * absolute value; the sign is kept because losing it hides a polarity mistake, and a
 * polarity mistake is exactly the kind of error that survives a design review.
 */
export function apcaContrast(text: Srgb, background: Srgb): number {
  const yTxt = apcaY(text);
  const yBg = apcaY(background);

  if (Math.abs(yBg - yTxt) < APCA_DELTA_Y_MIN) return 0;

  let sapc: number;
  let output: number;

  if (yBg > yTxt) {
    sapc = (Math.pow(yBg, APCA_NORM_BG) - Math.pow(yTxt, APCA_NORM_TXT)) * APCA_SCALE_BOW;
    output = sapc < APCA_LO_CLIP ? 0 : sapc - APCA_LO_BOW_OFFSET;
  } else {
    sapc = (Math.pow(yBg, APCA_REV_BG) - Math.pow(yTxt, APCA_REV_TXT)) * APCA_SCALE_WOB;
    output = sapc > -APCA_LO_CLIP ? 0 : sapc + APCA_LO_WOB_OFFSET;
  }

  return output * 100;
}

// ── Dichromacy simulation (Viénot, Brettel & Mollon 1999) ──────────────────────

/**
 * The two dichromacies this console is tested against.
 *
 * Tritanopia is deliberately absent: it is far rarer, the 1999 single-matrix model does
 * not cover it, and claiming a check we did not perform is worse than naming the gap.
 * `docs/visual-language.md` names it as an unmeasured risk.
 */
export type Dichromacy = 'protanopia' | 'deuteranopia';

/**
 * The Viénot 1999 dichromacy matrices, expressed for LINEAR sRGB primaries.
 *
 * ── A TRAP WORTH RECORDING, BECAUSE THIS MODULE FELL INTO IT ─────────────────────
 *
 * The numbers most often quoted for "Viénot 1999" — `[0, 2.02344, -2.52581]` for
 * protanopia — are the matrices for **LMS** space, and they are correct there. Applied
 * to RGB they produce a transform under which a NEUTRAL GREY comes out negative and
 * clips to black, which is nonsense: a dichromat sees achromatic colours exactly as a
 * trichromat does.
 *
 * The correct RGB-space forms are below. Their defining property is visible in the
 * numbers: every row sums to 1, so greys are fixed points. `severity.test.ts` asserts
 * that directly, and that assertion is what caught the LMS matrices here — which is the
 * entire argument for a property test over a plausible-looking constant.
 *
 * Both are RANK-DEFICIENT projections onto the dichromat's two-dimensional gamut: the
 * first two output rows are identical, so red and green collapse onto one axis and blue
 * survives. Two consequences the tests use: the transform is IDEMPOTENT, and for any
 * chromatic colour `c`, `c` and `simulate(c)` are two different colours that a dichromat
 * cannot tell apart.
 */
const DICHROMACY_MATRIX: Readonly<Record<Dichromacy, readonly (readonly number[])[]>> =
  Object.freeze({
    protanopia: [
      [0.11238, 0.88762, 0.0],
      [0.11238, 0.88762, 0.0],
      [0.00401, -0.00401, 1.0],
    ],
    deuteranopia: [
      [0.29275, 0.70725, 0.0],
      [0.29275, 0.70725, 0.0],
      [-0.02234, 0.02234, 1.0],
    ],
  });

/**
 * Simulates a median dichromat's percept of a colour.
 *
 * The transform is applied in LINEAR sRGB, which is the whole point of the 1999 paper —
 * running it on gamma-encoded values (a common shortcut) gives visibly wrong hues and
 * would make this check decorative.
 */
export function simulateDichromacy(colour: Srgb, kind: Dichromacy): Srgb {
  const lin = toLinear(colour);
  const m = DICHROMACY_MATRIX[kind];
  const row = (index: number): number => {
    const r = m[index] ?? [0, 0, 0];
    return (r[0] ?? 0) * lin.r + (r[1] ?? 0) * lin.g + (r[2] ?? 0) * lin.b;
  };
  return fromLinear({ r: row(0), g: row(1), b: row(2) });
}

/**
 * CIE L* (0–100) from relative luminance, for "are these two swatches separable by
 * lightness alone" questions. A ramp that is monotone in L* survives every colour
 * vision deficiency and every monochrome photocopier, which is why the severity ramp is
 * built on lightness first and chroma second.
 */
export function cieLStar(colour: Srgb): number {
  const y = relativeLuminance(colour);
  return y > 216 / 24389 ? 116 * Math.cbrt(y) - 16 : (24389 / 27) * y;
}

/**
 * Parses the `oklch(L C H)` / `oklch(L% C H)` form actually used in `tokens.css`.
 *
 * Deliberately narrow. It refuses `oklch(… / alpha)`, colour-mix, relative colour syntax
 * and every other CSS Color 4 form — not because they are bad, but because a token this
 * parser cannot read is a token the contrast gate silently stops covering. Refusing to
 * parse is how the gate stays total.
 */
export function parseOklch(value: string): Oklch | null {
  const match = /^oklch\(\s*([0-9.]+%?)\s+([0-9.]+)\s+([0-9.]+)\s*\)$/i.exec(value.trim());
  if (match === null) return null;
  const [, rawL, rawC, rawH] = match;
  if (rawL === undefined || rawC === undefined || rawH === undefined) return null;
  const l = rawL.endsWith('%') ? Number(rawL.slice(0, -1)) / 100 : Number(rawL);
  const c = Number(rawC);
  const h = Number(rawH);
  if (!Number.isFinite(l) || !Number.isFinite(c) || !Number.isFinite(h)) return null;
  return { l, c, h };
}
