// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The kernel client, against a stubbed `fetch`.
 *
 * These tests assert the properties the demo's honesty rests on — same-origin URLs, the
 * emulator header, the verbatim bytes, a named failure instead of an empty state — and the
 * last two are a grep over the shipped source, because a rule that only a reviewer enforces
 * is a rule that survives exactly until the reviewer is busy.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { get, post } from '../../../../src/operator/kernel/client';
import { entries, resetLog } from '../../../../src/operator/kernel/log';
import { originFacts, resetOrigin } from '../../../../src/operator/kernel/origin';

interface StubCall {
  readonly url: string;
  readonly init: RequestInit | undefined;
}

const calls: StubCall[] = [];

function stubFetch(make: (call: StubCall) => Response | Promise<Response> | Promise<never>): void {
  vi.stubGlobal('fetch', (input: URL, init?: RequestInit) => {
    const call: StubCall = { url: input.href, init };
    calls.push(call);
    return Promise.resolve(make(call));
  });
}

/** A minimal, well-formed read envelope, written as TEXT so the bytes are the fixture. */
const ENVELOPE_TEXT =
  '{\n' +
  '  "envelope_version": 1,\n' +
  '  "resource": "permit",\n' +
  '  "schema_id": "https://console.mainline.trappoint.org/contracts/1.0/permit.schema.json",\n' +
  '  "observed_at": "2026-08-15T09:00:00Z",\n' +
  '  "staged": false,\n' +
  '  "staged_note": null,\n' +
  '  "provenance": [{ "pointer": "/state", "chip": "db:column" }],\n' +
  '  "data": { "zeta": 1, "alpha": "§" }\n' +
  '}\n';

function envelopeResponse(headers: Record<string, string> = {}): Response {
  return new Response(ENVELOPE_TEXT, {
    status: 200,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

beforeEach(() => {
  calls.length = 0;
  resetLog();
  resetOrigin();
});

describe('same-origin URL construction', () => {
  it('builds every request as new URL(path, location.origin)', async () => {
    stubFetch(() => envelopeResponse());

    await get('/v1/permits/abc');

    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe(`${location.origin}/v1/permits/abc`);
  });

  it('carries no compiled-in hostname: the URL origin IS the document origin', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get('/v1/demo/subjects');

    expect(new URL(exchange.url).origin).toBe(location.origin);
    expect(exchange.sameOrigin).toBe(true);
  });

  it('refuses a path that is not an addressable /v1 path, as a NAMED failure', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get('https://example.invalid/v1/permits/abc');

    expect(calls).toHaveLength(0);
    expect(exchange.failure?.kind).toBe('unaddressable');
    expect(exchange.status).toBe(0);
    expect(exchange.data).toBeNull();
  });

  it('refuses a non-API path rather than letting the SPA fallback answer it', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get('/operator.html');

    expect(calls).toHaveLength(0);
    expect(exchange.failure?.kind).toBe('unaddressable');
  });
});

describe('response headers, which are readable only because we are same-origin', () => {
  it('captures X-Mainline-Emulator verbatim', async () => {
    stubFetch(() => envelopeResponse({ 'x-mainline-emulator': 'local_furl' }));

    const exchange = await get('/v1/permits/abc');

    expect(exchange.emulator).toBe('local_furl');
    expect(originFacts().emulator).toBe('local_furl');
    expect(originFacts().emulatorObservedAt).not.toBeNull();
  });

  it('reports a missing emulator header as null, never as a guess', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get('/v1/permits/abc');

    expect(exchange.emulator).toBeNull();
    expect(originFacts().emulator).toBeNull();
    expect(originFacts().responsesObserved).toBe(1);
  });

  it('captures the Date header and the local_furl not-the-demo-url marker', async () => {
    stubFetch(() =>
      envelopeResponse({
        date: 'Sat, 15 Aug 2026 09:00:01 GMT',
        'x-mainline-not-the-demo-url': 'scripts/deploy/local_furl.py',
        'x-mainline-read-ms': '12.5',
      }),
    );

    const exchange = await get('/v1/permits/abc');

    expect(exchange.serverDate).toBe('Sat, 15 Aug 2026 09:00:01 GMT');
    expect(exchange.notTheDemoUrl).toBe('scripts/deploy/local_furl.py');
    expect(exchange.serverReadMs).toBe(12.5);
  });

  it('dispatches the import-free bridge event the origin strip listens for', async () => {
    const seen: unknown[] = [];
    const handler = (event: Event): void => {
      seen.push(event instanceof CustomEvent ? event.detail : null);
    };
    document.addEventListener('mainline-operator:exchange', handler);
    stubFetch(() => envelopeResponse({ 'x-mainline-emulator': 'local_furl' }));

    await get('/v1/permits/abc');
    document.removeEventListener('mainline-operator:exchange', handler);

    expect(seen).toEqual([{ emulator: 'local_furl' }]);
  });
});

