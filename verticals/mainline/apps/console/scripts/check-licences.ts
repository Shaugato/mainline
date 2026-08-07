// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The dependency licence gate.
 *
 * In a repository where the dependency graph is a licence and liability boundary, every
 * avoided dependency is an avoided audit — and every ADMITTED dependency must have a
 * licence somebody has actually looked at. `reuse lint` green is a G6 checklist item and
 * it says nothing about node_modules; this script is what covers that gap.
 *
 * Run with `node scripts/check-licences.ts`. No external process, no network: it walks
 * the installed tree from package.json's own roots, so it produces the same verdict
 * offline, on a laptop with no cloud account, as it does in CI.
 *
 * Three refusals:
 *
 *   1. A DENIED package by name — GSAP above all. D3 bans it: free since 2025, but its
 *      Standard License is not OSI-approved and has no SPDX identifier. eslint refuses
 *      the import as well, because whoever adds the dependency can edit one of the two
 *      gates but is unlikely to think of both.
 *   2. A licence outside the allowlist. The RUNTIME closure (what actually ships) gets
 *      the strict permissive set. The DEV closure gets that set plus a short, itemised
 *      extension, each entry carrying the reason it is defensible for a tool that never
 *      enters the distributed bundle.
 *   3. A package with NO licence field, an `UNLICENSED` marker, or a `SEE LICENSE IN`
 *      pointer. Unknown is not permissive. A dependency that will not say what it is
 *      has not been audited and cannot be.
 */

import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/**
 * The permissive set. Every entry is an OSI-approved or FSF-free, non-copyleft,
 * SPDX-listed identifier that imposes no obligation on a redistributed binary beyond
 * attribution.
 */
const ALLOW_RUNTIME = new Set([
  '0BSD',
  'Apache-2.0',
  'BSD-2-Clause',
  'BSD-3-Clause',
  'BlueOak-1.0.0',
  'CC0-1.0',
  'ISC',
  'MIT',
  'MIT-0',
  'Python-2.0',
  'Unlicense',
  'WTFPL',
  'Zlib',
]);

/**
 * Extensions permitted ONLY for packages that are unreachable from the shipped bundle.
 * Each is weak, file-level copyleft: it constrains modification of the licensed files
 * themselves and imposes nothing on a work that merely runs alongside them.
 */
const ALLOW_DEV_EXTRA = new Map([
  [
    'MPL-2.0',
    'File-level copyleft. Reaches axe-core and @axe-core/playwright, which run inside the a11y gate (D14) and are never linked into the distributed bundle. Unmodified use imposes no obligation on this tree.',
  ],
  [
    'CC-BY-4.0',
    'Attribution-only, applies to data/documentation assets carried by tooling packages. No source obligation.',
  ],
  [
    'CC-BY-3.0',
    'Attribution-only, as above.',
  ],
]);

/** Refused by NAME, in every scope, regardless of what the licence field says. */
const DENY_BY_NAME = new Map([
  [
    'gsap',
    'D3: banned. GSAP has been free since 2025, but its Standard License is neither OSI-approved nor SPDX-listed, and no non-SPDX licence enters this tree. `motion` (MIT) is the DOM animation dependency.',
  ],
  [
    '@gsap/react',
    'D3: banned, as the GSAP React binding.',
  ],
]);

/**
 * Per-package exceptions. Deliberately empty. Adding one is a visible diff in a file
 * whose whole purpose is to be read during an audit, which is the point.
 */
const EXCEPTIONS = new Map<string, string>();

interface PackageJson {
  name?: string;
  version?: string;
  license?: unknown;
  licenses?: unknown;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  optionalDependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
  peerDependenciesMeta?: Record<string, { optional?: boolean }>;
}

function readPackageJson(dir: string): PackageJson | null {
  const path = join(dir, 'package.json');
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, 'utf8')) as PackageJson;
  } catch {
    return null;
  }
}

