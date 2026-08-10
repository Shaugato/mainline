// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Fixture bytes and the tampering helpers, for the evidence-view tests.
 *
 * Deliberately a local copy of the glob rather than an import from
 * `tests/unit/data/_support.ts`: that file belongs to the data-contracts-replay worker,
 * and a test suite whose fixtures can be changed out from under it by another worker's
 * refactor is a test suite that goes green for reasons nobody chose.
 *
 * Every tamper below is a REAL mutation of the sealed bytes — a flipped hex digit, a
 * truncated file, a deleted file, a smuggled file. None of them is a mocked verdict.
 * The audit under test hashes what it is given with WebCrypto, so a tamper test that
 * passes proves the arithmetic ran; the intact case is asserted in the same file so the
 * refusal cannot be vacuous.
 *
 * Not a `.test.ts`, so Vitest's `include` does not collect it.
 */

import type { BundleSource } from '../../../src/data/bundle';
import type { ListableBundleSource } from '../../../src/features/evidence/source';

const BUNDLE_ROOT = '/fixtures/bundles/blk-07/';

const RAW_FILES = import.meta.glob<string>('/fixtures/bundles/blk-07/**/*', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

/**
 * `manifest.seed.json` is the INPUT to sealing (docs/evidence-bundle.md §8.2), not
 * captured evidence. The producer excludes it from `manifest.files`, so a directory
 * listing that included it would report a legitimate producer input as a smuggled file.
 */
const NOT_BUNDLE_CONTENT: ReadonlySet<string> = new Set(['manifest.seed.json']);

/** The sealed bundle, exactly as committed. */
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
      'no fixture files were globbed from fixtures/bundles/blk-07. Every assertion in this ' +
        'directory would otherwise iterate an empty collection and pass.',
    );
  }
  return files;
}

/** SHA-256 of `fixtures/bundles/blk-07/manifest.json`, verified with `sha256sum`. */
export const FIXTURE_MANIFEST_SHA256 =
  '4e639c85e0f46f5d3deddfc63bda969c81de599821cb54ece462883c003eb5f3';

/** The permit frame the transport-integration test asks for. */
export const FIXTURE_PERMIT_ID = '018f3a2f-1104-7c88-b3aa-77c1de40e2b1';

/**
 * The bundle path of the frame answering a canonical request key.
 *
 * Read out of the SEALED manifest rather than computed. Frame names are content
 * addresses (`<METHOD>-<sha256(key)[:16]>.json`) written by `scripts/capture-bundle.ts`,
 * and `src/**` computes no digests, so `manifest.files[].key` is the index — for a test
 * as for the transport. Spelling a name here would put a second, unchecked copy of the
 * naming scheme in the test tree, which is exactly what the old encoding did.
 */
export function frameAddressOf(requestKey: string): string {
  const manifestBytes = bundleFiles().get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json.');
  const manifest = JSON.parse(decoder.decode(manifestBytes)) as {
    files: { path: string; key?: string | null }[];
  };
  const entry = manifest.files.find((file) => file.key === requestKey);
  if (entry === undefined) {
    throw new Error(`the sealed blk-07 manifest lists no frame answering "${requestKey}".`);
  }
  return entry.path;
}

// ── Sources ────────────────────────────────────────────────────────────────

/** A source over a byte map that CAN enumerate itself, so `unlisted` is exercised. */
export class ListableMemorySource implements ListableBundleSource {
  readonly id: string;
  private readonly files: ReadonlyMap<string, Uint8Array>;

  constructor(id: string, files: ReadonlyMap<string, Uint8Array>) {
    this.id = id;
    this.files = files;
  }

  read(path: string): Promise<Uint8Array> {
    const bytes = this.files.get(path);
    return bytes === undefined
      ? Promise.reject(new Error(`${this.id}: no such file in bundle: ${path}`))
      : Promise.resolve(bytes);
  }

  list(): Promise<readonly string[]> {
    return Promise.resolve([...this.files.keys()]);
  }
}

/** The same bytes behind a source that CANNOT enumerate itself — the static-host case. */
export class OpaqueMemorySource implements BundleSource {
  readonly id: string;
  private readonly files: ReadonlyMap<string, Uint8Array>;

