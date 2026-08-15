// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The gate run.
 *
 * The load-bearing test in this file is the `40001` one. A run the database left UNDECIDED
 * arrives as HTTP 503 with a full envelope, and the failure mode this module exists to
 * prevent is a screen drawing a refusal banner over it — claiming the gate said no when the
 * database said "ask me again". Everything else here is bookkeeping by comparison.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  disclosureLine,
  isRefusal,
  refusedBeats,
  runGate,
} from '../../../../src/operator/kernel/gate-run';
import { resetLog } from '../../../../src/operator/kernel/log';
import { resetOrigin } from '../../../../src/operator/kernel/origin';

import type { Beat } from '../../../../src/data/types.generated';

const RUN_TOKEN = 'run-token-from-the-kernel';

/**
 * A beat, as JSON. Deliberately typed loosely: these are WIRE fixtures, and the whole
 * question this suite asks is what the client does with bytes it did not author. Typing
 * them as `Beat` would let the compiler assert a shape the server is the authority on.
 */
function beat(
  overrides: { readonly ordinal: number; readonly name: Beat['name'] } & Record<string, unknown>,
): unknown {
  return {
    label: 'a label the driver wrote',
    expected: { outcome: 'read' },
    outcome: 'read',
    sqlstate: null,
    constraint: null,
    constraint_source: 'absent',
    message: null,
    matched_expectation: true,
    elapsed_ms: 1.5,
    statement: null,
    refusal: null,
    observed: {},
    note: null,
    ...overrides,
  };
}

function gateRunBody(
  run: Record<string, unknown>,
  envelope: Record<string, unknown> = {},
): string {
  return JSON.stringify({
    envelope_version: 1,
    resource: 'demo_gate_run',
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    observed_at: '2026-08-15T09:00:00Z',
    staged: false,
    staged_note: null,
    provenance: [{ pointer: '/verdict', chip: 'derived' }],
    ...envelope,
    data: {
      schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
      run_id: RUN_TOKEN,
      generated_at: '2026-08-15T09:00:00Z',
      outcome: 'completed',
      verdict: 'PROVEN',
      failures: [],
      persisted: false,
      elapsed_ms: 1900,
      transaction: {
        isolation: 'SERIALIZABLE',
        disposition: 'rolled_back',
        opened_logical_timestamp: '1786745433293875086.0000000000',
        closed_logical_timestamp: '1786745433293875086.0000000000',
        single_transaction: true,
        savepoints: [],
        retry_sqlstate: null,
        canonicalisation: 'trappoint.canon.v1',
      },
      subject: {},
      persistence_check: {},
      ...run,
    },
  });
}

const FOUR_BEATS = [
  beat({ ordinal: 1, name: 'read', outcome: 'read' }),
  beat({
    ordinal: 2,
    name: 'merge',
    outcome: 'refused',
    sqlstate: '23514',
    constraint: 'gate_closed_when_issued',
    constraint_source: 'reported',
    refusal: { sqlstate: '23514' },
  }),
  beat({
    ordinal: 3,
    name: 'projection_drift_attack',
    outcome: 'refused',
    sqlstate: 'P0001',
    constraint: 'mainline.fn_permit_merge_gate',
    constraint_source: 'parsed',
    refusal: { sqlstate: 'P0001' },
  }),
  beat({ ordinal: 4, name: 'admit', outcome: 'admitted', sqlstate: null }),
];

function stub(body: string, status: number): void {
  vi.stubGlobal('fetch', () => Promise.resolve(new Response(body, { status })));
}

beforeEach(() => {
  resetLog();
  resetOrigin();
});

describe('a completed run', () => {
  it('reports PROVEN and hands back the payload’s own four beats', async () => {
    stub(gateRunBody({ beats: FOUR_BEATS }), 200);

    const result = await runGate();

    expect(result.classification).toBe('proven');
    expect(result.undecided).toBe(false);
    expect(result.retrySqlstate).toBeNull();
    expect(result.beats).toHaveLength(4);
    expect(result.beats[1]?.sqlstate).toBe('23514');
    expect(result.beats[1]?.constraint).toBe('gate_closed_when_issued');
    expect(result.anomalies).toEqual([]);
  });

  it('POSTs the gate-run route and NEVER the permit merge route (R4)', async () => {
    const seen: string[] = [];
    vi.stubGlobal('fetch', (input: URL, init?: RequestInit) => {
      seen.push(`${String(init?.method)} ${input.pathname}`);
      return Promise.resolve(new Response(gateRunBody({ beats: FOUR_BEATS }), { status: 200 }));
    });

    await runGate();

    expect(seen).toEqual(['POST /v1/demo/gate-run']);
    expect(seen.some((entry) => entry.includes('/merge'))).toBe(false);
  });

  it('separates the refusals from the read and the admission', async () => {
    stub(gateRunBody({ beats: FOUR_BEATS }), 200);

    const result = await runGate();

    expect(refusedBeats(result).map((b) => b.ordinal)).toEqual([2, 3]);
    expect(result.beats.filter((b) => b.outcome === 'admitted')).toHaveLength(1);
  });

  it('reports NOT PROVEN as a real answer, not as an error', async () => {
    stub(
      gateRunBody({
        beats: FOUR_BEATS,
        verdict: 'NOT PROVEN',
        failures: ['beat 3 observed outcome "admitted" and expected "refused"'],
      }),
      200,
    );

    const result = await runGate();

    expect(result.classification).toBe('not_proven');
    expect(result.run?.failures).toEqual([
      'beat 3 observed outcome "admitted" and expected "refused"',
    ]);
  });
});

