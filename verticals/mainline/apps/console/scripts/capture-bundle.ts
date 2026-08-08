// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Produces an EvidenceBundle: `manifest.json` + `frames/` + `ledger/` + `sql/`.
 *
 *   node scripts/capture-bundle.ts seal    --dir fixtures/blk-07
 *   node scripts/capture-bundle.ts capture --plan capture-plan.json --out out/blk-07
 *   node scripts/capture-bundle.ts check   --dir fixtures/blk-07
 *
 * **seal** is offline and complete: it walks a bundle directory, records every file's
 * length and SHA-256, merges `manifest.seed.json` over the result and writes
 * `manifest.json`. It is what turns a hand-authored fixture into a bundle the player
 * will accept, and it is the mode CI exercises.
 *
 * **capture** performs a real run: each plan step is either an HTTP exchange against a
 * live read API or a `cockroach sql` invocation, and both are recorded byte-for-byte —
 * the HTTP response body base64 exactly as it arrived, the SQL round trip as the exact
 * command line, stdout, stderr and exit code, including the SQLSTATE and constraint
 * name the driver reported on a refusal. The SQL path exists because `docs/leads/ui.md`
 * §4 records that the ancestry read endpoint has **no owner**: the capture script
 * sources that payload directly from SQL, and the console never learns the difference.
 *
 * **check** re-derives every digest and reports disagreement. It is a producer-side
 * self-check, not the console's verifier.
 *
 * On hashing: this script computes SHA-256 because a manifest is a list of digests and
 * there is no way to write one without computing them. That is PRODUCTION, not
 * verification. Nothing in `src/data/**` hashes anything; the console's verification is
 * owned by the verifier-custody-room worker and injected into `BundleTransport`.
 *
 * Honest limit: `capture` has NOT been exercised against a live kernel or a live
 * cluster in this repository — no AWS credential and no CockroachDB Cloud connection is
 * available on the machine this was written on. The code is complete and the failure
 * paths are real, but a reader should treat "capture works" as untested until an
 * `evidence/demo-run-<ts>/` directory produced by it exists.
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { resolveRequest } from '../src/data/resources.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

// ── Small utilities ────────────────────────────────────────────────────────

function die(message: string): never {
  process.stderr.write(`capture-bundle: ${message}\n`);
  process.exit(1);
}

function argValue(flag: string): string | null {
  const index = process.argv.indexOf(flag);
  if (index === -1) return null;
  const value = process.argv[index + 1];
  return value === undefined || value.startsWith('--') ? null : value;
}

function sha256Hex(bytes: Uint8Array): string {
  return createHash('sha256').update(bytes).digest('hex');
}

/** Bundle-relative, forward-slashed, deterministic. Windows separators never leak in. */
function bundlePath(dir: string, file: string): string {
  return relative(dir, file).split(sep).join('/');
}

function walkFiles(dir: string, base: string = dir): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkFiles(full, base));
    else out.push(full);
  }
  return out;
}

/**
 * Files that are bundle METADATA rather than bundle CONTENT.
 *
 * `manifest.json` is excluded because a file cannot carry its own digest.
 * `manifest.seed.json` is excluded because it is the input to sealing, not part of the
 * captured evidence. Everything else in the directory is content and is listed — an
 * unlisted file would sit outside everything the verifier checks.
 */
const NOT_CONTENT = new Set(['manifest.json', 'manifest.seed.json']);

function isContent(relPath: string): boolean {
  if (NOT_CONTENT.has(relPath)) return false;
  // REUSE metadata and version-control attributes are not evidence.
  return !relPath.endsWith('.license') && !relPath.endsWith('.gitattributes') && relPath !== 'REUSE.toml';
}

const MEDIA_TYPES: readonly (readonly [string, string])[] = [
  ['.json', 'application/json'],
  ['.txt', 'text/plain; charset=utf-8'],
  ['.note', 'text/plain; charset=utf-8'],
  ['.md', 'text/markdown; charset=utf-8'],
];

function mediaTypeFor(path: string): string | null {
  for (const [suffix, type] of MEDIA_TYPES) {
    if (path.endsWith(suffix)) return type;
  }
  return null;
}

// ── seal ───────────────────────────────────────────────────────────────────

interface FileEntry {
  path: string;
  sha256: string;
  bytes: number;
  media_type: string | null;
}

interface ManifestSeed {
  bundle_id?: unknown;
  captured_at?: unknown;
  generator?: unknown;
  cluster_fingerprint?: unknown;
  schema_version?: unknown;
  staged?: unknown;
  staged_note?: unknown;
  checkpoint?: unknown;
}

