// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

import { describe, expect, it } from 'vitest';

import { DEFAULT_PATH, hrefFor, normalisePath, parseRoute } from '../../../src/app/router';
import { SURFACE_REGISTRY, buildRegistry } from '../../../src/app/surfaces';

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
  it('resolves an empty hash to the default surface', () => {
    const route = parseRoute('', '', ENTRIES);
    expect(route.path).toBe(DEFAULT_PATH);
    expect(route.surfaceId).toBe('overview');
  });

  /**
   * THE FIRST FIFTEEN SECONDS, AS AN ASSERTION.
   *
   * `DEFAULT_PATH` used to be `/gate`, and the bare URL therefore opened on
   * `NO SUBJECT ADDRESSED — address a permit by its identifier #/gate?permit=<uuid>`,
   * because `GateSurfaceRoot` renders ONE subject and does not choose one for a reader.
   * That rule is right and stays; what moved is the landing.
   *
   * Two properties, and the second is the one that could rot silently: the landing must
   * resolve to a surface the registry actually carries, and it must not be a surface whose
   * own doctrine is to refuse to pick a subject. A future worker who points `DEFAULT_PATH`
   * back at such a screen gets a red test rather than a judge meeting an empty headline.
   */
  it('lands on a screen that needs no identifier typed into the address bar', () => {
    const route = parseRoute('', '', ENTRIES);
    // Resolved against the LIVE glob, not against `buildRegistry({})`: the question is
    // whether a module is on disk behind the landing, and an empty module map answers
    // `declared-missing` for every surface in the console.
    const landing = SURFACE_REGISTRY.find((entry) => entry.id === route.surfaceId);

    expect(
      landing,
      `DEFAULT_PATH is ${DEFAULT_PATH}, which no registered surface claims. The bare URL ` +
        'would render "No surface at this address".',
    ).toBeDefined();

    expect(
      route.surfaceId,
      'the Gate renders the gate of ONE subject and does not choose one for you ' +
        '(GateSurfaceRoot). Landing there means a stranger opening the bare URL is asked ' +
        'to type a UUID they do not have. Point DEFAULT_PATH at a screen that builds its ' +
        'own addressed doors instead — do NOT give the Gate a default permit.',
    ).not.toBe('gate');

    // Not `declared-missing`: a landing that is a NOT-BUILT-YET card is a first screen
    // that names the milestone that owes it and shows a judge nothing else.
    expect(landing?.status, `${route.surfaceId}: the landing surface has no module`).toBe(
      'loadable',
    );
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
