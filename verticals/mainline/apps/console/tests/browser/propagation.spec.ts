// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * G5 — THE FLEET SPEC. The claim it exists to defend, in one sentence:
 *
 *   > a site that DECLINED a lesson is rendered with equal prominence to a site that
 *   > ADOPTED it, and it carries its declination kind and its predicate.
 *
 * Neither a site code, nor a declination kind, nor a predicate id is written down in this
 * file. All of them are read out of `fixtures/bundles/blk-07/` at run time — the same bytes
 * the console's replay transport serves — and the last describe block re-seals a MUTATED
 * copy of the bundle and requires the screen to follow it. A console that hardcoded a
 * declination kind and a spec that hardcoded the one it expected would both pass a naive
 * suite and neither would assert anything.
 *
 * ── WHY "EQUAL PROMINENCE" IS ASSERTED IN THE BROWSER AND NOT ONLY IN JSDOM ──────
 *
 * `tests/unit/propagation/screen.test.tsx` asserts the DOM property: both rows carry the
 * same class attribute and the same `data-prominence`. That is necessary and not
 * sufficient — a stylesheet could give `.site[data-state="declined"]` half the opacity and
 * every jsdom assertion would stay green, because jsdom does not cascade.
 *
 * So this file measures COMPUTED values in a real engine: font size, font weight, opacity
 * and rendered width of the state label, compared between the adopted row and the declined
 * row. It is the only tier that can see a whisper.
 *
 * ── PL-2: WHAT MAKES THIS SPEC RED TODAY ─────────────────────────────────────────
 *
 * Two things it depends on are owned by other workers and had not landed when it was
 * written. They are named here rather than worked around, because a spec that quietly
 * degrades to advisory is a spec that asserts nothing:
 *
 *   1. **`playwright.config.ts` with a `baseURL`, cinema mode and the 1920×1080 /
 *      `deviceScaleFactor: 1` / `page.clock.install()` project** — the
 *      `cinema-conformance-harness` worker (ui W4). Every `page.goto('/…')` below is
 *      relative to that `baseURL`; without it this file does not even run.
 *   2. **A composed transport.** The console shell does not yet provide a
 *      `MainlineTransport` to its surfaces, and this surface deliberately does not build
 *      one for itself — `BundleTransport` has no default verifier, and inventing a
 *      permissive one to make a screen paint is the exact lie the transport was shaped to
 *      prevent. Until the shell composes `BundleTransport` + the in-browser verifier over
 *      `EVIDENCE_BUNDLE_BASE`, the surface renders its honest NO SOURCE panel and every
 *      assertion here fails on it.
 *
 * The equivalent claims are asserted TODAY, end to end through the real transport and a
 * real SHA-256 verifier, in `tests/unit/propagation/screen.test.tsx`. This file is the
 * browser tier of the same claims, not a substitute for them.
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Locator, type Page, type Route } from '@playwright/test';

// ── The fixture, read from disk ────────────────────────────────────────────

const HERE = dirname(fileURLToPath(import.meta.url));
const BUNDLE_DIR = resolve(HERE, '../../fixtures/bundles/blk-07');
const SOURCES_DIR = resolve(HERE, '../../fixtures/sources/blk-07');

const EVIDENCE_BUNDLE_BASE = process.env['MAINLINE_BUNDLE_BASE'] ?? '/fixtures/bundles/blk-07/';

interface Frame {
  readonly key: string;
  readonly response: { readonly status: number; readonly body_b64: string };
}

interface PropagationRow {
  readonly site_id: string;
  readonly site_code: string | null;
  readonly state: string;
  readonly score: number;
  readonly model_version: string;
  readonly due_by: string;
  readonly declination_kind: string | null;
  readonly declination_predicate_id: string | null;
}

interface ConflictRow {
  readonly conflict_id: string;
  readonly base_digest: string;
  readonly ours_digest: string;
  readonly theirs_digest: string;
}

interface PropagationEnvelope {
  readonly observed_at: string;
  readonly data: {
    readonly lesson: { readonly lesson_id: string; readonly control_delta: string };
    readonly propagations: readonly PropagationRow[];
    readonly conflicts: readonly ConflictRow[];
  };
}

