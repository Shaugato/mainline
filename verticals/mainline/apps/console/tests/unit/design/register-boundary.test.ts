// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REGISTER BOUNDARY — the half a lint cannot provide (`docs/leads/ui.md` D9).
 *
 * `eslint.config.js` refuses a forbidden import where it is written. This walks the
 * whole source graph, from every register-owned file, following relative imports
 * transitively, and reports the chain when it arrives somewhere that register may not
 * see. It exists because the lint is defeated by one `eslint-disable` comment, by one
 * intermediate module, and by one edit to the config's own globs.
 *
 * ── PL-2, AND HOW THIS SUITE WAS MADE RED ────────────────────────────────────────
 *
 * The production assertion — "the real graph has no violations" — is green on the day it
 * is written and will stay green. That is precisely the condition under which a broken
 * walker is indistinguishable from a clean codebase.
 *
 * So `tests/unit/design/fixtures/planted/` contains four REAL `.ts` modules with real
 * imports of `motion/react`, `motion` and `three`, type-checked by `tsc` and resolved by
 * the same resolver the production walk uses. The test declares that directory an
 * EVIDENCE register and requires exactly those four violations, including the transitive
 * one — the case ESLint structurally cannot catch. Delete an import from a planted file
 * and this suite goes red.
 *
 * They sit under `tests/` rather than under `src/features/gate/` for one reason: that
 * directory belongs to another worker, and planting a file in it would corrupt their
 * tree. See `fixtures/planted/README.md`.
 */

import { describe, expect, it } from 'vitest';

import {
  extractImports,
  findComputedImports,
  findRegisterViolations,
  inDirectory,
  matchesPackageGlob,
  packagesReachableFrom,
  registerOf,
  resolveSpecifier,
  type SourceMap,
} from '../../../src/design/module-graph';
import {
  GPU_PACKAGES,
  MOTION_PACKAGES,
  NEUTRAL_DIRECTORIES,
  REGISTERS,
  REGISTER_LAW,
  registerBoundaryConfigs,
  type Register,
} from '../../../src/design/registers';
import { REGISTERS as APP_REGISTERS } from '../../../src/app/surfaces';
import { applicationSources, plantedSources } from './raw-sources';

/**
 * The real source graph, and the planted violations. Both arrive through
 * `raw-sources.ts`, which refuses a glob that matched fewer files than the checks need —
 * a walk over an empty graph finds no violation and reports the console clean.
 */
const realGraph: SourceMap = applicationSources();
const PLANTED = plantedSources();
const plantedGraph: SourceMap = new Map([...realGraph, ...PLANTED]);

const PLANTED_DIR = 'tests/unit/design/fixtures/planted';
const PLANTED_AS_EVIDENCE = new Map<string, Register>([[PLANTED_DIR, 'evidence']]);

describe('the walker sees the repository it thinks it sees', () => {
  it('found source files', () => {
    // A glob that silently matched nothing would make every assertion below vacuous —
    // the classic way a boundary test becomes decorative.
    expect(realGraph.size).toBeGreaterThan(10);
    expect([...realGraph.keys()]).toContain('/src/design/registers.ts');
    expect([...realGraph.keys()]).toContain('/src/app/App.tsx');
  });

  it('found the planted fixtures', () => {
    expect(PLANTED.size).toBe(5);
  });

  it('classifies files into the registers the law declares', () => {
    expect(registerOf('/src/features/gate/GateScreen.tsx')).toBe('evidence');
    expect(registerOf('/src/app/App.tsx')).toBe('evidence');
    expect(registerOf('/src/features/propagation/surface.tsx')).toBe('instrument');
    // MEMORY must win over the EVIDENCE flat match on the ancestry directory, or the one
    // dimensional surface in the console gets classified EVIDENCE and then failed for
    // importing three — a false refusal that would be "fixed" by widening the boundary.
    expect(registerOf('/src/features/ancestry/render3d/Walk.tsx')).toBe('memory');
    expect(registerOf('/src/features/ancestry/surface.tsx')).toBe('evidence');
    expect(registerOf('/src/features/ancestry/ribbon/Ribbon.tsx')).toBe('evidence');
    // The design package is register-NEUTRAL and must not be classified at all.
    expect(registerOf('/src/design/primitives/Counter.tsx')).toBeNull();
    expect(registerOf('/src/main.tsx')).toBeNull();
  });
});

