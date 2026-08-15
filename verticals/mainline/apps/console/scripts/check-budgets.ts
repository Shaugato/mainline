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
 *
 * ── TWO MEASURES, AND THE SECOND ONE IS THE ONE WITH TEETH (added 2026-08-16) ────────
 *
 * `measure: "closure_total"` (the default, and what every budget here did until today)
 * SUMS the gzipped closure. That answers "how much does this screen cost to paint",
 * which is what a performance budget is for.
 *
 * `measure: "largest_object"` — which the required `wire_ceiling` gate uses — answers a
 * different question and it is the one that can take the demo dark: **how big is the
 * biggest SINGLE object this origin has to put on the wire.** `static_site.py` refuses any one response body over
 * `DEFAULT_MAX_RESPONSE_BYTES` (136 * 1024 = 139,264) with a 413, and that bound is per
 * object, not per closure. A sum can therefore sit comfortably inside its threshold while
 * one chunk inside it is a few hundred bytes from a total outage — measured on
 * 2026-08-16, `evidentiary-shell` reported 63 % of its 220 KB budget in the same run
 * where its entry chunk measured 1,332 B under the wire ceiling.
 *
 * When the entry chunk crosses, the origin answers 413 to its own entry JavaScript for
 * every browser: `GET /` still returns a 200 shell, the shell's only module returns a JSON
 * problem document, and the reader gets a BLANK PAGE. The fix is a smaller or split entry
 * chunk — a lazy route, or a second HTML entry as `operator.html` already is. It is never
 * a larger ceiling and never a larger number in `budgets.json`; both bounds are frozen by
 * ruling R3 of `docs/demo/proof-and-polish-plan.md`, and
 * `verticals/mainline/apps/demo-api/tests/test_static_site.py` asserts that the wire
 * budget below still equals `DEFAULT_MAX_RESPONSE_BYTES - _MINIMUM_HEADROOM_BYTES`, so
 * loosening one of the two files is red in the other.
 *
 * ── A BAN THAT CANNOT SEE ITS SUBJECT HAS NOT PASSED EITHER ─────────────────────────
 *
 * `forbidden_in_entry` rows now carry an optional `scope` (`node_modules`, the default, or
 * `source`) and an optional `in` (which entry root the ban applies to, default `entry` =
 * every `isEntry` chunk). `source` is what lets a ban name a directory of ours —
 * `src/operator/` must never be statically reachable from `index.html` — where the old
 * needle could only name a package. If an `in` root matches no chunk, that is a FAILURE
 * and not a silent pass: an entry that was renamed takes its bans with it.
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
  /** `closure_total` (default) sums the closure; `largest_object` takes its widest file. */
  measure?: 'closure_total' | 'largest_object';
  max_gzip_bytes: number;
  max_gzip_human: string;
  required: boolean;
  absent_note?: string;
}

interface ForbiddenInEntry {
  match: string;
  why: string;
  /** `node_modules` (default) matches a package; `source` matches a path of ours. */
  scope?: 'node_modules' | 'source';
  /** Which root's static closure the ban applies to. Default `entry` = every entry. */
  in?: string;
}

