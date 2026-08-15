// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * W7 — THE PERMIT-TO-WORK SCREEN, IN A REAL BROWSER, AGAINST A REAL KERNEL.
 *
 * The subject is `CONTROL OF WORK` — the software a site supervisor works in. MAINLINE is
 * not named on it. You see MAINLINE by seeing what it stops.
 *
 * Everything here runs against `scripts/deploy/local_furl.py`, which imports the real
 * `mainline_demo_api.app.handler` and answers out of the local CockroachDB node. **No route
 * is intercepted, no response is stubbed and no payload is injected anywhere in this file.**
 * Every SQLSTATE, every constraint name, every timestamp and every count asserted below was
 * produced by the database during the test run. A harness that mocked the kernel would be
 * mocking the exact layer the first judging criterion scores.
 *
 * ── WHAT THIS FILE ASSERTS, AND WHY EACH ONE IS HERE ─────────────────────────────────
 *
 *   §1  The screen addresses subjects it was TOLD about (`GET /v1/demo/subjects`), never a
 *       UUID compiled into it. A literal in a source file is a demo that keeps working
 *       after the world it describes has gone.
 *   §2  The fidelity checklist from `operator-systems-plan.md` §5 — the ten things an
 *       industry judge checks and a fake screen normally gets wrong.
 *   §3  The STORE → RETRIEVE → ACT card. The hackathon's whole theme is agentic memory and
 *       the brief's third bullet is the one we are most at risk of failing: the loop has to
 *       be VISIBLE, not narrated.
 *   §4  The refusal experience — a banner over a locked action (R15), two stacked registers,
 *       never a modal, and beat 4 shown so the film does not end on a refusal (R16).
 *   §5  Honesty of absence — R9's typed fields, the not-carried PPE row, the omitted
 *       extension row, the unsigned hand-back. Absence has to look different from emptiness.
 *   §6  THE 480 TEST (r5-craft §2.1) at the filming geometry, and the accessibility floor a
 *       browser can measure but jsdom cannot.
 *
 * ── THE FILMING GEOMETRY IS THE TEST GEOMETRY ────────────────────────────────────────
 *
 * `playwright.config.ts` uses 1024 x 576 CSS at `deviceScaleFactor: 2.5`, which renders a
 * 2560 x 1440 frame — r5-craft's "175-200 % zoom at 1440p", pushed to 250 % because W7
 * measured the SQLSTATE value, the constraint name, the reason set and the mandatory
 * disclosure line all BELOW the 2 %-of-frame-height floor at 200 %. §6 pins that choice with
 * a measurement so a later viewport change cannot silently make the video illegible.
 */

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const OPERATOR_URL = '/operator.html#/permit';

/** 2 % of the frame height, expressed in CSS px at the configured viewport (r5-craft §2.1). */
const FRAME_HEIGHT_CSS = 576;
const LEGIBILITY_FLOOR_CSS_PX = 0.02 * FRAME_HEIGHT_CSS;

/**
 * The strings that MUST be readable in the video, by the selector that carries each.
 *
 * This list is r5-craft §8's checklist turned into selectors: the SQLSTATE frame, the `mus`
 * block, the red refusal treatment, the state chip and the sentence that makes the reveal
 * honest. Every one of them is a thing the founder will say out loud while it is on screen.
 */
const MUST_BE_READABLE: readonly { readonly what: string; readonly selector: string }[] = [
  { what: 'the permit reference', selector: '.cow-ref' },
  { what: 'the state chip (verbatim enum)', selector: '.cow-state-chip' },
  { what: 'the refusal headline', selector: '.cow-refusal__headline' },
  { what: 'the SQLSTATE and every fact beside it', selector: '.cow-refusal__value' },
  { what: 'the reason set (mus)', selector: 'dd[data-row="mus"] li' },
  { what: 'the mandatory disclosure line', selector: '[data-disclosure="line"]' },
  { what: 'the admission headline', selector: '.cow-beat__headline' },
  { what: 'the verdict', selector: '.cow-run__headline' },
  { what: 'the synthetic watermark', selector: '[data-cw="watermark"]' },
  { what: 'the origin the page was served from', selector: '[data-cw-field="origin"]' },
];

