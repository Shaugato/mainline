// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * USE CASE 2, HALF ONE — the walkthrough, against the real replay transport.
 *
 * Ruling R9 makes the two use cases a shipped feature rather than a slide, so they are
 * tested like one. Every number this file expects is COUNTED OUT OF THE FIXTURE at run
 * time; a test that hardcoded "two sites" would stay green against a walkthrough that
 * printed two of something else.
 *
 * Three properties, and each one is written so that the comfortable failure is red:
 *
 *   1. the walkthrough's figures come from the payload — asserted by comparing them to the
 *      fixture's own array lengths, not to literals;
 *   2. **it prints no figures when there is no payload** — asserted by requiring the
 *      absence branch and requiring the step list to be gone, because a walkthrough that
 *      kept a stale count next to a failure panel would be the one screen in this console
 *      that made something up;
 *   3. the STAGED badge and its plain sentence are in the open flow above it. R6 forbids
 *      PLAIN hiding a STAGED badge and this is the surface the ruling was written for:
 *      `reads.py::read_propagation` stages this resource in full.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { PropagationSurfaceRoot } from '../../../src/features/propagation/PropagationSurfaceRoot';
import { PropagationTransportContext } from '../../../src/features/propagation/transport-context';
import type { MainlineTransport } from '../../../src/data/transport';

import { bundleFiles, bundleTransport, lessonId, sourcePropagation } from './_fixture';

const LESSON = lessonId();
const PAYLOAD = sourcePropagation();

function mount(transport: MainlineTransport | null): ReactNode {
  window.location.hash = `#/propagation?lesson=${LESSON}`;
  return (
    <HonestyProvider>
      <PropagationTransportContext.Provider value={transport}>
        <PropagationSurfaceRoot />
      </PropagationTransportContext.Provider>
    </HonestyProvider>
  );
}

/** The walkthrough is a lazy chunk, so every read of it waits for the import. */
async function walkthrough(): Promise<HTMLElement> {
  await waitFor(() => {
    expect(screen.getByTestId('propagation-use-case')).toBeInTheDocument();
  });
  return screen.getByTestId('propagation-use-case');
}

describe('the walkthrough counts what is on the wire', () => {
  it('names the number of sites and the number that answered, from the payload', async () => {
    render(mount(bundleTransport(bundleFiles())));
    await walkthrough();
    await waitFor(() => {
      expect(screen.getByTestId('propagation-use-case-steps')).toBeInTheDocument();
    });

    // Re-queried, never reused: the walkthrough is re-mounted when the payload lands, so a
    // reference taken while the read was in flight is a detached node.
    expect(screen.getByTestId('propagation-use-case')).toHaveAttribute('data-view', 'present');
    expect(screen.getByTestId('use-case-site-count')).toHaveTextContent(
      String(PAYLOAD.data.propagations.length),
    );
    // "answered" is every row whose state is no longer the state it was proposed in.
    const answered = PAYLOAD.data.propagations.filter((row) => row.state !== 'proposed').length;
    expect(screen.getByTestId('use-case-answered-count')).toHaveTextContent(String(answered));
  });

  it('states the open-conflict count, or states that there is none', async () => {
    render(mount(bundleTransport(bundleFiles())));
    await walkthrough();
    const open = PAYLOAD.data.conflicts.length;
    if (open === 0) {
      expect(screen.queryByTestId('use-case-conflict-count')).toBeNull();
    } else {
      await waitFor(() => {
        expect(screen.getByTestId('use-case-conflict-count')).toHaveTextContent(String(open));
      });
    }
  });

  it('links to the other half of the case rather than describing it', async () => {
    render(mount(bundleTransport(bundleFiles())));
    await walkthrough();
    const link = screen.getByTestId('propagation-use-case-link');
    expect(link).toHaveAttribute('href', '#/silence');
  });
});

describe('the STAGED badge is above the walkthrough and is not collapsed', () => {
  it('renders the badge, a plain sentence, and the emitter’s note, all in the open flow', async () => {
    render(mount(bundleTransport(bundleFiles())));
    await waitFor(() => {
      expect(screen.getByTestId('propagation-staged')).toBeInTheDocument();
    });
    await walkthrough();

    const staged = screen.getByTestId('propagation-staged');
    expect(staged).toBeInTheDocument();
    // Not inside a <details>: R6 forbids PLAIN collapsing a STAGED badge.
    expect(staged.closest('details')).toBeNull();

    const plain = screen.getByTestId('propagation-staged-plain');
    expect(plain).toHaveTextContent('these rows come from a fixture, not from the live database');
    expect(plain.closest('details')).toBeNull();

    // And the walkthrough repeats the fact rather than letting a reader meet only a badge.
    expect(screen.getByTestId('propagation-use-case-staged')).toBeInTheDocument();
  });
});

describe('no payload, no numbers', () => {
  it('renders the walkthrough with a named absence and NO figures when there is no source', async () => {
    render(mount(null));
    const panel = await walkthrough();

    expect(panel).toHaveAttribute('data-view', 'absent');
    expect(screen.getByTestId('propagation-use-case-absent')).toHaveTextContent(
      'No transport was provided to this surface',
    );
    // The comfortable failure — a walkthrough that kept its counts beside a NO SOURCE
    // panel — is exactly what these three lines are here to make red.
    expect(screen.queryByTestId('propagation-use-case-steps')).toBeNull();
    expect(screen.queryByTestId('use-case-site-count')).toBeNull();
    expect(screen.queryByTestId('use-case-conflict-count')).toBeNull();
  });
});

describe('no query string, and no guess', () => {
  it('asks the kernel and, when it does not answer, names the absence without inventing a lesson', async () => {
    // No `?lesson=`. The fixture bundle carries no frame for `GET /v1/demo/subjects`, so the
    // index read fails — which is the state a deployment that has not been redeployed is in,
    // and the state this surface must survive without reaching for a literal.
    window.location.hash = '#/propagation';
    render(
      <HonestyProvider>
        <PropagationTransportContext.Provider value={bundleTransport(bundleFiles())}>
          <PropagationSurfaceRoot />
        </PropagationTransportContext.Provider>
      </HonestyProvider>,
    );

    const panel = await screen.findByTestId('propagation-no-subject');
    expect(panel).toHaveTextContent('does not guess which lesson you meant');
    expect(panel).toHaveTextContent('#/propagation?lesson=<uuid>');
    // No identifier anywhere on screen but the one in the example, which is a placeholder.
    expect(panel.textContent ?? '').not.toContain(LESSON);
    expect(screen.queryByTestId('propagation-surface')).toBeNull();
  });
});