interface BudgetsFile {
  /** The per-object bound the ORIGIN refuses at. Required; its absence is a failure. */
  wire_ceiling?: Budget;
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

// The wire ceiling runs FIRST and its absence is a failure, not a silent skip. It is the
// only gate here whose breach is an outage rather than a slow page, so it may not be
// disabled by deleting a key — a gate that can be removed by removing it is not a gate.
if (config.wire_ceiling === undefined || typeof config.wire_ceiling.max_gzip_bytes !== 'number') {
  problems.push(
    '[wire-ceiling] budgets.json declares no `wire_ceiling` with a numeric max_gzip_bytes, so\n' +
      '      NOTHING in this run measures the widest SINGLE object the origin has to serve. Every\n' +
      "      other budget here is a SUM over a closure, and this origin's 413 is per object: a sum\n" +
      '      can pass at 63% while one chunk inside it is a few hundred bytes from a blank page.',
  );
}

const gates = config.wire_ceiling === undefined
  ? config.budgets
  : [config.wire_ceiling, ...config.budgets];

for (const budget of gates) {
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
  let widestFile = '';
  let widestBytes = 0;
  for (const file of files) {
    const bytes = gzipBytes(file);
    total += bytes;
    if (bytes > widestBytes) {
      widestBytes = bytes;
      widestFile = file;
    }
  }

  const perObject = (budget.measure ?? 'closure_total') === 'largest_object';
  const measured = perObject ? widestBytes : total;

  const verdict = measured <= budget.max_gzip_bytes ? 'PASS' : 'FAIL';
  const pct = ((measured / budget.max_gzip_bytes) * 100).toFixed(0);
  // The margin is printed on every run, PASS included: at 0.2 % of the wire ceiling the
  // interesting number is not "did it pass" but "by how much", and a reader who only ever
  // sees a verdict cannot tell 300 bytes of room from 30,000.
  const margin = budget.max_gzip_bytes - measured;
  process.stdout.write(
    `  ${verdict}  ${budget.id.padEnd(24)} ${human(measured).padStart(10)} gzip  /  ${budget.max_gzip_human.padStart(7)}  (${pct}%, ${margin} B left, ` +
      `${perObject ? `widest of ${files.size}: ${widestFile}` : `${files.size} files`})\n`,
  );

  if (verdict === 'FAIL') {
    problems.push(
      perObject
        ? `[${budget.id}] ${widestFile} is ${measured} B gzipped — ${measured - budget.max_gzip_bytes} B OVER the ` +
            `${budget.max_gzip_bytes} B wire budget (${budget.max_gzip_human}).\n` +
            `      ${budget.why}\n` +
            `      Make THAT CHUNK smaller. Do not raise this number, and do not raise ` +
            `DEFAULT_MAX_RESPONSE_BYTES: move what grew behind a lazy import, or give it its own HTML entry.`
        : `[${budget.id}] ${human(total)} gzip exceeds the ${budget.max_gzip_human} budget.\n` +
            `      ${budget.why}\n` +
            `      Files in the closure: ${[...files].sort().join(', ')}`,
    );
  }
}

// ── The lazy boundary ──────────────────────────────────────────────────────

const reportedMissingMaps = new Set<string>();
const scanned = new Map<string, string[]>();

/** Every original module inside the static closure of `root`. Missing maps are a FAILURE. */
function modulesReachableFrom(root: string): string[] {
  const cached = scanned.get(root);
  if (cached !== undefined) return cached;

  const seeds = rootKeys(manifest, root);
  if (seeds.length === 0) {
    // A ban whose subject is not in the build has not been satisfied; it has not run.
    // `operator.html` being renamed must take its bans down loudly, not silently.
    problems.push(
      `[lazy-boundary] no chunk matched the root "${root}", so every forbidden_in_entry row\n` +
        '      scoped to it was NOT checked. Fix the root name, or delete the rows that name it —\n' +
        '      a boundary check that cannot find its subject is not a boundary check.',
    );
  }

  const modules: string[] = [];
  for (const file of filesOf(manifest, closure(manifest, seeds, 'static'))) {
    const inChunk = modulesInChunk(file);
    if (inChunk === null) {
      if (!reportedMissingMaps.has(file)) {
        reportedMissingMaps.add(file);
        problems.push(
          `[lazy-boundary] ${file} has no sourcemap, so the modules inside it cannot be enumerated.\n` +
            '      `build.sourcemap` must stay true: without it this gate cannot tell a lazy 3D chunk\n' +
            '      from a 3D library welded into the evidentiary shell.',
        );
      }
      continue;
    }
    modules.push(...inChunk);
  }
  scanned.set(root, modules);
  return modules;
}

const entryModules = modulesReachableFrom('entry');
if (reportedMissingMaps.size === 0) {
  process.stdout.write(
    `  lazy boundary: ${entryModules.length} modules inside the entry closure\n`,
  );
}

for (const forbidden of config.forbidden_in_entry) {
  const root = forbidden.in ?? 'entry';
  const source = (forbidden.scope ?? 'node_modules') === 'source';
  // `source` matches a path of OURS, so a vendored copy under node_modules/ that happens
  // to share the path fragment is not the finding this row is about.
  const needle = source ? forbidden.match : `/node_modules/${forbidden.match}/`;
  const hits = [
    ...new Set(
      modulesReachableFrom(root).filter(
        (module) => module.includes(needle) && (!source || !module.includes('/node_modules/')),
      ),
    ),
  ];
  if (hits.length > 0) {
    problems.push(
      `[lazy-boundary] "${forbidden.match}" is bundled INTO the static closure of "${root}".\n` +
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