describe('the real console', () => {
  it('has no register-boundary violation', () => {
    const violations = findRegisterViolations(realGraph);
    expect(
      violations.map((violation) => violation.message),
      'a register-owned module reaches a package its register may not see',
    ).toEqual([]);
  });

  /**
   * THE HOLE THAT WOULD BE INVISIBLE EVERYWHERE ELSE.
   *
   * `src/design/**` is register-neutral, so the walk above never starts there. Every
   * register imports these primitives — so a `motion` import inside `Counter.tsx` would
   * put `motion` into every EVIDENCE chunk in the console while every ESLint rule and
   * every assertion above stayed green.
   */
  it('keeps the design package free of both restricted groups', () => {
    const roots = [...realGraph.keys()].filter((path) =>
      NEUTRAL_DIRECTORIES.some((directory) => inDirectory(path, directory, false)),
    );
    expect(roots.length).toBeGreaterThan(5);

    const reachable = packagesReachableFrom(realGraph, roots);
    const forbidden = [...GPU_PACKAGES, ...MOTION_PACKAGES];
    const offending = [...reachable].filter((specifier) =>
      forbidden.some((pattern) => matchesPackageGlob(specifier, pattern)),
    );

    expect(
      offending,
      `src/design/ reaches ${offending.join(', ')}. Every register imports these primitives, so ` +
        'this would put a restricted package into every EVIDENCE chunk in the console while ' +
        'every lint rule stayed green. The design package animates with CSS transitions under ' +
        'motion.ts and imports no animation library — see registers.ts, NEUTRAL_DIRECTORIES.',
    ).toEqual([]);
  });

  it('contains no dynamic import the walker cannot follow', () => {
    const unfollowable: string[] = [];
    for (const [path, source] of realGraph) {
      if (registerOf(path) === null && !NEUTRAL_DIRECTORIES.some((d) => inDirectory(path, d, false))) {
        continue;
      }
      for (const argument of findComputedImports(source)) {
        unfollowable.push(`${path}: import(${argument})`);
      }
    }
    expect(
      unfollowable,
      'a dynamic import with a computed specifier is a hole in this walk. The day one is ' +
        'genuinely needed, this assertion fails and the boundary’s limit gets discussed rather ' +
        'than forgotten.',
    ).toEqual([]);
  });
});

describe('PL-2 — the planted violations (fixtures/planted/)', () => {
  const violations = findRegisterViolations(plantedGraph, {
    extraDirectories: PLANTED_AS_EVIDENCE,
  }).filter((violation) => violation.entry.startsWith(`/${PLANTED_DIR}/`));

  it('reports the direct `import { motion } from "motion/react"` named in done_when', () => {
    const hit = violations.find(
      (violation) =>
        violation.entry.endsWith('direct-motion.ts') && violation.specifier === 'motion/react',
    );
    expect(
      hit,
      'the walker did NOT catch a literal `import { motion } from "motion/react"` in a file it ' +
        'was told is an EVIDENCE surface. Every green assertion in this file is therefore ' +
        'meaningless.',
    ).toBeDefined();
    expect(hit?.chain).toHaveLength(1);
  });

  it('reports a direct GPU import', () => {
    const hit = violations.find(
      (violation) => violation.entry.endsWith('direct-three.ts') && violation.specifier === 'three',
    );
    expect(hit).toBeDefined();
  });

  it('reports a TRANSITIVE reach — the case ESLint structurally cannot catch', () => {
    const hit = violations.find((violation) => violation.entry.endsWith('transitive-entry.ts'));
    expect(hit, 'transitive-entry.ts imports nothing forbidden; it reaches motion one hop away').toBeDefined();
    expect(hit?.specifier).toBe('motion');
    expect(hit?.chain.length).toBe(2);
    expect(hit?.importer.endsWith('transitive-helper.ts')).toBe(true);
    expect(hit?.message).toContain('→');
  });

  it('reports NOTHING for the clean control', () => {
    const noise = violations.filter((violation) => violation.entry.endsWith('clean-surface.ts'));
    expect(
      noise,
      'the walker flagged a file that imports only React and a local module. A checker that ' +
        'flags everything is as useless as one that flags nothing.',
    ).toEqual([]);
  });

  it('reports exactly the four planted entries and no others', () => {
    const entries = [...new Set(violations.map((violation) => violation.entry))].sort();
    expect(entries).toEqual([
      `/${PLANTED_DIR}/direct-motion.ts`,
      `/${PLANTED_DIR}/direct-three.ts`,
      `/${PLANTED_DIR}/transitive-entry.ts`,
      `/${PLANTED_DIR}/transitive-helper.ts`,
    ]);
  });
});

/**
 * PL-2, IN ITS LITERAL FORM — the planted import inside a REAL evidence directory.
 *
 * The block above plants files in `tests/unit/design/fixtures/planted/` and tells the
 * walker to treat that directory as EVIDENCE via `extraDirectories`. That proves the
 * walker works, but it does NOT prove the production directory law is right: a typo in
 * `EVIDENCE_DIRECTORIES` would leave `src/features/gate/` classified as nothing, the walk
 * would never start there, and every assertion above would still be green.
 *
 * So these tests inject a module at a path inside a real EVIDENCE directory and pass NO
 * options at all — `registerOf()` alone decides. The injection is in memory because
 * `src/features/gate/` belongs to another worker and this suite may not write into their
 * tree; the walker reads text out of a `Map` and cannot tell the difference, and the
 * directory law under test is the shipped one.
 */
