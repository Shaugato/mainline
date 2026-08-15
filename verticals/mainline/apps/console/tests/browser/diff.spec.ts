// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * G5 — THE CLAUSE DIFF SPEC.
 *
 * The claim this file exists to make falsifiable:
 *
 *   > The console computed WHAT changed and shows its arithmetic. Only the database says
 *   > WHY, and where the database said nothing, the console says nothing.
 *
 * Both halves are checked against the FIXTURE BYTES, never against a literal in this
 * file. Not one clause, anchor, pointer, rule id or note is typed here: every expected
 * value is read from `fixtures/sources/blk-07/payloads/clause-version.json` at run time,
 * and the last describe block REWRITES those bytes and requires the screen to follow. A
 * console that hardcoded the demo clause, and a spec that hardcoded what it expected,
 * would both pass an eyeball review and neither would assert anything.
 *
 * The load-bearing assertion is the reassembly property:
 *
 *     concat(runs where data-segment ≠ added)   === parent.canon_text
 *     concat(runs where data-segment ≠ removed) === version.canon_text
 *
 * taken from the DOM. A diff that lost a sentence would still look like a diff; it would
 * fail here.
 *
 * ── PL-2: WHAT IS RED TODAY, AND WHY IT IS NOT WORKED AROUND ─────────────────────
 *
 * Two dependencies are owned by other workers and had not landed when this was written.
 * They are named rather than stubbed, because a spec that quietly degrades to advisory is
 * a spec that asserts nothing:
 *
 *   1. `playwright.config.ts` with a `baseURL`, cinema mode and the 1920×1080 /
 *      `deviceScaleFactor: 1` / `page.clock.install()` project — `cinema-conformance-harness`
 *      (ui W4). Every `page.goto` below is relative to that `baseURL`.
 *   2. A COMPOSED TRANSPORT. `src/app` provides no `MainlineTransport`, and this surface
 *      deliberately does not build one: `BundleTransport` has no default verifier, and
 *      inventing a permissive one so a screen paints is exactly the lie the transport was
 *      shaped to prevent. Until the shell composes one, the surface renders its honest
 *      NO BYTES panel.
 *
 * `describe('the absence')` below is green the moment (1) lands, with or without (2) —
 * it asserts that the console renders an honest absence rather than a blank pane, which
 * is a real product claim and not a placeholder. The rest goes green with (2).
 *
 * Every equivalent claim is asserted TODAY, through the real model and the real contract
 * validator, in `tests/unit/diff/`. This file is the browser tier of the same claims.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Page, type Route } from '@playwright/test';

// ── The fixture, read from disk ────────────────────────────────────────────

const HERE = dirname(fileURLToPath(import.meta.url));
const PAYLOAD_PATH = resolve(
  HERE,
  '../../fixtures/sources/blk-07/payloads/clause-version.json',
);

interface ClauseVersionShape {
  readonly clause_uuid: string;
  readonly commit_id: string;
  readonly canon_text: string;
  readonly anchor_set: readonly string[];
  readonly control_delta: string;
}

interface WitnessShape {
  readonly rule_id: string;
  readonly field: string;
  readonly from_repr: string;
  readonly to_repr: string;
  readonly note: string;
}

interface PayloadShape {
  readonly staged: boolean;
  readonly data: {
    readonly clause_uuid: string;
    readonly version: ClauseVersionShape;
    readonly parent: ClauseVersionShape | null;
    readonly delta: {
      readonly delta: string;
      readonly basis: string;
      readonly witnesses: readonly WitnessShape[] | null;
      readonly minimal: boolean | null;
    };
  };
}

function payload(): PayloadShape {
  return JSON.parse(readFileSync(PAYLOAD_PATH, 'utf8')) as PayloadShape;
}

const FIXTURE = payload();
const VERSION = FIXTURE.data.version;
const PARENT = FIXTURE.data.parent;

if (PARENT === null) {
  throw new Error(
    `${PAYLOAD_PATH} carries no \`parent\`. Every assertion about a diff below would be ` +
      'vacuous, so this fails loudly rather than skipping.',
  );
}

/** The address the surface reads out of the hash query. */
const ROUTE = `/#/diff?clause=${VERSION.clause_uuid}&commit=${VERSION.commit_id}`;

