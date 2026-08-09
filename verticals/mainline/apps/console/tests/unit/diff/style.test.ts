// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REGISTER, ENFORCED ON THIS FEATURE'S OWN STYLESHEET.
 *
 * `tests/unit/design/primitives-css.test.ts` holds the DESIGN package to the token law.
 * It globs `/src/design/**` and therefore says nothing about a feature stylesheet — which
 * is where the law would actually be broken, because a feature author reaching for a
 * colour reaches for it in their own CSS Module and no lint in the repository objects.
 *
 * So this file holds `src/features/diff/**` to the same law:
 *
 *   • every custom property referenced is declared in `TOKEN_LAW` and permitted in the
 *     EVIDENCE register (`--tp-duration-instrument`, `--tp-ease-*` are not);
 *   • no raw hex, `rgb()`, `hsl()`, `oklch()` or named colour — one token set, no second
 *     source of colour;
 *   • nothing that moves and nothing with depth: no `transition`, `animation`,
 *     `transform`, `box-shadow`, `filter` or gradient. "Nothing moves that a screenshot
 *     could not reproduce" is either a test or a slogan.
 *
 * It reads the shipped bytes rather than a TypeScript copy of them, the same way every
 * gate in `tests/unit/design/` does.
 */

import { describe, expect, it } from 'vitest';

import { TOKEN_LAW, tokenAllowedIn } from '../../../src/design/registers';

const SHEETS = import.meta.glob<string>('/src/features/diff/**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const DECLARED = new Set(TOKEN_LAW.map((rule) => rule.token));

function stylesheets(): [string, string][] {
  const entries = Object.entries(SHEETS);
  if (entries.length === 0) {
    throw new Error(
      'no stylesheet was globbed from src/features/diff/. A glob that matches nothing makes ' +
        'every assertion below pass by iterating an empty collection.',
    );
  }
  return entries;
}

/** Comments carry prose that legitimately contains the words below. */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

describe('the clause diff stylesheet obeys the EVIDENCE register', () => {
  it('references only declared tokens, and only ones EVIDENCE may use', () => {
    for (const [path, css] of stylesheets()) {
      const used = new Set(
        [...stripComments(css).matchAll(/var\((--[a-z0-9-]+)/g)].flatMap((match) => {
          const token = match[1];
          return token === undefined ? [] : [token];
        }),
      );
      expect(used.size, `${path} references no token at all`).toBeGreaterThan(0);
      for (const token of used) {
        expect(DECLARED.has(token), `${path} uses undeclared token ${token}`).toBe(true);
        expect(
          tokenAllowedIn(token, 'evidence'),
          `${path} uses ${token}, which the EVIDENCE register may not reference`,
        ).toBe(true);
      }
    }
  });

  it('contains no colour outside the token set', () => {
    const FORBIDDEN = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\bcolor\(/;
    for (const [path, css] of stylesheets()) {
      const body = stripComments(css);
      expect(FORBIDDEN.test(body), `${path} contains a colour outside src/design/tokens.css`).toBe(
        false,
      );
    }
  });

  it('declares nothing that moves and nothing with depth', () => {
    /**
     * Matched as PROPERTY POSITIONS, not as substrings. `text-transform: uppercase` is a
     * label style and contains the word `transform`; a substring check would fail on it,
     * and the fix somebody would reach for is deleting the check.
     */
    const FORBIDDEN_PROPERTIES = [
      'transition',
      'transition-property',
      'animation',
      'transform',
      'box-shadow',
      'text-shadow',
      'filter',
      'backdrop-filter',
      'perspective',
      'will-change',
    ];
    for (const [path, css] of stylesheets()) {
      const body = stripComments(css);
      for (const property of FORBIDDEN_PROPERTIES) {
        const declared = new RegExp(`(^|[;{}\\s])${property}\\s*:`, 'm').test(body);
        expect(declared, `${path} declares "${property}"`).toBe(false);
      }
      expect(/gradient\s*\(/.test(body), `${path} uses a gradient`).toBe(false);
      expect(body.includes('@keyframes'), `${path} declares keyframes`).toBe(false);
    }
  });
});

describe('the clause diff sources stay inside the EVIDENCE register', () => {
  const SOURCES = import.meta.glob<string>('/src/features/diff/**/*.{ts,tsx}', {
    query: '?raw',
    import: 'default',
    eager: true,
  });

  it('imports no DOM-animation and no GPU package, directly', () => {
    const entries = Object.entries(SOURCES);
    expect(entries.length).toBeGreaterThan(5);
    const FORBIDDEN = /from\s+'(motion|motion\/|framer-motion|three|@react-three)/;
    for (const [path, source] of entries) {
      expect(FORBIDDEN.test(source), `${path} imports a forbidden package`).toBe(false);
    }
  });

  it('contains no console.log — a composed claim gets composed there first', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(/\bconsole\.log\(/.test(source), path).toBe(false);
    }
  });
});