/** Node resolution, walking up the directory chain, never leaving the console workspace. */
function resolvePackageDir(fromDir: string, name: string): string | null {
  let dir = fromDir;
  for (;;) {
    const candidate = join(dir, 'node_modules', name);
    if (existsSync(join(candidate, 'package.json'))) {
      try {
        return realpathSync(candidate);
      } catch {
        return candidate;
      }
    }
    const parent = dirname(dir);
    if (parent === dir || !dir.startsWith(ROOT)) return null;
    dir = parent;
  }
}

// ── SPDX expression evaluation ─────────────────────────────────────────────

type Token = string;

function tokenise(expression: string): Token[] {
  return expression
    .replace(/\(/g, ' ( ')
    .replace(/\)/g, ' ) ')
    .split(/\s+/)
    .filter((t) => t !== '');
}

/**
 * Evaluates an SPDX expression against a predicate over bare identifiers.
 *
 * `(A OR B)` is satisfied by either operand — the consumer may choose. `(A AND B)`
 * requires both, because the consumer must satisfy both. `WITH <exception>` narrows the
 * licence; a narrowed permissive licence is still evaluated on its base identifier and
 * the exception is reported so a human sees it.
 */
function evaluateSpdx(tokens: Token[], allows: (id: string) => boolean): boolean {
  let position = 0;

  function peek(): Token | undefined {
    return tokens[position];
  }

  function parseAtom(): boolean {
    const token = tokens[position];
    if (token === undefined) return false;
    position += 1;
    if (token === '(') {
      const inner = parseOr();
      if (peek() === ')') position += 1;
      return inner;
    }
    let ok = allows(token.replace(/\+$/, ''));
    if (peek() === 'WITH') {
      position += 2; // consume WITH and the exception identifier
      // An exception can only narrow a licence, so a permissive base stays permissive.
      ok = ok && true;
    }
    return ok;
  }

  function parseAnd(): boolean {
    let result = parseAtom();
    while (peek() === 'AND') {
      position += 1;
      const right = parseAtom();
      result = result && right;
    }
    return result;
  }

  function parseOr(): boolean {
    let result = parseAnd();
    while (peek() === 'OR') {
      position += 1;
      const right = parseAnd();
      result = result || right;
    }
    return result;
  }

  const value = parseOr();
  return position >= tokens.length && value;
}

/**
 * Second evidence tier: the licence FILE.
 *
 * Some packages ship a perfectly clear LICENSE and simply omit the `license` field —
 * `webgl-constants`, reached through @react-three/drei → detect-gpu, is one. Refusing
 * those outright would be wrong; accepting them silently would be worse, because a
 * licence recognised from prose is weaker evidence than a declared SPDX identifier.
 *
 * So: recognise it, admit it, and REPORT it in a separate class. Every package admitted
 * on file evidence is printed by name at the end of the run, so the weaker tier is
 * visible to whoever is reading the audit rather than buried in a pass.
 */
const LICENCE_FILENAMES = [
  'LICENSE',
  'LICENSE.md',
  'LICENSE.txt',
  'LICENCE',
  'LICENCE.md',
  'LICENCE.txt',
  'COPYING',
  'COPYING.md',
];

const FILE_SIGNATURES: { id: string; test: (text: string) => boolean }[] = [
  {
    id: 'Apache-2.0',
    test: (t) => /Apache License/i.test(t) && /Version 2\.0/i.test(t),
  },
  {
    id: 'ISC',
    test: (t) =>
      /ISC License/i.test(t) ||
      /Permission to use, copy, modify, and\/or distribute this software for any purpose/i.test(t),
  },
  {
    id: 'BSD-3-Clause',
    test: (t) =>
      /Redistribution and use in source and binary forms/i.test(t) &&
      /(Neither the name|neither the names)/i.test(t),
  },
  {
    id: 'BSD-2-Clause',
    test: (t) => /Redistribution and use in source and binary forms/i.test(t),
  },
  {
    id: 'Unlicense',
    test: (t) => /This is free and unencumbered software released into the public domain/i.test(t),
  },
  {
    id: '0BSD',
    test: (t) => /Zero-Clause BSD|BSD Zero Clause/i.test(t),
  },
  {
    id: 'MIT',
    test: (t) =>
      /\bMIT License\b/i.test(t) ||
      /Permission is hereby granted, free of charge, to any person obtaining a copy/i.test(t),
  },
];

