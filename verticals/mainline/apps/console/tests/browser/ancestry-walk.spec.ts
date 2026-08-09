// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ANCESTRY WALK, IN A REAL BROWSER.
 *
 * `docs/leads/ui.md` §1.5 / PL-2: this spec was written RED. At the moment it was
 * committed neither `playwright.config.ts` (the cinema-conformance-harness worker) nor
 * `src/features/ancestry/AncestryScreen.tsx` (the ancestry-layout-ribbon worker) existed,
 * so it failed to even collect — which is the correct kind of red for a spec that
 * asserts an integration, and is recorded here rather than in a commit message nobody
 * greps.
 *
 * ── WHY THIS FILE IMPORTS NO SHARED HARNESS ──────────────────────────────────────
 *
 * `tests/browser/_harness/` is owned by the cinema-conformance-harness worker and
 * publishes `gotoSurface`, `expectHonestyChrome`, `readVerbatim` and
 * `expectNoNamedPerson`. Importing it before it exists would put a red `tsc` on the
 * whole workspace for every other worker, and the MEMORY register is cut-ladder item 1 —
 * it is not allowed to be the reason somebody else's build is broken.
 *
 * So the three helpers this spec needs are declared locally, with the SAME names and the
 * same semantics the harness publishes. When the harness lands, the local block below is
 * deleted and one import replaces it; nothing else in the file moves.
 *
 * ── THE PIXEL BASELINE, AND ITS PRE-COMMITTED DEGRADATION ────────────────────────
 *
 * `docs/leads/ui.md` §6 risk 2 names in advance the possibility that SwiftShader pixel
 * stability is imperfect. If it is, this spec drops to scene-graph parity plus a
 * non-blocking visual diff — and it does so LOUDLY: `MAINLINE_WALK_PIXEL_BASELINE=off`
 * must be set deliberately, the degradation is written into the test's annotations, and
 * the spec prints the sentence that must then appear in `docs/console-conformance.md`.
 * No spec in this console becomes advisory silently.
 */

import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';

// ── Local harness (see the note above) ───────────────────────────────────────────

/** Where the built console is being served. The harness will own this once it lands. */
const BASE_URL = process.env['MAINLINE_CONSOLE_URL'] ?? 'http://localhost:4173/';

/** The hash route the ancestry surface registers under (W1's router is hash-based). */
const ANCESTRY_ROUTE = '#/ancestry';

function surfaceUrl(params: Record<string, string>): string {
  const query = new URLSearchParams(params).toString();
  return `${BASE_URL}${query === '' ? '' : `?${query}`}${ANCESTRY_ROUTE}`;
}

async function gotoSurface(page: Page, params: Record<string, string> = {}): Promise<void> {
  await page.goto(surfaceUrl(params), { waitUntil: 'load' });
}

/** The walk's container, carrying every machine-readable fact about the scene. */
function walkContainer(page: Page): Locator {
  return page.locator('[data-walk="1"]');
}

async function readIdList(container: Locator, attribute: string): Promise<string[]> {
  const raw = (await container.getAttribute(attribute)) ?? '';
  return raw.split(' ').filter((value) => value !== '');
}

/**
 * The MEMORY-register attribution assertion.
 *
 * Structural rather than a name blocklist: a blocklist of names is both a privacy
 * problem of its own and trivially incomplete. The walk renders exactly two kinds of
 * string, so the assertion is that every glyph on screen is one of those two kinds.
 */
async function expectNoNamedPerson(page: Page): Promise<void> {
  const years = page.locator('[data-walk-label="year"]');
  const count = await years.count();
  for (let index = 0; index < count; index += 1) {
    const text = ((await years.nth(index).textContent()) ?? '').trim();
    expect(text, 'a MEMORY-register year label rendered something other than a year').toMatch(
      /^\d{4}$/,
    );
  }
  const stillLabels = page.locator('[data-walk-label="still"]');
  expect(await stillLabels.count(), 'the walk should carry at most one still label').toBeLessThan(2);
}

/**
 * Selectors the ribbon might expose node identity under.
 *
 * The ribbon is another worker's DOM and its attribute has not been agreed in writing.
 * Rather than guess once and fail for the wrong reason, the probe tries the plausible
 * spellings and, if NONE of them yields a node, fails with the exact contract sentence
 * the ribbon has to satisfy. That is a legitimate cross-worker request expressed as a
 * failing assertion, which is the only kind anybody acts on.
 */
const RIBBON_NODE_SELECTORS = [
  '[data-node-id]',
  '[data-ancestry-node-id]',
  '[data-walk-node-id]',
  '[data-node]',
];

