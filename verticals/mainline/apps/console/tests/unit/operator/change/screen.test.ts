// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MANAGEMENT-OF-CHANGE SCREEN — what it renders, and the four things it cannot do.
 *
 * ── WHERE THE PAYLOADS BELOW CAME FROM, EXACTLY ──────────────────────────────────────
 *
 * Captured 2026-08-15 from `scripts/deploy/local_furl.py` — the real
 * `mainline_demo_api.app.handler` in process, over the local CockroachDB `mainline_demo`.
 *
 *   • `REAL_CR_RAW` and `REAL_404_RAW` are the real response bytes with **two stated
 *     edits**: every id is replaced by a `*-UNDER-TEST` placeholder, and the CR payload's
 *     `provenance` array and the pg_catalog SQL `text` are elided (this screen reads
 *     neither). The placeholders are not cosmetic — a screen that only works against the
 *     seeded ids would pass with real ones and fail with these, so they prove the screen
 *     is addressing-driven. Structure, key order, field names, enum values, counters and
 *     predicates are the deployment's, untouched; `statement_refs` and the route table
 *     are parsed out of exactly these bytes. `absence.test.ts` carries the 404 fully
 *     verbatim, ids and all.
 *   • `REAL_CLAUSE_DATA` and `REAL_DISPOSITION_DATA` are the **`data` objects of the real
 *     payloads, transcribed field for field**, ids likewise placeheld. The screen reads
 *     only `data` from those two responses. Every value is the deployment's; the byte
 *     layout is this file's, and that is stated rather than implied. Wire-byte counts
 *     printed by the screen under test are therefore this file's lengths, not the
 *     deployment's, which is why no test asserts a particular byte count.
 *
 * Nothing here was reshaped to make an assertion pass. If a value below stops matching
 * the deployment, the fix is to re-capture, never to edit the expectation.
 *
 * ── THE FOUR THINGS THIS SUITE PROVES THE SCREEN CANNOT DO ───────────────────────────
 *
 *  R12  It cannot render a proposed clause from anywhere but a `<textarea>`. The diff is
 *       reconstructed in both directions and must equal (one real string, one typed
 *       string) exactly — so a single character from any third source fails the test.
 *  R11  It cannot enable the approve control, and it cannot reach a merge route.
 *  R10  It cannot translate `checks_materialised`, and the ribbon cannot mark a step.
 *   R1  It cannot import React, the console's design system, or `features/diff/`; and it
 *       cannot contain a UUID literal, a `setTimeout`, an `innerHTML` or a bare `fetch`.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  mountChangeScreen,
  statementTables,
  type ChangeKernel,
  type KernelExchange,
} from '../../../../src/operator/change/ChangeScreen';

/* ══ verbatim bytes ═══════════════════════════════════════════════════════════════ */

/** `GET /v1/change-requests/<cr_id>` → 200. Ids placeheld, provenance/SQL elided — see above. */
const REAL_CR_RAW =
  '{"data":{"constraints":[{"blamed_by_refusal":false,"constraint":"cr_conflicts_resolved_when_merged","counters":[{"column":"open_conflicts","value":0}],"predicate":"CHECK (((state != \'merged\'::mainline.subject_state) OR (open_conflicts = 0)))"},{"blamed_by_refusal":false,"constraint":"cr_gate_closed_when_merged","counters":[{"column":"open_blocking","value":1}],"predicate":"CHECK (((state != \'merged\'::mainline.subject_state) OR (open_blocking = 0)))"},{"blamed_by_refusal":false,"constraint":"cr_identity_conserved_when_merged","counters":[{"column":"open_residue","value":0}],"predicate":"CHECK (((state != \'merged\'::mainline.subject_state) OR (open_residue = 0)))"},{"blamed_by_refusal":false,"constraint":"cr_merge_evidence","counters":[],"predicate":"CHECK (((state != \'merged\'::mainline.subject_state) OR (merged_commit IS NOT NULL)))"}],"counters":{"open_blocking":1,"open_conflicts":0,"open_residue":0},"cr_id":"CR-UNDER-TEST","external_ref":"DEMO-MOC-0001","gate_epoch":1,"head_seq":1,"merged_commit":null,"opened_at":"2026-08-01T03:00:00Z","ref_name":"refs/changes/demo-0001","site_id":"SITE-UNDER-TEST","state":"checks_materialised","target_ref":"refs/heads/main"},"envelope_version":1,"observed_at":"2026-08-15T11:05:56.371908Z","resource":"change_request","server_date":"2026-08-15T11:05:56.371908Z","staged":false,"staged_note":null,"statement_refs":[{"kind":"table","object":"mainline.change_request","text":null},{"kind":"view","object":"pg_catalog.pg_constraint","text":"SELECT con.conname"}]}';

