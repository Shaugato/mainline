// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

/*
 * D9 — the three registers are an ENFORCED IMPORT BOUNDARY, not a style guide.
 *
 * docs/leads/ui.md §1.1 partitions every component into exactly one register and makes
 * the partition a dependency rule. This file is half of the enforcement; a unit test
 * over the built module graph (owned by the visual-language worker) is the other half,
 * because a lint can be disabled inline and a module-graph assertion cannot.
 *
 *   EVIDENCE   severe        no motion, no 3D, nothing a screenshot could not reproduce
 *   INSTRUMENT mechanical    motion permitted only where the transition IS the fact
 *   MEMORY     dimensional   the ancestry walk, and nothing else, ever
 *
 * A design law nobody can violate is worth more than a design law everybody agrees with.
 */

/*
 * Every denial below is expressed as a `patterns` GROUP rather than a `paths` NAME.
 *
 * That is not a style choice. `no-restricted-imports` `paths` entries are matched as
 * exact strings — `{ name: 'motion/*' }` refuses a module literally called `motion/*`
 * and silently permits `motion/react`, which is the import anybody would actually
 * write. A boundary that reads as enforced and is not is worse than no boundary, so
 * the subentry forms are covered by glob and the probe that caught this is recorded in
 * the README.
 */

/** Packages that draw with a GPU. Only the MEMORY register may see these. */
const THREE_D = ['three', 'three/**', '@react-three/*', '@react-three/*/**'];

/** Packages that move DOM. Forbidden in EVIDENCE, permitted in INSTRUMENT and MEMORY. */
const MOTION = [
  'motion',
  'motion/**',
  'motion-dom',
  'motion-dom/**',
  'motion-utils',
  'framer-motion',
  'framer-motion/**',
];

/**
 * D3 — GSAP is banned outright, in every register, forever.
 *
 * Not on technical grounds: GSAP has been free since 2025. Its Standard License is not
 * OSI-approved and has no SPDX identifier, and `reuse lint` green is a G6 checklist
 * item. No non-SPDX licence enters this tree. scripts/check-licences.ts refuses it at
 * the dependency layer as well — two independent refusals, because one of them can be
 * edited by the person adding the dependency.
 */
const BANNED_EVERYWHERE = [
  {
    group: ['gsap', 'gsap/**', '@gsap/*'],
    message: 'D3: GSAP is banned — its Standard License is not OSI-approved and has no SPDX identifier.',
  },
  {
    group: ['react-router', 'react-router-dom', 'react-router/**', '@tanstack/react-router'],
    message: 'D2: no router library. src/app/router.ts is the router — hash-based, typed, ~60 lines.',
  },
  {
    group: ['@tanstack/react-query', 'swr', 'axios', 'superagent', 'got'],
    message: 'D2: no data-fetching library. fetch() plus AbortController, in src/data/.',
  },
  {
    group: ['tailwindcss', 'tailwindcss/**', 'styled-components', '@emotion/*', 'bootstrap'],
    message: 'D2: no CSS framework. CSS Modules plus custom properties, tokens in src/design/.',
  },
  {
    group: ['@mui/*', 'antd', 'antd/**', '@chakra-ui/*', '@radix-ui/*', 'react-bootstrap'],
    message: 'D2: no component library. Six static surfaces do not need one, and every avoided dependency is an avoided audit.',
  },
  {
    group: ['moment', 'moment/**'],
    message: 'Use Intl.DateTimeFormat with an explicit UTC timeZone; evidentiary instants are UTC.',
  },
];

const restrict = (extra) => ({
  'no-restricted-imports': [
    'error',
    { patterns: [...BANNED_EVERYWHERE, ...extra.patterns] },
  ],
});

const deny = (group, message) => [{ group, message }];

const EVIDENCE_GLOBS = [
  'src/app/**/*.{ts,tsx}',
  'src/data/**/*.{ts,tsx}',
  'src/verify/**/*.{ts,tsx}',
  'src/features/gate/**/*.{ts,tsx}',
  'src/features/diff/**/*.{ts,tsx}',
  'src/features/disposition/**/*.{ts,tsx}',
  'src/features/custody/**/*.{ts,tsx}',
  'src/features/audit/**/*.{ts,tsx}',
  'src/features/silence/**/*.{ts,tsx}',
];

const INSTRUMENT_GLOBS = ['src/features/propagation/**/*.{ts,tsx}', 'src/design/**/*.{ts,tsx}'];

