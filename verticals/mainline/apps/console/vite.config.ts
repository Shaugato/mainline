// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const here = fileURLToPath(new URL('.', import.meta.url));

/**
 * EVERY BUILD INPUT THIS CONFIG READS, IN ONE PLACE.
 *
 * A `define` is substituted into every module before minification, so anything that feeds
 * one reaches the emitted bytes. An input that reaches the bytes and is written down
 * nowhere is *ambient*, and this repository has already paid for one: it carries two
 * different entry chunks at an identical 433,564 bytes, `index-BKZMI9SJ.js` and
 * `index-DzVoV1YM.js`, both recorded as "the build at HEAD", from a source tree that
 * `git diff` says never changed. Measured (`evidence/deploy/console-repro.json`): the
 * committed source builds `index-DzVoV1YM.js` three times out of three, byte for byte, and
 * `BKZMI9SJ` is what the same source builds when one CSS module is checked out CRLF —
 * a scoped class name is a hash of the module's bytes, and a hash is fixed-length, so the
 * value moves and the length does not.
 *
 * These two names are the declaration. `scripts/deploy/console_repro.py`
 * `BUILD_INPUT_NAMES` lists them alongside the four `VITE_*` names Vite reads from
 * `.env.demo`, and `tests/deploy/test_console_repro.py` fails if this file grows a
 * `process.env` read that is not on that list. Adding an input is allowed; adding one
 * silently is not.
 *
 * `??` and not `||`: an EMPTY value is a value somebody supplied, and it must not be
 * quietly replaced by the default.
 */
const BUILD_INPUTS = {
  /** The `build` cell of the honesty chrome. A screenshot must name the artefact it came from. */
  MAINLINE_BUILD_ID: process.env['MAINLINE_BUILD_ID'] ?? 'dev',
  /** An explicit attestation path, overriding the two probed below. */
  MAINLINE_ATTESTATION: process.env['MAINLINE_ATTESTATION'],
} as const;

/**
 * The files `readSignaturePath()` probes, relative to the repository root.
 *
 * **Whether a file exists is a build input.** Neither of these exists today, so the build
 * resolves `unknown`/`absent` — which is the honest answer and is compiled as one. The
 * paths are named here so a record of a build can state which of them was present.
 */
const ATTESTATION_CANDIDATES = [
  '../../../../evidence/attestations/g1-attestation.json',
  '../../../../evidence/g1-attestation.json',
] as const;

/**
 * D17 — the signature-capture path is a RENDER-TIME SWITCH, not a runtime branch.
 *
 * `GT-15` decides whether WebAuthn is available on the target fleet. Its verdict is
 * written to an attestation file by the platform domain. The console reads that file
 * **at build time** and compiles exactly one capture path, and the honesty chrome
 * names which one. An unverified capability must not reach a rendered artefact.
 *
 * If the attestation is absent the answer is `unknown` — never a guess, and never a
 * silent default to the capability we would prefer to have.
 */
type SignaturePath = 'webauthn' | 'oidc_envelope' | 'unknown';

interface Attestation {
  readonly signature_path?: unknown;
  readonly gate?: unknown;
  readonly verdict?: unknown;
}

function readSignaturePath(): { path: SignaturePath; source: string } {
  const override = BUILD_INPUTS.MAINLINE_ATTESTATION;
  const candidates = override
    ? [override]
    : ATTESTATION_CANDIDATES.map((candidate) => resolve(here, candidate));

  for (const candidate of candidates) {
    let raw: string;
    try {
      raw = readFileSync(candidate, 'utf8');
    } catch {
      continue;
    }
    // A malformed attestation is louder than a missing one: it means somebody
    // produced the file and it does not parse. Fail the build rather than fall
    // back to `unknown`, which would look identical to "nobody ran GT-15".
    const parsed = JSON.parse(raw) as Attestation;
    const declared = parsed.signature_path ?? parsed.verdict;
    if (declared === 'webauthn' || declared === 'oidc_envelope') {
      return { path: declared, source: candidate };
    }
    throw new Error(
      `MAINLINE console build: ${candidate} exists but declares no usable signature_path ` +
        `(got ${JSON.stringify(declared)}; expected "webauthn" or "oidc_envelope").`,
    );
  }

  return { path: 'unknown', source: 'absent' };
}

const attestation = readSignaturePath();

export default defineConfig({
  // Relative base. The built console must load from a bare static host, from a
  // sub-path, and from file:// — the offline reproduction tier in BUILD_PLAN §5 is
  // on the never-cut list, and routing is hash-based for the same reason.
  base: './',

  plugins: [react()],

  define: {
    __MAINLINE_BUILD_ID__: JSON.stringify(BUILD_INPUTS.MAINLINE_BUILD_ID),
    __MAINLINE_SIGNATURE_PATH__: JSON.stringify(attestation.path),
    __MAINLINE_ATTESTATION_SOURCE__: JSON.stringify(
      attestation.source === 'absent' ? 'absent' : 'g1-attestation.json',
    ),
  },

  build: {
    target: 'es2022',
    outDir: 'dist',
    assetsDir: 'assets',
    // scripts/check-budgets.ts reads dist/.vite/manifest.json. The budget gate is a
    // test (D13); without the manifest it has nothing to measure and must fail.
    manifest: true,
    sourcemap: true,
    // Vite's own "chunk is large" warning is advisory. The real gate is
    // check-budgets.ts, which fails the build. Keep the warning below the budget so
    // it fires first and is informative rather than duplicative.
    chunkSizeWarningLimit: 200,
    rollupOptions: {
      output: {
        // Named chunks make a budget addressable by the thing it is a budget FOR.
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },

  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
});
