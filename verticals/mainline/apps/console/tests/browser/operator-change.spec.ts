// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * W7 — THE MANAGEMENT-OF-CHANGE SCREEN, AND THE ABSENCE IT HAS TO NAME.
 *
 * Screen two is the harder honesty problem in this wave, and `operator-systems-plan.md` R11
 * is the ruling that makes it tractable:
 *
 *   > **No route in `ROUTES` yields the change request's blocking-check id (M10)**, and
 *   > taking that id from a document would be a hardcoded literal of exactly the kind
 *   > `subjects.py:24-27` argues against. So screen two renders the real `change_request`
 *   > payload... and an **approve control rendered disabled with the obligation named as the
 *   > reason**. Beside it, the **404 route table** the deployment itself returns, as the
 *   > evidence for the absence. ... **A hardcoded `dec0de00-000d-…` is forbidden.**
 *
 * A screen that quietly filled that gap would be the single most damaging thing in this
 * demonstration, because it would be indistinguishable from working. So the assertions below
 * are mostly about what is NOT there and how the screen says so: the 404 is fetched and its
 * verbatim body is on screen, the two absent routes are named, the approve control is inert
 * and gives its reason, and the proposed clause text is typed on camera rather than loaded
 * from a column that does not exist (R12).
 *
 * Same rules as the rest of W7's tier: no `page.route`, no stub, no fixture standing in for
 * the kernel. `scripts/deploy/local_furl.py` runs the real handler over the local
 * CockroachDB node and every byte asserted here came off a socket during the run.
 */

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const CHANGE_URL = '/operator.html#/change';

/**
 * OSHA 1910.119(l)(2) — the five things a management-of-change procedure must address.
 * Written out here, not imported from the module that renders them: a checklist that reads
 * its own answer key asserts nothing.
 */
const OSHA_FIVE: readonly string[] = [
  'The technical basis for the proposed change',
  'Impact of change on safety and health',
  'Modifications to operating procedures',
  'Necessary time period for the change',
  'Authorization requirements for the proposed change',
];

/** The IChemE Safety Centre's five-step Management of Change model, in order. */
const ICHEME_FIVE: readonly string[] = ['Initiate', 'Screen', 'Review', 'Approve', 'Implement'];

interface Subjects {
  readonly cr_id: string;
  readonly check_id: string;
  readonly clause_uuid: string;
  readonly commit_id: string;
  readonly subjects: {
    readonly change_request: {
      readonly external_ref: string;
      readonly ref_name: string;
      readonly state: string;
    };
  };
}

async function subjectsOf(page: Page): Promise<Subjects> {
  const response = await page.request.get('/v1/demo/subjects');
  expect(response.status()).toBe(200);
  return ((await response.json()) as { data: Subjects }).data;
}

/**
 * Refuses to continue on a read the kernel throttled.
 *
 * A `429 rate_limited` is a real, correct, transient answer from
 * `mainline_demo_api.ratelimit`, and the screen reports it honestly instead of rendering an
 * empty form — which is exactly right, and which turns every assertion below into an
 * unhelpful "element not found". So it is caught here and named. Raise the four
 * `MAINLINE_RATE_*` variables on the emulator (playwright.config.ts does when it starts one).
 */
async function refuseThrottledReads(page: Page): Promise<void> {
  const failure = page.locator('[role="status"]').filter({ hasText: 'did not read' });
  if ((await failure.count()) === 0) return;
  throw new Error(
    'a read came back throttled or failed, so the screen has nothing on it:\n  ' +
      ((await failure.first().textContent()) ?? '(no text)') +
      '\nThis is the emulator refusing, not the product failing. Start local_furl with ' +
      'MAINLINE_RATE_GLOBAL_RPS / MAINLINE_RATE_IP_RPS raised, as playwright.config.ts does.',
  );
}

