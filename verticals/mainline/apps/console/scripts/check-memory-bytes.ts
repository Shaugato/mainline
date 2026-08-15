// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * R-M2, TURNED FROM AN ARGUMENT INTO A MEASUREMENT.
 *
 * `docs/demo/memory-visible-plan.md` R-M2 rules that a file in `console/public/` adds
 * **zero bytes to the console entry closure**, because Vite copies `public/` verbatim: it
 * never enters the module graph, never gets hashed, and never gets written into
 * `dist/.vite/manifest.json` — which is the only thing `scripts/check-budgets.ts` reads, so
 * a file absent from the manifest is outside both `budgets.json` roots by construction.
 *
 * That is a good argument. **A ruling that is only an argument is not a test**, and the
 * failure it guards is the one that is invisible from outside:
 *
 *   `static_site.DEFAULT_MAX_RESPONSE_BYTES` is 136 KiB = 139,264 B and it bounds the WIRE
 *   bytes of ONE response, static files included. When the console's compressed entry chunk
 *   crosses it, `static_site.serve` answers **413 for the console's own entry JavaScript**,
 *   to every client, because the gzip representation is the one every browser takes.
 *   `GET /` still answers 200 with its 4.7 KB shell; the shell asks for its single module
 *   and receives a JSON problem document; the judge is looking at a **blank page** while
 *   this origin logs a healthy day. Headroom on the deployed package is 1,087 B and
 *   `verticals/mainline/apps/demo-api/tests/test_static_site.py::_MINIMUM_HEADROOM_BYTES`
 *   is 1,024, so 63 more gzipped bytes in the entry closure turns CI red.
 *
 * **The constant is not available to be raised** (R10, `docs/leads/reconcile-constants-plan.md`).
 * So this script proves the memory panel did not spend a byte of that margin, by building
 * the console twice — once with `public/` moved out of the way, once with it in place — and
 * asserting the entry closure is **byte-identical** across the two.
 *
 * WHAT IT ASSERTS, AND WHAT EACH FAILURE WOULD MEAN
 * -------------------------------------------------
 *   A1  `public/` exists and is non-empty ........ nothing to measure otherwise; a green
 *                                                  from an empty probe is the worst answer
 *   A2  the manifest is the same manifest, key
 *       for key, and names no `public/` file ..... a key appeared or vanished, or a file
 *                                                  entered the module graph — either way it
 *                                                  is now inside a `budgets.json` root, which
 *                                                  resolves every root through a manifest key
 *   A3  the entry set is unchanged ............... a second entry appeared, or one moved
 *   A4  every entry-closure file is sha256- and
 *       gzip-identical across the two builds ..... `public/` reached the emitted bytes
 *   A5  every `public/` file is under the wire
 *       ceiling on BOTH representations .......... the page would 413 and render nothing
 *   A6  every `public/` file reaches `dist/`
 *       byte-for-byte ............................ "copied verbatim" was not true
 *
 * WHICH GZIP, AND THE DISAGREEMENT THIS SCRIPT WILL NOT PAPER OVER
 * ----------------------------------------------------------------
 * The bytes a browser actually pulls are the `<name>.gz` sibling written by
 * `scripts/deploy/build_lambda.{sh,ps1}` — `gzip_bytes()`, a hand-written RFC 1952 container
 * around `zlib.compressobj(9, DEFLATED, -MAX_WBITS)`. This script reproduces that container
 * exactly (10-byte header, raw deflate at level 9, CRC32 + ISIZE), but through **Node's**
 * zlib rather than **CPython's**, and the two do not agree: measured 2026-08-15 on this
 * workstation, `public/memory.html` deflates to 7,943 B under Node and 7,990 B under
 * CPython. Tens of bytes, both far under any bound that matters here — but it is a real
 * difference and it is named rather than rounded away.
 *
 * So the numbers below are used for exactly two things, and the calibration is irrelevant to
 * both: **equality between two builds compressed by the same compressor** (A3/A4, where any
 * consistent compressor answers the question), and an order-of-magnitude line item against
 * the ceiling (A5, where the margin is ~123,000 B and 47 B changes nothing). The
 * AUTHORITATIVE per-file sibling size is measured in CPython, with the packer's own
 * `gzip_bytes`, by `tests/deploy/test_memory_page_is_served.py`, which then feeds the result
 * to the real `static_site.serve`. Both figures are recorded in
 * `docs/demo/memory-visible-BYTES.md`.
 *
 * THE CEILING IS READ, NEVER RESTATED
 * ------------------------------------
 * `DEFAULT_MAX_RESPONSE_BYTES` is parsed out of `static_site.py` on every run. A mirrored
 * copy of a constant is a constant that can drift from the thing it claims to check, and
 * this script exists precisely to catch drift.
 *
 * RUN IT
 * -------
 *     cd verticals/mainline/apps/console
 *     node scripts/check-memory-bytes.ts
 *
 * It builds twice (~5 s each) and leaves `dist/` in the state a plain `vite build` leaves
 * it: the second build is an ordinary one, with `public/` present. Exit 0 means every
 * assertion above held; exit 1 means one did not; exit 2 means it could not measure, which
 * is a failure and not an absence of findings.
 *
 * WHAT IT MAY NEVER DO. It does not edit `vite.config.ts`, `budgets.json` or
 * `static_site.py`; it does not raise a ceiling; it does not deploy. If the entry closure
 * has grown, the answer is a smaller or split entry chunk — never a larger bound.
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, renameSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateRawSync } from 'node:zlib';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist');
const MANIFEST = join(DIST, '.vite', 'manifest.json');
const PUBLIC = join(ROOT, 'public');
const VITE_BIN = join(ROOT, 'node_modules', 'vite', 'bin', 'vite.js');