/** `GET /v1/change-requests/<cr_id>/blocking-checks` → 404. Only the echoed id is placeheld. */
const REAL_404_RAW =
  '{"error":{"declared":["/v1/audit","/v1/change-requests/{cr_id}",' +
  '"/v1/checks/{check_id}/disposition","/v1/clauses/{clause_uuid}/ancestry",' +
  '"/v1/clauses/{clause_uuid}/versions/{commit_id}","/v1/demo/gate-run",' +
  '"/v1/demo/subjects","/v1/ledger","/v1/lessons/{lesson_id}/propagation",' +
  '"/v1/permits/{permit_id}","/v1/permits/{permit_id}/blocking-checks",' +
  '"/v1/permits/{permit_id}/checks:materialise","/v1/permits/{permit_id}/merge",' +
  '"/v1/permits/{permit_id}/silence","/v1/permits/{permit_id}/suspend",' +
  '"/v1/recall-runs/{run_id}","/v1/receipts/{receipt_id}"],' +
  '"detail":"no resource is declared at GET /v1/change-requests/CR-UNDER-TEST/' +
  'blocking-checks","kind":"no_route","status":404}}';

/**
 * The clause of record, exactly as `mainline.clause_version.canon_text` returned it,
 * `SYNTHETIC —` prefix and all. This is the ONLY clause-shaped string in this repository's
 * operator surface, it lives in a test fixture, and `src/operator/change/**` is asserted
 * below not to contain it.
 */
const REAL_CANON_TEXT =
  'SYNTHETIC — Before any intrusive work, stored energy shall be isolated, locked and ' +
  'verified at zero by a competent person.';

/** `data` of `GET /v1/clauses/<uuid>/versions/<commit>` → 200, transcribed. */
const REAL_CLAUSE_DATA = {
  version: {
    canon_text: REAL_CANON_TEXT,
    printed_label: '7.3.2(b)',
    commit_id: 'COMMIT-UNDER-TEST',
    anchor_set: ['LOTO', 'ZERO_ENERGY'],
  },
};

/** `data` of `GET /v1/checks/<check_id>/disposition` → 200, transcribed. */
const REAL_DISPOSITION_DATA = {
  check_id: 'CHECK-UNDER-TEST',
  virulence: 'blood_major',
  lattice: [
    {
      kind: 'applied',
      virulence: 'blood_major',
      min_signer_rank: 3,
      req_second_signer: false,
      req_foreign_org: false,
      req_compensating: false,
      req_predicate: false,
      req_reassert: false,
      max_ttl_hours: null,
      policy_version: 'cl-1.0',
    },
    {
      kind: 'emergency_override',
      virulence: 'blood_major',
      min_signer_rank: 5,
      req_second_signer: true,
      req_foreign_org: true,
      req_compensating: false,
      req_predicate: false,
      req_reassert: false,
      max_ttl_hours: 12,
      policy_version: 'cl-1.0',
    },
  ],
  defeater_options: [
    {
      check_id: 'CHECK-UNDER-TEST',
      defeater_code: 'MECHANISM_PRESENT_AND_VERIFIED',
      prompt: 'Which isolation point was locked, and who verified it at zero?',
      vocab_sha256: 'vocab-under-test',
    },
  ],
};

/* ══ the replay kernel ════════════════════════════════════════════════════════════ */