/** The seeded world, as `GET /v1/demo/subjects` reports it. Read, never written down. */
interface Subjects {
  readonly permit_id: string;
  readonly cr_id: string;
  readonly clause_uuid: string;
  readonly run_id: string;
  readonly receipt_id: string;
  readonly subjects: {
    readonly permit: { readonly external_ref: string; readonly state: string; readonly open_blocking: number };
    readonly event: { readonly external_ref: string; readonly severity_gate: number };
    readonly exposure_receipt: { readonly receipt_id: string };
  };
}

async function subjectsOf(page: Page): Promise<Subjects> {
  const response = await page.request.get('/v1/demo/subjects');
  expect(response.status(), 'GET /v1/demo/subjects did not answer 200').toBe(200);
  const envelope = (await response.json()) as { data: Subjects };
  return envelope.data;
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

async function openPermit(page: Page): Promise<void> {
  await page.goto(OPERATOR_URL, { waitUntil: 'networkidle' });
  await expect(page.locator('[data-screen="permit"]')).toBeVisible();
  await refuseThrottledReads(page);
}

async function pressIssue(page: Page): Promise<void> {
  const waitForRun = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/v1/demo/gate-run',
  );
  await page.locator('[data-action="issue"]').click();
  await waitForRun;
  await expect(page.locator('[data-beat]').first()).toBeVisible();
}

