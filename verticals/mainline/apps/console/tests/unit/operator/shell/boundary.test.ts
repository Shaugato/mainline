// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE OPERATOR BOUNDARY — the half a lint cannot provide.
 *
 * `eslint.config.js` refuses a forbidden import in `src/operator/**` where it is typed. This
 * walks the file TEXT of every module in that tree and refuses the same imports when the lint
 * is suppressed inline, when the config's globs are edited, and when the import is reached
 * through a file nobody thought to look at.
 *
 * It is the same two-gate idiom `src/design/registers.ts` and
 * `tests/unit/design/register-boundary.test.ts` use for the three visual registers, for the
 * same reason: a lint can be disabled by the person violating it.
 *
 * ── WHY THIS IS THE HARDEST CONSTRAINT IN THE REPOSITORY RIGHT NOW ───────────────────
 *
 * `docs/STATE-OF-THE-BUILD.md` §12.9 measures the console's entry chunk at 138,156 B gzipped
 * against a 139,264 B response ceiling — 1,108 bytes of headroom — and `check-budgets`'
 * `_MINIMUM_HEADROOM_BYTES` fails CI below 1,024. A single shared module between
 * `src/operator/**` and the console puts both entries in one chunk closure and spends that
 * headroom, and a 413 on the console's entry chunk is the "NOT YET BOOTED" screen.
 * `docs/demo/operator-systems-plan.md` R2 states the invariant as bytes:
 * `dist/assets/index-*.js` must be byte-identical before and after the operator surface
 * existed. This file is how that stays true after the measurement stops being taken by hand.
 */

import { describe, expect, it } from 'vitest';

import { asSources } from '../../design/raw-sources';
import lintConfigSource from '../../../../eslint.config.js?raw';

/**
 * Every TypeScript module under `src/operator/`.
 *
 * A minimum of 6 because the shell alone is `boot.ts`, `route.ts` and four chrome modules; a
 * glob that matched fewer has stopped seeing the tree and every assertion below would pass by
 * iterating almost nothing.
 */
