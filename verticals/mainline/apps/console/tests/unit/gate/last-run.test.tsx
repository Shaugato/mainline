// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * CONTRACT B, PINNED FROM THE PRODUCER'S SIDE.
 *
 * `docs/leads/demo-story-plan.md` §7.1 fixes this contract so that nobody negotiates it:
 * `src/features/gate/last-run.ts` publishes the last COMPLETED gate-run payload, or
 * `null` before any press. This file asserts the half this worker owns — that the value
 * appears when a run completes, that it is the payload VERBATIM, and above all that
 * `null` is what a subscriber sees until then.
 *
 * ── WHY `null` GETS MORE COVERAGE THAN THE PAYLOAD ───────────────────────────────
 *
 * The contract's last clause is the load-bearing one: *"`null` must keep W4's `NO
 * ATTEMPT` state exactly as it renders today."* A refusal band that quietly filled in
 * during a load, or after a transport failure, or after the endpoint itself refused,
 * would be claiming an attempt the database never answered — which is the same family of
 * defect as `docs/leads/demo-story-plan.md` §0.4(i), only inverted and harder to notice.
 * So the three not-a-completed-run states each get their own case below.
 */

import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import { resolveRequest, type ResourceRequest } from '../../../src/data/resources';
import { TransportError, type Exchange, type MainlineTransport } from '../../../src/data/transport';
import { DemoDriver } from '../../../src/features/gate/DemoDriver';
import type { GateRunData } from '../../../src/features/gate/beats';
import {
  LastGateRunContext,
  lastGateRunSnapshot,
  publishLastGateRun,
  resetLastGateRun,
  useLastGateRun,
} from '../../../src/features/gate/last-run';
import { GateTransportContext } from '../../../src/features/gate/transport-context';

// ── A payload nobody could mistake for the demonstration's own ─────────────

/**
 * The exhibits are planted. If this run ever reached a screen that was meant to be
 * showing the real demonstration, the planted codes would say so immediately — and a
 * consumer that read its values from a literal rather than from this channel would keep
 * printing the demo's own `23514` while this fixture carried `42501`.
 */
function plantedRun(runId: string): GateRunData {
  const fingerprint = {
    row_counts: { 'mainline.permit': 1 },
    subject_row_counts: { 'mainline.disposition': 0 },
    permit_row: {
      state: 'planted',
      head_seq: 1,
      gate_epoch: 2,
      open_blocking: 5,
      unmet_floor_count: 5,
      countersigned_count: 0,
      merged_commit: null,
    },
  } as const;

  return {
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    run_id: runId,
    generated_at: '2026-08-15T00:00:00Z',
    outcome: 'completed',
    verdict: 'PROVEN',
    failures: [],
    persisted: false,
    elapsed_ms: 3,
    transaction: {
      isolation: 'SERIALIZABLE',
      disposition: 'rolled_back',
      opened_logical_timestamp: '1786000000000000000.0000000000',
      closed_logical_timestamp: '1786000000000000000.0000000000',
      single_transaction: true,
      savepoints: ['gate_run_beat_2'],
      retry_sqlstate: null,
      canonicalisation: 'trappoint-canon/1.0',
    },
    subject: {
      subject_kind: 'permit',
      subject_id: '00000000-0000-4000-8000-000000000000',
      external_ref: 'planted/fixture',
      state: 'planted',
      head_seq: 1,
      gate_epoch: 2,
      open_blocking: 5,
      open_blocking_derived: 5,
      blocking_check_id: null,
      exposure_receipt_id: null,
      site_code: 'PLANT-00',
    },
    beats: [
      {
        ordinal: 1,
        name: 'read',
        label: 'planted read',
        expected: { outcome: 'read' },
        outcome: 'read',
        sqlstate: '01000',
        constraint: null,
        constraint_source: null,
        message: null,
        matched_expectation: true,
        elapsed_ms: 0.011,
        statement: 'SELECT 1',
        observed: {},
        note: null,
        refusal: null,
      },
      {
        ordinal: 2,
        name: 'merge',
        label: 'planted merge',
        expected: { outcome: 'refused' },
        outcome: 'refused',
        sqlstate: '42501',
        constraint: 'planted_check_not_the_real_one',
        constraint_source: 'reported',
        message: 'PLANTED MESSAGE FOR BEAT 2',
        matched_expectation: true,
        elapsed_ms: 527.051,
        statement: 'CALL planted()',
        observed: {},
        note: null,
        refusal: {
          spec_version: '1.0',
          refusal_id: '00000000-0000-4000-8000-00000000000f',
          observed_at: '2026-08-15T00:00:00Z',
          class: 'gate',
          sqlstate: '23514',
          constraint: 'planted_check_not_the_real_one',
          constraint_source: 'reported',
          message: 'PLANTED REFUSAL MESSAGE',
          subject_kind: 'permit',
          subject_id: '00000000-0000-4000-8000-000000000000',
          gate_epoch: 2,
          diagnosis: 'declarative',
          probe_calls: 0,
          mus: [
            {
              kind: 'obligation',
              obligation_id: '00000000-0000-4000-8000-000000000007',
              detail: 'PLANTED MUS DETAIL',
            },
          ],
          naa: {
            kind: 'dispose_obligations',
            obligation_ids: ['00000000-0000-4000-8000-000000000007'],
            cardinality: 1,
            description: 'PLANTED NAA DESCRIPTION',
          },
        },
      },
    ],
    persistence_check: {
      before: fingerprint,
      after: fingerprint,
      identical: true,
      self_persisted: false,
      self_evidence: {
        minted_disposition_id: null,
        minted_disposition_rows_after_rollback: 0,
        subject_row_counts_before: fingerprint.subject_row_counts,
        subject_row_counts_after: fingerprint.subject_row_counts,
        permit_row_identical: true,
      },
      concurrent_writes: null,
      tables: ['mainline.permit'],
      note: 'PLANTED NOTE, carried verbatim.',
    },
  };
}