function listContent(dir: string): FileEntry[] {
  const entries: FileEntry[] = [];
  for (const full of walkFiles(dir)) {
    const relPath = bundlePath(dir, full);
    if (!isContent(relPath)) continue;
    const bytes = readFileSync(full);
    entries.push({
      path: relPath,
      sha256: sha256Hex(bytes),
      bytes: bytes.byteLength,
      media_type: mediaTypeFor(relPath),
    });
  }
  // Sorted by path so two seals of the same directory are byte-identical. Evidence Act
  // 1995 (Cth) ss.146–147 need a process that "ordinarily" produces an outcome; a
  // generator whose output varies run to run has no "ordinarily" to appeal to.
  entries.sort((a, b) => a.path.localeCompare(b.path));
  return entries;
}

function seal(dir: string): void {
  const seedPath = join(dir, 'manifest.seed.json');
  if (!existsSync(seedPath)) {
    die(
      `${bundlePath(ROOT, seedPath)} does not exist. A bundle is sealed against a seed that states ` +
        'its identity, its capture time, the cluster behind it and whether it is staged. Those are ' +
        'claims a human makes; this script only computes the digests.',
    );
  }
  const seed = JSON.parse(readFileSync(seedPath, 'utf8')) as ManifestSeed;

  for (const required of ['bundle_id', 'captured_at', 'cluster_fingerprint', 'schema_version', 'staged']) {
    if (seed[required as keyof ManifestSeed] === undefined) {
      die(`manifest.seed.json is missing "${required}".`);
    }
  }
  if (seed.staged === true && typeof seed.staged_note !== 'string') {
    die('manifest.seed.json declares staged: true but carries no staged_note. An unexplained flag is a flag nobody has to justify.');
  }

  const files = listContent(dir);
  if (files.length === 0) die(`${dir} contains no content files.`);

  const manifest = {
    manifest_version: 1,
    bundle_id: seed.bundle_id,
    captured_at: seed.captured_at,
    generator: seed.generator ?? 'capture-bundle.ts 1.0',
    cluster_fingerprint: seed.cluster_fingerprint,
    schema_version: seed.schema_version,
    staged: seed.staged,
    staged_note: seed.staged === true ? seed.staged_note : null,
    checkpoint: seed.checkpoint ?? null,
    files,
  };

  // Two spaces, trailing newline: the same shape the fixtures are hand-authored in, so
  // a `git diff` after a re-seal shows the digests that moved and nothing else.
  writeFileSync(join(dir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `capture-bundle seal: ${bundlePath(ROOT, dir)} — ${files.length} file(s), ` +
      `${files.reduce((sum, file) => sum + file.bytes, 0)} bytes` +
      `${seed.staged === true ? ', STAGED' : ''}\n`,
  );
}

// ── check ──────────────────────────────────────────────────────────────────

function check(dir: string): void {
  const manifestPath = join(dir, 'manifest.json');
  if (!existsSync(manifestPath)) die(`${bundlePath(ROOT, manifestPath)} does not exist. Run \`seal\` first.`);
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as { files?: FileEntry[] };
  const listed = new Map((manifest.files ?? []).map((file) => [file.path, file]));

  const problems: string[] = [];
  const onDisk = new Set<string>();

  for (const full of walkFiles(dir)) {
    const relPath = bundlePath(dir, full);
    if (!isContent(relPath)) continue;
    onDisk.add(relPath);
    const entry = listed.get(relPath);
    if (entry === undefined) {
      problems.push(`${relPath}: present on disk, absent from manifest.files. An unlisted file is never served.`);
      continue;
    }
    const bytes = readFileSync(full);
    if (bytes.byteLength !== entry.bytes) {
      problems.push(`${relPath}: manifest says ${entry.bytes} bytes, file is ${bytes.byteLength}.`);
    }
    const digest = sha256Hex(bytes);
    if (digest !== entry.sha256) {
      problems.push(`${relPath}: manifest says sha256 ${entry.sha256}, file hashes to ${digest}.`);
    }
  }

  for (const path of listed.keys()) {
    if (!onDisk.has(path)) problems.push(`${path}: listed in manifest.files, missing on disk.`);
  }

  if (problems.length > 0) {
    process.stderr.write(`capture-bundle check: FAILED for ${bundlePath(ROOT, dir)}\n`);
    for (const problem of problems) process.stderr.write(`  • ${problem}\n`);
    process.exit(1);
  }
  process.stdout.write(`capture-bundle check: ${bundlePath(ROOT, dir)} — ${listed.size} file(s) agree.\n`);
}

// ── capture ────────────────────────────────────────────────────────────────

interface HttpStep {
  kind: 'http';
  resource: string;
  path?: Record<string, string>;
  query?: Record<string, string>;
  body?: unknown;
}

interface SqlStep {
  kind: 'sql';
  resource: string;
  path?: Record<string, string>;
  query?: Record<string, string>;
  /** Path, relative to the plan file, of a .sql file returning ONE row of ONE JSON column. */
  sql_file: string;
  /** File name stem under sql/ for the verbatim round trip. */
  sql_name: string;
  /** HTTP status the frame should claim. 200 for a read; 409 for a captured refusal. */
  status?: number;
  /** When true, a non-zero exit is the EXPECTED outcome and the round trip is the payload. */
  expect_error?: boolean;
}

interface CapturePlan {
  manifest: ManifestSeed;
  api_base_url?: string;
  cockroach?: { binary?: string; url?: string };
  steps: (HttpStep | SqlStep)[];
}

const CAPTURED_HEADERS = ['content-type', 'date'] as const;

function toBase64(text: string): string {
  return Buffer.from(text, 'utf8').toString('base64');
}

async function captureHttp(step: HttpStep, baseUrl: string, outDir: string): Promise<void> {
  const request: Parameters<typeof resolveRequest>[0] = {
    resource: step.resource,
    ...(step.path === undefined ? {} : { path: step.path }),
    ...(step.query === undefined ? {} : { query: step.query }),
    ...(step.body === undefined ? {} : { body: step.body }),
  };
  const resolved = resolveRequest(request);

  const url = new URL(
    resolved.query.length === 0
      ? resolved.path
      : `${resolved.path}?${resolved.query.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')}`,
    baseUrl,
  ).toString();

  const started = Date.now();
  const response = await fetch(url, {
    method: resolved.method,
    headers:
      resolved.method === 'POST'
        ? { accept: 'application/json', 'content-type': 'application/json' }
        : { accept: 'application/json' },
    ...(resolved.method === 'POST' ? { body: JSON.stringify(resolved.body ?? {}) } : {}),
  });
  const bodyText = await response.text();
  const duration = Date.now() - started;

  const headers: { name: string; value: string }[] = [];
  for (const name of CAPTURED_HEADERS) {
    const value = response.headers.get(name);
    if (value !== null) headers.push({ name, value });
  }

  writeFrame(outDir, resolved.framePath, {
    frame_version: 1,
    key: resolved.key,
    request: {
      method: resolved.method,
      path: resolved.path,
      query: resolved.query.map(([name, value]) => ({ name, value })),
      body_b64: resolved.method === 'POST' ? toBase64(JSON.stringify(resolved.body ?? {})) : null,
    },
    response: { status: response.status, headers, body_b64: toBase64(bodyText) },
    captured_at: new Date().toISOString(),
    duration_ms: duration,
  });
}

function captureSql(step: SqlStep, planDir: string, cockroach: { binary?: string; url?: string }, outDir: string): void {
  const binary = cockroach.binary ?? 'cockroach';
  const url = cockroach.url;
  if (url === undefined) die('a sql step needs plan.cockroach.url.');

  const sqlPath = resolve(planDir, step.sql_file);
  const statement = readFileSync(sqlPath, 'utf8');

  const request: Parameters<typeof resolveRequest>[0] = {
    resource: step.resource,
    ...(step.path === undefined ? {} : { path: step.path }),
    ...(step.query === undefined ? {} : { query: step.query }),
  };
  const resolved = resolveRequest(request);

  const args = ['sql', '--url', url, '--format', 'csv', '--set', 'errexit=true', '-e', statement];
  const started = Date.now();
  const run = spawnSync(binary, args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  const duration = Date.now() - started;

  // The verbatim round trip. Redact the URL: it carries a password, and an evidence
  // bundle is a thing we hand to strangers.
  const roundTrip =
    `$ ${binary} sql --url <redacted> --format csv --set errexit=true -e <statement below>\n` +
    `--- statement ---\n${statement}\n` +
    `--- exit code ---\n${run.status ?? 'null'}\n` +
    `--- stdout ---\n${run.stdout ?? ''}\n` +
    `--- stderr ---\n${run.stderr ?? ''}\n`;
  writeText(outDir, `sql/${step.sql_name}.txt`, roundTrip);

  const failed = run.status !== 0;
  if (failed !== (step.expect_error === true)) {
    die(
      `sql step "${step.sql_name}" ${failed ? 'failed' : 'succeeded'} but the plan expected the opposite. ` +
        'A capture that records the wrong outcome is worse than no capture.\n' +
        (run.stderr ?? ''),
    );
  }

  // A statement expected to fail produces no payload of its own: the refusal payload is
  // assembled by the kernel, not by the SQL shell, so a plan that wants one must use an
  // http step against the kernel. This branch exists so the round trip is still filed.
  if (failed) return;

  const payload = singleCsvCell(step.sql_name, run.stdout ?? '');
  writeFrame(outDir, resolved.framePath, {
    frame_version: 1,
    key: resolved.key,
    request: {
      method: resolved.method,
      path: resolved.path,
      query: resolved.query.map(([name, value]) => ({ name, value })),
      body_b64: null,
    },
    response: {
      status: step.status ?? 200,
      headers: [{ name: 'content-type', value: 'application/json' }],
      body_b64: toBase64(payload),
    },
    captured_at: new Date().toISOString(),
    duration_ms: duration,
  });
}

/**
 * Extracts the one cell of a one-row, one-column CSV result.
 *
 * `--format csv` is used rather than a JSON output format because CSV has been in every
 * CockroachDB release this product could run on, and because a single quoted cell is
 * unambiguous to parse. The statement is required to return exactly one row and one
 * column; anything else is a plan error and says so.
 */
export function singleCsvCell(name: string, stdout: string): string {
  const text = stdout.replace(/\r\n/g, '\n');
  const newlineIndex = text.indexOf('\n');
  if (newlineIndex === -1) {
    die(`sql step "${name}" produced no rows (stdout had no header line).`);
  }
  const body = text.slice(newlineIndex + 1).replace(/\n$/, '');
  if (body === '') die(`sql step "${name}" returned a header and no row.`);

  if (!body.startsWith('"')) {
    if (body.includes('\n')) die(`sql step "${name}" returned more than one row.`);
    return body;
  }
  // RFC 4180: doubled quotes inside a quoted field.
  let out = '';
  let index = 1;
  for (;;) {
    if (index >= body.length) die(`sql step "${name}" returned an unterminated quoted field.`);
    const char = body[index] ?? '';
    if (char === '"') {
      if (body[index + 1] === '"') {
        out += '"';
        index += 2;
        continue;
      }
      index += 1;
      break;
    }
    out += char;
    index += 1;
  }
  if (index !== body.length) {
    die(`sql step "${name}" returned more than one column or more than one row.`);
  }
  return out;
}

function writeFrame(outDir: string, relPath: string, frame: unknown): void {
  writeText(outDir, relPath, `${JSON.stringify(frame, null, 2)}\n`);
}

function writeText(outDir: string, relPath: string, text: string): void {
  const full = join(outDir, ...relPath.split('/'));
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, text, 'utf8');
}

async function capture(planPath: string, outDir: string): Promise<void> {
  const plan = JSON.parse(readFileSync(planPath, 'utf8')) as CapturePlan;
  const planDir = dirname(resolve(planPath));
  mkdirSync(outDir, { recursive: true });

  for (const step of plan.steps) {
    if (step.kind === 'http') {
      if (plan.api_base_url === undefined) die('an http step needs plan.api_base_url.');
      await captureHttp(step, plan.api_base_url, outDir);
      process.stdout.write(`  http  ${step.resource}\n`);
    } else {
      captureSql(step, planDir, plan.cockroach ?? {}, outDir);
      process.stdout.write(`  sql   ${step.resource} (${step.sql_name})\n`);
    }
  }

  writeFileSync(
    join(outDir, 'manifest.seed.json'),
    `${JSON.stringify(plan.manifest, null, 2)}\n`,
    'utf8',
  );
  seal(outDir);
}

// ── stage ──────────────────────────────────────────────────────────────────

interface StageStep {
  resource: string;
  path?: Record<string, string>;
  query?: Record<string, string>;
  body?: unknown;
  status?: number;
  /** Path, relative to the sources directory, of the response body EXACTLY as served. */
  payload: string;
  captured_at?: string;
  /** Path, relative to the sources directory, of the verbatim SQL round trip, if any. */
  sql?: string;
}

interface StagePlan {
  manifest: ManifestSeed;
  /** Directories under the sources root copied into the bundle verbatim. */
  copy?: string[];
  steps: StageStep[];
}

/**
 * Assembles a bundle from hand-authored, human-readable sources.
 *
 * This is how the committed fixtures are built, and it is deliberately not a shortcut
 * around capture: the payload files are the response bodies BYTE FOR BYTE — `stage`
 * copies their bytes into the frame rather than re-serialising a parsed object — so
 * what a reviewer reads in `fixtures/sources/**` is exactly what the console receives,
 * to the byte, digest included.
 *
 * Every bundle built this way MUST declare `staged: true` with a note, because it is
 * hand-authored demonstration material and the honesty chrome has to say so on every
 * screen it feeds. This function refuses to build one that does not.
 */
function stage(sourcesDir: string, outDir: string): void {
  const planPath = join(sourcesDir, 'plan.json');
  if (!existsSync(planPath)) die(`${bundlePath(ROOT, planPath)} does not exist.`);
  const plan = JSON.parse(readFileSync(planPath, 'utf8')) as StagePlan;

  if (plan.manifest.staged !== true) {
    die(
      'a staged bundle must declare manifest.staged = true. Hand-authored material that does not ' +
        'announce itself is the one thing this console must never render.',
    );
  }

  mkdirSync(outDir, { recursive: true });

  for (const step of plan.steps) {
    const request: Parameters<typeof resolveRequest>[0] = {
      resource: step.resource,
      ...(step.path === undefined ? {} : { path: step.path }),
      ...(step.query === undefined ? {} : { query: step.query }),
      ...(step.body === undefined ? {} : { body: step.body }),
    };
    const resolved = resolveRequest(request);

    const payloadPath = join(sourcesDir, ...step.payload.split('/'));
    if (!existsSync(payloadPath)) die(`step "${step.resource}" names a missing payload: ${step.payload}`);
    const payloadBytes = readFileSync(payloadPath);

    const headers = [{ name: 'content-type', value: 'application/json' }];
    writeFrame(outDir, resolved.framePath, {
      frame_version: 1,
      key: resolved.key,
      request: {
        method: resolved.method,
        path: resolved.path,
        query: resolved.query.map(([name, value]) => ({ name, value })),
        body_b64:
          resolved.method === 'POST' ? Buffer.from(JSON.stringify(resolved.body ?? {}), 'utf8').toString('base64') : null,
      },
      response: {
        status: step.status ?? 200,
        headers,
        body_b64: payloadBytes.toString('base64'),
      },
      captured_at: step.captured_at ?? plan.manifest.captured_at,
      duration_ms: null,
    });
    process.stdout.write(`  stage ${step.resource.padEnd(20)} ${resolved.key}\n`);
  }

  for (const directory of plan.copy ?? []) {
    const from = join(sourcesDir, directory);
    if (!existsSync(from)) die(`plan.copy names a missing directory: ${directory}`);
    for (const full of walkFiles(from)) {
      const relPath = `${directory}/${bundlePath(from, full)}`;
      if (!isContent(relPath.split('/').slice(-1)[0] ?? '')) continue;
      const target = join(outDir, ...relPath.split('/'));
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, readFileSync(full));
    }
    process.stdout.write(`  copy  ${directory}/\n`);
  }

  writeFileSync(join(outDir, 'manifest.seed.json'), `${JSON.stringify(plan.manifest, null, 2)}\n`, 'utf8');
  seal(outDir);
}

