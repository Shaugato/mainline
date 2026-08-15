// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REFUSAL BANNER, AND THE THINGS IT MUST REFUSE TO RENDER.
 *
 * Three claims are worth more than the rest of this file put together:
 *
 *   1. **The banner renders NOTHING when a beat is absent.** A refusal that appears
 *      without a payload behind it is a fabricated exhibit, whatever it says inside.
 *   2. **A 40001 retry is never rendered as a refusal.** An undecided transaction has no
 *      reason set — `spec/wire/refusal.schema.json` excludes the code from its enum for
 *      exactly this reason — so it gets a notice that says NOT DECIDED, HTTP 503, and no
 *      auto-retry.
 *   3. **The shipped source of `src/operator/issue/**` contains no scheduling primitive,
 *      no SQLSTATE literal and no constraint name.** That is asserted against the file
 *      TEXT at the bottom of this file, because an assertion about what a screen renders
 *      can be satisfied by a constant, and an assertion about the bytes cannot.
 */

import { describe, expect, it } from 'vitest';

import { toBeatView, type RunReading } from '../../../../src/operator/issue/beats';
import {
  renderRefusalBanner,
  renderUndecidedNotice,
} from '../../../../src/operator/issue/RefusalBanner';

import type { Beat, GateRun } from '../../../../src/data/types.generated';

// ───────────────────────────────────────────────────────────────────────────────────────
// Fixtures, transcribed from evidence/deploy/live-gate-run.json and typed against the
// generated contract so a drifted shape stops compiling.
// ───────────────────────────────────────────────────────────────────────────────────────

const PERMIT = 'dec0de00-0006-4000-8000-000000000001';
const OBLIGATION = 'dec0de00-0007-4000-8000-000000000001';
const PRECURSOR = 'dec0de00-0005-4000-8000-000000000001';

const BASE = {
  ordinal: 1,
  name: 'read',
  label: 'The permit, and the obligation that is still open on it.',
  expected: { outcome: 'read' },
  outcome: 'read',
  sqlstate: '00000',
  constraint: null,
  constraint_source: null,
  message: null,
  matched_expectation: true,
  elapsed_ms: 0.011,
  statement: 'SELECT … FROM mainline.permit …',
  refusal: null,
  observed: { state: 'dispositioned', open_blocking_derived: 1 },
  note: null,
} satisfies Beat;

const CHECK_MESSAGE =
  "failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))";

const MERGE = {
  ...BASE,
  ordinal: 2,
  name: 'merge',
  label: 'MERGE the permit. One open obligation, no signed disposition.',
  expected: {
    outcome: 'refused',
    sqlstate: '23514',
    constraint: 'gate_closed_when_issued',
    constraint_source: 'reported',
  },
  outcome: 'refused',
  sqlstate: '23514',
  constraint: 'gate_closed_when_issued',
  constraint_source: 'reported',
  message: CHECK_MESSAGE,
  elapsed_ms: 572.251,
  statement: 'CALL mainline.merge_permit(%s, %s)',
  refusal: {
    spec_version: '1.0.0-rc.1',
    refusal_id: '7d0dd6bd-acab-4dcf-ba71-a08dd7d59bc8',
    observed_at: '2026-08-14T22:10:33Z',
    class: 'gate',
    sqlstate: '23514',
    constraint: 'gate_closed_when_issued',
    constraint_source: 'reported',
    message: CHECK_MESSAGE,
    subject_kind: 'permit',
    subject_id: PERMIT,
    gate_epoch: 1,
    diagnosis: 'declarative',
    probe_calls: 0,
    mus: [
      {
        kind: 'obligation',
        obligation_id: OBLIGATION,
        origin: 'blame_ancestry',
        event_id: PRECURSOR,
        severity: 4,
        virulence: 'blood_major',
      },
    ],
    naa: {
      kind: 'dispose_obligations',
      obligation_ids: [OBLIGATION],
      cardinality: 1,
      description: '1 obligation(s) remain open on this subject',
    },
    naa_reason: null,
  },
  observed: {},
} satisfies Beat;

const ATTACK_MESSAGE =
  'MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero';

