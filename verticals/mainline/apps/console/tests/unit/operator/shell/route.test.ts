// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The operator router: two modules, a hash, and a registry the screens fill in themselves.
 *
 * The three things worth a test are the three that fail quietly:
 *
 *   • a hand-typed or truncated hash must land somewhere rather than render a blank page;
 *   • two screens claiming one route must be a loud error, not a race the module evaluation
 *     order decides; and
 *   • a route with no screen must be distinguishable from a screen with no data, which is why
 *     `screenFor()` returns `null` rather than a no-op mount.
 */

import { afterEach, describe, expect, it } from 'vitest';

import {
  DEFAULT_ROUTE,
  MODULES,
  OPERATOR_ROUTES,
  clearScreens,
  currentRoute,
  hashFor,
  isOperatorRoute,
  moduleFor,
  onRouteChange,
  registerScreen,
  registeredRoutes,
  routeFromHash,
  screenFor,
} from '../../../../src/operator/route';

afterEach(() => {
  clearScreens();
});

describe('the module table', () => {
  it('describes every route exactly once, with a hash and a name', () => {
    expect(MODULES.map((entry) => entry.route)).toEqual([...OPERATOR_ROUTES]);
    for (const route of OPERATOR_ROUTES) {
      const descriptor = moduleFor(route);
      expect(descriptor.hash).toBe(`#/${route}`);
      expect(descriptor.name.length).toBeGreaterThan(4);
      expect(hashFor(route)).toBe(descriptor.hash);
    }
  });

  it('gives management of change no left-rail register, rather than inventing one', () => {
    // The four registers a control-of-work rail lists do not include change management.
    // Filing it under one of them would be a small lie about how these systems are organised.
    expect(moduleFor('permit').railSection).toBe('Permits');
    expect(moduleFor('change').railSection).toBeNull();
  });

  it('recognises a route and refuses one it does not have', () => {
    expect(isOperatorRoute('permit')).toBe(true);
    expect(isOperatorRoute('change')).toBe(true);
    expect(isOperatorRoute('isolations')).toBe(false);
    expect(isOperatorRoute(undefined)).toBe(false);
  });
});

describe('reading a route out of a hash', () => {
  it('reads the two it knows', () => {
    expect(routeFromHash('#/permit')).toBe('permit');
    expect(routeFromHash('#/change')).toBe('change');
  });

  it('defaults rather than blanking, for every shape a person can type', () => {
    // A router that throws or renders nothing on a mistyped character shows an empty page to
    // somebody who is one keystroke from the screen they wanted.
    for (const hash of ['', '#', '#/', '/', '#/nope', '#permit', '#/PERMIT', '#//', '#/?x=1']) {
      expect(routeFromHash(hash), `hash ${JSON.stringify(hash)}`).toBe(DEFAULT_ROUTE);
    }
    expect(DEFAULT_ROUTE).toBe('permit');
  });

  it('ignores a query on the hash', () => {
    expect(routeFromHash('#/change?raw=1')).toBe('change');
    expect(routeFromHash('#/permit&x')).toBe('permit');
  });

  it('reads the route out of a window', () => {
    expect(currentRoute({ location: { hash: '#/change' } as Location })).toBe('change');
    expect(currentRoute({ location: { hash: '' } as Location })).toBe(DEFAULT_ROUTE);
  });
});

describe('the screen registry', () => {
  it('starts empty, so an unbuilt module is distinguishable from an empty one', () => {
    expect(screenFor('permit')).toBeNull();
    expect(registeredRoutes()).toEqual([]);
  });

  it('hands back the mount that was registered', () => {
    // `undefined`, not `void`: a screen with nothing to tear down says so explicitly, so the
    // shell never tries to call a value that was never a teardown.
    const mount = (): undefined => undefined;
    registerScreen('permit', mount);
    expect(screenFor('permit')).toBe(mount);
    expect(screenFor('change')).toBeNull();
    expect(registeredRoutes()).toEqual(['permit']);
  });

  it('refuses a second registration for the same route', () => {
    registerScreen('change', () => undefined);
    expect(() => {
      registerScreen('change', () => undefined);
    }).toThrow(/already registered/);
  });
});

describe('route changes', () => {
  it('reports the new route on hashchange and stops when unsubscribed', () => {
    const seen: string[] = [];
    const stop = onRouteChange((route) => seen.push(route));

    window.location.hash = '#/change';
    window.dispatchEvent(new Event('hashchange'));
    expect(seen).toEqual(['change']);

    stop();
    window.location.hash = '#/permit';
    window.dispatchEvent(new Event('hashchange'));
    expect(seen).toEqual(['change']);
  });

  it('does not fire on subscribe', () => {
    // The caller has already rendered the current route by the time it subscribes; firing
    // immediately would render it twice and, on a screen that fetches, request it twice.
    const seen: string[] = [];
    const stop = onRouteChange((route) => seen.push(route));
    expect(seen).toEqual([]);
    stop();
  });
});
