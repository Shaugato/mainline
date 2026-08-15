// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE AUDIT SCREEN, THROUGH THE REAL TRANSPORT.
 *
 * Like `custody-screen.test.tsx`, this file lives under `tests/unit/verify/` because
 * `tests/unit/audit/` is outside this worker's path allocation. The subject is the audit
 * surface.
 *
 * The claims worth a test here are all claims about NOT ASSERTING:
 *
 *   • the screen holds no column list and renders whatever columns arrive, so a view that
 *     gains a column tomorrow is rendered rather than truncated;
 *   • a result AT the row cap is reported as very probably TRUNCATED, not as a count;
 *   • a view with no truncation flag is reported as making no completeness claim;
 *   • an EMPTY negative-probe list is reported as "nothing was checked", never as
 *     "nothing is reachable";
 *   • the one writable table is represented read-only, with no form that could insert.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BundleTransport, MemoryBundleSource } from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import { HttpTransport } from '../../../src/data/transport';
import { toBase64, toHex, utf8 } from '../../../src/verify/bytes';
import { InBrowserBundleVerifier } from '../../../src/verify/bundle-verifier';
import { InlineVerifier } from '../../../src/verify/client';
import { NO_ANCHOR } from '../../../src/verify/config';
import { sha256Sync } from '../../../src/verify/sha256';
import { AuditRoot } from '../../../src/features/audit/AuditRoot';
import { surface } from '../../../src/features/audit/surface';
import { AuditTransportContext } from '../../../src/features/audit/transport-context';
import {
  capReading,
  completeness,
  readCarriage,
  readUnreachable,
  tallyCalls,
  type AuditPayload,
  type AuditView,
} from '../../../src/features/audit/model';
import type { BundleManifest } from '../../../src/data/bundle';

const RAW = import.meta.glob<string>('/fixtures/bundles/blk-07/**/*', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const BUNDLE_ROOT = '/fixtures/bundles/blk-07/';
const AUDIT_FRAME = 'frames/GET-540549b3695a753c.json';

function bundleFiles(): Map<string, Uint8Array> {
  const files = new Map<string, Uint8Array>();
  for (const [key, text] of Object.entries(RAW)) {
    if (!key.startsWith(BUNDLE_ROOT)) continue;
    const path = key.slice(BUNDLE_ROOT.length);
    if (path === 'manifest.seed.json') continue;
    files.set(path, utf8(text));
  }
  if (files.size === 0) throw new Error('no fixture bundle files were globbed');
  return files;
}

function decode(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes);
}

function auditEnvelope(files: Map<string, Uint8Array>): Record<string, unknown> {
  const frameBytes = files.get(AUDIT_FRAME);
  if (frameBytes === undefined) throw new Error(`${AUDIT_FRAME} is not in the fixture bundle`);
  const frame = JSON.parse(decode(frameBytes)) as {
    response: { body_b64: string };
  };
  return JSON.parse(decode(utf8(atob(frame.response.body_b64)))) as Record<string, unknown>;
}

function withAuditEnvelope(
  files: Map<string, Uint8Array>,
  envelope: unknown,
): Map<string, Uint8Array> {
  const frameBytes = files.get(AUDIT_FRAME);
  if (frameBytes === undefined) throw new Error(`${AUDIT_FRAME} is not in the fixture bundle`);
  const frame = JSON.parse(decode(frameBytes)) as Record<string, unknown>;
  const response = frame.response as Record<string, unknown>;
  frame.response = { ...response, body_b64: toBase64(utf8(JSON.stringify(envelope))) };

  const next = new Map(files);
  next.set(AUDIT_FRAME, utf8(JSON.stringify(frame)));

  const manifestBytes = next.get('manifest.json');
  if (manifestBytes === undefined) throw new Error('no manifest.json');
  const manifest = JSON.parse(decode(manifestBytes)) as BundleManifest;
  const sealed = {
    ...manifest,
    files: manifest.files.map((entry) => {
      const bytes = next.get(entry.path);
      if (bytes === undefined) throw new Error(`manifest lists ${entry.path}, which is absent`);
      return { ...entry, sha256: toHex(sha256Sync(bytes)), bytes: bytes.byteLength };
    }),
  };
  next.set('manifest.json', utf8(JSON.stringify(sealed, null, 2)));
  return next;
}

/**
 * The SAME audit payload, over the live transport.
 *
 * It is the fixture bundle's own envelope handed back by an injected `fetch`, so the two
 * mounts below differ in exactly one thing — how the bytes arrived — which is the only
 * thing the sentence under test is allowed to be about.
 */