const ATTACK = {
  ...MERGE,
  ordinal: 3,
  name: 'projection_drift_attack',
  label: 'THE ATTACK: force the projected counter to zero out of band, then merge again.',
  expected: {
    outcome: 'refused',
    sqlstate: 'P0001',
    constraint: 'mainline.fn_permit_merge_gate',
    constraint_source: 'parsed',
  },
  sqlstate: 'P0001',
  constraint: 'mainline.fn_permit_merge_gate',
  constraint_source: 'parsed',
  message: ATTACK_MESSAGE,
  elapsed_ms: 564.509,
  statement: 'UPDATE mainline.permit SET open_blocking = 0 …; CALL mainline.merge_permit(…)',
  refusal: {
    ...MERGE.refusal,
    refusal_id: '868322e7-95b3-44d9-9b43-2254a9ad32a6',
    sqlstate: 'P0001',
    constraint: 'mainline.fn_permit_merge_gate',
    constraint_source: 'parsed',
    message: ATTACK_MESSAGE,
    diagnosis: 'none',
    mus: [{ kind: 'capability_gap', capability: 'mainline.fn_permit_merge_gate' }],
    naa: null,
    naa_reason: 'not_computable',
  },
  observed: {
    attack: 'mainline.permit.open_blocking set out of band',
    counter_forced_to: 0,
    open_blocking_derived: 1,
  },
} satisfies Beat;

const ADMIT = {
  ...BASE,
  ordinal: 4,
  name: 'admit',
  label: 'Sign one disposition against the obligation, then merge again.',
  expected: { outcome: 'admitted', sqlstate: '00000' },
  outcome: 'admitted',
  observed: { disposition_kind: 'applied', open_blocking_after_signature: 0 },
} satisfies Beat;

/** A beat abandoned by SQLSTATE 40001. It carries NO refusal payload — by contract. */
const RETRY = {
  ...BASE,
  ordinal: 2,
  name: 'merge',
  outcome: 'retry',
  sqlstate: '40001',
  refusal: null,
  matched_expectation: false,
  note: 'the transaction was rolled back undecided',
} satisfies Beat;

const OPTIONS = { priorRefusals: 0 } as const;

function undecidedReading(): RunReading {
  const run = {
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    run_id: 'rehearsal',
    generated_at: '2026-08-14T22:10:33Z',
    outcome: 'retry',
    verdict: 'NOT PROVEN',
    failures: ['the run was abandoned as undecided'],
    persisted: false,
    elapsed_ms: 91.2,
    transaction: {
      isolation: 'SERIALIZABLE',
      disposition: 'rolled_back',
      opened_logical_timestamp: '1786745433293875086.0000000000',
      closed_logical_timestamp: null,
      single_transaction: true,
      savepoints: ['gate_run_beat_2'],
      retry_sqlstate: '40001',
      canonicalisation: 'mainline_demo_api.gate_run.canonical_json',
    },
    subject: {
      subject_kind: 'permit',
      subject_id: PERMIT,
      external_ref: 'DEMO-PTW-0001',
      state: 'dispositioned',
      head_seq: 2,
      gate_epoch: 1,
      open_blocking: 1,
      open_blocking_derived: 1,
      blocking_check_id: OBLIGATION,
      exposure_receipt_id: null,
      site_code: 'dec0de00-0001-4000-8000-000000000001',
    },
    beats: [BASE, RETRY, ADMIT, ADMIT],
    persistence_check: {
      before: { row_counts: {}, subject_row_counts: {}, permit_row: null },
      after: { row_counts: {}, subject_row_counts: {}, permit_row: null },
      identical: true,
      self_persisted: false,
      self_evidence: {
        minted_disposition_id: null,
        minted_disposition_rows_after_rollback: 0,
        subject_row_counts_before: {},
        subject_row_counts_after: {},
        permit_row_identical: true,
      },
      concurrent_writes: null,
      tables: ['mainline.permit'],
      note: 'nothing was attempted after the abort',
    },
  } satisfies GateRun;

  return {
    kind: 'undecided',
    run,
    retrySqlstate: run.transaction.retry_sqlstate,
    httpStatus: 503,
    facts: { status: 503, wireBytes: 1_024, receivedAt: '2026-08-14T22:10:35.412Z', data: run },
  };
}

function rowText(banner: HTMLElement, key: string): string {
  return banner.querySelector(`dd[data-row="${key}"]`)?.textContent ?? '';
}

// ───────────────────────────────────────────────────────────────────────────────────────

describe('the banner renders nothing without a refusal behind it', () => {
  it('renders nothing when the beat is absent', () => {
    expect(renderRefusalBanner(null, OPTIONS)).toBeNull();
    expect(renderRefusalBanner(undefined, OPTIONS)).toBeNull();
  });

  it('renders nothing for the read beat', () => {
    expect(renderRefusalBanner(toBeatView(BASE), OPTIONS)).toBeNull();
  });

  it('renders nothing for the admitted beat', () => {
    expect(renderRefusalBanner(toBeatView(ADMIT), OPTIONS)).toBeNull();
  });

  it('renders nothing for a 40001 beat — an undecided transaction is NOT a refusal', () => {
    expect(renderRefusalBanner(toBeatView(RETRY), OPTIONS)).toBeNull();
  });
});

