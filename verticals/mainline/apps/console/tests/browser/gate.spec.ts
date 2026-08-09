// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * G5 — THE GATE SPEC. The one assertion `docs/leads/ui.md` §1.5 says must be red first:
 *
 *   > `gate.spec.ts` asserting the refusal bar renders the string
 *   > `gate_closed_when_issued` and SQLSTATE `23514` **taken from the bundle, not from a
 *   > literal in the test**.
 *
 * So this file contains neither string. Both are read out of
 * `fixtures/bundles/blk-07/` at run time — the same bytes the console's replay transport
 * serves — and the last describe block rewrites them in a re-sealed copy of the bundle
 * and requires the rendered headline to follow. A console that hardcoded the constraint
 * name, and a spec that hardcoded the one it expected, would both pass a naive test and
 * neither would assert anything.
 *
 * ── PL-2: WHAT MAKES THIS SPEC RED TODAY, AND WHAT WILL MAKE IT GREEN ────────────
 *
 * Two things it depends on are owned by other workers and had not landed when it was
 * written. They are named here rather than worked around, because a spec that quietly
 * degrades to advisory is a spec that asserts nothing:
 *
 *   1. **`playwright.config.ts` with a `baseURL`, cinema mode and the 1920×1080 /
 *      `deviceScaleFactor: 1` / `page.clock.install()` project** — the
 *      `cinema-conformance-harness` worker (ui W4). Every `page.goto('/…')` below is
 *      relative to that `baseURL`.
 *   2. **A composed transport.** The console shell does not yet provide a
 *      `MainlineTransport` to its surfaces, and the gate surface deliberately does not
 *      build one for itself — `BundleTransport` has no default verifier, and inventing a
 *      permissive one to make a screen paint is the exact lie the transport was shaped to
 *      prevent. Until the shell composes `BundleTransport` + the in-browser verifier
 *      (ui W8) over `EVIDENCE_BUNDLE_BASE` below, the surface renders its honest
 *      NO SOURCE panel and the assertions here fail on it.
 *
 * The equivalent claims are asserted TODAY, end to end through the real transport and a
 * real SHA-256 verifier, in `tests/unit/gate/screen.test.tsx`. This file is the browser
 * tier of the same claims, not a substitute for them.
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Page, type Route } from '@playwright/test';

// ── The fixture, read from disk ────────────────────────────────────────────

const HERE = dirname(fileURLToPath(import.meta.url));
const BUNDLE_DIR = resolve(HERE, '../../fixtures/bundles/blk-07');
const SOURCES_DIR = resolve(HERE, '../../fixtures/sources/blk-07');

/**
 * Where the built console fetches the EvidenceBundle from. Overridable so the spec can
 * run against a demo URL that serves the bundle from a different prefix.
 */
const EVIDENCE_BUNDLE_BASE = process.env['MAINLINE_BUNDLE_BASE'] ?? '/fixtures/bundles/blk-07/';

interface Frame {
  readonly key: string;
  readonly response: { readonly status: number; readonly body_b64: string };
}

interface RefusalShape {
  readonly constraint: string;
  readonly sqlstate: string;
  readonly message: string;
  readonly gate_epoch: number;
  readonly subject_id: string;
  readonly subject_kind: string;
  readonly diagnosis: string;
  readonly mus: readonly unknown[];
  readonly naa: unknown;
}

// `T` is the CALLER's assertion about JSON read off disk. The rule below flags this
// shape in production APIs, where an unchecked assertion hides behind a signature.
// Here the alternative is an `as` at every call site, which hides the same assertion
// in more places; the payloads are validated against their contracts by the transport.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

/** The permit the staged bundle is about, read from the source payload. */
function permitId(): string {
  const permit = readJson<{ data: { permit_id: string } }>(
    join(SOURCES_DIR, 'payloads/permit.json'),
  );
  return permit.data.permit_id;
}