function mountLive(files: ReadonlyMap<string, Uint8Array>): void {
  const body = JSON.stringify(auditEnvelope(new Map(files)));
  const transport = new HttpTransport({
    baseUrl: 'https://kernel.invalid',
    registry: createContractRegistry(),
    fetchImpl: () =>
      Promise.resolve(
        new Response(body, { status: 200, headers: { 'content-type': 'application/json' } }),
      ),
  });
  render(
    <AuditTransportContext.Provider value={transport}>
      <AuditRoot />
    </AuditTransportContext.Provider>,
  );
}

function mount(files: ReadonlyMap<string, Uint8Array>): void {
  const transport = new BundleTransport({
    source: new MemoryBundleSource('audit-screen-test', files),
    registry: createContractRegistry(),
    verifier: new InBrowserBundleVerifier({
      verifier: new InlineVerifier('unit test — jsdom has no Worker'),
      config: NO_ANCHOR,
    }),
  });
  render(
    <AuditTransportContext.Provider value={transport}>
      <AuditRoot />
    </AuditTransportContext.Provider>,
  );
}

function view(overrides: Partial<AuditView> = {}): AuditView {
  return {
    view: 'mainline_audit.v_test',
    columns: [{ name: 'site_id', sql_type: 'UUID' }],
    rows: [['018f3a2e-0000-7000-8000-000000000001']],
    limits: { row_cap: 25, byte_cap: 10240, rows_returned: 1, bytes_returned: 100 },
    truncation_flag: null,
    statement: 'SELECT * FROM mainline_audit.v_test',
    ...overrides,
  };
}

describe('the surface registers itself honestly', () => {
  it('declares the id its directory requires, in the EVIDENCE register', () => {
    expect(surface.id).toBe('audit');
    expect(surface.path).toBe('/audit');
    expect(surface.register).toBe('evidence');
    expect(surface.milestone).toBe('K6');
  });
});

describe('caps are read, not counted', () => {
  it('reports a result AT the row cap as very probably truncated', () => {
    const reading = capReading(
      view({ limits: { row_cap: 25, byte_cap: 10240, rows_returned: 25, bytes_returned: 900 } }),
    );
    expect(reading.state).toBe('at-row-cap');
    expect(reading.detail).toContain('rows were very probably discarded');
  });

  it('reports a result at the byte cap', () => {
    const reading = capReading(
      view({ limits: { row_cap: 25, byte_cap: 10240, rows_returned: 3, bytes_returned: 10240 } }),
    );
    expect(reading.state).toBe('at-byte-cap');
    expect(reading.detail).toContain('10 KiB ceiling');
  });

  it('reports unstated caps as unknowable', () => {
    const reading = capReading(
      view({ limits: { row_cap: 0, byte_cap: 0, rows_returned: 3, bytes_returned: 100 } }),
    );
    expect(reading.state).toBe('unstated');
    expect(reading.detail).toContain('cannot be read as complete');
  });

  it('reports a result inside both caps plainly', () => {
    expect(capReading(view()).state).toBe('within');
  });
});

describe('completeness is a claim about the view, not a default', () => {
  it('says a view with no flag makes no completeness claim', () => {
    const reading = completeness(view({ truncation_flag: null }));
    expect(reading.known).toBe(false);
    expect(reading.detail).toContain('makes no completeness claim');
  });

  it('names the column and calls a false flag an undercount', () => {
    const reading = completeness(
      view({ truncation_flag: { column: 'ancestry_complete', complete: false } }),
    );
    expect(reading.known).toBe(true);
    expect(reading.complete).toBe(false);
    expect(reading.detail).toContain('undercount');
    expect(reading.detail).toContain('ancestry_complete');
  });
});

describe('which views carried rows is stated, and no view is dropped to state it', () => {
  const carrying = view({ view: 'v_full', rows: [['a'], ['b']] });
  const empty = view({ view: 'v_empty', rows: [] });

  it('partitions without losing a view', () => {
    const reading = readCarriage([empty, carrying, empty]);
    expect(reading.total).toBe(3);
    expect(reading.carrying).toHaveLength(1);
    expect(reading.empty).toHaveLength(2);
    // The failure this guards against is a "show the interesting ones" helper that
    // quietly becomes a filter, so a view that was read and came back empty is never seen.
    expect(reading.ordered).toHaveLength(3);
    expect(reading.carrying.length + reading.empty.length).toBe(reading.total);
  });

  it('prints the ones with rows first, and says so rather than doing it silently', () => {
    const reading = readCarriage([empty, carrying]);
    expect(reading.ordered[0]?.view).toBe('v_full');
    expect(reading.detail).toContain('1 of the 2 view(s)');
    expect(reading.detail).toContain('a reading order and not a filter');
    // The claim about empty aggregates may be restated but never weakened.
    expect(reading.detail).toContain('not a statement that nothing exists');
  });

  it('says nothing was read when nothing was carried', () => {
    expect(readCarriage([]).detail).toContain('not a claim that nothing exists');
  });
});

