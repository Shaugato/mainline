// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SOURCE CHECKS, AGAINST PLANTED FILES.
 *
 * `scripts/check-a11y.ts` is green today and will stay green, which is exactly the
 * condition under which a broken regex is indistinguishable from a clean repository. So
 * the judgement was moved into `src/a11y/source-checks.ts` and is run here against
 * `fixtures/planted/` — real committed bytes, read as text, the same way the CLI reads
 * the shipped sources.
 *
 * Each check has a file that MUST trip it and a control that must not. The last block is
 * the one that catches a hollowed-out checker: it requires the planted run to produce
 * exactly the expected set of check ids, so a checker that had stopped matching anything
 * fails, and so does one that started matching everything.
 */

import { describe, expect, it } from 'vitest';

import {
  CHECK_IDS,
  SELF_EXEMPT,
  SOURCE_CHECKS,
  classify,
  commentedOut,
  runSourceChecks,
  type SourceFile,
  type SourceKind,
} from '../../../src/a11y/source-checks';

const RAW: Record<string, unknown> = import.meta.glob(
  '/tests/unit/a11y/fixtures/planted/*.fixture',
  { query: '?raw', import: 'default', eager: true },
);

function fixtureText(name: string): string {
  const key = `/tests/unit/a11y/fixtures/planted/${name}`;
  const value = RAW[key];
  if (typeof value !== 'string') {
    throw new Error(
      `fixtures/planted/${name} did not load as text. A planted-violation suite whose fixtures ` +
        'are missing passes every assertion by iterating nothing.',
    );
  }
  return value;
}

/**
 * Builds the `SourceFile` the checks take, with the path and kind supplied EXPLICITLY.
 *
 * The `.fixture` suffix keeps these files out of the TypeScript program and out of the
 * Vite build; the path given here is the one the check should believe, which is also how
 * a fixture is placed inside `render3d/` without creating a file there.
 */
function planted(path: string, kind: SourceKind, name: string): SourceFile {
  return {
    path,
    kind,
    text: fixtureText(name),
    inMemoryRegister: path.startsWith('src/features/ancestry/render3d/'),
  };
}

const VIOLATIONS_TSX = planted('src/features/gate/PlantedPanel.tsx', 'tsx', 'violations.tsx.fixture');
const CLEAN_TSX = planted('src/features/gate/CleanPanel.tsx', 'tsx', 'clean.tsx.fixture');
const VIOLATIONS_CSS = planted('src/features/gate/planted.module.css', 'css', 'violations.css.fixture');
const NOTES_CSS = planted('src/app/planted-shell.module.css', 'css', 'notes.css.fixture');
const CLEAN_CSS = planted('src/features/gate/clean.module.css', 'css', 'clean.css.fixture');
const MEMORY_TSX = planted(
  'src/features/ancestry/render3d/PlantedWalk.tsx',
  'tsx',
  'memory-person.tsx.fixture',
);

function idsFrom(files: readonly SourceFile[]): readonly string[] {
  return [...new Set(runSourceChecks(files).violations.map((violation) => violation.checkId))].sort();
}

describe('the fixtures loaded at all', () => {
  it('found every planted file', () => {
    expect(Object.keys(RAW).length).toBe(6);
    for (const file of [VIOLATIONS_TSX, CLEAN_TSX, VIOLATIONS_CSS, NOTES_CSS, CLEAN_CSS, MEMORY_TSX]) {
      expect(file.text.length, `${file.path} is empty`).toBeGreaterThan(100);
    }
  });

  it('declares more than one check, so an id list cannot be vacuously satisfied', () => {
    expect(SOURCE_CHECKS.length).toBeGreaterThan(8);
    expect(CHECK_IDS).toEqual(SOURCE_CHECKS.map((check) => check.id));
  });
});

describe('the planted TSX', () => {
  const found = idsFrom([VIOLATIONS_TSX]);

  it.each([
    'positive-tabindex',
    'aria-hidden-interactive',
    'click-handler-on-non-interactive',
    'img-without-alt',
    'inner-html',
    'access-key',
    'no-canvas-outside-memory',
    'signer-sub',
  ])('catches %s', (checkId) => {
    expect(found, `${checkId} did not fire on a file that plants it`).toContain(checkId);
  });

  it('reports the line number, so the failure is actionable', () => {
    const result = runSourceChecks([VIOLATIONS_TSX]);
    for (const violation of result.violations) {
      expect(violation.line).toBeGreaterThan(0);
      expect(violation.text.length).toBeGreaterThan(0);
      expect(violation.help.length).toBeGreaterThan(40);
    }
  });
});

describe('the clean control', () => {
  it('produces no violation at all, including on every near-miss it contains', () => {
    expect(
      runSourceChecks([CLEAN_TSX]).violations.map((v) => `${v.checkId}: ${v.message}`),
      'the checker flagged correct markup — tabIndex={0}, tabIndex={-1}, aria-hidden on a ' +
        'decorative glyph, a div with role AND a key handler, alt="". A checker that flags ' +
        'everything is as useless as one that flags nothing.',
    ).toEqual([]);
  });

  it('produces no violation on the clean stylesheet', () => {
    expect(runSourceChecks([CLEAN_CSS]).violations).toEqual([]);
  });
});

