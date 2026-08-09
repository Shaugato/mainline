// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REGISTER BOUNDARY FOR THIS WORKER'S TWO DIRECTORIES.
 *
 * `src/features/silence` is an EVIDENCE directory in `src/design/registers.ts`, so the
 * domain-wide walk in `tests/unit/design/register-boundary.test.ts` already refuses a
 * `motion` or `@react-three/*` import there.
 *
 * `src/features/propagation` is an INSTRUMENT directory in that same file, and INSTRUMENT
 * PERMITS DOM animation. So the domain-wide walk would stay green if this surface imported
 * `motion` tomorrow — and this surface's brief says it may not. That gap is the entire
 * reason this file exists.
 *
 * ── WHY THE GAP IS CLOSED HERE AND NOT BY EDITING registers.ts ───────────────────
 *
 * `src/design/registers.ts` belongs to the visual-language worker, and moving
 * `src/features/propagation` from `INSTRUMENT_DIRECTORIES` to `EVIDENCE_DIRECTORIES` would
 * break two of their existing assertions — one that classifies this directory INSTRUMENT,
 * and one that uses it as the example of a directory that IS allowed to import motion.
 * Editing another worker's tree to satisfy this brief would corrupt the build; asserting
 * the same property from inside this worker's own tree does not. Recorded as a
 * cross-domain note.
 *
 * ── THE WALK IS TRANSITIVE, WHICH IS THE POINT ───────────────────────────────────
 *
 * ESLint refuses a forbidden import where it is written. It cannot see a forbidden package
 * reached through two local modules, and it is defeated by one inline suppression. This
 * walks the real module graph from every file in both directories, following relative
 * imports, and reports the chain.
 *
 * ── PL-2: HOW THIS FILE WAS MADE TO FAIL ─────────────────────────────────────────
 *
 * "The real graph has no violation" is green on the day it is written and stays green,
 * which is exactly the condition under which a broken walker is indistinguishable from a
 * clean codebase. So the last block injects a module at a path INSIDE each real directory
 * — in memory, because writing a planted file into the shipped tree is not something a
 * test may do — and requires the walk to catch it, both directly and one hop away. Delete
 * the transitive branch of the walker and this suite goes red.
 */

import { describe, expect, it } from 'vitest';

import {
  extractImports,
  inDirectory,
  matchesPackageGlob,
  packagesReachableFrom,
  type SourceMap,
} from '../../../src/design/module-graph';
import { GPU_PACKAGES, MOTION_PACKAGES } from '../../../src/design/registers';

/** The two directories this worker owns, as they appear in the module graph. */
const OWNED = ['src/features/propagation', 'src/features/silence'] as const;

/** Everything EVIDENCE forbids. INSTRUMENT forbids only the first group. */
const FORBIDDEN: readonly string[] = [...GPU_PACKAGES, ...MOTION_PACKAGES];

const RAW = import.meta.glob<string>('/src/**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function applicationSources(): SourceMap {
  const entries = Object.entries(RAW);
  if (entries.length < 10) {
    throw new Error(
      `tests/unit/propagation/register.test.ts: the source glob matched ${entries.length} file(s). ` +
        'A walk over an empty graph finds no violation and reports the console clean.',
    );
  }
  const map = new Map<string, string>();
  for (const [path, text] of entries) {
    if (typeof text !== 'string') {
      throw new Error(`${path} came back as ${typeof text} rather than text.`);
    }
    map.set(path, text);
  }
  return map;
}

const GRAPH = applicationSources();

function filesIn(graph: SourceMap, directory: string): readonly string[] {
  return [...graph.keys()].filter((path) => inDirectory(path, directory, false));
}

function forbiddenReachableFrom(graph: SourceMap, roots: readonly string[]): readonly string[] {
  const reachable = packagesReachableFrom(graph, roots);
  return [...reachable].filter((specifier) =>
    FORBIDDEN.some((pattern) => matchesPackageGlob(specifier, pattern)),
  );
}

describe('the walker sees the directories it thinks it sees', () => {
  it('found both owned directories, with real files in them', () => {
    for (const directory of OWNED) {
      const files = filesIn(GRAPH, directory);
      expect(files.length, `${directory} matched no source files`).toBeGreaterThan(3);
    }
  });

  it('found the two surface modules', () => {
    expect([...GRAPH.keys()]).toContain('/src/features/propagation/surface.tsx');
    expect([...GRAPH.keys()]).toContain('/src/features/silence/surface.tsx');
  });
});