describe('the negative assertion', () => {
  it('treats an empty probe list as "nothing was checked"', () => {
    const reading = readUnreachable([]);
    expect(reading.allRefused).toBe(false);
    expect(reading.detail).toContain('not a claim that nothing is reachable');
    expect(reading.detail).toContain('mainline_qa');
  });

  it('treats a reachable schema as a finding against the deployment', () => {
    const reading = readUnreachable([
      { schema_name: 'mainline_qa', probe: 'SELECT 1', outcome: 'reachable', sqlstate: null },
    ]);
    expect(reading.allRefused).toBe(false);
    expect(reading.detail).toContain('finding against the deployment');
  });

  it('treats a listed-but-unprobed schema as establishing nothing', () => {
    const reading = readUnreachable([
      { schema_name: 'mainline_qa', probe: 'SELECT 1', outcome: 'not_probed', sqlstate: null },
    ]);
    expect(reading.allRefused).toBe(false);
    expect(reading.detail).toContain('establishes nothing');
  });

  it('accepts refusals as the assertion', () => {
    const reading = readUnreachable([
      { schema_name: 'mainline_qa', probe: 'SELECT 1', outcome: 'refused', sqlstate: '42501' },
    ]);
    expect(reading.allRefused).toBe(true);
    expect(reading.detail).toContain('The refusal is the assertion');
  });
});

describe('the call tally is a reading of the log', () => {
  it('flags a write verb in the granted scopes', () => {
    const tally = tallyCalls([
      {
        action_id: '018f3a35-1100-7c60-8a33-095c7d4f82b3',
        agent_role: 'r',
        tool: 't',
        transport: 'mcp',
        granted_scopes: ['mainline_meas.external_attestation:INSERT'],
        outcome: 'ok',
        at: '2026-08-07T00:00:00.000Z',
      },
    ]);
    expect(tally.readOnly).toBe(false);
    expect(tally.writeScopes).toEqual(['mainline_meas.external_attestation:INSERT']);
  });

  it('reports read-only when every scope is a SELECT', () => {
    const tally = tallyCalls([
      {
        action_id: '018f3a35-1100-7c60-8a33-095c7d4f82b4',
        agent_role: 'mainline_auditor_ro',
        tool: 'run_query',
        transport: 'mcp',
        granted_scopes: ['mainline_audit:SELECT'],
        outcome: 'ok',
        at: '2026-08-07T00:00:00.000Z',
      },
    ]);
    expect(tally.readOnly).toBe(true);
    expect(tally.roles).toEqual(['mainline_auditor_ro']);
  });
});

describe('with no transport, it says so and shows nothing else', () => {
  it('renders the NO SOURCE panel', () => {
    render(<AuditRoot />);
    expect(screen.getByTestId('audit-no-source')).toBeInTheDocument();
    expect(screen.queryByTestId('call-table')).not.toBeInTheDocument();
  });
});