// ── Transports ─────────────────────────────────────────────────────────────

function answering(payload: GateRunData): MainlineTransport {
  return {
    describe: () => ({
      mode: 'live',
      source: 'https://demo.example.test/api',
      bundleDigestPrefix: null,
      staged: false,
      stagedNote: null,
    }),
    exchange: <T,>(request: ResourceRequest): Promise<Exchange<T>> =>
      Promise.resolve({
        request: resolveRequest(request),
        envelope: {
          envelope_version: 1,
          resource: request.resource,
          schema_id: payload.schema_id,
          staged: false,
          provenance: [],
          data: payload as unknown as Record<string, unknown>,
        },
        data: payload as unknown as T,
        httpStatus: 200,
        clockSkewMs: null,
        mode: 'live',
      }),
  };
}

function failing(): MainlineTransport {
  return {
    describe: () => ({
      mode: 'replay',
      source: 'https://demo.example.test/bundle/',
      bundleDigestPrefix: 'a1b2c3d4',
      staged: true,
      stagedNote: 'staged capture',
    }),
    exchange: () =>
      Promise.reject(
        new TransportError(
          'missing_frame',
          'POST /v1/demo/gate-run demo_gate_run',
          'bundle "demo-cloud" has no frame for this request.',
        ),
      ),
  };
}

/**
 * The store is module-level — that is the whole point of it — so a case that left a run
 * published would hand the next case another case's evidence.
 *
 * Wrapped in `act` because this hook can run while a subscriber from the same case is
 * still mounted (Testing Library's own cleanup is a separate `afterEach` and the order
 * between them is not this file's to fix). Waking a `useSyncExternalStore` subscriber IS
 * a React update, so it is announced as one rather than left to print a warning.
 */
afterEach(() => {
  act(() => {
    resetLastGateRun();
  });
});

// ── 1. Before any press ────────────────────────────────────────────────────