  constructor(id: string, files: ReadonlyMap<string, Uint8Array>) {
    this.id = id;
    this.files = files;
  }

  read(path: string): Promise<Uint8Array> {
    const bytes = this.files.get(path);
    return bytes === undefined
      ? Promise.reject(new Error(`${this.id}: no such file in bundle: ${path}`))
      : Promise.resolve(bytes);
  }
}

// ── Tampering ──────────────────────────────────────────────────────────────

function readText(files: ReadonlyMap<string, Uint8Array>, path: string): string {
  const bytes = files.get(path);
  if (bytes === undefined) throw new Error(`fixture has no ${path}`);
  return decoder.decode(bytes);
}

function writeText(files: Map<string, Uint8Array>, path: string, text: string): void {
  files.set(path, encoder.encode(text));
}

/** Rewrites `manifest.json` through a plain-object transform. */
export function editManifest(
  files: Map<string, Uint8Array>,
  edit: (manifest: Record<string, unknown>) => void,
): Map<string, Uint8Array> {
  const manifest = JSON.parse(readText(files, 'manifest.json')) as Record<string, unknown>;
  edit(manifest);
  writeText(files, 'manifest.json', JSON.stringify(manifest, null, 2));
  return files;
}

interface ManifestEntry {
  path: string;
  sha256: string;
  bytes: number;
  media_type?: string | null;
  key?: string | null;
}

function entriesOf(manifest: Record<string, unknown>): ManifestEntry[] {
  const files = manifest.files;
  if (!Array.isArray(files)) throw new Error('manifest.files is not an array');
  return files as ManifestEntry[];
}

/** Flips ONE hex digit of ONE declared digest. The minimal possible tamper. */
export function flipDeclaredDigest(files: Map<string, Uint8Array>, path: string): Map<string, Uint8Array> {
  return editManifest(files, (manifest) => {
    const entry = entriesOf(manifest).find((candidate) => candidate.path === path);
    if (entry === undefined) throw new Error(`manifest does not list ${path}`);
    const first = entry.sha256[0];
    if (first === undefined) throw new Error(`manifest declares an empty digest for ${path}`);
    entry.sha256 = (first === '0' ? '1' : '0') + entry.sha256.slice(1);
  });
}

/** Truncates a file's bytes without touching the manifest. */
export function truncateFile(
  files: Map<string, Uint8Array>,
  path: string,
  keep: number,
): Map<string, Uint8Array> {
  const bytes = files.get(path);
  if (bytes === undefined) throw new Error(`fixture has no ${path}`);
  files.set(path, bytes.slice(0, keep));
  return files;
}

/** Deletes a file the manifest still lists. */
export function deleteFile(files: Map<string, Uint8Array>, path: string): Map<string, Uint8Array> {
  if (!files.delete(path)) throw new Error(`fixture has no ${path}`);
  return files;
}

/** Adds a file the manifest does not list. */
export function smuggleFile(
  files: Map<string, Uint8Array>,
  path: string,
  content: string,
): Map<string, Uint8Array> {
  writeText(files, path, content);
  return files;
}

/**
 * Removes a frame's request key from the manifest, leaving the file in place.
 *
 * The bundle still verifies — every digest is untouched — and the frame becomes
 * unreachable, because a frame is addressed by `manifest.files[].key` and this one no
 * longer has one. That is the failure the evidence view has to SEE rather than skip.
 */
export function dropFrameKey(files: Map<string, Uint8Array>, path: string): Map<string, Uint8Array> {
  return editManifest(files, (manifest) => {
    const entry = entriesOf(manifest).find((candidate) => candidate.path === path);
    if (entry === undefined) throw new Error(`manifest does not list ${path}`);
    delete entry.key;
  });
}

/** Renames a frame file (and its manifest entry) to a non-canonical name. */
export function renameFrame(
  files: Map<string, Uint8Array>,
  from: string,
  to: string,
): Map<string, Uint8Array> {
  const bytes = files.get(from);
  if (bytes === undefined) throw new Error(`fixture has no ${from}`);
  files.delete(from);
  files.set(to, bytes);
  return editManifest(files, (manifest) => {
    const entry = entriesOf(manifest).find((candidate) => candidate.path === from);
    if (entry === undefined) throw new Error(`manifest does not list ${from}`);
    entry.path = to;
  });
}