/**
 * Finds the frame file whose canonical request key matches, by READING the frames rather
 * than by recomputing the file-name encoding. Recomputing it here would put a second copy
 * of `src/data/resources.ts`'s encoder in the test tree, and the copy is the one that
 * silently stops matching.
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

// `T` is the CALLER's assertion about JSON read off disk. The rule below flags this
// shape in production APIs, where an unchecked assertion hides behind a signature.
// Here the alternative is an `as` at every call site, which hides the same assertion
// in more places; the payloads are validated against their contracts by the transport.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
function decodeEnvelope<T>(frame: Frame): T {
  return JSON.parse(Buffer.from(frame.response.body_b64, 'base64').toString('utf8')) as T;
}

const PERMIT_ID = permitId();
const MERGE_KEY = `POST /v1/permits/${PERMIT_ID}/merge`;
const MERGE_FRAME = findFrame(MERGE_KEY);

/** THE expected values. Read from the bundle; never written down in this file. */
const REFUSAL = decodeEnvelope<{ data: { refusal: RefusalShape } }>(MERGE_FRAME.frame).data.refusal;

// ── Navigation ─────────────────────────────────────────────────────────────

/**
 * Cinema mode (D12): a frozen clock, a seeded PRNG, transitions disabled. The harness
 * owns the implementation; this spec passes the parameters and installs the clock so the
 * screenshot tier is byte-stable whether or not it is enabled here.
 */
const CINEMA = 'cinema=1&seed=8891&t=2026-08-07T02%3A15%3A00.000Z';
const FIXED_CLOCK = new Date('2026-08-07T02:15:00.000Z');

async function openGate(page: Page, query = ''): Promise<void> {
  await page.clock.install({ time: FIXED_CLOCK });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/?${CINEMA}#/gate?permit=${PERMIT_ID}${query}`);
  await expect(page.getByTestId('gate-surface')).toBeVisible();
}

async function attemptMerge(page: Page): Promise<void> {
  const button = page.getByTestId('attempt-merge');
  await expect(button).toBeEnabled();
  await button.click();
}

// ── Serving a mutated, RE-SEALED bundle ────────────────────────────────────

