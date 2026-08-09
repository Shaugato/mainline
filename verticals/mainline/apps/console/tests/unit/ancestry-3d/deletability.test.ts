// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CUT — `docs/dimensionality-charter.md` §2 (C2) and §8.
 *
 * `BUILD_PLAN` §10.2 makes the 3D walk the scope ladder's FIRST cut. `docs/leads/ui.md`
 * §6 records that as the intended outcome if D-7 preflight is not green, not as a
 * failure. That is only true if nothing has been allowed to come to depend on it, and
 * "nothing depends on it" is a property of the import graph, so it is asserted over the
 * import graph.
 *
 * The rule, precisely:
 *
 *   • NO module outside `render3d/` may STATICALLY import anything inside it.
 *   • Exactly one module — `src/features/ancestry/AncestryScreen.tsx` — may DYNAMICALLY
 *     import it, inside an error boundary that falls back to the ribbon.
 *   • Modules inside `render3d/` may reach the register-neutral design package and the
 *     app shell, and no other feature directory — so the MEMORY register cannot become
 *     the place a fact lives.
 *
 * The middle rule is stated as "at most one", not "exactly one", on purpose:
 * `AncestryScreen.tsx` is another worker's file and may not have landed. A test that
 * demanded its existence would make this worker's suite red for somebody else's
 * sequencing, which is the one thing the cut-ladder item is not allowed to do.
 */

import { describe, expect, it } from 'vitest';

import { applicationSources, memoryCode, stripComments } from './_sources';

const MEMORY_DIR = '/src/features/ancestry/render3d/';
const LAZY_IMPORTER = '/src/features/ancestry/AncestryScreen.tsx';

/** Module specifiers pulled in by a STATIC import or re-export. */
function staticSpecifiers(code: string): string[] {
  const found: string[] = [];
  const fromClause = /(?:^|[\n;])\s*(?:import|export)\b[^;\n]*?\bfrom\s*['"]([^'"]+)['"]/g;
  const sideEffect = /(?:^|[\n;])\s*import\s*['"]([^'"]+)['"]/g;
  for (const match of code.matchAll(fromClause)) {
    if (match[1] !== undefined) found.push(match[1]);
  }
  for (const match of code.matchAll(sideEffect)) {
    if (match[1] !== undefined) found.push(match[1]);
  }
  return found;
}

/** Module specifiers reached by a DYNAMIC `import(...)`. */
function dynamicSpecifiers(code: string): string[] {
  const found: string[] = [];
  for (const match of code.matchAll(/\bimport\(\s*['"]([^'"]+)['"]\s*\)/g)) {
    if (match[1] !== undefined) found.push(match[1]);
  }
  return found;
}

describe('nothing outside the MEMORY register imports it', () => {
  const sources = Object.entries(applicationSources()).filter(
    ([path]) => !path.startsWith(MEMORY_DIR),
  );

  it('finds an application to walk in the first place', () => {
    expect(sources.length).toBeGreaterThanOrEqual(20);
  });

  it('has no static import of render3d anywhere in the application', () => {
    for (const [path, raw] of sources) {
      for (const specifier of staticSpecifiers(stripComments(raw))) {
        expect(
          specifier.includes('render3d'),
          `${path} statically imports ${specifier}. Deleting render3d/ would break the build, ` +
            'and the MEMORY-register libraries would be reachable from the evidentiary shell.',
        ).toBe(false);
      }
    }
  });

  it('permits at most one dynamic import, and only from the ancestry screen', () => {
    const importers: string[] = [];
    for (const [path, raw] of sources) {
      for (const specifier of dynamicSpecifiers(stripComments(raw))) {
        if (specifier.includes('render3d')) importers.push(path);
      }
    }
    for (const path of importers) {
      expect(
        path,
        'Only AncestryScreen.tsx may reach the MEMORY register, and only lazily.',
      ).toBe(LAZY_IMPORTER);
    }
    expect(new Set(importers).size).toBeLessThanOrEqual(1);
  });
});

describe('the MEMORY register does not reach sideways', () => {
  const sources = Object.entries(memoryCode());

  it('imports no other feature directory', () => {
    for (const [path, code] of sources) {
      for (const specifier of [...staticSpecifiers(code), ...dynamicSpecifiers(code)]) {
        if (!specifier.startsWith('.')) continue;
        const reachesAnotherFeature =
          specifier.includes('features/') ||
          /\.\.\/\.\.\/(gate|diff|disposition|custody|audit|silence|propagation|evidence)\b/.test(
            specifier,
          );
        expect(
          reachesAnotherFeature,
          `${path} imports ${specifier}. The walk renders the ancestry layout and nothing else; ` +
            'a fact that lived only here would be a fact the ribbon could not print.',
        ).toBe(false);
      }
    }
  });

  it('imports nothing from the ancestry surface’s own EVIDENCE modules', () => {
    // `../layout`, `../ribbon`, `../model` would all couple the cut to the ribbon.
    for (const [path, code] of sources) {
      for (const specifier of staticSpecifiers(code)) {
        expect(
          /^\.\.\/(layout|ribbon|exhibit|model|AncestryScreen|surface)/.test(specifier),
          `${path} imports ${specifier}; the layout contract is mirrored structurally instead.`,
        ).toBe(false);
      }
    }
  });

  it('reaches only react, three, @react-three, the design package, and itself', () => {
    const allowedBare = /^(react|react\/|react-dom|three|@react-three\/)/;
    for (const [path, code] of sources) {
      for (const specifier of staticSpecifiers(code)) {
        if (specifier.startsWith('.')) continue;
        expect(allowedBare.test(specifier), `${path} imports the bare module ${specifier}`).toBe(
          true,
        );
      }
    }
  });
});

describe('the budget already anticipates the cut', () => {
  const budgets = Object.values(
    import.meta.glob('/budgets.json', { query: '?raw', import: 'default', eager: true }),
  );

  it('declares the walk’s chunk NOT required, so its absence is legal', () => {
    const text = budgets[0];
    expect(typeof text).toBe('string');
    const parsed = JSON.parse(text as string) as {
      budgets: { id: string; required: boolean; root: string; absent_note?: string }[];
    };
    const walk = parsed.budgets.find((budget) => budget.id === 'memory-register-walk');
    expect(walk).toBeDefined();
    expect(walk?.required).toBe(false);
    expect(walk?.root).toBe('glob:src/features/ancestry/render3d/**');
    expect(walk?.absent_note).toBeTruthy();
  });
});

describe('the charter ships beside the code it governs', () => {
  const docs = import.meta.glob('/docs/dimensionality-charter.md', {
    query: '?raw',
    import: 'default',
    eager: true,
  });

  it('exists and states the four rules as testable sentences', () => {
    const text = Object.values(docs)[0];
    expect(typeof text).toBe('string');
    const charter = text as string;
    expect(charter).toContain('THE STILLNESS RULE');
    expect(charter).toContain('CAMERA ON RAILS, CONSTANT VELOCITY');
    expect(charter).toContain('NO EMISSIVE VOCABULARY');
    expect(charter).toContain('NO NAMED PERSON, EVER');
    expect(charter).toContain('rm -r verticals/mainline/apps/console/src/features/ancestry/render3d/');
  });
});
