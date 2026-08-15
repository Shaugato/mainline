// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The shell's honesty properties.
 *
 * Everything asserted here is a claim the console makes about ITSELF, which is the one
 * class of claim it is allowed to make (D5). The assertions are written so that the
 * comfortable failure — a generic "something went wrong", a green tick on an unfilled
 * slot, a promised screen that quietly disappears — is red.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import { type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { App, Shell } from '../../../src/app/App';
import { ErrorBoundary } from '../../../src/app/ErrorBoundary';
import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { NotBuiltYet } from '../../../src/app/NotBuiltYet';
import { RefusalError } from '../../../src/app/refusal';
import { SurfaceHost } from '../../../src/app/SurfaceHost';
import { buildRegistry, type SurfaceEntry } from '../../../src/app/surfaces';
import { resetDemoSubjects } from '../../../src/data/demo-subjects';
import {
  TransportError,
  type Exchange,
  type MainlineTransport,
  type TransportDescription,
} from '../../../src/data/transport';

const ENTRIES = buildRegistry({});
const gate = (): SurfaceEntry => {
  const found = ENTRIES.find((entry) => entry.id === 'gate');
  if (found === undefined) throw new Error('gate is not declared');
  return found;
};

function Boom({ error }: { readonly error: unknown }): ReactNode {
  throw error;
}

beforeEach(() => {
  window.location.hash = '';
  resetDemoSubjects();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

describe('the honesty chrome is permanent and starts by admitting it knows nothing', () => {
  it('renders on every screen with no dismiss affordance', () => {
    render(<App entries={ENTRIES} />);
    const chrome = screen.getByTestId('honesty-chrome');
    expect(chrome).toBeInTheDocument();
    // Non-dismissible (D16): the strip must contain no control at all.
    expect(chrome.querySelectorAll('button')).toHaveLength(0);
    expect(chrome.querySelectorAll('input')).toHaveLength(0);
    expect(chrome.querySelectorAll('[hidden]')).toHaveLength(0);
  });

  it('renders every unfilled slot as unknown, marked unset — never as a reassuring default', () => {
    render(<App entries={ENTRIES} />);
    expect(screen.getByTestId('chrome-transport')).toHaveTextContent('UNKNOWN');
    expect(screen.getByTestId('chrome-seal')).toHaveTextContent('NOT VERIFIED');
    expect(screen.getByTestId('chrome-bundle')).toHaveTextContent('unknown');
    expect(screen.getByTestId('chrome-clock-skew')).toHaveTextContent('unknown');

    const chrome = screen.getByTestId('honesty-chrome');
    expect(chrome.querySelectorAll('[data-provenance="unset"]').length).toBeGreaterThan(0);
  });

  it('survives a surface that throws — the must-not-claim control cannot be taken off screen', () => {
    const entry: SurfaceEntry = {
      ...gate(),
      status: 'loadable',
      load: () => Promise.resolve({ surface: { ...gate(), Component: () => <Boom error={new Error('surface exploded')} /> } }),
    };
    render(<App entries={[entry]} />);
    expect(screen.getByTestId('honesty-chrome')).toBeInTheDocument();
  });
});

describe('a promised surface that does not exist renders its own absence', () => {
  it('names the milestone and the owner that owe it', () => {
    // Addressed explicitly rather than relying on where a bare hash lands. This case is
    // about what a MODULE-LESS surface renders, and it used to reach the gate for an
    // unrelated reason: `DEFAULT_PATH` was `/gate`. It is `/overview` now (see
    // `src/app/router.ts` — the bare URL used to open on NO SUBJECT ADDRESSED), and a test
    // that changes its subject when the landing changes was never asserting the landing.
    window.location.hash = '#/gate';
    render(<App entries={ENTRIES} />);
    const card = screen.getByTestId('not-built-yet');
    expect(card).toHaveAttribute('data-surface', 'gate');
    expect(card).toHaveTextContent('NOT BUILT YET');
    expect(card).toHaveTextContent('K5');
    expect(card).toHaveTextContent('ui/gate-refusal-screen');
    expect(card).toHaveTextContent('src/features/gate/surface.tsx');
  });

  it('says so in the navigation before the click is spent', () => {
    render(<App entries={ENTRIES} />);
    const link = screen.getByRole('link', { name: /Gate — the refusal/ });
    expect(link).toHaveAttribute('data-status', 'declared-missing');
  });

  it('renders the promise, so the reader learns what is missing and not merely that it is', () => {
    render(<NotBuiltYet entry={gate()} reason="no module" />);
    expect(screen.getByTestId('not-built-yet')).toHaveTextContent(/minimal unsatisfiable subset/i);
  });
});

describe('an address that matches no surface', () => {
  it('shows the raw hash verbatim and lists what does exist', () => {
    window.location.hash = '#/fabrications';
    render(<App entries={ENTRIES} />);
    const failure = screen.getByRole('alert');
    expect(failure).toHaveAttribute('data-failure', 'no-such-surface');
    expect(failure).toHaveTextContent('#/fabrications');
    expect(failure).toHaveTextContent('/gate');
  });
});

describe('the error boundary never swallows a message', () => {
  it('renders a plain exception verbatim, and says the database did not refuse', () => {
    render(
      <ErrorBoundary boundary="test">
        <Boom error={new TypeError('cannot read properties of undefined (reading ‘mus’)')} />
      </ErrorBoundary>,
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveAttribute('data-failure', 'exception');
    expect(alert).toHaveTextContent('cannot read properties of undefined');
    expect(alert).toHaveTextContent('TypeError');
    expect(alert).toHaveTextContent(/not the database refusing/i);
    // The comfortable lie must not appear anywhere.
    expect(alert.textContent ?? '').not.toMatch(/something went wrong/i);
  });

  it('renders a refusal as a refusal: constraint, SQLSTATE and the message verbatim', () => {
    render(
      <ErrorBoundary boundary="test">
        <Boom
          error={
            new RefusalError({
              sqlstate: '23514',
              constraint: 'gate_closed_when_issued',
              message: 'MAINLINE: merge refused — undispositioned precursor in blame ancestry',
              subject_kind: 'permit',
              gate_epoch: 7,
            })
          }
        />
      </ErrorBoundary>,
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveAttribute('data-failure', 'refusal');
    expect(alert).toHaveTextContent('23514');
    expect(alert).toHaveTextContent('gate_closed_when_issued');
    expect(alert).toHaveTextContent(
      'MAINLINE: merge refused — undispositioned precursor in blame ancestry',
    );
    expect(alert).toHaveTextContent('7');
  });

  it('flags a SQLSTATE outside the closed REFUSE set as a defect, not an edge case', () => {
    render(
      <ErrorBoundary boundary="test">
        <Boom
          error={new RefusalError({
            sqlstate: '23502',
            constraint: 'blocking_check_severity_not_null',
            message: 'MAINLINE: null value in column "severity"',
          })}
        />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/defect, not an edge case/i);
  });

  it('marks a parsed constraint name as the weakened diagnosis it is', () => {
    render(
      <ErrorBoundary boundary="test">
        <Boom
          error={new RefusalError({
            sqlstate: '23514',
            constraint: 'gate_closed_when_issued',
            message: 'MAINLINE: merge refused',
            constraint_source: 'parsed',
          })}
        />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/WEAKENED diagnosis/i);
  });
});

describe('SurfaceHost — four outcomes, all of which paint', () => {
  it('renders the surface when the module is well formed', async () => {
    const entry: SurfaceEntry = {
      ...gate(),
      status: 'loadable',
      load: () =>
        Promise.resolve({
          surface: { ...gate(), Component: () => <p>the refusal bar</p> },
        }),
    };
    render(<SurfaceHost entry={entry} />);
    expect(await screen.findByText('the refusal bar')).toBeInTheDocument();
  });

  it('renders NOT-BUILT-YET carrying the import error verbatim when the chunk fails to load', async () => {
    const entry: SurfaceEntry = {
      ...gate(),
      status: 'loadable',
      load: () => Promise.reject(new Error('Failed to fetch dynamically imported module')),
    };
    render(<SurfaceHost entry={entry} />);
    const card = await screen.findByTestId('not-built-yet');
    expect(card).toHaveTextContent('Failed to fetch dynamically imported module');
    expect(card).toHaveTextContent('K5');
  });

  it('treats a module that lies about itself as a module that is not there', async () => {
    const entry: SurfaceEntry = {
      ...gate(),
      status: 'loadable',
      load: () =>
        Promise.resolve({
          surface: { ...gate(), id: 'disposition', Component: () => <p>wrong screen</p> },
        }),
    };
    render(<SurfaceHost entry={entry} />);
    const card = await screen.findByTestId('not-built-yet');
    expect(card).toHaveTextContent('disposition');
    expect(screen.queryByText('wrong screen')).toBeNull();
  });

  it('never renders a blank pane — a rejected loader still produces a card', async () => {
    const entry: SurfaceEntry = {
      ...gate(),
      status: 'loadable',
      // Rejecting with a non-Error is exactly the case under test: a bundler that throws
      // a string must still produce a card, not a blank pane.
      // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
      load: () => Promise.reject('a string, thrown by a bundler that forgot Error'),
    };
    render(<SurfaceHost entry={entry} />);
    await waitFor(() => {
      expect(screen.getByTestId('not-built-yet')).toHaveTextContent('a string, thrown by a bundler');
    });
  });
});

// ── The navigation's subject, and the detail mode ──────────────────────────

/**
 * THE TWO THINGS THE NAVIGATION MUST NOT DO.
 *
 * 1. **Guess.** Four states reach `Shell` — no transport, in flight, the route did not
 *    answer, the route answered — and only ONE of them is an answer. The other three must
 *    produce the bare `#/path` that shipped before this wave, because a link carrying an
 *    identifier nobody supplied is exactly how `BLK-07` reached the live URL.
 * 2. **Drop the reader out of FULL DETAIL.** The mode lives in the address (R6). A single
 *    nav item built without it is the same defect as holding the mode in storage: two
 *    readers on one link, seeing different screens, with nothing saying which they got.
 */

/** Opaque, and deliberately not uuid-shaped — nothing in the console parses one. */
const SEEDED = Object.freeze({
  permit_id: 'permit-named-by-the-kernel',
  cr_id: 'change-request-named-by-the-kernel',
  check_id: 'check-named-by-the-kernel',
  receipt_id: 'receipt-named-by-the-kernel',
  clause_uuid: 'clause-named-by-the-kernel',
  commit_id: 'commit-named-by-the-kernel',
  run_id: 'run-named-by-the-kernel',
  lesson_id: 'lesson-named-by-the-kernel',
  site_code: 'site-code-named-by-the-kernel',
  site_id: 'site-named-by-the-kernel',
  absent: [],
});

function describeLive(): TransportDescription {
  return { mode: 'live', source: 'scripted', bundleDigestPrefix: null, staged: false, stagedNote: null };
}

function transportAnswering(data: unknown): MainlineTransport {
  return {
    describe: describeLive,
    exchange: <T,>(): Promise<Exchange<T>> =>
      Promise.resolve({ data, httpStatus: 200, mode: 'live' } as unknown as Exchange<T>),
  };
}

/** An older kernel, or a replay bundle: the route is simply not there. */
function transportWithoutTheRoute(): MainlineTransport {
  return {
    describe: describeLive,
    exchange: <T,>(): Promise<Exchange<T>> =>
      Promise.reject(
        new TransportError(
          'status',
          'GET /v1/demo/subjects',
          'HTTP 404 — no resource is declared at GET /v1/demo/subjects',
        ),
      ),
  };
}

function mountShell(transport: MainlineTransport | null) {
  return render(
    <HonestyProvider>
      <Shell entries={ENTRIES} sourceChrome={null} transport={transport} />
    </HonestyProvider>,
  );
}

function hrefOf(name: RegExp): string {
  return screen.getByRole('link', { name }).getAttribute('href') ?? '';
}

describe('the navigation opens each surface on the subject the kernel named', () => {
  it('carries it under the parameter that surface reads', async () => {
    mountShell(transportAnswering(SEEDED));
    await waitFor(() => {
      expect(hrefOf(/Gate — the refusal/)).toBe('#/gate?permit=permit-named-by-the-kernel');
    });
    expect(hrefOf(/Custody/)).toBe('#/custody?site=site-code-named-by-the-kernel');
    expect(hrefOf(/Clause diff|Diff/)).toBe(
      '#/diff?clause=clause-named-by-the-kernel&commit=commit-named-by-the-kernel',
    );
  });

  it('gives no subject to a screen that reads none — no link carries a dead parameter', async () => {
    mountShell(transportAnswering(SEEDED));
    await waitFor(() => {
      expect(hrefOf(/Gate — the refusal/)).toContain('permit=');
    });
    expect(hrefOf(/Audit/)).toBe('#/audit');
    expect(hrefOf(/Evidence/)).toBe('#/evidence');
  });
});

describe('the navigation never guesses — three states, three bare paths', () => {
  it('carries no subject when no transport was composed', () => {
    mountShell(null);
    expect(hrefOf(/Gate — the refusal/)).toBe('#/gate');
    expect(hrefOf(/Custody/)).toBe('#/custody');
  });

  it('carries no subject while the read is in flight', () => {
    // Never settles: the in-flight state, held open for the length of the assertion.
    mountShell({ describe: describeLive, exchange: <T,>() => new Promise<Exchange<T>>(() => undefined) });
    expect(hrefOf(/Gate — the refusal/)).toBe('#/gate');
  });

  it('carries no subject when the route is not there, and says which nothing it is', async () => {
    // Opened in FULL DETAIL so that ONE render settles both halves of the claim: the links
    // stay bare, AND the shell names the failure rather than leaving a blank row.
    window.location.hash = '#/gate?detail=full';
    mountShell(transportWithoutTheRoute());

    await waitFor(() => {
      const notes = screen.getAllByTestId('nav-address');
      expect(notes.some((note) => (note.textContent ?? '').includes('subject index unavailable'))).toBe(true);
    });

    // The address is bare in every mode. That is the whole degradation requirement: this
    // wave lands useful against a deployment that was never redeployed.
    expect(hrefOf(/Gate — the refusal/)).toBe('#/gate?detail=full');
    expect(hrefOf(/Custody/)).toBe('#/custody?detail=full');
    expect(hrefOf(/Silence/)).toBe('#/silence?detail=full');
    expect(hrefOf(/Propagation/)).toBe('#/propagation?detail=full');
  });

  it('names the absence of a transport as the absence of a transport, not as a slow read', () => {
    window.location.hash = '#/gate?detail=full';
    mountShell(null);
    const notes = screen.getAllByTestId('nav-address').map((node) => node.textContent ?? '');
    expect(notes.some((text) => text.includes('no transport composed'))).toBe(true);
    // "nobody gave this console a source" and "the read did not answer" are different
    // findings; a shell that printed one for the other would be flattening them.
    expect(notes.some((text) => text.includes('subject index unavailable'))).toBe(false);
  });
});

describe('PLAIN and FULL DETAIL — one control, carried in the address', () => {
  it('arrives PLAIN, with no detail parameter written into any link', () => {
    const { container } = mountShell(null);
    expect(container.querySelector('[data-detail]')).toHaveAttribute('data-detail', 'plain');
    expect(screen.getByTestId('detail-plain')).toHaveAttribute('aria-current', 'true');
    expect(screen.getByTestId('detail-full')).not.toHaveAttribute('aria-current');
    // PLAIN is the default and therefore has no spelling: `#/gate` and `#/gate?detail=plain`
    // are the same address, so only the short one is ever emitted.
    expect(hrefOf(/Gate — the refusal/)).toBe('#/gate');
    expect(screen.queryAllByTestId('nav-address')).toHaveLength(0);
  });

  it('propagates ?detail=full through every navigation link', () => {
    window.location.hash = '#/audit?detail=full';
    mountShell(null);
    const links = screen.getAllByRole('link');
    const nav = links.filter((link) => (link.getAttribute('href') ?? '').startsWith('#/'));
    for (const link of nav) {
      const href = link.getAttribute('href') ?? '';
      // The two toggle links are the exception BY CONSTRUCTION: one of them is the way out.
      if (link.getAttribute('data-testid') === 'detail-plain') continue;
      expect(href, `${href} would drop the reader out of FULL DETAIL`).toContain('detail=full');
    }
  });

  it('shows the exact address of every link in FULL DETAIL, and nothing extra in PLAIN', async () => {
    window.location.hash = '#/gate?detail=full';
    mountShell(transportAnswering(SEEDED));
    await waitFor(() => {
      expect(screen.getAllByTestId('nav-address').length).toBe(ENTRIES.length);
    });
    const addresses = screen.getAllByTestId('nav-address').map((node) => node.textContent ?? '');
    expect(addresses.some((text) => text.includes('#/gate?permit=permit-named-by-the-kernel'))).toBe(
      true,
    );
    expect(addresses.some((text) => text.includes('named by GET /v1/demo/subjects'))).toBe(true);
  });

  it('keeps an identifier the reader typed when the mode is switched', () => {
    window.location.hash = '#/gate?permit=typed-by-the-reader';
    mountShell(null);
    expect(screen.getByTestId('detail-full')).toHaveAttribute(
      'href',
      '#/gate?permit=typed-by-the-reader&detail=full',
    );
  });

  it('is not inside the honesty chrome, which carries no controls at all (D16)', () => {
    render(<App entries={ENTRIES} />);
    const chrome = screen.getByTestId('honesty-chrome');
    expect(within(chrome).queryByTestId('detail-plain')).toBeNull();
    expect(within(chrome).queryByTestId('detail-full')).toBeNull();
    expect(chrome.querySelectorAll('a')).toHaveLength(0);
  });
});