const CR_ID = 'CR-UNDER-TEST';
const CHECK_ID = 'CHECK-UNDER-TEST';
const CLAUSE_UUID = 'CLAUSE-UNDER-TEST';
const COMMIT_ID = 'COMMIT-UNDER-TEST';
const PERMIT_ID = 'PERMIT-UNDER-TEST';

interface Reply {
  readonly status: number;
  readonly raw: string;
  readonly data: unknown;
}

function replies(): Record<string, Reply> {
  return {
    [`/v1/change-requests/${CR_ID}`]: {
      status: 200,
      raw: REAL_CR_RAW,
      data: (JSON.parse(REAL_CR_RAW) as { data: unknown }).data,
    },
    [`/v1/change-requests/${CR_ID}/blocking-checks`]: {
      status: 404,
      raw: REAL_404_RAW,
      data: null,
    },
    [`/v1/clauses/${CLAUSE_UUID}/versions/${COMMIT_ID}`]: {
      status: 200,
      raw: JSON.stringify({ data: REAL_CLAUSE_DATA }),
      data: REAL_CLAUSE_DATA,
    },
    [`/v1/checks/${CHECK_ID}/disposition`]: {
      status: 200,
      raw: JSON.stringify({ data: REAL_DISPOSITION_DATA }),
      data: REAL_DISPOSITION_DATA,
    },
  };
}

let requested: string[] = [];

function makeKernel(overrides: Partial<ChangeKernel> = {}): ChangeKernel {
  const table = replies();
  const kernel: ChangeKernel = {
    resolveAddressing: () =>
      Promise.resolve({
        permitId: PERMIT_ID,
        crId: CR_ID,
        checkId: CHECK_ID,
        clauseUuid: CLAUSE_UUID,
        commitId: COMMIT_ID,
        absent: [],
      }),
    get: <T,>(path: string): Promise<KernelExchange<T>> => {
      requested.push(path);
      const reply = table[path] ?? { status: 404, raw: '{}', data: null };
      return Promise.resolve({
        method: 'GET',
        path,
        status: reply.status,
        wireBytes: reply.raw.length,
        receivedAt: '2026-08-15T11:05:56.371908Z',
        emulator: 'local_furl',
        data: reply.data as T | null,
        raw: reply.raw,
      });
    },
    ...overrides,
  };
  return kernel;
}

async function mount(kernel: ChangeKernel = makeKernel()): Promise<HTMLElement> {
  const host = document.createElement('div');
  document.body.append(host);
  const handle = mountChangeScreen(host, kernel);
  await handle.ready;
  return handle.root;
}

/*
 * Narrowing helpers. `instanceof` rather than `!` or `as`: if the screen ever stops
 * rendering one of these controls, the test says which one instead of failing on a null
 * dereference three lines later.
 */
function button(root: ParentNode, selector: string): HTMLButtonElement {
  const found = root.querySelector(selector);
  if (!(found instanceof HTMLButtonElement)) throw new Error(`no button at ${selector}`);
  return found;
}

function textarea(root: ParentNode, selector: string): HTMLTextAreaElement {
  const found = root.querySelector(selector);
  if (!(found instanceof HTMLTextAreaElement)) throw new Error(`no textarea at ${selector}`);
  return found;
}

/** The rendered body with the collapsed raw-payload blocks removed. */
function withoutRawPayloads(root: HTMLElement): HTMLElement {
  const copy = root.cloneNode(true) as HTMLElement;
  for (const raw of copy.querySelectorAll('details')) raw.remove();
  return copy;
}

beforeEach(() => {
  requested = [];
  document.body.replaceChildren();
});

/* ══ the header ═══════════════════════════════════════════════════════════════════ */

