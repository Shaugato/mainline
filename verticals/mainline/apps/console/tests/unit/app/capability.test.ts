// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The capability probe.
 *
 * Written RED, before src/app/capability.ts existed.
 *
 * ui.md §1.3: the 2D ribbon is the SAME TRUTH MINUS ONE AXIS, never a fallback, and
 * `prefers-reduced-motion`, a failed WebGL2 probe, `deviceMemory < 4`, a battery-saver
 * signal or `?render=2d` all select it. The two assertions that matter here and would
 * pass a careless implementation:
 *
 *   1. An UNREPORTED deviceMemory is `null`, not a guess, and does not by itself
 *      select the ribbon. Guessing a number and then gating on it is a fabricated
 *      claim about the reader's machine.
 *   2. `?render=3d` is a REQUEST, not an override. It cannot conjure a WebGL2 context
 *      that does not exist, and the refusal is recorded in `reasons`.
 */

import { describe, expect, it } from 'vitest';

import {
  type CapabilityHost,
  MEMORY_REGISTER_MIN_DEVICE_MEMORY_GB,
  probeCapability,
} from '../../../src/app/capability';

const capableHost = (over: Partial<CapabilityHost> = {}): CapabilityHost => ({
  search: '',
  hash: '',
  deviceMemoryGb: 8,
  hardwareConcurrency: 8,
  prefersReducedMotion: false,
  saveData: false,
  probeWebgl2: () => true,
  ...over,
});

describe('probeCapability — the honest answer, with its arithmetic', () => {
  it('selects the dimensional walk on a capable machine', () => {
    const cap = probeCapability(capableHost());
    expect(cap.webgl2).toBe(true);
    expect(cap.renderMode).toBe('3d');
    expect(cap.reasons.length).toBeGreaterThan(0);
  });

  it('is frozen, reasons included', () => {
    const cap = probeCapability(capableHost());
    expect(Object.isFrozen(cap)).toBe(true);
    expect(Object.isFrozen(cap.reasons)).toBe(true);
  });

  it('reports an unreported deviceMemory as null and does NOT infer one', () => {
    const cap = probeCapability(capableHost({ deviceMemoryGb: null }));
    expect(cap.deviceMemoryGb).toBeNull();
    expect(cap.renderMode).toBe('3d');
    expect(cap.reasons.join(' ')).toMatch(/deviceMemory/i);
    expect(cap.reasons.join(' ')).toMatch(/unreported|not reported/i);
  });

  it('selects the ribbon when deviceMemory is below the floor', () => {
    const cap = probeCapability(
      capableHost({ deviceMemoryGb: MEMORY_REGISTER_MIN_DEVICE_MEMORY_GB - 1 }),
    );
    expect(cap.renderMode).toBe('2d');
    expect(cap.reasons.join(' ')).toContain('deviceMemory');
  });

  it('selects the ribbon under prefers-reduced-motion', () => {
    const cap = probeCapability(capableHost({ prefersReducedMotion: true }));
    expect(cap.prefersReducedMotion).toBe(true);
    expect(cap.renderMode).toBe('2d');
    expect(cap.reasons.join(' ')).toMatch(/reduced.?motion/i);
  });

  it('selects the ribbon under a battery-saver / save-data signal', () => {
    const cap = probeCapability(capableHost({ saveData: true }));
    expect(cap.renderMode).toBe('2d');
    expect(cap.reasons.join(' ')).toMatch(/save.?data/i);
  });

  it('selects the ribbon when the WebGL2 probe fails', () => {
    const cap = probeCapability(capableHost({ probeWebgl2: () => false }));
    expect(cap.webgl2).toBe(false);
    expect(cap.renderMode).toBe('2d');
    expect(cap.reasons.join(' ')).toMatch(/webgl2/i);
  });

  it('never lets a throwing WebGL2 probe escape', () => {
    const cap = probeCapability(
      capableHost({
        probeWebgl2: () => {
          throw new Error('not implemented');
        },
      }),
    );
    expect(cap.webgl2).toBe(false);
    expect(cap.renderMode).toBe('2d');
  });
});

describe('the ?render override', () => {
  it('honours ?render=2d from the search string', () => {
    const cap = probeCapability(capableHost({ search: '?render=2d' }));
    expect(cap.renderOverride).toBe('2d');
    expect(cap.renderMode).toBe('2d');
    expect(cap.reasons.join(' ')).toContain('render=2d');
  });

  it('honours render=2d carried in the hash query', () => {
    const cap = probeCapability(capableHost({ hash: '#/ancestry?render=2d' }));
    expect(cap.renderOverride).toBe('2d');
    expect(cap.renderMode).toBe('2d');
  });

  it('treats ?render=3d as a request that a missing WebGL2 context refuses', () => {
    const cap = probeCapability(capableHost({ search: '?render=3d', probeWebgl2: () => false }));
    expect(cap.renderOverride).toBe('3d');
    expect(cap.renderMode).toBe('2d');
    expect(cap.reasons.join(' ')).toMatch(/refused|cannot|no webgl2/i);
  });

  it('lets ?render=3d defeat a soft signal, but records that it did', () => {
    const cap = probeCapability(capableHost({ search: '?render=3d', deviceMemoryGb: 2 }));
    expect(cap.renderMode).toBe('3d');
    expect(cap.reasons.join(' ')).toContain('render=3d');
  });

  it('ignores a ?render value it does not understand', () => {
    const cap = probeCapability(capableHost({ search: '?render=holographic' }));
    expect(cap.renderOverride).toBeNull();
    expect(cap.renderMode).toBe('3d');
  });

  it('carries hardwareConcurrency through verbatim', () => {
    expect(probeCapability(capableHost({ hardwareConcurrency: 2 })).hardwareConcurrency).toBe(2);
    expect(probeCapability(capableHost({ hardwareConcurrency: null })).hardwareConcurrency).toBeNull();
  });
});
