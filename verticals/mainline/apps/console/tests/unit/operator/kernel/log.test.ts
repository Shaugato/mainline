// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The request log (R18).
 *
 * Two properties are asserted here and both are the point of the affordance: it is
 * COMPLETE — the client records every exchange itself, so a screen cannot forget — and it
 * is APPEND-ONLY, so nothing that happened can leave it. A log a page could edit is worth
 * less than no log, because it invites the reader to trust it.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { get, post, type Exchange } from '../../../../src/operator/kernel/client';
import * as log from '../../../../src/operator/kernel/log';
import { resetOrigin } from '../../../../src/operator/kernel/origin';
import { rawViewOf, renderRequestLog } from '../../../../src/operator/kernel/raw';

const BODY =
  '{"envelope_version":1,"resource":"permit","schema_id":"s","staged":false,' +
  '"provenance":[],"data":{"a":1}}';

function stubOk(): void {
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      new Response(BODY, { status: 200, headers: { 'x-mainline-emulator': 'local_furl' } }),
    ),
  );
}

beforeEach(() => {
  log.resetLog();
  resetOrigin();
});

describe('completeness', () => {
  it('records every exchange the client made, in order, without the caller helping', async () => {
    stubOk();

    await get('/v1/permits/a');
    await post('/v1/demo/gate-run', {});

    expect(log.count()).toBe(2);
    expect(log.entries().map((x) => `${x.method} ${x.path}`)).toEqual([
      'GET /v1/permits/a',
      'POST /v1/demo/gate-run',
    ]);
  });

  it('records a failure too — the log is not a log of successes', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));

    await get('/v1/permits/a');

    expect(log.count()).toBe(1);
    expect(log.entries()[0]?.failure?.kind).toBe('network');
  });
});

describe('append-only', () => {
  it('exposes no way to remove or edit an entry', () => {
    const surface = Object.keys(log).sort();
    expect(surface).toEqual(['count', 'entries', 'onChange', 'record', 'resetLog']);
  });

  it('leaves earlier entries untouched as later ones arrive', async () => {
    stubOk();

    await get('/v1/permits/a');
    const first = log.entries()[0];
    await get('/v1/permits/b');

    expect(log.entries()[0]).toBe(first);
    expect(log.entries()).toHaveLength(2);
  });
});

describe('subscription', () => {
  it('notifies on every append and stops after unsubscribe', async () => {
    stubOk();
    let notified = 0;
    const unsubscribe = log.onChange(() => {
      notified += 1;
    });

    await get('/v1/permits/a');
    expect(notified).toBe(1);

    unsubscribe();
    await get('/v1/permits/b');
    expect(notified).toBe(1);
  });
});

describe('the rendered log and the raw drawer', () => {
  it('renders one row per entry, with the emulator marker when one was stamped', async () => {
    stubOk();
    await get('/v1/permits/a');

    const host = document.createElement('div');
    renderRequestLog(host, log.entries());

    expect(host.querySelectorAll('.mlk-log__row')).toHaveLength(1);
    expect(host.textContent).toContain('/v1/permits/a');
    expect(host.textContent).toContain('local_furl');
  });

  it('says so plainly when nothing has been requested yet', () => {
    const host = document.createElement('div');
    renderRequestLog(host, []);

    expect(host.textContent).toBe('no request has been made from this page yet');
  });

  it('carries the verbatim body into the drawer model, byte for byte', async () => {
    stubOk();
    const exchange: Exchange<unknown> = await get('/v1/permits/a');

    const view = rawViewOf(exchange);

    expect(view.body).toBe(BODY);
    expect(view.method).toBe('GET');
    expect(view.path).toBe('/v1/permits/a');
    expect(view.status).toBe(200);
    expect(view.wireBytes).toBe(new TextEncoder().encode(BODY).length);
    expect(view.emulator).toBe('local_furl');
  });
});