describe('the record, as GET /v1/change-requests/{cr_id} actually returns it', () => {
  it('renders external_ref, ref_name → target_ref, head_seq, gate_epoch and the counters', async () => {
    const text = (await mount()).textContent ?? '';
    expect(text).toContain('DEMO-MOC-0001');
    expect(text).toContain('refs/changes/demo-0001');
    expect(text).toContain('refs/heads/main');
    expect(text).toContain('head_seq');
    expect(text).toContain('gate_epoch');
    expect(text).toContain('counters.open_blocking');
    expect(text).toContain('2026-08-01T03:00:00Z');
  });

  it('keeps the branch aimed at a protected branch legible as a branch', async () => {
    const branch = (await mount()).querySelector('.moc-branch')?.textContent ?? '';
    expect(branch.replace(/\s+/g, ' ').trim()).toBe('refs/changes/demo-0001 → refs/heads/main');
  });

  it('renders merged_commit as an absence rather than as an empty cell', async () => {
    expect((await mount()).textContent).toContain('null — never merged');
  });

  it('renders all four constraints with their predicates and the table they sit on', async () => {
    const text = (await mount()).textContent ?? '';
    for (const name of [
      'cr_conflicts_resolved_when_merged',
      'cr_gate_closed_when_merged',
      'cr_identity_conserved_when_merged',
      'cr_merge_evidence',
    ]) {
      expect(text).toContain(name);
    }
    expect(text).toContain("CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))");
    expect(text).toContain('mainline.change_request');
  });

  it('reads the table names out of the verbatim envelope bytes', () => {
    expect(statementTables(REAL_CR_RAW)).toEqual(['mainline.change_request']);
    expect(statementTables('not json')).toEqual([]);
  });
});

/* ══ the ribbon ═══════════════════════════════════════════════════════════════════ */

describe('the IChemE ribbon sits BESIDE our state, never asserts it', () => {
  it('renders the five steps and the close-out band', async () => {
    const steps = [...(await mount()).querySelectorAll('.moc-step')].map((li) => li.textContent);
    expect(steps).toEqual([
      'Initiate',
      'Screen',
      'Review',
      'Approve',
      'Implement',
      'Capture and Close-out',
    ]);
  });

  it('marks NO step as current — there is no column that would justify one', async () => {
    const root = await mount();
    expect(root.querySelectorAll('[aria-current]')).toHaveLength(0);
    for (const step of root.querySelectorAll('.moc-step')) {
      expect(step.className).not.toMatch(/current|active|done|complete/);
    }
    expect(root.textContent).toContain('No step is marked current');
  });

  it('prints checks_materialised verbatim and does not translate it', async () => {
    const chip = (await mount()).querySelector('.moc-statechip');
    expect(chip?.querySelector('code')?.textContent).toBe('checks_materialised');
    expect(chip?.textContent).toContain('mainline.change_request.state');
    const text = (await mount()).textContent?.toLowerCase() ?? '';
    for (const gloss of ['awaiting review', 'in review', 'under review', 'pending approval']) {
      expect(text).not.toContain(gloss);
    }
  });
});

/* ══ the OSHA five ════════════════════════════════════════════════════════════════ */

describe('the body is 29 CFR 1910.119(l)(2), in the regulation’s own words', () => {
  it('renders the five headings verbatim and in order', async () => {
    const headings = [...(await mount()).querySelectorAll('.moc-section-heading')].map(
      (h) => h.textContent,
    );
    expect(headings).toEqual([
      'The technical basis for the proposed change',
      'Impact of change on safety and health',
      'Modifications to operating procedures',
      'Necessary time period for the change',
      'Authorization requirements for the proposed change',
    ]);
  });

  it('cites each heading to its paragraph', async () => {
    const cites = [...(await mount()).querySelectorAll('.moc-section-cite')].map(
      (c) => c.textContent,
    );
    expect(cites).toEqual([
      '1910.119(l)(2)(i)',
      '1910.119(l)(2)(ii)',
      '1910.119(l)(2)(iii)',
      '1910.119(l)(2)(iv)',
      '1910.119(l)(2)(v)',
    ]);
  });

  it('renders (iv) as an absence, and points at the one real ceiling instead', async () => {
    const period = [...(await mount()).querySelectorAll('.moc-section')][3];
    const text = period?.textContent ?? '';
    expect(text).toContain('Not carried by this deployment');
    expect(text).toContain('has no column for a time period');
    expect(text).toContain('emergency_override max_ttl_hours = 12');
  });

  it('renders (v) as the live authorisation matrix with its scope named', async () => {
    const auth = [...(await mount()).querySelectorAll('.moc-section')][4];
    expect(auth?.querySelectorAll('tbody tr')).toHaveLength(2);
    expect(auth?.textContent).toContain('keyed by VIRULENCE, not by subject');
  });
});