describe('PL-2 — the production law, with nothing overridden', () => {
  const GATE_STUB = '/src/features/gate/planted-stub.tsx';
  const RIBBON_STUB = '/src/features/ancestry/ribbon/planted-stub.tsx';
  const WALK_STUB = '/src/features/ancestry/render3d/planted-stub.tsx';

  const withStub = (path: string, source: string): SourceMap =>
    new Map([...realGraph, [path, source]]);

  it('refuses `import { motion } from "motion/react"` in the gate surface', () => {
    const violations = findRegisterViolations(
      withStub(GATE_STUB, "import { motion } from 'motion/react';\nexport const x = motion;\n"),
    );
    const hit = violations.find((violation) => violation.entry === GATE_STUB);
    expect(
      hit,
      'the shipped EVIDENCE directory list does not actually cover src/features/gate/. The ' +
        'planted-fixture tests above would stay green through exactly this mistake, because ' +
        'they name their own directory.',
    ).toBeDefined();
    expect(hit?.specifier).toBe('motion/react');
    expect(hit?.register).toBe('evidence');
  });

  it('refuses a GPU import in the ancestry ribbon, which is EVIDENCE, not MEMORY', () => {
    const violations = findRegisterViolations(
      withStub(RIBBON_STUB, "import { Scene } from 'three';\nexport const x = Scene;\n"),
    );
    expect(violations.find((violation) => violation.entry === RIBBON_STUB)).toBeDefined();
  });

  it('refuses a motion import reached one hop away from an evidence surface', () => {
    // ESLint cannot see this: the gate file imports a local helper, and the helper is in
    // a directory that is allowed to import motion. Only the graph walk catches it.
    const graph = new Map([
      ...realGraph,
      [GATE_STUB, "import { helper } from '../propagation/planted-helper';\nexport const x = helper;\n"],
      ['/src/features/propagation/planted-helper.tsx', "import { motion } from 'motion';\nexport const helper = motion;\n"],
    ]);
    const hit = findRegisterViolations(graph).find((violation) => violation.entry === GATE_STUB);
    expect(hit?.chain).toHaveLength(2);
    expect(hit?.specifier).toBe('motion');
  });

  it('PERMITS the same GPU import inside render3d/, so the boundary is a rule and not a ban', () => {
    const violations = findRegisterViolations(
      withStub(WALK_STUB, "import { Scene } from 'three';\nexport const x = Scene;\n"),
    );
    expect(
      violations.filter((violation) => violation.entry === WALK_STUB),
      'MEMORY is the one register permitted to import three. A checker that refuses it ' +
        'everywhere refuses the product’s only dimensional surface and would be “fixed” by ' +
        'deleting the rule.',
    ).toEqual([]);
  });
});

describe('the walker’s parts', () => {
  it('extracts every import form the console uses', () => {
    const source = [
      "import { a } from './a';",
      "import type { T } from './types';",
      "import b from 'pkg';",
      "import './side-effect.css';",
      "export { c } from './c';",
      "export * from './d';",
      "const lazy = () => import('./lazy');",
      "const cjs = require('legacy');",
    ].join('\n');
    const specifiers = extractImports(source).map((record) => record.specifier);
    expect(specifiers).toContain('./a');
    expect(specifiers).toContain('pkg');
    expect(specifiers).toContain('./side-effect.css');
    expect(specifiers).toContain('./c');
    expect(specifiers).toContain('./d');
    expect(specifiers).toContain('./lazy');
    expect(specifiers).toContain('legacy');
    // `import type` is erased and cannot put a package in a chunk. Reporting it would
    // train people to ignore the report.
    expect(specifiers).not.toContain('./types');
  });

  it('ignores imports inside comments', () => {
    const source = ["// import { motion } from 'motion/react';", "/* import 'three'; */"].join('\n');
    expect(extractImports(source)).toEqual([]);
  });

  it('resolves relative specifiers the way a bundler does', () => {
    expect(resolveSpecifier('/src/features/gate/panel.tsx', './bits')).toBe(
      '/src/features/gate/bits',
    );
    expect(resolveSpecifier('/src/features/gate/panel.tsx', '../../design/motion')).toBe(
      '/src/design/motion',
    );
    expect(resolveSpecifier('/src/features/gate/panel.tsx', '/src/design/motion')).toBe(
      '/src/design/motion',
    );
    expect(resolveSpecifier('/src/a.ts', 'motion/react')).toBeNull();
    // A `?raw` or `?worker` query must not defeat resolution.
    expect(resolveSpecifier('/src/a.ts', './b.css?raw')).toBe('/src/b.css');
  });

  it('matches package globs by segment, not by prefix', () => {
    expect(matchesPackageGlob('motion/react', 'motion/**')).toBe(true);
    expect(matchesPackageGlob('motion', 'motion')).toBe(true);
    expect(matchesPackageGlob('motion-dom/anything', 'motion-dom/**')).toBe(true);
    expect(matchesPackageGlob('@react-three/fiber', '@react-three/*')).toBe(true);
    expect(matchesPackageGlob('@react-three/fiber/native', '@react-three/*/**')).toBe(true);
    // The trap the ESLint `paths` form falls into: an exact-string entry named
    // `motion/*` refuses a module literally called `motion/*` and permits `motion/react`.
    expect(matchesPackageGlob('motion/react', 'motion')).toBe(false);
    expect(matchesPackageGlob('emotion', 'motion')).toBe(false);
    expect(matchesPackageGlob('three-mesh-bvh', 'three')).toBe(false);
  });

  it('honours the flat/recursive distinction that isolates render3d/', () => {
    expect(inDirectory('/src/features/ancestry/model.ts', 'src/features/ancestry', true)).toBe(true);
    expect(
      inDirectory('/src/features/ancestry/render3d/Walk.tsx', 'src/features/ancestry', true),
    ).toBe(false);
    expect(
      inDirectory('/src/features/ancestry/render3d/Walk.tsx', 'src/features/ancestry', false),
    ).toBe(true);
  });
});

