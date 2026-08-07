// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE STYLESHEET GATES.
 *
 * `contrast.test.ts` proves that every DECLARED pair is legible. This file proves the
 * declaration is TOTAL — that the stylesheets do not use a colour the contrast gate has
 * never heard of. Without it, `pairs.ts` is a list somebody maintains by hand and the
 * gate covers whatever happens to be on it.
 *
 * Four rules, each of which encodes a decision from `docs/visual-language.md`:
 *
 *   1. Every token used as a `color` is in `FOREGROUNDS`; every token used as a
 *      `background` is in `SURFACES`. A colour outside both lists fails.
 *   2. `--tp-ok` — the only green in the console — appears in exactly ONE declaration
 *      block, the VerificationSeal's `verified` state. There is no green tick without a
 *      recomputation behind it, and a green available to any stylesheet is a green
 *      available without arithmetic.
 *   3. Every block that sets an EMPHASIS-ONLY foreground as its `color` also sets the
 *      emphasis weight. That is the half of the emphasis rule a stylesheet can be held
 *      to; the size half is carried by primitives with no prop that shrinks them.
 *   4. No stylesheet in the design package contains a raw hex, `rgb()`, or named colour.
 *      One token set, no second source of colour.
 */

import { describe, expect, it } from 'vitest';

import { EMPHASIS_MIN_WEIGHT, EMPHASIS_ONLY, FOREGROUNDS, SURFACES } from '../../../src/design/pairs';
import {
  parseRuleBlocks,
  parseTokenScopes,
  stripCssComments,
  toMap,
} from '../../../src/design/token-source';
import tokensCss from '../../../src/design/tokens.css?raw';