/* ══ R12 — the proposed text ══════════════════════════════════════════════════════ */

describe('R12 — no proposed clause text exists, so none is rendered', () => {
  it('quotes the clause of record verbatim, exactly once in the rendered body', async () => {
    const root = await mount();
    expect(root.querySelector('blockquote.moc-quote')?.textContent).toBe(REAL_CANON_TEXT);

    // The clause text legitimately appears a second time, inside the collapsed verbatim
    // payload the raw-payload affordance offers (R18) — that is the response's own bytes
    // and hiding it would be the dishonest move. Outside the raw blocks it appears once.
    const rendered = withoutRawPayloads(root);

    expect((rendered.textContent ?? '').split(REAL_CANON_TEXT)).toHaveLength(2);
  });

  it('does not claim the change request targets that clause', async () => {
    const text = (await mount()).textContent ?? '';
    expect(text).toContain('has no target-clause column');
    expect(text).toContain('no edge from this record to this clause is asserted here');
  });

  it('leaves the proposed-wording box empty — no value, no defaultValue', async () => {
    const field = textarea(await mount(), '#moc-proposed-text');
    expect(field.value).toBe('');
    expect(field.defaultValue).toBe('');
    expect(field.textContent).toBe('');
  });

  it('renders no diff at all before anything is typed', async () => {
    const root = await mount();
    button(root, 'button.moc-compare').click();
    expect(root.querySelectorAll('.moc-diff')).toHaveLength(0);
    expect(root.textContent).toContain('Nothing has been typed');
  });

  it('reconstructs to exactly (one real string, one typed string) — nothing else', async () => {
    const root = await mount();
    const field = textarea(root, '#moc-proposed-text');

    // Deliberately unlike the clause: if any token of the rendered right-hand side came
    // from a third source, the reconstruction below would not equal this string.
    const typed = 'Zephyr quokka must ratify every luminous isolation before dusk.';
    field.value = typed;
    button(root, 'button.moc-compare').click();

    const diff = root.querySelector('.moc-diff');
    expect(diff).not.toBeNull();
    const spans = [...(diff?.querySelectorAll('span') ?? [])];

    const left = spans
      .filter((s) => !s.classList.contains('moc-diff-ins'))
      .map((s) => s.textContent ?? '')
      .join('');
    const right = spans
      .filter((s) => !s.classList.contains('moc-diff-del'))
      .map((s) => s.textContent ?? '')
      .join('');

    expect(left).toBe(REAL_CANON_TEXT);
    expect(right).toBe(typed);

    // Every inserted token must be a token of what was typed. This is the assertion that
    // a hard-coded "proposed" clause would fail.
    const typedTokens = new Set(typed.split(/(\s+)/).filter((t) => t !== ''));
    for (const span of spans.filter((s) => s.classList.contains('moc-diff-ins'))) {
      expect(typedTokens.has(span.textContent ?? '')).toBe(true);
    }
  });

  it('labels the comparison as computed here, not as a kernel claim', async () => {
    const root = await mount();
    textarea(root, '#moc-proposed-text').value = 'something else';
    button(root, 'button.moc-compare').click();
    const text = root.textContent ?? '';
    expect(text).toContain('Computed in this browser, just now');
    expect(text).toContain('no part of the right-hand side came from the database');
  });
});

/* ══ R11 — the absence, at screen level ══════════════════════════════════════════ */