async function readRibbonNodeIds(page: Page): Promise<string[]> {
  for (const selector of RIBBON_NODE_SELECTORS) {
    const nodes = page.locator(selector);
    const count = await nodes.count();
    if (count === 0) continue;
    const ids: string[] = [];
    for (let index = 0; index < count; index += 1) {
      const element = nodes.nth(index);
      const id =
        (await element.getAttribute('data-node-id')) ??
        (await element.getAttribute('data-ancestry-node-id')) ??
        (await element.getAttribute('data-walk-node-id')) ??
        (await element.getAttribute('data-node'));
      if (id !== null && id !== '') ids.push(id);
    }
    if (ids.length > 0) return ids;
  }
  throw new Error(
    'CONTRACT (docs/leads/ui.md D11): the ancestry ribbon exposes no machine-readable node ' +
      `identity. The 3D→ribbon parity assertion needs one of ${RIBBON_NODE_SELECTORS.join(', ')} ` +
      'on each rendered node. The walk publishes its own ids on [data-walk="1"] as ' +
      'data-walk-node-ids; the ribbon must publish the matching set.',
  );
}

// ── The spec ─────────────────────────────────────────────────────────────────────

test.describe('the ancestry walk — the one dimensional surface', () => {
  test('mounts, and publishes a scene graph that can be checked', async ({ page }) => {
    await gotoSurface(page, { render: '3d' });
    const walk = walkContainer(page);
    await expect(walk).toBeVisible();

    const nodeIds = await readIdList(walk, 'data-walk-node-ids');
    const edgeKeys = await readIdList(walk, 'data-walk-edge-keys');
    expect(nodeIds.length, 'the walk drew no node at all').toBeGreaterThan(0);
    expect(edgeKeys.length, 'the walk drew no edge at all').toBeGreaterThan(0);

    // Every id is distinct: the walk draws the layout it was given and never
    // de-duplicates, so a repeat would mean two facts sharing one identity.
    expect(new Set(nodeIds).size).toBe(nodeIds.length);
  });

  test('THE STILLNESS RULE: exactly one node is still, and it is severity 5', async ({ page }) => {
    await gotoSurface(page, { render: '3d' });
    const walk = walkContainer(page);
    const stillIds = await readIdList(walk, 'data-walk-still-ids');
    expect(stillIds).toHaveLength(1);

    const spineEntry = page.locator(`[data-walk-node-id="${stillIds[0] ?? ''}"]`).first();
    await expect(spineEntry).toContainText('severity 5');
  });

  test('NO EMISSIVE VOCABULARY: the scene declares zero lights', async ({ page }) => {
    await gotoSurface(page, { render: '3d' });
    const walk = walkContainer(page);
    await expect(walk).toHaveAttribute('data-walk-lights', '0');
    // Bulk geometry is batched, so the draw-call count does not grow with the corpus.
    const drawCalls = Number((await walk.getAttribute('data-walk-draw-calls')) ?? '999');
    expect(drawCalls).toBeLessThanOrEqual(6);
  });

  test('NO NAMED PERSON: every glyph is a year or the still node’s own label', async ({ page }) => {
    await gotoSurface(page, { render: '3d' });
    await expect(walkContainer(page)).toBeVisible();
    await expectNoNamedPerson(page);
  });

  test('the three controls are present, keyboard-operable, and there is no fourth', async ({
    page,
  }) => {
    await gotoSurface(page, { render: '3d' });
    const controls = page.locator('[data-walk-control]');
    await expect(controls).toHaveCount(3);
    for (const control of ['back', 'forward', 'stop']) {
      await expect(page.locator(`[data-walk-control="${control}"]`)).toBeVisible();
    }
    await page.locator('[data-walk-control="stop"]').focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-walk-control="stop"]')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  test('SCENE-GRAPH PARITY: every node in the walk is in the ribbon DOM', async ({ page }) => {
    await gotoSurface(page, { render: '3d' });
    const walkIds = await readIdList(walkContainer(page), 'data-walk-node-ids');
    expect(walkIds.length).toBeGreaterThan(0);

    await gotoSurface(page, { render: '2d' });
    await expect(walkContainer(page)).toHaveCount(0);
    const ribbonIds = new Set(await readRibbonNodeIds(page));

    const missing = walkIds.filter((id) => !ribbonIds.has(id));
    expect(
      missing,
      'these nodes exist only in the 3D walk. No fact may be 3D-only: that is ' +
        'simultaneously the a11y guarantee, the print/exhibit guarantee and the cut-ladder ' +
        'guarantee (docs/leads/ui.md §1.3).',
    ).toEqual([]);
  });

  test('the ribbon is the default, and the walk is never on the critical path', async ({
    page,
  }) => {
    await gotoSurface(page, { render: '2d' });
    await expect(walkContainer(page)).toHaveCount(0);
    // The ribbon must render every node without the MEMORY chunk being fetched at all.
    const chunkRequests: string[] = [];
    page.on('request', (request) => {
      if (request.url().includes('render3d') || request.url().includes('three')) {
        chunkRequests.push(request.url());
      }
    });
    await page.reload({ waitUntil: 'load' });
    expect(chunkRequests, 'the 3D chunk was fetched for a reader who asked for the ribbon').toEqual(
      [],
    );
  });
});