function operatorSources(): Record<string, string> {
  return asSources(
    import.meta.glob('/src/operator/**/*.{ts,tsx}', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
    'src/operator/**/*.{ts,tsx}',
    6,
  );
}

/** Import specifiers, with `import type` separated because a type erases to zero bytes. */
interface Specifier {
  readonly text: string;
  readonly typeOnly: boolean;
}

/**
 * Extracts every static and dynamic import specifier, ignoring anything inside a comment.
 *
 * Comment stripping first, because this file's own documentation quotes the module names it
 * bans and a checker that reads its own prose reports a violation in every run.
 */
function specifiersIn(source: string): Specifier[] {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
  const out: Specifier[] = [];

  const statement = /\bimport\s+(type\s+)?([^'";]*?)from\s*['"]([^'"]+)['"]/g;
  let match = statement.exec(code);
  while (match !== null) {
    const clause = match[2] ?? '';
    out.push({
      text: match[3] ?? '',
      // `import type { X } from` and `import { type X } from` both erase.
      typeOnly: match[1] !== undefined || /^\s*\{\s*(type\s)/.test(clause),
    });
    match = statement.exec(code);
  }

  const bare = /\bimport\s*['"]([^'"]+)['"]/g;
  match = bare.exec(code);
  while (match !== null) {
    out.push({ text: match[1] ?? '', typeOnly: false });
    match = bare.exec(code);
  }

  const dynamic = /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g;
  match = dynamic.exec(code);
  while (match !== null) {
    out.push({ text: match[1] ?? '', typeOnly: false });
    match = dynamic.exec(code);
  }

  return out;
}

/** Package families no module in this tree may reach, at all, in any form. */
const BANNED_PACKAGES = [
  'react',
  'react-dom',
  'three',
  '@react-three/fiber',
  '@react-three/drei',
  'motion',
  'motion/react',
  'framer-motion',
];

function isPackageReach(specifier: string, family: string): boolean {
  return specifier === family || specifier.startsWith(`${family}/`);
}

/** The console directories this tree may not import a runtime value from. */
const CONSOLE_PACKAGES = ['app', 'design', 'features', 'verify', 'data'];

/** Which console package a specifier reaches, or `null`. */
function consolePackageOf(specifier: string): string | null {
  for (const name of CONSOLE_PACKAGES) {
    const patterns = [
      new RegExp(`^/src/${name}(/|$)`),
      new RegExp(`^(\\.\\./)+${name}(/|$)`),
      new RegExp(`(^|/)src/${name}/`),
    ];
    if (patterns.some((pattern) => pattern.test(specifier))) return name;
  }
  return null;
}

const SOURCES = operatorSources();

describe('the walk sees the tree it thinks it sees', () => {
  it('found the shell', () => {
    const paths = Object.keys(SOURCES);
    expect(paths).toContain('/src/operator/boot.ts');
    expect(paths).toContain('/src/operator/route.ts');
    expect(paths).toContain('/src/operator/chrome/AppBar.ts');
    expect(paths).toContain('/src/operator/chrome/Rail.ts');
    expect(paths).toContain('/src/operator/chrome/Watermark.ts');
    expect(paths).toContain('/src/operator/chrome/OriginStrip.ts');
  });

  it('extracts the import forms this tree uses, and ignores the ones in comments', () => {
    // Without this the assertions below could be reading an empty list from a broken regex
    // and reporting the whole tree clean.
    const probe = specifiersIn(
      [
        "import { a } from './a';",
        "import type { T } from '../types';",
        "import { type U, v } from './mixed';",
        "import './side-effect.css';",
        "const lazy = () => import('./lazy');",
        "// import React from 'react';",
        "/* import 'three'; */",
      ].join('\n'),
    );
    const texts = probe.map((entry) => entry.text);
    expect(texts).toContain('./a');
    expect(texts).toContain('../types');
    expect(texts).toContain('./mixed');
    expect(texts).toContain('./side-effect.css');
    expect(texts).toContain('./lazy');
    expect(texts).not.toContain('react');
    expect(texts).not.toContain('three');
    expect(probe.find((entry) => entry.text === '../types')?.typeOnly).toBe(true);
    expect(probe.find((entry) => entry.text === './a')?.typeOnly).toBe(false);
  });
});

describe('src/operator/** imports no framework and no GPU or animation package', () => {
  it.each(Object.keys(SOURCES))('%s', (path) => {
    const source = SOURCES[path] ?? '';
    const offending = specifiersIn(source)
      .map((entry) => entry.text)
      .filter((specifier) => BANNED_PACKAGES.some((family) => isPackageReach(specifier, family)));

    expect(
      offending,
      `${path} imports ${offending.join(', ')}. src/operator/** is vanilla TypeScript so that ` +
        'operator.html shares no chunk with index.html: the console entry has ~1.1 KB of ' +
        'headroom against the response ceiling and a shared closure spends it ' +
        '(operator-systems-plan.md R1/R2).',
    ).toEqual([]);
  });
});

describe('src/operator/** imports nothing from the console', () => {
  it.each(Object.keys(SOURCES))('%s', (path) => {
    const source = SOURCES[path] ?? '';
    const offending: string[] = [];

    for (const specifier of specifiersIn(source)) {
      const reached = consolePackageOf(specifier.text);
      if (reached === null) continue;

      // The one permitted reach: `import type` from src/data/types.generated.ts. A type
      // erases to zero bytes, and it is the same contract the kernel client answers to.
      const isGeneratedTypes = /(^|\/)data\/types\.generated(\.ts)?$/.test(specifier.text);
      if (reached === 'data' && isGeneratedTypes && specifier.typeOnly) continue;

      offending.push(specifier.text);
    }

    expect(
      offending,
      `${path} imports ${offending.join(', ')} from the console. CONTROL OF WORK is a different ` +
        'product: sharing MAINLINE’s design system would defeat the demonstration, and sharing ' +
        'any module at all would weld the two entry closures together (operator-systems-plan.md ' +
        'R1). The one permitted reach is `import type` from src/data/types.generated.ts.',
    ).toEqual([]);
  });
});

describe('nothing in this tree fakes work', () => {
  it.each(Object.keys(SOURCES))('%s uses no timer to simulate latency', (path) => {
    const source = SOURCES[path] ?? '';
    const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
    const hits = [...code.matchAll(/\b(setTimeout|setInterval|requestIdleCallback)\s*\(/g)].map(
      (match) => match[1] ?? '',
    );
    expect(
      hits,
      `${path} schedules ${hits.join(', ')}. A timer on this surface can only ever make ` +
        'something feel like work that is not work. Every duration on screen is one the kernel ' +
        'reported (operator-systems-plan.md R5, §6).',
    ).toEqual([]);
  });
});

describe('eslint.config.js carries the fast half of this boundary', () => {
  it('was read, so the checks below are not measuring an empty string', () => {
    expect(lintConfigSource.length).toBeGreaterThan(1000);
    expect(lintConfigSource).toContain('no-restricted-imports');
  });

  it('names the operator glob, so the directory is covered at all', () => {
    // A directory the lint has never heard of looks exactly like a directory with no
    // violations — the failure mode nobody notices.
    expect(lintConfigSource).toContain('src/operator/**/*.{ts,tsx}');
  });

  it('names every family this walk refuses', () => {
    for (const family of ['react', 'react-dom', 'three', '@react-three', 'motion']) {
      expect(
        lintConfigSource.includes(`'${family}`),
        `eslint.config.js never mentions ${family} in a pattern group, so an author learns about ` +
          'the violation from CI minutes later rather than from the editor immediately.',
      ).toBe(true);
    }
    for (const name of CONSOLE_PACKAGES) {
      expect(
        lintConfigSource.includes(`'${name}'`) || lintConfigSource.includes(`/src/${name}`),
        `eslint.config.js never mentions src/${name} for the operator register.`,
      ).toBe(true);
    }
  });
});
