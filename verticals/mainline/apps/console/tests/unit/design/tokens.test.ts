// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE TOKEN GATE.
 *
 * Everything here reads the literal text of `src/design/tokens.css`. Not a TypeScript
 * copy of the values, not `getComputedStyle` in jsdom (which does not implement
 * `oklch()` and would therefore agree with anything) — the bytes that ship.
 *
 * Four claims, each of which can fail:
 *
 *   1. The token map in `registers.ts` and the stylesheet are in exact bijection. A
 *      token nobody mapped to a register is a token outside the visual language.
 *   2. Every colour is inside the sRGB gamut, so every contrast number computed
 *      downstream is a claim about the colour the reader is actually seeing.
 *   3. The two light scopes are identical, so reviewing the print register on screen
 *      reviews the print register.
 *   4. The shell's fallback sheet is a strict subset. `src/app/tokens-fallback.css`
 *      (owned by the console-foundation worker) exists so the shell is legible before
 *      this file lands; if this file failed to define something the fallback defines,
 *      landing it would REGRESS the shell — the one failure mode a design system can
 *      cause in somebody else's directory.
 */

import { describe, expect, it } from 'vitest';

import { oklchToSrgb, parseOklch, toHex } from '../../../src/design/color';
import { TOKEN_LAW } from '../../../src/design/registers';
import {
  parseDeclarations,
  parseTokenScopes,
  referencedTokens,
  resolveTokens,
  stripCssComments,
  toMap,
} from '../../../src/design/token-source';
import tokensCss from '../../../src/design/tokens.css?raw';
import fallbackCss from '../../../src/app/tokens-fallback.css?raw';

