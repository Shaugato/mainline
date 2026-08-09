// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE WHOLE SCREEN, THROUGH THE REAL TRANSPORT.
 *
 * Every other file in this suite renders a component with a payload handed to it. This
 * one drives the surface the way the console drives it: a `BundleTransport` over the
 * staged EvidenceBundle, gated by a verifier that actually hashes the bytes, feeding
 * `useGateData`, feeding `GateScreen`.
 *
 * Three claims are only provable here.
 *
 * **1. The strings are not hardcoded anywhere in the chain.** `mutateFrame` rewrites the
 * constraint name inside the captured response body, re-seals the manifest, and the test
 * requires the rendered headline to follow. A component that hardcoded
 * `gate_closed_when_issued`, or a test that did, fails this immediately.
 *
 * **2. The merge is not attempted on page load.** The refusal bar reports that nothing
 * has been refused until the reader presses the control. A screen that POSTed a merge
 * because a link was opened would, on the day the gate is legitimately open, issue a
 * permit nobody asked for.
 *
 * **3. A tampered bundle renders nothing at all.** Change one byte without re-sealing and
 * the verifier refuses; the surface shows a read failure and no claims. *The console
 * cannot show you a screen we made up* is a mechanism, and this is where it is exercised.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { GateTransportContext } from '../../../src/features/gate/transport-context';
import { GateSurfaceRoot } from '../../../src/features/gate/GateSurfaceRoot';
import { surface } from '../../../src/features/gate/surface';
import type { InvokeResult } from '../../../src/data/types.generated';
import {
  bundleFiles,
  bundleTransport,
  frameEnvelope,
  mergeFramePath,
  mutateFrame,
  permitId,
} from './_support';

interface InvokeEnvelope {
  readonly data: InvokeResult;
}

const files = bundleFiles();
const subject = permitId();
const framePath = mergeFramePath();

/** The values the BUNDLE carries. Nothing in this file retypes them. */
function bundleRefusal(): NonNullable<InvokeResult['refusal']> {
  const envelope = frameEnvelope<InvokeEnvelope>(files, framePath);
  const refusal = envelope.data.refusal;
  if (refusal === null) throw new Error('the staged merge frame carries no refusal');
  return refusal;
}

function mount(source: ReadonlyMap<string, Uint8Array> = files): void {
  render(
    <GateTransportContext.Provider value={bundleTransport(source)}>
      <GateSurfaceRoot />
    </GateTransportContext.Provider>,
  );
}

beforeEach(() => {
  window.location.hash = `#/gate?permit=${subject}`;
});

afterEach(() => {
  window.location.hash = '';
});

describe('the surface registers itself honestly', () => {
  it('declares the id its directory requires, in the EVIDENCE register', () => {
    expect(surface.id).toBe('gate');
    expect(surface.path).toBe('/gate');
    expect(surface.register).toBe('evidence');
    expect(typeof surface.Component).toBe('function');
  });
});

describe('addressing a subject', () => {
  it('refuses to guess a permit when the URL names none', async () => {
    window.location.hash = '#/gate';
    mount();
    expect((await screen.findByTestId('gate-no-subject')).textContent).toContain(
      'does not choose one for you',
    );
  });

  it('renders NO SOURCE, not an empty screen, when no transport was provided', async () => {
    render(
      <GateTransportContext.Provider value={null}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );
    const panel = await screen.findByTestId('gate-no-source');
    expect(panel.textContent).toContain('nothing has been read');
    expect(panel.textContent).toContain('bundle player without a verifier is a mock');
  });
});

describe('before anything has been attempted', () => {
  it('reads the permit and shows its projected counters', async () => {
    mount();
    await waitFor(() => {
      expect(screen.getByTestId('permit-state')).toBeInTheDocument();
    });
    expect(screen.getByTestId('weld')).toBeInTheDocument();
    expect(screen.getByTestId('counter-open_blocking')).toBeInTheDocument();
  });

  it('says the database has refused nothing — and does not POST a merge', async () => {
    mount();
    const bar = await screen.findByTestId('refusal-bar');
    await waitFor(() => {
      expect(screen.getByTestId('permit-state')).toBeInTheDocument();
    });

    expect(bar.dataset.state).toBe('none');
    expect(bar.textContent).toContain('nothing has been refused');
    expect(screen.getByTestId('reason-set-absent').textContent).toContain('no reason set');
    // The attempt control is present and has not been used.
    expect(screen.getByTestId('attempt-merge')).toBeEnabled();
  });

  it('shows the precursors and the clause behind the first open check', async () => {
    mount();
    await waitFor(() => {
      expect(screen.getAllByTestId('precursor').length).toBeGreaterThan(0);
    });
    await waitFor(() => {
      expect(screen.getByTestId('canon-current')).toBeInTheDocument();
    });
    expect(screen.getByTestId('clause-diff').textContent).toContain(
      'not a claim that this clause is the reason',
    );
  });
});

