// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MODULE-GRAPH WALKER — the half of the register boundary a lint cannot provide.
 *
 * `eslint.config.js` refuses a forbidden import at the moment it is typed. It is not
 * sufficient, for three reasons:
 *
 *   1. `// eslint-disable-next-line no-restricted-imports` is one line, and the person
 *      most motivated to write it is the person violating the boundary.
 *   2. The rule is per-file. `src/features/gate/panel.tsx` importing a local helper
 *      that imports a shared util that imports `motion` is a clean lint run and a dead
 *      boundary — the EVIDENCE surface really does pull `motion` into its chunk.
 *   3. The config itself is editable, and a `files` glob that no longer matches a
 *      directory fails silently and forever.
 *
 * So this walker takes the whole source graph, starts from every EVIDENCE and every
 * INSTRUMENT file, follows relative imports transitively, and reports the chain when it
 * arrives at a package that register may not see. It is pure — a map of path → source
 * text in, a list of violations out — so the tests can run it against the real sources
 * AND against a deliberately poisoned fixture, which is what makes it a test that has
 * been red.
 *
 * ── SCOPE, STATED HONESTLY ───────────────────────────────────────────────────────
 *
 * This walks the SOURCE graph by regular expression, not Rollup's built module graph.
 * The difference matters and is recorded rather than glossed:
 *
 *   • It sees every static `import`/`export … from`, every dynamic `import()` with a
 *     literal specifier, and every `require()` with a literal specifier.
 *   • It CANNOT see a specifier computed at runtime (`import(someVariable)`). Nothing
 *     in this workspace does that, and `dynamic-specifier.test.ts`-style coverage is
 *     provided by asserting that no design or feature file contains `import(` followed
 *     by a non-literal — see `findComputedImports`.
 *   • It ignores type-only imports (`import type …`), because a type import is erased
 *     and cannot put a package in a chunk. A `motion` TYPE in an EVIDENCE file is
 *     pointless but not a boundary violation, and reporting it would train people to
 *     ignore the report.
 */

import {
  EVIDENCE_FLAT_DIRECTORIES,
  REGISTER_LAW,
  type Register,
  type RegisterLaw,
} from './registers';

/** Path → file text. Paths are root-relative and start with `/`, as Vite's glob keys do. */
export type SourceMap = ReadonlyMap<string, string>;

export interface ImportRecord {
  readonly specifier: string;
  /** `static` | `dynamic` | `require` — reported so a chain reads as what it is. */
  readonly kind: 'static' | 'dynamic' | 'require';
}

export interface RegisterViolation {
  /** The register-owned file the walk started from. */
  readonly entry: string;
  /** The register that file belongs to. */
  readonly register: Register;
  /** The file that contains the offending import. Equal to `entry` when it is direct. */
  readonly importer: string;
  /** The package that must not be reachable. */
  readonly specifier: string;
  /** entry → … → importer, so a transitive violation is legible without a debugger. */
  readonly chain: readonly string[];
  readonly message: string;
}

// ── Import extraction ────────────────────────────────────────────────────────────

/**
 * Removes comments and string-ish noise that would otherwise produce phantom imports.
 *
 * Line and block comments only. Template literals are left alone: a specifier cannot be
 * a template literal in a static import, and a dynamic `import(\`…\`)` is a computed
 * specifier, which `findComputedImports` reports separately rather than resolving.
 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

const STATIC_IMPORT = /(?:^|\n)\s*import\s+(?!type\s)([\s\S]*?)from\s*['"]([^'"]+)['"]/g;
const BARE_IMPORT = /(?:^|\n)\s*import\s*['"]([^'"]+)['"]/g;
const REEXPORT = /(?:^|\n)\s*export\s+(?!type\s)(?:\*|\{[\s\S]*?\})\s*(?:as\s+\w+\s*)?from\s*['"]([^'"]+)['"]/g;
const DYNAMIC_IMPORT = /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g;
const REQUIRE = /\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)/g;

/**
 * Every import specifier in a module, excluding type-only ones.
 *
 * `import { type Register } from './registers'` is INCLUDED: the inline-type form still
 * emits a runtime import of the module in `verbatimModuleSyntax` unless every binding is
 * a type — and rather than reimplement TypeScript's elision rules, the walker keeps the
 * edge. A false edge can only make the boundary stricter, never weaker, which is the
 * correct direction for an error in a safety gate.
 */
