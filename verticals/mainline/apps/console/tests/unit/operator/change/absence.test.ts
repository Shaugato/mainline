// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * R11 — THE ABSENCE, AND THE FOUR WAYS A BUILDER COULD HAVE FAKED IT.
 *
 * The change request has one blocking obligation open on it and NO declared route returns
 * it. That is an awkward fact and there are four comfortable ways around it, all of them
 * lies a screenshot could not detect:
 *
 *   1. copy `dec0de00-000d-…` out of `docs/demo/research/r3-operator.md` and read the
 *      obligation with it;
 *   2. print the three change-request defeater prompts from that same document;
 *   3. hard-code the struck-through "missing" routes so the evidence panel looks full;
 *   4. wire the approve button to `POST /v1/permits/{permit_id}/merge`, which DOES exist,
 *      so the screen "works".
 *
 * Each test below closes one of them. The route-table fixtures are verbatim bytes
 * captured from a real 404 (see `screen.test.ts` for the capture note); the synthetic
 * tables are clearly labelled as synthetic and exist only to prove that the discovery is
 * driven by the deployment's own table rather than by anything remembered here.
 */

import { describe, expect, it } from 'vitest';

import {
  composeAbsentCrRoutes,
  discoverCrCheckIds,
  fillTemplate,
  parseRouteTable,
  renderActionBar,
  renderDefeaterPrompts,
  renderObligation,
  routesMergingChangeRequest,
  routesYieldingCrChecks,
  type AbsenceReader,
  type RouteTable,
} from '../../../../src/operator/change/absence';

/**
 * VERBATIM. Captured 2026-08-15 from `scripts/deploy/local_furl.py` running the real
 * `mainline_demo_api.app.handler` against the local CockroachDB `mainline_demo`:
 *
 *   GET /v1/change-requests/<cr_id>/blocking-checks  →  404, 695 bytes
 *
 * Not edited, not reshaped, not trimmed. The cr_id inside `detail` is the deployment's
 * own echo of the path it was asked for — it is data in a captured response, not an
 * address this suite or `src/operator/change/**` uses to reach anything.
 */
const REAL_404 =
  '{"error":{"declared":["/v1/audit","/v1/change-requests/{cr_id}",' +
  '"/v1/checks/{check_id}/disposition","/v1/clauses/{clause_uuid}/ancestry",' +
  '"/v1/clauses/{clause_uuid}/versions/{commit_id}","/v1/demo/gate-run",' +
  '"/v1/demo/subjects","/v1/ledger","/v1/lessons/{lesson_id}/propagation",' +
  '"/v1/permits/{permit_id}","/v1/permits/{permit_id}/blocking-checks",' +
  '"/v1/permits/{permit_id}/checks:materialise","/v1/permits/{permit_id}/merge",' +
  '"/v1/permits/{permit_id}/silence","/v1/permits/{permit_id}/suspend",' +
  '"/v1/recall-runs/{run_id}","/v1/receipts/{receipt_id}"],' +
  '"detail":"no resource is declared at GET /v1/change-requests/' +
  'dec0de00-000c-4000-8000-000000000001/blocking-checks","kind":"no_route","status":404}}';

const CR_ID = 'test-cr-id-not-a-uuid';

/** Parse, or fail the test with a useful sentence. Never `!`, never a cast. */
function mustParse(raw: string): RouteTable {
  const table = parseRouteTable(raw);
  if (table === null) throw new Error('expected a readable no_route route table');
  return table;
}

/** A synthetic `no_route` body carrying exactly the templates a test wants to reason about. */
function syntheticTable(declared: readonly string[]): RouteTable {
  return mustParse(
    JSON.stringify({ error: { declared, detail: 'synthetic', kind: 'no_route', status: 404 } }),
  );
}

interface Probe {
  readonly reader: AbsenceReader;
  readonly calls: readonly string[];
}

function reader(routes: Readonly<Record<string, { status: number; body: string }>> = {}): Probe {
  const calls: string[] = [];
  return {
    calls,
    reader: {
      get: (path: string) => {
        calls.push(path);
        const hit = routes[path] ?? { status: 404, body: '{}' };
        return Promise.resolve({
          method: 'GET',
          path,
          status: hit.status,
          data: hit.status === 200 ? (JSON.parse(hit.body) as unknown) : null,
          raw: hit.body,
          wireBytes: hit.body.length,
          receivedAt: '2026-08-15T00:00:00.000Z',
        });
      },
    },
  };
}

