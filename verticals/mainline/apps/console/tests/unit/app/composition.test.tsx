// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * THE COMPOSITION ROOT'S PROPERTIES.
 *
 * Four claims are under test here and each one is written so that the comfortable failure
 * is red:
 *
 *   1. with neither build variable set, NOTHING is constructed and every surface keeps
 *      its own NO SOURCE panel — the shell does not quietly invent a transport to make a
 *      screen paint;
 *   2. with an API base, ONE live transport reaches every surface context — the same
 *      object, not six — and `describe().mode` is `live`;
 *   3. with a bundle URL and a verifier that rejects, NO FRAME IS SERVED and the failure
 *      state renders. This is the assertion that makes the replay path evidence rather
 *      than a fixture player: the console must be unable to show a screen from bytes that
 *      did not verify;
 *   4. switching modes changes the badge and NOTHING ELSE — asserted by DOM node
 *      identity, so a switch that quietly remounted the surface below it would fail.
 *
 * Plus the demo driver's two present-tense truths: it renders the three beats' exhibits
 * verbatim when it has a payload, and it renders an actionable absence when it does not.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { Composition } from '../../../src/app/composition';
import { HonestyChrome } from '../../../src/app/HonestyChrome';
import { HonestyProvider } from '../../../src/app/HonestyProvider';
import {
  paramsFromAddress,
  selectSource,
  sourceFor,
  type ConsoleEnvironment,
} from '../../../src/app/source-select';
import { TransportError, type MainlineTransport } from '../../../src/data/transport';
import { useAuditTransport } from '../../../src/features/audit/transport-context';
import { useCustodyTransport } from '../../../src/features/custody/transport-context';
import { useDiffTransport } from '../../../src/features/diff/transport-context';
import {
  DemoDriver,
  GateRunReport,
  type GateRunData,
} from '../../../src/features/gate/DemoDriver';
import { GateTransportContext, useGateTransport } from '../../../src/features/gate/transport-context';
import { usePropagationTransport } from '../../../src/features/propagation/transport-context';
import { useSilenceTransport } from '../../../src/features/silence/transport-context';
import { bundleFiles, refusingVerifier } from '../data/_support';

// ── Scaffolding ────────────────────────────────────────────────────────────

const API_BASE = 'https://demo.example.test/api';
const BUNDLE_URL = 'https://demo.example.test/bundle/';

interface Seen {
  gate: MainlineTransport | null;
  audit: MainlineTransport | null;
  custody: MainlineTransport | null;
  diff: MainlineTransport | null;
  silence: MainlineTransport | null;
  propagation: MainlineTransport | null;
}

let seen: Seen;

beforeEach(() => {
  seen = {
    gate: null,
    audit: null,
    custody: null,
    diff: null,
    silence: null,
    propagation: null,
  };
});

/**
 * Stands in for a surface. It reads all six contexts, so "one transport reaches every
 * surface" is checkable by object identity rather than by six separate renders.
 */
function Probe(): ReactNode {
  const gate = useGateTransport();
  const audit = useAuditTransport();
  const custody = useCustodyTransport();
  const diff = useDiffTransport();
  const silence = useSilenceTransport();
  const propagation = usePropagationTransport();

  useEffect(() => {
    seen = { gate, audit, custody, diff, silence, propagation };
  }, [gate, audit, custody, diff, silence, propagation]);

  const description = gate?.describe() ?? null;
  return (
    <p
      data-testid="probe"
      data-mode={description?.mode ?? 'none'}
      data-source={description?.source ?? ''}
    >
      {gate === null ? 'NO SOURCE' : 'the surface, unchanged by which transport is behind it'}
    </p>
  );
}

function mount(env: ConsoleEnvironment, extra: Partial<Parameters<typeof Composition>[0]> = {}) {
  return render(
    <HonestyProvider>
      <Composition env={env} params={new URLSearchParams()} {...extra}>
        {(chrome) => (
          <>
            <HonestyChrome />
            {chrome}
            <Probe />
          </>
        )}
      </Composition>
    </HonestyProvider>,
  );
}

/** Serves `fixtures/bundles/blk-07` at BUNDLE_URL. No network, no real `fetch`. */
function bundleFetch(): typeof fetch {
  const files = bundleFiles();
  const prefix = new URL(BUNDLE_URL).pathname;
  return ((input: string): Promise<Response> => {
    const url = new URL(input);
    const path = url.pathname.startsWith(prefix) ? url.pathname.slice(prefix.length) : url.pathname;
    const bytes = files.get(path);
    if (bytes === undefined) {
      return Promise.resolve({ ok: false, status: 404 } as unknown as Response);
    }
    const buffer = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(buffer).set(bytes);
    return Promise.resolve({
      ok: true,
      status: 200,
      arrayBuffer: () => Promise.resolve(buffer),
    } as unknown as Response);
  }) as unknown as typeof fetch;
}

