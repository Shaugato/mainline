// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Shared scaffolding for the data-layer tests.
 *
 * Two things live here and nowhere else.
 *
 * **A real SHA-256 bundle verifier, written in the TEST tree.** `src/data/**` computes
 * no digests — verification is the verifier-custody-room worker's, injected into
 * `BundleTransport`. But a tamper test that injects a verifier which never actually
 * hashes anything proves nothing, so this file implements the manifest-integrity check
 * with WebCrypto. It is a stand-in for the real verifier, it says so, and it is
 * deliberately confined to `tests/`.
 *
 * **A reader for `node:fs`, obtained through a non-literal dynamic import.** The unit
 * project's `types` list is `["vite/client", "vitest/globals"]` — the application must
 * not be able to reach a Node global by accident, which is correct and is not this
 * worker's file to change. A test that has to read a file OUTSIDE the console workspace
 * (the specification copy of the refusal schema) therefore resolves the module at
 * runtime rather than at type-check time, and narrows it to the two functions it uses.
 */

import type {
  BundleFinding,
  BundleVerificationInput,
  BundleVerificationReport,
  BundleVerifier,
} from '../../../src/data/bundle';

// ── Fixture bytes ──────────────────────────────────────────────────────────

const BUNDLE_ROOT = '/fixtures/bundles/blk-07/';

const RAW_FILES = import.meta.glob<string>('/fixtures/bundles/blk-07/**/*', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const encoder = new TextEncoder();

/**
 * `manifest.seed.json` is the INPUT to sealing, not part of the bundle, and the manifest
 * deliberately does not list it. Serving it would mean serving a file nothing checked.
 */
const NOT_BUNDLE_CONTENT = new Set(['manifest.seed.json']);

export function bundleFiles(): Map<string, Uint8Array> {
  const files = new Map<string, Uint8Array>();
  for (const [key, text] of Object.entries(RAW_FILES)) {
    if (!key.startsWith(BUNDLE_ROOT)) continue;
    const path = key.slice(BUNDLE_ROOT.length);
    if (NOT_BUNDLE_CONTENT.has(path)) continue;
    files.set(path, encoder.encode(text));
  }
  if (files.size === 0) {
    throw new Error(
      'no fixture files were globbed. Run `node scripts/capture-bundle.ts stage ' +
        '--sources fixtures/sources/blk-07 --out fixtures/bundles/blk-07`.',
    );
  }
  return files;
}

/** The raw source payloads, keyed by file name — used to check them against contracts. */
const RAW_SOURCES = import.meta.glob<string>('/fixtures/sources/blk-07/payloads/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

export function sourcePayloads(): Map<string, string> {
  const payloads = new Map<string, string>();
  for (const [key, text] of Object.entries(RAW_SOURCES)) {
    payloads.set(key.split('/').slice(-1)[0] ?? key, text);
  }
  return payloads;
}

/** The staging plan, so a test can walk exactly the steps that produced the bundle. */
const RAW_PLAN = import.meta.glob<string>('/fixtures/sources/blk-07/plan.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

export interface StagePlanStep {
  readonly resource: string;
  readonly path?: Record<string, string>;
  readonly query?: Record<string, string>;
  readonly body?: unknown;
  readonly status?: number;
  readonly payload: string;
}

export interface StagePlan {
  readonly manifest: { readonly bundle_id: string; readonly staged: boolean };
  readonly steps: readonly StagePlanStep[];
}

export function stagePlan(): StagePlan {
  const text = Object.values(RAW_PLAN)[0];
  if (text === undefined) throw new Error('fixtures/sources/blk-07/plan.json was not globbed.');
  return JSON.parse(text) as StagePlan;
}

// ── A real verifier, for tests only ────────────────────────────────────────

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

/**
 * Manifest integrity, and nothing else.
 *
 * The verdict this verifier returns answers exactly one question: **are these the bytes
 * that were sealed?** It says nothing about whether the ledger inside the bundle
 * verifies — that is a claim about the CONTENTS, it belongs to the custody surface, and
 * for a staged fixture it is expected to fail. Conflating the two would mean a bundle
 * of demonstration material could not be played at all, and the demonstration would
 * quietly move somewhere with no integrity check instead.
 */
export function manifestIntegrityVerifier(name = 'test:manifest-integrity'): BundleVerifier {
  return {
    name,
    async verify(input: BundleVerificationInput): Promise<BundleVerificationReport> {
      const findings: BundleFinding[] = [];
      let checked = 0;

      for (const entry of input.manifest.files) {
        let bytes: Uint8Array;
        try {
          bytes = await input.read(entry.path);
        } catch (error) {
          findings.push({
            subject: entry.path,
            check: 'manifest-file-present',
            detail: String(error),
          });
          continue;
        }
        checked += 1;
        const digest = await sha256Hex(bytes);
        if (digest !== entry.sha256) {
          findings.push({
            subject: entry.path,
            check: 'manifest-digest',
            detail: `manifest declares sha256 ${entry.sha256}; the bytes hash to ${digest}.`,
          });
        }
      }

      return {
        verdict: findings.length === 0 ? 'verified' : 'failed',
        manifestDigest: await sha256Hex(input.manifestBytes),
        filesChecked: checked,
        summary:
          findings.length === 0
            ? `${checked} file(s) match the manifest.`
            : `${findings.length} file(s) do not match the manifest.`,
        findings,
      };
    },
  };
}

/** A verifier that always refuses. Proves the transport's gate is not decorative. */
export function refusingVerifier(reason: string): BundleVerifier {
  return {
    name: 'test:always-refuses',
    verify(): Promise<BundleVerificationReport> {
      return Promise.resolve({
        verdict: 'failed',
        manifestDigest: '0'.repeat(64),
        filesChecked: 0,
        summary: reason,
        findings: [{ subject: 'manifest.json', check: 'test', detail: reason }],
      });
    },
  };
}

// ── Reading outside the console workspace ──────────────────────────────────

interface FsSlice {
  readFileSync(path: string, encoding: 'utf8'): string;
  existsSync(path: string): boolean;
}

/**
 * The repository root, relative to the VITEST WORKING DIRECTORY (the console
 * workspace), which is what `readFileSync` resolves a relative path against.
 * `verticals/mainline/apps/console` is four levels below the repository root.
 */
export const REPO_ROOT = '../../../../';

export async function nodeFs(): Promise<FsSlice> {
  // A non-literal specifier: TypeScript does not resolve it, so this file needs no
  // `@types/node` and the application project's type surface stays closed.
  const specifier = ['node', 'fs'].join(':');
  const mod: unknown = await import(/* @vite-ignore */ specifier);
  return mod as FsSlice;
}