export function extractImports(source: string): readonly ImportRecord[] {
  const clean = stripComments(source);
  const out: ImportRecord[] = [];
  const push = (specifier: string | undefined, kind: ImportRecord['kind']): void => {
    if (specifier !== undefined && specifier !== '') out.push({ specifier, kind });
  };

  for (const pattern of [STATIC_IMPORT]) {
    pattern.lastIndex = 0;
    let match = pattern.exec(clean);
    while (match !== null) {
      push(match[2], 'static');
      match = pattern.exec(clean);
    }
  }
  for (const pattern of [BARE_IMPORT, REEXPORT]) {
    pattern.lastIndex = 0;
    let match = pattern.exec(clean);
    while (match !== null) {
      push(match[1], 'static');
      match = pattern.exec(clean);
    }
  }
  DYNAMIC_IMPORT.lastIndex = 0;
  let dynamic = DYNAMIC_IMPORT.exec(clean);
  while (dynamic !== null) {
    push(dynamic[1], 'dynamic');
    dynamic = DYNAMIC_IMPORT.exec(clean);
  }
  REQUIRE.lastIndex = 0;
  let required = REQUIRE.exec(clean);
  while (required !== null) {
    push(required[1], 'require');
    required = REQUIRE.exec(clean);
  }

  return out;
}

/**
 * `import(` calls whose specifier is not a string literal.
 *
 * The walker cannot follow these, so it must be able to say that none exist rather than
 * quietly stepping over them. `register-boundary.test.ts` asserts the list is empty for
 * every register-owned directory; the day somebody needs a computed dynamic import,
 * that assertion fails and the boundary's limit gets discussed instead of forgotten.
 */