describe('40001 — an undecided transaction, which is NOT a refusal', () => {
  const undecidedBody = gateRunBody({
    outcome: 'retry',
    verdict: 'NOT PROVEN',
    failures: ['the transaction was aborted by 40001 and the run could not continue'],
    beats: [
      beat({ ordinal: 1, name: 'read', outcome: 'read' }),
      beat({ ordinal: 2, name: 'merge', outcome: 'retry', sqlstate: '40001', refusal: null }),
    ],
    transaction: {
      isolation: 'SERIALIZABLE',
      disposition: 'rolled_back',
      opened_logical_timestamp: '1786745433293875086.0000000000',
      closed_logical_timestamp: null,
      single_transaction: true,
      savepoints: [],
      retry_sqlstate: '40001',
      canonicalisation: 'trappoint.canon.v1',
    },
  });

  it('classifies a 503-with-envelope as undecided, not as unavailable', async () => {
    stub(undecidedBody, 503);

    const result = await runGate();

    expect(result.exchange.status).toBe(503);
    expect(result.classification).toBe('undecided');
    expect(result.undecided).toBe(true);
    expect(result.run).not.toBeNull();
  });

  it('reads the retry SQLSTATE off transaction.retry_sqlstate', async () => {
    stub(undecidedBody, 503);

    const result = await runGate();

    expect(result.retrySqlstate).toBe('40001');
  });

  it('carries no refusal: the 40001 beat is not a refused beat', async () => {
    stub(undecidedBody, 503);

    const result = await runGate();

    expect(refusedBeats(result)).toEqual([]);
    const retryBeat = result.beats.find((b) => b.sqlstate === '40001');
    expect(retryBeat).toBeDefined();
    expect(retryBeat?.outcome).toBe('retry');
    expect(retryBeat === undefined ? null : isRefusal(retryBeat)).toBe(false);
    expect(retryBeat?.refusal).toBeNull();
  });

  it('does not re-send on the caller’s behalf', async () => {
    let sent = 0;
    vi.stubGlobal('fetch', () => {
      sent += 1;
      return Promise.resolve(new Response(undecidedBody, { status: 503 }));
    });

    await runGate();

    expect(sent).toBe(1);
  });
});

describe('when no run happened', () => {
  it('classifies a problem body as unavailable and keeps the kernel’s sentence', async () => {
    const detail = "SSM GetParameter '/mainline/demo/cockroach_dsn' failed: ParameterNotFound";
    stub(JSON.stringify({ error: { kind: 'dsn_unset', status: 503, detail } }), 503);

    const result = await runGate();

    expect(result.classification).toBe('unavailable');
    expect(result.run).toBeNull();
    expect(result.beats).toEqual([]);
    expect(result.exchange.problem?.detail).toBe(detail);
  });

  it('classifies a transport failure as unavailable rather than rejecting', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));

    const result = await runGate();

    expect(result.classification).toBe('unavailable');
    expect(result.exchange.failure?.kind).toBe('network');
  });
});

describe('this client’s own reading of the payload against the contract', () => {
  it('names a payload that claims to have persisted something', async () => {
    stub(gateRunBody({ beats: FOUR_BEATS, persisted: true }), 200);

    const result = await runGate();

    expect(result.anomalies.join(' ')).toContain('persisted=true');
  });

  it('names a completed run that did not carry four beats', async () => {
    stub(gateRunBody({ beats: FOUR_BEATS.slice(0, 2) }), 200);

    const result = await runGate();

    expect(result.anomalies.join(' ')).toContain('carried 2 beats');
  });

  it('names a PROVEN verdict that also lists failures', async () => {
    stub(gateRunBody({ beats: FOUR_BEATS, failures: ['something did not hold'] }), 200);

    const result = await runGate();

    expect(result.anomalies.join(' ')).toContain('PROVEN with 1 failure');
  });
});

describe('the R5 disclosure line', () => {
  it('is composed entirely from values the exchange produced', async () => {
    stub(gateRunBody({ beats: FOUR_BEATS }), 200);

    const result = await runGate();
    const line = disclosureLine(result);

    expect(line).toBe(
      `one request · 4 beats · POST /v1/demo/gate-run · run_id ${RUN_TOKEN} · ` +
        `response received ${result.exchange.receivedAt} · ${result.exchange.wireBytes} bytes`,
    );
  });

  it('states the real beat count when a run was cut short, rather than the word four', async () => {
    stub(
      gateRunBody({
        outcome: 'retry',
        beats: [beat({ ordinal: 1, name: 'read', outcome: 'read' })],
      }),
      503,
    );

    const result = await runGate();

    expect(disclosureLine(result)).toContain('1 beats');
    expect(disclosureLine(result)).not.toContain('4 beats');
  });
});
