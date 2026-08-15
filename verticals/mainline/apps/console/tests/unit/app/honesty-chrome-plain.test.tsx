// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE STRIP'S PLAIN SENTENCES, AND THE FOURTH NOTHING.
 *
 * `honesty-chrome.test.tsx` holds the three cells whose WORDS changed. This file holds the
 * two properties ruling R4 adds on top of them, and it is a separate file so that neither
 * set of assertions can be relaxed while editing the other.
 *
 *   1. **Every cell owes a plain sentence, and a `title=` is not one.** The sentence must
 *      be a real text node in the DOM, and the cell must be reachable by keyboard with
 *      that sentence as its accessible description. The comfortable failure — moving the
 *      explanation into a hover and calling the cell documented — is caught by asserting
 *      the sentence is in `textContent`, which a `title` attribute never reaches.
 *
 *   2. **The checkpoint signature check is a NAMED SKIP.** `.env.demo` ships
 *      `VITE_MAINLINE_LOG_VKEY=` empty, so the check that would say who signed the log's
 *      checkpoints cannot run. R4 requires the cell to say which nothing that is, in those
 *      words, in amber — never green, because nothing passed, and never red, because a
 *      checkpoint nobody could check has not been accused of anything.
 *
 * The cell is filled by a check that ACTUALLY RUNS: `resolveVerifierConfig()` reads the
 * anchor compiled into this artefact and the one this page's address carries. Under vitest
 * neither exists, which is the same state the demo build ships, so the SKIP asserted here
 * is the SKIP a judge sees.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HonestyChrome } from '../../../src/app/HonestyChrome';
import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { NO_ANCHOR } from '../../../src/verify/config';
import type { HonestyPatch } from '../../../src/app/honesty';

function mount(initial: HonestyPatch): void {
  render(
    <HonestyProvider initial={initial}>
      <HonestyChrome />
    </HonestyProvider>,
  );
}

/**
 * The plain sentences are a lazy chunk, so every read of them waits for the import.
 *
 * The FACTS are not: every assertion about a value, a tone or a provenance marker below is
 * made without waiting for anything, which is the property that keeps the deck an
 * explanation rather than a claim.
 */
async function plainDeck(): Promise<void> {
  await waitFor(() => {
    expect(screen.getByTestId('chrome-plain-transport')).toBeInTheDocument();
  });
}

/** The cell wrapper carrying `data-tone` and `data-provenance` for a labelled value. */
function cell(label: string): HTMLElement {
  const value = screen.getByTestId(`chrome-${label}`);
  const wrapper = value.closest('[data-provenance]');
  if (wrapper === null) throw new Error(`chrome-${label} has no provenance wrapper`);
  return wrapper as HTMLElement;
}

/** Every cell the strip renders, by the slug its test id uses. */
const CELLS = [
  'transport',
  'bundle',
  'seal',
  'checkpoint-signature',
  'corpus-root',
  'clock-skew',
  'signature-path',
  'render',
  'build',
] as const;

describe('every cell carries a plain sentence a keyboard can reach', () => {
  it('renders one for each cell, as TEXT rather than as a title attribute', async () => {
    mount({ transport: 'live' });
    await plainDeck();
    for (const slug of CELLS) {
      const plain = screen.getByTestId(`chrome-plain-${slug}`);
      const text = plain.textContent ?? '';
      // A sentence, not a label. Short enough to read, long enough to be one.
      expect(text.length, `${slug} has no plain sentence`).toBeGreaterThan(40);
      // In the DOM, which is what a `title` attribute never is.
      expect(cell(slug).textContent ?? '').toContain(text);
    }
  });

  it('makes each cell a keyboard stop that names itself and describes itself', async () => {
    mount({ transport: 'live' });
    await plainDeck();
    for (const slug of CELLS) {
      const target = cell(slug);
      expect(target, `${slug} is not reachable by keyboard`).toHaveAttribute('tabindex', '0');
      // Positive tabindex is forbidden by the a11y contract; zero keeps DOM order.
      expect(target.getAttribute('tabindex')).toBe('0');

      const describedBy = target.getAttribute('aria-describedby');
      expect(describedBy, `${slug} has no aria-describedby`).not.toBeNull();
      const described = document.getElementById(describedBy ?? '');
      expect(described, `${slug}'s description does not resolve`).not.toBeNull();
      expect(described).toBe(screen.getByTestId(`chrome-plain-${slug}`));

      const labelledBy = target.getAttribute('aria-labelledby');
      expect(document.getElementById(labelledBy ?? ''), `${slug} has no label`).not.toBeNull();
    }
  });

  it('adds no control while doing it', async () => {
    mount({ transport: 'live' });
    await plainDeck();
    const chrome = screen.getByTestId('honesty-chrome');
    expect(chrome.querySelectorAll('button')).toHaveLength(0);
    expect(chrome.querySelectorAll('input')).toHaveLength(0);
    expect(chrome.querySelectorAll('[hidden]')).toHaveLength(0);
    expect(chrome.querySelectorAll('details')).toHaveLength(0);
  });
});

describe('the checkpoint signature check names itself as a skip', () => {
  it('reads SKIPPED with the reason, in amber, with nothing established', () => {
    mount({ transport: 'live' });
    const value = screen.getByTestId('chrome-checkpoint-signature');
    expect(value).toHaveTextContent('SKIPPED — this build carries no log key');
    // Never green: nothing passed. Never red: nothing was accused.
    expect(cell('checkpoint-signature')).toHaveAttribute('data-tone', 'warn');
    expect(cell('checkpoint-signature')).not.toHaveAttribute('data-tone', 'ok');
    expect(cell('checkpoint-signature')).not.toHaveAttribute('data-tone', 'refuse');
    expect(cell('checkpoint-signature')).toHaveAttribute('data-provenance', 'unset');
  });

  it('carries the verifier’s own reason under the strip, not only in a hover', () => {
    mount({ transport: 'live' });
    const note = screen.getByTestId('honesty-note-checkpoint-signature').textContent ?? '';
    // Verbatim from `src/verify/config.ts` — the module that decides the anchor is the
    // module that gets to say why there is not one, and this console does not restate it.
    expect(note).toContain(NO_ANCHOR.sourceNote);
    expect(note).toContain('no checkpoint signature on this screen has been checked');
  });

  it('explains the amber in the plain sentence, once the deck lands', async () => {
    mount({ transport: 'live' });
    await plainDeck();
    expect(screen.getByTestId('chrome-plain-checkpoint-signature')).toHaveTextContent(
      'the question cannot be asked at all',
    );
  });

  it('says the same thing in REPLAY, because the anchor is a fact about the BUILD', () => {
    mount({ transport: 'replay' });
    expect(screen.getByTestId('chrome-checkpoint-signature')).toHaveTextContent(
      'SKIPPED — this build carries no log key',
    );
    expect(cell('checkpoint-signature')).toHaveAttribute('data-provenance', 'unset');
  });

  it('never claims a signature held — the words green would need are absent', () => {
    mount({ transport: 'live' });
    const text = cell('checkpoint-signature').textContent ?? '';
    expect(text).not.toContain('VERIFIED');
    expect(text).not.toContain('valid');
  });
});
