// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Fixture scaffolding for the gate suite.
 *
 * ── WHY THE TESTS READ THE BUNDLE RATHER THAN LITERALS ───────────────────────────
 *
 * `docs/leads/ui.md` §1.5 names the one assertion this domain must get right: the gate
 * spec asserts the refusal bar renders `gate_closed_when_issued` and SQLSTATE `23514`
 * **taken from the bundle, not from a literal in the test**. A test that hardcodes the
 * string it expects passes just as happily against a component that hardcodes the string
 * it renders, and the pair of them assert nothing at all.
 *
 * So every expectation in this suite is read out of `fixtures/`, and `mutate*` below
 * exists so the suite can prove the coupling directly: change the fixture, and the
 * rendered text must change with it.
 *
 * ── THE VERIFIER IS REAL ─────────────────────────────────────────────────────────
 *
 * `BundleTransport` has no default verifier and no skip switch, on purpose. The one
 * here computes SHA-256 with WebCrypto over the actual bytes — a stand-in for the
 * in-browser verifier the custody worker owns, confined to `tests/`, and it genuinely
 * fails on a tampered file. That is what makes `resealBundle` necessary: a mutated
 * fixture only renders if its manifest is re-sealed, which is the transport's gate
 * working rather than being bypassed.
 */

import { contractRegistry } from '../../../src/data/contracts';
import {
  BundleTransport,
  MemoryBundleSource,
  type BundleFinding,
  type BundleManifest,
  type BundleVerificationInput,
  type BundleVerificationReport,
  type BundleVerifier,
} from '../../../src/data/bundle';
import type { MainlineTransport } from '../../../src/data/transport';

// ── Bundle bytes ───────────────────────────────────────────────────────────

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
      'tests/unit/gate/_support.ts: the fixture bundle glob matched nothing. Every assertion ' +
        'in this suite would then be vacuous. Run `node scripts/capture-bundle.ts stage ' +
        '--sources fixtures/sources/blk-07 --out fixtures/bundles/blk-07`.',
    );
  }
  return files;
}

/**
 * A source payload, parsed. Used by the pure-model tests, which have no transport and
 * should not need one to read the same bytes the bundle carries.
 */
// `T` is the CALLER's assertion about JSON read off disk. The rule below flags this
// shape in production APIs, where an unchecked assertion hides behind a signature.
// Here the alternative is an `as` at every call site, which hides the same assertion
// in more places; the payloads are validated against their contracts by the transport.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
export function sourcePayload<T>(name: string): T {
  const key = `/fixtures/sources/blk-07/payloads/${name}`;
  const text = RAW_PAYLOADS[key];
  if (text === undefined) {
    throw new Error(
      `tests/unit/gate/_support.ts: no source payload ${name}. Available: ` +
        Object.keys(RAW_PAYLOADS).join(', '),
    );
  }
  return JSON.parse(text) as T;
}

// ── Frames ─────────────────────────────────────────────────────────────────

export interface Frame {
  readonly frame_version: 1;
  readonly key: string;
  readonly request: { readonly method: string; readonly path: string };
  readonly response: { readonly status: number; readonly body_b64: string };
  readonly captured_at: string;
}

/**
 * The bundle path of the frame answering a canonical request key.
 *
 * Read out of the SEALED manifest rather than computed. Frame names are content
 * addresses (`<METHOD>-<sha256(key)[:16]>.json`) written by `scripts/capture-bundle.ts`,
 * and `src/**` computes no digests, so the manifest's `key` field is the index — here as
 * it is for the transport itself.
 */
export function framePath(requestKey: string): string {
  const manifestBytes = bundleFiles().get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json.');
  const manifest = JSON.parse(decoder.decode(manifestBytes)) as BundleManifest;
  const entry = manifest.files.find((file) => file.key === requestKey);
  if (entry === undefined) {
    throw new Error(
      `the sealed blk-07 manifest lists no frame answering "${requestKey}". Re-run ` +
        '`node scripts/capture-bundle.ts stage --sources fixtures/sources/blk-07 --out fixtures/bundles/blk-07`.',
    );
  }
  return entry.path;
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

/** The decoded envelope a frame carries. */
// `T` is the CALLER's assertion about JSON read off disk. The rule below flags this
// shape in production APIs, where an unchecked assertion hides behind a signature.
// Here the alternative is an `as` at every call site, which hides the same assertion
// in more places; the payloads are validated against their contracts by the transport.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- fixture reader
export function frameEnvelope<T>(files: ReadonlyMap<string, Uint8Array>, path: string): T {
  const raw = files.get(path);
  if (raw === undefined) {
    throw new Error(`no frame at ${path}. Present: ${[...files.keys()].sort().join(', ')}`);
  }
  const frame = JSON.parse(decoder.decode(raw)) as Frame;
  return JSON.parse(decoder.decode(fromBase64(frame.response.body_b64))) as T;
}

/**
 * Rewrites one frame's response envelope and re-seals the manifest over the result.
 *
 * Re-sealing is not a convenience — it is the point. The transport refuses any file
 * whose digest disagrees with the manifest, so a mutated frame that renders at all
 * proves the mutation went through the same integrity gate the untouched bundle does.
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
  next.set(
    'manifest.json',
    encoder.encode(JSON.stringify({ ...manifest, files: sealed }, null, 2)),
  );
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
 * Manifest integrity, and nothing else. It answers one question — *are these the bytes
 * that were sealed?* — and says nothing about whether the ledger inside verifies, which
 * is the custody surface's claim and is expected to be unprovable for a staged fixture.
 */
export function manifestIntegrityVerifier(): BundleVerifier {
  return {
    name: 'gate-suite:manifest-integrity',
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
    source: new MemoryBundleSource('gate-suite', new Map(files)),
    registry: contractRegistry(),
    verifier: manifestIntegrityVerifier(),
  });
}

// ── The subject under test ─────────────────────────────────────────────────

/**
 * The permit the staged bundle is about, READ OUT OF THE FIXTURE.
 *
 * Retyping the UUID here would put a second copy of the truth in the test tree, and the
 * copy would be the one that silently stopped matching.
 */
export function permitId(): string {
  const permit = sourcePayload<{ data: { permit_id: string } }>('permit.json');
  return permit.data.permit_id;
}

export function mergeFramePath(): string {
  return framePath(`POST /v1/permits/${permitId()}/merge`);
}
