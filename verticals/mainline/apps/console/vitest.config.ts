// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config.ts';

/**
 * The unit tier. It runs in jsdom, it never touches the network, and it never needs
 * a database, a cloud account or a model call.
 *
 * `tests/browser/**` is EXCLUDED here on purpose: those are Playwright specs owned by
 * the cinema-conformance-harness worker and they run under `pnpm run test:browser`.
 * A Playwright spec picked up by Vitest fails for an uninteresting reason and teaches
 * the fleet to ignore red, which is the one thing PL-2 cannot survive.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./tests/setup.ts'],
      include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
      exclude: ['node_modules/**', 'dist/**', 'tests/browser/**'],
      restoreMocks: true,
      unstubEnvs: true,
      unstubGlobals: true,
      css: true,
      coverage: {
        provider: 'v8',
        reportsDirectory: 'coverage',
        reporter: ['text-summary', 'json-summary'],
        include: ['src/**/*.{ts,tsx}'],
        exclude: ['src/**/*.d.ts', 'src/main.tsx'],
      },
    },
  }),
);
