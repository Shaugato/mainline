// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Fixture scaffolding for the fleet suite.
 *
 * ── EVERY EXPECTATION IS READ OUT OF THE BUNDLE ──────────────────────────────────
 *
 * Not one site code, declination kind, predicate id or digest is written down in this
 * directory. They are read from `fixtures/`, which is the same bytes the console's replay
 * transport serves. A test that hardcodes the string it expects passes just as happily
 * against a component that hardcodes the string it renders, and the pair of them assert
 * nothing at all — the failure mode `docs/leads/ui.md` §1.5 names by name.
 *
 * `mutateFrame` exists so the suite can prove the coupling directly: change the fixture,
 * and the rendered text must change with it.
 *
 * ── THE VERIFIER IS REAL ─────────────────────────────────────────────────────────
 *
 * `BundleTransport` has no default verifier and no skip switch, on purpose. The one here
 * computes SHA-256 with WebCrypto over the actual bytes; it genuinely fails on a tampered
 * file, which is why `mutateFrame` has to re-seal the manifest. A mutated fixture that
 * renders at all has passed the same integrity gate the untouched one does.
 *
 * ── WHY THIS FILE IS NOT SHARED WITH tests/unit/gate/ ────────────────────────────
 *
 * That directory belongs to another worker. Importing across the boundary would couple two
 * trees that are meant to be independently deletable, and reaching into it to add a helper
 * would corrupt their tree outright. The ~90 lines below are the price of that isolation
 * and are deliberate.
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
import type { MainlineTransport } from '../../../src/data/transport';
import type { PropagationResponse } from '../../../src/data/types.generated';

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
      'tests/unit/propagation/_fixture.ts: the fixture bundle glob matched nothing. Every ' +
        'assertion in this suite would then be vacuous.',
    );
  }
  return files;
}

/** A source payload, parsed. The pure-model tests need the rows and no transport. */
export function sourcePropagation(): PropagationResponse {
  const key = '/fixtures/sources/blk-07/payloads/propagation.json';
  const text = RAW_PAYLOADS[key];
  if (text === undefined) {
    throw new Error(
      `tests/unit/propagation/_fixture.ts: no ${key}. Available: ${Object.keys(RAW_PAYLOADS).join(', ')}`,
    );
  }
  return JSON.parse(text) as PropagationResponse;
}

/** The lesson the staged bundle is about, READ OUT OF THE FIXTURE. */
export function lessonId(): string {
  return sourcePropagation().data.lesson.lesson_id;
}

/**
 * The bundle path of the frame answering a canonical request key.
 *
 * Read out of the SEALED manifest rather than computed: frame names are content
 * addresses written by `scripts/capture-bundle.ts`, and `src/**` computes no digests,
 * so `manifest.files[].key` is the index — here as it is for the transport itself.
 */
function frameAddress(requestKey: string): string {
  const manifestBytes = bundleFiles().get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json.');
  const manifest = JSON.parse(decoder.decode(manifestBytes)) as BundleManifest;
  const entry = manifest.files.find((file) => file.key === requestKey);
  if (entry === undefined) {
    throw new Error(`the sealed blk-07 manifest lists no frame answering "${requestKey}".`);
  }
  return entry.path;
}

export function propagationFramePath(): string {
  return frameAddress(`GET /v1/lessons/${lessonId()}/propagation`);
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

/** The decoded envelope a frame carries — what the transport will hand a surface. */
export function frameEnvelope(
  files: ReadonlyMap<string, Uint8Array>,
  path: string,
): PropagationResponse {
  const raw = files.get(path);
  if (raw === undefined) {
    throw new Error(`no frame at ${path}. Present: ${[...files.keys()].sort().join(', ')}`);
  }
  const frame = JSON.parse(decoder.decode(raw)) as Frame;
  return JSON.parse(decoder.decode(fromBase64(frame.response.body_b64))) as PropagationResponse;
}

/**
 * Rewrites one frame's response envelope and RE-SEALS the manifest over the result.
 *
 * Re-sealing is the point, not a convenience: the transport refuses any file whose digest
 * disagrees with the manifest.
 */
export async function mutateFrame(
  files: ReadonlyMap<string, Uint8Array>,
  path: string,
  transform: (envelope: Record<string, unknown>) => void,
): Promise<Map<string, Uint8Array>> {
  const raw = files.get(path);
  if (raw === undefined) throw new Error(`no frame at ${path}`);

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

/** Recomputes every `manifest.files[].sha256` and `bytes` over the current contents. */
export async function resealBundle(
  files: ReadonlyMap<string, Uint8Array>,
): Promise<Map<string, Uint8Array>> {
  const manifestBytes = files.get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json.');
  const manifest = JSON.parse(decoder.decode(manifestBytes)) as BundleManifest;

  // `key` is carried through verbatim. It is not derived from the bytes, so a reseal
  // must preserve it: dropping it would leave every frame digest-valid and every
  // frame unreachable, because the transport addresses frames by key.
  const sealed: {
    path: string;
    sha256: string;
    bytes: number;
    media_type?: string | null;
    key?: string | null;
  }[] = [];
  for (const entry of manifest.files) {
    const bytes = files.get(entry.path);
    if (bytes === undefined) throw new Error(`manifest lists ${entry.path}, which is absent.`);
    sealed.push({
      path: entry.path,
      sha256: await sha256Hex(bytes),
      bytes: bytes.byteLength,
      ...(entry.media_type === undefined ? {} : { media_type: entry.media_type }),
      ...(entry.key === undefined ? {} : { key: entry.key }),
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

/**
 * Manifest integrity, and nothing else. It answers one question — *are these the bytes that
 * were sealed?* — and says nothing about whether the ledger inside verifies, which is the
 * custody surface's claim and is expected to be unprovable for a staged fixture.
 */
export function manifestIntegrityVerifier(): BundleVerifier {
  return {
    name: 'propagation-suite:manifest-integrity',
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
    source: new MemoryBundleSource('propagation-suite', new Map(files)),
    registry: contractRegistry(),
    verifier: manifestIntegrityVerifier(),
  });
}