/**
 * The read this surface performs, as `src/data/resources.ts` builds it.
 *
 * Written out rather than imported because the Playwright project compiles under
 * `tsconfig.node.json` and must not reach into the application's module graph — but it is
 * derived from the fixture's own identifiers, so a changed fixture changes this URL too.
 */
const REQUEST_PATH = `/v1/clauses/${VERSION.clause_uuid}/versions/${VERSION.commit_id}`;

/**
 * Serves one clause-version payload for any transport that asks over HTTP.
 *
 * `mutate` lets a test re-write the bytes before they are served, which is how the
 * "nothing is hardcoded" block proves the screen follows the payload.
 */
async function serveClause(
  page: Page,
  mutate: (source: PayloadShape) => PayloadShape = (source) => source,
): Promise<void> {
  await page.route(`**${REQUEST_PATH}`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mutate(payload())),
    });
  });
}

/**
 * Opens every disclosure on the panel.
 *
 * Since 2026-08-15 the canonical texts, the anchor table, the structured fields, the
 * witness rows and the stored columns open COLLAPSED — `docs/leads/two-audience-ux-plan.md`
 * R6, so that a first-time reader meets the plain band and the verdict before meeting a
 * hash table. Nothing was removed: every one of them is in the DOM in both states, which is
 * why the reassembly assertions below still hold either way. What a closed `<details>` does
 * change is `toBeVisible()`, so a spec that asserts what a reader SEES has to perform the
 * click the reader performs.
 *
 * It sets `open` rather than clicking, deliberately: the assertion that the summary is a
 * real operable control belongs to one dedicated test ("collapsed, not removed"), and
 * repeating it in every fixture step would make an unrelated failure look like a layout
 * regression.
 */
async function openDisclosures(page: Page): Promise<void> {
  await page.evaluate(() => {
    for (const node of document.querySelectorAll('details')) node.open = true;
  });
}

/** Reassembles one side of the clause from the rendered runs. */
async function reassemble(page: Page, side: 'parent' | 'version'): Promise<string> {
  const excluded = side === 'parent' ? 'added' : 'removed';
  return page.evaluate((skip) => {
    const panel = document.querySelector('[data-testid="text-unified"]');
    if (panel === null) return '';
    return [...panel.querySelectorAll('[data-segment]')]
      .filter((node) => node.getAttribute('data-segment') !== skip)
      .map((node) => node.getAttribute('data-text') ?? '')
      .join('');
  }, excluded);
}

// ── The absence: true today, and a product claim in its own right ──────────

test.describe('the absence', () => {
  test('renders an honest NO BYTES panel rather than a blank pane', async ({ page }) => {
    await page.goto(ROUTE);
    const notice = page.getByTestId('diff-no-transport');
    await expect(notice).toBeVisible();
    // It must name the read it WOULD have made, so the absence is actionable.
    await expect(notice).toContainText('clause_version');
    await expect(notice).toContainText(VERSION.clause_uuid);
  });

  test('the honest absence is itself accessible', async ({ page }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('diff-no-transport')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    );
    expect(serious.map((violation) => violation.id)).toEqual([]);
  });
});

// ── The diff, once a transport is composed ─────────────────────────────────

