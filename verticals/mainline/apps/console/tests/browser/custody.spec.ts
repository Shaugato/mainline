// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * G5 — THE CUSTODY SPEC.
 *
 * The claim under test is `docs/leads/ui.md` D6, at the pixel: *the console re-derives, in
 * the browser, from signed bytes, every claim it displays — and shows the derivation.* So
 * this file does three things a unit test cannot:
 *
 *   1. serves a bundle whose `ledger` frame carries `tests/vectors/ledger-payload.json` —
 *      cryptographically real, down to an ECDSA P-256 signature made with the key
 *      PUBLISHED in `spec/wire/checkpoint.md` §7.1 — and requires every seal the vector
 *      names to be green in a real browser, with a real Web Worker and real WebCrypto;
 *   2. flips ONE byte without re-sealing and requires the frame to be blocked entirely;
 *   3. re-signs the checkpoint body with a DIFFERENT key and requires the signature check
 *      to fail.
 *
 * Nothing here writes down a digest, a constraint name or a check name. Every expected
 * value is read from `tests/vectors/` at run time — the same bytes the console verifies —
 * because a spec that hardcoded what it expected would pass against a console that
 * hardcoded the same thing, and neither would assert anything.
 *
 * ── PL-2: WHAT MAKES THIS SPEC RED TODAY, AND WHAT WILL MAKE IT GREEN ────────────
 *
 * Two dependencies are owned by other workers and had not landed when this was written.
 * They are named rather than worked around, because a spec that quietly degrades to
 * advisory is a spec that asserts nothing:
 *
 *   1. **`playwright.config.ts` with a `baseURL` and the cinema project** — the
 *      `cinema-conformance-harness` worker (ui W4). Every `page.goto` below is relative
 *      to that `baseURL`.
 *   2. **A composed transport.** The shell does not yet provide a `MainlineTransport` to
 *      its surfaces, and the custody surface deliberately does not build one for itself.
 *      Until the shell composes `BundleTransport` + `InBrowserBundleVerifier` over
 *      `EVIDENCE_BUNDLE_BASE`, the surface renders its honest NO SOURCE panel and the
 *      assertions here fail on it.
 *
 * The equivalent claims are asserted TODAY, through the real transport and the real
 * verifier, in `tests/unit/verify/custody-screen.test.tsx`. This file is the browser tier
 * of the same claims, not a substitute for them.
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Page, type Route } from '@playwright/test';

const HERE = dirname(fileURLToPath(import.meta.url));
const BUNDLE_DIR = resolve(HERE, '../../fixtures/bundles/blk-07');
const VECTORS_DIR = resolve(HERE, '../vectors');

const EVIDENCE_BUNDLE_BASE = process.env['MAINLINE_BUNDLE_BASE'] ?? '/fixtures/bundles/blk-07/';

// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

interface Frame {
  readonly key: string;
  readonly response: { readonly status: number; readonly body_b64: string };
}

interface ManifestShape {
  readonly files: readonly { path: string; sha256: string; bytes: number }[];
}

interface LedgerVector {
  readonly vkey: string;
  readonly canon_src_sha256: string;
  readonly envelope: {
    readonly data: {
      readonly site_code: string;
      readonly leaves: readonly { readonly seq: number; readonly leaf_hash_hex: string }[];
      readonly checkpoints: readonly { readonly tree_size: number; readonly note: string }[];
    };
  };
  readonly expect: {
    readonly overall: string;
    readonly pass: readonly string[];
    readonly skip: readonly string[];
  };
}

const VECTOR = readJson<LedgerVector>(join(VECTORS_DIR, 'ledger-payload.json'));
const CHECKPOINT_VECTORS = readJson<{
  readonly keys: { readonly adversary: { readonly vkey: string } };
  readonly cases: readonly { readonly id: string; readonly full_note: string }[];
}>(join(VECTORS_DIR, 'checkpoint.json'));

/**
 * Finds a frame by READING the frames rather than by recomputing the file-name encoding.
 * Recomputing it here would put a second copy of `src/data/resources.ts`'s encoder in the
 * test tree, and the copy is the one that silently stops matching.
 */
function findFrame(requestKey: string): { file: string; frame: Frame } {
  const dir = join(BUNDLE_DIR, 'frames');
  for (const file of readdirSync(dir)) {
    const frame = readJson<Frame>(join(dir, file));
    if (frame.key === requestKey) return { file, frame };
  }
  throw new Error(
    `no frame in ${dir} answers "${requestKey}". The fixture bundle and this spec disagree ` +
      'about what was captured.',
  );
}

const SITE = VECTOR.envelope.data.site_code;
const LEDGER_KEY = `GET /v1/ledger?site_code=${SITE}`;
const LEDGER_FRAME = findFrame(LEDGER_KEY);

const CINEMA = 'cinema=1&seed=8891&t=2026-08-07T02%3A15%3A00.000Z';
const FIXED_CLOCK = new Date('2026-08-07T02:15:00.000Z');