// `T` is the CALLER's assertion about JSON read off disk. The payloads are validated
// against their contracts by the transport; asserting here beats an `as` at every call site.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

function lessonId(): string {
  return readJson<PropagationEnvelope>(join(SOURCES_DIR, 'payloads/propagation.json')).data.lesson
    .lesson_id;
}

/**
 * Finds the frame whose canonical request key matches, by READING the frames rather than by
 * recomputing the file-name encoding. Recomputing it here would put a second copy of
 * `src/data/resources.ts`'s encoder in the test tree, and the copy is the one that silently
 * stops matching.
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

function decodeEnvelope(frame: Frame): PropagationEnvelope {
  return JSON.parse(
    Buffer.from(frame.response.body_b64, 'base64').toString('utf8'),
  ) as PropagationEnvelope;
}

const LESSON_ID = lessonId();
const FRAME = findFrame(`GET /v1/lessons/${LESSON_ID}/propagation`);
const PAYLOAD = decodeEnvelope(FRAME.frame);

/** THE two rows the claim is about. Read from the bundle; never written down here. */
const ADOPTED = PAYLOAD.data.propagations.find((row) => row.state === 'adopted');
const DECLINED = PAYLOAD.data.propagations.find((row) => row.state === 'declined');

function siteKey(row: PropagationRow | undefined): string {
  return row?.site_code ?? row?.site_id ?? '';
}

// ── Navigation ─────────────────────────────────────────────────────────────

const CINEMA = 'cinema=1&seed=8891&t=2026-08-07T02%3A15%3A00.000Z';
const FIXED_CLOCK = new Date('2026-08-07T02:15:00.000Z');

async function openPropagation(page: Page): Promise<void> {
  await page.clock.install({ time: FIXED_CLOCK });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/?${CINEMA}#/propagation?lesson=${LESSON_ID}`);
  await expect(page.getByTestId('propagation-surface')).toBeVisible();
  await expect(page.getByTestId('site-list')).toBeVisible();
}

function siteRow(page: Page, site: string): Locator {
  return page.locator(`[data-testid="site-row"][data-site="${site}"]`);
}

/** The computed values that would betray a whispered row. */
async function prominenceOf(row: Locator): Promise<Record<string, string>> {
  return row.locator('[data-testid="site-state"]').evaluate((node) => {
    const style = window.getComputedStyle(node);
    const container = node.closest('[data-testid="site-row"]');
    const containerStyle =
      container === null ? null : window.getComputedStyle(container);
    return {
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      opacity: style.opacity,
      textTransform: style.textTransform,
      display: style.display,
      visibility: style.visibility,
      containerOpacity: containerStyle?.opacity ?? 'unknown',
      containerDisplay: containerStyle?.display ?? 'unknown',
      containerFontSize: containerStyle?.fontSize ?? 'unknown',
    };
  });
}

// ── Serving a mutated, RE-SEALED bundle ────────────────────────────────────