/**
 * Where `public/` is parked for the first build.
 *
 * Dot-prefixed and inside the Vite root on purpose: `renameSync` is atomic on one volume, so
 * the directory is never copied and never at risk of a partial move, and Vite's `publicDir`
 * default is the literal name `public`, which this is not. If this script dies between the
 * two renames the files are still here, under this name, and the next run restores them
 * before doing anything else.
 */
const PARKED = join(ROOT, '.public-bytes-probe');

/** `static_site.py`, read for its ceiling. Not imported, not copied, never edited. */
const STATIC_SITE = join(
  ROOT,
  '..',
  'demo-api',
  'src',
  'mainline_demo_api',
  'static_site.py',
);

/** `test_static_site.py`, read for the headroom floor the entry chunk is held to. */
const STATIC_SITE_TEST = join(ROOT, '..', 'demo-api', 'tests', 'test_static_site.py');

/**
 * Suffixes `build_lambda`'s `gzip_siblings()` writes a `<name>.gz` beside. Held identical to
 * `COMPRESSIBLE_SUFFIXES` in that script: a suffix missing here would be reported as an
 * identity-only object and would understate nothing, but would misname what ships.
 */
const COMPRESSIBLE = new Set([
  '.css',
  '.html',
  '.js',
  '.json',
  '.map',
  '.mjs',
  '.svg',
  '.txt',
  '.wasm',
  '.webmanifest',
]);

interface ManifestChunk {
  file: string;
  isEntry?: boolean;
  imports?: string[];
  css?: string[];
  assets?: string[];
}

type Manifest = Record<string, ManifestChunk>;

interface FileFacts {
  identity: number;
  wire: number;
  sha256: string;
}

interface Snapshot {
  /** `manifest key -> emitted file`, entries only, sorted by key. */
  entries: [string, string][];
  /** Every emitted file in the static closure of every entry, sorted. */
  closure: string[];
  /** Facts per closure file. */
  facts: Record<string, FileFacts>;
  /** Sum of the closure's wire bytes — the number `check-budgets.ts` budgets. */
  closureWire: number;
  /** Every key and every emitted path the manifest mentions, for the A2 search. */
  mentioned: string[];
  /** Every manifest key, sorted. The set itself is compared across the two builds. */
  keys: string[];
}

const problems: string[] = [];

function die(message: string): never {
  process.stderr.write(`\ncheck-memory-bytes: ${message}\n\n`);
  process.exit(2);
}

function readJson(path: string): unknown {
  if (!existsSync(path)) die(`${path} does not exist.`);
  return JSON.parse(readFileSync(path, 'utf8'));
}

/**
 * The packer's sibling, byte-for-byte as `build_lambda.gzip_bytes()` writes it.
 *
 * `1f 8b` magic, `08` deflate, `00` flags (no FNAME — the name is the zip entry's job),
 * four zero bytes of MTIME (there is no clock in that program), `02` XFL for maximum
 * compression, `ff` OS unknown; then the raw deflate stream, then CRC32 and ISIZE. Only the
 * LENGTH is wanted here, and the length is `10 + deflate + 8`, so the trailer is arithmetic
 * rather than a second allocation.
 *
 * See the module docstring for why this is Node's zlib and what that costs.
 */
function siblingBytes(data: Buffer): number {
  return 10 + deflateRawSync(data, { level: 9 }).byteLength + 8;
}