/** The ancestry ribbon, exhibit and layout are EVIDENCE; only render3d/ is MEMORY. */
const ANCESTRY_FLAT_GLOBS = [
  'src/features/ancestry/*.{ts,tsx}',
  'src/features/ancestry/layout/**/*.{ts,tsx}',
  'src/features/ancestry/ribbon/**/*.{ts,tsx}',
  'src/features/ancestry/exhibit/**/*.{ts,tsx}',
];

const MEMORY_GLOBS = ['src/features/ancestry/render3d/**/*.{ts,tsx}'];

/**
 * CONTROL OF WORK — the second entry point (docs/demo/operator-systems-plan.md R1).
 *
 * `operator.html` → `src/operator/**` is a DIFFERENT PRODUCT's user interface, built in
 * vanilla TypeScript with no framework, and its isolation from the console is an arithmetic
 * constraint rather than a taste: the console's entry chunk sits ~1.1 KB under the response
 * ceiling `static_site.py` serves objects at (docs/STATE-OF-THE-BUILD.md §12.9). One shared
 * import puts both entries in one closure and spends that headroom, and a 413 on the entry
 * chunk is the "NOT YET BOOTED" screen.
 *
 * So this register forbids MORE than any other: no framework, no animation library, no GPU
 * package (the no-GPU restriction that EVIDENCE and INSTRUMENT carry applies here too), and
 * no module from the console's own directories. `tests/unit/operator/shell/boundary.test.ts`
 * asserts the same law over the file text, because a lint is defeated by one inline
 * suppression and by one edit to this file.
 */
const OPERATOR_GLOBS = ['src/operator/**/*.{ts,tsx}'];

/** React and the DOM renderer. The operator surface has neither and must never gain one. */
const FRAMEWORK = ['react', 'react/**', 'react-dom', 'react-dom/**'];

/**
 * The console's own directories, in both spellings an author would reach for: the
 * root-absolute form Vite resolves (`/src/app/...`) and the relative climbs available from
 * `src/operator/**` and from one and two levels below it.
 */
const CONSOLE_PACKAGES = ['app', 'design', 'features', 'verify'];