describe('the attempt, and the refusal it produces', () => {
  it('renders the constraint name and the SQLSTATE the BUNDLE carries', async () => {
    const expected = bundleRefusal();
    mount();

    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);

    const name = await screen.findByTestId('refusal-constraint');
    expect(name.dataset.constraint).toBe(expected.constraint);
    expect(screen.getByTestId('refusal-bar').dataset.sqlstate).toBe(expected.sqlstate);
    expect(screen.getByTestId('refusal-message').textContent).toBe(expected.message);
    expect(screen.getByTestId('refusal-gate-epoch').textContent).toBe(String(expected.gate_epoch));
  });

  it('decomposes the refusal into the reason set the payload carries', async () => {
    const expected = bundleRefusal();
    mount();
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);

    await screen.findByTestId('mus-list');
    expect(screen.getAllByTestId('mus-atom')).toHaveLength(expected.mus.length);
    if (expected.naa !== null) {
      expect(screen.getByTestId('naa-kind').textContent).toBe(expected.naa.kind);
    }
  });

  it('marks the constraint the refusal named on the weld diagram', async () => {
    const expected = bundleRefusal();
    mount();
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);

    await screen.findByTestId('refusal-constraint');
    const row = screen.getByTestId(`weld-row-${expected.constraint}`);
    expect(row.dataset.blamed).toBe('true');
  });

  it('offers no automatic retry — the control disables after one attempt', async () => {
    mount();
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);
    await screen.findByTestId('refusal-constraint');
    expect(screen.getByTestId('attempt-merge')).toBeDisabled();
  });
});

describe('nothing is hardcoded — mutate the fixture and the screen must follow', () => {
  it('renders whatever constraint name the re-sealed bundle carries', async () => {
    const original = bundleRefusal();
    const replacement = 'reading_floor_when_issued';
    expect(replacement).not.toBe(original.constraint);

    const mutated = await mutateFrame(files, framePath, (envelope) => {
      const data = envelope.data as { refusal: Record<string, unknown> };
      data.refusal.constraint = replacement;
    });

    mount(mutated);
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);

    const name = await screen.findByTestId('refusal-constraint');
    expect(name.dataset.constraint).toBe(replacement);
    expect(name.textContent).not.toContain(original.constraint);
    // …and the weld diagram follows it to the row that now carries the blame.
    expect(screen.getByTestId(`weld-row-${replacement}`).dataset.blamed).toBe('true');
  });

  it('renders whatever SQLSTATE the re-sealed bundle carries', async () => {
    const original = bundleRefusal();
    const replacement = original.sqlstate === '23503' ? '23505' : '23503';

    const mutated = await mutateFrame(files, framePath, (envelope) => {
      const data = envelope.data as { refusal: Record<string, unknown> };
      data.refusal.sqlstate = replacement;
    });

    mount(mutated);
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);

    await screen.findByTestId('refusal-constraint');
    expect(screen.getByTestId('refusal-bar').dataset.sqlstate).toBe(replacement);
  });

  it('announces a parsed constraint source when the bundle declares one', async () => {
    const mutated = await mutateFrame(files, framePath, (envelope) => {
      const data = envelope.data as { refusal: Record<string, unknown> };
      data.refusal.constraint_source = 'parsed';
    });

    mount(mutated);
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);

    expect((await screen.findByTestId('refusal-parsed')).textContent).toContain(
      'WEAKENED DIAGNOSIS',
    );
  });

  it('renders the honest not-computable state when the bundle carries no alternative', async () => {
    const mutated = await mutateFrame(files, framePath, (envelope) => {
      const data = envelope.data as { refusal: Record<string, unknown> };
      data.refusal.naa = null;
      data.refusal.naa_reason = 'no_legal_verdict_exists';
    });

    mount(mutated);
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await userEvent.click(button);

    const absent = await screen.findByTestId('naa-absent');
    expect(absent.dataset.naaReason).toBe('no_legal_verdict_exists');
    expect(absent.textContent).toContain('no way to sign this away');
    expect(screen.queryByTestId('naa')).toBeNull();
  });
});

describe('a tampered bundle renders no claims at all', () => {
  it('refuses to serve a frame whose bytes disagree with the manifest', async () => {
    // One byte changed, manifest NOT re-sealed. This is what a swapped fixture looks
    // like, and the transport's verifier gate is the only thing between it and a screen.
    const tampered = new Map(files);
    const original = tampered.get(framePath);
    if (original === undefined) throw new Error('no merge frame in the fixture');
    tampered.set(framePath, new TextEncoder().encode(new TextDecoder().decode(original) + ' '));

    mount(tampered);
    const failure = await screen.findByTestId('read-failed-permit');
    expect(failure.textContent).toContain('tampered');
    expect(screen.queryByTestId('permit-state')).toBeNull();
  });
});
