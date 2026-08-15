// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PROGRESSIVE DISCLOSURE, AND THE SENTENCE THAT KEEPS IT HONEST.
 *
 * One press is one `POST /v1/demo/gate-run`, and that one response carries all four beats.
 * Revealing them in order is legitimate — it is disclosure of data already received — but
 * only if the screen says so, permanently and without a dismiss control. R5 makes that
 * sentence mandatory and this file pins its exact shape.
 *
 * The second half covers `pending.ts`: the wait is driven by the REAL promise off a REAL
 * clock. The tests inject a fake host so the assertions are deterministic, which is the
 * opposite of a fake timer in the module — the module schedules nothing at all, and the
 * source-hygiene scan in `refusal.test.ts` proves it against the shipped bytes.
 */

import { describe, expect, it, vi } from 'vitest';

import { toBeatView } from '../../../../src/operator/issue/beats';
import {
  advanceLabel,
  createDisclosure,
  disclosureShapeIsExpected,
  renderDisclosureLine,
} from '../../../../src/operator/issue/disclosure';
import {
  PENDING_NOTE,
  createPending,
  pendingLabel,
  type ClockHost,
} from '../../../../src/operator/issue/pending';
import { disclosureLine, type GateRunResult } from '../../../../src/operator/kernel/gate-run';

import type { Beat, GateRun } from '../../../../src/data/types.generated';
import type { Exchange } from '../../../../src/operator/kernel/client';

/** The line as the kernel client composes it for a four-beat run. */
const SENTENCE =
  'one request · 4 beats · POST /v1/demo/gate-run · run_id judge-walk · ' +
  'response received 2026-08-14T22:10:35.412Z · 24137 bytes';

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
  statement: null,
  refusal: null,
  observed: {},
  note: null,
} satisfies Beat;

const ATTACK = {
  ...BASE,
  ordinal: 3,
  name: 'projection_drift_attack',
  outcome: 'refused',
  expected: { outcome: 'refused' },
  observed: { counter_forced_to: 0, open_blocking_derived: 1 },
  refusal: null,
} satisfies Beat;

const ADMIT = {
  ...BASE,
  ordinal: 4,
  name: 'admit',
  outcome: 'admitted',
  expected: { outcome: 'admitted' },
} satisfies Beat;

const EMPTY_FINGERPRINT = { row_counts: {}, subject_row_counts: {}, permit_row: null } as const;

/** One press of the button, as the kernel client hands it back. */
function gateRunResult(): GateRunResult {
  const run = {
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    run_id: 'judge-walk',
    generated_at: '2026-08-14T22:10:33Z',
    outcome: 'completed',
    verdict: 'PROVEN',
    failures: [],
    persisted: false,
    elapsed_ms: 1857.405,
    transaction: {
      isolation: 'SERIALIZABLE',
      disposition: 'rolled_back',
      opened_logical_timestamp: '1786745433293875086.0000000000',
      closed_logical_timestamp: '1786745433293875086.0000000000',
      single_transaction: true,
      savepoints: ['gate_run_beat_2', 'gate_run_beat_3', 'gate_run_beat_4'],
      retry_sqlstate: null,
      canonicalisation: 'mainline_demo_api.gate_run.canonical_json',
    },
    subject: {
      subject_kind: 'permit',
      subject_id: 'dec0de00-0006-4000-8000-000000000001',
      external_ref: 'DEMO-PTW-0001',
      state: 'dispositioned',
      head_seq: 2,
      gate_epoch: 1,
      open_blocking: 1,
      open_blocking_derived: 1,
      blocking_check_id: 'dec0de00-0007-4000-8000-000000000001',
      exposure_receipt_id: null,
      site_code: 'dec0de00-0001-4000-8000-000000000001',
    },
    beats: [BASE, BASE, ATTACK, ADMIT],
    persistence_check: {
      before: EMPTY_FINGERPRINT,
      after: EMPTY_FINGERPRINT,
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
      note: 'row counts taken before and after',
    },
  } satisfies GateRun;

  const exchange: Exchange<GateRun> = {
    method: 'POST',
    path: '/v1/demo/gate-run',
    url: 'https://example.invalid/v1/demo/gate-run',
    sameOrigin: true,
    status: 200,
    ok: true,
    wireBytes: 24_137,
    requestedAt: '2026-08-14T22:10:32.900Z',
    receivedAt: '2026-08-14T22:10:35.412Z',
    elapsedMs: 2512.4,
    serverDate: 'Fri, 14 Aug 2026 22:10:35 GMT',
    emulator: null,
    notTheDemoUrl: null,
    serverReadMs: null,
    contentType: 'application/json',
    envelope: null,
    data: run,
    raw: '{}',
    problem: null,
    failure: null,
  };

  return {
    exchange,
    run,
    classification: 'proven',
    undecided: false,
    retrySqlstate: null,
    beats: run.beats,
    anomalies: [],
  };
}

