// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CONTRAST GATE — `docs/leads/ui.md` D14.
 *
 * WCAG 2.2 and APCA, computed from the literal text of `tokens.css`, for the CROSS
 * PRODUCT of every foreground and every surface in `pairs.ts`, in BOTH registers of
 * light. 15 foregrounds × 4 surfaces × 2 registers = 120 assertions per pass.
 *
 * The floors:
 *
 *   body       WCAG ≥ 4.5   APCA ≥ 45
 *   emphasis   WCAG ≥ 4.5   APCA ≥ 32
 *   nontext    WCAG ≥ 3.0   APCA not asserted
 *   decorative WCAG ≥ 1.2   APCA not asserted, exemption stated in data
 *
 * WCAG 2.2 is the NORMATIVE gate: it is what the axe-core run in `tests/browser/a11y.spec.ts`
 * enforces and what a procurement questionnaire asks about. APCA-W3 is a WCAG 3 working
 * draft and its floors here are RATCHETS — set at what this palette measures with a
 * margin, so the palette cannot get worse without somebody noticing. Nothing in this
 * repository claims APCA Bronze conformance, and `docs/visual-language.md` says so in
 * the same words.
 *
 * ── PL-2 ─────────────────────────────────────────────────────────────────────────
 *
 * `the gate is capable of refusing` is a real test in this file, not a comment. It runs
 * the same assertion machinery over a deliberately illegal pair and requires it to fail.
 * A contrast suite that has never been red is a contrast suite that asserts nothing —
 * and a contrast suite is exactly the kind that silently stops covering the palette when
 * a parser breaks, because a parse failure and a passing palette look identical from the
 * outside.
 */

import { describe, expect, it } from 'vitest';

import {
  apcaContrast,
  oklchToSrgb,
  parseOklch,
  toHex,
  wcagContrast,
  type Srgb,
} from '../../../src/design/color';
import { BOUNDARIES, declaredPairs, FLOORS, FOREGROUNDS, SURFACES } from '../../../src/design/pairs';
import { parseTokenScopes, resolveTokens, type TokenScope } from '../../../src/design/token-source';
import tokensCss from '../../../src/design/tokens.css?raw';

const scopes = parseTokenScopes(tokensCss);

function colourOf(tokens: ReadonlyMap<string, string>, token: string): Srgb {
  const raw = tokens.get(token);
  if (raw === undefined) throw new Error(`contrast: tokens.css declares no ${token}.`);
  const parsed = parseOklch(raw);
  if (parsed === null) throw new Error(`contrast: ${token} = "${raw}" did not parse as oklch().`);
  return oklchToSrgb(parsed).srgb;
}

interface Measurement {
  readonly wcag: number;
  readonly apca: number;
}

function measure(foreground: Srgb, background: Srgb): Measurement {
  return {
    wcag: wcagContrast(foreground, background),
    apca: Math.abs(apcaContrast(foreground, background)),
  };
}

const REGISTERS_OF_LIGHT: readonly { scope: TokenScope; name: string }[] = [
  { scope: 'dark', name: 'dark (default — control room)' },
  { scope: 'print', name: 'light (print exhibit)' },
];