describe('the ESLint fragment eslint.config.js spreads', () => {
  const configs = registerBoundaryConfigs();

  it('covers every register that forbids anything', () => {
    const restricted = REGISTER_LAW.filter((law) => law.forbidden.length > 0);
    expect(configs).toHaveLength(restricted.length);
    expect(configs.map((config) => config.name)).toEqual([
      'mainline/register-evidence',
      'mainline/register-instrument',
    ]);
  });

  it('expresses every denial as a glob GROUP, never an exact path name', () => {
    for (const config of configs) {
      const [level, options] = config.rules['no-restricted-imports'];
      expect(level).toBe('error');
      expect(options.patterns.length).toBeGreaterThan(0);
      for (const pattern of options.patterns) {
        expect(pattern.group.length).toBeGreaterThan(0);
        // A message that does not cite the rule is a message somebody deletes.
        expect(pattern.message.length).toBeGreaterThan(30);
      }
    }
  });

  it('refuses motion and GPU packages in EVIDENCE, and only GPU in INSTRUMENT', () => {
    const evidence = configs.find((config) => config.name === 'mainline/register-evidence');
    const instrument = configs.find((config) => config.name === 'mainline/register-instrument');
    const groups = (config: typeof evidence): string[] =>
      config === undefined ? [] : config.rules['no-restricted-imports'][1].patterns.flatMap((p) => [...p.group]);

    expect(groups(evidence)).toContain('motion/**');
    expect(groups(evidence)).toContain('@react-three/*');
    expect(groups(evidence)).toContain('**/render3d/**');
    expect(groups(instrument)).toContain('@react-three/*');
    expect(groups(instrument)).not.toContain('motion/**');
  });

  it('names file globs that actually match the register directories', () => {
    const evidence = configs.find((config) => config.name === 'mainline/register-evidence');
    expect(evidence?.files).toContain('src/features/gate/**/*.{ts,tsx}');
    // Non-recursive for the ancestry root, so render3d/ keeps its own register.
    expect(evidence?.files).toContain('src/features/ancestry/*.{ts,tsx}');
    expect(evidence?.files).not.toContain('src/features/ancestry/**/*.{ts,tsx}');
  });
});

describe('the register vocabulary is shared with the surface registry', () => {
  it('agrees with src/app/surfaces.ts', () => {
    // Two workers, two files, one vocabulary. A surface declaring a register the design
    // system has never heard of would render with no law applied and no error raised.
    expect([...REGISTERS]).toEqual([...APP_REGISTERS]);
  });

  it('declares a law for every register, with testable sentences', () => {
    expect(REGISTER_LAW.map((law) => law.register)).toEqual([...REGISTERS]);
    for (const law of REGISTER_LAW) {
      expect(law.laws.length, `${law.label} states no law`).toBeGreaterThan(3);
      for (const sentence of law.laws) {
        expect(sentence.trim().length).toBeGreaterThan(20);
      }
      expect(law.surfaces.length).toBeGreaterThan(0);
    }
  });

  it('gives MEMORY exactly one directory and one surface, and nothing else, ever', () => {
    const memory = REGISTER_LAW.find((law) => law.register === 'memory');
    expect(memory?.directories).toEqual(['src/features/ancestry/render3d']);
    expect(memory?.surfaces).toEqual(['the ancestry walk']);
  });
});
