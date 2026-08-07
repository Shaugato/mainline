// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * D13 — budgets are tests.
 *
 * "Sub-second on a mine-site laptop" is a number or it is marketing. This script reads
 * the Vite build manifest, walks the real static-import closure of each budgeted root,
 * gzips the actual emitted bytes, and exits non-zero when a threshold in budgets.json
 * is exceeded.
 *
 * Run with `node scripts/check-budgets.ts` (Node 24 strips the types; there is no
 * bundler in this path, which is why this file uses only erasable syntax).
 *
 * Two things it refuses that a naive byte-count would miss:
 *
 *   • A budget whose manifest is missing FAILS. A gate that cannot measure has not
 *     passed; it has not run.
 *   • A MEMORY-register library that has become statically reachable from the entry
 *     chunk FAILS, even if the total is under budget. That means the lazy boundary
 *     broke and every machine is now paying for a surface most of them never render.
 */

import { gzipSync } from 'node:zlib';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist');
const MANIFEST = join(DIST, '.vite', 'manifest.json');
const BUDGETS = join(ROOT, 'budgets.json');

interface ManifestChunk {
  file: string;
  name?: string;
  src?: string;
  isEntry?: boolean;
  isDynamicEntry?: boolean;
  imports?: string[];
  dynamicImports?: string[];
  css?: string[];
  assets?: string[];
}

type Manifest = Record<string, ManifestChunk>;

interface Budget {
  id: string;
  title: string;
  why: string;
  root: string;
  follow: 'static' | 'all';
  subtract?: string;
  max_gzip_bytes: number;
  max_gzip_human: string;
  required: boolean;
  absent_note?: string;
}

interface ForbiddenInEntry {
  match: string;
  why: string;
}

interface BudgetsFile {
  budgets: Budget[];
  forbidden_in_entry: ForbiddenInEntry[];
}

const problems: string[] = [];
const notes: string[] = [];

function die(message: string): never {
  process.stderr.write(`\ncheck-budgets: ${message}\n\n`);
  process.exit(2);
}

function readJson(path: string): unknown {
  if (!existsSync(path)) die(`${path} does not exist.`);
  return JSON.parse(readFileSync(path, 'utf8'));
}

function gzipBytes(relativeFile: string): number {
  const absolute = join(DIST, relativeFile);
  if (!existsSync(absolute)) {
    problems.push(`manifest names ${relativeFile}, which is not in dist/. The build is incoherent.`);
    return 0;
  }
  // level 9: the wire is served by a CDN that will do at least this well, and a budget
  // measured at a weaker setting flatters the number.
  return gzipSync(readFileSync(absolute), { level: 9 }).byteLength;
}

/** Turns `glob:src/features/ancestry/render3d/**` into a predicate over a manifest key. */
function globToTest(pattern: string): (key: string) => boolean {
  // `**` crosses directory separators, `*` does not. Split on the wider token first, so
  // that no sentinel character is ever injected into the pattern and every literal
  // segment is regex-escaped on its own.
  const source = pattern
    .split('**')
    .map((wide) =>
      wide
        .split('*')
        .map((literal) => literal.replace(/[.+^${}()|[\]\\?]/g, '\\$&'))
        .join('[^/]*'),
    )
    .join('.*');
  const re = new RegExp(`^${source}$`);
  return (key) => re.test(key);
}

function rootKeys(manifest: Manifest, root: string): string[] {
  if (root === 'entry') {
    return Object.keys(manifest).filter((key) => manifest[key]?.isEntry === true);
  }
  if (root.startsWith('glob:')) {
    const test = globToTest(root.slice('glob:'.length));
    return Object.keys(manifest).filter(test);
  }
  return Object.keys(manifest).filter((key) => key === root);
}

/** Transitive closure over `imports` (static) and, when asked, `dynamicImports` too. */
function closure(manifest: Manifest, seeds: string[], follow: 'static' | 'all'): Set<string> {
  const seen = new Set<string>();
  const queue = [...seeds];
  while (queue.length > 0) {
    const key = queue.pop();
    if (key === undefined || seen.has(key)) continue;
    const chunk = manifest[key];
    if (chunk === undefined) continue;
    seen.add(key);
    for (const next of chunk.imports ?? []) queue.push(next);
    if (follow === 'all') {
      for (const next of chunk.dynamicImports ?? []) queue.push(next);
    }
  }
  return seen;
}

function filesOf(manifest: Manifest, keys: Set<string>): Set<string> {
  const files = new Set<string>();
  for (const key of keys) {
    const chunk = manifest[key];
    if (chunk === undefined) continue;
    files.add(chunk.file);
    for (const css of chunk.css ?? []) files.add(css);
  }
  return files;
}