describe('the database register carries the database’s own words', () => {
  const banner = renderRefusalBanner(toBeatView(MERGE), OPTIONS);

  it('rendered at all', () => {
    expect(banner).not.toBeNull();
  });

  it('prints the payload’s sqlstate, constraint and constraint_source', () => {
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'sqlstate')).toBe(MERGE.sqlstate);
    expect(rowText(banner, 'constraint')).toContain(MERGE.constraint);
    expect(rowText(banner, 'constraint')).toContain(MERGE.constraint_source);
    expect(banner.dataset.sqlstate).toBe(MERGE.sqlstate);
  });

  it('prints the CHECK predicate lifted out of the message, and the message verbatim', () => {
    if (banner === null) throw new Error('no banner');
    const predicate = rowText(banner, 'predicate');
    expect(MERGE.message).toContain(predicate.split('Read out of')[0]?.trim() ?? '');
    expect(rowText(banner, 'message')).toBe(MERGE.message);
  });

  it('prints the statement the beat actually sent', () => {
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'statement')).toBe(MERGE.statement);
  });

  it('states the ABSENCE where the payload does not name the raising object', () => {
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'raised-by')).toContain('Not named in this payload');
  });

  it('prints the payload’s own elapsed_ms and says the server measured it', () => {
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'elapsed')).toContain('572.3 ms');
    expect(rowText(banner, 'elapsed')).toContain('server');
  });

  it('is a banner over a locked action, never a modal (R15)', () => {
    if (banner === null) throw new Error('no banner');
    expect(banner.getAttribute('role')).toBe('alert');
    expect(banner.getAttribute('aria-modal')).toBeNull();
    expect(banner.querySelector('dialog')).toBeNull();
    expect(banner.querySelector('[role="dialog"]')).toBeNull();
  });

  it('is filmed calm — beat 2 is a CHECK refusing a write, not the climax', () => {
    if (banner === null) throw new Error('no banner');
    expect(banner.dataset.emphasis).toBe('calm');
  });
});

describe('the operator register speaks the supervisor’s language', () => {
  it('names what is outstanding and which precursor was never answered', () => {
    const banner = renderRefusalBanner(toBeatView(MERGE), OPTIONS);
    if (banner === null) throw new Error('no banner');
    const facts = banner.querySelector('.cow-refusal__facts')?.textContent ?? '';
    expect(banner.querySelector('.cow-refusal__headline')?.textContent).toBe('PERMIT NOT ISSUED');
    expect(facts).toContain('obligation outstanding');
    expect(facts).toContain(PRECURSOR);
  });

  it('uses a real external reference when a read supplied one, and never invents one', () => {
    const withRef = renderRefusalBanner(toBeatView(MERGE), {
      priorRefusals: 0,
      precursorLabel: 'DEMO-INC-0001',
    });
    expect(withRef?.textContent).toContain('DEMO-INC-0001');

    const noEvents = {
      ...MERGE,
      refusal: { ...MERGE.refusal, mus: [{ kind: 'capability_gap', capability: 'x' }] },
    } satisfies Beat;
    const banner = renderRefusalBanner(toBeatView(noEvents), OPTIONS);
    expect(banner?.textContent).not.toContain('has never been answered');
  });
});

describe('beat 3 is the peak, and its diagnosis is honestly weaker', () => {
  const banner = renderRefusalBanner(toBeatView(ATTACK), { priorRefusals: 1 });

  it('lands harder: STILL not issued, at peak emphasis', () => {
    if (banner === null) throw new Error('no banner');
    expect(banner.querySelector('.cow-refusal__headline')?.textContent).toBe(
      'PERMIT STILL NOT ISSUED',
    );
    expect(banner.dataset.emphasis).toBe('peak');
  });

  it('quotes the forged counter and the re-derived count from the payload', () => {
    if (banner === null) throw new Error('no banner');
    const facts = banner.querySelector('.cow-refusal__facts')?.textContent ?? '';
    expect(facts).toContain(`counter now reads ${ATTACK.observed.counter_forced_to}`);
    expect(facts).toContain(`and got ${ATTACK.observed.open_blocking_derived}`);
    expect(facts).toContain(ATTACK.observed.attack);
  });

  it('renders constraint_source: parsed as a WEAKENED diagnosis', () => {
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'constraint')).toContain(ATTACK.constraint_source);
    expect(rowText(banner, 'constraint')).toContain('weakened diagnosis');
  });

  it('names the raising object from the qualified exhibit', () => {
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'raised-by')).toContain(ATTACK.constraint);
  });

  it('reports that a nearest admissible alternative was NOT COMPUTABLE, with its reason', () => {
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'naa')).toContain('NOT COMPUTABLE');
    expect(rowText(banner, 'naa')).toContain(ATTACK.refusal.naa_reason);
    expect(rowText(banner, 'diagnosis')).toContain(ATTACK.refusal.diagnosis);
  });
});

