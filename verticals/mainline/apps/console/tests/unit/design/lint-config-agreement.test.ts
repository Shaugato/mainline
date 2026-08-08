// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SHIPPED LINT CONFIG AGREES WITH THE REGISTER LAW.
 *
 * D9 enforces the register boundary twice: `eslint.config.js` refuses a forbidden import
 * where it is typed, and `register-boundary.test.ts` walks the module graph so the same
 * import is still refused when the lint is suppressed, reached transitively, or edited
 * away. This file checks the FIRST half is actually wired to the law rather than to a
 * copy of the law — which is the failure nobody notices, because a lint that has stopped
 * covering a directory is indistinguishable from a directory with no violations.
 *
 * `src/design/registers.ts` exports `registerBoundaryConfigs()` precisely so that
 * `eslint.config.js` can spread it and this question cannot arise. It does not spread it
 * today: `eslint.config.js` belongs to the console-foundation worker and hand-writes an
 * equivalent boundary. So the assertion below is the one that holds in either world:
 *
 *   EITHER the config spreads the exported fragment,
 *   OR every directory the law names appears in the config as a literal glob.
 *
 * ── WHAT THIS FILE DELIBERATELY DOES NOT ASSERT ──────────────────────────────────
 *
 * It does not require the lint's package patterns to be complete down to every subpath.
 * They are not: at the time of writing the hand-written config lists `motion-utils` but
 * not `motion-utils/**`, so `import 'motion-utils/some/deep/module'` inside an EVIDENCE
 * file is a lint the config lets through. That import is still refused — by the module
 * graph walk, which matches the same glob groups this file's law exports and is total
 * over the source tree. Recording the difference here beats asserting a completeness the
 * repository does not have; the fix is one string in a file this worker does not own.
 *
 * What IS asserted is that every restricted package FAMILY is named at all. A config that
 * had never heard of `motion` would be a boundary with a hole no walk-shaped argument
 * could excuse.
 */

import { describe, expect, it } from 'vitest';

import {
  EVIDENCE_DIRECTORIES,
  EVIDENCE_FLAT_DIRECTORIES,
  GPU_PACKAGES,
  INSTRUMENT_DIRECTORIES,
  MEMORY_DIRECTORIES,
  MOTION_PACKAGES,
  registerBoundaryConfigs,
} from '../../../src/design/registers';
import lintConfigSource from '../../../eslint.config.js?raw';

/** True when `eslint.config.js` consumes the exported fragment instead of copying it. */
const SPREADS_THE_FRAGMENT =
  /from\s+'\.\/src\/design\/registers(?:\.ts)?'/.test(lintConfigSource) &&
  /registerBoundaryConfigs\s*\(/.test(lintConfigSource);

/**
 * The package family a pattern names: everything before the first glob character, with a
 * trailing separator removed, so `motion` and `motion/**` both come back as `motion`, and
 * every `@react-three` pattern comes back as `@react-three`. (The two-segment scoped
 * globs are not written out in this comment: the characters in the middle of one close a
 * block comment, which is a real bug this directory has already paid for once.)
 */
const familyOf = (pattern: string): string => {
  const head = pattern.split('*')[0] ?? pattern;
  return head.endsWith('/') ? head.slice(0, -1) : head;
};

describe('eslint.config.js — the fast half of the register boundary', () => {
  it('was read, so the checks below are not measuring an empty string', () => {
    expect(lintConfigSource.length).toBeGreaterThan(1000);
    expect(lintConfigSource).toContain('no-restricted-imports');
  });

  it('covers every directory the register law puts under a restriction', () => {
    if (SPREADS_THE_FRAGMENT) return;

    const required = registerBoundaryConfigs().flatMap((config) => [...config.files]);
    expect(required.length).toBeGreaterThan(10);

    const missing = required.filter((glob) => !lintConfigSource.includes(glob));
    expect(
      missing,
      'these directories carry a register law but no lint rule in eslint.config.js:\n' +
        `  ${missing.join('\n  ')}\n\n` +
        'A directory the lint has never heard of looks exactly like a directory with no ' +
        'violations. The intended fix is for eslint.config.js to spread ' +
        "`registerBoundaryConfigs()` from src/design/registers.ts, after which this list " +
        'cannot drift at all.',
    ).toEqual([]);
  });

  it('names every restricted package family', () => {
    if (SPREADS_THE_FRAGMENT) return;

    const families = [...new Set([...GPU_PACKAGES, ...MOTION_PACKAGES].map(familyOf))];
    expect(families).toContain('motion');
    expect(families).toContain('@react-three');

    const missing = families.filter((family) => !lintConfigSource.includes(`'${family}`));
    expect(
      missing,
      `eslint.config.js never mentions ${missing.join(', ')}. A restricted family absent from ` +
        'the lint is refused only by the module-graph walk, which runs in CI rather than in ' +
        'the editor — so the author learns about it minutes later instead of immediately.',
    ).toEqual([]);
  });

  it('never widens the ancestry root to a recursive glob', () => {
    // `src/features/ancestry/**` would swallow `render3d/`, classify the console's one
    // dimensional surface as EVIDENCE, and refuse the `three` import it exists to make.
    // The predictable "fix" for that false refusal is to delete the rule.
    for (const directory of EVIDENCE_FLAT_DIRECTORIES) {
      expect(
        lintConfigSource.includes(`${directory}/**/*.{ts,tsx}`),
        `${directory} is matched recursively in eslint.config.js. It must be matched flatly, or ` +
          `${MEMORY_DIRECTORIES.join(', ')} inherits the EVIDENCE law and the walk surface ` +
          'becomes unbuildable.',
      ).toBe(false);
      expect(lintConfigSource).toContain(`${directory}/*.{ts,tsx}`);
    }
  });

  it('keeps the memory register out of the restricted set entirely', () => {
    // MEMORY forbids nothing at the import level (its law is the stillness rule, which is
    // asserted over the scene graph, not the module graph). A lint entry restricting it
    // would mean somebody re-derived the law instead of reading it.
    const restricted = registerBoundaryConfigs().map((config) => config.name);
    expect(restricted).not.toContain('mainline/register-memory');
  });

  it('agrees with the law about which directories exist at all', () => {
    // A sanity check on the law itself: the three lists must be disjoint, or a file could
    // belong to two registers and the answer would depend on iteration order.
    const all = [...EVIDENCE_DIRECTORIES, ...INSTRUMENT_DIRECTORIES, ...MEMORY_DIRECTORIES];
    expect(new Set(all).size).toBe(all.length);
    for (const memory of MEMORY_DIRECTORIES) {
      expect(EVIDENCE_DIRECTORIES).not.toContain(memory);
      expect(INSTRUMENT_DIRECTORIES).not.toContain(memory);
    }
  });
});