/** Component stylesheets only — `tokens.css` DECLARES the palette rather than using it. */
const COMPONENT_STYLESHEETS = Object.fromEntries(
  Object.entries(
    import.meta.glob('/src/design/**/*.css', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
  ).filter(([path]) => !path.endsWith('/tokens.css')),
);

const ALL_STYLESHEETS = import.meta.glob('/src/design/**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const foregroundTokens = new Set(FOREGROUNDS.map((entry) => entry.token));
const surfaceTokens = new Set(SURFACES);

/**
 * The tokens that actually carry a COLOUR, determined by reading `tokens.css` rather
 * than by naming them here.
 *
 * The distinction matters because `border: var(--tp-hairline) solid var(--tp-rule)` is
 * one declaration mentioning two tokens, only one of which is a colour. A check that
 * treated every token in a border shorthand as a colour would fail on the width and
 * would be "fixed" by adding the width to the colour allow-list — at which point the
 * allow-list means nothing.
 */
const COLOUR_TOKENS = new Set(
  [...toMap(parseTokenScopes(tokensCss)[0] ?? { scope: 'dark', selector: '', declarations: [] })]
    .filter(([, value]) => value.startsWith('oklch('))
    .map(([token]) => token),
);

interface Usage {
  readonly path: string;
  readonly selector: string;
  readonly property: string;
  readonly token: string;
  readonly body: string;
}

function usages(property: RegExp): readonly Usage[] {
  const out: Usage[] = [];
  for (const [path, css] of Object.entries(COMPONENT_STYLESHEETS)) {
    for (const rule of parseRuleBlocks(css)) {
      const declarations = rule.body.split(';');
      for (const declaration of declarations) {
        const colon = declaration.indexOf(':');
        if (colon < 0) continue;
        const name = declaration.slice(0, colon).trim();
        const value = declaration.slice(colon + 1);
        if (!property.test(name)) continue;
        const pattern = /var\(\s*(--[a-z0-9-]+)/g;
        let match = pattern.exec(value);
        while (match !== null) {
          const token = match[1];
          if (token !== undefined) {
            out.push({ path, selector: rule.selector, property: name, token, body: rule.body });
          }
          match = pattern.exec(value);
        }
      }
    }
  }
  return out;
}

describe('every colour a stylesheet uses is covered by the contrast gate', () => {
  it('found colour tokens to check against, so the checks below are not vacuous', () => {
    expect(COLOUR_TOKENS.size).toBeGreaterThan(15);
    expect(COLOUR_TOKENS.has('--tp-ink')).toBe(true);
    expect(COLOUR_TOKENS.has('--tp-hairline')).toBe(false);
  });

  it('uses only declared FOREGROUNDS as a `color`', () => {
    const bad = usages(/^color$/)
      .filter((usage) => COLOUR_TOKENS.has(usage.token) && !foregroundTokens.has(usage.token))
      .map((usage) => `${usage.path} ${usage.selector} { color: var(${usage.token}) }`);
    expect(
      bad,
      'a token used as a foreground but absent from pairs.ts FOREGROUNDS is a colour the ' +
        'contrast gate never measures',
    ).toEqual([]);
  });

  it('uses only declared SURFACES as a `background`', () => {
    const bad = usages(/^background(-color)?$/)
      .filter((usage) => COLOUR_TOKENS.has(usage.token) && !surfaceTokens.has(usage.token))
      .map((usage) => `${usage.path} ${usage.selector} { ${usage.property}: var(${usage.token}) }`);
    expect(
      bad,
      'a token used as a background but absent from pairs.ts SURFACES escapes the cross ' +
        'product entirely. Use `background: currentColor` with a declared foreground instead.',
    ).toEqual([]);
  });

  it('uses only declared boundary or foreground tokens as a border colour', () => {
    const allowed = new Set([...foregroundTokens, '--tp-rule', '--tp-rule-strong', '--tp-focus']);
    const bad = usages(/^border(-[a-z]+)?-color$|^border(-[a-z]+)?$/)
      .filter((usage) => COLOUR_TOKENS.has(usage.token) && !allowed.has(usage.token))
      .map((usage) => `${usage.path} ${usage.selector} { ${usage.property}: var(${usage.token}) }`);
    expect(bad).toEqual([]);
  });

  /**
   * The escape hatch a component-local custom property would otherwise be.
   *
   * `--meter-fraction` and `--digest-prefix-width` are set from an inline `style` prop,
   * so their VALUES are invisible to every check in this file. That is fine while they
   * carry lengths. The moment one carried a colour it would be a colour the contrast
   * gate has never measured and cannot measure, so the rule is simply: a local custom
   * property is never a colour.
   */
  it('never uses a component-local custom property as a colour', () => {
    const colourProperties = /^(color|background(-color)?|border(-[a-z]+)?-color|outline-color|fill|stroke)$/;
    const bad = usages(colourProperties)
      .filter((usage) => !usage.token.startsWith('--tp-'))
      .map((usage) => `${usage.path} ${usage.selector} { ${usage.property}: var(${usage.token}) }`);
    expect(
      bad,
      'a component-local custom property is set from an inline style, so the contrast gate ' +
        'cannot see its value. Local properties carry lengths; colours come from --tp- tokens.',
    ).toEqual([]);
  });
});

describe('the only green in the console', () => {
  it('appears in exactly one declaration block, and it is the verified seal', () => {
    const blocks: string[] = [];
    for (const [path, css] of Object.entries(ALL_STYLESHEETS)) {
      if (path.endsWith('/tokens.css')) continue;
      for (const rule of parseRuleBlocks(css)) {
        if (rule.body.includes('--tp-ok')) blocks.push(`${path} ${rule.selector}`);
      }
    }
    expect(
      blocks,
      'ui.md D6: there is no green tick without a recomputation behind it. A green available ' +
        'to any stylesheet is a green available without arithmetic.',
    ).toEqual(["/src/design/primitives/chips.module.css .seal[data-state='verified']"]);
  });
});

describe('the emphasis rule', () => {
  it('sets the emphasis weight wherever an emphasis-only foreground is the colour', () => {
    const offenders: string[] = [];
    for (const usage of usages(/^color$/)) {
      if (!EMPHASIS_ONLY.includes(usage.token)) continue;
      const weight = /font-weight\s*:\s*([^;]+)/.exec(usage.body);
      const raw = weight?.[1]?.trim() ?? '';
      const numeric = /var\(\s*--tp-weight-strong\s*\)/.test(raw)
        ? EMPHASIS_MIN_WEIGHT
        : Number(raw);
      if (!Number.isFinite(numeric) || numeric < EMPHASIS_MIN_WEIGHT) {
        offenders.push(
          `${usage.path} ${usage.selector} sets color: var(${usage.token}) with font-weight "${raw || '(none)'}"`,
        );
      }
    }
    expect(
      offenders,
      `${EMPHASIS_ONLY.join(', ')} are emphasis-only foregrounds under pairs.ts: APCA penalises ` +
        'a saturated accent on near-black hard enough that these must never be small regular ' +
        'text. Every block that colours with one must also set --tp-weight-strong.',
    ).toEqual([]);
  });
});

describe('one token set, no second source of colour', () => {
  it('contains no raw hex, rgb(), hsl() or named colour outside tokens.css', () => {
    const offenders: string[] = [];
    for (const [path, css] of Object.entries(COMPONENT_STYLESHEETS)) {
      const clean = stripCssComments(css);
      for (const pattern of [/#[0-9a-f]{3,8}\b/gi, /\brgba?\(/gi, /\bhsla?\(/gi]) {
        pattern.lastIndex = 0;
        let match = pattern.exec(clean);
        while (match !== null) {
          offenders.push(`${path}: ${match[0]}`);
          match = pattern.exec(clean);
        }
      }
      // The named colours a stylesheet reaches for by accident. `transparent`,
      // `currentColor`, `inherit` and `none` are structural, not colour choices.
      for (const named of ['white', 'black', 'red', 'green', 'grey', 'gray', 'orange', 'yellow']) {
        const pattern = new RegExp(`:\\s*[^;{}]*\\b${named}\\b`, 'gi');
        let match = pattern.exec(clean);
        while (match !== null) {
          offenders.push(`${path}: ${match[0].trim()}`);
          match = pattern.exec(clean);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('parses a representative stylesheet into rules, so the checks above are not vacuous', () => {
    const chips = ALL_STYLESHEETS['/src/design/primitives/chips.module.css'] ?? '';
    const rules = parseRuleBlocks(chips);
    expect(rules.length).toBeGreaterThan(8);
    expect(rules.some((rule) => rule.selector.includes("[data-virulence='blood_fatal']"))).toBe(true);
    // Declarations inside @media print must be reachable, or a policy stops at a media
    // query and everybody learns where the loophole is.
    const printRules = parseRuleBlocks(chips).filter((rule) => rule.selector.startsWith('@media'));
    expect(printRules.length).toBeGreaterThan(0);
  });
});
