// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE HONESTY STRIP'S THREE MEANINGLESS CELLS.
 *
 * `shell.test.tsx` already asserts that the strip is permanent, carries no control, and
 * starts by admitting it knows nothing. This file asserts the property that was measured
 * BROKEN on the live demo: three cells printed the word `unknown` (or `NOT VERIFIED`) in
 * situations where that word describes a lookup that failed, when in fact nothing had been
 * attempted and nothing was going to be.
 *
 * Every assertion here is written so that the comfortable failure is red:
 *
 *   • replacing a true absence with a soothing word is caught by the `unset` assertions;
 *   • turning a cell green to make the strip look finished is caught by the `data-tone`
 *     assertions, which forbid `ok` on every one of the three;
 *   • hiding the explanation in a `title` nobody hovers is caught by asserting the
 *     sentence is in the rendered TEXT.
 *
 * `HonestyChrome` is rendered directly under `HonestyProvider` rather than through `App`,
 * because the subject is the strip and the shell's registry is somebody else's file.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HonestyChrome } from '../../../src/app/HonestyChrome';
import { HonestyProvider } from '../../../src/app/HonestyProvider';
import type { HonestyPatch } from '../../../src/app/honesty';

function mount(initial: HonestyPatch): void {
  render(
    <HonestyProvider initial={initial}>
      <HonestyChrome />
    </HonestyProvider>,
  );
}

/** The cell wrapper carrying `data-tone` and `data-provenance` for a labelled value. */
function cell(label: string): HTMLElement {
  const value = screen.getByTestId(`chrome-${label}`);
  const wrapper = value.closest('[data-provenance]');
  if (wrapper === null) throw new Error(`chrome-${label} has no provenance wrapper`);
  return wrapper as HTMLElement;
}

describe('under LIVE, a cell with no meaning says so in words', () => {
  it('bundle: names that none was consulted, rather than one it failed to obtain', () => {
    mount({ transport: 'live' });
    expect(screen.getByTestId('chrome-bundle')).toHaveTextContent('none consulted');
    expect(screen.getByTestId('chrome-bundle').textContent).not.toBe('unknown');
    expect(screen.getByTestId('honesty-note-bundle').textContent ?? '').toContain(
      'there was no EvidenceBundle to open and none was consulted',
    );
    // Still an unfilled slot. The words changed; the marker did not.
    expect(cell('bundle')).toHaveAttribute('data-provenance', 'unset');
    expect(cell('bundle')).not.toHaveAttribute('data-tone', 'ok');
  });

  it('seal: says the bundle verifier did not run, and points at the surface that does', () => {
    mount({ transport: 'live' });
    const seal = screen.getByTestId('chrome-seal');
    expect(seal).toHaveTextContent('NOT RUN (no bundle in LIVE)');
    expect(seal.textContent ?? '').not.toMatch(/^NOT VERIFIED$/);
    const note = screen.getByTestId('honesty-note-seal').textContent ?? '';
    expect(note).toContain('nothing here has passed and nothing here has failed');
    expect(note).toContain('custody');
    expect(note).toContain('RFC 6962');
    // Amber, never green: a check nobody ran is not a check that passed.
    expect(cell('seal')).toHaveAttribute('data-tone', 'warn');
    expect(cell('seal')).toHaveAttribute('data-provenance', 'unset');
  });

  it('signature path: states the fact about this BUILD, in both transports', () => {
    for (const transport of ['live', 'replay'] as const) {
      const { unmount } = render(
        <HonestyProvider initial={{ transport, signaturePath: 'unknown' }}>
          <HonestyChrome />
        </HonestyProvider>,
      );
      expect(screen.getByTestId('chrome-signature-path')).toHaveTextContent('none compiled');
      const note = screen.getByTestId('honesty-note-signature-path').textContent ?? '';
      expect(note).toContain('No GT-15 attestation was present when this artefact was built');
      expect(note).toContain('NEITHER path');
      // The two names it must never print without an attestation behind them.
      expect(screen.getByTestId('chrome-signature-path').textContent).not.toBe('webauthn');
      expect(screen.getByTestId('chrome-signature-path').textContent).not.toBe('oidc_envelope');
      expect(cell('signature-path')).toHaveAttribute('data-provenance', 'unset');
      unmount();
    }
  });
});

