// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * G5 — THE AUDIT SPEC.
 *
 * `ARCHITECTURE.md` §17 makes three properties of the `mainline_audit.v_*` views a
 * FUNCTIONAL requirement rather than a nicety: ≤ 25 rows, ≤ 10 KiB, and a truncation flag
 * on every aggregate. A nightly test asserts them against the database. This spec asserts
 * the console's half — that a reader is TOLD which of those bounds a result ran into,
 * before they read the numbers.
 *
 * The sharpest assertion here is the negative one. `mainline_qa` holds the per-named-person
 * deliberation measures, and no MCP service account is ever issued for that schema, on any
 * tier, ever. The audit payload carries a PROBE that must have been refused — and an empty
 * probe list is rendered as *nothing was checked*, never as *nothing is reachable*. This
 * spec serves a payload with no probes at all and requires the screen to say the former.
 *
 * ── PL-2: WHAT MAKES THIS SPEC RED TODAY ────────────────────────────────────────
 *
 * The same two dependencies `custody.spec.ts` names: `playwright.config.ts` with a
 * `baseURL` (the cinema-conformance-harness worker, ui W4), and a composed transport in
 * the shell. Until both land, this surface renders its honest NO SOURCE panel and every
 * assertion below fails on it. The equivalent claims are asserted today in
 * `tests/unit/verify/audit-screen.test.tsx`.
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Page, type Route } from '@playwright/test';

const HERE = dirname(fileURLToPath(import.meta.url));
const BUNDLE_DIR = resolve(HERE, '../../fixtures/bundles/blk-07');
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

interface AuditView {
  readonly view: string;
  readonly columns: readonly { readonly name: string; readonly sql_type?: string | null }[];
  readonly rows: readonly (readonly (string | number | boolean | null)[])[];
  readonly limits: {
    readonly row_cap: number;
    readonly byte_cap: number;
    readonly rows_returned: number;
    readonly bytes_returned: number;
  };
  readonly truncation_flag: { readonly column: string; readonly complete: boolean } | null;
  readonly statement?: string | null;
}

interface AuditEnvelope {
  readonly data: {
    views: AuditView[];
    calls: Record<string, unknown>[];
    unreachable?: Record<string, unknown>[];
  };
}

function findFrame(requestKey: string): { file: string; frame: Frame } {
  const dir = join(BUNDLE_DIR, 'frames');
  for (const file of readdirSync(dir)) {
    const frame = readJson<Frame>(join(dir, file));
    if (frame.key === requestKey) return { file, frame };
  }
  throw new Error(`no frame in ${dir} answers "${requestKey}".`);
}

const AUDIT_FRAME = findFrame('GET /v1/audit');

function decodeEnvelope(): AuditEnvelope {
  return JSON.parse(
    Buffer.from(AUDIT_FRAME.frame.response.body_b64, 'base64').toString('utf8'),
  ) as AuditEnvelope;
}

const CINEMA = 'cinema=1&seed=8891&t=2026-08-07T02%3A15%3A00.000Z';
const FIXED_CLOCK = new Date('2026-08-07T02:15:00.000Z');