// ── 1. The decision, as a pure function ────────────────────────────────────

describe('selectSource — build-time only, three rules', () => {
  it('carries no source when neither variable is set, and says which two were absent', () => {
    const selection = selectSource({});
    expect(selection.configured).toHaveLength(0);
    expect(selection.initial).toBeNull();
    expect(selection.switchable).toBe(false);
    expect(selection.why).toContain('VITE_MAINLINE_API_BASE');
    expect(selection.why).toContain('VITE_MAINLINE_BUNDLE_URL');
  });

  it('treats an empty or whitespace value as unset rather than as a base URL', () => {
    expect(selectSource({ VITE_MAINLINE_API_BASE: '   ' }).initial).toBeNull();
    expect(selectSource({ VITE_MAINLINE_BUNDLE_URL: '' }).initial).toBeNull();
  });

  it('builds the one that is set, with no control, when only one is set', () => {
    const live = selectSource({ VITE_MAINLINE_API_BASE: API_BASE });
    expect(live.initial?.kind).toBe('live');
    expect(live.switchable).toBe(false);

    const replay = selectSource({ VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL });
    expect(replay.initial?.kind).toBe('replay');
    expect(replay.switchable).toBe(false);
  });

  it('prefers LIVE and offers the switch when both are set', () => {
    const both = selectSource({
      VITE_MAINLINE_API_BASE: API_BASE,
      VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL,
    });
    expect(both.initial?.kind).toBe('live');
    expect(both.switchable).toBe(true);
    expect(sourceFor(both, 'replay')?.location).toBe(BUNDLE_URL);
  });

  it('honours ?source= only when the build carries both — it can never introduce an origin', () => {
    const both = {
      VITE_MAINLINE_API_BASE: API_BASE,
      VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL,
    };
    expect(selectSource(both, new URLSearchParams('source=replay')).initial?.kind).toBe('replay');
    expect(selectSource(both, new URLSearchParams('source=nonsense')).initial?.kind).toBe('live');

    // Only the bundle is compiled in; a link asking for LIVE cannot conjure an API.
    const replayOnly = selectSource(
      { VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL },
      new URLSearchParams('source=live'),
    );
    expect(replayOnly.initial?.kind).toBe('replay');
    expect(replayOnly.switchable).toBe(false);
  });

  it('merges the address the way the router does, hash winning', () => {
    const params = paramsFromAddress('?source=live', '#/gate?source=replay');
    expect(params.get('source')).toBe('replay');
  });
});

// ── 2. Neither variable set ────────────────────────────────────────────────

describe('with neither variable set', () => {
  it('constructs nothing, so every surface keeps its own NO SOURCE panel', async () => {
    mount({});
    await waitFor(() => {
      expect(seen.gate).toBeNull();
    });
    expect(screen.getByTestId('probe')).toHaveTextContent('NO SOURCE');
    expect(seen.audit).toBeNull();
    expect(seen.custody).toBeNull();
    expect(seen.diff).toBeNull();
    expect(seen.silence).toBeNull();
    expect(seen.propagation).toBeNull();
  });

  it('adds no chrome of its own — "unchanged" means nothing was added above the panel', () => {
    mount({});
    expect(screen.queryByTestId('source-chrome')).toBeNull();
  });

  it('leaves the honesty chrome saying UNKNOWN, marked unset', async () => {
    mount({});
    await waitFor(() => {
      expect(screen.getByTestId('chrome-transport')).toHaveTextContent('UNKNOWN');
    });
  });
});

// ── 3. Live ────────────────────────────────────────────────────────────────

describe('with an API base', () => {
  it('reaches every surface context with ONE transport, and describe().mode is live', async () => {
    mount({ VITE_MAINLINE_API_BASE: API_BASE });

    await waitFor(() => {
      expect(seen.gate).not.toBeNull();
    });

    expect(seen.gate?.describe().mode).toBe('live');
    expect(seen.gate?.describe().source).toBe(API_BASE);

    // ONE transport, six sockets. Six equivalent transports would satisfy a mode
    // assertion and would still be six caches, six clocks and six verification states.
    expect(seen.audit).toBe(seen.gate);
    expect(seen.custody).toBe(seen.gate);
    expect(seen.diff).toBe(seen.gate);
    expect(seen.silence).toBe(seen.gate);
    expect(seen.propagation).toBe(seen.gate);
  });

  it('publishes the badge into the honesty chrome, from describe() rather than from a flag', async () => {
    mount({ VITE_MAINLINE_API_BASE: API_BASE });
    await waitFor(() => {
      expect(screen.getByTestId('chrome-transport')).toHaveTextContent('LIVE');
    });
    expect(screen.getByTestId('source-badge')).toHaveTextContent('LIVE');
    expect(screen.getByTestId('source-location')).toHaveTextContent(API_BASE);
  });

  it('offers no switch when the build carries only a live source', async () => {
    mount({ VITE_MAINLINE_API_BASE: API_BASE });
    await screen.findByTestId('source-badge');
    expect(screen.queryByTestId('source-switch')).toBeNull();
  });
});

