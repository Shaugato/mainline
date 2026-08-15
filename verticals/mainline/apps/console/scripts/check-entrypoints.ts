// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ENTRY-POINT GATE — every HTML document this build emits, and every asset it points at.
 *
 * `docs/demo/operator-systems-plan.md` R7. Run with `node scripts/check-entrypoints.ts`
 * (Node 24 strips the types; there is no bundler in this path, which is why this file uses
 * only erasable syntax) and it is wired into `pnpm run ci` after `vite build`.
 *
 * ── THE GAP IT CLOSES ────────────────────────────────────────────────────────────────
 *
 * `scripts/deploy/build_lambda.sh` copies the whole of `dist/` into `web/` and has a STALE
 * CONSOLE check that reads the asset references out of **`index.html` only** (M6). The day
 * the build emits a second document, that check covers half the surface, and a stale or
 * missing `operator.html` reaches a static host as a page that 404s its own bundle — which
 * renders as the boot notice, i.e. as a product that has nothing to say.
 *
 * The deploy scripts are off limits to this wave (R8), so the assertion is made console-side,
 * over the same `dist/` the packer will pick up.
 *
 * ── THE THREE REFUSALS ───────────────────────────────────────────────────────────────
 *
 *   1. An HTML entry the manifest declares that is NOT on disk, or an HTML file on disk the
 *      manifest never declared. Either direction is an incoherent build.
 *   2. An `./assets/...` reference inside any emitted document that does not resolve to a
 *      real file. This is the STALE CONSOLE failure, generalised to every document.
 *   3. A React module inside the operator entry's static closure. R1 makes `src/operator/**`
 *      framework-free so that `dist/assets/index-*.js` cannot move (R2), and a boundary that
 *      is only a lint is a boundary one `eslint-disable` wide. The module list comes from the
 *      sourcemap, which is the only thing that can answer "what is INSIDE this chunk" — the
 *      same `modulesInChunk()` idiom `scripts/check-budgets.ts` uses for `three`.
 *
 * A missing sourcemap is a FAILURE, not an absence of findings. A check that cannot see the
 * module graph has not passed; it has not run.
 */

import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, dirname, posix } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist');
const MANIFEST = join(DIST, '.vite', 'manifest.json');

/** The manifest key of the operator document, and the modules it may never contain. */
const OPERATOR_KEY = 'operator.html';

/**
 * Bare package directories that must not appear in the operator entry's module list.
 *
 * `react-dom` and `scheduler` are on the list beside `react` because the plan's sentence —
 * "no `node_modules/react` module" — means the React runtime, and shipping `react-dom`
 * without `react` is not a state anybody would defend. Widening a ban is a strengthening.
 */
const FRAMEWORK_MODULES = ['react', 'react-dom', 'react/jsx-runtime', 'scheduler'];

interface ManifestChunk {
  file: string;
  isEntry?: boolean;
  imports?: string[];
  css?: string[];
}

type Manifest = Record<string, ManifestChunk>;

const problems: string[] = [];

function die(message: string): never {
  process.stderr.write(`\ncheck-entrypoints: ${message}\n\n`);
  process.exit(2);
}

/** Every `.html` file emitted into `dist/`, at any depth, as a dist-relative POSIX path. */
function htmlFilesOnDisk(directory: string, prefix: string, out: string[]): void {
  for (const entry of readdirSync(directory)) {
    // `.vite/` holds the manifest, not output.
    if (entry === '.vite') continue;
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) {
      htmlFilesOnDisk(full, posix.join(prefix, entry), out);
      continue;
    }
    if (entry.endsWith('.html')) out.push(posix.join(prefix, entry));
  }
}

/**
 * Asset references inside an emitted document.
 *
 * Deliberately textual and deliberately narrow: `src=`, `href=` and the `import(...)` inside
 * a module preload are the three forms Vite emits, and every one of them lands in `assets/`
 * because `build.assetsDir` says so. Anything that does not mention `assets/` is a data URI,
 * an anchor, or a reference to something this gate has no opinion about.
 */