function sha256Hex(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

interface ManifestShape {
  readonly files: readonly { path: string; sha256: string; bytes: number }[];
}

/**
 * Rewrites one field of the captured refusal and re-seals the manifest over the result,
 * then serves both files through `page.route`.
 *
 * Re-sealing is the point rather than an inconvenience: the console refuses any bundle
 * file whose digest disagrees with the manifest, so a mutated fixture that renders at all
 * has passed the same integrity gate the untouched one does. Serving a mutation WITHOUT
 * re-sealing is asserted separately, and must produce no claims at all.
 */
async function serveMutatedBundle(
  page: Page,
  mutate: (refusal: Record<string, unknown>) => void,
  options: { readonly reseal?: boolean } = {},
): Promise<void> {
  const reseal = options.reseal ?? true;

  const envelope = decodeEnvelope<Record<string, unknown>>(MERGE_FRAME.frame);
  const data = envelope['data'] as { refusal: Record<string, unknown> };
  mutate(data.refusal);

  const frameBytes = Buffer.from(
    JSON.stringify({
      ...MERGE_FRAME.frame,
      response: {
        ...MERGE_FRAME.frame.response,
        body_b64: Buffer.from(JSON.stringify(envelope), 'utf8').toString('base64'),
      },
    }),
    'utf8',
  );

  const manifestPath = join(BUNDLE_DIR, 'manifest.json');
  const manifest = readJson<ManifestShape>(manifestPath);
  const framePath = `frames/${MERGE_FRAME.file}`;

  const sealed = [];
  for (const entry of manifest.files) {
    if (entry.path === framePath && reseal) {
      sealed.push({
        ...entry,
        sha256: sha256Hex(frameBytes),
        bytes: frameBytes.byteLength,
      });
    } else {
      sealed.push(entry);
    }
  }
  const manifestBytes = Buffer.from(
    JSON.stringify({ ...manifest, files: sealed }, null, 2),
    'utf8',
  );

  const fulfil = (route: Route, body: Buffer): Promise<void> =>
    route.fulfill({ status: 200, contentType: 'application/json', body });

  await page.route(`**${EVIDENCE_BUNDLE_BASE}manifest.json`, (route) =>
    fulfil(route, manifestBytes),
  );
  await page.route(`**${EVIDENCE_BUNDLE_BASE}${framePath}`, (route) => fulfil(route, frameBytes));
}

// ── The spec ───────────────────────────────────────────────────────────────

test.describe('the gate surface', () => {
  test('the fixture this spec reads is the one it thinks it reads', () => {
    // A guard, not a formality. If the frame lookup silently returned an empty payload,
    // every assertion below would compare '' with '' and pass.
    expect(REFUSAL.constraint.length).toBeGreaterThan(0);
    expect(REFUSAL.sqlstate.length).toBeGreaterThan(0);
    expect(REFUSAL.mus.length).toBeGreaterThan(0);
    expect(MERGE_FRAME.frame.response.status).toBeGreaterThanOrEqual(400);
  });

  test('shows no refusal until the merge has actually been attempted', async ({ page }) => {
    await openGate(page);
    const bar = page.getByTestId('refusal-bar');
    await expect(bar).toHaveAttribute('data-state', 'none');
    await expect(bar).toContainText('nothing has been refused');
    await expect(page.getByTestId('reason-set-absent')).toBeVisible();
  });

  test('renders the constraint name and the SQLSTATE THE BUNDLE CARRIES', async ({ page }) => {
    await openGate(page);
    await attemptMerge(page);

    await expect(page.getByTestId('refusal-constraint')).toHaveAttribute(
      'data-constraint',
      REFUSAL.constraint,
    );
    await expect(page.getByTestId('refusal-constraint')).toContainText(REFUSAL.constraint);
    await expect(page.getByTestId('refusal-bar')).toHaveAttribute(
      'data-sqlstate',
      REFUSAL.sqlstate,
    );
    await expect(page.getByTestId('refusal-sqlstate')).toContainText(REFUSAL.sqlstate);
  });

  test('renders the database message verbatim, and composes none of its own', async ({ page }) => {
    await openGate(page);
    await attemptMerge(page);
    await expect(page.getByTestId('refusal-message')).toHaveText(REFUSAL.message);
    await expect(page.getByTestId('refusal-gate-epoch')).toHaveText(String(REFUSAL.gate_epoch));
    await expect(page.getByTestId('refusal-subject')).toContainText(REFUSAL.subject_id);
  });

  test('decomposes the refusal into the reason set and the alternative', async ({ page }) => {
    await openGate(page);
    await attemptMerge(page);

    await expect(page.getByTestId('mus-atom')).toHaveCount(REFUSAL.mus.length);
    if (REFUSAL.naa === null) {
      await expect(page.getByTestId('naa-absent')).toBeVisible();
    } else {
      await expect(page.getByTestId('naa')).toBeVisible();
    }
  });

  test('welds the gate: every counter under the CHECK that reads it', async ({ page }) => {
    await openGate(page);
    await attemptMerge(page);

    await expect(page.getByTestId('weld')).toHaveAttribute('data-register', 'instrument');
    await expect(page.getByTestId(`weld-row-${REFUSAL.constraint}`)).toHaveAttribute(
      'data-blamed',
      'true',
    );
    await expect(page.getByTestId('weld-counter-open_blocking')).toHaveAttribute(
      'data-counter-state',
      'blocking',
    );
  });

  test('shows the precursors and the clause diff that armed the check', async ({ page }) => {
    await openGate(page);
    await attemptMerge(page);

    await expect(page.getByTestId('precursor').first()).toBeVisible();
    await expect(page.getByTestId('precursor-anchor').first()).toBeVisible();
    await expect(page.getByTestId('canon-current')).toBeVisible();
    await expect(page.getByTestId('canon-parent')).toBeVisible();
    await expect(page.getByTestId('control-delta')).toBeVisible();
  });

  test('the EVIDENCE register moves nothing a screenshot could not reproduce', async ({ page }) => {
    await openGate(page);
    await attemptMerge(page);

    // Two renderings a frame apart must be identical: nothing on this surface animates.
    const before = await page.getByTestId('gate-surface').innerHTML();
    await page.waitForTimeout(400);
    const after = await page.getByTestId('gate-surface').innerHTML();
    expect(after).toBe(before);
  });

  test('has no serious or critical accessibility violation', async ({ page }) => {
    await openGate(page);
    await attemptMerge(page);

    const results = await new AxeBuilder({ page })
      .include('[data-testid="gate-surface"]')
      .analyze();
    const blocking = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    );
    expect(blocking.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
  });
});

test.describe('nothing is hardcoded', () => {
  test('renders whatever constraint name the re-sealed bundle carries', async ({ page }) => {
    const replacement = 'reading_floor_when_issued';
    expect(replacement).not.toBe(REFUSAL.constraint);

    await serveMutatedBundle(page, (refusal) => {
      refusal['constraint'] = replacement;
    });
    await openGate(page);
    await attemptMerge(page);

    await expect(page.getByTestId('refusal-constraint')).toHaveAttribute(
      'data-constraint',
      replacement,
    );
    await expect(page.getByTestId('refusal-constraint')).not.toContainText(REFUSAL.constraint);
    await expect(page.getByTestId(`weld-row-${replacement}`)).toHaveAttribute(
      'data-blamed',
      'true',
    );
  });

  test('renders whatever SQLSTATE the re-sealed bundle carries', async ({ page }) => {
    const replacement = REFUSAL.sqlstate === '23503' ? '23505' : '23503';

    await serveMutatedBundle(page, (refusal) => {
      refusal['sqlstate'] = replacement;
    });
    await openGate(page);
    await attemptMerge(page);

    await expect(page.getByTestId('refusal-bar')).toHaveAttribute('data-sqlstate', replacement);
  });

  test('renders the honest not-computable state for a null alternative', async ({ page }) => {
    await serveMutatedBundle(page, (refusal) => {
      refusal['naa'] = null;
      refusal['naa_reason'] = 'no_legal_verdict_exists';
    });
    await openGate(page);
    await attemptMerge(page);

    const absent = page.getByTestId('naa-absent');
    await expect(absent).toHaveAttribute('data-naa-reason', 'no_legal_verdict_exists');
    await expect(absent).toContainText('no way to sign this away');
    await expect(page.getByTestId('naa')).toHaveCount(0);
  });

  test('announces a parsed constraint source as a weakened diagnosis', async ({ page }) => {
    await serveMutatedBundle(page, (refusal) => {
      refusal['constraint_source'] = 'parsed';
    });
    await openGate(page);
    await attemptMerge(page);

    await expect(page.getByTestId('refusal-parsed')).toContainText('WEAKENED DIAGNOSIS');
  });
});

test.describe('a tampered bundle shows no claims at all', () => {
  test('refuses to render when a frame’s bytes disagree with the manifest', async ({ page }) => {
    await serveMutatedBundle(
      page,
      (refusal) => {
        refusal['constraint'] = 'this_constraint_was_never_reported';
      },
      { reseal: false },
    );
    await page.clock.install({ time: FIXED_CLOCK });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`/?${CINEMA}#/gate?permit=${PERMIT_ID}`);

    // The verifier refuses the bundle, so no payload reaches a surface: the screen shows
    // a read failure and the fabricated constraint name appears nowhere.
    await expect(page.locator('body')).not.toContainText('this_constraint_was_never_reported');
    await expect(page.getByTestId('refusal-constraint')).toHaveCount(0);
  });
});