async function openChange(page: Page): Promise<void> {
  await page.goto(CHANGE_URL, { waitUntil: 'networkidle' });
  await expect(page.locator('.moc')).toBeVisible();
  await refuseThrottledReads(page);
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// §1 · IT READS THE RECORD IT CAN ACTUALLY READ
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the change request, from the kernel', () => {
  test('is addressed from /v1/demo/subjects, never from a literal', async ({ page }) => {
    const paths: string[] = [];
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith('/v1/')) paths.push(`${request.method()} ${path}`);
    });

    const world = await subjectsOf(page);
    await openChange(page);
    await page.waitForLoadState('networkidle');

    expect(paths[0]).toBe('GET /v1/demo/subjects');
    expect(paths).toContain(`GET /v1/change-requests/${world.cr_id}`);
    expect(paths).toContain(
      `GET /v1/clauses/${world.clause_uuid}/versions/${world.commit_id}`,
    );
    // R11's escape hatch, used honestly: the disposition lattice is rendered ONLY because a
    // check id came back from a live read. The id requested must be the one the kernel named.
    expect(paths).toContain(`GET /v1/checks/${world.check_id}/disposition`);
  });

  test('renders the reference, the refs and the state chip verbatim', async ({ page }) => {
    const world = await subjectsOf(page);
    await openChange(page);

    await expect(page.locator('.moc-ref')).toHaveText(world.subjects.change_request.external_ref);
    await expect(page.locator('.moc-branch')).toContainText(world.subjects.change_request.ref_name);
    // R10: the enum is not translated and the chip says which column it is.
    const chip = page.locator('.moc-statechip');
    await expect(chip).toContainText('mainline.change_request.state');
    await expect(chip).toContainText(world.subjects.change_request.state);
  });

  test('shows the CHECK constraints the record is held to, with their predicates', async ({
    page,
  }) => {
    await openChange(page);
    const table = page.locator('.moc-table').first();
    await expect(table.locator('caption')).toContainText('CHECK constraints');
    // Four, as `mainline.change_request`'s DDL declares them.
    await expect(page.locator('.moc-pred')).toHaveCount(4);
    await expect(page.locator('.moc-pred').first()).toContainText('CHECK');
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §2 · THE ABSENCE, NAMED — R11
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('what this deployment cannot do, said out loud', () => {
  test('the two missing routes are named, and named as templates', async ({ page }) => {
    await openChange(page);
    const missing = await page.$$eval('li.moc-route-missing', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(missing).toEqual([
      '/v1/change-requests/{cr_id}/blocking-checks',
      '/v1/change-requests/{cr_id}/merge',
    ]);
  });

  test('the 404 is REALLY FETCHED, and its verbatim body is on screen', async ({ page }) => {
    const world = await subjectsOf(page);

    let status = 0;
    let body = '';
    page.on('response', (response) => {
      if (new URL(response.url()).pathname === `/v1/change-requests/${world.cr_id}/blocking-checks`) {
        status = response.status();
        void response
          .text()
          .then((text) => {
            body = text;
          })
          .catch(() => {
            /* the assertion below reports the empty body */
          });
      }
    });

    await openChange(page);
    await page.waitForLoadState('networkidle');

    // The absence is EVIDENCE, and evidence is fetched. A screen that asserted the route was
    // missing without asking would be asserting about a document.
    expect(status, 'the screen never asked for the route it claims does not exist').toBe(404);
    expect(body).not.toBe('');

    const shown = await page.locator('pre[aria-label="verbatim 404 response body"]').innerText();
    expect(shown.trim()).toBe(body.trim());
  });

  test('the deployment’s own route table is on screen, and it is the whole table', async ({
    page,
  }) => {
    await openChange(page);
    // 17 routes, declared by `app.py` ROUTES and printed by the 404 body itself, plus the
    // two the screen adds to name what is NOT there — which is why the two sets are counted
    // separately rather than together.
    expect(await page.locator('li.moc-route:not(.moc-route-missing)').count()).toBe(17);
    expect(await page.locator('li.moc-route-missing').count()).toBe(2);
    await expect(page.locator('.moc-routes')).toContainText('/v1/demo/gate-run');
  });

  test('the approve control is inert, and it names the obligation as the reason', async ({
    page,
  }) => {
    await openChange(page);

    const approve = page.locator('button.moc-approve');
    await expect(approve).toBeDisabled();
    await expect(approve).toHaveAttribute('aria-disabled', 'true');
    await expect(approve).toHaveAttribute('aria-describedby', 'moc-approve-reason');
    // The reason is the obligation, in the operator's language, with the count from the read.
    await expect(page.locator('#moc-approve-reason')).toContainText('blocking obligation');
    await expect(page.locator('#moc-approve-reason')).toContainText('Cannot approve');
  });

  test('pressing the approve control does nothing over the network', async ({ page }) => {
    await openChange(page);
    await page.waitForLoadState('networkidle');

    const after: string[] = [];
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith('/v1/')) after.push(`${request.method()} ${path}`);
    });
    // A disabled button cannot be clicked by a user, so the claim is tested the way an
    // over-eager script would break it: dispatch the event directly.
    await page.locator('button.moc-approve').dispatchEvent('click');
    await page.waitForTimeout(500);
    expect(after, 'the disabled approve control is wired to something').toEqual([]);
  });

  test('names the blocking check’s own row as the thing it cannot show', async ({ page }) => {
    await openChange(page);
    const text = await page.locator('.moc').innerText();
    expect(text).toContain('does NOT return');
    // And it does not invent one. `dec0de00-000d` is the id a builder would be tempted to
    // paste out of a design document; R11 forbids it and this is the assertion that enforces it.
    expect(text).not.toContain('dec0de00-000d');
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §3 · THE STANDARDS RIBBON AND THE OSHA HEADINGS — fidelity items 9-10
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the industry frame around our record', () => {
  test('renders the OSHA five headings, in order', async ({ page }) => {
    await openChange(page);
    const headings = await page.$$eval('.moc-section-heading', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(headings).toEqual(OSHA_FIVE);
    // Each cites where it came from rather than presenting the standard as ours.
    expect(await page.locator('.moc-section-cite').count()).toBe(OSHA_FIVE.length);
  });

  test('renders the IChemE five-step ribbon with our enum BESIDE it, never AS it', async ({
    page,
  }) => {
    await openChange(page);
    const steps = await page.$$eval('.moc-step:not(.moc-step-trailer)', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(steps).toEqual(ICHEME_FIVE);

    // R11: the ribbon is orientation, not a claim that our state machine is theirs. The
    // provenance note has to say so, and no ribbon step may be marked current.
    const ribbonNote = page.locator('.moc-ribbon-wrap .moc-provenance').first();
    await expect(ribbonNote).toContainText('IChemE');
    await expect(ribbonNote).toContainText('No step');
    expect(await page.locator('.moc-step[aria-current]').count()).toBe(0);
  });

  test('shows the authorisation matrix scaled to risk', async ({ page }) => {
    await openChange(page);
    const lattice = page.locator('.moc-table').last();
    await expect(lattice.locator('caption')).toContainText('Dispositions legal at virulence');
    expect(await lattice.locator('tbody tr').count()).toBeGreaterThan(0);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §4 · R12 — NO PROPOSED CLAUSE TEXT IS FABRICATED
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the proposed wording is typed on camera', () => {
  test('the box starts empty and says why nothing was loaded into it', async ({ page }) => {
    await openChange(page);
    const proposed = page.locator('#moc-proposed-text');
    await expect(proposed).toHaveValue('');
    await expect(proposed).toBeEditable();
    // `mainline.change_request` has no column for it (0051_change_request.sql), and the
    // screen says exactly that rather than leaving an ambiguous blank.
    const note = page.locator('.moc-typed-note').filter({ hasText: 'proposed text' });
    await expect(note.first()).toContainText('no column');
  });

  test('the clause of record is the database’s, verbatim, with its identity', async ({ page }) => {
    const world = await subjectsOf(page);
    await openChange(page);
    const quote = page.locator('blockquote.moc-quote').first();
    // The seed's own SYNTHETIC prefix survives — we do not launder the marker out.
    await expect(quote).toContainText('SYNTHETIC —');
    await expect(quote).toContainText('stored energy shall be isolated');
    await expect(page.locator('.moc-provenance').filter({ hasText: world.commit_id })).toHaveCount(1);
  });

  test('the diff is computed in this browser, over one real string and one typed one', async ({
    page,
  }) => {
    await openChange(page);
    await page.waitForLoadState('networkidle');

    const typed = 'SYNTHETIC TYPED — stored energy shall be isolated by any person.';
    const after: string[] = [];
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith('/v1/')) after.push(path);
    });

    await page.locator('#moc-proposed-text').fill(typed);
    await page.locator('button.moc-compare').click();

    const diff = page.locator('.moc-diff').first();
    await expect(diff).toBeVisible();
    // Labelled as what it is. R12: the comparison is ours, computed here, and never
    // presented as something the kernel returned.
    await expect(diff).toHaveAttribute('aria-label', /computed in this browser/);
    await expect(diff).toContainText('TYPED');
    await expect(diff).toContainText('stored energy shall be isolated');

    await page.waitForTimeout(300);
    expect(after, 'the client-side comparison went to the network').toEqual([]);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §5 · RAW PAYLOADS, LEGIBILITY, ACCESSIBILITY
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('what a judge in devtools cross-checks', () => {
  test('every raw drawer holds a response body byte for byte (R18)', async ({ page }) => {
    const bodies = new Map<string, string>();
    page.on('response', (response) => {
      const path = new URL(response.url()).pathname;
      if (!path.startsWith('/v1/')) return;
      void response
        .text()
        .then((text) => {
          bodies.set(path, text);
        })
        .catch(() => {
          /* reported by the assertion below */
        });
    });

    await openChange(page);
    await page.waitForLoadState('networkidle');

    const summaries = await page.$$eval('details > summary.moc-label', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(summaries.length).toBeGreaterThanOrEqual(4);
    for (const summary of summaries) expect(summary).toContain('Raw payload');

    const drawn = await page.$$eval('details pre.moc-raw', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(drawn.length).toBe(summaries.length);

    const served = [...bodies.values()].map((text) => text.trim());
    for (const text of drawn) {
      expect(
        served,
        'a raw drawer shows text that is not verbatim any response this page received. ' +
          'src/operator/kernel/raw.ts is explicit that the body must be Exchange.raw and never ' +
          'JSON.stringify(JSON.parse(raw)) — a re-serialised payload looks identical to a judge ' +
          'and no longer diffs against the Network panel.',
      ).toContain(text);
    }
  });

  test('the must-read strings clear the 480 test at the filming geometry', async ({ page }) => {
    await openChange(page);
    const floor = 0.02 * 576;
    const failures: string[] = [];
    for (const selector of ['.moc-ref', '.moc-statechip', '.moc-section-heading', '#moc-approve-reason', '.moc-quote']) {
      const sizes = await page.$$eval(selector, (nodes) =>
        nodes.map((node) => ({
          size: Number.parseFloat(getComputedStyle(node).fontSize),
          text: node.textContent.trim().slice(0, 40),
        })),
      );
      expect(sizes.length, `${selector} matched nothing`).toBeGreaterThan(0);
      for (const { size, text } of sizes) {
        if (size < floor) {
          failures.push(`${selector} renders "${text}" at ${size.toFixed(2)} px (floor ${floor})`);
        }
      }
    }
    expect(failures, `480 test failures on the change screen:\n  ${failures.join('\n  ')}`).toEqual(
      [],
    );
  });

  test('every interactive control has an accessible name', async ({ page }) => {
    await openChange(page);
    const unnamed = await page.$$eval(
      'button, a[href], input, select, textarea, [role="button"]',
      (nodes) =>
        nodes
          .filter((node) => {
            const label = node.getAttribute('aria-label');
            if (label !== null && label.trim() !== '') return false;
            if (node.getAttribute('aria-labelledby') !== null) return false;
            if ((node as HTMLInputElement).labels?.length) return false;
            return node.textContent.trim() === '';
          })
          .map((node) => `${node.tagName.toLowerCase()}.${node.getAttribute('class') ?? ''}`),
    );
    expect(unnamed).toEqual([]);
  });

  test('has no CRITICAL accessibility violation', async ({ page }) => {
    await openChange(page);
    const results = await new AxeBuilder({ page }).analyze();
    const critical = results.violations.filter((violation) => violation.impact === 'critical');
    expect(
      critical.map((violation) => `${violation.id} — ${String(violation.nodes[0]?.target)}`),
    ).toEqual([]);
  });

  /**
   * Ratchet, not amnesty. Every entry names the rule, what was measured and who owns it; a
   * NEW serious or moderate finding fails this test.
   */
  test('records the serious and moderate findings, and refuses any new one', async ({ page }) => {
    await openChange(page);
    const results = await new AxeBuilder({ page }).analyze();
    const known = new Set([
      // OWNER W1 (src/operator/chrome/tokens.css): .cw-rail__name is #5c636b on #14171b =
      // 2.95:1 against a 4.5:1 requirement.
      'color-contrast',
      // OWNER W1 (src/operator/chrome/Watermark.ts): the watermark sits outside every landmark.
      'region',
      // OWNER W6 (src/operator/change/change.css + absence.ts): .moc-routes and the verbatim
      // 404 <pre> scroll but are not focusable, so a keyboard user cannot reach the evidence
      // for the absence — which is the one thing on this screen that has to be checkable.
      // `tabindex="0"` plus the existing aria-label on each closes it.
      'scrollable-region-focusable',
    ]);
    const unexpected = results.violations
      .filter((violation) => violation.impact === 'serious' || violation.impact === 'moderate')
      .map((violation) => violation.id)
      .filter((id) => !known.has(id))
      .sort();
    expect(unexpected, `new accessibility violation(s): ${unexpected.join(', ')}`).toEqual([]);
  });
});