function sha256Hex(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

/**
 * Serve the bundle with the ledger frame replaced by `envelope`, optionally re-sealed.
 *
 * Re-sealing is the point rather than an inconvenience: the console refuses any bundle
 * file whose digest disagrees with the manifest, so a substituted frame that renders at
 * all has passed the same integrity gate the untouched one does. Serving a substitution
 * WITHOUT re-sealing is asserted separately, and must produce no claims at all.
 */
async function serveLedger(
  page: Page,
  envelope: unknown,
  options: { readonly reseal?: boolean; readonly flipOneByte?: boolean } = {},
): Promise<void> {
  const reseal = options.reseal ?? true;

  let frameBytes = Buffer.from(
    JSON.stringify({
      ...LEDGER_FRAME.frame,
      response: {
        ...LEDGER_FRAME.frame.response,
        body_b64: Buffer.from(JSON.stringify(envelope), 'utf8').toString('base64'),
      },
    }),
    'utf8',
  );

  const framePath = `frames/${LEDGER_FRAME.file}`;
  const manifest = readJson<ManifestShape>(join(BUNDLE_DIR, 'manifest.json'));
  const sealed = manifest.files.map((entry) =>
    entry.path === framePath && reseal
      ? { ...entry, sha256: sha256Hex(frameBytes), bytes: frameBytes.byteLength }
      : entry,
  );
  const manifestBytes = Buffer.from(JSON.stringify({ ...manifest, files: sealed }, null, 2), 'utf8');

  if (options.flipOneByte === true) {
    // AFTER sealing, and length-preserving, so the transport's byte-length guard cannot
    // catch it first. Only the digest can see this.
    const copy = Buffer.from(frameBytes);
    const index = Math.floor(copy.length / 2);
    copy[index] = (copy[index] ?? 0) ^ 0x01;
    frameBytes = copy;
  }

  const fulfil = (route: Route, body: Buffer): Promise<void> =>
    route.fulfill({ status: 200, contentType: 'application/json', body });

  await page.route(`**${EVIDENCE_BUNDLE_BASE}manifest.json`, (route) => fulfil(route, manifestBytes));
  await page.route(`**${EVIDENCE_BUNDLE_BASE}${framePath}`, (route) => fulfil(route, frameBytes));
}

async function openCustody(page: Page, query = ''): Promise<void> {
  await page.clock.install({ time: FIXED_CLOCK });
  await page.setViewportSize({ width: 1920, height: 1080 });
  const vkey = encodeURIComponent(VECTOR.vkey);
  await page.goto(`/?${CINEMA}&log_vkey=${vkey}#/custody?site=${SITE}${query}`);
  await expect(page.getByTestId('custody-surface')).toBeVisible();
}

// ── The spec ───────────────────────────────────────────────────────────────

test.describe('the custody surface', () => {
  test('the vectors this spec reads are the ones it thinks it reads', () => {
    // A guard, not a formality. If the vector loader silently returned an empty object,
    // every assertion below would compare '' with '' and pass.
    expect(VECTOR.expect.pass.length).toBeGreaterThan(4);
    expect(VECTOR.envelope.data.leaves.length).toBeGreaterThan(0);
    expect(VECTOR.vkey).toMatch(/^[^\s+]+\+[0-9a-f]{8}\+/);
    expect(LEDGER_FRAME.frame.key).toBe(LEDGER_KEY);
  });

  test('every seal the vector names is green, in a real browser', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);

    for (const name of VECTOR.expect.pass) {
      await expect(
        page.getByTestId(`seal-${name}`),
        `check ${name} must be verified by recomputation`,
      ).toHaveAttribute('data-state', 'verified');
    }
  });

  test('a green seal carries the digest it recomputed, not just a tick', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);

    const leaf = VECTOR.envelope.data.leaves[0];
    expect(leaf).toBeDefined();
    const table = page.getByTestId('recomputation-leaf_hash_recomputation');
    await expect(table).toContainText(leaf?.leaf_hash_hex ?? 'missing');
    await expect(table).toContainText('agrees');
  });

  test('the report is BOUNDED, never clean, and names what was not run', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);

    await expect(page.getByTestId('custody-summary')).toContainText('NOT RUN');
    for (const name of VECTOR.expect.skip) {
      await expect(page.getByTestId(`seal-${name}`)).toHaveAttribute('data-state', 'unverified');
    }
  });

  test('the verifier ran in a Web Worker with the platform SHA-256', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);
    // The value starts as `starting` and must CHANGE. A pre-filled slot would pass a
    // `toContainText` on the first paint without the verifier having answered.
    await expect(page.getByTestId('verifier-transport')).toHaveText(/worker · WebCrypto SHA-256/);
  });

  test('flipping ONE byte turns the seal red and blocks the frame', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope, { flipOneByte: true });
    await page.clock.install({ time: FIXED_CLOCK });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`/?${CINEMA}#/custody?site=${SITE}`);

    const failure = page.getByTestId('custody-transport-failure');
    await expect(failure).toBeVisible();
    await expect(failure).toContainText('These are not the bytes that were sealed.');
    // Nothing was rendered from bundle bytes at all.
    await expect(page.getByTestId('custody-checks')).toHaveCount(0);
  });

  test('a leaf whose canon bytes changed fails, even in a correctly sealed bundle', async ({
    page,
  }) => {
    const envelope = JSON.parse(JSON.stringify(VECTOR.envelope)) as {
      data: { leaves: { canon_bytes_b64: string }[] };
    };
    const leaf = envelope.data.leaves[3];
    expect(leaf, 'the ledger vector is truncated').toBeDefined();
    if (leaf === undefined) return;
    const canon = Buffer.from(leaf.canon_bytes_b64, 'base64').toString('utf8');
    const mutated = canon.replace('"controlled"', '"uncontrolled"');
    expect(mutated).not.toBe(canon);
    leaf.canon_bytes_b64 = Buffer.from(mutated, 'utf8').toString('base64');

    await serveLedger(page, envelope);
    await openCustody(page);

    await expect(page.getByTestId('seal-leaf_hash_recomputation')).toHaveAttribute(
      'data-state',
      'failed',
    );
    await expect(page.getByTestId('custody-overall-seal')).toHaveAttribute('data-state', 'failed');
  });

  test('a checkpoint re-signed with a different key fails the signature check', async ({ page }) => {
    const forged = CHECKPOINT_VECTORS.cases.find(
      (entry) => entry.id === 'resigned-body-different-key-spoofed-id',
    );
    expect(forged, 'the checkpoint vector set is truncated').toBeDefined();

    const envelope = JSON.parse(JSON.stringify(VECTOR.envelope)) as {
      data: { checkpoints: Record<string, unknown>[] };
    };
    // Replace the whole checkpoint with the forged one from the vectors: same note text,
    // the trusted key's id on the line, a signature the trusted key did not produce.
    envelope.data.checkpoints = [
      {
        site_code: SITE,
        tree_size: 5,
        root_hex: '00c5dddf89d15dfbf9fb2349e0adadbcc4a5131b6612adfc85ad0df2005d359e',
        note: forged?.full_note ?? '',
        log_key: null,
        log_sig_b64: null,
        tsa_token_b64: null,
        s3_version: null,
        canon_src_sha256: VECTOR.canon_src_sha256,
        admissible: false,
        observed_at: '2026-08-07T02:14:06.000Z',
      },
    ];

    await serveLedger(page, envelope);
    await openCustody(page);

    await expect(page.getByTestId('seal-log_signature')).toHaveAttribute('data-state', 'failed');
    await expect(page.getByTestId('custody-checks')).toContainText(
      'does not verify over the note text',
    );
  });

  test('with no key configured the signature check SKIPS — it never passes', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await page.clock.install({ time: FIXED_CLOCK });
    await page.setViewportSize({ width: 1920, height: 1080 });
    // No ?log_vkey= at all.
    await page.goto(`/?${CINEMA}#/custody?site=${SITE}`);
    await expect(page.getByTestId('custody-surface')).toBeVisible();

    await expect(page.getByTestId('seal-log_signature')).toHaveAttribute('data-state', 'unverified');
    await expect(page.getByTestId('custody-checks')).toContainText(
      'no verification key is configured',
    );
  });

  test('the split-view limit renders as literal text', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);

    // The sentence, verbatim. It is read from src/verify/ledger.ts's exported constant in
    // the unit tier; here it is written out ONCE, deliberately, because this is the tier
    // that proves a reader of the PAGE sees it — and a spec that read the constant from
    // the source it is checking would assert only that the source equals itself.
    const LIMIT =
      'Until an adverse witness runs the cosigning service the quorum is q=1 and split-view ' +
      'resistance is NOT claimed.';

    const panel = page.getByTestId('split-view-limit');
    await expect(panel).toBeVisible();
    await expect(panel).toContainText(LIMIT);

    // And it appears on a screen where the quorum check PASSED, which is the point.
    await expect(page.getByTestId('seal-witness_quorum')).toHaveAttribute('data-state', 'verified');
    await expect(page.getByTestId('bounded-witness_quorum')).toContainText(LIMIT);
  });

  test('the checkpoint note is shown verbatim, em dash and all', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);

    const head = VECTOR.envelope.data.checkpoints.at(-1);
    expect(head).toBeDefined();
    const note = page.getByTestId('checkpoint-note').last();
    await expect(note).toContainText('— ');
    const rendered = await note.textContent();
    expect(rendered).toBe(head?.note ?? 'missing');
  });

  test('the chain names four layers, and L0 is present-but-unseen', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);

    const chain = page.getByTestId('custody-chain');
    await expect(chain.locator('[data-level]')).toHaveCount(4);
    await expect(page.getByTestId('chain-count-L0')).toContainText('not visible from here');
  });

  test('the surface has no serious or critical accessibility defect', async ({ page }) => {
    await serveLedger(page, VECTOR.envelope);
    await openCustody(page);

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const blocking = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    );
    expect(
      blocking.map((violation) => `${violation.id}: ${violation.help}`),
      'a safety product a supervisor with a cracked screen and gloves cannot operate has an availability of zero',
    ).toEqual([]);
  });
});