describe('parseRouteTable — the evidence is the bytes, or it is nothing', () => {
  it('reads the deployment’s own route table out of a real 404 body', () => {
    const table = parseRouteTable(REAL_404);
    expect(table).not.toBeNull();
    expect(table?.status).toBe(404);
    expect(table?.kind).toBe('no_route');
    expect(table?.declared).toHaveLength(17);
    expect(table?.declared).toContain('/v1/change-requests/{cr_id}');
  });

  it('returns null — never an empty table — when the body is not a no_route 404', () => {
    // The distinction matters: an empty `declared` would render as "the deployment
    // declares nothing", which is a claim. `null` renders as "we could not read it".
    expect(parseRouteTable('not json')).toBeNull();
    expect(parseRouteTable('{"data":{}}')).toBeNull();
    expect(parseRouteTable('{"error":{"kind":"no_route","status":404}}')).toBeNull();
    expect(parseRouteTable('{"error":{"declared":[1,2],"kind":"no_route","status":404}}')).toBeNull();
  });
});

describe('the two routes screen two would need are genuinely absent', () => {
  it('finds no declared route that yields a change request’s blocking checks', () => {
    const table = parseRouteTable(REAL_404);
    expect(routesYieldingCrChecks(table?.declared ?? [])).toEqual([]);
  });

  it('finds no declared route that merges a change request', () => {
    const table = parseRouteTable(REAL_404);
    expect(routesMergingChangeRequest(table?.declared ?? [])).toEqual([]);
  });

  it('confirms the PERMIT has both, which is what makes the absence legible', () => {
    const declared = parseRouteTable(REAL_404)?.declared ?? [];
    expect(declared).toContain('/v1/permits/{permit_id}/blocking-checks');
    expect(declared).toContain('/v1/permits/{permit_id}/merge');
  });
});

describe('composeAbsentCrRoutes — the struck-through list is derived, never remembered', () => {
  it('composes the two missing paths out of the deployment’s own table', () => {
    const declared = parseRouteTable(REAL_404)?.declared ?? [];
    expect(composeAbsentCrRoutes(declared)).toEqual([
      '/v1/change-requests/{cr_id}/blocking-checks',
      '/v1/change-requests/{cr_id}/merge',
    ]);
  });

  it('returns nothing when the table declares no change-request base route', () => {
    expect(composeAbsentCrRoutes(['/v1/permits/{permit_id}'])).toEqual([]);
  });

  it('drops a route the moment the deployment declares it', () => {
    // SYNTHETIC table — a hypothetical future deployment. If the missing list were a
    // constant this assertion would fail, which is the whole point of it.
    const future = [
      '/v1/change-requests/{cr_id}',
      '/v1/change-requests/{cr_id}/blocking-checks',
      '/v1/permits/{permit_id}/blocking-checks',
      '/v1/permits/{permit_id}/merge',
    ];
    expect(composeAbsentCrRoutes(future)).toEqual(['/v1/change-requests/{cr_id}/merge']);
  });

  it('follows a rename on the permit rather than keeping a stale word', () => {
    // SYNTHETIC. The sibling suffix is the source of the word, so if the deployment ever
    // called it something else, nothing here would keep asking for the old name.
    const renamed = ['/v1/change-requests/{cr_id}', '/v1/permits/{permit_id}/open-obligations'];
    expect(composeAbsentCrRoutes(renamed, ['open-obligations'])).toEqual([
      '/v1/change-requests/{cr_id}/open-obligations',
    ]);
    expect(composeAbsentCrRoutes(renamed, ['blocking-checks'])).toEqual([]);
  });
});

describe('fillTemplate — fails closed', () => {
  it('fills a placeholder from a supplied value', () => {
    expect(fillTemplate('/v1/change-requests/{cr_id}/x', { cr_id: CR_ID })).toBe(
      `/v1/change-requests/${CR_ID}/x`,
    );
  });

  it('returns null rather than a path with a brace or a gap in it', () => {
    expect(fillTemplate('/v1/change-requests/{cr_id}', { cr_id: null })).toBeNull();
    expect(fillTemplate('/v1/change-requests/{cr_id}', {})).toBeNull();
    expect(fillTemplate('/v1/change-requests/{cr_id}', { cr_id: '' })).toBeNull();
  });
});

const CR_CHECKS_ROUTE = '/v1/change-requests/{cr_id}/blocking-checks';