describe('R11 — the approve control is disabled and the absence is on screen', () => {
  it('renders the approve control disabled with the obligation as the reason', async () => {
    const root = await mount();
    const approve = button(root, 'button.moc-approve');
    expect(approve.disabled).toBe(true);
    expect(approve.textContent).toBe('Approve change');
    const reason = root.querySelector('#moc-approve-reason')?.textContent ?? '';
    expect(reason).toContain('1 blocking obligation is outstanding');
  });

  it('renders the route table from the actual 404 body, not from a constant', async () => {
    const root = await mount();
    expect(root.querySelector('.moc-evidence pre.moc-raw')?.textContent).toBe(REAL_404_RAW);
    expect(root.querySelectorAll('li.moc-route')).toHaveLength(19);
    expect([...root.querySelectorAll('li.moc-route-missing')].map((li) => li.textContent)).toEqual([
      '/v1/change-requests/{cr_id}/blocking-checks',
      '/v1/change-requests/{cr_id}/merge',
    ]);
  });

  it('renders NO defeater prompts, and says why they are unreachable', async () => {
    const root = await mount();
    expect(root.querySelectorAll('.moc-prompt')).toHaveLength(0);
    expect(root.querySelectorAll('input[type="radio"]')).toHaveLength(0);
    expect(root.textContent).toContain('they are unreachable');
  });

  it('does not borrow the permit’s defeater vocabulary into the rendered body', async () => {
    // The disposition read this screen makes for the LATTICE also returns the addressable
    // check's own defeater options. They belong to a different subject and must not be
    // presented here as the change request's. They remain visible in the collapsed
    // verbatim payload, because that is the response and R18 requires it whole — but
    // nothing outside that block may show them.
    const root = await mount();
    const rendered = withoutRawPayloads(root);

    expect(rendered.textContent).not.toContain('MECHANISM_PRESENT_AND_VERIFIED');
    expect(rendered.textContent).not.toContain('Which isolation point was locked');
  });

  it('never requests a merge route, for either subject', async () => {
    await mount();
    expect(requested.filter((path) => path.includes('merge'))).toEqual([]);
    expect(requested.filter((path) => path.includes('/v1/permits/'))).toEqual([]);
  });

  it('supplies only this subject’s id to route discovery, never another subject’s', async () => {
    // A future `/v1/change-requests/{cr_id}/checks/{check_id}` must NOT be filled with the
    // permit's check id. It fails closed instead, and says so.
    const kernel = makeKernel();
    const root = await mount({
      resolveAddressing: kernel.resolveAddressing.bind(kernel),
      get: <T,>(path: string): Promise<KernelExchange<T>> =>
        path.endsWith('/blocking-checks')
          ? Promise.resolve({
              method: 'GET',
              path,
              status: 404,
              wireBytes: 0,
              receivedAt: '2026-08-15T11:05:56.371908Z',
              emulator: 'local_furl',
              data: null,
              raw: JSON.stringify({
                error: {
                  declared: [
                    '/v1/change-requests/{cr_id}',
                    '/v1/change-requests/{cr_id}/checks/{check_id}',
                  ],
                  detail: 'synthetic',
                  kind: 'no_route',
                  status: 404,
                },
              }),
            })
          : kernel.get<T>(path),
    });
    expect(requested.filter((path) => path.includes('/checks/'))).toEqual([
      `/v1/checks/${CHECK_ID}/disposition`,
    ]);
    expect(root.textContent).toContain('no value for its placeholders');
  });

  it('requests exactly the four reads it needs, and no more', async () => {
    await mount();
    expect(requested).toEqual([
      `/v1/change-requests/${CR_ID}`,
      `/v1/change-requests/${CR_ID}/blocking-checks`,
      `/v1/clauses/${CLAUSE_UUID}/versions/${COMMIT_ID}`,
      `/v1/checks/${CHECK_ID}/disposition`,
    ]);
  });
});