describe('the transport marker names what establishes the transport', () => {
  /*
   * The strip shipped reading `transport LIVE · staged`, and `src/design/provenance.ts`
   * defines `staged` as "it exists only in this browser — nothing written, nothing refused,
   * nobody has signed anything". That is the marker for a number the console made up, and
   * LIVE is read off `transport.describe().mode` on the object holding the bytes. A false
   * label on a true value is the one line a sceptical reader checks first.
   */
  it('never marks a declared transport `staged`', () => {
    for (const transport of ['live', 'replay'] as const) {
      const { unmount } = render(
        <HonestyProvider initial={{ transport }}>
          <HonestyChrome />
        </HonestyProvider>,
      );
      expect(cell('transport')).toHaveAttribute('data-provenance', 'transport:describe');
      expect(cell('transport')).not.toHaveAttribute('data-provenance', 'staged');
      unmount();
    }
  });

  it('keeps `unset` for the one state nothing established', () => {
    mount({});
    expect(screen.getByTestId('chrome-transport')).toHaveTextContent('UNKNOWN');
    expect(cell('transport')).toHaveAttribute('data-provenance', 'unset');
  });

  it('changes the marker and nothing else — no cell goes green, REPLAY stays amber', () => {
    mount({ transport: 'live' });
    expect(screen.getByTestId('chrome-transport')).toHaveTextContent('LIVE');
    expect(cell('transport')).toHaveAttribute('data-tone', 'neutral');

    cleanup();
    mount({ transport: 'replay' });
    expect(screen.getByTestId('chrome-transport')).toHaveTextContent('REPLAY');
    expect(cell('transport')).toHaveAttribute('data-tone', 'warn');
  });
});

describe('a value somebody established still wins over every explanation', () => {
  it('prints a bundle digest recomputed under LIVE rather than the LIVE sentence', () => {
    mount({ transport: 'live', bundleDigestPrefix: '49b225260e1f' });
    expect(screen.getByTestId('chrome-bundle')).toHaveTextContent('49b225260e1f');
    expect(cell('bundle')).toHaveAttribute('data-provenance', 'recomputed');
    expect(screen.queryByTestId('honesty-note-bundle')).toBeNull();
  });

  it('prints the verifier verdict, not the LIVE sentence, once one exists', () => {
    mount({ transport: 'live', seal: 'failed', sealDetail: 'leaf 0 reconstructs 032980be…' });
    expect(screen.getByTestId('chrome-seal')).toHaveTextContent('VERIFICATION FAILED');
    expect(screen.queryByTestId('honesty-note-seal')).toBeNull();
    expect(screen.getByTestId('honesty-seal-detail')).toHaveTextContent('032980be');
  });

  it('prints the compiled capture path when an attestation selected one', () => {
    mount({ transport: 'live', signaturePath: 'webauthn' });
    expect(screen.getByTestId('chrome-signature-path')).toHaveTextContent('webauthn');
    expect(cell('signature-path')).toHaveAttribute('data-provenance', 'build');
    expect(screen.queryByTestId('honesty-note-signature-path')).toBeNull();
  });
});

describe('`unknown` survives where `unknown` is the true and complete answer', () => {
  it('keeps it for a transport that has not declared itself', () => {
    mount({});
    expect(screen.getByTestId('chrome-transport')).toHaveTextContent('UNKNOWN');
    expect(screen.getByTestId('chrome-bundle')).toHaveTextContent('unknown');
    expect(screen.getByTestId('chrome-seal')).toHaveTextContent('NOT VERIFIED');
    expect(screen.queryByTestId('honesty-note-bundle')).toBeNull();
    expect(screen.queryByTestId('honesty-note-seal')).toBeNull();
  });

  it('keeps it for corpus root and clock skew, which no code in this file fills', () => {
    mount({ transport: 'live' });
    expect(screen.getByTestId('chrome-corpus-root')).toHaveTextContent('unknown');
    expect(screen.getByTestId('chrome-clock-skew')).toHaveTextContent('unknown');
    expect(cell('corpus-root')).toHaveAttribute('data-provenance', 'unset');
    expect(cell('clock-skew')).toHaveAttribute('data-provenance', 'unset');
  });

  it('renders both the moment a surface establishes them', () => {
    mount({
      transport: 'live',
      corpusRoot: '49b22526023f4932c8dbd8cd2df1bc22e612cf8ddf40768d84b9e07d09498983',
      clockSkewMs: -1,
    });
    expect(screen.getByTestId('chrome-corpus-root')).toHaveTextContent('49b22526');
    expect(screen.getByTestId('chrome-clock-skew')).toHaveTextContent('−1 ms');
    expect(cell('corpus-root')).toHaveAttribute('data-provenance', 'db:column');
    expect(cell('clock-skew')).toHaveAttribute('data-provenance', 'recomputed');
  });
});

describe('the strip is still the strip', () => {
  it('carries no control of any kind, on any of the new paths', () => {
    mount({ transport: 'live' });
    const chrome = screen.getByTestId('honesty-chrome');
    expect(chrome.querySelectorAll('button')).toHaveLength(0);
    expect(chrome.querySelectorAll('input')).toHaveLength(0);
    expect(chrome.querySelectorAll('[hidden]')).toHaveLength(0);
  });

  it('never reaches the ok tone on a cell nobody filled', () => {
    mount({ transport: 'live' });
    const chrome = screen.getByTestId('honesty-chrome');
    for (const element of chrome.querySelectorAll('[data-provenance="unset"]')) {
      expect(element.getAttribute('data-tone')).not.toBe('ok');
    }
    expect(chrome.querySelectorAll('[data-provenance="unset"]').length).toBeGreaterThan(0);
  });
});
