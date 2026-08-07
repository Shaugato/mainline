// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Vitest setup for the unit tier. Referenced by `vitest.config.ts`.
 *
 * Three jobs, and nothing else. This file must never contain a stub that makes a
 * test pass — the whole domain's PL-2 discipline depends on a red test being red for
 * the reason the test names.
 */

import '@testing-library/jest-dom/vitest';
import { afterEach, expect } from 'vitest';

/**
 * 1. `matchMedia` does not exist in jsdom. The capability probe reads it, and the
 *    reduced-motion contract (D14) is asserted in unit tests, so a missing
 *    implementation would make those tests pass for the wrong reason. Install a
 *    minimal, honest one: every query is reported as NOT matching. Tests that care
 *    about a specific query stub `probeCapability`'s host explicitly rather than
 *    reaching for this.
 */
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }),
  });
}

/**
 * 2. jsdom has no WebGL. `HTMLCanvasElement.getContext` throws a "not implemented"
 *    error rather than returning null, which would make the WebGL2 probe fail with a
 *    stack trace instead of a `false`. Return null, which is what a browser without
 *    WebGL2 actually does.
 */
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = function getContext(): null {
    return null;
  };
}

/**
 * 3. The router is hash-based. Each test starts from a known location so that a
 *    leaked `location.hash` from a previous test cannot make the next one green.
 */
afterEach(() => {
  if (typeof window !== 'undefined') {
    window.location.hash = '';
  }
});

// Fail loudly if jest-dom did not install: a missing matcher silently degrades to
// `expect(...).toBeInTheDocument is not a function`, which reads as a test-authoring
// mistake rather than a setup failure.
if (typeof expect(document.body).toBeInTheDocument !== 'function') {
  throw new Error('tests/setup.ts: @testing-library/jest-dom matchers did not install.');
}
