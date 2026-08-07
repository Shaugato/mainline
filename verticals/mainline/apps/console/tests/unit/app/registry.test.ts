// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The surface registry (D8).
 *
 * Written RED, before src/app/surfaces.ts existed. PL-2: for a product whose
 * deliverable is a refusal, a test suite that has never been red asserts nothing —
 * and the specific thing asserted here is that an ABSENT surface produces an honest
 * card naming the milestone that owns it, never a blank screen and never a throw.
 * A registry that silently drops a missing surface would pass an eyeball review and
 * would be exactly the lie BUILD_PLAN §3 warns about.
 */

import { describe, expect, it } from 'vitest';

import {
  DECLARED_SURFACES,
  REGISTERS,
  buildRegistry,
  surfaceIdFromModuleKey,
  validateSurfaceModule,
} from '../../../src/app/surfaces';

const GLOB_KEY = (id: string): string => `/src/features/${id}/surface.tsx`;

const okComponent = (): null => null;

describe('DECLARED_SURFACES — the expectation the console is honest about', () => {
  it('declares at least the six surfaces the K5 walkthrough names', () => {
    const ids = DECLARED_SURFACES.map((s) => s.id);
    for (const required of [
      'gate',
      'ancestry',
      'disposition',
      'custody',
      'audit',
      'propagation',
      'silence',
    ]) {
      expect(ids).toContain(required);
    }
  });

  it('has unique ids, unique paths and unique orders', () => {
    const ids = DECLARED_SURFACES.map((s) => s.id);
    const paths = DECLARED_SURFACES.map((s) => s.path);
    const orders = DECLARED_SURFACES.map((s) => s.order);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(paths).size).toBe(paths.length);
    expect(new Set(orders).size).toBe(orders.length);
  });

  it('names a real register and a real milestone for every surface', () => {
    for (const surface of DECLARED_SURFACES) {
      expect(REGISTERS).toContain(surface.register);
      expect(surface.milestone).toMatch(/^K[0-9]+$/);
      expect(surface.owner).toMatch(/^ui\/[a-z0-9-]+$/);
      expect(surface.path.startsWith('/')).toBe(true);
    }
  });

  it('is frozen — a surface list a feature worker can mutate is not a contract', () => {
    expect(Object.isFrozen(DECLARED_SURFACES)).toBe(true);
    for (const surface of DECLARED_SURFACES) {
      expect(Object.isFrozen(surface)).toBe(true);
    }
  });
});

describe('surfaceIdFromModuleKey', () => {
  it('extracts the feature directory name', () => {
    expect(surfaceIdFromModuleKey('/src/features/gate/surface.tsx')).toBe('gate');
    expect(surfaceIdFromModuleKey('/src/features/ancestry/surface.tsx')).toBe('ancestry');
  });

  it('refuses a key that is not exactly one directory deep', () => {
    expect(surfaceIdFromModuleKey('/src/features/gate/panels/surface.tsx')).toBeNull();
    expect(surfaceIdFromModuleKey('/src/surface.tsx')).toBeNull();
    expect(surfaceIdFromModuleKey('/src/features/surface.tsx')).toBeNull();
  });

  it('refuses a directory name that is not a legal surface id', () => {
    expect(surfaceIdFromModuleKey('/src/features/Gate/surface.tsx')).toBeNull();
    expect(surfaceIdFromModuleKey('/src/features/_scratch/surface.tsx')).toBeNull();
  });
});

