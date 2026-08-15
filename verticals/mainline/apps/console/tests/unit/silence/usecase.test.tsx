// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * USE CASE 2, HALF TWO — the walkthrough and the bound, against the real replay transport.
 *
 * The sentence this file exists to protect is the receipt's own:
 *
 *   > PER proves exhaustion of the retrieval that ran, not of the corpus.
 *
 * Ruling R8 says a gloss goes BESIDE a verbatim value, never instead of it and never inside
 * the same element. So there are two assertions and they pull in opposite directions: the
 * emitter's statement must appear CHARACTER FOR CHARACTER as the payload holds it, and the
 * console's plain restatement must appear as a SEPARATE element that is not equal to it.
 * A future edit that "simplified" the bound into one friendly paragraph fails both.
 *
 * The second property is the one the empty-ledger case turns on: a walkthrough is allowed
 * to say *this run declined nothing*, and is not allowed to say *nothing was withheld*.
 * The first is a count; the second is a claim about a corpus nobody searched exhaustively.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { PER_BOUND_GLOSS } from '../../../src/features/silence/model';
import { SilenceSurfaceRoot } from '../../../src/features/silence/SilenceSurfaceRoot';
import { SilenceTransportContext } from '../../../src/features/silence/transport-context';
import type { MainlineTransport } from '../../../src/data/transport';

import { bundleFiles, bundleTransport, permitId, sourceSilence } from './_fixture';

const PERMIT = permitId();
const SILENCE = sourceSilence().data;

function mount(transport: MainlineTransport | null): ReactNode {
  window.location.hash = `#/silence?permit=${PERMIT}`;
  return (
    <HonestyProvider>
      <SilenceTransportContext.Provider value={transport}>
        <SilenceSurfaceRoot />
      </SilenceTransportContext.Provider>
    </HonestyProvider>
  );
}

/** The walkthrough is a lazy chunk, so every read of it waits for the import. */
async function walkthrough(): Promise<HTMLElement> {
  await waitFor(() => {
    expect(screen.getByTestId('silence-use-case')).toBeInTheDocument();
  });
  return screen.getByTestId('silence-use-case');
}

describe('the walkthrough reads the receipt rather than describing one', () => {
  it('prints theta, s and n from the payload', async () => {
    const receipt = SILENCE.receipt;
    if (receipt === null) throw new Error('the fixture has no receipt');

    render(mount(bundleTransport(bundleFiles())));
    await walkthrough();
    await waitFor(() => {
      expect(screen.getByTestId('use-case-receipt')).toBeInTheDocument();
    });

    expect(screen.getByTestId('use-case-theta')).toHaveTextContent(String(receipt.theta));
    expect(screen.getByTestId('use-case-s')).toHaveTextContent(String(receipt.s));
    expect(screen.getByTestId('use-case-n')).toHaveTextContent(String(receipt.n));
    expect(screen.getByTestId('use-case-row-count')).toHaveTextContent(
      String(SILENCE.entries.length),
    );
  });

  it('links to the other half of the case rather than describing it', async () => {
    render(mount(bundleTransport(bundleFiles())));
    await walkthrough();
    expect(screen.getByTestId('silence-use-case-link')).toHaveAttribute('href', '#/propagation');
  });
});

describe('the bound is quoted verbatim and glossed BESIDE, never instead', () => {
  it('renders the emitter’s sentence character for character', async () => {
    const receipt = SILENCE.receipt;
    if (receipt === null) throw new Error('the fixture has no receipt');

    render(mount(bundleTransport(bundleFiles())));
    await waitFor(() => {
      expect(screen.getByTestId('use-case-bound-statement')).toBeInTheDocument();
    });
    expect(screen.getByTestId('use-case-bound-statement').textContent).toBe(
      receipt.bound.statement,
    );
  });

  it('puts the plain restatement in a DIFFERENT element, and does not let it replace the sentence', async () => {
    const receipt = SILENCE.receipt;
    if (receipt === null) throw new Error('the fixture has no receipt');

    render(mount(bundleTransport(bundleFiles())));
    await waitFor(() => {
      expect(screen.getByTestId('use-case-bound-gloss')).toBeInTheDocument();
    });

    const gloss = screen.getByTestId('use-case-bound-gloss');
    const statement = screen.getByTestId('use-case-bound-statement');
    expect(gloss).not.toBe(statement);
    expect(gloss.contains(statement)).toBe(false);
    expect(statement.contains(gloss)).toBe(false);
    expect(gloss.textContent).toBe(PER_BOUND_GLOSS);

    // The gloss must not widen the claim. It says what is NOT proved, in as many words.
    expect(PER_BOUND_GLOSS).toContain('does not prove the search looked everywhere');
  });

  it('glosses the same sentence on the PER panel, in its own element', async () => {
    render(mount(bundleTransport(bundleFiles())));
    await waitFor(() => {
      expect(screen.getByTestId('per-bound-gloss')).toBeInTheDocument();
    });
    expect(screen.getByTestId('per-bound-gloss').textContent).toBe(PER_BOUND_GLOSS);
    expect(screen.getByTestId('per-bound-statement').textContent).not.toContain(PER_BOUND_GLOSS);
  });
});

describe('no payload, no numbers', () => {
  it('renders the walkthrough with a named absence and NO figures when there is no source', async () => {
    render(mount(null));
    const panel = await walkthrough();

    expect(panel).toHaveAttribute('data-payload', 'absent');
    expect(screen.getByTestId('silence-use-case-absent')).toHaveTextContent(
      'No transport was provided to this surface',
    );
    expect(screen.queryByTestId('silence-use-case-steps')).toBeNull();
    expect(screen.queryByTestId('use-case-row-count')).toBeNull();
    expect(screen.queryByTestId('use-case-bound-statement')).toBeNull();
  });
});

describe('the STAGED badge keeps its scope', () => {
  it('renders the badge, a plain sentence and the emitter’s note, none of them collapsed', async () => {
    render(mount(bundleTransport(bundleFiles())));
    await waitFor(() => {
      expect(screen.getByTestId('silence-staged')).toBeInTheDocument();
    });

    const staged = screen.getByTestId('silence-staged');
    expect(staged.closest('details')).toBeNull();
    const plain = screen.getByTestId('silence-staged-plain');
    expect(plain.closest('details')).toBeNull();
    // It sends the reader to the emitter's own note for the scope rather than deciding it.
    expect(plain).toHaveTextContent('own note is next, and it names exactly which value that is');
  });
});

describe('no query string, and no guess', () => {
  it('asks the kernel and, when it does not answer, names the absence without inventing a permit', async () => {
    window.location.hash = '#/silence';
    render(
      <HonestyProvider>
        <SilenceTransportContext.Provider value={bundleTransport(bundleFiles())}>
          <SilenceSurfaceRoot />
        </SilenceTransportContext.Provider>
      </HonestyProvider>,
    );

    const panel = await screen.findByTestId('silence-no-subject');
    expect(panel).toHaveTextContent('does not guess which permit you meant');
    expect(panel).toHaveTextContent('#/silence?permit=<uuid>');
    expect(panel.textContent ?? '').not.toContain(PERMIT);
    expect(screen.queryByTestId('silence-surface')).toBeNull();
  });
});