describe('discoverCrCheckIds — a check id comes from a live read or it does not come', () => {
  it('makes NO request and yields NO check id against the real route table', async () => {
    const io = reader();
    const found = await discoverCrCheckIds(io.reader, mustParse(REAL_404), { cr_id: CR_ID });

    expect(found.candidateRoutes).toEqual([]);
    expect(found.checkIds).toEqual([]);
    // Closing lie 1: nothing was fetched, and in particular nothing was fetched with an
    // id this file remembered, because there is no such id in this file.
    expect(io.calls).toEqual([]);
  });

  it('follows a route the deployment declares, and takes the id from the response', async () => {
    // SYNTHETIC table + SYNTHETIC response: proves the mechanism is table-driven. On the
    // day this route ships, `src/operator/change/**` needs no edit.
    const io = reader({
      [`/v1/change-requests/${CR_ID}/blocking-checks`]: {
        status: 200,
        body: JSON.stringify({ checks: [{ check_id: 'discovered-check', open: true }] }),
      },
    });

    const found = await discoverCrCheckIds(
      io.reader,
      syntheticTable(['/v1/change-requests/{cr_id}', CR_CHECKS_ROUTE]),
      { cr_id: CR_ID },
    );
    expect(found.candidateRoutes).toEqual([CR_CHECKS_ROUTE]);
    expect(found.checkIds).toEqual(['discovered-check']);
    expect(found.attempts[0]).toContain('→ 200');
  });

  it('records the attempt and yields nothing when the declared route answers non-200', async () => {
    const found = await discoverCrCheckIds(
      reader().reader,
      syntheticTable(['/v1/change-requests/{cr_id}', CR_CHECKS_ROUTE]),
      { cr_id: CR_ID },
    );
    expect(found.checkIds).toEqual([]);
    expect(found.attempts.join(' ')).toContain('→ 404');
  });

  it('ignores a 200 whose body carries nothing that looks like a check id', async () => {
    const io = reader({
      [`/v1/change-requests/${CR_ID}/blocking-checks`]: {
        status: 200,
        body: JSON.stringify({ checks: [{ note: 'no id here' }, 7, null] }),
      },
    });
    const found = await discoverCrCheckIds(
      io.reader,
      syntheticTable(['/v1/change-requests/{cr_id}', CR_CHECKS_ROUTE]),
      { cr_id: CR_ID },
    );
    expect(found.checkIds).toEqual([]);
  });

  it('does not invent a path when the placeholder cannot be filled', async () => {
    const io = reader();
    const found = await discoverCrCheckIds(
      io.reader,
      syntheticTable(['/v1/change-requests/{cr_id}', CR_CHECKS_ROUTE]),
      { cr_id: null },
    );
    expect(io.calls).toEqual([]);
    expect(found.checkIds).toEqual([]);
    expect(found.attempts.join(' ')).toContain('no value for its placeholders');
  });
});

