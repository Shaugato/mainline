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
import { bundleFiles, nodeFs, refusingVerifier } from '../data/_support';

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

  /**
   * The shell has to be able to ASK which subjects exist, because its navigation now opens
   * each surface on one. The render prop is the boundary that already exists between this
   * module and the shell, so the transport crosses THERE rather than through a seventh
   * context — and it must be the SAME object the six surface contexts were given, or the
   * shell's subject index would be an answer about a source nobody is looking at.
   */
  it('hands the shell the same transport it hands every surface context', async () => {
    let handed: MainlineTransport | null | undefined;
    render(
      <HonestyProvider>
        <Composition env={{ VITE_MAINLINE_API_BASE: API_BASE }} params={new URLSearchParams()}>
          {(chrome, transport) => {
            handed = transport;
            return (
              <>
                {chrome}
                <Probe />
              </>
            );
          }}
        </Composition>
      </HonestyProvider>,
    );

    await waitFor(() => {
      expect(seen.gate).not.toBeNull();
    });
    expect(handed).toBe(seen.gate);
  });

  it('hands the shell null when the build carries no source, never a stand-in', () => {
    let handed: MainlineTransport | null | undefined;
    render(
      <HonestyProvider>
        <Composition env={{}} params={new URLSearchParams()}>
          {(_chrome, transport) => {
            handed = transport;
            return null;
          }}
        </Composition>
      </HonestyProvider>,
    );
    expect(handed).toBeNull();
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
    // ugliest honest state is the correct one — but the ugliest honest state is now
    // stated rather than implied: under LIVE the bundle verifier does not run at all, so
    // the cell says THAT instead of "NOT VERIFIED", which reads as a failure that has not
    // occurred. The assertions below are the properties that must survive the wording:
    // no green tick, the slot still marked `unset`, and no lingering failure panel.
    const sealCell = screen.getByTestId('chrome-seal');
    expect(sealCell).toHaveTextContent('NOT RUN (no bundle in LIVE)');
    expect(sealCell.textContent ?? '').not.toMatch(/verified in this browser/i);
    expect(sealCell.closest('[data-provenance]')).toHaveAttribute('data-provenance', 'unset');
    expect(sealCell.closest('[data-tone]')).toHaveAttribute('data-tone', 'warn');
    expect(screen.getByTestId('honesty-note-seal').textContent ?? '').toContain(
      'nothing here has passed and nothing here has failed',
    );
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
  // WIDENED 2026-08-14 alongside the contract (lead ruling R10). The schema requires
  // eight members here, and the three this fixture used to carry were led by the one the
  // contract says the verdict does NOT key on. `self_persisted` is the run-scoped claim;
  // `identical` is the whole-database reading beside it; `concurrent_writes` is null
  // exactly when `identical` is true, which is the state this PROVEN run is in.
  persistence_check: {
    before: {
      row_counts: { 'mainline.permit': 3, 'mainline.merge_record': 1, 'mainline.disposition': 2 },
      subject_row_counts: {
        'mainline.merge_record': 0,
        'mainline.permit_event': 4,
        'mainline.disposition': 1,
      },
      permit_row: {
        state: 'dispositioned',
        head_seq: 4,
        gate_epoch: 1,
        open_blocking: 1,
        unmet_floor_count: 1,
        countersigned_count: 0,
        merged_commit: null,
      },
    },
    after: {
      row_counts: { 'mainline.permit': 3, 'mainline.merge_record': 1, 'mainline.disposition': 2 },
      subject_row_counts: {
        'mainline.merge_record': 0,
        'mainline.permit_event': 4,
        'mainline.disposition': 1,
      },
      permit_row: {
        state: 'dispositioned',
        head_seq: 4,
        gate_epoch: 1,
        open_blocking: 1,
        unmet_floor_count: 1,
        countersigned_count: 0,
        merged_commit: null,
      },
    },
    identical: true,
    self_persisted: false,
    self_evidence: {
      minted_disposition_id: '6b1f2f0e-6a1f-4a3e-9e0e-2f6b1f2f0e6a',
      minted_disposition_rows_after_rollback: 0,
      subject_row_counts_before: {
        'mainline.merge_record': 0,
        'mainline.permit_event': 4,
        'mainline.disposition': 1,
      },
      subject_row_counts_after: {
        'mainline.merge_record': 0,
        'mainline.permit_event': 4,
        'mainline.disposition': 1,
      },
      permit_row_identical: true,
    },
    concurrent_writes: null,
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

  it('shows self_persisted BESIDE identical, because the verdict keys on the first', () => {
    // ADDED 2026-08-14 under lead ruling R10. The contract's own persistence_check
    // description says the verdict keys on `self_persisted`, not on `identical`; the
    // screen showed only `identical`, which is a true statement about a DIFFERENT
    // SUBJECT — every one of those tables, counted whole, including rows another caller
    // wrote. Nothing was removed to correct that.
    render(<GateRunReport run={RUN} reveal="all" />);
    const persistence = screen.getByTestId('gate-run-persistence');
    expect(persistence).toHaveTextContent('self_persisted');
    expect(persistence).toHaveTextContent('identical');
    expect(persistence).toHaveTextContent('concurrent_writes');
    expect(persistence).toHaveTextContent(RUN.persistence_check.note);

    // The run-scoped readings the verdict is computed FROM, so a reader can recompute it.
    const self = screen.getByTestId('gate-run-persistence-self');
    expect(self).toHaveTextContent(
      RUN.persistence_check.self_evidence.minted_disposition_id ?? 'this must not be reached',
    );
  });

  it('names the other caller when a whole-table count moved and this run did not write', () => {
    // The state this widening exists for: a shared cluster, somebody else committing a
    // row between the two readings. `identical` goes false and says nothing about whose
    // rows moved; `self_persisted` stays false and is what the verdict keys on. A screen
    // carrying only the first would read as an accusation against the run in front of it.
    const shared: GateRunData = {
      ...RUN,
      persistence_check: {
        ...RUN.persistence_check,
        identical: false,
        after: {
          ...RUN.persistence_check.after,
          row_counts: { ...RUN.persistence_check.after.row_counts, 'mainline.permit': 4 },
        },
        concurrent_writes: { 'mainline.permit': [3, 4] },
      },
    };
    render(<GateRunReport run={shared} reveal="all" />);

    const persistence = screen.getByTestId('gate-run-persistence');
    expect(persistence).toHaveTextContent('mainline.permit 3 → 4');

    // And the fingerprint those two readings came from is on screen, table by table,
    // with the row that moved marked by a data attribute rather than by a sentence.
    const moved = screen.getByTestId('gate-run-fingerprint-row_counts.mainline.permit');
    expect(moved).toHaveAttribute('data-moved', 'true');
    expect(moved).toHaveTextContent('3');
    expect(moved).toHaveTextContent('4');
    expect(
      screen.getByTestId('gate-run-fingerprint-permit_row.open_blocking'),
    ).toHaveAttribute('data-moved', 'false');
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

  it('does NOT render the not-declared panel, because the endpoint is declared', () => {
    // INVERTED ON 2026-08-14, and the inversion is the point of the change.
    //
    // This test used to assert that the panel RENDERED and named the three files that
    // still had to declare the endpoint. `demo_gate_run` is now the seventeenth entry in
    // `src/data/resources.ts` (lead ruling R1: a beat that is not declared cannot be
    // driven by a console-faithful walk), so the panel is unreachable and asserting that
    // it appears would pin the defect rather than the fix.
    //
    // The panel itself is deliberately KEPT in `DemoDriver.tsx` as the honest fallback
    // for a build that ever strips the declaration. This test is what proves such a build
    // is not the one shipping: it mounts the driver with a real transport and requires
    // the absence of the panel AND the presence of every control.
    const stub: MainlineTransport = {
      describe: () => ({
        mode: 'live',
        source: API_BASE,
        bundleDigestPrefix: null,
        staged: false,
        stagedNote: null,
      }),
      // Still rejects: pressing a control is a separate test. Reaching here at MOUNT
      // would mean the driver fires an exchange nobody asked for.
      exchange: () => Promise.reject(new Error('the driver must not have called this')),
    };
    render(
      <GateTransportContext.Provider value={stub}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );

    expect(screen.queryByTestId('demo-driver-not-declared')).toBeNull();

    // Every control the panel used to stand in for is now offered, and the driver names
    // the endpoint it will actually address.
    expect(screen.getByTestId('demo-driver')).toHaveTextContent('POST /v1/demo/gate-run');
    for (const control of ['merge', 'forge', 'admit', 'all']) {
      expect(screen.getByTestId(`demo-control-${control}`)).toBeInTheDocument();
    }
  });

  it('still carries an accurate remedy list for a build that strips the declaration', async () => {
    // The fallback panel is only worth keeping if what it SAYS is true, and one of its
    // three entries was not: it told the reader that app.py's route table declared the
    // four kernel POSTs and no demo route, "so the endpoint 404s". app.py:229 has carried
    // Route("POST", "/v1/demo/gate-run", "demo_gate_run") since 2026-08-11, and the
    // deployed URL answers 503 dsn_unset — reachable, refusing for a named reason.
    //
    // Asserted against the COMMITTED SOURCE rather than an exported constant, for two
    // reasons. The panel is unreachable in this build (the test above is what proves
    // that), so its prose cannot be read off a render; and exporting the array purely to
    // test it would trip `react-refresh/only-export-components` — which is a real rule
    // about a real hazard, not an obstacle to route around. What a judge would read is
    // the file, so the file is what is checked.
    const fs = await nodeFs();
    const file = fs.readFileSync('src/features/gate/DemoDriver.tsx', 'utf8');

    // Only the ARRAY LITERAL is examined, not the whole file. The module docstring above
    // it quotes the false sentence verbatim in order to record what was corrected and
    // why — that quotation is the fix, not a relapse, and a naive grep over the file
    // would fail on the very comment that documents the repair. What a reader sees is
    // the array, so the array is the thing under test.
    const start = file.indexOf('const DECLARATION_GAP');
    expect(start, 'DECLARATION_GAP must still exist: it is the fallback panel’s prose').toBeGreaterThan(
      -1,
    );
    const source = file.slice(start, file.indexOf('\n];', start));

    // Three entries still, so the list did not quietly shrink to avoid being wrong.
    expect(source.match(/^\s{2}'/gm) ?? []).toHaveLength(3);

    // The false sentence, and the shape of it, must not come back.
    expect(source).not.toMatch(/so the endpoint 404s/);
    expect(source).not.toMatch(/declares the four kernel POSTs and no demo route/);

    // What replaced it is the measurement.
    expect(source).toMatch(/503 dsn_unset/);
    expect(source).toMatch(/ALREADY DONE/);

    // The two console files a stripped build really would need are still named, so the
    // fallback remains actionable rather than becoming a shrug.
    expect(source).toMatch(/src\/data\/resources\.ts/);
    expect(source).toMatch(/src\/data\/contracts\.ts/);
  });
});