// ───────────────────────────────────────────────────────────────────────────────────────
// The mandatory line
// ───────────────────────────────────────────────────────────────────────────────────────

describe('the shape R5 requires of the disclosure line', () => {
  it('accepts the sentence the kernel client composes', () => {
    expect(disclosureShapeIsExpected(SENTENCE)).toBe(true);
  });

  it('rejects a line that names any other route, or drops a member', () => {
    expect(disclosureShapeIsExpected(SENTENCE.replace('/v1/demo/gate-run', '/v1/permits/x/merge'))).toBe(
      false,
    );
    expect(disclosureShapeIsExpected(SENTENCE.replace(' · 24137 bytes', ''))).toBe(false);
    expect(disclosureShapeIsExpected(SENTENCE.replace('one request', 'two requests'))).toBe(false);
    expect(disclosureShapeIsExpected(SENTENCE.replace('run_id judge-walk', 'run_id '))).toBe(false);
  });

  it('is the shape the kernel client actually produces, end to end', () => {
    // Composed by src/operator/kernel/gate-run.ts, beside the request that produced it.
    // A screen that composed its own copy would be a second place for it to be wrong.
    expect(disclosureLine(gateRunResult())).toBe(SENTENCE);
    expect(disclosureShapeIsExpected(disclosureLine(gateRunResult()))).toBe(true);
  });
});