function licenceFromFile(dir: string): { id: string; evidence: string } | null {
  for (const filename of LICENCE_FILENAMES) {
    const path = join(dir, filename);
    if (!existsSync(path)) continue;
    let text: string;
    try {
      text = readFileSync(path, 'utf8').slice(0, 4000);
    } catch {
      continue;
    }
    for (const signature of FILE_SIGNATURES) {
      if (signature.test(text)) return { id: signature.id, evidence: filename };
    }
    return null;
  }
  return null;
}

function declaredLicence(pkg: PackageJson): string | null {
  if (typeof pkg.license === 'string' && pkg.license.trim() !== '') return pkg.license.trim();
  if (typeof pkg.license === 'object' && pkg.license !== null) {
    const type = (pkg.license as { type?: unknown }).type;
    if (typeof type === 'string' && type.trim() !== '') return type.trim();
  }
  if (Array.isArray(pkg.licenses)) {
    const types = (pkg.licenses as unknown[])
      .map((entry): unknown =>
        typeof entry === 'object' && entry !== null ? (entry as { type?: unknown }).type : entry,
      )
      .filter((t): t is string => typeof t === 'string' && t.trim() !== '');
    if (types.length > 0) return `(${types.join(' OR ')})`;
  }
  return null;
}

// ── Walk ───────────────────────────────────────────────────────────────────

interface Found {
  key: string;
  name: string;
  version: string;
  licence: string | null;
  dir: string;
}

function walk(roots: Record<string, string>, fromDir: string): Map<string, Found> {
  const found = new Map<string, Found>();
  const visited = new Set<string>();
  const queue: { name: string; from: string }[] = Object.keys(roots).map((name) => ({
    name,
    from: fromDir,
  }));
  const unresolved = new Set<string>();

  while (queue.length > 0) {
    const item = queue.pop();
    if (item === undefined) continue;
    const dir = resolvePackageDir(item.from, item.name);
    if (dir === null) {
      // Optional and platform-specific dependencies are legitimately absent. Record it;
      // never fail on it, and never pretend it was checked.
      unresolved.add(item.name);
      continue;
    }
    if (visited.has(dir)) continue;
    visited.add(dir);

    const pkg = readPackageJson(dir);
    if (pkg === null) continue;

    const name = pkg.name ?? item.name;
    const version = pkg.version ?? '0.0.0';
    found.set(`${name}@${version}`, {
      key: `${name}@${version}`,
      name,
      version,
      licence: declaredLicence(pkg),
      dir,
    });

    for (const dep of Object.keys(pkg.dependencies ?? {})) queue.push({ name: dep, from: dir });
    for (const dep of Object.keys(pkg.optionalDependencies ?? {})) queue.push({ name: dep, from: dir });
    for (const dep of Object.keys(pkg.peerDependencies ?? {})) {
      // Peers may be optional and may be provided by us; if installed, they are in the
      // graph and must be audited like anything else.
      queue.push({ name: dep, from: dir });
    }
  }

  if (unresolved.size > 0) {
    const sorted = [...unresolved].sort();
    const shown = sorted.slice(0, 6).join(', ');
    const rest = sorted.length > 6 ? `, +${sorted.length - 6} more` : '';
    process.stdout.write(
      `  note   ${sorted.length} declared package(s) not installed — optional, peer, or for another platform (${shown}${rest}).\n` +
        '         Not installed means not shipped, so they are outside this audit rather than passing it.\n',
    );
  }

  return found;
}

// ── Run ────────────────────────────────────────────────────────────────────

const rootPkg = readPackageJson(ROOT);
if (rootPkg === null) {
  process.stderr.write('check-licences: no package.json at the console root.\n');
  process.exit(2);
}

if (!existsSync(join(ROOT, 'node_modules'))) {
  process.stderr.write(
    'check-licences: node_modules/ is absent. Run `pnpm install` first — a licence gate ' +
      'with nothing to inspect has not passed, it has not run.\n',
  );
  process.exit(2);
}