/** Identity size, wire size (the sibling when one would be written) and digest of a file. */
function factsOf(absolute: string): FileFacts {
  const data = readFileSync(absolute);
  const dot = absolute.lastIndexOf('.');
  const suffix = dot === -1 ? '' : absolute.slice(dot).toLowerCase();
  return {
    identity: data.byteLength,
    wire: COMPRESSIBLE.has(suffix) ? siblingBytes(data) : data.byteLength,
    sha256: createHash('sha256').update(data).digest('hex'),
  };
}

/** Parse `NAME: Final = 136 * 1024` or `NAME: Final = 139264` out of a Python module. */
function pythonConstant(path: string, name: string): number {
  if (!existsSync(path)) die(`${path} does not exist, so ${name} cannot be read.`);
  const source = readFileSync(path, 'utf8');
  const pattern = new RegExp(`^${name}\\s*:\\s*Final\\s*=\\s*([0-9_]+)(?:\\s*\\*\\s*([0-9_]+))?`, 'm');
  const found = pattern.exec(source);
  if (found === null) die(`${path} does not declare ${name} in a shape this can read.`);
  const left = Number(found[1]?.replace(/_/g, '') ?? Number.NaN);
  const right = found[2] === undefined ? 1 : Number(found[2].replace(/_/g, ''));
  const value = left * right;
  if (!Number.isSafeInteger(value) || value <= 0) {
    die(`${name} in ${path} parsed to ${value}, which is not a byte count.`);
  }
  return value;
}

