// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Addressing — the subject index, and the absences it names.
 *
 * The fixtures below are SHAPED like the real payload and carry no real identifier: the
 * point of this module is that identifiers come off the wire, so a test that pinned one
 * would be asserting the defect the module exists to remove.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { absenceOf, resetAddressing, resolveAddressing } from '../../../../src/operator/kernel/addressing';
import { entries, resetLog } from '../../../../src/operator/kernel/log';
import { resetOrigin } from '../../../../src/operator/kernel/origin';

const PERMIT_ID = 'aaaaaaaa-0000-4000-8000-000000000001';
const CLAUSE_ID = 'bbbbbbbb-0000-4000-8000-000000000002';

/** The `absent[]` reason, with the punctuation and casing the emitter used. */
const ABSENT_REASON =
  'mainline.change_request holds no row for this site; the predicate ' +
  'site_id = $1 ORDER BY (opened_at, cr_id) returned nothing.';

function subjectsBody(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    envelope_version: 1,
    resource: 'demo_subjects',
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/subjects.schema.json',
    observed_at: '2026-08-15T09:00:00Z',
    staged: false,
    staged_note: null,
    provenance: [],
    data: {
      site_id: null,
      site_code: 'SYNTHETIC-SITE',
      permit_id: PERMIT_ID,
      cr_id: null,
      check_id: null,
      receipt_id: null,
      clause_uuid: CLAUSE_ID,
      commit_id: 'deadbeef',
      run_id: null,
      lesson_id: null,
      subjects: { site: { count: 1, site_id: null, site_code: 'SYNTHETIC-SITE' } },
      absent: [
        {
          subject: 'change_request',
          relation: 'mainline.change_request',
          reason: ABSENT_REASON,
        },
      ],
      ...overrides,
    },
  });
}

let fetchCount = 0;

beforeEach(() => {
  fetchCount = 0;
  resetAddressing();
  resetLog();
  resetOrigin();
});

describe('resolveAddressing', () => {
  it('asks GET /v1/demo/subjects and takes every identifier from the answer', async () => {
    const paths: string[] = [];
    vi.stubGlobal('fetch', (input: URL) => {
      paths.push(input.pathname);
      return Promise.resolve(new Response(subjectsBody(), { status: 200 }));
    });

    const addressing = await resolveAddressing();

    expect(paths).toEqual(['/v1/demo/subjects']);
    expect(addressing.resolved).toBe(true);
    expect(addressing.permitId).toBe(PERMIT_ID);
    expect(addressing.clauseUuid).toBe(CLAUSE_ID);
    expect(addressing.commitId).toBe('deadbeef');
    expect(addressing.siteCode).toBe('SYNTHETIC-SITE');
  });

  it('leaves a slot null rather than standing anything in for a missing row', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve(new Response(subjectsBody(), { status: 200 })));

    const addressing = await resolveAddressing();

    expect(addressing.crId).toBeNull();
    expect(addressing.checkId).toBeNull();
    expect(addressing.receiptId).toBeNull();
    expect(addressing.runId).toBeNull();
    expect(addressing.siteId).toBeNull();
  });

  it('caches for the page load: two callers make one request', async () => {
    vi.stubGlobal('fetch', () => {
      fetchCount += 1;
      return Promise.resolve(new Response(subjectsBody(), { status: 200 }));
    });

    const [first, second] = await Promise.all([resolveAddressing(), resolveAddressing()]);
    const third = await resolveAddressing();

    expect(fetchCount).toBe(1);
    expect(entries()).toHaveLength(1);
    expect(second).toBe(first);
    expect(third).toBe(first);
  });
});

describe('absence', () => {
  it('surfaces the absent[] entry verbatim — subject, relation and reason unedited', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve(new Response(subjectsBody(), { status: 200 })));

    const addressing = await resolveAddressing();

    expect(addressing.absent).toEqual([
      {
        subject: 'change_request',
        relation: 'mainline.change_request',
        reason: ABSENT_REASON,
      },
    ]);
    // Character-for-character. A trimmed, re-punctuated or sentence-cased reason is the
    // kernel's words rewritten, and the whole value of the sentence is that they are its.
    expect(absenceOf(addressing, 'change_request')?.reason).toBe(ABSENT_REASON);
    expect(absenceOf(addressing, 'permit')).toBeNull();
  });

  it('keeps a relation that reports the table itself does not exist', async () => {
    const relation = 'mainline.recall_run (no such relation)';
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(
          subjectsBody({
            absent: [{ subject: 'recall_run', relation, reason: 'this cluster has no such table.' }],
          }),
          { status: 200 },
        ),
      ),
    );

    const addressing = await resolveAddressing();

    expect(absenceOf(addressing, 'recall_run')?.relation).toBe(relation);
  });
});

describe('when addressing cannot be resolved at all', () => {
  it('reports the kernel’s own sentence and invents no identifier', async () => {
    const detail = "SSM GetParameter '/mainline/demo/cockroach_dsn' failed: ParameterNotFound";
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(JSON.stringify({ error: { kind: 'dsn_unset', status: 503, detail } }), {
          status: 503,
        }),
      ),
    );

    const addressing = await resolveAddressing();

    expect(addressing.resolved).toBe(false);
    expect(addressing.failure).toEqual({ kind: 'dsn_unset', detail });
    expect(addressing.permitId).toBeNull();
    expect(addressing.clauseUuid).toBeNull();
    expect(addressing.absent).toEqual([]);
  });

  it('does not reject when the transport fails', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));

    const addressing = await resolveAddressing();

    expect(addressing.resolved).toBe(false);
    expect(addressing.failure?.kind).toBe('network');
    expect(addressing.permitId).toBeNull();
  });

  it('refuses a frame that answers a different resource', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            envelope_version: 1,
            resource: 'permit',
            schema_id: 's',
            staged: false,
            provenance: [],
            data: { permit_id: PERMIT_ID },
          }),
          { status: 200 },
        ),
      ),
    );

    const addressing = await resolveAddressing();

    expect(addressing.resolved).toBe(false);
    expect(addressing.failure?.kind).toBe('wrong_resource');
  });
});
