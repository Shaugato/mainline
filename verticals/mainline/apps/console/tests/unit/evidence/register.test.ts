// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE BOUNDARY THIS DIRECTORY ENFORCES ON ITSELF.
 *
 * `src/design/registers.ts` holds the EVIDENCE directory list, and `src/features/evidence`
 * is not on it — that file belongs to the visual-language worker and this worker may not
 * edit it. The consequence is precise and worth stating rather than discovering: neither
 * the ESLint fragment nor `register-boundary.test.ts` currently covers this directory, so
 * a `motion` import here would be caught by nothing.
 *
 * Rather than leave the hole open until another worker closes it, this suite walks the
 * real module graph from every file in this directory using the SAME walker the design
 * package uses, and refuses any reach into a GPU or DOM-animation package. When
 * `EVIDENCE_DIRECTORIES` gains `src/features/evidence`, this becomes a second,
 * redundant refusal — which is the correct end state, not a duplication to delete.
 */

import { describe, expect, it } from 'vitest';

import { validateSurfaceModule } from '../../../src/app/surfaces';
import {
  matchesPackageGlob,
  packagesReachableFrom,
  type SourceMap,
} from '../../../src/design/module-graph';
import {
  EVIDENCE_DIRECTORIES,
  GPU_PACKAGES,
  MOTION_PACKAGES,
} from '../../../src/design/registers';
import * as surfaceModule from '../../../src/features/evidence/surface';

const DIRECTORY = '/src/features/evidence/';

function applicationSources(): SourceMap {
  const glob = import.meta.glob<string>('/src/**/*.{ts,tsx}', {
    query: '?raw',
    import: 'default',
    eager: true,
  });
  const map = new Map<string, string>();
  for (const [path, text] of Object.entries(glob)) map.set(path, text);
  if (map.size < 10) {
    throw new Error(
      `the source glob matched ${map.size} file(s). A walk over an empty graph finds no ` +
        'violation and reports the directory clean.',
    );
  }
  return map;
}

describe('the evidence surface stays inside the EVIDENCE register', () => {
  const graph = applicationSources();
  const roots = [...graph.keys()].filter((path) => path.startsWith(DIRECTORY));

  it('found this directory in the graph', () => {
    // Without this the assertion below walks from nothing and passes vacuously.
    expect(roots.length).toBeGreaterThanOrEqual(8);
    expect(roots).toContain('/src/features/evidence/surface.tsx');
    expect(roots).toContain('/src/features/evidence/EvidenceScreen.tsx');
  });

  it('reaches no GPU package and no DOM-animation package, transitively', () => {
    const reachable = packagesReachableFrom(graph, roots);
    const forbidden = [...GPU_PACKAGES, ...MOTION_PACKAGES];
    const offending = [...reachable].filter((specifier) =>
      forbidden.some((pattern) => matchesPackageGlob(specifier, pattern)),
    );
    expect(
      offending,
      `src/features/evidence reaches ${offending.join(', ')}. Nothing on an evidentiary screen ` +
        'may move in a way a screenshot cannot reproduce (docs/leads/ui.md §1.1).',
    ).toEqual([]);
  });

  it('reaches nothing under render3d/, the one deletable directory', () => {
    const reachable = packagesReachableFrom(graph, roots);
    expect([...reachable].filter((specifier) => specifier.includes('render3d'))).toEqual([]);
  });

  it('records that the shipped directory law does not yet name this directory', () => {
    // Not a failure — a fact, asserted so that the day visual-language adds the entry
    // this test goes red and somebody deletes the paragraph above rather than leaving a
    // stale warning in the tree.
    expect(
      EVIDENCE_DIRECTORIES.includes('src/features/evidence'),
      'src/design/registers.ts now lists src/features/evidence. The self-enforced boundary in ' +
        'this file is redundant with the shipped one — keep both, and delete the note in the ' +
        'header that says it is not yet covered.',
    ).toBe(false);
  });
});

describe('self-registration (D8)', () => {
  it('exports a descriptor the shell accepts, under the directory name', () => {
    const validation = validateSurfaceModule('evidence', surfaceModule);
    expect(validation.ok ? 'ok' : validation.reason).toBe('ok');
  });

  it('declares the EVIDENCE register and a rooted path matching the registry’s convention', () => {
    expect(surfaceModule.surface.register).toBe('evidence');
    // `buildRegistry` addresses an undeclared surface at `/<id>`; a descriptor that named
    // a different path would be reachable by no link in the console.
    expect(surfaceModule.surface.path).toBe('/evidence');
    expect(surfaceModule.surface.id).toBe('evidence');
    expect(surfaceModule.surface.milestone).toMatch(/^K[0-9]+$/);
  });
});
