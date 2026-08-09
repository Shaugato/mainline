// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Fixture scaffolding for the silence suite.
 *
 * Every expected number — a score, a threshold, theta, s, n, the four conservation counts —
 * is read out of `fixtures/` at run time. None is written down in this directory. On a
 * surface whose entire subject is arithmetic, a test that restated the arithmetic would be
 * checking that two copies of the same literal agree, which is not a property of anything.
 *
 * The verifier here is real: SHA-256 over the actual bytes, through the same
 * `BundleTransport` the console uses, which has no default verifier and no skip switch. A
 * mutated fixture only renders after `mutateFrame` re-seals the manifest, so a mutation
 * that renders has passed the integrity gate rather than gone around it.
 *
 * Self-contained rather than shared with `tests/unit/gate/` or `tests/unit/propagation/`:
 * the first belongs to another worker, and both directories are meant to be independently
 * deletable.
 */

import {
  BundleTransport,
  MemoryBundleSource,
  type BundleFinding,
  type BundleManifest,
  type BundleVerificationInput,
  type BundleVerificationReport,
  type BundleVerifier,
} from '../../../src/data/bundle';
import { contractRegistry } from '../../../src/data/contracts';
import { framePathForKey } from '../../../src/data/resources';
import type { MainlineTransport } from '../../../src/data/transport';
import type { RecallRunResponse, SilenceResponse } from '../../../src/data/types.generated';

const BUNDLE_ROOT = '/fixtures/bundles/blk-07/';

const RAW_BUNDLE = import.meta.glob<string>('/fixtures/bundles/blk-07/**/*', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const RAW_PAYLOADS = import.meta.glob<string>('/fixtures/sources/blk-07/payloads/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/** `manifest.seed.json` is the INPUT to sealing and is deliberately not bundle content. */
const NOT_BUNDLE_CONTENT = new Set(['manifest.seed.json']);

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

export function bundleFiles(): Map<string, Uint8Array> {
  const files = new Map<string, Uint8Array>();
  for (const [key, text] of Object.entries(RAW_BUNDLE)) {
    if (!key.startsWith(BUNDLE_ROOT)) continue;
    const path = key.slice(BUNDLE_ROOT.length);
    if (NOT_BUNDLE_CONTENT.has(path)) continue;
    files.set(path, encoder.encode(text));
  }
  if (files.size === 0) {
    throw new Error(
      'tests/unit/silence/_fixture.ts: the fixture bundle glob matched nothing. Every assertion ' +
        'in this suite would then be vacuous.',
    );
  }
  return files;
}

function payload(name: string): string {
  const key = `/fixtures/sources/blk-07/payloads/${name}`;
  const text = RAW_PAYLOADS[key];
  if (text === undefined) {
    throw new Error(
      `tests/unit/silence/_fixture.ts: no ${key}. Available: ${Object.keys(RAW_PAYLOADS).join(', ')}`,
    );
  }
  return text;
}

export function sourceSilence(): SilenceResponse {
  return JSON.parse(payload('silence.json')) as SilenceResponse;
}

export function sourceRecallRun(): RecallRunResponse {
  return JSON.parse(payload('recall-run.json')) as RecallRunResponse;
}

/** The permit the staged bundle is about, READ OUT OF THE FIXTURE. */
export function permitId(): string {
  return sourceSilence().data.subject_id;
}

/** The run the RECEIPT names. The console never guesses one, and neither does this suite. */
export function runId(): string {
  const receipt = sourceSilence().data.receipt;
  if (receipt === null) {
    throw new Error(
      'tests/unit/silence/_fixture.ts: the staged silence payload carries no receipt, so the ' +
        'conservation panel has nothing to read and half this suite would be vacuous.',
    );
  }
  return receipt.run_id;
}

export function silenceFramePath(): string {
  return framePathForKey(`GET /v1/permits/${permitId()}/silence`);
}

export function recallRunFramePath(): string {
  return framePathForKey(`GET /v1/recall-runs/${runId()}`);
}

// ── Frames ─────────────────────────────────────────────────────────────────

interface Frame {
  readonly key: string;
  readonly response: { readonly status: number; readonly body_b64: string };
}

function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function fromBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

/**
 * Rewrites one frame's response envelope and RE-SEALS the manifest over the result.
 *
 * Re-sealing is the point rather than an inconvenience: the transport refuses any file
 * whose digest disagrees with the manifest.
 */
export async function mutateFrame(
  files: ReadonlyMap<string, Uint8Array>,
  path: string,
  transform: (envelope: Record<string, unknown>) => void,
): Promise<Map<string, Uint8Array>> {
  const raw = files.get(path);
  if (raw === undefined) {
    throw new Error(`no frame at ${path}. Present: ${[...files.keys()].sort().join(', ')}`);
  }

  const frame = JSON.parse(decoder.decode(raw)) as Frame;
  const envelope = JSON.parse(decoder.decode(fromBase64(frame.response.body_b64))) as Record<
    string,
    unknown
  >;
  transform(envelope);

  const body = encoder.encode(JSON.stringify(envelope));
  const rewritten = { ...frame, response: { ...frame.response, body_b64: toBase64(body) } };

  const next = new Map(files);
  next.set(path, encoder.encode(JSON.stringify(rewritten, null, 2)));
  return resealBundle(next);
}

export async function resealBundle(
  files: ReadonlyMap<string, Uint8Array>,
): Promise<Map<string, Uint8Array>> {
  const manifestBytes = files.get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json.');
  const manifest = JSON.parse(decoder.decode(manifestBytes)) as BundleManifest;

  const sealed: { path: string; sha256: string; bytes: number; media_type?: string | null }[] = [];
  for (const entry of manifest.files) {
    const bytes = files.get(entry.path);
    if (bytes === undefined) throw new Error(`manifest lists ${entry.path}, which is absent.`);
    sealed.push({
      path: entry.path,
      sha256: await sha256Hex(bytes),
      bytes: bytes.byteLength,
      ...(entry.media_type === undefined ? {} : { media_type: entry.media_type }),
    });
  }

  const next = new Map(files);
  next.set('manifest.json', encoder.encode(JSON.stringify({ ...manifest, files: sealed }, null, 2)));
  return next;
}

// ── A real verifier, for tests only ────────────────────────────────────────

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function manifestIntegrityVerifier(): BundleVerifier {
  return {
    name: 'silence-suite:manifest-integrity',
    async verify(input: BundleVerificationInput): Promise<BundleVerificationReport> {
      const findings: BundleFinding[] = [];
      let checked = 0;
      for (const entry of input.manifest.files) {
        let bytes: Uint8Array;
        try {
          bytes = await input.read(entry.path);
        } catch (error) {
          findings.push({ subject: entry.path, check: 'present', detail: String(error) });
          continue;
        }
        checked += 1;
        const digest = await sha256Hex(bytes);
        if (digest !== entry.sha256) {
          findings.push({
            subject: entry.path,
            check: 'manifest-digest',
            detail: `manifest declares ${entry.sha256}; the bytes hash to ${digest}.`,
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

export function bundleTransport(files: ReadonlyMap<string, Uint8Array>): MainlineTransport {
  return new BundleTransport({
    source: new MemoryBundleSource('silence-suite', new Map(files)),
    registry: contractRegistry(),
    verifier: manifestIntegrityVerifier(),
  });
}