function sha256Hex(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

interface ManifestShape {
  readonly files: readonly { path: string; sha256: string; bytes: number }[];
}

/**
 * Rewrites the propagation frame and re-seals the manifest over the result.
 *
 * Re-sealing is the point rather than an inconvenience: the console refuses any bundle file
 * whose digest disagrees with the manifest, so a mutated fixture that renders at all has
 * passed the same integrity gate the untouched one does.
 */
async function serveMutatedBundle(
  page: Page,
  mutate: (data: Record<string, unknown>) => void,
): Promise<void> {
  const envelope = JSON.parse(
    Buffer.from(FRAME.frame.response.body_b64, 'base64').toString('utf8'),
  ) as Record<string, unknown>;
  mutate(envelope['data'] as Record<string, unknown>);

  const frameBytes = Buffer.from(
    JSON.stringify({
      ...FRAME.frame,
      response: {
        ...FRAME.frame.response,
        body_b64: Buffer.from(JSON.stringify(envelope), 'utf8').toString('base64'),
      },
    }),
    'utf8',
  );

  const manifest = readJson<ManifestShape>(join(BUNDLE_DIR, 'manifest.json'));
  const framePath = `frames/${FRAME.file}`;
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

test.describe('the fleet surface', () => {
  test('the fixture this spec reads is the one it thinks it reads', () => {
    // A guard, not a formality. If the payload lost its declination, every prominence
    // assertion below would compare one row with itself and pass.
    expect(ADOPTED, 'the bundle carries no adopted propagation row').toBeDefined();
    expect(DECLINED, 'the bundle carries no declined propagation row').toBeDefined();
    expect(DECLINED?.declination_kind).toBeTruthy();
    expect(PAYLOAD.data.conflicts.length).toBeGreaterThan(0);
  });

  test('renders one row per site, and every one of them equally', async ({ page }) => {
    await openPropagation(page);
    await expect(page.getByTestId('site-row')).toHaveCount(PAYLOAD.data.propagations.length);
    for (const row of await page.getByTestId('site-row').all()) {
      await expect(row).toHaveAttribute('data-prominence', 'equal');
    }
  });

  test('EQUAL PROMINENCE — the declined row is not whispered', async ({ page }) => {
    await openPropagation(page);

    const adopted = siteRow(page, siteKey(ADOPTED));
    const declined = siteRow(page, siteKey(DECLINED));
    await expect(adopted).toBeVisible();
    await expect(declined).toBeVisible();

    // 1. The same class attribute, character for character — there is no muted variant.
    expect(await declined.getAttribute('class')).toBe(await adopted.getAttribute('class'));

    // 2. The same COMPUTED type and opacity. This is what jsdom cannot see.
    expect(await prominenceOf(declined)).toEqual(await prominenceOf(adopted));

    // 3. The same rendered width for the row itself: a collapsed or inset declination
    //    would be visually secondary even with identical type.
    const adoptedBox = await adopted.boundingBox();
    const declinedBox = await declined.boundingBox();
    expect(adoptedBox).not.toBeNull();
    expect(declinedBox).not.toBeNull();
    expect(declinedBox?.width).toBeCloseTo(adoptedBox?.width ?? 0, 0);
    expect(declinedBox?.x).toBeCloseTo(adoptedBox?.x ?? 0, 0);

    // 4. The declined row renders MORE, not less.
    await expect(declined.getByTestId('site-declination')).toBeVisible();
  });

  test('the declination carries its kind, its constraint and its predicate', async ({ page }) => {
    await openPropagation(page);
    const declined = siteRow(page, siteKey(DECLINED));

    await expect(declined.getByTestId('site-declination')).toHaveAttribute(
      'data-declination-kind',
      DECLINED?.declination_kind ?? '',
    );
    await expect(declined.getByTestId('site-declination-kind')).toContainText(
      DECLINED?.declination_kind ?? '',
    );
    await expect(declined.getByTestId('site-declination-constraint')).toBeVisible();

    if (DECLINED?.declination_predicate_id != null) {
      await expect(declined.getByTestId('site-declination-predicate')).toContainText(
        DECLINED.declination_predicate_id,
      );
    }
  });

  test('the SLA clock is an instant with a named reference, never a countdown', async ({ page }) => {
    await openPropagation(page);
    const due = siteRow(page, siteKey(DECLINED)).getByTestId('site-due');
    await expect(due).toContainText(DECLINED?.due_by ?? '');
    await expect(due).toContainText(PAYLOAD.observed_at);
  });

  test('only_tightenings_travel is a stated law, with no filter control', async ({ page }) => {
    await openPropagation(page);
    await expect(page.getByTestId('tightenings-constraint')).toContainText(
      'only_tightenings_travel',
    );
    await expect(page.getByTestId('tightenings-law')).toContainText('not a representable row');
    for (const excluded of ['weaken', 'remove']) {
      await expect(page.locator(`[data-testid="tightenings-terms"] [data-term="${excluded}"]`)).toHaveAttribute(
        'data-admitted',
        'false',
      );
    }
    // A "show weakenings" toggle would advertise a state the database cannot hold.
    await expect(page.getByRole('checkbox')).toHaveCount(0);
  });

  test('every conflict shows base, ours and theirs', async ({ page }) => {
    await openPropagation(page);
    const first = PAYLOAD.data.conflicts[0];
    expect(first).toBeDefined();
    const conflict = page.locator(`[data-testid="conflict"][data-conflict="${first?.conflict_id}"]`);
    await expect(conflict.getByTestId('conflict-base')).toContainText(first?.base_digest ?? '');
    await expect(conflict.getByTestId('conflict-ours')).toContainText(first?.ours_digest ?? '');
    await expect(conflict.getByTestId('conflict-theirs')).toContainText(first?.theirs_digest ?? '');
  });

  test('names the resolution-memory column it cannot show', async ({ page }) => {
    await openPropagation(page);
    await expect(page.getByTestId('inheritance-limit')).toContainText('recalled_at');
  });

  test('no map, no globe, no canvas', async ({ page }) => {
    await openPropagation(page);
    // A decorative geography would rank sites by their distance from a viewport, which
    // means nothing about safety, and would spend the screen's whole visual budget on it.
    await expect(page.locator('[data-testid="propagation-surface"] canvas')).toHaveCount(0);
    await expect(page.locator('[data-testid="propagation-surface"] svg')).toHaveCount(0);
  });
});

test.describe('the EVIDENCE register', () => {
  test('moves nothing a screenshot could not reproduce', async ({ page }) => {
    await openPropagation(page);
    const before = await page.getByTestId('propagation-surface').innerHTML();
    await page.waitForTimeout(400);
    const after = await page.getByTestId('propagation-surface').innerHTML();
    expect(after).toBe(before);
  });

  test('loads no animation or GPU chunk', async ({ page }) => {
    // The runtime half of the register boundary. `tests/unit/propagation/register.test.ts`
    // walks the module graph; this watches what the browser actually fetched, which catches
    // a chunk arriving through a route the walker could not follow.
    const scripts: string[] = [];
    page.on('request', (request) => {
      if (request.resourceType() === 'script') scripts.push(request.url());
    });
    await openPropagation(page);
    const offending = scripts.filter((url) => /three|@react-three|framer-motion|motion-dom/i.test(url));
    expect(offending, `the fleet surface pulled ${offending.join(', ')}`).toEqual([]);
  });

  test('has no serious or critical accessibility violation', async ({ page }) => {
    await openPropagation(page);
    const results = await new AxeBuilder({ page })
      .include('[data-testid="propagation-surface"]')
      .analyze();
    const blocking = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    );
    expect(blocking.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
  });
});

test.describe('nothing is hardcoded', () => {
  test('renders whatever declination kind the re-sealed bundle carries', async ({ page }) => {
    const site = siteKey(DECLINED);
    const replacement = DECLINED?.declination_kind === 'waiver' ? 'mitigated' : 'waiver';

    await serveMutatedBundle(page, (data) => {
      const rows = data['propagations'] as Record<string, unknown>[];
      for (const row of rows) {
        if (row['site_code'] !== site && row['site_id'] !== site) continue;
        row['declination_kind'] = replacement;
        // `waiver_expires` requires an expiry, and the CONTRACT enforces it — a mutation
        // that broke the schema would be refused by the transport, which is the transport
        // working rather than the spec being clever.
        row['declination_expires_at'] = '2026-12-31T00:00:00.000Z';
      }
    });

    await openPropagation(page);
    await expect(siteRow(page, site).getByTestId('site-declination')).toHaveAttribute(
      'data-declination-kind',
      replacement,
    );
  });

  test('a re-sealed state change keeps equal prominence', async ({ page }) => {
    const site = siteKey(ADOPTED);
    await serveMutatedBundle(page, (data) => {
      const rows = data['propagations'] as Record<string, unknown>[];
      for (const row of rows) {
        if (row['site_code'] !== site && row['site_id'] !== site) continue;
        row['state'] = 'revoked';
        row['adopted_commit'] = null;
      }
    });

    await openPropagation(page);
    const changed = siteRow(page, site);
    await expect(changed).toHaveAttribute('data-state', 'revoked');
    await expect(changed).toHaveAttribute('data-prominence', 'equal');
  });
});
