// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `LIVE` and `REPLAY` differ in one line of composition and in one badge — never in a
 * code path (D7).
 *
 * That sentence is a claim about behaviour, so it is tested as one: the SAME assertion
 * block runs against `HttpTransport` and `BundleTransport`, and the only difference
 * between the two setups is which object is constructed. The live transport is driven
 * by a `fetch` implementation that serves the bundle's own captured frames, so both
 * transports are answering from identical bytes and any divergence is a divergence in
 * the transports rather than in the data.
 *
 * If a future change makes a surface behave differently under replay, it fails here
 * rather than in front of a judge.
 */

import { describe, expect, it } from 'vitest';

import { BundleTransport, MemoryBundleSource } from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import { RefusalError } from '../../../src/app/refusal';
import type { MainlineTransport } from '../../../src/data/transport';
import { HttpTransport, TransportError } from '../../../src/data/transport';
import { resolveRequest } from '../../../src/data/resources';

import { bundleFiles, frameAddressOf, manifestIntegrityVerifier, stagePlan } from './_support';

const registry = createContractRegistry();
const decoder = new TextDecoder();

const PERMIT_ID = '018f3a2f-1104-7c88-b3aa-77c1de40e2b1';
const CHECK_ID = '018f3a31-1000-7b30-9e53-2e1c60997a24';
const BASE_URL = 'https://kernel.mainline.test';

/**
 * A `fetch` that answers from the bundle's captured frames.
 *
 * This is NOT a mock of the kernel. It replays exactly the bytes the kernel produced
 * (or, for the staged fixtures, exactly the bytes a human wrote and labelled as
 * staged), with the captured status code — which is what makes it a fair comparison
 * against the replay transport rather than a restatement of it.
 */