export function findComputedImports(source: string): readonly string[] {
  const clean = stripComments(source);
  const out: string[] = [];
  const pattern = /\bimport\s*\(\s*([^'")][^)]*)\)/g;
  let match = pattern.exec(clean);
  while (match !== null) {
    const argument = match[1]?.trim();
    // `import.meta.glob(...)` is Vite's build-time expansion, not a runtime specifier:
    // it resolves to a literal set of modules at build time and is safe to skip.
    if (argument !== undefined && argument !== '' && !argument.startsWith('meta')) {
      out.push(argument);
    }
    match = pattern.exec(clean);
  }
  return out;
}

// ── Resolution ───────────────────────────────────────────────────────────────────

const EXTENSIONS = ['', '.ts', '.tsx', '.js', '.jsx', '/index.ts', '/index.tsx'];

function normalise(path: string): string {
  const parts: string[] = [];
  for (const segment of path.split('/')) {
    if (segment === '' || segment === '.') continue;
    if (segment === '..') parts.pop();
    else parts.push(segment);
  }
  return `/${parts.join('/')}`;
}

/**
 * Resolves a relative or root-absolute specifier against the source map.
 *
 * Returns `null` for a bare package specifier (which is checked against the forbidden
 * list instead) and for a relative specifier that resolves to nothing in the map — a
 * `.css` module, an asset, a `?raw` query. Those are not modules that can carry a
 * package into a chunk, so dropping them narrows the walk without weakening it.
 */
export function resolveSpecifier(fromPath: string, specifier: string): string | null {
  const withoutQuery = specifier.split('?')[0] ?? specifier;
  if (!withoutQuery.startsWith('.') && !withoutQuery.startsWith('/')) return null;

  const base = withoutQuery.startsWith('/')
    ? withoutQuery
    : `${fromPath.slice(0, fromPath.lastIndexOf('/'))}/${withoutQuery}`;

  return normalise(base);
}

function resolveInMap(sources: SourceMap, fromPath: string, specifier: string): string | null {
  const base = resolveSpecifier(fromPath, specifier);
  if (base === null) return null;
  for (const extension of EXTENSIONS) {
    const candidate = `${base}${extension}`;
    if (sources.has(candidate)) return candidate;
  }
  return null;
}

// ── Glob matching ────────────────────────────────────────────────────────────────

/**
 * Whether a root-relative path lies inside a directory from the register law.
 *
 * `flat` restricts the match to the directory's own files, which is how
 * `src/features/ancestry/*.tsx` stays EVIDENCE while `…/render3d/**` becomes MEMORY.
 */
export function inDirectory(path: string, directory: string, flat: boolean): boolean {
  const prefix = `/${directory.replace(/^\/+/, '')}/`;
  if (!path.startsWith(prefix)) return false;
  return flat ? !path.slice(prefix.length).includes('/') : true;
}

/**
 * The register that owns a file, or `null` for a file outside the register partition
 * (`src/design/**`, `src/main.tsx`).
 *
 * MEMORY is tested FIRST. `src/features/ancestry/render3d/scene.tsx` also lies under
 * `src/features/ancestry`, and asking the questions in the wrong order would classify
 * the one dimensional surface in the console as EVIDENCE and then fail it for importing
 * three.js — a false refusal that would be "fixed" by widening the boundary.
 */
export function registerOf(path: string): Register | null {
  const ordered: readonly RegisterLaw[] = [
    ...REGISTER_LAW.filter((law) => law.register === 'memory'),
    ...REGISTER_LAW.filter((law) => law.register !== 'memory'),
  ];
  for (const law of ordered) {
    for (const directory of law.directories) {
      if (inDirectory(path, directory, false)) return law.register;
    }
    for (const directory of law.flatDirectories) {
      if (inDirectory(path, directory, true)) return law.register;
    }
  }
  return null;
}

/** Glob match for a package specifier: `*` is one segment, `**` is any depth. */
export function matchesPackageGlob(specifier: string, pattern: string): boolean {
  const escaped = pattern
    .split('**')
    .map((part) =>
      part
        .split('*')
        .map((segment) => segment.replace(/[.+^${}()|[\]\\]/g, '\\$&'))
        .join('[^/]*'),
    )
    .join('.*');
  return new RegExp(`^${escaped}$`).test(specifier);
}

// ── The walk ─────────────────────────────────────────────────────────────────────

export interface WalkOptions {
  /**
   * Directories treated as belonging to a register even though the register law does
   * not list them. Used only by the fixture tests, which plant a violating file in a
   * directory this worker owns.
   */
  readonly extraDirectories?: ReadonlyMap<string, Register>;
}

function ownerOf(path: string, options: WalkOptions): Register | null {
  const extra = options.extraDirectories;
  if (extra !== undefined) {
    for (const [directory, register] of extra) {
      if (inDirectory(path, directory, false)) return register;
    }
  }
  return registerOf(path);
}

/**
 * Every forbidden package reachable from a register-owned file.
 *
 * Each entry point is walked independently, so the reported chain is the shortest path
 * from THAT surface to the offending import — breadth-first, because "gate imports
 * motion" and "gate imports a util that imports a util that imports motion" want
 * different fixes and a depth-first chain would often report the longer one.
 */
export function findRegisterViolations(
  sources: SourceMap,
  options: WalkOptions = {},
): readonly RegisterViolation[] {
  const violations: RegisterViolation[] = [];

  const forbiddenFor = (register: Register): readonly string[] => {
    const law = REGISTER_LAW.find((entry) => entry.register === register);
    return law?.forbidden ?? [];
  };

  for (const entry of [...sources.keys()].sort()) {
    const register = ownerOf(entry, options);
    if (register === null) continue;
    const forbidden = forbiddenFor(register);
    if (forbidden.length === 0) continue;

    const seen = new Set<string>([entry]);
    const queue: { path: string; chain: readonly string[] }[] = [{ path: entry, chain: [entry] }];

    while (queue.length > 0) {
      const current = queue.shift();
      if (current === undefined) break;
      const source = sources.get(current.path);
      if (source === undefined) continue;

      for (const record of extractImports(source)) {
        const resolved = resolveInMap(sources, current.path, record.specifier);
        if (resolved !== null) {
          if (!seen.has(resolved)) {
            seen.add(resolved);
            queue.push({ path: resolved, chain: [...current.chain, resolved] });
          }
          continue;
        }
        // Not a local module: a bare package specifier, or an asset. Only the former
        // can be forbidden.
        const hit = forbidden.find((pattern) => matchesPackageGlob(record.specifier, pattern));
        if (hit === undefined) continue;

        violations.push({
          entry,
          register,
          importer: current.path,
          specifier: record.specifier,
          chain: current.chain,
          message:
            current.chain.length === 1
              ? `${register.toUpperCase()} surface ${entry} imports "${record.specifier}" directly.`
              : `${register.toUpperCase()} surface ${entry} reaches "${record.specifier}" through ` +
                `${current.chain.join(' → ')} → "${record.specifier}".`,
        });
      }
    }
  }

  return violations;
}

/**
 * Packages reachable from `src/design/**`.
 *
 * The design package is register-NEUTRAL, so the walk above never starts there — and
 * that is exactly the hole a careless day would fall into. Every register imports these
 * primitives, so a `motion` import inside `Counter.tsx` would put `motion` in every
 * EVIDENCE chunk in the console while every ESLint rule and every walk above stayed
 * green. This function is how `register-boundary.test.ts` closes it: the design package
 * must reach NEITHER restricted group, from any file, at any depth.
 */
export function packagesReachableFrom(
  sources: SourceMap,
  roots: readonly string[],
): ReadonlySet<string> {
  const packages = new Set<string>();
  const seen = new Set<string>(roots);
  const queue = [...roots];

  while (queue.length > 0) {
    const path = queue.shift();
    if (path === undefined) break;
    const source = sources.get(path);
    if (source === undefined) continue;
    for (const record of extractImports(source)) {
      const resolved = resolveInMap(sources, path, record.specifier);
      if (resolved === null) {
        if (!record.specifier.startsWith('.') && !record.specifier.startsWith('/')) {
          packages.add(record.specifier);
        }
        continue;
      }
      if (!seen.has(resolved)) {
        seen.add(resolved);
        queue.push(resolved);
      }
    }
  }
  return packages;
}

/** The flat-directory list, re-exported so tests can assert the split is honoured. */
export const ANCESTRY_FLAT_DIRECTORIES = EVIDENCE_FLAT_DIRECTORIES;
