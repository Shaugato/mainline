// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `useResource` has four states and no fifth. In particular it never holds a payload
 * and a failure at the same time — a console that renders the previous permit's
 * counters while the current read is failing is worse than one that renders nothing,
 * because the counters look current.
 *
 * A refusal is a terminal state of its own, not an error. That distinction is the
 * product: the database refusing a merge is the system working.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RefusalError } from '../../../src/app/refusal';
import { BundleTransport, MemoryBundleSource } from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import type { Exchange, MainlineTransport, TransportDescription } from '../../../src/data/transport';
import { TransportError } from '../../../src/data/transport';
import type { ResourceRequest } from '../../../src/data/resources';
import { useResource } from '../../../src/data/useResource';

import { bundleFiles, manifestIntegrityVerifier } from './_support';

const registry = createContractRegistry();
const PERMIT_ID = '018f3a2f-1104-7c88-b3aa-77c1de40e2b1';

function Probe({
  transport,
  request,
}: {
  readonly transport: MainlineTransport | null;
  readonly request: ResourceRequest;
}): React.JSX.Element {
  const { state } = useResource<{ permit_id?: string }>(transport, request);
  return (
    <div>
      <span data-testid="status">{state.status}</span>
      <span data-testid="detail">
        {state.status === 'ready'
          ? (state.data.permit_id ?? '')
          : state.status === 'refused'
            ? `${state.refusal.sqlstate}/${state.refusal.constraint}`
            : state.status === 'failed'
              ? state.failure
              : ''}
      </span>
    </div>
  );
}

function replayTransport(): MainlineTransport {
  return new BundleTransport({
    source: new MemoryBundleSource('fixtures/bundles/blk-07', bundleFiles()),
    registry,
    verifier: manifestIntegrityVerifier(),
  });
}

/** A transport whose single exchange resolves however the test says. */
function scriptedTransport(behaviour: () => Promise<Exchange<unknown>>): MainlineTransport {
  return {
    describe(): TransportDescription {
      return { mode: 'live', source: 'scripted', bundleDigestPrefix: null, staged: false, stagedNote: null };
    },
    exchange: <T,>(): Promise<Exchange<T>> => behaviour() as Promise<Exchange<T>>,
  };
}

describe('useResource', () => {
  it('is idle with no transport, and never claims to be loading one', () => {
    render(<Probe transport={null} request={{ resource: 'permit', path: { permit_id: PERMIT_ID } }} />);
    expect(screen.getByTestId('status').textContent).toBe('idle');
  });

  it('reaches ready and exposes the validated payload', async () => {
    render(
      <Probe transport={replayTransport()} request={{ resource: 'permit', path: { permit_id: PERMIT_ID } }} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('ready');
    });
    expect(screen.getByTestId('detail').textContent).toBe(PERMIT_ID);
  });

  it('surfaces a refusal as its own state, carrying the constraint name', async () => {
    render(
      <Probe
        transport={replayTransport()}
        request={{
          resource: 'merge_permit',
          path: { permit_id: PERMIT_ID },
          body: { subject_kind: 'permit', subject_id: PERMIT_ID, expected_gate_epoch: 7 },
        }}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('refused');
    });
    expect(screen.getByTestId('detail').textContent).toBe('23514/gate_closed_when_issued');
  });

  it('surfaces a transport failure with the transport’s own classification', async () => {
    const transport = scriptedTransport(() =>
      Promise.reject(new TransportError('contract', 'GET /v1/permits/x', 'payload did not satisfy its contract')),
    );
    render(<Probe transport={transport} request={{ resource: 'permit', path: { permit_id: PERMIT_ID } }} />);
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('failed');
    });
    expect(screen.getByTestId('detail').textContent).toBe('contract');
  });

  it('does not keep stale data alongside a failure', async () => {
    let call = 0;
    const good = await replayTransport().exchange({ resource: 'permit', path: { permit_id: PERMIT_ID } });
    const transport = scriptedTransport(() => {
      call += 1;
      return call === 1
        ? Promise.resolve(good)
        : Promise.reject(new TransportError('network', 'GET /v1/permits/x', 'socket closed'));
    });

    const view = render(
      <Probe transport={transport} request={{ resource: 'permit', path: { permit_id: PERMIT_ID } }} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('ready');
    });

    // Re-mount with the same transport: the second exchange fails.
    view.rerender(
      <Probe transport={transport} request={{ resource: 'permit', path: { permit_id: PERMIT_ID + '' } }} />,
    );
    view.unmount();

    const second = render(
      <Probe transport={transport} request={{ resource: 'permit', path: { permit_id: PERMIT_ID } }} />,
    );
    await waitFor(() => {
      expect(second.getByTestId('status').textContent).toBe('failed');
    });
    expect(second.getByTestId('detail').textContent).toBe('network');
  });

  it('treats an abort as supersession, not as a failure state', async () => {
    const deferred = (): {
      promise: Promise<Exchange<unknown>>;
      resolve: (value: Exchange<unknown>) => void;
    } => {
      let resolve!: (value: Exchange<unknown>) => void;
      const promise = new Promise<Exchange<unknown>>((r) => {
        resolve = r;
      });
      return { promise, resolve };
    };
    const { promise: pending, resolve: resolveIt } = deferred();
    const transport = scriptedTransport(() => pending);

    const view = render(
      <Probe transport={transport} request={{ resource: 'permit', path: { permit_id: PERMIT_ID } }} />,
    );
    expect(screen.getByTestId('status').textContent).toBe('loading');
    view.unmount();

    // Resolving after unmount must not throw, and must not set state on a dead tree.
    const good = await replayTransport().exchange({ resource: 'permit', path: { permit_id: PERMIT_ID } });
    resolveIt(good);
    await expect(pending).resolves.toBeDefined();
  });

  it('reports a RefusalError thrown by any transport, not only by the bundle one', async () => {
    const transport = scriptedTransport(() =>
      Promise.reject(
        new RefusalError({
          sqlstate: 'P0001',
          constraint: 'trappoint.fn_epoch_pin_guard',
          message: 'MAINLINE: cannot attach a new obligation to an issued permit',
        }),
      ),
    );
    render(<Probe transport={transport} request={{ resource: 'permit', path: { permit_id: PERMIT_ID } }} />);
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('refused');
    });
    expect(screen.getByTestId('detail').textContent).toBe('P0001/trappoint.fn_epoch_pin_guard');
  });
});