function frameServingFetch(): typeof fetch {
  const files = bundleFiles();
  const frames = new Map<string, { status: number; body: string }>();

  for (const [path, bytes] of files) {
    if (!path.startsWith('frames/')) continue;
    const frame = JSON.parse(decoder.decode(bytes)) as {
      key: string;
      response: { status: number; body_b64: string };
    };
    frames.set(frame.key, {
      status: frame.response.status,
      body: decoder.decode(Uint8Array.from(atob(frame.response.body_b64), (c) => c.charCodeAt(0))),
    });
  }

  return (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
    const method = (init?.method ?? 'GET').toUpperCase();
    const query = [...url.searchParams.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]))
      .map(([name, value]) => `${encodeURIComponent(name)}=${encodeURIComponent(value)}`)
      .join('&');
    const key = query === '' ? `${method} ${url.pathname}` : `${method} ${url.pathname}?${query}`;

    const frame = frames.get(key);
    if (frame === undefined) {
      return Promise.resolve(new Response('{"error":"no such route"}', { status: 404 }));
    }
    return Promise.resolve(
      new Response(frame.body, {
        status: frame.status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  };
}

function liveTransport(): MainlineTransport {
  return new HttpTransport({ baseUrl: BASE_URL, registry, fetchImpl: frameServingFetch() });
}

function replayTransport(): MainlineTransport {
  return new BundleTransport({
    source: new MemoryBundleSource('fixtures/bundles/blk-07', bundleFiles()),
    registry,
    verifier: manifestIntegrityVerifier(),
  });
}

const TRANSPORTS: readonly (readonly [string, () => MainlineTransport])[] = [
  ['HttpTransport', liveTransport],
  ['BundleTransport', replayTransport],
];

describe.each(TRANSPORTS)('%s — the same assertions, against the same bytes', (name, make) => {
  it('reads the permit and returns the projected counters verbatim', async () => {
    const transport = make();
    const exchange = await transport.exchange({ resource: 'permit', path: { permit_id: PERMIT_ID } });

    const permit = exchange.data as {
      permit_id: string;
      gate_epoch: number;
      state: string;
      counters: { open_blocking: number };
      constraints: { constraint: string; blamed_by_refusal: boolean }[];
    };

    expect(exchange.envelope.resource).toBe('permit');
    expect(permit.permit_id).toBe(PERMIT_ID);
    expect(permit.gate_epoch).toBe(7);
    expect(permit.state).toBe('dispositioned');
    expect(permit.counters.open_blocking).toBe(1);
    expect(permit.constraints.map((c) => c.constraint)).toContain('gate_closed_when_issued');
  });

  it('carries the staged flag and its note into the exchange', async () => {
    const transport = make();
    const exchange = await transport.exchange({ resource: 'permit', path: { permit_id: PERMIT_ID } });
    expect(exchange.envelope.staged).toBe(true);
    expect(exchange.envelope.staged_note).toMatch(/Hand-authored demonstration bundle/);
  });

  it('throws RefusalError carrying the database’s own constraint name and SQLSTATE', async () => {
    const transport = make();
    const caught = await transport
      .exchange({
        resource: 'merge_permit',
        path: { permit_id: PERMIT_ID },
        body: { subject_kind: 'permit', subject_id: PERMIT_ID, expected_gate_epoch: 7 },
      })
      .catch((error: unknown) => error);

    expect(caught, `${name} must refuse`).toBeInstanceOf(RefusalError);
    const refusal = (caught as RefusalError).refusal;
    expect(refusal.sqlstate).toBe('23514');
    expect(refusal.constraint).toBe('gate_closed_when_issued');
    expect(refusal.constraint_source).toBe('reported');
    // D18: the message is the database's, verbatim, including its MAINLINE: prefix.
    expect(refusal.message).toMatch(/^MAINLINE: /);
    expect((caught as RefusalError).message).toBe(refusal.message);
  });

  it('refuses the clearance lattice violation with 23503 on fk_clearance', async () => {
    const transport = make();
    const caught = await transport
      .exchange({
        resource: 'sign_disposition',
        path: { check_id: CHECK_ID },
        body: {
          check_id: CHECK_ID,
          kind: 'mechanism_absent',
          defeater_code: 'D-114',
          receipt_id: '018f3a32-1100-7a80-82aa-81d4f5760a3b',
          rationale:
            'The hydraulic power unit on this drive was replaced in 2024 with a unit that has no accumulator, so the 2004 mechanism cannot occur on this asset. The isolation is electrical only and there is no stored pressure to bleed down before intrusive work begins.',
        },
      })
      .catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(RefusalError);
    expect((caught as RefusalError).refusal.sqlstate).toBe('23503');
    expect((caught as RefusalError).refusal.constraint).toBe('fk_clearance');
  });

  it('reads the ancestry projection, whose read endpoint has no owner in any domain', async () => {
    const transport = make();
    const exchange = await transport.exchange({
      resource: 'clause_ancestry',
      path: { clause_uuid: '018f3a30-2200-7d10-9f31-0c9a4e77bb02' },
      query: { as_of: '5f916282a2a3e5765f916282a2a3e5765f916282a2a3e5765f916282a2a3e576' },
    });
    const data = exchange.data as { closure: { max_severity: number }; events: unknown[] };
    expect(data.closure.max_severity).toBe(5);
    expect(data.events.length).toBe(4);
  });

  it('rejects a payload that answers a different resource than the one asked for', async () => {
    // Both transports run the same post-condition in finishExchange, so both must
    // refuse a swapped payload. Only the live path can be pointed at one from a test.
    const transport =
      name === 'HttpTransport'
        ? new HttpTransport({
            baseUrl: BASE_URL,
            registry,
            fetchImpl: () =>
              Promise.resolve(
                new Response(
                  JSON.stringify({
                    envelope_version: 1,
                    resource: 'audit',
                    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/permit.schema.json',
                    staged: false,
                    staged_note: null,
                    provenance: [],
                    data: {},
                  }),
                  { status: 200, headers: { 'content-type': 'application/json' } },
                ),
              ),
          })
        : null;
    if (transport === null) return;

    const caught = await transport
      .exchange({ resource: 'permit', path: { permit_id: PERMIT_ID } })
      .catch((error: unknown) => error);
    expect(caught).toBeInstanceOf(TransportError);
    expect(['mismatch', 'contract']).toContain((caught as TransportError).failure);
  });

  it('honours an already-aborted signal without performing the exchange', async () => {
    const transport = make();
    const controller = new AbortController();
    controller.abort(new Error('cancelled before start'));

    await expect(
      transport.exchange({ resource: 'permit', path: { permit_id: PERMIT_ID } }, controller.signal),
    ).rejects.toThrow();
  });

  it('describes itself honestly', () => {
    const description = make().describe();
    expect(description.mode).toBe(name === 'HttpTransport' ? 'live' : 'replay');
  });
});

describe('the parity suite exercises the whole captured surface', () => {
  it('every step in the staging plan is addressable by its declared resource', () => {
    for (const step of stagePlan().steps) {
      const resolved = resolveRequest({
        resource: step.resource,
        ...(step.path === undefined ? {} : { path: step.path }),
        ...(step.query === undefined ? {} : { query: step.query }),
        ...(step.body === undefined ? {} : { body: step.body }),
      });
      const framePath = frameAddressOf(resolved.key);
      expect(bundleFiles().has(framePath), `${step.resource} → ${framePath}`).toBe(true);
    }
  });
});