describe('renderActionBar — disabled, reasoned, and wired to nothing', () => {
  const table = mustParse(REAL_404);

  function bar(): HTMLElement {
    return renderActionBar({
      openBlocking: 1,
      blockingConstraint: {
        constraint: 'cr_gate_closed_when_merged',
        predicate: "CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))",
        blamed_by_refusal: false,
        counters: [{ column: 'open_blocking', value: 1 }],
      },
      tables: ['mainline.change_request'],
      table,
      raw: REAL_404,
      probeLine: 'GET /v1/change-requests/x/blocking-checks → 404 · 695 bytes on the wire',
      soughtButAbsent: composeAbsentCrRoutes(table.declared),
      discoveryAttempts: [],
    });
  }

  /** Narrow by `instanceof` rather than by assertion: a wrong element fails loudly. */
  function approveButton(root: ParentNode): HTMLButtonElement {
    const found = root.querySelector('button.moc-approve');
    if (!(found instanceof HTMLButtonElement)) throw new Error('no approve button was rendered');
    return found;
  }

  it('renders the approve control disabled', () => {
    const button = approveButton(bar());
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('aria-disabled')).toBe('true');
  });

  it('names the obligation as the reason, in the database’s own words', () => {
    const text = bar().textContent ?? '';
    expect(text).toContain('1 blocking obligation is outstanding');
    expect(text).toContain('cr_gate_closed_when_merged');
    expect(text).toContain('open_blocking = 0');
    expect(text).toContain('mainline.change_request');
  });

  it('renders the 404 route table from the response, all 17 routes, plus the two missing', () => {
    const items = [...bar().querySelectorAll('li.moc-route')];
    const missing = items.filter((li) => li.classList.contains('moc-route-missing'));
    expect(items).toHaveLength(19);
    expect(missing.map((li) => li.textContent)).toEqual([
      '/v1/change-requests/{cr_id}/blocking-checks',
      '/v1/change-requests/{cr_id}/merge',
    ]);
  });

  it('shows the verbatim 404 body, byte for byte', () => {
    const pre = bar().querySelector('pre.moc-raw');
    expect(pre?.textContent).toBe(REAL_404);
  });

  it('will not strike through a route the response declares (closing lie 3)', () => {
    const rendered = renderActionBar({
      openBlocking: 1,
      blockingConstraint: null,
      tables: [],
      table,
      raw: REAL_404,
      probeLine: 'probe',
      // A caller asks for a route to be shown missing that the table in fact declares.
      soughtButAbsent: ['/v1/permits/{permit_id}/merge'],
      discoveryAttempts: [],
    });
    expect(rendered.querySelectorAll('li.moc-route-missing')).toHaveLength(0);
  });

  it('makes no claim about routes at all when the probe body could not be read', () => {
    const rendered = renderActionBar({
      openBlocking: 1,
      blockingConstraint: null,
      tables: [],
      table: null,
      raw: 'gateway timeout',
      probeLine: 'probe',
      soughtButAbsent: ['/v1/change-requests/{cr_id}/merge'],
      discoveryAttempts: [],
    });
    expect(rendered.querySelectorAll('li.moc-route')).toHaveLength(0);
    expect(rendered.textContent).toContain('makes no claim about which routes exist');
  });

  it('carries no href, no form, and no listener that could reach a merge route (lie 4)', () => {
    const rendered = bar();
    expect(rendered.querySelectorAll('a[href]')).toHaveLength(0);
    expect(rendered.querySelectorAll('form')).toHaveLength(0);
    const button = approveButton(rendered);
    // A disabled button cannot dispatch a click from a user gesture; dispatching one
    // programmatically must still do nothing, because nothing is listening.
    expect(() => {
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }).not.toThrow();
    expect(button.disabled).toBe(true);
  });
});

describe('renderObligation — what is known, and the boundary named in the same breath', () => {
  it('prints the real counter and the real predicates', () => {
    const rendered = renderObligation({
      openBlocking: 1,
      constraints: [
        {
          constraint: 'cr_gate_closed_when_merged',
          predicate: "CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))",
          blamed_by_refusal: false,
          counters: [{ column: 'open_blocking', value: 1 }],
        },
      ],
      tables: ['mainline.change_request'],
      readFrom: 'GET /v1/change-requests/x → 200',
    });
    const text = rendered.textContent ?? '';
    expect(text).toContain('counters.open_blocking = 1');
    expect(text).toContain('open_blocking = 0');
    expect(text).toContain('not reachable from any declared route');
  });

  it('renders an absence, not a zero, when the read has not landed', () => {
    const rendered = renderObligation({
      openBlocking: null,
      constraints: [],
      tables: [],
      readFrom: 'GET /v1/change-requests/x → 503',
    });
    expect(rendered.textContent).toContain('not read');
    expect(rendered.textContent).not.toContain('0 blocking obligations');
  });
});

describe('renderDefeaterPrompts — verbatim from a payload, with no way out', () => {
  it('prints the prompts exactly as given and offers no “not applicable”', () => {
    // These strings stand in for whatever a live disposition read returns. The point of
    // the test is that the module prints its argument and composes nothing.
    const rendered = renderDefeaterPrompts(
      [
        { defeater_code: 'ALPHA_CODE', prompt: 'Which alpha, and where?' },
        { defeater_code: 'BETA_CODE', prompt: 'Which beta, and at which commit?' },
      ],
      'GET /v1/checks/x/disposition → 200',
    );
    const text = rendered.textContent ?? '';
    expect(text).toContain('ALPHA_CODE');
    expect(text).toContain('Which alpha, and where?');
    expect(text).toContain('BETA_CODE');
    expect(rendered.querySelectorAll('input[type="radio"]')).toHaveLength(2);
    expect(rendered.querySelectorAll('input[type="text"]')).toHaveLength(2);
    expect(text.toLowerCase()).not.toContain('n/a');
    const values = [...rendered.querySelectorAll('input[type="radio"]')].map(
      (input) => (input as HTMLInputElement).value,
    );
    expect(values).toEqual(['ALPHA_CODE', 'BETA_CODE']);
  });
});
