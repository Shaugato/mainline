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

import { render, screen, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from '../../../src/app/App';
import { ErrorBoundary } from '../../../src/app/ErrorBoundary';
import { NotBuiltYet } from '../../../src/app/NotBuiltYet';
import { RefusalError } from '../../../src/app/refusal';
import { SurfaceHost } from '../../../src/app/SurfaceHost';
import { buildRegistry, type SurfaceEntry } from '../../../src/app/surfaces';

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
