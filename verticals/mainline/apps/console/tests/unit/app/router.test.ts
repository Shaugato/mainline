// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

import { describe, expect, it } from 'vitest';

import { DEFAULT_PATH, hrefFor, normalisePath, parseRoute } from '../../../src/app/router';
import { buildRegistry } from '../../../src/app/surfaces';

const ENTRIES = buildRegistry({});

describe('normalisePath', () => {
  it('roots a bare segment and drops a trailing slash', () => {
    expect(normalisePath('gate')).toBe('/gate');
    expect(normalisePath('/gate/')).toBe('/gate');
    expect(normalisePath('/')).toBe('/');
  });
});

describe('hrefFor', () => {
  it('produces a hash link, so deep links survive a static host and file://', () => {
    expect(hrefFor('/gate')).toBe('#/gate');
    expect(hrefFor('ancestry')).toBe('#/ancestry');
  });
});

describe('parseRoute', () => {
  it('resolves an empty hash to the default surface — the refusal', () => {
    const route = parseRoute('', '', ENTRIES);
    expect(route.path).toBe(DEFAULT_PATH);
    expect(route.surfaceId).toBe('gate');
  });

  it('resolves a surface path', () => {
    expect(parseRoute('#/ancestry', '', ENTRIES).surfaceId).toBe('ancestry');
    expect(parseRoute('#/silence', '', ENTRIES).surfaceId).toBe('silence');
  });

  it('reports no surface rather than guessing at an unknown path', () => {
    const route = parseRoute('#/fabrications', '', ENTRIES);
    expect(route.surfaceId).toBeNull();
    expect(route.path).toBe('/fabrications');
    expect(route.raw).toBe('#/fabrications');
  });

  it('merges both query positions, with the hash query winning', () => {
    const route = parseRoute('#/gate?seed=7&cinema=1', '?cinema=0&t=1000', ENTRIES);
    expect(route.params.get('cinema')).toBe('1');
    expect(route.params.get('seed')).toBe('7');
    expect(route.params.get('t')).toBe('1000');
    expect(route.path).toBe('/gate');
  });

  it('keeps the raw hash verbatim so an unmatched address can be shown as typed', () => {
    expect(parseRoute('#/Gate?x=1', '', ENTRIES).raw).toBe('#/Gate?x=1');
  });
});