function build(label: string): void {
  if (!existsSync(VITE_BIN)) {
    die(`${VITE_BIN} does not exist. Run \`pnpm install\` in ${ROOT} first.`);
  }
  const started = Date.now();
  const run = spawnSync(process.execPath, [VITE_BIN, 'build'], {
    cwd: ROOT,
    encoding: 'utf8',
    // The build is loud and its output is not the finding. It is printed only on failure,
    // where it IS the finding.
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  if (run.status !== 0) {
    process.stderr.write(`${run.stdout ?? ''}\n${run.stderr ?? ''}\n`);
    die(`\`vite build\` (${label}) exited ${run.status}. Nothing below was measured.`);
  }
  process.stdout.write(`  built  ${label.padEnd(28)} ${seconds}s\n`);
}

/** Transitive closure over static `imports`, exactly as `check-budgets.ts` walks it. */
function closureOf(manifest: Manifest, seeds: string[]): Set<string> {
  const seen = new Set<string>();
  const queue = [...seeds];
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

function snapshot(): Snapshot {
  const manifest = readJson(MANIFEST) as Manifest;
  const keys = Object.keys(manifest);
  if (keys.length === 0) die('dist/.vite/manifest.json is empty.');

  const entryKeys = keys.filter((key) => manifest[key]?.isEntry === true).sort();
  if (entryKeys.length === 0) die('the manifest declares no entry chunk.');

  const entries: [string, string][] = entryKeys.map((key) => [key, manifest[key]?.file ?? '']);

  const files = new Set<string>();
  for (const key of closureOf(manifest, entryKeys)) {
    const chunk = manifest[key];
    if (chunk === undefined) continue;
    files.add(chunk.file);
    for (const css of chunk.css ?? []) files.add(css);
  }

  const closure = [...files].sort();
  const facts: Record<string, FileFacts> = {};
  let closureWire = 0;
  for (const file of closure) {
    const absolute = join(DIST, file);
    if (!existsSync(absolute)) die(`the manifest names ${file}, which is not in dist/.`);
    const measured = factsOf(absolute);
    facts[file] = measured;
    closureWire += measured.wire;
  }

  const mentioned: string[] = [...keys];
  for (const key of keys) {
    const chunk = manifest[key];
    if (chunk === undefined) continue;
    mentioned.push(chunk.file, ...(chunk.css ?? []), ...(chunk.assets ?? []));
  }

  return { entries, closure, facts, closureWire, mentioned, keys: [...keys].sort() };
}

function human(bytes: number): string {
  return bytes.toLocaleString('en-US');
}

// ── Run ────────────────────────────────────────────────────────────────────

process.stdout.write('\ncheck-memory-bytes — R-M2, measured rather than argued\n\n');

// A leftover park from a run that died between the two renames. Restoring it is the first
// thing this does, before it can be mistaken for "there is no public/ to measure".
if (existsSync(PARKED)) {
  if (existsSync(PUBLIC)) {
    die(
      `both ${PUBLIC} and ${PARKED} exist. A previous run was interrupted and something has ` +
        'since recreated public/. Merge them by hand — this script will not choose for you.',
    );
  }
  renameSync(PARKED, PUBLIC);
  process.stdout.write(`  restored ${PARKED} -> public/ (a previous run was interrupted)\n`);
}

// A1 — there is something to measure.
if (!existsSync(PUBLIC) || !statSync(PUBLIC).isDirectory()) {
  die(`${PUBLIC} does not exist. R-M2 puts the memory panel there; there is nothing to measure.`);
}
const publicNames = readdirSync(PUBLIC).sort();
if (publicNames.length === 0) {
  die(`${PUBLIC} is empty. A green from an empty probe would prove nothing.`);
}

const CEILING = pythonConstant(STATIC_SITE, 'DEFAULT_MAX_RESPONSE_BYTES');
const MIN_HEADROOM = pythonConstant(STATIC_SITE_TEST, '_MINIMUM_HEADROOM_BYTES');

process.stdout.write(`  ceiling  ${human(CEILING)} B   read from static_site.py, never restated\n`);
process.stdout.write(`  floor    ${human(MIN_HEADROOM)} B   _MINIMUM_HEADROOM_BYTES, from test_static_site.py\n`);
process.stdout.write(`  public/  ${publicNames.length} files: ${publicNames.join(', ')}\n\n`);

let without: Snapshot;
renameSync(PUBLIC, PARKED);
try {
  build('WITHOUT public/');
  without = snapshot();
} finally {
  // Unconditional, and before anything is compared: the tree is restored even when the
  // build above threw, so a failed measurement never costs anybody their files.
  if (existsSync(PARKED)) renameSync(PARKED, PUBLIC);
}

build('WITH public/');
const wit = snapshot();

process.stdout.write('\n');

// A3 — the same entries, under the same names, emitting the same files.
const before = JSON.stringify(without.entries);
const after = JSON.stringify(wit.entries);
if (before !== after) {
  problems.push(
    `[A3] the entry set changed when public/ was added.\n      without: ${before}\n      with:    ${after}`,
  );
}

// A4 — every file in the entry closure is the same file.
if (JSON.stringify(without.closure) !== JSON.stringify(wit.closure)) {
  problems.push(
    '[A4] the entry closure names a different set of files with public/ present.\n' +
      `      without (${without.closure.length}): ${without.closure.join(', ')}\n` +
      `      with    (${wit.closure.length}): ${wit.closure.join(', ')}`,
  );
} else {
  for (const file of wit.closure) {
    const a = without.facts[file];
    const b = wit.facts[file];
    if (a === undefined || b === undefined) continue;
    if (a.sha256 !== b.sha256) {
      problems.push(
        `[A4] ${file} is not byte-identical across the two builds.\n` +
          `      without sha256 ${a.sha256}\n      with    sha256 ${b.sha256}`,
      );
    }
    if (a.wire !== b.wire) {
      problems.push(
        `[A4] ${file} gzips to ${human(a.wire)} B without public/ and ${human(b.wire)} B with it ` +
          `(${b.wire - a.wire >= 0 ? '+' : ''}${b.wire - a.wire} B). ` +
          'R-M2 says a public/ file adds ZERO bytes to the entry closure.',
      );
    }
  }
}

if (without.closureWire !== wit.closureWire) {
  problems.push(
    `[A4] the entry closure totals ${human(without.closureWire)} B gzipped without public/ and ` +
      `${human(wit.closureWire)} B with it.`,
  );
}

// A2 — the manifest is the SAME manifest. Compared as a set before the search below, because
// "no public/ name is in it" is a weaker statement than "public/ did not change it at all":
// a budget root is resolved from a key, so a key appearing or vanishing is the event.
if (JSON.stringify(without.keys) !== JSON.stringify(wit.keys)) {
  const added = wit.keys.filter((key) => !without.keys.includes(key));
  const gone = without.keys.filter((key) => !wit.keys.includes(key));
  problems.push(
    `[A2] dist/.vite/manifest.json changed when public/ was added — ` +
      `${without.keys.length} keys without, ${wit.keys.length} with.\n` +
      `      appeared: ${added.length > 0 ? added.join(', ') : '(none)'}\n` +
      `      vanished: ${gone.length > 0 ? gone.join(', ') : '(none)'}`,
  );
}

// A2 — nothing from public/ is in the manifest, so nothing from public/ is in a budget root.
for (const name of publicNames) {
  const hits = wit.mentioned.filter((mention) => mention === name || mention.endsWith(`/${name}`));
  if (hits.length > 0) {
    problems.push(
      `[A2] public/${name} appears in dist/.vite/manifest.json as ${hits.join(', ')}. ` +
        'It has entered the module graph, so it is now inside a budgets.json root and R-M2 no ' +
        'longer holds by construction.',
    );
  }
}

// ── The entry closure, reported either way ─────────────────────────────────

process.stdout.write('  ENTRY CLOSURE — byte-identical is the whole claim\n');
for (const [key, file] of wit.entries) {
  const a = without.facts[file];
  const b = wit.facts[file];
  if (b === undefined) continue;
  const same = a?.sha256 === b.sha256 && a?.wire === b.wire;
  process.stdout.write(
    `    ${same ? 'SAME' : 'MOVED'}  ${key.padEnd(14)} ${file.padEnd(30)} ` +
      `${human(b.identity).padStart(9)} B identity  ${human(b.wire).padStart(9)} B wire  ` +
      `headroom ${human(CEILING - b.wire).padStart(9)} B\n`,
  );
  if (b.wire > CEILING) {
    problems.push(
      `[CEILING] ${file} would put ${human(b.wire)} B on the wire, over the ${human(CEILING)} B ` +
        'ceiling. static_site.serve answers 413 for the console entry chunk and the page is ' +
        'blank. The fix is a smaller or split entry chunk; the ceiling is not available.',
    );
  } else if (CEILING - b.wire < MIN_HEADROOM) {
    process.stdout.write(
      `    NOTE   ${file} leaves ${human(CEILING - b.wire)} B, under the ${human(MIN_HEADROOM)} B ` +
        'floor test_static_site.py holds the DEPLOYED package to.\n',
    );
  }
}
process.stdout.write(
  `    total  ${wit.closure.length} files, ${human(wit.closureWire)} B gzipped ` +
    `(unchanged: ${without.closureWire === wit.closureWire ? 'yes' : 'NO'})\n` +
    `    keys   ${without.keys.length} manifest keys without public/, ${wit.keys.length} with ` +
    `(identical set: ${JSON.stringify(without.keys) === JSON.stringify(wit.keys) ? 'yes' : 'NO'})\n\n`,
);

// ── A5 / A6 — the memory panel's own files, as their own line item ─────────

process.stdout.write('  public/ FILES — their own line item against the same ceiling\n');
for (const name of publicNames) {
  const source = join(PUBLIC, name);
  if (!statSync(source).isFile()) {
    problems.push(`[A6] public/${name} is not a plain file; the packer copies a flat tree.`);
    continue;
  }
  const src = factsOf(source);
  const copied = join(DIST, name);
  if (!existsSync(copied)) {
    problems.push(
      `[A6] public/${name} did not reach dist/. Vite's default publicDir copy is what puts the ` +
        'memory panel on the origin; without it /memory.html is a 404.',
    );
    continue;
  }
  const out = factsOf(copied);
  if (out.sha256 !== src.sha256) {
    problems.push(
      `[A6] dist/${name} is not byte-identical to public/${name}. "Copied verbatim, never ` +
        'transformed" is the property R-M2 rests on.',
    );
  }
  const verdict = out.wire <= CEILING && out.identity <= CEILING ? 'PASS' : 'FAIL';
  process.stdout.write(
    `    ${verdict}  ${name.padEnd(18)} ${human(out.identity).padStart(8)} B identity  ` +
      `${human(out.wire).padStart(8)} B wire  headroom ${human(CEILING - out.wire).padStart(9)} B\n`,
  );
  if (out.wire > CEILING) {
    problems.push(
      `[A5] ${name} would put ${human(out.wire)} B on the wire, over the ${human(CEILING)} B ` +
        'ceiling: static_site.serve answers 413 and the memory panel renders nothing.',
    );
  }
  if (out.identity > CEILING) {
    problems.push(
      `[A5] ${name} is ${human(out.identity)} B identity, over the ${human(CEILING)} B ceiling. ` +
        'A client that does not send `accept-encoding: gzip` gets a 413 — including curl ' +
        'without --compressed, which is how a judge checks the page by hand.',
    );
  }
}

// ── Report ─────────────────────────────────────────────────────────────────

if (problems.length > 0) {
  process.stderr.write('\ncheck-memory-bytes: FAILED\n\n');
  for (const problem of problems) process.stderr.write(`  • ${problem}\n`);
  process.stderr.write(
    '\n  Raising DEFAULT_MAX_RESPONSE_BYTES is not one of the available fixes (R10).\n\n',
  );
  process.exit(1);
}

process.stdout.write(
  '\ncheck-memory-bytes: the entry closure is byte-identical with and without public/,\n' +
    'and every file the memory panel adds is served well under the wire ceiling.\n\n',
);