describe('before any run has completed', () => {
  it('publishes null', () => {
    expect(lastGateRunSnapshot()).toBeNull();
    expect(renderHook(() => useLastGateRun()).result.current).toBeNull();
  });

  it('is still null while a run is IN FLIGHT', async () => {
    // The exchange never settles, so the driver sits in `loading`. A subscriber that saw
    // a value here would be rendering an attempt whose answer has not arrived.
    const pending: MainlineTransport = {
      describe: () => ({
        mode: 'live',
        source: 'https://demo.example.test/api',
        bundleDigestPrefix: null,
        staged: false,
        stagedNote: null,
      }),
      exchange: () => new Promise(() => undefined),
    };

    render(
      <GateTransportContext.Provider value={pending}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await userEvent.click(screen.getByTestId('demo-control-all'));
    await screen.findByTestId('demo-run-loading');

    expect(lastGateRunSnapshot()).toBeNull();
  });

  it('is still null after a TRANSPORT FAILURE', async () => {
    render(
      <GateTransportContext.Provider value={failing()}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await userEvent.click(screen.getByTestId('demo-control-all'));
    await screen.findByTestId('demo-run-failed');

    // A failure is not a refusal and is certainly not a completed run. Whatever the
    // subscriber renders for `null`, it must still be rendering it here.
    expect(lastGateRunSnapshot()).toBeNull();
  });
});

// ── 2. After a run completes ───────────────────────────────────────────────

describe('after a run completes', () => {
  it('publishes the payload the driver received, verbatim and whole', async () => {
    const run = plantedRun('published-run-1');

    render(
      <GateTransportContext.Provider value={answering(run)}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await userEvent.click(screen.getByTestId('demo-control-all'));
    await screen.findByTestId('gate-run-report');

    await waitFor(() => {
      expect(lastGateRunSnapshot()).not.toBeNull();
    });

    // Identity, not equality. A producer that reshaped, cloned or summarised the payload
    // on its way out would be deciding on the consumer's behalf which of the emitter's
    // statements survive — and the refusal object, with its `mus` and its `naa`, is
    // exactly what §0.4(i) says has to reach the screen below.
    expect(lastGateRunSnapshot()).toBe(run);
    expect(lastGateRunSnapshot()?.beats[1]?.refusal?.naa?.description).toBe(
      'PLANTED NAA DESCRIPTION',
    );
    expect(lastGateRunSnapshot()?.beats[1]?.refusal?.mus).toHaveLength(1);
  });

  it('replaces the previous run when a second press answers', async () => {
    const first = plantedRun('published-run-first');
    const second = plantedRun('published-run-second');

    const { rerender } = render(
      <GateTransportContext.Provider value={answering(first)}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await userEvent.click(screen.getByTestId('demo-control-all'));
    await waitFor(() => {
      expect(lastGateRunSnapshot()?.run_id).toBe('published-run-first');
    });

    rerender(
      <GateTransportContext.Provider value={answering(second)}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await userEvent.click(screen.getByTestId('demo-control-merge'));
    await waitFor(() => {
      expect(lastGateRunSnapshot()?.run_id).toBe('published-run-second');
    });
  });

  it('wakes a subscriber that was already mounted', async () => {
    const run = plantedRun('published-run-live');
    const hook = renderHook(() => useLastGateRun());
    expect(hook.result.current).toBeNull();

    render(
      <GateTransportContext.Provider value={answering(run)}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await userEvent.click(screen.getByTestId('demo-control-all'));

    await waitFor(() => {
      expect(hook.result.current).toBe(run);
    });
  });
});

// ── 3. The store, and the provider that may override it ────────────────────

describe('the channel itself', () => {
  it('forgets on reset, so no case can read another case’s run', () => {
    act(() => {
      publishLastGateRun(plantedRun('to-be-forgotten'));
    });
    expect(lastGateRunSnapshot()).not.toBeNull();
    act(() => {
      resetLastGateRun();
    });
    expect(lastGateRunSnapshot()).toBeNull();
  });

  it('lets a provider state the value explicitly, and null is a value', () => {
    const run = plantedRun('provided');
    act(() => {
      publishLastGateRun(plantedRun('in-the-store'));
    });

    const provided = renderHook(() => useLastGateRun(), {
      wrapper: ({ children }) => (
        <LastGateRunContext.Provider value={run}>{children}</LastGateRunContext.Provider>
      ),
    });
    expect(provided.result.current).toBe(run);

    // `null` from a provider means NO COMPLETED RUN and must beat a store that holds one.
    // If it did not, a composition could never render the un-pressed state deliberately.
    const nulled = renderHook(() => useLastGateRun(), {
      wrapper: ({ children }) => (
        <LastGateRunContext.Provider value={null}>{children}</LastGateRunContext.Provider>
      ),
    });
    expect(nulled.result.current).toBeNull();
  });

  it('falls back to the store when no provider is mounted', () => {
    // Which is the shipped arrangement: the driver and the gate surface are SIBLINGS in
    // src/app/App.tsx, so there is no shared ancestor to hold a provider and none is
    // added — hoisting one would put a gate concern into the console's frame.
    const run = plantedRun('from-the-store');
    act(() => {
      publishLastGateRun(run);
    });
    expect(renderHook(() => useLastGateRun()).result.current).toBe(run);
  });
});
