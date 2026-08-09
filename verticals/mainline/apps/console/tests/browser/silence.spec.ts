// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * G5 — THE SILENCE SPEC. Three claims, and they are the three the brief names:
 *
 *   1. the conservation identity renders AND VISIBLY BALANCES — the sum on screen equals
 *      the total on screen, with `candidates_conserved` named beside it;
 *   2. the PER honest-limit sentence appears VERBATIM — and it is read out of
 *      `src/features/silence/model.ts` rather than retyped here, so this spec is the CI
 *      grep for that sentence rather than a second copy of it that could drift;
 *   3. no score is displayed without its threshold and its policy version — asserted by
 *      re-sealing a bundle with the threshold removed and requiring the NUMBER to leave
 *      the DOM, not merely to lose its caption.
 *
 * Not one count, score, threshold or theta is written down in this file. All of them are
 * read from `fixtures/bundles/blk-07/` at run time — the same bytes the console's replay
 * transport serves.
 *
 * ── PL-2: WHAT MAKES THIS SPEC RED TODAY ─────────────────────────────────────────
 *
 *   1. **`playwright.config.ts`** with a `baseURL`, cinema mode and the 1920×1080 /
 *      `page.clock.install()` project — the `cinema-conformance-harness` worker (ui W4).
 *      Without it this file does not run at all.
 *   2. **A composed transport.** The shell does not yet provide a `MainlineTransport` to
 *      its surfaces, and this surface deliberately does not build one for itself: on a
 *      screen whose entire subject is what the system chose not to say, a fabricated
 *      source would be the worst possible lie. Until the shell composes `BundleTransport`
 *      plus the in-browser verifier, the surface renders its honest NO SOURCE panel and
 *      every assertion here fails on it.
 *
 * The equivalent claims are asserted TODAY, end to end through the real transport and a
 * real SHA-256 verifier, in `tests/unit/silence/screen.test.tsx`.
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
const MODEL_SOURCE = resolve(HERE, '../../src/features/silence/model.ts');

const EVIDENCE_BUNDLE_BASE = process.env['MAINLINE_BUNDLE_BASE'] ?? '/fixtures/bundles/blk-07/';

interface Frame {
  readonly key: string;
  readonly response: { readonly status: number; readonly body_b64: string };
}

interface SilenceEntryShape {
  readonly silence_id: string;
  readonly source: string;
  readonly reason: string;
  readonly severity: number;
  readonly score: number | null;
  readonly threshold: number | null;
  readonly policy_version: string | null;
  readonly arithmetic: Record<string, unknown>;
}

interface ReceiptShape {
  readonly run_id: string;
  readonly theta: number;
  readonly s: number;
  readonly n: number;
  readonly boundary_proof: {
    readonly leaf_s: { readonly index: number; readonly score: number };
    readonly leaf_s_plus_1: { readonly index: number; readonly score: number } | null;
  };
  readonly bound: { readonly statement: string };
}

interface SilenceEnvelope {
  readonly data: {
    readonly subject_id: string;
    readonly entries: readonly SilenceEntryShape[];
    readonly receipt: ReceiptShape | null;
  };
}

interface RunEnvelope {
  readonly data: {
    readonly counts: {
      readonly n_candidates: number;
      readonly n_blocking: number;
      readonly n_advisory: number;
      readonly n_silenced: number;
      readonly n_deduped: number;
      readonly n_bonded_sev5: number;
      readonly n_bonded_sev5_blocking: number;
    };
    readonly arms_degraded: boolean;
  };
}

// `T` is the CALLER's assertion about JSON read off disk; the payloads are validated
// against their contracts by the transport.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

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

// `T` is the CALLER's assertion about the decoded frame body.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
function decode<T>(frame: Frame): T {
  return JSON.parse(Buffer.from(frame.response.body_b64, 'base64').toString('utf8')) as T;
}

/**
 * THE SENTENCE, read out of the shipped source rather than retyped.
 *
 * The brief requires the PER bound to appear verbatim and to be CI-grepped. A spec that
 * retyped it would be a second copy that can drift from the constant the console renders —
 * and the day they diverged, this spec would still pass while the screen said something
 * else. Reading the export is the grep.
 */
function perLimitSentence(): string {
  const source = readFileSync(MODEL_SOURCE, 'utf8');
  const match = /export const PER_LIMIT_SENTENCE\s*=\s*'([^']+)'/.exec(source);
  if (match?.[1] === undefined) {
    throw new Error(
      `src/features/silence/model.ts no longer exports a single-quoted PER_LIMIT_SENTENCE. The ` +
        'bound on Proof of Exhausted Recall is a named export precisely so that rewording it is a ' +
        'deliberate edit and not a copy edit; find it, or restore it.',
    );
  }
  return match[1];
}