// ── 4. Replay, with a verifier that refuses ────────────────────────────────

describe('with a bundle URL and a verifier that rejects', () => {
  it('serves no frame and renders the failure state', async () => {
    const reason = 'the manifest digest is not the digest that was sealed';
    mount(
      { VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL },
      { fetchImpl: bundleFetch(), verifier: refusingVerifier(reason) },
    );

    const panel = await screen.findByTestId('replay-verification-failed');
    expect(panel).toHaveTextContent(reason);
    expect(panel).toHaveTextContent('test:always-refuses');
    // The panel is an alert, because a bundle that failed verification is not a state a
    // reader may scroll past.
    expect(panel).toHaveAttribute('role', 'alert');

    await waitFor(() => {
      expect(screen.getByTestId('chrome-seal')).toHaveTextContent('VERIFICATION FAILED');
    });

    // NO FRAME IS SERVED. Not a degraded one, not a cached one, not a placeholder.
    const transport = seen.gate;
    expect(transport).not.toBeNull();
    const failure = await transport
      ?.exchange({ resource: 'permit', path: { permit_id: '018f3a2f-1104-7c88-b3aa-77c1de40e2b1' } })
      .then(
        () => null,
        (error: unknown) => error,
      );
    expect(failure).toBeInstanceOf(TransportError);
    expect((failure as TransportError).failure).toBe('tampered');
  });

  it('reports REPLAY in the chrome even while its bundle is refused — the badge is not a verdict', async () => {
    mount(
      { VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL },
      { fetchImpl: bundleFetch(), verifier: refusingVerifier('no') },
    );
    await waitFor(() => {
      expect(screen.getByTestId('chrome-transport')).toHaveTextContent('REPLAY');
    });
  });
});

// ── 5. Switching ───────────────────────────────────────────────────────────

describe('switching modes', () => {
  it('changes the badge and nothing else', async () => {
    const user = userEvent.setup();
    mount(
      { VITE_MAINLINE_API_BASE: API_BASE, VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL },
      { fetchImpl: bundleFetch(), verifier: refusingVerifier('not the point of this test') },
    );

    await waitFor(() => {
      expect(screen.getByTestId('source-badge')).toHaveTextContent('LIVE');
    });

    const before = screen.getByTestId('probe');
    const beforeText = before.textContent;

    await user.click(screen.getByTestId('source-switch'));

    await waitFor(() => {
      expect(screen.getByTestId('source-badge')).toHaveTextContent('REPLAY');
    });

    const after = screen.getByTestId('probe');
    // Node IDENTITY, not text equality: a switch that remounted the surface below it
    // would lose scroll position, focus and any in-flight read, and would pass a
    // textContent check while doing so.
    expect(after).toBe(before);
    expect(after.textContent).toBe(beforeText);

    expect(seen.gate?.describe().mode).toBe('replay');
    expect(seen.gate?.describe().source).toBe(BUNDLE_URL);
    // Still one transport, still every socket.
    expect(seen.propagation).toBe(seen.gate);

    await waitFor(() => {
      expect(screen.getByTestId('chrome-transport')).toHaveTextContent('REPLAY');
    });
  });

  it('withdraws the replay seal when the reader switches back to LIVE', async () => {
    const user = userEvent.setup();
    mount(
      { VITE_MAINLINE_API_BASE: API_BASE, VITE_MAINLINE_BUNDLE_URL: BUNDLE_URL },
      { fetchImpl: bundleFetch(), verifier: refusingVerifier('this bundle is not the sealed one') },
    );

    await user.click(await screen.findByTestId('source-switch'));
    await waitFor(() => {
      expect(screen.getByTestId('chrome-seal')).toHaveTextContent('VERIFICATION FAILED');
    });

    await user.click(screen.getByTestId('source-switch'));
    await waitFor(() => {
      expect(screen.getByTestId('chrome-transport')).toHaveTextContent('LIVE');
    });

    // A verdict about a bundle nobody is looking at any more is a verdict the chrome
    // must not keep displaying. Nothing has been verified on the live path, and the
    // ugliest honest state is the correct one.
    expect(screen.getByTestId('chrome-seal')).toHaveTextContent('NOT VERIFIED');
    expect(screen.queryByTestId('replay-verification-failed')).toBeNull();
  });
});