function assetReferences(html: string): string[] {
  const found = new Set<string>();
  const pattern = /(?:src|href)\s*=\s*["']([^"']+)["']/g;
  let match = pattern.exec(html);
  while (match !== null) {
    const reference = match[1];
    if (reference?.includes('assets/') === true) found.add(reference);
    match = pattern.exec(html);
  }
  return [...found];
}

/** Resolves a document-relative reference against `dist/`. */
function resolveReference(documentPath: string, reference: string): string {
  const cleaned = reference.split('?')[0]?.split('#')[0] ?? reference;
  const withoutLeadingSlash = cleaned.startsWith('/') ? cleaned.slice(1) : cleaned;
  const base = posix.dirname(documentPath);
  return posix.normalize(posix.join(base === '.' ? '' : base, withoutLeadingSlash));
}

/**
 * Every original module Rollup folded into an emitted chunk, read out of its sourcemap.
 *
 * `null` means there is no sourcemap or it did not parse — which the caller treats as a
 * failure. Reused verbatim in shape from `scripts/check-budgets.ts:168-180`; the two gates ask
 * different questions of the same evidence.
 */
function modulesInChunk(relativeFile: string): string[] | null {
  if (!relativeFile.endsWith('.js')) return [];
  const mapPath = join(DIST, `${relativeFile}.map`);
  if (!existsSync(mapPath)) return null;
  try {
    const map = JSON.parse(readFileSync(mapPath, 'utf8')) as { sources?: unknown };
    return Array.isArray(map.sources)
      ? map.sources.filter((source): source is string => typeof source === 'string')
      : [];
  } catch {
    return null;
  }
}

/** Transitive closure over static `imports`, plus the CSS each chunk owns. */
function staticClosure(manifest: Manifest, seed: string): Set<string> {
  const seen = new Set<string>();
  const queue = [seed];
  while (queue.length > 0) {
    const key = queue.pop();
    if (key === undefined || seen.has(key)) continue;
    const chunk = manifest[key];
    if (chunk === undefined) continue;
    seen.add(key);
    for (const next of chunk.imports ?? []) queue.push(next);
  }
  return seen;
}

// ── Run ────────────────────────────────────────────────────────────────────

if (!existsSync(DIST) || !statSync(DIST).isDirectory()) {
  die('dist/ does not exist. Run `vite build` before the entry-point gate.');
}
if (!existsSync(MANIFEST)) {
  die(
    'dist/.vite/manifest.json does not exist. `build.manifest` must be true in vite.config.ts — ' +
      'without it this gate cannot tell which documents the build meant to emit.',
  );
}

const manifest = JSON.parse(readFileSync(MANIFEST, 'utf8')) as Manifest;

process.stdout.write('\ncheck-entrypoints — every document, and every asset it points at\n\n');

// 1 · The documents the manifest declares, against the documents on disk.

const declared = Object.keys(manifest)
  .filter((key) => key.endsWith('.html') && manifest[key]?.isEntry === true)
  .sort();

const onDisk: string[] = [];
htmlFilesOnDisk(DIST, '', onDisk);
onDisk.sort();

if (declared.length === 0) {
  die(
    'the manifest declares no HTML entry at all. A gate over zero documents passes by iterating ' +
      'an empty list, which is the failure this file exists to make impossible.',
  );
}

for (const key of declared) {
  if (!existsSync(join(DIST, key))) {
    problems.push(
      `the manifest declares the entry "${key}" and dist/${key} is not on disk. The packer ` +
        'copies dist/ verbatim, so this document would be missing from web/ and its URL would ' +
        'fall through to the console (static_site.py SPA fallback) rather than 404.',
    );
  }
}