describe('the screen renders whatever columns arrive', () => {
  it('renders the fixture views, their statements and their caps', async () => {
    mount(bundleFiles());
    await waitFor(
      () => {
        expect(screen.getByTestId('view-count')).toBeInTheDocument();
      },
      { timeout: 10000 },
    );
    const payload = (auditEnvelope(bundleFiles()).data as AuditPayload | undefined) ?? null;
    expect(payload).not.toBeNull();

    for (const carried of payload?.views ?? []) {
      const caps = await screen.findByTestId(`caps-${carried.view}`);
      expect(caps.textContent).toContain(String(carried.limits.rows_returned));
      for (const column of carried.columns) {
        expect(screen.getAllByText(column.name).length).toBeGreaterThan(0);
      }
    }
  }, 20000);

  it('renders a column this console has never heard of', async () => {
    const envelope = auditEnvelope(bundleFiles());
    const data = envelope.data as AuditPayload;
    const invented: AuditView = {
      view: 'mainline_audit.v_invented_tomorrow',
      columns: [
        { name: 'site_id', sql_type: 'UUID' },
        { name: 'a_column_the_console_has_never_heard_of', sql_type: 'INT8' },
      ],
      rows: [['018f3a2e-0000-7000-8000-000000000001', 42]],
      limits: { row_cap: 25, byte_cap: 10240, rows_returned: 1, bytes_returned: 120 },
      truncation_flag: { column: 'ancestry_complete', complete: false },
      statement: 'SELECT * FROM mainline_audit.v_invented_tomorrow',
    };
    envelope.data = { ...data, views: [...data.views, invented] };

    mount(withAuditEnvelope(bundleFiles(), envelope));

    expect(
      await screen.findByText('a_column_the_console_has_never_heard_of', undefined, {
        timeout: 10000,
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText('42')).toBeInTheDocument();
    const flag = await screen.findByTestId('completeness-mainline_audit.v_invented_tomorrow');
    expect(flag.textContent).toContain('undercount');
  }, 20000);

  it('shows the write surface read-only, with no form that could insert', async () => {
    mount(bundleFiles());
    const shape = await screen.findByTestId('attestation-shape', undefined, { timeout: 10000 });
    expect(shape.textContent).toContain('attestor_kind');
    expect(screen.getByTestId('attestation-read-only').textContent).toContain(
      'never writes an evidentiary row',
    );
    expect(document.querySelector('form')).toBeNull();
    expect(document.querySelector('input')).toBeNull();
  }, 20000);

  it('labels the plan fragment as a plan and never a measurement', async () => {
    mount(bundleFiles());
    const table = await screen.findByTestId('call-table', undefined, { timeout: 10000 });
    expect(table.textContent).toContain('EXPLAIN ANALYZE is not available');
  }, 20000);

  it('states the ratio of views that carried rows, and prints those first', async () => {
    mount(bundleFiles());
    const payload = (auditEnvelope(bundleFiles()).data as AuditPayload | undefined) ?? null;
    const reading = readCarriage(payload?.views ?? []);
    expect(reading.total).toBeGreaterThan(0);
    // The ratio renders before the payload lands, reading 0 of 0, which is true of an
    // empty payload; wait for the read to settle before asserting on it.
    await screen.findByTestId(`caps-${reading.ordered[0]?.view ?? ''}`, undefined, {
      timeout: 10000,
    });
    const ratio = screen.getByTestId('views-carrying-rows');
    expect(ratio.textContent).toContain(`${reading.carrying.length} of ${reading.total}`);
    expect(screen.getByTestId('view-count').textContent).toBe(String(reading.total));

    // Every view the payload carried is still on screen, empty ones included.
    for (const carried of reading.ordered) {
      expect(screen.getByTestId(`caps-${carried.view}`)).toBeInTheDocument();
    }
    const rendered = [...document.querySelectorAll('[data-view]')].map((node) =>
      node.getAttribute('data-view'),
    );
    expect(rendered).toEqual(reading.ordered.map((carried) => carried.view));
  }, 20000);
});

/**
 * THE SENTENCE THAT SHIPPED FALSE.
 *
 * On the live demo this screen printed *"The bytes reached it through a bundle whose
 * every file digest and whose checkpoint were recomputed in this browser"* while the
 * transport was `live`, `bundleDigestPrefix` was null and the honesty strip two inches
 * above said no bundle had been consulted. Both mounts below carry the SAME payload, so
 * the only thing either assertion can be sensitive to is how the bytes arrived.
 */
describe('what this screen says about how its bytes arrived', () => {
  it('under REPLAY, keeps the bundle sentence verbatim — it is true there', async () => {
    mount(bundleFiles());
    const note = await screen.findByTestId('audit-seal-note', undefined, { timeout: 10000 });
    expect(note).toHaveAttribute('data-transport', 'replay');
    expect(note.textContent ?? '').toContain(
      'The bytes reached it through a bundle whose every file digest and whose checkpoint ' +
        'were recomputed in this browser',
    );
  }, 20000);

  it('under LIVE, claims no bundle, and names where live arithmetic does run', async () => {
    mountLive(bundleFiles());
    const note = await screen.findByTestId('audit-seal-note', undefined, { timeout: 10000 });
    expect(note).toHaveAttribute('data-transport', 'live');
    const text = note.textContent ?? '';
    // The false claim, in the form it shipped in.
    expect(text).not.toContain('reached it through a bundle');
    expect(text).toContain('no bundle was consulted');
    expect(text).toContain('custody');
    // The screen still refuses to borrow a seal it did not earn.
    expect(text).toContain('a tick with nothing behind it is decoration');
  }, 20000);
});