function human(bytes: number): string {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

/**
 * Every original module that ended up inside an emitted chunk.
 *
 * The Vite manifest lists only entry points, so it cannot answer "is three.js inside the
 * entry chunk" — three.js has no manifest key, it is bundled INTO one. The sourcemap can
 * answer it: `sources` is the complete list of modules Rollup folded into that chunk.
 *
 * Returns `null` when there is no sourcemap, which the caller treats as a FAILURE rather
 * than an absence of findings. A boundary check that cannot see the module graph has not
 * passed; it has not run.
 */
function modulesInChunk(relativeFile: string): string[] | null {
  if (!relativeFile.endsWith('.js')) return [];
  const mapPath = join(DIST, `${relativeFile}.map`);
  if (!existsSync(mapPath)) return null;
  try {
    const map = JSON.parse(readFileSync(mapPath, 'utf8')) as { sources?: unknown };
    return Array.isArray(map.sources)
      ? map.sources.filter((s): s is string => typeof s === 'string')
      : [];
  } catch {
    return null;
  }
}

// ── Run ────────────────────────────────────────────────────────────────────

if (!existsSync(DIST) || !statSync(DIST).isDirectory()) {
  die('dist/ does not exist. Run `vite build` before the budget gate.');
}
if (!existsSync(MANIFEST)) {
  die(
    'dist/.vite/manifest.json does not exist. `build.manifest` must be true in vite.config.ts — ' +
      'a budget gate with nothing to measure has not passed, it has not run.',
  );
}

const manifest = readJson(MANIFEST) as Manifest;
const config = readJson(BUDGETS) as BudgetsFile;

if (Object.keys(manifest).length === 0) {
  die('dist/.vite/manifest.json is empty.');
}

process.stdout.write('\ncheck-budgets — D13, budgets are tests\n');
process.stdout.write(`  manifest: ${Object.keys(manifest).length} chunks\n\n`);

for (const budget of config.budgets) {
  const seeds = rootKeys(manifest, budget.root);

  if (seeds.length === 0) {
    if (budget.required) {
      problems.push(
        `[${budget.id}] no chunk matched root "${budget.root}". ${budget.title} is required and could not be measured.`,
      );
    } else {
      notes.push(`[${budget.id}] absent. ${budget.absent_note ?? 'Not present in this build.'}`);
    }
    continue;
  }

  const included = closure(manifest, seeds, budget.follow);
  if (budget.subtract !== undefined) {
    for (const key of closure(manifest, rootKeys(manifest, budget.subtract), 'static')) {
      included.delete(key);
    }
  }

  const files = filesOf(manifest, included);
  let total = 0;
  for (const file of files) total += gzipBytes(file);

  const verdict = total <= budget.max_gzip_bytes ? 'PASS' : 'FAIL';
  const pct = ((total / budget.max_gzip_bytes) * 100).toFixed(0);
  process.stdout.write(
    `  ${verdict}  ${budget.id.padEnd(24)} ${human(total).padStart(10)} gzip  /  ${budget.max_gzip_human.padStart(7)}  (${pct}%, ${files.size} files)\n`,
  );

  if (verdict === 'FAIL') {
    problems.push(
      `[${budget.id}] ${human(total)} gzip exceeds the ${budget.max_gzip_human} budget.\n` +
        `      ${budget.why}\n` +
        `      Files in the closure: ${[...files].sort().join(', ')}`,
    );
  }
}

// ── The lazy boundary ──────────────────────────────────────────────────────

const entryClosure = closure(manifest, rootKeys(manifest, 'entry'), 'static');
const entryFiles = [...filesOf(manifest, entryClosure)];

const entryModules: string[] = [];
let mapsMissing = false;
for (const file of entryFiles) {
  const modules = modulesInChunk(file);
  if (modules === null) {
    mapsMissing = true;
    problems.push(
      `[lazy-boundary] ${file} has no sourcemap, so the modules inside it cannot be enumerated.\n` +
        '      `build.sourcemap` must stay true: without it this gate cannot tell a lazy 3D chunk\n' +
        '      from a 3D library welded into the evidentiary shell.',
    );
    continue;
  }
  entryModules.push(...modules);
}

if (!mapsMissing) {
  process.stdout.write(
    `  lazy boundary: ${entryModules.length} modules inside the entry closure\n`,
  );
}

for (const forbidden of config.forbidden_in_entry) {
  const needle = `/node_modules/${forbidden.match}/`;
  const hits = [...new Set(entryModules.filter((source) => source.includes(needle)))];
  if (hits.length > 0) {
    problems.push(
      `[lazy-boundary] "${forbidden.match}" is bundled INTO the evidentiary entry chunk.\n` +
        `      ${forbidden.why}\n` +
        `      First offending modules: ${hits.slice(0, 5).join(', ')}${hits.length > 5 ? ` (+${hits.length - 5} more)` : ''}`,
    );
  }
}

// ── Report ─────────────────────────────────────────────────────────────────

for (const note of notes) process.stdout.write(`  note   ${note}\n`);

if (problems.length > 0) {
  process.stderr.write('\ncheck-budgets: FAILED\n\n');
  for (const problem of problems) process.stderr.write(`  • ${problem}\n`);
  process.stderr.write('\n');
  process.exit(1);
}

process.stdout.write('\ncheck-budgets: all budgets held.\n\n');