for (const file of onDisk) {
  if (!declared.includes(file)) {
    problems.push(
      `dist/${file} is on disk but the manifest declares no entry for it. It is a leftover from ` +
        'an earlier build with a different input list, and the packer would ship it. Rebuild ' +
        'into a clean dist/.',
    );
  }
}

// 2 · Every asset reference inside every document resolves.

let referencesChecked = 0;

for (const key of declared) {
  const documentPath = join(DIST, key);
  if (!existsSync(documentPath)) continue;
  const html = readFileSync(documentPath, 'utf8');
  const references = assetReferences(html);

  if (references.length === 0) {
    problems.push(
      `dist/${key} references no asset at all. Every entry document loads at least its own ` +
        'entry chunk; a document with no reference is a document whose script tag was dropped, ' +
        'which renders as the boot notice and looks like a product with nothing to say.',
    );
    continue;
  }

  for (const reference of references) {
    referencesChecked += 1;
    const resolved = resolveReference(key, reference);
    if (!existsSync(join(DIST, resolved))) {
      problems.push(
        `dist/${key} references "${reference}", which resolves to dist/${resolved} and is not ` +
          'there. This is the STALE CONSOLE failure: a document from one build served beside ' +
          "another build's assets returns 404 for its own bundle.",
      );
    }
  }
  process.stdout.write(`  ok    ${key.padEnd(16)} ${references.length} asset reference(s)\n`);
}

// 3 · No framework module inside the operator entry's static closure.

const operatorChunk = manifest[OPERATOR_KEY];
if (operatorChunk === undefined) {
  problems.push(
    `the manifest has no "${OPERATOR_KEY}" entry. The operator surface is a required budget ` +
      '(budgets.json, operator-surface) and a required document; a build without it is a build ' +
      'that dropped rollupOptions.input.',
  );
} else {
  const closure = staticClosure(manifest, OPERATOR_KEY);
  const files: string[] = [];
  for (const key of closure) {
    const chunk = manifest[key];
    if (chunk === undefined) continue;
    files.push(chunk.file);
  }

  const modules: string[] = [];
  let mapsMissing = false;
  for (const file of files) {
    const inside = modulesInChunk(file);
    if (inside === null) {
      mapsMissing = true;
      problems.push(
        `${file} is in the operator closure and has no sourcemap, so the modules inside it ` +
          'cannot be enumerated. `build.sourcemap` must stay true: without it this gate cannot ' +
          'tell a framework-free entry from one React was welded into.',
      );
      continue;
    }
    modules.push(...inside);
  }

  if (!mapsMissing) {
    process.stdout.write(
      `  ok    operator closure  ${files.length} file(s), ${modules.length} module(s) inside\n`,
    );
  }

  for (const banned of FRAMEWORK_MODULES) {
    const needle = `/node_modules/${banned}/`;
    const hits = [...new Set(modules.filter((source) => source.includes(needle)))];
    if (hits.length > 0) {
      problems.push(
        `"${banned}" is bundled INTO the operator entry closure.\n` +
          '      src/operator/** is vanilla TypeScript so that operator.html shares no chunk ' +
          'with index.html\n' +
          '      (operator-systems-plan.md R1). The console entry has ~1.1 KB of headroom ' +
          'against the response\n' +
          '      ceiling and a shared closure spends it — R2 requires ' +
          'dist/assets/index-*.js to be\n' +
          '      byte-identical across this change.\n' +
          `      First offending modules: ${hits.slice(0, 5).join(', ')}${hits.length > 5 ? ` (+${hits.length - 5} more)` : ''}`,
      );
    }
  }
}

// ── Report ─────────────────────────────────────────────────────────────────

if (problems.length > 0) {
  process.stderr.write('\ncheck-entrypoints: FAILED\n\n');
  for (const problem of problems) process.stderr.write(`  • ${problem}\n\n`);
  process.exit(1);
}

process.stdout.write(
  `\ncheck-entrypoints: ${declared.length} document(s), ${referencesChecked} asset reference(s), ` +
    'all resolved.\n\n',
);