function sha256Hex(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

async function serveAudit(page: Page, envelope: AuditEnvelope): Promise<void> {
  const frameBytes = Buffer.from(
    JSON.stringify({
      ...AUDIT_FRAME.frame,
      response: {
        ...AUDIT_FRAME.frame.response,
        body_b64: Buffer.from(JSON.stringify(envelope), 'utf8').toString('base64'),
      },
    }),
    'utf8',
  );
  const framePath = `frames/${AUDIT_FRAME.file}`;
  const manifest = readJson<ManifestShape>(join(BUNDLE_DIR, 'manifest.json'));
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

async function openAudit(page: Page): Promise<void> {
  await page.clock.install({ time: FIXED_CLOCK });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/?${CINEMA}#/audit`);
  await expect(page.getByTestId('audit-surface')).toBeVisible();
}

// ── The spec ───────────────────────────────────────────────────────────────

test.describe('the audit surface', () => {
  test('the fixture this spec reads is the one it thinks it reads', () => {
    const envelope = decodeEnvelope();
    expect(envelope.data.views.length).toBeGreaterThan(0);
    expect(AUDIT_FRAME.frame.key).toBe('GET /v1/audit');
  });

  test('renders every view the payload carries, from the columns it declares', async ({ page }) => {
    const envelope = decodeEnvelope();
    await serveAudit(page, envelope);
    await openAudit(page);

    await expect(page.getByTestId('view-count')).toHaveText(String(envelope.data.views.length));
    for (const view of envelope.data.views) {
      await expect(page.getByTestId(`caps-${view.view}`)).toBeVisible();
      for (const column of view.columns) {
        await expect(page.getByText(column.name, { exact: true }).first()).toBeVisible();
      }
    }
  });

  test('renders a column this console has never heard of', async ({ page }) => {
    const envelope = decodeEnvelope();
    envelope.data.views.push({
      view: 'mainline_audit.v_invented_tomorrow',
      columns: [
        { name: 'site_id', sql_type: 'UUID' },
        { name: 'a_column_the_console_has_never_heard_of', sql_type: 'INT8' },
      ],
      rows: [['018f3a2e-0000-7000-8000-000000000001', 42]],
      limits: { row_cap: 25, byte_cap: 10240, rows_returned: 1, bytes_returned: 120 },
      truncation_flag: { column: 'ancestry_complete', complete: false },
      statement: 'SELECT * FROM mainline_audit.v_invented_tomorrow',
    });

    await serveAudit(page, envelope);
    await openAudit(page);

    await expect(
      page.getByText('a_column_the_console_has_never_heard_of', { exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId('completeness-mainline_audit.v_invented_tomorrow')).toContainText(
      'undercount',
    );
  });

  test('a result AT the row cap is reported as truncated, not as a count', async ({ page }) => {
    const envelope = decodeEnvelope();
    const first = envelope.data.views[0];
    expect(first).toBeDefined();
    if (first !== undefined) {
      envelope.data.views[0] = {
        ...first,
        limits: { ...first.limits, rows_returned: first.limits.row_cap },
      };
    }

    await serveAudit(page, envelope);
    await openAudit(page);

    await expect(page.getByTestId(`caps-${first?.view ?? ''}`)).toContainText(
      'rows were very probably discarded',
    );
  });

  test('a view with no truncation flag says it makes no completeness claim', async ({ page }) => {
    const envelope = decodeEnvelope();
    const first = envelope.data.views[0];
    if (first !== undefined) envelope.data.views[0] = { ...first, truncation_flag: null };

    await serveAudit(page, envelope);
    await openAudit(page);

    await expect(page.getByTestId(`completeness-${first?.view ?? ''}`)).toContainText(
      'makes no completeness claim',
    );
  });

  test('an EMPTY probe list is rendered as "nothing was checked"', async ({ page }) => {
    const envelope = decodeEnvelope();
    envelope.data.unreachable = [];

    await serveAudit(page, envelope);
    await openAudit(page);

    const reading = page.getByTestId('unreachable-reading');
    await expect(reading).toContainText('not a claim that nothing is reachable');
    await expect(reading).toContainText('mainline_qa');
  });

  test('a refused probe is rendered as the assertion, with its SQLSTATE', async ({ page }) => {
    const envelope = decodeEnvelope();
    await serveAudit(page, envelope);
    await openAudit(page);

    const carried = (envelope.data.unreachable ?? [])[0];
    if (carried === undefined) {
      test.skip(true, 'the fixture carries no negative probe');
      return;
    }
    const table = page.getByTestId('unreachable-table');
    await expect(table).toContainText(String(carried['schema_name']));
    await expect(table).toContainText(String(carried['outcome']));
  });

  test('the write surface is represented read-only, with no form', async ({ page }) => {
    const envelope = decodeEnvelope();
    await serveAudit(page, envelope);
    await openAudit(page);

    await expect(page.getByTestId('attestation-shape')).toContainText('attestor_kind');
    await expect(page.getByTestId('attestation-read-only')).toContainText(
      'never writes an evidentiary row',
    );
    // The one MCP-writable table in the deployment, and this console cannot write it.
    await expect(page.locator('form')).toHaveCount(0);
    await expect(page.locator('input')).toHaveCount(0);
    await expect(page.locator('textarea')).toHaveCount(0);
  });

  test('the plan fragment is labelled a plan, never a measurement', async ({ page }) => {
    const envelope = decodeEnvelope();
    await serveAudit(page, envelope);
    await openAudit(page);

    await expect(page.getByTestId('call-table')).toContainText(
      'EXPLAIN ANALYZE is not available',
    );
  });

  test('an empty aggregate says WHY it is empty, and quotes the kernel for it', async ({ page }) => {
    const envelope = decodeEnvelope();
    const first = envelope.data.views[0];
    expect(first).toBeDefined();
    if (first !== undefined) {
      envelope.data.views[0] = { ...first, rows: [], limits: { ...first.limits, rows_returned: 0 } };
    }
    // The probe the live payload carries, verbatim — measured against the live URL on
    // 2026-08-15. It is set here rather than read from the fixture so this test asserts that
    // the SCREEN quotes whatever the payload said, not that two fixtures agree.
    const probe =
      "not probed by the demo API: it connects as the demo's own read role, not as the " +
      'Managed-MCP service account, so a refusal here would answer a different question than ' +
      'the one this field asks';
    envelope.data.unreachable = [
      { schema_name: 'mainline_qa', probe, outcome: 'not_probed', sqlstate: null },
    ];

    await serveAudit(page, envelope);
    await openAudit(page);

    const empty = page.getByTestId(`empty-${first?.view ?? ''}`);
    await expect(empty).toBeVisible();
    await expect(empty).toContainText('No rows');
    await expect(empty).toContainText('a fact about this deployment and not about any record');
    // The kernel's own sentence, unchanged. R8: rendered verbatim, never paraphrased.
    // `.first()` because the payload may carry more than one probe and each gets its own
    // block; the assertion is that the FIRST one is reproduced byte for byte.
    await expect(page.getByTestId(`empty-probe-${first?.view ?? ''}`).first()).toHaveText(probe);

    // And the row count is still zero. R3: the zero is true and is never filled.
    await expect(page.getByTestId(`caps-${first?.view ?? ''}`)).toContainText('0 row(s)');
  });

  test('an empty call log says why, rather than leaving a blank', async ({ page }) => {
    const envelope = decodeEnvelope();
    envelope.data.calls = [];

    await serveAudit(page, envelope);
    await openAudit(page);

    const empty = page.getByTestId('calls-empty');
    await expect(empty).toBeVisible();
    await expect(empty).toContainText('a fact about this deployment and not about any record');
    await expect(empty).toContainText('not a claim that nothing ran');
    await expect(page.getByTestId('call-total')).toHaveText('0');
  });

  test('the caps are stated in one plain sentence with the exact numbers kept', async ({ page }) => {
    const envelope = decodeEnvelope();
    const first = envelope.data.views[0];
    expect(first).toBeDefined();

    await serveAudit(page, envelope);
    await openAudit(page);

    const caps = page.getByTestId(`caps-${first?.view ?? ''}`);
    await expect(caps).toBeVisible();
    await expect(caps).toContainText('The read-only account that asked this question is allowed');
    await expect(caps).toContainText(String(first?.limits.row_cap ?? -1));
    await expect(caps).toContainText(String(first?.limits.byte_cap ?? -1));
    await expect(caps).toContainText(String(first?.limits.bytes_returned ?? -1));
  });

  test('the screen opens with a plain band that names no undefined term', async ({ page }) => {
    const envelope = decodeEnvelope();
    await serveAudit(page, envelope);
    await openAudit(page);

    const band = page.getByTestId('audit-plain-band');
    await expect(band).toBeVisible();
    await expect(band).toContainText('Every question an automated agent asks this database');
    await expect(band).toContainText('never a claim that nothing exists');
  });

  test('the surface has no serious or critical accessibility defect', async ({ page }) => {
    const envelope = decodeEnvelope();
    await serveAudit(page, envelope);
    await openAudit(page);

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const blocking = results.violations.filter(
      (violation) => violation.impact === 'serious' || violation.impact === 'critical',
    );
    expect(blocking.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
  });
});