describe('neither directory imports motion or a GPU package', () => {
  for (const directory of OWNED) {
    it(`${directory} reaches neither group, directly or transitively`, () => {
      const roots = filesIn(GRAPH, directory);
      const offending = forbiddenReachableFrom(GRAPH, roots);
      expect(
        offending,
        `${directory} reaches ${offending.join(', ')}. Both surfaces are held to the EVIDENCE ` +
          'register: nothing on them moves that a screenshot could not reproduce. If a ' +
          'transition really is the fact being reported, the component belongs in the ' +
          'INSTRUMENT register and this assertion should be changed deliberately, not ' +
          'discovered by a reviewer.',
      ).toEqual([]);
    });
  }

  it('names no render3d module either — the MEMORY register is reachable from one place', () => {
    const roots = OWNED.flatMap((directory) => filesIn(GRAPH, directory));
    const reaching: string[] = [];
    for (const path of roots) {
      const source = GRAPH.get(path) ?? '';
      for (const record of extractImports(source)) {
        if (record.specifier.includes('render3d')) reaching.push(`${path}: ${record.specifier}`);
      }
    }
    expect(reaching).toEqual([]);
  });
});

describe('both surfaces declare the EVIDENCE register on the tree they render', () => {
  it('every surface root wraps its screen in a RegisterFrame register="evidence"', () => {
    for (const path of [
      '/src/features/propagation/PropagationScreen.tsx',
      '/src/features/silence/SilenceScreen.tsx',
    ]) {
      const source = GRAPH.get(path);
      expect(source, `${path} is missing from the graph`).toBeDefined();
      expect(source ?? '').toContain('RegisterFrame register="evidence"');
    }
  });

  it('the surface descriptors declare `evidence`', () => {
    for (const path of [
      '/src/features/propagation/surface.tsx',
      '/src/features/silence/surface.tsx',
    ]) {
      expect(GRAPH.get(path) ?? '').toContain("register: 'evidence'");
    }
  });
});

describe('PL-2 — the walk catches a planted import in each real directory', () => {
  const withStub = (path: string, source: string): SourceMap => new Map([...GRAPH, [path, source]]);

  for (const directory of OWNED) {
    it(`refuses a direct \`motion/react\` import in ${directory}`, () => {
      const stub = `/${directory}/planted-stub.tsx`;
      const graph = withStub(stub, "import { motion } from 'motion/react';\nexport const x = motion;\n");
      const offending = forbiddenReachableFrom(graph, [stub]);
      expect(
        offending,
        'the walker did NOT catch a literal motion import in a file inside the directory it was ' +
          'told to check. Every green assertion above is therefore meaningless.',
      ).toContain('motion/react');
    });

    it(`refuses a GPU import in ${directory}`, () => {
      const stub = `/${directory}/planted-gpu.tsx`;
      const graph = withStub(stub, "import { Scene } from 'three';\nexport const x = Scene;\n");
      expect(forbiddenReachableFrom(graph, [stub])).toContain('three');
    });

    it(`refuses motion reached ONE HOP away from ${directory} — the case ESLint cannot see`, () => {
      const entry = `/${directory}/planted-entry.tsx`;
      const helper = `/${directory}/planted-helper.tsx`;
      const graph = new Map([
        ...GRAPH,
        [entry, "import { helper } from './planted-helper';\nexport const x = helper;\n"],
        [helper, "import { motion } from 'motion';\nexport const helper = motion;\n"],
      ]);
      expect(forbiddenReachableFrom(graph, [entry])).toContain('motion');
    });
  }

  it('reports NOTHING for a clean control', () => {
    const stub = '/src/features/silence/planted-clean.tsx';
    const graph = withStub(
      stub,
      "import { useMemo } from 'react';\nimport { PER_LIMIT_SENTENCE } from './model';\nexport const x = [useMemo, PER_LIMIT_SENTENCE];\n",
    );
    expect(forbiddenReachableFrom(graph, [stub])).toEqual([]);
  });
});