const PERMIT_ID = readJson<SilenceEnvelope>(join(SOURCES_DIR, 'payloads/silence.json')).data
  .subject_id;
const SILENCE_FRAME = findFrame(`GET /v1/permits/${PERMIT_ID}/silence`);
const SILENCE = decode<SilenceEnvelope>(SILENCE_FRAME.frame);
const RECEIPT = SILENCE.data.receipt;
const RUN_FRAME = findFrame(`GET /v1/recall-runs/${RECEIPT?.run_id ?? 'no-receipt'}`);
const RUN = decode<RunEnvelope>(RUN_FRAME.frame);

const PER_LIMIT = perLimitSentence();
const SCORED = SILENCE.data.entries.find((entry) => entry.score !== null);

/**
 * Every raw-similarity number anywhere in an arithmetic blob, whatever nests it.
 *
 * Walking the blob rather than reaching for a known channel name keeps the withholding
 * assertion independent of the fixture's shape: rename `ann_scoped` and this still checks
 * the right numbers, instead of silently checking none.
 */
function rawValuesIn(value: unknown, key = ''): readonly number[] {
  if (typeof value === 'number') {
    return /cosine|similarity|logit|_raw$|^raw$|fused_raw|distance/i.test(key) ? [value] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => rawValuesIn(item, key));
  }
  if (typeof value === 'object' && value !== null) {
    return Object.entries(value).flatMap(([childKey, childValue]) =>
      rawValuesIn(childValue, childKey),
    );
  }
  return [];
}

// ── Navigation ─────────────────────────────────────────────────────────────

const CINEMA = 'cinema=1&seed=8891&t=2026-08-07T02%3A15%3A00.000Z';
const FIXED_CLOCK = new Date('2026-08-07T02:15:00.000Z');

async function openSilence(page: Page): Promise<void> {
  await page.clock.install({ time: FIXED_CLOCK });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/?${CINEMA}#/silence?permit=${PERMIT_ID}`);
  await expect(page.getByTestId('silence-surface')).toBeVisible();
  await expect(page.getByTestId('entry-list')).toBeVisible();
}

// ── Serving a mutated, RE-SEALED bundle ────────────────────────────────────