describe('absence propagates rather than being papered over', () => {
  it('renders nothing but a stated absence when addressing yields no change request', async () => {
    const root = await mount(
      makeKernel({
        resolveAddressing: () =>
          Promise.resolve({
            permitId: null,
            crId: null,
            checkId: null,
            clauseUuid: null,
            commitId: null,
            absent: [
              { subject: 'change_request', relation: 'demo world', reason: 'not seeded here' },
            ],
          }),
      }),
    );
    expect(root.textContent).toContain('did not address a change request');
    expect(root.textContent).toContain('not seeded here');
    expect(root.textContent).not.toContain('DEMO-MOC-0001');
    expect(requested).toEqual([]);
  });

  it('renders an absence, not a clause, when the clause read returns nothing', async () => {
    const kernel = makeKernel();
    const root = await mount({
      resolveAddressing: kernel.resolveAddressing.bind(kernel),
      get: <T,>(path: string): Promise<KernelExchange<T>> =>
        path.includes('/versions/')
          ? Promise.resolve({
              method: 'GET',
              path,
              status: 503,
              wireBytes: 0,
              receivedAt: '2026-08-15T11:05:56.371908Z',
              emulator: 'local_furl',
              data: null,
              raw: '',
            })
          : kernel.get<T>(path),
    });
    expect(root.querySelectorAll('blockquote.moc-quote')).toHaveLength(0);
    expect(root.textContent).toContain('no text is quoted');
  });
});

describe('every rendered exchange is traceable to a real response', () => {
  it('prints the method, path, status, wire bytes, clock and emulator header', async () => {
    const line = (await mount()).querySelector('.moc-exchange')?.textContent ?? '';
    expect(line).toContain('GET /v1/change-requests/');
    expect(line).toContain('→ 200');
    expect(line).toContain('bytes on the wire');
    expect(line).toContain('this browser’s clock');
    expect(line).toContain('x-mainline-emulator: local_furl');
  });

  it('offers the verbatim payload of every read it made, in reading order (R18)', async () => {
    const root = await mount();
    const summaries = [...root.querySelectorAll('details summary')].map((s) => s.textContent);
    expect(summaries).toEqual([
      'Raw payload — change request',
      'Raw payload — blocking-checks probe (404)',
      'Raw payload — clause version',
      'Raw payload — disposition, the addressable check (NOT this change request’s)',
    ]);

    const raws = [...root.querySelectorAll('details pre.moc-raw')].map((pre) => pre.textContent);
    expect(raws).toContain(REAL_CR_RAW);
    expect(raws).toContain(REAL_404_RAW);
    // One panel per read: a screen that made four requests and offered three payloads
    // would be hiding one, and the hidden one is the one worth seeing.
    expect(raws).toHaveLength(requested.length);
  });

  it('still offers the payloads it did get when a later read cannot be addressed', async () => {
    const kernel = makeKernel();
    const root = await mount({
      resolveAddressing: () =>
        Promise.resolve({
          permitId: PERMIT_ID,
          crId: CR_ID,
          checkId: null,
          clauseUuid: null,
          commitId: null,
          absent: [],
        }),
      get: kernel.get.bind(kernel),
    });
    expect(root.textContent).toContain('No check id was addressable in this page load');
    expect([...root.querySelectorAll('details summary')].map((s) => s.textContent)).toEqual([
      'Raw payload — change request',
      'Raw payload — blocking-checks probe (404)',
    ]);
  });
});

/* ══ R1 / R12 — what the SOURCE of this directory may not contain ═════════════════ */

