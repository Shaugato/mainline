// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PLAIN and FULL DETAIL — ruling R6's state, and the two properties that make it
 * reproducible.
 *
 *   1. **It is parsed from the address, from both query positions, with the hash
 *      winning** — the same merge `src/app/router.ts` performs and that
 *      `src/app/source-select.ts` and `src/features/evidence/source.ts` each restate. The
 *      four copies are held together by the four tests that each assert the hash-wins
 *      rule; this is the fourth.
 *
 *   2. **It touches no browser storage.** Asserted twice, on purpose: structurally, by
 *      reading the module's own bytes, and behaviourally, by making both storages throw on
 *      any access and then exercising every export. The structural check catches a future
 *      edit that only runs on a code path this test does not take; the behavioural check
 *      catches an indirect access the grep would miss.
 *
 * Why it matters is not hygiene. The console must run from `file://`, where the origin is
 * opaque and `localStorage` is either unavailable or shared with every other `file://`
 * document the reader has ever opened; and a screenshot must reproduce from its URL, which
 * is the entire argument this console makes about itself.
 */

import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_DETAIL_MODE,
  DETAIL_MODES,
  DETAIL_PARAM,
  detailModeFrom,
  detailModeFromAddress,
  hrefWithDetail,
  isDetailMode,
  paramsFromAddress,
  useDetailMode,
  useDetailModeFromAddress,
  useHrefWithDetail,
} from '../../../src/app/detail-mode';
import source from '../../../src/app/detail-mode.ts?raw';

describe('the mode', () => {
  it('is two values, PLAIN first, and PLAIN is what a reader gets on arrival', () => {
    expect([...DETAIL_MODES]).toEqual(['plain', 'full']);
    expect(DEFAULT_DETAIL_MODE).toBe('plain');
    expect(isDetailMode('plain')).toBe(true);
    expect(isDetailMode('full')).toBe(true);
    expect(isDetailMode('FULL')).toBe(false);
    expect(isDetailMode(undefined)).toBe(false);
  });
});

describe('parsing', () => {
  it('reads ?detail from the search position', () => {
    expect(detailModeFromAddress('?detail=full', '#/gate')).toBe('full');
  });

  it('reads ?detail from the hash position', () => {
    expect(detailModeFromAddress('', '#/gate?detail=full')).toBe('full');
  });

  it('lets the hash query WIN over the search query, in both directions', () => {
    // The hash is the more specific of the two, which is the rule router.ts documents.
    expect(detailModeFromAddress('?detail=plain', '#/gate?detail=full')).toBe('full');
    expect(detailModeFromAddress('?detail=full', '#/gate?detail=plain')).toBe('plain');
  });

  it('merges the two positions rather than choosing one of them', () => {
    const params = paramsFromAddress('?permit=abc&detail=plain', '#/gate?detail=full');
    expect(params.get('permit')).toBe('abc');
    expect(params.get('detail')).toBe('full');
  });

  it('tolerates the address in every shape a link can arrive in', () => {
    expect(detailModeFromAddress('detail=full', '/gate')).toBe('full');
    expect(detailModeFromAddress('', '')).toBe('plain');
    expect(detailModeFromAddress('', '#')).toBe('plain');
    expect(detailModeFromAddress('', '#/gate')).toBe('plain');
  });

  it('accepts a pasted ?detail=FULL, because that reader is asking for the same thing', () => {
    expect(detailModeFromAddress('', '#/gate?detail=FULL')).toBe('full');
    expect(detailModeFromAddress('', '#/gate?detail=%20full%20')).toBe('full');
  });

  it('falls back to PLAIN on an unrecognised value, and that direction is chosen', () => {
    // PLAIN never hides the refusal bar, the SQLSTATE, the constraint name, a provenance
    // chip, a STAGED badge, a SYNTHETIC marker or the honesty strip (R6), so falling back
    // to it can only collapse a disclosure a reader can open. Falling back the other way
    // would silently promote a typo into "show everything".
    expect(detailModeFromAddress('', '#/gate?detail=verbose')).toBe('plain');
    expect(detailModeFromAddress('', '#/gate?detail=')).toBe('plain');
    expect(detailModeFromAddress('', '#/gate?detail=1')).toBe('plain');
  });

  it('parses a merged URLSearchParams directly, so a caller with one need not re-merge', () => {
    expect(detailModeFrom(new URLSearchParams({ [DETAIL_PARAM]: 'full' }))).toBe('full');
    expect(detailModeFrom(new URLSearchParams())).toBe('plain');
  });
});