describe.each(REGISTERS_OF_LIGHT)('contrast · $name', ({ scope }) => {
  const tokens = resolveTokens(scopes, scope);
  const pairs = declaredPairs();

  it('declares a pair for every foreground on every surface', () => {
    expect(pairs.length).toBe(SURFACES.length * (FOREGROUNDS.length + BOUNDARIES.length));
  });

  it.each(pairs.map((pair) => [`${pair.foreground.token} on ${pair.background}`, pair] as const))(
    '%s',
    (_name, pair) => {
      const foreground = colourOf(tokens, pair.foreground.token);
      const background = colourOf(tokens, pair.background);
      const measured = measure(foreground, background);

      const where = `${pair.foreground.where} · ${toHex(foreground)} on ${toHex(background)}`;

      expect(
        measured.wcag,
        `WCAG 2.2: ${pair.foreground.token} on ${pair.background} measures ` +
          `${measured.wcag.toFixed(2)}:1, below the ${pair.foreground.use} floor of ` +
          `${pair.floor.wcag}:1. ${pair.floor.rationale} (${where})`,
      ).toBeGreaterThanOrEqual(pair.floor.wcag);

      if (pair.floor.apca !== null) {
        expect(
          measured.apca,
          `APCA: ${pair.foreground.token} on ${pair.background} measures Lc ` +
            `${measured.apca.toFixed(1)}, below the ${pair.foreground.use} ratchet of ` +
            `${pair.floor.apca}. This is a ratchet, not a conformance claim — but a ratchet ` +
            `that moves backwards is a palette that got worse. (${where})`,
        ).toBeGreaterThanOrEqual(pair.floor.apca);
      }
    },
  );
});

describe('the exemptions are written down rather than granted by omission', () => {
  it('names a reason for every decorative foreground', () => {
    for (const pair of declaredPairs()) {
      if (pair.foreground.use !== 'decorative') continue;
      expect(
        pair.foreground.exemptionReason,
        `${pair.foreground.token} is exempt from SC 1.4.11 with no stated reason. An exemption ` +
          'that is not written down is an omission.',
      ).toBeTruthy();
    }
  });

  it('grants no exemption to any token used as text', () => {
    const textual = declaredPairs().filter(
      (pair) => pair.foreground.use === 'body' || pair.foreground.use === 'emphasis',
    );
    for (const pair of textual) {
      expect(pair.floor.wcag).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe('PL-2 — the gate is capable of refusing', () => {
  /**
   * `--tp-ink-faint` on `--tp-rule` is a pair the design does not use and must never
   * pass: mid grey on mid grey. If this measures at or above the body floor, the
   * arithmetic is broken and every green assertion above is meaningless.
   */
  it('refuses a deliberately illegal pair', () => {
    const tokens = resolveTokens(scopes, 'dark');
    const measured = measure(colourOf(tokens, '--tp-ink-faint'), colourOf(tokens, '--tp-rule'));
    expect(measured.wcag).toBeLessThan(FLOORS.body.wcag);
  });

  it('refuses a token against itself', () => {
    const tokens = resolveTokens(scopes, 'dark');
    const ink = colourOf(tokens, '--tp-ink');
    expect(wcagContrast(ink, ink)).toBeCloseTo(1, 6);
    expect(Math.abs(apcaContrast(ink, ink))).toBe(0);
  });

  /**
   * The arithmetic itself, against values every implementation agrees on. If
   * `wcagContrast` were subtly wrong — a transfer-function mistake, a coefficient typo —
   * every assertion in this file would still be self-consistent and every one of them
   * would be wrong together.
   */
  it('agrees with the published reference values', () => {
    const black: Srgb = { r: 0, g: 0, b: 0 };
    const white: Srgb = { r: 1, g: 1, b: 1 };
    expect(wcagContrast(black, white)).toBeCloseTo(21, 6);
    expect(wcagContrast(white, white)).toBeCloseTo(1, 6);
    // Mid grey #767676 is the canonical 4.54:1-on-white example from the WCAG
    // understanding documents.
    const grey: Srgb = { r: 0x76 / 255, g: 0x76 / 255, b: 0x76 / 255 };
    expect(wcagContrast(grey, white)).toBeGreaterThan(4.5);
    expect(wcagContrast(grey, white)).toBeLessThan(4.6);
    // APCA: black text on white is the maximum-magnitude normal-polarity case and is
    // published at Lc ≈ 106.
    expect(apcaContrast(black, white)).toBeGreaterThan(104);
    expect(apcaContrast(black, white)).toBeLessThan(108);
    // Reverse polarity is negative, which is the sign convention colour.ts documents.
    expect(apcaContrast(white, black)).toBeLessThan(0);
  });
});
