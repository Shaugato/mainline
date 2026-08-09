// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CINEMA BRIDGE — `docs/dimensionality-charter.md` §5.
 *
 * The walk is the one WebGL surface in this product that is screenshot-testable, and
 * that property rests entirely on two facts arriving correctly: `enabled` and `frame`.
 * This file asserts the grammar for both paths — the provider's published state and the
 * URL fallback — and asserts that they agree, because the second copy of a grammar is
 * only a fallback if it cannot drift.
 */

import { describe, expect, it } from 'vitest';

import {
  CINEMA_ABSENT,
  CINEMA_WINDOW_KEY,
  decideCinema,
  readCinema,
} from '../../../src/features/ancestry/render3d/cinema';

const url = (search: string, hash = ''): { search: string; hash: string; published: unknown } => ({
  search,
  hash,
  published: undefined,
});

describe('absent', () => {
  it('reports absent when nothing asks for a capture', () => {
    expect(decideCinema(url(''))).toEqual(CINEMA_ABSENT);
    expect(decideCinema(url('?render=3d', '#/ancestry'))).toEqual(CINEMA_ABSENT);
  });

  it('refuses a cinema flag that is not the contract’s flag', () => {
    expect(decideCinema(url('?cinema=yes')).enabled).toBe(false);
    expect(decideCinema(url('?cinema=0')).enabled).toBe(false);
  });

  it('reports absent with no window at all — a machine with no document takes no screenshot', () => {
    expect(readCinema(undefined)).toEqual(CINEMA_ABSENT);
  });
});

describe('the URL grammar', () => {
  it('reads ?cinema=1&seed=&t=&frame=', () => {
    const state = decideCinema(url('?cinema=1&seed=7&t=2026-08-04T00:00:00Z&frame=42'));
    expect(state).toEqual({
      enabled: true,
      frame: 42,
      seed: 7,
      tIso: '2026-08-04T00:00:00Z',
      source: 'url',
    });
  });

  it('defaults the frame to 0 when cinema mode is on and no frame is named', () => {
    expect(decideCinema(url('?cinema=1')).frame).toBe(0);
  });

  it('reads the same grammar out of the hash, because the console is hash-routed', () => {
    const state = decideCinema(url('', '#/ancestry?cinema=1&frame=9'));
    expect(state.enabled).toBe(true);
    expect(state.frame).toBe(9);
  });

  it('lets the hash query win, matching src/app/capability.ts’s precedence exactly', () => {
    const state = decideCinema(url('?cinema=1&frame=1', '#/ancestry?cinema=1&frame=99'));
    expect(state.frame).toBe(99);
  });

  it('refuses a negative or non-integer frame rather than guessing one', () => {
    expect(decideCinema(url('?cinema=1&frame=-3')).frame).toBe(0);
    expect(decideCinema(url('?cinema=1&frame=abc')).frame).toBe(0);
    expect(decideCinema(url('?cinema=1&frame=3.7')).frame).toBe(0);
  });

  it('reports a missing seed as null rather than as zero', () => {
    expect(decideCinema(url('?cinema=1')).seed).toBeNull();
    expect(decideCinema(url('?cinema=1&seed=0')).seed).toBe(0);
  });
});

describe('the provider path', () => {
  it('wins over the URL when the harness has published its state', () => {
    const state = decideCinema({
      search: '?cinema=1&frame=1',
      hash: '',
      published: { enabled: true, frame: 120, seed: 3, t: '2026-08-04T00:00:00Z' },
    });
    expect(state.source).toBe('provider');
    expect(state.frame).toBe(120);
  });

  it('falls through to the URL when the provider says cinema is off', () => {
    const state = decideCinema({
      search: '?cinema=1&frame=5',
      hash: '',
      published: { enabled: false },
    });
    expect(state.source).toBe('url');
    expect(state.frame).toBe(5);
  });

  it('never trusts the published shape — a malformed frame becomes 0, not NaN', () => {
    const state = decideCinema({
      search: '',
      hash: '',
      published: { enabled: true, frame: { evil: true }, seed: 'x' },
    });
    expect(state.frame).toBe(0);
    expect(state.seed).toBeNull();
  });

  it('accepts a string frame, because a query parameter arrives as one', () => {
    const state = decideCinema({ search: '', hash: '', published: { enabled: true, frame: '17' } });
    expect(state.frame).toBe(17);
  });

  it('produces the same state either way, which is what makes the fallback a fallback', () => {
    const viaUrl = decideCinema(url('?cinema=1&seed=7&t=2026-08-04T00:00:00Z&frame=42'));
    const viaProvider = decideCinema({
      search: '',
      hash: '',
      published: { enabled: true, frame: 42, seed: 7, t: '2026-08-04T00:00:00Z' },
    });
    expect({ ...viaProvider, source: 'url' }).toEqual(viaUrl);
  });
});

describe('the live read', () => {
  it('reads a real window object', () => {
    const fake = {
      location: { search: '?cinema=1&frame=8', hash: '' },
    } as unknown as Window;
    expect(readCinema(fake).frame).toBe(8);
  });

  it('prefers the published object on the window when the harness has installed one', () => {
    const fake = {
      location: { search: '', hash: '' },
      [CINEMA_WINDOW_KEY]: { enabled: true, frame: 4 },
    } as unknown as Window;
    const state = readCinema(fake);
    expect(state.source).toBe('provider');
    expect(state.frame).toBe(4);
  });
});