function sha256Hex(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

interface ManifestShape {
  readonly files: readonly { path: string; sha256: string; bytes: number }[];
}

async function serveMutatedBundle(
  page: Page,
  target: { file: string; frame: Frame },
  mutate: (data: Record<string, unknown>) => void,
): Promise<void> {
  const envelope = decode<Record<string, unknown>>(target.frame);
  mutate(envelope['data'] as Record<string, unknown>);

  const frameBytes = Buffer.from(
    JSON.stringify({
      ...target.frame,
      response: {
        ...target.frame.response,
        body_b64: Buffer.from(JSON.stringify(envelope), 'utf8').toString('base64'),
      },
    }),
    'utf8',
  );

  const manifest = readJson<ManifestShape>(join(BUNDLE_DIR, 'manifest.json'));
  const framePath = `frames/${target.file}`;
  const sealed = manifest.files.map((entry) =>
    entry.path === framePath
      ? { ...entry, sha256: sha256Hex(frameBytes), bytes: frameBytes.byteLength }
      : entry,
  );
  const manifestBytes = Buffer.from(JSON.stringify({ ...manifest, files: sealed }, null, 2), 'utf8');

  const fulfil = (route: Route, body: Buffer): Promise<void> =>
    route.fulfill({ status: 200, contentType: 'application/json', body });

  await page.route(`**${EVIDENCE_BUNDLE_BASE}manifest.json`, (route) => fulfil(route, manifestBytes));
  await page.route(`**${EVIDENCE_BUNDLE_BASE}${framePath}`, (route) => fulfil(route, frameBytes));
}

// ── The spec ───────────────────────────────────────────────────────────────

test.describe('the silence surface', () => {
  test('the fixture this spec reads is the one it thinks it reads', () => {
    // Guards, not formalities. Without them the arithmetic assertions below would compare
    // zero with zero and the score rule would be exercised against no score.
    expect(RECEIPT, 'the bundle carries no PER receipt').not.toBeNull();
    expect(SCORED, 'the bundle carries no scored silence entry').toBeDefined();
    expect(RUN.data.counts.n_candidates).toBeGreaterThan(0);
    expect(PER_LIMIT.length).toBeGreaterThan(20);
  });

  test('THE CONSERVATION IDENTITY renders and balances', async ({ page }) => {
    await openSilence(page);

    const counts = RUN.data.counts;
    await expect(page.getByTestId('conservation-total')).toHaveText(String(counts.n_candidates));
    await expect(page.getByTestId('conservation-n_blocking')).toHaveText(String(counts.n_blocking));
    await expect(page.getByTestId('conservation-n_advisory')).toHaveText(String(counts.n_advisory));
    await expect(page.getByTestId('conservation-n_silenced')).toHaveText(String(counts.n_silenced));
    await expect(page.getByTestId('conservation-n_deduped')).toHaveText(String(counts.n_deduped));

    // It BALANCES on screen: the rendered sum equals the rendered total. Read back from the
    // DOM rather than recomputed here, because the claim is about what a reader can add up.
    const total = Number(await page.getByTestId('conservation-total').innerText());
    const sum = Number(await page.getByTestId('conservation-sum').innerText());
    expect(sum).toBe(total);

    await expect(page.getByTestId('conservation-equation')).toHaveAttribute('data-balances', 'true');
    await expect(page.getByTestId('conservation-constraint')).toContainText('candidates_conserved');
  });

  test('renders the bonded invariant as a satisfied constraint, by name', async ({ page }) => {
    await openSilence(page);
    const counts = RUN.data.counts;
    await expect(page.getByTestId('bonded-equation')).toHaveAttribute('data-holds', 'true');
    await expect(page.getByTestId('bonded-constraint')).toContainText(
      'bonded_fatalities_all_blocking',
    );
    await expect(page.getByTestId('bonded-total')).toHaveText(String(counts.n_bonded_sev5));
    await expect(page.getByTestId('bonded-blocking')).toHaveText(
      String(counts.n_bonded_sev5_blocking),
    );
  });

  test('THE PER HONEST-LIMIT SENTENCE appears verbatim', async ({ page }) => {
    await openSilence(page);
    await expect(page.getByTestId('per-limit-sentence')).toHaveText(PER_LIMIT);
    // And the emitter's own bounding statement, also verbatim, from the payload.
    await expect(page.getByTestId('per-bound-statement')).toHaveText(RECEIPT?.bound.statement ?? '');
  });

  test('renders theta, s, n and the boundary pair from the bundle', async ({ page }) => {
    await openSilence(page);
    await expect(page.getByTestId('per-theta')).toContainText(String(RECEIPT?.theta ?? ''));
    await expect(page.getByTestId('per-s')).toContainText(String(RECEIPT?.s ?? ''));
    await expect(page.getByTestId('per-n')).toContainText(String(RECEIPT?.n ?? ''));
    await expect(page.getByTestId('per-leaf-s-score')).toContainText(
      String(RECEIPT?.boundary_proof.leaf_s.score ?? ''),
    );
    await expect(page.getByTestId('per-bracket')).toHaveAttribute('data-brackets', 'true');
  });

  test('shows NO seal — the inclusion paths are displayed, not verified', async ({ page }) => {
    await openSilence(page);
    await expect(page.getByTestId('per-not-recomputed')).toContainText('DISPLAYED, not verified');
    // The console's only green belongs to the VerificationSeal, and nothing here has been
    // cryptographically verified.
    await expect(page.locator('[data-testid="silence-surface"] [data-testid="verification-seal"]')).toHaveCount(0);
  });

  test('states arms_degraded in whichever direction the bundle carries', async ({ page }) => {
    await openSilence(page);
    await expect(page.getByTestId('arms-degraded')).toHaveAttribute(
      'data-degraded',
      String(RUN.data.arms_degraded),
    );
  });

  test('NO SCORE WITHOUT ITS THRESHOLD AND POLICY VERSION', async ({ page }) => {
    await openSilence(page);

    const shown = page.locator('[data-testid="entry-score"][data-score-state="shown"]');
    await expect(shown.first()).toBeVisible();

    for (const node of await shown.all()) {
      await expect(node.getByTestId('entry-score-value')).toBeVisible();
      await expect(node.getByTestId('entry-threshold-value')).toBeVisible();
      await expect(node.getByTestId('entry-policy-version')).toBeVisible();
    }

    await expect(shown.first().getByTestId('entry-score-value')).toContainText(
      String(SCORED?.score ?? ''),
    );
    await expect(shown.first().getByTestId('entry-threshold-value')).toContainText(
      String(SCORED?.threshold ?? ''),
    );
    await expect(shown.first().getByTestId('entry-policy-version')).toContainText(
      SCORED?.policy_version ?? '',
    );
  });

  test('renders every row in full, with its arithmetic expanded', async ({ page }) => {
    await openSilence(page);
    await expect(page.getByTestId('entry')).toHaveCount(SILENCE.data.entries.length);

    const table = page.getByTestId(`entry-arithmetic-${SCORED?.silence_id ?? ''}`);
    await expect(table).toHaveAttribute('data-raw-admissible', 'true');
    await expect(table.getByTestId('arithmetic-policy-version')).toContainText(
      SCORED?.policy_version ?? '',
    );
    await expect(table.getByTestId('arithmetic-calibrator')).toBeVisible();
    expect(await table.getByTestId('arithmetic-row').count()).toBeGreaterThan(3);
  });
});

test.describe('the EVIDENCE register', () => {
  test('moves nothing a screenshot could not reproduce', async ({ page }) => {
    await openSilence(page);
    const before = await page.getByTestId('silence-surface').innerHTML();
    await page.waitForTimeout(400);
    const after = await page.getByTestId('silence-surface').innerHTML();
    expect(after).toBe(before);
  });

  test('loads no animation or GPU chunk, and draws no chart', async ({ page }) => {
    const scripts: string[] = [];
    page.on('request', (request) => {
      if (request.resourceType() === 'script') scripts.push(request.url());
    });
    await openSilence(page);
    expect(scripts.filter((url) => /three|@react-three|framer-motion|motion-dom/i.test(url))).toEqual(
      [],
    );
    // The arithmetic is a table, not a plot: a stacked bar of channel contributions would
    // make the fusion look measured at a glance, and the numbers are what must be checkable.
    await expect(page.locator('[data-testid="silence-surface"] canvas')).toHaveCount(0);
    await expect(page.locator('[data-testid="silence-surface"] svg')).toHaveCount(0);
  });

  test('has no serious or critical accessibility violation', async ({ page }) => {
    await openSilence(page);
    const results = await new AxeBuilder({ page })
      .include('[data-testid="silence-surface"]')
      .analyze();
    const blocking = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    );
    expect(blocking.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
  });
});

test.describe('nothing is hardcoded', () => {
  test('follows a re-sealed bundle that breaks the identity, and says so', async ({ page }) => {
    await serveMutatedBundle(page, RUN_FRAME, (data) => {
      const counts = data['counts'] as Record<string, number>;
      counts['n_silenced'] = (counts['n_silenced'] ?? 0) + 1;
    });

    await openSilence(page);
    await expect(page.getByTestId('conservation-equation')).toHaveAttribute(
      'data-balances',
      'false',
    );
    await expect(page.getByTestId('conservation-imbalance')).toContainText(
      'THIS IDENTITY DOES NOT BALANCE',
    );
  });

  test('WITHHOLDS the number when the re-sealed bundle removes a threshold', async ({ page }) => {
    await serveMutatedBundle(page, SILENCE_FRAME, (data) => {
      const entries = data['entries'] as Record<string, unknown>[];
      for (const row of entries) {
        if (row['silence_id'] === SCORED?.silence_id) row['threshold'] = null;
      }
    });

    await openSilence(page);
    const withheld = page.locator('[data-testid="entry-score"][data-score-state="withheld"]');
    await expect(withheld.first()).toBeVisible();
    await expect(withheld.first()).toContainText('threshold');
    // The NUMBER is gone, not merely uncaptioned.
    await expect(withheld.first().getByTestId('entry-score-value')).toHaveCount(0);
  });

  test('WITHHOLDS raw similarities when the re-sealed bundle strips the calibration', async ({
    page,
  }) => {
    const withCosine = SILENCE.data.entries.find((entry) =>
      JSON.stringify(entry.arithmetic).includes('cosine'),
    );
    expect(withCosine).toBeDefined();

    await serveMutatedBundle(page, SILENCE_FRAME, (data) => {
      const entries = data['entries'] as Record<string, unknown>[];
      for (const row of entries) {
        if (row['silence_id'] !== withCosine?.silence_id) continue;
        row['score'] = null;
        row['threshold'] = null;
        const arithmetic = row['arithmetic'] as Record<string, unknown>;
        delete arithmetic['p_relevant'];
      }
    });

    await openSilence(page);
    const table = page.getByTestId(`entry-arithmetic-${withCosine?.silence_id ?? ''}`);
    await expect(table).toHaveAttribute('data-raw-admissible', 'false');
    await expect(table.getByTestId('arithmetic-raw-refused')).toBeVisible();
    await expect(table.getByTestId('arithmetic-withheld').first()).toBeVisible();

    // The cosine's VALUE must not be anywhere in the table — the row, the path and the
    // kind stay, and only the number is withheld. Every raw value in the blob is checked,
    // whatever its channel is called, so the assertion does not depend on the fixture's
    // channel names.
    for (const value of rawValuesIn(withCosine?.arithmetic ?? {})) {
      await expect(table).not.toContainText(String(value));
    }
  });
});