describe('the raw bytes', () => {
  it('preserves the response text byte for byte and never re-serialises it', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get('/v1/permits/abc');

    expect(exchange.raw).toBe(ENVELOPE_TEXT);
    // The proof that this is the wire text and not a round trip: a re-serialisation of the
    // same payload differs, and it is the difference a judge would spot in the Network tab.
    expect(JSON.stringify(JSON.parse(ENVELOPE_TEXT))).not.toBe(exchange.raw);
  });

  it('measures wireBytes as UTF-8 bytes of the body, not characters', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get('/v1/permits/abc');

    expect(exchange.wireBytes).toBe(new TextEncoder().encode(ENVELOPE_TEXT).length);
    // '§' is two bytes in UTF-8 and one JavaScript character. A length-based count would
    // be one byte short, and the drawer would be printing a number that was not the size.
    expect(exchange.wireBytes).toBeGreaterThan(ENVELOPE_TEXT.length);
  });

  it('keeps the bytes even when the body is not JSON, and names the failure', async () => {
    stubFetch(() => new Response('<!doctype html><title>console</title>', { status: 200 }));

    const exchange = await get('/v1/permits/abc');

    expect(exchange.raw).toBe('<!doctype html><title>console</title>');
    expect(exchange.failure?.kind).toBe('unparseable');
    expect(exchange.envelope).toBeNull();
    expect(exchange.data).toBeNull();
  });
});

describe('the envelope and the problem body', () => {
  it('parses the envelope and exposes data and provenance', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get<{ zeta: number }>('/v1/permits/abc');

    expect(exchange.envelope?.resource).toBe('permit');
    expect(exchange.envelope?.staged).toBe(false);
    expect(exchange.envelope?.observed_at).toBe('2026-08-15T09:00:00Z');
    expect(exchange.envelope?.provenance).toEqual([
      { pointer: '/state', kind: 'db:column', chip: 'db:column' },
    ]);
    expect(exchange.data?.zeta).toBe(1);
  });

  it('parses a problem body and renders no envelope', async () => {
    const problem =
      '{"error":{"kind":"no_route","status":404,"detail":"no resource is declared at ' +
      'GET /v1/change-requests/x/blocking-checks","declared":["GET /v1/audit"]}}';
    stubFetch(() => new Response(problem, { status: 404 }));

    const exchange = await get('/v1/change-requests/x/blocking-checks');

    expect(exchange.status).toBe(404);
    expect(exchange.problem?.kind).toBe('no_route');
    expect(exchange.problem?.detail).toBe(
      'no resource is declared at GET /v1/change-requests/x/blocking-checks',
    );
    expect(exchange.problem?.extra.declared).toEqual(['GET /v1/audit']);
    expect(exchange.envelope).toBeNull();
  });

  it('parses the FLAT error contract the transition surface uses', async () => {
    // Measured against local_furl on 2026-08-15: POST /v1/demo/gate-run answers 422 with
    // `{"detail": …, "error": "demo_history_not_seeded"}` — `transitions.py:_error`, which
    // says of itself "NOT an envelope, on purpose". A client that knew only the nested
    // shape would render a blank panel where the kernel had written the sentence.
    const flat =
      '{"detail":"no mainline.permit with permit_id … in this database. The demo history ' +
      'is seeded by w2-cloud-database; override the identifier with ' +
      'MAINLINE_DEMO_PERMIT_ID if this deployment seeded a different one.",' +
      '"error":"demo_history_not_seeded"}';
    stubFetch(() => new Response(flat, { status: 422 }));

    const exchange = await post('/v1/demo/gate-run', {});

    expect(exchange.problem?.kind).toBe('demo_history_not_seeded');
    expect(exchange.problem?.status).toBe(422);
    expect(exchange.problem?.detail).toContain('override the identifier with');
    expect(exchange.envelope).toBeNull();
    expect(exchange.failure).toBeNull();
  });

  it('names a JSON body that is neither an envelope nor an error, rather than blanking', async () => {
    stubFetch(() => new Response('{"something":"else"}', { status: 200 }));

    const exchange = await get('/v1/permits/abc');

    expect(exchange.failure?.kind).toBe('unrecognised_body');
    expect(exchange.raw).toBe('{"something":"else"}');
  });

  it('parses an envelope carried on a 5xx — status does not decide shape', async () => {
    stubFetch(() => new Response(ENVELOPE_TEXT, { status: 503 }));

    const exchange = await get('/v1/permits/abc');

    expect(exchange.status).toBe(503);
    expect(exchange.ok).toBe(false);
    expect(exchange.envelope?.resource).toBe('permit');
    expect(exchange.data).not.toBeNull();
  });

  it('refuses an envelope version it does not recognise, and says why', async () => {
    stubFetch(
      () =>
        new Response('{"envelope_version":2,"resource":"permit","schema_id":"s","staged":false}', {
          status: 200,
        }),
    );

    const exchange = await get('/v1/permits/abc');

    expect(exchange.envelope).toBeNull();
    expect(exchange.failure?.kind).toBe('unrecognised_envelope');
    expect(exchange.failure?.detail).toContain('envelope_version is 2');
  });

  it('refuses a frame that answers a different resource than the one asked for', async () => {
    stubFetch(() => envelopeResponse());

    const exchange = await get('/v1/permits/abc', { expectResource: 'change_request' });

    expect(exchange.failure?.kind).toBe('wrong_resource');
    expect(exchange.failure?.detail).toContain('"permit"');
  });
});