const SOURCES = import.meta.glob<string>('../../../../src/operator/change/**/*.{ts,css}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

describe('the source of src/operator/change/** — the grep the brief asks for', () => {
  it('finds every module in the directory, so no file escapes the greps below', () => {
    const names = Object.keys(SOURCES)
      .map((path) => path.split('/').pop())
      .sort();
    expect(names).toEqual([
      'ChangeScreen.ts',
      'absence.ts',
      'change.css',
      'lattice.ts',
      'osha-sections.ts',
      'ribbon.ts',
      'screen.ts',
    ]);
  });

  it('binds the kernel in exactly one file — screen.ts, and nowhere else', () => {
    // The screen takes its kernel as a parameter. If a second module ever reached for
    // `kernel/` directly, this screen would have two data sources and the port would stop
    // being the single place to look.
    const binders = Object.entries(SOURCES).filter(([, source]) =>
      /from\s+['"][^'"]*kernel\//.test(source),
    );
    expect(binders.map(([path]) => path.split('/').pop())).toEqual(['screen.ts']);
  });

  it('contains NO UUID literal anywhere', () => {
    const uuid = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(uuid.test(source), `${path} contains a UUID literal`).toBe(false);
    }
  });

  it('contains no clause text — the only real clause string lives in this fixture', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(source.includes(REAL_CANON_TEXT), `${path} carries the clause text`).toBe(false);
      expect(/stored energy shall be/i.test(source), `${path} carries clause prose`).toBe(false);
    }
  });

  /*
   * Each pattern below matches the ACT, not the discussion of it. These modules are
   * required to explain in prose why they do not call `setTimeout`, why they never touch
   * `innerHTML`, and why `features/diff/` is out of bounds — a grep that failed on the
   * explanation would push those sentences out of the source, which is the opposite of
   * what this suite is for.
   */

  it('never writes a literal string into a field a human types into', () => {
    // `placeholder` is deliberately NOT in this pattern. R9 requires these fields to
    // carry one: it is styled as placeholder text, it vanishes on the first keypress, and
    // it is what stops a still frame from reading an empty box as a missing value. `value`
    // and `textContent` are the assignments that would put content there and stay.
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(/\.(value|textContent|innerText)\s*=\s*['"`]/.test(source), path).toBe(false);
      expect(/defaultValue\s*=[^=]/.test(source), `${path} assigns defaultValue`).toBe(false);
    }
  });

  it('leaves every typed field empty at mount, whatever the source says', async () => {
    const root = await mount();
    for (const field of root.querySelectorAll('textarea')) {
      expect(field.value).toBe('');
      expect(field.defaultValue).toBe('');
      expect(field.textContent).toBe('');
    }
    for (const field of root.querySelectorAll('input')) {
      expect(field.value).toBe('');
    }
  });

  it('calls no timer — nothing here can fake work', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(/\b(setTimeout|setInterval|requestIdleCallback)\s*\(/.test(source), path).toBe(false);
      expect(/@keyframes|animation\s*:|transition\s*:/.test(source), path).toBe(false);
    }
  });

  it('builds DOM without innerHTML, outerHTML or insertAdjacentHTML', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(
        /\.(inner|outer)HTML\s*=|insertAdjacentHTML\s*\(|document\.write\s*\(/.test(source),
        path,
      ).toBe(false);
    }
  });

  it('never calls fetch, XMLHttpRequest or names an absolute origin', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(/\bfetch\s*\(|new\s+XMLHttpRequest|new\s+EventSource|new\s+WebSocket/.test(source), path).toBe(
        false,
      );
      expect(/https?:\/\//.test(source), `${path} names an absolute origin`).toBe(false);
    }
  });

  it('imports nothing from React or from the console’s own surfaces (R1)', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(/from\s+['"]react/.test(source), `${path} imports React`).toBe(false);
      expect(
        /from\s+['"][^'"]*\/(app|design|features|verify|data)\//.test(source),
        `${path} imports a console surface`,
      ).toBe(false);
      expect(
        /from\s+['"][^'"]*features\/diff/.test(source),
        `${path} reaches for features/diff`,
      ).toBe(false);
    }
  });

  it('carries an SPDX header on every file', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(source.includes('SPDX-License-Identifier: FSL-1.1-ALv2'), path).toBe(true);
      expect(source.includes('SPDX-FileCopyrightText: 2026 MAINLINE contributors'), path).toBe(
        true,
      );
    }
  });
});

/* ══ a mounted screen must not have acquired a second data source ═════════════════ */

describe('the screen has exactly one way to get data', () => {
  it('makes no request at all if the kernel is never asked', () => {
    const spy = vi.fn();
    const host = document.createElement('div');
    mountChangeScreen(host, {
      resolveAddressing: () =>
        new Promise(() => {
          /* never resolves: the screen must render its chrome and then wait */
        }),
      get: spy,
    });
    expect(spy).not.toHaveBeenCalled();
    expect(host.querySelector('.moc-title')?.textContent).toBe('Management of change');
    expect(host.textContent).toContain('Reading the change request…');
  });
});