// ── 6. The demo driver ─────────────────────────────────────────────────────

/**
 * A gate-run payload in the shape `verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`
 * governs. The exhibits are the ones `docs/deploy/gate-run-contract.md` §1 records as
 * OBSERVED on CockroachDB CCL v26.2.5 — they are quoted here so the rendering assertion
 * is against real output rather than against a shape somebody invented for a test.
 */
const RUN: GateRunData = {
  schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
  run_id: 'w8-render-check',
  generated_at: '2026-08-10T12:00:00Z',
  outcome: 'completed',
  verdict: 'PROVEN',
  failures: [],
  persisted: false,
  elapsed_ms: 412,
  transaction: {
    isolation: 'SERIALIZABLE',
    disposition: 'rolled_back',
    opened_logical_timestamp: '1786000000000000000.0000000000',
    closed_logical_timestamp: '1786000000000000000.0000000000',
    single_transaction: true,
    savepoints: ['gate_run_beat_2', 'gate_run_beat_3', 'gate_run_beat_4'],
    retry_sqlstate: null,
    canonicalisation: 'trappoint-canon/1.0',
  },
  subject: {
    subject_kind: 'permit',
    subject_id: '077a6fdd-2167-559c-b2ff-8e3c8352504d',
    external_ref: 'demo/2026-08',
    state: 'dispositioned',
    head_seq: 4,
    gate_epoch: 1,
    open_blocking: 1,
    open_blocking_derived: 1,
    blocking_check_id: null,
    exposure_receipt_id: null,
    site_code: 'BLK-07',
  },
  beats: [
    {
      ordinal: 1,
      name: 'read',
      label: 'the permit and its open obligation',
      expected: { outcome: 'read' },
      outcome: 'read',
      sqlstate: '00000',
      constraint: null,
      constraint_source: null,
      message: null,
      matched_expectation: true,
      elapsed_ms: 8,
      statement: 'SELECT … FROM mainline.permit WHERE permit_id = %s',
      observed: { state: 'dispositioned', open_blocking_projected: 1, open_blocking_derived: 1 },
      note: null,
    },
    {
      ordinal: 2,
      name: 'merge',
      label: 'merge the permit',
      expected: { outcome: 'refused', sqlstate: '23514', constraint: 'gate_closed_when_issued' },
      outcome: 'refused',
      sqlstate: '23514',
      constraint: 'gate_closed_when_issued',
      constraint_source: 'reported',
      message:
        "failed to satisfy CHECK constraint ((state != 'merged') OR (open_blocking = 0))",
      matched_expectation: true,
      elapsed_ms: 61,
      statement: 'CALL mainline.merge_permit(…)',
      observed: { open_blocking_projected: 1, open_blocking_derived: 1, counters_agree: true },
      note: null,
    },
    {
      ordinal: 3,
      name: 'projection_drift_attack',
      label: 'force the projected counter to zero, then merge',
      expected: { outcome: 'refused', sqlstate: 'P0001', constraint: 'mainline.fn_permit_merge_gate' },
      outcome: 'refused',
      sqlstate: 'P0001',
      constraint: 'mainline.fn_permit_merge_gate',
      constraint_source: 'parsed',
      message:
        'MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero',
      matched_expectation: true,
      elapsed_ms: 74,
      statement: 'UPDATE mainline.permit SET open_blocking = 0; CALL mainline.merge_permit(…)',
      observed: {
        counter_forced_to: 0,
        open_blocking_projected: 0,
        open_blocking_derived: 1,
        counters_agree: false,
      },
      note: null,
    },
    {
      ordinal: 4,
      name: 'admit',
      label: 'sign one disposition, then merge',
      expected: { outcome: 'admitted', sqlstate: '00000' },
      outcome: 'admitted',
      sqlstate: '00000',
      constraint: null,
      constraint_source: null,
      message: null,
      matched_expectation: true,
      elapsed_ms: 97,
      statement: 'INSERT INTO mainline.disposition (…); CALL mainline.merge_permit(…)',
      observed: {
        open_blocking_after_signature: 0,
        merge_record: {
          clearance_digest:
            'c283343729c7a787b9d102ae461c6d795b9335341fbcf8fd276325d020d78990',
          merged_commit: 'ab',
          gate_epoch: 1,
          merged_at: '2026-08-10T12:00:00Z',
        },
      },
      note: null,
    },
  ],
  persistence_check: {
    identical: true,
    tables: ['mainline.permit', 'mainline.merge_record'],
    note: 'Row counts taken before the transaction opened and after it was rolled back.',
  },
};