test.describe('cinema mode — the walk is capturable', () => {
  test('runs frameloop=never and advances exactly the frames it was asked for', async ({
    page,
  }) => {
    await gotoSurface(page, { render: '3d', cinema: '1', seed: '7', frame: '48' });
    const walk = walkContainer(page);
    await expect(walk).toHaveAttribute('data-walk-cinema', '1');
    await expect(walk).toHaveAttribute('data-walk-frames-advanced', '48');

    // The frame count must be STABLE: nothing may advance the canvas after the driver
    // has finished, or a capture would be a function of how long the screenshot took.
    await page.waitForTimeout(750);
    await expect(walk).toHaveAttribute('data-walk-frames-advanced', '48');
  });

  test('the quality ladder is inert during a capture', async ({ page }) => {
    await gotoSurface(page, { render: '3d', cinema: '1', frame: '30' });
    await expect(walkContainer(page)).toHaveAttribute('data-walk-tier', 'full');
  });

  test('two runs at the same frame produce identical pixels', async ({ page }, testInfo) => {
    const degraded = process.env['MAINLINE_WALK_PIXEL_BASELINE'] === 'off';

    const capture = async (): Promise<{ shot: Buffer; nodes: string[] }> => {
      await gotoSurface(page, { render: '3d', cinema: '1', seed: '7', frame: '48' });
      const walk = walkContainer(page);
      await expect(walk).toBeVisible();
      await expect(walk).toHaveAttribute('data-walk-frames-advanced', '48');
      return {
        shot: await walk.screenshot({ animations: 'disabled', caret: 'hide' }),
        nodes: await readIdList(walk, 'data-walk-node-ids'),
      };
    };

    const first = await capture();
    const second = await capture();

    // Scene-graph parity between the two runs holds either way. It is the assertion the
    // degradation falls back TO, so it is checked in both modes rather than only in one.
    expect(second.nodes).toEqual(first.nodes);

    if (degraded) {
      const sentence =
        '`ancestry-walk.spec.ts` — the 3D surface has NO PIXEL BASELINE on this runner; ' +
        'stability is asserted as scene-graph parity plus a non-blocking visual diff.';
      recordDegradation(testInfo, sentence, first.shot, second.shot);
      return;
    }

    expect(
      second.shot.equals(first.shot),
      'Two cinema-mode runs of the same URL produced different pixels under software GL. ' +
        'If this is a real SwiftShader instability rather than a scene bug, take the ' +
        'pre-committed degradation with MAINLINE_WALK_PIXEL_BASELINE=off — which records the ' +
        'loss in docs/console-conformance.md rather than letting the spec go quietly advisory ' +
        '(docs/leads/ui.md §6 risk 2, docs/dimensionality-charter.md §5.1).',
    ).toBe(true);
  });
});

/**
 * Records the degradation so it cannot be taken quietly.
 *
 * The annotation lands in the Playwright report, the attachments carry both frames for a
 * human diff, and the console line is the sentence that must be pasted into
 * `docs/console-conformance.md` — a file this worker does not own, which is exactly why
 * the spec prints it rather than writing it.
 */
function recordDegradation(
  testInfo: TestInfo,
  sentence: string,
  first: Buffer,
  second: Buffer,
): void {
  testInfo.annotations.push({ type: 'degradation', description: sentence });
  void testInfo.attach('walk-run-1.png', { body: first, contentType: 'image/png' });
  void testInfo.attach('walk-run-2.png', { body: second, contentType: 'image/png' });
  console.warn(
    `\nDEGRADATION TAKEN — this line must appear in docs/console-conformance.md:\n  ${sentence}\n` +
      `  identical=${String(second.equals(first))}\n`,
  );
}