// ── Entry point ────────────────────────────────────────────────────────────

const command = process.argv[2];

if (command === 'stage') {
  const sourcesArg = argValue('--sources');
  const outArg = argValue('--out');
  if (sourcesArg === null || outArg === null) die('stage needs --sources <directory> --out <directory>.');
  stage(resolve(ROOT, sourcesArg), resolve(ROOT, outArg));
} else if (command === 'seal' || command === 'check') {
  const dirArg = argValue('--dir');
  if (dirArg === null) die(`${command} needs --dir <bundle directory>.`);
  const dir = resolve(ROOT, dirArg);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) die(`${dirArg} is not a directory.`);
  if (command === 'seal') seal(dir);
  else check(dir);
} else if (command === 'capture') {
  const planArg = argValue('--plan');
  const outArg = argValue('--out');
  if (planArg === null || outArg === null) die('capture needs --plan <plan.json> --out <directory>.');
  await capture(resolve(ROOT, planArg), resolve(ROOT, outArg));
} else {
  process.stderr.write(
    'capture-bundle — produces an EvidenceBundle\n\n' +
      '  node scripts/capture-bundle.ts stage   --sources <directory> --out <directory>\n' +
      '  node scripts/capture-bundle.ts seal    --dir <bundle directory>\n' +
      '  node scripts/capture-bundle.ts check   --dir <bundle directory>\n' +
      '  node scripts/capture-bundle.ts capture --plan <plan.json> --out <directory>\n\n' +
      'See docs/evidence-bundle.md.\n',
  );
  process.exit(2);
}