describe('a run that did not match its expectation says so', () => {
  it('renders the mismatch and the note rather than swallowing it', () => {
    const unmatched = { ...MERGE, matched_expectation: false, note: 'observed an admission' } satisfies Beat;
    const banner = renderRefusalBanner(toBeatView(unmatched), OPTIONS);
    if (banner === null) throw new Error('no banner');
    expect(rowText(banner, 'unmatched')).toContain('observed an admission');
  });
});

describe('the undecided transaction is never dressed as a refusal', () => {
  it('renders nothing for a completed reading', () => {
    const completed: RunReading = {
      kind: 'unreadable',
      httpStatus: 500,
      facts: { status: 500, wireBytes: 0, receivedAt: '2026-08-14T22:10:35.412Z', data: null },
    };
    expect(renderUndecidedNotice(completed)).toBeNull();
  });

  it('says NOT DECIDED, carries the payload’s sqlstate and the 503, and offers no auto-retry', () => {
    const reading = undecidedReading();
    const notice = renderUndecidedNotice(reading);
    if (notice === null) throw new Error('no notice');
    expect(notice.className).not.toContain('cow-refusal');
    expect(notice.getAttribute('role')).toBe('status');
    expect(notice.textContent).toContain('NOT DECIDED');
    expect(notice.textContent).toContain('no refusal');
    expect(rowText(notice, 'sqlstate')).toBe(
      reading.kind === 'undecided' ? reading.retrySqlstate : '',
    );
    expect(rowText(notice, 'http')).toBe('503');
    // No control inside the notice re-sends anything: the caller decides.
    expect(notice.querySelector('button')).toBeNull();
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// SOURCE HYGIENE — asserted against the shipped bytes, not against a render
// ───────────────────────────────────────────────────────────────────────────────────────

const RAW: Record<string, unknown> = import.meta.glob('/src/operator/issue/*.{ts,css}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/**
 * The glob's values as TEXT, with the type narrowed here rather than at every use.
 *
 * A `?raw` glob that lost its `import: 'default'` yields modules, every `includes()` below
 * becomes a call on an object, and the whole scan passes by never matching anything. So a
 * value that is not a string throws at load rather than being coerced.
 */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(RAW).map(([path, value]) => {
    if (typeof value !== 'string') {
      throw new Error(`${path} did not load as text; the raw glob is missing import: 'default'.`);
    }
    return [path, value];
  }),
);

/**
 * Every token that would mean the screen had stopped reading and started asserting.
 *
 * The SQLSTATEs and the constraint names are the exhibits the demo exists to show; if one
 * of them appears in this directory's source, the screen can render it without the database
 * having said it, and no amount of test coverage over the render can tell the difference.
 * The two scheduling primitives are here because faked latency is the failure the brief
 * names by name.
 */
const BANNED: readonly string[] = [
  'setTimeout',
  'setInterval',
  '23514',
  '23503',
  '23505',
  'P0001',
  'gate_closed_when_issued',
  'fn_permit_merge_gate',
  'boundary_certified_when_issued',
  'clearance_digest_present_when_merged',
];

/**
 * R4's wrong turn is CODE that addresses the write-protected merge route. The rule itself
 * has to be written down in these files as a comment, so the check is made against the
 * source with its comments removed: naming the trap in prose is required, reaching for it
 * in a statement is the defect.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

describe('the shipped source of src/operator/issue/**', () => {
  const entries = Object.entries(SOURCES);

  it('was actually read — a glob that matches nothing passes every check below', () => {
    expect(entries.length).toBeGreaterThanOrEqual(6);
    expect(Object.keys(SOURCES)).toContain('/src/operator/issue/ActionBar.ts');
    expect(Object.keys(SOURCES)).toContain('/src/operator/issue/issue.css');
  });

  it('contains no scheduling primitive, no SQLSTATE literal and no constraint name', () => {
    for (const [path, source] of entries) {
      for (const token of BANNED) {
        expect(source.includes(token), `${path} contains the banned token ${token}`).toBe(false);
      }
    }
  });

  it('states R4 in prose and never addresses the merge route in code', () => {
    const actionBar = SOURCES['/src/operator/issue/ActionBar.ts'] ?? '';
    // The rule is written down where the button is built. That is required.
    expect(actionBar).toContain('/v1/permits/{id}/merge');
    for (const [path, source] of entries) {
      const code = withoutComments(source);
      expect(code.includes('/v1/permits'), `${path} addresses the merge route in code`).toBe(false);
    }
    // …and the stripper really did strip, so the assertion above is not vacuous.
    expect(withoutComments(actionBar).length).toBeLessThan(actionBar.length);
  });

  it('posts to exactly one path, and it is the gate-run route', () => {
    expect(SOURCES['/src/operator/issue/beats.ts'] ?? '').toContain(
      "GATE_RUN_PATH = '/v1/demo/gate-run'",
    );
  });
});