async function revealAll(page: Page): Promise<void> {
  for (let guard = 0; guard < 8; guard += 1) {
    const advance = page.locator('[data-action="advance"]');
    if ((await advance.count()) === 0) return;
    await advance.first().click();
  }
  throw new Error('the advance control never went away; that is a loop, not a reveal.');
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// §1 · NOTHING IS ADDRESSED BY A LITERAL
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the screen addresses what the kernel told it to address', () => {
  test('reads /v1/demo/subjects first and then the permit it named', async ({ page }) => {
    const paths: string[] = [];
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith('/v1/')) paths.push(`${request.method()} ${path}`);
    });

    const world = await subjectsOf(page);
    await openPermit(page);
    await page.waitForLoadState('networkidle');

    expect(paths[0]).toBe('GET /v1/demo/subjects');
    expect(paths).toContain(`GET /v1/permits/${world.permit_id}`);
    expect(paths).toContain(`GET /v1/permits/${world.permit_id}/blocking-checks`);
    // The reads that make the memory loop showable, addressed the same way.
    expect(paths).toContain(`GET /v1/recall-runs/${world.run_id}`);
    expect(paths).toContain(`GET /v1/receipts/${world.receipt_id}`);
  });

  test('renders the reference, the state and the counter the API reported', async ({ page }) => {
    const world = await subjectsOf(page);
    await openPermit(page);

    await expect(page.locator('.cow-ref')).toHaveText(world.subjects.permit.external_ref);
    // R10: the enum is not translated. `dispositioned` is a real value of
    // `mainline.subject_state` and it renders as the database spells it.
    await expect(page.locator('.cow-state-chip')).toContainText(world.subjects.permit.state);
    await expect(page.locator('.cow-actionbar__standing')).toContainText(
      String(world.subjects.permit.open_blocking),
    );
  });

  test('the current state is marked in the lattice, and the rest are not', async ({ page }) => {
    const world = await subjectsOf(page);
    await openPermit(page);
    const current = page.locator('.cow-state-value[data-current="true"]');
    await expect(current).toHaveCount(1);
    await expect(current).toHaveText(world.subjects.permit.state);
    // Fidelity item 6: suspension is present as a state distinct from closed.
    const lattice = await page.$$eval('.cow-state-value', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(lattice).toContain('suspended');
    expect(lattice).toContain('closed');
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §2 · THE FIDELITY CHECKLIST — operator-systems-plan.md §5
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the ten things an industry judge checks', () => {
  test('1-2 · reference number, verbatim status chip, and a validity window', async ({ page }) => {
    await openPermit(page);
    await expect(page.locator('.cow-ref')).toBeVisible();
    await expect(page.locator('.cow-state-chip')).toBeVisible();
    const facts = page.locator('.cow-hdr-facts');
    await expect(facts).toContainText('Valid from');
    await expect(facts).toContainText('Expires');
  });

  test('3 · isolation is a linked obligation with an identity, not a checkbox', async ({ page }) => {
    await openPermit(page);
    const status = page.locator('[data-row="status"]');
    await expect(status).toBeVisible();
    // A checkbox has no id, no severity and no origin. This one has all three.
    await expect(page.locator('[data-row="status"] .hz-state-word')).toHaveText('OPEN');
    expect(await page.locator('input[type="checkbox"]').count()).toBe(0);
  });

  test('4-5 · HSG250 Table 1 role names, and an UNSIGNED hand-back row', async ({ page }) => {
    await openPermit(page);
    const roles = await page.$$eval('.cow-sig-role', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(roles.join(' | ')).toContain('Issuing authority');
    expect(roles.join(' | ')).toContain('Performing authority');
    // R14: `exposure_receipt.actor_sub` means WHO THE OBLIGATION WAS SHOWN TO. It is the
    // acceptor, and it is given no issuing role.
    expect(roles.join(' | ')).toContain('Acceptor');
    expect(roles.join(' | ')).not.toContain('Approver');

    // The hand-back (Figure 1 element 12) is present and unsigned, which is the whole point:
    // a permit that shows only the signatures it has is a permit with no outstanding work.
    const handBack = page.locator('[data-figure1-element="12"]');
    await expect(handBack).toHaveAttribute('data-signed', 'false');
    await expect(handBack.locator('[data-unsigned="true"]').first()).toContainText('unsigned');
  });

  test('7-8 · a display copy affordance, and a cold-work permit type the operator chose', async ({
    page,
  }) => {
    await openPermit(page);
    await expect(page.locator('[data-action="display-copy"]')).toBeVisible();

    // R9 / §7: no column carries a permit type, so it is an operator-typed SELECTION and it
    // says so. A hard-coded "cold work" presented as data would be the same class of act as
    // reshaping a seed to match a constant.
    const type = page.locator('#cow-permit-type');
    await expect(type).toHaveValue('cold-work');
    await expect(page.locator('[data-figure1-element="2"] .cow-hint').first()).toContainText(
      'selected on this device',
    );
    // Blue-edged, not red. The edge is decoration and carries no meaning a reader can lose.
    const edge = page.locator('.cow-edge');
    await expect(edge).toHaveAttribute('aria-hidden', 'true');
    expect((await edge.textContent())?.trim() ?? '').toBe('');
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §3 · THE MEMORY LOOP, VISIBLE — the brief's third bullet
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('store → retrieve → act, on screen', () => {
  test('shows all three rows, in operator language, from three different tables', async ({
    page,
  }) => {
    const world = await subjectsOf(page);
    await openPermit(page);

    // R17: RECALLED / SHOWN TO / STATUS, sourced from recall_run, exposure_receipt and
    // blocking_check.open. Past tense for the recall, present tense only for the
    // re-derivation on the press.
    const recalled = page.locator('[data-row="recalled"]');
    const shownTo = page.locator('[data-row="shown-to"]');
    const status = page.locator('[data-row="status"]');
    await expect(recalled).toBeVisible();
    await expect(shownTo).toBeVisible();
    await expect(status).toBeVisible();

    await expect(recalled).toContainText(world.run_id);
    await expect(shownTo).toContainText('demo.signer');
    await expect(status).toContainText('OPEN');
  });

  test('claims no embedding, no similarity and no vector — because there are none', async ({
    page,
  }) => {
    await openPermit(page);
    const text = (await page.locator('[data-screen="permit"]').innerText()).toLowerCase();
    // r6-honesty A5/A5.1 and r2-memory warning 4. There are no cues, no candidate rows and
    // no embeddings in this world; a screen that implied otherwise would be inventing the
    // one thing the hackathon theme is about.
    for (const forbidden of ['embedding', 'similarity', 'cosine', 'vector search', 'semantic search']) {
      expect(text, `the memory card claims "${forbidden}", which this system does not do`).not.toContain(
        forbidden,
      );
    }
  });

  test('names the precursor incident the obligation descends from', async ({ page }) => {
    await openPermit(page);
    const world = await subjectsOf(page);
    await expect(page.locator('.hz-precursor')).toContainText(world.subjects.event.external_ref);
    await expect(page.locator('.hz-sev')).toContainText(String(world.subjects.event.severity_gate));
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §4 · THE REFUSAL, AND THE ADMISSION AFTER IT
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the refusal experience', () => {
  test('is a banner over a locked action, never a modal (R15)', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);

    const banner = page.locator('.cow-refusal').first();
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('role', 'alert');
    // r3-operator §2.5: not one vendor's control-of-work product uses a modal for this.
    expect(await page.locator('dialog, [role="dialog"], [role="alertdialog"]').count()).toBe(0);
    // The action is locked, and the lock says which write was refused.
    await expect(page.locator('[data-action="issue"]')).toBeDisabled();
    await expect(page.locator('.cow-actionbar__lock')).toContainText('refused this write');
  });

  test('renders two stacked registers: the supervisor’s, then the database’s', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);

    const banner = page.locator('.cow-refusal').first();
    await expect(banner.locator('.cow-refusal__operator')).toContainText('PERMIT NOT ISSUED');
    const database = banner.locator('.cow-refusal__database');
    await expect(database).toContainText('The database refused this write');
    await expect(banner.locator('dd[data-row="sqlstate"]')).toHaveText('23514');
    await expect(banner.locator('dd[data-row="constraint"]')).toContainText(
      'gate_closed_when_issued',
    );
    // The CHECK predicate is shown, and the screen says where it got it from rather than
    // pretending a field carried it.
    await expect(banner.locator('dd[data-row="predicate"]')).toContainText('open_blocking');
    await expect(banner.locator('dd[data-row="predicate"]')).toContainText('no field carries it');
  });

  test('beat 3 is the peak: the counter reads zero and the gate refuses anyway', async ({
    page,
  }) => {
    await openPermit(page);
    await pressIssue(page);

    // The control that reveals it quotes the value the counter was forced to, so the label
    // cannot promise something the payload does not then show.
    const advance = page.locator('[data-action="advance"]');
    await expect(advance).toContainText('counter now reads 0');
    await advance.click();

    const attack = page.locator('[data-beat="projection_drift_attack"]');
    await expect(attack).toHaveAttribute('data-sqlstate', 'P0001');
    await expect(attack).toContainText('re-derived open obligation count is 1');
    // The diagnosis is honestly weaker here — the name was recovered from the message text,
    // not reported by the driver — and it is labelled as such.
    await expect(attack.locator('dd[data-row="constraint"]')).toContainText('parsed');
    await expect(attack.locator('dd[data-row="constraint"]')).toContainText('weakened diagnosis');
  });

  test('beat 4 is shown: the film does not end on a refusal (R16)', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);
    await revealAll(page);

    const admit = page.locator('[data-beat="admit"]');
    await expect(admit).toHaveAttribute('data-outcome', 'admitted');
    await expect(admit).toContainText('ISSUE ADMITTED');
    // And the run proves it wrote nothing.
    await expect(page.locator('.cow-run__headline')).toContainText('VERDICT PROVEN');
    await expect(page.locator('.cow-run')).toContainText('rolled_back');
  });

  test('the whole result region is still and reproducible by a screenshot', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);
    await revealAll(page);

    const before = await page.locator('[data-result="true"]').innerHTML();
    await page.waitForTimeout(500);
    const after = await page.locator('[data-result="true"]').innerHTML();
    expect(after, 'something on the refusal is animating; nothing here may move').toBe(before);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §5 · ABSENCE LOOKS DIFFERENT FROM EMPTINESS (R9)
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the fields no column carries', () => {
  test('are empty inputs with a caret, never echoed back as server data', async ({ page }) => {
    await openPermit(page);
    for (const id of ['cow-permit-title', 'cow-job-location', 'cow-work-description']) {
      const field = page.locator(`#${id}`);
      await expect(field).toBeEditable();
      await expect(field).toHaveValue('');
      await expect(field).toHaveAttribute('placeholder', /.+/);
    }
    // Every one of them says it is typed here and not carried by the deployment.
    const typed = page.locator('[data-typed="operator"]');
    expect(await typed.count()).toBeGreaterThanOrEqual(3);
  });

  test('PPE says "not carried by this deployment"; the extension row says omitted', async ({
    page,
  }) => {
    await openPermit(page);
    await expect(page.locator('[data-figure1-element="8"] [data-not-carried="true"]')).toContainText(
      'not carried by this deployment',
    );
    await expect(page.locator('[data-figure1-element="11"][data-omitted="true"]')).toContainText(
      'omitted',
    );
  });

  test('the one signed row is the ACCEPTANCE, and it is the only one', async ({ page }) => {
    await openPermit(page);
    const signed = page.locator('[data-signed="true"]');
    await expect(signed).toHaveCount(1);
    await expect(signed).toHaveAttribute('data-figure1-element', '10');
    await expect(signed).toContainText('Acceptor');
    await expect(signed).toContainText('demo.signer');
  });

  test('the synthetic marker is permanent and the seed’s own prefixes survive', async ({ page }) => {
    await openPermit(page);
    await expect(page.locator('[data-cw="watermark"]')).toContainText('SYNTHETIC DEMONSTRATION');
    // R13: the seed's own `SYNTHETIC —` prefixes stay visible; we do not launder them out.
    await expect(page.locator('.cow-clause-text')).toContainText('SYNTHETIC —');
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// §6 · LEGIBILITY AND THE ACCESSIBILITY FLOOR A BROWSER CAN MEASURE
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the 480 test, at the geometry we film at', () => {
  test('every must-read string clears 2 % of frame height per em', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);
    await revealAll(page);

    const failures: string[] = [];
    for (const { what, selector } of MUST_BE_READABLE) {
      const sizes = await page.$$eval(selector, (nodes) =>
        nodes.map((node) => ({
          size: Number.parseFloat(getComputedStyle(node).fontSize),
          text: node.textContent.trim().slice(0, 40),
        })),
      );
      expect(sizes.length, `${what} (${selector}) matched nothing at all`).toBeGreaterThan(0);
      for (const { size, text } of sizes) {
        if (size < LEGIBILITY_FLOOR_CSS_PX) {
          failures.push(
            `${what}: ${selector} renders "${text}" at ${size.toFixed(2)} CSS px; the floor at ` +
              `this viewport is ${LEGIBILITY_FLOOR_CSS_PX.toFixed(2)} px ` +
              `(2 % of a ${FRAME_HEIGHT_CSS}-px frame, r5-craft §2.1).`,
          );
        }
      }
    }
    expect(
      failures,
      'the 480 test failed. Downscaled to 854x480 a judge will not be able to read these:\n  ' +
        failures.join('\n  '),
    ).toEqual([]);
  });

  test('every interactive control has an accessible name', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);

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

  test('focus is managed when a beat is revealed — it never falls to <body>', async ({ page }) => {
    await openPermit(page);

    // Keyboard only, which is how the claim is actually tested. Focus the control, activate
    // it, and ask where focus went.
    await page.locator('[data-action="issue"]').focus();
    const waitForRun = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/v1/demo/gate-run',
    );
    await page.keyboard.press('Enter');
    await waitForRun;
    await expect(page.locator('[data-beat]').first()).toBeVisible();

    const active = (): Promise<string> =>
      page.evaluate(() => {
        const node = document.activeElement;
        return node === null ? 'null' : node.tagName.toLowerCase();
      });

    expect(
      await active(),
      'pressing ISSUE disables the button and drops focus to <body>. A keyboard or ' +
        'screen-reader operator is now at the top of a page that just changed underneath them, ' +
        'with no way back to the refusal except Tab from the start. WCAG 2.4.3.\n' +
        'OWNER: W5 (src/operator/issue/ActionBar.ts). The shell already provides the target — ' +
        '`boot.ts` gives #cw-module `tabIndex = -1` "a programmatic focus target for the skip ' +
        'that the module screens own". Nothing calls .focus() anywhere in src/operator/**.',
    ).not.toBe('body');

    for (let guard = 0; guard < 8; guard += 1) {
      const advance = page.locator('[data-action="advance"]');
      if ((await advance.count()) === 0) break;
      await advance.first().focus();
      await page.keyboard.press('Enter');
      expect(
        await active(),
        'revealing a beat replaced the advance control and dropped focus to <body>. ' +
          'OWNER: W5 (src/operator/issue/ActionBar.ts).',
      ).not.toBe('body');
    }
  });

  test('has no CRITICAL accessibility violation', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);
    await revealAll(page);

    const results = await new AxeBuilder({ page }).analyze();
    const critical = results.violations.filter((violation) => violation.impact === 'critical');
    expect(
      critical.map(
        (violation) =>
          `${violation.id} (${violation.nodes.length} node(s)) — ${violation.help} — first at ` +
          String(violation.nodes[0]?.target),
      ),
      'OWNER of the signature-block finding: W3 (src/operator/permit/signatures.ts). ' +
        'The block sets role="table" on the wrapper and role="row" on each row, but the ' +
        '.cow-sig-h header spans and .cow-sig-cell divs carry no role, so the table exposes no ' +
        'cells at all and a screen reader reads it as an empty grid. Two attributes fix it: ' +
        'role="columnheader" on .cow-sig-h and role="cell" on .cow-sig-cell / .cow-sig-what.',
    ).toEqual([]);
  });

  /**
   * The serious and moderate findings are RECORDED here rather than gated on, and every
   * exclusion is named with its owner. A skip with no reason is not accepted in this
   * repository (`src/a11y/audit.ts` AuditOptions.skip), so none of these is silent.
   *
   * This is a ratchet, not an amnesty: the assertion is that the set of serious/moderate
   * rule ids is EXACTLY the known set. A new one fails this test.
   */
  test('records the serious and moderate findings, and refuses any new one', async ({ page }) => {
    await openPermit(page);
    await pressIssue(page);
    await revealAll(page);

    const results = await new AxeBuilder({ page }).analyze();
    const known = new Set([
      // OWNER W1 (src/operator/chrome/tokens.css) + W3 (src/operator/permit/permit.css).
      // Measured: .cw-rail__name #5c636b on #14171b = 2.95:1; .cow-hint and
      // .cow-state-value #7d8994 on #ffffff = 3.57:1. Both below 4.5:1. Colour contrast is
      // out of scope for src/a11y/audit.ts by its own NOT_CHECKED_HERE note, so this
      // browser tier is the only place it is measured at all.
      'color-contrast',
      // OWNER W1 (src/operator/permit/screen.ts heading level, and chrome/Watermark.ts).
      // The permit screen's headings start at h2 and the watermark sits outside every
      // landmark. Neither costs a byte to fix.
      'page-has-heading-one',
      'region',
    ]);
    const seen = results.violations
      .filter((violation) => violation.impact === 'serious' || violation.impact === 'moderate')
      .map((violation) => violation.id)
      .sort();
    const unexpected = seen.filter((id) => !known.has(id));
    expect(
      unexpected,
      `new serious/moderate accessibility violation(s) on the permit screen: ${unexpected.join(', ')}`,
    ).toEqual([]);
  });
});