describe('failures are named, never empty states', () => {
  it('names a timeout and does not reject', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.reject(new DOMException('The operation timed out.', 'TimeoutError')),
    );

    const exchange = await get('/v1/permits/abc');

    expect(exchange.failure?.kind).toBe('timeout');
    expect(exchange.status).toBe(0);
    expect(exchange.raw).toBe('');
    expect(exchange.data).toBeNull();
  });

  it('names a caller abort separately from a deadline', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.reject(new DOMException('The user aborted a request.', 'AbortError')),
    );

    const exchange = await get('/v1/permits/abc');

    expect(exchange.failure?.kind).toBe('aborted');
  });

  it('names a transport failure and states that no HTTP status exists', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));

    const exchange = await get('/v1/permits/abc');

    expect(exchange.failure?.kind).toBe('network');
    expect(exchange.failure?.detail).toContain('No HTTP status exists');
  });
});

describe('POST', () => {
  it('sends the body as JSON and asks for JSON back', async () => {
    stubFetch(() => envelopeResponse());

    await post('/v1/demo/gate-run', {});

    expect(calls[0]?.url).toBe(`${location.origin}/v1/demo/gate-run`);
    expect(calls[0]?.init?.method).toBe('POST');
    expect(calls[0]?.init?.body).toBe('{}');
  });

  it('sends no body at all when none was given', async () => {
    stubFetch(() => envelopeResponse());

    await post('/v1/demo/gate-run');

    expect(calls[0]?.init?.body).toBeUndefined();
  });
});

describe('the request log is complete by construction', () => {
  it('records every exchange, including the failed ones', async () => {
    stubFetch(() => envelopeResponse());
    await get('/v1/permits/abc');
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await get('/v1/permits/def');
    await get('not-an-api-path');

    expect(entries()).toHaveLength(3);
    expect(entries().map((x) => x.path)).toEqual([
      '/v1/permits/abc',
      '/v1/permits/def',
      'not-an-api-path',
    ]);
  });
});

describe('the rules, enforced over the shipped source rather than by review', () => {
  const sources = import.meta.glob<string>('../../../../src/operator/kernel/*.{ts,css}', {
    query: '?raw',
    import: 'default',
    eager: true,
  });

  it('reads every kernel source file', () => {
    // If the glob ever matched nothing, the two assertions below would pass vacuously —
    // which is the failure mode of every grep-shaped test.
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(8);
  });

  it('contains no UUID literal anywhere in src/operator/kernel/**', () => {
    const uuid = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;
    const offenders = Object.entries(sources).filter(([, text]) => uuid.test(text));
    expect(offenders.map(([name]) => name)).toEqual([]);
  });

  it('schedules no timer anywhere in src/operator/kernel/**', () => {
    const timer = /\bset(?:Timeout|Interval)\b/;
    const offenders = Object.entries(sources).filter(([, text]) => timer.test(text));
    expect(offenders.map(([name]) => name)).toEqual([]);
  });

  it('does not so much as mention a build-time API base variable', () => {
    // R3. Clean under a plain `grep VITE_` too, so a reviewer's first search settles it
    // without having to read the surrounding sentence.
    const offenders = Object.entries(sources).filter(([, text]) => text.includes('VITE_'));
    expect(offenders.map(([name]) => name)).toEqual([]);
  });

  /**
   * The three tests below are about CODE, not prose — these files argue at length about
   * what they do not do, and a scan that counted those sentences as violations would push
   * the next author to delete the explanation rather than keep the property. The two tests
   * above deliberately do NOT strip comments: they are the ones a reviewer will re-run as a
   * plain `grep`, and they must be clean under a plain `grep`.
   */
  const code = (text: string): string =>
    text.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/[^\n]*/g, '$1');

  const modulesWhere = (pattern: RegExp): readonly string[] =>
    Object.entries(sources)
      .filter(([, text]) => pattern.test(code(text)))
      .map(([name]) => name.slice(name.lastIndexOf('/') + 1))
      .sort();

  it('reads no build-time environment value', () => {
    // R3: no absolute URL is compiled in. An API base read from the environment would be
    // one with a deployment step in front of it, which is worse — it would look
    // configurable and would be unreadable anyway, the Function URL carrying no CORS block.
    expect(modulesWhere(/import\.meta\.env|process\.env|VITE_/)).toEqual([]);
  });

  it('calls fetch from exactly one module', () => {
    expect(modulesWhere(/\bfetch\(/)).toEqual(['client.ts']);
  });

  it('builds a request URL from a path in exactly one module', () => {
    expect(modulesWhere(/new URL\(path/)).toEqual(['origin.ts']);
  });
});