test.describe('the diff', () => {
  test.beforeEach(async ({ page }) => {
    await serveClause(page);
  });

  test('reassembles both canon_text values exactly from the DOM', async ({ page }) => {
    await page.goto(ROUTE);
    await openDisclosures(page);
    await expect(page.getByTestId('text-unified')).toBeVisible();
    expect(await reassemble(page, 'parent')).toBe(PARENT.canon_text);
    expect(await reassemble(page, 'version')).toBe(VERSION.canon_text);
  });

  test('opens plain, and the exact wording is one click away and complete', async ({ page }) => {
    await page.goto(ROUTE);

    // What a first-time reader meets: the plain band and the verdict, not a hash table.
    await expect(page.getByTestId('diff-plain-band')).toBeVisible();
    await expect(page.getByTestId('delta-verdict')).toBeVisible();
    await expect(page.getByTestId('text-unified')).not.toBeVisible();

    // ONE click, on a control that names what is behind it, and nothing was lost.
    await page.getByText('Show the exact wording of the rule, before and after').click();
    await expect(page.getByTestId('text-unified')).toBeVisible();
    expect(await reassemble(page, 'parent')).toBe(PARENT.canon_text);
    expect(await reassemble(page, 'version')).toBe(VERSION.canon_text);
  });

  test('renders the control_delta the payload carries, verbatim', async ({ page }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('delta-verdict')).toContainText(FIXTURE.data.delta.delta);
    await expect(page.getByTestId('delta-verdict')).toContainText(FIXTURE.data.delta.basis);
  });

  test('renders every witness note verbatim', async ({ page }) => {
    await page.goto(ROUTE);
    const table = page.getByTestId('delta-witnesses');
    for (const witness of FIXTURE.data.delta.witnesses ?? []) {
      await expect(table).toContainText(witness.rule_id);
      await expect(table).toContainText(witness.note);
    }
  });

  test('badges the diff as recomputed and the witnesses as db:column', async ({ page }) => {
    await page.goto(ROUTE);
    await openDisclosures(page);
    await expect(
      page.getByTestId('text-diff').locator('[data-kind="recomputed"]').first(),
    ).toBeVisible();
    // The reason a control changed is never something this browser computed.
    await expect(page.getByTestId('delta-witnesses').locator('[data-kind="recomputed"]')).toHaveCount(
      0,
    );
  });

  test('names every dropped anchor', async ({ page }) => {
    await page.goto(ROUTE);
    const dropped = PARENT.anchor_set.filter((anchor) => !VERSION.anchor_set.includes(anchor));
    expect(dropped.length).toBeGreaterThan(0);
    for (const anchor of dropped) {
      await expect(page.getByTestId('anchor-residue')).toContainText(anchor);
    }
  });

  test('says STAGED when the payload says staged', async ({ page }) => {
    test.skip(!FIXTURE.staged, 'this fixture is not staged, so there is nothing to assert');
    await page.goto(ROUTE);
    await expect(page.getByTestId('diff-staged')).toBeVisible();
  });

  test('has no serious or critical accessibility violation', async ({ page }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('clause-diff')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    );
    expect(serious.map((violation) => violation.id)).toEqual([]);
  });
});

// ── Nothing is hardcoded: rewrite the bytes, the screen must follow ────────

test.describe('nothing is hardcoded', () => {
  test('shows WITNESS UNAVAILABLE when the witnesses member is removed', async ({ page }) => {
    await serveClause(page, (source) => ({
      ...source,
      data: {
        ...source.data,
        delta: { ...source.data.delta, witnesses: null, minimal: null },
      },
    }));
    await page.goto(ROUTE);
    await expect(page.getByTestId('delta-witnesses')).toContainText('WITNESS UNAVAILABLE');
  });

  test('shows a DIFFERENT screen when the emitter asserts there are none', async ({ page }) => {
    await serveClause(page, (source) => ({
      ...source,
      data: { ...source.data, delta: { ...source.data.delta, witnesses: [] } },
    }));
    await page.goto(ROUTE);
    const table = page.getByTestId('delta-witnesses');
    await expect(table).toContainText('reports that there are none');
    await expect(table).not.toContainText('WITNESS UNAVAILABLE');
  });

  test('refuses to diff when the payload carries the wrong ancestor', async ({ page }) => {
    await serveClause(page, (source) => {
      const wrongParent = source.data.parent;
      if (wrongParent === null) return source;
      return {
        ...source,
        data: {
          ...source.data,
          parent: { ...wrongParent, commit_id: 'f'.repeat(64) },
        },
      };
    });
    await page.goto(ROUTE);
    await expect(page.getByTestId('diff-no-comparison')).toContainText('WRONG ANCESTOR');
    // The refusal IS the screen: no diff is drawn at all.
    await expect(page.getByTestId('text-unified')).toHaveCount(0);
    await expect(page.locator('ins')).toHaveCount(0);
    await expect(page.locator('del')).toHaveCount(0);
  });

  test('renders whatever canon_text the payload carries', async ({ page }) => {
    const replacement = `${VERSION.canon_text} Verification shall be witnessed.`;
    await serveClause(page, (source) => ({
      ...source,
      data: {
        ...source.data,
        version: { ...source.data.version, canon_text: replacement },
      },
    }));
    await page.goto(ROUTE);
    await openDisclosures(page);
    await expect(page.getByTestId('text-unified')).toBeVisible();
    expect(await reassemble(page, 'version')).toBe(replacement);
  });
});