describe('the stylesheets', () => {
  it('refuses outline:none inside :focus-visible', () => {
    expect(idsFrom([VIOLATIONS_CSS])).toContain('focus-visible-outline');
  });

  it('refuses words in a pseudo-element', () => {
    expect(idsFrom([VIOLATIONS_CSS])).toContain('verbatim-in-pseudo-element');
  });

  it('reports plain :focus as a NOTE, and the note does not fail the gate', () => {
    const result = runSourceChecks([NOTES_CSS]);
    expect(result.violations).toEqual([]);
    expect(result.notes.map((note) => note.checkId)).toEqual(['plain-focus-outline-removed']);
  });
});

describe('the MEMORY register — wrong only because of where it is', () => {
  const result = runSourceChecks([MEMORY_TSX]);

  it('refuses a person identified inside the walk', () => {
    const hit = result.violations.find((violation) => violation.checkId === 'signer-sub');
    expect(hit?.message).toContain('MEMORY register');
  });

  it('PERMITS the canvas there, so the boundary is a rule and not a ban', () => {
    expect(
      result.violations.filter((violation) => violation.checkId === 'no-canvas-outside-memory'),
      'MEMORY is the one register permitted to draw with a GPU. A checker that refused a canvas ' +
        'everywhere would refuse the product’s only dimensional surface and be "fixed" by ' +
        'deleting the rule.',
    ).toEqual([]);
  });

  it('would have refused the same person outside the MEMORY register only as a dimension', () => {
    const elsewhere = { ...MEMORY_TSX, path: 'src/features/gate/Elsewhere.tsx', inMemoryRegister: false };
    // `data-person` outside MEMORY is not this check's business; the attribution rule for
    // the dimensional surface is, and a check that fired everywhere would be turned off.
    expect(idsFrom([elsewhere])).not.toContain('signer-sub');
  });
});

describe('the whole planted run', () => {
  const files = [VIOLATIONS_TSX, VIOLATIONS_CSS, NOTES_CSS, CLEAN_TSX, CLEAN_CSS, MEMORY_TSX];

  it('reports exactly the expected set of checks — no more, no fewer', () => {
    expect(idsFrom(files)).toEqual([
      'access-key',
      'aria-hidden-interactive',
      'click-handler-on-non-interactive',
      'focus-visible-outline',
      'img-without-alt',
      'inner-html',
      'no-canvas-outside-memory',
      'positive-tabindex',
      'signer-sub',
      'verbatim-in-pseudo-element',
    ]);
  });

  it('counts the files it checked, so an empty run cannot look like a clean one', () => {
    expect(runSourceChecks(files).filesChecked).toBe(files.length);
  });
});

describe('the self-exemption', () => {
  it('is exactly one file, and that file is the checker itself', () => {
    // The module that defines the patterns necessarily contains them. The list is a
    // literal of length one; anything added would have to be defended here.
    expect(SELF_EXEMPT).toEqual(['src/a11y/source-checks.ts']);
  });

  it('is applied by path and reported in the result', () => {
    const self: SourceFile = {
      path: 'src/a11y/source-checks.ts',
      kind: 'ts',
      text: 'accessKey= dangerouslySetInnerHTML',
      inMemoryRegister: false,
    };
    const result = runSourceChecks([self]);
    expect(result.violations).toEqual([]);
    expect(result.filesExempt).toEqual(['src/a11y/source-checks.ts']);
    expect(result.filesChecked).toBe(0);
  });

  it('does not exempt a file that merely looks similar', () => {
    const impostor: SourceFile = {
      path: 'src/features/gate/source-checks.ts',
      kind: 'ts',
      text: 'const x = <button accessKey="s" />;',
      inMemoryRegister: false,
    };
    expect(idsFrom([impostor])).toContain('access-key');
  });
});

describe('the helpers', () => {
  it('classifies by extension and by directory', () => {
    expect(classify('src/features/gate/Panel.tsx', '').kind).toBe('tsx');
    expect(classify('src/design/tokens.css', '').kind).toBe('css');
    expect(classify('src/data/transport.ts', '').kind).toBe('ts');
    expect(classify('src\\features\\ancestry\\render3d\\Walk.tsx', '').inMemoryRegister).toBe(true);
    expect(classify('src/features/ancestry/ribbon/Ribbon.tsx', '').inMemoryRegister).toBe(false);
  });

  it('skips comment lines, and errs toward skipping', () => {
    expect(commentedOut('  // <img src="x">')).toBe(true);
    expect(commentedOut('   * accessKey=')).toBe(true);
    expect(commentedOut('const x = 1;')).toBe(false);
  });
});