describe('the demo driver renders what the database said, verbatim', () => {
  it('shows all three exhibits under RUN ALL', () => {
    render(<GateRunReport run={RUN} reveal="all" />);

    expect(screen.getByTestId('gate-run-beat-2-sqlstate')).toHaveTextContent('23514');
    expect(screen.getByTestId('gate-run-beat-2-constraint')).toHaveTextContent(
      'gate_closed_when_issued',
    );
    expect(screen.getByTestId('gate-run-beat-3-sqlstate')).toHaveTextContent('P0001');
    expect(screen.getByTestId('gate-run-beat-3-constraint')).toHaveTextContent(
      'mainline.fn_permit_merge_gate',
    );
    expect(screen.getByTestId('gate-run-beat-4-sqlstate')).toHaveTextContent('00000');

    // The exhibits carry the raw value in a data attribute, so a browser spec can read
    // them without depending on how they are laid out.
    expect(screen.getByTestId('gate-run-beat-2-constraint')).toHaveAttribute(
      'data-constraint',
      'gate_closed_when_issued',
    );

    expect(screen.getByTestId('gate-run-verdict')).toHaveTextContent('PROVEN');
    expect(screen.getByTestId('gate-run-persisted')).toHaveTextContent('false');
    expect(screen.getByTestId('gate-run-single-transaction')).toHaveTextContent('true');
  });

  it('renders the database message verbatim, with no sentence of its own around it', () => {
    render(<GateRunReport run={RUN} reveal="all" />);
    const message = screen.getByTestId('gate-run-beat-3-message');
    expect(message.textContent).toBe(RUN.beats[2]?.message);
  });

  it('marks a PARSED exhibit as the weakened diagnosis it is, and a reported one not at all', () => {
    render(<GateRunReport run={RUN} reveal="all" />);
    expect(screen.getByTestId('gate-run-beat-3-parsed')).toHaveTextContent(/WEAKENED/);
    expect(screen.queryByTestId('gate-run-beat-2-parsed')).toBeNull();
  });

  it('shows only the beat a single control names', () => {
    render(<GateRunReport run={RUN} reveal={3} />);
    expect(screen.getByTestId('gate-run-beat-3')).toBeInTheDocument();
    expect(screen.queryByTestId('gate-run-beat-2')).toBeNull();
    expect(screen.queryByTestId('gate-run-beat-4')).toBeNull();
  });

  it('says loudly when a beat did not match the expectation it was written against', () => {
    const notProven: GateRunData = {
      ...RUN,
      verdict: 'NOT PROVEN',
      failures: ['beat 2 observed admitted where refused was expected.'],
      beats: RUN.beats.map((beat) =>
        beat.ordinal === 2
          ? { ...beat, outcome: 'admitted', matched_expectation: false, sqlstate: '00000' }
          : beat,
      ),
    };
    render(<GateRunReport run={notProven} reveal="all" />);
    expect(screen.getByTestId('gate-run-verdict')).toHaveTextContent('NOT PROVEN');
    expect(screen.getByTestId('gate-run-beat-2-mismatch')).toBeInTheDocument();
    expect(screen.getByTestId('gate-run-failures')).toHaveTextContent(
      'beat 2 observed admitted where refused was expected.',
    );
  });
});

describe('the demo driver states its own absences', () => {
  it('renders NO SOURCE when the composition root built no transport', () => {
    render(
      <GateTransportContext.Provider value={null}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    expect(screen.getByTestId('demo-driver-no-source')).toHaveTextContent('VITE_MAINLINE_API_BASE');
  });

  it('names the three files that must declare the endpoint before the controls can fire', () => {
    const stub: MainlineTransport = {
      describe: () => ({
        mode: 'live',
        source: API_BASE,
        bundleDigestPrefix: null,
        staged: false,
        stagedNote: null,
      }),
      exchange: () => Promise.reject(new Error('the driver must not have called this')),
    };
    render(
      <GateTransportContext.Provider value={stub}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    const panel = screen.getByTestId('demo-driver-not-declared');
    expect(panel).toHaveTextContent('src/data/resources.ts');
    expect(panel).toHaveTextContent('src/data/contracts.ts');
    expect(panel).toHaveTextContent('app.py');
    // No control is offered that cannot fire.
    expect(screen.queryByTestId('demo-control-merge')).toBeNull();
  });
});