const consoleReach = (packages) =>
  packages.flatMap((name) => [
    `/src/${name}`,
    `/src/${name}/**`,
    `**/src/${name}/**`,
    `../${name}`,
    `../${name}/**`,
    `../../${name}`,
    `../../${name}/**`,
    `../../../${name}`,
    `../../../${name}/**`,
  ]);

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'coverage/**',
      'node_modules/**',
      'test-results/**',
      'playwright-report/**',
      'fixtures/**/*.json',
      'src/data/types.generated.ts',
    ],
  },

  // ── Baseline ───────────────────────────────────────────────────────────────
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        // Both projects, explicitly. projectService cannot find tsconfig.node.json for
        // vite.config.ts / scripts/**, and routing those through an inferred project
        // would silently drop every type-aware rule on exactly the files that gate CI.
        project: ['./tsconfig.json', './tsconfig.node.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },

  // ── Application and unit tests ─────────────────────────────────────────────
  {
    files: ['src/**/*.{ts,tsx}', 'tests/unit/**/*.{ts,tsx}', 'tests/setup.ts'],
    languageOptions: {
      globals: { ...globals.browser },
      ecmaVersion: 2023,
      sourceType: 'module',
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // D5 — the console never composes an evidentiary claim. `console.log` is how a
      // claim gets composed by accident and then screenshotted.
      'no-console': ['error', { allow: ['error', 'warn'] }],
      'no-alert': 'error',
      'no-debugger': 'error',
      eqeqeq: ['error', 'always'],
      'prefer-const': 'error',
      'no-var': 'error',

      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
      '@typescript-eslint/no-unnecessary-condition': 'off',
      '@typescript-eslint/restrict-template-expressions': [
        'error',
        { allowNumber: true, allowBoolean: true },
      ],
      // A refusal payload arrives as `unknown` and is narrowed by a type guard. That is
      // the correct shape; `no-unsafe-*` would push authors toward `as` instead.
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
    },
  },

  // ── Register: EVIDENCE ─────────────────────────────────────────────────────
  {
    files: [...EVIDENCE_GLOBS, ...ANCESTRY_FLAT_GLOBS],
    rules: restrict({
      patterns: [
        ...deny(
          THREE_D,
          'EVIDENCE register: no GPU rendering. Only src/features/ancestry/render3d/** may import a 3D library (ui.md §1.1).',
        ),
        ...deny(
          MOTION,
          'EVIDENCE register: nothing moves that a screenshot could not reproduce (ui.md §1.1). If the transition IS the fact, the component belongs in the INSTRUMENT register.',
        ),
        {
          group: ['**/render3d/**'],
          message:
            'The MEMORY register is reachable only through a lazy import in the ancestry surface. Nothing else may depend on it — deleting render3d/ must leave a working ribbon (BUILD_PLAN §10.2 cut 1).',
        },
      ],
    }),
  },

  // ── Register: INSTRUMENT ───────────────────────────────────────────────────
  {
    files: INSTRUMENT_GLOBS,
    rules: restrict({
      patterns: deny(
        THREE_D,
        'INSTRUMENT register: motion is permitted, dimensionality is not (ui.md §1.1).',
      ),
    }),
  },

  // ── Register: MEMORY ───────────────────────────────────────────────────────
  {
    files: MEMORY_GLOBS,
    rules: restrict({ patterns: [] }),
  },

  // ── Register: OPERATOR (the CONTROL OF WORK entry) ─────────────────────────
  {
    files: OPERATOR_GLOBS,
    rules: restrict({
      patterns: [
        ...deny(
          THREE_D,
          'OPERATOR register: no GPU rendering. Only src/features/ancestry/render3d/** may import a 3D library (ui.md §1.1), and the operator entry may not import a heavy dependency of any kind — it ships under a 136 KB wire ceiling of its own (budgets.json, operator-surface).',
        ),
        ...deny(
          MOTION,
          'OPERATOR register: nothing on a permit screen moves that a screenshot could not reproduce, and no animation library enters this entry closure (operator-systems-plan.md R1).',
        ),
        ...deny(
          FRAMEWORK,
          'OPERATOR register: no React. src/operator/** is vanilla TypeScript so that operator.html shares no chunk with index.html — the console entry has ~1.1 KB of headroom against the response ceiling and a shared closure spends it (operator-systems-plan.md R1/R2).',
        ),
        ...deny(
          consoleReach(CONSOLE_PACKAGES),
          'OPERATOR register: this is a different product’s UI. Importing src/app, src/design, src/features or src/verify would weld the two entries into one chunk closure AND dress the operator screens in MAINLINE’s design system, which is the one thing the demonstration must not do (operator-systems-plan.md R1).',
        ),
        {
          // src/data is the console's transport and schema layer. ONE module in it is free:
          // types.generated.ts, imported `import type`, because a type erases to zero bytes
          // and is the same contract the kernel client answers to. The negations below carve
          // exactly that module out; everything else in the directory is refused outright.
          group: [
            ...consoleReach(['data']),
            '!**/data/types.generated',
            '!**/data/types.generated.ts',
          ],
          message:
            'OPERATOR register: src/data is the console’s transport and schema layer and belongs to the console’s chunk closure. The one permitted reach is `import type` from src/data/types.generated.ts.',
        },
        {
          group: ['**/data/types.generated', '**/data/types.generated.ts'],
          message:
            'OPERATOR register: src/data/types.generated.ts may be imported ONLY as `import type`. A value import of a generated module pulls it into the operator entry closure, which is measured against its own 136 KB ceiling (budgets.json, operator-surface).',
          allowTypeImports: true,
        },
      ],
    }),
  },

  // ── Tooling: Node, not a browser ───────────────────────────────────────────
  {
    files: ['scripts/**/*.ts', 'vite.config.ts', 'vitest.config.ts', 'playwright.config.ts'],
    languageOptions: {
      // projectService (set in the baseline) locates tsconfig.node.json for these files
      // on its own; naming the project explicitly here is both redundant and an error.
      globals: { ...globals.node },
    },
    rules: {
      // The gate scripts report to a terminal. That is their entire output surface.
      'no-console': 'off',
      '@typescript-eslint/no-unnecessary-condition': 'off',
      '@typescript-eslint/restrict-template-expressions': [
        'error',
        { allowNumber: true, allowBoolean: true },
      ],
    },
  },

  // ── Playwright specs ───────────────────────────────────────────────────────
  {
    files: ['tests/browser/**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.node, ...globals.browser },
    },
    rules: {
      'no-console': 'off',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/restrict-template-expressions': [
        'error',
        { allowNumber: true, allowBoolean: true },
      ],
    },
  },

  // ── This file ──────────────────────────────────────────────────────────────
  {
    files: ['eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
    ...tseslint.configs.disableTypeChecked,
  },
);