/** Every stylesheet in the design package, so the "is it declared" check is total. */
const DESIGN_STYLESHEETS = import.meta.glob('/src/design/**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const scopes = parseTokenScopes(tokensCss);
const dark = toMap(scopes[0] ?? { scope: 'dark', selector: ':root', declarations: [] });

describe('tokens.css ⇄ TOKEN_LAW', () => {
  it('declares the three scopes the visual language requires', () => {
    expect(scopes.map((scope) => scope.scope)).toEqual(['dark', 'print', 'explicit-light']);
  });

  it('is in exact bijection with the token map', () => {
    const declared = [...dark.keys()].sort();
    const mapped = TOKEN_LAW.map((rule) => rule.token).sort();

    const undocumented = declared.filter((token) => !mapped.includes(token));
    const phantom = mapped.filter((token) => !declared.includes(token));

    expect(
      undocumented,
      `tokens.css declares ${undocumented.join(', ')} but registers.ts TOKEN_LAW does not map ` +
        'them to a register. A token nobody mapped is a token outside the visual language.',
    ).toEqual([]);
    expect(
      phantom,
      `TOKEN_LAW names ${phantom.join(', ')} but tokens.css does not declare them.`,
    ).toEqual([]);
  });

  it('gives every token exactly one purpose and at least one register', () => {
    for (const rule of TOKEN_LAW) {
      expect(rule.purpose.trim(), `${rule.token} has no stated purpose`).not.toBe('');
      expect(rule.registers.length, `${rule.token} is permitted in no register`).toBeGreaterThan(0);
    }
    const seen = new Set(TOKEN_LAW.map((rule) => rule.token));
    expect(seen.size, 'TOKEN_LAW contains a duplicate token').toBe(TOKEN_LAW.length);
  });

  /**
   * `--tp-*` is the design-system namespace. A component may also declare a LOCAL custom
   * property (`--meter-fraction`, `--digest-prefix-width`) set from an inline `style` —
   * that is a component's own plumbing, it carries a length rather than a colour, and
   * `primitives-css.test.ts` asserts separately that no local property is ever used as a
   * colour, which is the only way one could escape the contrast gate.
   */
  it('declares every --tp- token any design stylesheet references', () => {
    const referenced = new Set<string>();
    for (const css of Object.values(DESIGN_STYLESHEETS)) {
      for (const token of referencedTokens(css)) {
        if (token.startsWith('--tp-')) referenced.add(token);
      }
    }
    const undeclared = [...referenced].filter((token) => !dark.has(token)).sort();
    expect(
      undeclared,
      `these tokens are used via var() but never declared: ${undeclared.join(', ')}`,
    ).toEqual([]);
  });
});

describe('gamut', () => {
  const colourTokens = (map: ReadonlyMap<string, string>): [string, string][] =>
    [...map.entries()].filter(([, value]) => value.startsWith('oklch('));

  it('keeps every dark-register colour inside sRGB', () => {
    for (const [token, value] of colourTokens(dark)) {
      const parsed = parseOklch(value);
      expect(parsed, `${token}: "${value}" is not a form token-source.ts can parse`).not.toBeNull();
      if (parsed === null) continue;
      const { srgb, inGamut } = oklchToSrgb(parsed);
      expect(
        inGamut,
        `${token} = ${value} falls outside sRGB (clips to ${toHex(srgb)}). The browser would ` +
          'gamut-map it by an unspecified rule, so every contrast number computed from the ' +
          'authored coordinates would be a claim about a colour nobody is looking at.',
      ).toBe(true);
    }
  });

  it('keeps every print-register colour inside sRGB', () => {
    for (const [token, value] of colourTokens(resolveTokens(scopes, 'print'))) {
      const parsed = parseOklch(value);
      expect(parsed, `${token}: "${value}" did not parse`).not.toBeNull();
      if (parsed === null) continue;
      expect(oklchToSrgb(parsed).inGamut, `${token} = ${value} falls outside sRGB in print`).toBe(
        true,
      );
    }
  });

  it('parses every colour-valued token', () => {
    const unparsed = [...dark.entries()]
      .filter(([, value]) => value.includes('oklch') && parseOklch(value) === null)
      .map(([token]) => token);
    expect(
      unparsed,
      `token-source.ts could not parse ${unparsed.join(', ')}. A token the parser cannot read ` +
        'is a token the contrast gate silently stops covering.',
    ).toEqual([]);
  });
});

describe('the two light scopes', () => {
  it('are identical, so reviewing the print register on screen reviews the print register', () => {
    const print = resolveTokens(scopes, 'print');
    const explicit = resolveTokens(scopes, 'explicit-light');
    const drift = [...print.entries()].filter(([token, value]) => explicit.get(token) !== value);
    expect(
      drift.map(([token]) => token),
      'the @media print block and :root[data-register-theme="light"] disagree; the exhibit ' +
        'nobody can review before printing is the exhibit that is unreadable in the hearing',
    ).toEqual([]);
  });

  it('overrides every colour token and inherits everything else', () => {
    const printOnly = toMap(scopes[1] ?? { scope: 'print', selector: '', declarations: [] });
    const darkColours = [...dark.entries()]
      .filter(([, value]) => value.startsWith('oklch('))
      .map(([token]) => token);
    const missed = darkColours.filter((token) => !printOnly.has(token));
    expect(
      missed,
      `the print register does not restate ${missed.join(', ')}. A colour inherited from the ` +
        'dark register onto white paper is an unreadable exhibit.',
    ).toEqual([]);
  });
});

describe('the shell fallback (src/app/tokens-fallback.css, console-foundation worker)', () => {
  it('is a strict subset — landing tokens.css cannot regress the shell', () => {
    const fallbackTokens = new Set(
      parseDeclarations(stripCssComments(fallbackCss)).map((declaration) => declaration.token),
    );
    const dropped = [...fallbackTokens].filter((token) => !dark.has(token)).sort();
    expect(
      dropped,
      `the shell's fallback sheet declares ${dropped.join(', ')} and tokens.css does not. ` +
        'The fallback is wrapped in :where() (zero specificity) so tokens.css wins wherever it ' +
        'speaks — but where it says nothing the fallback still applies, and a token this file ' +
        'drops becomes a value nobody owns.',
    ).toEqual([]);
  });
});