describe('buildRegistry — absence is a rendered fact, not a gap', () => {
  it('marks every declared surface missing when no feature module exists', () => {
    const registry = buildRegistry({});
    expect(registry).toHaveLength(DECLARED_SURFACES.length);
    for (const entry of registry) {
      expect(entry.status).toBe('declared-missing');
      expect(entry.load).toBeNull();
      // The card must be able to name who owes this screen.
      expect(entry.milestone).toMatch(/^K[0-9]+$/);
      expect(entry.owner).toMatch(/^ui\//);
    }
  });

  it('marks a declared surface loadable once its module key appears', () => {
    const registry = buildRegistry({ [GLOB_KEY('gate')]: () => Promise.resolve({}) });
    const gate = registry.find((entry) => entry.id === 'gate');
    expect(gate?.status).toBe('loadable');
    expect(typeof gate?.load).toBe('function');
    const ancestry = registry.find((entry) => entry.id === 'ancestry');
    expect(ancestry?.status).toBe('declared-missing');
  });

  it('admits an UNDECLARED surface and defaults it to the most restrictive register', () => {
    const registry = buildRegistry({ [GLOB_KEY('fixity')]: () => Promise.resolve({}) });
    const extra = registry.find((entry) => entry.id === 'fixity');
    expect(extra).toBeDefined();
    expect(extra?.status).toBe('undeclared');
    expect(extra?.register).toBe('evidence');
    expect(extra?.milestone).toBe('unknown');
  });

  it('ignores a module key that is not a surface entry point', () => {
    const registry = buildRegistry({ '/src/features/gate/panels/surface.tsx': () => Promise.resolve({}) });
    expect(registry.find((entry) => entry.id === 'gate')?.status).toBe('declared-missing');
    expect(registry).toHaveLength(DECLARED_SURFACES.length);
  });

  it('orders by declared order, then by id', () => {
    const registry = buildRegistry({ [GLOB_KEY('zzz')]: () => Promise.resolve({}) });
    const orders = registry.map((entry) => entry.order);
    expect([...orders].sort((a, b) => a - b)).toEqual(orders);
    expect(registry.at(-1)?.id).toBe('zzz');
  });
});

describe('validateSurfaceModule — a module that lies is a missing surface', () => {
  it('accepts a well-formed descriptor', () => {
    const result = validateSurfaceModule('gate', {
      surface: {
        id: 'gate',
        path: '/gate',
        title: 'Gate',
        register: 'evidence',
        order: 10,
        milestone: 'K5',
        Component: okComponent,
      },
    });
    expect(result.ok).toBe(true);
  });

  it('refuses a module with no surface export, and says so', () => {
    const result = validateSurfaceModule('gate', { default: okComponent });
    expect(result.ok).toBe(false);
    expect(result.ok ? '' : result.reason).toMatch(/surface/i);
  });

  it('refuses an id mismatch, naming both ids', () => {
    const result = validateSurfaceModule('gate', {
      surface: {
        id: 'disposition',
        path: '/gate',
        title: 'Gate',
        register: 'evidence',
        order: 10,
        milestone: 'K5',
        Component: okComponent,
      },
    });
    expect(result.ok).toBe(false);
    const reason = result.ok ? '' : result.reason;
    expect(reason).toContain('gate');
    expect(reason).toContain('disposition');
  });

  it('refuses an unknown register', () => {
    const result = validateSurfaceModule('gate', {
      surface: {
        id: 'gate',
        path: '/gate',
        title: 'Gate',
        register: 'cinematic',
        order: 10,
        milestone: 'K5',
        Component: okComponent,
      },
    });
    expect(result.ok).toBe(false);
    expect(result.ok ? '' : result.reason).toContain('cinematic');
  });

  it('refuses a descriptor whose Component is not callable', () => {
    const result = validateSurfaceModule('gate', {
      surface: {
        id: 'gate',
        path: '/gate',
        title: 'Gate',
        register: 'evidence',
        order: 10,
        milestone: 'K5',
        Component: 'GateScreen',
      },
    });
    expect(result.ok).toBe(false);
    expect(result.ok ? '' : result.reason).toMatch(/component/i);
  });

  it('refuses a non-object module without throwing', () => {
    expect(validateSurfaceModule('gate', null).ok).toBe(false);
    expect(validateSurfaceModule('gate', 42).ok).toBe(false);
    expect(validateSurfaceModule('gate', undefined).ok).toBe(false);
  });
});