describe('hrefWithDetail', () => {
  it('carries FULL DETAIL across a nav click', () => {
    expect(hrefWithDetail('/custody', 'full')).toBe('#/custody?detail=full');
  });

  it('writes nothing at all in PLAIN, so the default reading has the shortest link', () => {
    expect(hrefWithDetail('/custody', 'plain')).toBe('#/custody');
    expect(hrefWithDetail('/custody')).toBe('#/custody');
  });

  it('removes a stale detail parameter rather than writing detail=plain', () => {
    // A bare `#/gate` and a `#/gate?detail=plain` must be the same address, or two links to
    // the same reading of the same screen compare unequal.
    expect(hrefWithDetail('/gate?detail=full', 'plain')).toBe('#/gate');
  });

  it('preserves every other parameter the path already carried', () => {
    expect(hrefWithDetail('/gate?permit=abc', 'full')).toBe('#/gate?permit=abc&detail=full');
    expect(hrefWithDetail('/gate?permit=abc&detail=full', 'plain')).toBe('#/gate?permit=abc');
  });

  it('normalises the path the way router.ts does — rooted, no trailing slash', () => {
    expect(hrefWithDetail('custody', 'full')).toBe('#/custody?detail=full');
    expect(hrefWithDetail('/custody/', 'full')).toBe('#/custody?detail=full');
    expect(hrefWithDetail('#/custody', 'full')).toBe('#/custody?detail=full');
    expect(hrefWithDetail('/', 'plain')).toBe('#/');
  });
});

describe('the context', () => {
  it('defaults to PLAIN outside any provider', () => {
    expect(renderHook(() => useDetailMode()).result.current).toBe('plain');
  });

  it('binds a link builder to the mode the subtree is being read in', () => {
    const { result } = renderHook(() => useHrefWithDetail());
    expect(result.current('/audit')).toBe('#/audit');
  });
});

describe('reading the live address', () => {
  it('re-reads when the hash changes, without a reload', () => {
    window.location.hash = '#/gate';
    const { result } = renderHook(() => useDetailModeFromAddress());
    expect(result.current).toBe('plain');

    act(() => {
      window.location.hash = '#/gate?detail=full';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(result.current).toBe('full');

    act(() => {
      window.location.hash = '#/gate';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(result.current).toBe('plain');
  });
});

describe('no browser storage, structurally', () => {
  it('names neither Storage in its executable source', () => {
    // Comments are stripped first, deliberately: the module's header ARGUES about
    // localStorage at length and must go on doing so, because the next person to reach for
    // it needs to find the reason there rather than rediscover it.
    const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    expect(code).not.toMatch(/\blocalStorage\b/);
    expect(code).not.toMatch(/\bsessionStorage\b/);
    expect(code).not.toMatch(/\bindexedDB\b/);
    expect(code).not.toContain('document.cookie');
  });

  it('says WHY, where the next reader will look', () => {
    expect(source).toContain('file://');
    expect(source).toContain('screenshot');
  });
});

describe('no browser storage, behaviourally', () => {
  it('parses, builds links and reads the address with both storages armed to throw', () => {
    const refuse = new Proxy(
      {},
      {
        get() {
          throw new Error('detail-mode reached browser storage. R6: the address is the state.');
        },
        set() {
          throw new Error('detail-mode wrote to browser storage. R6: the address is the state.');
        },
      },
    );
    vi.stubGlobal('localStorage', refuse);
    vi.stubGlobal('sessionStorage', refuse);

    window.location.hash = '#/gate?detail=full';
    expect(detailModeFromAddress('', '#/gate?detail=full')).toBe('full');
    expect(hrefWithDetail('/gate', 'full')).toBe('#/gate?detail=full');
    expect(renderHook(() => useDetailModeFromAddress()).result.current).toBe('full');
  });
});