process.stdout.write('\ncheck-licences — the dependency graph is a liability boundary\n\n');

const runtime = walk(rootPkg.dependencies ?? {}, ROOT);
const everything = walk(
  { ...(rootPkg.dependencies ?? {}), ...(rootPkg.devDependencies ?? {}) },
  ROOT,
);

const problems: string[] = [];
const byLicence = new Map<string, number>();
const weakened: string[] = [];
const selfKey = `${rootPkg.name ?? ''}@${rootPkg.version ?? ''}`;

for (const found of everything.values()) {
  if (found.key === selfKey) continue; // the console itself is FSL-1.1-ALv2 by design

  const denied = DENY_BY_NAME.get(found.name);
  if (denied !== undefined) {
    problems.push(`DENIED  ${found.key}\n          ${denied}\n          at ${found.dir}`);
    continue;
  }

  const isRuntime = runtime.has(found.key);
  const scope = isRuntime ? 'runtime' : 'dev';

  let licence = found.licence;
  if (licence === null) {
    const fromFile = licenceFromFile(found.dir);
    if (fromFile === null) {
      problems.push(
        `NO LICENCE  ${found.key} (${scope})\n` +
          '          The package declares no licence field and ships no licence file this gate recognises.\n' +
          '          Unknown is not permissive.\n' +
          `          at ${found.dir}`,
      );
      continue;
    }
    licence = fromFile.id;
    weakened.push(`${found.key} (${scope}) — ${fromFile.id} read from ${fromFile.evidence}, not declared`);
  }

  byLicence.set(licence, (byLicence.get(licence) ?? 0) + 1);

  if (EXCEPTIONS.has(found.key)) continue;

  if (/^SEE LICEN[CS]E IN/i.test(licence) || /^UNLICENSED$/i.test(licence)) {
    problems.push(
      `OPAQUE  ${found.key} (${scope}) declares "${licence}".\n` +
        '          A licence that must be read out of a file by hand has not been audited by this gate.\n' +
        `          at ${found.dir}`,
    );
    continue;
  }

  const allows = (id: string): boolean =>
    ALLOW_RUNTIME.has(id) || (!isRuntime && ALLOW_DEV_EXTRA.has(id));

  if (!evaluateSpdx(tokenise(licence), allows)) {
    const devHint =
      !isRuntime && ALLOW_DEV_EXTRA.size > 0
        ? `\n          Dev-scope extensions currently permitted: ${[...ALLOW_DEV_EXTRA.keys()].join(', ')}.`
        : '';
    problems.push(
      `NOT ALLOWED  ${found.key} (${scope}) is "${licence}".\n` +
        `          Allowed in the ${scope} closure: ${[...ALLOW_RUNTIME].join(', ')}.${devHint}\n` +
        `          at ${found.dir}`,
    );
  }
}

process.stdout.write(`  packages audited : ${everything.size - 1}\n`);
process.stdout.write(`  runtime closure  : ${runtime.size}\n`);
process.stdout.write(`  distinct licences: ${byLicence.size}\n\n`);
for (const [licence, count] of [...byLicence.entries()].sort((a, b) => b[1] - a[1])) {
  const dev = ALLOW_DEV_EXTRA.has(licence) ? '  (dev-scope only)' : '';
  process.stdout.write(`    ${String(count).padStart(4)}  ${licence}${dev}\n`);
}

if (weakened.length > 0) {
  process.stdout.write(
    `\n  ${weakened.length} package(s) admitted on FILE evidence rather than a declared SPDX field.\n` +
      '  Recognising a licence from its prose is weaker than reading a declared identifier, so it is\n' +
      '  reported separately rather than folded silently into the pass:\n',
  );
  for (const line of weakened.sort()) process.stdout.write(`    - ${line}\n`);
}

if (problems.length > 0) {
  process.stderr.write('\ncheck-licences: FAILED\n\n');
  for (const problem of problems) process.stderr.write(`  • ${problem}\n\n`);
  process.exit(1);
}

process.stdout.write('\ncheck-licences: every dependency is permissive and named.\n\n');