describe('the disclosure line is permanent', () => {
  const strip = renderDisclosureLine(SENTENCE);

  it('renders the sentence verbatim, as its own element', () => {
    expect(strip.querySelector('[data-disclosure="line"]')?.textContent).toBe(SENTENCE);
    expect(strip.dataset.shape).toBe('expected');
  });

  it('carries no dismiss control, no collapse and nothing hidden', () => {
    expect(strip.dataset.permanent).toBe('true');
    expect(strip.querySelector('button')).toBeNull();
    expect(strip.querySelector('details')).toBeNull();
    expect(strip.querySelector('[hidden]')).toBeNull();
    expect(strip.hidden).toBe(false);
  });

  it('says whose clock stamped the instant, beside the line rather than inside it', () => {
    const caveat = strip.querySelector('.cow-disclosure__caveat')?.textContent ?? '';
    expect(caveat).toContain('one response');
    expect(caveat).toContain('browser');
    expect(SENTENCE).not.toContain('browser');
  });

  it('renders an unexpected sentence VERBATIM and marks it, rather than repairing it', () => {
    const wrong = 'one request · four beats · and nothing else';
    const marked = renderDisclosureLine(wrong);
    expect(marked.querySelector('[data-disclosure="line"]')?.textContent).toBe(wrong);
    expect(marked.dataset.shape).toBe('unexpected');
    expect(marked.querySelector('[data-disclosure="shape-warning"]')).not.toBeNull();
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// The reveal, under operator control
// ───────────────────────────────────────────────────────────────────────────────────────

describe('the reveal', () => {
  it('starts where the press left it and advances one beat at a time, in order', () => {
    const disclosure = createDisclosure(4, 2);
    expect(disclosure.revealed).toBe(2);
    expect(disclosure.canAdvance).toBe(true);
    expect(disclosure.advance()).toBe(3);
    expect(disclosure.advance()).toBe(4);
    expect(disclosure.canAdvance).toBe(false);
  });

  it('never runs past the beats it was given', () => {
    const disclosure = createDisclosure(4, 4);
    expect(disclosure.advance()).toBe(4);
    expect(createDisclosure(4, 99).revealed).toBe(4);
    expect(createDisclosure(0, 2).revealed).toBe(0);
  });

  it('advances only when something calls advance — nothing schedules it', () => {
    const disclosure = createDisclosure(4, 2);
    const seen = vi.fn();
    disclosure.subscribe(seen);
    expect(seen).not.toHaveBeenCalled();
    disclosure.advance();
    expect(seen).toHaveBeenCalledWith(3);
  });

  it('offers everything at once to a reader who does not want the story', () => {
    const disclosure = createDisclosure(4, 2);
    expect(disclosure.revealAll()).toBe(4);
  });

  it('unsubscribes cleanly', () => {
    const disclosure = createDisclosure(4, 1);
    const seen = vi.fn();
    disclosure.subscribe(seen)();
    disclosure.advance();
    expect(seen).not.toHaveBeenCalled();
  });
});

describe('the control that reveals the next beat', () => {
  it('quotes the value the payload says the counter was forced to', () => {
    expect(advanceLabel(toBeatView(ATTACK))).toBe('But the counter now reads 0 ▸');
  });

  it('names the act for the admission and claims no number', () => {
    expect(advanceLabel(toBeatView(ADMIT))).toBe('Answer the obligation, then issue again ▸');
  });

  it('offers nothing when there is no next beat', () => {
    expect(advanceLabel(undefined)).toBeNull();
  });

  it('falls back to the ordinal rather than inventing a claim', () => {
    expect(advanceLabel(toBeatView(BASE))).toBe('Show beat 1 ▸');
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// The wait, which is real
// ───────────────────────────────────────────────────────────────────────────────────────

interface FakeHost extends ClockHost {
  advanceBy(ms: number): void;
  pumpFrame(): void;
  readonly cancelled: number;
}

function fakeHost(): FakeHost {
  let clock = 1000;
  let cancelled = 0;
  let queued: (() => void) | null = null;
  return {
    now: () => clock,
    frame: (callback) => {
      queued = callback;
      return 1;
    },
    cancelFrame: () => {
      cancelled += 1;
      queued = null;
    },
    advanceBy: (ms) => {
      clock += ms;
    },
    pumpFrame: () => {
      const next = queued;
      queued = null;
      if (next !== null) next();
    },
    get cancelled(): number {
      return cancelled;
    },
  };
}

describe('the pending state is driven by the real promise', () => {
  it('goes in flight on the promise and settles on the promise, not on a clock', async () => {
    const host = fakeHost();
    const pending = createPending(host);
    let release: (value: string) => void = () => undefined;
    const work = new Promise<string>((resolve) => {
      release = resolve;
    });

    expect(pending.state.phase).toBe('idle');
    const tracked = pending.track(work);
    expect(pending.state.phase).toBe('in_flight');

    host.advanceBy(2_500);
    host.pumpFrame();
    expect(pending.state.elapsedMs).toBe(2_500);

    release('the payload');
    await expect(tracked).resolves.toBe('the payload');
    expect(pending.state.phase).toBe('settled');
    expect(pending.state.elapsedMs).toBe(2_500);
    expect(host.cancelled).toBeGreaterThan(0);
  });

  it('reports the real elapsed on a cold round trip without capping or rounding it away', async () => {
    const host = fakeHost();
    const pending = createPending(host);
    const tracked = pending.track(Promise.resolve(1));
    host.advanceBy(8_940);
    await tracked;
    expect(pending.state.elapsedMs).toBe(8_940);
  });

  it('rethrows a transport failure unchanged and marks the state failed', async () => {
    const host = fakeHost();
    const pending = createPending(host);
    const boom = new Error('the socket closed');
    await expect(pending.track(Promise.reject(boom))).rejects.toBe(boom);
    expect(pending.state.phase).toBe('settled');
    expect(pending.state.failed).toBe(true);
  });

  it('publishes every reading to subscribers while in flight', async () => {
    const host = fakeHost();
    const pending = createPending(host);
    const seen: number[] = [];
    pending.subscribe((state) => seen.push(state.elapsedMs));
    const tracked = pending.track(Promise.resolve(0));
    host.advanceBy(120);
    host.pumpFrame();
    await tracked;
    expect(seen[0]).toBe(0);
    expect(seen).toContain(120);
  });

  it('labels the number as this browser’s measurement of the round trip', () => {
    expect(pendingLabel({ phase: 'in_flight', elapsedMs: 2_460, failed: false })).toBe('Issuing… 2.5 s');
    expect(pendingLabel({ phase: 'idle', elapsedMs: 0, failed: false })).toBe('');
    expect(PENDING_NOTE).toContain('browser');
    expect(PENDING_NOTE).toContain('server measured');
  });
});
